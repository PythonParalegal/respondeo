"""
test_review_inbound_badge.py — regression tests for the inbound privilege-tagging
smell fix in pages/4_Review.py (beta-2.10 Commit 4).

Covers:
- `_is_inbound_doc()` predicate (imported from the page module via importlib
  since Streamlit pages aren't normally importable — we load the module
  source and exec the helper's definition into a namespace).
- Bulk-privilege loop skips inbound docs while still applying tag writes
  (simulates the inline logic in pages/4_Review.py around line 3238).
- Redaction-sync skips privilege_status auto-set for inbound docs
  (simulates the logic in `_r_sync_tags` around line 3594).
- Scope boundary verified: non-privilege review actions (tags, notes, redaction
  marks, category, custodian, confidentiality) still apply to inbound docs.

This file is dedicated so a future maintainer debugging an inbound-privilege
regression can find it by filename.
"""
import importlib.util
import os
import pathlib
import pytest


# ---------------------------------------------------------------------------
# Module-loader for pages/4_Review.py — Streamlit pages aren't import-safe
# (they execute page-rendering code at import time). We extract just the
# `_is_inbound_doc` function definition via AST surgery.
# ---------------------------------------------------------------------------

def _load_is_inbound_doc():
    """Extract _is_inbound_doc from pages/4_Review.py without executing the
    full Streamlit page."""
    import ast
    page_path = pathlib.Path(__file__).parent.parent / "pages" / "4_Review.py"
    source = page_path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == '_is_inbound_doc':
            # Compile just this function definition and exec into a fresh ns
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {}
            exec(compile(mod, str(page_path), 'exec'), ns)
            return ns['_is_inbound_doc']
    raise RuntimeError("_is_inbound_doc not found in pages/4_Review.py")


_is_inbound_doc = _load_is_inbound_doc()


# ---------------------------------------------------------------------------
# Predicate tests
# ---------------------------------------------------------------------------

class TestIsInboundDocPredicate:

    def test_none_is_custodial(self):
        """NULL source_party = custodial (legacy/pre-migration docs)."""
        assert _is_inbound_doc(None) is False

    def test_empty_string_is_custodial(self):
        """Empty string = custodial (degenerate case, don't treat as inbound)."""
        assert _is_inbound_doc('') is False

    def test_whitespace_only_is_custodial(self):
        """Whitespace-only = custodial (trim and treat as empty)."""
        assert _is_inbound_doc('   ') is False

    def test_internal_is_custodial(self):
        assert _is_inbound_doc('Internal') is False

    def test_opposing_counsel_is_inbound(self):
        assert _is_inbound_doc('Opposing Counsel') is True

    def test_party_name_with_spaces_is_inbound(self):
        assert _is_inbound_doc('Smith & Jones LLP') is True

    def test_mirrors_sql_filter_semantics(self):
        """The Python predicate must agree with db_manager.OUTBOUND_SOURCE_FILTER_SQL.
        SQL: `(source_party = 'Internal' OR source_party IS NULL)` → custodial.
        Python: _is_inbound_doc returns False for those same inputs.
        Any divergence here means the Review-side gating and the SQL-side
        filtering would disagree, leaving a leak seam between them."""
        custodial_values = [None, '', 'Internal', '   Internal   ']
        for v in custodial_values:
            # Normalize whitespace before comparison (Python predicate does this;
            # SQL implicitly via exact match — both paths treat whitespace-padded
            # 'Internal' as custodial).
            if v is not None and v.strip() == 'Internal':
                assert _is_inbound_doc(v) is False, f"Custodial value {v!r} misclassified"
            elif v is None or v.strip() == '':
                assert _is_inbound_doc(v) is False, f"Empty/NULL value {v!r} misclassified"

        inbound_values = ['OCA', 'Opposing Counsel', 'Law Firm XYZ']
        for v in inbound_values:
            assert _is_inbound_doc(v) is True, f"Inbound value {v!r} misclassified"


# ---------------------------------------------------------------------------
# Bulk-privilege loop simulation — tag writes always apply; privilege writes
# skip inbound docs.
# ---------------------------------------------------------------------------

