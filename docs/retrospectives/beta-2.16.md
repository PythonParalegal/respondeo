# beta-2.16 Retrospective

**Sprint:** `beta-2.16`
**Status:** **In progress.** Phase 1 (self-correction infrastructure) landed; subsequent phases append below as the sprint continues.
**Version tag cut:** TBD at sprint close (will be `v2.16.0`)
**Commit range so far:** 4 commits (spec + 3 infrastructure commits, originally drafted under the `beta-2.16-meta` working name)
**Phase 1 written:** 2026-05-22 by CLI Claude
**Author:** CLI Claude (drafted inline during the Phase 1 sprint-close addendum commit; renamed from `beta-2.16-meta.md` at the grafting decision)

> **Naming note:** This retrospective was originally drafted as `beta-2.16-meta.md` because the self-correction infrastructure work was scoped as a standalone "meta-sprint" separate from the planned beta-2.16 product-code work. After Phase 1 closed, the maintainer grafted the meta-sprint onto beta-2.16 — the infrastructure work was substantively in beta-2.16's scope anyway (S-2 was on its backlog) and the project routinely mixes tooling + product in single version increments. The original commit subject lines retain the `beta-2.16-meta` prefix as forensic record of the sub-arc; the sprint as a whole is now just beta-2.16. Sections 2-6 below describe the Phase 1 work; Phase 2 (M-1 Flag #5 Pattern A consolidation) and later phases will append as they ship.

---

## 1. Sprint Scope

The sprint set out to build a self-correcting wiring layer over the
existing library. The maintainer observed in a chat-paste about CPU/GPU AI
hardware that despite the depth of CLAUDE.md + docs/references/ +
docs/lessons/ + auto-memory, "misses" — failures to consult relevant
docs at the right moment — were still happening. A brainstorming session
surveyed 22 documented misses across beta-2.11 through beta-2.15 and
found that 45% were TRIGGER gaps (rules exist but don't fire), 27%
were RECENCY decay, 18% were COMPREHENSION (multi-instance / meta-
recursive), 9% were CATALOG, 9% were META. The fix was scoped as a
hybrid approach — automation for binary-checkable patterns, prose
triggers for keyword-keyed reminders, ritual reinforcement for
judgment calls — designed in `docs/specs/library_self_correction_design.md`
and implemented in two main commits plus a sprint-close addendum.

## 2. What Shipped

| Commit | Summary |
| -------- | --------- |
| Spec | Design spec landed on `main` pre-sprint (10 sections, ~580 lines after edits, including §11 four-layer bootstrap closure for the meta-recursive structural hole). |
| 1 | Infrastructure: `triggers.py` (16 entries incl. `drift-correction-language` meta-trigger), `refresher.md` (5 slots), trigger-injector + session-refresher hooks (8 unit tests), Standing Orders A/B/D/E/G added to CLAUDE.md, `discipline_graveyard.md` scaffold. |
| 2 | First Tier 4 promotions: pre-commit hooks for Check 1 + secrets/PII guard (S-2 absorbed) + Check 12 (Broaden-without-reinventory) added to preflight-drafting-checklist. 13 unit tests total. 3 graveyard entries. Slots 1, 2, 4 of refresher.md vacated. Spec updated: `triggers.yaml` → `triggers.py` throughout. Standing Orders C/F added. |
| 3 (this) | Closing work: PII-guard binary-file skip. Current State refresh. CHANGELOG addition. This retrospective. Standing Order G triggers audit (inline in commit message). |

Net delta: 4 hook scripts (~280 lines of Python), 2 living-document files (`triggers.py`, `refresher.md`), 1 graveyard log, 6 Standing Orders added to CLAUDE.md, 1 new checklist item (Check 12), 1 design spec, 1 plan document, 1 retrospective. 13 hook unit tests, all passing. The pre-commit hook is installed locally and verified clean against the tracked tree.

## 3. Goals vs. Outcomes

**Achieved as planned:** All four components from the spec architecture landed. Plan §0 plan-level decisions all executed (Python module instead of YAML; tests at `.claude/hooks/tests/`; forward-slash relative paths in `settings.json`; graceful-degradation in every hook; hand-written pre-commit shell stub). MVP Commit 1 + Commit 2 split executed as designed. The Layer A `drift-correction-language` meta-trigger shipped Day 1 per the §11.6 bootstrap-order requirement. Two Tier 4 promotions ship live; the third (broaden-without-reinventory) ships as a preflight checklist item. The S-2 backlog item from beta-2.16 was absorbed cleanly per the bundling-principle test.

**Achieved with adjustment:**
- The PII guard needed one implementation fix: strict UTF-8 decode to skip binary files (PNG data produced byte-pattern false positives).
- `.claude/settings.json` is gitignored in this project (so are `.claude/hooks/__init__.py` files, via the `_*.py` pattern). Hooks are live on this machine but won't propagate to fresh clones. Accepted as solo-developer single-machine scope.

**Deferred:**
- Layer D Stop hook (auto-scan prior turn for un-acknowledged corrections) — conditional Tier 4 promotion if Layer A leaks. Held per §11.4 until evidence of leakage at 3+ sprint-close audits.
- Domain-specific trigger expansion beyond the initial 16 (PST family edge-cases, OpenSearch query DSL patterns, etc.). Add on encountering recurrences.
- `.claude/settings.json` portability (settings.example.json + setup script). Solo-developer scope doesn't require it; future iteration if needed.

## 4. Surprises and Learnings

Two things genuinely surprised. First, the survey of documented misses categorically reframed the problem. Going in, my instinct was that the library wasn't visible enough — that a catalog of references buried in `docs/references/` was the issue. The data refuted this immediately: only 9% of documented misses were CATALOG-class (didn't know it existed). The library is well-structured; the wiring is the failure mode. Forty-five percent of misses were TRIGGER gaps where rules exist but don't fire. If I had started building a catalog without surveying the misses, I'd have spent effort on the smallest leverage point.

