# Fix the Prose, Miss the Code Block

## One-sentence summary

When patching a preflight revision, PM attention concentrates on prose-explanation layers (which feel substantive) and skips code-block layers (which feel mechanical), so old references survive in the artifact CLI actually executes against.

## The pattern

Preflight revisions (v1 → v2 → v3 ...) often broaden a pattern: rename a function, flip a chosen option, replace one mechanism with another. The patch updates the prose that *describes* the change (revision history, content plan tables, verdict backing) and feels complete. But the patch misses the code-block instances of the OLD pattern embedded elsewhere in the preflight — example code in test scaffolds, verification commands, sample fixtures.

The result: the preflight contains an internally inconsistent prescription. CLI's execution follows the code-block, which is now wrong; or CLI catches the inconsistency at delta-check, costing a v+1 patch round.

This is the same defect class as `docs/lessons/grep-count-discipline.md`'s "broaden-without-reinventory" Check 12, applied specifically to preflight revisions. The cognitive root cause is that the prose change feels load-bearing while the code-block change feels mechanical and repetitive — so the prose change gets attention and the code-block change gets assumed-done.

## Concrete example

Three in-sprint recurrences within beta-2.16 Phase 2-3 demonstrate the pattern:

1. **C4 v2 → v3 (S-3 preflight):** PM flipped Option A → Option C in the docstring's new_string after the maintainer's Stage-1 ratification. Updated the §2 Edit instruction. Missed that §1 Content Plan's CHANGELOG entry text still described "drop stale reference" (Option A). CLI corrected at execution time.

2. **C6 v1 → v2 (S-1a preflight):** PM replaced §1.6 prose describing importlib `exec_module` (broken) with AST-surgery. Missed that §5.2 test scaffold code block still imported and called `exec_module`. Also missed §4 Phase A verification command still using `exec_module(m)`. CLI's F-5 caught both at delta-check.

3. **C6 v4 → v5 (S-1a preflight):** PM updated test count 8 → 9 at §4 Phase B verification line. Missed §4 Phase B scope line still saying "Create test file with 8 tests." Caught by PM's own post-patch grep at v5 (after CLI bookmarked the recurrence pattern at v4 check).

## How to apply

**Mechanical mitigation: post-patch grep on stems applied to the patch itself.** After every preflight revision (v→v+1):

1. Identify the OLD pattern's stems — the substrings that were the *target* of the change. Examples:
   - Renamed function: grep for the old function name
   - Flipped option: grep for the discarded option's identifying phrases
   - Mechanism swap: grep for the old mechanism's keywords (importlib, exec_module, etc.)
   - Count change: grep for **both** the old digit value (e.g., `6`) **and** the spelled word (e.g., `six`)
2. Run `grep -niE "<stems>" preflight.md` against the patched preflight. **The `-i` flag is load-bearing** — without it, capitalized variants (header words "Six" vs body text "six", title-case option names, etc.) slip past the sweep. For count changes, run a SECOND grep on the digit (`grep -nE "\b6\b" preflight.md`) because counts get capitalized in headers, abbreviated in tables, and spelled out in prose — the digit is the cross-section invariant.
3. For each hit, classify: retrospective/explanatory (KEEP — revision history entries, "why we changed" prose) vs stale prescription (PATCH — code blocks, verification commands, scope statements).
4. Patch any stale prescriptions BEFORE handing off to CLI.

The case-insensitive + digit refinement comes from the recursive demonstration during this lesson's own canonization commit: a v2 post-patch grep with case-sensitive `"six strategic touches"` missed the capitalized header `"Six strategic touches"` at L6. The lesson got upgraded in the same v3 patch that fixed the straggler — empirically grounded in the canonization itself.

This ritual is judgment-required (which stems to grep, how to classify hits) but binary-checkable in execution (grep ran with zero stale prescriptions remaining). It mirrors the Check-12 broaden-without-reinventory discipline, applied specifically at the preflight-revision boundary.

**Watch for:**

- High-feeling substantive narrative changes that "obviously cover" a code-block swap — the narrative IS substantive but the code-block isn't auto-covered.
- Patches that change a parameter or option choice — the old value tends to be cited in multiple sections.
- Patches that swap an entire mechanism — example code in scaffold sections often retains the old API verbatim.

**When in doubt, run the grep.** Cost is ~30 seconds; cost of missing a stale prescription is a full N-Stage Gate revision cycle.

## See also

- `docs/lessons/grep-count-discipline.md` — Check 12 (broaden-without-reinventory) is the abstract version; this lesson is the preflight-revision-specific application.
- `.claude/refresher.md` Slot 1 (proposed in this commit) — real-time reminder for the post-patch grep ritual.
- `.claude/triggers.py` `preflight-patch-revision` entry (proposed in this commit) — keyword trigger on `patch.*preflight` / `revis(e|ed|ion).*preflight` / `delta.?check` terms.
- `~/.claude/.../memory/feedback_meta_recursive_defect.md` — the meta-pattern (fixes commit defects they're closing) above this specific lesson.
