# M-4: SQL Migration — Refined Execution Plan

## Context

Audit finding M-4: ~261 raw `.execute()` calls + ~25 `pd.read_sql` calls scattered across 9 page files violate the architecture rule "Direct SQL in page files is a smell — queries should be in db_manager.py." This migration centralizes data access, deduplicates queries (some COUNT patterns appear 5+ times), and catches real bugs (8_Exhibits.py wrong column name).

**Source plan:** `.claude/plans/M4_SQL_MIGRATION_PLAN.md` (original spec, still valid as reference)
**This file:** Refined execution plan with verified line numbers, overlap fixes, and PM-approved scope decisions.

## Scope Decisions (PM-approved)

- **defensibility_report.py (49 calls):** Deferred to Batch 9 post-M-4 addendum. Not in core execution.
- **8_Exhibits.py `key` vs `setting_key` bug:** Fixed inline during Batch 2. Noted in CHANGELOG as bugfix.

## Key Verification Findings

1. **Line numbers verified exact** — no drift since plan was drafted
2. **db_manager.py confirmed:** 68 functions, 2,021 lines, version 1.15.0
3. **2 duplicate functions removed:** Plan proposed `get_review_batches_with_stats()` and `get_custodian_detail()` — both already exist as `get_all_batches()` (line 1810) and `get_custodian()` (line 1225). Swap call sites only.
4. **4_Review.py touches consolidated:** 4 → 2 batches (reduces regression risk in the 4,775-line file)
5. **Shared connection patterns:** Page-level `conn = get_connection()` in 7_Custodians.py and 4_Review.py batch section get eliminated. Simple reads → individual db_manager calls. Multi-table writes → atomic db_manager functions with internal connection.

## Critical Files

| File | Path | Batches |
|------|------|---------|
| db_manager.py | `C:\Projects\ediscovery\db_manager.py` | 1-7 (all) |
| home.py | `C:\Projects\ediscovery\home.py` | 1 |
| 2_Processor.py | `C:\Projects\ediscovery\pages\2_Processor.py` | 1, 7 |
| 3_Analytics.py | `C:\Projects\ediscovery\pages\3_Analytics.py` | 1, 5 |
| 4_Review.py | `C:\Projects\ediscovery\pages\4_Review.py` | 2, 3 |
| 5_Production.py | `C:\Projects\ediscovery\pages\5_Production.py` | 6 |
| 6_Sync.py | `C:\Projects\ediscovery\pages\6_Sync.py` | 1, 7 |
| 7_Custodians.py | `C:\Projects\ediscovery\pages\7_Custodians.py` | 4 |
| 8_Exhibits.py | `C:\Projects\ediscovery\pages\8_Exhibits.py` | 2 |

---

## Batch 1: Status Count Consolidation (LOW RISK)

**Files:** db_manager.py, home.py, 2_Processor.py, 3_Analytics.py, 6_Sync.py
**~50 duplicate COUNT queries → 7 NEW functions**

| New Function | Replaces | Returns |
|---|---|---|
| `get_document_status_counts(case_folder)` | home.py:303-308, 2_Processor.py:1516-1522, 3_Analytics.py:684-692 | dict: total, new, processed, duplicate, error, produced, nist_excluded, encrypted, partial, container_scanned, ready |
| `get_review_tag_counts(case_folder)` | home.py:311-327 | dict: all_tagged, responsive, not_responsive, needs_review, suppressed, privileged, threading_done, nd_done |
| `get_processing_queue_stats(case_folder)` | 2_Processor.py:1516-1523 (subset) | dict: queue_count, new_count, resumed_count, container_count |
| `get_file_type_breakdown(case_folder)` | 2_Processor.py:1526-1534 | list[dict]: extension, count |
| `get_data_reduction_stats(case_folder)` | 3_Analytics.py:684-698 | dict: all _dr_* counts |
| `get_sync_status_counts(case_folder)` | 6_Sync.py:568-571 | dict: total_valid, synced, pending, error |
| `get_byos_status_counts(case_folder)` | 6_Sync.py:667-678 | dict: total_pushable, already_pushed, pulled, redactions |

**Implementation notes:**
- Each function opens/closes its own connection (standard db_manager pattern)
- `get_document_status_counts` is the big dedup win — same COUNT queries appear in 3 files
- `get_data_reduction_stats` consolidates 10 separate COUNT queries into 1 function with 1 connection
- Add section header: `# ===== STATUS & COUNT QUERIES =====`

**Verification:** Run home.py dashboard, 2_Processor.py stats panel, 3_Analytics.py data reduction chart, 6_Sync.py status display. Compare numbers against direct SQL baseline.

**Commit:** `refactor: M-4 batch 1 — status count consolidation (7 functions, ~50 calls migrated)`

