# Near-Dupe Cluster Review (S-1b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project-specific override:** This project runs the PM→CLI two-tab model. Execution happens in the CLI tab under the maintainer's Stage-2 greenlight, **not** via PM-dispatched subagents. Treat this plan as the strategic skeleton; per the established workflow each commit (α/β/γ) gets a per-commit preflight + CLI pre-flight check at execution time. Honor all CLAUDE.md Standing Orders (version headers, CHANGELOG, DEPENDENCY_MAP, never-raise audit, atomic multi-table writes, closed-case discipline, `# permission:` annotations).

**Goal:** Give reviewers a Review-page tab to inspect each near-dupe cluster against its principal via a side-by-side diff, confirm true duplicates or rescue materially-distinct siblings, and attest the group — turning algorithmic suppression into a human-confirmed, court-defensible decision.

**Architecture:** Provisional suppression via **deferred tagging** — `NearDupe-Suppressed` is applied only when a reviewer confirms "Same as principal," never at Execute. Cluster membership + per-member decisions + per-cluster attestation persist in two new SQLite tables. The Review tab is a master/detail surface (`st.dataframe` single-row selection → `@st.fragment`-scoped detail with a `difflib` side-by-side diff) mirroring the proven `4_Review.py:3014` + `4_Review.py:4175` patterns. Exact (MD5/content) dedup is untouched — it is `processing_status`-based and hash-dispositive.

**Tech Stack:** Python 3 / Streamlit 1.55.0, SQLite (via `db_manager`), `datasketch` MinHash/LSH (already present), `difflib` (stdlib), OpenSearch (`os_manager`) for document text, pytest.

**Source spec:** `docs/superpowers/specs/2026-05-24-neardupe-cluster-review-design.md`

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `db_manager.py` | Modify | Two new tables in `init_db` (≈ L485, after `hold_documents`); six new helper functions (cluster persistence, member decision, attestation, clear). The decision+tag write is atomic. |
| `pages/3_Analytics.py` | Modify | `run_near_dupe` stashes MinHash signatures in session state (1 line). Execute block (L706–753) persists clusters + applies `NearDupe-Principal` only (no suppressed tag). "Clear & Re-run" (L628–643) also clears cluster tables. Near-dupe status/metrics show confirmed-vs-pending. |
| `pages/4_Review.py` | Modify | New "Near-Dupe Clusters" tab (STR-style). Master/detail UI; per-member Same/Distinct + per-cluster Approve handlers calling `db_manager`. |
| `os_manager.py` | Modify | `get_document_content(case_folder, control_number)` — fetch `_source.content` by control_number for the diff pane. |
| `neardupe_diff.py` | Create | Pure function `build_side_by_side_diff_html(principal_text, member_text)` — testable, no Streamlit/OS deps. |
| `defensibility_report.py` / Dedup Report | Modify (γ) | Read cluster detail from the new tables instead of family-`group_id` grouping. |
| `pages/5_Production.py` | Modify (γ) | Non-blocking "N clusters pending review" FYI at burn time. |
| `DEPENDENCY_MAP.md` | Modify | Register two new tables, new helpers, deferred-tagging semantics. |
| `tests/test_neardupe_clusters.py` | Create | Persistence, decision, attestation, clear, deferred-tagging fail-open, exact-dupe-untouched invariant. |
| `tests/test_neardupe_diff.py` | Create | Pure diff-HTML function. |

**No `auth_manager._NAV_PAGES` change** — this is a *tab* inside an existing page, not a new page file. (Nav-registry reconciliation, Standing Order audit step 6, does not apply.)

---

## COMMIT α — Persistence + deferred-tagging Execute

### Task α1: New tables in `init_db`

**Files:**
- Modify: `db_manager.py` (inside `init_db`, after the `hold_documents` block ≈ L485)

- [ ] **Step 1: Add the two `CREATE TABLE IF NOT EXISTS` blocks**

Insert after the `hold_documents` table creation (before the custodian auto-populate at ≈L488):

```python
    # NEAR-DUPE CLUSTER REVIEW TABLES (S-1b)
    # Cluster membership + per-member reviewer decisions + per-cluster attestation.
    # Suppression is provisional: NearDupe-Suppressed is applied only when a
    # reviewer confirms a member is "same" (see record_member_decision).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS near_dupe_clusters (
            cluster_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date         TEXT,
            principal_cn     TEXT,
            member_count     INTEGER DEFAULT 0,
            sim_min          REAL,
            sim_max          REAL,
            review_status    TEXT DEFAULT 'pending',
            reviewed_by      TEXT,
            reviewed_at      TEXT,
            attestation_note TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS near_dupe_cluster_members (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id             INTEGER NOT NULL,
            member_cn              TEXT NOT NULL,
            is_principal           INTEGER DEFAULT 0,
            similarity             REAL,
            decision               TEXT DEFAULT 'undecided',
            decided_by             TEXT,
            decided_at             TEXT,
            similarity_at_decision REAL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ndcm_cluster ON near_dupe_cluster_members(cluster_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ndcm_member ON near_dupe_cluster_members(member_cn)')
```

- [ ] **Step 2: Verify schema creates cleanly**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -c "import db_manager; db_manager.init_db('TEST_CASE'); print('ok')"`
Expected: `ok` (creates a throwaway TEST_CASE DB; delete its folder after).

- [ ] **Step 3: Commit** (bundled — commit at end of α after Task α5)

---

### Task α2: `clear_near_dupe_clusters` helper (write the failing test first)

**Files:**
- Modify: `db_manager.py` (new function, near the other near-dupe helpers ≈ L4309)
- Test: `tests/test_neardupe_clusters.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
import os, shutil, sqlite3
import db_manager

CASE = "PYTEST_NDC"

def _fresh_case():
    # init a clean throwaway case DB
    try:
        shutil.rmtree(db_manager.get_case_db_dir(CASE))  # if such a helper exists; else remove the case folder
    except Exception:
        pass
    db_manager.init_db(CASE)

