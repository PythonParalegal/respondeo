# M-4: SQL Migration — Page Files to db_manager.py

## Context

Audit finding M-4 identifies ~295 raw SQL `execute` calls scattered across 9 page files. The architecture rule states: "Direct SQL in page files is a smell -- queries should be in db_manager.py." This migration centralizes data access behind a consistent API, eliminating duplication (some COUNT queries appear 5+ times across files), enforcing parameterized queries, and making future schema changes easier by having a single place to update SQL.

db_manager.py currently has 68 functions across 2,021 lines, organized by feature area with consistent patterns: `get_connection() -> try/finally -> close()`, parameterized queries, `log_audit()` after writes.

## Scope Decision: Migrate vs. Leave in Place

### MIGRATE (~200 execute calls -> ~48 new functions)
SQL that represents reusable data-access patterns, is duplicated across files, or constitutes standalone read/write operations.

### LEAVE IN PLACE (~95 execute calls)
SQL that is:
1. **Processing loop internals** (2_Processor.py ~40 calls, 6_Sync.py ~25 calls) -- per-document status updates inside tight loops with shared connections. Wrapping each in a function that opens/closes its own connection would break performance and transaction semantics.
2. **Dynamically constructed queries** (4_Review.py main grid ~8 calls, 5_Production.py grid ~6 calls) -- SQL strings built programmatically from UI widget state across 50+ lines. Moving just the final execute gains nothing.
3. **Schema introspection** (PRAGMA, sqlite_master) -- infrastructure queries, not data access.
4. **Analytics bulk-update loops** (3_Analytics.py ~12 calls) -- threading/near-dupe tag manipulation in shared-connection bulk operations.

Each exempt statement gets a `# db_manager: exempt (reason)` comment.

---

## Execution Plan: 8 Batches

### Batch 1: Status Count Consolidation (LOW RISK)
**Files:** `db_manager.py`, `home.py`, `2_Processor.py`, `3_Analytics.py`, `6_Sync.py`
**~50 duplicate COUNT queries -> 7 functions**

| New Function | Replaces | Returns |
|---|---|---|
| `get_document_status_counts(case_folder)` | home.py:303-308, 2_Processor.py:1516-1522, 3_Analytics.py:684-692 | `dict` with keys: total, new, processed, duplicate, error, produced, nist_excluded, encrypted, partial, container_scanned, ready |
| `get_review_tag_counts(case_folder)` | home.py:311-335 | `dict`: all_tagged, responsive, not_responsive, needs_review, suppressed, privileged, threading_done, nd_done |
| `get_processing_queue_stats(case_folder)` | 2_Processor.py:1516-1523 (subset) | `dict`: queue_count, new_count, resumed_count, container_count |
| `get_file_type_breakdown(case_folder)` | 2_Processor.py:1526-1534 | `list[dict]`: extension, count |
| `get_data_reduction_stats(case_folder)` | 3_Analytics.py:684-698 | `dict`: all _dr_* counts |
| `get_sync_status_counts(case_folder)` | 6_Sync.py:568-571 | `dict`: total_valid, synced, pending, error |
| `get_byos_status_counts(case_folder)` | 6_Sync.py:667-676 | `dict`: total_pushable, already_pushed, pulled, redactions |

**Verification:** Run app against test case, compare dashboard numbers before/after on each page.

---

### Batch 2: Saved Searches + 8_Exhibits.py cleanup (LOW RISK)
**Files:** `db_manager.py`, `4_Review.py` (saved search section only), `8_Exhibits.py`
**~12 calls -> 7 functions**

| New Function | Replaces | Notes |
|---|---|---|
| `log_recent_search(case_folder, username, query)` | 4_Review.py:1241-1261 (`_log_recent`) | Includes rotation logic (keep 10) |
| `get_named_searches(case_folder, username)` | 4_Review.py:1263-1271 (`_get_named_saves`) | Returns visible saved + global |
| `get_recent_searches(case_folder, username)` | 4_Review.py:1273-1281 (`_get_recent`) | Last 10 recent |
| `delete_saved_search(case_folder, search_id, username)` | 4_Review.py:1283-1286 | Owner-only delete |
| `toggle_search_global(case_folder, search_id, username, is_global)` | 4_Review.py:1288-1295 | Toggle visibility |
| `save_named_search(case_folder, username, search_name, query, col_filters_json, is_global)` | 4_Review.py:1417 | Named save insert |
| `clear_recent_searches(case_folder, username)` | 4_Review.py:1489 | Delete all recent for user |

8_Exhibits.py has only 2 SQL calls (lines 87, 464). Check if db_manager already covers them; if so, just swap the call site.

**Verification:** Create/list/delete/toggle saved searches through the UI. Verify recent search rotation.

---

### Batch 3: Document Viewer + Tag Operations (MEDIUM RISK)
**Files:** `db_manager.py`, `4_Review.py`
**~20 calls -> 7 functions**

