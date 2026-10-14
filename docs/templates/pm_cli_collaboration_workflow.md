# PM–CLI Collaboration Workflow — Standing Orders

**Status:** Durable workflow documentation. Author: claude-code (Cowork session, 2026-04-17). Lifecycle: promoted from `docs/audits/` to `docs/templates/` in beta-2.11 Commit 6d; indexed in `docs/templates/README.md` and cross-referenced from the CLAUDE.md Dependency API References table and the PM–CLI Collaboration Workflow Standing Order.

**Why this file exists:** The Respondeo project uses two complementary Claude sessions — a "PM Claude" (typically browser-based or Cowork, handles planning and specs) and "CLI Claude" (terminal, handles execution inside the project). Over the life of the project we evolved a specific collaboration workflow that produced reliable, reviewable, reversible commits. The workflow is load-bearing: it prevents scope creep, surfaces ambiguity before code is touched, and makes every commit independently revertable. The maintainer explicitly asked that this workflow be preserved as a first-class artifact so it persists across sprints and across Claude context windows.

---

## 1. Role Split

| Role | Session | Responsibilities |
|------|---------|------------------|
| **PM Claude** | Browser Claude (claude.ai) or Cowork | Investigates, designs, writes preflights. Produces the spec that CLI executes against. Does not touch project code directly except to read. Has access to scratchpad-style iteration without polluting the project working directory. |
| **CLI Claude** | Claude Code in the terminal | Reads the preflight, executes against it, reports status. Owns the actual file edits, git commits, test runs. Operates one commit at a time. Does not design — only executes. |
| **The maintainer (human)** | — | Provides original intent, resolves ambiguity that the Claudes surface, reviews preflights before CLI executes, green-lights each commit before the next starts. Final authority on scope. |

**Critical principle:** PM Claude and CLI Claude do not share memory. The preflight is the ONLY durable artifact that bridges them. If it isn't written down in the preflight, it doesn't exist.

---

## 2. Preflight Structure

Every non-trivial commit gets a preflight file at `docs/audits/commit_NN_<purpose>_preflight.md` before CLI touches code. The preflight has the following sections (some optional for simpler commits):

### 2.1 Mandatory sections

1. **Status / Sprint / Commit slot / Author** — front matter identifying the work.
2. **Purpose of this file** — explicit statement that the preflight is a fresh-context rescue document. Written so a compacted Claude can read it linearly and reconstitute the plan.
3. **Why this work is happening** — the business or architectural reason, connected to the maintainer's explicit intent. Not filler; this is what prevents scope drift when edge cases arise.
4. **Target state (axiom)** — the architectural thesis in prose before any diagrams. For a bug fix, this is the root cause stated as one sentence. For a feature, this is the invariant being added.
5. **Current state → target state mapping** — exhaustive, usually a table. Every file, column, or signature that changes is listed with before/after. If it isn't in the table, it isn't in scope.
6. **Commit-by-commit action plan** — if the work spans multiple commits (6b → 6c → 6d → 6e pattern), each commit gets its own sub-section with explicit actions, files touched, verification steps, and rollback instructions.
7. **Scope-creep guardrails** — explicit "we are NOT doing this in this sprint" list. Named commitment from CLI to flag-and-defer if tempted mid-execution.
8. **Verification plan** — exact grep commands, tests to run, or inspection steps that prove the work landed correctly.
9. **Rollback plan** — per-commit revert instructions. Safe rollback is a prerequisite for starting execution, not an afterthought.

### 2.2 Conditional sections (include when relevant)

