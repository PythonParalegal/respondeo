"""
test_production_status.py — regression tests for production_runs.status and
production_runs.direction columns added in beta-2.10.

Covers:
- Migration idempotency (columns exist after init_db; re-running init_db is safe)
- **Upgrade-path backfill**: pre-existing rows (created before the migration)
  are flipped to status='finalized', direction='outbound'. This exercises the
  actual code path where rows exist *before* the ALTER TABLE runs — which is
  what the sentinel-guarded backfill is for. Prior tests only created rows
  after init_db completed, missing this path.
- record_production_run() accepts and persists status + direction
- update_production_status() round-trip + never-raise contract
- get_productions_with_staging_files() filters to outbound
- get_production_history() filters by direction
"""
import os
import sqlite3
import pytest


# ---------------------------------------------------------------------------
# Schema + migration
# ---------------------------------------------------------------------------

def _columns(case_folder, table):
    import db_manager
    conn = db_manager.get_connection(case_folder)
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    finally:
        conn.close()


class TestSchemaMigration:

    def test_status_column_exists(self, case_folder):
        assert 'status' in _columns(case_folder, 'production_runs')

    def test_direction_column_exists(self, case_folder):
        assert 'direction' in _columns(case_folder, 'production_runs')

    def test_init_db_idempotent(self, case_folder):
        """Running init_db twice must not raise (ALTER TABLE ... ADD COLUMN
        would otherwise error on the second call; the migration loop catches it)."""
        import db_manager
        db_manager.init_db(case_folder)  # second call
        assert 'status' in _columns(case_folder, 'production_runs')
        assert 'direction' in _columns(case_folder, 'production_runs')

    def test_backfill_sentinel_set(self, case_folder):
        """The one-time backfill sentinel must be recorded in case_settings."""
        import db_manager
        conn = db_manager.get_connection(case_folder)
        try:
            row = conn.execute(
                "SELECT 1 FROM case_settings WHERE setting_key = '_production_runs_status_backfill_v1'"
            ).fetchone()
            assert row is not None
        finally:
            conn.close()


class TestBackfillUpgradePath:
    """Simulates the actual upgrade path: an existing case DB created before
    beta-2.10 (old schema with no status/direction columns) with pre-existing
    production_runs rows. Running init_db() must add the columns AND flip
    the existing rows to 'finalized'/'outbound'.

    This is the failure mode the previous WHERE-IS-NULL backfill missed:
    ALTER TABLE ADD COLUMN ... DEFAULT populates existing rows with the default
    ('in_progress') immediately, so `WHERE status IS NULL` would match zero
    rows and the backfill would be a silent no-op.
    """

    def _make_old_schema_case(self, tmp_path):
        """Create a case folder with production_runs in its pre-beta-2.10
        shape: no status, no direction columns."""
        folder = str(tmp_path / "upgrade_case")
        os.makedirs(folder)
        db_path = os.path.join(folder, "case.db")

        conn = sqlite3.connect(db_path)
        # OLD production_runs schema (pre-beta-2.10)
        conn.execute("""
            CREATE TABLE production_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                production_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                format TEXT NOT NULL,
                mode TEXT NOT NULL,
                bates_prefix TEXT,
                bates_start TEXT,
                bates_end TEXT,
                document_count INTEGER DEFAULT 0,
                withheld_count INTEGER DEFAULT 0,
                redacted_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                endorsement_text TEXT,
                settings_json TEXT,
                UNIQUE(production_name)
            )
        """)
        # Pre-existing historical row
        conn.execute("""
            INSERT INTO production_runs
                (production_name, created_at, created_by, format, mode, document_count,
                 bates_prefix, bates_start, bates_end)
            VALUES ('OLD_PROD_001', '2026-01-01T00:00:00Z', 'u', 'PDF', 'Simple Production', 10,
                    'ABC', 'ABC-000001', 'ABC-000010')
        """)
        conn.commit()
        conn.close()
        return folder

    def test_columns_added_to_old_schema(self, tmp_path):
        """After init_db runs on an old-schema DB, the new columns must exist."""
        import db_manager
        folder = self._make_old_schema_case(tmp_path)
        db_manager.init_db(folder)
        assert 'status' in _columns(folder, 'production_runs')
        assert 'direction' in _columns(folder, 'production_runs')

    def test_preexisting_row_flipped_to_finalized(self, tmp_path):
        """The core upgrade-path assertion: a pre-existing row must be flipped
        from the DEFAULT ('in_progress') to 'finalized' by the backfill."""
        import db_manager
        folder = self._make_old_schema_case(tmp_path)
        db_manager.init_db(folder)
        run = db_manager.get_production_run(folder, 'OLD_PROD_001')
        assert run is not None
        assert run['status'] == 'finalized', (
            f"Pre-existing row was not backfilled. Got status={run['status']!r}. "
            f"This indicates the WHERE-IS-NULL bug regressed: ALTER TABLE ADD COLUMN "
            f"DEFAULT populates existing rows with the default, not NULL."
        )
        assert run['direction'] == 'outbound'

    def test_backfill_does_not_run_twice(self, tmp_path):
        """Second init_db() call must not re-flip rows. Simulates a user who
        opens their case, closes it, and reopens — the app should not clobber
        status changes made by the state machine in between.
        """
        import db_manager
        folder = self._make_old_schema_case(tmp_path)
        db_manager.init_db(folder)
        # Between init calls, simulate the Pass 1 state machine starting a new
        # production and moving it to in_progress
        db_manager.record_production_run(folder, {
            'production_name': 'NEW_PROD',
            'created_at': '2026-04-16T17:00:00Z',
            'created_by': 'u',
            'format': 'PDF',
            'mode': 'Simple Production',
            'status': 'in_progress',
        })
        # Second init_db — should NOT re-backfill NEW_PROD to 'finalized'
        db_manager.init_db(folder)
        new_run = db_manager.get_production_run(folder, 'NEW_PROD')
        assert new_run['status'] == 'in_progress', (
            f"Second init_db re-ran the backfill. Got {new_run['status']!r}. "
            f"Sentinel guard failed."
        )

    def test_fresh_case_also_sets_sentinel(self, case_folder):
        """Fresh case (no pre-existing rows) also sets the sentinel, so
        subsequent init_db calls are cheap no-ops on the backfill."""
        import db_manager
        conn = db_manager.get_connection(case_folder)
        try:
            sentinel = conn.execute(
                "SELECT 1 FROM case_settings WHERE setting_key = '_production_runs_status_backfill_v1'"
            ).fetchone()
            assert sentinel is not None
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# record_production_run with status + direction
# ---------------------------------------------------------------------------

