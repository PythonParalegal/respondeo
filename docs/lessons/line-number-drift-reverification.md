# Line-Number Drift Re-Verification

**One-sentence summary:** Preflights that cite line numbers in source files must re-verify those numbers against the current file state before execution — files shift as other commits land.

## The pattern

A preflight written on Monday says "edit `foo.py` line 247." Between Monday and Wednesday, another commit adds 30 lines above line 247. On Wednesday, line 247 is no longer the code the preflight described; it's something else. If CLI executes the Wednesday edit against line 247, the wrong code gets modified, and the failure mode depends on what code happens to be there now — sometimes a syntax error, sometimes a silently wrong behavior change.

The preflight is the spec. The preflight's line numbers are snapshots of the file state at preflight-authoring time. Files do not guarantee line-number stability across commits; commits freely insert, delete, and shift lines. So any preflight that cites line numbers must include a re-verification step at the start of execution: re-grep for the target function signature, block comment, or unique string near the cited line, and confirm the line number still matches.

The mitigation has two parts. First, preflights reference anchors in addition to line numbers — function names, unique strings, distinctive comments. "Edit `foo.py` at line 247, which is the `def compute_bates()` signature" is more robust than "edit line 247." Second, execution performs the re-grep before editing. If the line number has drifted, CLI updates the preflight inline (or a separate note), flags the drift in the commit message, and proceeds against the correct location. If the anchor has disappeared entirely, the preflight is stale and needs revision before execution.

The discipline is cheap — a single grep takes one second — and it prevents an entire class of defect that is hard to diagnose after the fact, because the wrong-line edit can silently produce working-but-wrong code.

## Concrete example

**Sprint:** beta-2.10 outbound extraction preflight (`docs/archive/sprints/beta-2.10/outbound_extraction_preflight.md` §7 Line-Number Drift Re-Verification).

The Commit 7 extraction plan referenced two in-tab `st.stop()` lines originally cited as "2229, 2234" from an earlier plan draft. Between plan draft and execution, Commits 2 and 3 had landed, shifting the file. The preflight's §7 re-verified against the current state:

> **Reconciled reading of plan's "2229, 2234":** plan meant the two **in-tab** outer stops (current 2260/2265), not the module-level stop at old ~230-ish. The in-tab stops are where the state-gate refactor lands. The module-level stop at current line 233 is the scope-expansion candidate (probe §6).

The reconciliation did two things: corrected the line numbers to current (2260/2265), and distinguished the in-tab stops from the module-level stop (which had drifted from ~230 to 233). Both correctives were applied during execution; the preflight doc itself was updated inline with the re-verified numbers so that a future re-read would not reintroduce the stale references.

The §7 verdict was:

> **Verdict:** Commit 7 section references have been re-verified. No additional stale line pointers. Plan's "line 308 title rename" instruction is fully stale (done in Commit 6).

"Fully stale" is another outcome type — the plan referenced work that had already been done by a prior commit. The re-verification catches that too: an already-done step shouldn't be executed again.

## How to apply

- Every preflight that cites line numbers must include a re-verification step at the top of execution. CLI does not edit on cited line numbers without re-grep first.
- Preflights reference anchors (function names, unique strings, distinctive comments) alongside line numbers. The anchor is the semantic target; the line number is the snapshot value.
- If the re-grep finds the anchor at a different line, update the preflight inline (with a one-line note) and proceed against the current line. Flag in the commit message: "Preflight cited line X; current state line Y; verified anchor intact."
- If the re-grep does not find the anchor at all, the preflight is stale. Stop and flag before editing.
- Preflights authored and executed in the same session are less prone to drift, but still worth re-verifying — multi-commit sprints land mid-plan changes.

## See also

- **Related lessons:** `docs/lessons/scope-expansion-probe.md`, `docs/lessons/batch-commit-discipline.md`
- **Source:** `docs/archive/sprints/beta-2.10/outbound_extraction_preflight.md` §7 (Line-Number Drift Re-Verification)
- **Relevant code:** any preflight in `docs/audits/` that cites line numbers demonstrates the pattern
