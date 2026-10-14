# Preflight Template — Lightweight (Doc-Only / Tiny Hygiene)

**Purpose:** Scaffold for a preflight covering doc-only commits (lesson
canonization, Standing Order installs, catalogue updates) and tiny hygiene
commits (CHANGELOG corrections, placeholder backfills, typo fixes). Covers the
risk profile those commits actually carry — wrong content, missing
cross-references, broken ref-consistency — without the 8-section ceremony
calibrated for code refactors.

**When to reach for this template:**
- Doc-only commit — no `.py` file touched, no code logic changed.
- Tiny hygiene commit — ≤3 files, ≤20 LOC, same hazard class (staleness
  corrections, placeholder backfills, typo fixes).
- Commit that triggers the CLAUDE.md `>1 file` threshold but has no
  behavior-change risk.

**When to use the full 8-section template instead** (`docs/templates/preflight_template.md`):
- Any code logic change.
- Refactor, extraction, or code motion.
- Schema migration.
- Behavior change or bug fix.
- Any commit with >50 LOC of behavior-bearing content.

**When to skip the preflight entirely:** One-line fixes with obvious scope
(single-import cleanup, single-character typo) — CLAUDE.md already exempts
these.

**Output:** a filled-in preflight at
`docs/audits/commit_NN_<purpose>_preflight.md`, reviewed by the maintainer,
CLI-delta-checked, then executed under Stage 2 greenlight per N-Stage Gate
doctrine.

---

## §0 — Greenlight Gate

Standard N-Stage Gate posture per `docs/lessons/n-stage-gate-revision-handling.md`:

1. The maintainer's Stage 1 review of this preflight.
2. CLI pre-flight check, reports findings.
3. PM revises if needed (every revision triggers a fresh delta-scoped CLI re-check — patch and greenlight never ship in the same message).
4. The maintainer's Stage 2 greenlight in a separate message.
5. CLI executes, reports §3-rollback-ready post-execution verification.

Keep this §0 terse — the N-Stage Gate Standing Order in CLAUDE.md carries
the authoritative version. This section exists to anchor the specific
greenlight posture for this commit (who reviews, what the gate waits on).

---

## §1 — Content Plan

Enumerate every file touched, the action (CREATE / MODIFY), and the content
to add or change. For new files, include the full content or quote the
substantive section inline. For modifications, quote the before/after snippet
or describe the targeted string replace.

Table: `file | action | LOC delta | summary`.

For multi-commit preflights (two or more small related commits under one
preflight to reduce ceremony overhead), split §1 into Part A / Part B etc.

---

## §2 — Insertion Points

For each modified file, state the exact anchor: line number, surrounding
context, or unique string match. For creates, state the destination path and
confirm the parent directory exists.

Include execution notes CLI needs to execute without ambiguity:
- Use Edit (not Write) for modifications.
- Stop-and-escalate posture on unexpected repo state.
- Any ordering dependencies with other commits.
- Grep-count predictions that serve as post-execution verification signals.
  **Verify each prediction against current repo state at draft time** —
  a wrong prediction forces CLI either to flag it as a blocker or to
  follow it into a false-negative signal on verification.

---

## §3 — Rollback Plan

State whether `git revert <this-commit>` is sufficient. Note any downstream
dependencies that might complicate revert (other commits that reference this
commit's additions, interactions with adjacent commits in the same arc).

---

## Ratification Gate

> Ready for CLI pre-flight check. Proceeding to execution only after CLI
> reports clean AND the maintainer issues Stage 2 greenlight in a separate message
> per N-Stage Gate Standing Order.

---

## §Appendix A — PM Drafting-Checklist Ledger

Canonical location for the 10-item `preflight_drafting_checklist.md`
self-check ledger. Lightweight preflights may legitimately mark several
checks N/A (Checks 5 version-cascade and 8 rollback plan are often N/A
for doc-only commits), but each check must be recorded with an
evidence note. A FAIL means the preflight is not ready for handoff —
fix before sending to the maintainer.

| # | Check | Result | Evidence / note |
|---|---|---|---|
| 1 | Not-in-git verification | PASS / FAIL / N/A | `git ls-files <path>` output |
| 2 | Scope-expansion probe enumeration | PASS / FAIL / N/A | bundling candidates enumerated |
| 3 | Line-number drift capture | PASS / FAIL / N/A | anchor hash or grep stem noted |
| 4 | Prior-arc destination check | PASS / FAIL / N/A | grep output / N/A for non-moves |
| 5 | Version-bump cascade identification | PASS / FAIL / N/A | N/A common for doc-only |
| 6 | Cross-module impact against DEPENDENCY_MAP | PASS / FAIL / N/A | map consulted / N/A for doc-only |
| 7 | Grep-by-behavior-stem discipline | PASS / FAIL / N/A | audit stems, not spec names |
| 8 | Rollback plan | PASS / FAIL / N/A | `git revert` usually sufficient |
| 9 | Test plan | PASS / FAIL / N/A | grep-count predictions as verification |
| 10 | Permission-gate visibility (strategic touches) | PASS / FAIL / N/A | strategic-file classification in §0 |
| 11 | Grep-count cross-verification | PASS / FAIL / N/A | grep commands + sum-check evidence |

---

## See also

- `docs/templates/preflight_template.md` — 8-section template for code
  refactors, behavior changes, and schema migrations.
- `docs/templates/pm_cli_collaboration_workflow.md` — the PM→CLI→the maintainer
  collaboration model this preflight is the planning artifact for.
- `docs/lessons/preflight-proportionality.md` — the lesson this template
  operationalizes. Read for the decision criteria on which template to pick.
- `docs/lessons/n-stage-gate-revision-handling.md` — N-stage revision
  discipline (applies to both templates equally).
