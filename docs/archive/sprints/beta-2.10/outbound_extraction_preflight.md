# Commit 7 Pre-Flight Audit — Outbound Config Extraction

**Target:** `pages/5_Production.py` — extract the ~1,100-line outbound config body into a helper function (currently working name `_render_outbound_production()`) so the three inner `st.stop()` calls can become `return`, dissolving the bug where `st.stop()` kills the entire Streamlit script and blanks `tab_privlog`.

**Post-Commit-6 file state:** 3,830 lines total. `with tab_outbound:` begins line 331; `with tab_privlog:` begins line 3370. Outbound block = 331-3369.

---

## §1 — Extraction Inventory

### 1.1 Line range of the block being extracted

| Region | Lines | Note |
|---|---|---|
| `with tab_outbound:` opening + grid-render guard | 331-338 | **Stays in place** — lives in tab, not in extracted function |
| Selection grid, filters, grid-action buttons | 346-612 | **Inside extraction range** |
| Nested helpers (`get_production_sets`, `_render_post_finalization`, `_render_pass1_checkpoint`, `_handle_retry`, `_handle_abort`, `_handle_finalize`) | 614-2251 | **Stays in place** — already callable from anywhere in tab_outbound; the new function will call some of them |
| State gates (two outer `st.stop()` sites) | 2258-2265 | **Replaced** by if/elif/else gate |
| **Extraction target — "2. Configure & Run" body** | **2267-3369** | **Lifted into `_render_outbound_production()`** |

Net extraction = lines 2267-3369 inclusive (~1,103 lines). The nested helpers at 614-2251 remain in `with tab_outbound:` scope and continue to be called from the new state gates. This differs from the plan's "extract 2236-3290" range — plan numbers predate Commits 2/3 shifts.

**Important nuance:** the grid (lines 346-612) currently renders **above** the state gates (lines 2258-2265) and is gated by `_show_selection_grid` at line 335. That flag remains in place, so the grid itself does not move into the extracted function — it stays in the tab body above, gated by the same boolean. Only the 2267-3369 body moves.

**Correction pending review:** if the reviewer wants the grid moved into the extracted function too, that's a different scope decision. The plan reads as "extract everything below the state gates"; the grid is above. My proposed extraction respects the plan's "2236-3290 → move" = "body below the state gates → move". Flagging for explicit confirmation.

### 1.2 Session state reads and writes inside the extraction block (2267-3369)

**Reads:**

| Line | Expression |
|---|---|
| 2371 | `st.session_state.get('_bates_continue_prev')` |
| 2572 | `st.session_state.get('prod_pass1')` |
| 2574 | `st.session_state.get('prod_pass1_complete')` |
| 2607 | `st.session_state.get('production_selection')` |
| 2608 | `cns = st.session_state['production_selection']` |
| 2805 | `st.session_state.get('username', 'unknown')` |
| 2943 | `st.session_state.get('_prod_cancel', False)` (cancel poll inside imaging loop) |
| 3131 | `st.session_state.get('_prod_cancel', False)` (cancel poll inside inner imaging retry loop) |
| (also) 2111 | `st.session_state.get('cat_family_mode', '')` (inside nested dict for Pass 1 params) |

**Writes:**

| Line | Write | Purpose |
|---|---|---|
| 2325 | `st.session_state["prod_name_input"] = default_prod_name` | widget-default seed (form rendering, every rerun) |
| 2373 | `st.session_state["bates_prefix_input"] = _default_prefix` | widget-default seed |
| 2374 | `st.session_state["bates_start_number"] = _default_start` | widget-default seed |
| 2375 | `st.session_state['_bates_continue_prev'] = _continue` | track continue-toggle for widget re-seed logic |
| 2382 | `st.session_state["bates_prefix_input"] = _default_prefix` | widget-default seed (else-branch of continue toggle) |
| 2385 | `st.session_state["bates_start_number"] = _default_start` | widget-default seed (else-branch) |
| 2817 | `st.session_state['_prod_cancel'] = False` | Pass 1 start — cancel flag initializer |
| 3255 | `st.session_state['prod_pass1'] = {…}` | Pass 1 complete — snapshot for checkpoint |
| 3279 | `st.session_state['prod_pass1_complete'] = True` | Pass 1 complete — gate flag |
| 3280 | `st.session_state['prod_finalized'] = False` | Pass 1 complete — make checkpoint active |

