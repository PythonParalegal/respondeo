"""
Render + reconciliation tests for the §4.2 Near-Duplicate Cluster Review &
Attestation section of the defensibility report (beta-2.16 C9 / S-1c).

Two layers:
  - Render tests drive `defensibility_report._render_html` with a hand-built
    `data` dict (mirroring the `_collect_*` fallback shapes, the minimal-valid
    inputs the renderer must tolerate) and assert the §4.2 HTML.
  - The reconciliation test is DB-backed (reuses the tempfile-case helpers from
    test_neardupe_clusters) and pins the B-1/B-2 document-level invariant under a
    Flag #30 overlap fixture: the summary counts a shared doc ONCE (= §4.1), the
    per-cluster table legitimately sums to MORE, and the four document-level
    buckets partition every distinct non-principal doc exactly once.

The non-overlap, all-six-cells companion (incl. the B-2 undecided+family cell)
lives in tests/test_neardupe_clusters.py::test_defensibility_dedup_neardupe_fields
— not duplicated here.
"""
import os
import shutil
import tempfile

import pytest

import db_manager
import defensibility_report as dr

# Self-contained tempfile-case helpers (mirrors test_neardupe_clusters' fixture;
# kept local to avoid cross-test-module import-path fragility under pytest).
CASE = None


@pytest.fixture(autouse=True)
def _cleanup_case():
    yield
    global CASE
    if CASE and os.path.isdir(CASE):
        shutil.rmtree(CASE, ignore_errors=True)
    CASE = None


def _fresh_case():
    global CASE
    if CASE and os.path.isdir(CASE):
        shutil.rmtree(CASE, ignore_errors=True)
    CASE = tempfile.mkdtemp(prefix="dr_ndc_test_")
    db_manager.init_db(CASE)
    return CASE


def _seed_doc(cn, tags='', parent_id=None, processing_status='Processed'):
    conn = db_manager.get_connection(CASE)
    conn.execute(
        "INSERT INTO documents (control_number, file_name, tags, parent_id, processing_status) "
        "VALUES (?,?,?,?,?)",
        (cn, cn + '.pdf', tags, parent_id, processing_status))
    conn.commit()
    conn.close()


def _base_data(dedup, clusters):
    """Minimal valid `data` dict for `_render_html` — every section uses its
    `_collect_*` fallback shape (the degraded-but-valid input the renderer
    tolerates), with the §4.2-relevant `dedup` + `near_dupe_clusters` injected."""
    return {
        'overview': {
            'case_name': 'Test Matter', 'case_status': 'Open',
            'generated_by': 'tester', 'generated_at': 'June 01, 2026 at 10:30 AM',
            'total_documents': 0, 'total_custodians': 0,
            'date_range_earliest': 'N/A', 'date_range_latest': 'N/A',
            'first_ingestion': 'N/A', 'last_processing': 'N/A',
            # matter_profile key omitted on purpose — mirrors the _collect_case_overview
            # except-branch fallback; the renderer defaults it to {} via .get(k, {}).
        },
        'ingestion': {'custodians': [], 'file_types': [], 'record_types': [],
                      'source_collections': [], 'total_size_kb': 0},
        'processing': {'status_breakdown': [], 'extraction_methods': [], 'error_docs': [],
                       'error_count': 0, 'encrypted_count': 0, 'ocr_count': 0},
        'dedup': dedup,
        'review': {'total_reviewable': 0, 'tagged_count': 0, 'review_completion_pct': 0,
                   'tag_distribution': [], 'reviewer_activity': [],
                   'responsive_count': 0, 'not_responsive_count': 0},
        'production': {'productions': [], 'bates_info': None, 'clawbacks': [],
                       'clawback_count': 0, 'prod_events': [], 'total_produced': 0,
                       'total_produced_jt': 0, 'prod_detail': [], 'production_runs': []},
        'privilege': {'withheld': 0, 'redacted': 0, 'no_disposition': 0,
                      'total_privileged': 0, 'redaction_marks_count': 0, 'redactions_applied': 0},
        'audit': {'total_events': 0, 'earliest_event': 'N/A', 'latest_event': 'N/A',
                  'by_action': [], 'by_user': [], 'by_module': []},
        'holds': {'holds': [], 'active_count': 0, 'released_count': 0,
                  'unacknowledged_count': 0, 'total_on_hold': 0},
        'collection_scope': [],
        'near_dupe_clusters': clusters,
    }


# ─── Render tests (Task 5) ──────────────────────────────────────────────────

def test_s1c_section_renders_with_clusters():
    dedup = {'total_ingested': 100, 'exact_dupes': 0, 'content_dupes': 0, 'processed': 100,
             'nd_suppressed': 6, 'nd_principals': 2, 'thread_suppressed': 0, 'thread_inclusive': 0,
             'net_reviewable': 94, 'reduction_pct': 6.0, 'exact_dupe_pct': 0.0,
             'content_dupe_pct': 0.0, 'nd_pct': 6.0, 'thread_pct': 0.0,
             'nd_family_retained': 1, 'nd_distinct': 1, 'nd_undecided': 2, 'n_clusters': 2}
    clusters = [
        {'cluster_id': 1, 'principal_cn': 'DOC-0000100', 'principal_name': 'a.pdf',
         'member_count': 9, 'sim_min': 0.90, 'sim_max': 0.97, 'review_status': 'approved',
         'reviewed_by': 'reviewer', 'reviewed_at': '2026-05-28T10:00:00',
         'confirmed_count': 7, 'family_retained_count': 1, 'distinct_count': 1, 'pending_count': 0},
        {'cluster_id': 2, 'principal_cn': 'DOC-0000200', 'principal_name': 'b.pdf',
         'member_count': 5, 'sim_min': 0.91, 'sim_max': 0.94, 'review_status': 'pending',
         'reviewed_by': None, 'reviewed_at': None,
         'confirmed_count': 2, 'family_retained_count': 0, 'distinct_count': 1, 'pending_count': 2},
    ]
    html = dr._render_html(_base_data(dedup, clusters))
    assert "Near-Duplicate Cluster Review" in html
    assert "Family-Ret" in html and "Distinct" in html and "Pending" in html
    assert "DOC-0000100" in html
    # Per-row self-audit for cluster 1: supp(6) + famret(1) + distinct(1) + pending(1) + 1 = 9
    assert "<td>6</td>" in html  # confirmed_count(7) - family_retained_count(1)
    # Attestation rendered for the approved cluster
    assert "reviewer" in html


