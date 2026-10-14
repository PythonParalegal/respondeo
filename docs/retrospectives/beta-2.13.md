# beta-2.13 Retrospective

**Sprint:** `beta-2.13`
**Version tag cut:** None — informal close; no `v2.13.0` git tag.
**Commit range:** sprint open (post-v2.12.0 Current State refresh) through sprint-wrap (CLAUDE.md Current State + beta-2.14 transition plan) — 11 commits on branch.
**Written:** `2026-04` by PM Claude (WARP tab)
**Author:** PM Claude

---

## 1. Sprint Scope

Beta-2.13 opened with an 8-commit DB-hygiene roadmap inherited from beta-2.12's deferral: **C1** Flag #20 (INSERT OR IGNORE silent drop on `document_productions.enddoc NOT NULL`) → **C2** Flag #18 narrow `conn=None` scaffolding → **C3** Flag #5 (9 page-held-conn sites + log_audit silent-drop surface) → **C4** Flag #16 (duplicate `get_root` fixture in `tests/test_bates.py:185`) → **C5** Flag #13 (aborted-run UX hygiene — `None — None` / `0 docs` in production history) → **C6** PM grep-count discipline canonization (Check 11 install in `preflight_drafting_checklist.md`, surfaced in beta-2.12 retrospective as a recurring PM drift pattern) → **C7** cleanup audit scheduling for beta-2.15 → **C8** sprint-close addendum + v2.13.0 tag cut.

Per the beta-2.12 retrospective's explicit sprint-open hand-off: *"beta-2.13's Commit 1 is naturally Flag #20 (INSERT OR IGNORE silent drop) per the registry."* The 8-commit plan was durable roadmap work — no novel architecture, no large refactors, each commit bounded and well-characterized.

Sprint theme in retrospect: **roadmap preemption by a hotfix chain.** Only C1 of the original 8 shipped; C2–C8 carry forward to beta-2.14 with numbering preserved. No version tag cut — the sprint closed informally by the maintainer's explicit decision so the planned C2–C8 roadmap can reboot on a clean branch rather than being orphaned at version 2.13.0 mid-plan.

## 2. What Shipped

11 commits on branch:

