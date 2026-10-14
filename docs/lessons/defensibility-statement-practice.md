# Defensibility Statement Practice

**One-sentence summary:** Every discovery-material decision (how a thread was built, why a dedup skipped a document, what metadata was used to form a family) carries a courtroom-ready paragraph stating the rationale, written before the code ships.

## The pattern

In eDiscovery, any decision that affects which documents are produced — or which documents are suppressed, or how families are grouped, or how dedup works — will eventually be challenged. Opposing counsel, a 30(b)(6) deposition, a discovery-about-discovery motion, a magistrate's order — all of these demand a written explanation of the methodology that shaped the production set. If the explanation does not exist in writing, the sponsoring attorney cannot certify the production under FRCP 26(g), and the methodology itself becomes the discovery fight.

The practice: for every feature that affects what documents get produced, suppressed, grouped, or labeled, a defensibility paragraph exists in writing, near the code, before the feature ships. The paragraph states the rule in plain language (an attorney, not an engineer, must be able to read and defend it), the inputs it considers, the edge cases and how they are handled, and the consistency guarantee (same inputs produce same outputs across runs).

The test: a reviewing attorney reads the paragraph and asks, "Can I sign FRCP 26(g) on this?" If yes, the paragraph is sufficient. If no — ambiguity, undocumented edge case, or a decision that the attorney cannot explain to a judge — the paragraph is incomplete, which means the feature's design is incomplete.

Write the paragraph before writing the code. If you cannot write the paragraph, you have not finished the design, and the code will ship with a methodology hole that discovery counsel will find later. The paragraph also serves as the acceptance test for the feature: if the implementation diverges from the paragraph, either the code is wrong or the paragraph needs updating, and one of them is a design error.

## Concrete example

**Sprint:** beta-2.9 attachment-aware threading (`docs/archive/specs/SPRINT_attachment_aware_threading.md` §Defensibility Statement).

The feature un-suppresses emails that carry attachments during thread suppression, so that their attachments don't get orphaned from the production. The spec's defensibility paragraph:

> This feature preserves parent-child document relationships during email thread suppression. When an email carries attachments, it is retained alongside the thread-principal rather than being suppressed, because suppressing the parent would orphan its attachments from production. This is consistent with EDRM best practices for maintaining family integrity in document productions.

Notice what the paragraph does: states the rule (retain attachment-bearing emails), states the rationale (suppression would orphan children), cites external authority (EDRM best practices), and is written in language a reviewing attorney or magistrate would understand. It does not mention Python, SQL, `_SYSTEM_TAGS`, or any implementation detail — those belong in the code comments. The paragraph is the methodology statement; the code is the implementation of it.

The paragraph also serves as a pointer back to the design. If the code ever drifts — say, someone adds a condition that un-suppresses only when attachments are unique — the drift contradicts the paragraph's "ALL attachment-bearing emails are un-suppressed" wording, and either the paragraph updates or the code does.

## How to apply

- For every feature that affects what documents are produced, suppressed, tagged, grouped, or labeled, write the defensibility paragraph before writing the code. Paste it into the sprint spec, the preflight, or an in-code docstring near the function.
- The paragraph's audience is a reviewing attorney, not a developer. If it contains `conn.execute`, function names, or table schema, it is the wrong audience.
- Include: the rule in plain language, the inputs considered, the edge cases and their handling, the consistency guarantee, and the external authority (EDRM, FRCP, Sedona Principles) if applicable.
- When the feature ships, the paragraph stays with it — in `docs/specs/`, a docstring, or `DEPENDENCY_MAP.md`. A paragraph that exists only in a commit message is not retrievable when discovery counsel asks for it.
- In code review, ask: "Where is the defensibility paragraph?" If the PR does not surface one, that is a review blocker, not a nit.

## See also

- **Related lessons:** `docs/lessons/family-integrity-over-dedup.md`, `docs/lessons/system-tags-protected-registry.md`, `docs/lessons/no-silent-default.md`
- **Source:** `docs/archive/specs/SPRINT_attachment_aware_threading.md` §Defensibility Statement (as an exemplar)
- **Relevant code:** any feature affecting production/suppression/family grouping should carry its defensibility paragraph in `docs/specs/` or an in-code docstring
