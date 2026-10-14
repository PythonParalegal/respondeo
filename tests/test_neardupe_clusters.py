"""
Regression tests for the near-dupe cluster persistence + provisional
(deferred-tag) suppression data layer (beta-2.16 C8a / S-1b).

Pins the contract of the six db_manager helpers introduced for the S-1b
cluster-review workflow:

    persist_near_dupe_clusters / get_near_dupe_clusters / get_cluster_members
    record_member_decision / approve_cluster / clear_near_dupe_clusters

Load-bearing invariants:
  - FAIL-OPEN: persistence applies NO NearDupe-Suppressed tag. Suppression is
    deferred to reviewer confirmation (record_member_decision with "same").
  - ATOMIC: record_member_decision writes the decision row AND documents.tags
    in one transaction.
  - FAMILY INTEGRITY: a member marked family_preserved=1 (parent_id set in the
    Execute routing) is NEVER tagged NearDupe-Suppressed even on a "same"
    decision — the guard records the decision but skips the tag, so the family
    is not orphaned (family-integrity-over-dedup lesson). The *guard* is pinned
    here; the *wiring* (Execute populating family_preserved from
    preserved_family_ids) is pinned by the Phase B live-Execute manual canary.
  - EXACT-DUPE UNTOUCHED: the near-dupe path never writes to exact-dupe
    (processing_status-based) rows that are not cluster members.

Fixture: a tempfile throwaway case dir (init_db creates case.db); no live
matter, no OpenSearch. Each test re-inits a clean case via _fresh_case().
"""
import ast
import os
import pathlib
import shutil
import tempfile

import pytest

import db_manager

CASE = None


def _load_build_cluster_payload():
    """AST-extract the pure `_build_cluster_payload` helper from 3_Analytics.py
    without importing the (non-import-safe) Streamlit page. Mirrors the pattern in
    tests/test_neardupe_shingling.py. The helper has no module-level dependencies,
    so it execs cleanly in an empty namespace."""
    page = pathlib.Path(__file__).parent.parent / "pages" / "3_Analytics.py"
    src = page.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_build_cluster_payload":
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {}
            exec(compile(mod, str(page), "exec"), ns)
            return ns["_build_cluster_payload"]
    raise RuntimeError("_build_cluster_payload not found in pages/3_Analytics.py")


_build_cluster_payload = _load_build_cluster_payload()


@pytest.fixture(autouse=True)
def _cleanup_case():
    yield
    global CASE
    if CASE and os.path.isdir(CASE):
        shutil.rmtree(CASE, ignore_errors=True)
    CASE = None


def _fresh_case():
    """Create a clean throwaway case DB in a temp dir and return its path."""
    global CASE
    if CASE and os.path.isdir(CASE):
        shutil.rmtree(CASE, ignore_errors=True)
    CASE = tempfile.mkdtemp(prefix="ndc_test_")
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


def _make_one_cluster():
    """A 2-member cluster (principal C1 + standalone near-dupe C2)."""
    _fresh_case()
    _seed_doc("C1")
    _seed_doc("C2")
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.94, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0}]}])
    return db_manager.get_near_dupe_clusters(CASE)[0]["cluster_id"]


def _make_one_cluster_with_family_member():
    """A 2-member cluster where C2 is a family-attached member (parent_id set,
    family_preserved=1) — must be guarded from suppression."""
    _fresh_case()
    _seed_doc("C1")
    _seed_doc("C2", parent_id="C1")  # C2 is an attachment of C1 — family member
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.94, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0,
                      "family_preserved": 1}]}])
    return db_manager.get_near_dupe_clusters(CASE)[0]["cluster_id"]


# ─── clear ───────────────────────────────────────────────────────────────────

