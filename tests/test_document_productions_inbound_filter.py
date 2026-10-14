"""
Regression coverage for the beta-2.11 Commit 5b fix — inbound contamination
of the document_productions junction table.

Pre-fix state: init_db() contained a one-time backfill (authored Phase 25,
2026-03-26) that inserted a document_productions row for every document
with a populated begdoc+production_volume pair, hardcoding
production_type='Original'. The backfill had no source_party filter —
it pre-dated the beta-2.10 inbound module by three weeks. On any case DB
where inbound ingest ran before the first outbound production, the
backfill swept inbound documents into document_productions with false
'Original' labels. This corrupts the ~10 downstream consumer sites that
treat document_productions as authoritative outbound production history.

Commit 5b applies two changes:

  1. Approach 1 — Add OUTBOUND_SOURCE_FILTER_SQL predicate to the backfill
     WHERE clause. Prevents new contamination on clean databases.
  2. Approach 3 — Add a guarded, transactional, idempotent cleanup
     migration that deletes inbound-CN rows from document_productions in
     previously-damaged DBs. Sentinel:
     _document_productions_inbound_cleanup_v1 in case_settings.

Discriminator proof (audit §3.3 and §4.4): the outbound production flow
applies OUTBOUND_SOURCE_FILTER_SQL in every query (base, selection,
family expansion), so no inbound document can reach the legitimate
document_productions INSERT at pages/5_Production.py:1622. Therefore any
inbound-CN row in document_productions originated from the defective
backfill and is safe to delete.

These tests use synthetic SQLite databases via the conftest.case_folder
fixture. No Streamlit, no OpenSearch, no real case data.
"""
import os
import pytest

import db_manager


def _insert_doc(conn, control_number, source_party, begdoc=None, enddoc=None,
                production_volume=None):
    """Insert a minimal documents row. source_party controls inbound/outbound.
    Both begdoc AND enddoc must be set for the row to pass the backfill's
    WHERE + the document_productions NOT NULL constraint — the backfill's
    INSERT OR IGNORE would silently drop rows with NULL enddoc."""
    if begdoc is not None and enddoc is None:
        enddoc = begdoc  # single-page documents have begdoc == enddoc
    conn.execute(
        "INSERT INTO documents (control_number, source_party, begdoc, enddoc, "
        "production_volume, file_name, processing_status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'Processed')",
        (control_number, source_party, begdoc, enddoc, production_volume,
         f'{control_number}.eml'),
    )


def _insert_dp_row(conn, control_number, production_volume, begdoc, enddoc='END',
                   production_type='Original'):
    """Insert a document_productions row directly (simulating either legitimate
    outbound production or pre-fix buggy backfill)."""
    conn.execute(
        "INSERT INTO document_productions (control_number, production_volume, begdoc, "
        "enddoc, page_count, produced_at, production_type) VALUES (?, ?, ?, ?, 1, "
        "'2026-01-01T00:00:00', ?)",
        (control_number, production_volume, begdoc, enddoc, production_type),
    )


def _clear_dp_and_sentinel(conn):
    """Clear document_productions and the cleanup sentinel so init_db's
    cleanup path can re-run. Used to stage dirty-case fixtures."""
    conn.execute("DELETE FROM document_productions")
    conn.execute(
        "DELETE FROM case_settings "
        "WHERE setting_key = '_document_productions_inbound_cleanup_v1'"
    )
    conn.commit()


def _count_dp_rows(conn, source_party_filter=None):
    """Count document_productions rows, optionally filtered by joined source_party."""
    if source_party_filter == 'inbound':
        q = ("SELECT COUNT(*) FROM document_productions dp "
             "JOIN documents d ON dp.control_number = d.control_number "
             "WHERE d.source_party IS NOT NULL AND d.source_party != 'Internal'")
    elif source_party_filter == 'outbound':
        q = ("SELECT COUNT(*) FROM document_productions dp "
             "JOIN documents d ON dp.control_number = d.control_number "
             "WHERE d.source_party = 'Internal' OR d.source_party IS NULL")
    else:
        q = "SELECT COUNT(*) FROM document_productions"
    return conn.execute(q).fetchone()[0]


