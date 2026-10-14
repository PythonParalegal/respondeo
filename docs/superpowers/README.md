# docs/superpowers/ — Skill-Mandated Save Location

Files in `docs/superpowers/specs/` and `docs/superpowers/plans/` are written
by Claude Code Superpowers skills, which mandate this path:

- **`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`** — brainstorming
  skill design-doc output (see
  `~/.claude/plugins/cache/claude-plugins-official/superpowers/*/skills/brainstorming/SKILL.md`).
- **`docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`** — writing-plans
  skill plan output (see the equivalent `writing-plans/SKILL.md`).

These files are kept at the skill-mandated location rather than migrated to
`docs/specs/` (the canonical home for every other to-do blueprint) because
the skills reference them by this path in downstream prompts
(`subagent-driven-development`, `requesting-code-review`, etc.). Moving them
would break the skills' internal cross-references on future runs.

If a spec or plan in this directory refers to work that has shipped, archive
it under `docs/archive/superpowers/` — do not move it to `docs/archive/specs/`.
The archive tier mirrors the live tier.

See CLAUDE.md Standing Orders — Save-Location Coordination (added in
beta-2.11 Commit 6e.3) for the full convention.