def _seed_doc(cn, tags=''):
    conn = db_manager.get_connection(CASE)
    conn.execute("INSERT INTO documents (control_number, file_name, tags, processing_status) VALUES (?,?,?,?)",
                 (cn, cn + '.pdf', tags, 'Processed'))
    conn.commit(); conn.close()

def test_clear_returns_counts_and_wipes():
    _fresh_case()
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.9, "sim_max": 0.95,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0}]}
    ])
    n_clusters, n_decisions = db_manager.clear_near_dupe_clusters(CASE)
    assert n_clusters == 1
    conn = db_manager.get_connection(CASE)
    assert conn.execute("SELECT COUNT(*) FROM near_dupe_clusters").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM near_dupe_cluster_members").fetchone()[0] == 0
    conn.close()
```

> NOTE for executor: confirm the exact throwaway-case helper (`get_case_db_dir` / case-folder path) during pre-flight; the project's existing tests (`tests/test_os_id_canonical.py`, `tests/test_neardupe_shingling.py`) show the established fixture pattern — mirror it.

- [ ] **Step 2: Run to verify it fails**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -m pytest tests/test_neardupe_clusters.py::test_clear_returns_counts_and_wipes -v`
Expected: FAIL — `AttributeError: module 'db_manager' has no attribute 'persist_near_dupe_clusters'`.

- [ ] **Step 3: Implement `clear_near_dupe_clusters`**

```python
def clear_near_dupe_clusters(case_folder):
    """Delete all near-dupe clusters + member decisions and strip the
    NearDupe-Suppressed / NearDupe-Principal tags they produced. Returns
    (n_clusters, n_decisions) measured before deletion (for the re-run warning).
    Re-run discards reviewer work by design — the caller warns first."""
    conn = get_connection(case_folder)
    try:
        n_clusters = conn.execute("SELECT COUNT(*) FROM near_dupe_clusters").fetchone()[0]
        n_decisions = conn.execute(
            "SELECT COUNT(*) FROM near_dupe_cluster_members WHERE decision != 'undecided'"
        ).fetchone()[0]
        conn.execute("DELETE FROM near_dupe_cluster_members")
        conn.execute("DELETE FROM near_dupe_clusters")
        # Strip the tags prior confirmations applied (same REPLACE pattern as the
        # Analytics re-run path). Outbound docs only — matches the tagging scope.
        conn.execute("UPDATE documents SET tags = REPLACE(tags, 'NearDupe-Suppressed', '') WHERE source_party = 'Internal' OR source_party IS NULL")
        conn.execute("UPDATE documents SET tags = REPLACE(tags, 'NearDupe-Principal', '') WHERE source_party = 'Internal' OR source_party IS NULL")
        conn.execute("UPDATE documents SET tags = REPLACE(tags, ';;', ';') WHERE tags LIKE '%;;%' AND (source_party = 'Internal' OR source_party IS NULL)")
        conn.commit()
        return (n_clusters, n_decisions)
    finally:
        conn.close()
```

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_neardupe_clusters.py::test_clear_returns_counts_and_wipes -v` → PASS.

---

### Task α3: `persist_near_dupe_clusters` + getters

**Files:**
- Modify: `db_manager.py`
- Test: `tests/test_neardupe_clusters.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify fail** — Expected: FAIL (functions undefined).

- [ ] **Step 3: Implement persistence + getters**

```python
def persist_near_dupe_clusters(case_folder, clusters):
    """Replace all near-dupe clusters with a fresh run's results. Applies NO
    suppression tag (deferred to reviewer confirmation). `clusters` is a list of
    dicts: {principal_cn, sim_min, sim_max, members:[{cn, similarity, is_principal}]}.
    Single transaction (atomic-multi-table-writes)."""
    conn = get_connection(case_folder)
    now = _dt_now_iso()
    try:
        conn.execute("DELETE FROM near_dupe_cluster_members")
        conn.execute("DELETE FROM near_dupe_clusters")
        for c in clusters:
            cur = conn.execute(
                """INSERT INTO near_dupe_clusters
                   (run_date, principal_cn, member_count, sim_min, sim_max, review_status)
                   VALUES (?,?,?,?,?, 'pending')""",
                (now, c["principal_cn"], len(c["members"]), c.get("sim_min"), c.get("sim_max")))
            cluster_id = cur.lastrowid
            conn.executemany(
                """INSERT INTO near_dupe_cluster_members
                   (cluster_id, member_cn, is_principal, similarity, decision)
                   VALUES (?,?,?,?, 'undecided')""",
                [(cluster_id, m["cn"], int(m.get("is_principal", 0)), m.get("similarity"))
                 for m in c["members"]])
        conn.commit()
    finally:
        conn.close()


def get_near_dupe_clusters(case_folder):
    """Cluster-level summary rows for the review list, principal filename joined in."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT c.cluster_id, c.principal_cn, c.member_count, c.sim_min, c.sim_max,
                   c.review_status, c.reviewed_by, c.reviewed_at,
                   d.file_name AS principal_name,
                   (SELECT COUNT(*) FROM near_dupe_cluster_members m
                     WHERE m.cluster_id = c.cluster_id AND m.decision != 'undecided') AS decided_count
            FROM near_dupe_clusters c
            LEFT JOIN documents d ON d.control_number = c.principal_cn
            ORDER BY c.member_count DESC, c.cluster_id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_cluster_members(case_folder, cluster_id):
    """Member rows for one cluster, joined to documents for display + decision state."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT m.member_cn, m.is_principal, m.similarity, m.decision,
                   m.decided_by, m.decided_at, d.file_name, d.custodian, d.date_sent
            FROM near_dupe_cluster_members m
            LEFT JOIN documents d ON d.control_number = m.member_cn
            WHERE m.cluster_id = ?
            ORDER BY m.is_principal DESC, m.similarity DESC
        """, (cluster_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
```

