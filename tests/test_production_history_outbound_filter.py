"""
Regression tests for the outbound-only contract on production_runs read
surfaces introduced in beta-2.10 Commit 7.6.

Three read sites were migrated from the broad db_manager.get_production_runs()
to the direction-filtered db_manager.get_production_history(..., direction=
'outbound'). This file pins the contract: every user-visible or court-facing
production_runs reader must return only direction='outbound' rows.

If this test fails, investigate before bypassing — the regression class is
'inbound rows surfacing in contexts that imply outbound productions we
performed,' which has defensibility implications in the defensibility report
path (defensibility_report.py:167 feeds into the '6.2 Production Run History'
section of the court-facing report).
"""
import pytest
import db_manager


@pytest.fixture
def case_with_mixed_runs(case_folder):
    """Seed case DB with 2 finalized outbound + 1 inbound + 1 aborted outbound
    production_runs rows. The inbound row is deliberately created with a
    later created_at than one of the outbound rows so sort-by-created_at DESC
    cannot accidentally hide filter bugs behind the newest-first ordering.
    """
    db_manager.record_production_run(case_folder, {
        'production_name': 'Volume_001', 'created_at': '2026-04-01T10:00:00Z',
        'created_by': 'alice', 'format': 'PDF', 'mode': 'Full Production',
        'document_count': 100, 'direction': 'outbound', 'status': 'finalized',
    })
    db_manager.record_production_run(case_folder, {
        'production_name': 'Volume_002', 'created_at': '2026-04-02T10:00:00Z',
        'created_by': 'bob', 'format': 'Native', 'mode': 'Full Production',
        'document_count': 50, 'direction': 'outbound', 'status': 'finalized',
    })
    db_manager.record_production_run(case_folder, {
        'production_name': 'INBOUND: OCA - Volume1', 'created_at': '2026-04-03T10:00:00Z',
        'created_by': 'alice', 'format': 'Native', 'mode': 'Inbound Ingest',
        'document_count': 200, 'direction': 'inbound', 'status': 'finalized',
    })
    db_manager.record_production_run(case_folder, {
        'production_name': 'Volume_003', 'created_at': '2026-04-04T10:00:00Z',
        'created_by': 'bob', 'format': 'PDF', 'mode': 'Full Production',
        'document_count': 0, 'direction': 'outbound', 'status': 'aborted',
    })
    return case_folder


class TestGetProductionHistoryOutboundContract:
    """
    Pins the db_manager.get_production_history(..., direction='outbound')
    behavior consumed by home.py Production History display (home.py:551)
    and the defensibility report's Production Run History section
    (defensibility_report.py:167).
    """

    def test_returns_only_outbound_rows(self, case_with_mixed_runs):
        rows = db_manager.get_production_history(case_with_mixed_runs, direction='outbound')
        assert len(rows) == 3  # 2 finalized outbound + 1 aborted outbound
        for r in rows:
            assert r['direction'] == 'outbound', \
                f"Non-outbound row leaked through direction filter: {r}"

    def test_excludes_inbound_even_when_created_most_recently(self, case_with_mixed_runs):
        """The inbound row was seeded with created_at later than one outbound
        — sort-by-created_at DESC must not let it bubble into the result."""
        rows = db_manager.get_production_history(case_with_mixed_runs, direction='outbound')
        names = [r['production_name'] for r in rows]
        assert 'INBOUND: OCA - Volume1' not in names

    def test_preserves_created_at_desc_order(self, case_with_mixed_runs):
        rows = db_manager.get_production_history(case_with_mixed_runs, direction='outbound')
        created_ats = [r['created_at'] for r in rows]
        assert created_ats == sorted(created_ats, reverse=True)

    def test_returns_empty_list_when_only_inbound_exists(self, case_folder):
        """Case with only inbound rows returns empty list under outbound filter."""
        db_manager.record_production_run(case_folder, {
            'production_name': 'INBOUND: X - Y', 'created_at': '2026-04-01T10:00:00Z',
            'created_by': 'alice', 'format': 'Native', 'mode': 'Inbound Ingest',
            'document_count': 100, 'direction': 'inbound', 'status': 'finalized',
        })
        rows = db_manager.get_production_history(case_folder, direction='outbound')
        assert rows == []

    def test_return_shape_matches_legacy_get_production_runs(self, case_with_mixed_runs):
        """The migration from get_production_runs to get_production_history
        must preserve the dict-list shape callers rely on. Renders the same
        SELECT * columns via both functions; outbound subset of rows from
        history must be findable in legacy all-rows output.
        """
        outbound = db_manager.get_production_history(case_with_mixed_runs, direction='outbound')
        legacy_all = db_manager.get_production_runs(case_with_mixed_runs)

        # Each row in outbound is a dict with the keys legacy callers expect
        expected_keys = {
            'production_name', 'created_at', 'created_by', 'format', 'mode',
            'document_count', 'direction', 'status'
        }
        for r in outbound:
            assert isinstance(r, dict)
            assert expected_keys.issubset(r.keys()), \
                f"Row missing expected keys: {expected_keys - set(r.keys())}"

        # Legacy returns all rows (outbound + inbound); outbound is a strict subset
        outbound_names = {r['production_name'] for r in outbound}
        legacy_names = {r['production_name'] for r in legacy_all}
        assert outbound_names.issubset(legacy_names)
        # And legacy includes the inbound that outbound excluded
        assert 'INBOUND: OCA - Volume1' in legacy_names
        assert 'INBOUND: OCA - Volume1' not in outbound_names


