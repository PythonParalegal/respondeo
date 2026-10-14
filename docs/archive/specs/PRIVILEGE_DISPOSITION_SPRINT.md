# Sprint: Privilege Disposition Defensibility Chain

**Date:** 2026-04-15  
**Branch:** `beta-2.9`  
**Scope:** Three connected fixes forming a single defensibility story: privilege tagging → disposition → production filtering.

---

## Background

Privilege disposition in Respondeo has three paths into the system:

1. **Individual tagging** (Review pane 3, ~line 4813) — privilege category tags trigger a Withhold/Redact radio. Works correctly but defaults to Redact regardless of context.
2. **Bulk tagging** (Review bulk form, ~line 3068) — applies tags to N documents but **never sets `privilege_status`**. Documents end up with privilege tags and NULL disposition.
3. **Redaction mark sync** (`_r_sync_tags()`, ~line 3454) — auto-sets disposition to Redact when marks exist, never overwrites Withhold. Works correctly.

The production module (~line 2688) detects privilege-tagged documents without disposition but only issues a soft warning — documents still produce normally, risking inadvertent privilege waiver.

---

## Fix 1: Bulk Tag Privilege Disposition Prompt

**File:** `pages/4_Review.py`  
**Location:** Bulk tag form, lines 3068–3138  
**Problem:** `_bulk_apply_op()` only updates the `tags` column. No privilege disposition is prompted or set.

### Spec

When the user selects a tag in the bulk form's selectbox (`bulk_tag_apply_select`, line 3072), check whether it belongs to a privilege category. If yes, render a disposition radio **inline in the form**, between the selectbox and the action buttons.

#### Implementation steps:

1. **After the selectbox** (after line 3077), determine if `chosen_tag` is a privilege tag:
   ```python
   _is_priv_tag = any(
       chosen_tag in cat_data.get('members', [])
       for cat_data in _bulk_cats.values()
       if cat_data.get('is_privilege')
   )
   ```

2. **Conditionally render disposition radio** (between selectbox and action buttons):
   ```python
   _bulk_disp_choice = None
   if _is_priv_tag and chosen_tag:
       st.markdown(
           "<span style='color:#ff6b6b; font-size:0.78em; font-weight:700; "
           "text-transform:uppercase; letter-spacing:0.08em;'>▸ Privilege Disposition</span>",
           unsafe_allow_html=True
       )
       _bulk_disp_options = [
           "Withhold (exclude from production)",
           "Redact (produce with redactions)"
       ]
       _bulk_disp_choice = st.radio(
           "Bulk Privilege Disposition",
           options=_bulk_disp_options,
           index=0,  # Withhold is default for bulk (document-level determination)
           label_visibility="collapsed",
           key="bulk_priv_disp_radio"
       )
   ```
   Note: **Default is Withhold (index 0)** because bulk tagging is a document-level determination — no redaction marks are being applied, so the safer default is to exclude from production entirely.

3. **Conflict detection — BEFORE applying** (after `btn_apply` and the tag/empty guards, around line 3112). When the chosen tag is a privilege tag, scan for existing disposition conflicts before executing:

   ```python
   # Detect disposition conflicts before applying
   _conflict_cns = []
   _unset_cns = []
   if _is_priv_tag and _bulk_disp_choice:
       _disp_val = 'Withhold' if 'Withhold' in _bulk_disp_choice else 'Redact'
       for cn in bulk_cns:
           _existing = db_manager.get_privilege_status(case_folder, cn)
           if _existing is None:
               _unset_cns.append(cn)
           elif _existing != _disp_val:
               _conflict_cns.append((cn, _existing))
           # else: already matches, no-op
   ```

