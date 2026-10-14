# docs/lessons — Durable Pattern Library

Durable lessons, patterns, gotchas, and principles extracted from sprint
retrospectives. Each file captures one focused idea.

Before writing code that resembles a past footgun, check whether the
pattern lives here. When a sprint retrospective surfaces a new lesson
worth keeping, classify it against the Lesson Integration Decision Tree
in `CLAUDE.md` — lessons land here when they are durable patterns, not
rules that belong in CLAUDE.md's always-injected context.

## Canonical lesson file structure

Every lesson follows the 5-section template: **One-sentence summary**,
**The pattern**, **Concrete example**, **How to apply**, **See also**.
Length target 50–150 lines per file.

## Catalogue

### Data integrity and defensibility

- [`defensibility-statement-practice.md`](defensibility-statement-practice.md) — Every discovery-material decision carries a courtroom-ready rationale paragraph.
- [`no-silent-default.md`](no-silent-default.md) — Missing values render as visible placeholders, never as plausible guesses.
- [`three-tier-cascade-resolution.md`](three-tier-cascade-resolution.md) — Cascaded value resolution must record which tier supplied the value.
- [`family-integrity-over-dedup.md`](family-integrity-over-dedup.md) — Preserve email/attachment families intact even when dedup would save space.
- [`container-family-model.md`](container-family-model.md) — Containers don't make families; emails do. Archive containers (.pst/.zip) at top-of-family must not propagate group_id. Canonized beta-2.15 Commit 4.
- [`extraction-rendering-symmetry.md`](extraction-rendering-symmetry.md) — When two code paths classify the same thing, use a single shared predicate. Fix for libpff CID over-skip. Canonized beta-2.15 Commit 5.
- [`system-tags-protected-registry.md`](system-tags-protected-registry.md) — Tags used by automation live in a protected namespace to prevent user edits breaking logic.
- [`arrow-serialization-hygiene.md`](arrow-serialization-hygiene.md) — Use `None`, not `''`, for missing numeric values in DataFrames.

### Data-layer discipline

- [`atomic-multi-table-writes.md`](atomic-multi-table-writes.md) — Multi-table writes run in a single connection with a single commit and rollback-on-exception.
- [`zero-risk-data-layer-rollback.md`](zero-risk-data-layer-rollback.md) — Preserve persisted format across refactors so commits stay revertable without data loss.
- [`batch-commit-discipline.md`](batch-commit-discipline.md) — Large migrations split into independently-revertable batches, each with its own verification gate.
- [`exempt-annotation-convention.md`](exempt-annotation-convention.md) — `# db_manager: exempt (reason)` distinguishes intentional page-file SQL from migration misses.
- [`sqlite-version-floor.md`](sqlite-version-floor.md) — Production SQL uses only operators available on the deployment SQLite version, not the dev machine's.
- [`sqlite-fk-off-by-default.md`](sqlite-fk-off-by-default.md) — SQLite ignores `ON DELETE CASCADE` unless `PRAGMA foreign_keys` is explicitly on; handle cascade manually.

### Code-pattern footguns

- [`substring-replace-ordering.md`](substring-replace-ordering.md) — Longer replacement target must run before any shorter substring of it.
- [`fragment-scope-rule.md`](fragment-scope-rule.md) — `@st.fragment` fits nav/zoom/draw; app scope fits DB writes. Mismatching bleeds state across tabs.
- [`streamlit-drawable-canvas-workarounds.md`](streamlit-drawable-canvas-workarounds.md) — Unmaintained upstream: post-install patch + load-canvas checkbox + per-doc/page canvas key.
- [`analytics-corpus-completeness.md`](analytics-corpus-completeness.md) — Threading and near-dupe require a complete corpus; enforced procedurally, not by UI guard.

### Workflow discipline

- [`scope-expansion-probe.md`](scope-expansion-probe.md) — Mid-sprint scope expansion passes a three-criteria test or becomes a separate commit.
- [`line-number-drift-reverification.md`](line-number-drift-reverification.md) — Preflights re-verify cited line numbers against current file state before execution.
- [`underscore-prefix-utility-scripts.md`](underscore-prefix-utility-scripts.md) — `_name.py` marks one-shot utility scripts exempt from version headers and per-file CHANGELOG entries.
- [`chain-of-moves-stale-refs.md`](chain-of-moves-stale-refs.md) — Multi-commit refactors must re-verify refs at every move; prior fixes don't inherit across commits in the same arc.
- [`grep-by-stem-not-spec-name.md`](grep-by-stem-not-spec-name.md) — Shipping-status audits grep behavior stems, not the literal function names specs propose; abbreviation is the norm.
- [`grep-count-discipline.md`](grep-count-discipline.md) — Count claims in preflights need verified grep at draft time and re-verification on every patch; canonizes 5 empirical defect classes across 3 families.
- [`predictive-scaffold-staleness.md`](predictive-scaffold-staleness.md) — Scaffold-READMEs should defer content lists to post-factum; predictive blocks go stale silently.
- [`synthetic-sample-data-in-docs.md`](synthetic-sample-data-in-docs.md) — Write docs with synthetic placeholders so lessons stay trackable; don't gitignore indefinitely.
- [`n-stage-gate-revision-handling.md`](n-stage-gate-revision-handling.md) — Preflight revisions require a fresh delta-scoped CLI pre-flight check before Stage 2 greenlight; patch and greenlight never ship in the same message.
- [`not-in-git-tracked-not-existent.md`](not-in-git-tracked-not-existent.md) — Existence ≠ tracked; `git ls-files <path>` is the authoritative check; in-session drafts are the common self-own.
- [`permission-gate-strategic-vs-hygienic.md`](permission-gate-strategic-vs-hygienic.md) — Permission-gate visibility is load-bearing for strategic edits, satisfied by tracked diffs for hygienic edits.
- [`premature-release-tag.md`](premature-release-tag.md) — Tag cut waits for the sprint-close addendum commit; force-retag is only safe on solo/private repos.
- [`preflight-proportionality.md`](preflight-proportionality.md) — The 8-section preflight fits code refactors; doc-only and tiny hygiene commits warrant the lightweight 3-section template instead.
- [`edit-tool-staging-gap.md`](edit-tool-staging-gap.md) — `Edit` and `Write` tools modify but don't stage; pre-commit verification must scan `git status --short` for leading-space-`M` and `??` entries before `git commit` fires.
- [`fix-the-prose-miss-the-code-block.md`](fix-the-prose-miss-the-code-block.md) — Preflight revisions update prose-explanation layers but miss code-block instances of the old pattern; mitigated by post-patch grep on stems. Canonized beta-2.16 Commit 7 after 3 in-sprint recurrences.
- [`regression-test-as-calibration-canary.md`](regression-test-as-calibration-canary.md) — Regression test failures on algorithm changes signal wrong parameter choices, not tuning targets. Canonized beta-2.16 Commit 7 from F-4 anti-fitting discipline shipped in S-1a.

## Adding a new lesson

1. Confirm the candidate belongs here via the Lesson Integration Decision Tree in `CLAUDE.md` (item 4: durable pattern extracted from a sprint).
2. Write the file following the 5-section template in §2 of the 6c.2 packet.
3. Add an entry to the appropriate section above with a one-line synopsis.
4. Cross-reference from any related existing lesson.
5. Commit with a `DOCS:` CHANGELOG entry.
