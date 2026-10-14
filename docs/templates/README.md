# docs/templates — Reusable Workflow Templates

Generalized scaffolds for recurring workflows. Each template captures a
pattern that has proven useful multiple times and strips out any
sprint-specific details so it can be re-instantiated on demand.

## What belongs here

- Generalized workflow scaffolds (preflight structure, defect-triage format,
  scoped audit pattern, etc.).
- Section-by-section frames that a future session can fill in for a new
  instance of the same kind of work.
- A short usage note at the top of each template explaining when to reach
  for it and what outputs it produces.

## What does NOT belong here

- Filled-in instances of a template (specific preflights) — those live in
  `docs/audits/` for active/upcoming commits or `docs/archive/` once done.
- Durable lessons / patterns / gotchas — those live in `docs/lessons/`.
- Dependency API references — those live in `docs/references/`.

## File conventions

- **Filename:** `<purpose>_template.md` (e.g., `preflight_template.md`).
- **Structure:**
  1. One-line purpose (what this template is for).
  2. When to reach for it (triggering conditions).
  3. The generalized section frame with brief explanatory comments for
     each section.
  4. A worked example or pointer to the source file the template was
     extracted from (in `docs/archive/` or the originating audit).

## How to add a template

1. Confirm the pattern has been used at least twice and would benefit
   from a reusable scaffold.
2. Extract the sections from the source files. Generalize the language
   (strip "this sprint"-isms, strip specific filenames/functions, keep
   the pattern).
3. Add a usage note at the top.
4. Add an entry to the index below.
5. Add a pointer row in `CLAUDE.md`'s Dependency API References table
   (the table is the canonical "where do I look for X" index).

## Current templates

- [preflight_template.md](preflight_template.md) — 8-section preflight
  scaffold for non-trivial commits (extraction inventory, signature
  proposal, verdict backing, phase plan, version bumps + test plan,
  scope-expansion probes, line-number drift re-verification,
  greenlight posture). Reach for this when a commit touches more than
  one file or more than ~50 lines, when a refactor or behavior change
  is in play, or when the source plan is more than one commit old.

- [preflight_lightweight.md](preflight_lightweight.md) — 3-section
  preflight scaffold (content plan / insertion points / rollback) for
  doc-only commits (lesson canonization, Standing Order installs,
  catalogue updates) and tiny hygiene commits (CHANGELOG corrections,
  placeholder backfills, typo fixes). See
  `docs/lessons/preflight-proportionality.md` for when to pick this
  vs. the 8-section template.

- [defect_triage_template.md](defect_triage_template.md) — 8-section
  defect triage scaffold (observed failure mode, failing code shape,
  upstream data flow, data-integrity question, candidate remediation
  paths, verified in advance, unblocker for current work, provenance).
  Reach for this when a defect discovered mid-sprint is scoped for a
  deferred fix commit.

- [scoped_audit_template.md](scoped_audit_template.md) — 6-pass audit
  scaffold (data integrity, status/enum propagation, feature
  verification, security/permission, session state, cross-module
  impact) with a read-only "do NOT fix" discipline. Reach for this
  when a bounded set of sprints needs a focused sweep before
  deployment.

- [pm_cli_collaboration_workflow.md](pm_cli_collaboration_workflow.md)
  — durable documentation of the two-session (PM Claude + CLI Claude +
  the maintainer) collaboration workflow: role split, preflight structure,
  investigation/execution protocols, review-and-proceed gate,
  compaction-survival design. Cross-referenced from CLAUDE.md Standing
  Orders.

- [preflight_drafting_checklist.md](preflight_drafting_checklist.md) —
  10-check PM-side self-check run against every preflight before
  handoff to the maintainer. Mirror of CLI's Pre-Fix Investigation Protocol.
  Catches drafting-class misses (gitignore collisions, scope-expansion
  gaps, line-number drift, prior-arc destinations, version-bump
  cascade, cross-module impact, grep-by-stem discipline, rollback
  plans, test plans, permission-gate visibility).

## See also

- `CLAUDE.md` — Lesson Integration Decision Tree Standing Order.
- `docs/lessons/` — durable project-level lessons (not workflow
  templates).
- `docs/audits/` — filled-in instances (active/upcoming preflights).
