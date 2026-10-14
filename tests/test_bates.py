"""
test_bates.py — regression tests for Bates numbering logic.

Tests the Bates string formatting formula used in 5_Production.py and
the last-Bates persistence helpers in db_manager (supplemental production).
"""
import pytest


# ---------------------------------------------------------------------------
# Bates string formatting (mirrors the inline logic in 5_Production.py)
# ---------------------------------------------------------------------------

def _beg(prefix, num, padding):
    return f"{prefix}-{str(num).zfill(padding)}"

def _end(prefix, num, page_count, padding):
    return f"{prefix}-{str(num + page_count - 1).zfill(padding)}"


class TestBatesFormat:

    def test_single_page_begdoc_equals_enddoc(self):
        assert _beg("ABC", 1, 6) == _end("ABC", 1, 1, 6)

    def test_multipage_end_is_beg_plus_pages_minus_one(self):
        beg = _beg("ABC", 1, 6)
        end = _end("ABC", 1, 5, 6)
        assert beg == "ABC-000001"
        assert end == "ABC-000005"

    def test_padding_respected(self):
        assert _beg("XYZ", 1, 4) == "XYZ-0001"
        assert _beg("XYZ", 1, 8) == "XYZ-00000001"

    def test_prefix_preserved(self):
        assert _beg("SMITH-JONES", 42, 6).startswith("SMITH-JONES-")

    def test_sequence_is_continuous_across_docs(self):
        """Simulate assigning Bates across 4 docs; verify no gaps."""
        docs = [
            {"pages": 3},
            {"pages": 1},
            {"pages": 10},
            {"pages": 2},
        ]
        prefix, padding = "ABC", 6
        current_num = 1
        ranges = []
        for doc in docs:
            beg = current_num
            end = current_num + doc["pages"] - 1
            ranges.append((beg, end))
            current_num += doc["pages"]

        # Check continuity: each end + 1 == next beg
        for i in range(len(ranges) - 1):
            assert ranges[i][1] + 1 == ranges[i + 1][0], (
                f"Gap detected between doc {i} end ({ranges[i][1]}) "
                f"and doc {i+1} beg ({ranges[i+1][0]})"
            )

    def test_supplemental_start_continues_from_last_end(self):
        """Vol II must start at last_end + 1 — no overlap, no gap."""
        vol1_start, vol1_pages = 1, 50
        vol1_end = vol1_start + vol1_pages - 1  # 50

        vol2_start = vol1_end + 1               # 51
        assert vol2_start == 51

    def test_large_bates_number(self):
        bates = _beg("ABC", 999_999, 6)
        assert bates == "ABC-999999"

    def test_bates_overflow_pads_beyond_width(self):
        """Numbers exceeding padding width must not be truncated."""
        bates = _beg("ABC", 1_000_001, 6)
        assert bates == "ABC-1000001"  # zfill doesn't truncate


# ---------------------------------------------------------------------------
# Bates token parser (pinned-value: sidebar Bates Lookup and Bulk Bates
# popover batch search in pages/4_Review.py both route through
# db_manager.parse_bates_token. Prior to v2.12.x they used divergent regexes
# and the popover's could not parse hyphenated Bates — degenerate tokens
# compared equal so every input matched every row-with-unparseable-Bates.
# If either call site is rewritten to stop using this helper, the Bulk Bates
# banner and grid will silently drift again. Keep them pinned.)
# ---------------------------------------------------------------------------

