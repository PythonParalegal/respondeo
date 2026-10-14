# Chain-of-Moves Stale Refs

**One-sentence summary:** When a reference is updated to reach a target and the target subsequently moves in a later commit of the same sprint arc, the reference becomes stale again — data-flow tracing must track both endpoints' stability across the arc, not just the initial move.

## The pattern

Refactors that span multiple commits often move the same piece of data or documentation more than once: out of a scratchpad, into a canonical directory, then later into an archive. A reference that was stale before the sprint and got fixed by the first move is silently re-broken by the second move — unless the second move explicitly re-verifies every ref it's creating.

The first fix becomes a false sense of security. Sprint execution remembers "we fixed that ref already" and skips the re-grep. Meanwhile the target's second move has invalidated the fix without the fixer noticing.

The discipline: every commit that moves a file must grep the repo for references to that file's previous location — including references that a previous commit in the same arc may have just updated. Stability is not inherited from a prior commit in the same arc. The reconciliation check runs against the live state of the repo each commit, not against the assumptions the arc's plan carried at kickoff.

## Concrete example

In beta-2.11 Commit 6e.1, CLI fixed `pages/9_InboundProduction.py:22` docstring to point at `docs/archive/specs/Inbound_Production_Module_Spec.md` — the spec had moved from project root to `docs/specs/` during that commit's consolidation phase. Verified, staged, committed.

In Commit 6e.2, CLI archived that same spec from `docs/specs/` to `docs/archive/specs/`. The docstring was now stale again — pointing at `docs/archive/specs/Inbound_Production_Module_Spec.md`, which no longer existed. CLI caught it during Phase 5's reconciliation grep (§9.4 equivalent) and re-fixed it in the same commit: `docs/specs/` → `docs/archive/specs/`, `last_modified` bumped, no version bump per the comment-only rule.

Had the reconciliation grep been skipped on the assumption "we already fixed that ref in 6e.1," the stale path would have shipped with the sprint. Nobody would have found it until a developer followed the docstring and got a 404.

## How to apply

- Multi-commit sprint arcs that move files must treat every commit as independent reconciliation territory. The plan's kickoff state is not authoritative against the live repo state at commit-N.
- Run the reconciliation grep against the current repo state each commit, not against the planned moves. A file moved again in the same arc counts as a new move for reconciliation purposes.
- When writing a preflight/packet that spans multiple commits, the preflight should explicitly name files that will move more than once in the arc. The drafter flags them for re-verification at each commit rather than assuming the earlier fix holds.
- Historical audit packets and CHANGELOG entries should reference paths as they existed at commit time — do NOT retroactively rewrite. Only live code (`.py`, active docs) gets updated to track the current target location.
- Templates and lesson files that cite a source path must be audited on every commit that moves the source, not just the first.

## See also

- **Related lessons:** `docs/lessons/line-number-drift-reverification.md` (same discipline applied to line numbers), `docs/lessons/predictive-scaffold-staleness.md` (same sprint-arc root cause).
- **Source:** the 6e archive-sweep audit (reconciliation grep found the re-stalled `9_InboundProduction.py:22` ref during 6e.2 execution).