### 1.3 Widget keys inside the extraction block (2267-3369)

Inventory (26 keys, all inside the extraction range):

| Line | Key | Widget |
|---|---|---|
| 2326 | `prod_name_input` | text_input |
| 2341 | `prod_mode_select` | selectbox |
| 2360 | `_bates_continue_toggle` | checkbox |
| 2383 | `bates_prefix_input` | text_input |
| 2386 | `bates_start_number` | number_input |
| 2392 | `prod_format_select` | selectbox |
| 2406 | `bates_padding` | slider |
| 2407 | `stamp_enabled` | checkbox |
| 2409 | `stamp_position_select` | selectbox |
| 2410 | `stamp_color_select` | selectbox |
| 2411 | `stamp_font_size` | slider |
| 2426 | `skip_redaction_burn` | checkbox |
| 2437 | `endorsement_choice` | selectbox |
| 2439 | `custom_endorsement_text` | text_input |
| 2446 | `use_date_range` | checkbox |
| 2450 | `date_range_start` | date_input |
| 2452 | `date_range_end` | date_input |
| 2473 | `prod_sort_mode` | selectbox |
| 2493 | `cat_family_mode` | radio/selectbox |
| 2536 | `prod_pl_profile` | selectbox |
| 2563 | `prod_imaging_workers` | slider |
| 2568 | `run_production_btn` | button |
| 2782 | `delete_rerun_prod_btn` | button |
| 2822 | `_prod_cancel_btn` | button (cancel Pass 1) |
| 3301 | `gap_run` | button |
| 3359 | `gap_download` | download_button |

**L-3 note:** L-3 widget-key namespacing convention (prefix discipline) is a deferred sprint. Keys above are a mix of `prod_*`, `bates_*`, `stamp_*`, bare descriptors, and `_prod_*`. No collisions with `_pl_*` (tab_privlog) or `_rv_*` (Review). No collisions between the 26 keys themselves. **Extraction does not change widget-key behavior** — Streamlit session-state is module-global and keyed, so moving widget code into a function is state-neutral.

### 1.4 Local helper functions defined inside the extraction range

Only two, both narrowly-scoped inline helpers:

| Line | Function | Scope | Action |
|---|---|---|---|
| 2631 | `def get_root(cn):` | Inside family-expansion logic (one-shot recursive parent-walker for the base_df family rollup) | **Moves with the extraction** — deeply nested, used only within the Run Production handler |
| 3304 | `def _bates_num(bates_str):` | Inside Gap Analysis button handler | **Moves with the extraction** — one-shot parser, used only in gap analysis |

Neither is referenced outside its enclosing button handler; both stay with the body.

### 1.5 Closure references — what the extracted function needs access to

Reads from outer scope (module-global or imported):

| Name | Source | Preserved how |
|---|---|---|
| `case_folder` | module-level (line 222) | closure |
| `_case_closed` | module-level (line 230) | closure |
| `_case_status` | module-level (line 229) | closure |
| `db_manager` | top-level import (line 16) | closure |
| `auth_manager` | top-level import (line 27) | closure |
| `config` | top-level import (line 19) | closure |
| `ui_utils` | top-level import (line 28) | closure |
| `os_manager` | top-level import (line 29) | closure |
| `universal_imager` | conditional import (line 44), gated by `IMAGER_AVAILABLE` | closure |
| `IMAGER_AVAILABLE` | module-level flag (line 45/47) | closure |
| `pd`, `os`, `io`, `sqlite3`, `json`, `zipfile`, `shutil`, `time`, `datetime`, `logging`, `logger`, `Path`, `st` | top-level imports | closure |
| `_ASSETS` | module-level (line 32) | closure |
| `_PL_ABBREV_MAP`, `_PL_COLUMN_DEFS`, `_PL_COL_KEY_TO_DISPLAY` | module-level (lines 89, 142, 165) | closure — **none are used in the extraction range**; they're tab_privlog constants. No cross-reference. |
| `get_production_sets`, `_render_pass1_checkpoint`, `_render_post_finalization`, `_handle_retry`, `_handle_abort`, `_handle_finalize` | Nested helpers in `with tab_outbound:` (lines 614-2251) | **In-scope by nesting** — if `_render_outbound_production` is defined INSIDE `with tab_outbound:` alongside them, all six are accessible via closure. If hoisted to module scope, only `get_production_sets` is accessible (others are `with`-block locals). See §2 for design choice. |