> Use the project's existing timestamp helper for `_dt_now_iso()` — confirm its real name during pre-flight (grep `datetime.now().isoformat` usage in db_manager); inline `datetime.now().isoformat()` if no helper exists.

- [ ] **Step 4: Run to verify pass** — both tests PASS.

---

### Task α4: `record_member_decision` + `approve_cluster` (atomic decision+tag)

**Files:**
- Modify: `db_manager.py`
- Test: `tests/test_neardupe_clusters.py`

- [ ] **Step 1: Write the failing tests**

```python
def _make_one_cluster():
    _fresh_case(); _seed_doc("C1"); _seed_doc("C2")
    db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn": "C1", "sim_min": 0.94, "sim_max": 0.94,
         "members": [{"cn": "C1", "similarity": 1.0, "is_principal": 1},
                     {"cn": "C2", "similarity": 0.94, "is_principal": 0}]}])
    return db_manager.get_near_dupe_clusters(CASE)[0]["cluster_id"]

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
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement**

```python
def record_member_decision(case_folder, cluster_id, member_cn, decision, username):
    """Record a reviewer's Same/Distinct call on one member and synchronize its
    NearDupe-Suppressed tag — atomically (decision row + documents.tags in one
    transaction). decision in {'same','distinct'}. 'same' applies the tag;
    'distinct' ensures it is absent. log_audit is best-effort (never-raise)."""
    assert decision in ("same", "distinct")
    conn = get_connection(case_folder)
    now = _dt_now_iso()
    try:
        row = conn.execute(
            "SELECT similarity FROM near_dupe_cluster_members WHERE cluster_id=? AND member_cn=?",
            (cluster_id, member_cn)).fetchone()
        sim = row["similarity"] if row else None
        conn.execute("""UPDATE near_dupe_cluster_members
                        SET decision=?, decided_by=?, decided_at=?, similarity_at_decision=?
                        WHERE cluster_id=? AND member_cn=?""",
                     (decision, username, now, sim, cluster_id, member_cn))
        old = conn.execute("SELECT tags FROM documents WHERE control_number=?", (member_cn,)).fetchone()
        old_tags = (old["tags"] if old else "") or ""
        if decision == "same":
            if "NearDupe-Suppressed" not in old_tags:
                new_tags = (old_tags + "NearDupe-Suppressed;") if old_tags else "NearDupe-Suppressed;"
                conn.execute("UPDATE documents SET tags=? WHERE control_number=?", (new_tags, member_cn))
        else:  # distinct -> strip the tag if present
            if "NearDupe-Suppressed" in old_tags:
                new_tags = old_tags.replace("NearDupe-Suppressed;", "").replace("NearDupe-Suppressed", "")
                conn.execute("UPDATE documents SET tags=? WHERE control_number=?", (new_tags, member_cn))
        conn.commit()
    finally:
        conn.close()
    try:
        log_audit(case_folder, "NEARDUPE_DECISION", username=username, module="Review",
                  control_number=member_cn,
                  details=json.dumps({"cluster_id": cluster_id, "decision": decision}))
    except Exception:
        pass


def approve_cluster(case_folder, cluster_id, username, note=None):
    """Record the per-cluster attestation. Caller enforces 'all members decided'."""
    conn = get_connection(case_folder)
    try:
        conn.execute("""UPDATE near_dupe_clusters
                        SET review_status='approved', reviewed_by=?, reviewed_at=?, attestation_note=?
                        WHERE cluster_id=?""",
                     (username, _dt_now_iso(), note, cluster_id))
        conn.commit()
    finally:
        conn.close()
    try:
        log_audit(case_folder, "NEARDUPE_CLUSTER_APPROVED", username=username, module="Review",
                  details=json.dumps({"cluster_id": cluster_id, "note": note}))
    except Exception:
        pass
```

> Confirm `log_audit`'s exact kwarg names during pre-flight (the `control_number=` / `details=` signature — Flag #24 was a `user=` vs `username=` typo here, so verify against the live signature). Match `bulk_tag_documents`'s separator convention (`tag + ';'`).

- [ ] **Step 4: Run to verify pass** — all four PASS.

---

### Task α5: Analytics Execute — persist + defer suppressed tag; re-run clears; confirmed/pending metric

**Files:**
- Modify: `pages/3_Analytics.py` — `run_near_dupe` (≈L409), Execute block (L706–753), "Clear & Re-run" (L628–643), status/metrics (L656–699)

- [ ] **Step 1: Stash signatures in `run_near_dupe`**

After `st.session_state['nd_clusters'] = clusters` (L409), add:

```python
    st.session_state['nd_minhashes'] = minhashes  # principal↔member similarity at persist time (S-1b)
```

- [ ] **Step 2: Replace the Execute tag-application block (L724–733) with persist + principal-only tag**

Replace the `if suppressed_ids: bulk_tag_documents(..., "NearDupe-Suppressed")` / `if principal_ids: bulk_tag_documents(..., "NearDupe-Principal")` pair with:

```python
            # S-1b: provisional suppression. Persist clusters + apply only the
            # informational NearDupe-Principal tag. NearDupe-Suppressed is applied
            # later, per-member, when a reviewer confirms "Same as principal" in
            # the Review → Near-Dupe Clusters tab (db_manager.record_member_decision).
            _mh = st.session_state.get('nd_minhashes', {})
            _persist = []
            for cluster in clusters:
                # principal for THIS cluster = the principal_id that is a member of it
                _p = next((p for p in principal_ids if p in cluster), None)
                if _p is None:
                    continue
                _members, _sims = [], []
                for cn in cluster:
                    sim = None
                    if _p in _mh and cn in _mh:
                        sim = float(_mh[_p].jaccard(_mh[cn]))
                    _members.append({"cn": cn, "similarity": sim, "is_principal": 1 if cn == _p else 0})
                    if cn != _p and sim is not None:
                        _sims.append(sim)
                _persist.append({"principal_cn": _p, "members": _members,
                                 "sim_min": min(_sims) if _sims else None,
                                 "sim_max": max(_sims) if _sims else None})
            db_manager.persist_near_dupe_clusters(case_folder, _persist)
            if principal_ids:
                try:
                    bulk_tag_documents(principal_ids, "NearDupe-Principal")
                except Exception as _btd_err:
                    st.error(f"❌ Near-duplicate principal tag failed and was rolled back: {_btd_err}")