| Commit | Summary |
| -------- | --------- |
| Sprint-open 1/4 | DOCS: CLAUDE.md Current State refresh post-v2.12.0 (housekeeping from beta-2.12 close — the "post-tag Current State refresh always trails the sprint-close commit" pattern beta-2.12 retrospective anticipated). Opens beta-2.13 sprint. |
| Sprint-open 2/4 | DOCS: docs/retrospectives/README.md backfill of beta-2.12 catalogue entry. Routine index maintenance the beta-2.12 close missed. |
| Sprint-open 3/4 | DOCS: Migrate PM Claude from Cowork sandbox to WARP two-tab model. New `docs/roles/` tier, `/pm` + `/cli` slash commands, full role definitions with write boundaries. Triggered by Cowork's environmental-observation failures during the beta-2.13 C1 preflight draft (phantom-directory claim that couldn't be reproduced on the filesystem). |
| Sprint-open 4/4 | Role + collaboration-workflow hygiene pass — 14 findings across role definitions, slash commands, `docs/templates/pm_cli_collaboration_workflow.md`, `docs/lessons/n-stage-gate-revision-handling.md`, `docs/FLAG_REGISTRY.md` maintenance-rule reconciliation, `docs/templates/preflight_template.md` + `docs/templates/preflight_lightweight.md` §8.1 / §Appendix A ledger stub installs. Shipped without a formal preflight under explicit maintainer "spirit-of-rule" wiggle-room authorization (logged in C1's Flag #20 preflight §0.0 drafting context as the precedent). |
| C1 — Flag #20 | FIX: db_manager.py — `d.enddoc` → `COALESCE(d.enddoc, d.begdoc)` in the one-time `document_productions` backfill SELECT. Pre-INSERT `_eligible` source-row count + post-INSERT `_dropped` diff + `logger.warning` canary on nonzero drop. Pinned-value discipline on the two WHERE clauses. Regression pin at `tests/test_document_productions_inbound_filter.py::test_backfill_recovers_documents_with_null_enddoc`. Only code-change commit that shipped per the original roadmap. Preflight cycle: v1 (initial draft, CLI v1 check found 2 hygiene + 1 PM-judgment) → v1 finalized (the maintainer's ratified open questions) → v2 (resolves CLI v1 findings) → v2 CLI delta-check clean. Clean two-revision cycle — the gate worked as designed. |
| Hotfix 1/4 | FIX: pages/4_Review.py — Bulk Bates popover filter not applied to Review grid. Guard extended from `if search_query and search_hit_ids:` to `if (search_query and search_hit_ids) or bates_batch_text:`. Regression chain starts here. |
| Hotfix 2/4 | Bates parser unification (NEW `db_manager.parse_bates_token`) + filter-precedence for targeted Bates lookup. Hyphenated Bates (`ABC-000700`) had been silently collapsing to a `('', -1)` sentinel in the popover's inline regex, producing banner counts that were "docs with populated begdoc" independent of user input. Pinned-value helper + 9-test `TestParseBatesToken` class. Also bypasses three hygiene filters (`Hide Junk Images`, `Hide Not Responsive`, `Show Suppressed Items`) when a Bates batch is active — user who pastes specific Bates has named the exact docs they want. |
| Hotfix 3/4 | FIX: pages/4_Review.py — Bates-batch guard crashed on Show-Family pivot. Regression: the family-override branch reset `search_hit_ids` to `None` but the `or bates_batch_text` clause still entered the block, passing `None` to `df['control_number'].isin()` and raising `TypeError`. Guard aligned with the pattern already used at three adjacent hygiene-filter sites. |
| Hotfix 4/4 | FIX: pages/4_Review.py — Paperclip-attachment click stomped by persistent grid selection. Unrelated to the Bates-batch chain — pre-existing bug surfaced during routine review use. On peek-mode rerun, Streamlit's `st.dataframe` persists selection state, so the grid's single-selection handler re-fires with stale `selected_rows` and pops `_peek_cn` before the viewer reads it. Fix: `family_nav = True` flag + guarded pop inside `not family_nav` branch. |
| Sprint hygiene | NEW: `docs/archive/specs/neardupe_false_positive_sensitivity.md` — unshipped design spec for near-dupe analytics false-positive surface (template-similar-but-content-distinct invoice-style documents clustered under NearDupe-Suppressed). Flag #22 registered in `docs/FLAG_REGISTRY.md` Active table, State `Characterized`. Roadmap-flagged — not beta-2.14 scope unless redirected. |
| Sprint-wrap | DOCS: CLAUDE.md — Current State table refreshed for beta-2.13 informal close. Captures the actual 9-commit arc, notes only C1 of 8 planned shipped, describes beta-2.14 carrying forward deferred C2–C8 with numbering preserved. No `v2.13.0` tag cut. |

## 3. Goals vs. Outcomes

### Achieved as planned

- **C1 Flag #20 — INSERT OR IGNORE silent drop.** The only commit that landed per original roadmap. Preflight cycle was clean: v1 → v2 revision resolved all CLI findings, v2 delta-check came back clean, execution landed in one pass. COALESCE fix + eligibility-diff observability + regression pin all shipped as designed.

### Achieved with adjustment

- **Sprint-open WARP migration.** Sprint-open was originally scoped as minor housekeeping; expanded when Cowork's environmental-observation failures during the C1 preflight draft surfaced the need for a PM-sandbox migration. Role definitions, `/pm` + `/cli` slash commands, write boundaries, and the 14-finding hygiene sweep all landed in the sprint-open arc. Defensibly in-scope — the migration was blocking further preflight work — but nowhere near the original sprint plan.
- **Flag #22 registration.** Scope expansion: a design review of near-dupe clustering on template-heavy (invoice-style) documents produced the near-dupe false-positive spec. Registered Flag #22 + tracked the spec at sprint hygiene time rather than deferring to beta-2.14.

### Deferred

- **C2 Flag #18** (narrow `conn=None` scaffolding for the specific db_manager functions Flag #5 needs) — still Active. First candidate for beta-2.14.
- **C3 Flag #5** (9 page-held-conn sites + log_audit silent-drop surface; may split C3a/C3b) — still Characterized/Deferred.
- **C4 Flag #16** (duplicate `get_root` fixture in `tests/test_bates.py:185`) — still Active.
- **C5 Flag #13** (aborted-run UX render hygiene — `None — None` / `0 docs`) — still Dormant (beta-2.10 retrospective origin).
- **C6 PM grep-count discipline canonization** (Check 11 install in `preflight_drafting_checklist.md`, beta-2.12 retrospective's recurring PM drift observation) — still pending.
- **C7 cleanup audit scheduling for beta-2.15** — still pending.
- **C8 sprint-close addendum + v2.13.0 tag** — sprint closed informally instead; no tag, and this addendum (retrospective + audit archival + context maintenance) landed as the first commit on beta-2.14.

## 4. Surprises and Learnings

The sprint opened on plan. C1 landed on 2026-04 after a clean two-revision preflight cycle — the WARP migration had just finished, the N-Stage Gate held up through its first trial run in the new harness, and the roadmap looked set to proceed through C2 next. Two days later the sprint blew up in two directions at once.

Separately, a design review of near-dupe clustering produced the near-dupe false-positive spec (template-similar invoice-style documents clustering together). None of that landed as beta-2.13 code; all of it shaped what could ship.

The Bates-batch regression chain was a textbook hotfix-on-hotfix pattern. Hotfix 1 (Bulk Bates popover filter not applied to grid) seemed self-contained — a single guard-clause extension. Hotfix 2 (Bates parser unification) fixed a separate but adjacent bug (hyphenated Bates collapsing to `('', -1)` sentinels, making every query match every doc with a populated begdoc) that was actually the root cause the user had hit first — the "grid showed all docs" symptom in Hotfix 1 was downstream of the parser returning zero real matches. Hotfix 3 (Bates-batch guard crashes on Show-Family pivot) was the direct regression from Hotfix 1's guard extension: the `or bates_batch_text` clause let the block enter family-override mode with `search_hit_ids = None`, causing `TypeError` at `.isin(None)`. Three commits, each containing the next's defect. In hindsight the arc says something about shipping under time pressure without explicit verification that a new code path doesn't interact with existing short-circuits on the same function — the candidate lesson the maintainer flagged for the beta-2.13 auto-memory as "Hotfix-on-hotfix regression chain."

Hotfix 4 (paperclip-click stomp) was unrelated to the Bates chain and surfaced during routine review use. It had been a pre-existing defect for weeks — the peek-mode rerun interaction with `st.dataframe`'s persistent selection was invisible because the usual workaround ("Show Full Family in Grid → Back to search results") incidentally cleared the selection state. PM initially misread this as a scope gap (flagging it as missing from the March `family_nav = True` infrastructure); `git blame` showed the in-queue family_nav setter had been in since March, and the actual missing piece was the peek-mode sibling branch. Precedent caught here: *always run `git show HEAD:<file>` and/or `git blame` on suspected-missing edits before raising concerns* — the memory entry now captures this as a durable PM-side check.

The WARP migration sprint-open (4 commits) was itself an arc worth preserving. PM-Cowork's environmental-observation failures during the C1 preflight draft (the "phantom directory" misdiagnosis — Cowork reported `docs/audits/` as non-existent when it was a real, writable, empty directory) prompted the migration, which in turn exposed 14 findings in the role definitions and collaboration workflow — including a Stage-2-issuer contradiction (who issues Stage 2 greenlight? the role docs and the lesson files disagreed), the N/A-for-lightweight preflight gaps, and the canonical ledger location for the drafting checklist. All 14 landed as a doc-only sweep without a formal preflight — the first maintainer-authorized "spirit-of-rule" wiggle-room exercise, logged in the C1 Flag #20 preflight §0.0 as precedent for future narrow exemptions.

Two scope-expansion probes fired correctly during the hotfix chain: Hotfix 2 expanded inline to add both `parse_bates_token` + the 9-test `TestParseBatesToken` class + the filter-precedence change (three things bundled because they had the same root cause, same fix pattern, same hazard class); Hotfix 4's paperclip-click bundled two code changes inside one hotfix for the same reason. Probes that did NOT fire but should have: the Hotfix 1 author (working with the maintainer) didn't probe for "what does the new `or bates_batch_text` branch imply for the existing family-override short-circuit?" — that scope probe would have caught Hotfix 3 at draft time rather than at crash time.

The sprint closed informally by the maintainer's explicit decision. Cutting `v2.13.0` would have tagged a state where only 1 of 8 planned commits shipped; the remaining 7 carry to beta-2.14 with their sprint numbering preserved (C2 through C8), which means beta-2.14's C1 slot is permanently orphaned. The trade-off: mental-model continuity for the C#-numbered roadmap at the cost of one unused slot. Precedent: sprint can close informally without a version tag if the originally-planned scope didn't ship.

## 5. Lessons Canonized

No new `docs/lessons/` files landed this sprint. Candidates surfaced but were left for future sprints:

- **Hotfix-on-hotfix regression chain pattern** — the Bates-batch triad is a textbook example. Candidate lesson text: "When shipping a hotfix, explicitly verify that the fix's new code path doesn't interact with existing short-circuits on the same function." Noted in `project_beta213_sprint.md` auto-memory as a lesson candidate. Not canonized this sprint.
- **Sprint-arc pivot pattern** — beta-2.12 and beta-2.13 both saw hotfix/hygiene work consume the planned roadmap. Two-sprint recurrence now. Candidate lesson: "Sprint roadmaps are plans, not contracts — unplanned work pre-empts, retrospective captures the actual arc."
- **Review-derived spec pattern** — Flag #22's spec is a new category: a design-review outcome that produces an unshipped spec needing Flag registration before it can live in the repo. Candidate template: "review-derived spec" preflight scaffold.
- **`git show HEAD:<file>` before raising scope concerns** — the paperclip-click misread establishes the precedent but isn't yet canonized.

No new `docs/templates/` entries.

No new `docs/references/` entries.

No new CLAUDE.md Standing Orders.

`docs/FLAG_REGISTRY.md` updates: Flag #20 moved Active → Dormant/Closed (C1 shipping); Flag #22 registered (beta-2.13 sprint hygiene).

## 6. Gotchas for Future Sprints

- **C1 slot permanently orphaned on beta-2.14.** Commit numbering carries across the informal close: beta-2.14 opens at C2, not C1. Preserves C2–C8 mental-model continuity for the Flag #18 → #5 → #16 → #13 → PM-grep-discipline → cleanup-audit → sprint-close roadmap. Documented in CLAUDE.md Current State "What's next."
- **Flag #22 (near-dupe false-positive sensitivity) is roadmap-flagged but NOT beta-2.14 scope unless the maintainer redirects.** Spec at `docs/archive/specs/neardupe_false_positive_sensitivity.md`, characterized but unshipped. If beta-2.14's C2–C8 plan holds, Flag #22 waits for beta-2.15 or later.
- **Ship-without-preflight wiggle room was exercised multiple times this sprint** (WARP hygiene sweep, three Bates hotfixes, paperclip hotfix). Each was a defensible case — iterative discovery, hotfix work, post-hoc validation — but there is no formal policy on when the wiggle-room applies. Future sprint: consider a `docs/lessons/preflight-wiggle-room.md` or a CLAUDE.md subsection codifying the narrow conditions (same-session iterative discovery, hotfix response, post-hoc user-validated bugfix).
- **PM grep-count discipline Check 11 is still pending install** (beta-2.12 retrospective's observation). Deferred through beta-2.13 because the sprint pivoted before C6's slot. If the pattern recurs in beta-2.14, prioritize C6 earlier rather than tail-ending it.
- **Paperclip-click misread as scope gap.** Precedent now recorded in `project_beta213_sprint.md`: always `git show HEAD:<file>` and/or `git blame` on suspected-missing edits before raising scope concerns. Pre-existing code is the default; in-session addition is the exception. Not yet canonized as a lesson.
- **`docs/FLAG_REGISTRY.md` cross-reference table at the bottom is stale.** Table ends at beta-2.11 C6a; beta-2.12 and beta-2.13 entries were never backfilled. Not load-bearing for future lookups (the main Active/Dormant tables carry the current state) but a recurring housekeeping drift. Candidate to include at whichever sprint gets a FLAG_REGISTRY touch next.
- **CHANGELOG staleness risk.** `## [beta-2.13] — In Progress` is the exact pattern beta-2.12 retrospective warned about. This retrospective-landing commit flips it to `Shipped 2026-04 (informal close — no git tag cut)`. The Tag-cut ordering Standing Order's sprint-close sequence (step 3: context maintenance refresh) is meant to catch this — worth verifying at beta-2.14 close that the pattern actually broke.

---

## Provenance

This retrospective was written by PM Claude (WARP tab) on 2026-04 during the beta-2.13 sprint-close addendum commit's drafting phase. Landing as part of `beta-2.14 Commit 1` (beta-2.13 sprint-close addendum) because beta-2.13 itself closed informally without a sprint-close addendum. The maintainer reviewed and approved the retrospective in the preflight's Stage-1 review, and CLI performed the pre-flight check on the addendum commit's full scope (retrospective creation, audit-doc archival, FLAG_REGISTRY ref update, CHANGELOG entries, CLAUDE.md Current State refresh) before Stage-2 greenlight.