def test_source_filter_prevents_new_contamination(case_folder):
    """Backfill with source_party filter must skip inbound docs on a
    previously-empty document_productions table."""
    conn = db_manager.get_connection(case_folder)
    # Seed 2 inbound docs with begdoc+production_volume populated (as an
    # inbound ingest would).
    _insert_doc(conn, 'AC-001', 'Acme Corp', begdoc='AC-0001', production_volume='VOL001')
    _insert_doc(conn, 'AC-002', 'Acme Corp', begdoc='AC-0002', production_volume='VOL001')
    # Clear document_productions and the cleanup sentinel so the backfill
    # + cleanup guards will evaluate on the next init_db() call.
    _clear_dp_and_sentinel(conn)
    conn.close()

    # Re-trigger init_db to exercise backfill + cleanup paths.
    db_manager.init_db(case_folder)

    conn = db_manager.get_connection(case_folder)
    try:
        assert _count_dp_rows(conn) == 0, (
            "Backfill must not populate document_productions for inbound docs"
        )
        assert _count_dp_rows(conn, 'inbound') == 0
    finally:
        conn.close()


def test_source_filter_preserves_outbound_backfill(case_folder):
    """Backfill must populate document_productions for outbound docs
    (source_party='Internal' or NULL)."""
    conn = db_manager.get_connection(case_folder)
    _insert_doc(conn, 'DOC-001', 'Internal', begdoc='B0001', production_volume='VOL001')
    _insert_doc(conn, 'DOC-002', None,       begdoc='B0002', production_volume='VOL001')
    _insert_doc(conn, 'DOC-003', 'Internal', begdoc='B0003', production_volume='VOL001')
    _clear_dp_and_sentinel(conn)
    conn.close()

    db_manager.init_db(case_folder)

    conn = db_manager.get_connection(case_folder)
    try:
        total = _count_dp_rows(conn)
        assert total == 3, f'Expected 3 outbound dp rows, got {total}'
        assert _count_dp_rows(conn, 'inbound') == 0
        # Sanity — the 3 rows belong to our 3 inserted docs.
        cns = {r[0] for r in conn.execute(
            "SELECT control_number FROM document_productions"
        ).fetchall()}
        assert cns == {'DOC-001', 'DOC-002', 'DOC-003'}
    finally:
        conn.close()


def test_cleanup_migration_heals_dirty_case(case_folder):
    """Pre-populated dirty inbound dp rows must be removed by the cleanup
    migration on a case DB that never ran the cleanup before."""
    conn = db_manager.get_connection(case_folder)
    # Seed 3 inbound docs + 3 dirty dp rows (as if the pre-fix backfill
    # had damaged this DB).
    for i, cn in enumerate(['AC-001', 'AC-002', 'AC-003'], start=1):
        _insert_doc(conn, cn, 'Acme Corp', begdoc=f'AC-{i:04d}', production_volume='VOL001')
        _insert_dp_row(conn, cn, 'VOL001', f'AC-{i:04d}')
    # Clear only the sentinel — keep the dirty dp rows so the cleanup can
    # observe them.
    conn.execute(
        "DELETE FROM case_settings "
        "WHERE setting_key = '_document_productions_inbound_cleanup_v1'"
    )
    conn.commit()
    conn.close()

    db_manager.init_db(case_folder)

    conn = db_manager.get_connection(case_folder)
    try:
        assert _count_dp_rows(conn, 'inbound') == 0, (
            'Cleanup migration must remove all inbound-CN dp rows'
        )
        # Sentinel must be set post-cleanup to prevent re-run.
        sentinel = conn.execute(
            "SELECT 1 FROM case_settings "
            "WHERE setting_key = '_document_productions_inbound_cleanup_v1'"
        ).fetchone()
        assert sentinel is not None, 'Cleanup sentinel must be set after run'
    finally:
        conn.close()


def test_cleanup_is_idempotent(case_folder):
    """Re-running init_db on a clean case DB must not cause any spurious
    deletion. The sentinel protects against re-scan."""
    conn = db_manager.get_connection(case_folder)
    _insert_doc(conn, 'DOC-001', 'Internal', begdoc='B0001', production_volume='VOL001')
    _insert_doc(conn, 'DOC-002', 'Internal', begdoc='B0002', production_volume='VOL001')
    _insert_dp_row(conn, 'DOC-001', 'VOL001', 'B0001')
    _insert_dp_row(conn, 'DOC-002', 'VOL001', 'B0002')
    conn.commit()
    count_before = _count_dp_rows(conn)
    conn.close()

    # Trigger init_db twice.
    db_manager.init_db(case_folder)
    db_manager.init_db(case_folder)

    conn = db_manager.get_connection(case_folder)
    try:
        count_after = _count_dp_rows(conn)
        assert count_after == count_before == 2, (
            f'Idempotent re-run must not alter dp count: before={count_before}, after={count_after}'
        )
    finally:
        conn.close()