```

> Remove the now-obsolete `_nd_audit` block that logged per-doc `NearDupe-Suppressed` TAGS_CHANGED at execute (L741–751) — suppressed-tagging no longer happens here; it is audited per-decision in `record_member_decision`. Keep the principal audit if desired. Update the success toast (L753) to: `f"✅ {len(clusters)} clusters staged for review. Suppression is applied as reviewers confirm duplicates."`

- [ ] **Step 3: "Clear & Re-run" also clears cluster tables (L628–643)**

Inside the `Clear & Re-run Near-Duplicate` button handler, before/with the existing tag REPLACE statements, call the helper and surface the count in the warning:

```python
                _n_clusters, _n_decisions = db_manager.clear_near_dupe_clusters(case_folder)
```

and change the expander warning text (L622) to include: *"Re-running discards all cluster review decisions. "* Display `_n_decisions` if > 0 before proceeding. (The existing tag-REPLACE statements become redundant with `clear_near_dupe_clusters` — remove them to avoid double work, since the helper now owns tag-stripping.)

- [ ] **Step 4: Confirmed/pending metric (L656–699 + status L612–620)**

Where the near-dupe results metrics render, replace the single "Actual Reduction" framing with confirmed-vs-pending sourced from the new tables:

```python
        _nd_clusters = db_manager.get_near_dupe_clusters(case_folder)
        _confirmed = sum(1 for c in _nd_clusters for m in db_manager.get_cluster_members(case_folder, c["cluster_id"]) if m["decision"] == "same")
        _pending = sum(c["member_count"] - 1 for c in _nd_clusters)  # non-principal members
        col3.metric("Confirmed suppressed", _confirmed, help="Members a reviewer confirmed as true duplicates.")
        # add a fourth metric or caption for pending review:
        st.caption(f"⏳ {max(_pending - _confirmed, 0)} members staged, awaiting reviewer confirmation in Review → Near-Dupe Clusters.")
```

> Keep this read lightweight; if cluster counts are large, prefer a single aggregate query (a `get_near_dupe_review_progress(case_folder)` helper returning `{confirmed, pending}`) — add it to `db_manager` if the per-cluster loop is too chatty. Decide during pre-flight.

- [ ] **Step 5: Manual verification**

Run the app, run near-dupe on a fixture set, click Execute. Verify: (a) no doc gains `NearDupe-Suppressed` (check grid "Show Suppressed" — empty for near-dupe); (b) principals tagged; (c) rows exist in `near_dupe_clusters`; (d) toast says "staged for review."

- [ ] **Step 6: Housekeeping + commit α**

- Bump version headers: `db_manager.py` (minor — new functions), `pages/3_Analytics.py` (patch — behavior change). Set `last_modified` to now, `last_commit: pending`, `project_ver` = `2.15.0`.
- CHANGELOG: `NEW: db_manager.py — near-dupe cluster persistence + reviewer-decision helpers (S-1b)` and `CHANGE: pages/3_Analytics.py — near-dupe Execute defers suppression tagging to reviewer confirmation (provisional suppression)`.
- `DEPENDENCY_MAP.md`: add `near_dupe_clusters` + `near_dupe_cluster_members` tables; note the deferred-tagging semantic (NearDupe-Suppressed now = human-confirmed); list the new helpers.
- Run full near-dupe test file: `pytest tests/test_neardupe_clusters.py -v` → all PASS.

```bash
git add db_manager.py pages/3_Analytics.py tests/test_neardupe_clusters.py CHANGELOG.md DEPENDENCY_MAP.md
git commit -m "beta-2.16 C8a (S-1b): near-dupe cluster persistence + provisional (deferred-tag) suppression"
```

---

## COMMIT β — Review "Near-Dupe Clusters" tab

> **§11 of the spec supersedes the strategic scaffold below for UX detail.** Per `docs/superpowers/specs/2026-05-24-neardupe-cluster-review-design.md` §11 (C8b UX detail, appended 2026-05-28), the authoritative sources for this commit are:
>
> - **§11.1** layout proportions (18/82 master/detail), `NEARDUPE_PANE_HEIGHT = 700` constant, Collapse-list-to-strip + Expand-diff-to-modal affordances.
> - **§11.2** member-nav widget (`◀ Prev / position / picker with status icons / Next ▶`).
> - **§11.3** diff pane: context-collapsed default via `difflib.HtmlDiff(context=True, numlines=2)`, "Show full text" toggle (flips `context=False`), `st.dialog` Expand modal, independent column scroll with sticky headers, `@st.cache_data` keyed by `(case_folder, cluster_id, member_cn, context_mode)`.
> - **§11.4** three per-member action states: normal (Same/Distinct), family-preserved (amber resolved panel, no buttons, auto-exempt), overlap-locked (badge + jump-to-source).
> - **§11.5** three attestation states (PENDING/READY/APPROVED) **incl. the `[↺ Re-open]` affordance** in APPROVED with two-click confirmation; calls new `db_manager.reopen_cluster` helper; snapshots prior attestation to `audit_log` as `NEARDUPE_CLUSTER_REOPENED`; member decisions preserved.
> - **§11.6** approval gate semantics: `all members where family_preserved == 0 have decision IN ('same','distinct')`; overlap-locked counts as decided.
> - **§11.7** schema delta — add `decided_in_cluster_id INTEGER` column to `near_dupe_cluster_members`; `record_member_decision` fans the decision out to every (cluster, member) row for the same `member_cn` (with `decided_in_cluster_id` = source cluster); UI reads `decided_in_cluster_id` to render the §11.4 State 3 lock when `!=` current cluster_id.
> - **§11.8** four cluster-list badge states: `PEND` / `M/N` / `N/N ✓` / `APPR`; sim range to row hover; doc count stays inline.
> - **§11.9** theme-safe color discipline: prefer `st.badge` where applicable; never dark text on dark backgrounds.
>
> Plus the re-run guard (§6 + §11.10 β-Analytics task below) is part of this commit's scope. **The C8b per-commit preflight pulls §11 into commit-level step-by-step discipline;** the tasks β1–β3 below remain as the strategic skeleton but are not the final execution contract.

### Task β1: Pure side-by-side diff function (TDD)

**Files:**
- Create: `neardupe_diff.py`
- Test: `tests/test_neardupe_diff.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
from neardupe_diff import build_side_by_side_diff_html

