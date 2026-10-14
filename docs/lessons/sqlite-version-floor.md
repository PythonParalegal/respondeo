# SQLite Version Floor

**One-sentence summary:** Windows Python ships a SQLite older than the development-machine baseline, so production SQL must use only operators supported by the deployment floor — `json_extract()` works; the `->>` operator does not.

## The pattern

Python's standard library bundles SQLite via the `sqlite3` module. The bundled version depends on the Python build, which depends on the installer, which depends on the target platform. The net effect: the SQLite version your production Windows users run is not the same SQLite version your Linux or macOS development machine runs, and is not the same version a modern CI container runs.

This matters because SQLite has added language features over time. Features that the language-level documentation describes as part of current SQLite may silently fail on older versions. The `->>` JSON extraction operator, for instance, requires SQLite 3.38 (released 2022). The `json_extract()` function, which does the same work, has been available since SQLite 3.9 (2015). If production SQL uses `->>`, the query runs but returns NULL on every row under an older SQLite — and no error, no warning, no log. It just silently produces wrong results.

The rule: choose SQL constructs that work on the deployment floor, not the development machine's version. When a newer operator tempts, check whether the equivalent function-form has broader support. When in doubt, pin the minimum SQLite version the platform supports and test against that explicitly.

## Concrete example

**Sprint:** beta-2.9 privilege log fixes (`docs/archive/specs/Privilege_Log_Fixes_Round2.md`).

The privilege log's mark-reason subquery originally used `->>`:

```sql
-- Broken on SQLite 3.37 and earlier:
SELECT GROUP_CONCAT(DISTINCT json_each.value ->> 'reason')
FROM redaction_marks, json_each(marks_json)
```

The maintainer's deployment environment runs SQLite 3.37.2 (bundled with Windows Python). The `->>` silently returned NULL for every document, so Tier 1 of the `_pl_resolve_privilege_basis` resolver never fired, and every privilege log fell through to fallback tiers that produced blank or guessed basis values.

The fix replaced `->>` with `json_extract()`:

```sql
-- Works on SQLite 3.9+ (our supported floor):
SELECT GROUP_CONCAT(DISTINCT json_extract(json_each.value, '$.reason'))
FROM redaction_marks, json_each(marks_json)
```

Both expressions produce the same result on modern SQLite; only the function form works on the deployment's older version.

## How to apply

- Before writing SQL that uses a feature added after ~2015, check the SQLite release notes for the minimum version. The `->>`, `IIF()`, `UNIXEPOCH()`, `STRFTIME()` variants, generated columns, and some `json_*` features all have version floors.
- The deployment's actual SQLite version is queryable:
  ```python
  import sqlite3
  sqlite3.sqlite_version  # e.g., '3.37.2' on Windows Python 3.11
  ```
  or from a connection: `conn.execute("SELECT sqlite_version();").fetchone()`.
- When refactoring, the `->>` → `json_extract()` substitution is almost always safe and does not require the floor version to change.
- Tests that exercise SQL with version-sensitive features should log the SQLite version as part of their output, so a test run on a newer-than-deployment SQLite shows up in the log.
- If a feature is needed that requires a newer SQLite than the deployment floor, the cost is a Python-version bump, a packaged SQLite binary, or a workaround in Python. None of those are free; factor that into the design.

## See also

- **Related lessons:** `docs/lessons/exempt-annotation-convention.md`, `docs/lessons/batch-commit-discipline.md`
- **Source:** `docs/archive/specs/Privilege_Log_Fixes_Round2.md` (Bug 2, SQLite version detail)
- **Relevant code:** `pages/5_Production.py` privilege log subqueries; any `json_*` usage in `db_manager.py`
