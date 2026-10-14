# Preflight-Drafting Checklist — Spec

**Date:** 2026-04-18
**Sprint:** beta-2.11 Commit 8 (post-hoc AI-collaboration infrastructure)
**Author:** PM Claude (Cowork)
**Status:** Draft — awaiting the maintainer's review + CLI execution
**Lifecycle:** After CLI lands the template at `docs/templates/preflight_drafting_checklist.md` in Commit 8, this spec archives to `docs/archive/specs/preflight_drafting_checklist_spec.md` per Spec Lifecycle Discipline.

---

## 1. Motivation

beta-2.11 Commit 7 ("documentation architecture reorganization") exposed a class of PM-side drafting misses that CLI had to catch during execution. The final one — proposing `config.py` as a `git add` staging target when the file is gitignored — was caught cleanly by CLI who substituted `config.example.py` (the tracked template) and extended scope to `__branch__` in the same pattern. The miss was small, the catch was quick, no harm was done.

The gap it revealed was bigger. PM Claude has the Lesson Integration Decision Tree (CLAUDE.md Standing Orders) for *sprint-close* lesson classification. PM Claude has the Pre-Fix Investigation Protocol (CLAUDE.md) for CLI's execution discipline. PM Claude does **not** have a "before I hand this preflight to the maintainer" self-check that catches systematic drafting misses in the packet itself.

This checklist fills that gap. It's mirror-image of the CLI-side pre-fix investigation protocol: ten checks PM runs against every preflight **before** the maintainer sees it, so drafting-class bugs don't reach review.

## 2. Why this is a spec, not a template directly

Two reasons worth preserving as forensic record:

1. **Spec Lifecycle Discipline symmetry.** Every other durable artifact in the project (features, refactors, standing orders) follows spec → implementation → archive. Infrastructure templates should follow the same lifecycle for consistency. Exceptions breed drift.

2. **Motivation preservation.** The template itself is a flat list of checks. The spec is where "why does check N exist?" lives. If a future session wants to know why the checklist requires running `git check-ignore` during packet draft, the answer is "beta-2.11 Commit 7 preflight §2.7 missed that `config.py` is gitignored, and we decided that class of miss should never ship to CLI again." That causal story is not in the template. It's here.

3. **Future editing discipline.** When a new lesson surfaces that should add a check to the template, the process is: (a) add to the template, (b) add a new spec in `docs/specs/` documenting the triggering incident, (c) archive the spec at sprint close. This keeps the template accurate without losing the context of why each check is there.

This is worth promoting to `docs/lessons/` as "Template creation follows Spec Lifecycle Discipline — archived spec is the forensic record of motivation." Candidate for inclusion in Commit 8 or 9.

## 3. Canonical template content

The content below is what CLI files to `docs/templates/preflight_drafting_checklist.md` in Commit 8. The spec's role ends when this content reaches the template; the spec then archives.

---

### BEGIN TEMPLATE CONTENT

