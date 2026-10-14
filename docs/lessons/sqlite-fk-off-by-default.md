# SQLite FK Off By Default

**One-sentence summary:** SQLite does not enforce foreign keys unless `PRAGMA foreign_keys = ON` is issued every connection — so `ON DELETE CASCADE` clauses may silently no-op, and the code must handle cascade manually with explicit DELETE.

## The pattern

SQLite's foreign-key enforcement is an optional feature that defaults to OFF for backward compatibility with pre-3.6.19 databases. A table declaration that includes `FOREIGN KEY (...) REFERENCES other_table(...)` with `ON DELETE CASCADE` looks like it will enforce referential integrity and cascade deletes — and on some databases (PostgreSQL, MySQL, SQL Server) it does. On SQLite, without the pragma, the declaration is documentation only. Inserts that violate the FK succeed; deletes on the parent do not cascade to children. The database can and does accumulate orphaned rows without any error.

The pragma is per-connection. Setting it once on one connection does not make it stick across the database — any other connection to the same DB file starts with `foreign_keys = OFF` unless it issues the pragma itself. This means a project that depends on FK enforcement must either issue the pragma in a central connection-opening helper that every connection flows through, OR assume the pragma is not set and handle cascade logic in application code.

This project follows the second approach: treat SQLite FK declarations as documentation, not enforcement. Every `DELETE` that could leave orphans explicitly deletes the children first. The belt-and-suspenders discipline means the code is correct whether the pragma is on or off, and onboarding a new connection-opening helper does not reintroduce orphan bugs.

The cost: slightly more code at every delete site. The benefit: correctness is not dependent on a pragma that may or may not be set. Given how subtle and how silent the failure mode is (orphaned rows accumulate without error), the trade-off is worth it.

## Concrete example

**Source:** `AGENTS.md` Known Constraints, item 7:

> **`batch_documents` ON DELETE CASCADE may not fire** (SQLite foreign key enforcement is off by default). The code handles cascade manually with explicit DELETE before batch deletion.

The `batch_documents` table declares a foreign key to `batches` with `ON DELETE CASCADE`. A naive reader of the schema might assume that `DELETE FROM batches WHERE id = ?` also removes the corresponding `batch_documents` rows. It does not, unless `PRAGMA foreign_keys = ON` has been issued on the current connection. In this project's typical connection flow, the pragma is not set, so the cascade does not fire, and deletes on `batches` silently leave `batch_documents` rows pointing at a non-existent batch_id.

The code handles cascade manually:

```python
# First delete children:
conn.execute("DELETE FROM batch_documents WHERE batch_id = ?", (batch_id,))
# Then delete the parent:
conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
```

Both statements run in the same transaction (per `atomic-multi-table-writes`), so they either both succeed or both roll back. The FK declaration in the schema remains as documentation — future developers reading the DDL see the intended relationship — but the application does not depend on it being enforced.

## How to apply

- When writing any `DELETE` that targets a table with dependent rows, add the dependent-delete first. Even if you believe `PRAGMA foreign_keys = ON` is set somewhere in the connection flow, do not rely on it — belt-and-suspenders.
- When reviewing schema changes that add `ON DELETE CASCADE` clauses, ask: "Is there code that deletes the parent? If so, does it explicitly delete children first?" If yes, the cascade declaration is fine as documentation. If no, flag the absence of manual cascade handling.
- Avoid silent assumptions like "this is handled by the FK." In SQLite, assume the FK is documentation until proven otherwise.
- If the project ever centralizes on a connection helper that issues `PRAGMA foreign_keys = ON`, the manual cascades become redundant but not wrong. Do not remove them — the belt-and-suspenders discipline continues to guard against anyone adding a direct-connect path that bypasses the helper.
- Tests for multi-table deletes should include a "verify no orphans" assertion that counts rows in the child table after deleting the parent.

## See also

- **Related lessons:** `docs/lessons/atomic-multi-table-writes.md`, `docs/lessons/exempt-annotation-convention.md`
- **Source:** `AGENTS.md` Known Constraints item 7
- **Relevant code:** `db_manager.py` `delete_all_batches()` and related cascade-handling deletes
