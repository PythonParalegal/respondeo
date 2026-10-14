# Scoped Audit Template

**Purpose:** Structured audit of a bounded code surface — either a set of
recently-landed sprints, or a specific trust boundary about to be exercised
in production. Produces findings; does not produce fixes.

**When to reach for this template:**
- A set of sprints has landed since the last holistic audit and a
  deployment / firm-usage milestone is approaching.
- A specific code surface (production pipeline, ingestion pipeline,
  authentication, privilege log) needs a focused sweep.
- A post-incident review requires a narrow audit of the affected surface.

**When NOT to reach for this template:**
- Debugging a specific defect — use `defect_triage_template.md`.
- Planning a specific refactor — use `preflight_template.md`.
- Ad-hoc code review during normal development — the Standing Orders
  already cover cross-module impact checks.

**Output produced:** a findings-only report. Fixes are triaged and scheduled
as separate commits using the defect-triage or preflight templates.

**The defining discipline:** Audit reports findings, not fixes. This
reminder appears in every generated instance.

---

## Context

Why the audit is happening. Typically: a set of sprints has landed since
the last holistic audit, a deployment is imminent, or a specific trust
boundary needs verification before real use.

Include:
- The prior audit's date and pointer (e.g., `docs/HOLISTIC_AUDIT_REMEDIATION.md`).
- A table of sprints / commits that have landed since, with date, sprint
  name, and files touched.
- The real-world event that motivates the audit (deployment, firm usage,
  post-incident review).

---

## Scope

Three-category split. The out-of-scope list is load-bearing — it prevents
scope creep during the audit.

### In scope (primary targets)

The files / modules most directly affected by the recent changes. Name them
explicitly by path; note the specific change surface (new function, new
column, new permission, etc.).

### In scope (cross-module verification)

Every module that consumes data produced by the primary targets. For a new
`processing_status` value: every module that filters on status. For a new
column: every consumer identified in DEPENDENCY_MAP.md plus grep-verified
consumers not yet in the map.

### Out of scope

Explicit list. Include at least:
- Documentation files (`.md`) — these are not code.
- Findings already catalogued in prior audits — do not re-report unless a
  recent change made them materially worse.
- Files not touched since the prior audit's date.

---

## Audit Passes

Execute in order. For each finding, record: **file, line(s), severity
(Critical/High/Medium/Low), description, suggested fix.**

### Pass 1 — Data-integrity pass on the highest-risk new code

The feature most capable of corrupting or misfiling data. For a document-
producing feature (split, trim, extraction): transaction safety, column
propagation, status transitions, audit logging, migration correctness.

Per-function checklist items:
- Single-transaction boundary. What rolls back if step N fails?
- Cross-reference full table schema — are all relevant columns copied?
- Boundary logic (page-range overlap/gap, count clamps, empty-result
  handling).
- UI-state hygiene after the operation (stale selection, filter drift).

### Pass 2 — Status / enum / schema propagation

When a new status value or column is added, every consumer must handle it.
This pass catches silent regressions from new enum values that slip past
existing filters.

For each consumer module: verify the new value is handled correctly
(included / excluded / flagged, per the feature's semantics). Cover the
obvious callers (grids, production queries, analytics counts, processing
queues) and the less-obvious ones (dashboards, custodian tallies,
OpenSearch indexing).

### Pass 3 — Feature verification — depth check on the feature's own assertions

Verify the CHANGELOG's claims about what the feature does. Catches "we said
we excluded X but the query still includes X" failures.

For each claim: find the code that implements it, trace the code path the
claim depends on, confirm the claim holds in every path. Edge cases: retry
logic, native-only variants, stale-record re-processing paths.

### Pass 4 — Security / permission gates

New permissions added to `auth_manager.py`: is each one in
`ALL_PERMISSIONS`, in the role defaults, in `auth_config.yaml`? New UI
elements: do they check closed-case status before allowing writes? Do the
checks use the correct pattern (`db_manager.get_case_status()`, not
session-state cache)?

Cross-reference prior audit findings (e.g., C-5 case-switch state leak, H-1
closed-case gate inconsistency) — did the new features reintroduce
known-fixed patterns?

### Pass 5 — Session state + widget keys

List all new `key=` parameters added. Verify no collisions with existing
keys (prefix conventions, sibling-module keys).

Session-state cleanup: when the user navigates away from the new UI, is its
state cleared? Stale state from a prior operation on Document A should not
affect Document B.

Tab-index / dynamic-lookup changes: verify no reference elsewhere in the
file uses a numeric index that has since shifted.

### Pass 6 — Cross-module impact verification

Per CLAUDE.md Standing Orders — Post-Sprint Cross-Module Impact Audit.

- List every new cross-module data surface introduced since the prior
  audit (columns, status values, permissions, session-state keys, file
  path patterns).
- Verify DEPENDENCY_MAP.md is current for each.
- Verify schema migrations use the check-then-alter pattern and run
  cleanly on databases that have never seen the column.

---

## Output Format

Findings table:

```
| # | File | Line(s) | Severity | Pass | Finding | Suggested Fix |
|---|------|---------|----------|------|---------|---------------|
| 1 | ...  | ...     | Critical | 1    | ...     | ...           |
```

Followed by a summary:
- Total findings by severity.
- Whether any findings are **deployment blockers** (anything that would
  cause data corruption, wrong documents in productions, or security
  bypasses if a real firm uses this tomorrow).
- Recommended fix order.

**Do NOT fix anything.** This is a read-only audit. Report findings only.
Fixes will be prioritized and implemented in a separate sprint.

**Do NOT re-report** findings already catalogued in the prior audit unless
a new change made them materially worse.

---

## Standing Orders Reminder

Per CLAUDE.md, the Iron Law applies even to audits: **trace the data flow
before flagging something as a bug.** If intent is unclear, flag it as
"needs human decision" rather than "bug." The audit's job is to surface
findings, not to make scoping calls the reviewer needs to make.

---

## See worked example

This template was generalized from a scoped pre-deployment audit
prompt, authored against a set of sprints
that landed between the last holistic audit (2026-03-27) and an imminent
law-firm deployment. The 6-pass structure is what this template
generalizes.

## See also

- `CLAUDE.md` — Standing Orders: Pre-Fix Investigation Protocol and
  Post-Sprint Cross-Module Impact Audit (the two orders §6 and the
  Standing Orders Reminder cross-reference).
- `docs/lessons/defensibility-statement-practice.md` — the courtroom-ready
  paragraph practice that audits frequently surface gaps in.
- `docs/templates/defect_triage_template.md` — the next step for any
  finding severe enough to warrant its own triage.
