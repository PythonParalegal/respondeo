# High-Tier Audit Remediation Sprint (H-1 through H-11)

**Date:** 2026-03-31
**Source:** `docs/HOLISTIC_AUDIT_REMEDIATION.md` — TIER 2 findings
**Branch:** `beta-2.8`
**Scope:** 11 findings, 2 already resolved, 9 to implement

---

## Pre-Sprint Notes

- **H-11 (bare except handlers) is RESOLVED.** All flagged locations now use `except Exception:` or specific exception types. No action needed. Mark as complete.
- **H-10 (DEPLOYMENT_GUIDE.md Python version)** is a docs-only fix. Quick one.
- **H-1 requires careful handling** — see detailed notes below.
- The audit line numbers are from 2026-03-27. Lines have shifted. Search by code pattern, not line number.

---

## Task 1: H-1 — Closed-Case Write Gate Audit

**Files:** `3_Analytics.py`, `4_Review.py`, `7_Custodians.py`

**IMPORTANT:** Do NOT add `st.stop()` to these files. The current pattern (warn + `_case_closed` boolean flag to disable writes) is CORRECT and INTENTIONAL. These modules must allow read-only access on closed cases per CLAUDE.md: "Closed cases must block ALL write operations; reads must stay open."

**What to do instead:** Audit every write operation in each file and verify it checks `_case_closed` before executing. A "write operation" is anything that calls `db_manager.*` to INSERT, UPDATE, or DELETE, or calls `log_audit()` for a user-initiated action, or modifies files on disk.

**3_Analytics.py — verify these write paths are gated:**
- Threading analysis — bulk tag writes (NearDupe, Thread tags)
- Near-dupe analysis — bulk tag writes
- Content dedup — bulk tag writes
- Junk image detection — bulk tag writes
- Any other bulk UPDATE/INSERT operations
- For each: verify the button or trigger is `disabled=_case_closed` or wrapped in `if not _case_closed:`

**4_Review.py — verify these write paths are gated:**
- Tag apply/remove/clear (single and bulk)
- Redaction mark save/clear
- Privilege disposition set
- Confidentiality designation set
- Mark as reviewed
- Document notes save
- Custom coding field save
- Saved search save/delete
- Split document
- Trim document
- Re-image document
- Batch assignment operations
- For each: verify the button is `disabled=_case_closed` or the operation is inside `if not _case_closed:`

**7_Custodians.py — verify these write paths are gated:**
- Custodian profile edit/save
- Custodian rename
- Custodian merge
- Custodian reassign
- Collection assignment
- Hold status change
- Hold document upload
- For each: verify the button/form is disabled or gated

**Output:** For each file, produce a table:

```
| Write Operation | Gated? | How |
|----------------|--------|-----|
| Tag apply      | Yes    | button disabled=_case_closed |
| ...            | ...    | ... |
```

If ANY write operation is ungated, fix it by adding the appropriate disable or conditional guard. Use the `# permission: <name>` annotation convention per CLAUDE.md.

---

## Task 2: H-2 — Custodian Write Permission Checks

**File:** `pages/7_Custodians.py`

The page-level gate (`require_permission('custodian_management')`) means only users with that permission can access the page at all. However, destructive operations should have inline permission checks as defense-in-depth.

**Add `has_permission()` checks for these operations:**

- **Rename custodian** — gate behind `has_permission('custodian_management')`. This is already the page gate, so this is defense-in-depth. Add the check at the operation level, not just page level.
- **Merge custodians** — same gate. Merge is destructive (deletes the source custodian record). Add explicit check.
- **Reassign documents** — same gate. Bulk UPDATE on documents table.
- **Delete custodian** — if this exists, gate it.

Pattern to follow:
```python
# permission: custodian_rename
if not auth_manager.has_permission('custodian_management'):
    st.error("Insufficient permissions.")
    st.stop()
```

Note: We're using the existing `custodian_management` permission for all of these rather than creating granular sub-permissions. The page gate already restricts access — these inline checks are a safety net against future refactoring that might change the page gate.

---

## Task 3: H-3 — Analytics Bulk Tag Permission Check

**File:** `pages/3_Analytics.py`

**Issue:** Threading, near-dupe, content dedup, and junk image operations modify document tags in bulk. These are gated behind `analytics` permission (page level), but they should also check `tag` permission since they write tags.

**Fix:** Before any bulk tag UPDATE operation in Analytics, add:
```python
# permission: bulk_tag_analytics
if not auth_manager.has_permission('tag'):
    st.error("You do not have permission to modify document tags.")
    st.stop()
```

This should gate the actual execution block, not the analysis itself. A user with `analytics` but not `tag` should be able to RUN the analysis and SEE results, but not APPLY the tags.

