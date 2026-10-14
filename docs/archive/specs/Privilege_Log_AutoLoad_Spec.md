# Privilege Log Auto-Load + Export Customization — Sprint Spec

**Date:** 2026-04-01
**Priority:** HIGH — Tab is currently non-functional (renders blank for user)
**Branch:** `beta-2.9`
**Files affected:** `5_Production.py` (lines ~3370–3743), `db_manager.py`

---

## Problem Statement

The Privilege Log tab in the Production module has four issues:

1. **Tab renders completely blank.** ~~FIXED by auto-load sprint (2026-04-01).~~ The button-gated pattern caused the blank tab. Now auto-loads.

2. **CRITICAL: Query uses tags instead of privilege_status.** The current query searches for documents by tag membership (`tags LIKE '%Privileged%'` or via `get_privilege_tag_members()`). This is wrong. The source of truth for "is this document on the privilege log?" is the **`privilege_status` column** (`Withhold` or `Redact`), not tags. Tags describe the *basis* for the privilege (e.g., "Privacy - Insurance Information", "Attorney-Client"), but the disposition determines log membership. The current query returns zero results for cases where documents have `privilege_status` set but no tag literally named "Privileged". **This is the #1 fix in this sprint.**

3. **Design flaw: button-gated data.** ~~FIXED by auto-load sprint (2026-04-01).~~

4. **Export format inflexibility.** The current export uses fixed column names and a 1:1 mapping of database columns to export columns. Real-world privilege logs need:
   - Custom header names (e.g., "Individuals Involved" instead of separate From/To/CC columns)
   - Merged columns (From + To + CC → single column)
   - Stripped email addresses (show names only)
   - Disposition-aware Bates formatting (full range for Withhold, specific redacted pages for Redact)

---

## Part 1: Core Fixes

### 1a. CRITICAL — Fix privilege log query to use privilege_status

**Current (broken):** The query finds documents by searching tags:
```python
# get_privilege_tag_members() returns tags from categories with is_privilege=True
# Falls back to: tags LIKE '%Privileged%'
_pl_base_conditions = ' OR '.join(["tags LIKE ?" for _ in _pl_priv_members])
```

**Correct:** The query should find documents by `privilege_status` column:
```python
# privilege_status is the source of truth — set to 'Withhold' or 'Redact' in Review
_pl_base_conditions = "d.privilege_status IN ('Withhold', 'Redact')"
```

**Tags still matter** — but for the *privilege basis* column in the export, not for determining which documents appear on the log. The `_pl_fuzzy_match_privilege_reason()` function still reads tags to populate the "Privilege Basis" column. This is correct behavior — keep it.

**"Include Needs Review" checkbox** — this should ALSO change to look at privilege_status or a dedicated flag, not `tags LIKE '%Needs Review%'`. For now, keep it as a tag-based filter since "Needs Review" is a workflow tag, not a disposition. But the main query must NOT depend on it — the primary filter is `privilege_status IN ('Withhold', 'Redact')`, with "Needs Review" as an optional additive filter.

**Updated query:**
```sql
SELECT d.control_number, d.begdoc, d.enddoc, d.file_name, d.custodian,
       d.record_type, d.date_sent, d.email_from, d.email_to, d.email_cc,
       d.email_subject, d.tags, d.privilege_status,
       d.confidentiality_designation, d.source_collection, d.page_count,
       d.reviewed_by,
       (SELECT dn.note_text FROM document_notes dn
        WHERE dn.control_number = d.control_number
        ORDER BY dn.updated_at DESC LIMIT 1) AS reviewer_note,
       (SELECT COUNT(DISTINCT rm.page_number) FROM redaction_marks rm
        WHERE rm.control_number = d.control_number) AS redacted_page_count,
       (SELECT GROUP_CONCAT(DISTINCT rm.page_number) FROM redaction_marks rm
        WHERE rm.control_number = d.control_number) AS redacted_pages_list
FROM documents d
WHERE d.privilege_status IN ('Withhold', 'Redact')
  {_pl_needs_review_clause}
  {_pl_shell_filter}
ORDER BY d.date_sent ASC, d.control_number ASC
```