def test_s1c_section_no_clusters_placeholder():
    dedup = {k: 0 for k in ('total_ingested', 'exact_dupes', 'content_dupes', 'processed',
             'nd_suppressed', 'nd_principals', 'thread_suppressed', 'thread_inclusive', 'net_reviewable',
             'reduction_pct', 'exact_dupe_pct', 'content_dupe_pct', 'nd_pct', 'thread_pct',
             'nd_family_retained', 'nd_distinct', 'nd_undecided', 'n_clusters')}
    html = dr._render_html(_base_data(dedup, []))
    assert "No near-duplicate clusters were identified" in html


def test_s1c_section_truncation_note_over_200():
    dedup = {'total_ingested': 5000, 'exact_dupes': 0, 'content_dupes': 0, 'processed': 5000,
             'nd_suppressed': 0, 'nd_principals': 0, 'thread_suppressed': 0, 'thread_inclusive': 0,
             'net_reviewable': 5000, 'reduction_pct': 0.0, 'exact_dupe_pct': 0.0,
             'content_dupe_pct': 0.0, 'nd_pct': 0.0, 'thread_pct': 0.0,
             'nd_family_retained': 0, 'nd_distinct': 0, 'nd_undecided': 0, 'n_clusters': 250}
    clusters = [{'cluster_id': i, 'principal_cn': f'DOC-{i:07d}', 'principal_name': 'x.pdf',
                 'member_count': 2, 'sim_min': 0.9, 'sim_max': 0.9, 'review_status': 'pending',
                 'reviewed_by': None, 'reviewed_at': None, 'confirmed_count': 0,
                 'family_retained_count': 0, 'distinct_count': 0, 'pending_count': 1}
                for i in range(200)]  # helper caps at 200
    html = dr._render_html(_base_data(dedup, clusters))
    assert "200 largest clusters" in html and "250" in html


# ─── Reconciliation test (Task 6 — the cross-section guard) ─────────────────

def test_s1c_reconciliation_under_flag30_overlap():
    """B-1/B-2 hybrid: document-level reconciliation. With docs in TWO clusters
    (Flag #30), the §4.2 SUMMARY (tag-based nd_suppressed, distinct docs) counts a
    shared doc ONCE and equals §4.1; the per-cluster table legitimately sums to
    MORE. This fixture MUST seed an overlap — a single-cluster fixture would pass
    and mislead (the v1 blind spot)."""
    case = _fresh_case()
    for cn in ("C1", "C2", "C3", "C5"):
        _seed_doc(cn)
    # Two clusters that SHARE non-principal members C2 (-> same) and C3 (-> distinct):
    db_manager.persist_near_dupe_clusters(case, [
        {"principal_cn": "C1", "sim_min": 0.90, "sim_max": 0.95,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.95, "is_principal": 0},
                     {"cn": "C3", "similarity": 0.93, "is_principal": 0}]},
        {"principal_cn": "C5", "sim_min": 0.91, "sim_max": 0.93,
         "members": [{"cn": "C5", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.92, "is_principal": 0},
                     {"cn": "C3", "similarity": 0.90, "is_principal": 0}]},
    ])
    # Each decision fans out to BOTH of the member's rows (WHERE member_cn=?):
    cid1 = db_manager.get_near_dupe_clusters(case)[0]["cluster_id"]
    db_manager.record_member_decision(case, cid1, "C2", "same", "reviewer")
    db_manager.record_member_decision(case, cid1, "C3", "distinct", "reviewer")

    d = db_manager.get_defensibility_dedup(case)
    detail = db_manager.get_near_dupe_cluster_detail(case)

    # (a) Summary/§4.1 suppressed counts the overlapping doc ONCE (distinct, tag-based).
    assert d["nd_suppressed"] == 1
    # (b) H-3: distinct bucket also dedups under overlap — C3 counted once, not twice.
    assert d["nd_distinct"] == 1
    # (c) Per-cluster table sum DOUBLE-counts C2 (one 'same' row per cluster) -> 2.
    per_cluster_supp = sum(c["confirmed_count"] - c["family_retained_count"] for c in detail)
    assert per_cluster_supp == 2
    # (d) Documented relationship: per-cluster sum strictly EXCEEDS the distinct
    #     figure under overlap. This is the corrected invariant (NOT equality).
    assert per_cluster_supp > d["nd_suppressed"]
    # (e) Partition identity (B-2/H-2): the four document-level buckets cover every
    #     distinct non-principal doc exactly once (here C2 + C3 = 2). Real regression
    #     guard — breaks if any decision×family cell is dropped (B-2) or if tag-based
    #     nd_suppressed diverges from the classification (B-1).
    assert (d["nd_suppressed"] + d["nd_family_retained"]
            + d["nd_distinct"] + d["nd_undecided"]) == 2
