# Discipline Graveyard

Append-only log of patterns promoted from `.claude/refresher.md` to
mechanical enforcement (Tier 4 of the promotion ladder).

A pattern lands here when:
1. It recurred 3+ times across 2+ sprints, AND
2. It was promoted to a refresher.md slot, AND
3. The refresher slot did not prevent further recurrence, AND
4. It was promoted to either:
   - A pre-commit hook / CI test / PreToolUse blocking hook
     (binary-checkable cases), OR
   - A preflight-drafting-checklist hard-gate item
     (judgment-required cases).

This file is institutional memory. Reading it prevents re-canonization
or re-debate of solved problems.

See `docs/specs/library_self_correction_design.md` §4 for the full
promotion ladder.

---

## Format per entry

```
## <YYYY-MM-DD> — <pattern name>

- **Recurrence count at promotion:** N (across <sprints>)
- **Mechanism:** <pre-commit hook | CI test | PreToolUse block |
  preflight-drafting-checklist Item N>
- **File:** `<path to enforcement code or doc>`
- **Refresher slot vacated:** yes
- **Original lesson:** `docs/lessons/<name>.md` (still authoritative)
```

---

## Promoted patterns

## 2026-05-22 — Check 1 (Not-in-Git)

- **Recurrence count at promotion:** 5 (across beta-2.11 C8, beta-2.13
  Hotfix 4, beta-2.15 C8)
- **Mechanism:** Pre-commit hook
- **File:** `.claude/hooks/precommit_check1.py`
- **Refresher slot vacated:** yes (was slot 1)
- **Original lesson:** `docs/lessons/not-in-git-tracked-not-existent.md`
  (still authoritative)

## 2026-05-22 — Manual pre-commit hygiene checks (absorbed S-2)

- **Mechanism:** Pre-commit hook (secrets/PII guard over tracked tree)
- **File:** `.claude/hooks/precommit_pii_guard.py`
- **Refresher slot vacated:** yes (was slot 4)
- **Original lesson:** manual pre-commit checks don't scale; built-in
  rules plus an optional local deny-list.

## 2026-05-22 — Broaden-without-reinventory

- **Recurrence count at promotion:** 6+ (beta-2.14 C6/C7/C8 + beta-2.15
  across preflight cycles)
- **Mechanism:** Preflight-drafting-checklist Check 12 (judgment-required
  hard gate)
- **File:** `docs/templates/preflight_drafting_checklist.md`
- **Refresher slot vacated:** yes (was slot 2)
- **Original lesson:** `docs/lessons/grep-count-discipline.md` +
  `feedback_meta_recursive_defect.md` (still authoritative)
