# beta-2.11 Retrospective

**Sprint:** `beta-2.11`
**Version tag cut:** `v2.11.0` (pending merge to main after this commit)
**Commit range:** sprint start through Commit 9; Commit 10 sprint-close addendum extends the range — see §7
**Written:** `2026-04-18` by PM Claude (Cowork session)
**Author:** PM Claude

---

## 1. Sprint Scope

Beta-2.11 began as a non-functional documentation architecture
reorganization. Thesis: the project had accumulated enough durable
knowledge (dependency references, workflow patterns, gotchas) that
keeping it in inline CLAUDE.md prose and scattered scratchpad notes
was no longer sustainable. The sprint installed the four-tier
`docs/{references,lessons,templates,archive}/` structure and migrated
23 durable lessons, 6 dependency references, and 4 workflow templates
into that structure. The sprint-close expected to be a clean "file
move + tag cut."

It wasn't. The sprint-close revealed four gaps that required two
additional commits — Commit 8 (preflight-drafting checklist install)
and Commit 9 (this retrospective + tests + N-stage gate doctrine + 3
lesson additions).

## 2. What Shipped

| Commit | Summary |
| -------- | --------- |
| 6b library scaffolding | Create four-tier `docs/{references,lessons,templates,archive}/` directory structure with placeholder README.md files |
| 6c reference moves | Move 6 existing `*_REFERENCE.md` / `*_PATTERNS.md` files into `docs/references/`; update CLAUDE.md pointer table |
| 6c.2 lesson payload | Install 19 canonical lesson files in `docs/lessons/` with the 5-section template; add `docs/lessons/README.md` index |
| 6d workflow templates | Move `pm_cli_collaboration_workflow.md`, `preflight_template.md`, `defect_triage_template.md`, `scoped_audit_template.md` into `docs/templates/`; CLAUDE.md pointer table |
| 6e.1 spec migrations | Move 8 scratchpad specs into `docs/specs/`; first use of `mv + git add` for gitignored sources |
| 6e.2 archive sweep | Move shipped specs from `docs/specs/` to `docs/archive/specs/`; install Spec Lifecycle Discipline Standing Order |
| 6e.3 save-location standing order | Install Save-Location Coordination Standing Order — codify `docs/specs/` vs `docs/superpowers/` vs `docs/archive/` conventions |
| 6f human-authored iron law | Relax "NEVER touch human-authored files" iron law to permission-gated edit pattern; the maintainer retains visibility via explicit greenlight, not prohibition |
| 7 sprint-close cascade | Update CLAUDE.md Current State, 4 PM-side auto-memories, PROJECT_CONTEXT.md, Walkthrough.md, Technical Overview.md, User_Guide.md; bump `__version__` 2.9.0→2.11.0 (skipping 2.10.x per the maintainer's decision) |
| 8 preflight-drafting checklist | Install `docs/templates/preflight_drafting_checklist.md` — 10-check PM self-audit run against every preflight before handoff |
| 9 sprint-close hardening | Index-drift pytest suite + `docs/retrospectives/` tier + N-Stage Gate doctrine + 3 new lessons (strategic/hygienic, N-stage gate, not-in-git) + corrective Check 1 / Check 10 edits to the preflight-drafting checklist |

## 3. Goals vs. Outcomes

### Achieved as planned

- Four-tier `docs/` architecture installed and populated.
- 23 canonical lessons extracted and filed.
- Workflow templates promoted from scratchpad notes to `docs/templates/`.
- Shipped specs swept to archive; Spec Lifecycle Discipline installed.
- Save-Location Coordination Standing Order installed.
- Human-authored iron law relaxed to permission-gated-edit pattern with
  the maintainer's endorsement.
- Version bump to 2.11.0 with `config.py` / `config.example.py` dual-update.

### Achieved with adjustment

- **Sprint close expanded from "doc cascade" to two additional commits
  (8 and 9).** Original plan was Commit 7 as the final commit of the
  sprint. The maintainer's post-7 review surfaced four gaps — preflight-drafting
  checklist (Gap 1), index-drift tests (Gap 2), retrospectives
  infrastructure (Gap 3), memory consolidation (Gap 4). Gap 4 was
  completed in-session by PM Claude before Commit 8 drafting started;
  Gap 1 shipped as Commit 8; Gaps 2 and 3 (plus three additional
  learnings that surfaced during Commit 8 execution) ship as Commit 9.

- **Commit 8 ironically caught its own meta-class of miss.** The preflight
  prescribed `git mv` to archive the spec file. PM asserted "Both paths
  are tracked," verifying path existence only. The spec was drafted
  in-session and untracked — not gitignored, but equally not-in-git.
  `git mv` failed; CLI recovered with `mv + git add`. This discovery
  spawned the not-in-git lesson (canonized in Commit 9) and the Check 1
  expansion.

- **N-Stage Gate doctrine discovered mid-Commit-9-drafting.** During
  Commit 8 execution, PM patched the preflight in response to CLI's
  pre-flight check flag, but bundled the patch with Stage 2 greenlight
  in the same message. The maintainer caught the pattern-level miss and asked
  whether revisions should go back through the gate. The answer was
  yes. This insight spawned the N-Stage Gate doctrine (Standing Order +
  workflow doc edit + lesson file in Commit 9).

### Deferred

- **Automated preflight-drafting checklist enforcement.** No CI hook or
  pytest case currently verifies that preflights ran the 10-check
  checklist before landing. Left as a future enhancement; human
  discipline suffices for now.
- **Retrospective hook in git pre-commit.** No automation currently
  prompts PM/CLI to write a retrospective at sprint-close. Discipline
  + the new Standing Order in Commit 9 suffice.

## 4. Surprises and Learnings

The biggest surprise of beta-2.11 was how much infrastructure the
"pure documentation" sprint revealed as missing. The reorg was
conceived as file-moves. It became file-moves plus install of two
Standing Orders (Save-Location, Spec Lifecycle) plus a relaxation of
an iron law (human-authored files) plus a checklist template (preflight
drafting) plus a doctrine codification (N-Stage Gate) plus six parity
tests plus a retrospectives tier. Each of these was a corrective
response to a failure mode that surfaced during the sprint, not a
feature in the original plan.

**Failure modes surfaced:**

- **Chain-of-moves stale refs.** Commit 6e.1 moved 8 specs; Commit 6e.2
  moved some of them again into archive; the README indexes at each
  tier needed reconciliation after each move. Prior fixes don't inherit
  across commits. Canonized as `docs/lessons/chain-of-moves-stale-refs.md`.

- **Predictive-scaffold staleness.** Commit 6c.2 pre-scaffolded an
  archive/sprints/README.md that predicted beta-2.11 would produce
  sprint files that never landed (because the sprint pivoted to
  doc-reorg). The scaffold became stale the moment it was committed.
  Canonized as `docs/lessons/predictive-scaffold-staleness.md`.

- **Grep-by-stem discipline.** A pre-sprint shipping-status audit
  searched for spec-proposed function names like `save_user_preferences`
  and reported the feature unshipped. The codebase had shipped it as
  `save_user_pref`. Canonized as `docs/lessons/grep-by-stem-not-spec-name.md`.

- **Not-in-git ≠ gitignored.** Surfaced in Commit 8 execution (see
  above). Canonized as `docs/lessons/not-in-git-tracked-not-existent.md`
  in this commit.

- **Two-stage gate insufficient for revisions.** Surfaced in Commit 9
  drafting (see above). Canonized as `docs/lessons/n-stage-gate-revision-handling.md`
  in this commit.

- **Strategic/hygienic ambiguity in permission-gated edits.** Surfaced
  in Commit 8 drafting. The original "NEVER touch X" iron law got
  relaxed in Commit 6f, but the relaxation introduced ambiguity about
  which edits need explicit greenlight. Resolved via the
  strategic/hygienic split in Check 10. Canonized as
  `docs/lessons/permission-gate-strategic-vs-hygienic.md` in this commit.

**Patterns that started ad-hoc and got canonized:**

- The preflight-drafting checklist itself (Commit 8).
- The N-Stage Gate pattern (this commit).
- The "run the checklist against yourself" discipline — Commit 8's
  preflight ran the 10-check checklist against its own draft and caught
  3 items worth fixing before execution. This should be standard for
  Commit 10+.

**maintainer-redirected decisions:**

- Version jump 2.9.0 → 2.11.0 (skip 2.10). Rationale: beta-2.10 had
  been cut as a tag but the real release-worthy state was the post-
  beta-2.11-reorg; bumping to 2.11.0 signaled "this is the real release
  users should adopt." PM Claude initially proposed 2.10.1; the maintainer
  redirected to 2.11.0.
- Option A vs. Option B on sprint labeling. Original plan was to rename
  the sprint post-hoc or begin beta-2.12. The maintainer chose Option A — treat
  Commits 8 and 9 as beta-2.11 continuation since the work was
  doc-architecture-adjacent.
- Memory consolidation scope. PM Claude initially proposed
  consolidating 18 PM auto-memories into a smaller set. The maintainer pushed
  back — "we want to be sure that content and actual memories are
  not lost." Execution stayed conservative: 1 merge (2 gitignore
  memories → 1), 2 content updates, net 18 → 17 files. No content loss.