def test_diff_marks_changed_tokens_both_sides():
    a = "Invoice INV-1041 Amount 4200"
    b = "Invoice INV-1042 Amount 3750"
    html = build_side_by_side_diff_html(a, b)
    assert isinstance(html, str)
    assert "INV-1041" in html and "INV-1042" in html
    assert "table" in html.lower()  # difflib HtmlDiff emits a table

def test_diff_identical_has_no_change_markers():
    html = build_side_by_side_diff_html("same text here", "same text here")
    # difflib marks changes with nowrap 'diff_chg'/'diff_add'/'diff_sub' classes
    assert "diff_chg" not in html and "diff_add" not in html and "diff_sub" not in html
```

- [ ] **Step 2: Run to verify fail** — `ModuleNotFoundError: neardupe_diff`.

- [ ] **Step 3: Implement**

```python
# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        neardupe_diff.py
# version:       1.0.0
# project:       Respondeo eDiscovery Platform
# project_ver:   2.15.0
# last_modified: <YYYY-MM-DD HH:MM>
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
"""Pure helpers for the near-dupe cluster review diff pane (S-1b).

No Streamlit or OpenSearch dependencies — kept pure for unit testing. The Review
tab fetches document text (os_manager) and feeds it here for rendering.
"""
import difflib

def build_side_by_side_diff_html(
    principal_text: str,
    member_text: str,
    context: bool = True,
    numlines: int = 2,
) -> str:
    """Return an HTML side-by-side diff table (principal | member) with changed
    spans highlighted. Word-level: text is split on whitespace so single changed
    tokens (invoice #, amount) are isolated rather than whole-line.

    Args:
        principal_text: principal document text.
        member_text: member document text being compared.
        context: when True (default), collapse unchanged stretches to "..." with
            `numlines` of context around each change hunk — keeps long documents
            tractable. When False, full text renders with change highlights only
            (drives the §11.3 "Show full text" toggle).
        numlines: context lines around each change hunk when `context=True`.
    """
    a = (principal_text or "").split()
    b = (member_text or "").split()
    differ = difflib.HtmlDiff(wrapcolumn=60)
    return differ.make_table(a, b, fromdesc="Principal", todesc="Member",
                             context=context, numlines=numlines)
```

- [ ] **Step 4: Run to verify pass** — both PASS.

---

### Task β2: `os_manager.get_document_content`

**Files:**
- Modify: `os_manager.py`

- [ ] **Step 1: Implement (integration-verified, not unit-tested — needs a live index)**

```python
def get_document_content(case_folder, control_number):
    """Fetch a single document's extracted text (`_source.content`) by
    control_number. Returns '' if not found. Used by the Review near-dupe diff."""
    es = get_client()  # use the module's existing client accessor — confirm name in pre-flight
    if not es:
        return ""
    index_name = get_index_name(case_folder)
    try:
        resp = es.search(index=index_name, body={
            "size": 1,
            "query": {"term": {"control_number": control_number}},
            "_source": ["content"]
        })
        hits = resp.get("hits", {}).get("hits", [])
        return hits[0]["_source"].get("content", "") if hits else ""
    except Exception:
        return ""
