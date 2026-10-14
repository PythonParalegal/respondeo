# S-1c — Near-Duplicate Cluster Reporting in the Defensibility Report (Design)

**Sprint:** beta-2.16 (S-1c, next commit after C8a/b/c)
**Author:** PM Claude (brainstorming session, 2026-05-29)
**Status:** DESIGN — awaiting the maintainer's review, then `writing-plans`
**Relates to:** `docs/superpowers/specs/2026-05-24-neardupe-cluster-review-design.md` §10 (which stubbed S-1c as "read the two tables, produce a court-ready listing"). This spec is that stub, designed.

> **Sample data.** All control-number examples in this spec are synthetic (`DOC-NNNNNNN`).

---

## 1. Problem

C8a/b/c shifted near-duplicate suppression from *automatic-at-analysis* to *deferred-until-reviewer-confirms* (the fail-open deferred-tagging model). The court-facing defensibility report (`defensibility_report.py` §4 "Deduplication Methodology") was written for the **old** model, where "near-duplicate suppressed" was a single unambiguous count. Under the new model it is not:

- A document is only *actually* suppressed (removed from review) when a reviewer marks it `same` AND it is not family-attached.
- Documents awaiting review remain in the active review population (fail-open).
- Documents a reviewer judged `distinct` were actively kept.
- Family-attached documents are never suppressed even when confirmed `same` (family-integrity-over-dedup).

**The report's current gap is disclosure, not arithmetic.** Today's §4.1 `nd_suppressed` count is correct (it counts tagged docs), but the report is silent about the reviewer-gated model and about pending candidates. S-1c closes that gap and adds a per-cluster attestation record.

## 2. Goal / Non-goals

**Goal.** Make the defensibility report honestly represent the reviewer-gated near-duplicate model: a corrected §4 narrative, a §4.1 table that reports only actual reductions, and a new §4.2 cluster-review-and-attestation section with a 4-bucket disposition breakdown and a per-cluster roll-up.

**Non-goals (deferred, out of scope for S-1c):**
- Flag #30 (non-transitive / overlapping clusters; union-find merge) — unchanged.
- Member-by-member listing in the PDF — the roll-up is cluster-level only.
- Any Production-gating behavior change — productions remain non-blocked on pending review (C8c FYI banner only).
- Any change to the near-dupe analysis algorithm, the Review cluster UI, or the persistence tables.

## 3. Approach (chosen: A — extend §4 in place)

Keep the entire deduplication story in §4. Update the §4 narrative + §4.1 table, then add a §4.2 sub-section. Rejected alternatives: a standalone top-level section (splits the dedup narrative across two locations → two numbers that can disagree) and a full §4 rewrite (disproportionate risk to a stable court-facing section).

## 4. Data model (verified)

Non-principal cluster member fate = `decision` × `family_preserved` (family-preservation is a cross-cutting guard, db_manager.py:4503):

| `decision` | family-attached? | Tagged `NearDupe-Suppressed`? | In review population? | Report bucket |
|---|---|---|---|---|
| `same` | no | **Yes** | **Removed** | Confirmed-Suppressed |
| `same` | yes | No (guarded) | Retained | Confirmed-but-Family-Retained |
| `distinct` | either | No | Retained | Reviewer-Distinct |
| `undecided` | either | No (fail-open) | Retained | Pending |

Plus the **principal** (`is_principal=1`) — retained as representative.

**Reconciliation invariant (revised — B-1, 2026-06-01).** Reconciliation is at the **document level**, not the per-cluster-sum level. Under Flag #30 a document can be a non-principal member of more than one cluster (observed on the Test(small) regression case), and `record_member_decision` fans one decision out to all of a member's rows. Therefore:
- **Document-level (reconciles):** the §4.1 + §4.2-summary "Confirmed-Suppressed" figure is the distinct-document tag count `nd_suppressed`. The other summary buckets (Family-Retained / Distinct / Pending) are distinct-document counts classified once per `member_cn`.
- **Per-row (always true):** within a single cluster row, `Suppressed + Family-Retained + Distinct + Pending + 1 principal = member_count`.
- **Cross-section (does NOT hold under overlap, by design):** summing the per-cluster "Suppressed" column does NOT equal `nd_suppressed` when documents span clusters — the per-cluster table is footnoted accordingly (§6.4). The earlier "summed clusters == nd_suppressed by construction" claim is withdrawn.

## 5. Data-layer changes (`db_manager.py` — CLI executes)

> Line numbers are draft-time references; CLI re-verifies against current state at execution (line-number-drift discipline).

