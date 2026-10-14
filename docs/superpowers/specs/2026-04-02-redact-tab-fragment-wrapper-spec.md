# Redact Tab — Full Fragment Wrapper Sprint

**Date:** 2026-04-02
**Phase:** UX Performance — Redaction Workflow (follow-up to batched drawing sprint)
**Estimated complexity:** ~30 lines changed in pages/4_Review.py (structural, not logic)

---

## Problem

Despite mark buffering in React, pixmap pre-caching, batched DB saves, and the reason-panel fragment, the Redact tab still feels laggy on every interaction: initial load, page navigation (arrows and typed page number), zoom changes, and the "Load Canvas" checkbox.

The reason: **all of those interactions trigger a full-page rerun of `4_Review.py` (~5,000+ lines).** The Streamlit runtime re-executes everything before the Redact tab — the document list sidebar, metadata panel, Native/Image tab, Extracted Text tab (including OpenSearch query), and Production tab — before it even reaches the Redact code. The pixmap cache means rendering is fast once we get there, but the overhead of everything *before* it is the wall we're hitting.

The existing `@st.fragment` wrapper only covers the **reason selector panel** (lines 4153-4216). Page navigation, zoom, the checkbox, the canvas component, and the save/clear buttons are all outside any fragment, so they all trigger full-page reruns.

## Solution

Wrap the **entire Redact tab body** in a single `@st.fragment`. This means page navigation, zoom changes, the canvas checkbox, pixmap rendering, component initialization, and the reason panel all execute within a fragment-scoped rerun. The document list, metadata panel, and other tabs are skipped entirely.

## Principle

Minimize rerun scope without changing any behavior. Every feature — drawing, saving, deleting, clearing, navigation, zoom, privilege sync, audit logging — must work identically. The only change is *what code re-executes* on each interaction.

---

## Implementation

### Step 1: Define the fragment function

**File:** `pages/4_Review.py`

Wrap the entire Redact tab body (everything inside `with tabs[_tab_idx["✏️ Redact"]]:`) in a `@st.fragment` function. The fragment is defined and called inside the `if _can_redact:` block.

**Current structure** (simplified):
```python
# Line 3891
if _can_redact:
 with tabs[_tab_idx["✏️ Redact"]]:
    if not FITZ_AVAILABLE:
        st.error(...)
    elif not VIEWER_AVAILABLE:
        st.error(...)
    else:
        # ... ~480 lines of redaction logic (lines 3898-4373)
        # PDF resolution, page count, checkbox, zoom, pixmap render,
        # canvas component, control panel, reason panel (inner fragment),
        # save/clear/delete buttons, summary table
```

**Target structure:**
```python
if _can_redact:
 with tabs[_tab_idx["✏️ Redact"]]:
    if not FITZ_AVAILABLE:
        st.error(...)
    elif not VIEWER_AVAILABLE:
        st.error(...)
    else:
        @st.fragment
        def _redact_tab_fragment():
            # ... entire redaction logic moves here (unchanged)
            # All ~480 lines, including the inner reason panel fragment

        _redact_tab_fragment()
```

### Step 2: Outer-scope variable capture

The fragment function captures outer-scope variables via closure. These are all set before the tab renders and do NOT change during fragment reruns:

| Variable | Set at | Used for |
|---|---|---|
| `case_folder` | Page init | DB queries, file paths |
| `current_cn` | Document navigator | Control number for current doc |
| `full_path` | Document navigator | Native file path |
| `ext` | Document navigator | File extension |
| `row` | Document query | Document metadata dict |
| `_case_closed` | Page init | Write gate |
| `_username` | Auth | Audit logging |
| `_doc_search_terms` | Search panel | Highlight terms |
| `_can_redact` | Permission check | Already gated before fragment |
| `db_manager` | Module import | DB operations |
| `fitz` | Module import | PDF rendering |
| `_safe_write` | Helper function (line 1503) | Save/clear operations |
| `_r_write_page_annotations` | Helper function | PDF annotation writing |
| `_r_write_all_annotations` | Helper function | Clear-all annotation writing |
| `_r_sync_tags` | Helper function | Tag synchronization |
| `_REDACT_NO_REASON` | Constant | Sentinel string |
| `_REDACT_CUSTOM` | Constant | Sentinel string |
| `redaction_viewer` | Component import | React component function |
| `_highlight_page_image` | Helper function | Search term overlay |

**All of these are safe to capture** — they are either immutable (constants, imports, functions) or set once before the tab renders and not modified by the fragment.

### Step 3: Convert `st.rerun()` calls to fragment-scoped

Within the Redact tab, there are ~10 `st.rerun()` calls. Each one needs a scope decision:

| Line | Trigger | Current | Target | Reason |
|---|---|---|---|---|
| ~4110 | ◀ Prev button | `st.rerun()` | `st.rerun(scope="fragment")` | Page nav — only canvas needs refresh |
| ~4119 | Page jump text_input | `st.rerun()` | `st.rerun(scope="fragment")` | Page nav — only canvas needs refresh |
| ~4128 | ▶ Next button | `st.rerun()` | `st.rerun(scope="fragment")` | Page nav — only canvas needs refresh |
| ~4197 | 🗑 Delete mark (in reason fragment) | `st.rerun(scope="app")` | `st.rerun(scope="app")` | **Keep as-is** — delete modifies tags visible in other panels |
| ~4281 | 💾 Save Marks | `st.rerun()` | `st.rerun(scope="app")` | **Full-page** — save modifies tags, privilege status, redaction status visible in metadata panel and Tags coding |
| ~4303 | 🗑 Clear This Page | `st.rerun()` | `st.rerun(scope="app")` | **Full-page** — same as save |
| ~4335 | 🗑🗑 Clear All Pages | `st.rerun()` | `st.rerun(scope="app")` | **Full-page** — same as save |
| ~4370 | Page count first-load | `st.rerun()` | `st.rerun(scope="fragment")` | Only needs to re-enter fragment with cached count |