def test_clear_returns_counts_and_wipes():
    _fresh_case()
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.9, "sim_max": 0.95,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0}]}
    ])
    n_clusters, n_decisions = db_manager.clear_near_dupe_clusters(CASE)
    assert n_clusters == 1
    assert n_decisions == 0  # no decisions recorded before the clear
    conn = db_manager.get_connection(CASE)
    assert conn.execute("SELECT COUNT(*) FROM near_dupe_clusters").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM near_dupe_cluster_members").fetchone()[0] == 0
    conn.close()


# ─── persist + getters ─────────────────────────────────────────────────────--

def test_persist_writes_rows_and_no_tags():
    _fresh_case()
    _seed_doc("C1"); _seed_doc("C2"); _seed_doc("C3")
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.92, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0},
                     {"cn": "C3", "similarity": 0.92, "is_principal": 0}]}
    ])
    clusters = db_manager.get_near_dupe_clusters(CASE)
    assert len(clusters) == 1
    assert clusters[0]["member_count"] == 3
    assert clusters[0]["review_status"] == "pending"
    members = db_manager.get_cluster_members(CASE, clusters[0]["cluster_id"])
    assert len(members) == 3
    # FAIL-OPEN INVARIANT: persistence applies NO NearDupe-Suppressed tag.
    conn = db_manager.get_connection(CASE)
    sup = conn.execute("SELECT COUNT(*) FROM documents WHERE tags LIKE '%NearDupe-Suppressed%'").fetchone()[0]
    conn.close()
    assert sup == 0


def test_persist_replaces_prior_run():
    _fresh_case(); _seed_doc("C1"); _seed_doc("C2")
    payload = [{"principal_cn": "C1", "sim_min": 0.9, "sim_max": 0.9,
                "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                            {"cn": "C2", "similarity": 0.9, "is_principal": 0}]}]
    db_manager.persist_near_dupe_clusters(CASE, payload)
    db_manager.persist_near_dupe_clusters(CASE, payload)  # second run
    assert len(db_manager.get_near_dupe_clusters(CASE)) == 1  # not 2


# ─── record_member_decision + approve_cluster ──────────────────────────────--

def test_same_applies_suppressed_tag_and_records():
    cid = _make_one_cluster()
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    conn = db_manager.get_connection(CASE)
    tags = conn.execute("SELECT tags FROM documents WHERE control_number='C2'").fetchone()["tags"]
    dec = conn.execute("SELECT decision, decided_by FROM near_dupe_cluster_members WHERE member_cn='C2'").fetchone()
    conn.close()
    assert "NearDupe-Suppressed" in (tags or "")
    assert dec["decision"] == "same" and dec["decided_by"] == "alice"


def test_distinct_records_and_leaves_no_tag():
    cid = _make_one_cluster()
    db_manager.record_member_decision(CASE, cid, "C2", "distinct", "alice")
    conn = db_manager.get_connection(CASE)
    tags = conn.execute("SELECT tags FROM documents WHERE control_number='C2'").fetchone()["tags"]
    conn.close()
    assert "NearDupe-Suppressed" not in (tags or "")


def test_distinct_after_same_removes_tag():
    cid = _make_one_cluster()
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    db_manager.record_member_decision(CASE, cid, "C2", "distinct", "alice")
    conn = db_manager.get_connection(CASE)
    tags = conn.execute("SELECT tags FROM documents WHERE control_number='C2'").fetchone()["tags"]
    conn.close()
    assert "NearDupe-Suppressed" not in (tags or "")


def test_approve_records_attestation():
    cid = _make_one_cluster()
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    db_manager.approve_cluster(CASE, cid, "alice", "reviewed all members")
    c = db_manager.get_near_dupe_clusters(CASE)[0]
    assert c["review_status"] == "approved" and c["reviewed_by"] == "alice"


# ─── family-integrity guard (V3) + exact-dupe invariant ────────────────────--

def test_family_preserved_member_not_suppressed():
    cid = _make_one_cluster_with_family_member()  # C2 has parent_id, family_preserved=1
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    conn = db_manager.get_connection(CASE)
    tags = conn.execute("SELECT tags FROM documents WHERE control_number='C2'").fetchone()["tags"]
    dec = conn.execute("SELECT decision FROM near_dupe_cluster_members WHERE member_cn='C2'").fetchone()["decision"]
    conn.close()
    assert "NearDupe-Suppressed" not in (tags or "")   # family guard held
    assert dec == "same"                                # decision still recorded


def test_exact_dupes_untouched_by_neardupe_path():
    """An exact-dupe row (processing_status-based, not a near-dupe cluster
    member) is never written by the near-dupe persistence/decision path."""
    _fresh_case()
    _seed_doc("C1"); _seed_doc("C2")
    _seed_doc("DUP1", processing_status="Duplicate (MD5)")  # exact dupe, not in any cluster
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.94, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0}]}])
    cid = db_manager.get_near_dupe_clusters(CASE)[0]["cluster_id"]
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    conn = db_manager.get_connection(CASE)
    row = conn.execute(
        "SELECT tags, processing_status FROM documents WHERE control_number='DUP1'").fetchone()
    conn.close()
    assert (row["tags"] or "") == ""                       # no NearDupe tag bled onto the exact dupe
    assert row["processing_status"] == "Duplicate (MD5)"   # status untouched


