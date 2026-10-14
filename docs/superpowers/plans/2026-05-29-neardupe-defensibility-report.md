# Near-Duplicate Cluster Reporting in the Defensibility Report — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **PM/CLI note (this project):** This plan is the basis for the beta-2.16 **C9 (S-1c)** CLI preflight. PM does not execute. CLI executes under the maintainer's Stage 2 greenlight, following CLAUDE.md version-tracking (header bumps on every `.py` touched; CHANGELOG entries) and the post-sprint impact audit. The per-task "commit checkpoint" steps below are logical checkpoints; the **actual commit packaging is the C9 preflight's call** — likely one commit (data layer + presentation are cohesive), or a data-layer/presentation split if the maintainer prefers. Do not micro-commit per task without confirming packaging.

**Goal:** Make the court-facing defensibility report honestly represent the reviewer-gated near-duplicate suppression model — corrected §4 narrative, §4.1 reporting only actual reductions, and a new §4.2 cluster-review-and-attestation section with a 4-bucket disposition breakdown and a self-auditing per-cluster roll-up.

**Architecture:** Presentation-only feature over the already-built C8a/b/c persistence (`near_dupe_clusters` + `near_dupe_cluster_members`). Two `db_manager.py` read helpers gain fields; `defensibility_report.py` consumes them in §4. No schema migration, no algorithm change, no UI change.

**Tech Stack:** Python, SQLite (`db_manager.py`), HTML→PDF via pdfkit/wkhtmltopdf (`defensibility_report.py`), pytest.

**Spec:** `docs/superpowers/specs/2026-05-29-neardupe-defensibility-report-design.md`

---

## File map

- **Modify** `db_manager.py`:
  - `get_near_dupe_cluster_detail()` (≈ L4367) — add `family_retained_count`, `distinct_count` (additive; `confirmed_count` retained so the existing Analytics Dedup Report consumer is untouched — resolves spec §9 item 1 in favor of additive).
  - `get_defensibility_dedup()` (≈ L5064) — add `nd_undecided`, `nd_distinct`, `nd_family_retained`, `n_clusters`.