```

> Confirm the client accessor + whether `control_number` needs `.keyword` (the Flag #28 work — `cn_from_hit`/`compute_os_id` — documents the id↔control_number nuance; reuse those conventions). Bump `os_manager.py` header (minor).

- [ ] **Step 2: Manual verification** — call against a live case index; confirm it returns text for a known control number.

---

### Task β3: The Review tab (component build + manual verification)

**Files:**
- Modify: `pages/4_Review.py` — add to the tab declaration; add the tab body. Build incrementally with `Edit` (file is on the Write-truncates list). Mirror the STR tab's structure, the `st.dataframe(... on_select="rerun", selection_mode=...)` at L3014, and the `@st.fragment` at L4175.

- [ ] **Step 1: Add the tab to the page's `st.tabs([...])` declaration**

Locate the Review page's top-level `st.tabs([...])` call; add `"🧬 Near-Dupe Clusters"` and a matching `with tabX:` block. (Grep `st.tabs(` in `pages/4_Review.py` to find the canonical declaration during pre-flight.)

- [ ] **Step 2: Tab body — access gate + closed-case + empty state**

```python
with tab_nd_clusters:
    st.header("Near-Dupe Cluster Review")
    st.caption("Review each near-dupe group against its principal. Confirm true duplicates "
               "(suppress) or mark distinct (return to review). Nothing is suppressed until you confirm.")
    # permission: tag
    _nd_can_write = auth_manager.has_permission('tag') and not _case_closed
    if _case_closed:
        st.warning("This matter is closed — cluster decisions are read-only.")
    elif not auth_manager.has_permission('tag'):
        st.info("Reviewing near-dupe clusters requires the 'tag' permission.")

    _clusters = db_manager.get_near_dupe_clusters(case_folder)
    if not _clusters:
        st.info("No near-dupe clusters staged. Run Near-Duplicate Detection in Analytics first.")
    else:
        # ... master/detail below
```

- [ ] **Step 3: Left pane — selectable cluster table (mirror L3014)**

```python
        import pandas as _pd
        _grid = _pd.DataFrame([{
            "Cluster": c["cluster_id"],
            "Principal": c.get("principal_name") or c["principal_cn"],
            "Docs": c["member_count"],
            "Similarity": f"{(c['sim_min'] or 0):.2f}–{(c['sim_max'] or 0):.2f}",
            "Status": "✅ approved" if c["review_status"] == "approved" else f"⏳ {c['decided_count']}/{c['member_count']-1} decided",
        } for c in _clusters])
        _left, _right = st.columns([0.42, 0.58])
        with _left:
            _evt = st.dataframe(_grid, hide_index=True, width='stretch',
                                on_select="rerun", selection_mode="single-row",
                                key="nd_cluster_select")
        _sel_rows = _evt.selection.rows if _evt and _evt.selection else []
        _sel_cluster = _clusters[_sel_rows[0]] if _sel_rows and _sel_rows[0] < len(_clusters) else None
```

> The `_sel_rows[0] < len(_clusters)` guard is the **stale-selection guard** (M-7 / list-mutates-after-action): after a re-run shrinks the list, a dangling index must not index out of range.

- [ ] **Step 4: Right pane — fragment-scoped detail with diff (read interactions only)**

```python
        with _right:
            if _sel_cluster is None:
                st.info("Select a cluster on the left to review its members.")
            else:
                _render_cluster_detail(case_folder, _sel_cluster, _nd_can_write)
```

Define `_render_cluster_detail` as an `@st.fragment` (mirror L4175). Inside: show principal; a member picker (`st.selectbox` of non-principal members, `key=f"nd_member_{cluster_id}"`); fetch principal + selected-member text via `os_manager.get_document_content`; render the diff:

```python
@st.fragment
def _render_cluster_detail(case_folder_path, cluster, can_write):
    cid = cluster["cluster_id"]
    members = db_manager.get_cluster_members(case_folder_path, cid)
    principal = next((m for m in members if m["is_principal"]), None)
    others = [m for m in members if not m["is_principal"]]
    st.markdown(f"**Principal:** {principal['file_name'] if principal else cluster['principal_cn']}")
    labels = [f"{m['file_name']} · sim {m['similarity']:.2f} · {m['decision']}" for m in others]
    idx = st.selectbox("Member to compare", range(len(others)),
                       format_func=lambda i: labels[i], key=f"nd_member_{cid}")
    member = others[idx]
    p_text = os_manager.get_document_content(case_folder_path, cluster["principal_cn"])
    m_text = os_manager.get_document_content(case_folder_path, member["member_cn"])
    import streamlit.components.v1 as _components
    _components.html(neardupe_diff.build_side_by_side_diff_html(p_text, m_text), height=420, scrolling=True)
    # --- decision buttons (WRITE — must run at app scope, see Step 5) ---
    _c1, _c2 = st.columns(2)
    if _c1.button("✓ Same as principal (suppress)", key=f"nd_same_{cid}_{member['member_cn']}", disabled=not can_write):
        db_manager.record_member_decision(case_folder_path, cid, member["member_cn"], "same",
                                           st.session_state.get('username', 'unknown'))
        st.rerun()  # full app rerun so the left list's status refreshes
    if _c2.button("✗ Distinct (keep in review)", key=f"nd_dist_{cid}_{member['member_cn']}", disabled=not can_write):
        db_manager.record_member_decision(case_folder_path, cid, member["member_cn"], "distinct",
                                           st.session_state.get('username', 'unknown'))
        st.rerun()
    # --- cluster attestation ---
    _all_decided = all(m["decision"] != "undecided" for m in others)
    _note = st.text_input("Attestation note (optional)", key=f"nd_note_{cid}")
    if st.button("✅ Approve cluster", key=f"nd_approve_{cid}",
                 disabled=not (can_write and _all_decided)):
        db_manager.approve_cluster(case_folder_path, cid, st.session_state.get('username', 'unknown'), _note or None)
        st.success("Cluster attested."); st.rerun()
    if not _all_decided:
        st.caption("Decide every member (Same/Distinct) to enable cluster approval.")
```

> **Widget-key hygiene (M-7):** every widget key is unique and namespaced (`nd_*_{cid}` / includes `member_cn`). Do not combine `index=`/`value=` with `key=`. The `st.rerun()` after each write is the **app-scope escape** required by the `fragment-scope-rule` lesson — the DB write must rerun the whole page so the left list badges/counts update; do not let the write live silently inside the fragment's local rerun.

- [ ] **Step 5: Manual verification (the UI has no unit harness)**

Walk a fixture: select a cluster → step members → confirm the diff highlights changed tokens → click "Same" → verify the member gains `NearDupe-Suppressed` and disappears from the default review grid → click "Distinct" on another → verify it stays in the grid → decide all → "Approve cluster" enables → approve → left list shows ✅. Re-open a closed case → buttons disabled, list still visible.

- [ ] **Step 6: Housekeeping + commit β**

- Version headers: `pages/4_Review.py` (minor — new tab/feature), `os_manager.py` (minor), `neardupe_diff.py` (new, 1.0.0).
- CHANGELOG: `NEW: pages/4_Review.py — Near-Dupe Clusters review tab (side-by-side diff, per-member confirm, cluster attestation)`, `NEW: neardupe_diff.py — pure side-by-side diff HTML helper`, `NEW: os_manager.py — get_document_content accessor`.
- `pytest tests/test_neardupe_diff.py -v` → PASS. Re-run `tests/test_neardupe_clusters.py` → PASS.

```bash
git add pages/4_Review.py os_manager.py neardupe_diff.py tests/test_neardupe_diff.py CHANGELOG.md
git commit -m "beta-2.16 C8b (S-1b): Review Near-Dupe Clusters tab — side-by-side diff + confirm/attest"
```

---

### Task β-Analytics: Re-run type-to-confirm guard + `get_near_dupe_review_progress` helper

> Added 2026-05-28 per spec §6 (refined re-run policy) + §11.10. Modifies the C8a-landed "Clear & Re-run Near-Duplicate" handler in `pages/3_Analytics.py` so a reviewer cannot accidentally discard accumulated decisions with a single click. Helper also subsumes the F2-dispositioned inline metric loop in the Execute path.

**Files:**
- Modify: `db_manager.py` — add `get_near_dupe_review_progress(case_folder)` near the other neardupe-cluster helpers (after `clear_near_dupe_clusters`).
- Modify: `pages/3_Analytics.py` — "Clear & Re-run Near-Duplicate" handler (C8a-landed at L628–643 against pre-Phase-B HEAD; **re-locate by stem** `Clear & Re-run Near-Duplicate` — line numbers will have drifted post-C8a/C8b α).
- Test: extend `tests/test_neardupe_clusters.py` with helper tests.

- [ ] **Step 1: Test for `get_near_dupe_review_progress` (TDD)**

```python
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
```

- [ ] **Step 2: Implement the helper**

```python
def get_near_dupe_review_progress(case_folder):
    """Aggregate read for the Analytics confirmed/pending metric AND the
    Clear-&-Re-run type-to-confirm guard. Returns a dict with:
      confirmed   — count of non-principal members with decision='same' (suppressed)
      pending     — count of non-principal members with decision='undecided'
      n_decisions — total count of members with decision != 'undecided'
                    (drives the §6 type-to-confirm guard threshold)
      n_clusters  — total cluster rows
    Single connection, single query — replaces the F2-dispositioned inline
    per-cluster get_cluster_members loop in 3_Analytics.py Execute metric block."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT
              SUM(CASE WHEN is_principal=0 AND decision='same' THEN 1 ELSE 0 END) as confirmed,
              SUM(CASE WHEN is_principal=0 AND decision='undecided' THEN 1 ELSE 0 END) as pending,
              SUM(CASE WHEN decision != 'undecided' THEN 1 ELSE 0 END) as n_decisions
            FROM near_dupe_cluster_members
        """).fetchone()
        n_clusters = conn.execute("SELECT COUNT(*) FROM near_dupe_clusters").fetchone()[0]
        return {
            "confirmed":   row["confirmed"]   or 0,
            "pending":     row["pending"]     or 0,
            "n_decisions": row["n_decisions"] or 0,
            "n_clusters":  n_clusters,
        }
    finally:
        conn.close()
