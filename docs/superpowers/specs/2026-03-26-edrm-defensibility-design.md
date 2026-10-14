# Phase 24a: EDRM Defensibility Gaps — Design Spec

## Context

The EDRM gap analysis identified 4 defensibility gaps with HIGH or CRITICAL legal exposure. These close the most important compliance holes in the platform: proving what was collected and why, verifying file integrity, enforcing session security, and making De-NIST filtering auditable and configurable.

---

## Item 1: Collection Scope Documentation

### Problem
No way to document per-custodian, per-source collection decisions (Collected, Searched-No-Hit, Not Reasonably Accessible, Out of Scope). This is a Rule 26(f) requirement and a frequent point of challenge in discovery disputes.

### Database

New `collection_scope` table in `db_manager.init_db()`:

```sql
CREATE TABLE IF NOT EXISTS collection_scope (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    custodian_id INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending', 'Collected', 'Searched-No-Hit',
                          'Not-Reasonably-Accessible', 'Out-of-Scope')),
    justification TEXT,
    reviewed_by TEXT,
    reviewed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (custodian_id) REFERENCES custodians(id) ON DELETE CASCADE,
    UNIQUE(custodian_id, source_name)
);
```

New `db_manager.py` functions:
- `get_collection_scope(case_folder, custodian_id)` — returns all scope rows for a custodian
- `upsert_collection_scope(case_folder, custodian_id, source_name, status, justification, reviewed_by)` — INSERT OR REPLACE
- `get_all_collection_scope(case_folder)` — returns all scope rows joined with custodian name (for defensibility report)
- `seed_collection_scope(case_folder, custodian_id, sources)` — bulk-insert Pending entries for a list of source names

### UI

New tab in `7_Custodians.py` Operations section: "Collection Scope"

When a custodian is selected:
1. Load their `data_sources` JSON list and their `collection_scope` rows
2. If `data_sources` has entries not yet in `collection_scope`, auto-seed them as "Pending"
3. Display editable grid: Source Name | Status (selectbox) | Justification (text) | Reviewed By (read-only) | Reviewed At (read-only)
4. Save button: upserts all rows, sets `reviewed_by` to current user and `reviewed_at` to now
5. Completeness indicator: "X of Y sources documented" with warning if any are still Pending

### Defensibility Report

New Section 2.2 "Collection Scope & Justification" in `defensibility_report.py`:
- Table: Custodian | Source | Status | Justification
- Summary counts: X Collected, Y Searched-No-Hit, Z Not Reasonably Accessible, W Out of Scope
- Called via `get_all_collection_scope()`

### Audit
- `COLLECTION_SCOPE_UPDATED` action logged per save with custodian name and source count

---

## Item 2: Hash Integrity Verification

### Problem
No way to verify that ingested files haven't been modified since ingestion. Opposing counsel could challenge file integrity if there's no verification mechanism.

### UI

New section in `home.py` > Case Maintenance expander: "Verify Document Integrity"

- "Verify Integrity" button (admin-only, gated by `_case_closed` check)
- On click: iterates all documents with `full_path` and `md5_hash` in the database
- For each: re-computes MD5 via `calculate_md5()` (same function from 1_Ingestor.py), compares to stored hash
- Progress bar during verification
- Results displayed as metrics: Total Verified | Matches | Mismatches | Missing Files
- If mismatches > 0: dataframe with Control Number, File Name, Expected Hash, Actual Hash
- If missing > 0: dataframe with Control Number, File Name, Expected Path

### Shared Function

Move `calculate_md5()` from `1_Ingestor.py` to a shared location (or import it from Ingestor). Since Ingestor already defines it at module level (line 64), import it directly:
```python
from pages import 1_Ingestor  # Not valid Python — use importlib or duplicate
```
Best approach: duplicate the small function in `db_manager.py` or a shared utils module. Since it's 7 lines and the project doesn't have a utils module, define it inline in the verification section of `home.py`.

### Audit
- `INTEGRITY_VERIFICATION` action logged with: total, matches, mismatches, missing counts
- If mismatches found: individual `INTEGRITY_MISMATCH` entries per document

---

## Item 3: Session Timeout / Auto-Logout

### Problem
No session timeout on shared workstations. A user who walks away leaves the session open indefinitely, creating a security/compliance gap.

### Configuration

Add to `auth_config.yaml`:
```yaml
session_timeout_minutes: 30
```

### Logic

In `auth_manager.check_login()`, after the `if st.session_state.get('authenticated'):` check:

1. Read timeout from config: `_load_auth_config().get('session_timeout_minutes', 30)`
2. Check: `time.time() - st.session_state.get('last_activity_time', 0) > timeout_seconds`
3. If expired: clear auth keys (`authenticated`, `username`, `user_role`, `display_name`), show `st.warning("Session expired due to inactivity. Please log in again.")`, return False
4. If not expired: update `st.session_state['last_activity_time'] = time.time()`, continue

On successful login (after setting auth keys):
- Set `st.session_state['last_activity_time'] = time.time()`

### Files Modified
- `auth_manager.py` only — all pages already call `check_login()` as their gate

### Edge Cases
- If `session_timeout_minutes` is 0 or missing: disable timeout (infinite session)
- Browser refresh: session state persists within Streamlit session, timeout continues tracking
- New browser tab: new Streamlit session, requires fresh login (existing behavior)

---

## Item 4: De-NIST Configurability

### Problem
NIST extension list is hardcoded in `2_Processor.py`. Cannot be audited, customized per case, or exported for defensibility documentation.

### Storage

New `case_settings` key: `nist_extensions`
- Value: JSON array of extensions (e.g., `[".exe", ".dll", ".sys", ...]`)
- Default: current hardcoded list of 24 extensions

New `db_manager.py` functions:
- `get_nist_extensions(case_folder)` — returns list, falls back to hardcoded default if not set
- `set_nist_extensions(case_folder, extensions_list)` — saves to case_settings

### UI

New section in `home.py` > Case Maintenance expander: "De-NIST Filter Configuration"

- `st.text_area` showing current extensions (one per line)
- "Reset to Default" button restores hardcoded list
- "Save" button persists to `case_settings`
- Read-only count: "X extensions configured"
- "Export Exclusion Report" button: generates CSV of all NIST-excluded documents with extension, file name, custodian

### Processor Change

In `2_Processor.py` `recursively_extract_all()`:
- Replace hardcoded `NIST_EXTENSIONS` set with: `set(db_manager.get_nist_extensions(case_folder))`
- Keep hardcoded list as the `DEFAULT_NIST_EXTENSIONS` constant (fallback + reset source)

### Audit
- `NIST_CONFIG_UPDATED` action logged when extensions list is saved, with count

---

## Files Modified

| File | Items | Changes |
|------|-------|---------|
| `db_manager.py` | 1, 4 | New `collection_scope` table, 4 scope functions, 2 NIST functions |
| `pages/7_Custodians.py` | 1 | New "Collection Scope" tab |
| `defensibility_report.py` | 1 | New Section 2.2 |
| `home.py` | 2, 4 | Hash verification section, De-NIST config section in Case Maintenance |
| `auth_manager.py` | 3 | Timeout logic in check_login() |
| `pages/2_Processor.py` | 4 | Load NIST extensions from DB instead of hardcoded |
| `auth_config.yaml` | 3 | New `session_timeout_minutes` key |
