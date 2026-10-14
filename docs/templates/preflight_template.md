# Preflight Template — Non-Trivial Commit

**Purpose:** Scaffold for a preflight that an executing session (CLI Claude)
reads before touching code. Fill in each section for the target commit;
leave sections that don't apply marked "N/A — <reason>" rather than deleting
them.

**When to reach for this template:**
- The commit touches more than one file or more than ~50 lines.
- The commit involves a refactor, a behavior change, or a schema migration.
- The commit's source plan was written more than one commit ago (line
  numbers drift).
- Any commit where the reviewer has asked for a review-and-proceed gate.

**When NOT to reach for this template:**
- One-line fixes with obvious scope (typo, single-import cleanup).
- Pure documentation edits inside one file.
- Commits where a lighter template (defect triage, scoped audit) fits
  better.

**Output produced:** a filled-in preflight file at
`docs/audits/commit_NN_<purpose>_preflight.md`, reviewed by the reviewer
before execution.

---

## §1 — Extraction Inventory

Inventory every piece of state the target touches. Missing a cross-reference
here is the failure mode that turns a "pure code motion" commit into a
regression.

### 1.1 Line range of the block being extracted

Table of regions: what moves, what stays, what is replaced. One row per
semantic region. Note explicitly when plan-cited line numbers predate
intervening commits — see §7 for the reconciliation pass.

### 1.2 Session state reads and writes inside the target range

Two tables (reads, writes). For each write, capture the line, the
expression, and the purpose (widget-default seed, handler-local flag,
persistent checkpoint, etc.). This inventory backs the "no transient writes
under early return" verdict in §3.

### 1.3 Widget keys inside the target range

List every `key=` parameter: line, key name, widget type. Cross-reference
surrounding modules' key-prefix conventions and flag any collision risk.

### 1.4 Local helper functions defined inside the target range

For each nested helper: line, name, scope, whether it moves with the
extraction or stays in place. Helpers referenced from elsewhere require a
separate decision.

### 1.5 Closure references — what the extracted code needs access to

Table of outer-scope names read: the name, definition site, and how access
is preserved (closure, parameter, context object). List writes to outer
scope separately; any outer-scope rebinding is a scope-expansion event.

### 1.6 Imports the target code needs

Two categories: top-level imports the range uses, and inline lazy imports
inside the range. Confirm all imports resolve at the new call site. Pure
extraction does not add imports.

---

## §2 — Signature Proposal

Fill in the four decisions below. Rename or skip for commits that are not
introducing a new function.

### 2.1 Parameters

Propose a parameter list with rationale. Default is zero parameters for a
paramless handler that relies on closure; justify any deviation. Consider
consistency with sibling helpers, testability, and drift risk.

### 2.2 Return type

Pure side-effect functions return `None`. Functions that compute a value
need the type named explicitly. Converted `st.stop()` → `return` sites
return without a value.

### 2.3 Location

Module scope vs. nested inside a `with` block vs. nested inside another
function. Location dictates which sibling helpers remain accessible via
closure. Hoisting costs cascade: moving one helper often requires moving
several.

### 2.4 Name justification

Propose a name. Note alternatives considered and rejected. The name should
capture the full scope of what the function does — a reader picking up the
name cold should not be surprised by the body.

---

## §3 — Verdict Backing

The three verdicts here are refactor-specific and may be renamed per commit.
Each needs a grep-backed finding, not an assertion.

### 3.1 Verdict 1 — Variable leak-out

Grep every name defined inside the extracted range against every region that
runs after the call site. Confirm no outer consumer reads a name local to
the extraction. State the grep scope (files, line ranges, identifier
patterns) so the reviewer can reproduce.

### 3.2 Verdict 2 — Session-state writes transient under early return

For each write inside the range and each early-return site, apply the
transient-write test: would skipping the write leave the system inconsistent,
or is it the intended control flow? Build a cluster matrix (form-rendering
seeds, prelude flags, completion flags) and map each cluster's behavior on
every early-return path. Also verify no DB connection, file handle, or lock
is left open on any early-return path.

### 3.3 Verdict 3 — Semantic equivalence of control-flow substitution

For each site where control flow changes (e.g., `st.stop()` → `return`,
`raise` → explicit signaling): state the handler's intent in one sentence,
describe the current behavior (often the defect), and explain why the
substitution is equivalent to the intent. Cross-cutting framework semantic
notes belong at the end of the section.

---

## §4 — Phase Plan

Default three phases (A/B/C). Simpler commits may collapse to 1–2 phases;
complex commits may extend to A/B/C/D. The discipline is isolation of risk:
pure code motion first, narrow behavior change second, structural behavior
change last.

### Phase A — Pure code motion (scaffolding)

Scope, expected behavior, and verification. Phase A must produce a
functionally identical program — any regression has one cause (extraction
mechanics) and is bisectable without ambiguity.

### Phase B — Narrow behavior change

Scope, expected behavior, and verification. Phase B isolates one category of
behavior change from the structural rewrite that follows.

### Phase C — Structural behavior change (the headline fix)

Scope, expected behavior, and verification. Phase C is where the commit's
stated thesis lands. Verification typically requires a live walkthrough of
the originally-reported defect, not just the unit test suite.

### Phase total table

Summary table: phase, LOC changed, risk class, verification surface.

---

## §5 — Version Bumps + Test Plan

### 5.1 Version bumps