---

## Batch 2: Saved Searches + Bates Lookup + 8_Exhibits (LOW RISK)

**Files:** db_manager.py, 4_Review.py, 8_Exhibits.py
**Consolidates original batches 2 and 8 (Review portion) — all low-risk, self-contained sections**

| New Function | Replaces | Notes |
|---|---|---|
| `log_recent_search(case_folder, username, query)` | 4_Review.py:1241-1261 | Includes rotation logic (keep 10) |
| `get_named_searches(case_folder, username)` | 4_Review.py:1263-1271 | Visible saved + global |
| `get_recent_searches(case_folder, username)` | 4_Review.py:1273-1281 | Last 10 recent |
| `delete_saved_search(case_folder, search_id, username)` | 4_Review.py:1283-1286 | Owner-only delete |
| `toggle_search_global(case_folder, search_id, username, is_global)` | 4_Review.py:1288-1295 | Toggle visibility |
| `save_named_search(case_folder, username, search_name, query, col_filters_json, is_global)` | 4_Review.py:1417 | Named save insert |
| `clear_recent_searches(case_folder, username)` | 4_Review.py:1489 | Delete all recent for user |
| `lookup_bates_to_control(case_folder, bates_number)` | 4_Review.py:1900 | Returns control_number or None |
| `get_all_bates_ranges(case_folder)` | 4_Review.py:1946 | Returns list[dict] for DataFrame |
| `get_case_setting(case_folder, key)` | 8_Exhibits.py:87 | **BUGFIX:** uses correct column `setting_key`/`setting_value` |

**8_Exhibits.py line 88 bugfix:** The query `WHERE key = 'case_caption'` silently fails because the column is `setting_key`. The new `get_case_setting()` function uses the correct column names. CHANGELOG must note this as `FIX:` entry.

**Section headers:** `# ===== SAVED SEARCHES =====`, `# ===== BATES LOOKUP =====`, `# ===== CASE SETTINGS =====`

**Verification:** Create/list/delete/toggle saved searches. Test recent search rotation (create 12, verify only 10 kept). Test Bates lookup. Verify 8_Exhibits.py case caption resolves correctly.

**Commit:** `refactor: M-4 batch 2 — saved searches, Bates lookup, 8_Exhibits bugfix (10 functions, ~14 calls migrated)`

---

## Batch 3: Document Viewer + Tags + Batch Management (MEDIUM RISK)

**Files:** db_manager.py, 4_Review.py
**Consolidates original batches 3 and 4 — coupled via tag-save → batch-status-update at line 4414**

| New Function | Replaces | Notes |
|---|---|---|
| `get_document(case_folder, control_number)` | 4_Review.py:3056 | Full document row as dict |
| `get_document_parent(case_folder, parent_id)` | 4_Review.py:3060 | Returns control_number or None |
| `get_document_children(case_folder, parent_cn)` | 4_Review.py:3064 | List of control_numbers |
| `get_document_tags(case_folder, control_number)` | 4_Review.py:3225, 2959, 2991 | Returns tags string |
| `update_document_tags(case_folder, control_number, new_tags)` | 4_Review.py:3233, 2965, 2996, 4342, 4584 | Pure write — caller handles tag normalization |
| `set_redaction_status(case_folder, control_number, status)` | 4_Review.py:4020, 4088 | NULL to clear |
| `mark_document_reviewed(case_folder, control_number, username)` | 4_Review.py:4345-4347 | Sets reviewed_by + reviewed_at |
| `get_unbatched_document_count(case_folder)` | 4_Review.py:931-938 | Complex WHERE clause |
| `get_unbatched_documents(case_folder)` | 4_Review.py:950-959 | Returns list for batch assignment |
| `create_review_batch(case_folder, batch_name, created_by, doc_count, page_count)` | 4_Review.py:992-995 | INSERT into review_batches |
| `assign_documents_to_batch(case_folder, batch_id, control_numbers)` | 4_Review.py executemany | Bulk INSERT into batch_documents |
| `recalculate_batch_counts(case_folder)` | 4_Review.py:1016 | UPDATE review_batches from subquery |
| `update_batch_assignment(case_folder, batch_id, assigned_to)` | 4_Review.py:1062 | Simple UPDATE |
| `reassign_batch_documents(case_folder, cns, new_batch_id)` | 4_Review.py:1088-1089 | Bulk UPDATE batch_documents |
| `delete_all_batches(case_folder)` | 4_Review.py:1104-1105 | DELETE from both tables |
| `get_batch_remaining_count(case_folder, batch_id)` | 4_Review.py:4417 | COUNT unreviewed in batch |