4. **Conflict-resolution UI** — If conflicts exist, present three options before executing. This surfaces the conflict explicitly so the user makes an informed choice. Use a session-state flag to gate the actual apply:

   **Scenario analysis driving this design:**
   - **No disposition → bulk sets Withhold/Redact:** Simple, no conflict. Applied directly.
   - **Has Redact (with marks) → bulk wants Withhold:** Legitimate workflow — attorney decides to escalate from partial redaction to full withhold. Marks become irrelevant (slip sheet replaces doc) but are harmless in the DB.
   - **Has Withhold → bulk wants Redact:** Attorney previously withheld, now decides to produce with redactions instead. Less common but valid. Should be an intentional, acknowledged override.
   - **Key principle:** Both direction changes (Redact→Withhold and Withhold→Redact) are legitimate attorney decisions. We must not silently block *or* silently apply either one. Surface the conflict, let the user decide.

   ```python
   if _conflict_cns:
       st.warning(
           f"⚠️ **Disposition conflict:** {len(_conflict_cns)} of {len(bulk_cns)} "
           f"selected document(s) already have a different disposition:\n\n"
           + "\n".join(f"- **{cn}**: currently {disp}" for cn, disp in _conflict_cns[:10])
           + (f"\n- ...and {len(_conflict_cns) - 10} more" if len(_conflict_cns) > 10 else "")
       )
       _resolve_cols = st.columns(3)
       _btn_override = _resolve_cols[0].form_submit_button(
           f"Override All → {_disp_val}", type="primary"
       )
       _btn_skip = _resolve_cols[1].form_submit_button(
           f"Apply to {len(_unset_cns)} Unset Only"
       )
       _btn_conflict_cancel = _resolve_cols[2].form_submit_button("Cancel")
   ```

   **Important Streamlit constraint:** All `form_submit_button` calls must be inside the `st.form()` block. Since the conflict buttons are additional submit buttons within the same form, only one can fire per form submission. The flow is:
   - **First submit** (user clicks "Apply Tag"): detects conflicts, rerenders form with conflict buttons visible. Use `st.session_state` to persist conflict detection across reruns.
   - **Second submit** (user clicks Override All / Apply Unset Only / Cancel): executes the chosen resolution.
   
   Recommended session state keys:
   - `_bulk_priv_conflicts`: list of `(cn, existing_disp)` tuples
   - `_bulk_priv_unset`: list of unset cns
   - `_bulk_priv_disp_val`: the chosen disposition value
   - `_bulk_priv_pending`: boolean flag indicating conflict resolution is pending

   **Alternative (simpler, if the two-submit Streamlit pattern is too complex):** Skip the second-submit pattern entirely. Instead, always show the three options inline when a privilege tag is selected and conflicts are detected on form load. Pre-scan dispositions when the bulk form renders (not on submit), so the user sees the conflict information *before* clicking anything. This avoids the rerun complexity.

5. **Inside `_bulk_apply_op()`** (after tag update, around line 3124), set disposition with conflict resolution applied:
   ```python
   # After the tag UPDATE executes for each cn:
   if _is_priv_tag and _bulk_disp_choice:
       _disp_val = 'Withhold' if 'Withhold' in _bulk_disp_choice else 'Redact'
       _old_priv = db_manager.get_privilege_status(case_folder, cn)
       
       # Conflict resolution: skip if user chose "Apply to Unset Only" and doc has disposition
       if _apply_mode == 'unset_only' and _old_priv is not None:
           continue  # or skip this cn's disposition update
       
       if _old_priv != _disp_val:
           db_manager.set_privilege_status(case_folder, cn, _disp_val)
           _bulk_audit.append({
               "action": "PRIVILEGE_DISPOSITION_CHANGED",
               "username": _username,
               "control_number": cn,
               "module": "Review",
               "details": f"bulk_tag_apply ({'override' if _old_priv else 'initial'})",
               "old_value": _old_priv or 'NULL',
               "new_value": _disp_val
           })
   ```

   The `details` field distinguishes between initial assignments and overrides for audit clarity.

6. **Do NOT change** the existing `btn_clear` logic (line 3140+). Clearing tags does not clear disposition — that's a separate action. This matches the individual path where removing privilege tags only clears disposition if no redaction marks exist (line 4966-4981). If we want bulk clear to also clear disposition, that's a separate decision — for now, be conservative.

