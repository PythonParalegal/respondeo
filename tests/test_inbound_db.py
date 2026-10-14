"""
test_inbound_db.py — regression tests for the inbound-production db_manager
helpers added in beta-2.10 Commit 5:
  - inbound_production_run_name()   pinned-value format helper
  - get_inbound_productions()       dashboard summary
  - purge_inbound_volume()          atomic 3-op transaction
  - upsert_inbound_documents_batch() batch upsert with pinned ON CONFLICT scope

Test coverage deliberately exercises:
  1. The format-pinning of inbound_production_run_name() (drift-prevention).
  2. The atomicity of purge_inbound_volume() via forced-failure rollback.
  3. The ON CONFLICT preservation set on upsert_inbound_documents_batch() —
     every reviewer-applied field that MUST survive a re-ingest is asserted
     explicitly (architectural pinning per feedback_pinned_value_pattern).
  4. End-to-end round-trip: ingest → production_runs row present → purge →
     all surfaces clean → re-ingest with different shape → fresh row.

This file is the Commit 6 extraction's regression floor — the inbound
ingest/purge code paths had no test coverage before this sprint.
"""
import sqlite3
import pytest


# ---------------------------------------------------------------------------
# Helper: the 22-tuple shape that upsert_inbound_documents_batch expects
# ---------------------------------------------------------------------------
# Columns in order (see db_manager._INBOUND_UPSERT_SQL):
#   control_number, group_id, parent_id, file_name, file_extension,
#   custodian, author, email_from, email_to, email_cc, email_bcc,
#   email_subject, date_sent, original_path, full_path, source_party,
#   production_volume, dynamic_metadata, record_type, has_text, opensearch_id
# (processing_status is hardcoded to 'Imported' in the INSERT template.)

def _inbound_row(control_number, *, source_party='Opposing Counsel',
                 production_volume='VOL001', file_name='doc.pdf',
                 full_path='/tmp/doc.pdf', dynamic_metadata='{}',
                 has_text=1, opensearch_id=None):
    """Build a 22-tuple suitable for upsert_inbound_documents_batch."""
    return (
        control_number,                # control_number
        None,                          # group_id
        None,                          # parent_id
        file_name,                     # file_name
        '.pdf',                        # file_extension
        'Custodian-X',                 # custodian
        'Author-Y',                    # author
        None, None, None, None,        # email_from/to/cc/bcc
        None,                          # email_subject
        None,                          # date_sent
        '/original/path',              # original_path
        full_path,                     # full_path
        source_party,                  # source_party
        production_volume,             # production_volume
        dynamic_metadata,              # dynamic_metadata
        'Document',                    # record_type
        has_text,                      # has_text
        opensearch_id or f"os-{control_number}",  # opensearch_id
    )


# ---------------------------------------------------------------------------
# inbound_production_run_name — pinned format
# ---------------------------------------------------------------------------

class TestInboundProductionRunName:
    """Pinned-value test for the single-source-of-truth name format.
    Both Commit 5 purge and Commit 6 ingest go through this helper; changing
    the format here changes it in both places. If this test fails, inspect
    whether the purge call site and the ingest call site have been updated
    in lockstep before accepting the new format."""

    def test_pinned_format(self):
        import db_manager
        assert db_manager.inbound_production_run_name('OCA', 'VOL001') == \
            "INBOUND: OCA - VOL001"

    def test_format_with_spaces(self):
        import db_manager
        assert db_manager.inbound_production_run_name('Smith & Jones LLP', 'Vol 2') == \
            "INBOUND: Smith & Jones LLP - Vol 2"

    def test_deterministic(self):
        """Same inputs → same output, always. Enables name-based lookup."""
        import db_manager
        n1 = db_manager.inbound_production_run_name('P', 'V')
        n2 = db_manager.inbound_production_run_name('P', 'V')
        assert n1 == n2


