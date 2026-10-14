# docs/roles/ — PM Claude + Execution CLI Role Definitions

Role definitions for the two-WARP-tab collaboration model used on the Respondeo eDiscovery project. Each role runs in a dedicated WARP tab with Claude Code; the maintainer bridges the two tabs by relaying artifacts (preflights) and findings (check reports) between them.

## What belongs here

- Role-definition files for each collaboration participant (PM Claude, Execution CLI, any future roles).
- Role definitions are strategic — they encode the collaboration model's guardrails. Changes belong in CLAUDE.md-tier permission-gated edits, not casual tweaks.

## What does NOT belong here

- Slash command entry points — those live at `.claude/commands/pm.md` and `.claude/commands/cli.md`. Those files invoke the role definitions here.
- Role-specific auto-memory — that lives per-tab under `~/.claude/projects/C--Users-<user>-Projects-ediscovery/memory/`.
- Collaboration workflow doctrine — that lives at `docs/templates/pm_cli_collaboration_workflow.md`. Role definitions describe *who does what*; the workflow doc describes *how the dance goes*.

## Current roles

- [`pm_claude.md`](pm_claude.md) — PM Claude role: preflight drafting, architectural review, planning. Activated via `/pm` in a fresh WARP tab. Write-scoped to `docs/audits/`, `docs/specs/`, `_scratchpad/`, and the memory directory.
- [`execution_cli.md`](execution_cli.md) — Execution CLI role: pre-flight checking, execution under Stage 2 greenlight, post-execution verification. Activated via `/cli` in a fresh WARP tab. Broad write access; destructive operations gated on explicit maintainer authorization.

## Why two tabs (not one session)

The PM ↔ CLI separation creates a genuine second opinion. Benefits come from independent cognitive contexts reasoning about the same artifact — not from any information asymmetry between the roles. Both tabs have the same repo access; what differs is the session history and the role-specific mandate.

Preserved benefits vs. single-session drafting:
- Forced handoffs via artifact passing (preflight → check report → patch → re-check).
- N-Stage Gate discipline (patch and Stage 2 greenlight never in the same message).
- Asymmetric incentives — PM optimizes for completeness, CLI optimizes for what's wrong.
- Independent evaluation of the same proposed change.

Prior to April 2026, PM Claude ran in Cowork (a sandboxed Claude interface) with limited filesystem observation. That caused persistent environmental-observation failures (hallucinated phantom directories, wrong path citations, unsourced counts). The WARP-tab migration preserves the two-session separation while giving PM the same filesystem tools CLI has — eliminating the "PM can't see current state" failure class.

## Session startup

Fresh WARP tab → `cd` into the repo → invoke the appropriate slash command:

- **PM tab:** type `/pm`. PM Claude loads `docs/roles/pm_claude.md`, reads project priors, confirms role activation.
- **CLI tab:** type `/cli`. Execution CLI loads `docs/roles/execution_cli.md`, reads project priors, confirms role activation.

The maintainer maintains both tabs open, pastes artifact pointers or findings between them as the workflow advances.

## Bridging conventions (maintainer-operated)

The two tabs don't share memory — the maintainer is the bridge. A reliable handoff requires operating the bridge with a predictable cadence. Conventions that have worked:

- **PM → CLI handoff (new preflight):** PM writes the preflight to `docs/audits/commit_N_<purpose>_preflight.md` and tells the maintainer "preflight ready at `<path>` for Stage 1 review." The maintainer reviews, issues Stage 1 (plan approval), then switches to the CLI tab and pastes: "Stage 1 approved; please run pre-flight check against `<path>`." CLI reads the file on disk — the preflight is the artifact, not the chat message.
- **CLI → PM handoff (check report):** CLI writes the check report to `docs/audits/commit_N_<purpose>_check_v<N>.md` (per `docs/roles/execution_cli.md` §Handoff protocol) and reports in the CLI tab. The maintainer switches to the PM tab and pastes either the report path or a summary — PM can read the file on disk for full detail.
- **PM → CLI handoff (revised preflight):** PM updates the preflight file in-place (incrementing v1 → v2 in §0.1 Revision History) and tells the maintainer "revised preflight at `<path>`; Stage 2 remains pending pending delta-check." The maintainer switches tabs, pastes the delta-check request to CLI.
- **Stage 2 greenlight:** the maintainer reads CLI's clean check report, then issues Stage 2 greenlight directly in the CLI tab — "Stage 2 approved. Proceed with execution." The N-Stage Gate doctrine requires this to be a separate message from any patch relay.

If the maintainer steps away mid-cycle, each tab's state is reconstructable from the files on disk. Check reports and preflights are durable artifacts precisely so the bridge can pause without losing work. Tab scrollback is not load-bearing; the filesystem is.

## See also

- `docs/templates/pm_cli_collaboration_workflow.md` — durable doc of the PM → CLI → maintainer collaboration model (role split, preflight structure, review gate, compaction-survival design).
- `docs/lessons/n-stage-gate-revision-handling.md` — revision discipline governing handoffs.
- `docs/lessons/preflight-proportionality.md` — template selection between 8-section and lightweight scaffolds.
- `CLAUDE.md` §Standing Orders — authoritative rules both roles must honor.
- `.claude/commands/pm.md`, `.claude/commands/cli.md` — the slash commands that activate each role.