```markdown
# Preflight-Drafting Checklist

**Purpose:** PM-side self-check run against every preflight before it reaches the maintainer. Catches systematic drafting misses that would otherwise force CLI to improvise mid-execution or force the maintainer to catch the issue on review.

**When to run:** After the preflight is drafted but before presenting it to the maintainer. 5-10 minutes. Each check has a concrete action — run through all ten before sending.

**Mental model:** This is the mirror image of CLI's Pre-Fix Investigation Protocol in CLAUDE.md. CLI's protocol catches root-cause drift before implementation. This checklist catches drafting drift before handoff.

---

## Check 1 — Gitignore verification

**The check:** For every file listed in §2 "Signature Proposal," §5 "Version Bumps + Test Plan," or any `git mv`/`git add` prescription, verify the file is actually tracked.

**What it prevents:** Preflight prescribes a git operation that will fail because the target is gitignored. See `docs/lessons/` for the `.gitignore` awareness pattern and the two canonical cases (gitignored sources need `mv + git add`; gitignored targets need tracked-template staging).

**How to run:** `git check-ignore <path>` returns exit 0 if path is ignored, 1 if not. This is the authoritative check — run it for any file you're uncertain about. As a memory aid, the gitignored paths that have actually appeared in packet prescriptions so far are `config.py` (tracked template: `config.example.py`) and `_scratchpad/` (no tracked analog). Sensitive config files like `auth_config.yaml` and `credentials.txt` are also gitignored and should never appear in a packet staging list — if they do, that's a deeper drafting error than gitignore-drift.

**Fix pattern if check fails:** Pair the gitignored file with its tracked template, stage the template, apply the same edit to the runtime file on-disk separately. Call out the dual application explicitly in the preflight — don't leave CLI to infer it.

## Check 2 — Scope-expansion probe enumeration

**The check:** For each target in the preflight's scope, run the three-criteria test: is there a nearby file/line/field that shares (a) same root cause, (b) same fix pattern, (c) same hazard class? If yes, either include it in scope or explicitly defer it with rationale.

**What it prevents:** CLI extends scope during execution (correctly, per the pattern) but I haven't enumerated it, so the expansion arrives unannounced. The maintainer can't review expansions that weren't in the preflight.

**How to run:** For each change target, grep for co-located similar patterns. Example: bumping `__version__` in `config.py`? Check for `__branch__` in the same file (same hazard class — config-level version metadata). Fixing a query in one module? Check for identical query patterns in adjacent modules.

**Fix pattern if check fails:** Add a §2.X "Scope-expansion probe findings" subsection enumerating the in-scope extensions and the explicitly-deferred candidates with rationale.

## Check 3 — Line-number drift capture

**The check:** If the preflight quotes code snippets with line numbers (for context or exact before/after blocks), note the exact commit hash or branch-state those line numbers were captured from.

**What it prevents:** Line numbers drift as soon as other commits land. A preflight written against `HEAD` at draft time may reference lines that no longer exist when CLI executes hours or days later.

**How to run:** At the top of the preflight, capture `git rev-parse HEAD` and `git branch --show-current`. Before CLI executes, verify the line numbers still match — or instruct CLI to re-locate by grep stem rather than line number if the branch has advanced.

**Fix pattern if check fails:** Prefer grep stems and anchoring text over line numbers in preflight prescriptions. Line numbers are snapshots; grep stems are durable.

## Check 4 — Prior-arc destination check

**The check:** If the preflight moves files in a multi-commit sprint arc, cross-check whether a prior commit in the same arc has already established a canonical destination for those files. Do not propose a fresh destination without verifying.

**What it prevents:** Splitting the sprint's planned destination from prior-commit cites, creating new dangling pointers while fixing one. See `feedback_cross_check_prior_arc_destinations.md` in auto-memory.

**How to run:** Before proposing a destination, grep the repo for references to the source filename AND the proposed destination path: `grep -rn <filename> docs/ .claude/`. Check `docs/audits/commit_*_execution_packet.md` files from earlier in the arc for destination planning. Check `docs/templates/` and `docs/lessons/` for "See worked example" cites that may assume a specific future path.

**Fix pattern if check fails:** Honor the prior-arc destination. If the prior destination is wrong, the right move is an explicit conversation with the maintainer to change it — not a silent override.

## Check 5 — Version-bump cascade identification

**The check:** If the preflight proposes a `__version__` bump in `config.py`/`config.example.py`, enumerate every `.py` file that gets touched in this sprint and will therefore need `project_ver` updated in its metadata header.

**What it prevents:** Mismatched `project_ver` fields across files — some files say `2.11.0`, others say `2.9.0`, nobody knows which is current. CLAUDE.md's Version Tracking rules require `project_ver` to match `config.py __version__` in every touched file.

**How to run:** Pre-sprint: list all files the preflight will modify. For each, the header's `project_ver` field needs to update to the bumped version. Include this as an explicit line-item in §5 "Version Bumps + Test Plan."

**Fix pattern if check fails:** Add a §5.X "Per-file `project_ver` update list" to the preflight explicitly enumerating which files get the bump.

## Check 6 — Cross-module impact check against DEPENDENCY_MAP

**The check:** For every database column, file path pattern, session state key, OpenSearch field, config value, or shared function signature that this preflight adds/modifies/removes, consult `DEPENDENCY_MAP.md` and identify every module that reads from or writes to it.

**What it prevents:** Sprint-introduced silent regressions. DEPENDENCY_MAP §7 "Known Regression Patterns" is the historical record of what happens when this check is skipped.

**How to run:** Mirror of CLAUDE.md's "Standing Orders — Post-Sprint Cross-Module Impact Audit," but at draft time instead of at sprint close. For each change target, look up in DEPENDENCY_MAP; if not listed, grep the codebase for the field/column/path/key.

**Fix pattern if check fails:** Enumerate affected consumers in the preflight's §6 "Scope-Expansion Probes" so CLI has the list at execution time, not just at impact-audit time.

## Check 7 — Grep-by-behavior-stem discipline

**The check:** If the preflight includes a shipping-status audit ("has spec X shipped?"), the grep targets must be behavior stems and semantic keywords, not the literal function names the spec originally proposed.

**What it prevents:** False-negative "UNSHIPPED" verdicts when the behavior actually shipped under an abbreviated or renamed identifier. See `feedback_grep_by_stem_not_spec_name.md` in auto-memory — `save_user_pref` (abbreviated) shipped, while the audit searched `save_user_preferences` (spec's proposed name) and reported UNSHIPPED.

**How to run:** Grep on behavior stems: the spec's verb/noun space rather than its proposed identifier. Expect abbreviation — codebases in this project tend to shorten `save_user_preferences` → `save_user_pref`, `get_configuration` → `get_config`, etc.

**Fix pattern if check fails:** Before concluding "unshipped," broaden the grep. Mark any tentative UNSHIPPED pre-findings in the preflight as "CLI to verify" so false negatives get caught.

## Check 8 — Rollback plan

**The check:** Every preflight has an explicit §7 "Rollback Plan" section stating how to undo this commit if it lands broken. Minimum: `git revert <SHA>` is enough for most, but any commit that touches migrations, schema, or file-system state outside git needs a specific rollback procedure.

**What it prevents:** "We landed it and now we can't roll back cleanly" situations. The Pre-Fix Investigation Protocol's three-strike circuit breaker assumes rollback is possible. If rollback requires non-trivial manual steps, those steps need to be in the preflight.

**How to run:** Ask: "If CLI lands this commit at 3am and it breaks production (or the pitch demo), what's the exact sequence to restore working state?" If the answer is "just `git revert`," say so. If not, spell out the steps.

**Fix pattern if check fails:** Add a §7 section with concrete steps. For schema migrations, include the reverse migration or a snapshot restore plan. For file-system state changes (move/delete operations), include the inverse operation.

## Check 9 — Test plan

**The check:** Every preflight has an explicit §5 "Test Plan" sub-section naming the pytest files to run, any manual verification steps, and a pass/fail threshold.

**What it prevents:** CLI lands the commit but hasn't been told what "verified" means. The commit sits in limbo because neither PM nor the maintainer knows what to smoke-test.

**How to run:** For each change target, identify the test that covers it. If no test exists and the change is behavioral, consider whether this sprint should add one. State the minimum acceptance threshold: "pytest non-e2e all passing, matching [prior-commit] baseline" or "import smoke + specific function call."

**Fix pattern if check fails:** Add a §5.X "Test Plan" enumeration. At minimum, "pytest tests/ --ignore=tests/e2e/" + import smoke + any module-specific manual check.

## Check 10 — Permission-gate visibility (strategic touches only)

**The check:** Does this preflight touch *strategic* files — files that encode decisions about direction, priority, or rules? If yes, has the preflight explicitly stated "PM proposes; the maintainer greenlights; CLI executes" in §1?

**The principle — strategic vs. hygienic.** The permission-gated-edit pattern (per `user_greenlight_pattern.md`) is visibility, not prohibition. Visibility is satisfied for *hygienic* touches by the git-tracked diff the maintainer reviews before merging to main. Visibility is satisfied for *strategic* touches only if the maintainer sees the change at preflight-draft time, because they haven't yet weighed in on the strategic choice. Mis-classifying hygienic as strategic creates friction without safety benefit; mis-classifying strategic as hygienic hides decisions.

**Strategic (in scope — needs §1 greenlight line):**
- `CLAUDE.md` — new Standing Orders, iron laws, pointer-table changes, policy edits
- `ROADMAP_TODO.md` — priority shifts, new roadmap items, deferred-item reshuffling
- `config.py` and `config.example.py` — `__version__`, `__branch__`, any non-machine-specific edit
- User-facing docs — `PROJECT_CONTEXT.md`, `User_Guide.md`, `Walkthrough.md`, `Technical Overview.md` body rewrites (not trivial typo fixes)
- `docs/lessons/` additions — canonizing a lesson is a strategic judgment
- `docs/templates/` additions — template creation is a strategic decision
- `docs/references/` additions — new dependency reference is a strategic scope decision
- `.gitignore`, top-level README — repo-level policy

**Hygienic (out of scope — CLI maintains autonomously under existing Standing Orders):**
- `.claude/memory/MEMORY.md` refresh at sprint close — Context Maintenance Standing Order authorizes this
- `CHANGELOG.md` entries for sprint work — Version Tracking rules require this
- Per-file version header updates (`last_modified`, `version`, `project_ver`, `last_commit: pending`) — Version Tracking rules require this for every touched file
- Spec archival moves (`docs/specs/` → `docs/archive/specs/`) — Spec Lifecycle Discipline requires this at sprint close
- `DEPENDENCY_MAP.md` audit-date refreshes when touched by in-scope sprint work
- `docs/lessons/README.md`, `docs/templates/README.md`, `docs/references/README.md` index updates when the underlying tier got a new entry (because the addition was already greenlit)

**How to run:** For each file in the preflight's scope, classify it against the two lists above. Any match on the strategic list triggers a greenlight requirement. If a file fits neither list, default to strategic and ask — it's a new category that should be explicitly classified.

**Fix pattern if check fails:** Add "Strategic files touched: [list]. Permission-gate posture: PM proposes + the maintainer greenlights + CLI executes." to §1. Hygienic-only touches do not need this line (they're authorized by existing Standing Orders).

**Why this precision matters:** The greenlight pattern exists so the maintainer isn't surprised by what lands, not so every edit gets reviewed in isolation. Treating routine memory refresh or CHANGELOG entries as strategic would create a turn-per-sprint back-and-forth for zero safety benefit. Treating a new Standing Order as hygienic would hide a decision. The scope split above is the line where visibility is load-bearing.

---

## Final check — "What would CLI catch?"

Before handoff, re-read the preflight one more time with the question: "If I were CLI executing this, what would I have to push back on?" If I can name anything, fix it in the preflight before the maintainer sees it. The goal is zero pushback from CLI on draft-class issues.

## When this checklist was installed

beta-2.11 Commit 8 (post-hoc AI-collaboration infrastructure). Spec that motivated it archived at `docs/archive/specs/preflight_drafting_checklist_spec.md`. Lessons that contributed: `feedback_gitignore_awareness_in_packets.md`, `feedback_cross_check_prior_arc_destinations.md`, `feedback_grep_by_stem_not_spec_name.md`, `feedback_timebox_introspection_phases.md` (all in PM auto-memory).
```