For each modified file, state the file-level version bump per the CLAUDE.md
header rules: patch for behavior/logic changes, minor for new
functions/classes, none for comment-only changes. Project version
(`project_ver`) stays unless the reviewer is cutting a release.
`last_modified` = commit time. `last_commit` = `pending`.

### 5.2 Test plan

Three sub-components:

1. **Existing coverage audit** — which tests cover the target surface and
   must pass at each phase boundary.
2. **New tests proposed** — import-smoke tests, signature checks, pure-Python
   invariants that can be pinned without a running UI context.
3. **Manual verification protocol** — numbered steps, one scenario per
   number. Each step should fail independently so failures localize. For UI
   commits, name the test fixture explicitly.

Flag automated-coverage gaps explicitly. UI-integration gaps are candidates
for Playwright E2E, not pytest.

---

## §6 — Scope-Expansion Probe Responses

Each probe answers a "while I'm here, should I also fix X?" question. Apply
the three-criteria test from `docs/lessons/scope-expansion-probe.md`:
same root cause, same fix pattern, same hazard class. All three must hold
for bundling.

### Probe 6.1 — What does <adjacent code site> do?

Quote the code. State the trigger condition and effect.

### Probe 6.2 — Is the equivalent handling already in place elsewhere?

Cross-reference analogous patterns in sibling modules.

### Probe 6.3 — Failure mode if the adjacent code stays unchanged

Describe the real-world consequence — "user X cannot do Y," not "feels
redundant." Cosmetic failures rarely justify bundling; behavioral failures
strengthen the case.

### Probe 6.4 — Does any other module follow the adjacent pattern?

Grep sibling pages/modules. Note whether this module is the outlier
(bundling converges) or the template (bundling diverges).

### Probe 6.5 — Revised recommendation

Apply the three-criteria test explicitly. Recommend bundle, defer, or
roadmap-flag. State the cost of each option. Flag for reviewer judgment
when the call is close.

---

## §7 — Line-Number Drift Re-Verification

Mandatory whenever the source plan was written more than one commit ago.
Two-column table: plan reference vs. current line position, with a status
column.

| Plan reference | Plan line | Current line | Status |
|---|---|---|---|
| `<target_function>` | `<line_N>` | `<line_N'>` | Shifted +K |
| `<title_rename_target>` | `<line_M>` | — | Already done in Commit P |

Also verify plan-cited ranges: "current range: X'-Y', semantically the same
(<description>)." For any plan instruction fully stale (already landed),
mark it skipped with a pointer to the commit that completed it.

---

## §8 — Summary / Greenlight Posture

Close with a verdict matrix and the explicit handoff posture. This is the
PM → reviewer handoff point.

### §8.1 — PM Drafting-Checklist Ledger

Canonical location for the 10-item `preflight_drafting_checklist.md`
self-check ledger. One row per check; mark PASS / FAIL / N/A with a
one-line evidence note. A FAIL means the preflight is not yet ready for
handoff — fix before sending to the maintainer.

| # | Check | Result | Evidence / note |
|---|---|---|---|
| 1 | Not-in-git verification | PASS / FAIL / N/A | `git ls-files <path>` output |
| 2 | Scope-expansion probe enumeration | PASS / FAIL / N/A | §6 section present |
| 3 | Line-number drift capture | PASS / FAIL / N/A | §7 section present / anchor hash recorded |
| 4 | Prior-arc destination check | PASS / FAIL / N/A | grep output |
| 5 | Version-bump cascade identification | PASS / FAIL / N/A | §5.1 per-file list |
| 6 | Cross-module impact against DEPENDENCY_MAP | PASS / FAIL / N/A | map consulted |
| 7 | Grep-by-behavior-stem discipline | PASS / FAIL / N/A | audit section |
| 8 | Rollback plan | PASS / FAIL / N/A | §7 rollback steps |
| 9 | Test plan | PASS / FAIL / N/A | §5.2 test plan |
| 10 | Permission-gate visibility (strategic touches) | PASS / FAIL / N/A | strategic-file classification |
| 11 | Grep-count cross-verification | PASS / FAIL / N/A | grep commands + sum-check evidence |

### §8.2 — Verdict matrix

| Audit Item | Verdict | Backing section |
|---|---|---|
| Verdict 1 | ✅ / ❌ / N/A | §3.1 |
| Verdict 2 | ✅ / ❌ / N/A | §3.2 |
| Verdict 3 | ✅ / ❌ / N/A | §3.3 |

State open questions explicitly: name decisions, scope-expansion decisions,
any ambiguous plan instructions. Do not close these on the preflight's
authority alone.

End with the ratification gate:

> Ready for greenlight. Proceeding only after reviewer ratifies the
> verdicts, confirms open questions, and resolves any scope-expansion
> decision.

---

## See worked example

`docs/archive/sprints/beta-2.10/outbound_extraction_preflight.md` — the
originating source for this template. Commit 7 of beta-2.10 extracted the
outbound production body from `pages/5_Production.py` to replace three
`st.stop()` calls with `return` and fix a tab-blanking defect. The
preflight's 8-section structure is what this template generalizes.

## See also

- `docs/lessons/scope-expansion-probe.md` — the three-criteria test the §6
  probes apply.
- `docs/lessons/line-number-drift-reverification.md` — the rule behind §7.
- `docs/lessons/batch-commit-discipline.md` — the phase-plan sizing
  discipline behind §4.
- `docs/templates/pm_cli_collaboration_workflow.md` — the collaboration
  workflow this preflight is the PM → CLI handoff for.