### Audit trail

Every document that gets a disposition change via bulk tagging gets its own `PRIVILEGE_DISPOSITION_CHANGED` audit entry with `details` indicating whether it was an initial assignment or an override:
- `"bulk_tag_apply (initial)"` — disposition was NULL, now set
- `"bulk_tag_apply (override)"` — disposition was changed from a different value

This makes it trivial to audit-search for "which documents had their attorney disposition overridden by a bulk operation."

---

## Fix 2: Context-Aware Default Disposition Direction

**File:** `pages/4_Review.py`  
**Location:** Individual privilege disposition radio, lines 4819–4828  
**Problem:** Default is always Redact (index 0) unless previously set to Withhold. Should be context-aware.

### Spec

Change the default index logic at line 4821 to consider whether redaction marks exist on the document:

#### Current code (line 4821):
```python
_default_disp_idx = 1 if _current_priv_status == 'Withhold' else 0
```

#### New code:
```python
# Preserve existing disposition if set; otherwise context-aware default:
# - Redaction marks exist → Redact (marks need to be burned)
# - No marks (document-level tag) → Withhold (safer default)
if _current_priv_status == 'Withhold':
    _default_disp_idx = 1  # Withhold
elif _current_priv_status == 'Redact':
    _default_disp_idx = 0  # Redact
else:
    # First time setting disposition — context-aware default
    _has_marks = db_manager.has_redaction_marks(case_folder, current_cn)
    _default_disp_idx = 0 if _has_marks else 1  # Redact if marks, Withhold if not
```

**Note:** The disposition options order is:
- Index 0: `"Redact (produce with redactions)"`
- Index 1: `"Withhold (exclude from production)"`

#### Scope guard

This only changes the **default selection** for documents that have **no existing disposition** (`_current_priv_status is None`). Documents that already have a disposition preserve their existing value — the reviewer's prior decision is never overridden.

#### Also applies to Fix 1

The bulk form (Fix 1) already defaults to Withhold because bulk tagging is inherently a document-level determination. But if we want to be truly context-aware there too, we could check whether *any* of the bulk-selected documents have redaction marks and warn the user. However, this adds complexity for an edge case (bulk-tagging documents that already have marks) — recommend keeping bulk default as Withhold and noting this as a future enhancement if needed.

---

## Fix 3: Production Hard Block for Missing Disposition

**File:** `pages/5_Production.py`  
**Location:** Pre-production privilege check, lines 2688–2706  
**Problem:** Privilege-tagged documents without disposition get a soft warning but still produce normally.

### Spec

Convert the soft warning to a **hard block** (`st.stop()`), matching the pattern already used for the "Redact disposition but no marks" check at lines 2673–2686.

#### Current code (lines 2699–2706):
```python
if _no_disp_cns:
    st.warning(
        f"⚠️ {len(_no_disp_cns)} document(s) have privilege tags but no disposition set. "
        f"These will be produced normally (no withholding, no redaction burn). "
        f"If this is intentional, proceed. Otherwise, return to Review and set dispositions.\n\n"
        f"**Affected:** {', '.join(_no_disp_cns[:10])}"
        f"{'...' if len(_no_disp_cns) > 10 else ''}"
    )
```

#### New code:
```python
if _no_disp_cns:
    st.error(
        f"🚫 **Production blocked:** {len(_no_disp_cns)} document(s) have privilege tags "
        f"but no disposition (Withhold/Redact). Producing these documents without a "
        f"privilege disposition decision risks inadvertent privilege waiver.\n\n"
        f"**Affected documents:** {', '.join(_no_disp_cns[:10])}"
        f"{'...' if len(_no_disp_cns) > 10 else ''}\n\n"
        f"Return to the Review module and set a disposition for each "
        f"privilege-tagged document, or remove the privilege tags if they "
        f"were applied in error."
    )
    st.stop()
```