- Strategic/hygienic split. PM Claude's initial Check 10 draft treated
  CLI's own `.claude/memory/MEMORY.md` as requiring greenlight. The maintainer
  pushed back: "memories should be editable outside of me... if you
  think CLI can be trusted with his own memories." The split was
  introduced in response — CLI maintains hygienic files autonomously
  under existing Standing Orders; strategic touches get greenlight.

## 5. Lessons Canonized

From this sprint, the following new entries landed in `docs/lessons/`:

- `docs/lessons/chain-of-moves-stale-refs.md` (installed in 6c.2) —
  Multi-commit refactors must re-verify refs at every move; prior
  fixes don't inherit across commits in the same arc.
- `docs/lessons/predictive-scaffold-staleness.md` (installed in 6c.2) —
  Scaffolds predicting future file contents become stale the moment
  they're committed.
- `docs/lessons/grep-by-stem-not-spec-name.md` (installed in 6c.2) —
  Shipping-status audits grep behavior stems, not the literal function
  names specs propose.
- `docs/lessons/permission-gate-strategic-vs-hygienic.md` (installed in
  Commit 9) — Permission-gate visibility is load-bearing for strategic
  edits, satisfied by tracked diffs for hygienic edits.
- `docs/lessons/n-stage-gate-revision-handling.md` (installed in
  Commit 9) — Preflight revisions require a fresh delta-scoped CLI
  pre-flight check pass before Stage 2 greenlight; patch and greenlight
  never ship in the same message.
