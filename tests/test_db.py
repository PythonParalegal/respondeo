"""
test_db.py — regression tests for db_manager.py

Covers: schema creation, migrations, audit logging, case settings,
clawback workflow, supplemental-production Bates persistence, and
get_clawback_summary().
"""
import sqlite3
import pytest
import db_manager


# ---------------------------------------------------------------------------
# Schema and migrations
# ---------------------------------------------------------------------------

class TestInitDb:

    def test_creates_documents_table(self, case_folder):
        conn = db_manager.get_connection(case_folder)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "documents" in tables

    def test_creates_audit_log_table(self, case_folder):
        conn = db_manager.get_connection(case_folder)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "audit_log" in tables

    def test_creates_case_settings_table(self, case_folder):
        conn = db_manager.get_connection(case_folder)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "case_settings" in tables

    def test_clawback_columns_exist(self, case_folder):
        conn = db_manager.get_connection(case_folder)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
        conn.close()
        assert "clawback_status" in cols
        assert "clawback_date" in cols

    def test_migration_idempotent(self, case_folder):
        """Calling init_db a second time on an existing DB must not raise."""
        db_manager.init_db(case_folder)  # second call
        conn = db_manager.get_connection(case_folder)
        count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        conn.close()
        assert count == 0  # no phantom rows


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

class TestAuditLog:

    def test_log_audit_writes_entry(self, case_folder):
        db_manager.log_audit(
            case_folder, "TAG_APPLIED",
            username="alice", control_number="DOC-00001",
            module="Review", details="Applied Privileged tag",
        )
        conn = db_manager.get_connection(case_folder)
        row = conn.execute(
            "SELECT action, username, control_number FROM audit_log WHERE action='TAG_APPLIED'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["action"] == "TAG_APPLIED"
        assert row["username"] == "alice"
        assert row["control_number"] == "DOC-00001"

    def test_log_audit_never_raises_on_bad_folder(self):
        """log_audit must swallow all exceptions — never raise."""
        db_manager.log_audit("/nonexistent/path/that/does/not/exist", "TAG_APPLIED")
        # If we reach here, the never-raise contract is upheld

    def test_log_audit_batch_writes_multiple(self, case_folder):
        entries = [
            {"action": "DOCUMENT_INGESTED", "username": "bob", "control_number": f"DOC-{i:05d}"}
            for i in range(5)
        ]
        db_manager.log_audit_batch(case_folder, entries)
        conn = db_manager.get_connection(case_folder)
        count = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='DOCUMENT_INGESTED'"
        ).fetchone()[0]
        conn.close()
        assert count == 5

    def test_log_audit_with_provided_conn_does_not_close_it(self, case_folder):
        """When caller passes conn, log_audit must not close it."""
        conn = db_manager.get_connection(case_folder)
        db_manager.log_audit(case_folder, "TAG_APPLIED", username="alice", conn=conn)
        # Connection still usable — would raise sqlite3.ProgrammingError if closed
        cur = conn.execute("SELECT 1").fetchone()
        assert cur is not None
        conn.close()

    def test_log_audit_with_provided_conn_does_not_commit(self, case_folder):
        """When caller passes conn, log_audit must not commit (caller owns transaction)."""
        conn = db_manager.get_connection(case_folder)
        db_manager.log_audit(case_folder, "TAG_APPLIED", username="bob", conn=conn)
        # Without conn.commit(), a separate connection should NOT see the row yet.
        # SQLite WAL: readers see committed snapshot; uncommitted writes invisible to other conns.
        conn2 = db_manager.get_connection(case_folder)
        row = conn2.execute(
            "SELECT action FROM audit_log WHERE username='bob'"
        ).fetchone()
        conn2.close()
        assert row is None, "log_audit should not commit when caller owns conn"
        # Now caller commits — second conn should see the row
        conn.commit()
        conn3 = db_manager.get_connection(case_folder)
        row3 = conn3.execute(
            "SELECT action FROM audit_log WHERE username='bob'"
        ).fetchone()
        conn3.close()
        conn.close()
        assert row3 is not None
        assert row3["action"] == "TAG_APPLIED"

    def test_log_audit_batch_with_provided_conn_does_not_close_it(self, case_folder):
        """log_audit_batch parallel to log_audit: caller owns conn lifecycle."""
        conn = db_manager.get_connection(case_folder)
        entries = [{"action": "BATCH_TAG", "username": f"u{i}"} for i in range(3)]
        db_manager.log_audit_batch(case_folder, entries, conn=conn)
        # Connection must still be open
        cur = conn.execute("SELECT 1").fetchone()
        assert cur is not None
        conn.commit()  # caller commits
        conn.close()