Writes to outer scope: **none** beyond session state and DB side-effects. No module-global name is rebound.

### 1.6 Imports the extracted code needs

All imports referenced by the extraction range are already at module top (line 10-30):
`os`, `io`, `sqlite3`, `json`, `zipfile`, `pandas as pd`, `db_manager`, `shutil`, `time`, `config`, `datetime`, `logging`, `streamlit as st`, `auth_manager`, `ui_utils`, `os_manager`, `Path`.

Plus inline lazy imports inside the range (these move with the extraction unchanged):

| Line | Import | Why lazy |
|---|---|---|
| 2545 | `import os as _os_perf` | Trivial — could be hoisted, but harmless inline |
| 2856 | `import time as _perf_time` | Inside Pass 1 loop prelude |
| 2992 | `from concurrent.futures import ProcessPoolExecutor, as_completed` | Inside Pass 1 imaging branch — avoids cost when Native Only |
| 3302 | `import re as _re` | Inside Gap Analysis handler — rarely-used feature |
| 3314 | `from collections import defaultdict as _dd` | Same as above |

All five lazy imports move with the extraction; no plumbing required.

---

## §2 — `_render_outbound_production()` Signature Proposal

### 2.1 Parameters

**Proposed: no parameters.**

Rationale:
- **Consistency with existing siblings.** `_render_pass1_checkpoint()`, `_render_post_finalization()`, `_handle_retry()`, `_handle_abort()`, `_handle_finalize()` all take zero parameters and access `case_folder` / `db_manager` / `st.session_state` via closure. Paramless matches the established pattern.
- **Testability doesn't improve with params.** The function depends on Streamlit's `st.session_state`, `st.button`, `st.text_input`, etc. — none of which are unit-testable without a running Streamlit script context. Passing `case_folder` as a param would not enable a unit test that can't already be written with the paramless form.
- **Closure access is less error-prone.** The function reads ~14 module-globals (listed in §1.5). Passing all of them as parameters creates a 14-arg signature that drifts whenever module-level state changes. Closure accesses are implicit but stable.

**Alternative considered and rejected: pass a config dict.** Over-engineered. The function isn't being prepared for reuse; it's being extracted to enable `return` semantics.

### 2.2 Return type

**Proposed: `None` (pure side-effect).**

The function renders widgets, handles button clicks, and triggers DB/session-state side-effects. It does not compute a value for a caller to consume. The three converted `st.stop()` → `return` sites return without a value (equivalent to `return None`).

### 2.3 Location

**Proposed: nested inside `with tab_outbound:` alongside the existing helpers, positioned after `_handle_finalize` (line 980ish) and before the "MAIN UI" state-gate section (line 2253+).**

Rationale:
- **Closure access to sibling helpers.** The extracted function needs to call `get_production_sets` (line 614) from its sidebar-management section. If hoisted to module scope, `get_production_sets` — defined inside `with tab_outbound:` at line 614 — would no longer be accessible. Hoisting `_render_outbound_production` also requires hoisting `get_production_sets`, which cascades into a multi-function hoist.
- **Match the current structure.** All five existing outbound helpers are nested inside `with tab_outbound:`. Consistency > marginal "cleaner scope" argument.
- **Cost of hoisting is larger than benefit.** Hoisting would require: (a) moving 6 helpers, (b) plumbing closures that currently rely on in-block scope, (c) explaining the asymmetry where tab_privlog's helpers are not hoisted. Not worth it for this commit.

### 2.4 Name justification

**Proposed: `_render_outbound_production()` (not `_render_outbound_config()`).**

The plan uses `_render_outbound_config`, but "config" undersells what the function does. The body contains:
- Sidebar production management (delete existing productions, etc.)
- Selection grid with filters and bulk actions — grid is actually above the extraction range (lines 346-612); stays in the tab
- Bates / format / stamp / endorsement / date-range configuration widgets
- The **Run Production** button handler — which executes **Pass 1 imaging** (the 800+ line imaging loop with cancel polling, worker pool, error reporting)
- The Gap Analysis button handler

