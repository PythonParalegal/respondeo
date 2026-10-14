# User Profile Preferences — Feature Spec

**Status:** Specced, not implemented
**Priority:** MEDIUM — Quality-of-life enhancement for review workflow
**Estimated effort:** Half-sprint (1 session)
**Files affected:** `auth_manager.py`, `pages/4_Review.py`, `home.py`, `auth_config.yaml`
**Prerequisite:** None — can be scheduled independently

---

## Problem Statement

The Review grid's "Configure Columns" picker (`column_picker` permission, Manager+) stores selections in `st.session_state["review_grid_columns"]`. When a session ends (tab close, timeout, reconnect), column preferences reset to `DEFAULT_COLS`. Users who have built a workflow around specific column layouts must reconfigure every session.

Additionally, the `column_picker` permission is currently Manager+ only. Reviewers doing privilege review need different visible columns than reviewers doing responsiveness coding. Forcing a manager to toggle columns on behalf of reviewers creates friction and doesn't scale.

## Design Decisions

### 1. Scope — Column Layout Only (Extensible)

The initial implementation covers **Review grid column preferences only**. The `save_user_pref()`/`get_user_pref()` API is generic key-value, so future preferences (default sort order, items per page, filter defaults, sidebar state) can be added without rearchitecting.

Initial preference key:

| Key | Type | Description |
|-----|------|-------------|
| `review_columns` | `list[str]` | Ordered list of column names for the Review grid |

### 2. Storage — auth_config.yaml (Global Across Cases)

Preferences are stored under each user's entry in `auth_config.yaml` via the existing `save_user_pref()` function. This means preferences are **global across all cases**, which is the right default — a reviewer's preferred workflow layout doesn't typically change from matter to matter.

Example YAML after a user saves column preferences:

```yaml
users:
  BWoessner:
    name: BAW
    password_hash: $2b$12$...
    role: reviewer
    last_case: D:\eDiscovery\Test(small)
    preferences:
      review_columns:
        - control_number
        - begdoc
        - file_name
        - custodian
        - date_sent
        - email_subject
        - tags
        - privilege_status
```

**Note:** The current `save_user_pref()` writes keys flat on the user dict (e.g., `last_case`). This spec nests preferences under a `preferences` sub-key for cleanliness. The implementation must update `save_user_pref()` and add `get_user_pref()` accordingly.

### 3. Two-Tier Permission Model

The feature introduces a separation between **pool control** and **personal customization**:

| Capability | Permission | Who | What it controls |
|---|---|---|---|
| Define allowed column pool | `column_picker` | Manager+ (existing) | Which columns are available to any user on this case. Retains the existing Configure Columns expander. |
| Personalize own layout | `personalize_columns` (new) | Reviewer+ | Pick from the allowed pool and save as personal default. |

**Why two tiers:** Some columns carry access implications (e.g., `privilege_status`, `production_volume`, work product fields). Managers retain control over what's *available*. Reviewers control what they *see* within that pool.

**Pool enforcement:** When a user's saved preferences contain columns that are no longer in the allowed pool (because a manager removed them), the load step silently filters them out. No error — the column just doesn't appear.

### 4. Profile Sets Default, Session Overrides

The user's saved preference sets what they **start** each session with. Any in-session changes via the column picker widget override during that session only. This preserves the existing UX while adding persistence.

Flow:

```
Session start
  → Load user's saved review_columns from auth_config.yaml
  → If none saved, fall back to DEFAULT_COLS
  → Write to st.session_state["review_grid_columns"]
  → User makes in-session changes (existing behavior, unchanged)
  → Explicit "💾 Save as My Default" button persists current selection
```

---

## Implementation Plan

### Part 1: auth_manager.py — Complete the Preference API

```
1. Modify save_user_pref() to nest under 'preferences' sub-key:
   config['users'][username].setdefault('preferences', {})[key] = value

2. Add get_user_pref(username, key, default=None):
   return config['users'][username].get('preferences', {}).get(key, default)

3. Backward compatibility: existing flat keys (last_case, doc_visibility)
   remain flat. Only new preferences go under 'preferences'.
   save_user_pref() checks: if key in ('last_case', 'doc_visibility', ...),
   write flat (existing behavior). Otherwise, write under 'preferences'.
```

### Part 2: auth_manager.py — Add `personalize_columns` Permission

```
4. Add 'personalize_columns' to ALL_PERMISSIONS list (in the Review group)

5. Add 'personalize_columns' to _DEFAULT_PERMISSIONS:
   - admin: already has '*'
   - manager: add to set
   - reviewer: add to set

6. auth_config.yaml will pick it up on next permission save, or use
   hardcoded default until then (zero-downtime pattern)
```

