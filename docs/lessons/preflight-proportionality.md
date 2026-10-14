# Preflight Proportionality

## One-sentence summary

The 8-section preflight template is calibrated for commits where
execution-time bugs have material cost; doc-only and tiny hygiene commits
warrant a lightweight 3-section template instead, and applying the heavy
template to a light commit is a form of discipline inflation that costs
tokens without reducing risk.

## The pattern

CLAUDE.md's preflight trigger threshold is ">1 file, >50 lines, behavior
change, or bug fix." That threshold answers "when do I need a preflight?"
It does not answer "which template do I use?"

The 8-section preflight template at `docs/templates/preflight_template.md`
was designed for code refactors: extraction inventories, signature
proposals, verdict backing for session-state transience and control-flow
equivalence, phase plans with isolation-of-risk discipline. Its structure
is proportional to the hazard class of mid-sprint code refactors where
getting the extraction mechanics wrong produces subtle behavior
regressions that may not surface until production.

Doc-only commits (lesson canonization, catalogue updates, Standing Order
installs) and tiny hygiene commits (CHANGELOG header corrections,
`<pending>` placeholder backfills, typo fixes) carry none of those
hazards. Their risk profile is: wrong content, missing cross-references,
broken ref-consistency. The 3-section lightweight template (content plan
/ insertion points / rollback) covers these risks at a fraction of the
token cost.

Applying the 8-section template to a doc-only commit is a form of
discipline inflation: the ceremony grows proportional to the gate
discipline, not the underlying hazard. The N-Stage Gate still applies —
patch + greenlight never in the same message — but the preflight
artifact itself should match the commit shape.

## Concrete example

Beta-2.12 Commit 2 shipped the premature-release-tag lesson as a doc-only
commit (4 files, ~91 additions, zero code changes, one `git revert` to
undo). The preflight went through four iteration cycles (v1 → v4
patched; v5 proposed and refused). Finding D at v3 → v4 was a real
execution bug catch: the literal CHANGELOG markdown block in §7.4
carried a duplicate section header that would have failed Phase C.
But Findings E and F were cleanup-level convention-compliance rather
than execution bugs, and Finding F surfaced only under broader
scope-expansion review.

The chain worked — the gate caught a real bug. But the total token
spend across the four-iteration cycle was disproportionate to a
doc-only commit's risk surface. The maintainer flagged the imbalance mid-v5 at
~95% context budget: "The discipline we put in place is becoming a
massive token burn... we are on version 5 of a preflight just trying
to fix a relatively small pedantic issue."

The correct response was to accept v4 as-is, resolve Finding F with a
one-line execution note in the Stage 2 greenlight message, and
canonize this lesson for future commits.

## How to apply

**Which template to pick:**

1. **Code refactor, behavior change, bug fix, or schema migration with
   >1 file or >50 LOC:** Use `docs/templates/preflight_template.md`
   (8-section). The structure is calibrated for this hazard class.

2. **Doc-only commit (lesson canonization, Standing Order install,
   catalogue updates) OR tiny hygiene commit (CHANGELOG staleness fix,
   placeholder backfill, typo correction) even if >1 file:** Use
   `docs/templates/preflight_lightweight.md` (3-section: content plan
   / insertion points / rollback). The structure matches the hazard
   class.

3. **One-line fix with obvious scope (single-import cleanup,
   single-character typo):** No preflight — CLAUDE.md already exempts
   these.

**Signals that you picked the wrong template:**

- The 8-section template's §2 (Signature Proposal), §3 (Verdict
  Backing for session-state transience / control-flow equivalence),
  or §4 (Phase Plan with isolation-of-risk discipline) all resolve
  to "N/A — doc-only commit." When three of eight sections are N/A,
  the template is wrong-sized.
- The preflight iteration count exceeds the file count (v5 on a
  4-file commit, v3 on a 2-file commit).
- Findings in later iterations are purely convention-compliance or
  cross-section consistency rather than execution bugs.

**The N-Stage Gate still applies.** The lightweight template does not
bypass the PM → CLI → maintainer cycle. PM drafts, CLI runs pre-flight
check, the maintainer greenlights Stage 2. Every PM revision triggers a
delta-check. The lighter template reduces the surface CLI has to
check, which reduces iteration count in the typical case — but it
does not remove the gate.

**Escalation path if the wrong template was picked mid-arc:** Don't
migrate templates mid-commit. Finish the commit with the template you
started with (switching adds churn for no safety benefit), and apply
the proportionality principle to the next commit in the sprint. The
proportionality lesson is forward-looking.

## Why this is worth canonizing

The cognitive failure mode is strong in two directions. Underclaiming:
"this is just doc-only, skip the preflight entirely" is how silent
convention drift enters the repo. Overclaiming: "every commit deserves
the full 8-section template because discipline" is how token budgets
evaporate on pedantic iteration. The right answer is in the middle:
the gate is load-bearing, but the template should match the hazard.

Neither CLAUDE.md's trigger threshold nor the 8-section template
itself carry guidance on template selection. This lesson fills that
gap and is pointed-to from both artifacts.

## See also

- `docs/templates/preflight_lightweight.md` — the 3-section template
  this lesson operationalizes.
- `docs/templates/preflight_template.md` — the 8-section template
  for code refactors.
- `docs/templates/preflight_drafting_checklist.md` — PM-side
  self-check run against every preflight before handoff; applies
  equally to both templates.
- `docs/lessons/n-stage-gate-revision-handling.md` — sibling lesson
  on revision discipline; applies equally to both templates.
- `docs/lessons/premature-release-tag.md` — the beta-2.12 C2 lesson
  whose preflight arc surfaced this proportionality lesson.