Calling this `_render_outbound_config` conflates "render the config form" (which is maybe 300 of the 1,100 lines) with "execute Pass 1 imaging" (the bulk of the body). Reader picking up the name cold would expect a pure render function and be surprised by the imaging loop.

`_render_outbound_production()` captures the full scope: config + run + imaging. Matches the tab's semantic role.

**Alternative names considered:**
- `_render_outbound_main()` — plain but accurate; acceptable fallback.
- `_render_outbound_tab_body()` — explicit about role, but clunky.
- `_render_outbound_config_and_run()` — explicit, clunky, hyphenates what is really one flow.

**Deferred to reviewer:** if you prefer `_render_outbound_config` for plan alignment, I'll use that. Flagging the mismatch for awareness, not pushing hard.

---

## §3 — Verdict Backing for (a)/(b)/(c)

### 3.1 (a) Variable leak-out — "None"

**Grep scope:**
1. Lines 3370-3830 (tab_privlog body + any post-tab module code) grepped for:
   - Named extraction-block vars: `prod_name`, `prod_format`, `bates_prefix`, `bates_start_number`, `exclude_non_responsive`, `exclude_privilege`, `exclude_suppressed`, `exclude_previously_produced`, `exclude_clawback`, `imaging_workers`, `base_df`, `df`, `cns`, `conn`
   - Generic name: `df\b` (the DataFrame variable carried through the Run Production handler)
2. Exhaustive widget-key list (26 keys from §1.3) checked for post-3370 reads.
3. Free-form scan of tab_privlog identifiers — all begin `_pl_*` (namespaced) or are module-globals (`case_folder`, `db_manager`, `st`, etc.).

**Finding:** zero hits in lines 3370-3830 for any name originating in the extraction range.

**What tab_privlog reads from the outer world:**
- Module-globals: `case_folder`, `_case_closed`, `_case_status`, `db_manager`, `auth_manager`, `config`, `st`, `pd`, `os`, `io`, `json`, `datetime`.
- Module-level constants: `_PL_ABBREV_MAP`, `_PL_COLUMN_DEFS`, `_PL_COL_KEY_TO_DISPLAY`, `_ASSETS`.
- Session-state: `prod_pass1`, `prod_finalized`, `_pl_cache_key`, `_pl_last_*`.

None of these are defined in the extraction range — all are at module scope (above line 331) or from imports.

**Why "none" is safe as a verdict:** tab_privlog communicates with the outbound workflow exclusively via session state (`st.session_state['prod_pass1']`) and module-globals. There is no local-variable reach-over from tab_privlog into tab_outbound.

### 3.2 (b) Session-state writes — "No inner-return path leaves any write transient"

**Transient-write test applied:**

For each session-state write W at line L_W, and each inner-return site R at line L_R:
- If L_W < L_R (write happens before the potentially-skipped return): ask "is the write part of normal form-rendering, or part of an in-flight Pass 1?"
  - Form-rendering writes (Cluster A): already-committed on this rerun, independent of the button handler. Safe.
  - Pass-1-prelude write (Cluster B, line 2817): happens AFTER all three stops fire. The stops prevent the prelude from executing — so this write simply doesn't happen on the return path, which is the intended control flow.
  - Pass-1-complete writes (Cluster C, lines 3255/3279/3280): happen AFTER the imaging loop — unreachable if any stop fires, intentionally.
- If L_W > L_R (write would happen after the early return): write doesn't execute. Is that a problem? For all writes in Clusters B and C, the write is gated on Pass 1 actually starting/completing. Skipping them when the handler exits early is the *correct* behavior — they describe Pass 1 state, which hasn't happened.

**Cluster-by-cluster matrix:**

| Cluster | Lines | Before or after all three stops? | Effect of early return |
|---|---|---|---|
| A: form-default seeds | 2325, 2373-2385 | **Before** — in form-rendering pass, not inside button handler | Writes already committed; early return of the handler does not roll them back. No transient state. |
| B: Pass 1 initializer | 2817 | **After** all three stops | Never runs on any early-return path. Correct: no Pass 1 started = no cancel flag to init. |
| C: Pass 1 complete | 3255, 3279, 3280 | **After** imaging loop | Never runs on any early-return path. Correct: no Pass 1 completed = no completion flags. |