class TestRecordProductionRunStatus:

    def test_default_status_is_in_progress(self, case_folder):
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'PROD_A',
            'created_at': '2026-04-16T17:00:00Z',
            'created_by': 'test',
            'format': 'PDF',
            'mode': 'Simple Production',
        })
        run = db_manager.get_production_run(case_folder, 'PROD_A')
        assert run['status'] == 'in_progress'
        assert run['direction'] == 'outbound'

    def test_explicit_status_persists(self, case_folder):
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'PROD_B',
            'created_at': '2026-04-16T17:00:00Z',
            'created_by': 'test',
            'format': 'PDF',
            'mode': 'Simple Production',
            'status': 'pass1_complete',
        })
        assert db_manager.get_production_run(case_folder, 'PROD_B')['status'] == 'pass1_complete'

    def test_inbound_direction_persists(self, case_folder):
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'INBOUND: OCA - VOL001',
            'created_at': '2026-04-16T17:00:00Z',
            'created_by': 'test',
            'format': 'Native',
            'mode': 'Inbound Ingest',
            'direction': 'inbound',
            'status': 'finalized',
        })
        run = db_manager.get_production_run(case_folder, 'INBOUND: OCA - VOL001')
        assert run['direction'] == 'inbound'
        assert run['status'] == 'finalized'

    def test_insert_or_replace_state_machine(self, case_folder):
        """Calling record_production_run twice with the same name updates status."""
        import db_manager
        base = {
            'production_name': 'PROD_C',
            'created_at': '2026-04-16T17:00:00Z',
            'created_by': 'test',
            'format': 'PDF',
            'mode': 'Simple Production',
        }
        db_manager.record_production_run(case_folder, {**base, 'status': 'in_progress'})
        db_manager.record_production_run(case_folder, {**base, 'status': 'pass1_complete'})
        db_manager.record_production_run(case_folder, {**base, 'status': 'finalized'})
        assert db_manager.get_production_run(case_folder, 'PROD_C')['status'] == 'finalized'


# ---------------------------------------------------------------------------
# update_production_status
# ---------------------------------------------------------------------------

