# Grep-Count Discipline

## One-sentence summary

Count claims in preflights and audit docs — N occurrences, M sites, K
hit-lines — must be backed by a verified grep at draft time AND must
re-verify whenever a patch touches the document, because counting at
the wrong granularity, letting counts go stale across a multi-section
document, and using over-strict inventory regexes are recurring
defect classes that bypass the second-opinion gate.

## The pattern

PM-side preflight drafting accumulates count claims faster than they
get verified. A typical preflight has 6–12 numbered claims of the
form "N occurrences of X across Y files," "K sites," or "M references."
Each one is the kind of factoid where being almost-right looks
indistinguishable from being right — until CLI's pre-flight check
runs the actual grep and finds the count off by one or off by half.

Three failure modes recur:

**Wrong-granularity counts.** The prose claims "N call sites" but
the table below collapses N call sites into M rows under shared
classification. The prose total reports M (per-row) when readers
read it as N (per-call). Same defect class: claiming "K hit-lines"
on a multi-token regex (`patternA|patternB`) but counting per-token
matches (which can exceed hit-lines when one line contains both
tokens) instead of per-line.

**Stale count rot.** A count claim recurs across a multi-section
document. PM patches §3.1 to fix the count, but §6.4, §8.1, and the
revision history note still cite the old number. Cousin to
`docs/lessons/chain-of-moves-stale-refs.md` — same root cause
(refactor cleanup must touch all instances of the moved/changed
target), different surface (counts in prose instead of file paths
in cross-references). Surfaces especially after scope expansion:
when a patch widens scope from N files to N+K, every "NOT touched"
list, every Hygienic/Strategic classification table, and every
verification protocol that named the original N becomes stale.

**Incomplete inventory.** Over-strict regex patterns (especially
`\b` word boundaries) miss valid matches. `\bOLD_NAME\b` won't
match `OLD_NAME123` even though the name is present.
Inventory sweeps that need to enumerate ALL occurrences must use
loose patterns first and tighten only when verifying canonical
spellings, not when sweeping for completeness.

The fix in all three cases is the same shape: **don't trust the count
without a verified grep, and re-verify on every patch.**

## Concrete examples

**Wrong-granularity, per-row vs. per-call** (beta-2.14 Commit 7 / roadmap C3b v1→v2): The preflight's §1.3 enumerated call sites of `get_privilege_status` / `set_privilege_status` / `get_privilege_tag_members` / `get_production_categories` across 3 page files. The prose roll-up at the bottom of the table read "Total: 17 callers ... 15 do not [sit inside Pattern C]." CLI's independent re-grep returned 22 actual call sites. The 5-site shortfall traced to one table row labeled `pages/4_Review.py:5174-5196` that collapsed 5 actual call sites (3 `get_privilege_status` + 2 `set_privilege_status`) into a single range entry. The prose total counted per-row (17) but the underlying enumeration was per-call (22). v2 patched: "17 callers" → "22 call sites"; "15 do not" → "20 do not." Mitigation that landed: prose totals report per-call, and where table rows collapse line ranges into a single entry, an explanatory parenthetical names the collapsing convention so the prose total is unambiguous.

**Wrong-granularity, per-token vs. per-line** (beta-2.14 Commit 10
v3 meta-recursive correction): The v3 patch addressed CLI's H-2
finding (an undercount) by listing per-file distribution. PM listed
`tests/test_production_status.py: 94,109 (2 hits)` — but
`grep -cE "bates_start|bates_end"` returns 3 hit-lines for that file
(line 109 contains both tokens on one line; the per-token match count
is 4, the per-line hit count is 3). The v3 patch's authoritative sum
check (3+5+1+12+3+0=24 ✅) caught the miscount before handoff.
Mitigation that landed: cross-check via `grep -cE` per file (which is
unambiguously per-line) and verify the per-file totals sum to the
project total.

**Stale count rot, chain-of-counts** (beta-2.14 Commit 7 / roadmap C3b v2→v3): The "17 callers / 15 do not" count from the §1.3 prose recurred 7 times across the preflight (§1.3 source claim, §3.1 verdict backing, §6.2 probe trigger condition, §6.2 a second mention, §8.1 ledger evidence, §8.2 CLI focus item, and the §4 CHANGELOG entry). v2 patched 2 of 7 instances — the §1.3 source and the §4 CHANGELOG — leaving 5 stale references at §3.1 L191, §6.2 L427+L434, §8.1 L552, §8.2 L577. The preflight became internally contradictory: §1.3 said "22 call sites" while §3.1 immediately below said "17 callers." CLI v2 caught the staleness; v3 swept all 5 stale references. Mitigation: `grep -n <old_value> <preflight-path>` after every count patch to catch sibling occurrences before declaring the patch done. Cousin to `chain-of-moves-stale-refs.md`.