**Additional test — does any early return leave a DB connection open?**
- Stop #1 (2578): no connection opened yet. Safe.
- Stop #2 (2752): `conn` closed at line 2719. `_audit_conn` closed at line 2739 (before this stop). Safe.
- Stop #3 (2776): same posture as stop #2. Safe.

No resource leak under any inner-return path.

### 3.3 (c) `st.stop()` → `return` equivalence — per site

#### Site 1 — line 2578 (duplicate production name guard)

**Handler intent:** the `"Run Production"` button handler runs a pre-flight check at the top: "does this production name already exist (as a folder), and is it NOT an in-progress Pass 1 for the same name?" If yes, show an error and halt. Nothing else in the handler has executed — no DB open, no file system touch, no session writes.

**Tab-blanking defect (current behavior):** `st.stop()` raises `StopException`, aborting the Streamlit script run. Result: tab_privlog's body never executes. User clicking "Run Production" with a duplicate name sees the error AND loses the ability to switch to the Privilege Log tab until the next rerun resets the state.

**Why `return` is equivalent:** the handler's intent is to stop its own execution (bail out of the pre-flight). `return` from the enclosing function (`_render_outbound_production`) accomplishes this — function exits, `with tab_outbound:` block finishes, `with tab_privlog:` block runs normally. The error message remains rendered on tab_outbound, and tab_privlog renders in parallel. **Equivalent AND fixes the defect.**

#### Site 2 — line 2752 (Redact-disposition without redaction marks — hard block)

**Handler intent:** same `"Run Production"` handler, later in the flow after `base_df` is built. Guards against producing docs marked for Redact without any redaction marks drawn (a defensibility hazard — would produce privileged content in the clear). On violation: show error naming affected CNs, halt the handler.

**Tab-blanking defect:** identical to Site 1 — `st.stop()` kills the entire script, blanks tab_privlog.

**Why `return` is equivalent:** handler's intent is to abort Run Production before any imaging starts. At line 2752, the DB connection `conn` was already closed at line 2719 (before the redact-check block), and the temporary `_audit_conn` was closed at line 2739 inside the check loop. No resources are open, no state has been mutated. Function return = handler aborted cleanly. **Equivalent AND fixes the defect.**

#### Site 3 — line 2776 (privilege tags without disposition — hard block)

**Handler intent:** same handler, immediately after Site 2. Soft-warns-turned-hard-error for docs tagged privileged without a disposition (Withhold/Redact). Halts the handler to force the reviewer back to Module 4 for disposition coding.

**Tab-blanking defect:** identical to Sites 1 and 2.

**Why `return` is equivalent:** same state posture as Site 2 — all connections closed, no session writes, no filesystem ops. Function return = handler aborted cleanly. **Equivalent AND fixes the defect.**

**Cross-cutting Streamlit-semantics note:** `return` inside a function exits *only that function*. The Streamlit script continues executing below the call site. This is the desired behavior. `st.stop()` raises `StopException` at the script-runner level, aborting all downstream rendering — including sibling tabs, sidebar updates, anything queued. That side-effect is the bug being fixed.

---

## §4 — Phase Plan (A/B/C)

Proposed three-phase execution, full test suite between each.

### Phase A — Pure extraction (scaffolding)

**Scope:**
- Define `_render_outbound_production()` inside `with tab_outbound:` after the existing helpers (around line 2252, before the "MAIN UI" section).
- Move lines 2267-3369 verbatim into the function body, indented one additional level.
- Preserve all three inner `st.stop()` calls **unchanged** — still call `st.stop()`, don't convert yet.
- Leave the two outer state gates (lines 2258-2265) unchanged — they still call `_render_pass1_checkpoint()`, `_render_post_finalization()`, and each still `st.stop()`s after.
- Add a new `else:` branch to the state gate: `else: _render_outbound_production()`.

**Expected behavior after Phase A:**
- Functionally identical to pre-Phase-A. The `_render_outbound_production()` call replaces the previous inline execution of the same body.
- `st.stop()` still blanks tab_privlog in checkpoint state — bug NOT fixed yet.

**Verification:** full pytest suite (185/185 expected); manual smoke-test — start a production, verify config form renders.

**Rationale for splitting:** Phase A is pure code motion. Any regression from Phase A has one cause (extraction mechanics). Phase B's behavior change is isolated from extraction risk.

