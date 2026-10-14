# Family Integrity Over Dedup

**One-sentence summary:** When deduplication threatens to orphan a child from its parent (e.g., an attachment whose parent email is the only copy kept), preserve the family intact over the dedup savings.

## The pattern

In eDiscovery, families are legal units. An email plus its attachments is produced together because the attachments are context for the email, and the email is provenance for the attachments. A document plus its extracted embeds, a PST container plus the messages extracted from it, a threaded conversation and its roots — all share the property that breaking them mid-production creates discovery gaps. Opposing counsel will see an attachment with no parent and ask where the parent went. A magistrate will order re-production. The cost of breaking a family at dedup time is more than the space saved.

The rule: every dedup, suppression, or filtering operation that could remove a document must check family relationships before removing. If removing the document would orphan a child, the document is retained by reference, even if retaining it means less-than-maximum dedup efficiency. The design choice is conservative and defensible: keeping an occasional extra copy is cheaper than re-producing under court order.

This applies across multiple operations: content-hash dedup (exact duplicates where one copy is an attachment), thread suppression (where the suppressed email is a parent), near-dupe clustering (where the representative is a parent whose children are not in the cluster), and custodian filtering (where a custodian boundary would sever a family). Each operation should include an explicit "does this break a family?" check before removing the candidate, and if it does, promote the candidate out of the removal set.

The forensic cost of breaking a family is higher than the storage cost of keeping it. Designers should err on the side of retention. When in doubt, tag the retained document with an informational marker (e.g., `Inclusive-Attachments`) so reviewers can see why a document that would normally be suppressed is being kept.

## Concrete example

**Sprint:** beta-2.9 attachment-aware thread suppression (`docs/archive/specs/SPRINT_attachment_aware_threading.md`).

Email threading in `3_Analytics.py → run_threading()` classifies emails as either `Inclusive` (thread principal, keep for review) or `Thread-Suppressed` (redundant, skip). Suppression propagates to children: when a parent email is marked `Thread-Suppressed`, all its attachments inherit the tag. The bug: if an original email with attachments is suppressed because a later reply is the thread principal, the attachments become orphaned — they exist in the DB but are invisible in production because both they and their parent are tagged `Thread-Suppressed`.

The fix adds a second classification pass. After the threading algorithm builds `inclusive_docs` and `suppressed_docs`, any email in the suppressed list that has child documents in `documents.parent_id` is moved to the inclusive list. The attachments then stay producible alongside their parent. The promoted emails receive a secondary tag `Inclusive-Attachments` so reviewers can see at a glance why the email was retained.

The spec's scope decision is explicit and load-bearing:

> ALL attachment-bearing emails are un-suppressed, regardless of whether the attachments are unique or duplicated elsewhere. No uniqueness checks. Conservative and defensible.

The conservative stance is the entire point. A uniqueness check would save more space but would create cases where the uniqueness logic itself becomes discoverable methodology. Keeping every attachment-bearing email is simpler to defend: "we preserved all families; no exceptions."

## How to apply

- Any function that filters, suppresses, or dedups documents must check family relationships before removal. Query `parent_id` for any removal candidate that could be a parent, or check against a pre-built family map.
- If removing the candidate would orphan a child, promote it out of the removal set and optionally tag with a family-preservation marker.
- Family-preservation tags are informational, not operational — they don't change filtering logic, they explain to reviewers why a document is retained.
- Tests for dedup, suppression, or filtering should include a "candidate has children" case and assert the candidate is retained.
- In code review of filtering/dedup code, explicitly ask: "Does this break families?" If the answer is unclear, add the family check.

## See also

- **Related lessons:** `docs/lessons/defensibility-statement-practice.md`, `docs/lessons/system-tags-protected-registry.md`
- **Source:** `docs/archive/specs/SPRINT_attachment_aware_threading.md` (full sprint spec — the attachment-aware promotion pattern)
- **Relevant code:** `pages/3_Analytics.py` `run_threading()` attachment-promotion pass; `db_manager.py` family-walk helpers like `_walk_family_root()`
