# Redaction Canvas — Batched Drawing & Performance Sprint

**Date:** 2026-04-02
**Phase:** UX Performance — Redaction Workflow
**Estimated complexity:** ~80 lines changed in React (useDrawing.ts, RedactionViewer.tsx), ~40 lines changed in Python (4_Review.py), plus investigation findings

---

## Problem

Drawing redaction boxes on a page is painfully slow. Each completed box triggers `Streamlit.setComponentValue()`, which causes a full Streamlit page rerun — the canvas dims, the entire Python script re-executes, and the canvas re-renders. This happens:

1. **Every time a box is drawn** — `useDrawing.ts` line 98 calls `onDrawComplete([...marks, newMark])`, which flows through `handleDrawComplete` → `sendValue` → `Streamlit.setComponentValue()`
2. **Every time a reason dropdown changes** — each `st.selectbox` interaction triggers a Streamlit rerun of the entire page

For a document with 5-6 redaction boxes per page (common for financial documents with account numbers, check images, etc.), this means 5-6 full-page reruns just to draw, plus additional reruns for reason assignment. Each rerun re-opens the PDF, re-renders the pixmap, and re-initializes the component.

The database save is already batched correctly (the "Save Marks" button collects all marks at once), so the persistence model is fine. The problem is purely the Streamlit rerun cycle during the drawing/editing phase.

## Principle

Eliminate unnecessary round-trips to Python during the mark-creation phase. The React component should accumulate marks locally and only notify Python when the user explicitly commits. No changes to the database schema, save logic, or audit trail.

---

## Sprint 1: Frontend Mark Buffering (React)

### Goal
Stop `Streamlit.setComponentValue()` from firing on every drawn box. Instead, buffer new marks in React state and send them to Python in a single batch.

### 1.1 New ComponentValue action: `"batch_update"`

**File:** `components/redaction_viewer/frontend/src/types.ts`

Add a new action type to distinguish batched commits from single-mark updates:

```typescript
// Before
export interface ComponentValue {
  marks: RedactionMark[];
  action: "update" | "delete" | null;
}

// After
export interface ComponentValue {
  marks: RedactionMark[];
  action: "update" | "delete" | "batch_update" | null;
}
```

### 1.2 Deferred `sendValue` in draw mode

**File:** `components/redaction_viewer/frontend/src/RedactionViewer.tsx`

Currently `handleDrawComplete` (lines 74-79) calls `sendValue` immediately:

```typescript
// BEFORE (current — sends to Python on every box drawn)
const handleDrawComplete = useCallback(
  (newMarks: RedactionMark[]) => {
    setMarks(newMarks);
    sendValue(newMarks, "update");  // ← triggers Streamlit rerun
  },
  [sendValue]
);
```

Change to buffer locally — only update React state, do NOT call `sendValue`:

```typescript
// AFTER (buffered — no Streamlit rerun)
const handleDrawComplete = useCallback(
  (newMarks: RedactionMark[]) => {
    setMarks(newMarks);
    setHasUnsaved(true);
    // Do NOT call sendValue here — marks stay in React state
    // until user explicitly commits via the "Done Drawing" action
  },
  []
);
```

Add state tracking for unsaved marks:

```typescript
const [hasUnsaved, setHasUnsaved] = useState(false);
```

### 1.3 Commit trigger: mode switch or explicit flush

Marks should be flushed to Python (triggering a single rerun) when:

1. **User switches from Draw to Select mode** — the mode switch already triggers a rerun (the radio button is a Python widget), so we need to send marks before that rerun discards React state.
2. **User clicks "Save Marks"** — but this is a Python-side button, so the component needs to have already sent its marks before the button's rerun.

The cleanest approach: **detect the mode prop change inside the component** and flush at that moment.

```typescript
// In RedactionViewer.tsx, update the mode-change detection block (lines 110-116)
if (prevModeRef.current !== mode) {
  prevModeRef.current = mode;
  if (mode === "draw") {
    selection.setSelectedIndex(null);
  }
  // Flush any unsaved marks when mode changes
  if (hasUnsaved) {
    sendValue(marks, "batch_update");
    setHasUnsaved(false);
  }
}
```

