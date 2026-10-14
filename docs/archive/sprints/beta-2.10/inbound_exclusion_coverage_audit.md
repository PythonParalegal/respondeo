# Outbound Inbound-Exclusion Coverage Audit (beta-2.10 Commit 3)

**Purpose:** Inventory every document query in an outbound-destined context and confirm each will be covered by the mandatory `source_party` filter after Commit 3. This audit is a pre-flight gate per the sprint plan — the maintainer must approve before any source edits land.

**Date:** 2026-04-16
**Sprint:** beta-2.10 Inbound Production Module Extraction, Commit 3 of 8
**Author:** claude-code (Explore agent + spot-check verification)

## Headline

Sprint plan assumed **4 outbound queries** (grid_sql, base_df, cns branch, family_sql). The exhaustive audit found **12 outbound-destined queries missing the filter plus 4 toggle-gated queries**, including:

- **Privilege log query** (`pages/5_Production.py:3894`) — inbound docs with accidental privilege tags would appear on the privilege log handed to opposing counsel. 26(g) hazard.
- **Nine queries in `db_manager.get_defensibility_*` functions** (lines 4130–4245+) — feed defensibility_report.py, which generates court-destined PDFs. Inbound docs would inflate universe totals and skew processing/review metrics.

These four+9 extensions expand Commit 3's scope significantly. **Worth the maintainer's review before implementation.**

## Summary

| Category | Count |
|---|---|
| Outbound-destined queries already compliant | 3 |
| Outbound-destined queries using user-toggleable filter (must hoist) | 4 |
| Outbound-destined queries missing the filter entirely | 9 |
| Defense-in-depth hoist (1315 text extraction) | 1 |
| **Total outbound-destined receiving the filter in Commit 3** | **14** |
| Transitively covered via base_df (load file writers) | ~3 sites, no direct fix |
| Ambiguous (in-memory derived from filtered base) | 1 |
| Queries correctly NOT covered (inbound inclusion is right) | 3+ |

All **14 outbound queries** receiving the fix are enumerated below with file:line and fix approach.

---

## 1. Production Assembly (pages/5_Production.py)

### 1.1 Grid query — `grid_sql` (line 362)
- **Current:** Conditional `if exclude_external: grid_sql += " AND (source_party = 'Internal' OR source_party IS NULL)"`
- **Problem:** User-toggleable checkbox at line 348 controls whether the filter applies.
- **Fix:** Delete the checkbox and its conditional; append the clause unconditionally to `grid_sql`.

### 1.2 Base query — `base_df` (line 2558-2571)
- **Current:** Filter hoisted to shared `_exclusion_clauses` helper built from the `exclude_external` toggle in beta-2.9.
- **Problem:** Toggle-gated; unchecking the box removes the filter.
- **Fix:** Remove the toggle check; keep the clause as an unconditional string appended inline or move to a shared `_MANDATORY_INBOUND_FILTER` constant.

### 1.3 cns branch — explicit control-number list (line 2555)
- **Current:** `query = f"SELECT * FROM documents WHERE control_number IN ({placeholders})"` — zero filters.
- **Problem:** If a user selects an inbound doc into the grid (which today they can, since grid shows inbound when the box is unchecked), this branch passes it through.
- **Fix:** Append the mandatory clause even on the cns path. Defensibility trumps user-explicit selection here.

### 1.4 Family-expansion — `family_sql` (line 2631 post-sprint after my earlier diff; line numbers may have shifted)
- **Current:** In beta-2.9, the family query was unconditional-unfiltered; a later beta-2.9 commit added the shared `_exclusion_sql` (which includes the toggleable source_party clause).
- **Problem:** Still toggle-gated.
- **Fix:** Same as 1.2 — unconditional clause.

### 1.5 Hierarchy query — `hierarchy_df` (line 2606 area)
- **Current:** Pulls parent_id mapping for the family-walker. Reads from the whole documents table.
- **Analysis:** Used only to walk from a candidate to its root for family-expansion — after 1.4 is fixed, any inbound parent would be excluded from the family set. BUT: if an inbound parent is the root of an outbound child (implausible but worth flagging), the walker could surface the inbound parent's control_number into `all_target_cns`, then 1.4's filter would still drop it from the actual INSERT. So functionally covered by 1.4.
- **Fix:** None required; verify after 1.4 lands.