# ─── _build_cluster_payload (Execute-side wiring + v3 overlap regression) ─────--

def test_payload_principal_and_family_split():
    entry = _build_cluster_payload([
        {"control_number": "C1", "parent_id": None},   # principal (iloc[0])
        {"control_number": "C2", "parent_id": "C1"},    # family child of C1
        {"control_number": "C3", "parent_id": None},    # standalone near-dupe
    ], {})
    assert entry["principal_cn"] == "C1"
    by = {m["cn"]: m for m in entry["members"]}
    assert by["C1"]["is_principal"] == 1 and by["C1"]["family_preserved"] == 0
    assert by["C2"]["is_principal"] == 0 and by["C2"]["family_preserved"] == 1
    assert by["C3"]["is_principal"] == 0 and by["C3"]["family_preserved"] == 0


def test_overlap_member_with_parent_always_family_preserved():
    """Regression pin for the v2 dual-selection leak (DOC-000250): a doc that is
    the metrics-principal of one cluster AND a non-principal member (real parent)
    of an overlapping cluster must be family_preserved=1 where it is a member — it
    can never persist as family_preserved=0 under the unified iloc[0] selection."""
    a = _build_cluster_payload([
        {"control_number": "DOC-217", "parent_id": "DOC-031"},  # principal of A
        {"control_number": "DOC-X", "parent_id": None},
    ], {})
    b = _build_cluster_payload([
        {"control_number": "DOC-319", "parent_id": None},        # principal of B
        {"control_number": "DOC-217", "parent_id": "DOC-031"},   # member of B, real parent
        {"control_number": "DOC-193", "parent_id": None},
    ], {})
    a217 = next(m for m in a["members"] if m["cn"] == "DOC-217")
    b217 = next(m for m in b["members"] if m["cn"] == "DOC-217")
    assert a217["is_principal"] == 1 and a217["family_preserved"] == 0   # principal of A
    assert b217["is_principal"] == 0                                      # member of B
    assert b217["family_preserved"] == 1                                  # the leak fix: never 0


def test_payload_handles_nan_parent():
    """parent_id arriving as NaN (pandas null) must be treated as no-parent."""
    entry = _build_cluster_payload([
        {"control_number": "C1", "parent_id": None},
        {"control_number": "C2", "parent_id": float("nan")},
    ], {})
    by = {m["cn"]: m for m in entry["members"]}
    assert by["C2"]["family_preserved"] == 0  # NaN parent is not a real family link


# ─── C8b: cross-cluster decision fan-out (spec §11.7) ────────────────────────--

import json


