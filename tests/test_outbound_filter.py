"""
test_outbound_filter.py — sealed contract for the outbound source_party filter.

Pins the SQL text of `db_manager.OUTBOUND_SOURCE_FILTER_SQL` and its
alias-aware helper `db_manager.outbound_source_filter_sql()`. These are the
DRY substrate for 14 outbound-destined queries across the codebase (beta-2.10
Commit 3 pre-flight audit at _scratchpad/inbound_exclusion_coverage_audit.md).

If any of these tests fail, do NOT adjust them — investigate whether the
change to the constant or helper is intentional. Changing the SQL form
affects 14 callsites and has defensibility implications (inbound docs must
never leak into outbound-destined output).

This file is intentionally dedicated and small so future maintainers
debugging a filter issue can find it by filename.
"""
import sqlite3
import pytest


# ---------------------------------------------------------------------------
# Constant: pinned value
# ---------------------------------------------------------------------------

class TestOutboundSourceFilterConstant:

    def test_pinned_value(self):
        """The SQL fragment is load-bearing across 14 queries. Its exact text
        is pinned here. Changing the text requires a simultaneous review of
        every callsite listed in the audit file."""
        import db_manager
        assert db_manager.OUTBOUND_SOURCE_FILTER_SQL == (
            "(source_party = 'Internal' OR source_party IS NULL)"
        )

    def test_is_parenthesized(self):
        """The fragment must be parenthesized so it's safe to join with
        existing WHERE clauses via AND without operator-precedence surprises."""
        import db_manager
        assert db_manager.OUTBOUND_SOURCE_FILTER_SQL.startswith("(")
        assert db_manager.OUTBOUND_SOURCE_FILTER_SQL.endswith(")")

    def test_handles_null_source_party(self):
        """Pattern MUST tolerate NULL (pre-migration docs may have NULL
        source_party). Matches the Analytics/Custodians convention."""
        import db_manager
        assert "IS NULL" in db_manager.OUTBOUND_SOURCE_FILTER_SQL
        assert "'Internal'" in db_manager.OUTBOUND_SOURCE_FILTER_SQL


# ---------------------------------------------------------------------------
# Helper: alias behavior
# ---------------------------------------------------------------------------

class TestOutboundSourceFilterHelper:

    def test_no_alias_returns_constant_by_identity(self):
        """Identity check (is, not ==) enforces that the no-alias branch
        returns the module constant itself, not a duplicate string literal.

        Why this matters: a future refactor that rewrites the no-alias branch
        as e.g. `return f"(source_party = 'Internal' OR source_party IS NULL)"`
        would pass a value-equality test but silently drift from the constant.
        Identity check catches that drift.
        """
        import db_manager
        assert db_manager.outbound_source_filter_sql() is db_manager.OUTBOUND_SOURCE_FILTER_SQL

    def test_no_alias_value(self):
        import db_manager
        assert db_manager.outbound_source_filter_sql() == (
            "(source_party = 'Internal' OR source_party IS NULL)"
        )

    def test_alias_d(self):
        """Used by the privilege log query (pages/5_Production.py:3894)
        which aliases `FROM documents d`."""
        import db_manager
        assert db_manager.outbound_source_filter_sql('d') == (
            "(d.source_party = 'Internal' OR d.source_party IS NULL)"
        )

    def test_alias_documents(self):
        """Full table name also works as an alias, for subqueries that use
        the unaliased table name inside a larger query context."""
        import db_manager
        assert db_manager.outbound_source_filter_sql('documents') == (
            "(documents.source_party = 'Internal' OR documents.source_party IS NULL)"
        )

    def test_empty_string_alias_treated_as_no_alias(self):
        """Empty string is falsy → same path as None. Pinning this so callers
        know passing '' is safe (not a silent injection)."""
        import db_manager
        assert db_manager.outbound_source_filter_sql('') is db_manager.OUTBOUND_SOURCE_FILTER_SQL

    def test_none_alias_explicit(self):
        import db_manager
        assert db_manager.outbound_source_filter_sql(None) is db_manager.OUTBOUND_SOURCE_FILTER_SQL


# ---------------------------------------------------------------------------
# End-to-end: fragment parses and filters correctly in real SQLite
# ---------------------------------------------------------------------------

class TestOutboundSourceFilterRuntime:
    """Sanity-check the fragment against a real SQLite engine. Defends against
    a subtle syntax regression (e.g. stray character, bad quoting) that
    pinned-value tests wouldn't catch if the test string was also broken."""

    def _mk_db(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE documents (id INTEGER, source_party TEXT)"
        )
        conn.executemany(
            "INSERT INTO documents VALUES (?, ?)",
            [
                (1, 'Internal'),       # custodial
                (2, None),              # pre-migration custodial (NULL)
                (3, 'Opposing Counsel'),# inbound
                (4, 'Third Party XYZ'), # inbound
            ],
        )
        return conn

    def test_bare_form_excludes_inbound(self):
        import db_manager
        conn = self._mk_db()
        ids = [r[0] for r in conn.execute(
            f"SELECT id FROM documents WHERE {db_manager.OUTBOUND_SOURCE_FILTER_SQL} ORDER BY id"
        ).fetchall()]
        assert ids == [1, 2]

    def test_aliased_form_excludes_inbound(self):
        import db_manager
        conn = self._mk_db()
        clause = db_manager.outbound_source_filter_sql('d')
        ids = [r[0] for r in conn.execute(
            f"SELECT d.id FROM documents d WHERE {clause} ORDER BY d.id"
        ).fetchall()]
        assert ids == [1, 2]

    def test_appended_to_existing_where_via_and(self):
        """Real-world usage: appending after an existing WHERE clause with AND."""
        import db_manager
        conn = self._mk_db()
        query = (
            f"SELECT id FROM documents WHERE id > 0 "
            f"AND {db_manager.OUTBOUND_SOURCE_FILTER_SQL} ORDER BY id"
        )
        ids = [r[0] for r in conn.execute(query).fetchall()]
        assert ids == [1, 2]
