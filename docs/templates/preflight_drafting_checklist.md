# Preflight-Drafting Checklist

**Purpose:** PM-side self-check run against every preflight before it reaches the maintainer. Catches systematic drafting misses that would otherwise force CLI to improvise mid-execution or force the maintainer to catch the issue on review.

**When to run:** After the preflight is drafted but before presenting it to the maintainer. 5-10 minutes. Each check has a concrete action — run through all ten before sending.

**Mental model:** This is the mirror image of CLI's Pre-Fix Investigation Protocol in CLAUDE.md. CLI's protocol catches root-cause drift before implementation. This checklist catches drafting drift before handoff.

---

## Check 1 — Not-in-git verification (tracked status, not existence)

**The check:** For every file listed in §2 "Signature Proposal," §5 "Version Bumps + Test Plan," or any `git mv`/`git add` prescription, verify the file is actually **tracked** in git — not merely existent on disk.

**What it prevents:** Preflight prescribes a git operation that will fail because the target is not-in-git. This has two root-cause variants that share the same recovery pattern:

- **Gitignored** — explicit rule in `.gitignore` keeps the file out of git. Detected by `git check-ignore <path>`.
- **Untracked-but-existing** — file was created and never `git add`'d (common for in-session drafted files). Detected by `git ls-files <path>` returning empty.

Both variants fail `git mv` with `fatal: not under version control`. Both require `mv + git add` recovery. See `docs/lessons/not-in-git-tracked-not-existent.md` for the canonized pattern.

**How to run:** `git ls-files <path>` returns the path if tracked, empty if not — authoritative. Also useful: `git check-ignore <path>` distinguishes gitignored from untracked; `git status <path>` shows untracked files explicitly. The fastest draft-time habit is to `git ls-files` every path in any `git mv` prescription.

**Especially check in-session drafted files.** A file you created mid-conversation is not tracked until `git add` runs. Path existence (confirmed by `ls` or `cat`) is not evidence of tracked status. This is the most common self-own — "I just made this file, of course it's tracked." Run `git ls-files` anyway.

**Fix pattern if check fails:** For a move, use `mv <source> <dest>` followed by `git add <dest>`; note that history preservation is forfeit (neither gitignored nor untracked sources have meaningful pre-move history). For a stage, pair the gitignored file with its tracked template (e.g., `config.example.py` for `config.py`); stage the template, apply the same edit to the runtime file on-disk; call out the dual application explicitly in the preflight.

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

**Plan approval ≠ execution approval.** This check runs during preflight *drafting*, before the maintainer sees the document. The maintainer's subsequent review produces Stage 1 (plan approval) greenlight, not Stage 2 (execution approval) greenlight. Stage 2 opens only after CLI runs the pre-flight check pass and reports back clean — see `docs/templates/pm_cli_collaboration_workflow.md` §5.2 and the N-Stage Gate Revision-Handling Standing Order in CLAUDE.md for the full protocol.

**The check:** Does this preflight touch *strategic* files — files that encode decisions about direction, priority, or rules? If yes, has the preflight explicitly stated "PM proposes; the maintainer greenlights; CLI executes" in §1?

**The principle — strategic vs. hygienic.** The permission-gated-edit pattern (per `user_greenlight_pattern.md`) is visibility, not prohibition. Visibility is satisfied for *hygienic* touches by the git-tracked diff the maintainer reviews before merging to main. Visibility is satisfied for *strategic* touches only if the maintainer sees the change at preflight-draft time, because they haven't yet weighed in on the strategic choice. Mis-classifying hygienic as strategic creates friction without safety benefit; mis-classifying strategic as hygienic hides decisions.

**Strategic (in scope — needs §1 greenlight line):**
- `CLAUDE.md` — new Standing Orders, iron laws, pointer-table changes, policy edits
- `ROADMAP_TODO.md` — priority shifts, new roadmap items, deferred-item reshuffling
- `config.py` and `config.example.py` — `__branch__` and any non-machine-specific edit **other than `__version__` bumps** (see Hygienic list; `__version__` bumps are autonomous engineering mechanics per CLAUDE.md Standing Orders — Decision Routing)
- User-facing docs — `PROJECT_CONTEXT.md`, `User_Guide.md`, `Walkthrough.md`, `Technical Overview.md` body rewrites (not trivial typo fixes)
- `docs/lessons/` additions — canonizing a lesson is a strategic judgment
- `docs/templates/` additions — template creation is a strategic decision
- `docs/references/` additions — new dependency reference is a strategic scope decision
- `.gitignore`, top-level README — repo-level policy