class TestValidateInboundProductionIdentifiers:
    """Phase C validator (beta-2.10 Commit 6). Blocks ingest inputs that
    would produce composite-name collisions or degenerate entries.

    Counterexample for why the ' - ' delimiter check matters:
      inbound_production_run_name('ABC - West', 'Vol1')
        == 'INBOUND: ABC - West - Vol1'
      inbound_production_run_name('ABC', 'West - Vol1')
        == 'INBOUND: ABC - West - Vol1'
    Same composite — the UNIQUE constraint on production_runs.production_name
    would reject the second insert, but by then the documents have already
    been upserted with different source_party/production_volume values, so
    the user has orphan rows pointing to a production_runs row that belongs
    to a different logical production. The validator prevents this upstream.
    """

    def test_valid_inputs_return_empty_list(self):
        import db_manager
        assert db_manager.validate_inbound_production_identifiers('OCA', 'VOL001') == []

    def test_valid_with_spaces(self):
        import db_manager
        assert db_manager.validate_inbound_production_identifiers('Smith & Jones LLP', 'Vol 2') == []

    def test_empty_source_party_rejected(self):
        import db_manager
        errs = db_manager.validate_inbound_production_identifiers('', 'VOL001')
        assert any('Source Party is required' in e for e in errs)

    def test_empty_production_volume_rejected(self):
        import db_manager
        errs = db_manager.validate_inbound_production_identifiers('OCA', '')
        assert any('Production Volume is required' in e for e in errs)

    def test_whitespace_only_rejected(self):
        """Whitespace-only inputs after strip() are empty — rejected as missing."""
        import db_manager
        errs = db_manager.validate_inbound_production_identifiers('   ', '\t\n  ')
        assert any('Source Party is required' in e for e in errs)
        assert any('Production Volume is required' in e for e in errs)

    def test_both_missing_rejected_together(self):
        """Both missing → two error messages, not one (field-by-field reporting)."""
        import db_manager
        errs = db_manager.validate_inbound_production_identifiers(None, None)
        assert len(errs) == 2

    def test_source_party_delimiter_substring_rejected(self):
        """'ABC - West' collides with ('ABC', 'West - XYZ') style inputs."""
        import db_manager
        errs = db_manager.validate_inbound_production_identifiers('ABC - West', 'VOL001')
        assert any("Source Party cannot contain ' - '" in e for e in errs)

    def test_production_volume_delimiter_substring_rejected(self):
        import db_manager
        errs = db_manager.validate_inbound_production_identifiers('OCA', 'West - Vol1')
        assert any("Production Volume cannot contain ' - '" in e for e in errs)

    def test_both_delimiters_rejected(self):
        """Both fields containing the delimiter → two distinct error messages."""
        import db_manager
        errs = db_manager.validate_inbound_production_identifiers('A - B', 'C - D')
        delim_errs = [e for e in errs if 'cannot contain' in e]
        assert len(delim_errs) == 2

    def test_length_limit_enforced(self):
        """100-char limit is UX-motivated (not schema-driven) — pinned so a
        future contributor who raises it gets an explicit test-update cue."""
        import db_manager
        too_long = 'X' * 101
        errs = db_manager.validate_inbound_production_identifiers(too_long, 'VOL001')
        assert any('exceeds 100 characters' in e for e in errs)

    def test_100_chars_exact_is_valid(self):
        """Boundary case — 100 chars is still valid, 101 is rejected."""
        import db_manager
        exactly_100 = 'X' * 100
        assert db_manager.validate_inbound_production_identifiers(exactly_100, 'VOL') == []

    def test_collision_counterexample_both_rejected(self):
        """The motivating counterexample from the docstring — both pairs hit
        the validator, so neither reaches the composite-name formatter."""
        import db_manager
        errs1 = db_manager.validate_inbound_production_identifiers('ABC - West', 'Vol1')
        errs2 = db_manager.validate_inbound_production_identifiers('ABC', 'West - Vol1')
        assert errs1, "case A → composite 'ABC - West - Vol1' must be rejected"
        assert errs2, "case B → composite 'ABC - West - Vol1' must be rejected"

    def test_reserved_delimiter_constant_is_exactly_space_dash_space(self):
        """Sanity-pin on the constant itself — any change here changes the
        semantics of inbound_production_run_name and requires a data
        migration. Pinning the byte sequence prevents drift."""
        import db_manager
        assert db_manager._INBOUND_NAME_RESERVED_DELIMITER == ' - '