- `docs/lessons/not-in-git-tracked-not-existent.md` (installed in
  Commit 9) — Existence ≠ tracked; `git ls-files <path>` is the
  authoritative check; in-session drafted files are the common self-own.

CLAUDE.md additions:

- Standing Order: Save-Location Coordination (Commit 6e.3).
- Standing Order: Spec Lifecycle Discipline (Commit 6e.2).
- Iron-law relaxation: "NEVER touch human-authored files" → permission-gated edit pattern (Commit 6f).
- Standing Order: Sprint-Close Retrospective (Commit 9).
- Standing Order: N-Stage Gate Revision-Handling Doctrine (Commit 9).
- Lesson Integration Decision Tree — updated to include retrospectives (Commit 9).

`docs/templates/` additions:

- `docs/templates/preflight_drafting_checklist.md` (Commit 8) — 10-check
  PM self-audit run against every preflight before handoff.
- `docs/templates/preflight_template.md` (Commit 6d) — 8-section preflight
  scaffold for non-trivial commits.
- `docs/templates/defect_triage_template.md` (Commit 6d) — 8-section
  defect triage scaffold with diagnosis-before-fix discipline.
- `docs/templates/scoped_audit_template.md` (Commit 6d) — 6-pass scoped
  audit scaffold.
- `docs/templates/pm_cli_collaboration_workflow.md` (Commit 6d;
  N-stage gate language added in Commit 9).

`docs/retrospectives/` additions:

- `docs/retrospectives/template.md` (Commit 9) — Retrospective scaffold.
- `docs/retrospectives/beta-2.11.md` (Commit 9) — this file.

Tests:

- `tests/test_docs_index_consistency.py` (Commit 9) — 6 parity tests
  pinning the four-tier docs architecture.

## 6. Gotchas for Future Sprints

- **Retrospective discipline not yet habitual.** This is the first
  retrospective. Commit 9 installs the Standing Order that requires
  one per sprint, but the discipline itself is untested. Beta-2.12's
  close is the first real validation that retrospectives are
  happening without prompting.

- **Index-drift tests cover only tier README ↔ tier file parity.** They
  do not cover CLAUDE.md pointer table drift beyond the `docs/references/`
  row set. Future enhancement: expand the test suite to cover the
  full CLAUDE.md Dependency API References table.

- **Preflight-drafting checklist is run-manually.** No CI enforcement
  yet. If PM drafts a preflight skipping checks, no tool catches it —
  only the maintainer's review or CLI's pre-flight check. The checklist itself
  is an institutional habit, not a technical gate.

- **Two-stage → N-stage gate language rename incomplete in the PM's
  own auto-memory index text.** The `feedback_revision_requires_fresh_gate.md`
  memory uses N-stage language. The MEMORY.md index line mentions
  Stage 2. Acceptable (index is a pointer, not the canonical) but
  worth consolidating at next memory-consolidation pass.

- **`docs/retrospectives/` not yet indexed in CLAUDE.md Dependency API
  References pointer table until Commit 9 lands.** The pointer table
  row is part of this commit's scope, so this gotcha self-resolves
  on Commit 9 merge.

