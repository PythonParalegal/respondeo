# Sprint Spec: Inbound Production Module Extraction

**Authored:** 2026-04-16 by Browser Claude (planning session with the maintainer)
**Assigned to:** CLI Claude
**Target branch:** `debug/inbound-production-extraction` off `beta-2.9` (confirm with the maintainer before cutting; may alternatively be folded into a new sprint branch)
**Status when starting:** Read this entire spec, then follow the **Pre-Investigation** checklist in §5 before touching any code.

---

## 1. Context

During end-to-end testing of production categories and strict grouping on 2026-04-16, the maintainer ran a Pass 1 test production (`PRODUCTION_001`) and surfaced two defects plus an architectural concern:

1. **Orphan detector false positive.** After Pass 1 completed, the orphan-file detector at `pages/5_Production.py:239-264` flagged the legitimately-staged TEMP/STAGED files as "abandoned" because it has no awareness of the active-but-not-finalized production.

2. **Privilege Log tab blank.** The phase-gating fix landed today (CHANGELOG 2026-04-16) uses `st.stop()` at `pages/5_Production.py:2229` and `:2234` to hide the outbound grid during the Pass 1 checkpoint. Because `st.stop()` halts the entire Streamlit script (not just `tab_outbound`), the subsequent `with tab_inbound:` and `with tab_privlog:` blocks never render. This gotcha is already noted in memory but was reintroduced.

3. **Architectural concern (the real finding).** "Inbound Productions" is semantically an *input* workflow — it ingests opposing counsel's deliverables into the review set. Housing it alongside outbound assembly and privilege log on Module 5 means:
   - Any gating applied to the outbound workflow risks locking users out of inbound ingestion
   - The page name ("Production & Export") is misleading; inbound is neither a production nor an export
   - Rolling productions and future production-management features have nowhere clean to grow

**The decision made in planning:** Extract inbound production into its own dedicated module now, rather than fix the phase-gating bug in place. Fixing in place would leave the underlying workflow hazard (lock-out risk) intact and force a re-rip later when production-management features expand.

---

## 2. Objective

1. Create a new dedicated module `pages/9_InboundProduction.py` housing the entire inbound-productions workflow currently rendered inside `tab_inbound` on `pages/5_Production.py`.
2. Simplify `pages/5_Production.py` to its true scope: outbound production assembly and the privilege log derived from it. Rename the display title accordingly.
3. Resolve the two bugs surfaced during testing as a natural consequence of the restructure (the privilege log tab blank bug is dissolved by the restructure itself; the orphan detector bug gets an upgraded fix that is DB-backed rather than session-state-backed).
4. Update all documentation (CLAUDE.md table, DEPENDENCY_MAP.md, Walkthrough, Technical Overview, User_Guide, PROJECT_CONTEXT) to reflect the new module boundary.

---

## 3. Decisions Already Made

These were reasoned through during planning. Do not re-litigate them without flagging to the maintainer.

- **Dedicated module, not a tab in the processor.** Rationale: expected future growth (rolling productions, overlays, corrections, re-productions), clean separation prevents a second rip-out later, and the platform already has 8 modules — one more does not strain the user's mental model.
- **Not folded into Custodians.** Custodian = original holder of the data (a legally-meaningful concept); an inbound production is a delivery vehicle, not a custodian. Per-document custodians in the incoming load file should still populate the existing `custodian` column. Conflating "who delivered this to us" with "who originally held this" would muddle privilege logs and authenticity challenges.
- **Not folded into Sync.** Sync is about ongoing external-system integration. An inbound production is a one-shot data load, not a sync relationship.
- **Privilege Log stays with outbound.** The privilege log is derived from *your* outbound production decisions. It belongs on Module 5 alongside outbound assembly.
- **Module 5's `st.stop()`-based phase gating is to be replaced**, not reordered. The existing hack of reordering `with tab_X:` blocks would be fragile and would not address the underlying "narrow the scope of the gate" principle. Once inbound is out, Module 5 has only two tabs (or can drop the tabs entirely — see §6.2.3).
- **Orphan detector's session-state-based guard is insufficient.** If the user closes the browser between Pass 1 and Finalize, session state is lost and legitimately-staged files would be flagged as orphaned again. The fix must read persistent state (the production status in the DB) to determine whether a production folder is actively in-flight or truly abandoned.

---

## 4. Open Decisions Requiring the Maintainer's Input Before Sprint Kickoff

These should be resolved in a short pre-sprint chat before you cut the branch.