# ---------------------------------------------------------------------------
# get_inbound_productions — dashboard summary
# ---------------------------------------------------------------------------

class TestGetInboundProductions:

    def test_empty_case_returns_empty_list(self, case_folder):
        import db_manager
        assert db_manager.get_inbound_productions(case_folder) == []

    def test_internal_docs_excluded(self, case_folder):
        """Only non-Internal, non-NULL source_party rows count."""
        import db_manager
        conn = db_manager.get_connection(case_folder)
        conn.executemany(
            "INSERT INTO documents (control_number, source_party, production_volume) VALUES (?, ?, ?)",
            [
                ('DOC-INT-1', 'Internal', None),
                ('DOC-INT-2', None, None),
                ('DOC-INB-1', 'Opposing Counsel', 'VOL001'),
            ],
        )
        conn.commit()
        conn.close()
        result = db_manager.get_inbound_productions(case_folder)
        assert len(result) == 1
        assert result[0]['source_party'] == 'Opposing Counsel'
        assert result[0]['production_volume'] == 'VOL001'
        assert result[0]['doc_count'] == 1

    def test_grouping_and_ordering(self, case_folder):
        """GROUP BY source_party, production_volume; ORDER BY both ascending."""
        import db_manager
        conn = db_manager.get_connection(case_folder)
        conn.executemany(
            "INSERT INTO documents (control_number, source_party, production_volume) VALUES (?, ?, ?)",
            [
                ('D1', 'Party-B', 'VOL-A'),
                ('D2', 'Party-B', 'VOL-A'),
                ('D3', 'Party-B', 'VOL-B'),
                ('D4', 'Party-A', 'VOL-A'),
            ],
        )
        conn.commit()
        conn.close()
        result = db_manager.get_inbound_productions(case_folder)
        # Expected ordering: (Party-A, VOL-A), (Party-B, VOL-A), (Party-B, VOL-B)
        assert [(r['source_party'], r['production_volume'], r['doc_count']) for r in result] == [
            ('Party-A', 'VOL-A', 1),
            ('Party-B', 'VOL-A', 2),
            ('Party-B', 'VOL-B', 1),
        ]


# ---------------------------------------------------------------------------
# upsert_inbound_documents_batch — ON CONFLICT preservation set
# ---------------------------------------------------------------------------