**Existing function reuse:** `get_all_batches()` (db_manager.py:1810) — swap call site at 4_Review.py:1034, remove duplicate SQL.

**Key constraint:** `_batch_conn` shared connection (line 928) gets eliminated. Each batch operation becomes an independent db_manager call. The `_create_batches()` helper in 4_Review.py keeps its family-grouping logic but calls db_manager for all SQL.

**Section headers:** `# ===== DOCUMENT ACCESS =====`, `# ===== DOCUMENT TAGS =====`, `# ===== REVIEW BATCH MANAGEMENT =====`

**Verification:** Tag a document → verify persistence. Remove tags → verify cleared. Family cascade test. Redaction mark → tag sync. Create batches with family grouping. Verify doc counts per batch. Reassign, delete all. Batch auto-close on last doc reviewed (line 4414 flow).

**Commit:** `refactor: M-4 batch 3 — document viewer, tags, batch management (16 new + 1 reuse, ~35 calls migrated)`

---

## Batch 4: Custodian Operations (MEDIUM-HIGH RISK)

**Files:** db_manager.py, 7_Custodians.py
**Eliminates page-level shared connection (line 75)**

| New Function | Replaces | Notes |
|---|---|---|
| `get_custodian_doc_stats(case_folder, name)` | 7_Custodians.py:149-159 | doc_count, email_count, date_range |
| `update_custodian_fields(case_folder, name, **fields)` | 7_Custodians.py:180-184 | Whitelisted kwargs: title, department, email, notes, data_sources |
| `rename_custodian(case_folder, old_name, new_name)` | 7_Custodians.py:222-236 | **ATOMIC** — 3 table UPDATEs, single conn, single commit |
| `merge_custodians(case_folder, source, target)` | 7_Custodians.py:266-291 | **ATOMIC** — 3 UPDATEs + DELETE, single conn, single commit |
| `get_custodian_inventory_df_data(case_folder)` | 7_Custodians.py:77 (pd.read_sql) | Returns list[dict], caller wraps in DataFrame |
| `get_custodian_source_stats(case_folder, name)` | 7_Custodians.py:266-270 | Source-type breakdown |

**Existing function reuse:** `get_custodian()` (db_manager.py:1225) — swap call site at 7_Custodians.py:127.

**CRITICAL — Atomicity:** `rename_custodian` and `merge_custodians` must use a SINGLE connection with a SINGLE commit after all table UPDATEs. Pattern:
```python
def rename_custodian(case_folder, old_name, new_name):
    conn = get_connection(case_folder)
    try:
        conn.execute("UPDATE documents SET custodian=? WHERE custodian=?", (new_name, old_name))
        conn.execute("UPDATE custodians SET name=? WHERE name=?", (new_name, old_name))
        conn.execute("UPDATE hold_documents SET custodian_name=? WHERE custodian_name=?", (new_name, old_name))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

**Section header:** Extend existing `# CUSTODIAN MANAGEMENT` section (line 1212)

**Verification:** Rename custodian → verify documents table updated. Merge two custodians → verify source deleted, target has all docs. Rename to existing name → verify clean failure. Check hold documents follow custodian rename.

**Commit:** `refactor: M-4 batch 4 — custodian operations (6 new + 1 reuse, ~30 calls migrated)`

---

## Batch 5: Analytics Report Queries (MEDIUM RISK)

**Files:** db_manager.py, 3_Analytics.py
**All pd.read_sql patterns — return list[dict], caller wraps in DataFrame**

| New Function | Replaces |
|---|---|
| `get_exact_dupe_clusters(case_folder)` | 3_Analytics.py:700 |
| `get_near_dupe_cluster_detail(case_folder)` | 3_Analytics.py:714 |
| `get_all_exact_dupes_detail(case_folder)` | 3_Analytics.py:728 |
| `get_content_dupe_clusters(case_folder)` | 3_Analytics.py:740 |
| `get_custodian_activity_data(case_folder)` | 3_Analytics.py:929 |
| `get_timeline_data(case_folder)` | 3_Analytics.py:1051 |

**Section header:** `# ===== ANALYTICS QUERIES =====`

**Verification:** Check all analytics charts render same data. Compare cluster counts against direct SQL baseline.

**Commit:** `refactor: M-4 batch 5 — analytics report queries (6 functions, ~12 calls migrated)`

---

## Batch 6: Production Record Management (HIGH RISK)

**Files:** db_manager.py, 5_Production.py

| New Function | Replaces | Risk |
|---|---|---|
| `insert_production_records(case_folder, records, cache_updates)` | 5_Production.py:1331-1343 | **HIGH** — Bates integrity |
| `delete_production_volume(case_folder, volume_name)` | 5_Production.py:1859-1884, 2218-2227 | **HIGH** — multi-table rollback |
| `get_production_gap_report(case_folder, volume_name)` | 5_Production.py:2732 | Low |