**Hygienic (out of scope — CLI maintains autonomously under existing Standing Orders):**
- `.claude/memory/MEMORY.md` refresh at sprint close — Context Maintenance Standing Order authorizes this
- `CHANGELOG.md` entries for sprint work — Version Tracking rules require this
- Per-file version header updates (`last_modified`, `version`, `project_ver`, `last_commit: pending`) — Version Tracking rules require this for every touched file
- `config.py __version__` bumps — PM/CLI-autonomous engineering mechanics per CLAUDE.md Standing Orders — Decision Routing (visibility via landing summary + diff); execute and report, do not propose-and-wait
- Spec archival moves (`docs/specs/` → `docs/archive/specs/`) — Spec Lifecycle Discipline requires this at sprint close
- `DEPENDENCY_MAP.md` audit-date refreshes when touched by in-scope sprint work
- `docs/lessons/README.md`, `docs/templates/README.md`, `docs/references/README.md` index updates when the underlying tier got a new entry (because the addition was already greenlit)

**How to run:** For each file in the preflight's scope, classify it against the two lists above. Any match on the strategic list triggers a greenlight requirement. If a file fits neither list, default to strategic and ask — it's a new category that should be explicitly classified.

**Fix pattern if check fails:** Add "Strategic files touched: [list]. Permission-gate posture: PM proposes + the maintainer greenlights + CLI executes." to §1. Hygienic-only touches do not need this line (they're authorized by existing Standing Orders).

**Why this precision matters:** The greenlight pattern exists so the maintainer isn't surprised by what lands, not so every edit gets reviewed in isolation. Treating routine memory refresh or CHANGELOG entries as strategic would create a turn-per-sprint back-and-forth for zero safety benefit. Treating a new Standing Order as hygienic would hide a decision. The scope split above is the line where visibility is load-bearing.

---

## Check 11 — Grep-count cross-verification

**The check:** Every count claim in the preflight — N occurrences, M sites, K hit-lines, "X references across Y files" — is backed by a grep command and a current result. Counts that recur across multiple sections are consistent. Inventory sweeps used loose patterns, not over-strict word-boundary regexes.

**What it prevents:** Wrong-granularity counts (per-row vs. per-call; per-token vs. per-line), stale count rot across a multi-section document after a patch, and incomplete inventories from over-strict regex word boundaries. Five empirical sprint examples are in `docs/lessons/grep-count-discipline.md`.

**How to run:**
- For every count claim, capture the grep command and result inline. `grep -cE <pattern>` is per-line and unambiguous. `grep -lE` is per-file.
- After patching any count, run `grep -n <old-value> <preflight-path>` and verify no sibling occurrences carry the stale value.
- For per-file distributions, sum-check the per-file totals against the project total. Arithmetic catches both granularity confusion and missing-file errors.
- For inventory sweeps, prefer loose patterns first; tighten only after the loose sweep is complete.

**Fix pattern if check fails:** Patch the offending count claim, then sweep the document for sibling occurrences. If after sweep more than one count claim was wrong, the preflight needs a more careful pass — count discipline failures cluster.

**Why this matters:** PM-side count discipline is the second-opinion model's blind spot. Every miss that reaches CLI costs a v1→v2 pinball round; sometimes a stale count reaches a court-facing artifact. The full canon and sprint examples live in `docs/lessons/grep-count-discipline.md`.

## Check 12 — Broaden-without-reinventory re-scan

If your preflight broadens a pattern, scope, or fix scope, paste the
output of re-grepping the broadened pattern against the patch itself.
The patch closing a defect class frequently commits the same class
elsewhere in its fix (meta-recursive defect — 6+ recurrences in
beta-2.14-2.15).

- Canonized in `docs/lessons/grep-count-discipline.md` after beta-2.15
  surfaced 6 recurrences across two preflight cycles.
- Pinned here per `docs/specs/library_self_correction_design.md` §3.4
  Standing Order C.

**Example:**
```
After patching `or bates_batch_text` in 3 sites, re-grep:
$ grep -n "bates_batch" pages/5_Production.py
[paste the output; verify no instance of the patched anti-pattern remains]
```

---

## Final check — "What would CLI catch?"

Before handoff, re-read the preflight one more time with the question: "If I were CLI executing this, what would I have to push back on?" If I can name anything, fix it in the preflight before the maintainer sees it. The goal is zero pushback from CLI on draft-class issues.

## When this checklist was installed

Originally installed beta-2.11 Commit 8 (Checks 1–10) (post-hoc AI-collaboration infrastructure). Spec that motivated the original 10 archived at `docs/archive/specs/preflight_drafting_checklist_spec.md`. Lessons that contributed to Checks 1–10: `feedback_gitignore_awareness_in_packets.md`, `feedback_cross_check_prior_arc_destinations.md`, `feedback_grep_by_stem_not_spec_name.md`, `feedback_timebox_introspection_phases.md` (all in PM auto-memory).

Check 11 (grep-count cross-verification) added beta-2.14 C6, canonizing 5 empirical defect-class observations from C7 (Pattern X audit), a rename sweep, and C5/Commit 10 (Flag #13 aborted-run UX). Full canon at `docs/lessons/grep-count-discipline.md`.