**5.1 `get_near_dupe_cluster_detail()` (≈ db_manager.py:4367).** Today returns `confirmed_count` (= `same`, both family values) + `pending_count` (= `undecided`, non-principal, family_preserved=0). Add:
- `family_retained_count` — `decision='same'` AND `family_preserved=1`, non-principal.
- `distinct_count` — `decision='distinct'`, non-principal.

Then **Suppressed (per cluster, for the table) = `confirmed_count − family_retained_count`** — a per-(cluster,member) figure used only in the §4.2 table rows, NOT summed for reconciliation. The document-level summary's Suppressed figure is the tag-based `nd_suppressed` (see §5.2). (Resolved additive per spec §9 / CLI PJ-1: keep `confirmed_count`, add the two fields.)

**5.2 `get_defensibility_dedup` (≈ db_manager.py:5064) — the helper the report actually calls** (NOT `get_data_reduction_stats` at 3315, which is the Analytics Dedup Report's helper and is where `nd_pending` currently lives). `get_defensibility_dedup` has none of the disposition fields yet. Add four **distinct-document** aggregates — `nd_undecided`, `nd_distinct`, `nd_family_retained` (each `COUNT(DISTINCT member_cn)` classified once per document by fan-out-consistent decision + per-document `MAX(family_preserved)`, mutually exclusive by precedence so they reconcile with the tag-based `nd_suppressed`), plus `n_clusters` (plain cluster-row count). Do NOT use `COUNT(*)` pair counts — they double-count under Flag #30 overlap. **(B-2) The "pending" bucket is named `nd_undecided` and counts ALL undecided members (any family state), NOT the shipped `pending_count`/`get_data_reduction_stats.nd_pending` semantic (undecided AND `fp=0`) — reusing the suppressibility filter would drop undecided+family members, the default post-run state.** `fp` mirrors the tag guard: `MAX(family_preserved)` over ALL of a member's rows. The plan (Task 2) carries the single-pass `GROUP BY member_cn` classification query:
- `nd_family_retained` — distinct docs classified `same` + family-protected (`MAX(family_preserved)=1`).
- `nd_distinct` — distinct docs classified `distinct`.
- `nd_undecided` — distinct docs classified `undecided` (**any** family state — B-2; family-attached undecided members are pending *review*, even though they can never be *suppressed*).
- (`nd_suppressed` already exists, tag-based + distinct — it is the authoritative "suppressed" figure; the classification's suppressed bucket must equal it.)
- `n_clusters` — **uncapped** count of `near_dupe_clusters` rows (needed for the §4.2 truncation note; must NOT be `len(get_near_dupe_cluster_detail(...))`, which is capped at 200).

`net_reviewable` is left untouched — it already excludes only tagged (Confirmed-Suppressed) docs, which is correct under the deferred-tagging model.

**5.3 Planned test-contract updates (calibration, NOT regression).** `tests/test_neardupe_clusters.py::test_dr_helper_returns_new_shape` (≈ L520) asserts the exact key-set of `get_near_dupe_cluster_detail`; CLI adds `family_retained_count` + `distinct_count` to the expected set. `test_dr_helper_confirmed_pending_counts` (≈ L529) already seeds a `distinct` decision (C3) and a `same` (C2) — add `distinct_count == 1` and (with a family-preserved seed) `family_retained_count` assertions. Flag these in the preflight as intended contract changes per `regression-test-as-calibration-canary.md`.

## 6. Presentation changes (`defensibility_report.py` — CLI executes)

**6.1 Data collection.** `_collect_dedup_stats()` (feeds `data['dedup']`, called at ≈ defensibility_report.py:863) surfaces the new `nd_family_retained` / `nd_distinct` / `n_clusters` fields. Add a new collector (e.g. `_collect_near_dupe_clusters()` calling `db_manager.get_near_dupe_cluster_detail`) into the `data` dict for the §4.2 table.

**6.2 §4 narrative (≈ L579–601).** Add a short paragraph after the MinHash LSH bullet explaining the reviewer-gated model: near-duplicate candidates are identified algorithmically (≥90% similarity), but suppression is **not** automatic — a reviewer confirms each. Confirmed → suppressed and attested; awaiting review → retained in the active population (fail-open); reviewer-distinct → actively retained; family-attached → retained to preserve family integrity even when confirmed.

**6.3 §4.1 table (≈ L603–617) — reductions only.** Relabel the existing row to **"Near-Duplicate Confirmed-Suppressed (reviewer-attested)"** = `nd_suppressed`. **Do NOT** add pending/distinct/family rows here — this table reports actual review-population reductions, and those three buckets are retained, not reductions. Adding them as rows risks a reader summing them as reductions. Net Review Population row is unchanged.

**6.4 §4.2 "Near-Duplicate Cluster Review & Attestation" (new).**

Lead summary sentence (sourced from the uncapped case-wide aggregates):

> The platform identified **{n_clusters}** near-duplicate clusters. Of the non-principal documents within them: **{nd_suppressed}** were reviewer-confirmed as duplicates and suppressed; **{nd_family_retained}** were confirmed duplicates but retained to preserve family integrity; **{nd_distinct}** were reviewed and determined distinct (retained); and **{nd_undecided}** remain pending review (retained pending confirmation). **{n_attested} of {n_clusters}** clusters have been reviewer-attested as of report generation.

Roll-up table (one row per cluster, biggest-first, ≤200 per the helper's LIMIT). **Principal column shows the control number, never Bates** — a suppressed document is excluded from production and therefore never receives a Bates number; the §4.2 namespace is control-number space (reduction happens pre-production):

```
Cluster | Principal (control #) | Members | Suppressed | Family-Ret. | Distinct | Pending | Similarity | Attestation
--------+-----------------------+---------+------------+-------------+----------+---------+------------+--------------------
  12    | DOC-0000100           |    9    |     6      |      1      |    1     |    0    |  90–97%    | ✓ reviewer  2026-05-28
   7    | DOC-0000200           |    5    |     2      |      0      |    1     |    2    |  91–94%    | Pending
```

Per-row arithmetic is self-auditing: `Suppressed + Family-Ret. + Distinct + Pending + 1 = Members`. Attestation column shows `✓ {reviewed_by}  {reviewed_at:date}` when `review_status='approved'`, else "Pending".

**Multi-cluster footnote (required — B-1).** Immediately below the table, render: *"A document may belong to more than one near-duplicate cluster; per-cluster counts above may therefore sum to more than the distinct-document totals in the summary. Each document is counted once in the summary."* This is what makes the per-cluster table honest under Flag #30 overlap — the table is per-(cluster,member), the summary is per-document, and the footnote names the gap rather than letting a reader infer an error.

**6.5 Edge cases.**
- **No clusters / analysis not run** (`get_near_dupe_cluster_detail` returns `[]` and `n_clusters == 0`): render an explicit narrative line — "No near-duplicate clusters were identified for this matter; accordingly, no near-duplicate suppressions were applied." Never an empty table or misleading zeros (`no-silent-default`).
- **> 200 clusters** (`n_clusters > 200`): the per-cluster table is capped at 200, so render a note — "The table lists the 200 largest clusters; **{n_clusters}** clusters were identified in total. The aggregate counts above and in §4.1 reflect all clusters." The summary line and §4.1 use uncapped aggregates, so only the *table* truncates, never the numbers (`no-silent-caps`).

## 7. Testing

- **db_manager:** extend `tests/test_neardupe_clusters.py` for the new helper fields + values (§5.3); add `nd_undecided` (incl. the B-2 undecided+family cell) / `nd_distinct` / `nd_family_retained` / `n_clusters` dedup-stats tests, paralleling the existing `get_data_reduction_stats` `nd_pending` test, plus the partition-identity assertion.
- **Report render:** new/extended test asserting (HTML-substring style, matching existing report tests) the §4.2 header, the four disposition labels, the not-run placeholder branch, and the >200 truncation note.
- **Reconciliation test (the key one — revised B-1):** with a **Flag #30 overlap fixture** (one doc a non-principal member of ≥2 clusters), assert (a) the document-level summary Suppressed (`nd_suppressed`, distinct) counts it once and equals §4.1; (b) the distinct-document classification's suppressed bucket equals `nd_suppressed`; (c) the per-cluster table "Suppressed" column summed *strictly exceeds* `nd_suppressed` under overlap — documenting the multi-cluster reality, not asserting a false equality. A non-overlap companion test pins the family-guarded-`same` case (`family_retained_count` rises, `nd_suppressed` does not).

## 8. Cross-module impact

- **DEPENDENCY_MAP.md:** register `defensibility_report.py` as a new consumer of `near_dupe_clusters` / `near_dupe_cluster_members` and of `get_near_dupe_cluster_detail` (with new fields); note the new `get_defensibility_dedup` fields.
- **Docs (sprint-close context maintenance):** note in user/technical docs that the defensibility report now reports near-duplicate review disposition + attestation.
- **No schema migration, no OpenSearch change, no session-state key, no new config value.**

## 9. Open items for the implementation plan

1. CLI's choice in §5.1: add `family_retained_count` + `distinct_count` alongside the existing `confirmed_count`, vs. replace `confirmed_count` with an explicit family-excluded `suppressed_count`. Either satisfies the reconciliation invariant; the plan picks one.
2. Exact PDF column widths / Principal filename inclusion (control number is required; filename is optional and may be dropped or truncated for Letter-portrait width) — a layout detail for implementation, not a design decision.