This uses `st.error()` + `st.stop()` — the same pattern as the existing "Redact with no marks" hard block at line 2673–2686. Production cannot proceed until every privilege-tagged document has an explicit disposition decision.

### Why hard block, not soft gate

A soft gate with an override checkbox creates the appearance of choice where there shouldn't be one. If a document has a privilege tag, someone determined it's privileged. Producing it without deciding whether to withhold or redact is never the right answer — it's always either a mistake (forgot to set disposition) or a tag error (shouldn't have been tagged). Both should be resolved in Review, not waved through in Production.

---

## Do NOT Change

- `_r_sync_tags()` (line 3454) — mark-sync logic is correct. It auto-sets Redact when marks exist and never overwrites Withhold.
- `btn_clear` bulk clear logic (line 3140) — clearing tags does not clear disposition; that's consistent with the individual path's safeguard at line 4966-4972.
- The privilege log queries in Production Tab 3 (~line 3772) — these already filter on `privilege_status IN ('Withhold', 'Redact')` and are unaffected.
- `db_manager.get_privilege_status()`, `set_privilege_status()`, `has_redaction_marks()`, `get_privilege_tag_members()` — all existing db functions are sufficient; no new db functions needed.

---

## Version Tracking

| File | Change Type | Version Bump |
|------|-------------|-------------|
| `pages/4_Review.py` | Bug fix (bulk disposition gap) + behavior change (default direction) | Patch bump |
| `pages/5_Production.py` | Behavior change (soft warning → hard block) | Patch bump |

---

## CHANGELOG Entries

```
- FIX: 4_Review.py — bulk privilege tagging now prompts for Withhold/Redact disposition inline
- CHANGE: 4_Review.py — individual privilege disposition defaults to Withhold when no redaction marks exist (context-aware)
- CHANGE: 5_Production.py — privilege-tagged documents without disposition now hard-block production instead of soft warning
```

---

## Verification Checklist

After implementation, verify:

- [ ] **Bulk tag a privilege tag on 3+ docs (all unset)** → disposition radio appears, Withhold default, choice applied to all, audit shows `bulk_tag_apply (initial)` for each
- [ ] **Bulk tag a privilege tag — mixed dispositions** → conflict warning appears, shows Override All / Apply to Unset Only / Cancel
- [ ] **Bulk conflict: Override All** → all documents get the new disposition, audit shows `bulk_tag_apply (override)` for changed docs
- [ ] **Bulk conflict: Apply to Unset Only** → only NULL-disposition docs get updated, already-set docs untouched
- [ ] **Bulk conflict: Cancel** → no changes, form resets
- [ ] **Bulk tag a non-privilege tag** → no disposition radio appears, behavior unchanged
- [ ] **Individual tag: add privilege tag to doc WITH redaction marks** → default is Redact
- [ ] **Individual tag: add privilege tag to doc WITHOUT marks** → default is Withhold
- [ ] **Individual tag: doc already has disposition set** → radio preserves existing choice regardless of marks
- [ ] **Production: include a privilege-tagged doc with NULL disposition** → hard block, cannot produce
- [ ] **Production: all privilege-tagged docs have disposition** → no block, proceeds normally
- [ ] **Closed case** → bulk disposition radio still respects "Write operations disabled" guard (line 3108)
- [ ] **`_r_sync_tags` still works** → drawing redaction marks auto-sets Redact, removing marks clears to NULL (unless Withhold)

---

## Cross-Module Impact

This sprint touches two files and no database schema changes. Impact is contained:

- **`privilege_status` column** — no schema change, just ensuring it gets populated in a path that previously skipped it
- **Session state** — one new key: `bulk_priv_disp_radio` (form-scoped, no persistence concerns)
- **Audit trail** — new `details` value `"bulk_tag_apply"` on existing `PRIVILEGE_DISPOSITION_CHANGED` action; no schema change
- **DEPENDENCY_MAP.md** — no update needed (no new cross-module dependencies)
