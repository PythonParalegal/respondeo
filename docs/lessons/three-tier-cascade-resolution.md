# Three-Tier Cascade Resolution

**One-sentence summary:** When multiple sources could supply a value (mark reasons → tags → explicit placeholder), resolve them in a declared tier order with fallthrough and make each tier's absence distinguishable from the next tier's presence.

## The pattern

A cascaded value resolution is the pattern `value = source_a or source_b or source_c`. It is convenient, compact, and correct when the consumer does not care which source supplied the value. The moment the consumer does care — for forensics, for audit, for defensibility — the compact form hides information the consumer needs.

Each tier in a cascade has different forensic weight. A privilege basis pulled from a reviewer-entered redaction mark is a direct statement by the reviewer at the moment of review. A basis inferred from a tag is a looser, convention-driven mapping. A basis that fell through to a placeholder is a missing-data signal. These are not interchangeable. A privilege log that renders "Attorney-Client Privilege" must be able to tell, at read time, whether that text came from a reviewer's mark, a tag inference, or a guess — because opposing counsel may later ask.

The rule: if a downstream consumer needs to know which tier supplied the value, the cascade must record the source. Options: log the source tier at resolution time, tag the value with a source marker (`("Attorney-Client Privilege", "tier_1_mark")`), or return a richer type (dict, named tuple) instead of a bare string. The compact `a or b or c` form is only safe when source-blindness is a defensible design decision.

A healthy cascade spec lists tiers in priority order, describes the forensic weight of each, and names the sentinel for the fallthrough case. The sentinel should follow the `no-silent-default` rule — an explicit placeholder like `"(No basis specified)"`, not a plausible-looking invented value.

## Concrete example

**Sprint:** beta-2.9 privilege log auto-load (`docs/archive/specs/Privilege_Log_AutoLoad_Spec.md` Part 1g).

The privilege log's Privilege Basis column resolves via a three-tier cascade:

1. **Tier 1 — Redaction mark reasons (most specific):** query `redaction_marks.marks_json` for the document, extract all `"reason"` fields. These are bases entered by the reviewer at redaction time. If found, use them (deduplicated, comma-joined).
2. **Tier 2 — Document tags (fallback):** if no mark reasons found, read the `tags` column and apply fuzzy matching against `_PL_ABBREV_MAP` to map abbreviations to standard names.
3. **Tier 3 — Placeholder (final fallback):** if neither source supplies a basis, render `"(No basis specified)"`.

The spec codified this in `_pl_resolve_privilege_basis(row, override, marks_reasons_str)`:

```python
# Tier 1: Redaction mark reasons
if marks_reasons_str:
    return marks_reasons_str

# Tier 2: Tag-based fuzzy matching
tag_result = _pl_fuzzy_match_privilege_reason(tags_str, override)
if tag_result and tag_result != '(No basis specified)':
    return tag_result

# Tier 3: explicit placeholder
return '(No basis specified)'
```

The override dropdown sits above all three tiers: if the user explicitly picks a basis, that overrides the cascade entirely, matching reviewer intent.

Each tier's presence is distinguishable because the upstream query isolates the sources. A basis that came from a mark reason appears in the subquery-joined `mark_reasons` column. A basis that came from a tag appears because the tag-fuzzy-match returned a non-placeholder value. A basis that came from neither renders the sentinel. A reader (or opposing counsel reviewing the log) can trace which tier fired by comparing the log row against the document's underlying marks and tags.

## How to apply

- Whenever you write `value = a or b or c`, ask: "Does any downstream consumer need to know which of `a`, `b`, or `c` actually supplied the value?" If yes, the cascade must record source.
- When designing a cascade, list tiers in priority order explicitly. Each tier gets a one-sentence description of its forensic weight and when it fires.
- Use an explicit sentinel for the fallthrough case (see `no-silent-default`). The sentinel is itself a tier — tier N is "none of the above, placeholder."
- Tests for a cascade should exercise each tier in isolation (data that makes only that tier fire) and confirm the output distinguishes it from other tiers.
- When a cascade is renamed or reordered, the commit message should list the old and new tier priorities and the forensic implication of the change.

## See also

- **Related lessons:** `docs/lessons/no-silent-default.md`, `docs/lessons/defensibility-statement-practice.md`
- **Source:** `docs/archive/specs/Privilege_Log_AutoLoad_Spec.md` Part 1g (three-tier cascade spec)
- **Relevant code:** `pages/5_Production.py` `_pl_resolve_privilege_basis`, `_pl_fuzzy_match_privilege_reason`