def _make_overlapping_clusters():
    """Two clusters sharing a non-principal member C2:
       cluster X = principal C1 + member C2
       cluster Y = principal C3 + member C2
    Returns (cid_x, cid_y). C2 appears as a non-principal member of BOTH."""
    _fresh_case()
    _seed_doc("C1"); _seed_doc("C2"); _seed_doc("C3")
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.94, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0}]},
        {"principal_cn": "C3", "sim_min": 0.91, "sim_max": 0.91,
         "members": [{"cn": "C3", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.91, "is_principal": 0}]},
    ])
    clusters = db_manager.get_near_dupe_clusters(CASE)
    cid_x = next(c["cluster_id"] for c in clusters if c["principal_cn"] == "C1")
    cid_y = next(c["cluster_id"] for c in clusters if c["principal_cn"] == "C3")
    return cid_x, cid_y


def _member_rows(member_cn):
    conn = db_manager.get_connection(CASE)
    rows = conn.execute(
        "SELECT cluster_id, decision, decided_by, decided_in_cluster_id "
        "FROM near_dupe_cluster_members WHERE member_cn=? ORDER BY cluster_id",
        (member_cn,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def test_decision_fans_out_across_clusters():
    """One 'same' decision on C2 (made in cluster X) propagates to its row in
    cluster Y; the doc is suppressed exactly once."""
    cid_x, cid_y = _make_overlapping_clusters()
    db_manager.record_member_decision(CASE, cid_x, "C2", "same", "alice")
    rows = _member_rows("C2")
    assert len(rows) == 2
    assert all(r["decision"] == "same" for r in rows)          # fanned out to both
    conn = db_manager.get_connection(CASE)
    tags = conn.execute("SELECT tags FROM documents WHERE control_number='C2'").fetchone()["tags"] or ""
    conn.close()
    assert tags.count("NearDupe-Suppressed") == 1              # suppressed once, not twice


def test_decided_in_cluster_id_pins_source():
    """Every fanned-out row records the SOURCE cluster (where the human clicked),
    not its own cluster_id."""
    cid_x, cid_y = _make_overlapping_clusters()
    db_manager.record_member_decision(CASE, cid_x, "C2", "same", "alice")
    rows = {r["cluster_id"]: r for r in _member_rows("C2")}
    assert rows[cid_x]["decided_in_cluster_id"] == cid_x       # source row
    assert rows[cid_y]["decided_in_cluster_id"] == cid_x       # non-source pins source, not cid_y


def test_distinct_distinct_distinct_fanout():
    """Re-deciding 'distinct' after 'same' clears the tag and updates BOTH rows."""
    cid_x, cid_y = _make_overlapping_clusters()
    db_manager.record_member_decision(CASE, cid_x, "C2", "same", "alice")
    db_manager.record_member_decision(CASE, cid_y, "C2", "distinct", "bob")  # re-decide in the other cluster
    rows = _member_rows("C2")
    assert all(r["decision"] == "distinct" for r in rows)      # both rows flipped
    assert all(r["decided_in_cluster_id"] == cid_y for r in rows)  # source is now Y
    conn = db_manager.get_connection(CASE)
    tags = conn.execute("SELECT tags FROM documents WHERE control_number='C2'").fetchone()["tags"] or ""
    conn.close()
    assert "NearDupe-Suppressed" not in tags                   # tag stripped


def test_family_preserved_fanout_does_not_suppress():
    """A doc that is family_preserved in ANY cluster is never suppressed, even on
    a 'same' decision made in a cluster where it is family-attached."""
    _fresh_case()
    _seed_doc("C1"); _seed_doc("C2", parent_id="C1"); _seed_doc("C3")
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.94, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0,
                      "family_preserved": 1}]},
        {"principal_cn": "C3", "sim_min": 0.9, "sim_max": 0.9,
         "members": [{"cn": "C3", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.9, "is_principal": 0}]},  # not family here
    ])
    clusters = db_manager.get_near_dupe_clusters(CASE)
    cid_y = next(c["cluster_id"] for c in clusters if c["principal_cn"] == "C3")
    # Decide 'same' in cluster Y (where C2 is NOT marked family) — the per-doc
    # guard must still hold because C2 is family_preserved in cluster X.
    db_manager.record_member_decision(CASE, cid_y, "C2", "same", "alice")
    conn = db_manager.get_connection(CASE)
    tags = conn.execute("SELECT tags FROM documents WHERE control_number='C2'").fetchone()["tags"] or ""
    conn.close()
    assert "NearDupe-Suppressed" not in tags                   # family guard held across fan-out
    assert all(r["decision"] == "same" for r in _member_rows("C2"))  # decision still recorded both rows