- **Modify** `defensibility_report.py`:
  - `_collect_dedup_stats()` (≈ L's wrapping `get_defensibility_dedup`) — pass new fields through + add to the exception-fallback dict.
  - `generate_report()` (≈ L859) — add `data['near_dupe_clusters']`.
  - new `_collect_near_dupe_clusters()` collector.
  - `_render_html()` §4 (≈ L569–617) — narrative paragraph + §4.1 relabel + new §4.2 section.
- **Modify** `tests/test_neardupe_clusters.py` — helper-shape + value tests.
- **Create/Modify** `tests/test_defensibility_neardupe_report.py` — render + reconciliation tests.
- **Modify** `DEPENDENCY_MAP.md` — register the new consumer + fields.

> All line numbers are draft-time references. **CLI re-verifies every cited line against current state before editing** (line-number-drift discipline).

---

### Task 1: `get_near_dupe_cluster_detail` — add `family_retained_count` + `distinct_count`

**Files:**
- Modify: `db_manager.py` — `get_near_dupe_cluster_detail()` (≈ L4393–4418, the SELECT)
- Test: `tests/test_neardupe_clusters.py` (≈ L515–536)

- [ ] **Step 1: Update the shape test to expect the two new keys**

In `test_dr_helper_returns_new_shape` (≈ L520), extend the expected set:

```python
    expected = {"cluster_id", "run_date", "principal_cn", "principal_name",
                "member_count", "sim_min", "sim_max", "review_status",
                "reviewed_by", "reviewed_at", "confirmed_count", "pending_count",
                "family_retained_count", "distinct_count"}
    assert set(r.keys()) == expected
```

- [ ] **Step 2: Add a value test for the new fields**

Append to `tests/test_neardupe_clusters.py`:

```python
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
    # Reconciliation: suppressed (tagged) == confirmed - family_retained
    assert r["confirmed_count"] - r["family_retained_count"] == 1
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -m pytest tests/test_neardupe_clusters.py -k "new_shape or distinct_and_family" -v`
Expected: FAIL — `AssertionError` on the key set / `KeyError: 'family_retained_count'`.

- [ ] **Step 4: Add the two subqueries to the SELECT**

In `get_near_dupe_cluster_detail()`, after the existing `pending_count` subquery (≈ L4413), add:

```python
                (SELECT COUNT(*) FROM near_dupe_cluster_members m
                 WHERE m.cluster_id = c.cluster_id
                   AND m.decision = 'same'
                   AND m.is_principal = 0
                   AND m.family_preserved = 1) AS family_retained_count,
                (SELECT COUNT(*) FROM near_dupe_cluster_members m
                 WHERE m.cluster_id = c.cluster_id
                   AND m.decision = 'distinct'
                   AND m.is_principal = 0) AS distinct_count
```

(Add a comma after the `pending_count` subquery's closing `AS pending_count`.) Update the docstring's "Returns list[dict] with keys" block to list `family_retained_count` and `distinct_count`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -m pytest tests/test_neardupe_clusters.py -v`
Expected: PASS (all, including the pre-existing tests).

- [ ] **Step 6: Version header + commit checkpoint**

Bump `db_manager.py` header (minor — new returned fields), `last_modified`, `last_commit: pending`. CHANGELOG: `CHANGE: db_manager.py — get_near_dupe_cluster_detail adds family_retained_count + distinct_count for S-1c report`.

---

### Task 2: `get_defensibility_dedup` — add `nd_undecided`, `nd_distinct`, `nd_family_retained`, `n_clusters`

**Files:**
- Modify: `db_manager.py` — `get_defensibility_dedup()` (≈ L5064–5119)
- Test: `tests/test_neardupe_clusters.py`

> **Scoping note (write this as a code comment):** `near_dupe_clusters`/`near_dupe_cluster_members` are populated only from the `source_party='Internal'` corpus (`pages/3_Analytics.py:352`), so these counts are outbound-scoped by construction — do NOT add `outbound_source_filter_sql()` (it targets the `documents` table; these query the cluster tables directly).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_neardupe_clusters.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -m pytest tests/test_neardupe_clusters.py::test_defensibility_dedup_neardupe_fields -v`
Expected: FAIL — `KeyError: 'n_clusters'`.

- [ ] **Step 3: Add the four counts + return keys**

In `get_defensibility_dedup()`, before the `return {` (≈ L5107), add:

```python
        # Near-dupe cluster dispositions (S-1c). Cluster tables are outbound-only by
        # construction (clusters built from source_party='Internal' corpus,
        # pages/3_Analytics.py:352) — no documents-table outbound filter applies here.
        #
        # B-1 FIX (v2): DISTINCT-DOCUMENT counts, not (cluster,member)-pair counts. Under
        # Flag #30 a doc can be a member of >1 cluster (observed on the Test(small) regression case); COUNT(*)
        # would double-count and break reconciliation with the tag-based nd_suppressed.
        #
        # B-2 FIX (v3): classify each distinct non-principal document ONCE over the FULL
        # decision×family grid (6 cells). v2 dropped (undecided, family_preserved=1) — the
        # DEFAULT post-run state of every family-attached member (decision DEFAULT
        # 'undecided', db_manager.py:515) — under-reporting the unreviewed population on a
        # court PDF. "Pending review" is therefore ALL undecided (any family state), named
        # `nd_undecided` to NOT collide with the suppressibility-`pending` semantic in
        # get_data_reduction_stats/pending_count (undecided AND fp=0, kept for Analytics).
        # fp mirrors the tag guard EXACTLY: MAX(family_preserved) over ALL of the member's
        # rows (db_manager.py:4523-4525), not just is_principal=0 rows (H-1).
        # Disposition cells: same&fp0 -> suppressed (= nd_suppressed, tag-based, below);
        # distinct -> distinct; same&fp1 -> family-retained; undecided(any fp) -> undecided.
        _disp = conn.execute("""
            SELECT
              SUM(CASE WHEN d_distinct=1 THEN 1 ELSE 0 END)      AS dist,
              SUM(CASE WHEN d_same=1 AND fp=1 THEN 1 ELSE 0 END) AS famret,
              SUM(CASE WHEN d_undecided=1 THEN 1 ELSE 0 END)     AS undecided_n
            FROM (
              SELECT m.member_cn,
                     (SELECT MAX(a.family_preserved) FROM near_dupe_cluster_members a
                       WHERE a.member_cn = m.member_cn) AS fp,
                     MAX(CASE WHEN m.decision='same' THEN 1 ELSE 0 END)      AS d_same,
                     MAX(CASE WHEN m.decision='distinct' THEN 1 ELSE 0 END)  AS d_distinct,
                     MAX(CASE WHEN m.decision='undecided' THEN 1 ELSE 0 END) AS d_undecided
              FROM near_dupe_cluster_members m
              WHERE m.is_principal=0
              GROUP BY m.member_cn
            )
        """).fetchone()
        nd_family_retained = _disp["famret"] or 0
        nd_distinct = _disp["dist"] or 0
        nd_undecided = _disp["undecided_n"] or 0
        n_clusters = conn.execute("SELECT COUNT(*) FROM near_dupe_clusters").fetchone()[0]
        # Partition identity (pinned by Task 6): the same&fp0 cell is carried by the
        # tag-based `nd_suppressed` (already computed above). Then
        #   nd_suppressed + nd_family_retained + nd_distinct + nd_undecided
        #   == COUNT(DISTINCT member_cn) over is_principal=0 rows.
        # All 6 decision×family cells have exactly one home.
```

Then add to the returned dict (after `'net_reviewable': net_reviewable,`):

```python
            'nd_family_retained': nd_family_retained,
            'nd_distinct': nd_distinct,
            'nd_undecided': nd_undecided,
            'n_clusters': n_clusters,
```

- [ ] **Step 4: Run to verify it passes**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -m pytest tests/test_neardupe_clusters.py -v`
Expected: PASS.

- [ ] **Step 5: Version header + commit checkpoint**

Bump `db_manager.py` header (minor). CHANGELOG: `CHANGE: db_manager.py — get_defensibility_dedup adds nd_undecided/nd_distinct/nd_family_retained/n_clusters for S-1c`.

---

### Task 3: Wire new fields + cluster detail into the report's data collection

**Files:**
- Modify: `defensibility_report.py` — `_collect_dedup_stats()`, `generate_report()` (≈ L859–870)
- Create function: `_collect_near_dupe_clusters()`

- [ ] **Step 1: Pass new dedup fields through + extend the fallback dict**

In `_collect_dedup_stats()`, the success path returns `stats` (already carries the new keys from Task 2). Update the **exception-fallback dict** key list to include the new keys so §4.2 never `KeyError`s on the error path:

```python
        return {k: 0 for k in ['total_ingested', 'exact_dupes', 'content_dupes', 'processed',
                'nd_suppressed', 'nd_principals', 'thread_suppressed', 'thread_inclusive',
                'net_reviewable', 'reduction_pct', 'exact_dupe_pct', 'content_dupe_pct',
                'nd_pct', 'thread_pct',
                'nd_family_retained', 'nd_distinct', 'nd_undecided', 'n_clusters']}
```

- [ ] **Step 2: Add the cluster-detail collector**

Add near the other `_collect_*` functions:

```python
def _collect_near_dupe_clusters(case_folder):
    """Per-cluster near-dupe disposition rows for §4.2 (court-facing roll-up).
    Returns [] on any error or when no clusters exist."""
    try:
        return db_manager.get_near_dupe_cluster_detail(case_folder)
    except Exception as e:
        logger.error(f"Near-dupe cluster detail collection failed: {e}")
        return []
```

- [ ] **Step 3: Add it to the `data` dict in `generate_report()`**

After `data['collection_scope'] = _collect_collection_scope(case_folder)` (≈ L870):

```python
        data['near_dupe_clusters'] = _collect_near_dupe_clusters(case_folder)
```

- [ ] **Step 4: Smoke-check import**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -c "import defensibility_report"`
Expected: no error.

- [ ] **Step 5: Version header (no commit yet — bundle with Tasks 4–5)**

Bump `defensibility_report.py` header (minor — new function). Hold the commit; Tasks 4–5 finish the presentation in the same file.

---

### Task 4: §4 narrative paragraph + §4.1 relabel (reductions only)

**Files:**
- Modify: `defensibility_report.py` — `_render_html()` §4 (narrative ≈ L579–601; §4.1 table ≈ L603–617)

- [ ] **Step 1: Add the reviewer-gated narrative paragraph**

After the closing `</div>` of the §4 Defensibility Summary `narrative` block (≈ L601), insert:

```python
    html += """<div class="narrative">
    <strong>Reviewer-Gated Near-Duplicate Suppression:</strong>
    Near-duplicate candidates are identified algorithmically (MinHash LSH, 90%+
    textual similarity), but suppression is not automatic. A reviewer confirms each
    candidate: documents confirmed as duplicates are suppressed and attested;
    documents still awaiting review remain in the active review population;
    documents a reviewer determines to be distinct are retained; and documents
    attached to a family are retained to preserve family integrity even when
    confirmed as duplicates. Only reviewer-confirmed, non-family documents are
    removed from the review population. Per-cluster dispositions and reviewer
    attestation are detailed in &sect;4.2.
    </div>"""
```

- [ ] **Step 2: Relabel the §4.1 near-dupe row**

In the §4.1 `_rows` list (≈ L611), change the label only:

```python
        ('Near-Duplicate Confirmed-Suppressed (reviewer-attested)', dedup['nd_suppressed'], str(dedup['nd_pct'])),
```

(Do NOT add pending/distinct/family rows here — §4.1 reports actual reductions only.)

- [ ] **Step 3: Smoke-check import**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -c "import defensibility_report"`
Expected: no error.

---

### Task 5: §4.2 "Near-Duplicate Cluster Review & Attestation" section

**Files:**
- Modify: `defensibility_report.py` — `_render_html()` (immediately after the §4.1 table close, ≈ L617)
- Test: `tests/test_defensibility_neardupe_report.py` (create)

- [ ] **Step 1: Write the render tests (failing)**

Create `tests/test_defensibility_neardupe_report.py`. Use the existing `_render_html` entry with a hand-built `data` dict (mirror the shape `generate_report` assembles; only the keys §4.2 reads must be present). Inspect `tests/test_defensibility_inbound_exclusion.py` for the established `_render_html`-calling convention and reuse it.

```python
import defensibility_report as dr

def _base_data(dedup, clusters):
    # Minimal data dict for _render_html; fill the sections §4.2 + §4/§4.1 read.
    # Other sections may be zero/empty dicts mirroring the _collect_* fallbacks.
    ...  # CLI: build per the _collect_* fallback shapes (see each _collect_* except branch)

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

def test_s1c_section_no_clusters_placeholder():
    dedup = {**{k: 0 for k in ('total_ingested','exact_dupes','content_dupes','processed',
            'nd_suppressed','nd_principals','thread_suppressed','thread_inclusive','net_reviewable',
            'reduction_pct','exact_dupe_pct','content_dupe_pct','nd_pct','thread_pct',
            'nd_family_retained','nd_distinct','nd_undecided','n_clusters')}}
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
                for i in range(200)]  # helper would cap at 200
    html = dr._render_html(_base_data(dedup, clusters))
    assert "200 largest clusters" in html and "250" in html
```

- [ ] **Step 2: Run to verify they fail**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -m pytest tests/test_defensibility_neardupe_report.py -v`
Expected: FAIL — strings not present.

- [ ] **Step 3: Render §4.2 (summary + table + edge cases)**

After the §4.1 table close (`html += '</tbody></table>'`, ≈ L617), insert:

```python
    # 4.2 Near-Duplicate Cluster Review & Attestation (S-1c)
    html += '<h3>4.2 Near-Duplicate Cluster Review &amp; Attestation</h3>'
    _nd_clusters = data.get('near_dupe_clusters', [])
    _n_clusters = dedup.get('n_clusters', 0)
    if _n_clusters == 0:
        html += """<p>No near-duplicate clusters were identified for this matter;
        accordingly, no near-duplicate suppressions were applied.</p>"""
    else:
        _n_attested = sum(1 for c in _nd_clusters if c.get('review_status') == 'approved')
        html += f"""<p>The platform identified <strong>{_n_clusters:,}</strong> near-duplicate
        cluster(s). Of the non-principal documents within them:
        <strong>{dedup['nd_suppressed']:,}</strong> were reviewer-confirmed as duplicates and
        suppressed; <strong>{dedup['nd_family_retained']:,}</strong> were confirmed duplicates but
        retained to preserve family integrity; <strong>{dedup['nd_distinct']:,}</strong> were
        reviewed and determined distinct (retained); and
        <strong>{dedup['nd_undecided']:,}</strong> remain pending review (retained pending
        confirmation). <strong>{_n_attested:,} of {_n_clusters:,}</strong> cluster(s) have been
        reviewer-attested as of report generation. Documents shown below are identified by
        internal control number; suppressed documents are excluded from production and therefore
        bear no Bates number.</p>"""
        if _n_clusters > len(_nd_clusters):
            html += f"""<p><em>The table lists the {len(_nd_clusters):,} largest clusters;
            {_n_clusters:,} clusters were identified in total. The aggregate counts above and in
            &sect;4.1 reflect all clusters.</em></p>"""
        html += """<table><thead><tr>
            <th>Cluster</th><th>Principal (control #)</th><th>Members</th>
            <th>Suppressed</th><th>Family-Ret.</th><th>Distinct</th><th>Pending</th>
            <th>Similarity</th><th>Attestation</th></tr></thead><tbody>"""
        for c in _nd_clusters:
            _supp = c.get('confirmed_count', 0) - c.get('family_retained_count', 0)
            # B-2 (v3): per-row Pending = ALL undecided (any family state), derived so the
            # row self-audits: Suppressed + Family-Ret + Distinct + Pending + 1 principal =
            # Members. Do NOT use pending_count (undecided & fp0) — it drops undecided-family
            # members and breaks the per-row sum. = member_count - 1 - confirmed - distinct.
            _pending = c.get('member_count', 0) - 1 - c.get('confirmed_count', 0) - c.get('distinct_count', 0)
            _sim = (f"{c['sim_min']*100:.0f}&ndash;{c['sim_max']*100:.0f}%"
                    if c.get('sim_min') is not None and c.get('sim_max') is not None else '&mdash;')
            if c.get('review_status') == 'approved':
                _att = f"&#10003; {c.get('reviewed_by') or ''} {(c.get('reviewed_at') or '')[:10]}".strip()
            else:
                _att = 'Pending'
            html += (f"<tr><td>{c.get('cluster_id')}</td><td>{c.get('principal_cn') or '&mdash;'}</td>"
                     f"<td>{c.get('member_count', 0):,}</td><td>{_supp:,}</td>"
                     f"<td>{c.get('family_retained_count', 0):,}</td>"
                     f"<td>{c.get('distinct_count', 0):,}</td><td>{_pending:,}</td>"
                     f"<td>{_sim}</td><td>{_att}</td></tr>")
        html += '</tbody></table>'
        # B-1 FIX (v2): Flag #30 multi-cluster footnote. The per-cluster columns above
        # are per-(cluster, document); a document may belong to more than one cluster, so
        # they may sum to more than the distinct-document totals in the summary paragraph.
        html += """<p><em>Note: a document may belong to more than one near-duplicate
        cluster. Per-cluster counts in the table above may therefore sum to more than the
        distinct-document totals stated in the summary; each document is counted once in the
        summary (suppressed, retained, or pending), and may appear in more than one row
        here.</em></p>"""
```

- [ ] **Step 4: Run to verify they pass**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -m pytest tests/test_defensibility_neardupe_report.py -v`
Expected: PASS.

- [ ] **Step 5: Version header + commit checkpoint (bundles Tasks 3–5)**

Finalize `defensibility_report.py` header bump. CHANGELOG: `NEW: defensibility_report.py — §4.2 Near-Duplicate Cluster Review & Attestation + reviewer-gated §4 narrative (S-1c)`.

---

### Task 6: Reconciliation test (the cross-section guard)

**Files:**
- Test: `tests/test_defensibility_neardupe_report.py`

- [ ] **Step 1: Write the reconciliation test**

```python
import db_manager  # reuse the _fresh_case / _seed_doc / CASE helpers from test_neardupe_clusters

def test_s1c_reconciliation_under_flag30_overlap():
    """B-1 (v2) hybrid: document-level reconciliation. With a doc in TWO clusters
    (Flag #30), the §4.2 SUMMARY suppressed figure (tag-based nd_suppressed, distinct
    docs) counts it ONCE and equals §4.1; the per-cluster table legitimately sums to
    MORE. This fixture MUST seed an overlap — a single-cluster fixture would pass and
    mislead (the exact v1 blind spot)."""
    _fresh_case()
    for cn in ("C1", "C2", "C3", "C5"):
        _seed_doc(cn)
    # Two clusters that SHARE non-principal members C2 (-> same) and C3 (-> distinct):
    db_manager.persist_near_dupe_clusters(CASE, [
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
    cid1 = db_manager.get_near_dupe_clusters(CASE)[0]["cluster_id"]
    db_manager.record_member_decision(CASE, cid1, "C2", "same", "reviewer")
    db_manager.record_member_decision(CASE, cid1, "C3", "distinct", "reviewer")

    d = db_manager.get_defensibility_dedup(CASE)
    detail = db_manager.get_near_dupe_cluster_detail(CASE)

    # (a) Summary/§4.1 suppressed counts the overlapping doc ONCE (distinct, tag-based).
    assert d["nd_suppressed"] == 1
    # (b) H-3: distinct bucket also dedups under overlap — C3 counted once, not twice.
    assert d["nd_distinct"] == 1
    # (c) Per-cluster table sum DOUBLE-counts C2 (one 'same' row per cluster) -> 2.
    per_cluster_supp = sum(c["confirmed_count"] - c["family_retained_count"] for c in detail)
    assert per_cluster_supp == 2
    # (d) Documented relationship: per-cluster sum strictly EXCEEDS the distinct figure
    #     under overlap. This is the corrected invariant (NOT equality).
    assert per_cluster_supp > d["nd_suppressed"]
    # (e) H-2 partition identity: the four document-level buckets cover every distinct
    #     non-principal doc exactly once (here C2 + C3 = 2). This is the real regression
    #     guard — it breaks if any decision×family cell is dropped (B-2) or if tag-based
    #     nd_suppressed diverges from the classification.
    assert (d["nd_suppressed"] + d["nd_family_retained"]
            + d["nd_distinct"] + d["nd_undecided"]) == 2
```

> **CLI note:** the overlap seed (C2, C3 in two clusters each) is mandatory — the exact Flag #30 condition B-1 identified. Assertion (e) is the B-2/H-2 partition guard. Also keep a **non-overlap companion test** (single cluster) covering all six decision×family cells — crucially an `undecided` + `family_preserved=1` member — asserting it lands in `nd_undecided` (the B-2 cell), `family_retained_count` rises on a family-guarded `same` while `nd_suppressed` does not (tag guard, db_manager.py:4536–4541), and the partition identity holds.

- [ ] **Step 2: Run to verify pass (after DB-backed variant implemented)**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -m pytest tests/test_defensibility_neardupe_report.py -v`
Expected: PASS.

- [ ] **Step 3: Full near-dupe + report regression**

Run: `/c/Projects/ediscovery/.venv/Scripts/python.exe -m pytest tests/test_neardupe_clusters.py tests/test_defensibility_neardupe_report.py tests/test_defensibility_inbound_exclusion.py -v`
Expected: PASS (no regression in existing defensibility/near-dupe tests).

---

### Task 7: DEPENDENCY_MAP + docs note

**Files:**
- Modify: `DEPENDENCY_MAP.md`

- [ ] **Step 1: Register the new consumer**

Add to the appropriate section: `defensibility_report.py` is now a consumer of `near_dupe_clusters` / `near_dupe_cluster_members` (via `get_near_dupe_cluster_detail`) and of the new `get_defensibility_dedup` fields (`nd_undecided`, `nd_distinct`, `nd_family_retained`, `n_clusters`). Note the §4.2 reconciliation invariant.

- [ ] **Step 2: Commit checkpoint**

CHANGELOG: `DOCS: DEPENDENCY_MAP.md — register defensibility_report.py near-dupe cluster consumer (S-1c)`. User-facing doc updates (User_Guide / Technical Overview noting the report now includes near-dupe attestation) fold into the beta-2.16 sprint-close context-maintenance pass, not necessarily this commit.

---

## Self-Review (PM, against the spec)

**Spec coverage:** §1 problem → narrative (Task 4). §4.1 reductions-only → Task 4 Step 2. §4.2 4-bucket + roll-up + summary → Task 5. control_number-not-Bates → Task 5 narrative + the "bear no Bates number" line. Edge cases (not-run, >200) → Task 5 tests + render. Data-layer fields → Tasks 1–2. Reconciliation test → Task 6. Impact → Task 7. Spec §9 item 1 (additive vs. replace) → resolved additive (file map + Task 1). Spec §9 item 2 (column width/filename) → Task 5 renders control # only (filename omitted from the table for width; available in `principal_name` if the maintainer wants it). **No gaps.**

**Placeholder scan:** The only `...` is in Task 5 Step 1's `_base_data` helper, which is explicitly delegated to CLI with the exact shape source named (`_collect_*` fallback branches) — flagged, not hidden. Task 6 Step 1 names the DB-backed variant as the preferred form. Acceptable for a preflight basis; CLI fills `_base_data` from the real fallback shapes during execution.

**Type/name consistency:** Field names (`family_retained_count`, `distinct_count`, `nd_family_retained`, `nd_distinct`, `nd_undecided`, `n_clusters`) are used identically across Tasks 1–6. Per-cluster suppressed is consistently `confirmed_count - family_retained_count`.

**Open carry to preflight:** Task 5 Step 1's `_base_data` builder and Task 6's DB-backed variant are the two spots CLI completes from live fixture shapes; both are explicitly scoped, not vague.