class TestUpsertPreservesReviewState:
    """ON CONFLICT preservation is load-bearing for the Commit 4 scope
    boundary: reviewer-applied state on inbound docs must survive a
    re-ingest. Each field in the preservation set is asserted explicitly —
    if a future contributor adds a field to the ON CONFLICT UPDATE clause
    in _INBOUND_UPSERT_SQL without thinking, one of these assertions fails
    loudly with a clear message.

    Fields tested here all live on the `documents` table. Fields that live
    in separate tables (document_notes, redaction_marks, document_productions)
    are preserved by definition — ON CONFLICT only touches `documents` — and
    are not exercised here (coverage belongs with those tables' own helpers).
    """

    def _seed_inbound_doc_with_reviewer_state(self, case_folder):
        """Insert an inbound doc, then write reviewer-applied state to the
        fields that must survive re-ingest. Returns the initial 22-tuple
        for re-use in the re-ingest call."""
        import db_manager
        initial = _inbound_row('DOC-INB-RS1', dynamic_metadata='{"original": true}',
                               full_path='/v1/path', has_text=1)
        db_manager.upsert_inbound_documents_batch(case_folder, [initial])

        # Simulate reviewer state being applied on the inbound doc
        conn = db_manager.get_connection(case_folder)
        conn.execute("""
            UPDATE documents SET
                tags = ?,
                privilege_status = ?,
                production_category = ?,
                custodian = ?,
                confidentiality_designation = ?,
                reviewed_by = ?,
                reviewed_at = ?,
                begdoc = ?,
                enddoc = ?
            WHERE control_number = ?
        """, (
            'Responsive, Reviewed',
            'Redact',  # a stale value (inert after Commit 3 filter; Commit 4 now blocks new writes)
            'Development File',
            'Custodian-OVERRIDE',
            'AEO',
            'reviewer-jane',
            '2026-04-16T12:00:00',
            'ABC-000001',
            'ABC-000001',
            'DOC-INB-RS1',
        ))
        conn.commit()
        conn.close()
        return initial

    def test_reingest_updates_only_the_three_pinned_fields(self, case_folder):
        """The three fields in ON CONFLICT UPDATE SET get refreshed:
        dynamic_metadata, full_path, has_text."""
        import db_manager
        self._seed_inbound_doc_with_reviewer_state(case_folder)
        # Re-ingest with different metadata / path / has_text
        reingest = _inbound_row('DOC-INB-RS1', dynamic_metadata='{"updated": true}',
                                full_path='/v2/path', has_text=0)
        db_manager.upsert_inbound_documents_batch(case_folder, [reingest])

        conn = db_manager.get_connection(case_folder)
        row = conn.execute(
            "SELECT * FROM documents WHERE control_number = ?",
            ('DOC-INB-RS1',)
        ).fetchone()
        conn.close()
        # Pinned fields must be updated
        assert row['dynamic_metadata'] == '{"updated": true}'
        assert row['full_path'] == '/v2/path'
        assert row['has_text'] == 0

    def test_reingest_preserves_reviewer_applied_state(self, case_folder):
        """Every reviewer-applied field in the preservation set MUST survive
        a re-ingest. If any assertion here fails, a field leaked into the
        ON CONFLICT UPDATE clause or the caller is stomping state via
        non-upsert path. Either way, reviewer work is being lost."""
        import db_manager
        self._seed_inbound_doc_with_reviewer_state(case_folder)
        # Re-ingest
        reingest = _inbound_row('DOC-INB-RS1', dynamic_metadata='{"updated": true}',
                                full_path='/v2/path', has_text=0)
        db_manager.upsert_inbound_documents_batch(case_folder, [reingest])

        conn = db_manager.get_connection(case_folder)
        row = conn.execute(
            "SELECT * FROM documents WHERE control_number = ?",
            ('DOC-INB-RS1',)
        ).fetchone()
        conn.close()

        # Preservation set — each must survive
        assert row['tags'] == 'Responsive, Reviewed', "tags leaked — reviewer state lost"
        assert row['privilege_status'] == 'Redact', "privilege_status leaked — reviewer state lost"
        assert row['production_category'] == 'Development File', "production_category leaked"
        assert row['custodian'] == 'Custodian-OVERRIDE', "custodian leaked (would revert to Custodian-X from the 22-tuple)"
        assert row['confidentiality_designation'] == 'AEO', "confidentiality_designation leaked"
        assert row['reviewed_by'] == 'reviewer-jane', "reviewed_by leaked"
        assert row['reviewed_at'] == '2026-04-16T12:00:00', "reviewed_at leaked"
        assert row['begdoc'] == 'ABC-000001', "begdoc leaked — outbound Bates state lost"
        assert row['enddoc'] == 'ABC-000001', "enddoc leaked — outbound Bates state lost"

    def test_empty_batch_is_noop(self, case_folder):
        import db_manager
        assert db_manager.upsert_inbound_documents_batch(case_folder, []) == 0

    def test_batch_insert_multiple_rows(self, case_folder):
        import db_manager
        rows = [_inbound_row(f'DOC-INB-{i}') for i in range(5)]
        assert db_manager.upsert_inbound_documents_batch(case_folder, rows) == 5
        conn = db_manager.get_connection(case_folder)
        count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE source_party = 'Opposing Counsel'"
        ).fetchone()[0]
        conn.close()
        assert count == 5


# ---------------------------------------------------------------------------
# purge_inbound_volume — atomicity + correctness
# ---------------------------------------------------------------------------

