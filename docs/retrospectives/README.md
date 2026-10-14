# docs/retrospectives — Sprint Retrospective Library

Sprint-close retrospectives captured as durable documents. Each retrospective
covers one sprint (one version bump's worth of work) and captures what was
learned beyond what the commit history alone conveys.

## Purpose

Commit history records what landed. CHANGELOG records why each commit
happened. Retrospectives record the texture of the sprint — the dead ends,
the course corrections, the patterns that surfaced, the lessons worth
canonizing. This is the layer where institutional knowledge lives when it
isn't yet (or isn't ever) a durable lesson in `docs/lessons/`.

## When to write a retrospective

At sprint close, before the version tag is cut. Mandatory for any sprint
that:

- Touched more than 3 files across more than 3 commits
- Produced at least one new `docs/lessons/` entry
- Required the maintainer's intervention on a scope or design question
- Revealed a failure mode in the PM–CLI collaboration workflow

For smaller sprints (single-commit patches, typo fixes, version bumps), a
retrospective is optional. Default to writing one if uncertain — the cost
is low and future Claude sessions benefit.

## Lifecycle

1. **Draft** during the sprint-close documentation cascade (the final
   doc commit of the sprint, typically named "sprint-close" or
   "hardening").
2. **Review** by the maintainer before the commit lands. The maintainer may ask for
   additions or redirections — retrospectives are a shared artifact.
3. **Archive** — retrospectives stay in place at `docs/retrospectives/`.
   They are not moved to `docs/archive/` at end-of-life; they remain the
   permanent record of the sprint.

## Canonical file structure

Every retrospective follows the 6-section template in `template.md`.
Length target 100–300 lines per file. Worked example:
`docs/retrospectives/beta-2.11.md`.

## Catalogue

- [`template.md`](template.md) — Retrospective scaffold for new sprints.
- [`beta-2.11.md`](beta-2.11.md) — Documentation architecture reorganization + collaboration-workflow hardening. Sprint arc: commits 6b through 9 + C10 sprint-close addendum.
- [`beta-2.12.md`](beta-2.12.md) — DB-hygiene Round 1 (Flag #17 raw sqlite3.connect fix) + premature-tag recovery + proportionality discipline. Sprint arc: C1 Flag #17 + C2 premature-release-tag lesson + C3 sprint-transition hygiene backfills + C4 proportionality lesson + lightweight template + C5 sprint-close addendum. First application of the Tag-cut ordering rule.
- [`beta-2.13.md`](beta-2.13.md) — DB-hygiene Round 2 preempted by a Bates-batch hotfix chain. Only C1 Flag #20 (COALESCE enddoc backfill) of the planned 8-commit C1→C8 roadmap shipped; C2–C8 carry to beta-2.14 with numbering preserved. Sprint-open included PM Cowork→WARP migration + 14-finding role/workflow hygiene sweep. Informal close — no `v2.13.0` git tag.
- [`beta-2.14.md`](beta-2.14.md) — Cleanup of beta-2.13's deferred C2–C8 backlog: Flag #5 Pattern X / Pattern C closure (9 sites hardened across C3a/C3a-followup/C3b), Flag #13 aborted-run UX render hygiene (asymmetric scope: home grid + defensibility PDF), Flag #18 narrow `conn=None` scaffolding, Flag #24 log_audit kwarg typo register-and-close, C6 PM grep-count discipline canonization with new lesson + Check 11 install, C7 beta-2.15 roadmap proposal. Off-roadmap: docs hygiene (C8 + C8a). 12 substantive commits + sprint-close addendum. v2.14.0 — first project-version-tag cut after the beta-2.13 informal close (skips v2.13.x cleanly per the maintainer's decision).
- [`beta-2.15.md`](beta-2.15.md) — Pivoted from a planned Flag #5 + analytics + hygiene cleanup-audit sprint to a hot-patch-dominant arc: M-1 Flag #5 Class B sub-span A (the only planned commit that shipped) + 4 out-of-roadmap hot patches surfacing family-model architectural defects (C3 family-expansion UX with Flag #25 latent-bug discovery, C4 PST-as-family-root with new `docs/lessons/container-family-model.md` lesson, C5 EML CID over-skip with new `docs/lessons/extraction-rendering-symmetry.md` lesson, C7 Flag #28 inbound search fix) + 1 docs hygiene commit (C6). Six recurrences of the "broaden-without-reinventory" defect family across C6 + C7 + C8 preflight cycles bookmarked for next-sprint canonization. 8 substantive commits + sprint-close addendum. v2.15.0 natural increment from v2.14.0.
- [`beta-2.16.md`](beta-2.16.md) — **Closed `v2.16.0` (2026-06-01).** Two arcs. **Phase 1** (self-correction infrastructure, originally `beta-2.16-meta`): the library self-correction system from `docs/specs/library_self_correction_design.md` — keyword/event triggers (incl. `drift-correction-language` meta-trigger), 5-slot session-start refresher, UserPromptSubmit + PreToolUse + SessionStart hooks, three Tier 4 promotions (pre-commit Check 1, pre-commit secrets/PII guard absorbing backlog S-2, preflight Check 12); surfaced its own first meta-recursive defect (Item 11 / Check 11 duplication, caught inline). **Phase 2+ product arc (C4–C9):** S-3 stale test ref · S-2 Flag #28 closure + canonical OS-id helpers · S-1a Flag #22 NearDupe k-gram shingling (5-revision anti-fitting cycle) · C7 mid-sprint debt absorption (three-deep recursion story) · S-1b near-dupe Cluster Review workflow (persistence/UI/reporting-glue, fail-open deferred-tagging model) · S-1c defensibility report §4.2 near-dupe attestation. The clearest N-Stage-Gate demonstration of the sprint: the S-1c **B-1→B-2 double-catch** at the preflight gate ("enumerate every cell of a partition and check the join key before asserting reconciliation" — partition-enumeration candidate lesson). Flags #22 + #28 closed; #30 registered/deferred. M-1 Flag #5 Pattern A deferred to a dedicated beta-2.17 DB-hygiene sprint.

## Integration with the Lesson Integration Decision Tree

A retrospective is a sprint-close artifact. Durable patterns surfaced in
a retrospective should be classified against the Lesson Integration
Decision Tree in CLAUDE.md and, if appropriate, promoted to:

- `docs/lessons/` (durable pattern worth re-reading when writing code)
- `docs/templates/` (reusable workflow scaffold)
- `docs/references/` (dependency-specific API gotcha)
- CLAUDE.md (iron law or Standing Order)

The retrospective itself remains in place as the forensic record of how
the lesson was derived.