10. **Exact replacement text** — when a preflight edits a Standing Order, MEMORY.md, or other persistent doc, include the exact target text verbatim. No paraphrase.
11. **Pointer reconciliation register** — when files move or rename, enumerate every doc that might reference the old path. "No stale arrows" is the standard.
12. **Lesson extraction list with sources** — when the work produces memorializable patterns, enumerate them with their source file so future-me can re-derive.
13. **Risk register** — known failure modes with mitigations. Residual risk documented, not hidden.
14. **Open questions for the maintainer** — ambiguity that blocks execution. Numbered. The maintainer answers inline or defers.
15. **Resolved questions** — populated as questions are answered. Captures the verdict AND the basis (grep output, test result, the maintainer's reply).

### 2.3 Self-containment rule

A preflight is complete when a fresh-context Claude can read it end-to-end and execute without asking clarifying questions. If CLI has to ask "what did the spec mean by X?" mid-execution, the preflight was incomplete.

---

## 3. Investigation Protocol (PM Claude's obligations before writing a preflight)

### 3.1 Recon before design

Before proposing any change, inventory what exists. Read-only audit, no writes. For a doc reorg: list every relevant file. For a bug fix: trace the data flow from origin to failure point. For a feature: identify every existing consumer of the data surfaces the feature touches.

### 3.2 Verify by inspection, not assumption

When the question is "is X shipped" or "does Y exist," grep the live code for distinctive markers. Read the file if the grep is ambiguous. Do not rely on documentation claims — documentation lags behind code. Examples from beta-2.11:
- "Is branding v2 shipped?" → grep for `inject_sidebar_branding` and `st.logo(`. 11 hits across home.py and pages. Shipped.
- "Is user preferences shipped?" → grep for `personalize_columns`, `get_user_pref`, `"Save as My Default"`. Zero hits. Not shipped.

### 3.3 Root cause before fix

Iron law: no fix without confirmed root cause. State the root cause as a single declarative sentence. If you cannot state it clearly, you have not found it yet — keep investigating.

### 3.4 Three-strike circuit breaker

If three successive fix attempts fail validation, STOP. Do not attempt a fourth. Report what was tried, what failed, what remains unknown. The maintainer reassesses the approach before execution continues.

### 3.5 Scope-expansion probe

When a related defect or improvement surfaces mid-investigation, bundling requires **all three** of:
- Same root cause
- Same fix pattern
- Same hazard class

Any mismatch means the adjacent work is a separate commit, filed as a new flag in `FLAG_REGISTRY.md` or a new preflight in `docs/audits/`. Do not expand scope silently.

---

## 4. Execution Protocol (CLI Claude's obligations when running a preflight)

### 4.1 Read the preflight end-to-end before touching anything

No partial reads. No "I'll skim it and start." If the preflight is 500 lines, read 500 lines. The preflight IS the spec.

### 4.2 One commit at a time

Multi-commit preflights (e.g. 6b → 6c → 6d → 6e) are executed sequentially with a reporting gate between each. Never chain commits without explicit human approval of the previous commit. "Proceed" must be an affirmative instruction, not an assumption.

### 4.3 Exactness over interpretation

When the preflight provides exact replacement text (Standing Orders, MEMORY.md content, Decision Tree wording), paste it verbatim. Do not rephrase, summarize, or "improve" it. The PM Claude and the maintainer agreed on the exact wording for a reason.

### 4.4 Scope-creep self-commitment

Before execution, CLI explicitly acknowledges the scope guardrails in the preflight. If during execution CLI notices an adjacent defect or improvement opportunity, it STOPS, writes the observation as an addendum to the preflight's open-questions section or as a new entry in `FLAG_REGISTRY.md`, and does not execute it in the current commit. This is the specific failure mode that justifies having a preflight in the first place.

### 4.5 Reconciliation pass

After any file moves, signature changes, or schema edits, grep the entire repo for references to the old form and update every hit. Commit does not land until the reconciliation register is walked and every arrow resolves.

### 4.6 Self-check before committing

Per existing CLAUDE.md rules: version header `last_modified` current, version bumped appropriately, `project_ver` matches `config.py`, `last_commit` says `pending`, CHANGELOG entry added. Run these checks explicitly, not implicitly.

### 4.7 Status report after each commit

CLI produces a brief status after each commit: what files changed, what tests passed, what was verified against the preflight's verification plan, what (if anything) deviated. The maintainer reads this. Only after the maintainer's affirmative "proceed" does CLI start the next commit.

---

## 5. Review-and-Proceed Protocol (the maintainer's gate)

### 5.1 Preflight review

The maintainer reads the preflight before CLI starts the first commit. This is
Stage 1 of the N-stage gate — **plan approval**, not execution
approval. Stage 1 confirms that the sprint's strategic choices are
aligned with control tower's direction. Options:
- **Plan greenlight (Stage 1):** the maintainer approves the strategic scope.
  CLI begins the pre-flight check pass (see §5.2).
- **Amendments:** the maintainer edits the preflight directly or asks PM Claude
  to revise. CLI waits. Every revision round restarts at §5.2 (new
  pre-flight check against the revised content) before Stage 2
  greenlight opens.
- **Deferral:** the maintainer defers the whole thing. Preflight stays in
  `docs/audits/` for future pickup.

### 5.2 Pre-flight check pass (CLI Claude's obligations between Stage 1 and Stage 2)

Between Stage 1 (plan approval) and Stage 2 (execution approval) of
the N-stage gate, CLI Claude runs a pre-flight check pass — a
systematic verification that the preflight's prescriptions will
execute cleanly. This is the "pilot walking around the aircraft before
engines start" step.

**Pre-flight check scope:**

1. **Branch state** — verify HEAD matches the preflight's anchor hash.
   Delta should be zero. If non-zero, report the delta.
2. **File existence** — verify every file the preflight references
   (by path) exists at the expected location. Gracefully report any
   missing files.
3. **Extraction dry-run** (for commits that extract content from one
   file to another) — simulate the extraction without writing; confirm
   the extracted content has the expected structural properties
   (heading counts, fence counts, marker presence).
4. **Prior-arc scan** — grep the repo for references to the files
   being moved/created; confirm no prior-arc commit already
   established a conflicting canonical destination.
5. **Scope-expansion second opinion** — read the preflight's scope
   and, independently of PM, identify any adjacent file/line/field
   that shares the preflight's root cause + fix pattern + hazard
   class. Flag candidates for PM to reclassify.
6. **Rollback check** — confirm the preflight's rollback plan is
   actually executable (e.g., `git revert HEAD` works for doc
   commits; schema migrations need reverse-migration verification).
7. **Grep-count predictions** — for every verification command in the
   preflight's §5 verification suite, predict the expected output
   given the current branch state + the preflight's prescribed
   operations. These predictions become the baseline CLI verifies
   against post-execution.

**Pre-flight check report format:** CLI writes the report to
`docs/audits/commit_N_<purpose>_check_v<N>.md` (persistent artifact)
AND posts it in the CLI tab for the maintainer to relay. See
`docs/roles/execution_cli.md` §Handoff protocol for the full skeleton —
findings grouped by severity (Blocking / Hygiene / PM-judgment),
grep-count predictions for §5 verification, and an overall posture
line. Sections may be brief ("Clean, no findings") or detailed
("Flagged: the spec's Check 1 enumerates `license.key` as gitignored
but it's not in .gitignore"). At sprint close, these check-report
files archive alongside preflights per the Audit-Doc Archival Standing
Order.

**The pre-flight check is NOT execution.** No files are modified, no
commits are written. CLI is verifying the preflight's correctness
against the execution environment before engines start.

**Lightweight preflights — which scope items apply.** The 7-item scope
above is calibrated for the 8-section preflight (code refactors,
schema migrations, behavior changes). For lightweight 3-section
preflights covering doc-only and tiny hygiene commits, several items
are legitimately N/A:

- **Item 3 (Extraction dry-run)** — N/A unless the lightweight
  preflight is moving content between files.
- **Item 6 (Rollback check)** — typically `git revert <SHA>` is
  sufficient for doc-only commits; explicit verification is N/A.

CLI marks these "N/A — doc-only" explicitly in the pre-flight check
report rather than skipping silently. Items 1 (branch state), 2 (file
existence), 4 (prior-arc scan), 5 (scope-expansion second opinion),
and 7 (grep-count predictions) remain load-bearing for every
preflight class.

### 5.3 Per-commit review

After each commit status report:
- **Green light:** the maintainer says "proceed" or equivalent. CLI starts the next commit.
- **Adjustment:** the maintainer flags an issue. CLI fixes in a follow-up commit, not by amending. (Per CLAUDE.md: NEVER `git commit --amend` after-the-fact fixes.)
- **Abort:** the maintainer calls a stop. CLI reverts the problem commit per the preflight's rollback plan.

### 5.4 Revision-handling protocol (the N-stage iteration)

When CLI's pre-flight check (§5.2) surfaces a finding that PM wants
to resolve via revision, the workflow is N-stage, not two-stage. Every
PM patch to the preflight is a new preflight; every revision adds a
gate rather than collapsing one.

**The flow:**

```
PM drafts preflight v1
  ↓
Stage 1: The maintainer plan-approval on v1
  ↓
Pre-flight check 1: CLI reads v1, runs checks, reports
  ↓
PM reviews CLI's report
  ↓
If CLI flags something and PM decides to patch:
  PM patches → preflight v2
    ↓
  PM announces "Stage 2 remains pending" and requests a delta-scoped re-check
    ↓
  Pre-flight check 2: CLI reads v2, runs delta-scoped checks, reports
    ↓
  PM reviews → repeat if needed (preflight v3, v4, ...)
  ↓
Stage 2: The maintainer issues execution greenlight in a separate message
  (only after latest CLI report is clean; PM does not issue Stage 2)
  ↓
CLI executes, runs §5 verification suite, reports post-execution
```

**Iron rule:** Patch and Stage 2 greenlight never ship in the same
message. If PM is tempted to bundle them ("the patch is small, the
predictions still hold, so we can skip re-check"), that temptation is
the tell, not a time-saver. The scenarios where the N-stage gate
matters most are precisely the ones where PM feels confident.

**Delta-check scope.** CLI does not re-run the full pre-flight check
pass on every patch. The delta-check is scoped to:

1. Structural verification on the patched content.
2. Scope-expansion second opinion on the new text.
3. Grep-count predictions affected by the patch.
4. Confirm the fix resolves the original flag.

Everything CLI already verified and PM did not touch stays verified.

**PM response skeleton** for sending a revised preflight to CLI:

```
Patch applied to <path> — [one-line description of change].

STAGE 2 (execution approval) REMAINS PENDING — the maintainer will issue separately
after your delta-check reports clean.

Please run a delta-scoped pre-flight check:
  1. [specific structural check the patch could affect]
  2. Scope-expansion second opinion on the revised text
  3. Re-predict grep counts if the patched content changes §5 expectations
  4. Confirm the fix resolves the original flag

Report back in this tab so the maintainer can relay to the PM tab; the maintainer's
Stage 2 greenlight depends on your clean report.
```

**Who issues Stage 2.** In the WARP two-tab model, the maintainer issues Stage 2
greenlight after reading CLI's clean pre-flight check report. PM does not
issue Stage 2 — PM's role on a revision is to send the patched preflight
back with "Stage 2 remains pending" and wait. This was a live contradiction
between earlier drafts of this workflow doc and the role definitions; the
role definitions (`docs/roles/pm_claude.md` and `docs/roles/execution_cli.md`)
are the authoritative source and this §5.4 now matches them.

**Origin:** This protocol was codified after beta-2.11 Commit 8, when
PM bundled a patch with Stage 2 greenlight in the same message. The maintainer
caught the pattern-level miss. Full context in
`docs/lessons/n-stage-gate-revision-handling.md`.

### 5.5 Sprint close review

After the last execution commit lands (before the documentation cascade and version tag), the maintainer reviews the sprint's commit history against the original preflight. Anything the preflight promised must have landed; anything that was deferred must be filed as a flag.

---

## 6. Recovery Protocols

### 6.1 Context compaction mid-arc

Claude sessions compact periodically. A commit-in-flight cannot assume its author will still be conscious when it finishes. Mitigation:
- All intent goes into the preflight. The preflight is on disk and survives compaction.
- MEMORY.md points at the active preflight.
- A compacted CLI Claude, on wake, reads CLAUDE.md → MEMORY.md → active preflight → current git status, and resumes.

### 6.2 Failed commit

If a commit fails a pre-commit hook or test, CLI does NOT amend. Per CLAUDE.md: fix the issue, re-stage, create a NEW commit. The failed commit never happened from git's perspective; `--amend` would operate on the previous commit.

### 6.3 Scope drift detection

If CLI finds itself editing a file not listed in the preflight's mapping table, STOP. This is the signal that scope has drifted. Options:
- Add the file to the mapping as an addendum (if it's a pure consequence of the original scope, e.g. an import statement that must be updated).
- Flag it and defer (if it's a new finding).
- Ask the maintainer (if ambiguous).

### 6.4 Diverging from the preflight

If during execution CLI concludes the preflight is wrong — wrong line numbers, wrong assumption, wrong root cause — it stops and reports. It does not silently "correct" the preflight and proceed. The preflight is a shared contract; CLI does not amend it unilaterally.

---

## 7. Key Phrases (load-bearing vocabulary)

These phrases have specific technical meaning in this workflow. Use them intentionally.

| Phrase | Meaning |
|--------|---------|
| **Preflight** | A `docs/audits/commit_NN_*_preflight.md` file with the structure in §2. Not a synonym for "plan" or "spec." |
| **Axiom** | The one-sentence architectural thesis that the preflight defends. Everything else in the preflight flows from the axiom. |
| **Iron law** | A rule that cannot be violated. Lives in CLAUDE.md. Examples: "audit logging is never-raise," "closed cases block all writes," "no fix without confirmed root cause." |
| **Green light** | The maintainer's explicit affirmative approval to proceed. Not an inference. |
| **Reconciliation pass** | Grepping the whole repo for references to moved/renamed artifacts and updating every hit. |
| **Scope-expansion probe** | The three-criteria test for whether adjacent work belongs in the current commit or a new one. |
| **Flag** | An entry in `FLAG_REGISTRY.md` capturing deferred work. A living TODO list scoped to future sprints. |
| **Status check** | CLI's brief post-commit report to the maintainer. Not a self-pat; it's the contractual handoff for the maintainer's review. |
| **Defensibility statement** | The courtroom-ready paragraph that accompanies any discovery-material decision. Not optional for production-affecting changes. |
| **Compaction-survival** | The design property that a preflight can be read by a fresh-context Claude and executed without clarification. |

---

## 8. Lifecycle — Keeping This Workflow Current

### 8.1 Per-sprint review

At sprint close (before the version tag), review this document against what actually happened. Questions:
- Did any commit skip the preflight? Why?
- Did CLI ever deviate from a preflight silently? What was the signal?
- Did the maintainer have to intervene mid-commit for a reason not covered here?
- Did any scope-expansion probe fail (i.e. work that should have been bundled got split, or vice versa)?

If the answer to any of these reveals a gap, update this document. File the update in the same commit as the sprint-close documentation cascade.

### 8.2 Decision Tree integration

This workflow is itself an instance of the Lesson Integration Decision Tree (CLAUDE.md Standing Orders). It is classified as **Tier 3 (on-read reference) / Template category**. It lives at `docs/templates/` after 6d.

### 8.3 When to deprecate a rule

A rule in this document should be removed or softened only when:
- The underlying constraint that motivated it has changed (e.g. a new tool makes the rule moot).
- Three or more sprints have passed without the rule triggering, AND no regression occurred that the rule would have caught.
- The maintainer and PM Claude explicitly agree.

Silent softening is forbidden. Any change to this document is itself a preflight-worthy commit.

---

## 9. Provenance

This document encapsulates the workflow that evolved across beta-2.6 through beta-2.11 of the Respondeo eDiscovery Platform. Specific patterns it preserves:

- The preflight-before-execution discipline from the M-4 SQL migration (Mar 2026).
- The "no fix without confirmed root cause" iron law from the Pre-Fix Investigation Protocol.
- The three-strike circuit breaker from the same.
- The Cross-Module Impact Audit Standing Order (sprint close).
- The `# db_manager: exempt (reason)` annotation pattern from M-4.
- The scope-expansion probe pattern from `docs/archive/sprints/beta-2.10/outbound_extraction_preflight.md`.
- The line-number drift re-verification pattern from the same.
- The defect-triage-without-fix format from `docs/archive/sprints/beta-2.10/sort_path_vulnerability_2026-04-17.md`.
- The scoped-audit 6-pass from the archived scoped pre-deployment audit prompt (not included in this tree; see `docs/templates/scoped_audit_template.md`).
- The master-preflight-with-§14 pattern from this sprint's sprint-close preflight.

The workflow did not exist in this form at project start. It was incrementally derived from the specific failure modes that bit the project (silent regressions from cross-module drift, scope-creep in bug fixes that introduced new bugs, context-compaction losing mid-session plans, CLI Claude guessing instead of verifying). Each rule here has a scar behind it.

---

**End of standing orders.** Next integration: 6c adds a terse pointer Standing Order to CLAUDE.md referencing this document. 6d promotes this file to `docs/templates/pm_cli_collaboration_workflow.md` and adds a row to `docs/templates/README.md`. 6e verifies all pointers resolve.