class TestUpdateProductionStatus:

    def test_round_trip(self, case_folder):
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'PROD_D',
            'created_at': '2026-04-16T17:00:00Z',
            'created_by': 'test',
            'format': 'PDF',
            'mode': 'Simple Production',
        })
        db_manager.update_production_status(case_folder, 'PROD_D', 'pass1_complete')
        assert db_manager.get_production_run(case_folder, 'PROD_D')['status'] == 'pass1_complete'

    def test_missing_production_name_is_noop(self, case_folder):
        """Updating a non-existent production_name must not raise."""
        import db_manager
        db_manager.update_production_status(case_folder, 'DOES_NOT_EXIST', 'finalized')
        # no exception = pass

    def test_never_raise_on_bad_case_folder(self, tmp_path):
        """Helper is never-raise contract — bogus case folder must not raise."""
        import db_manager
        db_manager.update_production_status(str(tmp_path / 'nonexistent'), 'X', 'Y')
        # no exception = pass


# ---------------------------------------------------------------------------
# get_productions_with_staging_files
# ---------------------------------------------------------------------------

class TestGetProductionsWithStagingFiles:

    def test_returns_outbound_only(self, case_folder):
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'OUT_1', 'created_at': 't', 'created_by': 'u',
            'format': 'PDF', 'mode': 'Simple Production', 'status': 'in_progress',
        })
        db_manager.record_production_run(case_folder, {
            'production_name': 'INBOUND: P - V', 'created_at': 't', 'created_by': 'u',
            'format': 'Native', 'mode': 'Inbound Ingest',
            'direction': 'inbound', 'status': 'finalized',
        })
        result = db_manager.get_productions_with_staging_files(case_folder)
        names = [r[0] for r in result]
        assert 'OUT_1' in names
        assert 'INBOUND: P - V' not in names

    def test_returns_status_tuple(self, case_folder):
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'OUT_2', 'created_at': 't', 'created_by': 'u',
            'format': 'PDF', 'mode': 'Simple Production', 'status': 'aborted',
        })
        result = db_manager.get_productions_with_staging_files(case_folder)
        assert ('OUT_2', 'aborted') in result


# ---------------------------------------------------------------------------
# get_production_history
# ---------------------------------------------------------------------------

class TestGetProductionHistory:

    def _seed(self, case_folder):
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'HIST_OUT',
            'created_at': '2026-04-16T10:00:00Z', 'created_by': 'u',
            'format': 'PDF', 'mode': 'Simple Production', 'status': 'finalized',
        })
        db_manager.record_production_run(case_folder, {
            'production_name': 'INBOUND: OCA - VOL001',
            'created_at': '2026-04-16T11:00:00Z', 'created_by': 'u',
            'format': 'Native', 'mode': 'Inbound Ingest',
            'direction': 'inbound', 'status': 'finalized',
        })

    def test_direction_none_returns_both(self, case_folder):
        import db_manager
        self._seed(case_folder)
        names = [r['production_name'] for r in db_manager.get_production_history(case_folder)]
        assert 'HIST_OUT' in names
        assert 'INBOUND: OCA - VOL001' in names

    def test_outbound_filter(self, case_folder):
        import db_manager
        self._seed(case_folder)
        names = [r['production_name'] for r in db_manager.get_production_history(case_folder, direction='outbound')]
        assert names == ['HIST_OUT']

    def test_inbound_filter(self, case_folder):
        import db_manager
        self._seed(case_folder)
        names = [r['production_name'] for r in db_manager.get_production_history(case_folder, direction='inbound')]
        assert names == ['INBOUND: OCA - VOL001']

    def test_ordered_newest_first(self, case_folder):
        import db_manager
        self._seed(case_folder)
        result = db_manager.get_production_history(case_folder)
        # INBOUND seeded at 11:00 is newer than HIST_OUT at 10:00
        assert result[0]['production_name'] == 'INBOUND: OCA - VOL001'
        assert result[1]['production_name'] == 'HIST_OUT'


# ---------------------------------------------------------------------------
# Orphan detector predicate (mirrors the inline logic at
# pages/5_Production.py:239-264 — the DB-backed orphan detector rewrite
# in beta-2.10 Commit 2). Covered here because the predicate is pure
# function of (has_staging_files, db_status).
# ---------------------------------------------------------------------------

