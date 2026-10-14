# Premature Release Tag

## One-sentence summary

Cutting the version tag before the sprint-close addendum commit lands
produces a tag pointing at an intermediate sprint state, forcing either
a force-retag (safe only on solo/private repos) or a patch release (the
only option when the tag is already public).

## The pattern

Sprint-close work is often a sequence of commits, not a single commit:
retrospective, audit-doc archival, context maintenance (CLAUDE.md
Current State, CHANGELOG, user-facing docs, memory), any final
Standing Order installs. The tag cut must wait for ALL of these to
land on the sprint branch and merge to main. Cutting the tag earlier
— even on the commit that bumps `__version__` — produces a tag that
names a state older than the sprint's actual close.

The failure mode is cognitive: when `__version__` is bumped and the
primary sprint theme has visibly shipped, tagging feels natural. The
sprint-close housekeeping that follows feels like post-release cleanup
rather than part of the release. It isn't. If it lands on the sprint
branch, it's part of the sprint's definition, and the tag needs to
include it.

## Concrete example

Beta-2.11 v2.11.0 tag was cut at Commit 7 on 2026-04-18.
C7 was the sprint-close doc cascade commit that bumped `__version__`
from 2.9.0 → 2.11.0 and shipped the primary sprint theme (documentation
architecture reorganization). At that moment, tagging felt natural.

Subsequently on beta-2.11:
- Commit 8 — preflight-drafting checklist template.
- Commit 9 — sprint-close collaboration hardening.
- Current State table refresh (hygienic cleanup caught
  post-C9).
- Commit 10 — sprint-close addendum installing the
  Audit-Doc Archival Standing Order.

None of these commits were behavioral — all docs and tests. But the
sprint was not fully closed until C10. The v2.11.0 tag at C7 named a
state that did not include the sprint's own housekeeping.

Correction on 2026-04-20 required force-retagging `v2.11.0` from its
original tag object (pointing at C7) to a new tag object
(pointing at C10). The force-retag was safe only
because the Respondeo repo is completely private and has a single
maintainer — zero downstream consumers could have cloned or fetched
the premature tag in the 2-day window.

In a multi-consumer project, force-retagging would have been
impossible without breaking downstream refs. The only viable correction
path would have been cutting `v2.11.1` as a patch release at C10,
accepting that v2.11.0 permanently names an intermediate state.

## How to apply

**Sprint-close sequence (mandatory order):**

1. Write the retrospective (`docs/retrospectives/<branch>.md`).
2. Archive audit docs to `docs/archive/audits/<branch>/` and update
   living-doc refs per chain-of-moves discipline.
3. Context maintenance: refresh CLAUDE.md Current State table, update
   memory files, update user-facing docs (Walkthrough.md, Technical
   Overview.md, User_Guide.md, PROJECT_CONTEXT.md), add CHANGELOG
   entries.
4. Merge sprint branch to main: `git merge --ff-only <sprint-branch>`.
5. Cut the version tag on main at the ff-merge-final commit:
   `git tag -a v<X.Y.Z> -m "<message>"`.
6. Push main, then push tag: `git push origin main && git push origin v<X.Y.Z>`.

**Counter-temptation:** When `__version__` is bumped and the sprint's
primary theme has shipped, tagging immediately feels right. Resist.
The 5–10 minutes to verify all sprint-close commits have landed is
cheap; a public tag pointing at the wrong state is forever (or
requires cascading corrections).

**How to correct if you discover a tag was cut prematurely:**

Two paths, depending on consumer exposure:

1. **Solo / private repo, sole maintainer, verified zero downstream
   consumers:** Force-retag is acceptable. Re-annotate the tag locally,
   then force-push:
   ```bash
   git tag -f -a <tag> <new-commit> -m "<message>"
   git push --force-with-lease=refs/tags/<tag>:<old-tag-object-hash> origin <tag>
   ```
   Note: plain `--force-with-lease` bails on tags because git doesn't
   auto-create remote-tracking refs for tags; the explicit-value form
   `<ref>:<expected-hash>` anchors against what you know the remote was.
   Document the retag in the sprint retrospective as forensic record.

2. **Multi-consumer repo, public tag, or any uncertainty about downstream
   exposure:** Do NOT force-retag. Cut a patch release at the
   sprint-close-final commit (e.g., v2.11.0 → v2.11.1). Accept that the
   premature tag permanently names a mid-sprint state; the patch release
   captures the final close. Document in the retrospective so future
   archaeology can reconstruct the full sprint scope.

Never apply option 1 without explicitly verifying zero downstream
consumers. "I think no one has pulled it" is not verification.

## Why this is worth canonizing

The cognitive failure mode is strong: `__version__` bump feels like the
tag cut trigger, but it isn't — the sprint-close commits that follow
are also part of the sprint. The Audit-Doc Archival Standing Order
(installed in beta-2.11 C10) is the structural prompt that says "there
is more sprint-close work after the primary theme ships." Without that
Standing Order in place, there was nothing in CLAUDE.md to catch the
premature tag — which is exactly what happened on 2026-04-18.

This lesson complements the Standing Order: the Standing Order says
"archive audit docs at sprint close"; this lesson says "the tag cut
waits for the archival commit." They're two halves of the same
sprint-close discipline.

## See also

- `CLAUDE.md` Standing Order: Audit-Doc Archival at Sprint Close — the
  structural prompt this lesson complements. Includes the Tag-cut
  ordering subsection added alongside this lesson.
- The beta-2.11 C10 preflight, which installed the Audit-Doc Archival Standing
  Order.
- `docs/retrospectives/beta-2.11.md` §7 — sprint-close addendum story.
- `docs/lessons/chain-of-moves-stale-refs.md` — companion lesson on
  ref-update scope after file moves.
- `docs/lessons/n-stage-gate-revision-handling.md` — sibling lesson on
  PM–CLI revision discipline.