**Also flush on unmount** (page navigation, document change) via a `useEffect` cleanup. Use a ref to hold the latest marks so the cleanup closure isn't stale:

```typescript
const marksForFlushRef = useRef(marks);
marksForFlushRef.current = marks;

const hasUnsavedRef = useRef(hasUnsaved);
hasUnsavedRef.current = hasUnsaved;

useEffect(() => {
  return () => {
    if (hasUnsavedRef.current) {
      const value: ComponentValue = { marks: marksForFlushRef.current, action: "batch_update" };
      Streamlit.setComponentValue(value);
    }
  };
}, []);  // empty deps — runs only on unmount
```

### 1.4 Unsaved mark count badge

Add a visual indicator so the user knows they have uncommitted marks. Render a small badge in the top-left corner of the SVG overlay:

```tsx
{hasUnsaved && (
  <text x={8} y={20} fontSize={13} fill="#ff9900" fontWeight="bold">
    {marks.length - initialMarks.length} unsaved
  </text>
)}
```

This is non-blocking — just a visual cue. The actual commit happens on mode switch or save.

### 1.5 useDrawing.ts — no changes needed

`useDrawing.ts` itself doesn't call `sendValue` — it calls `onDrawComplete`, which is the callback from `RedactionViewer.tsx`. The buffering change is entirely in the parent component's callback. The hook stays unchanged.

### 1.6 Selection mode — leave as-is

`useSelection.ts` already has the right pattern: `onLocalUpdate` during drag (visual only), `onMarksChanged` only on mouseup. Since selection edits are single operations (move one box, resize one box), the per-operation rerun is acceptable. Don't change selection behavior.

---

## Sprint 2: Python-Side Reason Panel Isolation

### Goal
Prevent reason-dropdown changes from redrawing the canvas. When a user picks a reason from the Box 1/2/3 selectboxes, only the control panel should rerun — the canvas image stays untouched.

### 2.1 `@st.fragment` wrapper for reason selectors

**File:** `pages/4_Review.py`

Streamlit 1.55 supports `@st.fragment` (introduced in 1.33). Wrap the per-box reason selector block in a fragment so that selectbox interactions only rerun the fragment, not the entire page.

**Current structure** (lines ~4108-4166 in the `_r_ctrl_col` block):
```python
# Per-box reason selectors with delete buttons
if _r_n_boxes > 0:
    st.divider()
    st.markdown("**Mark Reasons**")
    for _r_i in range(_r_n_boxes):
        # ... selectbox, delete button, custom text_input
```

**Target structure:**
```python
@st.fragment
def _render_reason_panel():
    if _r_n_boxes > 0:
        st.divider()
        st.markdown("**Mark Reasons**")
        for _r_i in range(_r_n_boxes):
            # ... selectbox, delete button, custom text_input
            # NOTE: delete button MUST still call st.rerun() (full page)
            # because it modifies marks and needs canvas to re-init.
            # Use st.rerun(scope="app") inside the delete handler.

_render_reason_panel()
```

