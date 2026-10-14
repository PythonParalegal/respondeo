# Beta-2.15 Sprint Plan — Cleanup Audits + Flag #5 Closeout

**Status:** UNSHIPPED — proposal authored 2026-04-30 at beta-2.14 sprint close (Commit 12 / roadmap C7). Awaiting beta-2.15 sprint-open ratification.

**Predecessor sprint:** beta-2.14 (`v2.14.0` to be tagged at C8 sprint-close commit). 12 substantive commits + sprint-close addendum.

## Sprint thesis

Beta-2.15 closes out three threads that beta-2.14 left open:

1. **Flag #5 surface closure** — Pattern X / Pattern C have shipped (9 sites hardened across C3a/C3a-followup/C3b in beta-2.14). Class B sub-span A (3 sites) and Pattern A consolidation (2-3 surfaces) remain. Closing Flag #5 fully retires the largest hazard class on the beta-2.10 retrospective inventory.
2. **Analytics quality (Flag #22)** — near-dupe false-positive sensitivity is characterized in `docs/archive/specs/neardupe_false_positive_sensitivity.md` and roadmap-flagged but unscheduled. Beta-2.15 schedules it.
3. **Discipline canonization continuation** — beta-2.14 C6 canonized 5 grep-count observations into `docs/lessons/grep-count-discipline.md`. The C6 cycle itself surfaced 2 new observations (sprint-mis-cite verification, cluster-interaction defects). Beta-2.15 holds these in auto-memory pending more empirical recurrences; if they accumulate, fold them mid-sprint.

Tertiary cleanup items (CI secrets/PII guard, stale doc references, PM auto-memory disposition, auto-memory hygiene-sweep Standing Order) round out the sprint with bounded-scope hygiene work.

## Item enumeration

### Must-do tier (sprint-bottlenecking; must ship for sprint to "succeed")

#### M-1. Flag #5 Class B sub-span A — `pages/6_Sync.py:328, 341, 354`

**Defect class:** Same Pattern X hazard as the Class A sub-span A already shipped in beta-2.14 C3a-followup. Three error-path sites where `log_audit` fires after an UPDATE inside a held-conn loop, then `continue`s to the next iteration. Naive `conn=conn` fix introduces last-iteration regression (next commit happens in NEXT iteration, not this one). Requires commit-restructuring: add `conn.commit()` after each error-path UPDATE+audit pair before `continue`.

**Scope estimate:** 1 commit, ~30 LOC across 3 sites. Edit-only; pinned-value test already exists for Pattern X invariant.

**Rationale for must-do:** Same hazard surface as C3a-followup; closing it fully retires Class B sub-span A. Failure mode is correctness-affecting (audit/UPDATE atomicity).

#### M-2. Flag #5 Pattern A consolidation — `pages/6_Sync.py:278, 516`; `pages/7_Custodians.py:79`

**Defect class:** Function-local + module-level held connections that orchestrate multi-step writes. Approach 3 from the original Flag #5 characterization: consolidate orchestration into `db_manager.run_*` helpers so the page-file held conn becomes unnecessary.

**Scope estimate:** 2-3 commits. ~80-150 LOC. Requires new `db_manager.run_<orchestration>` helpers (SIGNATURE proposal needed in dedicated preflight). Heavier than M-1; warrants its own preflight cycle with the 8-section template.

**Rationale for must-do:** Closes Flag #5 fully. Without M-2, Flag #5 remains characterized-but-open with the largest pattern surface untouched.

### Should-do tier (high-value, scoped, deferral-cost low)

#### S-1. Flag #22 — Near-dupe false-positive sensitivity tuning

**Spec exists:** `docs/archive/specs/neardupe_false_positive_sensitivity.md` (registered beta-2.13 sprint close). Characterizes the false-positive surface where invoice-style templates cluster under NearDupe-Suppressed despite content distinction.

**Scope estimate:** 1-2 commits. Likely a sensitivity-threshold tuning + test cases proving the new threshold catches templates without breaking content-similar dedup.

**Rationale for should-do:** Quality issue with case-management implications (template-similar documents clustering together can hide distinct records from review). Spec is ready; just needs sprint slot.

#### S-2. CI secrets/PII guard

**Background:** A pre-commit hook or pytest check that fails CI when secrets or personal contact data (keys, tokens, real-looking emails or phone numbers) appear in tracked files. Design questions deferred (which rules? allow-list? local deny-list?).

**Scope estimate:** 1 commit, ~40-60 LOC (a pre-commit script plus unit tests). Design Q answers proposed inline; the maintainer ratifies.

**Rationale for should-do:** Cheap safety net for secrets and contact data. Cheap to implement; high regression-prevention value.

#### S-3. Stale `TestProductionInboundExclusion` doc reference at `tests/test_bates.py:331`

**Defect class:** Comment-rot. References a test class that doesn't exist anywhere in `tests/`. Out-of-scope for any prior sprint; bookmarked for future cleanup audit (originally deferred from beta-2.14).

**Scope estimate:** 1 LOC fix in a tiny-hygiene commit. Could fold into another sprint-open hygiene commit; minimal standalone scope.

**Rationale for should-do:** Cheap; finishes a long-bookmarked cleanup item.

### Nice-to-have tier (discipline/quality items; defer if sprint runs hot)

#### N-1. Sprint-mis-cite verification (auto-memory observation A from beta-2.14 C6)

**Background:** Beta-2.14 Commit 11 v2 cited "beta-2.13 C7" for events that were actually beta-2.14 C7 — beta-2.13 only shipped C1. Caught at CLI v1 H-1 against Commit 11 preflight v2. Proposed mitigation: lesson canonizations citing prior-sprint events must verify the sprint label against `git log` / archive preflights before drafting.

**Canonization bar:** Hold in auto-memory until 2+ more recurrences. If a future sprint surfaces a second instance, fold both into either `docs/lessons/grep-count-discipline.md` as a fourth family OR a fresh lesson on lesson-canonization discipline.

**Scope estimate:** 0 commits if recurrences don't accumulate. Otherwise ~1 lesson-update commit.

**Rationale for nice-to-have:** Premature canonization is itself a discipline failure (`docs/lessons/preflight-proportionality.md` analog). Wait for empirical justification.

#### N-2. Cluster-interaction defects (auto-memory observation B from beta-2.14 C6)

**Background:** Commit 11 preflight v3 H-2 fix used a tight regex (`alphabetical position`) that missed semantic cousins (`alphabetical order`, `alphabetical sort`, `alphabetical convention`). The lesson's three families (wrong-granularity, stale count rot, incomplete inventory) interact rather than being independent; chain-of-counts mitigation must use loose patterns to avoid being itself an incomplete-inventory failure.

**Canonization bar:** Same as N-1. Hold until 2+ more recurrences.

**Scope estimate:** Same as N-1.

**Rationale for nice-to-have:** Same as N-1.

#### N-3. PM auto-memory disposition (H-2 from beta-2.14 C8)

**Background:** PM auto-memory files are local-only. The deferred decision: should they follow the same synthetic-sample-data practice as tracked docs?

**Scope estimate:** 0 LOC if "no, leave as-is" — purely a maintainer decision. ~5-10 LOC if "yes" (rename files + light edit).

**Rationale for nice-to-have:** No correctness impact; aesthetic/discipline question.

#### N-4. Transitive-wrapper threading on `get_privilege_tag_members` + `get_production_categories`

**Background:** Deferred per beta-2.14 C7 §6.1. No current Pattern C hazard surface justifies proactive API parameter addition. If Pattern C site emerges that needs threading, this becomes must-do retroactively.

**Scope estimate:** 0 commits unless triggered by a new hazard surface.

**Rationale for nice-to-have:** Pure proactive scaffolding; defer until justified.

#### N-5. Auto-memory hygiene-sweep Standing Order

**Background:** Auto-memory at `~/.claude/projects/C--Users-<user>-Projects-ediscovery/memory/` accumulates across sprints with no codified pruning discipline. As of 2026-05-06, MEMORY.md indexes 35+ entries; some older feedback memories (M-7 widget keys, Streamlit module caching) and project memories (older sprint snapshots) may be stale relative to current code state, partially superseded by Standing Orders that have since canonized the same rule, or contradicted by later memories that revised the position. The 200-line truncation cap on MEMORY.md is being approached; once exceeded, older index entries fall out of always-loaded context silently. CLAUDE.md currently has Standing Orders covering audit-doc archival, dependency-map maintenance, lesson integration, FLAG_REGISTRY discipline, and `docs/specs/` lifecycle, but auto-memory is treated as continuously self-maintained — there is no sprint-close gate that catches accumulated drift.

**Inspiration source:** Anthropic Managed Agents "Dreams" feature (research preview, 2026-04-21 beta), which automates memory-store deduplication and reorganization for hosted agents. Dreams is not directly applicable to Claude Code (we don't run on Managed Agents infrastructure), but its premise — that memory accumulates duplicates, contradictions, and stale entries over many sessions — describes our local auto-memory honestly. The proposal here is to codify the dedup/reorg pass as a sprint-close discipline executed by PM Claude (no API integration; pure file edits).

**Proposed Standing Order shape:**

> **Standing Orders — Auto-Memory Hygiene Sweep**
>
> At sprint close (after the retrospective is written, before the sprint-close addendum commit lands), PM Claude performs a structured pass over `~/.claude/projects/C--Users-<user>-Projects-ediscovery/memory/`:
>
> 1. **Enumerate.** List every memory file. For each, classify as one of: KEEP (still load-bearing), MERGE (overlaps another memory; consolidate), ARCHIVE (superseded by a Standing Order or canonized lesson; move to an `archive/` subdirectory), DELETE (factually wrong or contradicted by current state).
> 2. **Identify cross-references.** For ARCHIVE/DELETE candidates, grep MEMORY.md and other memory files for references; update or remove them.
> 3. **Rebuild MEMORY.md.** Regenerate the index from the post-sweep file set. Verify under 200-line truncation cap.
> 4. **Record disposition in the sprint retrospective.** Append a line: "Auto-memory sweep: N kept, M merged, K archived, J deleted." This is the audit trail since auto-memory is gitignored.
> 5. **The maintainer's ratification gate.** PM proposes the disposition list before executing ARCHIVE/DELETE actions. KEEP and MERGE may execute under PM judgment without explicit ratification (low-risk reorganization). ARCHIVE/DELETE require the maintainer's greenlight per the spirit of the permission-gate-strategic-vs-hygienic lesson — these are durable losses of session-readable context, not just file rearrangement.

**Scope estimate:** 1 commit, ~40-60 LOC. Components: (a) new Standing Order added to CLAUDE.md (~30 LOC); (b) optional new template at `docs/templates/auto_memory_sweep_template.md` (~50 LOC) providing the structured disposition-list scaffold; (c) one-time first-pass execution applied to current auto-memory at the same sprint-close (no LOC count — just memory file edits, recorded in retrospective). The first-pass execution is the discriminating test of whether the Standing Order is well-shaped: if PM struggles to classify entries cleanly, the Standing Order needs revision before canonizing.

**Folding option:** Could share Commit 7 with S-3 (stale doc reference) under the lightweight template, since both are tiny-hygiene work. CLAUDE.md edit makes it strategic-tier, so a dedicated commit with the 8-section template is cleaner if shipping standalone.

**Open design questions for preflight:**

1. **Archive directory layout.** Where do archived memories live? Proposal: `~/.claude/projects/.../memory/_archive/<YYYY-MM>/<original_name>.md` mirroring `docs/archive/audits/<branch>/` convention. Reversible if a future session needs to consult an old memory.
2. **First-pass scope.** Sweep all 35+ entries on first execution, or only entries older than N sprints? Proposal: first-pass sweeps all; subsequent sprint-close executions are incremental (only entries touched since previous sprint close).
3. **Conflict-handling.** What if the sweep proposes archiving a memory that another memory cross-references? Proposal: sweep order is "leaves first" — entries with zero inbound refs get classified before entries with refs. Refs to soon-archived files become orphans surfaced as MERGE candidates.

**Rationale for nice-to-have:** No correctness impact on production code or sprint deliverables. Auto-memory works fine with accumulated noise; the sweep is a context-quality and discipline investment that compounds over many sprints. Failure mode if deferred is gradual context degradation (older sessions' assumptions cited as still-current, MEMORY.md truncation silently dropping older entries), not regression. Cheap to implement; defer if sprint runs hot.

**Why not Should-do:** The first-pass sweep itself is judgment-heavy — classifying "is `feedback_pdf_viewer.md` still load-bearing or is it superseded by code state?" requires reading both the memory and the current code. That's a real cost the first time, low cost in subsequent sprints. Pushing this to nice-to-have keeps Should-do tier focused on items with clearer scope.

### Defer-further tier (parked indefinitely; needs the maintainer triage to promote)

_(No items.)_

## Sprint shape proposal

If Must-do + Should-do tiers all ship: ~5-7 commits + sprint-close addendum.

| Commit | Scope | Template |
|---|---|---|
| 1 | M-1 Flag #5 Class B sub-span A | 8-section |
| 2-4 | M-2 Flag #5 Pattern A consolidation (multi-commit arc) | 8-section per commit |
| 5 | S-1 Flag #22 near-dupe sensitivity tuning | 8-section |
| 6 | S-2 CI secrets/PII guard | 8-section |
| 7 (optional) | S-3 Stale doc reference + any nice-to-have folds | Lightweight |
| 8 | Sprint-close addendum + `v2.15.0` tag cut | Lightweight |

Total: ~7-8 commits. Comparable size to beta-2.14 (12 substantive commits + sprint-close addendum).

## Sprint exit criteria

Beta-2.15 is "done" when:

1. Flag #5 fully closed in `docs/FLAG_REGISTRY.md` (M-1 + M-2 ship; FLAG_REGISTRY row moves from Active to Dormant/Closed).
2. Flag #22 fully closed (S-1 ships; near-dupe spec moves from `docs/specs/` to `docs/archive/specs/`).
3. CI guard either landed (S-2 ships) OR explicitly deferred to beta-2.16 with a docs/lessons/ rationale entry.
4. Sprint-close addendum (retrospective + audit-doc archival + version bump + `v2.15.0` tag cut) lands per the Audit-Doc Archival Standing Order in CLAUDE.md.

## Open questions for sprint-open ratification

1. **M-2 multi-commit shape:** does Pattern A consolidation warrant 2 commits or 3? Depends on whether `db_manager.run_*` helpers have a natural split point. Resolve at M-2 preflight time.
2. **S-2 design questions:** which rules ship built in? Where does the optional local deny-list live? Resolve at S-2 preflight time with proposed answers + the maintainer's ratification.
3. **Tier promotions:** if the maintainer wants any nice-to-have item promoted to should-do, the sprint shape adjusts. Surface during sprint-open.

## See also

- `docs/archive/specs/neardupe_false_positive_sensitivity.md` — S-1 spec, ready for execution.
- `docs/lessons/grep-count-discipline.md` — beta-2.14 C6 canonization that surfaced N-1 + N-2 observations.
- `docs/retrospectives/beta-2.14.md` — sprint retrospective (will be authored at C8 sprint-close).
- The preflight whose v1→v3 cycle surfaced N-1 + N-2.
- `https://platform.claude.com/docs/en/managed-agents/dreams` — N-5 inspiration source (Anthropic Managed Agents "Dreams" research preview, 2026-04-21 beta). Not directly applicable to Claude Code workflow but premise (memory accumulates duplicates/contradictions/stale entries over many sessions) describes our local auto-memory honestly.
