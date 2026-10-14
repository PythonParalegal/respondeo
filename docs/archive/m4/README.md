# docs/archive/m4 — M4 SQL Migration Plans (Completed)

Planning documents for the M-4 SQL migration (the Holistic Audit finding
to consolidate all SQL into `db_manager.py` with an exempt-annotation
convention for intentional retentions). Migration is **complete** per the
CLAUDE.md Audit Remediation Status section:

> M-4: SQL migration — COMPLETE. All 9 batches landed: 58 new db_manager
> functions, ~180 page-file calls migrated, 153 retained calls
> exempt-annotated, 49 defensibility_report.py queries migrated.

These plans are preserved here for forensic reference (how the migration
was staged, which batch covered which surface, how the exempt-annotation
convention was chosen). Durable lessons from the migration have been
extracted into `docs/lessons/` (see `batch-commit-discipline.md` and
`exempt-annotation-convention.md`).

## Expected contents (post-6e)

Migrated from `.claude/plans/` in Commit 6e:

- `M4_REFINED_EXECUTION_PLAN.md`
- `M4_SQL_MIGRATION_PLAN.md`

Migrated from project root in Commit 6e:

- `M4_TEST_PLAN.md`

## See also

- `docs/archive/README.md`
- `docs/HOLISTIC_AUDIT_REMEDIATION.md` — audit findings tracker
  (M-4 listed as complete).
- `docs/lessons/batch-commit-discipline.md` — the durable lesson from
  M-4's execution model.
- `docs/lessons/exempt-annotation-convention.md` — the `# db_manager:
  exempt (reason)` convention born in M-4.
