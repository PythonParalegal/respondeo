# BUG: Save Button Clears privilege_status When No Privilege Tags Selected

**Severity:** HIGH — Data integrity / production defensibility
**Found during:** Production Categories sprint testing
**File:** `pages/4_Review.py`, lines ~4847–4869
**Two related issues:** Widget pre-population failure + destructive save logic

---

## Symptoms

1. Document has `privilege_status = 'Redact'` and active redaction marks (visible in Redaction Summary)
2. User opens document in Review detail pane — **Privilege, Responsiveness, and Review Status dropdowns all load as empty ("Choose options")** despite the document having tags/status in the database
3. User sets Production Category to "Insurance," clicks Save
4. User did NOT touch any privilege tags or the disposition radio
5. After save, `privilege_status` is cleared to NULL — the Privilege Disposition column in the grid goes blank
6. Redaction marks still exist in `redaction_marks` table, but the document no longer shows as having a privilege disposition
7. To restore, user must re-open the document, go to the Redact tab, and re-save tags to re-apply the redaction status

## Root Cause

The save handler (lines ~4847–4869) uses this logic:

```python
_priv_tags_on_doc = [t for t in selected_tags if t.lower() in privilege_tag_members]

if _priv_tags_on_doc:
    # Set privilege_status based on disposition radio
    _new_disp = 'Withhold' if 'Withhold' in _disposition_choice else 'Redact'
    ...
else:
    # No privilege tags remain — clear disposition
    _old_disp = db_manager.get_privilege_status(case_folder, _ts_cn)
    if _old_disp is not None:
        db_manager.set_privilege_status(case_folder, _ts_cn, None)  # <-- BUG
```

The `else` branch assumes "no privilege tags selected in the form = user wants to clear privilege status." This is incorrect. The user may not have interacted with the privilege dropdowns at all — they may have only changed Production Category, Confidentiality, or other fields.

## Secondary Issue

The privilege disposition radio button (`_disposition_choice`) is only rendered when privilege tags are selected in the form (line ~4699). If `_priv_tags_on_doc` is truthy but the radio was never rendered (because the user didn't select tags during this session — they were pre-existing in the DB but not re-selected in the widget), accessing `_disposition_choice` could raise a NameError.

## Two Related Issues

### Issue A — Widget Pre-Population Failure

The Privilege, Responsiveness, and Review Status multiselect dropdowns do NOT pre-populate with the document's existing tags when the detail pane loads. They all show "Choose options" even when the document has tags in the database. This means:
- The form does not reflect the current state of the document
- Any Save action sends empty selections for those fields
- This is the primary trigger for Issue B

**Fix:** When building the detail pane for a selected document, parse the document's current `tags` field from the database, match each tag against the tag category definitions, and set the `default` parameter on each `st.multiselect` widget to the matching tags. Similarly, if the document has `privilege_status` set, pre-select the disposition radio button to match ('Redact' or 'Withhold').

### Issue B — Destructive Save Logic

Even if widgets are pre-populated, the save handler should not clear privilege_status based solely on "no privilege tags in the form."

**Fix (compare before writing — recommended):**
Before the save handler runs, read the current `tags` from the database. Only clear privilege_status if:
- The document previously HAD privilege tags AND
- The user explicitly REMOVED those privilege tags in this save (i.e., the old tags contained privilege tags, the new tags do not)

If the tags haven't changed at all, don't touch privilege_status.

**Alternative fix (dirty flag):**
Track whether the privilege multiselect widgets were actually interacted with (using `st.session_state` change tracking). Only run the privilege_status logic if the user touched those widgets.

### For either approach, also:
- Ensure the disposition radio default reflects the current DB value when privilege tags are pre-populated
- Add a guard: if `_disposition_choice` is not defined when `_priv_tags_on_doc` is truthy, read the existing disposition from DB rather than crashing

## Consumers to Check (per DEPENDENCY_MAP.md)

- `5_Production.py` — privilege_status drives slip-sheeting (Withhold) and redaction burn (Redact)
- `5_Production.py` — Privilege Log generation reads privilege_status
- `4_Review.py` — grid column display, filter row
- `db_manager.py` — `get_privilege_status()`, `set_privilege_status()`

## Reproduction Steps

1. Process a document with redactions (e.g., mark two regions for "Premium and/or deductible information")
2. Save the redactions — document should show `privilege_status = 'Redact'` and `redaction_status = 'Has_Redactions'`
3. Go back to the document grid, click on the document to open detail pane
4. Set Production Category to any value (or change Confidentiality, or any non-privilege field)
5. Click Save
6. Observe: Privilege Disposition column in grid is now empty