### 1.6 Text-extraction query (pages/5_Production.py:1315) — **MEDIUM (defense-in-depth)**
- **Current:** `"SELECT extracted_text FROM documents WHERE control_number = ?"` inside Pass 2 burn/stamp loop. Annotated `# db_manager: exempt (production loop)` from the M-4 migration.
- **Analysis:** `cn` here is drawn from the already-filtered `base_df`, so transitively no inbound doc reaches this query in normal flow. The annotation predates this sprint and documents that the query is intentionally inline (performance-sensitive per-doc fetch during Pass 2).
- **But:** Hoisted from LOW to MEDIUM per reviewer direction (2026-04-16). Defense-in-depth is worth one extra clause — a future refactor that changes how `cn` is sourced could silently break the transitive guarantee.
- **Fix:** Append `AND (source_party = 'Internal' OR source_party IS NULL)` to the WHERE clause. Zero behavior change today (cn is already from a filtered set); guards against future refactor drift.

---

## 1b. Load files (DAT/OPT writer) — Transitively Covered (no direct fix needed)

Load file generation writes `.dat` (metadata) and `.opt` (image path manifest) files after Pass 2 finalize. These are **not direct queries** — the writer iterates over the same `prod_data` / `df` structure that was built from `base_df`, so any filter applied to `base_df` (fix 1.2 above) transitively covers the load files.

Coverage note for future maintainers: if you grep for "load file filter" and find none, that is correct. Load files are downstream of base_df and inherit its filtering. Any defect there would require either (a) the load-file writer fetching docs independently from the DB (does not happen today — verified) or (b) base_df filtering being broken (prevented by `TestProductionInboundExclusion` tests).

Specific writer locations in `pages/5_Production.py`:
- `.dat` generation (around line 1630+) — iterates `prod_data`, no DB query
- `.opt` generation (around line 1635) — iterates `opt_entries`, no DB query
- Privilege log export (3894+) — has its own query, covered by §2

If the writer is ever refactored to fetch docs independently, the mandatory filter must be re-applied there.

---

## 2. Privilege Log — `_pl_query` (pages/5_Production.py:3894) **🚨 26(g) HAZARD**

- **Current:**
  ```sql
  SELECT d.control_number, d.begdoc, d.enddoc, ... FROM documents d
  WHERE ({_pl_base_conditions}){_pl_shell_filter}
  ```
  `_pl_base_conditions` = `"d.privilege_status IN ('Withhold', 'Redact')"` + optional `"d.tags LIKE '%Needs Review%'"` branch.
- **Problem:** No source_party filter. If a reviewer accidentally tags an inbound doc as Withhold/Redact (see Commit 4 review smell), it would appear in the generated privilege log exported to opposing counsel.
- **Fix:** Add `AND (d.source_party = 'Internal' OR d.source_party IS NULL)` to the WHERE clause after the base conditions group.
- **Severity:** High — court-destined output.

---

## 3. Defensibility Report (db_manager.py, **28 queries** — firmed 2026-04-16)

These functions feed `defensibility_report.py`, which generates court-destined PDFs (26(g) certifications, production summaries). Inbound docs in these counts would misrepresent the case universe.