**Important constraints:**
- The fragment can read session state and outer-scope variables (closures work fine)
- The delete button inside the fragment needs a **full-page** rerun (`st.rerun(scope="app")`), not a fragment-scoped rerun, because deleting a mark changes the canvas
- The "Save Marks" button should remain **outside** the fragment (it already is — it's below the reason block)
- `st.fragment` functions cannot return values to the caller, so reason resolution (`_r_resolve_reason`) must read from session state at save time (which it already does)

### 2.2 Custom reason text_input: fire on Enter only

When the user selects "[Custom Reason...]", a `st.text_input` appears for them to type a custom reason. By default, Streamlit's `text_input` fires a rerun on every keystroke. Even inside a fragment (where the rerun is scoped to the panel, not the whole page), per-keystroke reruns create a flickery, laggy typing experience and are unnecessary — the typed value only matters at Save time.

**Fix:** Use the `on_change` callback pattern with explicit Enter/blur semantics. Streamlit 1.55 does not have a built-in "submit on Enter only" mode for `text_input`, but we can avoid the per-keystroke problem by ensuring the text input's value is read from session state only at save time (which `_r_resolve_reason` already does). The key behavior to verify:

- Inside `@st.fragment`, typing in a `text_input` triggers fragment-scoped reruns (not full page) — this is acceptable since the canvas is unaffected
- However, if fragment reruns during typing feel sluggish (e.g., the cursor jumps or input lags), switch to a **form-based approach**: wrap the custom text input in a `st.form` inside the fragment so it only submits on Enter:

```python
# Preferred: form-wrapped custom input (fires only on Enter)
if _r_chosen == _REDACT_CUSTOM:
    with st.form(key=f"custom_reason_form_{current_cn}_{_r_page_idx}_{_r_i}", border=False):
        st.text_input(
            f"Custom {_r_i+1}",
            value=_r_prev_custom,
            key=f"reason_custom_{current_cn}_{_r_page_idx}_{_r_n_boxes}_{_r_i}",
            placeholder="Enter reason, press Enter...",
            label_visibility="collapsed",
        )
        st.form_submit_button("Set", use_container_width=True)
```

**Note on `st.form` inside `@st.fragment`:** This is supported in Streamlit 1.55. The form submit triggers a fragment rerun (not a full page rerun), which is exactly what we want. The submit button can be small/subtle since Enter also submits forms.

**Test this explicitly** — if the `st.form` inside `@st.fragment` pattern causes issues (some Streamlit versions had edge cases with nested scoping), fall back to the plain `text_input` inside the fragment. The fragment-scoped rerun is still a major improvement over the current full-page rerun, even if it fires per-keystroke.

### 2.3 Verify fragment compatibility

Before implementing, verify:
- [ ] `st.selectbox` inside `@st.fragment` only reruns the fragment (not the page)
- [ ] `st.text_input` inside `@st.fragment` behaves the same way
- [ ] `st.form` inside `@st.fragment` submits on Enter and only triggers a fragment rerun
- [ ] `st.button` inside `@st.fragment` can call `st.rerun(scope="app")` for full-page rerun
- [ ] Session state keys written inside the fragment are visible outside it on the next full rerun
- [ ] Custom reason typed in form is readable via session state key at Save Marks time (outside the fragment)

Run a minimal test if any of these are uncertain. Streamlit's fragment scoping is well-documented but worth a quick smoke test given this is a critical workflow.

---

## Sprint 3: React Build & Deployment

After making changes to the TypeScript/React source files, the component must be rebuilt.

### 3.1 Build the React component

```bash
cd components/redaction_viewer/frontend
npm run build
```

Verify the build output lands in `components/redaction_viewer/frontend/build/` and that the Streamlit component loads correctly.

### 3.2 Smoke test

Test the following scenarios manually:
1. **Draw 5 boxes rapidly** — canvas should NOT dim/flicker between boxes
2. **Switch from Draw to Select** — all 5 boxes should appear in the reason panel
3. **Change a reason dropdown** — canvas should NOT redraw
4. **Select [Custom Reason...], type a reason, press Enter** — canvas should NOT redraw, typed text should persist in session state
5. **Click Save Marks** — all marks + reasons (including custom) should persist to DB
5. **Navigate to next page and back** — saved marks should reload correctly
6. **Draw boxes, then navigate away without saving** — unsaved marks should flush via unmount effect (verify they appear in reason panel on return)
7. **Delete a mark via trash button** — full page rerun, canvas re-inits correctly
8. **Closed case** — drawing should still be blocked (caseClosed prop)

---

## What NOT to Do

- **Do not change the database schema.** The `redaction_marks` table and `marks_json` format are correct as-is.
- **Do not change the Save Marks logic.** The save button's handler (`_save_marks_op`) is well-structured — it saves to DB, writes PDF annotations, syncs tags, and audits. Leave it alone.
- **Do not buffer in Python session state.** The buffering belongs in React (client-side), not in Python. Session state buffering would still trigger reruns on every state write.
- **Do not remove the `_r_reset_key` / `_r_reset_counter` pattern.** This is how the canvas reloads from DB after saves/deletes. It must stay.
- **Do not change `useSelection.ts`** behavior — its per-operation rerun pattern is acceptable for single-mark edits.

---

## Version Header Updates

Update metadata headers in every file touched:
- `RedactionViewer.tsx` — N/A (TSX files don't get Python headers)
- `useDrawing.ts` — N/A (same)
- `types.ts` — N/A (same)
- `4_Review.py` — bump patch version, update `last_modified` to current datetime

## CHANGELOG

```
- CHANGE: 4_Review.py — Wrap reason selectors in @st.fragment to prevent canvas redraws on dropdown change
- CHANGE: RedactionViewer.tsx — Buffer drawn marks in React state; flush to Python on mode switch or unmount instead of per-box
- CHANGE: types.ts — Add "batch_update" action to ComponentValue interface
```

---

## Investigation Directive: Broader Redaction Performance Audit

**While implementing the above sprints, investigate and document (but do not fix without approval) the following potential performance improvements.** Report findings as a separate section in the commit message or as a follow-up document.

### Areas to investigate:

1. **PDF re-open per rerun.** The Redact tab opens the PDF (`fitz.open`) on every page rerun to get the page count (lines 3923-3931), then opens it AGAIN to render the pixmap (lines 3958-3973). On a 100-page document like the one in the screenshot, this is two file opens per rerun. Can we cache the page count in session state and only open the PDF once for rendering?

2. **Pixmap re-rendering.** Every rerun re-renders the page pixmap even when nothing about the page changed (same page index, same zoom). Could we cache the rendered PNG bytes in session state keyed by `(control_number, page_idx, zoom_pct, pdf_mtime)` and skip re-rendering if the cache hits?

3. **Search term highlighting cost.** If `_doc_search_terms` is active, `_highlight_page_image()` runs on every rerun of the Redact tab. This involves opening the PDF, searching for terms, drawing highlight rectangles, and compositing with PIL. Could this be cached alongside the pixmap?

4. **Component key churn.** The viewer key is `f"rv_{current_cn}_{_r_page_idx}_{_r_zoom_pct}_{_r_reset_counter}"`. Any change to zoom, page, or reset counter destroys and recreates the React component from scratch. Is there a way to update props without destroying the component (e.g., separate the reset counter from the key and use a prop-based reset signal)?

5. **Full-page rerun scope.** The Review page (`4_Review.py`) is very large. Every widget interaction reruns the entire file — including the document list query, metadata panel, all tabs, etc. Could the Redact tab itself be wrapped in `@st.fragment` so that drawing/saving only reruns the Redact tab, not the entire page? (This is a bigger architectural question — may not be feasible if the Redact tab reads session state set by the document navigator.)

6. **Reason dropdown count.** Each box gets its own `st.selectbox` with a unique key. For a page with 10 boxes, that's 10 selectboxes rendered on every rerun (even fragment-scoped reruns). Could we use a single selectbox that applies to a "selected" box instead? This would also match the Select mode UX more naturally — click a box to select it, then pick its reason.

7. **Delete button immediate-save pattern.** Currently, clicking the trash button on a box immediately saves to DB, writes PDF annotations, and reruns. This is the right pattern for destructive operations, but check whether the `_r_write_page_annotations` call (which opens the PDF, deletes all annots, rewrites them, and does an incremental save) is a bottleneck. If so, could we defer annotation writing to the Save Marks button like we do for new marks?

### Output format for investigation:

For each item above, report:
- **Feasible?** Yes / No / Needs more investigation
- **Estimated impact:** High / Medium / Low (in terms of perceived speed improvement)
- **Estimated effort:** Lines of code, risk level
- **Dependencies:** Does it conflict with any other item?
- **Recommendation:** Do it in this sprint / Separate sprint / Defer

Save investigation findings to `docs/superpowers/specs/2026-04-02-redaction-perf-audit-findings.md`.

---

## Standing Orders Reminder

Per CLAUDE.md, after completing this sprint:
- [ ] Run post-sprint cross-module impact audit
- [ ] Update DEPENDENCY_MAP.md if any new session state keys or data flows were added
- [ ] Update Current State table in CLAUDE.md
- [ ] Update CHANGELOG.md
- [ ] Update documentation (User_Guide.md, Technical Overview.md) if user-facing behavior changed