Where `_pl_needs_review_clause` is:
- Empty string when checkbox is off (default)
- `OR (d.tags LIKE '%Needs Review%' AND d.privilege_status IS NULL)` when checkbox is on — this adds documents tagged "Needs Review" that don't yet have a disposition

### 1b. Auto-load on tab open (no button required)

Replace the `if _pl_run_btn:` pattern with auto-loading. When the tab renders:
- Query the privilege log data immediately
- Store the resulting DataFrame in `st.session_state`
- Display the grid, filters, metrics, and export controls unconditionally

### 1b. Session state persistence

Store these items in session state so they survive filter interactions:

```python
_pl_case_id = os.path.basename(case_folder)
# Keys:
f"pl_data_{_pl_case_id}"            # raw query result DataFrame
f"pl_display_{_pl_case_id}"         # processed display DataFrame
f"pl_last_basis_{_pl_case_id}"      # privilege basis override used for last query
f"pl_last_needs_review_{_pl_case_id}" # whether "include Needs Review" was checked
```

### 1c. Refresh button (replaces Generate)

Change "🔍 Generate Privilege Log" to "🔄 Refresh". Purpose:
- Force re-query when user has made changes in the Review module
- Auto-trigger when basis override or "Include Needs Review" checkbox changes

```python
needs_query = (
    _pl_state_key not in st.session_state
    or _pl_refresh_btn
    or st.session_state.get(f"pl_last_basis_{_pl_case_id}") != _pl_override_basis
    or st.session_state.get(f"pl_last_needs_review_{_pl_case_id}") != _pl_include_needs_review
)
```

### 1d. Error handling wrapper

Wrap the entire `with tab_privlog:` body:

```python
with tab_privlog:
    try:
        # ... all tab content ...
    except Exception as _pl_err:
        st.error(f"Error loading Privilege Log: {_pl_err}")
        import traceback
        with st.expander("Technical details"):
            st.code(traceback.format_exc())
```

### 1e. Audit logging adjustment

Move `log_audit("PRIVILEGE_LOG_GENERATED")` inside the `if needs_query:` block so it only fires on initial load or explicit refresh, not on every filter interaction.

### 1f. Empty-state handling

If no privileged documents found:
- Show info message: "No privileged documents found. Tag documents as 'Privileged' in the Review module."
- Still show the control panel (basis override + refresh button)
- Do NOT show filters, grid, metrics, or export

---

## Part 1g: Fix Privilege Basis Sourcing

**Current (broken):** `_pl_fuzzy_match_privilege_reason()` reads the document's `tags` column, tries to match against standard legal abbreviations (AC, WP, CI, etc.), and defaults to "Attorney-Client Privilege" when nothing matches. This gives wrong results for non-standard privilege reasons like "Privacy - Insurance Information" or "Premium and deductible information".

**Fix:** Replace the single-source lookup with a three-tier cascade:

1. **Redaction mark reasons (most specific):** Query `redaction_marks.marks_json` for the document, extract all `"reason"` fields. These are the actual privilege bases entered by the reviewer at redaction time. If found, use them (deduplicated, comma-joined if multiple distinct reasons exist).

2. **Document tags (fallback):** If no redaction mark reasons found (e.g., Withhold documents that have no marks), check the `tags` column. Apply the existing `_PL_ABBREV_MAP` fuzzy matching to map abbreviations to standard names.

3. **"(No basis specified)" (final fallback):** If neither source provides a basis, show this placeholder instead of silently defaulting to "Attorney-Client Privilege". This makes it visible that the document needs a basis assigned.

**The override dropdown still works:** If the user selects a specific basis from the Privilege Basis dropdown (not "Auto-detect"), that overrides everything — same as today.

**Implementation:**