**Per-function firm counts** (superseding the initial "~9" approximation in this audit's v1):

| Function | Line range | Queries hitting `documents` | Shape mix |
|---|---|---|---|
| `get_defensibility_overview` | 4179-4198 | 4 | 1 bare COUNT, 3 WHERE+AND |
| `get_defensibility_ingestion` | 4216-4247 | 5 | 4 GROUP BY (no WHERE), 1 bare SUM |
| `get_defensibility_processing` | 4264-4290 | 5 | 1 GROUP BY, 4 WHERE+AND |
| `get_defensibility_dedup` | 4307-4334 | **9** | 1 bare, 7 WHERE+AND, 1 WHERE with parenthesized OR block |
| `get_defensibility_review` | 4354-4386 | 5 | 3 WHERE with parenthesized OR blocks, 2 WHERE+AND |
| **Total** | — | **28** | — |

### 3.1 `get_defensibility_overview` — 4 queries at 4179-4198
- 4179: bare `SELECT COUNT(*) FROM documents` → prepend WHERE
- 4181: `WHERE custodian IS NOT NULL AND custodian != ''` → append AND
- 4184: `WHERE date_created IS NOT NULL` → append AND
- 4187: `WHERE date_created IS NOT NULL` → append AND
- Non-documents queries on lines 4190 (case_settings), 4194 (audit_log), 4197 (audit_log) are correctly out of scope.

### 3.2 `get_defensibility_ingestion` — 5 queries at 4216-4247
- 4216-4223: custodian_breakdown — GROUP BY, no WHERE → prepend WHERE before GROUP BY
- 4224-4231: file_types — GROUP BY, no WHERE → prepend WHERE
- 4232-4238: record_types — GROUP BY, no WHERE → prepend WHERE
- 4239-4245: source_collections — GROUP BY, no WHERE → prepend WHERE
- 4247: total_size `SELECT SUM(file_size_kb) FROM documents` bare → prepend WHERE

### 3.3 `get_defensibility_processing` — 5 queries at 4264-4290
- 4264-4269: status_breakdown — GROUP BY, no WHERE → prepend WHERE before GROUP BY
- 4270-4277: extraction_methods — existing WHERE (processing_status IN (...)) → append AND
- 4278-4284: error_docs — existing WHERE (processing_status LIKE '%Error%') → append AND
- 4286: encrypted_count — existing WHERE (is_encrypted = 1) → append AND
- 4289: ocr_count — existing WHERE (extraction_method = 'tesseract_ocr') → append AND

### 3.4 `get_defensibility_dedup` — **9 queries** at 4307-4334 (firmed from "~2-3")
- 4307: total_ingested bare → prepend WHERE
- 4309: exact_dupes — existing WHERE (processing_status='Duplicate (MD5)') → append AND
- 4312: content_dupes — existing WHERE → append AND
- 4315: processed — existing WHERE (processing_status IN ('Processed','Master')) → append AND
- 4318: nd_suppressed — existing WHERE (tags LIKE '%NearDupe-Suppressed%') → append AND
- 4321: nd_principals — existing WHERE → append AND
- 4324: thread_suppressed — existing WHERE → append AND
- 4327: thread_inclusive — existing WHERE → append AND
- 4329-4334: net_reviewable — **existing WHERE with parenthesized OR conditions** → append `AND {_outbound}` at end. Verified visually: existing ORs are wrapped in `(...)` so operator precedence holds.

### 3.5 `get_defensibility_review` — 5 queries at 4354-4386
- 4354-4359: total_reviewable — **WHERE with parenthesized OR blocks** → append AND
- 4360-4366: reviewable_tags — **WHERE with parenthesized OR blocks** → append AND
- 4367-4369: all_tags_raw — existing WHERE (tags IS NOT NULL AND tags != '') → append AND
- 4382: responsive — existing WHERE (tags LIKE/NOT LIKE) → append AND
- 4385: not_responsive — existing WHERE → append AND
- reviewer_activity at 4370-4380 queries audit_log, correctly out of scope.

### Already compliant in defensibility_report surfaces:
- **db_manager.py:4410** — `get_defensibility_production` already has `AND source_party = 'Internal'` (strict, no NULL tolerance). **Deliberate asymmetry** per reviewer decision 2026-04-16: productions are definitionally outbound, so a NULL source_party there indicates a data integrity issue rather than a legacy-migration condition. Documented with an inline comment in Commit 3; intentionally not changed to the `OR IS NULL` form.

---

## 4. Already Compliant Queries (for completeness; no action)

| File | Line | Current filter |
|---|---|---|
| `pages/3_Analytics.py` | 181 | `AND (d.source_party = 'Internal' OR d.source_party IS NULL)` — threading |
| `pages/3_Analytics.py` | 314 | `source_party.keyword == 'Internal'` filter in OpenSearch near-dupe |
| `pages/7_Custodians.py` | 370, 413, 422 | `WHERE ... AND (source_party = 'Internal' OR source_party IS NULL)` |
| `pages/1_Ingestor.py` | 497, 528 | Excludes inbound from custodian-assignment backfill |
| `db_manager.py` | 3948 | Email-related filter already has source_party |
| `db_manager.py` | 3968 | Date-range filter already has source_party |
| `db_manager.py` | 4365 | Defensibility production query filter |
| `processing_engine.py` | 1382 | Email imaging/OCR correctly filters internal-only |

---

## 5. Queries Correctly NOT Covered (inbound inclusion is right)

| File | Area | Reason |
|---|---|---|
| `pages/4_Review.py` | Grid rendering | Reviewers need to see inbound docs for analysis |
| `pages/3_Analytics.py` | Some grid/UI queries | Analysts may want cross-directory views |
| `pages/1_Ingestor.py` | Ingestion tracking | Inbound is ingestion source |

---

## 6. Ambiguous — In-Memory Structures

`pages/5_Production.py:1033, 1164, 1248` — `withhold_log_entries`, `redaction_log_data` are Python lists populated during the Pass 2 loop iterating over the already-filtered `df` (base_df post-Commit 3). As long as `base_df` is correctly filtered, these derived structures inherit the filter. **No direct query fix needed; confirms after 1.2 lands.**

---

## 6b. M-4 Exemption Annotation Check (per reviewer request 2026-04-16)

Reviewer directive: grep for `# exempt:` annotations in `db_manager.py` lines 4134-4305 (the defensibility_report function block) and confirm that any exemption rationale survives the filter addition.

**Result: zero exemption annotations in `db_manager.py:4134-4305`.**

Full grep on `db_manager.py`: no matches for `exempt` (case-insensitive). All M-4 exemption annotations live in page files (`home.py`, `pages/5_Production.py`, `processing_engine.py`, etc.), not in `db_manager.py`. The defensibility_report functions in that range were canonicalized in M-4 Batch 7 without exemptions.

**Implication:** No exemption annotations need updating or removing in Commit 3's db_manager.py edits. The 9 defensibility-function fixes are clean WHERE-clause additions to queries that have no prior exemption rationale to reconcile.

Exemption annotation found at `pages/5_Production.py:1314` (text-extraction query, covered in §1.6) predates this sprint and its rationale ("production loop") is orthogonal to the source_party filter — adding the filter does not invalidate the exemption. No update needed there either.

## 7. Methodology

- **Primary search:** `grep "FROM documents"` across all `.py` in project root + `pages/`. Inspected all ~60 hits.
- **Secondary search:** `grep "source_party"` to identify existing filters.
- **Context classification:** for each hit, read surrounding ±20 lines to determine outbound vs. review/analytics/ingestor context.
- **Spot-check verification:** grep confirmed db_manager.py:3894 (privilege log), 3948 + 3968 (compliant), 4134+ (defensibility-report block missing filters).
- **Excluded from audit:** non-documents-table queries, queries reading from `case_settings`, `audit_log`, `review_batches`, `redaction_marks`, `document_productions` — those are either analytic scope (include inbound correctly) or internal state (no inbound docs involved).

---

## 8. Recommended Implementation Order for Commit 3

1. **Delete `exclude_external` checkbox** at pages/5_Production.py:348 + help text + all conditional `if exclude_external:` branches (should be 1-3 sites).
2. **Define a single constant** at module top: `_MANDATORY_INBOUND_EXCLUSION_SQL = "(source_party = 'Internal' OR source_party IS NULL)"`. Reuse everywhere below.
3. **Hoist into grid_sql** (line ~362), `base_df` query (line 2558), `cns` branch (line 2555), `family_sql` (line 2599), privilege log `_pl_query` (line 3894).
4. **db_manager.py fixes** — add the filter to the 9 defensibility functions (lines 4134-4245+).
5. **Tests** — `tests/test_bates.py` `TestProductionInboundExclusion` covers every outbound query path with a seeded inbound doc + assertion that it never appears. Plus an integration test for `db_manager.get_defensibility_overview()` with an inbound doc that should not be counted.
6. **Verify empty-state paths** — on a case with only inbound docs and no custodial, the outbound queries return zero rows (not an error). Sanity-test.

## 9. Changes from Original Sprint Plan

| Plan assumed | Audit confirmed | Delta |
|---|---|---|
| 4 outbound queries | 13 outbound queries | +9 |
| All in pages/5_Production.py | 4 in 5_Production.py + 9 in db_manager.py | More files touched |
| Tests: TestProductionInboundExclusion | Same + defensibility function coverage | More tests |

**Recommendation:** Proceed with expanded scope. All 13 queries share the same root cause (filter missing or gated on exclude_external), the same fix (unconditional clause), and the same defensibility rationale. Bundling into Commit 3 is cheaper than a follow-up commit.

---

## 10. Approval Checkpoint

**Before any source edits in Commit 3, the maintainer must approve:**

- [ ] The audit is complete — no outbound query was missed.
- [ ] The expanded scope (13 queries vs. planned 4) is accepted.
- [ ] The privilege log fix lands in this commit (not deferred).
- [ ] The 9 defensibility_report.py fixes land in this commit (not deferred).
- [ ] Tests will cover every fixed query path.

Once approved, Commit 3 proceeds. If any item is deferred to a later sprint, note it here and in the plan file.