**Stale count rot, scope-expansion** (illustrative example): a
rename sweep for a helper function started scoped to 18 files; v2
expanded it to 22 files. The patch updated the §3 file enumeration but
left §6 ("NOT touched" list), §8.2 (Hygienic/Strategic table), §5.2
(verification protocol), and the §0.2 thesis prose stale with the
original 18-file framing. CLI v3 caught all four. Mitigation: after
patching scope in §X, grep ALL references to the patched concept
across the preflight and update the consistent set BEFORE declaring
done.

**Incomplete inventory, word-boundary regex** (illustrative example): a
sweep for a renamed constant used `\bOLD_NAME\b` to inventory
occurrences. The pattern missed tokens glued to digits (e.g.,
`OLD_NAME2`). v2 caught the gap by switching to a loose pattern
`OLD_NAME[A-Za-z0-9_]*` with a follow-up confirmation grep.
Mitigation: prefer loose patterns for inventory sweeps; tighten only
when verifying canonical spellings, not when sweeping for
completeness.

## How to apply

**At draft time:**

1. **Verify every count claim with a grep before writing it.** If
   the count is "5 files, 17 hit-lines," run `grep -lE <pattern>`
   for the file count and `grep -cE <pattern>` summed for the
   hit-line count. Quote the command and result inline. The
   `Check 11 — Grep-count cross-verification` step in
   `docs/templates/preflight_drafting_checklist.md` operationalizes
   this.

2. **Match prose granularity to grep granularity.** If you ran
   `grep -cE` (per-line) but the prose claims per-call sites,
   either re-grep with a tighter pattern or restate the prose to
   match the grep unit.

3. **Sum-check per-file distributions.** When a count claim breaks
   down by file, the per-file totals must sum to the project
   total. The arithmetic catches both per-line/per-token confusion
   AND missing-file errors.

**At patch time:**

4. **Grep the document for any count being patched.** Before
   declaring a count patch done, run `grep -n <old-value>
   <preflight-path>` to find sibling occurrences. Patch all of
   them or the preflight ships internally inconsistent.

5. **After scope expansion, sweep the document for the original
   scope's framing.** "NOT touched" lists, classification tables,
   verification protocols, thesis prose — anywhere the original
   scope was named, audit for staleness.

**At inventory-pattern time:**

6. **Prefer loose patterns for completeness sweeps.** `\b` word
   boundaries are correct for canonical-spelling verification but
   wrong for "find all instances." Run a loose-pattern sweep
   first, then tighten if filtering false positives.

## Why this is worth canonizing

PM-side count discipline is the second-opinion model's blind spot.
CLI's pre-flight check exists to catch what PM missed, and CLI is
good at catching count errors via authoritative greps. But every
miss that reaches CLI costs a v1→v2 round of pinball. Five separate
sprint cycles surfaced the same defect classes in the same shape.
Canonizing them as a lesson + Check turns the recurring catch into a
preventable miss — PM does the verification at draft time instead of
discovering it at CLI delta-check time.

The cost of running these checks at draft is small (5 minutes of
grep). The cost of NOT running them is at minimum one CLI round
(~10 minutes of pinball plus token spend on PM patch + CLI re-check)
and at worst a stale count making it into a court-facing artifact
(see `defensibility_report.py` rendering decisions in beta-2.14
Commit 10).

## See also

- `docs/templates/preflight_drafting_checklist.md` Check 11 —
  operational version of this lesson, run during preflight drafting.
- `docs/lessons/chain-of-moves-stale-refs.md` — sibling lesson on
  stale references after multi-step refactors; same root-cause family
  as Cluster B (stale count rot) here.
- `docs/lessons/n-stage-gate-revision-handling.md` — the gate
  doctrine that makes "every revision triggers a fresh CLI delta-check"
  load-bearing; this lesson reduces the count of delta-checks needed.
- `feedback_meta_recursive_defect.md` (PM auto-memory) — related
  meta-recursive defect family; CHANGELOG prose
  self-quoting
  is filed there, not here, because it's not a count failure — it's
  a prose self-referential failure.