def test_mixed_case_preserves_outbound_removes_inbound(case_folder):
    """Case DB with BOTH legitimate outbound dp rows AND pre-fix-backfill
    inbound dp rows. Cleanup must remove only the inbound ones."""
    conn = db_manager.get_connection(case_folder)
    # Legitimate outbound production: 2 internal docs + 2 legitimate dp rows.
    _insert_doc(conn, 'DOC-001', 'Internal', begdoc='B0001', production_volume='VOL001')
    _insert_doc(conn, 'DOC-002', 'Internal', begdoc='B0002', production_volume='VOL001')
    _insert_dp_row(conn, 'DOC-001', 'VOL001', 'B0001')
    _insert_dp_row(conn, 'DOC-002', 'VOL001', 'B0002')
    # Pre-fix buggy backfill: 2 inbound docs + 2 dirty dp rows.
    _insert_doc(conn, 'AC-001', 'Acme Corp', begdoc='AC-0001', production_volume='VOL002')
    _insert_doc(conn, 'AC-002', 'Acme Corp', begdoc='AC-0002', production_volume='VOL002')
    _insert_dp_row(conn, 'AC-001', 'VOL002', 'AC-0001')
    _insert_dp_row(conn, 'AC-002', 'VOL002', 'AC-0002')
    # Clear sentinel so cleanup re-runs.
    conn.execute(
        "DELETE FROM case_settings "
        "WHERE setting_key = '_document_productions_inbound_cleanup_v1'"
    )
    conn.commit()
    conn.close()

    db_manager.init_db(case_folder)

    conn = db_manager.get_connection(case_folder)
    try:
        assert _count_dp_rows(conn, 'outbound') == 2, (
            'Legitimate outbound dp rows must be preserved'
        )
        assert _count_dp_rows(conn, 'inbound') == 0, (
            'Dirty inbound dp rows must be removed'
        )
        # Total should be 2 outbound only.
        assert _count_dp_rows(conn) == 2
        # Sanity — check which specific CNs survived.
        surviving = {r[0] for r in conn.execute(
            "SELECT control_number FROM document_productions"
        ).fetchall()}
        assert surviving == {'DOC-001', 'DOC-002'}
    finally:
        conn.close()


def test_backfill_recovers_documents_with_null_enddoc(case_folder):
    """Pre-fix state: the backfill's INSERT OR IGNORE silently dropped any
    outbound document with populated begdoc + NULL enddoc because
    document_productions.enddoc is NOT NULL.

    Post-fix: COALESCE(d.enddoc, d.begdoc) recovers those rows with
    enddoc = begdoc (single-page document semantics per the module's
    convention). This regression pin catches a silent re-introduction of
    the bug if a future refactor drops the COALESCE."""
    conn = db_manager.get_connection(case_folder)
    # Insert WITHOUT the fixture helper's defensive enddoc=begdoc default.
    # Raw SQL so we can force enddoc=NULL explicitly — the fixture helper
    # at line 46 would silently coerce enddoc=begdoc and mask the bug.
    conn.execute(
        "INSERT INTO documents (control_number, source_party, begdoc, "
        "enddoc, production_volume, file_name, processing_status) "
        "VALUES (?, 'Internal', ?, NULL, ?, ?, 'Processed')",
        ('DOC-NULL-001', 'B0001', 'VOL001', 'DOC-NULL-001.eml'),
    )
    _clear_dp_and_sentinel(conn)
    conn.close()

    db_manager.init_db(case_folder)

    conn = db_manager.get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT control_number, begdoc, enddoc FROM document_productions"
        ).fetchall()
        assert len(rows) == 1, (
            f'Backfill must recover the NULL-enddoc outbound row '
            f'(COALESCE fix); got {len(rows)} rows'
        )
        row = rows[0]
        assert row['control_number'] == 'DOC-NULL-001'
        assert row['begdoc'] == 'B0001'
        assert row['enddoc'] == 'B0001', (
            f'enddoc must be coalesced to begdoc for single-page docs; '
            f'got enddoc={row["enddoc"]!r}'
        )
    finally:
        conn.close()