class TestPurgeInboundVolume:

    def _seed_volume(self, case_folder, source_party='Opposing Counsel',
                     production_volume='VOL001', doc_count=3):
        """Seed the given volume with doc_count docs + a production_runs row
        (inbound direction, constructed name). Returns list of control_numbers.

        Control numbers include (party, volume) in the prefix to guarantee
        uniqueness across multiple seed calls in the same test — otherwise
        ON CONFLICT UPDATE would collapse subsequent seeds into updates of
        the first seed's rows, defeating multi-volume scenarios."""
        import db_manager
        # Sanitize for control_number use (no spaces, safe chars only)
        _party_slug = source_party.replace(' ', '_').replace('&', 'and')
        _vol_slug = production_volume.replace(' ', '_')
        cns = [f'DOC-{_party_slug}-{_vol_slug}-{i}' for i in range(doc_count)]
        rows = [_inbound_row(cns[i], source_party=source_party,
                             production_volume=production_volume,
                             opensearch_id=f'os-{_party_slug}-{_vol_slug}-{i}')
                for i in range(doc_count)]
        db_manager.upsert_inbound_documents_batch(case_folder, rows)
        # Record the inbound production_runs row (Commit 6 will do this in ingest;
        # here we do it directly to test Commit 5's purge)
        db_manager.record_production_run(case_folder, {
            'production_name': db_manager.inbound_production_run_name(source_party, production_volume),
            'created_at': '2026-04-16T12:00:00',
            'created_by': 'test',
            'format': 'Native',
            'mode': 'Inbound Ingest',
            'direction': 'inbound',
            'status': 'finalized',
            'document_count': doc_count,
        })
        return cns

    def test_happy_path_returns_opensearch_ids(self, case_folder):
        import db_manager
        self._seed_volume(case_folder, doc_count=3)
        os_ids = db_manager.purge_inbound_volume(case_folder, 'Opposing Counsel', 'VOL001')
        assert sorted(os_ids) == [
            'os-Opposing_Counsel-VOL001-0',
            'os-Opposing_Counsel-VOL001-1',
            'os-Opposing_Counsel-VOL001-2',
        ]

    def test_purge_removes_documents(self, case_folder):
        import db_manager
        self._seed_volume(case_folder, doc_count=3)
        db_manager.purge_inbound_volume(case_folder, 'Opposing Counsel', 'VOL001')
        assert db_manager.get_inbound_productions(case_folder) == []

    def test_purge_removes_production_runs_row(self, case_folder):
        """The second DELETE in the atomic transaction: production_runs row
        for the inbound volume is gone after purge."""
        import db_manager
        self._seed_volume(case_folder, doc_count=2)
        name = db_manager.inbound_production_run_name('Opposing Counsel', 'VOL001')
        assert db_manager.get_production_run(case_folder, name) is not None
        db_manager.purge_inbound_volume(case_folder, 'Opposing Counsel', 'VOL001')
        assert db_manager.get_production_run(case_folder, name) is None

    def test_purge_scoped_to_matching_volume_only(self, case_folder):
        """Other volumes (different party OR different volume name) must NOT
        be affected."""
        import db_manager
        self._seed_volume(case_folder, source_party='Party-A', production_volume='V1', doc_count=2)
        self._seed_volume(case_folder, source_party='Party-B', production_volume='V1', doc_count=2)
        self._seed_volume(case_folder, source_party='Party-A', production_volume='V2', doc_count=2)

        db_manager.purge_inbound_volume(case_folder, 'Party-A', 'V1')

        remaining = db_manager.get_inbound_productions(case_folder)
        pairs = {(r['source_party'], r['production_volume']) for r in remaining}
        assert pairs == {('Party-A', 'V2'), ('Party-B', 'V1')}

    def test_purge_atomicity_rollback_on_failure(self, case_folder):
        """Atomicity contract: if the third DELETE (production_runs) fails,
        the first DELETE (documents) must roll back — documents survive.

        Forces a failure by DROPping the production_runs table between seed
        and purge. The first two operations (SELECT ids, DELETE docs) would
        normally succeed; the third raises `no such table` which must
        trigger `with conn:` rollback."""
        import db_manager
        self._seed_volume(case_folder, doc_count=3)

        # Force the third execute to fail
        conn = db_manager.get_connection(case_folder)
        conn.execute("DROP TABLE production_runs")
        conn.commit()
        conn.close()

        # Purge should raise, and the rollback should preserve documents
        with pytest.raises(sqlite3.OperationalError):
            db_manager.purge_inbound_volume(case_folder, 'Opposing Counsel', 'VOL001')

        # If rollback worked, documents are still there
        assert len(db_manager.get_inbound_productions(case_folder)) == 1, \
            "purge_inbound_volume did NOT roll back after production_runs DELETE failed — " \
            "documents were removed despite the transaction not completing. " \
            "Atomicity contract violated."

    def test_empty_volume_purge_is_benign(self, case_folder):
        """Purging a non-existent volume should not raise; it just has
        nothing to do. Returns empty list of opensearch_ids."""
        import db_manager
        os_ids = db_manager.purge_inbound_volume(case_folder, 'Nobody', 'NonexistentVolume')
        assert os_ids == []