# ---------------------------------------------------------------------------
# Case status
# ---------------------------------------------------------------------------

class TestCaseStatus:

    def test_default_status_is_active(self, case_folder):
        assert db_manager.get_case_status(case_folder) == "Active"

    def test_set_and_get_case_status(self, case_folder):
        db_manager.set_case_status(case_folder, "Closed")
        assert db_manager.get_case_status(case_folder) == "Closed"

    def test_reopen_case(self, case_folder):
        db_manager.set_case_status(case_folder, "Closed")
        db_manager.set_case_status(case_folder, "Active")
        assert db_manager.get_case_status(case_folder) == "Active"


# ---------------------------------------------------------------------------
# Clawback workflow
# ---------------------------------------------------------------------------

class TestClawback:

    def _insert_doc(self, case_folder, cn):
        conn = db_manager.get_connection(case_folder)
        conn.execute(
            "INSERT OR IGNORE INTO documents (control_number, file_name) VALUES (?, ?)",
            (cn, f"{cn}.pdf"),
        )
        conn.commit()
        conn.close()

    def test_mark_clawback_demanded(self, case_folder):
        self._insert_doc(case_folder, "DOC-00001")
        db_manager.mark_clawback(
            case_folder, "DOC-00001", "Clawback_Demanded",
            "2026-03-12", "Counsel demanded return", "alice"
        )
        conn = db_manager.get_connection(case_folder)
        row = conn.execute(
            "SELECT clawback_status, clawback_date FROM documents WHERE control_number='DOC-00001'"
        ).fetchone()
        conn.close()
        assert row["clawback_status"] == "Clawback_Demanded"
        assert row["clawback_date"] == "2026-03-12"

    def test_mark_clawback_resolved(self, case_folder):
        self._insert_doc(case_folder, "DOC-00002")
        db_manager.mark_clawback(
            case_folder, "DOC-00002", "Clawback_Demanded", "2026-03-10", "", "alice"
        )
        db_manager.mark_clawback(
            case_folder, "DOC-00002", "Clawback_Resolved", "2026-03-12", "Resolved", "alice"
        )
        conn = db_manager.get_connection(case_folder)
        row = conn.execute(
            "SELECT clawback_status FROM documents WHERE control_number='DOC-00002'"
        ).fetchone()
        conn.close()
        assert row["clawback_status"] == "Clawback_Resolved"

    def test_mark_clawback_writes_audit_entry(self, case_folder):
        self._insert_doc(case_folder, "DOC-00003")
        db_manager.mark_clawback(
            case_folder, "DOC-00003", "Clawback_Demanded",
            "2026-03-12", "Test demand", "alice"
        )
        conn = db_manager.get_connection(case_folder)
        row = conn.execute(
            "SELECT action FROM audit_log WHERE action='CLAWBACK_MARKED'"
        ).fetchone()
        conn.close()
        assert row is not None

    def test_get_clawback_summary_returns_demanded(self, case_folder):
        for cn in ("DOC-A", "DOC-B", "DOC-C"):
            self._insert_doc(case_folder, cn)
        db_manager.mark_clawback(case_folder, "DOC-A", "Clawback_Demanded", "2026-03-12", "", "u")
        db_manager.mark_clawback(case_folder, "DOC-B", "Clawback_Resolved", "2026-03-11", "", "u")
        # DOC-C has no clawback status
        summary = db_manager.get_clawback_summary(case_folder)
        cns = {r["control_number"] for r in summary}
        assert "DOC-A" in cns
        assert "DOC-B" in cns
        assert "DOC-C" not in cns

    def test_get_clawback_summary_empty_when_none(self, case_folder):
        assert db_manager.get_clawback_summary(case_folder) == []


# ---------------------------------------------------------------------------
# Supplemental Production — last Bates info persistence
# ---------------------------------------------------------------------------