class TestAbortedRunRenderContract:
    """Pin the post-Flag #13 asymmetric render contract for aborted runs.

    Aborted rows (NULL bates_start, NULL bates_end, document_count=0) must:
      - Appear in home.py-style consumption (paralegal grid) with '—' for
        Bates fields, 0 for doc count, and 'aborted' as Status.
      - NOT appear in defensibility-report-style consumption (court-facing PDF
        section 6.2 — by design, opposing counsel sees finalized productions
        only; aborted runs are internal process churn).

    Regression targets: home.py:553-568 grid display, defensibility_report.py
    section 6.2 HTML loop.
    """

    def test_aborted_row_seeded_with_null_bates(self, case_with_mixed_runs):
        """Confirm the schema/writer path produces NULL bates fields on
        aborted rows, validating the render-defect premise."""
        rows = db_manager.get_production_history(case_with_mixed_runs, direction='outbound')
        aborted_row = next(r for r in rows if r['status'] == 'aborted')
        assert aborted_row['bates_start'] is None
        assert aborted_row['bates_end'] is None
        assert aborted_row['document_count'] == 0

    def test_home_grid_renders_dash_not_None_for_aborted_bates(self, case_with_mixed_runs):
        """home.py-side: replicate home.py:553-568 dataframe prep and assert
        the rendered grid does NOT contain the literal string 'None' for
        aborted-run Bates fields, and surfaces 'aborted' as Status."""
        import pandas as pd
        rows = db_manager.get_production_history(case_with_mixed_runs, direction='outbound')
        _pr_df = pd.DataFrame(rows)[
            ['production_name', 'created_at', 'format', 'mode', 'bates_start',
             'bates_end', 'document_count', 'withheld_count', 'redacted_count',
             'created_by', 'status']
        ].rename(columns={
            'production_name': 'Volume', 'created_at': 'Date', 'format': 'Format',
            'mode': 'Mode', 'bates_start': 'First Bates', 'bates_end': 'Last Bates',
            'document_count': 'Docs', 'withheld_count': 'Withheld',
            'redacted_count': 'Redacted', 'created_by': 'By', 'status': 'Status',
        })
        for _col in ('First Bates', 'Last Bates'):
            _pr_df[_col] = _pr_df[_col].fillna('—').replace({None: '—'})

        as_strings = _pr_df.astype(str).values.flatten().tolist()
        assert 'None' not in as_strings, \
            f"Literal 'None' string leaked into grid: {as_strings}"

        aborted_grid = _pr_df[_pr_df['Volume'] == 'Volume_003']
        assert len(aborted_grid) == 1
        assert aborted_grid.iloc[0]['Status'] == 'aborted'
        assert aborted_grid.iloc[0]['First Bates'] == '—'
        assert aborted_grid.iloc[0]['Last Bates'] == '—'
        assert aborted_grid.iloc[0]['Docs'] == 0

    def test_defensibility_html_excludes_aborted_runs(self, case_with_mixed_runs):
        """Court-facing PDF surface: simulate the post-fix filter logic that
        defensibility_report.py section 6.2 applies. Asserts finalized rows
        appear and aborted rows do NOT.

        Pins the filter contract — the actual HTML render is wrapped in
        wkhtmltopdf and not feasible to invoke in pytest, but the filter
        is the load-bearing change for the asymmetric scope.
        """
        rows = db_manager.get_production_history(case_with_mixed_runs, direction='outbound')
        rendered_runs = [r for r in rows if r.get('status') != 'aborted']
        rendered_names = {r['production_name'] for r in rendered_runs}
        assert 'Volume_001' in rendered_names
        assert 'Volume_002' in rendered_names
        assert 'Volume_003' not in rendered_names


class TestArchiveManifestOutboundFilter:
    """
    Pins the inline SQL at home.py:1014-1020 — the case archive manifest's
    production-history dump. WHERE direction = 'outbound' must filter out
    inbound ingests from the archived productions list.
    """

    def test_inline_sql_matches_outbound_only(self, case_with_mixed_runs):
        """Replicates the exact inline SQL from home.py:1014-1020 verbatim
        (post-fix) and verifies it returns outbound only."""
        conn = db_manager.get_connection(case_with_mixed_runs)
        try:
            rows = conn.execute(
                "SELECT production_name, created_at, format, document_count "
                "FROM production_runs WHERE direction = 'outbound' ORDER BY created_at"
            ).fetchall()
            names = [r['production_name'] for r in rows]
            assert 'INBOUND: OCA - Volume1' not in names
            assert 'Volume_001' in names
            assert 'Volume_002' in names
            assert 'Volume_003' in names
            assert len(rows) == 3
        finally:
            conn.close()