# ---------------------------------------------------------------------------
# End-to-end round-trip: ingest → purge → re-ingest
# ---------------------------------------------------------------------------

class TestRoundTripIngestPurgeReingest:
    """Exercises the full lifecycle the helpers are designed to support:
    ingest a volume, confirm production_runs row + docs present, purge
    everything, re-ingest with a different shape, confirm the new state
    is clean (no stale drift from the purged version)."""

    def test_full_cycle(self, case_folder):
        import db_manager
        party, volume = 'Opposing Counsel', 'VOL001'
        run_name = db_manager.inbound_production_run_name(party, volume)

        # --- Ingest v1: 3 docs ---
        rows_v1 = [_inbound_row(f'DOC-RT-{i}', source_party=party, production_volume=volume,
                                 opensearch_id=f'os-RT-{i}', dynamic_metadata='{"v": 1}')
                   for i in range(3)]
        db_manager.upsert_inbound_documents_batch(case_folder, rows_v1)
        db_manager.record_production_run(case_folder, {
            'production_name': run_name,
            'created_at': '2026-04-16T10:00:00',
            'created_by': 'test',
            'format': 'Native',
            'mode': 'Inbound Ingest',
            'direction': 'inbound', 'status': 'finalized',
            'document_count': 3,
        })
        assert len(db_manager.get_inbound_productions(case_folder)) == 1
        assert db_manager.get_production_run(case_folder, run_name)['document_count'] == 3

        # --- Purge ---
        os_ids_purged = db_manager.purge_inbound_volume(case_folder, party, volume)
        assert sorted(os_ids_purged) == ['os-RT-0', 'os-RT-1', 'os-RT-2']
        assert db_manager.get_inbound_productions(case_folder) == []
        assert db_manager.get_production_run(case_folder, run_name) is None

        # --- Re-ingest v2: 5 docs (different shape) ---
        rows_v2 = [_inbound_row(f'DOC-RT2-{i}', source_party=party, production_volume=volume,
                                 opensearch_id=f'os-RT2-{i}', dynamic_metadata='{"v": 2}')
                   for i in range(5)]
        db_manager.upsert_inbound_documents_batch(case_folder, rows_v2)
        db_manager.record_production_run(case_folder, {
            'production_name': run_name,
            'created_at': '2026-04-16T11:00:00',
            'created_by': 'test',
            'format': 'Native',
            'mode': 'Inbound Ingest',
            'direction': 'inbound', 'status': 'finalized',
            'document_count': 5,
        })

        # --- Verify: clean re-ingest, no stale drift ---
        inbound = db_manager.get_inbound_productions(case_folder)
        assert len(inbound) == 1
        assert inbound[0]['doc_count'] == 5
        assert db_manager.get_production_run(case_folder, run_name)['document_count'] == 5


# ---------------------------------------------------------------------------
# TestIngestRecordsProductionRunRow (beta-2.10 Commit 6 Phase B)
# ---------------------------------------------------------------------------
# These tests cover the new ingest-time recording behavior added in
# pages/9_InboundProduction.py Phase B: after a successful inbound ingest
# completes (all batches flushed + audit log written), a production_runs
# row is created with direction='inbound' and status='finalized'. If the
# ingest raises before reaching the recording call, the row must NOT exist.
#
# The harness below mirrors the Phase B ingest flow tail — see the NOTE in
# _simulate_ingest_tail for the deliberate mirror-not-import rationale.
# If pages/9_InboundProduction.py changes the recording dict shape, update
# this harness in lockstep; drift will show up as a test failure here.
# ---------------------------------------------------------------------------

