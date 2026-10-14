# Holistic Audit Remediation Plan

**Audit Date:** 2026-03-27
**Passes Completed:** 3 (RBAC & Security), 4 (SQL & Data Integrity), 5 (Config & Deployment), 6 (Session State), 7 (Audit Trail), 8 (UI/UX Consistency), 9 (Synthesis)
**Total Findings:** 32 (7 critical, 11 high, 10 medium, 4 low)

---

## TIER 1: Critical (Data integrity / security at risk)

### C-1: auth_manager.py — Ungated admin functions — RESOLVED (2026-03-31)
**Pass:** 3 | **Severity:** HIGH (page-level gates prevent exploitation in current architecture)
**Issue:** Admin functions have no caller permission checks. Any authenticated user can call them.
**Resolution:** All admin functions now have `_require_admin()` guards: `update_role()`, `update_password()`, `delete_user()`, `update_allowed_cases()`, `update_doc_visibility()`, `save_role_permissions()`, `create_custom_role()`, `delete_custom_role()`. The centralized `_require_admin()` checks `has_permission('user_admin')`.

### C-2: auth_manager.py — Wildcard escalation in custom roles — RESOLVED (2026-03-31)
**Pass:** 3 | **Severity:** HIGH (page-level gates prevent exploitation in current architecture)
**Issue:** `save_role_permissions()` and `create_custom_role()` allow adding `'*'` wildcard to non-admin roles. No validation. Custom role inheritance allows inheriting from 'admin'.
**Resolution:** All protections implemented:
- `*` wildcard blocked in `save_role_permissions()` and `create_custom_role()` (raises ValueError)
- All permissions validated against `ALL_PERMISSIONS` (raises ValueError on unknown)
- Admin inheritance blocked in `_get_role_permissions()` (returns only additional perms)
- Multi-hop cycle detection via `_visited` set parameter
- `_require_admin()` caller checks added to all role management functions

### C-3: 8_Exhibits.py — Wrong session state key for case_folder — RESOLVED (pre-existing)
**Pass:** 6 | **Severity:** CRITICAL
**Issue:** Reading wrong session state key for case_folder.
**Resolution:** Already uses `st.session_state.get("current_case_folder")` — fixed in prior sprint.

### C-4: 8_Exhibits.py — Broken closed-case check — RESOLVED (pre-existing)
**Pass:** 6 | **Severity:** CRITICAL
**Issue:** Using session state for case status instead of db_manager.
**Resolution:** Already uses `db_manager.get_case_status(case_folder) == 'Closed'` — fixed in prior sprint.

### C-5: home.py — No case-specific state cleanup on case switch — RESOLVED (pre-existing)
**Pass:** 6 | **Severity:** CRITICAL
**Issue:** Stale session state persists when switching cases.
**Resolution:** `_clear_case_state()` function defined with comprehensive `_CASE_SPECIFIC_KEYS` list, called in all 4 case-switch paths (dropdown, custom path, create folder, open button) — fixed in prior sprint.

### C-6: 5_Production.py — SQL injection via date string interpolation — RESOLVED (pre-existing)
**Pass:** 4 | **Severity:** CRITICAL
**Issue:** f-string date interpolation in SQL query.
**Resolution:** All date queries use parameterized `?` placeholders with `params` list — fixed in prior sprint.

### C-7: 3_Analytics.py — Missing conn.commit() (FALSE POSITIVE)
**Pass:** 4 | **Severity:** N/A
**Issue:** Flagged as missing commit, but `conn.commit()` IS present on the next line. No fix needed.

---

## TIER 2: High (Should fix soon)

### H-1: Case-closed gate inconsistency — RESOLVED (2026-03-31)
**Pass:** 3 | **Files:** `3_Analytics.py`, `4_Review.py`, `7_Custodians.py`
**Issue:** These pages only warn about closed cases, don't `st.stop()`. Writes can proceed.
**Resolution:** Audited all write operations across all three files. All writes are gated behind `_case_closed` checks (button disabled or conditional block). The warn-only pattern is intentional — these modules allow read-only access on closed cases per CLAUDE.md. Fixed 2 minor gaps in 4_Review.py (saved search share/delete buttons).

### H-2: 7_Custodians.py — Missing permission checks on write operations — RESOLVED (2026-03-31)
**Pass:** 3 | **Files:** `pages/7_Custodians.py`
**Issue:** Rename, merge, reassign, hold status — all lack `has_permission()` checks. Rely only on page-level `require_permission('custodian_management')`.
**Resolution:** Added inline `has_permission('custodian_management')` defense-in-depth checks at profile save, hold status save, hold document upload, and hold document delete operations.

### H-3: 3_Analytics.py — Bulk tag operations lack write permission checks — RESOLVED (2026-03-31)
**Pass:** 3 | **Files:** `pages/3_Analytics.py`
**Issue:** Any user with 'analytics' permission can run threading/near-dupe and modify all document tags.
**Resolution:** Added `has_permission('tag')` gate at both EXECUTE buttons (threading and near-dupe). Users without tag permission can still run analysis and see results, but cannot apply tags.