### Phase B — `st.stop()` → `return` conversion

**Scope:**
- Replace `st.stop()` at lines 2578, 2752, 2776 with `return`.
- Replace `st.stop()` at the two outer gates (2260, 2265) with no-op (the `elif`/`else` structure handles flow) — see Phase C for the if/elif/else rewrite that makes this natural.

Actually, simpler: Phase B converts only the three *inner* stops. The outer gates are handled in Phase C. This keeps phases small and bisectable.

**Revised Phase B scope:**
- Replace `st.stop()` at lines 2578, 2752, 2776 (inside `_render_outbound_production`) with `return`.
- Leave the outer gates alone for now.

**Expected behavior after Phase B:**
- The three error-path halts inside Run Production no longer blank tab_privlog.
- Checkpoint state (the main bug) still blanks — because outer gate at line 2260 still `st.stop()`s. Phase C fixes that.

**Verification:** full pytest suite; manual test — click Run Production with a duplicate name, confirm tab_privlog is still reachable. Click with a Redact-without-marks doc selected, confirm tab_privlog is still reachable.

### Phase C — Outer state-gate rewrite + outer stop removal

**Scope:**
- Rewrite lines 2258-2265 as a single if/elif/else chain with no inner `st.stop()`:
  ```python
  if st.session_state.get('prod_pass1_complete') and not st.session_state.get('prod_finalized'):
      _render_pass1_checkpoint()
  elif st.session_state.get('prod_finalized') and st.session_state.get('prod_pass1'):
      _render_post_finalization()
  else:
      _render_outbound_production()
  ```
- **Optionally** (deferred to reviewer — see scope-expansion probe response below): handle closed-case inline: add an `if _case_closed and not st.session_state.get('prod_finalized')` branch at the top of the chain that renders the warning.

**Expected behavior after Phase C:**
- Checkpoint state no longer blanks tab_privlog. DOC-000150 custodian_a.eml appears in the Privilege Log tab when Pass 1 is at checkpoint. **Bug fixed.**
- All other flows unchanged.

**Verification:** full pytest suite; **the live-test on `Test(small)`** — reach checkpoint state, click 📋 Privilege Log tab, confirm DOC-000150 appears.

### Phase total

| Phase | LOC changed | Risk class | Verification |
|---|---|---|---|
| A | ~1,103 (indent + wrap) | Code motion only | Smoke test config form |
| B | 3 line changes | Behavior change, narrow | Run-Production error paths |
| C | 8-15 line changes | Behavior change, the actual bug fix | Live Streamlit checkpoint walk-through |

---

## §5 — Version Bumps + Test Plan

### 5.1 Version bumps

