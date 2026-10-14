# No Silent Default

**One-sentence summary:** When a required value is missing, render an explicit placeholder such as `"(No basis specified)"` rather than a plausible-sounding default like `"Attorney-Client Privilege"` — data integrity demands that absence be visible, not silently filled.

## The pattern

A silent default is a value the system invents when real data is missing, that happens to look like real data. The failure mode is that no one can tell the invented value apart from a real one. Every downstream consumer — reviewing attorney, opposing counsel, judge, auditor — reads the invented value as though it were sourced from the record. If the invented value happens to be correct, nothing goes wrong and the invention stays invisible. If it is wrong, the error propagates under a false label of authenticity.

The alternative is an explicit placeholder: a string that cannot be mistaken for real data. `"(No basis specified)"`, `"(unknown)"`, `"(missing)"`, `"[redacted]"` — anything visibly not a natural-language value that would appear in the source record. A reviewer seeing the placeholder knows the value is absent and can either source it from elsewhere, flag the row, or accept absence as the final state. A reviewer seeing a silent default cannot tell.

In eDiscovery the courtroom-defensibility dimension amplifies this. A privilege log with silently-inferred reasons cannot be sworn to under FRCP 26(g) — the attorney signing the log is certifying that the contents are true to their knowledge. A silent default that happens to be wrong is a certification failure that opposing counsel can exploit. An explicit placeholder is defensible because the missing state is disclosed on the face of the log.

The rule: every fallback must either be marked visibly or surface an error. Never guess a plausible value and present it as sourced.

## Concrete example

**Sprint:** beta-2.9 privilege log fixes (`docs/archive/specs/Privilege_Log_Fixes_Round2.md`).

The `_pl_fuzzy_match_privilege_reason` function in `pages/5_Production.py` (then line 3421) had `return 'Attorney-Client Privilege'` as its final fallback when the incoming privilege tag did not match anything in the abbreviation map. A document with a privilege tag like `PRIV-FOO` that the map did not recognize would be rendered on the privilege log as `"Attorney-Client Privilege"` — indistinguishable from documents whose basis was correctly sourced.

The fix:

```python
# Before:
return 'Attorney-Client Privilege'

# After:
return '(No basis specified)'
```

After the fix, only three paths produce the string `"Attorney-Client Privilege"` on the log: (1) the explicit override dropdown, (2) an actual tag match against the abbreviation map, (3) the deliberate `"Attorney-Client"` substring check earlier in the function. A blind guess is no longer one of them.

## How to apply

- Audit every function that returns a string field destined for a user-facing or court-facing surface. For each `return` that executes when inputs are missing, ask: "Can a reader tell this value apart from a value sourced from real data?" If no, the return is a silent default and must be replaced with a visible placeholder or an exception.
- Placeholder conventions: parenthesized lowercase (`(unknown)`) for automated fallbacks, or bracketed uppercase (`[MISSING]`) for editable fields a reviewer must fix.
- Tests that exercise the missing-input path should assert the placeholder string, not a plausible-looking value. A test that passes with a silent default has baked the defect in.
- When reviewing PRs that add fallback logic, ask the author to trace which UI surface will render the fallback and whether the surface can distinguish it from real data. If not, the fallback is a silent default.

## See also

- **Related lessons:** `docs/lessons/defensibility-statement-practice.md`, `docs/lessons/three-tier-cascade-resolution.md`
- **Source:** `docs/archive/specs/Privilege_Log_Fixes_Round2.md` (Bug 2 secondary fix)
- **Relevant code:** `pages/5_Production.py` `_pl_fuzzy_match_privilege_reason`, `_pl_resolve_privilege_basis`