```python
def _pl_resolve_privilege_basis(row, override, marks_reasons_str):
    """
    Three-tier privilege basis resolution:
    1. Redaction mark reasons (from marks_json 'reason' fields)
    2. Tag-based fuzzy matching (existing _PL_ABBREV_MAP logic)
    3. "(No basis specified)" placeholder
    """
    # Manual override takes precedence
    if override != "Auto-detect from tags":
        return override

    # Tier 1: Redaction mark reasons
    if marks_reasons_str:
        # marks_reasons_str comes from a GROUP_CONCAT subquery
        reasons = [r.strip() for r in marks_reasons_str.split(',') if r.strip()]
        # Filter out the no-reason sentinel
        reasons = [r for r in reasons if r != '[Redact — No Privilege Reason]']
        if reasons:
            # Deduplicate while preserving order
            seen = set()
            unique = []
            for r in reasons:
                if r not in seen:
                    seen.add(r)
                    unique.append(r)
            return ', '.join(unique)

    # Tier 2: Tag-based fuzzy matching (existing logic)
    tags = row.get('tags', '')
    result = _pl_fuzzy_match_privilege_reason(tags, "Auto-detect from tags")
    if result != 'Attorney-Client Privilege':  # Only use if it actually matched something
        return result

    # Tier 3: No basis found
    return '(No basis specified)'
```

**Query change:** Add a subquery to extract distinct redaction mark reasons:

```sql
(SELECT GROUP_CONCAT(DISTINCT reason_val)
 FROM (
   SELECT json_each.value ->> 'reason' AS reason_val
   FROM redaction_marks rm, json_each(rm.marks_json)
   WHERE rm.control_number = d.control_number
     AND json_each.value ->> 'reason' IS NOT NULL
     AND json_each.value ->> 'reason' != '[Redact — No Privilege Reason]'
 )
) AS mark_reasons
```

**Note:** SQLite's `json_each()` function is available in SQLite 3.38+ (2022). If the deployed SQLite version is older, use a Python-side approach: fetch `marks_json` rows and parse in the row-building loop. Check with:

```python
# In the query block, test SQLite JSON support:
try:
    _pl_conn.execute("SELECT json_each.value FROM json_each('[1,2]')").fetchone()
    _pl_has_json_each = True
except:
    _pl_has_json_each = False
```

If `json_each` isn't available, fetch marks in a separate query per document (less efficient but works everywhere).

**CHANGELOG entries:**
```
- FIX: 5_Production.py — Privilege basis now sourced from redaction mark reasons first, then tags, then "(No basis specified)"; fixes incorrect "Attorney-Client Privilege" default for non-standard privilege reasons
```

**Testing:**
```
[ ] Document with redaction marks containing "Privacy - Insurance Information" reason → shows that reason, NOT "Attorney-Client Privilege"
[ ] Document with multiple distinct redaction reasons → shows comma-joined reasons
[ ] Document with no redaction marks but standard privilege tags → shows matched basis from tags
[ ] Document with no marks and no recognizable tags → shows "(No basis specified)"
[ ] Override dropdown set to specific basis → overrides all three tiers
[ ] Withheld document (no marks) with AC Privilege tag → shows "Attorney-Client Privilege" from tag match
```

---

## Part 1h: Fix Mixed-Type Arrow Serialization Warning

**Problem:** The Streamlit terminal shows repeated `ArrowTypeError` warnings:
```
Conversion failed for column Page Count with type object
```

**Root cause:** Lines 3618-3619 in the row-building loop store `int` for present values and `''` (empty string) for missing values, creating mixed-type columns that Arrow can't serialize cleanly.

**Fix:** Use `None` instead of `''` for missing numeric values. This lets pandas use nullable integer types:

```python
# Line 3618 — change '' to None:
'page_count':      int(r['page_count']) if pd.notna(r['page_count']) else None,
# Line 3619 — change '' to None:
'redaction_pages': int(r['redacted_page_count']) if pd.notna(r['redacted_page_count']) and r['redacted_page_count'] > 0 else None,
```

**Also check:** Any other columns in the row-building loop that mix types (int/string, or string/None). The same pattern may exist for `redacted_page_count`.

**CHANGELOG:** `FIX: 5_Production.py — Privilege Log page_count and redaction_pages columns use None for missing values (fixes Arrow serialization warnings)`

---

## Part 2: Export Column Customization

### 2a. Export Profiles

Replace the simple column-list picker with named **Export Profiles** saved per-case. Each profile defines: which columns appear, their export header names, and merge rules.

**Data model** (stored in `case_settings` key `privilege_log_profiles` as JSON):

