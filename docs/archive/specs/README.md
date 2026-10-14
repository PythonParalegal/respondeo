# docs/archive/specs — Completed and Superseded Specs

Feature specifications and design documents that have either shipped or
been superseded. Preserved for forensic reference.

## What belongs here

- Specs for features that have shipped in a completed sprint (verify by
  looking at CLAUDE.md Current State or the CHANGELOG before moving).
- v1 specs where a v2 (or later) is still active — move v1 here, keep the
  active version at its current location.
- Specs that were abandoned or superseded by a different approach.

## What does NOT belong here

- Specs still awaiting implementation. Those live in `docs/specs/`.
- Sprint-in-progress docs. Those live in `docs/archive/sprints/`
  (if complete) or remain in their working location if active.
- Durable lessons extracted from a spec. Those live in `docs/lessons/`.

## Verification rule

Before moving a spec here, confirm shipping status by **code evidence**,
not by memory:
- Grep for key functions / classes / UI strings the spec defined.
- Check `pages/` for a corresponding page file.
- Check the Current State table in CLAUDE.md and recent CHANGELOG
  entries.

If evidence is ambiguous, leave the spec at its working location and
flag it in the commit message — do not guess.

## Current contents

Contents populated from `docs/specs/` in Commit 6e.2 (shipping-status-
verified archive sweep). Shipping status for each archived spec is
recorded in the CHANGELOG entries for the sprint in which the work
landed — consult `CHANGELOG.md` for the per-file sprint date. The
spec file's own front matter ("Date:" / "Branch:" lines) names the
sprint it targeted.

## See also

- `docs/archive/README.md`
- `docs/specs/` — active specs awaiting implementation.