# ─── C8b: reopen_cluster (spec §11.5) ────────────────────────────────────────--

def _reopen_audit_entries():
    conn = db_manager.get_connection(CASE)
    rows = conn.execute(
        "SELECT details FROM audit_log WHERE action='NEARDUPE_CLUSTER_REOPENED'").fetchall()
    conn.close()
    return [json.loads(r["details"]) for r in rows if r["details"]]


def test_reopen_snapshots_attestation_to_audit_log():
    cid = _make_one_cluster()
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    db_manager.approve_cluster(CASE, cid, "alice", "all members reviewed")
    db_manager.reopen_cluster(CASE, cid, "bob")
    entries = _reopen_audit_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e["cluster_id"] == cid
    assert e["prior_reviewed_by"] == "alice"
    assert e["prior_attestation_note"] == "all members reviewed"
    assert e["prior_reviewed_at"] is not None
    # current state reverted to pending
    c = db_manager.get_near_dupe_clusters(CASE)[0]
    assert c["review_status"] == "pending" and c["reviewed_by"] is None


def test_reopen_preserves_member_decisions():
    cid = _make_one_cluster()
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    db_manager.approve_cluster(CASE, cid, "alice")
    db_manager.reopen_cluster(CASE, cid, "alice")
    conn = db_manager.get_connection(CASE)
    dec = conn.execute(
        "SELECT decision FROM near_dupe_cluster_members WHERE member_cn='C2'").fetchone()["decision"]
    conn.close()
    assert dec == "same"  # member decision survives the re-open


def test_reopen_re_enables_re_approval():
    cid = _make_one_cluster()
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    db_manager.approve_cluster(CASE, cid, "alice", "first pass")
    db_manager.reopen_cluster(CASE, cid, "alice")
    db_manager.approve_cluster(CASE, cid, "bob", "second pass after re-open")
    c = db_manager.get_near_dupe_clusters(CASE)[0]
    assert c["review_status"] == "approved"
    assert c["reviewed_by"] == "bob"  # current attestation is the second one
    # the first attestation lives immutably in the audit log
    assert _reopen_audit_entries()[0]["prior_reviewed_by"] == "alice"


# ─── C8b: get_near_dupe_review_progress (spec §6 / §11.10) ───────────────────--

def test_review_progress_counts_correctly():
    cid = _make_one_cluster()  # principal C1 + member C2, undecided
    p = db_manager.get_near_dupe_review_progress(CASE)
    assert p == {"confirmed": 0, "pending": 1, "n_decisions": 0, "n_clusters": 1}
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    p = db_manager.get_near_dupe_review_progress(CASE)
    assert p["confirmed"] == 1 and p["pending"] == 0 and p["n_decisions"] == 1


def test_review_progress_zero_when_empty():
    _fresh_case()
    assert db_manager.get_near_dupe_review_progress(CASE) == \
        {"confirmed": 0, "pending": 0, "n_decisions": 0, "n_clusters": 0}


# ─── C8b UI: auto-advance skip logic (Bug 2 / §11.4) ─────────────────────────--