```

- [ ] **Step 3: Run tests** → both PASS.

- [ ] **Step 4: Wire the type-to-confirm guard into the Analytics handler**

Locate the "Clear & Re-run Near-Duplicate" button in `pages/3_Analytics.py` (grep `Clear & Re-run Near-Duplicate`). Replace the immediate-fire path with:

```python
# § 6 re-run type-to-confirm guard
_progress = db_manager.get_near_dupe_review_progress(case_folder)
_n_dec = _progress["n_decisions"]
if _n_dec == 0:
    # No decisions to lose — the original warning-and-click flow stands.
    if st.button("⚠️ Clear & Re-run Near-Duplicate", key="clear_rerun_nd"):
        n_clusters, n_decisions = db_manager.clear_near_dupe_clusters(case_folder)
        # ... existing re-cluster + log_audit calls ...
        st.rerun()
else:
    st.error(
        f"⚠️ This will discard **{_n_dec} reviewer decisions** across "
        f"**{_progress['n_clusters']} clusters**, including any granular "
        f"Re-open work. Type the exact phrase below to confirm — or cancel."
    )
    _required = f"CLEAR {_n_dec} DECISIONS"
    _typed = st.text_input(
        f"Type `{_required}` to enable Clear & Re-run:",
        key="nd_clear_confirm_text",
        placeholder=_required,
    )
    _col_a, _col_b = st.columns(2)
    if _col_b.button("Cancel", key="nd_clear_cancel"):
        st.session_state.pop("nd_clear_confirm_text", None)
        st.rerun()
    if _col_a.button(
        "Clear & Re-run Near-Duplicate",
        type="primary",
        disabled=(_typed != _required),
        key="nd_clear_rerun_armed",
    ):
        n_clusters, n_decisions = db_manager.clear_near_dupe_clusters(case_folder)
        # ... existing re-cluster + log_audit calls ...
        db_manager.log_audit(
            case_folder, "NEARDUPE_FORCE_RERUN",
            username=st.session_state.get('username', 'unknown'),
            module="Analytics",
            details=json.dumps({"discarded_decisions": _n_dec,
                                "discarded_clusters": _progress['n_clusters']}),
        )
        st.session_state.pop("nd_clear_confirm_text", None)
        st.rerun()
```

> Notes for the executor: confirm at preflight time that the C8a-landed handler's exact structure matches this skeleton (the surrounding tag-clear `REPLACE` statements were already removed in C8a per the v3 preflight; `clear_near_dupe_clusters` owns tag-stripping). Match `st.button` `key=` and `st.text_input` `key=` to the project's existing prefix convention if any (grep for `key="nd_` in `pages/3_Analytics.py`).

- [ ] **Step 5: Manual verification**
  1. Empty case (no decisions): "Clear & Re-run" fires on a single click → no prompt.
  2. With 1+ decisions: button click reveals the type-to-confirm; wrong text → button stays disabled; correct text → button enables and fires; audit_log shows `NEARDUPE_FORCE_RERUN` with the discarded count.
  3. Cancel button clears the armed state.

- [ ] **Step 6: Replace the confirmed/pending metric inline loop with the new helper**

In the Execute metric block (the F2-dispositioned inline `for c in _nd_clusters` loop in 3_Analytics.py, post-Execute persist), replace with:

