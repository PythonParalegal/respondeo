# Analytics Corpus Completeness

**One-sentence summary:** Threading and near-dupe analytics produce wrong results if run on an incomplete corpus — there is no UI guard against it, so the rule is enforced by procedure.

## The pattern

Certain analytics operations depend on having every relevant document in the corpus before they run. Email threading builds a reply graph keyed on message IDs and reference headers; a late-arriving message that holds the chain's missing link means threads computed before the message arrived are wrong and stay wrong. Near-duplicate clustering uses MinHash LSH with a probabilistic false-positive rate that depends on the full-corpus shingle distribution; running it on a partial corpus produces a different representative-cluster assignment than running it on the complete corpus, and re-running later does not always converge to the same groupings.

The platform cannot programmatically detect completeness. Knowing whether the user has more documents coming is outside the system's reach — documents arrive through whatever ingestion path the case requires, on whatever schedule the matter demands. An attempted UI guard that blocked analytics until "the corpus looks complete" would produce false-positive blocks (a case where ingestion is intentionally phased) and false-negative passes (a case where the user forgot a PST). The platform's choice: no UI guard. The rule is enforced by training, documentation, and review discipline.

The procedural rule: analytics runs AFTER ingestion and processing are fully complete for the corpus being analyzed. If new documents arrive after analytics has run, analytics must be re-run, not incrementally updated. The Analytics page documents this constraint; supervision during review catches it; the analytics features themselves do not try to be cleverer than the user about it.

A future enhancement candidate is an ingestion-completeness dashboard that makes corpus state visible without trying to infer completeness — show counts, show last-ingest timestamps, show any docs in `Needs_Processing` status, and let the user decide. That decision support is cheaper than a UI guard and keeps the judgment call with the paralegal.

## Concrete example

**Source:** `AGENTS.md` Known Constraints, item 4:

> **Analytics requires a complete corpus.** Threading and near-dupe produce wrong results if run mid-ingestion. No UI guard — enforce by procedure.

The concrete failure modes:

- Threading: a reply chain `A → B → C → D` where `C` has not yet been ingested at analytics-run time. Threading sees `A → B` (short thread, `B` is the principal) and separately `D` (singleton, no parent found). When `C` arrives later, the system does not re-link: `D` stays a singleton, `B` stays the principal of a two-message thread. The actual four-message thread is split and silently incorrect.
- Near-dupe: MinHash LSH's similarity judgments depend on the corpus's shingle distribution. If the corpus grows after clustering, a late-arriving document that would have been a cluster representative ends up in a different cluster (or none). The clustering result is stable against the corpus-at-analytics-time but not against the corpus-at-production-time.

In practice, the procedural rule is enforced by: (1) the Analytics page's documentation explicitly stating the constraint; (2) paralegal training during onboarding; (3) attorney supervision during matter prep; (4) the CHANGELOG entry that lands any analytics feature explicitly flagging the completeness requirement.

## How to apply

- Before running threading or near-dupe, confirm ingestion is fully complete for the corpus being analyzed. No `Needs_Processing` documents, no pending PST explosions, no queued BYOS syncs with inbound content.
- If documents arrive after analytics has run, re-run analytics from scratch. Do not attempt incremental updates — the current platform does not guarantee convergence of incremental threading/near-dupe results.
- Feature additions that extend analytics (new dedup algorithm, new threading heuristic) inherit this constraint. The feature's documentation must state it explicitly.
- When writing user-facing copy for analytics, include a visible reminder of the completeness requirement (e.g., a banner on the Analytics page). Procedural enforcement is weaker than any UI guard; visible prompts strengthen it.
- If a case requires phased analytics (regulatory rolling production, e.g.), document the batch boundaries explicitly in the case's defensibility trail. "We ran threading on Batch 1 at time T1, and threading on Batch 2 at T2" is defensible if the batches are document-disjoint. "We ran threading at T1, got more documents at T2, kept using T1's result" is not.

## See also

- **Related lessons:** `docs/lessons/defensibility-statement-practice.md`, `docs/lessons/family-integrity-over-dedup.md`
- **Source:** `AGENTS.md` Known Constraints item 4
- **Relevant code:** `pages/3_Analytics.py` `run_threading()`, `run_near_dupe()`; Analytics-page documentation
