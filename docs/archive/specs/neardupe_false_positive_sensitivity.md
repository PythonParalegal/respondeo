# Spec — NearDupe Analytics False-Positive Sensitivity

**Status:** UNSHIPPED — awaiting sprint allocation.
**Origin:** A design review of near-dupe tag behavior on template-heavy documents showed that template-similar-but-content-distinct business records can be clustered under `NearDupe-Suppressed`.
**Severity:** Latent fragility. No known defensibility failure, but a failure mode exists in the near-dupe clustering that could cause either over-withholding or under-review in future productions on different case profiles.

## Partial shipping note (added 2026-05-24, beta-2.16 Phase 3)

S-1a (algorithm tuning) shipped at beta-2.16 Commit 6: word-level shingling
replaced with a 5-word k-gram sliding window in
`pages/3_Analytics.py:_compute_minhash_signature()`; regression fixture pinned
at `tests/test_neardupe_shingling.py`. Slider default threshold unchanged at
0.90 — empirically, k=5 shingling alone addresses Flag #22 (template-distinct
invoices drop from word-level ~0.93 to k=5 ~0.73–0.81, well below the existing
0.90 default; an earlier proposal to also raise the threshold to 0.95 was
reverted after it broke true-near-dupe recall — see the S-1a preflight arc).

Fixture-design note: the FW-clustering test uses narrow-preamble fixtures
(`"FW: "` + ~170-token body → exact Jaccard ~0.99) to keep MinHash estimates
(num_perm=128, variance ~0.088) reliably above the 0.90 threshold. The tests
do NOT pin clustering for substantial-content additions like RE-with-reply —
those are distinct documents by design, pinned separately by
`test_re_with_substantive_reply_NOT_clustered`.

**Still UNSHIPPED:** S-1b (cluster review UI with un-suppress affordance and
attestation audit trail) and S-1c (defensibility report listing every
NearDupe suppression with reviewer attestation). Spec stays at NUANCED status
until both ship; full archival per Spec Lifecycle Discipline at S-1c.

## The problem

The near-dupe analytics pipeline tags documents as `NearDupe-Suppressed` / `NearDupe-Principal` based on content similarity. In observed cases, the algorithm is aggregating documents that share a **template/layout** but contain **independently material content** — for example, a series of invoices from the same vendor, each with a distinct invoice number, date, amount, and services rendered.

The tag has downstream production-pipeline effects:
- `NearDupe-Suppressed` documents are typically excluded from reviewer batch exports
- The reviewer sees only the `NearDupe-Principal` version
- The reviewer's disposition (withhold / redact / keep clean) is applied to the principal
- The suppressed siblings inherit the principal's fate

**If the principal and siblings are TRUE near-dupes** (e.g., FW:/RE: copies of the same email with identical body text), the cluster-behavior is correct and saves reviewer time.

**If the principal and siblings share only template and not content**, the cluster-behavior can:
1. Cause distinct responsive records to never reach attorney review (the reviewer sees one invoice, passes on it, all the "siblings" follow — even though each was a distinct transaction)
2. Cause privilege-suppression contagion (if the principal has privileged content, suppressed siblings without that content still get withheld)
3. Cause non-responsive-suppression contagion in the other direction (if the principal is non-responsive for a content-specific reason, siblings that are actually responsive get dropped)

## Possible root causes (to investigate)

Without inspecting the algorithm, candidate failure modes include:

1. **Similarity threshold too low.** If the cosine/Jaccard similarity cutoff for near-dupe clustering is, say, 0.7, invoices sharing 70%+ of their text (boilerplate, company info, vendor terms) will cluster even if the 30% of unique content is where the material information lives.

2. **Insufficient weighting on high-signal tokens.** Numeric identifiers (invoice numbers, dollar amounts, dates, reference numbers) are typically the differentiators on template documents. If the algorithm uses term-frequency weighting that treats these as low-signal (because they vary across the corpus), template similarity dominates.

3. **No structured-data awareness.** Most near-dupe algorithms (MinHash, SimHash, shingled-text) operate on plaintext without awareness of invoice-number fields, dollar-amount fields, or date fields. A structured pre-check that identifies distinct reference numbers before invoking text similarity could eliminate the false positive.

4. **Missing reviewer affordance.** Even if analytics cluster aggressively, a UI mechanism for reviewers to "un-suppress" a flagged sibling upon inspection would let the review process correct the analytics. If the UI only shows the `NearDupe-Principal` and suppresses the siblings from view entirely, there's no escape hatch.

## Recommended design investigation phases

### Phase A — Locate and characterize

- Identify the near-dupe code: likely in `pages/3_Analytics.py` or `db_manager.py` helpers that populate `NearDupe-*` tags
- Document the algorithm: shingling, MinHash, LSH? What's the similarity metric, what's the threshold, what's the clustering linkage?
- Identify the export filter: which queries filter out `NearDupe-Suppressed`? (Should intersect with `pages/5_Production.py` family expansion and review-export paths)

### Phase B — Reproduce with controlled fixtures

- Create a fixture of 5–10 template-similar-but-content-distinct documents (invoice-style)
- Run them through the analytics pipeline
- Capture the similarity scores and clustering decisions
- Confirm the failure mode is reproducible

### Phase C — Remediation options (pick one or more)

1. **Threshold tuning** — raise the similarity cutoff; validate no regression on true near-dupes (the classic FW/RE email thread case).
2. **Structured-field differentiator** — add a pre-check: if docs share >N% text similarity but contain distinct numeric identifiers (invoice number patterns, reference numbers, different dollar totals), treat as distinct.
3. **Reviewer un-suppress affordance** — on the Review page, surface `NearDupe-Suppressed` siblings under a collapsible section when a reviewer opens the principal. Let the reviewer click "un-suppress this sibling" to promote it to independent review. This is a safety net even if the algorithm stays the same.
4. **Export-filter safety** — currently Non-Responsive filter is applied but NearDupe-Suppressed exclusion is less visible. Add a pre-production defensibility report that lists suppressed-but-still-in-family-expanded-production docs so reviewers can see the reach of the filter.

### Phase D — Regression pinning

Add a fixture + test (analogous to `TestProductionFamilyFiltering` added in beta-2.9) that pins the near-dupe threshold behavior. Test with a known template-similar-but-distinct fixture to ensure the algorithm does NOT cluster them after the remediation.

## Relationship to other known issues

- **Flag #5** (page-held connection pattern, deferred to beta-2.13): unrelated
- **Flag #20** (INSERT OR IGNORE silent drop, closed beta-2.13 C1): unrelated
- **Family-expansion leak** (beta-2.9): related surface — both involve the analytics tag applying differently than users expect at production time. The family-expansion fix closed one loop; this spec addresses a different loop (the near-dupe clustering that precedes the family-expansion).

## Action to initialize this in Flag Registry

At the next PM→CLI handoff, add a row to `docs/FLAG_REGISTRY.md` Active flags table:

```
| 22 | Near-dupe analytics clusters template-similar-but-content-distinct documents under NearDupe-Suppressed | Characterized | 2026-04 | 2026-04 | beta-2.13 near-dupe design review | docs/specs/neardupe_false_positive_sensitivity.md |
```

## What this spec does NOT do

- It does NOT prescribe a specific algorithm change without Phase A characterization
- It does NOT block any current production work — the concern is forward-looking
- It does NOT replace the near-dupe analytics with anything specific — it proposes investigating and tuning