### END TEMPLATE CONTENT

---

## 4. Implementation notes for CLI

When Commit 8 preflight hands this to CLI, CLI's execution steps are:

1. **Create the template file** at `docs/templates/preflight_drafting_checklist.md` with exactly the content between BEGIN TEMPLATE CONTENT and END TEMPLATE CONTENT markers above. Strip the markdown code-fence wrapper — the template content is raw markdown, not nested markdown.

2. **Update `docs/templates/README.md`** to add the new template to the index. Follow the pattern of existing entries (preflight_template, defect_triage_template, scoped_audit_template, pm_cli_collaboration_workflow, and — if Commit 9 lands first — sprint_retrospective_template).

3. **Update CLAUDE.md's Dependency API References table** to add a row:
   ```
   | `docs/templates/preflight_drafting_checklist.md` | 10-check PM-side self-check run against every preflight before handoff to the maintainer. Mirror of CLI's Pre-Fix Investigation Protocol. | When drafting any preflight — run all 10 checks before presenting to the maintainer. |
   ```

4. **Add CHANGELOG entry** under the Commit 8 block:
   ```
   - NEW: docs/templates/preflight_drafting_checklist.md — 10-item PM-side self-check mirroring CLI's Pre-Fix Investigation Protocol.
   - DOCS: CLAUDE.md — added preflight_drafting_checklist row to Dependency API References table.
   ```

