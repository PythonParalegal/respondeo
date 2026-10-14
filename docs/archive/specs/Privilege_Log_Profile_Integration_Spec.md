# Privilege Log Profile Integration — Feature Spec

**Date:** 2026-04-01
**Priority:** MEDIUM — Workflow improvement, not a bug fix
**Branch:** future sprint (after current round of fixes lands)
**Files affected:** `5_Production.py` (both Outbound Production tab and Privilege Log tab)

---

## Concept

Privilege log export profiles (column selection, headers, merge rules, ordering) are currently configured and used only in the Privilege Log QC tab. This spec extends profiles to the production pipeline so that:

1. **Production-time privilege log** uses a saved profile to format its output — same columns, headers, and merge rules that the paralegal configured in the QC tab
2. **QC tab** remains a standalone tool for regenerating/fixing privilege logs after production, using the same profiles
3. **One set of profiles, two consumers** — profiles are saved per-case in `case_settings`, read by both code paths

---

## Current State (Two Separate Code Paths)

### Path 1: Production-Time Privilege Log (Pass 2)
- **Location:** 5_Production.py, inside the production execution flow (~lines 1540-1580)
- **Trigger:** Runs automatically during Pass 2 of production
- **Format:** Hardcoded columns — BegBates, Page, PrivilegeReason, ControlNumber, FileName
- **Output:** CSV written to `{prod_path}/PRIVILEGE_LOG.csv`
- **Data source:** `redaction_marks` table + `_priv_redact_cns` set (documents with Redact disposition that were produced)
- **Bates:** Computes per-page Bates from production data (begdoc + page offset) — accurate because it runs during production

### Path 2: QC Tab Privilege Log
- **Location:** 5_Production.py, Privilege Log tab (~lines 3370-3900)
- **Trigger:** User visits the tab (auto-load) or clicks Refresh
- **Format:** Configurable via export profiles (column selection, ordering, merges, custom headers)
- **Output:** CSV/Excel download via browser
- **Data source:** `documents` table (privilege_status IN ('Withhold', 'Redact')) + `redaction_marks` for reasons and pages
- **Bates:** Currently shows page offsets (pending per-page Bates fix)

---

## Design: Unified Profile System

### Step 1: Profile selector in Configure Production

In the Outbound Production tab's "Configure & Run" section (Section 2), add a privilege log profile selector:

```
Configure Production
├── Production Name: [PRODUCTION_NAME_002]
├── Production Mode: ○ Simple  ○ Full EDRM
├── Continue from Last: [toggle]
├── ...existing options...
└── Privilege Log Format
    ├── Profile: [dropdown — EDRM Standard / Sample Matter / Custom Profile / ...]
    └── Preview: "5 columns: Date, Record Type, Individuals Involved, Privilege Basis, Bates"
```

The dropdown reads from the same `privilege_log_profiles` key in `case_settings` that the QC tab writes to. If no profiles are saved, default to "EDRM Standard" (built-in).

### Step 2: Production-time privilege log uses selected profile

During Pass 2, when generating the privilege log CSV:

1. Read the selected profile from `case_settings` (or session state)
2. Apply the profile's column selection, ordering, header renames, and merge rules
3. Write the formatted CSV to `{prod_path}/PRIVILEGE_LOG.csv` (same location as today)
4. Also write Excel version if openpyxl is available: `{prod_path}/PRIVILEGE_LOG.xlsx`

The production-time code already has access to per-page Bates numbers (it computes them during production). This is MORE accurate than the QC tab's math-based approach because the numbers come directly from the production counter.

### Step 3: QC tab inherits per-page Bates from production data

When the QC tab generates a privilege log for documents that have already been produced:
- Use the same `begdoc + page_offset` math (which is identical to what production used)
- The `redacted_pages_list` from `redaction_marks` provides the page numbers
- This gives the same result as production-time calculation

### Step 4: Profile round-trip

Both code paths read from and write to the same profile storage:

```
case_settings['privilege_log_profiles'] = {
    "active_profile": "profile_a",
    "production_profile": "profile_a",  ← NEW: which profile production uses
    "profiles": {
        "edrm_standard": { ... },
        "profile_a": { ... }
    }
}
```

The QC tab has `active_profile` (for previewing/exporting).
The production config has `production_profile` (for production-time generation).
They CAN be different — e.g., the paralegal might be experimenting with a new profile in the QC tab while the production still uses the established one.

---

## Production Code Changes