def _load_nd_next_to_review():
    """AST-extract the pure _nd_next_to_review helper from 4_Review.py (the page is
    not import-safe). Mirrors the _build_cluster_payload extraction pattern."""
    page = pathlib.Path(__file__).parent.parent / "pages" / "4_Review.py"
    tree = ast.parse(page.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_nd_next_to_review":
            ns = {}
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(page), "exec"), ns)
            return ns["_nd_next_to_review"]
    raise RuntimeError("_nd_next_to_review not found in pages/4_Review.py")


_nd_next_to_review = _load_nd_next_to_review()


def test_auto_advance_skips_family_and_decided():
    others = [
        {"decision": "same"},                            # 0 decided
        {"decision": "undecided", "family_preserved": 1},  # 1 family -> skip
        {"decision": "undecided"},                       # 2 needs review -> target
        {"decision": "undecided"},
    ]
    assert _nd_next_to_review(others, 0, len(others)) == 2   # skips the family member at 1


def test_auto_advance_falls_back_to_next_when_none_need_review():
    others = [
        {"decision": "same"},
        {"decision": "distinct"},
        {"decision": "undecided", "family_preserved": 1},  # family, exempt
    ]
    # nothing after idx 0 needs a decision -> fall back to idx+1
    assert _nd_next_to_review(others, 0, len(others)) == 1


def test_auto_advance_stays_at_last():
    others = [{"decision": "same"}, {"decision": "same"}]
    assert _nd_next_to_review(others, 1, len(others)) == 1   # clamped at last


# ─── C8c: Dedup Report helper migration + nd_pending stat (S-1b γ) ───────────--

def _seed_3member_cluster():
    """Principal C1 + 3 non-principal suppressible members C2/C3/C4."""
    _fresh_case()
    for cn in ("C1", "C2", "C3", "C4"):
        _seed_doc(cn)
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.90, "sim_max": 0.96,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.96, "is_principal": 0},
                     {"cn": "C3", "similarity": 0.93, "is_principal": 0},
                     {"cn": "C4", "similarity": 0.90, "is_principal": 0}]}])
    return db_manager.get_near_dupe_clusters(CASE)[0]["cluster_id"]


def test_dr_helper_returns_new_shape():
    _seed_3member_cluster()
    rows = db_manager.get_near_dupe_cluster_detail(CASE)
    assert len(rows) == 1
    r = rows[0]
    expected = {"cluster_id", "run_date", "principal_cn", "principal_name",
                "member_count", "sim_min", "sim_max", "review_status",
                "reviewed_by", "reviewed_at", "confirmed_count", "pending_count",
                "family_retained_count", "distinct_count"}
    assert set(r.keys()) == expected
    # old shape retired
    assert "group_id" not in r and "cluster_size" not in r and "suppressed_count" not in r
    assert r["member_count"] == 4 and r["review_status"] == "pending"


def test_dr_helper_confirmed_pending_counts():
    cid = _seed_3member_cluster()
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    db_manager.record_member_decision(CASE, cid, "C3", "distinct", "alice")
    # C4 left undecided
    r = db_manager.get_near_dupe_cluster_detail(CASE)[0]
    assert r["confirmed_count"] == 1   # only 'same' counts as confirmed
    assert r["pending_count"] == 1     # only the undecided C4 counts as pending


def test_dr_helper_excludes_family_preserved_from_pending():
    _fresh_case()
    _seed_doc("C1"); _seed_doc("C2"); _seed_doc("C3", parent_id="C1")
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.9, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0},
                     {"cn": "C3", "similarity": 0.90, "is_principal": 0,
                      "family_preserved": 1}]}])
    r = db_manager.get_near_dupe_cluster_detail(CASE)[0]
    assert r["pending_count"] == 1     # only C2; the family-preserved C3 is exempt


def test_dr_helper_empty_case_returns_empty_list():
    _fresh_case()
    assert db_manager.get_near_dupe_cluster_detail(CASE) == []