5. **Archive this spec** by moving `docs/archive/specs/preflight_drafting_checklist_spec.md` → `docs/archive/specs/preflight_drafting_checklist_spec.md` in the same commit, per Spec Lifecycle Discipline.

6. **Update `ROADMAP_TODO.md`** if this spec was bookmarked in an "Active Specs" section (verify during §2 cross-module impact check — it likely wasn't since this spec was drafted after 2.11 closed, but confirm).

## 5. Verification after Commit 8 lands

```bash
# Template exists and has the 10 checks
grep -c "^## Check [0-9]" docs/templates/preflight_drafting_checklist.md  # expect 10

# Template indexed
grep "preflight_drafting_checklist" docs/templates/README.md  # expect 1+ matches

# CLAUDE.md references it
grep "preflight_drafting_checklist" CLAUDE.md  # expect 1+ matches

# Spec archived, not duplicated
test -f docs/archive/specs/preflight_drafting_checklist_spec.md && \
  ! test -f docs/specs/preflight_drafting_checklist_spec.md && \
  echo "Spec correctly archived"

# CHANGELOG entry present
grep "preflight_drafting_checklist" CHANGELOG.md | head -3
```

## 6. Rollback plan

`git revert <commit-hash>` is sufficient. No schema changes, no file-system state outside git, no dependency updates. If the template content is wrong after review, fix-forward in a follow-up commit rather than revert.

## 7. Open questions — resolved

1. **Commit placement: Commit 8.** Resolved by the maintainer 2026-04-18 ("commit 8"). This spec's canonical content ships as part of Commit 8, the PM-drafted AI-collaboration infrastructure commit. Commit 9 remains focused on tests + retrospectives.

2. **CLI's `.claude/memory/MEMORY.md` in Check 10 scope: NO — out of scope.** Resolved by the maintainer 2026-04-18 with the strategic/hygienic split. CLI is trusted to maintain its own memory file autonomously under the Context Maintenance Standing Order. Visibility is satisfied by the git-tracked diff the maintainer reviews before merging to main. Requiring per-commit greenlight would create turn-per-sprint friction without safety benefit. Check 10's refined scope (above) reflects this — only strategic touches need greenlight.

3. **Meta-check placement: end of template.** Resolved by the maintainer 2026-04-18 ("It makes sense to put meta check at the end as a second-opinion after everything else is digested"). The meta-check stays at the end as a review-discipline gut-check after all ten concrete checks are run.

## 8. Principle worth promoting to `docs/lessons/`

The strategic/hygienic split in Check 10 is worth promoting to a standalone lesson file. Candidate title: `permission_gate_strategic_vs_hygienic.md`. Core claim: "the permission-gated-edit pattern (per greenlight memory) applies to strategic decisions, not hygienic maintenance — scoping the gate precisely is what keeps it from becoming friction." Anchor: beta-2.11 Commit 8 spec review, where the maintainer surfaced the concern that requiring greenlight on every memory refresh would over-micromanage CLI.

This lesson is a Commit 8 or Commit 9 candidate depending on scope appetite. Defaulting Commit 9 — the lesson is about visibility-vs-autonomy, which is a conceptual companion to the retrospectives infrastructure landing in Commit 9.
