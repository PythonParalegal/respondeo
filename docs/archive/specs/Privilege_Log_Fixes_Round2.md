# Privilege Log Fixes — Round 2

**Date:** 2026-04-01
**Priority:** HIGH — Three bugs + two missing features from spec
**Branch:** `beta-2.9`
**Files affected:** `5_Production.py`

---

## Bug 1: Description column says "withheld" for ALL documents

**Line:** 3638
**Current:** `'description': f"Document withheld on grounds of privilege: {r['file_name']}"`
**Problem:** This hardcoded text is used for every row, including Redact documents. "Withheld" is wrong for documents that were produced with redactions.

**Fix:** Make the description disposition-aware:

```python
# Replace line 3638 with:
if _pl_disp_key == 'Withhold':
    _pl_desc = f"Document withheld on grounds of privilege: {r['file_name']}"
elif _pl_disp_key == 'Redact':
    _pl_desc = f"Produced with redactions on grounds of privilege: {r['file_name']}"
else:
    _pl_desc = f"Privilege review pending: {r['file_name']}"

# Then in the row dict:
'description': _pl_desc,
```

---

## Bug 2: Redaction mark reasons not populating (SQLite version)

**Lines:** 3587-3595
**Root cause:** The SQL subquery uses the `->>` JSON operator (`json_each.value ->> 'reason'`), which requires SQLite 3.38+. The maintainer's environment runs **SQLite 3.37.2**. The `->>` silently fails and returns NULL for every document, so Tier 1 of `_pl_resolve_privilege_basis` never fires.

**Fix:** Replace the `->>` operator with the `json_extract()` function, which has been available since SQLite 3.9.0 (2015):

```sql
-- Replace lines 3587-3595 with:
(SELECT GROUP_CONCAT(DISTINCT reason_val)
 FROM (
   SELECT json_extract(json_each.value, '$.reason') AS reason_val
   FROM redaction_marks rm2, json_each(rm2.marks_json)
   WHERE rm2.control_number = d.control_number
     AND json_extract(json_each.value, '$.reason') IS NOT NULL
     AND json_extract(json_each.value, '$.reason') != '[Redact — No Privilege Reason]'
 )
) AS mark_reasons
```

The `json_extract(value, '$.reason')` function does the same thing as `value ->> 'reason'` but works on SQLite 3.9+.

**Also:** The `_pl_fuzzy_match_privilege_reason` function (line 3421) still has `return 'Attorney-Client Privilege'` as its final fallback. Now that Tier 1 should work, this fallback will only fire for Withhold documents that have tags but no matching abbreviation. However, per the spec, the Tier 2 fallback should ALSO return `'(No basis specified)'` when it doesn't match anything in the abbreviation map, instead of blindly guessing Attorney-Client. **Change line 3421 from:**

```python
return 'Attorney-Client Privilege'
```

**To:**

```python
return '(No basis specified)'
```

This way the only paths that produce "Attorney-Client Privilege" are: (1) the override dropdown, (2) an actual tag match against the abbreviation map, or (3) the "Attorney-Client" substring check on line 3415. Never a blind default.

---

## Bug 3: Mixed-type Arrow serialization (Page Count)

**Lines:** 3649-3650
**Already in spec Part 1h.** Change `''` to `None` for missing numeric values:

```python
'page_count':      int(r['page_count']) if pd.notna(r['page_count']) else None,
'redaction_pages': int(r['redacted_page_count']) if pd.notna(r['redacted_page_count']) and r['redacted_page_count'] > 0 else None,
```

---

## Missing Feature 1: Column reordering (up/down arrows)

**Not implemented in last sprint.** The spec (Part 2b) calls for ⬆️/⬇️ buttons next to each selected column to reorder the export column sequence.

**Implementation approach:**

Store column order in session state as a list. For each column, render a row with position number, up/down buttons, the column display name, a header rename text input, and a remove button.