def _is_orphan(has_staging_files, db_status):
    """Replicates the inline decision at pages/5_Production.py:239-264.

    A folder is flagged as orphan only when TEMP/STAGED files exist on disk
    AND the DB says the production is missing or in a terminal state.
    Active lifecycle states (in_progress, pass1_complete, finalizing) are
    NEVER flagged — those files are legitimately staged.
    """
    if not has_staging_files:
        return False
    return (db_status is None) or (db_status in ('finalized', 'aborted'))


class TestOrphanDetectorPredicate:
    """Verifies the orphan detector's decision logic under every possible
    combination of (files present, DB status). Guards against re-introducing
    the pre-beta-2.10 false-positive on legitimately-staged Pass 1 output.
    """

    def test_no_files_never_orphan(self):
        for status in (None, 'in_progress', 'pass1_complete', 'finalizing', 'finalized', 'aborted'):
            assert _is_orphan(False, status) is False, (
                f"No staging files must never be orphan (status={status!r})"
            )

    def test_files_plus_in_progress_is_legitimate(self):
        """The core bug fix: a Pass 1 that's actively running has TEMP/STAGED
        files and must NOT be flagged, even though files exist on disk."""
        assert _is_orphan(True, 'in_progress') is False

    def test_files_plus_pass1_complete_is_legitimate(self):
        """The scenario that triggered this sprint: Pass 1 complete, user
        hasn't clicked Finalize yet. Files exist, status is active. Not orphan."""
        assert _is_orphan(True, 'pass1_complete') is False

    def test_files_plus_finalizing_is_legitimate(self):
        """Finalize is in progress — staging files may briefly still exist
        before the finalize step cleans them up."""
        assert _is_orphan(True, 'finalizing') is False

    def test_files_plus_finalized_is_orphan(self):
        """Finalize should have cleaned staging files. Their presence after
        finalized status means something went wrong during cleanup — flag."""
        assert _is_orphan(True, 'finalized') is True

    def test_files_plus_aborted_is_orphan(self):
        """Abort deletes the folder. If files exist with an aborted row, the
        folder cleanup failed — flag so the user can finish cleaning up."""
        assert _is_orphan(True, 'aborted') is True

    def test_files_without_db_row_is_orphan(self):
        """Truly abandoned: staging files with no DB record. This is the
        classic orphan case (e.g., server crash before Pass 1 seeded the row,
        or DB was reset while files remained on disk)."""
        assert _is_orphan(True, None) is True


class TestOrphanDetectorIntegration:
    """Exercises the detector predicate against real rows in production_runs
    via get_productions_with_staging_files(). Confirms the end-to-end chain:
    seed state → query helper → predicate → correct verdict."""

    def test_in_progress_row_not_flagged(self, case_folder):
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'LIVE_RUN',
            'created_at': 't', 'created_by': 'u',
            'format': 'PDF', 'mode': 'Simple Production',
            'status': 'in_progress',
        })
        status_map = dict(db_manager.get_productions_with_staging_files(case_folder))
        assert _is_orphan(True, status_map.get('LIVE_RUN')) is False

    def test_finalized_row_with_staging_is_flagged(self, case_folder):
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'STALE_RUN',
            'created_at': 't', 'created_by': 'u',
            'format': 'PDF', 'mode': 'Simple Production',
            'status': 'finalized',
        })
        status_map = dict(db_manager.get_productions_with_staging_files(case_folder))
        assert _is_orphan(True, status_map.get('STALE_RUN')) is True

    def test_unknown_folder_name_is_flagged(self, case_folder):
        """Folder on disk with no matching production_runs row → orphan.
        Exercises the None branch of the predicate against the real lookup."""
        import db_manager
        status_map = dict(db_manager.get_productions_with_staging_files(case_folder))
        assert _is_orphan(True, status_map.get('NEVER_RECORDED')) is True

    def test_inbound_row_is_invisible_to_detector(self, case_folder):
        """get_productions_with_staging_files filters to direction='outbound'.
        Inbound rows must not appear — they never stage files so flagging
        them would be meaningless."""
        import db_manager
        db_manager.record_production_run(case_folder, {
            'production_name': 'INBOUND: OCA - VOL001',
            'created_at': 't', 'created_by': 'u',
            'format': 'Native', 'mode': 'Inbound Ingest',
            'direction': 'inbound', 'status': 'finalized',
        })
        status_map = dict(db_manager.get_productions_with_staging_files(case_folder))
        assert 'INBOUND: OCA - VOL001' not in status_map