class TestParseBatesToken:

    def test_hyphenated_format(self):
        import db_manager
        assert db_manager.parse_bates_token("ABC-000700") == ("ABC", 700)

    def test_concatenated_format(self):
        import db_manager
        assert db_manager.parse_bates_token("ABC000700") == ("ABC", 700)

    def test_multi_segment_prefix_with_hyphen(self):
        import db_manager
        # Real-world prefix style e.g. from a merged firm's production stamp.
        assert db_manager.parse_bates_token("SMITH-JONES-000042") == ("SMITH-JONES", 42)

    def test_lowercase_prefix_uppercased(self):
        import db_manager
        assert db_manager.parse_bates_token("abc-001") == ("ABC", 1)

    def test_trailing_whitespace_tolerated(self):
        import db_manager
        assert db_manager.parse_bates_token("ABC-000700   ") == ("ABC", 700)

    def test_empty_string_returns_none(self):
        import db_manager
        assert db_manager.parse_bates_token("") == (None, None)

    def test_none_input_returns_none(self):
        import db_manager
        assert db_manager.parse_bates_token(None) == (None, None)

    def test_no_digits_returns_none(self):
        import db_manager
        # Critical: two unparseable inputs must NOT compare equal via the
        # helper. Returning (None, None) lets callers guard with `is None`
        # and skip. The prior inline parser returned ('', -1) which compared
        # equal across every unparseable token and caused the over-match.
        assert db_manager.parse_bates_token("ABC-XYZ") == (None, None)

    def test_bulk_bates_and_lookup_use_same_helper(self):
        """Pinned-value: both Review-page Bates features route through the
        same helper, so prefix/number parsing agrees by construction. Any
        regression that bypasses this function re-opens the divergence bug.
        """
        import db_manager
        f = db_manager.parse_bates_token
        # The exact invariant both callers depend on:
        assert f("ABC-000415") == f("abc-000415") == ("ABC", 415)
        assert f("ABC-000415") != f("ABC-000416")  # distinct nums stay distinct


# ---------------------------------------------------------------------------
# Last Bates persistence (supplemental production)
# ---------------------------------------------------------------------------

class TestLastBatesPersistence:

    def test_no_prior_production_returns_none(self, case_folder):
        import db_manager
        assert db_manager.get_last_bates_info(case_folder) is None

    def test_saved_info_is_retrievable(self, case_folder):
        import db_manager
        db_manager.save_last_bates_info(case_folder, "ABC", 150, "PRODUCTION_001", 6)
        info = db_manager.get_last_bates_info(case_folder)
        assert info["prefix"] == "ABC"
        assert info["end_num"] == 150
        assert info["prod_name"] == "PRODUCTION_001"
        assert info["padding"] == 6

    def test_supplemental_start_from_stored_end(self, case_folder):
        import db_manager
        db_manager.save_last_bates_info(case_folder, "DEF", 300, "VOL1", 6)
        info = db_manager.get_last_bates_info(case_folder)
        next_start = info["end_num"] + 1
        assert next_start == 301
        assert _beg(info["prefix"], next_start, info["padding"]) == "DEF-000301"

    def test_second_production_overwrites_first(self, case_folder):
        import db_manager
        db_manager.save_last_bates_info(case_folder, "ABC", 50,  "VOL1", 6)
        db_manager.save_last_bates_info(case_folder, "ABC", 100, "VOL2", 6)
        info = db_manager.get_last_bates_info(case_folder)
        assert info["end_num"] == 100
        assert info["prod_name"] == "VOL2"

    def test_end_num_is_stored_as_integer(self, case_folder):
        import db_manager
        db_manager.save_last_bates_info(case_folder, "ABC", 42, "VOL1", 6)
        info = db_manager.get_last_bates_info(case_folder)
        assert isinstance(info["end_num"], int)


# ---------------------------------------------------------------------------
# Production family-expansion filtering (mirrors the inline logic at
# 5_Production.py lines ~2549-2610). Regression guard for the defect where
# FIX #8 family expansion pulled non-responsive / suppressed / external /
# previously-produced attachments into production despite the user's
# exclusion checkboxes being set.
# ---------------------------------------------------------------------------

def _build_exclusion_sql(exclude_previously_produced, exclude_suppressed,
                         exclude_non_responsive):
    """Build the user-toggleable exclusion fragment. The mandatory outbound
    source_party filter is applied separately via db_manager.OUTBOUND_SOURCE_FILTER_SQL
    (beta-2.10 Commit 3) and is no longer user-configurable — do NOT include
    a source_party clause here."""
    clauses = []
    if exclude_previously_produced:
        clauses.append("(begdoc IS NULL OR begdoc = '')")
    if exclude_suppressed:
        clauses.append("(tags NOT LIKE '%Suppressed%' OR tags IS NULL)")
    if exclude_non_responsive:
        clauses.append(
            "(tags NOT LIKE '%Non-Responsive%' OR tags IS NULL) "
            "AND (tags NOT LIKE '%Not Responsive%' OR tags IS NULL)"
        )
    return (" AND " + " AND ".join(clauses)) if clauses else ""