**CRITICAL — Bates integrity:** `insert_production_records` must atomically write to `document_productions` AND update cache columns on `documents`. `delete_production_volume` must atomically remove records, clear cache, and rebuild cache from remaining productions via existing `refresh_production_cache()` (db_manager.py:1555).

**Section header:** Extend existing `# PRODUCTION JUNCTION TABLE` section (line 1552)

**Verification:** Run a test production → verify Bates assigned. Delete it → verify Bates cleared. Run two productions, delete the first → verify second production's Bates remain in cache. Check gap report accuracy.

**Commit:** `refactor: M-4 batch 6 — production record management (3 functions, ~10 calls migrated)`

---

## Batch 7: Retry Operations + Misc Utilities (LOW RISK)

**Files:** db_manager.py, 2_Processor.py, 6_Sync.py

| New Function | Replaces |
|---|---|
| `retry_processing_errors(case_folder)` | 2_Processor.py:1554 |
| `retry_sync_errors(case_folder)` | 6_Sync.py:614 |
| `get_sync_error_details(case_folder)` | 6_Sync.py:609 (pd.read_sql) |
| `save_case_settings_batch(case_folder, settings_dict)` | 6_Sync.py:552, 648-650, 977 |

**Section header:** `# ===== RETRY OPERATIONS =====`, `# ===== CASE SETTINGS =====`

**Verification:** Trigger error retry in Processor and Sync pages. Verify error docs reset to New/Pending. Verify case settings persist across page reloads.

**Commit:** `refactor: M-4 batch 7 — retry operations and case settings (4 functions, ~6 calls migrated)`

---

## Batch 8: Exempt Annotation Sweep (LOW RISK)

**No new functions.** This batch annotates all intentionally retained SQL with `# db_manager: exempt (reason)` comments.

**Exempt categories (~95 statements):**
- `# db_manager: exempt (processing loop)` — 2_Processor.py ~40 calls, per-document status updates in tight loops with shared connections
- `# db_manager: exempt (dynamic query)` — 4_Review.py main grid ~8 calls, 5_Production.py grid ~6 calls, SQL built programmatically from UI widget state
- `# db_manager: exempt (schema introspection)` — PRAGMA and sqlite_master queries
- `# db_manager: exempt (analytics bulk-update)` — 3_Analytics.py ~12 calls, threading/near-dupe tag manipulation in shared-connection bulk operations

**Verification:** `grep -n "\.execute(" pages/*.py home.py` should show ONLY exempt-annotated lines.

**Commit:** `refactor: M-4 batch 8 — exempt annotations on ~95 retained SQL statements`

---

## Batch 9: Defensibility Report (POST-M-4, DEFERRED)

**Status:** Not executed during M-4 core sprint. Picked up as fast follow-on after Batches 1-8 land and are verified.

**Files:** db_manager.py, defensibility_report.py
**49 read-only .execute() calls across 8 `_collect_*` functions → ~9 new db_manager functions**

All reads, no writes, no atomicity concerns. Report-specific queries unlikely to be reused by other modules — benefit is purely architectural consistency.

---

## Totals

| Metric | Count |
|---|---|
| Core batches | 7 functional + 1 annotation sweep |
| New db_manager functions | ~52 |
| Existing functions reused (call-site swap) | 3 (`get_all_batches`, `get_custodian`, `get_case_setting` if exists) |
| Calls migrated | ~157 (.execute) + ~25 (pd.read_sql) ≈ 182 |
| Calls annotated exempt | ~95 |
| 4_Review.py touches | 2 (batches 2, 3) |
| db_manager.py projected size | ~2,700 lines, ~120 functions |
| Bugs fixed | 1 (8_Exhibits.py setting_key) |

## Per-Batch Protocol

For EACH batch:
1. Add new functions to db_manager.py with section headers
2. Update page file(s) to call new functions, removing raw SQL
3. Update version headers on ALL touched files (bump patch or minor as appropriate)
4. Add CHANGELOG entries (use `FIX:` for the 8_Exhibits bugfix, `CHANGE:` for migrations)
5. Verify against running app before committing
6. Commit with message: `refactor: M-4 batch N — description`

## Post-Sprint

After all 8 batches:
1. Full app walkthrough: Home → Ingest → Process → Analytics → Review → Production → Sync → Custodians → Exhibits
2. Verify audit log entries still generated for all write operations
3. Final grep: `grep -n "\.execute(" pages/*.py home.py` — only exempt-annotated lines
4. Context maintenance (CLAUDE.md, docs, MEMORY.md)
5. Then optionally pick up deferred Batch 9
