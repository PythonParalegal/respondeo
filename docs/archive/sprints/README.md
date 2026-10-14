# docs/archive/sprints — Completed Sprint Documents

Sprint plans and in-progress sprint docs that ran to completion. Preserved
for forensic reference.

## What belongs here

- Named sprint documents that described a body of work and have since
  shipped (e.g., `SPLIT_DOCUMENT_SPRINT.md`, `TRIM_DOCUMENT_SPRINT.md`,
  `PRIVILEGE_DISPOSITION_SPRINT.md`).
- Mid-sprint planning docs that are no longer active.

## What does NOT belong here

- Specs for features (whether shipped or pending). Those live in
  `docs/archive/specs/` (when complete/superseded) or `docs/specs/`
  (when active).
- One-shot hand-off prompts. Those live in `docs/archive/prompts/`.
- Durable lessons extracted from the sprint. Those live in
  `docs/lessons/`.

## Current contents

- `beta-2.10/` — per-sprint subdirectory containing preflight source material promoted from `_scratchpad/` in Commit 6e.3: `outbound_extraction_preflight.md`, `sort_path_vulnerability_2026-04-17.md`. Plus a `README.md` describing the sprint's preflight provenance.

Future sprints may each get their own `docs/archive/sprints/<sprint-name>/` subdirectory when promoted preflight sources accumulate.

## Where shipped specs actually live

Sprint-named markdown files (`PRIVILEGE_DISPOSITION_SPRINT.md`, `SPLIT_DOCUMENT_SPRINT.md`, `TRIM_DOCUMENT_SPRINT.md`, `High_Tier_Remediation_Sprint.md`, `SPRINT_attachment_aware_threading.md`) were reclassified as shipped specs and moved to `docs/archive/specs/` in Commit 6e.2 — not here. The "SPRINT" suffix in their filenames predates the `docs/archive/specs/` vs `docs/archive/sprints/` distinction and refers to the work they described, not their archive tier.

## See also

- `docs/archive/README.md`
- `CHANGELOG.md` — historical sprint-landing entries.
