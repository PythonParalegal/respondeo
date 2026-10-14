# Regression Test as Calibration Canary

## One-sentence summary

When a regression test fails on an algorithm change, treat the failure as a signal that the *parameter choices* were wrong, never as a target to fit by tuning parameters or fixtures.

## The pattern

Algorithm-tuning preflights often pick concrete parameter values (similarity thresholds, k-gram sizes, retry counts) backed by informal arithmetic. The regression test pins the expected behavior at those values. When execution shows the test failing:

- **Anti-pattern:** silently adjust the threshold / k / fixture content until the test passes. This fits the algorithm to the test and defeats the regression-pinning purpose — every future change risks the same silent re-fit.
- **Correct response:** treat the failure as empirical evidence that the parameter choice was wrong. Abort the commit. Report the failure with measured values. PM drafts a new preflight cycle revising the parameter choices with the empirical data.

The discipline preserves the audit trail (every parameter value is PM-deliberated against measured data) and ensures the regression test remains a meaningful contract rather than a moving target.

The exception is *fixture correctness* — if a fixture is wrong for reasons unrelated to algorithm parameters (e.g., the fixture text was too short for the threshold to discriminate, or the fixture happened to share a literal phrase with the negative-case fixture), adjustments are allowed. CLI judgment distinguishes "fixture is wrong" (allowed) from "parameters need tuning" (preflight revision required). When uncertain, default to preflight revision.

## Concrete example

beta-2.16 S-1a (NearDupe shingling fix) chose k=5 shingling + threshold 0.95 at preflight v3 based on PM's informal Jaccard arithmetic (~0.86 predicted invoice similarity). At execution, the FW-near-dupe test failed: short-body fixtures had Jaccard 0.79-0.89, not clustering at 0.95.

The anti-fitting guardrail (codified in S-1a §5.2) prevented tuning. CLI aborted with measured data. PM's v4 preflight cycle revealed:
- k=5 alone dropped invoices to ~0.73 (PM's arithmetic was off; k=5 is MORE aggressive than predicted)
- The threshold raise to 0.95 was over-correction — k=5 alone fixes Flag #22 at any threshold ≥ 0.74
- v4 reverted threshold to 0.90 (unchanged from production); rewrote fixtures with realistic-length bodies

At v4 delta-check, CLI's pre-measurement caught a second calibration issue (MinHash estimator undershoot at num_perm=128). Again no tuning — v5 redesigned fixtures with narrow preambles (exact Jaccard ~0.99) to clear the estimator-variance margin. v5 shipped clean at an earlier commit.

Without the anti-fitting discipline, the most likely outcome would have been: tune k or threshold or fixture until v3 tests passed, ship a "working" algorithm that's actually parameter-fit to one fixture, and discover months later that production behavior didn't match the test claims.

## How to apply

- In every algorithm-tuning preflight's §5 Test Plan, include an explicit anti-fitting guardrail: enumerate which values (thresholds, k, num_perm, fixture content) are PM-deliberated and locked at preflight time vs. which are CLI-adjustable at execution.
- For PM-deliberated values: failures abort the commit; PM drafts a new preflight cycle with the empirical measurement data.
- For CLI-adjustable values: CLI judgment, documented in the commit message with rationale.
- Pre-measure fixtures BEFORE writing tests — for probabilistic algorithms (MinHash, locality-sensitive hashing, sampling-based estimators), informal arithmetic on exact-Jaccard or similar can mislead by full standard-deviation margins. Empirical pre-measurement at preflight delta-check time prevents execution-abort cycles.
- The N-Stage Gate's CLI pre-measurement step is the safety net for under-calibrated preflights; PM's responsibility is to make preflights well-calibrated enough that pre-measurement passes on first try.

## See also

- `docs/lessons/grep-count-discipline.md` — sibling discipline for non-algorithm count claims; both rest on "measure, don't assume."
- `docs/lessons/n-stage-gate-revision-handling.md` — the gate that operationalizes "abort, don't fudge."
- `docs/lessons/preflight-proportionality.md` — calibration-discipline is heavier than typical doc commits; this lesson reflects that heavy ceremony.
- `docs/specs/library_self_correction_design.md` §3 — the broader self-correction infrastructure this discipline plugs into.