### Part 3: 4_Review.py — Load Saved Preferences on Session Init

```
7. At the existing session_state init block (current line ~2294):

   if "review_grid_columns" not in st.session_state:
       _username = st.session_state.get("username", "")
       _saved_cols = auth_manager.get_user_pref(_username, "review_columns")
       if _saved_cols and isinstance(_saved_cols, list):
           # Filter against allowed pool (ALL_GRID_COLUMNS keys)
           _valid = [c for c in _saved_cols if c in ALL_GRID_COLUMNS]
           st.session_state["review_grid_columns"] = _valid or DEFAULT_COLS
       else:
           st.session_state["review_grid_columns"] = DEFAULT_COLS
```

### Part 4: 4_Review.py — Personal Save Button

```
8. Inside the Configure Columns expander, after the existing Reset button:

   # permission: personalize_columns
   if auth_manager.has_permission('personalize_columns'):
       if st.button("💾 Save as My Default", width='stretch'):
           auth_manager.save_user_pref(
               st.session_state["username"],
               "review_columns",
               st.session_state["review_grid_columns"]
           )
           st.success("Column layout saved as your default.")

9. Also add a "🗑️ Clear My Default" button that removes the saved pref:
   auth_manager.save_user_pref(username, "review_columns", None)
   → get_user_pref returns None → falls back to DEFAULT_COLS on next session
```

### Part 5: Column Picker Visibility for Reviewers

```
10. Currently the entire Configure Columns expander is gated behind
    column_picker (Manager+). Split this into two sections:

    a. Manager section (column_picker permission):
       - Full multiselect from ALL_GRID_COLUMNS (existing behavior)
       - Reset to Default button (existing)
       - This controls what everyone sees in the current session

    b. Personal section (personalize_columns permission):
       - Shows current active columns (read-only display or reorder-only)
       - "💾 Save as My Default" button
       - "🗑️ Clear My Default" button
       - If user does NOT also have column_picker, they can only save/clear
         their default — they cannot change columns in the current session
         unless a manager has already opened the picker

    Design note: Reviewers with personalize_columns but NOT column_picker
    see a simplified expander: their saved layout loads automatically,
    and the save/clear buttons let them persist whatever a manager configured.
    If they also have column_picker, they get the full picker + save.
```

---

## Audit Trail

| Event | Logged When | Details |
|---|---|---|
| `USER_PREF_SAVED` | User saves column layout | `username`, `key=review_columns`, `new_value=<column list>` |
| `USER_PREF_CLEARED` | User clears saved layout | `username`, `key=review_columns` |

These are low-volume, non-case-specific events. Log via `log_audit()` with `module='home'` (preference is global, not case-scoped).

---

## Edge Cases

1. **User has saved columns that no longer exist** (e.g., a column was removed from `ALL_GRID_COLUMNS` in a code update): Filter silently on load; invalid column names are dropped.

2. **Manager restricts column pool after user saved preferences**: Same silent filter — user's saved list is intersected with `ALL_GRID_COLUMNS` on load.

3. **No case selected yet**: Column preferences load from YAML before any case context. This is fine — the preference is case-independent.

4. **Multiple sessions**: If a user has two browser tabs open and saves in one, the other tab continues with its in-session state until refresh. No conflict — YAML is source of truth for *next* session only.

5. **Custom roles**: `personalize_columns` can be granted or denied independently per custom role. An `expert` role might get it; a `contract_reviewer` might not.

---

## What This Does NOT Include (Future Extensions)

These are natural follow-ons but are explicitly out of scope for this sprint:

- Per-case column preferences (store in case_settings instead of auth_config)
- Default sort order preference
- Items-per-page preference
- Filter preset saving (distinct from saved searches)
- Review grid theme/density preference
- Manager-imposed column *restrictions* per role (enforced pool beyond what's in ALL_GRID_COLUMNS)

The `get_user_pref()`/`save_user_pref()` API supports all of these — the investment here is the infrastructure, not just the column feature.

---

## Testing Checklist

```
[ ] Reviewer login → no saved pref → DEFAULT_COLS loads
[ ] Manager configures columns → reviewer saves as default → logout → login → saved columns load
[ ] Saved columns include a removed column → loads without error, invalid column dropped
[ ] Clear My Default → next session falls back to DEFAULT_COLS
[ ] Expert role with personalize_columns → can save; without it → no save button
[ ] Two concurrent sessions: save in one, other unaffected until refresh
[ ] auth_config.yaml: preferences nested under 'preferences' key, not flat
[ ] Audit log: USER_PREF_SAVED and USER_PREF_CLEARED events recorded
```
