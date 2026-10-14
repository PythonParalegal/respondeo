# Fragment Scope Rule

**One-sentence summary:** `@st.fragment` scope fits navigation/zoom/drawing interactions; app scope fits DB-writing operations. Mismatching the two causes session-state bleed between tabs.

## The pattern

Streamlit's `@st.fragment` decorator isolates reruns: a widget interaction inside a fragment re-executes only the fragment body, not the entire page. For a 5,000-line page like `4_Review.py`, that is a massive performance win — clicking a page-nav arrow inside the Redact tab should not re-query OpenSearch for the Extracted Text tab, re-render the document list sidebar, or re-compute production metrics.

But fragments have a constraint: they see a snapshot of session state at fragment-entry time. Writes inside a fragment are visible to that fragment's subsequent reruns, but they are not guaranteed to be consistent with other tabs or the main page flow until the fragment exits and the page does a full rerun. This is fine for interactions that are locally scoped (zoom, draw, navigate) but dangerous for interactions whose result another tab must read immediately.

The rule: decide per-widget. Navigation, zoom, drawing, local UI state — fragment scope. DB write or cross-tab state mutation whose effect another tab must see — app scope. A widget that writes to the database AND also needs the local fragment's cached snapshot to refresh typically needs *both*: fragment rerun first (for local state refresh), then a deliberate full rerun (for cross-tab visibility).

The cost of getting scope wrong: a reviewer saves a redaction mark inside the Redact tab's fragment. The fragment reruns. The mark count display updates within the fragment. The reviewer switches to the Production tab. The Production tab reads the still-cached pre-save state because no full-page rerun fired. The reviewer sees no new redaction in the production assembly and files a bug that the save "didn't work," when in fact it saved but a cached view of session state is stale.

## Concrete example

**Sprint:** beta-2.10 redact-tab fragment wrapper (`docs/superpowers/specs/2026-04-02-redact-tab-fragment-wrapper-spec.md`).

The Redact tab in `4_Review.py` was slow because every interaction (page navigation, zoom, draw, canvas checkbox) triggered a full-page rerun of a 5,000-line file. The spec's solution: wrap the entire Redact tab body in `@st.fragment`. Within the tab, the ~10 `st.rerun()` calls were each classified:

- **Page-nav arrow buttons, page-jump input, zoom slider, canvas checkbox:** `st.rerun(scope="fragment")`. Only the canvas needs to refresh; no other tab is affected.
- **Save Redactions button, Clear Redactions button:** `st.rerun()` (app scope, the default). Production and privilege-log tabs must see the new mark state immediately when the reviewer switches tabs.

The rule captured in the spec:

> Every feature — drawing, saving, deleting, clearing, navigation, zoom, privilege sync, audit logging — must work identically. The only change is *what code re-executes* on each interaction.

Drawing / navigating / zooming = fragment scope. Saving / deleting / clearing = app scope. Classification per-widget.

The canvas interactions (draw a box, adjust a box, delete a box) use fragment scope because the React component maintains its own local state until the reviewer explicitly hits Save. Up until Save, no DB write has happened; there is nothing for other tabs to see. Save is the app-scope boundary.

## How to apply

- Default a widget to fragment scope when its effect is visually local and does not touch the DB.
- Promote a widget to app scope when another tab reads the state it writes.
- Save/commit buttons are almost always app scope. Navigation and display-only controls are almost always fragment scope.
- When in doubt, test: open two tabs, perform an action in tab A that should be visible in tab B, switch to B, check. If B shows stale data, the action in A was mis-scoped (probably fragment when it needed app).
- When adding `@st.fragment` to a large block, audit every `st.rerun()` inside it. Any unclassified call is a latent state-bleed bug.

## See also

- **Related lessons:** `docs/lessons/atomic-multi-table-writes.md`
- **Source:** `docs/superpowers/specs/2026-04-02-redact-tab-fragment-wrapper-spec.md` (full sprint spec; scope classification table)
- **Relevant code:** `pages/4_Review.py` Redact tab — `@st.fragment` wrapper, `st.rerun(scope="fragment")` vs `st.rerun()` call sites