```json
{
  "active_profile": "attorney_format",
  "profiles": {
    "edrm_standard": {
      "name": "EDRM Standard",
      "builtin": true,
      "columns": [
        {"key": "control_number", "header": "Control Number"},
        {"key": "begdoc", "header": "BegBates"},
        {"key": "enddoc", "header": "EndBates"},
        {"key": "privilege_basis", "header": "Privilege Basis"},
        {"key": "disposition", "header": "Disposition"},
        {"key": "description", "header": "Description"},
        {"key": "date_sent", "header": "Date"},
        {"key": "email_from", "header": "From"},
        {"key": "email_to", "header": "To"},
        {"key": "email_cc", "header": "CC"},
        {"key": "email_subject", "header": "Subject / Title"},
        {"key": "custodian", "header": "Custodian"}
      ]
    },
    "attorney_format": {
      "name": "Reviewer A's Format",
      "builtin": false,
      "columns": [
        {"key": "date_sent", "header": "Date"},
        {"key": "record_type", "header": "Document"},
        {"key": "_merged_individuals", "header": "Individuals Involved",
         "merge": {"sources": ["email_from", "email_to", "email_cc"],
                   "separator": ", ",
                   "strip_emails": true}},
        {"key": "_merged_bates", "header": "Bates",
         "merge": {"type": "bates_range",
                   "sources": ["begdoc", "enddoc"],
                   "disposition_aware": true}},
        {"key": "privilege_basis", "header": "Privilege"}
      ]
    }
  }
}
```

### 2b. Profile UI

**Layout:**

```
[Profile selector dropdown] [Save Profile] [New Profile] [Delete Profile]

Column Configuration (expander, open when editing):
  [Add Column button]
  For each column row:
    [⬆️] [⬇️] [Source column dropdown] [Export Header text input] [Remove ✕]
    If merge: [Merge sources multiselect] [Separator] [Strip emails checkbox]

  Special merge presets:
    ☑ "Individuals Involved" — merges From/To/CC, strips emails, comma-separated
    ☑ "Bates Range" — merges BegBates/EndBates, disposition-aware formatting

── Export Preview (live-updating) ──────────────────────────────
  [st.dataframe showing first ~10 rows with current profile applied]
  [Caption: "Preview of export format. Showing first 10 rows."]
```

**Column Reordering — Up/Down Arrow Buttons:**

Each selected column in the profile gets ⬆️ and ⬇️ buttons to change its position in the export order. Implementation:

```python
# Store column order in session state as a list
_pl_col_order_key = f"pl_col_order_{_pl_case_id}"
if _pl_col_order_key not in st.session_state:
    st.session_state[_pl_col_order_key] = [col['key'] for col in active_profile['columns']]

# Render each column as a row with move buttons
for i, col_key in enumerate(st.session_state[_pl_col_order_key]):
    _btn_col, _up_col, _dn_col, _name_col, _header_col, _rm_col = st.columns([0.3, 0.3, 0.3, 2, 2, 0.5])
    _btn_col.write(f"**{i+1}.**")

    # Up button (disabled for first item)
    if _up_col.button("⬆️", key=f"pl_up_{col_key}", disabled=(i == 0)):
        order = st.session_state[_pl_col_order_key]
        order[i], order[i-1] = order[i-1], order[i]
        st.rerun()

    # Down button (disabled for last item)
    if _dn_col.button("⬇️", key=f"pl_dn_{col_key}", disabled=(i == len(order) - 1)):
        order = st.session_state[_pl_col_order_key]
        order[i], order[i+1] = order[i+1], order[i]
        st.rerun()

    _name_col.write(col_display_name)
    # Header rename input
    custom_header = _header_col.text_input(
        "Header", value=col.get('header', col_display_name),
        key=f"pl_header_{col_key}", label_visibility="collapsed"
    )
    # Remove button
    if _rm_col.button("✕", key=f"pl_rm_{col_key}"):
        st.session_state[_pl_col_order_key].remove(col_key)
        st.rerun()
```

**Export Preview — Live-Updating Table:**

Below the column picker/reorder UI, show a compact preview of the export using the current profile settings. This updates live as the user changes columns, order, or headers — no save required.