**Rule of thumb:** Navigation/zoom/drawing = fragment scope. Anything that writes to DB and affects other panels = full-page scope.

### Step 4: Remove the inner reason panel `@st.fragment`

The reason panel is currently wrapped in its own `@st.fragment` (lines 4153-4216). Once the entire Redact tab is a fragment, the inner fragment becomes **a fragment nested inside a fragment**. This is supported in Streamlit 1.55, but:

- The inner fragment's reruns are already scoped to just the reason panel — no benefit is lost by removing it
- Nested fragments add complexity and potential edge cases
- The outer fragment already prevents reason-dropdown changes from re-executing anything outside the Redact tab

**Recommendation:** Remove the inner `@st.fragment` decorator from `_render_reason_panel()` and make it a regular function call. The outer fragment provides sufficient isolation. The reason dropdowns will trigger a fragment-scoped rerun (re-rendering the canvas), but that's now cheap since the fragment only executes ~480 lines instead of ~5,000.

**However:** If re-rendering the canvas on every dropdown change is still perceptibly slow (because pixmap rendering + component init happens on each dropdown change), **keep the inner fragment**. Test both and decide. The nested pattern works; it's just added complexity.

### Step 5: Zoom slider scope

The zoom slider (`st.select_slider`) is inside the Redact tab. Currently, changing zoom triggers a full-page rerun. Inside the fragment, it triggers a fragment rerun — much faster. The pixmap cache key includes zoom, so a zoom change is a cache miss that requires re-rendering. This is unavoidable but will feel faster with the fragment.

---

## What NOT to Do

- **Do not move code out of the Redact tab.** The entire tab body moves into the fragment function unchanged. No logic changes, no reordering.
- **Do not change the save/clear/delete logic.** These must remain `scope="app"` because they modify state visible in other panels.
- **Do not change the React component or TypeScript.** This is purely a Python-side structural change.
- **Do not change the pixmap caching or pre-caching logic.** It works correctly and is unaffected by the fragment wrapper.
- **Do not change the mark buffering or auto-flush.** These are React-side and unaffected.

---

## Risks and Mitigations

**Risk: Session state keys set inside the fragment aren't visible outside on full-page rerun.**
Mitigation: This is not an issue — Streamlit fragments share the same `st.session_state` with the main page. Keys set inside a fragment are globally visible. The save/clear handlers set keys like `_r_reset_key` and clear tag cache keys, and these will be visible on the subsequent full-page rerun triggered by `st.rerun(scope="app")`.

**Risk: `_safe_write()` uses `st.toast()` and `st.error()` — do these work inside a fragment?**
Mitigation: Yes. `st.toast()` is a global overlay (not scoped to fragment layout). `st.error()` renders within the fragment's container, which is the Redact tab — correct placement.

**Risk: The `_r_doc_info = fitz.open()` for page count (lines 3923-3931) runs on every fragment rerun.**
Mitigation: Claude Code already added page count caching in session state (`_r_pgcount_key`). The `fitz.open()` only runs on first load when the cache is empty. On subsequent fragment reruns, the cached count is used. Verify this is working correctly.

---

## Version Header Updates

- `4_Review.py` — bump patch version, update `last_modified`

## CHANGELOG

```
- CHANGE: 4_Review.py — Wrap entire Redact tab in @st.fragment so page navigation, zoom, and canvas interactions only rerun the tab (~480 lines) instead of the full page (~5000 lines)
```

---

## Verification

1. **Page navigation (arrows):** Click ▶ on page 1 of a multi-page doc. Should show page 2 noticeably faster than before. The document list, metadata panel, and other tabs should NOT re-execute (verify by adding a temporary `print("FULL PAGE RERUN")` at the top of the file — it should NOT print on arrow clicks).
2. **Page navigation (typed):** Type "50" in the page input. Should jump to page 50 with fragment-scoped rerun only.
3. **Zoom change:** Change zoom from 75% to 100%. Fragment rerun, pixmap re-renders at new zoom. Other tabs untouched.
4. **Load Canvas checkbox:** Check/uncheck. Fragment rerun only.
5. **Draw boxes:** Draw 3 boxes. No rerun at all (mark buffering). Wait 2s for auto-flush — fragment rerun.
6. **Change reason dropdown:** Select a reason. If inner fragment kept: inner fragment rerun only. If inner fragment removed: outer fragment rerun only.
7. **Save Marks:** Click save. **Full-page rerun** (`scope="app"`). Tags panel should reflect updated privilege tags.
8. **Delete mark:** Click trash. **Full-page rerun**. Canvas re-inits, mark gone.
9. **Clear This Page / Clear All Pages:** Full-page rerun. Marks cleared, tags updated.
10. **Closed case:** All write buttons disabled. Drawing blocked. No behavioral change.

## Standing Orders Reminder

Per CLAUDE.md, after completing this sprint:
- [ ] Run post-sprint cross-module impact audit (new session state patterns? new fragment scope?)
- [ ] Update CHANGELOG.md
- [ ] Update module version headers
- [ ] Verify no collateral damage to other tabs