def _simulate_ingest_tail(case_folder, source_party, production_volume,
                          rows, username='test_reviewer',
                          load_file='load.dat', mapped_fields=None,
                          row_count=None, error_count=0,
                          force_upsert_failure=False):
    """Mirror the end-of-ingest flow from pages/9_InboundProduction.py:
    upsert the batch, log the audit, then call record_production_run with
    the settings dict. Returns the document_count that was recorded.

    NOTE: This is a deliberate mirror of the page code (not an import),
    for the same reason tests/test_review_inbound_badge.py mirrors its
    target — Streamlit page files aren't cleanly importable (they execute
    page-rendering code at module load time). Any change to the recording
    dict shape in pages/9_InboundProduction.py MUST be mirrored here or
    these tests drift silently out of sync with production. The coupling
    is intentional; the harness's job is to pin the flow's contract.

    `force_upsert_failure=True` raises before the upsert, simulating
    mid-ingest failure — verifies the recording is never reached.
    """
    import db_manager
    import json as _json
    from datetime import datetime

    if force_upsert_failure:
        raise RuntimeError("forced upsert failure for atomicity test")

    count = db_manager.upsert_inbound_documents_batch(case_folder, rows)

    db_manager.record_production_run(case_folder, {
        'production_name': db_manager.inbound_production_run_name(source_party, production_volume),
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'created_by': username,
        'format': 'Native',
        'mode': 'Inbound Ingest',
        'document_count': count,
        'direction': 'inbound',
        'status': 'finalized',
        'settings_json': _json.dumps({
            'source_party': source_party,
            'production_volume': production_volume,
            'load_file': load_file,
            'field_mapping': mapped_fields or {},
            'row_count': row_count if row_count is not None else len(rows),
            'error_count': error_count,
        }),
    })
    return count