Specifically find and gate these operations:
- Thread suppression tag application
- Near-dupe tag application
- Content dedup tag application
- Junk image tag application
- Any "Apply Tags" or "Mark as..." buttons that write to the documents table

---

## Task 4: H-4 — Session Fixation Fix

**File:** `auth_manager.py`

**Issue:** When a user logs in, pre-existing session state variables from a prior session (or from someone who logged out) persist. This is a session fixation risk.

**Fix:** In the login success path (where `st.session_state['authenticated'] = True` is set), add `st.session_state.clear()` BEFORE setting the new authenticated session variables.

**IMPORTANT SEQUENCING:**
```python
# Clear all prior session state first
st.session_state.clear()
# THEN set new authenticated session
st.session_state['authenticated'] = True
st.session_state['username'] = username
st.session_state['role'] = role
# ... etc
```

If `clear()` is called AFTER setting the new values, it would wipe them. Order matters.

**Also check:** The logout flow — verify it also calls `st.session_state.clear()`. If logout only pops specific keys, stale state from a reviewer's session could persist into a manager's next login.

---

## Task 5: H-5 — Block Admin Inheritance + Cycle Detection

**File:** `auth_manager.py`

**Issue:** Custom roles can inherit from 'admin', which grants them the `*` wildcard (all permissions). There's also no cycle detection in the inheritance chain.

**Fix — two changes in `_get_role_permissions()`:**

1. **Block admin inheritance:**
```python
if role_def.get('inherits') == 'admin':
    logger.warning(f"Custom role attempted to inherit from admin — blocked")
    # Return only the role's explicit permissions, not admin's
    return set(role_def.get('permissions', []))
```

2. **Cycle detection with visited set:**
```python
def _get_role_permissions(role_name, _visited=None):
    if _visited is None:
        _visited = set()
    if role_name in _visited:
        logger.warning(f"Permission inheritance cycle detected: {role_name}")
        return set()
    _visited.add(role_name)
    # ... existing logic, passing _visited to recursive calls
```

**Also fix in `save_role_permissions()` and `create_custom_role()`:**
- Validate that `'*'` wildcard is not in the permissions set for non-admin roles
- Validate all permission names exist in `ALL_PERMISSIONS`
- Block setting `inherits` to `'admin'`

---

## Task 6: H-6 — Auth Config File Permissions

**File:** `auth_manager.py`

**Issue:** `auth_config.yaml` contains password hashes and is saved with default OS permissions.

**Fix:** After every `yaml.dump()` write to `AUTH_CONFIG_PATH`, restrict file permissions.

**Platform-aware implementation:**
```python
import sys
if sys.platform != 'win32':
    os.chmod(AUTH_CONFIG_PATH, 0o600)
# On Windows, file permissions are ACL-based and more complex.
# The file is in the project directory which is already user-restricted.
# Optionally: use icacls via subprocess, but this is low-priority on Windows
# since the deployment model is single-machine, single-user.
```

Add this after every call site that writes to the YAML file. Search for all locations where the auth config is saved (look for `yaml.dump` or `save_config` patterns in auth_manager.py).

---

## Task 7: H-7 — Sync Module Audit Logging

**File:** `pages/6_Sync.py`

**Issue:** 12 write operations in Sync lack audit trail entries. For a module that communicates with external systems (Filevine, BYOS), this is a defensibility gap.

**Find and add `log_audit()` for each of these operation types:**
1. Sync error status updates (when marking a doc as sync error or clearing error)
2. Sync config changes (endpoint URL, credentials, mapping changes)
3. Tag updates received from external system
4. Redaction mark updates received from external system
5. Document status changes from pull-back operations
6. BYOS push operations (which documents were pushed, when)
7. BYOS pull-back operations (which documents were pulled, what changed)
8. Reindex operations
9. Any other UPDATE/INSERT/DELETE operations

**Audit action naming convention:** Use `SYNC_` prefix for all sync audit events. Examples:
- `SYNC_CONFIG_CHANGED`
- `SYNC_ERROR_CLEARED`
- `SYNC_TAG_UPDATED`
- `SYNC_REDACTION_IMPORTED`
- `SYNC_PUSH_COMPLETED`
- `SYNC_PULLBACK_COMPLETED`
- `SYNC_REINDEX_STARTED`

Each `log_audit()` call should include the `username`, `module="Sync"`, and relevant `details` (JSON with operation-specific info like document count, which fields changed, etc.).

---

## Task 8: H-8 — Document Coding Audit Log

**File:** `pages/4_Review.py`

**Issue:** `upsert_document_coding()` saves custom coding field values without audit logging. These are potentially discovery-critical values (issue codes, relevance ratings, etc.).

