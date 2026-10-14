# Privilege Log QC Editor — Feature Spec

**Date:** 2026-03-31
**Priority:** HIGH — Demo differentiator + paralegal workflow win
**Branch:** `beta-2.8` (implement after audit fix sprint completes)
**Files affected:** `5_Production.py`, `db_manager.py`, possibly `auth_manager.py`

---

## Problem Statement

The current Privilege Log tab in Production generates a fixed-column CSV/Excel export based on privilege tags and the fuzzy-match privilege reason system. It works, but it has several limitations for real-world use:

1. **No column control** — The export always includes the same 12 columns. Different matters, courts, and opposing counsel may require different privilege log formats. Some jurisdictions require a "Description" column with a substantive privilege description; others require only Bates range, date, from/to, and privilege basis.
2. **No pre-production QC grid** — The paralegal sees the data in a read-only `st.dataframe()` and must export to Excel to review. There's no way to verify the log looks correct before it goes out.
3. **No row filtering** — All privilege-tagged documents appear. In a large case, the paralegal may want to filter by disposition, custodian, date range, or privilege basis to QC specific subsets.
4. **"Needs disposition review" documents are buried** — Documents tagged privileged but lacking a Redact/Withhold disposition show up with a warning icon but there's no way to action them from this tab.

## Feature Overview

Replace the current Privilege Log tab with a two-section layout:

1. **QC Grid** — An interactive, filterable data grid showing all privilege-tagged documents with their log metadata. Includes visual flagging for documents missing dispositions. Read-only — editing privilege metadata happens in the Review module.
2. **Column Picker + Export** — A per-case configurable column picker that controls which columns appear in the exported CSV/XLSX. The picker state is saved in `case_settings` so it persists across sessions and users.

### What this is NOT

- NOT inline editing. Document tags, redaction marks, and privilege dispositions are set in the Review module. The privilege log is a *derived view* of that data. Breaking that continuity would create two sources of truth.
- NOT a separate module. This stays as a tab in the Production module where it lives today.

---

## Detailed Design

### Section 1: QC Grid

**Data source:** Same query as today — all documents with privilege-related tags (from `get_privilege_tag_members()` or fallback `tags LIKE '%Privileged%'`), plus the optional "Needs Review" toggle.

**New additions to the query:**
- Add `confidentiality_designation`, `source_collection`, `document_notes` (from `document_notes` table — LEFT JOIN or subquery for latest note), and `reviewer` (from `review_batches` if assigned) to the SELECT
- Add `processing_status` to enable the `view_shell_documents` permission gate (from the audit fix sprint)

**Grid display:**
- Use `st.dataframe()` with column configuration for display formatting
- Show ALL available columns in the grid regardless of export column picker state — the grid is for QC, the picker is for export
- Color-code rows by disposition:
  - **Withhold** — light red/pink background
  - **Redact** — light yellow background
  - **No disposition (⚠️)** — light orange background with warning icon in Disposition column
- Sort: default by control number; allow column-click sorting if Streamlit supports it (otherwise keep default)

**Filter bar** (above the grid):
- **Disposition filter** — multiselect: `Withhold`, `Redact`, `Needs Disposition`, `All` (default: All)
- **Privilege Basis filter** — multiselect from distinct values in the generated PrivilegeBasis column
- **Custodian filter** — multiselect from distinct custodians in the result set
- **Date range** — optional date_start / date_end inputs
- **"Show only ⚠️ Needs Disposition"** — convenience checkbox that is equivalent to filtering to `Needs Disposition` only. This is the QC power feature — one click to see everything that needs attorney attention.

**Metrics bar** (same as today but enhanced):
- Privileged Documents (total)
- Withheld
- Redact & Produce
- ⚠️ Needs Disposition (highlighted in orange if > 0)
- NEW: Documents with Bates (count of docs that have been produced)
- NEW: Documents without Bates (count of docs not yet produced — matters for supplemental productions)

### Section 2: Column Picker + Export

**Available columns** (EDRM standard set + extended metadata):

| Column Key | Display Name | Default On | EDRM Standard |
|-----------|-------------|-----------|---------------|
| `control_number` | Control Number | ✅ | ✅ |
| `begdoc` | BegBates | ✅ | ✅ |
| `enddoc` | EndBates | ✅ | ✅ |
| `privilege_basis` | Privilege Basis | ✅ | ✅ |
| `disposition` | Disposition | ✅ | ✅ |
| `description` | Description | ✅ | ✅ |
| `date_sent` | Date | ✅ | ✅ |
| `email_from` | From | ✅ | ✅ |
| `email_to` | To | ✅ | ✅ |
| `email_cc` | CC | ✅ | ✅ |
| `email_subject` | Subject / Title | ✅ | ✅ |
| `custodian` | Custodian | ✅ | ✅ |
| `record_type` | Record Type | ❌ | ✅ |
| `file_name` | File Name | ❌ | ❌ |
| `confidentiality` | Confidentiality | ❌ | ❌ |
| `source_collection` | Source Collection | ❌ | ❌ |
| `page_count` | Page Count | ❌ | ❌ |
| `redaction_pages` | Redacted Pages | ❌ | ❌ |
| `reviewer_notes` | Reviewer Notes | ❌ | ❌ |