def _run_production_selection(case_folder, *, exclude_previously_produced=True,
                              exclude_suppressed=True, exclude_non_responsive=True):
    """
    Replicate the base-set + FIX #8 family-expansion logic from
    5_Production.py (beta-2.10 Commit 3 version). Returns the list of
    control_numbers that would be produced.

    The mandatory outbound source_party filter
    (db_manager.OUTBOUND_SOURCE_FILTER_SQL) is always applied to every query
    path — no longer user-toggleable.
    """
    import db_manager
    import pandas as pd
    conn = db_manager.get_connection(case_folder)
    try:
        _exclusion_sql = _build_exclusion_sql(
            exclude_previously_produced, exclude_suppressed, exclude_non_responsive,
        )
        _outbound = db_manager.OUTBOUND_SOURCE_FILTER_SQL

        base_query = (
            f"SELECT * FROM documents WHERE processing_status IN ('Processed', 'Master') "
            f"AND {_outbound}"
            + _exclusion_sql
        )
        base_df = pd.read_sql_query(base_query, conn)

        if base_df.empty:
            return []

        hierarchy_df = pd.read_sql_query(
            "SELECT control_number, parent_id FROM documents", conn
        )
        parent_map = dict(zip(hierarchy_df['control_number'], hierarchy_df['parent_id']))

        def get_root(cn):
            curr = cn
            visited = set()
            while curr in parent_map and pd.notna(parent_map[curr]) \
                    and str(parent_map[curr]).strip() != '':
                if curr in visited:
                    break
                visited.add(curr)
                curr = parent_map[curr]
            return curr

        affected_roots = set(base_df['control_number'].apply(get_root))
        all_target_cns = [cn for cn in parent_map if get_root(cn) in affected_roots]

        if not all_target_cns:
            return list(base_df['control_number'])

        placeholders = ','.join(['?'] * len(all_target_cns))
        family_sql = (
            f"SELECT * FROM documents WHERE control_number IN ({placeholders}) "
            f"AND processing_status IN ('Processed', 'Master') "
            f"AND {_outbound}{_exclusion_sql}"
        )
        family_df = pd.read_sql_query(family_sql, conn, params=all_target_cns)

        merged = pd.concat([base_df, family_df]).drop_duplicates(subset='id')
        return sorted(merged['control_number'].tolist())
    finally:
        conn.close()


