# beta-2.14 Retrospective

**Sprint:** `beta-2.14`
**Version tag cut:** `v2.14.0` (pending merge to main + tag cut)
**Commit range:** Commit 1 (beta-2.13 sprint-close addendum landing on beta-2.14 branch) through this addendum (Commit 13)
**Written:** 2026-04-30 by PM Claude (WARP tab)
**Author:** PM Claude

---

## 1. Sprint Scope

Beta-2.14 inherited a 7-commit roadmap from beta-2.13's informal close (C2-C8 of the original 8-commit DB-hygiene plan, with C1 Flag #20 already shipped on beta-2.13). The plan: C2 Flag #18 narrow `conn=None` scaffolding → C3 Flag #5 (9 page-held-conn sites + log_audit silent-drop surface, anticipated to split into C3a/C3b) → C4 Flag #16 (test_bates.py duplicate `get_root` fixture consolidation) → C5 Flag #13 (aborted-run UX render hygiene) → C6 PM grep-count discipline canonization (Check 11 install, accumulated empirical observations from prior sprints) → C7 cleanup audit scheduling for beta-2.15 → C8 sprint-close addendum + `v2.13.0` tag cut.

Per the beta-2.13 retrospective hand-off: beta-2.14 was the second sprint executed under the WARP two-tab PM/CLI collaboration model. The N-Stage Gate had been exercised lightly during beta-2.13 (only C1 went through a full preflight cycle); beta-2.14 would be its substantive trial.

## 2. What Shipped

12 substantive commits + this sprint-close addendum:

