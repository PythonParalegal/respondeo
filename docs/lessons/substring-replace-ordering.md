# Substring Replace Ordering

**One-sentence summary:** When a `REPLACE()` call targets a token that is a substring of another token you also replace, run the longer replacement first, or the longer token gets partially consumed by the shorter one.

## The pattern

String replacement is not associative. If `"Inclusive-Attachments"` and `"Inclusive"` both appear in the same text and both must be replaced with `""`, the ordering of those two operations determines the final state. Replacing the shorter token first turns `"Inclusive-Attachments"` into `"-Attachments"`, leaving a corrupted artifact that no subsequent replace will clean up. Replacing the longer token first removes `"Inclusive-Attachments"` entirely, and the shorter `"Inclusive"` replace then cleans up any remaining standalone occurrences.

This applies wherever multiple literal substitutions operate on overlapping tokens: SQLite `REPLACE()`, Python `str.replace()`, `re.sub()` with literal patterns, and any chained string-substitution pipeline. The failure mode is silent data corruption, not an error — the sort of defect that only surfaces when someone notices a stray `-Attachments` tag on a document and asks where it came from.

The cleanest defensive form is to sort replacement targets by descending length before applying them. Where semantics permit (natural-language text, not arbitrary identifiers), word-boundary anchors such as `\b` in regex provide a second line of protection. When neither is available (e.g., SQLite's `REPLACE()` takes only literal strings, not regex), descending-length ordering is the only defense and must be enforced by convention and code review.

## Concrete example

**Sprint:** beta-2.9 attachment-aware threading (`docs/archive/specs/SPRINT_attachment_aware_threading.md`).

The Analytics "Clear & Re-Run Threading" block clears three tags from the `documents.tags` column via chained `REPLACE()` calls. The three tags are `Inclusive-Attachments`, `Thread-Suppressed`, and `Inclusive`. The first tag contains the third as a substring. The required ordering:

```sql
-- Correct:
UPDATE documents SET tags = REPLACE(tags, 'Inclusive-Attachments', '') WHERE ...;
UPDATE documents SET tags = REPLACE(tags, 'Thread-Suppressed',     '') WHERE ...;
UPDATE documents SET tags = REPLACE(tags, 'Inclusive',             '') WHERE ...;
```

If the first two statements are swapped (shorter first), `Inclusive-Attachments` becomes `-Attachments` and the subsequent `Inclusive` replace does nothing because the string it was looking for was already partially eaten.

The spec's change-5 block explicitly flags the ordering constraint:

> **IMPORTANT ORDER:** The `Inclusive-Attachments` replace MUST run BEFORE the `Inclusive` replace, because `Inclusive-Attachments` contains the substring `Inclusive`.

## How to apply

- When writing a chained-replace operation, list the target tokens and sort them by descending length. The longest token is replaced first.
- Before adding a new replace to an existing pipeline, check every existing target for substring containment with the new token. If containment exists in either direction, re-sort.
- Tests that cover tag cleanup should assert the absence of partial artifacts (e.g., `-Attachments`, `Suppressed`) in addition to the intended tags. A pipeline that leaves corrupted substrings passes a "tags are gone" test but fails a "no artifacts remain" test.
- In code review, any PR that adds or modifies a `REPLACE` chain should list the tokens and their ordering as part of the review summary. Reviewers check ordering by inspection, not by running the code.

## See also

- **Related lessons:** `docs/lessons/system-tags-protected-registry.md`, `docs/lessons/no-silent-default.md`
- **Source:** `docs/archive/specs/Privilege_Log_Fixes_Round2.md`, `docs/archive/specs/SPRINT_attachment_aware_threading.md` (change 5 ordering block)
- **Relevant code:** `pages/3_Analytics.py` (threading reset block)