### H-4: auth_manager.py — Session fixation risk — RESOLVED (2026-03-31)
**Pass:** 3 | **Files:** `auth_manager.py`
**Issue:** Session state not cleared on login. Pre-existing session variables persist.
**Resolution:** Login already cleared all keys (implemented in prior sprint). Fixed logout to use `st.session_state.clear()` instead of popping 4 specific keys — ensures no stale state persists across sessions.

### H-5: auth_manager.py — Custom role inherits from admin — RESOLVED (2026-03-31)
**Pass:** 3 | **Files:** `auth_manager.py`
**Issue:** No block on inheriting from 'admin'. No cycle detection.
**Resolution:** Admin inheritance blocking and wildcard validation were already implemented. Added multi-hop cycle detection via `_visited` set parameter in `_get_role_permissions()` — catches A→B→A chains, not just A→A.

### H-6: auth_manager.py — Auth config file permissions — RESOLVED (pre-existing)
**Pass:** 3 | **Files:** `auth_manager.py`
**Issue:** YAML saved with default OS permissions (world-readable). Contains password hashes.
**Resolution:** Already implemented in `_save_config()` — applies `os.chmod(0o600)` on Unix, `icacls` on Windows after every write.

### H-7: 6_Sync.py — 12 unlogged write operations — RESOLVED (2026-03-31)
**Pass:** 7 | **Files:** `pages/6_Sync.py`
**Issue:** Sync error status updates, config changes, tag/redaction updates from external system not audit-logged.
**Resolution:** 19 of 22 write operations already had audit logging. Added `SYNC_REDACTION_IMPORTED` after annotation extraction writes and `SYNC_REDACTION_OVERRIDE` after reconciliation overrides. BYOS pull redaction_status updates are covered by the batch-level `BYOS_PULL` audit entry.

### H-8: 4_Review.py — upsert_document_coding() not audit-logged — RESOLVED (pre-existing)
**Pass:** 7 | **Files:** `pages/4_Review.py`
**Issue:** Custom coding field values (potentially discovery-critical) saved without audit trail.
**Resolution:** Already implemented — `CODING_VALUE_CHANGED` audit entry is logged after each `upsert_document_coding()` call.

### H-9: db_manager.py — Audit vocabulary docstring incomplete — RESOLVED (2026-03-31)
**Pass:** 7 | **Files:** `db_manager.py`
**Issue:** ~15 action types used in code but not listed in the vocabulary docstring.
**Resolution:** Updated docstring to include all current action types including Split/Trim actions and new Sync actions (`SYNC_REDACTION_IMPORTED`, `SYNC_REDACTION_OVERRIDE`).

### H-10: DEPLOYMENT_GUIDE.md — Python version contradiction — RESOLVED (pre-existing)
**Pass:** 5 | **Files:** `DEPLOYMENT_GUIDE.md`
**Issue:** Line 84 says Python 3.12, line 110 says 3.11.
**Resolution:** All 8 Python version references already specify 3.11. No contradiction exists in current file.

### H-11: Multiple files — Bare except handlers — RESOLVED (pre-existing)
**Pass:** 8 | **Files:** `1_Ingestor.py:71`, `2_Processor.py:218,283,963`, `4_Review.py:3427`
**Issue:** 5 bare `except:` handlers silently swallow errors without logging.
**Resolution:** All flagged locations now use `except Exception:` or specific exception types. Resolved during Phase 20 Module Hardening sprints.

---

## TIER 3: Medium (Improve)

### M-1: auth_manager.py — No login rate limiting
**Pass:** 3 | Track failed attempts, lock after N failures.

### M-2: auth_manager.py — Legacy SHA-256 hashes
**Pass:** 3 | Consider force-reset for remaining SHA-256 users or remove legacy path.

### M-3: auth_manager.py — Session timeout ineffective
**Pass:** 3 | Timeout resets on every page load. Should track actual user interaction, not page reruns.

### M-4: ~145 SQL statements in page files
**Pass:** 4 | Long-term: migrate to db_manager.py helper functions. Not urgent but violates stated architecture.

### M-5: Race condition — case status not re-checked before writes
**Pass:** 6 | All pages check case status at load, not before individual write operations.

### M-6: Several unlogged write operations
**Pass:** 7 | `3_Analytics.py` tag cleanup, `7_Custodians.py` collection assignments, exhibit update/remove operations.

### M-7: 9 widgets missing key= parameters
**Pass:** 8 | `1_Ingestor.py`, `2_Processor.py`, `3_Analytics.py`, `4_Review.py`, `5_Production.py`.

### M-8: 12 disabled widgets with no explanatory message
**Pass:** 8 | `7_Custodians.py` — users see greyed-out inputs with no reason.

### M-9: Empty state messages missing
**Pass:** 8 | Analytics, Review, Production — zero-result scenarios show blank UI.

### M-10: COM mutex timeout hardcoded
**Pass:** 5 | Should be in config.example.py. Default 300000ms (5 min).

---

## TIER 4: Low (Nice to have)

### L-1: Password complexity only checks length >= 6
### L-2: Progress bar granularity could be improved
### L-3: Inconsistent widget key naming convention
### L-4: Filevine API URLs hardcoded

---

## REMEDIATION PHASES

**Phase A (Critical — do now):** Items C-1 through C-7
**Phase B (High — next sprint):** Items H-1 through H-11
**Phase C (Medium — backlog):** Items M-1 through M-10
**Phase D (Low — as encountered):** Items L-1 through L-4
