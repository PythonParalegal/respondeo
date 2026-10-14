# System Tags Protected Registry

**One-sentence summary:** The `_SYSTEM_TAGS` registry protects tags that automated logic sets and reads from accidental user manipulation — a user-edited system tag breaks the automation that depends on it.

## The pattern

When an application uses string tags as both user-visible labels and inputs to automated logic, the two purposes conflict. A reviewer editing tags in the UI to re-categorize a document can accidentally remove a tag that a downstream pipeline depends on. Threading, near-dupe clustering, production family grouping, redaction-status inference — any automation that reads tags as input breaks silently when a reviewer removes the expected tag from the wrong row.

The failure mode is hard to diagnose after the fact. The reviewer removed a tag three days ago; the production run today produced the wrong subset; no direct audit trail connects the two events because the reviewer's edit was a legitimate action on a field the UI allowed them to edit. Reconstructing the state requires comparing historical audit-log entries against current tag state, document by document.

The rule: tags used as automation inputs live in a namespace the UI cannot edit. The `_SYSTEM_TAGS` registry is the explicit list of those tags. Any tag in the registry cannot be added, removed, or modified through the reviewer-facing tag editor. The registry is the single source of truth — UI logic checks against it before allowing edits, and automation code reads it when needing to protect against manual drift.

The cost of the registry is small: a central set, a UI guard, a test that exercises the guard. The benefit is that automation can trust its input tags to mean what they meant when the automation last ran. A reviewer can still *see* the tags; they just cannot *change* them from the Review UI. If a human needs to override a system tag (rare, needed for certain data-quality repairs), that goes through a separate admin-path tool that logs the override explicitly.

## Concrete example

**Sprint:** beta-2.9 attachment-aware thread suppression (`docs/archive/specs/SPRINT_attachment_aware_threading.md` change 6).

The Review page has a `_SYSTEM_TAGS` set that protects threading and near-dupe outputs from reviewer edit:

```python
_SYSTEM_TAGS = {'Inclusive', 'Thread-Suppressed', 'NearDupe-Suppressed', 'Inclusive-Attachments'}
```

When the spec introduced the new `Inclusive-Attachments` informational tag (applied to emails promoted out of thread suppression because they carry attachments), it explicitly added the tag to `_SYSTEM_TAGS`. The rationale in the spec: the tag is set by the threading pipeline and read by the downstream production sort. A reviewer who removed it from one email would silently change production output for that email's family.

The spec's change-6 block stated the rule:

> In `4_Review.py`, the `_SYSTEM_TAGS` set and `_SYS` tuple protect system-computed tags from being cleared during re-imaging. Add `Inclusive-Attachments` to both.

Two registrations are needed because the Review UI and the re-imaging logic consult the registry at different points. The set is the authoritative list; the tuple is a prefix-match optimization. Both must stay in sync.

The related `substring-replace-ordering` lesson in this library comes from the same sprint — `Inclusive-Attachments` contains `Inclusive` as a substring, so cleanup operations that strip system tags must strip the longer one first.

## How to apply

- Before adding a new tag that feeds downstream logic, register it in the project's system-tag registry (`_SYSTEM_TAGS` or equivalent). Do not rely on the tag being rare or on reviewers knowing not to touch it.
- Verify the Review UI (or equivalent tag editor) consults the registry before allowing edits. If the UI does not currently do this, the registry is documentation, not enforcement.
- When writing a tag-stripping operation (re-imaging, re-running threading, cleanup), consult the registry and preserve registered tags. Otherwise the automation's next run has missing input.
- Tests: for every system tag, include a test that attempts to remove it through the reviewer-editor path and asserts the removal is refused.
- When renaming a system tag, update the registry and every caller in the same commit. A mid-rename state where the tag name doesn't match the registry is a broken state.

## See also

- **Related lessons:** `docs/lessons/substring-replace-ordering.md`, `docs/lessons/family-integrity-over-dedup.md`
- **Source:** `docs/archive/specs/SPRINT_attachment_aware_threading.md` change 6 (`_SYSTEM_TAGS` update)
- **Relevant code:** `pages/4_Review.py` `_SYSTEM_TAGS` and `_SYS` registries; Review UI tag-editor guard