- **`docs/retrospectives/beta-2.11.md` placeholder not created.** The
  archive/sprints/ directory's README was edited in Commit 7 to remove
  the stale predictive-scaffold reference. No forward-looking beta-2.11
  sprint-close summary lives there — the retrospective at
  `docs/retrospectives/beta-2.11.md` serves that role instead. This is
  the correct outcome (retrospectives are the durable sprint-close
  record; archive/sprints/ holds superseded planning docs only) but
  warrants a cross-reference in the archive README. Future sprint may
  add one.

## 7. Sprint-Close Addendum (Commit 10, 2026-04-20)

Beta-2.11 closed with Commit 9 + Current State refresh on 2026-04-18. Two days later, during PM/CLI/the maintainer planning for beta-2.12's first commit (Flag #17 raw sqlite3.connect fix), a naming collision surfaced: the beta-2.12 preflight wanted to be `commit_1_flag17_raw_sqlite_preflight.md`, but beta-2.11's own `commit_1_sqlite3_dead_import_preflight.md` was still living in `docs/audits/`. The initial workaround was to prefix the 2.12 file as `commit_b212_1_*`. The maintainer caught the pattern-level miss: the entire point of beta-2.11 was doc architecture cleanup — the sprint's own per-commit audit docs should have been archived at close, not left polluting the active-preflights working directory.

Commit 10 is the corrective addendum. It:

- Created `docs/archive/audits/beta-2.11/` with a chronological tier-README.
- Moved all 21 beta-2.11 per-commit audit files (plus this Commit 10 preflight, self-archiving) into the new tier.
- Moved the one orphan beta-2.10 audit file (`inbound_exclusion_coverage_audit.md`) to `docs/archive/sprints/beta-2.10/` alongside its sibling `outbound_extraction_preflight.md`.
- Renamed `commit_b212_1_flag17_raw_sqlite_preflight.md` → `commit_1_flag17_raw_sqlite_preflight.md` and updated its internal refs to the archived paths.
- Updated 21 living-doc refs across 8 files (lessons, templates, FLAG_REGISTRY, active beta-2.12 preflight) to point at the archive locations. Historical archives (CHANGELOG, moving files' sibling cross-refs) were left stale by design per `docs/lessons/chain-of-moves-stale-refs.md`.
- **Installed CLAUDE.md Standing Order "Audit-Doc Archival at Sprint Close"** codifying the archival step as a mandatory part of sprint close going forward.

**Lesson:** The sprint-close checklist needs to include the archival step explicitly. Leaving it implicit in "wrap up sprint docs" let Commit 10's work slip past the gate. The Standing Order fixes this for future sprints; beta-2.11 itself becomes a worked example of the failure mode.

**Failure mode surfaced — checklist-implicit housekeeping:** High-salience sprint-close artifacts (CHANGELOG, retrospective, Current State table, version tag) crowded out low-salience artifacts (per-commit audit archival). The fix is explicit checklist enforcement via the new Standing Order — not reliance on the reviewer to remember. See the Standing Order in CLAUDE.md for the full rule.

**Placeholder backfills (two sites — scope explicit per CLI pre-flight check Flag F):**

1. **`§2 What Shipped` table, Commit 9 row (line 42):** backfill the Commit 9 hash placeholder with the actual hash.

2. **Metadata header `§` Commit range (line 5):** updated to end at Commit 9, noting that the Commit 10 sprint-close addendum extends the range (see §7). This handles both the placeholder and the fact that Commit 10 is the true final commit of beta-2.11, without introducing a new `<C10-hash>` placeholder that would itself need post-commit backfill.

**N-Stage Gate worked example — v1 → v2 → v3.** The Commit 10 preflight itself exercised the N-Stage Gate Revision-Handling Doctrine installed in Commit 9. Draft v1 passed PM's Stage 1 after the maintainer's §10 ratification. CLI's Stage 1.5 pre-flight check surfaced 6 flags (1 blocking, 3 hygiene, 2 PM-judgment). PM's v2 patch addressed all 6. CLI's v2 delta-re-check surfaced 3 new flags (1 blocking — an execution-level contradiction between §1.5 item 2's withdrawal and §4 Phase B item 8's instruction, 2 non-blocking hygiene). PM's v3 patch closed the contradiction and corrected the two hygiene items. CLI's v3 delta-check was clean; the maintainer greenlit Stage 2. The gate caught a real execution-time instruction bug (CLI literally following §4 Phase B v2 would have made the withdrawn line-229 edit) that would have silently diverged from the agreed behavior. Retaining this as the first worked example of the doctrine in practice.

---

## Provenance

This retrospective was written by PM Claude during beta-2.11 Commit 9
drafting. The maintainer reviewed and approved before the commit landed. First
use of the retrospective template at `docs/retrospectives/template.md`
(also installed this commit). All patterns it references are canonized
in `docs/lessons/` or `CLAUDE.md` Standing Orders as of this commit.
