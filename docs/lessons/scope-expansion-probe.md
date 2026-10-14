# Scope Expansion Probe

**One-sentence summary:** Mid-sprint scope expansion is safe only when the new work passes a three-criteria test — same root cause, same fix pattern, same hazard class — and any mismatch means the new work becomes a separate commit.

## The pattern

During execution of a planned commit, it is common to notice an adjacent defect or improvement opportunity. The temptation is to bundle: "while I'm editing this file, I should also fix X." Bundling is occasionally correct and occasionally catastrophic, and the difference depends on whether the adjacent work shares the characteristics that make the current commit reviewable and revertable as a unit.

The three criteria that gate bundling:

1. **Same root cause.** The adjacent defect is produced by the same underlying issue as the work already in flight. Not "looks similar" — literally traces to the same root. If tracing the adjacent defect would lead to a different bug report, different fix, different area of the code, the root cause is not the same.

2. **Same fix pattern.** The code changes needed for the adjacent work look like the code changes already being made. If the current commit is renaming a function and the adjacent defect requires a schema migration, the fix patterns are different.

3. **Same hazard class.** The risk-of-regression surface for the adjacent work is the same one the current preflight covered. If the current commit's preflight analyzed risks for outbound production and the adjacent defect affects inbound ingestion, the hazard class is different — the preflight did not cover the inbound risk surface.

Any one of the three failing means the adjacent work is a separate commit. "Same file" is not a criterion. "Same sprint" is not a criterion. File proximity is the classic red herring — two defects in the same 5,000-line page can have three distinct root causes and should be three commits.

When all three match, bundling is safe and saves a review cycle. When any one fails, CLI flags the adjacent work in `FLAG_REGISTRY.md` or a new preflight, finishes the current commit as scoped, and handles the adjacent work as its own commit in the same sprint. The scope-expansion probe is a one-minute sanity check that prevents a recurring failure mode.

## Concrete example

**Sprint:** beta-2.10 outbound production refactor (`docs/archive/sprints/beta-2.10/outbound_extraction_preflight.md` §6 Scope-Expansion Probe Responses).

Commit 7's preflight specified extracting the outbound production body into a helper function. During preflight review, CLI noticed a module-level `st.stop()` at line 233 that would also benefit from removal — same broad area of the file, same general concern about `st.stop()` script-halting.

The scope-expansion probe response (§6.5) ran the three-criteria check:

> **Revised recommendation:** include the removal in Commit 7 Phase C. Rationale: same root cause (script-halt side-effect of `st.stop()` in Module 5), same hazard class (tab-blanking). Per `feedback_commit_bundling_principle.md`: "bundle only when same root cause AND same fix pattern AND same hazard class" — all three criteria met.

All three matched, so the removal was folded into the same commit. Had any criterion failed — say, if the `st.stop()` had been in a different module entirely — the removal would have been a separate commit in the same sprint, with its own preflight and its own verification.

The counter-example in the same preflight: a related defect in `production_selection` was noticed during the same sprint. The scope probe concluded: same root cause (session-state ghost-bug pattern), but different fix pattern (session-state lifecycle vs. script-halt), different hazard class (cross-tab state bleed vs. in-tab blanking). Two criteria failed. The `production_selection` work was flagged (registered as Flag #10) and deferred to a future sprint rather than bundled into Commit 7.

## How to apply

- Whenever during execution you think "while I'm here, I should also...", stop and run the probe. All three criteria must match.
- Write the answer in the preflight or commit message: "Scope-expansion probe: same root cause (X), same fix pattern (Y), same hazard class (Z). All three match; folding in." OR "Probe failed on [criterion]; flagging as #NN, deferring."
- If any criterion is ambiguous, treat it as a fail. The cost of an extra commit is much less than the cost of a bundled commit that ships a regression in the "while I was there" change.
- File proximity does not count. Same sprint does not count. Same conversational thread does not count. Only root cause + fix pattern + hazard class count.
- Reviewers: when a PR mixes what appear to be two different concerns, ask the author to run the probe publicly. Unambiguous classification either confirms the bundling or splits the PR.

## See also

- **Related lessons:** `docs/lessons/batch-commit-discipline.md`, `docs/lessons/line-number-drift-reverification.md`
- **Source:** `docs/archive/sprints/beta-2.10/outbound_extraction_preflight.md` §6 (Scope-Expansion Probe Responses), §6.5 (revised recommendation)
