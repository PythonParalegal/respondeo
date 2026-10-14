# Sprint Retrospective Template

> Replace this header with the sprint identifier (e.g., `# beta-2.12
> Retrospective`). Update every section below. Delete this blockquote.

**Sprint:** `beta-X.Y`
**Version tag cut:** `vX.Y.Z` (or "pending merge" if this retrospective
ships before tag)
**Commit range:** `<first-commit-sha>` through `<last-commit-sha>`
**Written:** `YYYY-MM-DD` by <author>
**Author:** PM Claude (Cowork session) or CLI Claude — name the role

---

## 1. Sprint Scope

One paragraph: what the sprint set out to do. The original intent, before
scope evolved during execution. Quote the ROADMAP_TODO line or original
preflight thesis if one exists.

## 2. What Shipped

Enumerate the commits with one-line summaries. Reference commit hashes.
Group related commits (e.g., "6b–6e: four-tier library scaffolding";
"7: sprint close"; "8: post-hoc checklist install").

| Commit | Hash | Summary |
|--------|------|---------|
| ... | ... | ... |

## 3. Goals vs. Outcomes

Did the sprint achieve its original intent? Three buckets:

- **Achieved as planned.** What landed cleanly.
- **Achieved with adjustment.** What shipped but with scope
  modifications, timing shifts, or approach changes. Explain the
  adjustment.
- **Deferred.** What was in original scope but didn't ship. Where does
  the deferred work live (ROADMAP_TODO entry, FLAG_REGISTRY entry,
  future preflight)?

## 4. Surprises and Learnings

The narrative section. What happened during the sprint that wasn't
anticipated at draft time? Include:

- Mid-sprint discoveries that changed the plan.
- Failure modes exposed (in the code, the architecture, the
  collaboration workflow).
- Patterns that started as ad-hoc fixes and got canonized.
- Questions the maintainer raised that redirected the work.
- Scope-expansion probes that fired; scope-expansion probes that
  should have fired and didn't.

Write in prose, not bullets. This section is what compacted future
sessions will read to understand "what was it like to be here."

## 5. Lessons Canonized

Enumerate the new `docs/lessons/` entries, `docs/templates/` entries,
`docs/references/` entries, or CLAUDE.md additions this sprint produced.
For each: one-line summary + pointer.

Format:

- `docs/lessons/<file>.md` — one-line summary.
- `CLAUDE.md` Standing Order: "<name>" — one-line summary.
- ... etc.

## 6. Gotchas for Future Sprints

Flags, caveats, known-incomplete work, or architectural choices made
under time pressure that a future sprint should revisit. Each item
becomes a candidate for FLAG_REGISTRY.md or ROADMAP_TODO.md.

Format:

- **Flag name (or short description):** What the gotcha is. Where it
  lives. Suggested future-sprint response.
- ... etc.

---

## Provenance

This retrospective was written by <PM|CLI> Claude during the sprint-close
documentation cascade for `beta-X.Y`. The maintainer reviewed and approved before
the commit landed.