@pytest.fixture()
def family_case(case_folder):
    """
    Seeds a case with one responsive parent email and three attachments:
    responsive, non-responsive, and suppressed. Used by the family-expansion
    filter tests below.
    """
    import db_manager
    conn = db_manager.get_connection(case_folder)
    # (control_number, parent_id, file_name, ext, status, pages, tags, source_party, begdoc)
    rows = [
        ("DOC-00100", None,        "email.eml",  ".eml",   "Processed", 1, "",               "Internal", None),
        ("DOC-00101", "DOC-00100", "good.pdf",   ".pdf",   "Processed", 3, "",               "Internal", None),
        ("DOC-00102", "DOC-00100", "junk.png",   ".png",   "Processed", 1, "Not Responsive", "Internal", None),
        ("DOC-00103", "DOC-00100", "spam.txt",   ".txt",   "Processed", 1, "Suppressed",     "Internal", None),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO documents
           (control_number, parent_id, file_name, file_extension,
            processing_status, page_count, tags, source_party, begdoc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return case_folder


class TestProductionFamilyFiltering:

    def test_non_responsive_attachment_excluded_by_default(self, family_case):
        """Responsive parent must not drag its non-responsive child into production."""
        produced = _run_production_selection(family_case)
        assert "DOC-00100" in produced, "responsive parent must be produced"
        assert "DOC-00101" in produced, "responsive attachment must be produced"
        assert "DOC-00102" not in produced, \
            "non-responsive attachment leaked into production (FIX #8 family-expansion bug)"

    def test_suppressed_attachment_excluded_by_default(self, family_case):
        produced = _run_production_selection(family_case)
        assert "DOC-00103" not in produced, \
            "suppressed attachment leaked into production"

    def test_non_responsive_included_when_flag_off(self, family_case):
        """Flipping exclude_non_responsive=False must include the non-responsive child."""
        produced = _run_production_selection(family_case, exclude_non_responsive=False)
        assert "DOC-00102" in produced
        # Suppressed still excluded (its flag is still on)
        assert "DOC-00103" not in produced

    def test_all_exclusions_off_produces_full_family(self, family_case):
        """With all user-toggleable exclusions off, all 4 seeded docs (all
        source_party='Internal') must appear. The mandatory outbound filter
        still applies but doesn't affect this fixture since no inbound docs
        are seeded — that path is covered by tests/test_defensibility_inbound_exclusion.py."""
        produced = _run_production_selection(
            family_case,
            exclude_previously_produced=False,
            exclude_suppressed=False,
            exclude_non_responsive=False,
        )
        assert set(produced) == {"DOC-00100", "DOC-00101", "DOC-00102", "DOC-00103"}

    def test_exclusion_sql_fragment_shape(self):
        """The shared fragment must begin with ' AND ' or be empty.
        source_party is NOT in this fragment anymore — it moved to the
        mandatory OUTBOUND_SOURCE_FILTER_SQL constant in beta-2.10 Commit 3."""
        assert _build_exclusion_sql(False, False, False) == ""
        frag = _build_exclusion_sql(True, True, True)
        assert frag.startswith(" AND ")
        assert "Non-Responsive" in frag
        assert "Not Responsive" in frag
        assert "Suppressed" in frag
        assert "source_party" not in frag, \
            "source_party must NOT be in the toggleable fragment — it lives in OUTBOUND_SOURCE_FILTER_SQL"
        assert "begdoc IS NULL" in frag


# ===========================================================================
# Family-expansion helper coverage (beta-2.15 Commit 3)
# ===========================================================================
# Mirrors pages/4_Review.py::_expand_to_families. Per the project's
# test-inlining-by-design convention (see beta-2.14 C13 / Flag #16 WONTFIX),
# the test helper duplicates the production helper rather than importing it,
# so the tests stay headless (no Streamlit runtime required) and serve as
# a regression snapshot of the contract. If the production helper drifts
# in shape, manual UI verification (preflight §5.2 Track 1+2) catches it.

def _expand_to_families_under_test(matched_cns, conn):
    if not matched_cns:
        return matched_cns
    placeholders = ",".join("?" * len(matched_cns))
    rows = conn.execute(
        f"SELECT DISTINCT group_id FROM documents "
        f"WHERE control_number IN ({placeholders}) "
        f"  AND group_id IS NOT NULL AND group_id != ''",
        list(matched_cns),
    ).fetchall()
    group_ids = [r['group_id'] for r in rows]
    if not group_ids:
        return matched_cns
    placeholders2 = ",".join("?" * len(group_ids))
    fam_rows = conn.execute(
        f"SELECT control_number FROM documents "
        f"WHERE group_id IN ({placeholders2})",
        group_ids,
    ).fetchall()
    return matched_cns | {r['control_number'] for r in fam_rows}


@pytest.fixture()
def family_expand_case(case_folder):
    """
    Seeds a case with two families (group_id-keyed) plus a NULL-group orphan,
    for TestFamilyExpansionHelper coverage.

    - Family A (group_id='DOC-00200'): parent + 2 children
    - Family B (group_id='DOC-00210'): parent + 2 children
    - Orphan (group_id=NULL): standalone document
    """
    import db_manager
    conn = db_manager.get_connection(case_folder)
    rows = [
        ("DOC-00200", "DOC-00200", None,        "email_a.eml",  ".eml",  "Processed", 1, "", "Internal"),
        ("DOC-00201", "DOC-00200", "DOC-00200", "att_a1.pdf",   ".pdf",  "Processed", 2, "", "Internal"),
        ("DOC-00202", "DOC-00200", "DOC-00200", "att_a2.pdf",   ".pdf",  "Processed", 1, "", "Internal"),
        ("DOC-00210", "DOC-00210", None,        "email_b.eml",  ".eml",  "Processed", 1, "", "Internal"),
        ("DOC-00211", "DOC-00210", "DOC-00210", "att_b1.pdf",   ".pdf",  "Processed", 2, "", "Internal"),
        ("DOC-00212", "DOC-00210", "DOC-00210", "att_b2.pdf",   ".pdf",  "Processed", 1, "", "Internal"),
        ("DOC-00299", None,        None,        "loose.pdf",    ".pdf",  "Processed", 1, "", "Internal"),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO documents
           (control_number, group_id, parent_id, file_name, file_extension,
            processing_status, page_count, tags, source_party)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return case_folder


class TestFamilyExpansionHelper:
    """Pinned-value coverage for _expand_to_families (beta-2.15 Commit 3).

    The helper is called from two sites: Bulk Bates Search and the main
    dual-search path in pages/4_Review.py. Both share this helper; tests
    verify the helper invariants directly. End-to-end behavior is covered
    by manual verification (preflight §5.2 Track 1+2).
    """

    def test_empty_input_returns_empty(self, family_expand_case):
        import db_manager
        conn = db_manager.get_connection(family_expand_case)
        try:
            result = _expand_to_families_under_test(set(), conn)
        finally:
            conn.close()
        assert result == set()

    def test_no_group_id_passes_through(self, family_expand_case):
        import db_manager
        conn = db_manager.get_connection(family_expand_case)
        try:
            result = _expand_to_families_under_test({"DOC-00299"}, conn)
        finally:
            conn.close()
        assert result == {"DOC-00299"}, "NULL-group_id orphan must not expand"

    def test_parent_expands_to_children(self, family_expand_case):
        import db_manager
        conn = db_manager.get_connection(family_expand_case)
        try:
            result = _expand_to_families_under_test({"DOC-00200"}, conn)
        finally:
            conn.close()
        assert result == {"DOC-00200", "DOC-00201", "DOC-00202"}

    def test_child_expands_to_parent_and_siblings(self, family_expand_case):
        import db_manager
        conn = db_manager.get_connection(family_expand_case)
        try:
            result = _expand_to_families_under_test({"DOC-00201"}, conn)
        finally:
            conn.close()
        assert result == {"DOC-00200", "DOC-00201", "DOC-00202"}

    def test_mixed_groups_expand_independently(self, family_expand_case):
        import db_manager
        conn = db_manager.get_connection(family_expand_case)
        try:
            result = _expand_to_families_under_test({"DOC-00200", "DOC-00210"}, conn)
        finally:
            conn.close()
        assert result == {
            "DOC-00200", "DOC-00201", "DOC-00202",
            "DOC-00210", "DOC-00211", "DOC-00212",
        }

    def test_null_group_orphans_do_not_cluster(self, family_expand_case):
        # Two NULL-group_id docs must not falsely union via shared NULL match.
        import db_manager
        conn = db_manager.get_connection(family_expand_case)
        try:
            conn.execute(
                """INSERT OR IGNORE INTO documents
                   (control_number, group_id, file_name, file_extension,
                    processing_status, page_count, tags, source_party)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("DOC-00298", None, "other.pdf", ".pdf", "Processed", 1, "", "Internal"),
            )
            conn.commit()
            result = _expand_to_families_under_test({"DOC-00298", "DOC-00299"}, conn)
        finally:
            conn.close()
        assert result == {"DOC-00298", "DOC-00299"}, \
            "NULL group_ids must not cluster via SQL NULL semantics"


class TestProducedOnlyUXFilter:
    """Pinned-value coverage for the produced_only UX-filter gate logic
    (beta-2.15 Commit 3).

    The gate is a one-line composition:
      _session_produced_only_ux = bool(session_state.get(...)) and _vis_mode != 'produced_only'

    Tests verify all four user×toggle quadrants yield the correct boolean,
    plus the composition (security OR ux) at the SQL injection sites.
    SQL composition is verified inline against pages/4_Review.py — see the
    4 extended sites at L438, L450, L2496, L3012 in the v2.15 source.
    L2717 (banner) was intentionally NOT extended per the maintainer's Option 1
    decision: the banner is admin-imposed-restriction semantics, not a
    user-chose-this filter indicator.
    """

    def _gate(self, toggle_value, vis_mode):
        # Mirrors pages/4_Review.py: _session_produced_only_ux at the _vis_mode read site.
        return bool(toggle_value) and vis_mode != 'produced_only'

    def _composed(self, toggle_value, vis_mode):
        # Mirrors the SQL injection condition: `_vis_mode == 'produced_only' or _session_produced_only_ux`
        return (vis_mode == 'produced_only') or self._gate(toggle_value, vis_mode)

    def test_gate_blocks_ux_filter_for_restricted_user(self):
        # _vis_mode == 'produced_only' (security-restricted) → gate False regardless of toggle
        assert self._gate(True, 'produced_only') is False
        assert self._gate(False, 'produced_only') is False
        assert self._gate(None, 'produced_only') is False

    def test_gate_allows_ux_filter_for_full_universe_user(self):
        # _vis_mode == 'full' or 'hidden_tags' → gate honors toggle
        assert self._gate(True, 'full') is True
        assert self._gate(False, 'full') is False
        assert self._gate(True, 'hidden_tags') is True
        assert self._gate(False, 'hidden_tags') is False

    def test_security_mode_still_filters_when_ux_toggle_off(self):
        # Security restriction must still drive the SQL filter when UX toggle is off.
        assert self._composed(False, 'produced_only') is True

    def test_ux_toggle_filters_when_security_mode_full(self):
        # Full-universe admin who opts in → composed gate True.
        assert self._composed(True, 'full') is True
        # Full-universe admin who opts out → composed gate False.
        assert self._composed(False, 'full') is False

    def test_ux_filter_composes_with_family_expansion(self, family_expand_case):
        # End-to-end: family-expansion enlarges the matched set; produced_only filter
        # then narrows to begdoc-non-empty members.
        import db_manager
        import pandas as pd

        conn = db_manager.get_connection(family_expand_case)
        try:
            # Set begdoc on Family A's 3 docs and Family B's parent only (B's children unproduced).
            conn.executemany(
                "UPDATE documents SET begdoc = ? WHERE control_number = ?",
                [
                    ("ABC-000001", "DOC-00200"),
                    ("ABC-000002", "DOC-00201"),
                    ("ABC-000004", "DOC-00202"),
                    ("ABC-000005", "DOC-00210"),
                ],
            )
            conn.commit()

            # Step 1: matched_cns simulating a search hit on each family parent.
            matched = {"DOC-00200", "DOC-00210"}

            # Step 2: family-expansion via the helper.
            expanded = _expand_to_families_under_test(matched, conn)
            assert expanded == {
                "DOC-00200", "DOC-00201", "DOC-00202",
                "DOC-00210", "DOC-00211", "DOC-00212",
            }, "Family expansion must include all 6 family members"

            # Step 3: produced_only filter applied to the expanded set
            # (same ` AND begdoc IS NOT NULL AND begdoc != ''` fragment used at L2496).
            placeholders = ",".join("?" * len(expanded))
            produced = pd.read_sql_query(
                f"SELECT control_number FROM documents "
                f"WHERE control_number IN ({placeholders}) "
                f"  AND begdoc IS NOT NULL AND begdoc != ''",
                conn,
                params=list(expanded),
            )
            produced_set = set(produced['control_number'])
            assert produced_set == {"DOC-00200", "DOC-00201", "DOC-00202", "DOC-00210"}, \
                "produced_only filter must narrow expanded set to begdoc-set members"
        finally:
            conn.close()