| Commit | Summary |
| -------- | --------- |
| 1 (beta-2.13 close) | DOCS: beta-2.13 sprint-close addendum landing on beta-2.14 branch (retrospective + audit-doc archival to `docs/archive/audits/beta-2.13/` + CLAUDE.md Current State refresh). Beta-2.13 closed informally without a `v2.13.0` tag per the maintainer's decision; this addendum landed on the new branch. |
| 2 (sprint-open) | DOCS: edit-tool-staging-gap lesson canonization. Sprint-open hygiene observation that `Edit` and `Write` tools modify but don't stage; pre-commit verification must scan `git status --short` for leading-space-`M` and `??` entries. |
| 3 (C2 / Flag #18) | NEW (db_manager API): narrow `conn=None` scaffolding on 4 db_manager functions Flag #5 needs. Avoided full Flag #18 sweep across all 163 public functions; scoped to the specific functions C3 would consume. |
| 4 (C3a / Flag #5 Pattern X core) | FIX: Flag #5 Pattern X log_audit hardening, 3 sites in `2_Processor.py:198, 240` + `7_Custodians.py:704`. Naive `conn=conn` restored atomic-audit intent that the separate-conn implementation broke (phantom-audit-on-rollback). |
| 5 (Flag #24) | FIX: log_audit `user=` kwarg typo, 3 sites in `pages/7_Custodians.py:545`, `home.py:761`, `home.py:807`. Silent no-op since written; surfaced during C3a CLI v1 H-1 finding. Flag #24 registered + closed in same commit. |
| 6 (C3a-followup / Flag #5 Pattern X sub-span A Class A) | FIX: Flag #5 Pattern X sub-span A, 4 sites in `6_Sync.py:374, 380, 405, 414`. Class A subset of sub-span A (the success-path sites). Class B sub-span A (3 error-path sites at `6_Sync.py:328, 341, 354`) deferred to beta-2.15+ per commit-restructuring requirement. |
| 7 (C3b / Flag #5 Pattern C) | FIX: Flag #5 Pattern C `privilege_status` nesting in `4_Review.py:_bulk_apply_op`, 2 sites at `4_Review.py:3287, 3292`. PM grep-sweep confirmed Pattern C surface fully closed by this commit (only Pattern C site in codebase). |
| 8 (C8 docs hygiene — off-roadmap) | DOCS: documentation hygiene pass; CLAUDE.md Current State table trimmed. |
| 9 (C8a — off-roadmap) | DOCS: CHANGELOG wording fix for Commit 8. |
| 10 (C5 / Flag #13) | FIX: Flag #13 aborted-run UX render hygiene. Asymmetric scope per the maintainer's Stage 1: home grid shows aborted with Status column + `—` for Bates; defensibility PDF section 6.2 excludes aborted runs entirely; 5_Production.py post-finalization banner gets defensive `(value or '—')`. Court-facing PDF stays clean. |
| 11 (C6 / grep-count canonization) | DOCS: PM grep-count discipline canonization. New `docs/lessons/grep-count-discipline.md` (5 observations / 3 families) + Check 11 install in `preflight_drafting_checklist.md` + ledger row in both heavyweight and lightweight templates. v3 cycle surfaced 2 new observations (sprint-mis-cite verification, cluster-interaction defects) bookmarked for future canonization. |
| 12 (C7 / beta-2.15 spec) | DOCS: beta-2.15 cleanup-audit roadmap proposal. New `docs/archive/specs/beta_2_15_roadmap_proposal.md` enumerating 10 candidates across 4 priority tiers + ROADMAP_TODO.md bookmark + header refresh. |
| 13 (C8 / sprint close, this commit) | DOCS: beta-2.14 sprint-close addendum. Retrospective + audit-doc archival + tier-README + living-doc ref updates + CLAUDE.md Current State refresh + `__version__` 2.12.0 → 2.14.0 + FLAG_REGISTRY (Flag #16 WONTFIX, Flag #23 register-and-close for CHANGELOG ordering) + user-facing doc updates for Flag #13 + retrospectives README catalogue backfill + this preflight self-archives. |

## 3. Goals vs. Outcomes

### Achieved as planned

- **C2 Flag #18, C3a/C3a-followup/C3b Flag #5, C5 Flag #13, C6 grep-count canonization, C7 beta-2.15 spec, C8 this addendum.** Every roadmap commit shipped per its design. Pattern X / Pattern C of Flag #5 fully closed; 9 sites hardened total.
- **Tag identity decision (`v2.14.0`).** The maintainer confirmed skipping `v2.13.0` cleanly; the substantive 12-commit sprint is recognizably 2.14.x scope rather than a 2.13.x continuation.

### Achieved with adjustment

- **C4 Flag #16 disposition.** Recommended WONTFIX 2026-04-30 after PM reconnaissance (test-inlining-by-design as regression-snapshot decoupled from production drift; original Flag #8 preflight already considered + deferred cross-file consolidation; consolidation would defeat broader inline-mirror convention). The maintainer confirmed WONTFIX. Closed in this addendum's FLAG_REGISTRY edit.
- **Docs hygiene (Commit 8) + C8a (Commit 9).** Off-roadmap insertions. The chronological commit numbering then diverged from the roadmap-C# label convention — chronological commits 8 and 9 don't map to roadmap C8/C9; instead, roadmap-C8 became chronological Commit 13.

### Deferred

- **Class B sub-span A** (3 sites in 6_Sync.py:328, 341, 354) — requires commit-restructuring (add `conn.commit()` after each error-path UPDATE+audit pair before `continue`). Bookmarked as M-1 in the beta-2.15 roadmap proposal.
- **Pattern A consolidation surfaces** (function-local + module-level held conns at 6_Sync.py:278, 516; 7_Custodians.py:79) — broader refactor; bookmarked as M-2 in beta-2.15 proposal.
- **Flag #22 near-dupe false-positive sensitivity** — spec at `docs/archive/specs/neardupe_false_positive_sensitivity.md` ready for execution. Bookmarked as S-1 in beta-2.15 proposal.
- **CI secrets/PII guard** — bookmarked as S-2 in beta-2.15 proposal.
- **Stale `TestProductionInboundExclusion` doc reference at `tests/test_bates.py:331`** — bookmarked as S-3.
- **3 grep-count canonization observations** from C6 cycle (sprint-mis-cite verification, cluster-interaction defects, predecessor-count-self-increments) — bookmarked as N-1 / N-2 in beta-2.15 proposal; predecessor-count is a third bookmark in PM auto-memory.
- **PM auto-memory disposition** (whether to prune or rename older PM auto-memory files) — bookmarked as N-3.

## 4. Surprises and Learnings

The sprint opened on the heels of beta-2.13's informal close. The C2-C7 roadmap was substantially what beta-2.13 had originally planned, deferred forward when a Bates-batch hotfix chain consumed beta-2.13's mid-sprint cycles. Beta-2.14 was supposed to execute that backlog cleanly.

It mostly did. The Flag #5 Pattern X / Pattern C arc landed across three commits (C3a, C3a-followup, C3b) without major incident, hardening 9 sites total. Each commit carried a focused preflight cycle; CLI's pre-flight check caught H-class findings at v1 that resolved cleanly in v2. The N-Stage Gate doctrine held up — the cycle that had been theoretical at beta-2.13 close became operational practice across nine substantive cycles in beta-2.14.

Two patterns surprised. First, the off-roadmap docs hygiene commits (C8 + C8a) added two unscheduled commits and produced the chronological-vs-roadmap numbering divergence described in §1 above.

Second, the C6 canonization cycle itself surfaced THREE new defect-class observations from its own preflight cycle:
- **Sprint-mis-cite verification** (CLI v1 H-1 against C6 preflight v2): PM cited "beta-2.13 C7" for events that were actually beta-2.14 C7. Lesson canonizations citing prior-sprint events must verify sprint labels against `git log` / archive preflights before drafting.
- **Cluster-interaction defects** (CLI v2 H-3 against C6 preflight v3): the lesson's three identified families (wrong-granularity, stale count rot, incomplete inventory) interact rather than being independent. Specifically, when running chain-of-counts mitigation, use a semantic-stem regex covering all phrasing variants of the patched concept, not the literal substring. PM's v3 self-sweep on `alphabetical position` missed cousins `alphabetical order/sort/convention` — exactly the incomplete-inventory failure mode the lesson identifies as Cluster C, applied to its own draft cycle.
- **Predecessor-count-self-increments** (CLI v1 H-1 against C7 preflight v1): when a sprint-plan doc cites the predecessor sprint's commit count, the count is correct at draft time but goes stale because the patch landing IS itself an additional commit. PM's "11 substantive commits" became 12 when C7 itself landed.

The first two of these the C6 canonization didn't anticipate; the third surfaced one commit later. All three are bookmarked in PM auto-memory pending 2+ more recurrences before formal canonization. The pattern is clear: canonizing a discipline doesn't immunize the canonization itself from the discipline's failure modes. The lesson body shipping in `docs/lessons/grep-count-discipline.md` is correct; the preflight that produced it iterated on its own canon. The forensic record of that iteration lives in the v1→v3 + H-3 narrow waiver patch chain, captured in the preflight v3 entry and now archived.

The N-Stage Gate held up well. PM-CLI pinball was substantive (multiple v1→v2 cycles + one v3 + one v3-with-narrow-waiver) but each round produced a real catch. The maintainer's articulation of "tightening up our preflights and getting closer to zero error and PM-CLI back and forth" mid-sprint reframed the iteration cost discussion. The narrow-waiver pattern (per `feedback_v3_cycle_truncation.md`, codified during beta-2.13) absorbed the H-3 finding without a v4 round; the systemic improvement (semantic-stem patterns for final-sweep verification) was bookmarked as a future canonization candidate rather than folded mid-flight.

## 5. Lessons Canonized

- `docs/lessons/grep-count-discipline.md` — new lesson canonizing 5 grep-count defect classes across 3 families (wrong-granularity counts, stale count rot, incomplete inventory). 165 LOC, 5-section template.
- `docs/templates/preflight_drafting_checklist.md` Check 11 — operational discipline check for grep-count cross-verification, paired with the lesson above.
- `docs/templates/preflight_template.md` §8.1 ledger row 11 — heavyweight ledger consistency.
- `docs/templates/preflight_lightweight.md` §Appendix A ledger row 11 — lightweight ledger consistency.
- `docs/lessons/edit-tool-staging-gap.md` (sprint-open Commit 2) — Edit and Write tools modify but don't stage; pre-commit verification must scan `git status --short` for leading-space-`M` and `??` entries.

## 6. Gotchas for Future Sprints

- **Class B sub-span A** (3 sites in `6_Sync.py:328, 341, 354`): commit-restructuring required for the error-path Pattern X fix. Bookmarked as beta-2.15 M-1.
- **Pattern A consolidation surfaces:** function-local + module-level held conns at 3 sites; broader refactor likely 2-3 commits. Bookmarked as beta-2.15 M-2.
- **Flag #22 near-dupe sensitivity:** spec ready, sprint slot needed. Bookmarked as beta-2.15 S-1.
- **CI secrets/PII guard:** a pre-commit check for keys, real-looking contact details, and local deny-list terms; design questions deferred. Bookmarked as beta-2.15 S-2.
- **3 PM grep-count discipline observations** awaiting 2+ more recurrences before canonization: sprint-mis-cite verification, cluster-interaction defects, predecessor-count-self-increments. Bookmarked as N-1 / N-2 in beta-2.15 proposal + auto-memory.
- **C8 (this addendum) v1→v3 + H-5 — fourth empirical recurrence of the cluster-interaction defect class.** The closing canonization sprint's own sprint-close preflight shipped with FIVE grep-count-discipline misses: H-1 (CHANGELOG block-relocation scope under-specified at "~30 lines" when the relocation alone is ~75 lines), H-2 (living-doc ref count estimated "~5-10" when verified is 0), H-3 (archive-note file count "8 docs" when actual is 9), H-4 (audit-doc count drift across §0.2/§2 Phase B/§Appendix A with three different framings), and H-5 (residual arithmetic off-by-one in the v3 reconciliation of H-4 — `32 + 1 + ≥1 = ≥33` should be `≥34`). CLI v1 caught H-1 through H-4; v3 corrected H-1 substantively but introduced H-5 in its reconciliation prose; CLI v2 caught H-5; the maintainer's ratified narrow waiver at Stage 2; CLI applied mechanical H-5 patch during execution before the preflight self-archived. The observation: count discipline cluster failures recur even WHEN the failure mode is being actively canonized in the very preflight documenting the lesson. This is now the FOURTH empirical recurrence of N-2 cluster-interaction (after C6 v2/v3 + C7 v1) plus a continuing N-1 sprint-mis-cite type pattern (this preflight's audit-doc count miscounts share the same cluster-interaction shape). The bar for canonization remains "2+ more recurrences before formal canonization" per N-1/N-2 convention — but this sprint alone has now produced 4-5 recurrences. Beta-2.15 should plan to canonize in the next iteration or fold into `docs/lessons/grep-count-discipline.md` as a new "incomplete-inventory defeats chain-of-counts (and vice versa)" observation. Forensic record lives in `docs/archive/audits/beta-2.14/commit_13_*_check_v1.md` + `_v2.md`.

---

## Provenance

This retrospective was written by PM Claude during the sprint-close documentation cascade for `beta-2.14`. The maintainer reviewed and approved before the commit landed. The §6 final bullet (C8 v1→v3 + H-5 recursive-irony observation) was folded in by CLI at execution time per the maintainer's Stage 2 narrow waiver instruction.
