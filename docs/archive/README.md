# docs/archive — Forensic Preservation

Completed, shipped, or superseded documents are preserved here for
historical and forensic record. The archive is **never** loaded into
working context automatically; it exists so that later investigations
(git blame, audit prep, "how did we get here?" questions) have the source
material at hand.

## What belongs here

- Completed sprint docs (specs that shipped, sprint plans that ran).
- Superseded specs (v1 docs where a v2 has replaced them and is still
  active — v1 archived, v2 kept at its active location).
- One-shot prompts that already served their purpose but whose framing
  is worth preserving (often written as hand-offs to Claude Code).
- Completed migration plans (e.g., the M4 SQL migration plan, now that
  migration is complete).
- Old superpowers specs/plans that have been superseded or completed.

## What does NOT belong here

- Active specs awaiting implementation — those live in `docs/specs/`.
- Durable lessons extracted from completed work — those live in
  `docs/lessons/`. (Archiving the sprint doc does not itself preserve the
  lesson; extract it first, then archive the source.)
- Dependency API references — those live in `docs/references/`.
- Reusable templates distilled from completed one-shot docs — those live
  in `docs/templates/`.

## Subdirectory layout

- `sprints/` — completed sprint docs (e.g., `SPLIT_DOCUMENT_SPRINT.md`).
- `specs/` — completed or superseded specs (e.g., v1 branding spec,
  shipped Inbound Production spec).
- `prompts/` — one-shot prompts that already ran (bug repros, cowork
  handoff briefings, recon scripts).
- `m4/` — M4 SQL migration plans (migration complete; kept for forensic
  reference).
- `superpowers/specs/` and `superpowers/plans/` — older superpowers
  spec/plan files moved out of `docs/superpowers/`.

## Rules

1. **Preserve, do not delete.** Default behavior on a completed artifact
   is to archive, not delete. Deletion is reserved for stale + redundant
   content (the Lesson Integration Decision Tree in `CLAUDE.md` codifies
   the distinction).
2. **Extract the lesson before archiving.** If a file contains a durable
   lesson or a reusable pattern, extract it to `docs/lessons/` or
   `docs/templates/` first, then archive the source.
3. **Don't re-reference.** New specs and lessons should cite the live
   sources they depend on, not the archive. Archive references are
   acceptable for historical context ("this was superseded by X, see
   `docs/archive/specs/old-spec.md`") but should be rare.
4. **`_scratchpad/` promotion is one-way.** `_scratchpad/` is gitignored;
   moving a file from there into `docs/archive/` promotes it into the
   committed record. Human review the 6e diff before landing.

## Current archive contents

_This directory was created in beta-2.11 Commit 6b. Content migration
from project root, `.claude/plans/`, `docs/superpowers/`, and
`_scratchpad/` happens in Commit 6e. See preflight §4 for the complete
move list._

## See also

- `CLAUDE.md` — Lesson Integration Decision Tree Standing Order (step 5
  defines archive vs. delete).
- `CHANGELOG.md` — each archive move logs a DOCS entry pointing at the
  original location.
