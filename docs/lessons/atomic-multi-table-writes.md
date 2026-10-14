# Atomic Multi-Table Writes

**One-sentence summary:** Multi-table writes (rename_custodian, merge_custodians, any operation that touches 2+ tables in one logical step) must run in a single connection with a single commit, rollback on exception, and close in finally.

## The pattern

An operation that updates multiple tables as part of one logical change is a transaction, not a sequence of independent writes. If each table gets its own connection or its own commit, a failure midway through leaves the database in a half-updated state that no caller is prepared to handle. The user renames a custodian; the SQL updates the `custodians` table but crashes before updating `documents` or `custody_chain`; now the system has a custodian named X-new attached to documents still labeled X-old, and the audit trail has a partial `CUSTODIAN_RENAMED` entry. Recovery requires manual DB inspection.

The pattern that eliminates this failure mode: one SQLite connection, implicit `BEGIN` at the first write, all statements on that connection, `commit()` on success, `rollback()` on exception, `close()` in `finally`. SQLite's default deferred-transaction behavior means the sequence is atomic — either every write lands or none do. If the function raises at any point before commit, the rollback undoes everything and the database is exactly as it was before the call.

The shape of the function body is:

```python
def rename_custodian(case_folder, old_name, new_name):
    conn = get_connection(case_folder)
    try:
        conn.execute("UPDATE custodians SET name=? WHERE name=?", (new_name, old_name))
        conn.execute("UPDATE documents SET custodian=? WHERE custodian=?", (new_name, old_name))
        conn.execute("UPDATE custody_chain SET custodian=? WHERE custodian=?", (new_name, old_name))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

The anti-pattern is a function that opens a connection per table, or that commits after each statement. Either form sacrifices atomicity. Any function that writes to two or more tables in one logical step must use the atomic pattern above, and any test for it must include a "fail midway" path that asserts no partial state remains.

## Concrete example

**Sprint:** M-4 SQL migration Batch 4 (`.claude/plans/M4_REFINED_EXECUTION_PLAN.md`).

`7_Custodians.py` originally ran custodian rename and merge logic inline on a page-held connection. The M-4 migration moved those operations into `db_manager.rename_custodian()` and `db_manager.merge_custodians()`, each marked in the plan's Batch 4 table with `**ATOMIC** — 3 table UPDATEs, single conn, single commit` (for rename) and `**ATOMIC** — 3 UPDATEs + DELETE, single conn, single commit` (for merge).

The rename path touches `custodians`, `documents`, and `custody_chain`. The merge path touches the same three plus deletes the source custodian row. Both land as single-transaction operations inside the db_manager function, so a caller doesn't have to know anything about the multi-table coordination — it calls the function, waits for it to return, and trusts that the database is either fully updated or unchanged.

## How to apply

- Any function that writes to 2 or more tables in one logical step is a candidate. Scan db_manager for functions with 2+ `conn.execute("UPDATE ...")` or `conn.execute("INSERT ...")` calls — each one needs the try/except/commit/rollback/close pattern.
- Write a test that raises mid-operation. After the test, assert each table is in its pre-call state. A function without this test may still be non-atomic in practice even if the code looks right.
- Avoid mixing atomic db_manager writes with page-held connections that have their own uncommitted state. See the beta-2.12 backlog on "page-held connection + nested db_manager call pattern" (Flag #5).
- When reviewing a PR that adds a new multi-table write, check: (1) single connection, (2) single commit, (3) rollback on exception, (4) close in finally, (5) test for mid-operation failure.

## See also

- **Related lessons:** `docs/lessons/zero-risk-data-layer-rollback.md`, `docs/lessons/batch-commit-discipline.md`, `docs/lessons/exempt-annotation-convention.md`
- **Source:** `.claude/plans/M4_REFINED_EXECUTION_PLAN.md` Batch 4 (rename_custodian, merge_custodians atomic contract)
- **Relevant code:** `db_manager.py` `rename_custodian`, `merge_custodians`, and any function touching 2+ tables