1. **Module number.** Recommendation: `9_InboundProduction.py`, placing it after Exhibits. Alternatives: renumber to slot near Ingestor/Processor (workflow-logical placement) — but file renames cascade through imports, navigation links, and bookmarks. Recommend avoiding renumbering.

2. **Display name and icon.** Recommendation: "Inbound Productions" (plural, matches the existing tab label). Pick an emoji/icon consistent with the module set.

3. **Future-feature scaffolding scope.** Should this sprint scaffold DB columns for rolling-production tracking (`volume_number`, `production_set_id`, `producing_party`, `received_date`, `bates_prefix`)? Or defer until there is a concrete feature need? Recommend: defer. Add only what is needed for behavior-parity with today's `tab_inbound`. Future features get their own sprint with a proper DB migration.

4. **Branch strategy.** Confirm: is this a `debug/*` branch off `beta-2.9`, or does it warrant a new sprint branch (e.g. `beta-2.10`)? Per CLAUDE.md, `beta-X.Y` is for sprint work — this sprint is substantial enough that a new sprint branch may be appropriate.

5. **Deprecation question, separate from this sprint.** The maintainer mentioned the Sync module is becoming less necessary. Not in scope here, but worth noting on the roadmap — if Sync is retired, `6_Sync.py`'s slot frees up for logical reordering later.

---

## 5. Pre-Investigation (MANDATORY per Standing Orders)

Per CLAUDE.md §"Standing Orders — Pre-Fix Investigation Protocol" and §"Standing Orders — Post-Sprint Cross-Module Impact Audit," complete the following before writing any code. Record findings in a scratchpad file or at the top of the first commit.

### 5.1 Trace the data flow

Document the path of an inbound-production document from ingestion to review:

- Where does the load file parser live today? (module, function names)
- What DB columns are populated specifically for inbound docs? (e.g., `source_type`, `production_volume`, `received_date`, `producing_party`, Bates fields)
- Where are inbound native files written on disk? (e.g., `Productions/INBOUND/<volume>/NATIVES/` vs. `case_files/<custodian>/`)
- How are inbound docs represented in OpenSearch? (are they in the same index as custodial docs, with a source-type discriminator?)
- Which session-state keys does `tab_inbound` read or write? (e.g., `inbound_*`, `prod_inbound_*`)

### 5.2 Identify all consumers

For every data surface identified in §5.1, list every module that reads from or writes to it. Consult `DEPENDENCY_MAP.md`. Grep the codebase:

- All `.py` files in project root and `pages/`
- SQL strings (including f-strings, parameterized queries, `db_manager.py` function bodies)
- OpenSearch query DSL referencing source-type or production fields
- Session-state keys (`st.session_state["..."]` and `st.session_state['...']`)
- File path construction for inbound volumes
- Any cross-module function calls that operate on inbound documents

**Specific questions you need answered by the end of this step:**

