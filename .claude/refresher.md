# Top recurring misses — refresh at every sprint-close

These are the failure modes that have recurred 3+ times across recent
sprints despite canonization. Keep them in active mind throughout this
session.

Maintained per CLAUDE.md Standing Order B. Cap: 5 slots. Empty slots
are fine — better than padded ones that dilute signal. See
`docs/discipline_graveyard.md` for promoted patterns.

---

## Slot 1 — Fix-the-prose, miss-the-code-block (post-patch grep on stems)

When patching a preflight revision (v→v+1), PM attention concentrates on prose-explanation layers and skips code-block instances of the old pattern. The patched artifact ends up internally inconsistent; CLI follows the (stale) code block.

**Mitigation:** post-patch grep on the OLD pattern's stems applied to the patch itself, BEFORE CLI handoff. Use `grep -ni` (case-insensitive) and, for count changes, grep the digit value in addition to the spelled word. Cost ~30 sec; alternative is a full N-Stage Gate revision cycle.

- **Recurrences:** beta-2.16 — C4 v2→v3 (Option flip missed CHANGELOG entry text), C6 v1→v2 (importlib→AST surgery missed scaffold + verification), C6 v4→v5 (8→9 test count missed Phase B scope line), **C9 v2→v3 (`nd_pending`→`nd_undecided` rename left ~14 stragglers across preflight/spec/plan — caught by PM's post-patch grep ritual before handoff)**.
- **Lesson:** `docs/lessons/fix-the-prose-miss-the-code-block.md`
- **Trigger:** `.claude/triggers.py` `preflight-patch-revision` entry (fires on `patch.*preflight` / `revis(e|ed|ion).*preflight` / `delta.?check` keywords)
- **Watch:** at C9 the mitigation WORKED — the post-patch grep ritual caught all ~14 stragglers before CLI handoff (trigger + ritual functioning as designed, not slipping through). No Check-13 promotion this sprint: the pattern still recurs in *authoring* but the *catch* is now reliable. Promote to a preflight-drafting-checklist Check 13 (Tier 3) only if a straggler ever slips PAST the ritual into a landed commit.

## Slot 2 — (vacated 2026-05-22)

Previous occupant: Broaden-without-reinventory. Promoted to
preflight-drafting-checklist Check 12. See graveyard entry 2026-05-22.

## Slot 3 — Scope-expansion probe before hotfix bundling

Two hotfixes touching the same code path require a probe: would
Hotfix A's change interact with Hotfix B's path? Textbook regression:
beta-2.13 Bates-batch (Hotfix 1's guard clause broke Hotfix 3's path).

- **Recurrences:** 1 textbook + multiple lesson-candidate occurrences
- **Lesson:** `feedback_commit_bundling_principle.md` +
  `feedback_no_loose_threads.md`

## Slot 4 — (vacated 2026-05-22)

Previous occupant: Manual pre-commit hygiene checks. Promoted to
`.claude/hooks/precommit_pii_guard.py`. See graveyard entry 2026-05-22.

## Slot 5 — Post-tag housekeeping slips

Sprint-close commits land before merge+tag, so Current State table /
CHANGELOG often need a small follow-up on next sprint's branch.

- **Recurrences:** beta-2.9, beta-2.10, beta-2.11, beta-2.13 — every other sprint
- **Lesson:** Implicit in `docs/lessons/premature-release-tag.md` and
  sprint-close Standing Order

---

## Sprint-close review log

- **beta-2.16 (2026-06-01).** Slot 1 recurred once (C9 rename, ritual caught it — no promotion). Slots 3 & 5: no recurrence this sprint (Slot 3 now a demote candidate if beta-2.17 is also clean). **Not added to a slot:** `partition-enumeration` (S-1c B-1+B-2) — first occurrence, below the 3+/2-sprint bar; landed a `.claude/triggers.py` `partition-enumeration` entry as the first-line catch + candidate-lesson bookmark. Promote to a slot / `docs/lessons/` on recurrence in beta-2.17. Cap respected (Slots 2 & 4 stay vacated).