- `pages/5_Production.py`: **1.22.7 → 1.23.0** (minor bump — new function `_render_outbound_production` added to the module's public-ish surface; also a structural behavior change in the state-gate flow).
  - Alternative: 1.22.7 → 1.22.8 (patch — no new public API, internal refactor). Leaning minor because "new function" is the file-level version rule even for local helpers; reviewer preference wins.
- No changes expected to `db_manager.py`, `pages/9_InboundProduction.py`, or any other page. No test helper changes.

`project_ver: 2.9.0` stays. `last_modified` set to commit time. `last_commit: pending`.

### 5.2 Test plan

**Existing coverage (185/185 passing pre-Commit-7):**
- No test exists that specifically verifies "tab_privlog renders during checkpoint state". This is a UI-integration concern that pytest cannot reach — Streamlit widgets require a running script context.

**New regression test proposed:** none at the pytest layer. The bug is a Streamlit-runtime behavior (script-halt side-effect of `st.stop()`), not a testable pure-Python invariant.

**What I can add:**
- `tests/test_production_helpers.py` — import-smoke test: verify `_render_outbound_production` is defined, is callable, takes no arguments (via `inspect.signature`). Weak but non-zero.

**Manual verification protocol (mandatory for Phase C):**
1. Fresh reset on `D:\eDiscovery\Test(small)`. Clear `prod_pass1_complete` from session state.
2. Run a small production through Pass 1 to reach checkpoint state.
3. Click the **📋 Privilege Log** tab.
4. Confirm DOC-000150 (custodian_a.eml, tagged Redact) appears in the log.
5. Confirm the rest of the privilege log renders (not just a blank tab).
6. Click back to **📦 Outbound Production** — verify checkpoint UI is still there.
7. Click **Finalize** — verify post-finalization screen renders.
8. Start a new production — verify config UI renders from the `else` branch.
9. Start a Pass 1 with a duplicate name — confirm error shows AND tab_privlog still reachable.
10. Start a Pass 1 with a Redact-marked-doc that has no redaction marks — confirm hard block fires AND tab_privlog still reachable.

Each of 1-10 is a distinct scenario mapping to a separate audit item. Failures localized.

**Regression coverage gap flagged:** "tab_privlog renders during checkpoint" has no automated test. This is inherent to Streamlit's testing story. Playwright E2E (see memory `reference_playwright_e2e.md`) is the right tool for a future automated check — noting as a roadmap candidate, not blocking Commit 7.

---

## §6 — Scope-Expansion Probe Responses

### Probe 6.1 — What does line 233's `st.stop()` do?

**Current code (lines 231-235):**
```python
if _case_closed and not st.session_state.get('prod_finalized'):
    st.warning('🔒 This matter is closed. Write operations are disabled.')
    st.stop()
elif _case_closed:
    st.warning('🔒 This matter is closed. Downloads are available below.')
```

**Trigger condition:** case is Closed AND no production has been finalized in the current session (`prod_finalized` is falsy).

**Effect:** script halts entirely — no tab rendering, no sidebar updates. User on a closed case sees only the warning banner above the tabs bar. **Tab_privlog never renders on closed cases.**

### Probe 6.2 — Is per-tab closed-case handling already in place?

**No.** Neither `tab_outbound` nor `tab_privlog` has its own closed-case handling. The module-level `st.stop()` at 233 is the only gate.

If scope-expansion is accepted: this commit would *remove* the module-level gate AND *add* per-tab handling (tab_outbound gets a read-only variant via the new if/elif/else; tab_privlog renders unconditionally since it's read-only by nature — privilege log is a historical view, not a write operation).

### Probe 6.3 — Failure mode if line 233 stays in place

If line 233 stays:
- Closed cases still blank tab_privlog. This is a **real UX defect**, not just redundancy: a reviewer on a closed case cannot view the privilege log via Module 5. They would have to reopen the case (admin action) just to read a log.
- The Phase C rewrite doesn't fix this — it only fixes the checkpoint-state blanking. The closed-case blanking remains.

**But:** the closed-case blanking is a separate bug from the checkpoint-state blanking. It's caused by the same root (script-halt) but lives in a different gate. Commit 7's stated scope (per plan §7) is "phase-gating refactor" — which targets the checkpoint-state gates (2258/2265 in current file). The closed-case gate at 233 is structurally adjacent but semantically distinct.

**Acknowledging your probe's framing:** "redundant warnings" was my earlier characterization and it's wrong. The failure mode is **closed-case reviewers cannot view privilege log** — a behavioral defect, not a UX redundancy. The correct framing matters for scope decision.

### Probe 6.4 — Does any other page use the module-level closed-case pattern?

Examined `pages/3_Analytics.py` and `pages/4_Review.py`:

**`pages/4_Review.py` (lines 297-302):**
```python
_case_status = db_manager.get_case_status(case_folder)
_case_closed = (_case_status == 'Closed')
if _case_closed:
    st.warning('🔒 This matter is closed. Write operations are disabled. '
               'Read-only access is available below.')
```
**No `st.stop()`.** Pattern: display warning, continue rendering. Individual write actions check `_case_closed` at their site and disable themselves.

**`pages/3_Analytics.py` (lines 81-82):**
```python
_case_closed = (_case_status == 'Closed')
if _case_closed:
    # warning banner; no st.stop()
```
Same pattern as Review.

**`pages/5_Production.py` (current, lines 231-235):** DIVERGES — does `st.stop()` after the warning when not finalized.

**Verdict on divergence:** `pages/5_Production.py` is the outlier. Removing the `st.stop()` at line 233 would make it match Review's and Analytics' established pattern — **converging, not diverging**.

### Probe 6.5 — Revised scope-expansion recommendation

Given §6.1-6.4:
- The failure mode is behavioral (closed-case reviewers locked out of privilege log), not UX-cosmetic.
- Removing line 233 converges toward Review's / Analytics' pattern, not away from it.
- The fix is small: remove `st.stop()` at line 233 (the warning at 232 stays). Let tab_outbound's new if/elif/else handle closed-case inside the tab.

**Revised recommendation:** include the removal in Commit 7 Phase C. Rationale: same root cause (script-halt side-effect of `st.stop()` in Module 5), same hazard class (tab-blanking). Per `feedback_commit_bundling_principle.md`: "bundle only when same root cause AND same fix pattern AND same hazard class" — all three criteria met.

**Counter-option:** defer to Commit 7.5 or roadmap-flag for beta-2.11. Costs: ships beta-2.10 with a known closed-case defect.

**Deferring to reviewer judgment:** I'll execute either scope. Flagging that my initial framing ("redundant warnings") was wrong and the real case for inclusion is stronger than I stated.

---

## §7 — Line-Number Drift Re-Verification

Plan §7 line references and their current (post-Commit-6) positions:

| Plan reference | Plan line | Current line | Status |
|---|---|---|---|
| Outer `st.stop()` #1 (closed-case + not finalized) | 2229 | 233 (module-level) | **Shifted significantly** — and now recognized as module-level, not in-tab |
| Outer `st.stop()` #2 (unclear — plan may have meant the second module-level stop, but plan's language suggests in-tab) | 2234 | 2260 or 2265 | **Ambiguous** — plan's "2229, 2234" likely refers to the two in-tab outer stops (now 2260/2265) |
| Inner stop — duplicate name | 2547 | 2578 | Shifted +31 |
| Inner stop — Redact no marks | 2708 | 2752 | Shifted +44 |
| Inner stop — priv tags no disposition | 2732 | 2776 | Shifted +44 |
| Extraction range start | 2236 | 2267 | Shifted +31 |
| Extraction range end | 3290 | 3369 | Shifted +79 (growth from Commit 6 NOT affecting this — outbound tab grew, not shrank) |
| Title rename target | 308 | 319 | **Already done in Commit 6** — skip |

**Reconciled reading of plan's "2229, 2234":** plan meant the two **in-tab** outer stops (current 2260/2265), not the module-level stop at old ~230-ish. The in-tab stops are where the state-gate refactor lands. The module-level stop at current line 233 is the scope-expansion candidate (probe §6).

**Other plan references in Commit 7's section:**

> "2. Extract lines 2236-3290 (the '2. Configure & Run' block and everything below it through end of outbound tab) into a function..."

Current range: 2267-3369. Semantically the same ("Configure & Run" block + everything below it in tab_outbound). Confirmed.

> "3. Rename page title at line 308: 'Module 5: Production & Export 📦' → 'Module 5: Outbound Production & Privilege Log 📦'."

Current title is already the new string at line 319. **Commit 6 landed this rename.** Skip this step in Commit 7.

> "Any local variables in the block that are also used by the outer caller need to be either passed in or returned. Spot-check: the block references `case_folder`, `_case_closed`, `auth_manager`, `db_manager`, `st.session_state` — all module-scope, safe."

Spot-check confirmed in §1.5. All outer references are module-scope or imports. Safe.

> "New regression tests in `tests/test_bates.py` class `TestProductionInboundExclusion`: seed a case..."

This refers to Commit 3, not Commit 7. No Commit-7 test-file reference to validate.

**Verdict:** Commit 7 section references have been re-verified. No additional stale line pointers. Plan's "line 308 title rename" instruction is fully stale (done in Commit 6).

---

## §8 — Summary / Greenlight Posture

| Audit Item | Verdict | Backing section |
|---|---|---|
| (a) Variable leak-out | ✅ None | §3.1 |
| (b) Session-state writes transient under early return | ✅ No | §3.2 |
| (c) `st.stop()` → `return` semantically equivalent at 2578/2752/2776 | ✅ Yes, at each site | §3.3 |

**Open scope question for reviewer:** include the module-level `st.stop()` removal at line 233 in Commit 7 Phase C (my current recommendation per §6.5), or defer to Commit 7.5 / beta-2.11.

**Function name open question:** `_render_outbound_production()` (my proposal) vs `_render_outbound_config()` (plan's name).

**Ready for greenlight.** Proceeding only after reviewer ratifies (a)/(b)/(c), confirms function name, and resolves the scope-expansion decision.
