# Permission Gate — Strategic vs. Hygienic Edits

## One-sentence summary

Permission-gate visibility is load-bearing for *strategic* edits and is
satisfied by the tracked git diff for *hygienic* edits; mis-classifying
either way breaks the collaboration model.

## The pattern

The "NEVER touch X" language in CLAUDE.md is not a prohibition; it is a
visibility requirement. The gate exists so the maintainer isn't surprised by
what lands in files that encode direction, priority, or rules. Edits
fall into two categories:

**Strategic edits** encode decisions. CLAUDE.md Standing Orders,
`ROADMAP_TODO.md` priority shifts, `config.py` / `config.example.py`
non-machine-specific changes, user-facing documentation body rewrites,
new `docs/lessons/` entries, new `docs/templates/` entries, new
`docs/references/` entries, `.gitignore` changes, top-level README —
these all encode choices that the maintainer is presumed not to have weighed in
on yet. Visibility is satisfied only if the maintainer sees the proposed change
at preflight-draft time, because he hasn't already endorsed it. The
pattern is: PM proposes + the maintainer greenlights + CLI executes. Writing
the edit into the preflight's §1 "Strategic files touched" list
(required by Check 10 of the preflight-drafting checklist) operationalizes
this.

**Hygienic edits** carry out decisions that have already been endorsed.
`.claude/memory/MEMORY.md` sprint-close refreshes, `CHANGELOG.md`
entries for in-scope sprint work, per-file version header updates
(`last_modified`, `version`, `project_ver`, `last_commit: pending`),
spec archival moves (`docs/specs/` → `docs/archive/specs/`),
`DEPENDENCY_MAP.md` audit-date refreshes, index README updates
(`docs/lessons/README.md`, `docs/templates/README.md`, etc.) when the
underlying tier entry is already greenlit — these execute Standing
Orders the maintainer already approved. Visibility is satisfied by the tracked
git diff he reviews before merging to main. Requiring a separate
greenlight for each hygienic edit creates friction without safety
benefit.

## Concrete example

Beta-2.11 Commit 8 drafting surfaced this ambiguity. The initial Check
10 draft treated CLI's own `.claude/memory/MEMORY.md` as requiring
greenlight for every refresh. The maintainer pushed back: "memories should be
editable outside of me... if you think CLI can be trusted with his own
memories, or if we should have direct control? It increases labor to
micromanage his memories, and would be preferable if he revised
himself."

The split was introduced in response. CLI's memory refresh became
hygienic — authorized by the existing Context Maintenance Standing
Order. New CLAUDE.md Standing Orders and new lesson files stayed
strategic — greenlight required. The classification was formalized in
Check 10's body text and is now canonized here.

## How to apply

1. **When drafting a preflight**, classify each touched file against
   the two lists in the preflight-drafting checklist Check 10 preamble.
2. **If any file is strategic**, add "Strategic files touched: [list].
   Permission-gate posture: PM proposes + the maintainer greenlights + CLI
   executes." to §1 of the preflight. The maintainer's Stage 1 approval
   explicitly covers these edits.
3. **If all files are hygienic**, no greenlight line is required —
   existing Standing Orders authorize the edits, and visibility is
   satisfied by the tracked diff.
4. **If a file fits neither list**, default to strategic and raise it
   as an open question for the maintainer. The new category needs explicit
   classification before it ships.

## See also

- `docs/templates/preflight_drafting_checklist.md` Check 10 — the
  operational checklist item that enforces this split at draft time.
- `docs/templates/pm_cli_collaboration_workflow.md` §5 — the durable
  collaboration-model documentation.
- `CLAUDE.md` — the permission-gated edit pattern (relaxed from the
  original "NEVER touch human-authored files" iron law in beta-2.11
  Commit 6f) and the Standing Orders that authorize hygienic edits
  (Context Maintenance, Version Tracking, Spec Lifecycle Discipline).
- User auto-memory `user_greenlight_pattern.md` — the underlying
  "the gate is visibility, not prohibition" principle.