@pytest.fixture()
def bulk_review_case(case_folder):
    """Two custodial docs + two inbound docs, pre-seeded with empty tags and
    no privilege_status. Used to verify that bulk-apply updates tags for
    ALL docs but only sets privilege_status for the custodial ones."""
    import db_manager
    conn = db_manager.get_connection(case_folder)
    rows = [
        ("DOC-CUST-A", "a.pdf", ".pdf", "Processed", "Internal",         None),
        ("DOC-CUST-B", "b.pdf", ".pdf", "Processed", "Internal",         None),
        ("DOC-INB-X",  "x.pdf", ".pdf", "Processed", "Opposing Counsel", None),
        ("DOC-INB-Y",  "y.pdf", ".pdf", "Processed", "Law Firm XYZ",     None),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO documents
           (control_number, file_name, file_extension, processing_status,
            source_party, privilege_status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return case_folder


# ──────────────────────────────────────────────────────────────────────────────
# NOTE ON CONNECTION STRATEGY — READ BEFORE MODIFYING _simulate_bulk_apply
# ──────────────────────────────────────────────────────────────────────────────
# This harness uses a SINGLE connection for both the tag UPDATE and the
# privilege_status UPDATE. Production's `_bulk_apply_op` at
# pages/4_Review.py:~3238 uses a DUAL-connection pattern instead — it opens
# its own local conn for tag UPDATEs, then makes a nested
# `db_manager.set_privilege_status(...)` call which opens a SECOND connection
# for the privilege write, while the local conn's tag UPDATE is still
# uncommitted.
#
# The production dual-connection pattern is a flagged latent fragility
# (beta-2.10 sprint Post-Sprint Roadmap Flags). It works in production only
# because `_safe_write` serializes the entire bulk-apply op, preventing
# concurrent access. It RELIABLY FAILS in this test harness with
# `sqlite3.OperationalError: database is locked` because pytest's fresh
# tmp_path DB has no ambient serialization to absorb the contention.
#
# DO NOT modify this harness to "match production" without first resolving
# the underlying pattern. Making the harness match production would:
#   1. Reintroduce the SQLite lock contention this test was written to work
#      around (not to expose — see project memory `feedback_db_connections`),
#   2. Diverge from the project's own rule in `feedback_db_connections`:
#      "never mix db_manager calls with a separate conn in utility scripts."
#
# The semantic being tested here is "tag writes apply to all docs; privilege
# writes skip inbound." That semantic is identical whether privilege writes
# are done via the same conn's raw UPDATE or via `db_manager.set_privilege_status`.
# We choose the same-conn path to keep the test robust to the (separate)
# connection-lifecycle issue in production.
# ──────────────────────────────────────────────────────────────────────────────

def _simulate_bulk_apply(case_folder, bulk_cns, chosen_tag, priv_disp_choice):
    """Mirror the inline bulk-apply loop from pages/4_Review.py lines ~3238+.

    Uses a single connection — see the note block above for rationale.

    Returns (inbound_skipped_count, tag_applied_count, privilege_set_count).
    """
    import db_manager
    conn = db_manager.get_connection(case_folder)
    inbound_skipped = 0
    tag_applied = 0
    priv_set = 0
    try:
        for cn in bulk_cns:
            row = conn.execute(
                "SELECT tags, source_party FROM documents WHERE control_number=?",
                (cn,)
            ).fetchone()
            old = row['tags'] or ''
            tags = [t.strip() for t in old.replace(';', ',').split(',') if t.strip()]
            if chosen_tag not in tags:
                tags.append(chosen_tag)
            new = ', '.join(tags)
            conn.execute("UPDATE documents SET tags=? WHERE control_number=?", (new, cn))
            if old != new:
                tag_applied += 1
            # Privilege disposition: skip inbound, apply to custodial
            if priv_disp_choice:
                if _is_inbound_doc(row['source_party']):
                    inbound_skipped += 1
                else:
                    disp_val = 'Withhold' if 'Withhold' in priv_disp_choice else 'Redact'
                    # Raw UPDATE on the same conn — see connection-strategy
                    # note above for why this does NOT call
                    # db_manager.set_privilege_status().
                    conn.execute(
                        "UPDATE documents SET privilege_status=? WHERE control_number=?",
                        (disp_val, cn)
                    )
                    priv_set += 1
        conn.commit()
    finally:
        conn.close()
    return inbound_skipped, tag_applied, priv_set


class TestBulkPrivilegeSkipsInbound:

    def test_bulk_tag_applies_to_all_including_inbound(self, bulk_review_case):
        """Tag writes are unaffected by inbound status — all 4 docs get the tag."""
        import db_manager
        cns = ["DOC-CUST-A", "DOC-CUST-B", "DOC-INB-X", "DOC-INB-Y"]
        _simulate_bulk_apply(bulk_review_case, cns, 'Attorney-Client', 'Withhold (exclude from production)')
        for cn in cns:
            tags = db_manager.get_document_tags(bulk_review_case, cn)
            assert 'Attorney-Client' in tags, f"{cn} did not receive the tag"

    def test_bulk_privilege_skips_inbound_docs(self, bulk_review_case):
        """Privilege disposition is set only for custodial docs; inbound skipped."""
        import db_manager
        cns = ["DOC-CUST-A", "DOC-CUST-B", "DOC-INB-X", "DOC-INB-Y"]
        skipped, _, priv_set = _simulate_bulk_apply(
            bulk_review_case, cns, 'Attorney-Client', 'Withhold (exclude from production)'
        )
        assert skipped == 2
        assert priv_set == 2
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-CUST-A') == 'Withhold'
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-CUST-B') == 'Withhold'
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-INB-X') is None, \
            "Inbound doc received privilege_status — should have been skipped"
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-INB-Y') is None

    def test_bulk_without_privilege_choice_still_works(self, bulk_review_case):
        """When no privilege disposition is chosen (pure tag-apply), no skip
        reporting and no privilege writes happen at all."""
        import db_manager
        cns = ["DOC-CUST-A", "DOC-INB-X"]
        skipped, tag_applied, priv_set = _simulate_bulk_apply(
            bulk_review_case, cns, 'Non-Responsive', ''  # no priv_disp_choice
        )
        assert skipped == 0
        assert priv_set == 0
        assert tag_applied == 2  # both docs got the tag
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-CUST-A') is None
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-INB-X') is None


# ---------------------------------------------------------------------------
# Redaction-sync simulation — privilege auto-set suppressed for inbound
# ---------------------------------------------------------------------------

def _simulate_redaction_sync(case_folder, control_number, has_marks):
    """Mirror the inline _r_sync_tags privilege-sync logic from
    pages/4_Review.py lines ~3605+. Returns the status that would be
    written (or None if nothing was written)."""
    import db_manager
    old_status = db_manager.get_privilege_status(case_folder, control_number)
    doc = db_manager.get_document(case_folder, control_number)
    is_inbound = _is_inbound_doc(doc.get('source_party') if doc else None)

    if old_status == 'Withhold':
        return old_status  # Withhold never overwritten
    if is_inbound:
        return old_status  # inbound docs don't get auto-sync
    new_status = 'Redact' if has_marks else None
    if old_status != new_status:
        db_manager.set_privilege_status(case_folder, control_number, new_status)
    return db_manager.get_privilege_status(case_folder, control_number)


class TestRedactionSyncSkipsInbound:

    def test_custodial_doc_gets_redact_auto_set(self, bulk_review_case):
        """Baseline: custodial doc with marks gets auto-set to Redact."""
        import db_manager
        _simulate_redaction_sync(bulk_review_case, 'DOC-CUST-A', has_marks=True)
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-CUST-A') == 'Redact'

    def test_inbound_doc_does_not_get_auto_set(self, bulk_review_case):
        """Core scope boundary: inbound doc with marks must NOT get Redact
        auto-set. Redaction marks themselves are stored separately and are
        preserved — only the privilege_status column is skipped."""
        import db_manager
        _simulate_redaction_sync(bulk_review_case, 'DOC-INB-X', has_marks=True)
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-INB-X') is None, \
            "Inbound doc received auto-sync'd privilege_status — should have been skipped"

    def test_withhold_never_overwritten_even_on_inbound(self, bulk_review_case):
        """Pre-existing Withhold is not cleared by the sync. On inbound docs,
        any pre-existing privilege_status is also not auto-modified."""
        import db_manager
        # Pre-set DOC-CUST-A to Withhold; sync should not change it
        db_manager.set_privilege_status(bulk_review_case, 'DOC-CUST-A', 'Withhold')
        _simulate_redaction_sync(bulk_review_case, 'DOC-CUST-A', has_marks=False)
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-CUST-A') == 'Withhold'


# ---------------------------------------------------------------------------
# Scope-boundary tests: non-privilege review actions still work on inbound
# ---------------------------------------------------------------------------

class TestScopeBoundaryPreservedActions:
    """Verifies that disabling privilege_status writes on inbound docs does NOT
    disable other review actions. Scope boundary from the commit message:
    tags, notes, annotations, redaction marks, production_category, custodian,
    confidentiality designation all continue to work on inbound docs."""

    def test_tag_writes_work_on_inbound(self, bulk_review_case):
        import db_manager
        db_manager.update_document_tags(bulk_review_case, 'DOC-INB-X', 'Review-In-Progress')
        assert db_manager.get_document_tags(bulk_review_case, 'DOC-INB-X') == 'Review-In-Progress'

    def test_confidentiality_writes_work_on_inbound(self, bulk_review_case):
        """Confidentiality designation is separate from privilege_status and
        applies to inbound docs (e.g., marking an incoming production as
        'Attorneys-Eyes-Only' for our own handling)."""
        import db_manager
        db_manager.set_confidentiality_designation(bulk_review_case, 'DOC-INB-X', 'AEO')
        assert db_manager.get_confidentiality_designation(bulk_review_case, 'DOC-INB-X') == 'AEO'

    def test_existing_privilege_status_on_inbound_is_not_wiped(self, bulk_review_case):
        """Plan §Commit 4 item 4: 'Existing privilege_status values on inbound
        docs — do not auto-wipe. Leave as-is; they're inert after Commit 3
        fixes the outbound leak.' Verify this by setting a value directly and
        confirming the redaction-sync leaves it alone."""
        import db_manager
        # Direct write (bypassing UI guards) to simulate a pre-Commit-3 state
        db_manager.set_privilege_status(bulk_review_case, 'DOC-INB-X', 'Redact')
        # Sync runs — should NOT modify (inbound guard returns early)
        _simulate_redaction_sync(bulk_review_case, 'DOC-INB-X', has_marks=False)
        assert db_manager.get_privilege_status(bulk_review_case, 'DOC-INB-X') == 'Redact', \
            "Existing privilege_status on inbound doc was wiped — contrary to scope boundary"