**Column picker UI:**
- `st.multiselect` with all available columns listed
- Default selection loaded from `case_settings` key `privilege_log_columns` (JSON array of column keys)
- If no saved config, default to all columns marked "Default On" above
- "Save Column Config" button writes selection to `case_settings`
- "Reset to EDRM Defaults" button restores the default set

**Per-case persistence:**
- `case_settings` key: `privilege_log_columns`
- Value: JSON array of column keys, e.g. `["control_number", "begdoc", "enddoc", "privilege_basis", "disposition", "date_sent", "email_from", "email_to", "email_subject", "custodian"]`
- Read via `db_manager.get_case_setting()`, write via `db_manager.save_case_setting()`

**Export:**
- CSV and Excel download buttons (same as today)
- Export respects the column picker — only selected columns appear in the file
- Column order in export matches the order in the multiselect
- Excel version gets light formatting: header row bold, auto-width columns, sheet name "Privilege Log"
- File naming: `{case_name}_PRIVILEGE_LOG.csv` / `.xlsx` (unchanged)

**Privilege Basis Override:**
- Keep the existing `_pl_override_basis` selectbox (Auto-detect / specific basis / Custom)
- This controls the value in the `privilege_basis` column for ALL rows
- "Auto-detect from tags" remains the default and uses the existing `_pl_fuzzy_match_privilege_reason()` logic

---

## Permission Gates

- **Tab visibility:** `has_permission('privilege_log')` (existing — no change)
- **Column config save:** `has_permission('production')` — only users who can run productions should set the log format (managers/admins). Reviewers can view the QC grid but not change the column config.
- **Closed-case behavior:** Grid and export still functional (read-only operations). Column config save blocked.

---

## Implementation Notes

### db_manager.py changes
- Add `get_privilege_log_column_config(case_folder)` → returns saved column list or None
- Add `save_privilege_log_column_config(case_folder, columns: list)` → writes to case_settings
- These are simple wrappers around existing `get_case_setting` / `save_case_setting` patterns

### 5_Production.py changes
- Replace the current Privilege Log tab content (lines ~3362-3551) with the new two-section layout
- Keep `_PL_ABBREV_MAP` and `_pl_fuzzy_match_privilege_reason()` — they work correctly
- The main query needs additional columns in the SELECT and the conditional `Split_Source` filter from the audit fix sprint
- Grid rendering: use `st.dataframe()` with `column_config` for formatting. Streamlit's native dataframe handles sorting. For row coloring, use a `Disposition` column with styled values (emoji + text, as today) rather than CSS row highlighting (Streamlit doesn't support row-level styling natively)
- Filter bar: use `st.columns()` layout with `st.multiselect` / `st.date_input` widgets
- Apply filters to the DataFrame in memory (no re-query needed — the dataset is small enough)

### What NOT to change
- The production-time merged privilege log generation (the one that writes to the production folder during Pass 2) is a SEPARATE code path and must NOT be affected. It uses `_priv_redact_cns` and the `redaction_marks` table, not the tag-based query. Leave it alone.
- The `_PL_ABBREV_MAP` and fuzzy matching logic — battle-tested, leave in place.

---

## DEPENDENCY_MAP.md Update

Add to case_settings section:
```
| `privilege_log_columns` | 5_Production.py (Priv Log tab) | 5_Production.py (Priv Log tab) | JSON array of column keys for privilege log export format. Per-case. |
```

---

## Testing Checklist

```
[ ] Generate privilege log with default columns — verify output matches current behavior
[ ] Save custom column config — reload page — verify config persists
[ ] Export CSV with custom columns — verify only selected columns appear in correct order
[ ] Export Excel with custom columns — verify formatting
[ ] Filter by disposition "Needs Disposition" — verify only undispositioned docs shown
[ ] Filter by custodian — verify correct filtering
[ ] Filter by date range — verify correct filtering
[ ] Verify production-time privilege log is unaffected (run a test production)
[ ] Verify column config save is blocked on closed cases
[ ] Verify column config save requires production permission
[ ] Reset to EDRM defaults — verify correct columns restored
[ ] Case with no privileged documents — verify empty state message
```
