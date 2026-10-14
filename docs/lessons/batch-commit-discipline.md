# Batch Commit Discipline

**One-sentence summary:** Large migrations split into atomic, independently-revertable batches — each batch leaves the system in a working state, and each batch has its own verification gate before the next starts.

## The pattern

A migration that refactors dozens or hundreds of call sites cannot land as a single commit without accepting a very high regression risk. Review surface scales with commit size; once a commit exceeds what one reviewer can read end-to-end in a sitting, defects slip through. The mitigation is batching: split the migration into commits that are individually small enough to review, individually atomic (the system works after each one), and individually revertable (any single batch can be reverted without cascading failures into the others).

Batch boundaries are chosen along dimensions where the work naturally groups: low-risk vs. higher-risk file touches, related-function clusters, or risk-tier boundaries (LOW → MEDIUM → HIGH). Every batch has an explicit verification step before moving to the next batch — a smoke test, a targeted regression run, or a manual UI walk — so a regression surfaces within the batch that introduced it, not three batches later.

The guarantee each batch provides is that reverting it does not strand the rest of the migration. If Batch 5 of a 9-batch plan introduces a regression, `git revert` on Batch 5 leaves Batches 1–4 landed and functional, and Batches 6–9 can proceed on the reverted state (or be deferred). A migration that requires all-or-nothing application has been improperly batched.

A batching plan lists the batches in priority order, describes what each batch changes, names the verification step, and identifies any cross-batch dependencies (so a reviewer can tell which batches must land first). A batch that has "we'll figure out the verification later" is a batch that is not ready to commit.

## Concrete example

**Sprint:** M-4 SQL migration (`.claude/plans/M4_SQL_MIGRATION_PLAN.md` and `M4_REFINED_EXECUTION_PLAN.md`).

M-4 consolidated ~180 direct-SQL call sites in page files into ~58 `db_manager.py` functions. Migrating all of that as one commit would have been a 4,000+-line diff across a dozen files with coupled behavior. Instead, the plan split into batches:

- **Batch 1 — Status Count Consolidation (LOW RISK):** 7 functions replacing ~50 duplicate COUNT queries across `home.py`, `2_Processor.py`, `3_Analytics.py`, `6_Sync.py`.
- **Batch 2 — Saved Searches + Bates Lookup + 8_Exhibits (LOW RISK):** 10 functions, ~14 calls, self-contained.
- **Batch 3 — Document Viewer + Tags + Batch Management (MEDIUM RISK):** 16 new + 1 reuse, ~35 calls. Coupled via tag-save → batch-status-update flow.
- **Batch 4 — Custodian Operations (MEDIUM-HIGH RISK):** atomic `rename_custodian` and `merge_custodians`.
- ...through Batch 8 annotation sweep + Batch 9 defensibility_report addendum.

Each batch committed independently with its own verification step. Batch 1's verification was "dashboard numbers match before/after on each page." Batch 3's was tag persistence and family-cascade tests. Batch 4's was custodian rename/merge round-trip with data integrity checks.

The payoff: when a Batch 5 regression surfaced in testing, reverting just Batch 5 was clean. Batches 1–4 stayed landed and functional; Batch 5 was re-drafted and re-shipped without disturbing the rest.

## How to apply

- Before starting a big migration, draft the batch list. Each batch has: a scope (what files, what functions), a risk tier (LOW/MEDIUM/HIGH), and a verification step that proves correctness before the next batch starts.
- Each batch = one commit. Commit messages follow a consistent scheme (`refactor: M-4 batch N — <scope> (N functions, M calls migrated)`) so `git log` shows the migration's progress at a glance.
- A batch that has no natural stopping point means the scope is wrong — re-scope until it does. A batch that leaves the system broken between the previous batch and this one is not a batch; it is a partial change that needs its scope expanded until it is self-contained.
- If a batch is higher-risk than it first looked, split further. The cost of an extra commit is much less than the cost of an undo-the-whole-migration commit.
- Verification after each batch is non-negotiable. Skipping verification to "catch up on batches" is the specific failure mode that makes multi-batch migrations ship with undiscovered bugs.

## See also

- **Related lessons:** `docs/lessons/atomic-multi-table-writes.md`, `docs/lessons/exempt-annotation-convention.md`, `docs/lessons/scope-expansion-probe.md`
- **Source:** `.claude/plans/M4_SQL_MIGRATION_PLAN.md`, `.claude/plans/M4_REFINED_EXECUTION_PLAN.md` (batch list, risk tiers, verification plan)
- **Relevant code:** `db_manager.py` migrated functions; `CHANGELOG.md` M-4 batch entries
