# Exempt Annotation Convention

**One-sentence summary:** `# db_manager: exempt (reason)` annotates intentionally-retained page-file SQL, distinguishing "we meant to leave this here" from "we missed this one during migration."

## The pattern

A migration that moves SQL out of page files and into a data-access layer will always leave some SQL in the page files. Not all SQL should move: processing loops with shared connections lose their transaction semantics if wrapped in per-call functions; dynamically constructed queries gain nothing from extraction because the dynamic construction is the point; schema introspection is infrastructure, not data access; one-shot analytics bulk updates don't benefit from a library wrapper.

The hazard: a reader six months later sees SQL in a page file and cannot tell whether it is intentional retention or a migration miss. A migration miss is a latent defect (a call that should be centralized but isn't). Intentional retention is a design decision. Without annotation, the two are indistinguishable, and the entire migration's correctness claim weakens over time as new code is added to page files in the "there's already SQL here, might as well" pattern.

The annotation is a single in-code comment:

```python
# db_manager: exempt (processing loop)
conn.execute("UPDATE documents SET status=? WHERE id=?", (status, doc_id))
```

The `(reason)` parenthetical names which exempt category applies. The reason is not decorative — it documents the specific design constraint that justified the exemption. A future reader sees the annotation and knows this call was examined and left deliberately. A call without annotation is a call that escaped the migration sweep and belongs in the next batch.

Sprint-close verification: grep all page files for unannotated `.execute(` calls. Any hit is a call site that was missed. The exempt annotation is what makes that grep meaningful.

## Concrete example

**Sprint:** M-4 SQL migration (`.claude/plans/M4_SQL_MIGRATION_PLAN.md`).

The M-4 plan explicitly identified four exempt categories encountered during the migration:

1. **Processing loop internals** (`2_Processor.py` ~40 calls, `6_Sync.py` ~25 calls) — per-document status updates inside tight loops with shared connections. Wrapping each in a function that opens/closes its own connection would break performance and transaction semantics.
2. **Dynamically constructed queries** (`4_Review.py` main grid ~8 calls, `5_Production.py` grid ~6 calls) — SQL strings built programmatically from UI widget state across 50+ lines. Moving just the final execute gains nothing.
3. **Schema introspection** (`PRAGMA`, `sqlite_master`) — infrastructure queries, not data access.
4. **Analytics bulk-update loops** (`3_Analytics.py` ~12 calls) — threading/near-dupe tag manipulation in shared-connection bulk operations.

Every call site that stayed in a page file got `# db_manager: exempt (processing loop)` or the equivalent for its category. The plan's §Exempt Statement Annotation block called this out explicitly, and the sprint-close verification step was:

> Grep for any remaining unexempted raw SQL: `grep -n "\.execute(" pages/*.py home.py` should show only exempt-annotated lines.

That grep is meaningful because the annotation is present. Without it, the grep would return every `.execute(` and provide no signal about intent.

## How to apply

- When moving SQL to `db_manager.py`, any call site that stays in a page file MUST carry the annotation. No exceptions.
- The reason parenthetical picks from the four known categories (processing loop / dynamic query / schema introspection / analytics bulk-update) OR introduces a new category. A new category requires a one-sentence justification in the commit message.
- When reviewing PRs that add new `.execute(` calls to page files, ask: "Is this exempt? Which category?" If the answer is not obvious, the call should probably be in db_manager.
- Sprint-close greps:
  ```bash
  grep -n "\.execute(" pages/*.py home.py | grep -v "# db_manager: exempt"
  ```
  Zero hits = all page-file SQL is annotated. Hits = either missed migrations or new call sites lacking annotation.
- The annotation is in-code, not in a separate document. Documentation rots; an in-code comment travels with the call site forever.

## See also

- **Related lessons:** `docs/lessons/batch-commit-discipline.md`, `docs/lessons/atomic-multi-table-writes.md`
- **Source:** `.claude/plans/M4_SQL_MIGRATION_PLAN.md` §Exempt Statement Annotation, §Verification
- **Relevant code:** `pages/2_Processor.py`, `pages/3_Analytics.py`, `pages/4_Review.py`, `pages/5_Production.py`, `pages/6_Sync.py` exempt-annotated call sites