- Does `4_Review.py` filter, flag, or group inbound docs differently from custodial?
- Does `3_Analytics.py` include inbound docs in near-dupe / cluster analysis, and is that correct behavior?
- Does `5_Production.py` outbound-assembly already exclude inbound docs from being re-produced? (It must. If it does not, that's a privilege/work-product hazard and a fix-in-passing candidate.)
- Does `7_Custodians.py` represent inbound productions as pseudo-custodians? If so, that's a data-model smell to flag to the maintainer.

### 5.3 Confirm root cause for each existing bug (one-sentence statements)

- **Orphan detector false positive:** "The orphan detector at `pages/5_Production.py:239-264` enumerates `Productions/<name>/IMAGES/TEMP_*` and `NATIVES/STAGED_*` folders without consulting the database to determine whether the containing production is still in-flight, so legitimately-staged files from a Pass 1 awaiting Finalize are classified as abandoned."
- **Privilege Log tab blank:** "The `st.stop()` calls at `pages/5_Production.py:2229` and `:2234` terminate the entire Streamlit script when the outbound production is in the Pass 1 checkpoint state, preventing the subsequent `with tab_inbound:` and `with tab_privlog:` blocks from ever executing."

### 5.4 Three-strike circuit breaker

If the extraction or bug fix fails validation three times, STOP. Report to the maintainer before a fourth attempt.

---

## 6. In-Scope Changes

### 6.1 New file: `pages/9_InboundProduction.py`

Create with full module metadata header block, `version: 1.0.0`, `project_ver` matching current `__version__` in `config.py`.

Structure (mirror conventions from existing pages):

1. **Access gate.** Reviewer role minimum? Manager minimum? Check what `tab_inbound` currently requires and preserve it. Annotate with `# permission: ingest_inbound_production`.
2. **Case status check.** Closed cases must block write operations (ingest) but allow reads (viewing already-ingested inbound productions). Mirror the pattern from other pages.
3. **Layout.** Single-purpose page, no tabs needed unless current `tab_inbound` has internal subtabs. Preserve all existing functionality — load file upload, field mapping, ingest trigger, per-volume status display, Bates range display, etc.
4. **Session-state keys.** Rename any keys currently prefixed `prod_inbound_*` or similar to a clean `inbound_*` prefix since this is no longer a sub-tab of Production. Document the rename in the commit message and update any cross-module consumers found in §5.2.

### 6.2 Changes to `pages/5_Production.py`

#### 6.2.1 Remove `tab_inbound`

- Delete the `tab_inbound` entry from the `st.tabs([...])` call at line 310 (approximate).
- Delete the entire `with tab_inbound:` block.
- Move any helper functions used *only* by `tab_inbound` to the new `9_InboundProduction.py` file. Helpers shared between inbound and outbound (if any) move to `db_manager.py` or a new helper module — do not leave them stranded in `5_Production.py`.

#### 6.2.2 Phase-gating refactor (fixes "Privilege Log blank" bug)

Replace the `st.stop()` pattern at lines ~2229 and ~2234 with an extract-to-function pattern:

```python
# Before (current bug):
if st.session_state.get('prod_pass1_complete') and not st.session_state.get('prod_finalized'):
    _render_pass1_checkpoint()
    st.stop()   # ← kills script, hides privilege log
if st.session_state.get('prod_finalized'):
    _render_finalized_view()
    st.stop()

# After:
with tab_outbound:
    if st.session_state.get('prod_pass1_complete') and not st.session_state.get('prod_finalized'):
        _render_pass1_checkpoint()
    elif st.session_state.get('prod_finalized'):
        _render_finalized_view()
    else:
        _render_outbound_grid()   # extract existing grid/selection code to a helper
```

The extracted `_render_outbound_grid()` function contains the code that currently executes after the `st.stop()` calls. This is a pure code move (no logic change); verify by diffing line-by-line.

**Important:** After extracting, confirm that the helper does not rely on any code that currently runs *before* the `st.stop()` checks. If it does (e.g., loading query results, setting up session state), that setup must move to the top of `with tab_outbound:` before the if-chain, OR be moved into the helper itself.

#### 6.2.3 Tab structure reduction

With `tab_inbound` removed, the page has two tabs: `tab_outbound` and `tab_privlog`. Options:

- Keep as two tabs (minimal change).
- Promote `tab_outbound` to be the default page body and relegate `tab_privlog` to a single tab or a sidebar section. (More invasive; defer unless the maintainer wants this.)

**Recommendation:** keep two tabs for this sprint. Post-sprint, the maintainer can evaluate whether the page reads better as a flat layout.

#### 6.2.4 Rename the display title

Change the page header from `Module 5: Production & Export 📦` to something accurate, e.g. `Module 5: Outbound Production & Privilege Log 📦`. Update any internal references to the display string. **Do not rename the filename** — that would cascade through navigation and bookmarks.

#### 6.2.5 Orphan detector fix (DB-backed)

Rewrite the orphan detector at `pages/5_Production.py:239-264` to consult the database rather than session state.

Proposed logic:
1. Enumerate production folders on disk as today.
2. For each folder, look up the corresponding production row in the DB (e.g., by name or ID).
3. A folder is "orphaned" only if one of:
   - No DB row exists, OR
   - The DB row's status is `abandoned`, `aborted`, or equivalent, OR
   - The DB row's status is `finalized` but TEMP/STAGED folders still exist (staging should be cleaned on finalize)
4. A folder is NOT orphaned if the DB row's status is `pass1_complete`, `in_progress`, or any other active state. Those files are legitimately staged.

**Pre-requisite investigation:** Confirm the exact status column and values in use. If the DB doesn't currently track production status at this granularity, either (a) add the status column and migration as part of this sprint (small addition), or (b) flag to the maintainer that this fix requires a DB schema change first.

### 6.3 `db_manager.py`

- Move any inbound-production-specific query functions into a dedicated section commented clearly (e.g., `# --- Inbound Production Queries ---`). No renames unless names are misleading.
- If any inbound-specific queries live inline in `5_Production.py` (direct SQL is a smell per CLAUDE.md), migrate them to `db_manager.py` before moving to `9_InboundProduction.py`. Do not carry forward the smell into the new module.
- Version-bump `db_manager.py` per CLAUDE.md rules (patch bump if behavior unchanged; minor bump if new functions added).

### 6.4 `DEPENDENCY_MAP.md`

- Add a new section (or update existing) documenting the inbound production module's data surfaces: DB columns, session state keys, file path conventions, OpenSearch fields, cross-module consumers.
- If a new regression pattern emerged during investigation (e.g., inbound docs were appearing in outbound assembly — see §5.2 check), add it to §7 "Known Regression Patterns."
- Update the `<!-- Last audited: -->` timestamp at the top of the file.

### 6.5 Documentation cascade (per Standing Orders — Context Maintenance)

Update each of the following to reflect the new module:

- **`CLAUDE.md` Current State table** — bump "Last completed sprint" to this one, update "What's next."
- **`MEMORY.md`** (Claude memory directory) — reflect the new module and the resolved bugs.
- **`Walkthrough.md`** — add a section on inbound production as a distinct workflow for partners/supervising attorneys.
- **`Technical Overview.md`** — add module to architecture diagram; document the DB surfaces, file path conventions, and cross-module interactions.
- **`User_Guide.md`** — add end-user instructions for loading inbound productions via the new module. Update any references to "Inbound Productions tab" to point to the new module.
- **`PROJECT_CONTEXT.md`** — add comprehensive AI-development context for the new module.

### 6.6 CHANGELOG.md entries

At minimum:

```
- NEW: pages/9_InboundProduction.py — dedicated module for loading opposing counsel production volumes
- CHANGE: pages/5_Production.py — removed inbound production tab (extracted to 9_InboundProduction.py); renamed page title to reflect outbound scope
- FIX: pages/5_Production.py — privilege log tab no longer blank during Pass 1 checkpoint (replaced st.stop() with if/elif/else scoped to tab_outbound)
- FIX: pages/5_Production.py — orphan detector now consults production status in DB rather than session state; no longer flags legitimately-staged Pass 1 files as abandoned after browser close
- DOCS: updated Walkthrough.md, Technical Overview.md, User_Guide.md, PROJECT_CONTEXT.md, DEPENDENCY_MAP.md, CLAUDE.md to reflect new module boundary
```

---

## 7. Out of Scope (defer to future sprints)

Do NOT add any of the following in this sprint, even if tempting:

- Rolling production tracking (volume 1 → 2 → 3 continuation logic)
- Production overlays (replace-these-docs update handling)
- Production corrections / clawback workflows
- Authenticity certification / 26(g) receipt logs
- Multi-party discovery UI (producing-party dropdown beyond what exists today)
- Changes to the outbound production workflow beyond what's needed to remove inbound
- Changes to Sync module (separate decision for later)
- Any renumbering of existing pages

If investigation reveals a bug or hazard outside this scope (e.g., inbound docs appearing in outbound assembly), flag it to the maintainer, do not silently fix unless it is a privilege/ethics hazard — in which case fix in a separate commit with a clear callout in the commit message.

---

## 8. Cross-Module Impact Audit Checklist (per Standing Orders)

Complete after implementation, before the final commit.

- [ ] Every session-state key renamed or relocated has been updated in every consumer module found in §5.2.
- [ ] Every DB column or file path referenced by inbound production has been verified in `DEPENDENCY_MAP.md`.
- [ ] `4_Review.py` still renders inbound documents correctly (or still filters them out if that's the design).
- [ ] `3_Analytics.py` still treats inbound docs according to design (include/exclude from clustering as appropriate).
- [ ] `5_Production.py` outbound assembly still correctly excludes inbound documents from being re-produced.
- [ ] `7_Custodians.py` does not break if inbound docs appear in custodian queries (or if they were previously represented as pseudo-custodians, flag that behavior).
- [ ] All file paths constructed via `os.path.join` or f-strings pointing to inbound volumes still resolve correctly after module move.
- [ ] OpenSearch queries that filter on source-type or production-origin still return the expected documents.
- [ ] Commit message includes the audit report per Standing Orders: `Impact audit: N change targets, M cross-refs verified, K fixes applied, J items flagged for human review.`

---

## 9. Testing Checklist

End-to-end scenarios to run against the dev venv (`.venv/Scripts/python.exe`) before handing back to the maintainer:

### 9.1 New module smoke test
- [ ] `pages/9_InboundProduction.py` loads without error
- [ ] Access gate enforces correct role
- [ ] Closed-case check blocks ingest, allows view
- [ ] Uploading a sample load file + native set produces ingested documents with correct Bates, metadata, and source-type tagging
- [ ] Ingested documents appear in `4_Review.py` with correct source-type indicator

### 9.2 Production page regression test
- [ ] `pages/5_Production.py` loads without error
- [ ] Outbound tab renders normal grid when no production is in-flight
- [ ] Pass 1 checkpoint UI renders inside outbound tab when a production is in the Pass 1 state
- [ ] **Privilege log tab renders and is populated during Pass 1 checkpoint** (this is the core bug fix)
- [ ] Finalized-view UI renders inside outbound tab when a production is finalized
- [ ] Orphan detector does NOT flag a freshly-completed Pass 1 production as orphaned (test: complete Pass 1, close browser, reopen, verify no false warning)
- [ ] Orphan detector DOES flag a truly abandoned production (test: abort a Pass 1, verify warning appears and cleanup works)

### 9.3 Interaction test
- [ ] With a Pass 1 outbound production in-flight, user can navigate to `9_InboundProduction.py` and ingest an unrelated inbound production volume **without being locked out** (this is the workflow hazard the restructure resolves)
- [ ] Inbound documents ingested during a Pass 1 in-flight state do NOT appear in the outbound volume when finalized

### 9.4 Documentation sanity
- [ ] All doc updates in §6.5 render correctly (no broken links, no stale tab references)
- [ ] CLAUDE.md Current State table is updated with new sprint entry

---

## 10. Version Tracking Requirements (reminder)

Per CLAUDE.md §"Version Tracking — Mandatory on Every Edit":

- **New file** `9_InboundProduction.py` gets full header block, `version: 1.0.0`, `project_ver` matching `config.py` `__version__`.
- **Modified files** (`5_Production.py`, `db_manager.py`, any others touched): bump `version` per the rules (patch for behavior change, minor for new function/class, no bump for formatting only). Update `last_modified` to current `YYYY-MM-DD HH:MM` (24-hour local time). Set `modified_by: claude-code`. Set `last_commit: pending`.
- **Never bump** `__version__` in `config.py` yourself. Only the maintainer does that.

Run the self-check in CLAUDE.md before any commit.

---

## 11. Acceptance Criteria ("done" looks like)

- [ ] `pages/9_InboundProduction.py` exists, is functional, and is the sole home of the inbound-productions workflow
- [ ] `pages/5_Production.py` contains only outbound production + privilege log
- [ ] Privilege log tab renders correctly in all outbound states (pre-Pass-1, during Pass 1 checkpoint, finalized)
- [ ] Orphan detector no longer produces false positives on legitimately-staged Pass 1 productions (verified after a simulated browser close)
- [ ] A user with an in-flight Pass 1 outbound production can still ingest an unrelated inbound production volume
- [ ] All cross-module consumers identified in §5.2 have been verified or fixed
- [ ] DEPENDENCY_MAP.md reflects the new module boundary
- [ ] All version headers are updated and CHANGELOG.md has entries
- [ ] All documentation files listed in §6.5 are updated
- [ ] Commit message includes the Impact Audit report per Standing Orders
- [ ] the maintainer has reviewed a test run end-to-end and confirmed the workflow hazard is resolved

---

## 12. Notes for CLI Claude

- **Do not skip the pre-investigation.** The maintainer has been burned by sprints that jumped to code; CLAUDE.md's "Iron Law" (no fix without confirmed root cause) is active on this project.
- **Do not silently rename** session-state keys or DB columns. If a rename seems warranted, call it out explicitly in the spec-compliance commit and update `DEPENDENCY_MAP.md` in the same commit.
- **If investigation reveals the situation is materially different from what this spec assumes** (e.g., inbound docs are already represented in a way that makes module extraction complex, or DB schema lacks the status column needed for the orphan detector fix), STOP and report back to the maintainer before continuing. Do not improvise a workaround.
- **Bundle the two bug fixes with the extraction.** They are root-caused in the same file and the restructure dissolves or upgrades them naturally.
- **This is a paralegal-facing platform in active use.** Defensibility and data integrity trump cleverness. If a choice is between a simple, obvious, slightly-verbose approach and a slick abstraction, take the simple approach.

---

**End of spec.**