class TestLastBatesInfo:

    def test_returns_none_when_no_prior_production(self, case_folder):
        assert db_manager.get_last_bates_info(case_folder) is None

    def test_save_and_retrieve_round_trip(self, case_folder):
        db_manager.save_last_bates_info(
            case_folder, prefix="ABC", end_num=150, prod_name="PRODUCTION_001", padding=6
        )
        info = db_manager.get_last_bates_info(case_folder)
        assert info is not None
        assert info["prefix"] == "ABC"
        assert info["end_num"] == 150
        assert info["prod_name"] == "PRODUCTION_001"
        assert info["padding"] == 6

    def test_overwrite_with_new_production(self, case_folder):
        db_manager.save_last_bates_info(case_folder, "ABC", 150, "PRODUCTION_001", 6)
        db_manager.save_last_bates_info(case_folder, "ABC", 275, "PRODUCTION_002", 6)
        info = db_manager.get_last_bates_info(case_folder)
        assert info["end_num"] == 275
        assert info["prod_name"] == "PRODUCTION_002"

    def test_next_start_number_is_end_plus_one(self, case_folder):
        db_manager.save_last_bates_info(case_folder, "XYZ", 99, "VOL1", 6)
        info = db_manager.get_last_bates_info(case_folder)
        assert info["end_num"] + 1 == 100


# ---------------------------------------------------------------------------
# Privilege status — caller-owned-conn contract (Flag #18 narrow scaffolding)
# ---------------------------------------------------------------------------

class TestPrivilegeStatusConnOwnership:
    """Pin the caller-owned-conn contract for get_privilege_status / set_privilege_status."""

    def test_set_privilege_status_default_path_commits(self, case_folder):
        """Default-call (conn=None) commits its own write."""
        conn = db_manager.get_connection(case_folder)
        conn.execute("INSERT INTO documents (control_number) VALUES ('DOC-A')")
        conn.commit()
        conn.close()
        db_manager.set_privilege_status(case_folder, 'DOC-A', 'Withhold')
        assert db_manager.get_privilege_status(case_folder, 'DOC-A') == 'Withhold'

    def test_set_privilege_status_with_provided_conn_does_not_commit(self, case_folder):
        """When caller passes conn, set_privilege_status must not commit."""
        conn = db_manager.get_connection(case_folder)
        conn.execute("INSERT INTO documents (control_number) VALUES ('DOC-B')")
        conn.commit()
        db_manager.set_privilege_status(case_folder, 'DOC-B', 'Redact', conn=conn)
        # Separate reader should NOT see the redact tag yet
        conn_reader = db_manager.get_connection(case_folder)
        row = conn_reader.execute(
            "SELECT privilege_status FROM documents WHERE control_number='DOC-B'"
        ).fetchone()
        conn_reader.close()
        assert row['privilege_status'] is None, "set_privilege_status should not commit with caller-owned conn"
        conn.commit()  # now caller commits
        assert db_manager.get_privilege_status(case_folder, 'DOC-B') == 'Redact'
        conn.close()

    def test_get_privilege_status_with_provided_conn_does_not_close_it(self, case_folder):
        """get_privilege_status with caller's conn must not close it."""
        conn = db_manager.get_connection(case_folder)
        conn.execute("INSERT INTO documents (control_number, privilege_status) VALUES ('DOC-C', 'Withhold')")
        conn.commit()
        result = db_manager.get_privilege_status(case_folder, 'DOC-C', conn=conn)
        assert result == 'Withhold'
        # Conn still usable
        cur = conn.execute("SELECT 1").fetchone()
        assert cur is not None
        conn.close()

    def test_round_trip_set_then_get_via_shared_conn(self, case_folder):
        """End-to-end: set + get on a single shared conn proves the pattern works."""
        conn = db_manager.get_connection(case_folder)
        conn.execute("INSERT INTO documents (control_number) VALUES ('DOC-D')")
        # No commit — DOC-D row only visible to this conn
        db_manager.set_privilege_status(case_folder, 'DOC-D', 'Withhold', conn=conn)
        # Same-conn read sees the uncommitted write (sqlite3 default isolation)
        result = db_manager.get_privilege_status(case_folder, 'DOC-D', conn=conn)
        assert result == 'Withhold'
        conn.commit()
        conn.close()