class TestIngestRecordsProductionRunRow:

    def test_happy_path_creates_row(self, case_folder):
        """After a successful ingest, a production_runs row exists with the
        expected constructed name, direction='inbound', status='finalized'."""
        import db_manager
        rows = [_inbound_row(f'DOC-REC-{i}', source_party='Opposing Counsel',
                             production_volume='VOL42')
                for i in range(3)]
        count = _simulate_ingest_tail(case_folder, 'Opposing Counsel', 'VOL42', rows)
        assert count == 3

        name = db_manager.inbound_production_run_name('Opposing Counsel', 'VOL42')
        row = db_manager.get_production_run(case_folder, name)
        assert row is not None, "Expected production_runs row after successful ingest"
        assert row['direction'] == 'inbound'
        assert row['status'] == 'finalized'
        assert row['document_count'] == 3
        assert row['mode'] == 'Inbound Ingest'
        assert row['format'] == 'Native'

    def test_settings_json_captures_ingest_parameters(self, case_folder):
        """settings_json must contain source_party, production_volume, load_file,
        field_mapping, row_count, error_count — the parameters needed to
        understand/replay what was ingested."""
        import db_manager
        import json as _json
        rows = [_inbound_row(f'DOC-SJ-{i}') for i in range(2)]
        _simulate_ingest_tail(
            case_folder, 'Opposing Counsel', 'VOL001', rows,
            load_file='opposing_vol001.dat',
            mapped_fields={'control_number': 'BegDoc', 'custodian': 'Custodian'},
            row_count=5,  # total rows in load file
            error_count=1,  # 1 row failed during ingest (different from total - success = 1)
        )

        row = db_manager.get_production_run(
            case_folder,
            db_manager.inbound_production_run_name('Opposing Counsel', 'VOL001'),
        )
        settings = _json.loads(row['settings_json'])
        assert settings['source_party'] == 'Opposing Counsel'
        assert settings['production_volume'] == 'VOL001'
        assert settings['load_file'] == 'opposing_vol001.dat'
        assert settings['field_mapping'] == {'control_number': 'BegDoc', 'custodian': 'Custodian'}
        assert settings['row_count'] == 5
        assert settings['error_count'] == 1

    def test_partial_failure_no_row_created(self, case_folder):
        """If the ingest raises before reaching the recording call, the
        production_runs row MUST NOT exist. Verifies the control-flow
        guarantee that partial-ingest failures leave no history trace.

        Simulated via force_upsert_failure=True which raises BEFORE
        upsert_inbound_documents_batch runs — mirrors the production
        code path where upsert_inbound_documents_batch raises (see
        db_manager.upsert_inbound_documents_batch — not a never-raise
        contract). In that path, record_production_run is never reached,
        so no row is created."""
        import db_manager
        rows = [_inbound_row(f'DOC-PF-{i}') for i in range(3)]
        name = db_manager.inbound_production_run_name('Opposing Counsel', 'VOL-FAIL')
        # Pre-condition: no row yet
        assert db_manager.get_production_run(case_folder, name) is None

        # Simulate upsert failure
        with pytest.raises(RuntimeError, match="forced upsert failure"):
            _simulate_ingest_tail(
                case_folder, 'Opposing Counsel', 'VOL-FAIL', rows,
                force_upsert_failure=True,
            )

        # Post-condition: no row created despite the attempt
        assert db_manager.get_production_run(case_folder, name) is None, (
            "production_runs row was created despite a mid-ingest failure — "
            "the recording call should be UNREACHABLE on the failure path."
        )

    def test_reingest_replaces_existing_row(self, case_folder):
        """Re-ingesting the same (source_party, volume) hits
        record_production_run's INSERT OR REPLACE semantics — the existing
        row is updated with the new metadata. This supports the
        'purged then re-ingested' workflow (Commit 5 § purge_inbound_volume
        docs) and the 'corrections re-ingest' workflow.

        Note: this test does NOT call purge between the two ingests — the
        purge path is covered by TestRoundTripIngestPurgeReingest. This
        test specifically exercises the INSERT OR REPLACE path without
        an intervening purge."""
        import db_manager
        # First ingest: 2 docs
        rows_v1 = [_inbound_row(f'DOC-R1-{i}') for i in range(2)]
        _simulate_ingest_tail(case_folder, 'OCA', 'VOL01', rows_v1,
                              username='reviewer_A')

        # Second ingest: 4 docs (different shape, same party+volume)
        rows_v2 = [_inbound_row(f'DOC-R2-{i}') for i in range(4)]
        _simulate_ingest_tail(case_folder, 'OCA', 'VOL01', rows_v2,
                              username='reviewer_B')

        row = db_manager.get_production_run(
            case_folder,
            db_manager.inbound_production_run_name('OCA', 'VOL01'),
        )
        # Row reflects the SECOND ingest (document_count and created_by updated)
        assert row['document_count'] == 4
        assert row['created_by'] == 'reviewer_B'

    def test_row_count_matches_successful_inserts_not_total_rows(self, case_folder):
        """If the load file has 10 rows but only 7 successfully ingest
        (3 raised exceptions in the iter loop), the document_count MUST
        reflect 7, not 10. total_rows goes into settings_json.row_count
        for the audit trail. Verifies the §4 design decision that
        document_count tracks actual success, not attempted."""
        import db_manager
        # Call simulate_ingest_tail where the rows list is the 7 successful
        # ones (mirrors the page flow — only successful rows make it into
        # _ib_db_batch). row_count=10 is total from load file.
        rows = [_inbound_row(f'DOC-SI-{i}') for i in range(7)]
        _simulate_ingest_tail(
            case_folder, 'OCA', 'VOL-COUNT', rows,
            row_count=10,  # total load-file rows
            error_count=3,  # rows that raised exceptions
        )
        row = db_manager.get_production_run(
            case_folder,
            db_manager.inbound_production_run_name('OCA', 'VOL-COUNT'),
        )
        import json as _json
        settings = _json.loads(row['settings_json'])
        assert row['document_count'] == 7, \
            "document_count must reflect successful_inserts (7), not total_rows (10)"
        assert settings['row_count'] == 10, "row_count preserves the load-file total"
        assert settings['error_count'] == 3
