# Grep by Stem, Not by Spec Name

**One-sentence summary:** When auditing whether a spec has shipped, grep for behavior stems and keywords, not the literal function names the spec proposed — real code often uses abbreviated or renamed identifiers.

## The pattern

Specs are written before implementation. They propose function names that feel right at design time. By the time the code lands, the functions are often named differently: abbreviated (`save_user_preferences` → `save_user_pref`), renamed to fit a class's internal vocabulary, or split across multiple helpers with names the spec never anticipated.

A shipping-status audit that greps only for the spec's proposed names will false-negative: the behavior shipped, under a different identifier, and the audit concludes "unshipped." The spec stays in `docs/specs/` and the ROADMAP bookmark continues to list it as open work, when in fact part or all of the behavior has landed.

The false-negative is worse than a false-positive in this setup. A false-positive ("spec shipped" when it didn't) gets caught by the next CHANGELOG cross-check. A false-negative ("spec unshipped" when it did) leaves open-work claims on a registry that future sessions trust, causing scope confusion and sometimes duplicate implementation.

## Concrete example

In beta-2.11 6e.2 Phase 1, PM's pre-audit for `USER_PREFERENCES_SPEC.md` greped for literal patterns from the spec: `user preference`, `USER_PREFERENCES`, `user_preferences`. Zero hits. PM's tentative verdict: UNSHIPPED.

CLI's broader audit greped on behavior stems: `save_user`, `user_pref`, `get_user_pref`. Found `save_user_pref` at `auth_manager.py:392` — the primitive HAD shipped (for `last_case` persistence in `home.py`), just under an abbreviated name the spec didn't predict.

The fuller verdict was NUANCED: primitive shipped, Review-grid-column-persistence broader scope still unshipped. The abbreviated-primitive detail materially changed the spec's status triage. Had the audit relied on PM's pre-finding alone, the spec would have been archived as "fully unshipped" and the half-shipping would have been invisible to future sessions.

## How to apply

When drafting a shipping-status audit:

- Grep on behavior stems: the verb + partial noun (`save_user`, `load_config`, `log_audit`), not the full identifier. Abbreviation is the norm in this codebase, not the exception.
- Cross-reference CHANGELOG by subject matter, not just spec name. A spec titled "User Preferences" may have shipped under a CHANGELOG entry titled "Last-case persistence."
- If zero hits on proposed names, broaden the grep before concluding UNSHIPPED. Absence of the literal name is not absence of the behavior.
- In a packet's pre-audit section, mark any UNSHIPPED pre-findings as "tentative — CLI to verify." False negatives (spec shipped under different name) are worse than false positives (CLI asked to double-check).
- When a spec's behavior lands in an abbreviated form but the broader scope is unshipped, use the NUANCED status per `CLAUDE.md` Standing Order §Spec Lifecycle Discipline — don't archive, don't claim fully unshipped, record the partial-ship note at the top of the spec.

## See also

- **Related lessons:** `docs/lessons/line-number-drift-reverification.md` (similar discipline: re-verify evidence against live state, don't trust plan-time claims).
- **Source:** the USER_PREFERENCES_SPEC shipping audit (Phase 1), which produced the lesson.