### Current production-time privilege log code (approximate):

```python
# During Pass 2, after processing all Redact documents:
priv_log_rows = []
for cn in _priv_redact_cns:
    marks = db_manager.get_all_redaction_marks(case_folder, cn)
    for mark_row in marks:
        for mark in json.loads(mark_row['marks_json']):
            reason = mark.get('reason', '')
            if reason and reason != _REDACT_NO_REASON:
                page_bates = compute_page_bates(begdoc, mark_row['page_number'])
                priv_log_rows.append({
                    'BegBates': page_bates,
                    'Page': mark_row['page_number'] + 1,
                    'PrivilegeReason': reason,
                    'ControlNumber': cn,
                    'FileName': filename
                })
priv_df = pd.DataFrame(priv_log_rows)
priv_df.to_csv(os.path.join(prod_path, 'PRIVILEGE_LOG.csv'), index=False)
```

### New: Apply profile to production output

```python
# Read the production profile
prod_profile_name = db_manager.get_case_setting(case_folder, 'privilege_log_profiles')
# ... parse JSON, get the production_profile ...

# Build the privilege log DataFrame using the profile
# (same _pl_build_export_df logic from the QC tab, extracted to a shared function)
priv_df = build_privilege_log_df(
    case_folder,
    profile=prod_profile,
    produced_cns=_priv_redact_cns,  # limit to documents in this production
    withheld_cns=_priv_withhold_cns
)

# Write to production folder
priv_df.to_csv(os.path.join(prod_path, 'PRIVILEGE_LOG.csv'), index=False)
# Also Excel if available
```

### Shared function: `build_privilege_log_df()`

Extract the core DataFrame-building logic from the QC tab into a shared function that both code paths can call. This function:
- Queries privilege documents (by disposition)
- Resolves privilege basis (mark reasons → tags → placeholder)
- Applies profile: column selection, ordering, header renames, merges
- Computes per-page Bates numbers
- Returns a formatted DataFrame ready for export

This could live in `5_Production.py` as a module-level function, or in a separate utility file.

---

## What This Does NOT Change

- The QC tab remains fully functional as a standalone tool
- The QC tab's export (CSV/Excel download) still works independently
- Profiles are still managed in the QC tab (create, edit, reorder, save, delete)
- The production pipeline's core behavior (imaging, Bates stamping, load files) is unaffected
- Only the privilege log CSV/XLSX generation step in the production pipeline is modified

---

## Migration / Backward Compatibility

- If no profile is selected in production config, use "EDRM Standard" (current hardcoded behavior, just expressed as a profile)
- Existing production outputs are not affected (already-generated privilege logs stay as-is)
- The new `production_profile` key in case_settings is optional — absent = default

---

## Implementation Order

This is a future sprint, NOT part of the current round of fixes. Prerequisites:
1. ✅ QC tab auto-load + session state (done)
2. ✅ Query fix: privilege_status instead of tags (done)
3. ✅ Privilege basis from redaction marks (done)
4. ✅ Export profiles with column customization (done)
5. ✅ Column reordering + live preview (done)
6. ⬜ Per-page Bates calculation (current spec — Privilege_Log_Bates_Fix.md)
7. ⬜ **This spec: Profile-to-production integration**
8. ⬜ Extract shared `build_privilege_log_df()` function
9. ⬜ Add profile selector to production config UI

---

## CHANGELOG entries (when implemented)

```
- NEW: 5_Production.py — Production-time privilege log uses saved export profiles (column selection, headers, merge rules)
- NEW: 5_Production.py — Privilege log profile selector added to production configuration
- CHANGE: 5_Production.py — Extracted shared build_privilege_log_df() function used by both QC tab and production pipeline
- NEW: 5_Production.py — Production privilege log includes Excel (.xlsx) format alongside CSV
```

---

## Testing Checklist

```
[ ] Production config shows privilege log profile dropdown
[ ] Selecting a profile shows preview of column layout
[ ] Running production generates privilege log using selected profile's columns/headers
[ ] Production privilege log CSV has custom column names (e.g., "Individuals Involved")
[ ] Production privilege log Excel version is generated alongside CSV
[ ] QC tab still works independently — can export with different profile than production
[ ] No profile selected in production → falls back to EDRM Standard
[ ] Changing profile in QC tab does NOT automatically change production profile (they're independent)
[ ] Profile created in QC tab appears in production dropdown
[ ] Production privilege log includes both Withhold and Redact documents
```