```python
st.subheader("Export Preview")
st.caption("Preview of export format. Showing first 10 rows.")

# Build preview DataFrame using current profile settings (same logic as export)
_pl_preview_df = _pl_build_export_df(
    _pl_filtered,
    column_order=st.session_state[_pl_col_order_key],
    headers=_pl_current_headers,
    merge_config=_pl_current_merges
)
st.dataframe(_pl_preview_df.head(10), hide_index=True, use_container_width=True)
```

The preview uses the same `_pl_build_export_df()` function that the CSV/Excel download uses, so what you see is exactly what you get. Changes to column selection, order, headers, or merge settings are reflected immediately.

**Profile operations:**
- **Switch profile:** dropdown changes active profile, re-renders column config and preview
- **Save Profile:** saves current column config under the active profile name (requires `production` permission, blocked on closed cases)
- **New Profile:** text input for name → creates empty profile, user adds columns
- **Delete Profile:** removes non-builtin profile (with confirmation)
- **EDRM Standard** profile is builtin and cannot be deleted or renamed, but CAN be modified (modifications saved as a separate copy if needed, or just allowed — user's choice)

### 2c. Merged Column: "Individuals Involved"

When this merge is active:

```python
def _pl_merge_individuals(row, strip_emails=True):
    """Combine From, To, CC into a single comma-separated string of names."""
    parts = []
    for field in ['email_from', 'email_to', 'email_cc']:
        val = row.get(field, '')
        if val:
            if strip_emails:
                # Extract names, strip email addresses
                # "John Smith <john@example.com>" → "John Smith"
                # "john@example.com" → "john@example.com" (no name to extract)
                import re
                names = re.findall(r'([^<,;]+?)(?:\s*<[^>]+>)', val)
                if names:
                    parts.extend([n.strip() for n in names if n.strip()])
                else:
                    # No angle-bracket emails — split on commas/semicolons
                    # and strip whitespace
                    parts.extend([p.strip() for p in re.split(r'[,;]', val) if p.strip()])
            else:
                parts.extend([p.strip() for p in val.split(',') if p.strip()])
    # Deduplicate while preserving order
    seen = set()
    unique_parts = []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            unique_parts.append(p)
    return ', '.join(unique_parts)
```

### 2d. Merged Column: "Bates" (Disposition-Aware)

This is the most complex merge. Logic:

- **Withheld documents** (`privilege_status = 'Withhold'`):
  - Single Bates number only (begdoc). Withheld documents are replaced by a one-page placeholder slip sheet in production, so there is no range — just one page, one Bates number.
  - If not yet produced: show `"(not yet produced)"`

- **Redacted documents** (`privilege_status = 'Redact'`):
  - Query `redaction_marks` table for the specific pages with redactions
  - Compute page-level Bates numbers: `begdoc_prefix + (begdoc_number + page_offset)`
  - Show only those page Bates numbers: `"ABC-000301, ABC-000303"` (pages 2 and 4 of a 5-page doc)
  - If not yet produced: show `"(not yet produced — N pages redacted)"`

- **Needs Disposition** (no privilege_status set):
  - Show `"(not yet produced)"` or begdoc if it exists

**Implementation — Bates page calculation:**

```python
import re

def _pl_compute_page_bates(begdoc, page_numbers):
    """Given a begdoc like 'ABC-000300' and page numbers [2, 4],
    return ['ABC-000301', 'ABC-000303']."""
    if not begdoc or begdoc == '(not yet produced)':
        return []
    # Parse prefix and number
    match = re.match(r'^([A-Za-z]+-?)(\d+)$', begdoc)
    if not match:
        return [begdoc]  # can't parse, return as-is
    prefix, num_str = match.groups()
    base_num = int(num_str)
    padding = len(num_str)
    result = []
    for pg in sorted(page_numbers):
        page_bates = f"{prefix}{str(base_num + pg - 1).zfill(padding)}"
        result.append(page_bates)
    return result
```

**Query change needed:** The main privilege log query must also fetch per-document redacted page numbers (not just the count). Add to the query:

```sql
-- In the main query, add a subquery or do a separate lookup
(SELECT GROUP_CONCAT(DISTINCT rm.page_number) FROM redaction_marks rm
 WHERE rm.control_number = d.control_number) AS redacted_pages_list
```

This replaces the current `redacted_page_count` subquery (or supplements it — keep the count too if used elsewhere in the metrics).

**db_manager.py change:** Add `get_redacted_page_numbers(case_folder, control_number)` helper OR just include the `GROUP_CONCAT` in the main privilege log query (preferred — avoids N+1 queries).

### 2e. Export Build Logic

When building the export DataFrame, process columns according to the active profile:

```python
for col_def in active_profile['columns']:
    if 'merge' in col_def:
        merge_cfg = col_def['merge']
        if merge_cfg.get('type') == 'bates_range':
            # Apply disposition-aware bates formatting
            export_df[col_def['header']] = _pl_filtered.apply(
                lambda r: _pl_format_bates(r), axis=1)
        else:
            # Apply standard merge (e.g., Individuals Involved)
            export_df[col_def['header']] = _pl_filtered.apply(
                lambda r: _pl_merge_individuals(r, merge_cfg.get('strip_emails', False)),
                axis=1)
    else:
        # Simple column rename
        source_key = col_def['key']
        export_df[col_def['header']] = _pl_filtered[source_key]
```

---

## Part 3: What NOT to Change

- `_PL_ABBREV_MAP` and `_pl_fuzzy_match_privilege_reason()` — working correctly, keep as-is
- The base SQL query structure (add fields, don't restructure)
- The filter bar logic — keep as-is
- The metrics bar — keep as-is
- The QC grid (always shows ALL available columns for QC; the profile only affects export)
- The production-time merged privilege log — completely separate code path, do NOT touch
- The `_PL_COLUMN_DEFS` list — keep as the source of truth for available columns

---

## Permission Gates (mostly unchanged)

- **view_shell_documents** — conditional Split_Source filter in query (existing, keep)
- **production** — profile save/delete (was column config save). Reviewers can view the grid and export with any profile but cannot modify profiles.
- **Closed-case** — grid/export functional (read-only), profile save/new/delete blocked

---

## db_manager.py Changes

1. **Modify the `get_case_setting` / `save_case_setting` calls** — no function changes needed, just the key changes from `privilege_log_columns` to `privilege_log_profiles`
2. **Add `redacted_pages_list` to any privilege log query** — the `GROUP_CONCAT(DISTINCT rm.page_number)` subquery. This can stay inline in the SQL in 5_Production.py since it's specific to the privilege log display. OR add a dedicated helper if cleaner.

---

## Migration from Old Config

The old `privilege_log_columns` key in `case_settings` (simple JSON array of column keys) should be migrated gracefully:

```python
# On load, check for old format
old_config = db_manager.get_case_setting(case_folder, 'privilege_log_columns')
new_config = db_manager.get_case_setting(case_folder, 'privilege_log_profiles')
if old_config and not new_config:
    # Migrate: create a profile from the old column list
    old_cols = json.loads(old_config)
    migrated_profile = {
        "active_profile": "migrated",
        "profiles": {
            "edrm_standard": _PL_BUILTIN_EDRM_PROFILE,
            "migrated": {
                "name": "Previous Config",
                "builtin": False,
                "columns": [{"key": k, "header": _PL_COL_KEY_TO_DISPLAY[k]} for k in old_cols if k in _PL_ALL_COL_KEYS]
            }
        }
    }
    db_manager.save_case_setting(case_folder, 'privilege_log_profiles', json.dumps(migrated_profile))
```

---

## DEPENDENCY_MAP.md Update

Add to case_settings section:
```
| `privilege_log_profiles` | 5_Production.py (Priv Log tab) | 5_Production.py (Priv Log tab) | JSON object with named export profiles (column selection, headers, merge rules). Per-case. Replaces old `privilege_log_columns` key. |
```

---

## CHANGELOG Entries

```
- FIX: 5_Production.py — Privilege Log query now uses privilege_status column (Withhold/Redact) instead of tag membership; fixes zero-result bug when documents have dispositions but no literal "Privileged" tag
- FIX: 5_Production.py — Privilege Log tab restructured: auto-loads on tab open instead of requiring Generate button click; data persisted in session state to survive filter interactions
- FIX: 5_Production.py — Privilege Log tab wrapped in error handler to surface rendering failures
- CHANGE: 5_Production.py — Privilege Log "Generate" button replaced with "Refresh" button; auto-refreshes when basis override or needs-review toggle changes
- FIX: 5_Production.py — Privilege Log audit logging moved to query-time only (prevents duplicate log entries on every filter interaction)
- NEW: 5_Production.py — Export Profiles for privilege log: named column configurations with custom headers, column merging, and per-case persistence
- NEW: 5_Production.py — "Individuals Involved" merge column: combines From/To/CC with email address stripping and deduplication
- NEW: 5_Production.py — Disposition-aware Bates formatting: Withheld docs show full range, Redacted docs show only specific redacted page Bates numbers
- NEW: 5_Production.py — Builtin "EDRM Standard" profile; users can create, save, and switch between named export profiles per case
- NEW: 5_Production.py — Column reordering with up/down arrow buttons in export profile editor
- NEW: 5_Production.py — Live export preview table below profile editor; updates immediately on column/order/header changes
```

---

## Testing Checklist

```
### Query Fix
[ ] Documents with privilege_status='Redact' appear on the privilege log
[ ] Documents with privilege_status='Withhold' appear on the privilege log
[ ] Documents without privilege_status do NOT appear (unless "Include Needs Review" is checked)
[ ] Tags are used for Privilege Basis column, NOT for log membership
[ ] "Include Needs Review" adds undispositioned docs tagged "Needs Review"

### Auto-Load & Session State
[ ] Tab loads and shows privilege log data immediately (no button click required)
[ ] Changing a filter (disposition, custodian, date range) does NOT blank the grid
[ ] Clicking "Refresh" re-queries and shows updated data
[ ] Changing the basis override auto-refreshes the data
[ ] Toggling "Include Needs Review" auto-refreshes the data
[ ] Empty case (no privileged docs) shows info message, not a blank tab
[ ] Error state shows error message with expandable traceback, not a blank tab
[ ] Switching cases clears and reloads correct privilege log data
[ ] Audit log entries only created on initial load or refresh, not on filter changes

### Export Profiles
[ ] EDRM Standard profile loads by default when no saved profiles exist
[ ] Switching profiles changes the export column configuration
[ ] New profile creation works (name input, column picker, save)
[ ] Profile save requires production permission — reviewers cannot save
[ ] Profile save blocked on closed cases
[ ] Old privilege_log_columns config migrated to new format gracefully
[ ] Deleting a non-builtin profile works (with confirmation)
[ ] Cannot delete the EDRM Standard builtin profile

### Column Reordering
[ ] Up arrow moves column one position higher in export order
[ ] Down arrow moves column one position lower
[ ] Up arrow disabled on first column, down arrow disabled on last
[ ] Reordering persists when profile is saved
[ ] Export CSV/Excel reflects the reordered column sequence

### Export Preview
[ ] Preview table appears below the column picker
[ ] Preview updates immediately when columns are added/removed
[ ] Preview updates immediately when columns are reordered
[ ] Preview updates when column headers are renamed
[ ] Preview shows merged columns (Individuals Involved, Bates Range) correctly
[ ] Preview shows first ~10 rows (not entire dataset)
[ ] Downloaded CSV/Excel matches the preview exactly

### Merged Columns
[ ] "Individuals Involved" merge: From/To/CC combined, emails stripped, comma-separated
[ ] Deduplication: same name appearing in From and CC only shows once
[ ] Names-only extraction: "John Smith <john@example.com>" → "John Smith"
[ ] Bare emails preserved: "john@example.com" (no display name) → "john@example.com"

### Bates Formatting
[ ] Withheld doc with Bates: shows single Bates number (slip sheet = 1 page)
[ ] Redacted doc with Bates: shows only redacted pages' Bates numbers
[ ] Redacted doc not yet produced: shows "(not yet produced — N pages redacted)"
[ ] Needs Disposition doc: shows "(not yet produced)" or begdoc if exists

### Export
[ ] CSV export respects active profile (correct