| New Function | Replaces | Notes |
|---|---|---|
| `get_document(case_folder, control_number)` | 4_Review.py:3056 | Full document row as dict |
| `get_document_parent(case_folder, parent_id)` | 4_Review.py:3060 | Returns control_number or None |
| `get_document_children(case_folder, parent_cn)` | 4_Review.py:3064 | List of control_numbers |
| `get_document_tags(case_folder, control_number)` | 4_Review.py:3225, 2959, 2991 | Returns tags string |
| `update_document_tags(case_folder, control_number, new_tags)` | 4_Review.py:3233, 2965, 2996, 4342, 4584 | Simple UPDATE, caller handles normalization |
| `set_redaction_status(case_folder, control_number, status)` | 4_Review.py:4020, 4088 | NULL to clear |
| `mark_document_reviewed(case_folder, control_number, username)` | 4_Review.py:4345-4347 | Sets reviewed_by + reviewed_at |

**CRITICAL:** Tag normalization (`;` -> `,` split, strip, rejoin) stays in the caller. The db_manager functions are pure read/write; they do not interpret tag semantics.

**Verification:** Tag a document, verify tags persist. Remove tags, verify cleared. Check family cascade still works. Verify redaction mark -> tag sync in the redaction panel.

---

### Batch 4: Review Batch Management (MEDIUM RISK)
**Files:** `db_manager.py`, `4_Review.py`
**~15 calls -> 10 functions**

| New Function | Replaces |
|---|---|
| `get_unbatched_document_count(case_folder)` | 4_Review.py:931-938 |
| `get_unbatched_documents(case_folder)` | 4_Review.py:950-959 |
| `create_review_batch(case_folder, batch_name, created_by, doc_count, page_count)` | 4_Review.py:992-995 |
| `assign_documents_to_batch(case_folder, batch_id, control_numbers)` | 4_Review.py executemany pattern |
| `recalculate_batch_counts(case_folder)` | 4_Review.py:1016 |
| `get_review_batches_with_stats(case_folder)` | 4_Review.py:1034 |
| `update_batch_assignment(case_folder, batch_id, assigned_to)` | 4_Review.py:1062 |
| `reassign_batch_documents(case_folder, cns, new_batch_id)` | 4_Review.py:1088-1089 |
| `delete_all_batches(case_folder)` | 4_Review.py:1104-1105 |
| `get_batch_remaining_count(case_folder, batch_id)` | 4_Review.py:4417 |

**KEY CHANGE:** `_create_batches()` currently receives a connection object. After migration, it will call db_manager functions that manage their own connections. The family-grouping logic (OrderedDict bucketing) stays in the page file — only the SQL operations move.

**Verification:** Create batches with family grouping enabled. Verify doc counts per batch. Reassign, then delete all. Check batch status auto-close on last doc reviewed.

---

### Batch 5: Custodian Operations (MEDIUM-HIGH RISK)
**Files:** `db_manager.py`, `7_Custodians.py`
**~18 calls -> 7 functions**

| New Function | Replaces | Risk |
|---|---|---|
| `get_custodian_detail(case_folder, name)` | 7_Custodians.py:127 | Low |
| `get_custodian_doc_stats(case_folder, name)` | 7_Custodians.py:149-156 | Low |
| `update_custodian_fields(case_folder, name, **fields)` | 7_Custodians.py:180 | Low (whitelisted kwargs pattern) |
| `rename_custodian(case_folder, old_name, new_name)` | 7_Custodians.py:222-236 | **HIGH** — 3 tables |
| `merge_custodians(case_folder, source, target)` | 7_Custodians.py:266-291 | **HIGH** — 3 tables + delete |
| `get_custodian_inventory_df_data(case_folder)` | 7_Custodians.py:77 | Low (replaces pd.read_sql) |
| `get_custodian_source_stats(case_folder, name)` | 7_Custodians.py:266-270 | Low |

**CRITICAL:** `rename_custodian` and `merge_custodians` must be **atomic** — single connection, single commit after all 3 table UPDATEs. If any fails, none should persist. Current page code does this correctly with a shared connection; the db_manager version must preserve this.

**Verification:** Rename a custodian, verify documents table updated. Merge two custodians, verify source deleted and target has all docs. Test rollback by renaming to an existing name (should fail cleanly).

---

### Batch 6: Production Record Management (HIGH RISK)
**Files:** `db_manager.py`, `5_Production.py`
**~10 calls -> 3 functions**

| New Function | Replaces | Risk |
|---|---|---|
| `insert_production_records(case_folder, records, cache_updates)` | 5_Production.py:1331-1343 | **HIGH** — Bates integrity |
| `delete_production_volume(case_folder, volume_name)` | 5_Production.py:1859-1884, 2218-2227 | **HIGH** — multi-table rollback |
| `get_production_gap_report(case_folder, volume_name)` | 5_Production.py:2732 | Low |

**CRITICAL:** Bates numbers are court-record identifiers. The insert function must atomically write to `document_productions` AND update cache columns on `documents`. The delete function must atomically remove records, clear cache, and rebuild cache from remaining productions (using the existing `refresh_production_cache` pattern).