**Fix:** After each successful `upsert_document_coding()` call, add:
```python
db_manager.log_audit(
    case_folder, "CODING_VALUE_CHANGED",
    username=st.session_state.get('username', 'unknown'),
    module="Review",
    control_number=control_number,
    details=json.dumps({"field": field_name, "old_value": old_value, "new_value": new_value})
)
```

To capture old_value, you'll need to read the current value before the upsert. If that's too expensive (multiple coding fields saved at once), at minimum log the new values:
```python
details=json.dumps({"field": field_name, "new_value": new_value})
```

---

## Task 9: H-9 — Audit Vocabulary Docstring Update

**File:** `db_manager.py`

**Issue:** The `log_audit()` docstring lists ~15 action types but the codebase uses ~30+.

**Fix:**
1. Grep the entire codebase for `log_audit(` calls
2. Extract every unique action string (the second positional argument)
3. Update the docstring in `log_audit()` to list ALL current action types, organized by module
4. Include the new `SYNC_*` actions from Task 7 and `CODING_VALUE_CHANGED` from Task 8

Format in the docstring:
```python
"""
...
Known action types (keep this list current):
    Home:       LOGIN, LOGOUT, CASE_CREATED, CASE_SETTING_CHANGED, ...
    Ingestor:   INGESTION_STARTED, INGESTION_COMPLETED, ...
    Processor:  PROCESSING_STARTED, PROCESSING_COMPLETED, PROCESSING_CANCELLED, ...
    Review:     TAG_APPLIED, TAG_REMOVED, REDACTION_SAVED, CODING_VALUE_CHANGED, ...
    Production: PRODUCTION_PASS1_COMPLETE, PRODUCTION_FINALIZED, ...
    Sync:       SYNC_CONFIG_CHANGED, SYNC_PUSH_COMPLETED, ...
    Custodians: CUSTODIAN_RENAMED, CUSTODIAN_MERGED, ...
    Analytics:  THREADING_COMPLETED, NEARDUPE_COMPLETED, ...
"""
```

---

## Task 10: H-10 — Deployment Guide Python Version

**File:** `DEPLOYMENT_GUIDE.md`

**Fix:** Find both references to Python version and align them to `3.11`. Search for "3.12" and "3.11" to find all occurrences. The correct version is **3.11** (matching the venv and the libpff wheel).

---

## Task 11: H-11 — Bare Except Handlers (ALREADY RESOLVED)

**Status:** No action needed. All flagged locations now use `except Exception:` or specific exception types. This was resolved during Phase 20 Module Hardening sprints.

Mark as RESOLVED in `docs/HOLISTIC_AUDIT_REMEDIATION.md`.

---

## Completion Checklist

After all tasks are done:

```
[ ] H-1:  Closed-case write gate audit table produced for 3_Analytics, 4_Review, 7_Custodians
[ ] H-1:  Any ungated writes fixed
[ ] H-2:  Inline permission checks on custodian destructive operations
[ ] H-3:  Tag permission check before Analytics bulk tag operations
[ ] H-4:  st.session_state.clear() on login and logout
[ ] H-5:  Admin inheritance blocked + cycle detection in _get_role_permissions
[ ] H-5:  Wildcard and admin-inherit validation in save_role_permissions/create_custom_role
[ ] H-6:  File permission restriction after auth config writes (non-Windows)
[ ] H-7:  All 12 Sync write operations audit-logged
[ ] H-8:  Document coding upsert audit-logged
[ ] H-9:  Audit vocabulary docstring updated with all current action types
[ ] H-10: DEPLOYMENT_GUIDE.md Python version aligned to 3.11
[ ] H-11: Marked as RESOLVED in HOLISTIC_AUDIT_REMEDIATION.md
[ ] HOLISTIC_AUDIT_REMEDIATION.md updated — all H-tier items marked with resolution status
[ ] CHANGELOG.md entries for all changes
[ ] Version headers updated on all modified .py files
```

## Fix Order

Handle security items first, then audit trail gaps, then docs:

1. **H-4** (session fixation) — security, quick fix
2. **H-5** (admin inheritance + cycle detection) — security, moderate complexity
3. **H-6** (file permissions) — security, quick fix
4. **H-3** (analytics tag permission) — security, quick fix
5. **H-2** (custodian permission checks) — security, quick fix
6. **H-1** (closed-case gate audit) — security, requires careful audit of three large files
7. **H-7** (sync audit logging) — audit trail, moderate complexity
8. **H-8** (coding audit log) — audit trail, quick fix
9. **H-9** (audit vocabulary) — docs/code quality
10. **H-10** (deployment guide) — docs only
11. **H-11** (mark resolved) — docs only