def test_dr_helper_distinct_and_family_counts():
    _fresh_case()
    _seed_doc("C1"); _seed_doc("C2"); _seed_doc("C3", parent_id="C1"); _seed_doc("C4")
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.90, "sim_max": 0.96,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.96, "is_principal": 0},
                     {"cn": "C3", "similarity": 0.93, "is_principal": 0,
                      "family_preserved": 1},
                     {"cn": "C4", "similarity": 0.90, "is_principal": 0}]}])
    cid = db_manager.get_near_dupe_clusters(CASE)[0]["cluster_id"]
    db_manager.record_member_decision(CASE, cid, "C2", "same", "reviewer")      # suppressed
    db_manager.record_member_decision(CASE, cid, "C3", "same", "reviewer")      # family-guarded
    db_manager.record_member_decision(CASE, cid, "C4", "distinct", "reviewer")  # kept
    r = db_manager.get_near_dupe_cluster_detail(CASE)[0]
    assert r["confirmed_count"] == 2          # both 'same' (C2 + C3)
    assert r["family_retained_count"] == 1    # only C3 (family-attached 'same')
    assert r["distinct_count"] == 1           # C4
    assert r["pending_count"] == 0
    # Per-cluster suppressed (tagged) == confirmed - family_retained
    assert r["confirmed_count"] - r["family_retained_count"] == 1


def test_defensibility_dedup_neardupe_fields():
    _fresh_case()
    for cn in ("C1", "C2", "C3", "C4", "C5", "C6"):
        _seed_doc(cn)
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.90, "sim_max": 0.96,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.96, "is_principal": 0},
                     {"cn": "C3", "similarity": 0.93, "is_principal": 0, "family_preserved": 1},
                     {"cn": "C4", "similarity": 0.90, "is_principal": 0},
                     {"cn": "C5", "similarity": 0.91, "is_principal": 0},
                     # C6: family-attached AND left undecided — the B-2 cell
                     # (undecided & family_preserved=1), the default post-run state.
                     {"cn": "C6", "similarity": 0.90, "is_principal": 0, "family_preserved": 1}]}])
    cid = db_manager.get_near_dupe_clusters(CASE)[0]["cluster_id"]
    db_manager.record_member_decision(CASE, cid, "C2", "same", "reviewer")      # suppressed
    db_manager.record_member_decision(CASE, cid, "C3", "same", "reviewer")      # family-retained
    db_manager.record_member_decision(CASE, cid, "C4", "distinct", "reviewer")  # distinct
    # C5 (undecided, fp0) and C6 (undecided, fp1) both left undecided -> both nd_undecided
    d = db_manager.get_defensibility_dedup(CASE)
    assert d["n_clusters"] == 1
    assert d["nd_suppressed"] == 1          # only C2 (C3 is family-guarded, not tagged)
    assert d["nd_family_retained"] == 1     # C3
    assert d["nd_distinct"] == 1            # C4
    assert d["nd_undecided"] == 2           # C5 + C6 (B-2: family-undecided is counted)
    # Partition identity over the 5 non-principal members:
    assert (d["nd_suppressed"] + d["nd_family_retained"]
            + d["nd_distinct"] + d["nd_undecided"]) == 5


def test_data_reduction_stats_nd_pending_field():
    _fresh_case()
    _seed_doc("C1"); _seed_doc("C2"); _seed_doc("C3")
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.9, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0},
                     {"cn": "C3", "similarity": 0.90, "is_principal": 0}]}])
    assert db_manager.get_data_reduction_stats(CASE)["nd_pending"] == 2


def test_data_reduction_stats_nd_pending_excludes_family_preserved():
    _fresh_case()
    _seed_doc("C1"); _seed_doc("C2"); _seed_doc("C3", parent_id="C1")
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.9, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0},
                     {"cn": "C3", "similarity": 0.90, "is_principal": 0,
                      "family_preserved": 1}]}])
    assert db_manager.get_data_reduction_stats(CASE)["nd_pending"] == 1