**Verification:** Run a test production, verify Bates assigned. Delete it, verify Bates cleared. Run two productions, delete the first, verify second production's Bates remain in cache.

---

### Batch 7: Retry Operations + Misc Utilities (LOW RISK)
**Files:** `db_manager.py`, `2_Processor.py`, `6_Sync.py`
**~6 calls -> 4 functions**

| New Function | Replaces |
|---|---|
| `retry_processing_errors(case_folder)` | 2_Processor.py:1554 |
| `retry_sync_errors(case_folder)` | 6_Sync.py:614 |
| `get_sync_error_details(case_folder)` | 6_Sync.py:609 (pd.read_sql) |
| `save_case_settings_batch(case_folder, settings_dict)` | 6_Sync.py:552, 648-650, 977 |

**Verification:** Trigger error retry in Processor and Sync pages. Verify error docs reset to New/Pending.

---

### Batch 8: Analytics Report Queries + Bates Lookup (MEDIUM RISK)
**Files:** `db_manager.py`, `3_Analytics.py`, `4_Review.py`
**~12 calls -> 8 functions**

| New Function | Replaces |
|---|---|
| `get_exact_dupe_clusters(case_folder)` | 3_Analytics.py:700 |
| `get_near_dupe_cluster_detail(case_folder)` | 3_Analytics.py:714 |
| `get_all_exact_dupes_detail(case_folder)` | 3_Analytics.py:728 |
| `get_content_dupe_clusters(case_folder)` | 3_Analytics.py:740 |
| `get_custodian_activity_data(case_folder)` | 3_Analytics.py:929 |
| `get_timeline_data(case_folder)` | 3_Analytics.py:1051 |
| `lookup_bates_to_control(case_folder, bates_number)` | 4_Review.py:1900 |
| `get_all_bates_ranges(case_folder)` | 4_Review.py:1946 |

**pd.read_sql pattern:** All return `list[dict]`. Callers wrap in `pd.DataFrame()`. db_manager.py does NOT import pandas.

**Verification:** Check analytics charts render same data. Test Bates lookup in Review page.

---

## Cross-Cutting Concerns

### pd.read_sql_query Handling
- New db_manager functions return `list[dict]` (consistent with existing pattern)
- Callers do `pd.DataFrame(db_manager.get_xxx(case_folder))`
- db_manager.py does NOT import pandas

### Connection Lifecycle
- Each new function opens/closes its own connection (standard db_manager pattern)
- For multi-table atomic operations (rename_custodian, production records), one connection with one commit
- SQLite WAL mode handles the increased connection churn fine

### db_manager.py Growth
- After all batches: ~2,600 lines, ~116 functions
- Add clear section headers (`# ===== SECTION: Name =====`) during migration
- Do NOT split into multiple modules in this sprint (import churn risk). Defer to future task if it exceeds 3,000 lines.

### Exempt Statement Annotation
Every SQL statement left in page files gets: `# db_manager: exempt (reason)`
Reasons: `processing loop`, `dynamic query`, `schema introspection`, `analytics bulk-update`

---

## Per-Batch Commit Protocol

For each batch:
1. Add new functions to db_manager.py with section headers
2. Update page file(s) to call new functions, removing raw SQL
3. Add `# db_manager: exempt` comments to intentionally retained SQL
4. Update version headers on ALL touched files (db_manager.py + page files)
5. Add CHANGELOG entries
6. Run the application against a test case to verify no regressions
7. Commit with message: `refactor: M-4 batch N — description`

## Files Modified (all batches combined)

| File | Batches | Approx Lines Changed |
|---|---|---|
| `db_manager.py` | 1-8 | +600 (new functions) |
| `home.py` | 1 | ~30 lines replaced |
| `pages/1_Ingestor.py` | 1 | ~10 lines replaced |
| `pages/2_Processor.py` | 1, 7 | ~40 lines replaced |
| `pages/3_Analytics.py` | 1, 8 | ~50 lines replaced |
| `pages/4_Review.py` | 2, 3, 4, 8 | ~150 lines replaced |
| `pages/5_Production.py` | 6 | ~40 lines replaced |
| `pages/6_Sync.py` | 1, 7 | ~30 lines replaced |
| `pages/7_Custodians.py` | 5 | ~80 lines replaced |
| `pages/8_Exhibits.py` | 2 | ~5 lines replaced |
| `CHANGELOG.md` | 1-8 | +8 entries |

## Verification Strategy

**Before starting:** Copy a test `case.db` as baseline reference.

**Per-batch:**
- Run the specific page(s) touched in that batch
- Compare dashboard counts, CRUD operations, and query results against baseline
- For write operations: verify database state matches expected

**After all batches:**
- Full app walkthrough: Ingest -> Process -> Analytics -> Review -> Production -> Sync -> Custodians -> Exhibits
- Verify audit log entries are still generated for all write operations
- Grep for any remaining unexempted raw SQL: `grep -n "\.execute(" pages/*.py home.py` should show only exempt-annotated lines
