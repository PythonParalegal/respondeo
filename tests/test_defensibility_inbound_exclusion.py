"""
test_defensibility_inbound_exclusion.py — integration tests for the mandatory
outbound source_party filter added in beta-2.10 Commit 3.

Five defensibility-function tests + one privilege log test + one E2E zero-
leakage regression. All seeded against a `mixed_party_case` fixture that
contains internal documents and one inbound (opposing counsel) document;
every outbound-destined surface must exclude the inbound document.

If any test here fails: an outbound query is missing the mandatory
`db_manager.OUTBOUND_SOURCE_FILTER_SQL` filter (or the alias-aware
`db_manager.outbound_source_filter_sql('d')`). The audit file at
_scratchpad/inbound_exclusion_coverage_audit.md inventories the expected
coverage; a new leak site should either be fixed or added to the audit
with explicit justification.
"""
import pytest


# ---------------------------------------------------------------------------
# Fixture: a case with two internal docs + one inbound (opposing counsel)
# ---------------------------------------------------------------------------

@pytest.fixture()
def mixed_party_case(case_folder):
    """Seed two internal documents + one inbound document. Attributes chosen
    to exercise every defensibility function (custodians, dates, file sizes,
    processing status, tags, privilege_status)."""
    import db_manager
    conn = db_manager.get_connection(case_folder)
    # (cn, file_name, ext, status, pages, tags, source_party, custodian,
    #  privilege_status, date_created, file_size_kb, extraction_method, is_encrypted, record_type)
    rows = [
        ("DOC-INT-001", "memo.pdf",          ".pdf", "Processed", 2, "Responsive",
         "Internal",         "Smith",           None,     "2026-01-01", 100, "pdf_native", 0, "Document"),
        ("DOC-INT-002", "email.eml",         ".eml", "Master",    1, "Not Responsive",
         "Internal",         "Jones",           None,     "2026-01-02",  50, "email_mime", 0, "Email"),
        ("DOC-INB-001", "opposing_memo.pdf", ".pdf", "Processed", 5, "Responsive",
         "Opposing Counsel", "OppC Custodian",  "Redact", "2026-01-03", 200, "pdf_native", 0, "Document"),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO documents
           (control_number, file_name, file_extension, processing_status, page_count,
            tags, source_party, custodian, privilege_status, date_created, file_size_kb,
            extraction_method, is_encrypted, record_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return case_folder


# ---------------------------------------------------------------------------
# Per-function defensibility tests (5 categories)
# ---------------------------------------------------------------------------

class TestDefensibilityOverviewExcludesInbound:

    def test_total_documents_counts_only_internal(self, mixed_party_case):
        import db_manager
        data = db_manager.get_defensibility_overview(mixed_party_case)
        assert data['total_documents'] == 2, (
            f"Expected 2 internal docs, got {data['total_documents']}. "
            f"Inbound doc leaked into overview total."
        )

    def test_total_custodians_excludes_inbound_custodian(self, mixed_party_case):
        import db_manager
        data = db_manager.get_defensibility_overview(mixed_party_case)
        # Smith + Jones = 2; OppC Custodian must not be counted
        assert data['total_custodians'] == 2

    def test_date_range_reflects_internal_only(self, mixed_party_case):
        """INB-001 has date_created='2026-01-03' (latest). If leaked, it would
        appear as the 'latest' date. Verify latest is 2026-01-02 (INT-002)."""
        import db_manager
        data = db_manager.get_defensibility_overview(mixed_party_case)
        assert data['date_range_latest'] == '2026-01-02'
        assert data['date_range_earliest'] == '2026-01-01'


class TestDefensibilityIngestionExcludesInbound:

    def test_custodian_breakdown_excludes_inbound_custodian(self, mixed_party_case):
        import db_manager
        data = db_manager.get_defensibility_ingestion(mixed_party_case)
        custodians = [c['custodian'] for c in data['custodians']]
        assert 'Smith' in custodians
        assert 'Jones' in custodians
        assert 'OppC Custodian' not in custodians

    def test_total_size_excludes_inbound_bytes(self, mixed_party_case):
        """INT-001 (100kb) + INT-002 (50kb) = 150. INB-001's 200kb must not add."""
        import db_manager
        data = db_manager.get_defensibility_ingestion(mixed_party_case)
        assert data['total_size_kb'] == 150

    def test_file_types_exclude_inbound_pdf(self, mixed_party_case):
        """Both INT-001 and INB-001 are .pdf. After filter, .pdf count = 1 (not 2)."""
        import db_manager
        data = db_manager.get_defensibility_ingestion(mixed_party_case)
        pdf_row = next((ft for ft in data['file_types'] if ft['ext'] == '.pdf'), None)
        assert pdf_row is not None
        assert pdf_row['count'] == 1


class TestDefensibilityProcessingExcludesInbound:

    def test_status_breakdown_total_excludes_inbound(self, mixed_party_case):
        """INT-001 Processed + INT-002 Master + INB-001 Processed = 3 total rows,
        but only the 2 internal docs should count."""
        import db_manager
        data = db_manager.get_defensibility_processing(mixed_party_case)
        total = sum(row['count'] for row in data['status_breakdown'])
        assert total == 2

    def test_extraction_method_counts_exclude_inbound(self, mixed_party_case):
        """pdf_native appears on both INT-001 and INB-001; after filter, count=1."""
        import db_manager
        data = db_manager.get_defensibility_processing(mixed_party_case)
        pdf_native = next((m for m in data['extraction_methods'] if m['method'] == 'pdf_native'), None)
        assert pdf_native is not None
        assert pdf_native['count'] == 1


class TestDefensibilityDedupExcludesInbound:

    def test_total_ingested_excludes_inbound(self, mixed_party_case):
        import db_manager
        data = db_manager.get_defensibility_dedup(mixed_party_case)
        assert data['total_ingested'] == 2

    def test_net_reviewable_excludes_inbound(self, mixed_party_case):
        """net_reviewable has parenthesized OR clauses for NearDupe/Thread
        suppression — this verifies the outbound filter appends correctly
        without breaking operator precedence in the 9-query dedup block."""
        import db_manager
        data = db_manager.get_defensibility_dedup(mixed_party_case)
        assert data['net_reviewable'] == 2  # INT-001 + INT-002, not INB-001


class TestDefensibilityReviewExcludesInbound:

    def test_responsive_count_excludes_inbound_responsive(self, mixed_party_case):
        """INB-001 has tags='Responsive' — would be counted if filter missing.
        Only INT-001 (internal, Responsive) should count."""
        import db_manager
        data = db_manager.get_defensibility_review(mixed_party_case)
        assert data['responsive_count'] == 1

    def test_not_responsive_count_excludes_inbound(self, mixed_party_case):
        """Only INT-002 has 'Not Responsive' tag. INB-001 doesn't, but this
        verifies the filter is always applied (not just when inbound-tagged)."""
        import db_manager
        data = db_manager.get_defensibility_review(mixed_party_case)
        assert data['not_responsive_count'] == 1

    def test_total_reviewable_excludes_inbound(self, mixed_party_case):
        """Exercises the parenthesized-OR case (3 OR blocks in this query)."""
        import db_manager
        data = db_manager.get_defensibility_review(mixed_party_case)
        assert data['total_reviewable'] == 2


# ---------------------------------------------------------------------------
# Privilege log test
# ---------------------------------------------------------------------------

class TestPrivilegeLogExcludesInbound:
    """The privilege log query lives inline in pages/5_Production.py at the
    _pl_query f-string. We replicate its WHERE-clause shape here to verify
    the outbound filter (aliased form with 'd.' prefix) correctly excludes
    inbound docs even when they carry a privilege_status tag.

    26(g) hazard: if a reviewer accidentally tags an inbound doc as
    Withhold/Redact, it must NEVER appear on the privilege log exported to
    opposing counsel.
    """

    def test_inbound_doc_with_redact_tag_not_in_privilege_log(self, mixed_party_case):
        """INB-001 has privilege_status='Redact' in the fixture. The privilege
        log query pattern must exclude it via the mandatory outbound filter."""
        import db_manager
        conn = db_manager.get_connection(mixed_party_case)
        try:
            _pl_outbound = db_manager.outbound_source_filter_sql('d')
            query = f"""
                SELECT d.control_number
                FROM documents d
                WHERE d.privilege_status IN ('Withhold', 'Redact')
                  AND {_pl_outbound}
            """
            cns = [r['control_number'] for r in conn.execute(query).fetchall()]
            assert 'DOC-INB-001' not in cns, (
                "Inbound doc with privilege_status='Redact' leaked into privilege log. "
                "This is a 26(g) hazard — the log may be exported to opposing counsel "
                "and must not contain their own documents."
            )
        finally:
            conn.close()

    def test_internal_doc_with_redact_tag_does_appear(self, case_folder):
        """Control: without the inbound filter catching them, internal privileged
        docs must still appear. Defends against over-filtering regressions."""
        import db_manager
        conn = db_manager.get_connection(case_folder)
        conn.execute(
            """INSERT OR IGNORE INTO documents
               (control_number, file_name, file_extension, processing_status,
                source_party, privilege_status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("DOC-INT-PRIV", "internal_memo.pdf", ".pdf", "Processed", "Internal", "Redact"),
        )
        conn.commit()
        try:
            _pl_outbound = db_manager.outbound_source_filter_sql('d')
            query = f"""
                SELECT d.control_number FROM documents d
                WHERE d.privilege_status IN ('Withhold', 'Redact')
                  AND {_pl_outbound}
            """
            cns = [r['control_number'] for r in conn.execute(query).fetchall()]
            assert 'DOC-INT-PRIV' in cns
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# E2E regression: zero leakage across all outbound surfaces
# ---------------------------------------------------------------------------

class TestE2EInboundZeroLeakage:
    """End-to-end defensibility backstop. If any single outbound surface
    forgets the mandatory outbound filter, this one test catches it.

    Mirrors the audit file's coverage inventory: every surface enumerated
    there gets a leakage assertion here. Adding a new outbound surface to
    the codebase must come with a new assertion in this test."""

    def test_inbound_doc_never_leaks_across_any_outbound_surface(self, mixed_party_case):
        import db_manager
        INBOUND_CN = 'DOC-INB-001'

        # Surface 1: defensibility overview
        overview = db_manager.get_defensibility_overview(mixed_party_case)
        assert overview['total_documents'] == 2, \
            "LEAK: inbound doc counted in defensibility overview total"

        # Surface 2: defensibility ingestion custodian breakdown
        ingestion = db_manager.get_defensibility_ingestion(mixed_party_case)
        custodians = [c['custodian'] for c in ingestion['custodians']]
        assert 'OppC Custodian' not in custodians, \
            "LEAK: inbound custodian in defensibility ingestion custodian breakdown"
        assert ingestion['total_size_kb'] == 150, \
            "LEAK: inbound file size added to defensibility total_size_kb"

        # Surface 3: defensibility processing status breakdown
        processing = db_manager.get_defensibility_processing(mixed_party_case)
        processing_total = sum(r['count'] for r in processing['status_breakdown'])
        assert processing_total == 2, \
            "LEAK: inbound doc in defensibility processing status breakdown"

        # Surface 4: defensibility dedup totals (parenthesized-OR case)
        dedup = db_manager.get_defensibility_dedup(mixed_party_case)
        assert dedup['total_ingested'] == 2, \
            "LEAK: inbound doc in defensibility dedup total_ingested"
        assert dedup['net_reviewable'] == 2, \
            "LEAK: inbound doc in defensibility dedup net_reviewable (parenthesized-OR)"

        # Surface 5: defensibility review (responsive/not-responsive counts)
        review = db_manager.get_defensibility_review(mixed_party_case)
        assert review['responsive_count'] == 1, \
            "LEAK: inbound doc with 'Responsive' tag in defensibility review responsive_count"
        assert review['total_reviewable'] == 2, \
            "LEAK: inbound doc in defensibility review total_reviewable (parenthesized-OR)"

        # Surface 6: privilege log SQL (aliased form)
        conn = db_manager.get_connection(mixed_party_case)
        try:
            _pl_outbound = db_manager.outbound_source_filter_sql('d')
            priv_cns = [r['control_number'] for r in conn.execute(f"""
                SELECT d.control_number FROM documents d
                WHERE d.privilege_status IN ('Withhold', 'Redact')
                  AND {_pl_outbound}
            """).fetchall()]
            assert INBOUND_CN not in priv_cns, \
                "LEAK: inbound doc with privilege tag in privilege log query"
        finally:
            conn.close()

        # Surface 7: production assembly base query (unaliased constant form)
        conn = db_manager.get_connection(mixed_party_case)
        try:
            prod_cns = [r[0] for r in conn.execute(f"""
                SELECT control_number FROM documents
                WHERE processing_status IN ('Processed', 'Master')
                  AND {db_manager.OUTBOUND_SOURCE_FILTER_SQL}
            """).fetchall()]
            assert INBOUND_CN not in prod_cns, \
                "LEAK: inbound doc in production assembly base query"
        finally:
            conn.close()
