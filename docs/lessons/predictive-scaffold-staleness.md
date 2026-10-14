# Predictive Scaffold Staleness

**One-sentence summary:** Predictive "Expected contents" blocks in scaffold-READMEs tend to go stale between draft-time and fill-time; prefer minimal scaffolds with post-factum content lists.

## The pattern

When creating a new directory with a README, there is a temptation to enumerate what will live there eventually — "this folder will contain X, Y, Z specs once the sprint archives them." This predictive block is written before the actual contents exist, based on what the drafter expects.

By the time the files land, the prediction often differs from reality: shipping-status tags (archived / partially-shipped / superseded) turn out wrong, some predicted entries never materialize, and unpredicted entries arrive. The README is now worse than no README — it actively misleads a reader who trusts it over git log.

The failure mode is that the drafter writes the prediction based on their mental model at scaffold-time, and the mental model drifts over the intervening sprint arc as shipping-status audits refine the real verdicts. The README is not updated at each shift because the scaffold author is rarely the sprint executor, and the executor doesn't treat README predictions as live claims to audit.

## Concrete example

In beta-2.11 6e.1, the scaffold-draft for `docs/archive/specs/README.md` seeded an "Expected contents (post-6e)" block listing four predicted archive entries with shipping-status tags. By 6e.2 execution, CLI found four of the tags were wrong:

- `Respondeo_License_System_Spec.md` tagged "archived" — actually unshipped (spec stayed in `docs/specs/`).
- `SPEC_interactive_redaction_viewer.md` same misclassification.
- `Privilege_Log_Editor_Spec.md` tagged "superseded by AutoLoad" — actually shipped 2026-03-31 per CHANGELOG line 383.
- `Privilege_Log_Profile_Integration_Spec.md` tagged "partially shipped, rest deferred" — actually fully shipped 2026-04-01 per CHANGELOG line 293.

CLI replaced the predictive block with a generic post-factum note pointing to `CHANGELOG.md` per-file sprint dates as the authoritative shipping record. The corrected README is shorter, cannot go stale from prediction-vs-reality drift, and directs the reader to the canonical shipping-status source rather than duplicating it.

## How to apply

- When creating a scaffold README for a directory that will be populated later, write a 1–2 sentence purpose statement and stop. Resist the urge to pre-list contents.
- Let the real entries accumulate. The directory listing itself IS the content list.
- If a content pointer is genuinely useful, point at the authoritative external source (CHANGELOG date, git log, commit hash) rather than duplicating it in the README.
- A README that enumerates contents is a manifest, and manifests go stale silently. A README that describes purpose stays stable as contents turn over.
- If scaffold-time prediction is unavoidable (e.g., to document the architectural intent of a soon-to-be-populated tier), mark the block as "planned, verify at fill-time" so the fill-time executor knows to audit it rather than assume it's current.

## See also

- **Related lessons:** `docs/lessons/chain-of-moves-stale-refs.md` (same sprint arc, same multi-commit-refactor root cause).
- **Source:** the scaffold-README correction during 6e.2 execution.