Second, the implementation surfaced its own first defect. Batch 11 of the plan execution accidentally introduced an "Item 11" section to `docs/templates/preflight_drafting_checklist.md` alongside the existing "Check 11" that already covered grep-count discipline. The implementer flagged it; I caught and fixed it inline before commit. But the texture of it was striking — the very meta-recursive defect pattern (patches commit the defect class they're closing) that the hook system was being built to enforce showed up *in* the system's own implementation. The retrospective entry felt almost too on-the-nose to be real, but the diff was right there. Encoded as Check 12 in the same commit; the existing Check 11 covers the grep-count side, and the new Check 12 covers the broaden-without-reinventory side.

A smaller surprise that's worth flagging: the plan's own grep-count prediction was wrong. The plan said the implementer would find "3+" references to `discipline_graveyard.md` in the post-Batch-6 CLAUDE.md; the implementer's grep returned 2. The implementer correctly identified this as a plan-spec error rather than a content error and flagged rather than improvised. This is the exact discipline that Check 11 / Check 12 are meant to enforce. So the discipline works when the workflow follows it — the plan-writing phase itself didn't follow the discipline that the plan was about to install. Bookmarked but not canonized as a new lesson (one occurrence).


## 5. Lessons Canonized

No new `docs/lessons/` entries this sprint. The behaviors this sprint installed (Check 12 broaden-without-reinventory, the four-layer §11 bootstrap closure, the promotion ladder, the graveyard log) are themselves the canonization of patterns surfaced in prior sprints. Lessons referenced by this sprint's installation:

- `docs/lessons/grep-count-discipline.md` — Check 11 (existing) + new Check 12 both surface from this lesson.
- `docs/lessons/not-in-git-tracked-not-existent.md` — Check 1 pre-commit hook enforces this lesson.
- `docs/lessons/n-stage-gate-revision-handling.md` — referenced by Standing Order G.
- `docs/lessons/premature-release-tag.md` — referenced by `sprint-close` trigger.

Standing Order additions to CLAUDE.md (all in this sprint):

- **A — Triggers & Refresher Living Documents.** `triggers.py` continuously updated; `refresher.md` at sprint-close.
- **B — Sprint-Close Refresher Review.** Per-slot promotion criteria; Tier 4 ships in the sprint-close commit.
- **C — Preflight-Drafting-Checklist Check 11 + Check 12.** Both judgment-required, both hard-gated.
- **D — Dependency API References row.** Adds `.claude/triggers.py` / `refresher.md` / `discipline_graveyard.md` to the pointer table.
- **E — Lesson Integration Decision Tree step 1.5.** "Is this a recurring drift pattern?" → add a trigger.
- **G — Sprint-Close Triggers Audit.** Layer B hard gate (table in commit message; no addendum without it).

The spec itself (`docs/specs/library_self_correction_design.md`) and the plan
(`docs/superpowers/plans/2026-05-22-library-self-correction.md`) are the
canonical references for the system going forward. The spec includes §11
on the meta-recursive structural hole and the four-layer mitigation.

## 6. Gotchas for Future Sprints

- **`.claude/settings.json` is gitignored.** Hook registration is per-clone, per-machine. A fresh clone will have the hook scripts (tracked) and the `install_precommit.sh` re-installer (tracked) but no hook event wiring in `settings.json`. Document the manual install step in the project README if multi-machine portability becomes a need. (Beta-2.16-meta Commit 1 commit message records this.)
- **Pre-commit hook scans the LATEST preflight by mtime.** If multiple preflights exist for different commits in the same sprint, Check 1 only checks the most-recently-modified one. For sprints with simultaneous preflight drafting, this is a coverage gap. Address if it surfaces.
- **Layer D Stop hook deferred.** If Layer A's real-time `drift-correction-language` trigger fails to surface corrections in-session, sprint-close audits (Layer B) will catch them post-hoc. If sprint-close audits keep finding misses that Layer A didn't catch, promote Layer D (Stop hook scanning prior turn). Criteria: 3+ sprint-close audits with un-logged in-session corrections.
- **The refresher.md cap is a max, not a min.** Empty slots are by design. The 5-slot ceiling forces hard prioritization at sprint-close: cannot add a new pattern without retiring (via promotion or via 2-sprint zero-recurrence demotion). If a future sprint wants to expand the ceiling, the promotion ladder design needs to be reconsidered — empty slots are the success signal.

---

## Provenance

This retrospective was written by CLI Claude during the sprint-close
addendum commit for `beta-2.16-meta`. The sprint had no formal preflight
process (the spec at `docs/specs/library_self_correction_design.md` +
the plan at `docs/superpowers/plans/2026-05-22-library-self-correction.md`
were the planning artifacts), so the retrospective documents the sprint
arc directly. The maintainer reviewed the closing-work commit diff (including
this retrospective) before the commit landed and the branch merged to main.

---

# Phase 2 onward — the product arc (C4–C9)

**Appended:** 2026-06-01 by PM Claude at sprint close.
**Commit range:** C4 … C9, on `beta-2.16` (local; no remote push).
**Status at close:** product arc complete; M-1 (Flag #5 Pattern A) **deferred to a dedicated beta-2.17 DB-hygiene sprint** (decision below). `v2.16.0` tag to be cut at the ff-merge-final commit after the audit-doc archival addendum lands.

## P2.1 — What shipped

| Commit | Roadmap | Summary |
| -------- | --------- | --------- |
| C4 | S-3 | Fix stale `TestProductionInboundExclusion` test docstring reference (Option C pointer fix). |
| C5 | S-2 | Close **Flag #28** — canonical `os_manager.cn_from_hit()` + `compute_os_id()` helpers; consumer migrations (Review search loop, `9_InboundProduction.py`); `reindex_from_sqlite` content-preservation bug fix; 9-test regression pin. |
| C6 | S-1a | **Flag #22** NearDupe k-gram shingling fix; 9 regression tests. 4-revision preflight cycle (v1→v5) with an anti-fitting guardrail that caught a real over-correction (v3 abort) + estimator undershoot (v4 pre-measurement). Registered **Flag #30** (non-transitive clustering). |
| C7 | — | Mid-sprint debt absorption: canonized `regression-test-as-calibration-canary.md` + `fix-the-prose-miss-the-code-block.md`; filled `.claude/refresher.md` Slot 1; added `preflight-patch-revision` trigger. |
| — | hygiene | Check 1 pre-commit hook: skip gitignored-by-design files. |
| C8a | S-1b | Near-dupe cluster persistence (`near_dupe_clusters` + `near_dupe_cluster_members`) + provisional deferred-tag suppression (fail-open). |
| — | hygiene | Track sprint audit corpus (catch-up — 20 untracked docs/audits files). |
| C8b | S-1b | Review "Near-Dupe Clusters" surface + cross-cluster decision fan-out + re-run guard. |
| C8c | S-1b γ | Dedup Report migration to cluster tables + Production pending-review FYI banner. |
| — | hygiene | Install audit-doc-sample-data trigger. |
| — | tooling | Cross-agent tooling (Gemini CLI / Antigravity read-only collaborator; `.gemini-context/` gitignored). |
| C9 | S-1c | Near-dupe cluster reporting in the defensibility report (§4.2 cluster review + attestation; document-level reconciliation). |

## P2.2 — The forensic stories

**S-1b deferred-tagging model (C8a/b/c).** The architectural keystone of the sprint: near-dupe suppression moved from *automatic-at-analysis* to *deferred-until-reviewer-confirms* (fail-open — nothing leaves the review population until a human attests). Cross-cluster decision fan-out (`record_member_decision` writes every row for a `member_cn`) is what makes one human decision authoritative across overlapping clusters. This model is what C9/S-1c then had to report honestly.

**S-1c B-1 → B-2 double-catch (C9).** The clearest demonstration this sprint of the N-Stage Gate working. PM's v1 preflight asserted the §4.2 disposition counts "reconcile with §4.1 by construction." CLI's pre-flight check caught **B-1**: a per-cluster sum can never equal a distinct-document count when a document belongs to multiple clusters (Flag #30, observed on the Test(small) set). PM revised to reconcile at the document-level summary + footnote the per-cluster table. CLI's v2 delta-check then caught **B-2**: the corrected distinct-document partition dropped the `undecided & family_preserved=1` cell — the *default post-run state* of every family-attached member — which would have under-reported the unreviewed population on a court PDF. Both were caught at the preflight gate, before any code; the manual PDF spot-check on the Test(small) set (which exhibits Flag #30 overlap) confirmed the shipped §4.2 reconciles and self-audits per row.

**M-1 investigation → deferral.** Scoped as the sprint's "heavy lift," M-1 (Flag #5 Pattern A) was investigated at close and revealed to be larger and riskier than the carried-over "2–3 commit, `run_*` helpers" shorthand implied. Pattern A is the 3 long-span (837/599/774-line) UI-interwoven orchestration sites; it was never previously done (2.14/2.15 did Patterns B/C/X — call-site hardening only); no `run_*` consolidation convention exists, and none of the ~11 nested writers are `conn`-aware. The central design fork — Approach 1 (thread `conn=None`, cautious/additive) vs. Approach 3 (consolidate into `db_manager.run_*`, cleaner but UI/DB-separation surgery on live-case pages) — was unresolved. The maintainer deferred it to a dedicated beta-2.17 DB-hygiene sprint rather than rush major refactoring into a sprint-closer. The investigation correcting the "apply established pattern" assumption is the Pre-Fix Investigation Protocol working as designed.

## P2.3 — Misses & saves (for the Sprint-Close Triggers Audit)

| Miss/save | Caught by | Trigger that would catch it |
|-----------|-----------|------------------------------|
| **B-1** — reconciliation claim false under cluster overlap (per-cluster sum ≠ distinct-doc count) | CLI v1 check | `partition-enumeration` (NEW — candidate; see lessons) |
| **B-2** — distinct-document partition dropped the undecided+family cell | CLI v2 delta-check | `partition-enumeration` (same class, one level down) |
| **`nd_pending`→`nd_undecided` rename left ~14 stragglers** in patched preflight/spec/plan | PM post-patch grep ritual | existing `preflight-patch-revision` / `fix-the-prose-miss-the-code-block` — fired correctly |

## P2.4 — Lessons & notes

- **Candidate lesson — partition-enumeration discipline.** B-1 + B-2 are two instances *in one preflight cycle* of "before asserting a reconciliation/partition holds, enumerate every cell of the underlying grid and check the join key; don't trust a fixture that only seeds some cells." Bookmarked in PM auto-memory (`feedback_partition_enumeration_discipline`); CLI independently seconded canonizing it. Canonization bar (3+ across 2+ sprints) not yet met — promote if it recurs in beta-2.17.
- **PM artifact discipline reaffirmed.** All beta-2.16 PM specs/preflights use synthetic sample data (`DOC-NNNNNNN`).

## P2.5 — Carryover to beta-2.17

- **M-1 / Flag #5 Pattern A** — dedicated DB-hygiene sprint; resolve Approach 1 vs 3 in a design pass first (characterized in beta-2.11 Commit 3).
- **Flag #30** (non-transitive / overlapping near-dupe clusters) — union-find merge over the LSH candidate graph; S-1c reports overlap honestly but does not merge.
- Family-grouped native export spec (UNSHIPPED, tracked since beta-2.15 C8).
- Partition-enumeration lesson — promote on recurrence.

## P2.6 — Provenance (Phase 2+)

The product-arc commits (C4–C9) used the full PM–CLI preflight workflow (preflights at `docs/audits/commit_N_*`, CLI pre-flight + delta-checks, the maintainer's Stage-1/Stage-2 gates). This Phase-2+ section was drafted by PM Claude at sprint close on 2026-06-01, to be reviewed by the maintainer in the sprint-close addendum commit diff before the `v2.16.0` tag is cut.