```python
_progress = db_manager.get_near_dupe_review_progress(case_folder)
col3.metric("Confirmed suppressed", _progress["confirmed"],
            help="Members a reviewer confirmed as true duplicates.")
st.caption(
    f"⏳ {_progress['pending']} members staged, awaiting reviewer confirmation "
    f"in Review → Near-Dupe Clusters."
)
```

- [ ] **Step 7: Commit (bundles into the C8b commit at end of β3, or lands as its own micro-commit before β3 — preflight decides)**

---

## COMMIT γ — Reporting + production glue

### Task γ1: Dedup Report reads new tables

**Files:**
- Modify: `db_manager.py` (`get_near_dupe_cluster_detail`) and/or `pages/3_Analytics.py` Tab 3 caller

- [ ] **Step 1: Repoint cluster detail at the real cluster tables**

Replace `get_near_dupe_cluster_detail`'s family-`group_id` query (the old grouping never reconstructed similarity clusters) with a read over `near_dupe_clusters` + `near_dupe_cluster_members`, returning per-cluster `principal_cn`, `principal_name`, `member_count`, confirmed-suppressed count, and `review_status`. Keep the return-key names the Tab 3 renderer expects, or update the renderer in the same commit.

- [ ] **Step 2: Manual verification** — Dedup Report shows clusters with confirmed/pending + attestation status.

### Task γ2: Production pending-review FYI

**Files:**
- Modify: `pages/5_Production.py`

- [ ] **Step 1: Non-blocking notice at burn time**

Where the production run is assembled, add a read of pending clusters and a non-blocking `st.warning` / `st.info`: `f"ℹ️ {n} near-dupe clusters are still pending review."` — **does not block** the burn. (The court-facing record is S-1c.)

- [ ] **Step 2: Manual verification** — message appears with pending clusters; production proceeds.

### Task γ3: Finalize cross-module record + tests

- [ ] **Step 1:** `DEPENDENCY_MAP.md` — finalize the two-table + helpers + deferred-tag entries; add the `get_document_content` OS read; note Dedup Report + Production consumers.
- [ ] **Step 2:** Full suite: `pytest tests/test_neardupe_clusters.py tests/test_neardupe_diff.py tests/test_neardupe_shingling.py -v` → all PASS.
- [ ] **Step 3: Housekeeping + commit γ**
  - Version headers: `db_manager.py`, `pages/3_Analytics.py`, `pages/5_Production.py` (patch each).
  - CHANGELOG: `CHANGE: db_manager.py — near-dupe cluster detail reads persisted cluster tables`, `NEW: pages/5_Production.py — pending near-dupe-review notice at burn`.

```bash
git add db_manager.py pages/3_Analytics.py pages/5_Production.py DEPENDENCY_MAP.md
git commit -m "beta-2.16 C8c (S-1b): dedup report + production glue for near-dupe cluster review"
```

---

## Self-Review (run by author after drafting)

**1. Spec coverage:**
- §3 deferred-tagging model → α2/α4/α5 (no tag at Execute; tag on "same"). ✓
- §4 schema (2 tables, decision log) → α1. ✓
- §5.1 Execute change + similarity source → α5 (MinHash.jaccard stash). ✓
- §5.2 master/detail + side-by-side diff + binary decision + attestation + fragment/app-scope + widget keys + stale-selection guard → β1/β3. ✓
- §5.3 helpers + supersede `get_near_dupe_cluster_detail` → α2-α4, γ1. ✓
- §5.4 dedup report + production FYI + DEPENDENCY_MAP + nav (none needed) → γ. ✓
- §6 RBAC (`tag`) / closed-case / re-run wipes decisions → β3 gate, α5 Step 3 + α2 clear. ✓
- §7 tests incl. exact-dupe-untouched invariant → **GAP found, fixed below**.
- §8 deferrals → not implemented by design (correct). ✓

**Gap fixed:** §7 calls for an explicit "exact dupes untouched" invariant pin. Add to `tests/test_neardupe_clusters.py`:

```python
def test_exact_dupes_untouched_by_neardupe_path():
    _fresh_case()
    conn = db_manager.get_connection(CASE)
    conn.execute("INSERT INTO documents (control_number, file_name, processing_status) VALUES ('E1','e1.pdf','Duplicate (MD5)')")
    conn.commit(); conn.close()
    _seed_doc("C1"); _seed_doc("C2")
    cid = db_manager.persist_near_dupe_clusters(CASE, [
        {"principal_cn":"C1","sim_min":0.9,"sim_max":0.9,
         "members":[{"cn":"C1","similarity":1.0,"is_principal":1},
                    {"cn":"C2","similarity":0.9,"is_principal":0}]}]) or db_manager.get_near_dupe_clusters(CASE)[0]["cluster_id"]
    db_manager.record_member_decision(CASE, cid, "C2", "same", "alice")
    conn = db_manager.get_connection(CASE)
    e1 = conn.execute("SELECT processing_status, tags FROM documents WHERE control_number='E1'").fetchone()
    conn.close()
    assert e1["processing_status"] == "Duplicate (MD5)"        # unchanged
    assert "NearDupe" not in (e1["tags"] or "")                # never touched
```

**2. Placeholder scan:** The "confirm during pre-flight" notes are deliberate CLI-verification anchors (live signatures: throwaway-case fixture, `_dt_now_iso`, `log_audit` kwargs, OS client accessor, `st.tabs` location) — not content placeholders. Every code step shows real code. ✓

**3. Type consistency:** `cluster` dict keys (`cluster_id`, `principal_cn`, `member_count`, `sim_min/max`, `review_status`, `principal_name`, `decided_count`) consistent across α3 getters and β3 UI. Member keys (`member_cn`, `is_principal`, `similarity`, `decision`, `file_name`) consistent across α3/α4/β3. `persist_near_dupe_clusters` payload shape (`principal_cn`, `members:[{cn,similarity,is_principal}]`, `sim_min/max`) consistent between α5 producer and α3 consumer. ✓ (Fixed inline: the Distinct button glyph rendered as mojibake on first draft → corrected to `✗`.)