```python
# After the column multiselect, add a reorder section:
st.markdown("**Column Order** *(drag to reorder is not supported — use arrows)*")

_pl_col_order = st.session_state.get(f"pl_col_order_{_pl_case_id}", list(_pl_export_cols))
# Sync with multiselect (add new, remove deselected)
_pl_col_order = [c for c in _pl_col_order if c in _pl_export_cols]
for c in _pl_export_cols:
    if c not in _pl_col_order:
        _pl_col_order.append(c)
st.session_state[f"pl_col_order_{_pl_case_id}"] = _pl_col_order

for i, col_key in enumerate(_pl_col_order):
    _oc1, _oc2, _oc3, _oc4 = st.columns([0.5, 0.5, 3, 0.5])
    if _oc1.button("⬆️", key=f"pl_up_{col_key}", disabled=(i == 0)):
        _pl_col_order[i], _pl_col_order[i-1] = _pl_col_order[i-1], _pl_col_order[i]
        st.session_state[f"pl_col_order_{_pl_case_id}"] = _pl_col_order
        st.rerun()
    if _oc2.button("⬇️", key=f"pl_dn_{col_key}", disabled=(i == len(_pl_col_order) - 1)):
        _pl_col_order[i], _pl_col_order[i+1] = _pl_col_order[i+1], _pl_col_order[i]
        st.session_state[f"pl_col_order_{_pl_case_id}"] = _pl_col_order
        st.rerun()
    _oc3.write(f"{i+1}. {_PL_COL_KEY_TO_DISPLAY.get(col_key, col_key)}")
```

**Use `_pl_col_order` instead of `_pl_export_cols`** when building the export DataFrame and the preview.

---

## Missing Feature 2: Live export preview table

**Not implemented in last sprint.** The spec (Part 2b) calls for a preview `st.dataframe()` below the profile editor that shows first ~10 rows using the current profile settings.

**Implementation:**

```python
# After the column picker/reorder UI, before the download buttons:
st.subheader("Export Preview")
st.caption(f"Showing first 10 of {len(_pl_export_df)} rows with current column settings.")
st.dataframe(_pl_export_df.head(10), hide_index=True, use_container_width=True)
```

The preview should use the same DataFrame that the download buttons use (`_pl_export_df`), so the preview is guaranteed to match the actual export. It should reflect:
- Current column selection
- Current column order (from the reorder UI)
- Current header renames
- Merged columns (Individuals Involved, Bates Range)

---

## CHANGELOG entries

```
- FIX: 5_Production.py — Privilege Log description column now disposition-aware: "Produced with redactions" for Redact, "Document withheld" for Withhold
- FIX: 5_Production.py — Privilege Log mark_reasons SQL uses json_extract() instead of ->> operator (fixes SQLite 3.37 compatibility)
- FIX: 5_Production.py — Privilege basis fuzzy match no longer defaults to "Attorney-Client Privilege"; shows "(No basis specified)" when no basis can be determined
- FIX: 5_Production.py — Page Count and Redacted Pages columns use None for missing values (fixes Arrow serialization warnings)
- NEW: 5_Production.py — Column reordering with ⬆️/⬇️ buttons in privilege log export profile editor
- NEW: 5_Production.py — Live export preview table shows first 10 rows with current profile settings
```

---

## Testing Checklist

```
[ ] Redact documents show "Produced with redactions on grounds of privilege: ..." in Description
[ ] Withhold documents show "Document withheld on grounds of privilege: ..." in Description
[ ] Redaction mark reasons now populate in Privilege Basis column (e.g., "Privacy - Insurance Information")
[ ] Documents with no mark reasons and no matching tags show "(No basis specified)"
[ ] Arrow serialization warnings no longer appear in terminal
[ ] Column reorder arrows move columns up/down in export order
[ ] Export preview table appears below profile editor
[ ] Preview updates when columns are reordered or changed
[ ] Downloaded CSV/Excel matches preview
```
