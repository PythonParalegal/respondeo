# Changelog — Respondeo eDiscovery Platform

All notable changes are logged here by Claude Code automatically.
Format: `ACTION: file.py — description`

---

## [public-seed] — Public repository initialization

- CHANGE: .claude/hooks — the pre-commit content guard is now `precommit_pii_guard.py`: built-in checks for private keys, common API tokens, email addresses outside reserved example domains, and phone numbers outside the 555 range, plus an optional gitignored local deny-list (`.claude/hooks/pii_denylist.local.txt`; template `pii_denylist.example.txt`). Findings report file:line and rule only. Tests rewritten (8).
- CHANGE: pages/4_Review.py — `FILEVINE_SUBDOMAIN` fallback is now empty (no Filevine link is rendered until the subdomain is configured in config.py).

## [beta-2.17] — In Progress — DB-hygiene sprint

- NEW: .claude/hooks/precommit_pii_guard.py — `--root DIR` mode scans any directory on disk instead of git-tracked files (prunes `.git/`, skips binary files, prints the scanned-file count; mutually exclusive with `--path`); 6 new tests in .claude/hooks/tests/.
- FIX: pages/6_Sync.py — all sync/BYOS connection paths close via try/finally (R-1/R-7 leak class: sync_pending_documents had no close at all; Filevine pull leaked on the empty-result early return; BYOS push/pull and the redaction-mark writer leaked on exception). File-Missing audit threads `conn=conn` for consistency. Pure lifetime hygiene — no transaction-semantics change.
- FIX: db_manager.py — save_redaction_marks closes its connection via try/finally (leak on execute/commit exception).
- FIX: pages/6_Sync.py — BYOS pull/push loops commit per iteration; pull loop no longer holds a write lock across nested redaction-mark writers (Flag #32, 60s lock-collision + lost pull state on abort).
- DOCS: CLAUDE.md — new Standing Order "Decision Routing: Maintainer-Judgment vs Engineering-Mechanics" (the maintainer ratifies legal/defensibility/EDRM/UI/scope; PM/CLI autonomous on commit/branch/registry/CHANGELOG and `__version__`-bump mechanics, visibility via landing summary + diff). Amends Version Tracking rule 5 + Context Maintenance item 4.
- CHANGE: .claude/triggers.py, docs/templates/preflight_drafting_checklist.md — align the `version-bump` reminder + Check 10 strategic/hygienic split to the Decision Routing order so the self-correction hooks stop injecting propose-and-wait for `__version__`.

## [post-v2.16.0] — 2026-06-10 — self-correction hook contract fix

- FIX: .claude/hooks/trigger_injector.py — reminders now reach the model via `hookSpecificOutput.additionalContext` (was `systemMessage`, which is terminal-UI-only — model-invisible since 2026-05-22); UserPromptSubmit now reads the documented `prompt` field (was `user_prompt`, so prompt-scope triggers scanned an empty string); added per-session 30-min dedup so a fired trigger doesn't re-inject on every tool call.
- FIX: .claude/hooks/session_refresher.py — same `additionalContext` contract fix; refresher.md now actually lands in the model's session-start context.
- CHANGE: .claude/hooks/tests/ — both suites rewritten to pin the consumer-side platform contract (correct input key, `additionalContext` carrier, dedup behavior) instead of the emitter's output shape; 12 tests (10 injector + 2 refresher). Fixed brittle refresher assertion that passed only as a substring accident ("Check 1" in "Check 12").
- CHANGE: .claude/triggers.py — new `hook-output-contract` entry canonizing the miss; tightened two high-noise patterns (bare `equal(s)` in partition-enumeration, bare `rename` in file-archival-or-move); `__version__`-bump reminder updated to the Decision Routing standing order.
- CHANGE: .claude/settings.example.json — PreToolUse matcher narrowed from `*` to action-bearing tools (Bash/PowerShell/Edit/Write/Task/Agent/Skill et al.), eliminating a Python process spawn on every Read/Grep/Glob.
- DOCS: docs/specs/library_self_correction_design.md — §3.1 post-ship correction note (supersedes §6 "visible in initial context" acceptance criteria with consumer-side assertions).

> Phase 1 (self-correction infrastructure) shipped 2026-05-22, originally drafted under the working name `beta-2.16-meta` and grafted onto beta-2.16 post-Phase 1. Phase 2+ product arc (C4–C9) shipped 2026-05-24 → 2026-06-01; sprint closed at the C10 addendum with `v2.16.0` cut on `main` at the ff-merge-final commit.

### Commit 1 — self-correction infrastructure (2026-05-22)

- NEW: .claude/triggers.py — 16-entry keyword → reminder map (incl. `drift-correction-language` meta-trigger closing §11 Layer A bootstrap).
- NEW: .claude/refresher.md — top-5 recurring misses, session-start injection, 5-slot cap.
- NEW: .claude/hooks/trigger_injector.py — UserPromptSubmit + PreToolUse hook, regex scan with scope filter, 6 unit tests.
- NEW: .claude/hooks/session_refresher.py — SessionStart hook, 2 unit tests.
- NEW: docs/discipline_graveyard.md — append-only log of Tier 4 promotions.
- DOCS: CLAUDE.md — Standing Orders A/B/D/E/G added (triggers/refresher living docs; sprint-close refresher review; dependency table row; lesson-integration step 1.5; sprint-close triggers audit hard gate).

### Commit 2 — first Tier 4 promotions (2026-05-22)

- NEW: .claude/hooks/precommit_check1.py — pre-commit hook enforcing Check 1 (preflight-cited files must be git-tracked), 3 unit tests. Recurrence count at promotion: 5.
- NEW: .claude/hooks/precommit_pii_guard.py — pre-commit secrets/PII guard (absorbs beta-2.16 backlog S-2), unit tests.
- NEW: .claude/hooks/install_precommit.sh — re-installer for fresh clones.
- DOCS: docs/templates/preflight_drafting_checklist.md — Check 12 added (broaden-without-reinventory re-scan, judgment-required hard gate).
- DOCS: CLAUDE.md — Standing Order C added (Check 11 + Check 12 documentation). Item 11 / Check 11 duplication caught and fixed inline.
- DOCS: ROADMAP_TODO.md — S-2 marked ABSORBED.
- DOCS: docs/discipline_graveyard.md — 3 promotion entries (Check 1, secrets/PII guard, broaden-without-reinventory).
- CHANGE: .claude/refresher.md — slots 1, 2, 4 vacated to mechanical enforcement.
- DOCS: docs/specs/library_self_correction_design.md — `triggers.yaml` → `triggers.py` throughout (21 substitutions) with implementation note.

### Commit 3 — sprint-close addendum (2026-05-22)

- CHANGE: .claude/hooks/precommit_pii_guard.py — strict UTF-8 decode (binary files now skip cleanly — PNG byte-pattern false positive fixed).
- NEW: docs/retrospectives/beta-2.16-meta.md — sprint retrospective per template.
- DOCS: CLAUDE.md — Current State table refresh (active branch, last sprint summary, what's next).
- DOCS: CHANGELOG.md — beta-2.16-meta section.

### Commit 4 (S-3) — stale test docstring reference fix (Phase 2 opener, 2026-05-24)

- DOCS: tests/test_bates.py — correct stale `TestProductionInboundExclusion` docstring reference (nonexistent class) to point at the real inbound-exclusion coverage in `tests/test_defensibility_inbound_exclusion.py` (S-3 carryover from beta-2.14).

### Commit 5 (S-2) — Flag #28 closure: canonical OS-id helpers + reindex bug fix + regression test (2026-05-24)

- FIX: os_manager.py — `reindex_from_sqlite` content-preservation lookup dropped inbound-doc content on reindex (keyed `existing_content` by composite `_id` but looked up by raw `control_number` → guaranteed miss for inbound); now keyed by `cn_from_hit(hit)`. Closes Flag #28's reindex surface.
- NEW: os_manager.py — `cn_from_hit(hit)` + `compute_os_id(source_party, production_volume, control_number)`: symmetric shared helpers normalizing the internal-vs-inbound OpenSearch `_id` convention in one place.
- NEW: tests/test_os_id_canonical.py — 9-test regression pin for both helpers (internal/inbound shapes, projection-stripped fallback, round-trip, ValueError precondition).
- CHANGE: pages/4_Review.py — search-loop consumer migration to `os_manager.cn_from_hit(hit)` (replaces the beta-2.15 C7 inline triplet symptom patch); 4-line comment block condensed to a one-line Flag #28 reference.
- CHANGE: pages/9_InboundProduction.py — ingest-write `_ib_opensearch_id` migrated to `os_manager.compute_os_id(...)`.
- DOCS: os_manager.py + docs/references/OPENSEARCH_PATTERNS.md — `scan_all` docstring and dual-search examples updated to use `cn_from_hit` with a Flag #28 note.
- DOCS: DEPENDENCY_MAP.md — §6 "Shared Functions — Import Surface" rows added for `cn_from_hit` + `compute_os_id`.
- DOCS: docs/FLAG_REGISTRY.md — Flag #28 moved Active → Dormant/Closed; closure row + numbering-history closure entry; cross-codebase audit confirmed `4_Review.py` was the only vulnerable consumer.

### Commit 6 (S-1a) — NearDupe shingling algorithm fix (Flag #22; 2026-05-24)

- FIX: pages/3_Analytics.py — NearDupe detection now shingles with a 5-word k-gram sliding window (new `_compute_minhash_signature` helper) instead of word-level (k=1) tokens. k=1 clustered template-similar-but-content-distinct documents (e.g., same-vendor invoices with different numbers/amounts) as false-positive near-dupes; k=5 preserves local word-order so template-distinct docs separate (measured Jaccard ~0.73–0.81, well below the unchanged 0.90 threshold) while true forwarded-email near-dupes still cluster. Slider default threshold UNCHANGED at 0.90 (a proposed raise to 0.95 was reverted — k=5 alone delivers the fix; 0.95 broke true-near-dupe recall). Re-run analytics on any case where NearDupe-Suppressed currently affects production scope to re-tag under the corrected algorithm.
- NEW: tests/test_neardupe_shingling.py — 9-test regression fixture pinning the k-gram contract: template-distinct invoices do NOT cluster, narrow-preamble FW near-dupes DO cluster, RE-with-substantive-reply stays distinct, threshold gating, and shingling basics.
- DOCS: docs/specs/neardupe_false_positive_sensitivity.md — partial-shipping note (NUANCED status; S-1a algorithm phase shipped, S-1b cluster-review UI + S-1c defensibility report still unshipped).
- DOCS: docs/FLAG_REGISTRY.md — registered Flag #30 (production NearDupe clustering loop lacks transitive closure; pre-existing, deferred) surfaced during the S-1a fixture pre-measurement.

### Commit 7 — Mid-sprint debt absorption (lessons + refresher + triggers) (2026-05-24)

- NEW: docs/lessons/regression-test-as-calibration-canary.md — durable canonization of S-1a F-4 anti-fitting discipline.
- NEW: docs/lessons/fix-the-prose-miss-the-code-block.md — durable canonization of the 3-in-sprint Check-12 recurrence pattern + post-patch-grep ritual mitigation.
- DOCS: docs/lessons/README.md — index both new entries under Workflow discipline.
- DOCS: .claude/refresher.md — Slot 1 filled with fix-the-prose-miss-the-code-block (vacated 2026-05-22; filled per Standing Order B as the empirical signal from beta-2.16 Phase 2-3 justified).
- DOCS: .claude/triggers.py — preflight-patch-revision trigger entry added for real-time reminder during preflight revision work.
- DOCS: Mid-sprint hygiene commit between S-1a close and S-1b open. No product-code behavior change.

### Commit 8 (S-1b α / C8a) — near-dupe cluster persistence + provisional (deferred-tag) suppression (2026-05-25)

- NEW: db_manager.py — near-dupe cluster data layer: tables `near_dupe_clusters` + `near_dupe_cluster_members` (incl. a `family_preserved` guard column) in `init_db`, plus six helpers (`persist_near_dupe_clusters`, `get_near_dupe_clusters`, `get_cluster_members`, `record_member_decision`, `approve_cluster`, `clear_near_dupe_clusters`). `record_member_decision` writes the decision row + `documents.tags` atomically (one transaction) and refuses to apply `NearDupe-Suppressed` to a `family_preserved` member.
- CHANGE: pages/3_Analytics.py — NearDupe Execute now DEFERS suppression: it persists clusters + applies only the informational `NearDupe-Principal` tag; no `NearDupe-Suppressed` is written at execute. Suppression is provisional — applied per-member only when a reviewer confirms "Same as principal" in the (forthcoming C8b) Review → Near-Dupe Clusters tab. Status detection + the "Last run" banner date now key off the cluster table (`near_dupe_clusters.run_date`) rather than the tag; the third metric is reframed to confirmed-vs-pending; Clear & Re-run now calls `clear_near_dupe_clusters` (which owns tag-stripping + table wipe) and reports the count of discarded review decisions.
- NEW: pages/3_Analytics.py — pure `_build_cluster_payload` helper: one `iloc[0]` principal per cluster drives BOTH `is_principal` and `family_preserved`, so they cannot disagree under Flag #30 overlapping clusters. Fixes a dual-selection family-integrity leak found during execution (a metrics-principal that is a non-principal member of an overlapping cluster could otherwise persist with the family guard off, letting a reviewer orphan its family).
- NEW: tests/test_neardupe_clusters.py — 12 tests: persistence/fail-open, atomic decision+tag, distinct round-trip, attestation, clear-returns-counts, exact-dupe-untouched invariant, the family-integrity guard, plus the `_build_cluster_payload` split, the overlap regression pin (the leak cannot recur), and the NaN-parent edge.
- DOCS: DEPENDENCY_MAP.md — §6 rows for the six new helpers + the two new tables; deferred-tagging semantic recorded (`NearDupe-Suppressed` now means "reviewer-confirmed").
- DOCS: docs/FLAG_REGISTRY.md — Flag #30 row stamped with empirical activity (multi-cluster members observed on the Test(small) set); overlap-coherence deferred to C8b design (the maintainer's Option A), full transitive-merge still deferred.

### Commit 9 — sprint-audit corpus catch-up (docs only) (2026-05-28)

- DOCS: docs/audits/ — track 20 sprint-audit files that had been untracked all of beta-2.16: C4–C7 preflights + CLI check reports (incl. C6 S-1a's v1–v5 + execution-abort report) and the C8a preflight v1→v3 saga + CLI delta-check reports (v1/v2/v3). Sets up `git mv` for archival to `docs/archive/audits/beta-2.16/` at sprint-close per the Audit-Doc Archival Standing Order. (S-1b spec + plan and the Flag #30 empirical stamp already landed tracked in C8a per Check 1 enforcement.) No code touched; no version-header bumps.

### Commit 10 (S-1b β / C8b) — Review Near-Dupe Clusters surface + decision fan-out + re-run guard (2026-05-28)

- NEW: pages/4_Review.py — Near-Dupe Cluster Review surface (spec §11): a top-level view mode (a `🧬 Near-Dupe Clusters` option added to the existing `_rv_view_options` view-mode radio, surfaced only when clusters exist), rendered symmetric with the STR view (branch + `st.stop()`). Master/detail layout (`st.columns([0.18, 0.82])`, collapsible list); left pane = selectable cluster list with four status badges (PEND / M-N / N-N ✓ / FINALIZED); right pane = detail with member nav (Prev / position-numbered unique-label picker / Next), a context-collapsed `difflib` side-by-side diff (Show-full-text toggle + `st.dialog` Expand modal, cached), three per-member action states (normal Same/Distinct, family-preserved resolved panel, overlap-locked badge + jump), and three attestation states (PENDING/READY/FINALIZED with two-click Re-open). A reviewer decision toasts and auto-advances to the next member needing review (skipping family-preserved/locked members). The cluster-level act is labeled "Finalize review" (the internal `review_status` value stays `approved`). Member-index navigation uses a plain-int source of truth with position-prefixed unique labels (filename collisions across near-dupe copies otherwise mis-resolve `st.selectbox` to the wrong member). Theme-safe colors. Closed-case + `tag`-permission read-only handling. Constant `NEARDUPE_PANE_HEIGHT = 700`.
- FIX: pages/4_Review.py — relocate `db_manager.init_db(case_folder)` ahead of the view-mode selector (was after it) so the cluster-existence read-side gate cannot race a missing-table `OperationalError` on a case.db that has not yet had a post-C8a `init_db` run (e.g. deep-link/refresh to Review before Home initializes the schema). `get_connection` migrates only `audit_log` columns; only `init_db` creates the near-dupe tables.
- CHANGE: db_manager.py — `record_member_decision` now fans a reviewer's decision out across every cluster row for the same document (a doc can be a non-principal member of multiple near-dupe clusters), stamping `decided_in_cluster_id` with the source cluster on all rows; the family-integrity guard is now per-document (a `family_preserved=1` row in ANY cluster blocks suppression). New column `decided_in_cluster_id` (idempotent migration for C8a-era DBs). New helpers `reopen_cluster` (snapshots the prior attestation to a `NEARDUPE_CLUSTER_REOPENED` audit-log entry, reverts the cluster to pending, preserves member decisions) and `get_near_dupe_review_progress` (single aggregate query: confirmed/pending/n_decisions/n_clusters). `get_near_dupe_clusters` + `get_cluster_members` extended with the fields the review surface consumes (suppressible counts; `decided_in_cluster_id`). `log_audit` action vocabulary documents `NEARDUPE_DECISION`/`NEARDUPE_CLUSTER_APPROVED`/`NEARDUPE_CLUSTER_REOPENED`/`NEARDUPE_FORCE_RERUN`.
- CHANGE: pages/3_Analytics.py — Clear & Re-run Near-Duplicate now type-to-confirm-gated when reviewer decisions exist (must type `CLEAR N DECISIONS`; audited as `NEARDUPE_FORCE_RERUN` with the discarded counts); the zero-decision path keeps the original single-click flow. Confirmed/pending metric block now reads the single `get_near_dupe_review_progress` aggregate (subsumes the C8a F2-dispositioned inline per-cluster loop now that the guard is a second caller).
- NEW: os_manager.py — `get_document_content(case_folder, control_number)` fetches `_source.content` via an exact `control_number.keyword` term query (mirrors the established `pages/4_Review.py` precedent; degrades to `""` when offline/not-found) for the diff pane.
- NEW: neardupe_diff.py — pure `build_side_by_side_diff_html(principal_text, member_text, *, context, numlines)`: LINE-based `difflib.HtmlDiff` with intra-line character highlighting (changes shown in surrounding context), a forced white-background + colored-highlight CSS wrapper (theme-independent inside the components.html iframe), empty-input → "" (image-only docs), and a strip of difflib's iframe-breaking fragment nav anchors (the "turtles all the way down" defect). No Streamlit/OpenSearch deps, kept uncached for testability.
- NEW: tests/test_neardupe_clusters.py — 9 tests: cross-cluster fan-out (3), per-document family guard across fan-out, reopen (3: audit-snapshot, decision-preservation, re-approve), review-progress (2). tests/test_neardupe_diff.py — 4 tests (change-marking both sides, identical-no-markers, context-collapses-unchanged, full-mode-renders-all).
- DOCS: DEPENDENCY_MAP.md — register `decided_in_cluster_id`, `reopen_cluster`, `get_near_dupe_review_progress`, `os_manager.get_document_content`, the per-document decision-propagation invariant, and the Review surface's new session-state keys.

### Commit 11 (S-1b γ / C8c) — Dedup Report migration + Production pending-review FYI (2026-05-29)

- CHANGE: db_manager.py — `get_near_dupe_cluster_detail` repointed at the C8a cluster tables (`near_dupe_clusters` + `near_dupe_cluster_members`), replacing the legacy family-`group_id` grouping that never reconstructed similarity clusters. New 12-column shape: `cluster_id, run_date, principal_cn, principal_name, member_count, sim_min, sim_max, review_status, reviewed_by, reviewed_at, confirmed_count, pending_count` (old 5-col `group_id/cluster_size/suppressed_count` shape retired). `get_data_reduction_stats` gains an `nd_pending` field (un-reviewed suppressible cluster members: undecided, non-principal, family-preserved-exempt — mirrors the §11.6 approval-gate denominator); `nd_suppressed` semantic unchanged (= reviewer-confirmed-suppressed post-C8b).
- CHANGE: pages/3_Analytics.py — Dedup Report updated for confirmed-vs-pending semantics across 6 display surfaces: metric card relabeled "Near-Dupe Suppressed" → "Near-Dupe Confirmed" + pending caption; waterfall pending caption; Defensibility Summary narrative reflects confirmed-suppressed-by-attestation + a pending sibling bullet; Suppression Breakdown table row relabeled to "Near-Duplicate Confirmed (Suppressed)" + a new "Near-Duplicate Pending Review" row; cluster-table caption + empty-state corrected from "family" to "cluster". **Excel export "Near-Dupe Clusters" sheet schema changed (12 cols, replaces the prior 5-col family-group_id shape — external-facing).**
- NEW: pages/5_Production.py — non-blocking pending-review FYI above the Run Production button (reads `get_near_dupe_review_progress`; surfaces un-reviewed near-dupe count before burn; does not gate the click).
- NEW: tests/test_neardupe_clusters.py — 6 tests: new helper shape + retired-keys, confirmed/pending counts, family-preserved exclusion from pending, empty-case, `nd_pending` stat field + family exclusion.
- DOCS: DEPENDENCY_MAP.md — register the new `get_near_dupe_cluster_detail` shape, the `get_data_reduction_stats.nd_pending` field, the Production-page `get_near_dupe_review_progress` consumer, and the external-facing Excel schema change.

### Commit 12 (S-1c / C9) — Near-duplicate cluster reporting in the defensibility report (2026-06-01)

- CHANGE: db_manager.py — `get_near_dupe_cluster_detail` gains 2 additive fields (`family_retained_count`, `distinct_count`) → 14-col shape; per-cluster suppressed = `confirmed_count − family_retained_count`. `get_defensibility_dedup` gains 4 fields (`nd_family_retained`, `nd_distinct`, `nd_undecided`, `n_clusters`), all **distinct-document** counts (`COUNT(DISTINCT member_cn)`, classified once by fan-out decision + per-document `MAX(family_preserved)`) so the §4.2 disposition summary reconciles with the tag-based `nd_suppressed` under Flag #30 overlap. `nd_undecided` = ALL undecided (any family state) — deliberately NOT the `fp=0` suppressibility semantic of `get_data_reduction_stats.nd_pending` (kept separate for Analytics).
- NEW: defensibility_report.py — §4.2 "Near-Duplicate Cluster Review & Attestation" section (per-cluster disposition roll-up + reviewer-attestation + Flag #30 multi-cluster footnote) + reviewer-gated §4 narrative paragraph + §4.1 row relabel ("Near-Duplicate Confirmed-Suppressed (reviewer-attested)"); new `_collect_near_dupe_clusters` collector; fallback dict extended with the 4 new keys. Per-row table Pending derived as `member_count − 1 − confirmed − distinct` so each row self-audits.
- NEW: tests/test_neardupe_clusters.py — 2 value tests (`distinct_and_family_counts`; `defensibility_dedup_neardupe_fields` covering all 6 decision×family cells incl. the undecided+family B-2 cell + partition identity); shape test calibrated to the 14-col key set.
- NEW: tests/test_defensibility_neardupe_report.py — render tests (with-clusters / no-clusters placeholder / >200 truncation note) + DB-backed reconciliation test pinning the document-level partition identity under a Flag #30 overlap fixture.
- DOCS: DEPENDENCY_MAP.md — register `defensibility_report.py` as a `get_near_dupe_cluster_detail` consumer (14-col shape), the new `get_defensibility_dedup` disposition fields + §4.2 reconciliation invariant, and the `nd_undecided` vs `nd_pending` distinction.

### Commit 13 (sprint-close addendum) — beta-2.16 close + `v2.16.0` release (2026-06-01)

- RELEASE: config.py / config.example.py — `__version__` 2.15.0 → 2.16.0.
- CHANGE: db_manager.py, defensibility_report.py, neardupe_diff.py, os_manager.py, pages/3_Analytics.py, pages/4_Review.py, pages/5_Production.py, pages/9_InboundProduction.py — `project_ver` header cascade 2.15.0 → 2.16.0 (header-only; no logic change).
- DOCS: archived the C4–C9 audit corpus (31 files) + the C10 preflight/check to `docs/archive/audits/beta-2.16/` with a tier-README; `git mv` the shipped Flag #22 spec to `docs/archive/specs/neardupe_false_positive_sensitivity.md`.
- DOCS: FLAG_REGISTRY.md — Flag #22 moved Active → Closed (C6); Flag #5 Pattern A deferred to beta-2.17; Flag #30 S-1c note; audit-path refs repointed to archive; cross-ref table backfilled C4–C10; Last-audited bumped.
- DOCS: CLAUDE.md Current State table, ROADMAP_TODO.md (beta-2.16 closed + beta-2.17 DB-hygiene seed + Flag #22 bookmark pruned), docs/retrospectives/README.md catalogue, and user-facing docs (Walkthrough / Technical Overview / User_Guide / PROJECT_CONTEXT) for the sprint's user-visible features (Flag #28 inbound search, NearDupe k-gram sensitivity, Cluster Review workflow, defensibility §4.2).

---

## [beta-2.15] — Shipped 2026-05-21 (v2.15.0)

### Commit 8 (sprint-close addendum) — beta-2.15 close + `v2.15.0` release prep (2026-05-21)

- DOCS: docs/retrospectives/beta-2.15.md — sprint retrospective per 6-section template (CLI-drafted at execution time per PM Appendix A nit (c) fallback; content plan in preflight §1.A.1).
- DOCS: docs/archive/audits/beta-2.15/README.md — tier-README indexing 17 archived audit docs + this preflight + 3 CLI check files.
- DOCS: docs/audits/ → docs/archive/audits/beta-2.15/ — 22 mid-sprint files archived (17 preflight + check files for Commits 2/3/4/5/6 plus this Commit 8 preflight + 3 CLI check files + new tier-README). Untracked sources required `mv` + `git add` per `docs/lessons/not-in-git-tracked-not-existent.md` recovery pattern (CLI v1 F-3 catch).
- DOCS: docs/specs/beta_2_15_roadmap_proposal.md → docs/archive/specs/ — spec lifecycle move (sprint executed against it; only M-1 shipped from the spec — M-2/S-tier/N-tier carry forward via ROADMAP_TODO + FLAG_REGISTRY).
- DOCS: docs/specs/family_grouped_native_export_preflight.md — L245 example updated; `git add`'d for the first time (UNSHIPPED status; carries to beta-2.16+ per Q5 disposition).
- DOCS: docs/retrospectives/README.md — catalogue backfill for beta-2.15.
- DOCS: CLAUDE.md — Current State table refresh (5 cells: active branch, project version, last CHANGELOG date, last completed sprint summary, what's next).
- DOCS: docs/FLAG_REGISTRY.md — last-audited annotation refresh + cross-reference table backfill (rows for Commits 1-8 of beta-2.15; Commits 3/4/5 in-place hash backfill per CLI v1 F-1 catch) + path remaps for R2-R5 ref-update sites + numbering history sprint-close entry. Cross-ref backfill scope: beta-2.15 commits only per Q3 Option A; beta-2.12/beta-2.13 drift per beta-2.13 retro §6 L98 stays bookmarked.
- DOCS: tests/test_processing_engine.py — L16 ref-update to archive path (R1 site per Commit 8 preflight §1.B.4).
- CHANGE: config.py + config.example.py — `__version__` bump 2.14.0 → 2.15.0 (Q2 ratified).
- CHANGE: pages/4_Review.py, pages/5_Production.py, pages/6_Sync.py, processing_engine.py, container_exploder.py, universal_imager.py — `project_ver` cascade 2.14.0 → 2.15.0 + `last_modified` refresh per CLAUDE.md Version Tracking rule 5.
- DOCS: ROADMAP_TODO.md — beta-2.15 closed; `beta_2_15_roadmap_proposal.md` bookmark pruned (spec archived); `family_grouped_native_export_preflight.md` + `neardupe_false_positive_sensitivity.md` bookmarks added; beta-2.16 placeholder with carryover priorities added.
- DOCS: Walkthrough.md, Technical Overview.md, User_Guide.md, PROJECT_CONTEXT.md — brief Beta-2.15 update notes per Q4 Brief ratified scope (C3 family-expansion + C5 EML CID + C7 Flag #28 user-visible; C4 PST-as-family-root Technical Overview only).
- RELEASE: v2.15.0 (8 commits: 1 sprint-open + 1 roadmap M-1 + 4 hot patches + 1 docs hygiene commit + 1 sprint-close addendum). Tag identity per Q1 (natural increment from v2.14.0; no skipping). Two lessons canonized this sprint: `docs/lessons/container-family-model.md` (C4) + `docs/lessons/extraction-rendering-symmetry.md` (C5).

### Commit 7 (out-of-roadmap insert) — Review text-search drops inbound hits (2026-05-20)

- FIX: pages/4_Review.py — OpenSearch text-search hits on inbound-production documents were silently dropped from the Review grid. The hit-collection loop read `hit['_id']` and added it to `search_hit_ids`, which is later used as `df['control_number'].isin(search_hit_ids)` to filter the SQL-fetched grid. Internal docs index with `_id = control_number`, but inbound docs index with the volume-prefixed composite `_id = f"{production_volume}-{control_number}"` (per `pages/9_InboundProduction.py:453`). The prefixed string never matched the unprefixed `control_number` column, so inbound content matches surfaced in OpenSearch (banner count incremented) but vanished from the visible grid. Fix reads `_source.control_number` with `_id` as a defensive fallback — works for both inbound and Internal hits.
- NEW: docs/FLAG_REGISTRY.md — registered Flag #28. Symptom patched in this commit; full audit-and-review deferred to a later sprint (cross-codebase scan for other inbound `_id`-vs-control_number mismatches in OS consumer paths, regression test).
- Surfaced during inbound re-ingest testing: a document visibly contained the searched phrase but was absent from the Review grid; OpenSearch direct-query confirmed the doc was indexed and matched the phrase.
- Out-of-roadmap insert; one-line fix shipped without preflight per the maintainer's direction.

### Commit 5 (out-of-roadmap insert) — EML attachment Content-ID over-skip fix (2026-05-18)

- FIX: container_exploder.py — `_explode_eml` no longer over-skips libpff-stamped Content-ID attachments. Replaces the `if part.get('Content-ID'): continue` rule (which silently dropped every PST-extracted attachment because libpff stamps CID on every attachment regardless of inline status) with the new shared `is_part_inline_image(part, html_cids, html_filenames)` predicate. The predicate requires BOTH image type AND actual HTML body reference (CID matched by `<img src="cid:...">` OR filename matched by `<img src="...">`). The previously-redundant filename-skip block at L1370-1377 is subsumed by the predicate and deleted.
- NEW: container_exploder.py — `HtmlInlineRefs` NamedTuple (fields: `filenames`, `cids`) + `is_part_inline_image(part, html_cids, html_filenames)` module-level predicate. Pinned-value source of truth shared by both extraction (`_explode_eml`) and rendering (`universal_imager.convert_eml_to_pdf`) — they cannot disagree about what's inline vs. attachment.
- CHANGE: container_exploder.py — `_collect_html_referenced_images` renamed to `_collect_html_inline_refs` and extended to return both filename refs AND CID refs as the `HtmlInlineRefs` NamedTuple. Previously returned only filename refs; CIDs were implicitly handled by the now-removed over-skip rule.
- CHANGE: universal_imager.py — `convert_eml_to_pdf` aligned with the new inline-image predicate (extraction-rendering symmetry). Pre-scan via `_collect_html_inline_refs` obtains `refs.cids` and `refs.filenames`. The CID-referenced inline-images dict is gated on `cid and cid.strip('<>') in refs.cids` (narrower than predicate, dict-key purposes); filename-referenced inlines are deferred for HTML body substitution; everything else with `disposition='attachment'` lands in `attachment_names` or `html_appendages`. Removes the per-iteration `_is_html_referenced` check from the deferred-resolution block (predicate already verified filename match).
- NEW: tests/test_container_exploder.py — 6 pinned-value tests: 4 predicate unit tests (libpff-attachment-False, CID-referenced-True, filename-referenced-True, unreferenced-image-False) + 2 end-to-end `_explode_eml` tests (libpff-style PST yields children, true inline image is skipped). Regression-pin for the case-wide test-case defect.
- NEW: docs/lessons/extraction-rendering-symmetry.md — durable pattern canonized per Lesson Integration Decision Tree step 4: "When two code paths classify the same thing, they must use the same predicate." Sibling lesson to `container-family-model.md` (Commit 4). Indexed in `docs/lessons/README.md`.
- DOCS: DEPENDENCY_MAP.md — §7 Known Regression Patterns gains "libpff EML attachment over-skip" row pointing at the new lesson.
- DOCS: docs/references/EMAIL_MIME_REFERENCE.md — Gotcha #2 rewritten to mark the obsolete `if part.get('Content-ID'): continue` rule as broken; new Gotcha #7 documents libpff's CID-stamping behavior on every MAPI attachment. Last-updated date bumped.
- NEW: docs/FLAG_REGISTRY.md — registered Flag #27 (.msg-path coverage gap). The .msg path uses MAPI properties (`PR_ATTACH_FLAGS`, `PR_ATTACHMENT_HIDDEN`) rather than Content-ID, so it does NOT share the defect today. Deferred — flag exists so a future .msg-path rewrite remembers to consume the shared predicate.
- Out-of-roadmap insert per the maintainer's discovery during the Commit-4 re-ingest of a test case. DOC-000123.eml visibly contained 2 attachments but the Review grid showed zero family members; case-wide impact: ~1k .eml files, all with `attachment_count > 0` per Tika, all with zero child rows. Connection to Commit 4: this fix is the dependency Commit 4's manual-verification protocol implicitly assumed — the missing children only became observable AFTER Commit 4 made families email-rooted. After Commit 5 lands and the maintainer re-ingests again, Commit 4's email-rooted family model becomes end-to-end observable for the first time.
- Existing-case migration: same as Commit 4 — full delete + re-ingest from raw .pst. The maintainer confirmed (verbatim): "all prior work is broken and useless and a complete re-do is required." Second consecutive full re-ingest in ~3 days acknowledged as cost-of-architectural-correctness.
- Sprint shape: pushed roadmap M-2 to Commits 6-8+; projected sprint length grew from "~9-10 commits" to "~10-11 commits". Heavyweight 8-section preflight per `docs/lessons/preflight-proportionality.md`. Three-revision N-Stage Gate cycle (v1 → v2 → v3 → v3.1, all clean delta-checks); v3.1 was a tiny rename-propagation cleanup CLI flagged out-of-delta-scope in the v3 round and PM patched preemptively. Stage 2 greenlight pre-authorized by the maintainer conditional on a clean v3.1 delta-check ("`feedback_v3_cycle_truncation.md`" precedent — hygiene-low residual under explicit narrow waiver).

### Commit 4 (out-of-roadmap insert) — PST-as-family-root architectural fix (2026-05-15)

- FIX: processing_engine.py — `add_children_to_db` no longer makes archive containers (`.pst`/`.zip`) define a family. Email-level family semantics restored. New module-level constant `ARCHIVE_EXTS = frozenset({'.pst', '.zip'})`. Top-of-family detection rule: `(not parent.group_id) or (parent.group_id == parent_id_str)`. For top-level archive parents, each child is INSERTed with NULL group_id then UPDATEd post-`lastrowid` to its own `DOC-{id:06d}` form (per-child new family). All other parents (emails OR archives nested in an email family) propagate parent's group_id unchanged.
- CHANGE: pages/5_Production.py — `_walk_family_root` helper (and its `# ── Family Hierarchy Helpers ──` section header) deleted. All 4 call sites rewritten to read `group_id` directly: Site #1 (main grid `_family_root`) collapses to `grid_df['_family_root'] = grid_df['group_id']` with the redundant `hierarchy_df` query removed entirely; Site #2 (`affected_roots`) uses `set(base_df['group_id'])`; Site #3 builds `cn_to_group = dict(...)` from a single `SELECT control_number, group_id` query and replaces both the loop iterator and the lookup; Site #4 (`sort_group`) uses `df['group_id']`.
- DOCS: DEPENDENCY_MAP.md — §1 `group_id` row updated to reflect email-rooted family semantics (writer column also updated to name `processing_engine.add_children_to_db` as the ingestion-time writer). §7 "Known Regression Patterns" gains "PST family-collapse via container ingestion" row pointing at the new lesson.
- NEW: docs/lessons/container-family-model.md — durable pattern canonized per Lesson Integration Decision Tree step 4: "Containers don't make families; emails do." Sibling lesson to `family-integrity-over-dedup.md`. Indexed in `docs/lessons/README.md`.
- NEW: docs/FLAG_REGISTRY.md — registered Flag #26 (archive-container coverage beyond .pst/.zip). Deferred until `container_exploder` gains handlers for `.rar`/`.7z`/`.tar`/`.gz`/`.mbox`. Preemptive set expansion would be dead code.
- NEW: tests/test_processing_engine.py — 3 pinned-value tests covering the family-model rule: `test_add_children_to_db_pst_assigns_email_family` (PST top-level → emails get own DOC-id), `test_add_children_to_db_email_propagates` (email parent → attachments inherit), `test_add_children_to_db_nested_archive_in_email_propagates` (PST → email → ZIP → file: innermost file has email's group_id, NOT ZIP's or PST's). Validates §3.1.2 NULL-handling derivation that motivated picking `parent.group_id == parent_id_str` over `parent.parent_id IS NULL` as the top-of-family detector.
- Out-of-roadmap insert per the maintainer's mid-sprint discovery (~500-doc PST exported as one mega-PDF via Review's "Combine families" toggle). Pushes roadmap M-2 (Flag #5 Pattern A consolidation) to Commits 5-7+; sprint-shape projection grows from "~8-9 commits" to "~9-10 commits". Heavyweight 8-section preflight per `docs/lessons/preflight-proportionality.md`. Three-revision N-Stage Gate cycle (v1 → v2 → v3, all clean delta-checks) before Stage 2 greenlight per `docs/lessons/n-stage-gate-revision-handling.md`.
- Existing-case migration: the maintainer chose path (a) — full delete + re-ingest from raw .pst — for the affected test case. Path (b) one-off SQL migration script (~50-80 LOC) deferred until an existing case requires it.

### Commit 3 (out-of-roadmap insert) — Bulk Bates "Include families" toggle + parallel main-search toggle + produced_only UX-filter (2026-05-07)

- NEW: pages/4_Review.py — added `_expand_to_families(matched_cns: set[str], conn) -> set[str]` module-level helper near `_parse_bates`. Two SQL queries: select group_ids from input CNs, then select all CNs sharing those group_ids. NULL/empty group_id passes through unchanged.
- NEW: pages/4_Review.py — added "📎 Include families in results" checkbox to the Bulk Bates popover (key `bates_batch_include_families`). When toggled on, the matched_cns set is expanded via the helper and the success banner reports "Identified M containing documents + K family members (M+K total)."
- NEW: pages/4_Review.py — added parallel "📎 Include families in results" checkbox below the main search input (key `search_include_families`). When toggled on, the dual-search hit set (SQLite + OpenSearch) is expanded and the success message appends "K family members" as a third part.
- NEW: pages/4_Review.py — added "📋 Produced docs only (Bates-stamped)" UX-filter checkbox to the col_filter cluster (key `filter_produced_only_ux`). Conditionally rendered only when `_vis_mode != 'produced_only'` so security-restricted users don't get a no-op widget.
- NEW: pages/4_Review.py — added `_session_produced_only_ux` computed boolean near the `_vis_mode` read site. Composition rule: `_vis_mode == 'produced_only' or _session_produced_only_ux` extends 2 SQL produced_only injection sites: L2496 (main grid base_query) and L3012 (export/STR-helper pre-filter check). Two further sites originally planned in the preflight were excluded mid-execution per the maintainer's Path 1 + Path 3 dispositions — see "Plan deviations" below.
- CHANGE: pages/4_Review.py — Bulk Bates "✖ Clear" handler now also pops `_bates_batch_include_families` from session-state (alongside the existing `_bates_batch_text` and `bates_hit_details` cleanup). The orthogonal `search_include_families` and `filter_produced_only_ux` keys are NOT cleared by this handler — they're per-session user preferences that should persist across Bates batch operations.
- NEW: tests/test_bates.py — added `TestFamilyExpansionHelper` (6 pinned-value tests: empty input, NULL-group passthrough, parent→children expansion, child→parent+siblings, mixed-group independence, NULL-orphan non-clustering) plus a new `family_expand_case` fixture seeding two families with explicit group_id columns. Mirrors the production helper inline per the project's test-inlining-by-design convention (beta-2.14 C13 / Flag #16 WONTFIX).
- NEW: tests/test_bates.py — added `TestProducedOnlyUXFilter` (5 pinned-value tests covering the 4 user×toggle quadrants of the gate logic plus the SQL-composition compose-with-family-expansion end-to-end). Pure-logic tests where possible; one DB-backed end-to-end test exercises the family-expand-then-filter pipeline.
- Test count: 237 → 248 (11 new). Full suite passes.
- Out-of-roadmap insert per a mid-sprint reviewer workflow ask (a Bates batch needing family expansion). Pushes roadmap M-2 (Flag #5 Pattern A consolidation) to Commits 4-6+; sprint-shape projection grows from "~7-8 commits" to "~8-9 commits". Preflight ratified at v2 with bundled scope (Option A + Feature 2 produced_only-UX-filter under the maintainer gate-keeper override per `feedback_v3_cycle_truncation.md` precedent). Audit-bookmark commitment per preflight §6.8: a future scoped audit (`docs/templates/scoped_audit_template.md`) will verify the security/UX filter primitives stay distinct, all 4 SQL sites consistently honor both gates, no regression in restricted-user path, and widget-render gate stays in sync with SQL-injection gates.
- Stale `project_ver` refresh on `pages/4_Review.py` (2.12.0 → 2.14.0) per the C4/C5/C3a-followup incidental-fix precedent. File version bumped 1.33.3 → 1.34.0 (MINOR — new helper + 3 new features).
- NEW: docs/FLAG_REGISTRY.md — registered Flag #25 ("`pages/4_Review.py` STR view branch (L335-628) references `_vis_mode` at L438/L450 before module-level assignment at L1459 — undefined-name when STR view is active") in the Active table per the registry's "register at the discovering commit" rule. State: Active / Deferred. Sprint origin: beta-2.15 Commit 3 mid-execution finding. Pre-existing latent bug since beta-2.7c; CLI surfaced it while attempting to extend L438/L450 with the produced_only UX-filter and discovered both `_vis_mode` and the new `_session_produced_only_ux` would be undefined when the STR Run button is clicked. Deferred to a future commit dedicated to STR scope hygiene (likely fix: hoist `_doc_visibility = auth_manager.get_doc_visibility(_username); _vis_mode = _doc_visibility['mode']` into the STR view branch top, after L335). Master numbering history updated; cross-reference table appended.
- Pre-flight check executed under Path B (gate-keeper waiver per `feedback_v3_cycle_truncation.md`): 4 hygiene findings (count predictions in §1.1/§5.2/§8.1) waived with observed counts substituted in this entry — actual baseline grep on the 6-stem regex `_bates_batch_text|_bates_batch_override|matched_cns|_family_override_gid|_search_include_families|filter_produced_only_ux` was 16 pre-fix (PM cited 21, transposed from §8.1 row 11's 5-stem regex which correctly counted 21 with `_family_override_group_id` included); `show_suppressed|hide_junk|hide_not_responsive` was 7 hits not 9 (3 widget defs + 4 application sites); `family_case` fixture lives in `tests/test_bates.py:278` not `tests/conftest.py`; pytest baseline was 237 not 231. PM-judgment findings (J-1 file-proximity hazard-class verdict, J-2 `feedback_v3_cycle_truncation.md` precedent extension) flagged for self-awareness; the maintainer reaffirmed the §6.8 override.
- Plan deviations from the v2 preflight (all surfaced mid-execution and ratified by the maintainer in dedicated messages):
  1. **L2717 (Option 1 reroute):** preflight §1.1 listed L2717 as 1 of 5 SQL gate-extension sites; CLI verified at execution that L2717 is a UI banner (`st.caption("🔒 Your view is restricted to produced (Bates-stamped) documents.")`) not a SQL filter. Extending it would fire admin-imposed-restriction wording when a user voluntarily toggled the UX-filter. The maintainer's Option 1: skip L2717, do not add a separate UX-toggle banner — the widget itself in the col_filter cluster is the on/off indicator. Net effect: no banner regression, no semantic conflation.
  2. **L438, L450 (Path 3 reroute):** while extending these STR-view sites, CLI discovered `_vis_mode` is referenced at L438/L450 (inside the STR view body L335-628 which `st.stop()`s at L628) but only assigned at L1459 — pre-existing scope bug since beta-2.7c. Extending would add a second undefined name (`_session_produced_only_ux`) to the same broken expression. The maintainer's Path 3: roll back the L438/L450 extensions (preserve pre-existing latent bug as-is), register the bug as Flag #25, defer the fix to a future dedicated commit. Discipline note: this is a pre-flight check miss — CLI verified the line content but didn't analyze whether the variables were in scope at those references; the Option 1 + Path 3 catches at execution time were a partial save.
  3. **Final SQL extension scope: 2 sites, not 5 (preflight §1.1) or 4 (Option 1 plan).** Composing-filter primitive (`_vis_mode == 'produced_only' or _session_produced_only_ux`) lands at L2496 (main grid base_query) and L3088 (export/STR-helper pre-filter check, post-edit line). STR view scope (L438/L450) deferred to Flag #25; banner site (L2717) excluded by design. The composing-filter contract per preflight §3.3 is unchanged in semantics — just scoped to the surfaces where `_vis_mode` is reliably in scope.

### Commit 1 — Sprint-open hygiene (2026-05-06)

- DOCS: docs/specs/beta_2_15_roadmap_proposal.md — added N-5 (Auto-Memory Hygiene Sweep Standing Order) to the nice-to-have tier, raising the sprint to 11 items across 4 priority tiers. Inspired by Anthropic Managed Agents "Dreams" research preview (2026-04-21 beta); proposes a sprint-close PM-side dedup/reorg pass over the gitignored auto-memory directory with the maintainer's ratification gate on ARCHIVE/DELETE actions. First-pass execution at sprint-close is the discriminating test of whether the Standing Order is well-shaped.
- DOCS: ROADMAP_TODO.md — refreshed line 2 staleness (was "2026-04-30 — beta-2.14 branch (sprint wrapping), version 2.12.0 (v2.14.0 tag pending sprint-close)"; now "2026-05-06 — beta-2.15 branch (sprint open), version 2.14.0"). Branch is now beta-2.15, beta-2.14 closed at v2.14.0 on 2026-04-30.
- DOCS: CHANGELOG.md — added `## [beta-2.15] — In Progress` section heading at the top per newest-first convention.

### Commit 2 (roadmap M-1) — Flag #5 Class B sub-span A — 6_Sync.py:328, 341, 354 (2026-05-06)

- FIX: pages/6_Sync.py — Class B Pattern-X hardening at 3 SYNC_ERROR audit sites in `sync_pending_documents` followed by `continue` (API S3 Auth Failed L328 / S3 Upload Failed L341 / Finalize Failed L354 — pre-fix line numbers per preflight). At each site, threaded `conn=conn` on the `log_audit` call AND inserted a new `conn.commit()` line immediately after the audit's `try/except` and before `continue`. The added commit is necessary, not redundant: under naive `conn=conn`-only, the staged UPDATE+audit pair would roll back at function-exit conn-GC on the loop's final iteration (the next reachable commit lives in the NEXT iteration's L390/L420 gate, never reached). Outside-try/except placement guarantees the UPDATE commits whether the audit raised or was swallowed by the never-raise contract.
- Stale `project_ver` refresh on `pages/6_Sync.py` (2.12.0 → 2.14.0) per the C4/C5/C3a-followup incidental-fix precedent.
- Closes Class B sub-span A — the 3 sites C3a-followup explicitly deferred for commit-restructuring complexity. Cumulative beta-2.14+beta-2.15 progress on Flag #5: 12 Pattern-X-or-C sites hardened across 4 commits (3 from C3a + 4 from C3a-followup + 2 from C3b + 3 from this commit). Pattern Y (Class C) sites at L311 and L392 intentionally left as separate-conn (audit-after-commit and warning-on-commit-failure semantics; `conn=conn` would regress both). Flag #5 stays Active until M-2 Pattern A consolidation lands.
- No new tests: caller-owned-conn contract pinned by `tests/test_db.py::TestAuditLog::test_log_audit_with_provided_conn_does_not_commit` (added beta-2.14 C2). Same rationale as C3a-followup — the contract this fix relies on is already pinned.

---

## [beta-2.14] — Shipped 2026-04-30 (v2.14.0)

### Sprint-open — beta-2.13 sprint-close addendum (2026-04)

- DOCS: First commit on beta-2.14 is the beta-2.13 sprint-close addendum (retrospective + audit archival + context maintenance). See `## [beta-2.13]` section below for full content. Pattern: when a sprint closes informally, the addendum lands as Commit 1 on the next branch. Sprint-numbering carries forward — beta-2.14 roadmap commits start at C2 (C1 slot orphaned to preserve C2–C8 mental-model continuity for the deferred Flag #18 → #5 → #16 → #13 → PM-grep-discipline → cleanup-audit → sprint-close roadmap).

### Sprint-open hygiene — `edit-tool-staging-gap` lesson canonization (2026-04-28)

- DOCS: docs/lessons/edit-tool-staging-gap.md — new lesson canonizing the `Edit`/`Write` tool staging behavior + pre-commit verification rule. Triggered by execution-tier staging-gap defect surfaced in beta-2.14 Commit 1 (sprint-close addendum) Phase 11 status check — five files (1 untracked `Write` output + 4 unstaged `Edit` outputs) missed the staging area pre-commit and required `git commit --amend` recovery. Lesson establishes `git status --short` leading-space-`M` and `??` scan as mandatory pre-commit verification.
- DOCS: docs/lessons/README.md — added `edit-tool-staging-gap.md` catalogue entry to the "Workflow discipline" section.

### Commit 3 (roadmap C2) — Flag #18 narrow `conn=None` scaffolding (2026-04-28)

- FIX: db_manager.py — added `conn=None` keyword parameter to `log_audit`, `log_audit_batch`, `get_privilege_status`, `set_privilege_status`. When provided, the caller's connection is reused and the function does not commit/close; when None (default, preserves existing behavior), the function opens, commits if applicable, and closes its own connection. Flag #18 narrow scaffolding for the 6 of 9 latent-risky page-held-conn sites in Pattern B + the 4_Review.py:3243 Pattern C site. Backwards-compat: all 14 existing consumer files unchanged. Call-site updates that actually reuse the parent conn land at C3a (Pattern B sites) + C3b (Pattern C site + transitive-wrapper helper threading).
- NEW: tests/test_db.py — `TestPrivilegeStatusConnOwnership` class (4 tests) + augmented `TestAuditLog` (3 tests) pinning the caller-owned-conn contract. Cross-conn-visibility test exercises SQLite WAL semantics to prove the no-commit-when-caller-owns claim.
- DOCS: db_manager.py — expanded docstrings on the 4 functions documenting `conn` parameter semantics + caller-owned-transaction contract; the `log_audit` docstring also documents the silent-partial-write hazard when a caller-provided conn fails mid-INSERT.

### Commit 4 (roadmap C3a) — Flag #5 log_audit Pattern-X hardening (2026-04-28)

- FIX: pages/2_Processor.py — pass `conn=conn` at 2 nested log_audit calls in `_delete_descendants` recursion + `re_extract_container` parent flow (CONTAINER_CHILD_DELETED L198, CONTAINER_CHILDREN_DELETED L240). Audit rows now stage into the parent's transaction and commit atomically with the DELETE writes at L253. Eliminates today's phantom-audit-on-rollback behavior (where descendant audits would commit independently even if the parent re-extract failed) AND closes the silent-drop hazard under WAL write-lock contention.
- FIX: pages/7_Custodians.py — pass `conn=conn` at the HOLD_DOCUMENT_UPLOADED log_audit at L704. Audit row now stages into the per-loop-iteration's INSERT and commits atomically with the L713 batch commit. Eliminates today's 3-way file/DB/audit mismatch on rare commit failure (file-on-disk + no-DB-record + phantom-audit) in favor of a 2-way mismatch (file-on-disk + no-DB-record-and-no-audit) that's more honestly recoverable.
- Closes 3 of ~9-10 Pattern-X (audit-mid-transaction) hazard sites identified by PM survey 2026-04-28. Sub-span A in 6_Sync.py:311-414 (sync_pending_documents loop, 6-7 likely-Pattern-X calls) deferred to separate analysis due to loop-control complications. Pattern Y sites (the dominant codebase pattern: audit-after-commit) intentionally left unchanged — naive `conn=conn` would cause rollback at those sites. Flag #5 stays Active until sub-span A follow-up + Pattern A consolidation land.

### Commit 5 — Flag #24 fix: log_audit `user=` kwarg typo (2026-04-28)

- FIX: pages/7_Custodians.py — replace `user=_username` with `username=_username` at L545 (COLLECTION_SCOPE_UPDATED log_audit call). The typo caused TypeError silently swallowed by surrounding `try/except Exception: pass`, so this audit class has never written to audit_log since the code was authored. Defensibility gap closed prospectively (past changes remain unaudited).
- FIX: home.py — replace `user=` with `username=` at L761 (INTEGRITY_VERIFICATION audit) and L807 (NIST_CONFIG_UPDATED audit). Same defect class as 7_Custodians.py:545. Audits will now write going forward.
- DOCS: docs/FLAG_REGISTRY.md — register Flag #24 (log_audit `user=` kwarg typo) directly in Dormant/Closed table since the fix ships in same commit. PM grep-sweep 2026-04-28 confirmed bounded scope: 3 of 156 log_audit calls affected; not systemic. Numbering history + Last-audited comment refreshed.

### Commit 6 (roadmap C3a-followup) — Flag #5 log_audit Pattern-X hardening, sub-span A (2026-04-28)

- FIX: pages/6_Sync.py — pass `conn=conn` at 4 Pattern-X log_audit calls in `sync_pending_documents` (FILEVINE_PUSH success L374; SYNC_ERROR Collection Map Failed L380; SYNC_ERROR Token Expired L405; SYNC_ERROR generic L414). At each site, the audit row now stages into the parent's transaction and commits atomically with the corresponding UPDATE write at the same-iteration commit gate (L390 for Sites 1+2; L420 for Sites 3+4). Eliminates today's phantom-audit-on-rollback behavior (where audits would commit independently even if the parent commit failed) AND closes the silent-drop hazard under WAL write-lock contention.
- Stale `project_ver` refresh on `pages/6_Sync.py` (2.9.0 → 2.12.0) per the C4/C5 incidental-fix precedent.
- Closes 4 of ~7 remaining Pattern-X (audit-mid-transaction) hazard sites identified by PM survey 2026-04-28. Cumulative beta-2.14 progress on Flag #5: 7 of ~10 Pattern-X sites hardened (3 from C3a + 4 from C3a-followup). Class B sub-span A sites (3 calls in `6_Sync.py:328, 341, 354` — error paths followed by `continue`) deferred — they require commit-restructuring rather than the kwarg-addition fix pattern (last-iteration regression risk if naive fix applied). Pattern Y sites (audit-after-commit, the dominant codebase pattern) intentionally left unchanged. Flag #5 stays Active until Class B follow-up + Pattern A consolidation land.

### Commit 7 (roadmap C3b) — Flag #5 Pattern C hardening: privilege_status nesting in `_bulk_apply_op` (2026-04-28)

- FIX: pages/4_Review.py — pass `conn=_conn` at 2 nested privilege_status calls inside the `_bulk_apply_op` closure (`get_privilege_status` L3287; `set_privilege_status` L3292). Both calls now stage into the closure's transaction and commit atomically with the surrounding tags UPDATE writes at the L3301 batch commit. Eliminates three failure modes the prior separate-conn behavior produced: out-of-order partial state on commit failure (tags rolled back, privilege already committed); mid-loop exception phantom state (iterations before the exception left privilege_status changes durable while tags rolled back); silent-drop OperationalError under WAL write-lock contention.
- Closes the Pattern C sub-surface of Flag #5 (privilege_status nesting). PM grep-sweep 2026-04-28 confirmed no other Pattern C sites in the codebase: 22 call sites of get_privilege_status / set_privilege_status / get_privilege_tag_members / get_production_categories examined across `pages/4_Review.py`, `pages/5_Production.py`, `pages/6_Sync.py`; only the 2 calls inside `_bulk_apply_op` sit inside a held-conn write-loop context. Transitive-wrapper threading on `get_privilege_tag_members` and `get_production_categories` deferred — no current Pattern C hazard surface justifies adding API parameters proactively.
- Cumulative beta-2.14 progress on Flag #5: 9 Pattern-X-or-C sites hardened across 3 commits (3 from C3a + 4 from C3a-followup + 2 from C3b). Remaining: 3 Class B sub-span A sites in `6_Sync.py:328, 341, 354` (deferred — commit-restructuring required) + Pattern A consolidation surfaces (deferred to beta-2.15+). Flag #5 stays Active.

### Commit 8 — Docs hygiene (2026-04-28)

- DOCS: documentation hygiene pass; CLAUDE.md Current State table trimmed. No code behavior change; pytest baseline 228/228 holds.

### Commit 9 (C8a) — CHANGELOG wording fix (2026-04-28)

- DOCS: CHANGELOG.md — Commit 8 entry wording tightened.

### Commit 10 (roadmap C5) — Flag #13 aborted-run UX render hygiene (2026-04-30)

- FIX: home.py — Production History grid (lines 553-568) extends column selection to include `status`, adds `'status': 'Status'` to the rename map, and applies `fillna('—').replace({None: '—'})` on the `First Bates` and `Last Bates` columns. Aborted runs (status='aborted') now surface in the paralegal-visible grid with `—` for Bates fields and `aborted` under a new Status column instead of the literal Python string `None`. Doc count continues to show `0` for aborted (correct schema state, not a defect).
- FIX: defensibility_report.py — `_render_html` section 6.2 "Production Run History" filters out `status='aborted'` rows before iteration. The pre-filter `_pr_runs_visible` list also drives the section-header guard (`if _pr_runs_visible:`), so a case with only aborted productions renders cleanly with the upstream "No productions have been completed for this matter" fallback rather than producing a half-empty `<table>` artifact. Court-facing PDF stays clean of internal process churn — the maintainer's Stage 1 decision: aborted runs are not material to opposing counsel.
- FIX: pages/5_Production.py — `_render_post_finalization` Bates Range banner (lines 644-649) replaces `run_info.get('bates_start', '—')` and `run_info.get('bates_end', '—')` with the project-convention `(value or '—')` idiom. Defensive — finalized runs always have Bates fields set, but the buggy `.get(key, default)`-vs-None idiom no longer lives in the file.
- NEW: tests/test_production_history_outbound_filter.py — `TestAbortedRunRenderContract` class (3 tests) pinning the asymmetric render contract: aborted rows (1) seed with NULL bates fields per the schema/writer path, (2) appear in home.py grid with `—` for Bates and `aborted` for Status (no literal `None` string anywhere in the rendered grid), (3) are excluded from defensibility section 6.2 iteration. Existing `case_with_mixed_runs` fixture already seeds Volume_003 with `status='aborted'` and missing bates fields → no fixture extension needed.
- Stale `project_ver` refresh on `defensibility_report.py` (2.9.0 → 2.12.0) and `pages/5_Production.py` (2.9.0 → 2.12.0) per CLAUDE.md §Version Tracking rule 5 (touched-file project_ver must match `__version__` in config.py). Aligns with the C4/C6 incidental-fix precedent.
- Closes Flag #13 (aborted-run UX render hygiene). Root cause: `dict.get(key, default)` returns the value when the key exists with a `None` value (SQLite NULL → `sqlite3.Row` → `dict` always produces this) — `default` only triggers when the key is missing. f-string then renders the `None` value as the literal four characters. Asymmetric fix: home.py grid (forensic record) gets render hygiene + Status column; defensibility PDF (court-facing) gets exclusion filter; 5_Production.py banner gets defensive substitution.

### Commit 11 (roadmap C6) — PM grep-count discipline canonization (2026-04-30)

- NEW: docs/lessons/grep-count-discipline.md — canonizes 5 empirical defect-class observations from beta-2.14 sprint cycles (C7 Pattern X audit's prose-total-vs-line-list + chain-of-counts; rename-sweep word-boundary regex over-strictness + scope-expansion stale-references; C5/Commit 10's per-line-vs-per-token distinction). Three failure-mode families: wrong-granularity counts (per-row vs per-call; per-token vs per-line), stale count rot (chain-of-counts; scope-expansion), incomplete inventory (over-strict regex word boundaries). 5-section template per the canonical `docs/lessons/` structure.
- DOCS: docs/templates/preflight_drafting_checklist.md — install Check 11 (Grep-count cross-verification) between current Check 10 and the "Final check" closing section. Operational version of the lesson's discipline; one-line pointer to the lesson body for the canonical why + sprint examples. "When this checklist was installed" footer updated to attribute Checks 1–10 to beta-2.11 Commit 8 install and Check 11 to beta-2.14 C6.
- DOCS: docs/templates/preflight_template.md — add Check 11 row to §8.1 PM Drafting-Checklist Ledger (heavyweight 8-section template). Bundling Check 11 into both heavyweight + lightweight ledgers preserves the consistency invariant — preflight authors reference the same 11-item ledger regardless of template choice.
- DOCS: docs/templates/preflight_lightweight.md — add Check 11 row to §Appendix A PM Drafting-Checklist Ledger (lightweight 3-section template).
- DOCS: docs/lessons/README.md — add grep-count-discipline.md row in topical position adjacent to the related grep-by-stem-not-spec-name.md entry under "Workflow discipline" section. The section is organized topically, not alphabetically (CLI v1 caught this framing in the preflight before v3 patched the prose).
- Recursive-meta-record: the canonization preflight itself surfaced a fresh instance of the lesson's "incomplete inventory" defect class — PM's v3 self-sweep used `grep -nE "alphabetical position"` but missed cousin phrasings (`alphabetical order` / `alphabetical sort` / `alphabetical convention`) at the preflight's L289 + L316. CLI v2 caught both; the maintainer's ratified inline mechanical patches at execution time. The lesson's two identified failure modes (chain-of-counts and incomplete-inventory) interact rather than being independent — a chain-of-counts sweep using a too-tight pattern can leave cousin phrasings stale. The preflight's §0.1 v3 row preserves this as forensic evidence for future canonization rounds.
- No code changes. No flag closes. Doc-only canonization commit using the lightweight 3-section preflight template per `docs/lessons/preflight-proportionality.md`.

### Commit 12 (roadmap C7) — Beta-2.15 cleanup-audit roadmap proposal (2026-04-30)

- NEW: docs/specs/beta_2_15_roadmap_proposal.md — beta-2.15 sprint plan authored as a forward-looking spec. Enumerates 10 candidate items across 4 priority tiers (2 must-do + 3 should-do + 4 nice-to-have + 1 defer-further) with a unifying sprint thesis: Flag #5 closeout + analytics quality (Flag #22) + canonization continuation. Sprint shape proposal targets ~7-8 commits + sprint-close addendum. Sprint exit criteria pinned to FLAG_REGISTRY state transitions on Flag #5 + Flag #22.
- DOCS: ROADMAP_TODO.md — "Last updated" header refreshed from "2026-04-18 — beta-2.11 branch, version 2.11.0" to current state. Bookmark to the new spec inserted under §Active Specs §Unshipped (now 6 entries) following the existing topical-position convention.
- The maintainer 2026-04-30 dialog explicitly delegated ROADMAP_TODO.md drafting authority — "either you or CLI (whichever is proper) updates the roadmap. I review, you guys can write." Per `docs/roles/pm_claude.md` write boundaries, PM cannot write to ROADMAP_TODO.md directly even with the maintainer's blanket delegation; CLI executes the patch.
- Inline H-1 correction during execution per Stage 2 narrow waiver: spec's predecessor-sprint count corrected from "11 substantive commits + sprint-close addendum" to "12 substantive commits + sprint-close addendum" (treats C7 as substantive, which it is — the spec authoring is a substantive deliverable, not housekeeping). Comparable line in Sprint shape proposal updated to match. Self-application of Check 11 (grep-count cross-verification, freshly canonized in C6).
- No code changes. No flag closes. Doc-only sprint-planning artifact using lightweight 3-section preflight template per `docs/lessons/preflight-proportionality.md`.

### Commit 13 (roadmap C8) — Beta-2.14 sprint-close addendum (2026-04-30)

- NEW: docs/retrospectives/beta-2.14.md — sprint retrospective per CLAUDE.md §Sprint-Close Retrospective Standing Order. 6-section template (Sprint Scope / What Shipped / Goals vs. Outcomes / Surprises and Learnings / Lessons Canonized / Gotchas for Future Sprints) + Provenance footer. Captures Pattern X / Pattern C closure (9 sites hardened); C8a off-roadmap insertions; C6 canonization with three surfaced observations (sprint-mis-cite verification, cluster-interaction defects, predecessor-count-self-increments); beta-2.15 spec authoring. §6 Gotchas folds in the C13 v1→v3 + H-5 recursive-irony observation as the fourth empirical recurrence of the cluster-interaction defect class.
- NEW: docs/archive/audits/beta-2.14/ — tier directory with README index + 35 archived audit files (32 from Commits 2-12 preflights + check rounds + this commit's preflight + 2 CLI delta-check rounds). Per CLAUDE.md §Audit-Doc Archival at Sprint Close Standing Order. Tier-README documents the chain-of-moves convention.
- DOCS: All 35 audit files moved from docs/audits/ to docs/archive/audits/beta-2.14/. The audit docs were untracked-but-existing per the not-in-git-tracked-not-existent lesson; recovery via `mv + git add` (history preservation forfeit; new files in archive). Living-doc ref grep returned 0 matches — no living-doc references to docs/audits/commit_*. paths needed updating.
- FIX: config.py + config.example.py — `__version__ = "2.12.0"` → `__version__ = "2.14.0"` (skip 2.13.x per the maintainer's decision; beta-2.13 closed informally without a v2.13.0 tag, and the substantive 12-commit beta-2.14 sprint is recognizably 2.14.x scope rather than a 2.13.x continuation). Dual application — config.py (gitignored; local) + config.example.py (tracked; template) per the not-in-git-tracked-not-existent lesson's gitignored-source recovery pattern.
- DOCS: CLAUDE.md — Current State table refresh. Active branch flips to `main` (post-merge framing); Project version 2.12.0 → 2.14.0; Last CHANGELOG date 2026-04 → 2026-04-30; Last completed sprint paragraph rewritten to summarize beta-2.14's 12-commit arc + this addendum; What's next replaces the beta-2.13/2.14 carryover description with a pointer to docs/specs/beta_2_15_roadmap_proposal.md.
- DOCS: CHANGELOG.md — Flag #23 fix: section ordering inversion. The `[beta-2.13]` block at lines 8-82 was incorrectly above `[beta-2.14]` (newest-at-top convention violated). Block relocated to immediately AFTER `[beta-2.14]`. The L87 prose reference "See `## [beta-2.13]` section above for full content." flipped to "section below" to match the new ordering. Also: `[beta-2.14]` heading converted from "In Progress" to "Shipped 2026-04-30 (v2.14.0)".
- DOCS: docs/FLAG_REGISTRY.md — Flag #16 moved from Active to Dormant/Closed (WONTFIX 2026-04-30 per the maintainer's confirmation; test-inlining-by-design as regression-snapshot decoupled from production drift; cross-file consolidation would defeat the broader inline-mirror convention). Flag #23 registered + closed in same commit (CHANGELOG section ordering inversion fix); register-and-close pattern matching Flag #24 precedent. Numbering history block updated. `<!-- Last audited: -->` comment bumped to 2026-04-30.
- DOCS: docs/retrospectives/README.md — catalogue backfill: beta-2.14 entry added with one-line summary linking to docs/retrospectives/beta-2.14.md.
- DOCS: Walkthrough.md, Technical Overview.md, User_Guide.md, PROJECT_CONTEXT.md — brief 1-5-line updates per doc capturing the Flag #13 asymmetric Production History UX changes (home grid Status column + `—` rendering for aborted runs; defensibility PDF section 6.2 excludes aborted runs entirely).
- Self-archive: this preflight (`commit_13_beta214_sprint_close_addendum_preflight.md`) + its 2 CLI delta-check reports (v1 + v2) archive in this same commit.
- Inline H-5 mechanical patch during execution per Stage 2 narrow waiver: §Appendix A check 7 + check 11 ls-citation and arithmetic corrected (32 + 1 + ≥2 = ≥35 files moved; ≥36 in archive). The H-1 through H-5 recursive-irony observation folded into the retrospective §6 Gotchas as additional empirical evidence for the bookmarked beta-2.15 N-1/N-2/N-3 observations.
- Tag-cut ordering protection: per `docs/lessons/premature-release-tag.md`, the `v2.14.0` tag is NOT cut in this commit. Post-commit ops (ff-merge to main → tag cut → push main → push tag) happen separately under the maintainer's instruction.

---

## [beta-2.13] — Shipped 2026-04 (informal close — no git tag cut)

### Sprint-open migration — PM Claude Cowork → WARP two-tab model (2026-04)

- NEW: docs/roles/ — new tier directory for role definitions in the two-WARP-tab collaboration model.
- NEW: docs/roles/README.md — tier index explaining the two-tab split, the migration rationale (Cowork sandbox environmental-observation failures), and role-activation mechanics.
- NEW: docs/roles/pm_claude.md — PM Claude role definition: preflight drafting, architectural review, grep-count discipline, three-criteria scope probes, write-scoped to docs/audits/ + docs/specs/ + _scratchpad/ + memory directory.
- NEW: docs/roles/execution_cli.md — Execution CLI role definition: pre-flight checking, execution under Stage 2 greenlight, post-execution verification, sprint-close Tag-cut ordering execution.
- NEW: .claude/commands/pm.md — `/pm` slash command that activates PM Claude role (reads docs/roles/pm_claude.md + loads project priors).
- NEW: .claude/commands/cli.md — `/cli` slash command that activates Execution CLI role (reads docs/roles/execution_cli.md + loads project priors).
- DOCS: CLAUDE.md — added docs/roles/README.md row to Dependency API References pointer table.
- DOCS: cleaned untracked PM-Cowork diagnostic detritus from docs/ root (docs/TEST_FILE.md, docs/test_dir_a/, docs/xyzzy/) — three files/dirs left behind during PM-Cowork's "phantom directory" misdiagnosis while drafting the Flag #20 preflight.

### Role + collaboration-workflow hygiene pass (2026-04)

Doc-only sweep landing 14 findings surfaced by PM's first post-WARP-migration review of the role files and collaboration workflow. No code touched.

- DOCS: docs/templates/pm_cli_collaboration_workflow.md — fix Stage-2-issuer contradiction (the maintainer issues Stage 2, not PM); §5.2 pre-flight check report persistence to `docs/audits/commit_N_*_check_v<N>.md`; §5.2 N/A-for-lightweight notes on scope items 3 and 6.
- DOCS: docs/lessons/n-stage-gate-revision-handling.md — flow diagram + PM-response skeleton updated so Stage 2 issuer matches role definitions (the maintainer, not PM).
- DOCS: docs/FLAG_REGISTRY.md — inline maintenance rule reconciled to match `docs/roles/pm_claude.md` write boundary (CLI-maintained; PM proposes new flags via preflight or auto-memory, CLI adds the row at commit time).
- DOCS: docs/roles/pm_claude.md — added precedence statement (CLAUDE.md Standing Orders win on conflict); inline maintainer-scope-expansion reciprocal pattern; PM veto authority over Stage 2 (rare but allowed); `_scratchpad/` ephemeral-only discipline; ledger location canonized to §8.1 / §Appendix A.
- DOCS: docs/roles/execution_cli.md — added precedence statement; manual-approve-mode operational preference; pre-flight check report persistence + minimum skeleton (Blocking / Hygiene / PM-judgment severities).
- DOCS: docs/roles/README.md — added "Bridging conventions" section documenting how the maintainer operates the PM↔CLI bridge (filesystem is load-bearing, tab scrollback is not).
- DOCS: docs/templates/preflight_template.md — added §8.1 PM Drafting-Checklist Ledger stub (canonical location per role definition).
- DOCS: docs/templates/preflight_lightweight.md — added §Appendix A PM Drafting-Checklist Ledger stub (lightweight variant with common N/A markers).
- DOCS: .claude/commands/pm.md, .claude/commands/cli.md — slimmed to pointers deferring to role files for the priors list; eliminates drift risk between slash commands and role definitions.
- DOCS: CLAUDE.md — Sprint-Close Retrospective Standing Order: codified authorship lane (PM drafts by default; CLI fallback during sprint-close addendum commit; retrospective lands in sprint-close commit subject to archival/Tag-cut rules either way).

### Commit 1 — Flag #20: COALESCE enddoc in document_productions backfill (2026-04)

- FIX: db_manager.py — replace `d.enddoc` with `COALESCE(d.enddoc, d.begdoc)` in the one-time document_productions backfill SELECT (Flag #20). Closes the INSERT OR IGNORE silent-drop surface for single-page outbound documents with populated begdoc + NULL enddoc. Pre-fix damage on already-affected case DBs is NOT retroactively healed — sentinel (`_dp_count == 0`) skips the backfill on next init_db.
- FIX: db_manager.py — add pre-INSERT `_eligible` source-row count + post-INSERT `_dropped = _eligible - _backfilled` diff; emit `logger.warning` on nonzero drop count. Canary against future silent-drop reintroductions (schema changes, concurrent writes, new constraint classes). Pinned-value discipline: `_eligible` SELECT's WHERE clause is character-identical to the INSERT's WHERE clause.
- NEW: tests/test_document_productions_inbound_filter.py — `test_backfill_recovers_documents_with_null_enddoc` asserts COALESCE behavior via raw SQL INSERT that bypasses the fixture helper's defensive `enddoc=begdoc` default (which had been masking the bug). Regression pin.
- DOCS: docs/FLAG_REGISTRY.md — move Flag #20 row from Active to Dormant/Closed; bump Last-audited comment to 2026-04 (beta-2.13 Commit 1, Flag #20 closed).

### Hotfix — Bulk Bates popover filter not applied to Review grid (2026-04)

- FIX: pages/4_Review.py — Bulk Bates Batch Search: extend the Document Grid filter guard from `if search_query and search_hit_ids:` to `if (search_query and search_hit_ids) or bates_batch_text:`. The original guard short-circuited on bates-batch-only searches (where the user populates the Bulk Bates popover but leaves the main search text input empty), so the success banner reported the matched subset (e.g. "Identified N containing documents") while the grid continued to render every document in the case. The new guard preserves the existing OpenSearch-offline fallback on the text-search path and narrows zero-hit bates batches to an empty grid instead of falling back to all docs.

### Hotfix — Paperclip-attachment click stomped by persistent grid selection (2026-04)

- FIX: pages/4_Review.py — Family & Related Items attachment / parent buttons: when the target doc is filtered out of the current queue, the handler enters peek mode (`_peek_cn = target_cn`) and reruns. On that rerun, Streamlit's `st.dataframe` persists its prior selection state, so the grid's single-selection handler at line 2940 re-fires with stale `selected_rows`, runs the "grid click exits peek mode" branch, and pops `_peek_cn` before the viewer at line 3452 reads it — leaving the user on the original document instead of the peeked attachment. Two changes close the hole: (1) the peek branches now set `family_nav = True` alongside `_peek_cn` so the grid handler recognises that the re-fire is spurious; (2) the grid handler moves the `_peek_cn` / `_peek_return_idx` pop inside the `not family_nav` guard so peek state survives a family-button rerun. Pre-existing symptom: clicking the paperclip attachment button in the Family panel did nothing; first click worked only after a "Show Full Family in Grid → Back to search results" round-trip (which rewrites the SQL and implicitly clears the dataframe's selection state, giving the paperclip a clean grid on the next rerun). Predates the beta-2.13 Bates-batch work.

### Sprint hygiene — Flag #22 registration + neardupe spec tracked (2026-04)

- NEW: docs/specs/neardupe_false_positive_sensitivity.md — unshipped design spec for near-dupe analytics clustering false-positive surface (template-similar-but-content-distinct invoice-style documents clustered under NearDupe-Suppressed). Roadmap-flagged — not in beta-2.14 scope unless redirected.
- DOCS: docs/FLAG_REGISTRY.md — register Flag #22 (Near-dupe analytics false-positive sensitivity) in Active table, State `Characterized`, pointing at the new spec. Numbering history section updated. `<!-- Last audited: -->` comment bumped to 2026-04.

### Sprint-wrap — beta-2.13 informal close + beta-2.14 transition plan (2026-04)

- DOCS: CLAUDE.md — Current State table refreshed for beta-2.13 informal close. New "Last completed sprint" captures the actual 9-commit arc (3 sprint-open housekeeping + 1 role-hygiene sweep + 1 planned commit [C1] + 3 Bates-batch hotfixes + 1 UX hotfix + 1 sprint-hygiene + this refresh). Only C1 of the original 8-commit plan shipped. "What's next" describes beta-2.14 carrying forward deferred C2–C8 with numbering preserved. No v2.13.0 tag cut.

### Hotfix — Bates-batch guard crashes on Show-Family pivot (2026-04)

- FIX: pages/4_Review.py — add `and not _family_override_gid` to the Document Grid search-filter guard at line 2542. Regression introduced by the Bates Batch Search work: when a Bates Batch Search was active and the user clicked Show-Family on a document (or navigated away and back with `_family_override_group_id` still in session state), the family-override branch reset `search_hit_ids` to `None` as a skip sentinel but the `or bates_batch_text` clause still entered the block, passing `None` to `df['control_number'].isin()` and raising `TypeError: only list-like objects are allowed to be passed to isin()`. The new guard matches the pattern already used for the three hygiene-filter sites (`hide_junk`, `hide_not_responsive`, and the orphan-cascade) at lines 2509 / 2512 / 2517 which all short-circuit when family-override mode is active.

### Hotfix — Bates parser unification + filter-precedence for targeted lookup (2026-04)

- NEW: db_manager.py — `parse_bates_token(s) -> (prefix, num) | (None, None)` module-level helper (regex `^(.*?)(\d+)\s*$` + uppercase + `rstrip('-')`). Pinned-value single source of truth for Bates prefix/number splitting across Review-page features.
- FIX: pages/4_Review.py — Bulk Bates popover `split_bates` inline parser (regex `^([A-Za-z_]+)?(\d+)$`) replaced with calls to `db_manager.parse_bates_token`. The inline regex rejected hyphenated Bates (`ABC-000700`), collapsing them to the `('', -1)` sentinel. Because every degenerate token compared equal, every input matched every DB row whose `begdoc` also used a hyphenated format — the banner's "Identified N containing documents" count was actually "docs in the case that have a populated begdoc," independent of the user's input. Hyphenated Bates now parse and match correctly.
- FIX: pages/4_Review.py — sidebar Bates Lookup `_bl_parse_bates` closure replaced with calls to `db_manager.parse_bates_token`. Sidebar behavior unchanged (its regex was already correct); the two features now route through one helper so future edits to Bates parsing semantics propagate to both call sites by construction.
- CHANGE: pages/4_Review.py — add `_bates_batch_override = bool(bates_batch_text)` flag; when active, the Document Grid query now bypasses three hygiene view filters (`Hide Junk Images`, `Hide Not Responsive`, `Show Suppressed Items`) so the grid count matches the banner count. Scope filters (date range, custodian, party, production volume, collection, subcollection, batch, per-user visibility mode) still apply. Rationale: a user who pastes specific Bates has named the exact documents they want — browse-time cosmetic filters should not hide targeted lookups.
- NEW: tests/test_bates.py — `TestParseBatesToken` class (9 pinned-value tests) asserting hyphenated/concatenated/multi-segment/lowercase/whitespace/empty/None/no-digits/call-site-agreement invariants. The class docstring pins the sidebar-and-popover-share-one-parser contract so a future divergence fails at test time, not in production.

### Sprint-close addendum — beta-2.13 retrospective + audit archival (2026-04)

This commit lands on beta-2.14 because beta-2.13 closed informally without an in-sprint addendum. The addendum that would have been beta-2.13 C8 is here instead.

- DOCS: docs/retrospectives/beta-2.13.md — sprint retrospective per CLAUDE.md §Sprint-Close Retrospective Standing Order. Captures the Bates-batch hotfix triad, paperclip-click hotfix, Flag #22 registration, informal-close decision. Third use of `docs/retrospectives/template.md` (after beta-2.11 + beta-2.12).
- DOCS: docs/archive/audits/beta-2.13/ — archived 4 audit docs from this sprint (3 Flag #20 files + this addendum's self-archive). Tier README created matching beta-2.11 + beta-2.12 pattern. Per CLAUDE.md §Audit-Doc Archival at Sprint Close Standing Order.
- DOCS: docs/FLAG_REGISTRY.md — Flag #20 closed-row resolution-reference path updated to archive location. `<!-- Last audited: -->` comment bumped.
- DOCS: CLAUDE.md — Current State table refresh: Active branch flips to beta-2.14; Last completed sprint marks beta-2.13 fully closed; What's next opens beta-2.14 with C2 Flag #18 narrow `conn=None` scaffolding as the first roadmap commit.

---

## [beta-2.12] — Shipped 2026-04-20 (v2.12.0)

### Commit 1 — Flag #17: raw sqlite3.connect → db_manager.get_connection() (2026-04-20)

- FIX: home.py — swap raw sqlite3.connect in case-picker dashboard to db_manager.get_connection(); remove dead _db_path local (Flag #17; WAL pragma + audit_log migration loop + 60s timeout now applied to dashboard reads).
- DOCS: docs/FLAG_REGISTRY.md — move Flag #17 row from Active to Dormant/Closed; bump Last-audited comment.

### Commit 2 — Premature Release Tag Lesson (2026-04-20)

- DOCS: docs/lessons/premature-release-tag.md — new lesson capturing the v2.11.0 premature-tag failure mode (tag cut at C7 on 2026-04-18, force-retagged to C10 on 2026-04-20) and correction procedure for solo/private vs. multi-consumer repos.
- DOCS: CLAUDE.md — add Tag-cut ordering subsection to Audit-Doc Archival Standing Order codifying the sprint-close sequence (retrospective → archival → context maintenance → merge → tag cut → push).
- DOCS: docs/lessons/README.md — add catalogue entry for premature-release-tag under Workflow discipline.

### Commit 3 — Sprint-transition hygiene backfills (2026-04-20)

- DOCS: docs/FLAG_REGISTRY.md — backfill three `<pending>` placeholders: Flag #17 row (C1 hash), line 15 authority-established sentence (C6a hash), line 103 numbering history row (C6a hash).
- DOCS: CHANGELOG.md — close three sprint-header staleness windows: beta-2.11 → `Shipped 2026-04-20 (v2.11.0)`, beta-2.10 → `Shipped 2026-04-17 (v2.10.0)`, beta-2.9 → `Shipped 2026-04-16 (internal __version__ 2.9.0; no git tag cut)`. Closes the transient two-"In Progress" state introduced at C1 plus two pre-existing historical stalenesses surfaced by CLI pre-flight check Findings A/B/D.

### Commit 4 — Preflight Proportionality Lesson + Lightweight Template (2026-04-20)

- DOCS: docs/templates/preflight_lightweight.md — new 3-section preflight scaffold for doc-only and tiny hygiene commits. Includes a §0 Greenlight Gate placeholder so filled-in preflights have a natural home for N-Stage Gate posture boilerplate (self-consistency fix surfaced by CLI pre-flight check Finding C).
- DOCS: docs/lessons/preflight-proportionality.md — new lesson capturing the template-selection principle (8-section fits code refactors; lightweight fits doc-only) surfaced by beta-2.12 C2's 4-iteration preflight cycle.
- DOCS: docs/lessons/README.md — add catalogue entry for preflight-proportionality under Workflow discipline.
- DOCS: docs/templates/README.md — add catalogue entry for preflight_lightweight.
- DOCS: CLAUDE.md — add pointer-table row for preflight_lightweight.md under Dependency API References.

### Sprint-Close Addendum — Commit 5 (2026-04-20)

- NEW: docs/archive/audits/beta-2.12/ — tier archive for beta-2.12 per-commit audit files (3 preflights covering C1–C4, chronological README index).
- NEW: docs/archive/audits/beta-2.12/README.md — tier index with one-line purpose per archived preflight.
- DOCS: docs/archive/audits/beta-2.12/ — archived 3 preflights via git mv (C1 Flag #17, C2 premature-release-tag, C3+C4 sprint-hygiene-and-proportionality).
- DOCS: docs/FLAG_REGISTRY.md — update Flag #17 row's resolution-reference path from `docs/audits/` to archived location `docs/archive/audits/beta-2.12/`.
- NEW: docs/retrospectives/beta-2.12.md — sprint retrospective (second use of template; covers the premature-tag recovery + proportionality-discipline arc).
- RELEASE: config.py + config.example.py — bump `__version__` 2.11.0 → 2.12.0; `__branch__` beta-2.11 → beta-2.12.
- DOCS: home.py — cascade `project_ver` header bump 2.11.0 → 2.12.0 (sole .py file touched this sprint).
- DOCS: CLAUDE.md — Current State table refreshed (Active branch beta-2.12, Project version 2.12.0, Last completed sprint = beta-2.12, What's next → beta-2.13 Flag #20).
- DOCS: CHANGELOG.md — flip `## [beta-2.12] — In Progress` → `## [beta-2.12] — Shipped 2026-04-20 (v2.12.0)` per Tag-cut ordering sequence (first real application of the rule installed in C2).

## [beta-2.11] — Shipped 2026-04-20 (v2.11.0)

### Sprint-Close Addendum — Commit 10 (2026-04-20)

- NEW: docs/archive/audits/beta-2.11/ — tier archive for beta-2.11 per-commit audit files (22 files, chronological README index).
- NEW: docs/archive/audits/beta-2.11/README.md — tier index with one-line purpose per archived file.
- DOCS: docs/archive/audits/beta-2.11/ — archived 21 beta-2.11 per-commit audit files + this commit's preflight (22 files total) via git mv.
- DOCS: docs/archive/sprints/beta-2.10/ — archived orphan beta-2.10 audit (inbound_exclusion_coverage_audit.md) alongside sibling outbound_extraction_preflight.md.
- DOCS: docs/audits/commit_1_flag17_raw_sqlite_preflight.md — renamed from commit_b212_1_flag17_raw_sqlite_preflight.md (beta-2.12 preflight; rename enabled by clearing beta-2.11 commit_1_* namespace); updated internal refs to archived beta-2.11 paths.
- DOCS: docs/templates/pm_cli_collaboration_workflow.md — 1 ref-path update to archived beta-2.11 audit (line 342).
- DOCS: docs/lessons/predictive-scaffold-staleness.md — 1 ref-path update to archived 6e2 packet (line 35).
- DOCS: docs/lessons/grep-by-stem-not-spec-name.md — 1 ref-path update to archived 6e2 packet (line 34).
- DOCS: docs/lessons/chain-of-moves-stale-refs.md — 1 ref-path update to archived 6e2 packet (line 32).
- DOCS: docs/lessons/README.md — 1 ref-path update to archived 6c2 lesson payload packet (line 17).
- DOCS: docs/FLAG_REGISTRY.md — 12 ref-path updates across flag rows to archived beta-2.11 audit paths; bumped Last-audited comment to 2026-04-20.
- DOCS: CLAUDE.md — installed Standing Order "Audit-Doc Archival at Sprint Close" codifying per-sprint archival step; updated Current State table (Last CHANGELOG date 2026-04-18→2026-04-20, What's next pointer refreshed for beta-2.12 Flag #17).
- DOCS: docs/retrospectives/beta-2.11.md — appended §7 "Sprint-Close Addendum (Commit 10)" documenting the archival addendum and backfilled placeholder C9-hash in two sites (§1 commit range, §2 What Shipped table).

### Sprint-Close Hardening — Commit 9 (2026-04-18)

- NEW: tests/test_docs_index_consistency.py — 6 parity pytest cases pinning the four-tier docs/ architecture (tier README ↔ tier files bijection; CLAUDE.md references pointer table targets exist).
- NEW: docs/retrospectives/ tier — sprint retrospective library for durable forensic records of each sprint's dead ends, course corrections, and canonized lessons.
- NEW: docs/retrospectives/README.md — tier index + purpose + lifecycle + Decision Tree integration.
- NEW: docs/retrospectives/template.md — 6-section retrospective scaffold for new sprints (scope, what shipped, goals vs. outcomes, surprises and learnings, lessons canonized, gotchas for future sprints).
- NEW: docs/retrospectives/beta-2.11.md — first retrospective; covers the 6b–9 sprint arc; worked example of the template.
- NEW: docs/lessons/permission-gate-strategic-vs-hygienic.md — permission-gate visibility is load-bearing for strategic edits, satisfied by tracked diffs for hygienic edits.
- NEW: docs/lessons/n-stage-gate-revision-handling.md — preflight revisions require a fresh delta-scoped CLI pre-flight check pass before Stage 2 greenlight.
- NEW: docs/lessons/not-in-git-tracked-not-existent.md — existence ≠ tracked; `git ls-files <path>` is authoritative.
- DOCS: docs/lessons/README.md — added 3 new lesson entries under "Workflow discipline" category.
- DOCS: CLAUDE.md — added Standing Order "Sprint-Close Retrospective" mandating a retrospective at the close of every significant sprint.
- DOCS: CLAUDE.md — added Standing Order "N-Stage Gate Revision-Handling Doctrine" codifying the iron rule that patch + Stage 2 greenlight never ship in the same message.
- DOCS: CLAUDE.md — added docs/retrospectives/README.md row to Dependency API References pointer table.
- DOCS: CLAUDE.md — extended Lesson Integration Decision Tree with step 4.5 for sprint-specific forensic records.
- DOCS: docs/templates/pm_cli_collaboration_workflow.md — renamed "two-stage gate" to "N-stage gate" in §5.1 and §5.3; added new §5.2 "Pre-flight check pass" and new §5.4 "Revision-handling protocol"; renumbered subsections.
- DOCS: docs/templates/preflight_drafting_checklist.md — Check 1 expansion (not-in-git = gitignored OR untracked; `git ls-files` authoritative); Check 10 preamble ("Plan approval ≠ execution approval" reminder).
- DOCS: docs/templates/README.md — harmonized "Current templates" catalogue to `[file](file)` markdown-link format; completed the truncated `preflight_drafting_checklist.md` entry (v3 scope-expansion delta, surfaced by test_templates_tier_parity on first run).
- DOCS: docs/references/README.md — harmonized "Current references" catalogue to markdown-link format; removed predictive-scaffold preamble per the predictive-scaffold-staleness lesson (v3 scope-expansion delta, surfaced by test_references_tier_parity on first run).
- DOCS: CLAUDE.md — renamed `X_REFERENCE.md` placeholder at line 320 to `<NAME>_REFERENCE.md` to match `docs/references/README.md` angle-bracket convention and eliminate false-positive from test_claude_md_references_table_targets_exist (v3 scope-expansion delta).

### Commit 8 (2026-04-18)

- NEW: docs/templates/preflight_drafting_checklist.md — 10-item PM-side self-check mirroring CLI's Pre-Fix Investigation Protocol. Strategic/hygienic split preempts permission-gate micromanagement of CLI's routine memory/CHANGELOG/version-header maintenance.
- DOCS: CLAUDE.md — added preflight_drafting_checklist row to Dependency API References table; archived preflight_drafting_checklist_spec.md under docs/archive/specs/ per Spec Lifecycle Discipline.

### Sprint Close — Commit 7 (2026-04-18)

- RELEASE: config.py — bumped `__version__` from 2.9.0 to 2.11.0 (beta-2.11 sprint close; 2.10.0 intentionally skipped — see Commit 7 preflight §2.7 rationale).
- DOCS: CLAUDE.md — Current State table refreshed: project version 2.11.0, last completed sprint beta-2.11 doc architecture, last CHANGELOG date 2026-04-18, what's next points at beta-2.12 flagged items.
- DOCS: PROJECT_CONTEXT.md — header bumped to 2.11.0 / beta-2.11; new §beta-2.11 Sprint block added to ROADMAP section documenting the seven-commit arc, four-tier documentation architecture, Standing Orders installs, and 6f/9 permission-gated rule relaxation.
- DOCS: Technical Overview.md — header bumped to Beta 2.11 (April 2026); legacy 6-row Dependency API References table replaced with 4-tier architecture summary pointing at CLAUDE.md for authoritative cross-reference.
- DOCS: Walkthrough.md, User_Guide.md — header-only version/date refresh (full body re-pass deferred to a future commit when user-visible feature changes land).
- DOCS: docs/lessons/ — 9 lesson files had stale `_scratchpad/*.md` "Source:" citations updated to their new `docs/archive/specs/` (8 files) and `docs/specs/` (1 file still unshipped) homes after Commit 6e.2's archive sweep. Chain-of-moves-stale-refs lesson applied.
- DOCS: docs/archive/sprints/README.md — "Expected contents (post-6e)" predictive scaffold replaced with actual contents block; aside added explaining that sprint-named shipped specs live in `docs/archive/specs/` not `docs/archive/sprints/`. Predictive-scaffold-staleness lesson applied.
- DOCS: ROADMAP_TODO.md — header line 2 version stamp refreshed from 2.9.0 to 2.11.0. Active Specs bookmark integrity verified (5 unshipped + 1 pattern-doc + superpowers note — no content change).
- DOCS: docs/audits/commit_7_execution_preflight.md — Commit 7 execution preflight.

### Standing Orders — Commit 6f (2026-04-18)

- DOCS: CLAUDE.md — CHANGE: relaxed "NEVER touch human-authored files" iron law to "request permission before updating" pattern for ROADMAP_TODO.md and config.py __version__. The gate is visibility, not prohibition — Claude proposes edits with rationale and executes after explicit greenlight.

### Documentation Architecture — Commit 6e.3 (2026-04-18)

- DOCS: docs/lessons/ — NEW: 4 lesson files (predictive-scaffold-staleness, chain-of-moves-stale-refs, grep-by-stem-not-spec-name, synthetic-sample-data-in-docs) memorialize patterns surfaced during the 6e arc.
- DOCS: docs/lessons/scope-expansion-probe.md, underscore-prefix-utility-scripts.md, line-number-drift-reverification.md — FIX: stale refs to moved files updated to archive paths; one broken memory-file pointer deleted (feedback_commit_bundling_principle.md, line 47 of scope-expansion-probe).
- DOCS: docs/archive/sprints/beta-2.10/ — NEW: promoted 2 preflight sources from _scratchpad/ (outbound_extraction_preflight.md; sort_path_vulnerability_2026-04-17.md). New per-sprint README.
- DOCS: docs/archive/prompts/ — scoped pre-deployment audit prompt promoted from _scratchpad/. All three template "See worked example" cites (preflight/defect-triage/scoped-audit) now resolve without any template text change.
- DOCS: docs/templates/pm_cli_collaboration_workflow.md — FIX: 3 stale _scratchpad/ refs updated to their new archive locations (chain-of-moves-stale-refs pattern).
- DOCS: CLAUDE.md — NEW: Standing Orders §Save-Location Coordination and §Spec Lifecycle Discipline installed between PM-CLI Collaboration Workflow and Supply Chain Security sections.
- DOCS: .claude/memory/MEMORY.md — UPDATE: Save-Location Discipline section mirrors CLAUDE.md Standing Order so PM and CLI share the rule.
- CHANGE: AGENTS.md — DELETE: content was folded into CLAUDE.md earlier in beta-2.11; vestigial copy removed.
- DOCS: docs/audits/commit_6e3_execution_packet.md — Commit 6e.3 execution record.

### Documentation Architecture — Commit 6e.2 (2026-04-18)

- CHANGE: docs/archive/specs/ + docs/archive/m4/ — archive sweep (14 shipped specs swept from docs/specs/: 13 → archive/specs/, 1 → archive/m4/). Per §Spec Lifecycle Discipline (added in 6e.3): shipped specs live permanently under docs/archive/, not docs/specs/.
- CHANGE: docs/archive/prompts/recon_script_prompt.md — relocated from project root (was gitignored).
- CHANGE: .gitignore — removed lines 74 (recon_script_prompt.md) and 75 (REVIEWER_CSV_IMPORT_SPRINT.md; vestigial, file never existed at root).
- CHANGE: ROADMAP_TODO.md — Active Specs registry pruned from 19 to 6 bookmarks (1 Pattern-docs + 5 Unshipped + 0 Superpowers-origin note-only). §Awaiting-Archive-6e.2 and §Unverified subsections removed as empty. USER_PREFERENCES_SPEC moved to §Unshipped with refined evidence notation.
- CHANGE: docs/archive/specs/README.md — predictive "Expected contents (post-6e)" block replaced with a generic "Current contents" note; per-file commentary removed (multiple entries were wrong — Privilege_Log_Editor tagged "superseded" was actually shipped; Privilege_Log_Profile_Integration tagged "partially shipped" was fully shipped 2026-04-01).
- FIX: pages/9_InboundProduction.py — docstring spec path updated (docs/specs/ → docs/archive/specs/) following 6e.1's prior docs/_scratchpad/ → docs/specs/ update; last_modified bumped, no version bump (comment-only change).
- DOCS: docs/audits/commit_6e2_execution_packet.md — Commit 6e.2 execution record.

### Documentation Architecture — Commit 6e.1 (2026-04-18)

- CHANGE: docs/specs/ — spec consolidation (11 files from ediscovery root, 8 files from _scratchpad/, Phase 3 superpowers outcome: Conclusion A — skill-mandated, 0 files moved). All to-do blueprints now live under docs/specs/; shipping-status sweep into docs/archive/specs/ deferred to Commit 6e.2.
- CHANGE: ROADMAP_TODO.md — added Active Specs section as canonical bookmark registry; header refreshed to beta-2.11 / 2026-04-18.
- CHANGE: .gitignore — removed lines 74, 75, 77 (COWORK_HANDOFF, *_SPRINT.md wildcard, fix_redact_nav_bug.md).
- CHANGE: docs/archive/prompts/COWORK_HANDOFF_BRIEFING.md — relocated from docs/specs/; handoff briefings are not to-do blueprints.
- DOCS: docs/superpowers/README.md — new. Documents the skill-mandated save convention for brainstorming/writing-plans outputs.
- DOCS: docs/audits/commit_6e1_execution_packet.md — Commit 6e.1 execution record.

### Documentation Architecture — Commit 6d (2026-04-18)

- DOCS: docs/templates/preflight_template.md — new. 8-section preflight scaffold extracted from beta-2.10 outbound extraction preflight.
- DOCS: docs/templates/defect_triage_template.md — new. 8-section defect triage scaffold extracted from sort-path vulnerability triage.
- DOCS: docs/templates/scoped_audit_template.md — new. 6-pass scoped audit scaffold extracted from the scoped pre-deployment audit prompt.
- DOCS: docs/templates/pm_cli_collaboration_workflow.md — promoted from docs/audits/collaboration_workflow_standing_orders.md via git mv. Resolves the intentional dangling pointer installed in 6c.1. Status line updated to reflect new home.
- DOCS: docs/templates/README.md — replaced "expected post-6d contents" framing with actual template descriptions.
- DOCS: CLAUDE.md — appended four rows to the Dependency API References table covering the new templates.

### Documentation Architecture — Commit 6c.2 (2026-04-17)

- DOCS: docs/lessons/ — extracted 19 durable lessons from sprint retrospectives, scratchpad specs, and AGENTS.md fold-in:
  - Data integrity: defensibility-statement-practice, no-silent-default, three-tier-cascade-resolution, family-integrity-over-dedup, system-tags-protected-registry, arrow-serialization-hygiene
  - Data-layer: atomic-multi-table-writes, zero-risk-data-layer-rollback, batch-commit-discipline, exempt-annotation-convention, sqlite-version-floor, sqlite-fk-off-by-default
  - Code patterns: substring-replace-ordering, fragment-scope-rule, streamlit-drawable-canvas-workarounds, analytics-corpus-completeness
  - Workflow: scope-expansion-probe, line-number-drift-reverification, underscore-prefix-utility-scripts
- DOCS: docs/lessons/README.md — rewritten as a categorized index of the 19 lessons with the canonical 5-section structure documented
- DOCS: docs/audits/commit_6c2_lesson_payload_packet.md — added (fresh-context rescue document for the lesson payload)

### Documentation Architecture — Commit 6c.1 (2026-04-17)

- DOCS: docs/ — moved 6 dependency references (EMAIL_MIME, LIBPFF_API, OPENSEARCH_PATTERNS, OUTLOOK_COM, PYMUPDF_PATTERNS, TIKA_METADATA_KEYS) from docs/ root into docs/references/
- DOCS: CLAUDE.md — Dependency API References table paths updated to docs/references/; added "Redaction Discipline" section (AGENTS.md fold-in #1); extended closed-case rule with disabled-widget pattern (fold-in #2); appended process_msg_batch bullet to PST Extraction Architecture (fold-in #5); added "Hold Documents are NOT case ESI" iron law (fold-in #8); added "Standing Orders — PM–CLI Collaboration Workflow" pointer
- DOCS: Technical Overview.md — reference table paths updated to docs/references/
- DOCS: container_exploder.py — docstring and comment references updated to docs/references/LIBPFF_API_REFERENCE.md (comment-only; no version bump)
- DOCS: tests/introspect_libpff.py — comment reference updated to docs/references/LIBPFF_API_REFERENCE.md
- DOCS: docs/LIBPFF_INTROSPECTION_DUMP.md — reference updated to docs/references/LIBPFF_API_REFERENCE.md
- DOCS: docs/references/PYMUPDF_PATTERNS.md — added Known Gotcha #7 (Windows file locking) from AGENTS.md fold-in #4
- DOCS: DEPENDENCY_MAP.md — added §7 regression pattern "Custodian rename/merge OS desync" from AGENTS.md fold-in #7
- DOCS: docs/audits/commit_6c_execution_packet.md — added (fresh-context rescue document for the 6c arc)

### Documentation Architecture Scaffolding — Commit 6b (2026-04-17)
- DOCS: documentation architecture scaffolding (6b) — `docs/references/`, `docs/lessons/`, `docs/templates/`, `docs/archive/{sprints,specs,prompts,m4}`, and `docs/archive/superpowers/{,specs,plans}/` created with per-directory README.md explaining scope, contents rules, and expected post-6c/6d/6e population. MEMORY.md refreshed to current-state pointer table per preflight §7. CLAUDE.md updated: Current State table now reflects beta-2.11 in flight and the 6b–6e → Commit 7 → v2.11.0 arc; three new rows added to the Dependency API References table (docs/references/README.md, docs/lessons/README.md, docs/templates/README.md); new "Standing Orders — Lesson Integration Decision Tree" section installed between Context Maintenance and Supply Chain Security. No existing files moved in 6b — reference migration lands in 6c, template extraction in 6d, archive sweep in 6e.

### Instruction Corpus Retrospective Inventory — Commit 6a (2026-04-17)
- DOCS: Commit 6a instruction-corpus retrospective inventory + new FLAG_REGISTRY.md. Sweep of git log (~200 commits since February), tag messages, root-level instructional docs, docs/ references, docs/audits/, .claude/ contents, and Python code comments. Validates PM's 23 seeded patterns against evidence (22 confirmed, 1 partial/pending context); surfaces 10 newly discovered findings including instruction-corpus alignment drift (AGENTS.md 3 sprints stale, 6 retired specs on older branches, 14 governance-adjacent files unreferenced by CLAUDE.md). Feeds Commit 6b instruction-corpus updates. New durable FLAG_REGISTRY.md reconciles flag numbering (#1–#21) between PM session memory and CLI audit docs into a single authoritative list.

### document_productions Inbound Contamination Fix — Commit 5b (2026-04-17)
- FIX: db_manager.py — init_db() backfill no longer mislabels inbound documents as outbound productions. Added source-party filter to the document_productions backfill WHERE clause (previously had no inbound awareness, written before inbound concept existed).
- FIX: db_manager.py — One-time cleanup migration removes dirty inbound rows from document_productions in previously-damaged case databases. Transactional, idempotent (sentinel: _document_productions_inbound_cleanup_v1 in case_settings), logged before/after with sample control_numbers. Users should back up case DBs before first run of the fixed platform version.
- NEW: tests/test_document_productions_inbound_filter.py — Regression coverage for source-party filter + cleanup migration (5 tests).

### document_productions LEFT JOIN Characterization — Commit 5 (2026-04-17)
- DOCS: docs/audits/commit_5_left_join_backfill_characterization.md — Characterized db_manager.py:731 LEFT JOIN and upsert_inbound_documents_batch flow. Verdict: CONFIRMED BUG — State A' (inbound-first fresh-case flow). The enclosing backfill migration (lines 712-738) pre-dates beta-2.10 Module 9 and has no inbound filter on its WHERE clause; when triggered on an inbound-only case, it sweeps inbound documents into document_productions as false production_type='Original' rows. Defensibility-class impact on ~10 reader sites. Fix scoped as 1 commit (Approach 1 + Approach 3: add OUTBOUND_SOURCE_FILTER_SQL to backfill WHERE + one-time cleanup migration). New Flag #19 registered for downstream-consumer inbound-filter gap.

### Review STR NULL-CN Crash Fix — Commit 4b (2026-04-17)
- FIX: pages/4_Review.py — STR report no longer raises ValueError on cases with 2+ PST/ZIP containers. Handle NULL control_number rows in _str_meta_map construction via dropna + drop_duplicates before set_index/to_dict('index'). Root cause in shared NULL-CN fragility pattern (see Flag #9); this is a surface-level fix.
- NEW: tests/test_review_str_null_cn.py — Regression coverage for NULL control_number handling in Review STR pipeline.

### Review .to_dict('index') Characterization — Commit 4 (2026-04-17)
- DOCS: docs/audits/commit_4_review_to_dict_silent_loss_characterization.md — Characterized .set_index('control_number').to_dict('index') pattern at pages/4_Review.py:442. Unsafe: pandas 2.3.3 raises ValueError (not silent loss, as Flag #11 described) when the documents table has ≥2 NULL control_number rows under default _vis_mode='full'. PST/ZIP containers store control_number=NULL; any case with 2+ containers hits the crash. Approach 2 one-statement fix identified (dropna + drop_duplicates before set_index); PM to decide fold-into-2.11 vs defer-to-2.12.

### Page-Held Connection Characterization — Commit 3 (2026-04-17)
- DOCS: docs/audits/commit_3_page_held_conn_characterization.md — Characterized page-held connection + nested db_manager call pattern across pages/. 61 sites identified (9 latent-risky, 0 active-risky, 0 ambiguous, 52 safe), classified by risk, with four remediation approaches scoped for a future fix sprint. Flag #5 framing substantiated, not dissolved: db_manager.get_connection() returns a fresh connection on every call with no pooling, and 0 of 163 db_manager public functions accept an explicit conn parameter.

### Duplicate get_root Consolidation — Commit 2 (2026-04-17)
- CHANGE: pages/5_Production.py — Consolidated duplicate get_root(cn) definitions at lines 398 and 2634 into single module-level _walk_family_root(cn, parent_map). Original defs were NOT shadowing (different scopes per LEGB); both were live code with identical algorithms. Consolidation removes duplication and makes the helper testable.

### Dead Import Cleanup — Commit 1 (2026-04-17)
- CHANGE: pages/5_Production.py — Removed dead import sqlite3 (unused since SQL migration, verified zero downstream refs).

---

## [beta-2.10] — Shipped 2026-04-17 (v2.10.0)

### Documentation Cascade — Commit 8/8 (2026-04-17)
- DOCS: sprint-closing documentation cascade for beta-2.10. CLAUDE.md Current State table refreshed (branch beta-2.10, Last CHANGELOG date 2026-04-17, last sprint "Inbound Production module + defensibility cleanup", What's next pointer to 2.11 planning). CLAUDE.md RBAC rule fixed: legacy `require_role()` reference replaced with `require_permission()` per post-Phase-13 reality. CLAUDE.md §Post-Sprint Cross-Module Impact Audit extended with step 6 (nav-registry reconciliation) — captures the 7.7 gap as a permanent procedural safeguard. DEPENDENCY_MAP.md updated: `production_runs.direction` and `.status` entered as tracked cross-module columns, new §2.5 Module-Level Registries subsection registers `_NAV_PAGES`, §7 Known Regression Patterns gained "silent cross-module filter drift" and "navigation registry drift" rows, audit date bumped to 2026-04-17. Walkthrough.md, Technical Overview.md, User_Guide.md, PROJECT_CONTEXT.md updated to reflect Module 9 extraction, outbound-only history semantics, `INBOUND_*` audit event family, `_NAV_PAGES` registry contract, and the three sprint teaching moments (sort-path NaN-index, silent filter drift, nav registry gap). Technical Overview §Module Visibility table: corrected stale Module 5 tabs reference (post-Commit-6 artifact). MEMORY.md refreshed with sprint-turnover entry and two new pattern memories (`feedback_silent_filter_drift.md`, `feedback_nav_registry.md`). Spec housekeeping: `docs/specs/` established as convention for design specs; `Spec_Intake_Inbox_Pattern.md` moved from repo root to `docs/specs/Spec_Intake_Inbox_Pattern.md`.

### Navigation Registry Fix — Commit 7.7/8 (2026-04-17)
- FIX: auth_manager.py — register Module 9 Inbound Productions in `_NAV_PAGES` so the page is reachable from the post-login sidebar. Commit 6 extracted the module into `pages/9_InboundProduction.py` but did not update the nav registry; logged-in users could reach the page only via direct URL, not via the sidebar. New tuple sits between Production and Sync, uses 📨 envelope to distinguish from Ingestor's 📥 inbox, and reuses the `production` permission (matches the page's own `require_permission` gate). Version 1.9.6 → 1.9.7.
- NEW: tests/test_nav_registry_consistency.py — smoke test asserting every `pages/*.py` file appears in `auth_manager._NAV_PAGES` (and vice-versa, to catch stale entries pointing at deleted files). Pins the registry-vs-filesystem contract so future page additions cannot silently repeat this failure mode.

### Phase-Gating Refactor — Commit 7/8 (2026-04-16)
- FIX: pages/5_Production.py — tab_privlog now renders during Pass 1 checkpoint and post-finalization states. Outer state gates rewritten from sequential if/st.stop() to single if/elif/else around the new _render_outbound_production() helper; inner st.stop() calls in the Run Production handler converted to return. The script-halt side-effect of st.stop() previously blanked tab_privlog on any of five error/state paths (checkpoint render, post-finalization render, duplicate-name guard, Redact-without-marks hard block, privilege-tags-without-disposition hard block). DOC-000150 (a custodian_a.eml tagged Redact) was the observable regression trigger. Version 1.22.7 → 1.23.2.
- FIX: pages/5_Production.py — tab_privlog now renders on closed cases. Removed the module-level st.stop() that fired on closed-not-finalized cases, matching the warn-without-halt pattern in pages/4_Review.py:297-302 and pages/3_Analytics.py:81-82. Write surfaces remain gated per-surface (sidebar Delete, Run Production, DELETE & RE-RUN, checkpoint Retry/Finalize/Abort via the new tab-level if/elif/else skipping _render_outbound_production and _render_pass1_checkpoint on closed+not-finalized; Save/Create/Delete Profile in tab_privlog via inline `disabled=(… not _case_closed)` at line 3795). Module-level stop was belt-and-suspenders on top of per-surface gates; removal restores read access to the privilege log on closed cases without changing write authority.
- CHANGE: pages/5_Production.py — extracted the outbound config body (former lines 2267-3369, ~1,103 lines) into `_render_outbound_production()` helper, nested inside `with tab_outbound:` alongside `_render_pass1_checkpoint`, `_render_post_finalization`, and the three `_handle_*` helpers. Two local helpers migrated with the body (`get_root` family-root walker in Run Production family-expansion logic, `_bates_num` Bates-string parser in Gap Analysis handler). Pure code motion + indent in Phase A; behavior changes (return-instead-of-stop, if/elif/else gate) layered in Phases B and C.

### Inbound Production Module Extraction — Commit 6/8 (2026-04-16)
- NEW: pages/9_InboundProduction.py — dedicated module for opposing-counsel production ingestion (extracted from pages/5_Production.py tab_inbound, 424-line lift). Module-level header, module docstring (aspirational access design), `require_permission('production')` gate, closed-case banner + form-hiding pattern per pages/4_Review.py precedent (beta-2.10 sprint, Commit 6 of 8).
- CHANGE: pages/5_Production.py — tab_inbound block removed; title changed from "Module 5: Production & Export" to "Module 5: Outbound Production & Privilege Log"; st.tabs collapsed 3→2 (outbound + privilege log); section comment renumbered TAB 3 → TAB 2; version 1.22.6 → 1.22.7.
- CHANGE: pages/5_Production.py — removed dead `from opensearchpy import helpers` import (only the deleted tab_inbound purge flow used it; caught during Phase A dead-code sweep).
- NEW: pages/9_InboundProduction.py — records a production_runs row (direction='inbound', status='finalized') after successful ingest; settings_json captures source_party, production_volume, load_file, field_mapping, row_count, error_count. Recording is non-blocking (narrow except sqlite3.Error with user-facing warning + recovery instructions) — deliberate design decision: documents table is primary provenance, production_runs history is secondary side-effect; partial-failure recovery via idempotent re-ingest.
- NEW: db_manager.py — `validate_inbound_production_identifiers(source_party, production_volume)` helper + `_INBOUND_NAME_RESERVED_DELIMITER = ' - '` constant. Rejects empty/whitespace-only inputs, inputs containing the ` - ` composite-name delimiter (prevents collision between ('A - B', 'C') and ('A', 'B - C') producing identical composite names), and inputs exceeding 100 chars (UX-motivated limit, not schema-driven). Version 1.29.0 → 1.30.0.
- NEW: tests/test_inbound_db.py — TestIngestRecordsProductionRunRow class (5 tests): happy-path row creation, settings_json field-level pinning, partial-failure-no-row-created control-flow guarantee, re-ingest INSERT OR REPLACE semantics, document_count tracks successful_inserts not total_rows.
- NEW: tests/test_inbound_db.py — TestValidateInboundProductionIdentifiers class (13 tests): valid inputs, empty field rejection, whitespace-only rejection, delimiter-substring rejection, 100-char boundary, collision counterexample both pairs rejected, reserved-delimiter constant pinning.
- DOCS: User_Guide.md §10.1 + §10.2 — updated inbound-production instructions to point at the new "9 Inbound Productions" sidebar module instead of the deleted "5 Production → Inbound Productions tab". Engineering-facing docs (PROJECT_CONTEXT, Technical Overview, Walkthrough, ROADMAP) deferred to Commit 8 docs cascade — only user-facing instructions updated here, per the "don't ship docs describing deleted UI" precedent from Commit 3.

### Inbound Production Module Extraction — Commit 5/8 (2026-04-16)
- CHANGE: pages/5_Production.py, db_manager.py — migrated 4 inline SQL queries from tab_inbound to db_manager helpers in preparation for Commit 6's module extraction. Behavior preserved except for a deliberate exception-narrowing noted below.
- NEW: db_manager.py — `inbound_production_run_name(source_party, production_volume)` formatter (pinned format, single source of truth for Commit 5 purge and Commit 6 ingest).
- NEW: db_manager.py — `get_inbound_productions(case_folder)` dashboard summary (GROUP BY source_party, production_volume; excludes Internal/NULL).
- NEW: db_manager.py — `purge_inbound_volume(case_folder, source_party, production_volume)` atomic 3-op transaction (SELECT os_ids + DELETE docs + DELETE production_runs row) using `with conn:` for rollback semantics; returns opensearch_ids for caller's OS cleanup.
- NEW: db_manager.py — `upsert_inbound_documents_batch(case_folder, rows)` batch INSERT OR UPDATE with pinned ON CONFLICT preservation scope (only dynamic_metadata, full_path, has_text updated on conflict; all other fields preserved to protect reviewer-applied state).
- NEW: tests/test_inbound_db.py — 17 regression tests covering: inbound_production_run_name pinned format, get_inbound_productions filtering/grouping, upsert ON CONFLICT preservation (explicit field-by-field enumeration of reviewer-state survival), purge happy-path + atomicity rollback (drops production_runs table mid-transaction, asserts documents survive), end-to-end ingest → purge → re-ingest round trip.
- CHANGE: exception-handling narrowed — inline code used `except Exception: return []` in get_inbound_productions call site; helper uses `except sqlite3.OperationalError: return []`. Narrows the catch to schema/connection failures while letting unexpected errors surface instead of silently returning empty — improves observability without regressing the dashboard-resilience goal. Applied only in get_inbound_productions; purge and batch-upsert intentionally propagate exceptions so callers know when an operation didn't complete.

### Inbound Production Module Extraction — Commit 4/8 (2026-04-16)
- FIX: pages/4_Review.py — inbound documents (source_party != 'Internal') no longer accept privilege disposition writes; Withhold/Redact/Clear suppressed across individual save, bulk-privilege loop, and redaction-sync paths. Privilege on opposing counsel's production is meaningless and a confusion hazard.
- NEW: pages/4_Review.py — `_is_inbound_doc(source_party)` predicate mirrors db_manager.OUTBOUND_SOURCE_FILTER_SQL semantics at the Python layer.
- NEW: pages/4_Review.py — grid column badge `📥 {party_name}` on inbound rows; privilege coding UI shows informational banner instead of disposition radio when the current doc is inbound; bulk-privilege apply reports skipped-count (e.g., "Skipped N inbound document(s) from the privilege disposition apply").
- NEW: tests/test_review_inbound_badge.py — 16 regression tests across 4 classes (predicate, bulk-privilege skip with tag-write preservation, redaction-sync skip, scope-boundary preservation of non-privilege review actions).
- DOCS: plan file Post-Sprint Roadmap Flags — new flag for page-held connection + nested db_manager.* call pattern at `pages/4_Review.py:~3238` (latent fragility; test harness documented accordingly, deferred to beta-2.11 DB-hygiene sprint).

### Inbound Production Module Extraction — Commit 3/8 (2026-04-16)
- FIX: pages/5_Production.py, db_manager.py — mandatory outbound source_party filter applied to 34 queries (4 production assembly, 1 privilege log, 1 text extraction, 28 defensibility). Eliminates pre-existing 26(g) hazard where inbound documents could leak into outbound output via the user-toggleable `exclude_external` checkbox (now removed).
- NEW: db_manager.py — `OUTBOUND_SOURCE_FILTER_SQL` constant and `outbound_source_filter_sql(alias=None)` alias-aware helper (beta-2.10 sprint, Commit 3 of 8).
- CHANGE: pages/5_Production.py — removed "Exclude External / Third-Party" checkbox; filter is now unconditional. Column layout rebalanced to 2+2.
- NEW: tests/test_outbound_filter.py — 12 pinned-value tests (sealed contract: constant identity check, alias helper round-trip, runtime SQL validation).
- NEW: tests/test_defensibility_inbound_exclusion.py — 16 integration tests (3 overview + 3 ingestion + 2 processing + 2 dedup + 3 review + 2 privilege log + 1 E2E zero-leakage regression).
- CHANGE: tests/test_bates.py — `_build_exclusion_sql` / `_run_production_selection` harness updated to match new architecture; `test_exclusion_sql_fragment_shape` now enforces separation (source_party must NOT be in the user-toggleable fragment).
- DOCS: User_Guide.md, PROJECT_CONTEXT.md — updated to reflect removed checkbox and mandatory filter.
- DOCS: docs/audits/inbound_exclusion_coverage_audit.md — pre-flight coverage audit for inbound exclusion enforcement (documents the 34-query scope expansion from the plan's assumed 4).

### Inbound Production Module Extraction — Commit 2/8 (2026-04-16)
- FIX: pages/5_Production.py — orphan detector (lines 239-264) now consults production_runs.status via db_manager.get_productions_with_staging_files(); no longer false-positives on legitimately-staged Pass 1 output after browser close (beta-2.10 sprint, Commit 2 of 8).
- CHANGE: pages/5_Production.py — Pass 1 lifecycle state machine wired: record_production_run(status='in_progress') at Pass 1 start, update_production_status('pass1_complete') at Pass 1 complete, 'aborted' on cancel or abort, 'finalized' at Finalize completion.
- NEW: tests/test_production_status.py — TestOrphanDetectorPredicate and TestOrphanDetectorIntegration classes (11 tests) covering every (files_present × db_status) combination.

### Inbound Production Module Extraction — Commit 1/8 (2026-04-16)
- NEW: db_manager.py — production_runs status/direction columns + helpers for inbound/outbound split (beta-2.10 sprint, Commit 1 of 8).
- NEW: tests/test_production_status.py — 21 regression tests including upgrade-path class that guards against SQLite ALTER-ADD-DEFAULT backfill gotcha.

---

## [beta-2.9] — Shipped 2026-04-16 (internal __version__ 2.9.0; no git tag cut)

### Production family-expansion exclusion leak fix (2026-04-16)
- FIX: 5_Production.py — FIX #8 family-integrity expansion (line 2599) now reuses the same exclusion clauses as the base-set query. Previously, non-responsive / suppressed / external / previously-produced attachments of responsive parents silently bypassed every user-selected exclusion checkbox and received Bates numbers in the production set. Live repro: on beta-2.9 Test(small) case, DOC-000501, DOC-000503, DOC-000505 (all tagged "Not Responsive") received Bates ABC-000040, ABC-000041, ABC-000035 despite "Exclude Non-Responsive" being checked.
- NEW: tests/test_bates.py — TestProductionFamilyFiltering class with 5 regression tests (family_case fixture + _build_exclusion_sql helper + _run_production_selection harness) guarding against reintroduction of the filter-bypass defect.

### Production page phase-gating fix (2026-04-16)
- FIX: pages/5_Production.py — hide document-selection grid and "Confirm Selection" button when Pass 1 checkpoint or post-finalization UI is active. Prior behavior rendered the grid above the checkpoint because the phase gate at line 2218 could not un-render output already written by the tab.

### Playwright E2E testing framework (2026-04-15)
- NEW: tests/e2e/ — Playwright E2E testing framework with login fixtures, ad-hoc screenshot utility, and smoke tests
- NEW: tests/e2e/screenshot.py — ad-hoc screenshot utility for Claude CLI visual inspection of any Streamlit page
- NEW: tests/e2e/seed_test_user.py — idempotent test user seeding script for E2E auth
- NEW: tests/e2e/test_smoke.py — smoke tests: app load, login flow, all 7 page navigation without errors

### Privilege disposition defensibility chain (2026-04-15)
- FIX: 4_Review.py — bulk privilege tagging now prompts for Withhold/Redact disposition inline; defaults to Withhold for document-level determinations
- FIX: 4_Review.py — bulk privilege tagging detects disposition conflicts (Redact↔Withhold); shows Override All / Apply to Unset Only / Cancel resolution with per-document audit trail
- CHANGE: 4_Review.py — individual privilege disposition defaults to Withhold when no redaction marks exist (was always Redact); preserves existing disposition if already set
- CHANGE: 5_Production.py — privilege-tagged documents without disposition now hard-block production instead of soft warning; prevents inadvertent privilege waiver

### Production category selection tools (2026-04-15)
- NEW: 5_Production.py — production_category column added to document selection query, grid display, and column filters
- NEW: 5_Production.py — Auto-Select/Deselect by Category dropdowns for producing only specific category sets (e.g., insurance documents only)

### PST/ZIP container status leak fix (2026-04-15)
- FIX: processing_engine.py — remove Phase 1 status promotion that set PST/ZIP containers to 'Processed' instead of leaving them as 'Container_Scanned'; caused containers to appear in Review grid with no control numbers and pollute dedup hash sets

### Respondeo branding integration (2026-04-15)
- NEW: ui_utils.py — inject_sidebar_branding() using st.logo() for sidebar logo with collapsed icon
- CHANGE: home.py — favicon, page_title rename to "Respondeo | Home", title section with logo + caption
- CHANGE: 1_Ingestor.py — favicon and page_title rename to "Respondeo | Ingest"
- CHANGE: 2_Processor.py — favicon and page_title rename to "Respondeo | Processor"
- CHANGE: 3_Analytics.py — favicon and page_title rename to "Respondeo | Analytics"
- CHANGE: 4_Review.py — favicon and page_title rename to "Respondeo | Review"
- CHANGE: 5_Production.py — favicon and page_title rename to "Respondeo | Production"
- CHANGE: 6_Sync.py — favicon and page_title rename to "Respondeo | Filevine Sync"
- CHANGE: 7_Custodians.py — favicon and page_title rename to "Respondeo | Custodians"
- CHANGE: 8_Exhibits.py — favicon, page_title rename to "Respondeo | Exhibits", added inject_custom_css() and inject_sidebar_branding() (previously missing)
- CHANGE: auth_manager.py — login page title renamed from "E-Discovery Hub" to "Respondeo"
- FIX: home.py — increase logo width from 80px to 140px for better visibility
- FIX: 8_Exhibits.py — add missing auth_manager.show_user_info() call (sidebar was empty after inject_custom_css hid default nav)
- CHANGE: defensibility_report.py — rename "DIY eDiscovery Hub" to "Respondeo" in generated PDF report headers/footers
- CHANGE: all .py files — rename metadata header `# project:` from "DIY eDiscovery Hub" to "Respondeo eDiscovery Platform"
- DOCS: all documentation files — rename "DIY E-Discovery Hub" / "DIY eDiscovery Hub" to "Respondeo" throughout

### Production categories stabilization (2026-04-14)
- FIX: processing_engine.py — add production_category to OpenSearch document payload (was missing from index, preventing search-based category filtering)
- FIX: os_manager.py — add production_category to reindex_from_sqlite() payload (same gap in reindex path)
- FIX: db_manager.py — add index on production_category column (speeds auto-categorize on large cases)
- FIX: db_manager.py — get_category_summary() now excludes 'Remediated' status (preventive for Phase 27)
- FIX: 5_Production.py — add warning when strict category sort will split document families
- FIX: 5_Production.py — correct misleading comment on parent sort order in folder sort mode
- FIX: tests/conftest.py — auth_config_file fixture now mocks session_state user_role=admin so CRUD tests pass headlessly

### Documentation update — background worker feature (2026-04-12)
- DOCS: User_Guide.md — add Background Processing & Job Monitor section (3.2), update warnings for session-independent processing
- DOCS: Technical Overview.md — expand jobs table schema, add Background Worker Architecture section with Mermaid diagram
- DOCS: Walkthrough.md — add Background Processing & Session Independence section
- DOCS: PROJECT_CONTEXT.md — expand jobs table columns, update Module 2 with worker architecture and SQLite contention details

### Processor progress display fix (2026-04-10)
- FIX: 2_Processor.py — Phase 1 progress showed nonsensical "3 / 1" because pass_num was used as progress with total=0 defaulting to 1; now hides counter when total is unknown

### Ingestor re-scan dedup fix (2026-04-10)
- FIX: 1_Ingestor.py — dedup check compared \\\\?\\ prefixed scan paths against unprefixed DB paths, causing all files to be re-registered on re-scan

### SQLite self-deadlock fix in Phase 1 (2026-04-09)
- FIX: processing_engine.py — conn.commit() before every log_audit() call in Phase 1 loops to prevent self-deadlock (uncommitted write lock on conn blocks log_audit's second connection; 10K docs × 60s timeout = 180hr hang)
- CHANGE: processing_engine.py — NIST, standard docs, and duplicate container audit calls batched to single BULK entries instead of per-document

### pre-init error guard (2026-04-08)
- FIX: db_manager.py — get_production_runs/get_production_run now return empty results instead of crashing when DB not yet initialized
- FIX: home.py — add st.stop() after "no database" warning to prevent queries on uninitialized case folders

### background processing worker (2026-04-08)
- NEW: processing_engine.py — shared processing logic extracted from 2_Processor.py (no Streamlit imports); run_phase_1/2/3 with callback-based progress
- NEW: _processing_worker.py — standalone subprocess that runs all 3 phases; survives session disconnects; communicates via jobs table
- NEW: .streamlit/config.toml — server stability config
- CHANGE: db_manager.py — expanded jobs table schema (phase, pid, cancel_requested, etc.) + 10 new job CRUD functions
- CHANGE: 2_Processor.py — refactored to import from processing_engine; background subprocess launch with inline fallback; job monitor UI

### session timeout increase (2026-04-08)
- CHANGE: auth_manager.py — increase default session timeout from 30 to 120 minutes for long-running jobs
- DOCS: config.example.py — add session_timeout_minutes setting with documentation

### production sort preservation fix (2026-04-03)
- FIX: 5_Production.py — remove unconditional re-sort by sort_group before Bates assignment that destroyed category/folder sort order

### production category family handling option (2026-04-03)
- NEW: 5_Production.py — "Family handling" radio under Sort by Production Category: keep families together vs strict category grouping (contiguous Bates ranges)

### production input persistence fix (2026-04-03)
- FIX: 5_Production.py — production name, Bates prefix, and start number no longer reset on rerun; defaults only set on first render, toggle changes force-update

### category summary non-responsive fix (2026-04-03)
- FIX: db_manager.py — get_category_summary() gains exclude_non_responsive param; Review sidebar shows all, Production page excludes non-responsive
- FIX: 5_Production.py — pass exclude_non_responsive=True so category breakdown matches what actually gets produced

### category reorder fix (2026-04-03)
- FIX: 4_Review.py — production category ▲/▼ reorder buttons now clear stale widget keys before rerun so swapped order persists

### path repair utility (2026-04-03)
- NEW: db_manager.py — detect_path_roots(), preview_path_repair(), repair_paths() for full case migration across drives/folders
- NEW: home.py — Path Repair utility in Case Maintenance; rebases documents.full_path, hold_documents.file_path, exhibit_sets.case_folder after drive/folder migration

### attachment-aware thread suppression (2026-04-02)
- NEW: 3_Analytics.py — Phase A5 in run_threading(): emails with attachments promoted from suppressed → inclusive to prevent attachment orphaning
- NEW: 3_Analytics.py — Inclusive-Attachments informational tag on promoted emails; metrics display shows retained count
- FIX: 3_Analytics.py — Clear & Re-Run removes Inclusive-Attachments before Inclusive to avoid substring corruption
- CHANGE: 4_Review.py — add "Inclusive-" to system tag prefixes so Inclusive-Attachments is hidden from user tag column/coding panel
- FIX: db_manager.py — get_category_summary() now excludes duplicates/junk/suppressed to match Review grid visibility
- CHANGE: 4_Review.py — remove @st.fragment from coding_layout(); add st.rerun() after production category save for sidebar refresh

### redaction tab fragment wrapper (2026-04-02)
- CHANGE: 4_Review.py — wrap entire Redact tab in @st.fragment; nav/zoom/checkbox reruns only execute ~480 lines instead of ~5000
- CHANGE: 4_Review.py — reason panel custom text_input always rendered (stable widget tree), hidden via container.empty() to eliminate rerun on dropdown change

### redaction canvas nav fix + performance (2026-04-02)
- FIX: 4_Review.py — redaction page navigation arrows now work correctly; relocated deferred pending nav pop before pixmap render
- CHANGE: 4_Review.py — pre-cache adjacent pages (prev/next) on pixmap cache miss for instant navigation
- NEW: db_manager.py — save_redaction_with_sync() batches mark upsert + tag/privilege/status sync in one connection (never-raise)
- CHANGE: 4_Review.py — save and delete handlers use batched DB function, reducing 7-10 connections to 2-3

### privilege_status save guard (2026-04-02)
- NEW: db_manager.py — has_redaction_marks() helper for privilege_status guard
- FIX: 4_Review.py — save handler no longer clears privilege_status when redaction marks are the disposition source
- FIX: 4_Review.py — bulk set production category conflict buttons (Apply all / Uncategorized only) now work via session state persistence
- NEW: 4_Review.py — column filters support (none) keyword to match NULL/empty values
- CHANGE: 4_Review.py — document preview pane remains visible during multi-select, showing last selected document
- FIX: 4_Review.py — inline new production category creation moved from st.button to form save handler (fixes StreamlitAPIException)
- CHANGE: RedactionViewer.tsx — buffer drawn marks in React state; flush on mode switch or 2s timer instead of per-box
- CHANGE: types.ts — add "batch_update" action to ComponentValue interface
- CHANGE: 4_Review.py — wrap reason selectors in @st.fragment to prevent canvas redraws on dropdown change
- CHANGE: RedactionViewer.tsx — auto-flush changed from fixed 2s interval to debounce (resets on each draw)
- CHANGE: 4_Review.py — cache PDF page count, rendered pixmap, and search highlights in session state to avoid re-opening PDF on every rerun

### Production Categories & Disclosure Ordering (2026-04-02)
- NEW: db_manager.py — production_category column migration on documents table
- NEW: db_manager.py — get_production_categories(), save_production_categories() with rename propagation
- NEW: db_manager.py — update_document_production_category(), bulk_update_production_category()
- NEW: db_manager.py — auto_categorize_documents() with dry_run preview and keyword/extension matching
- NEW: db_manager.py — get_category_summary() for category dashboard counts
- NEW: 4_Review.py — Production Categories sidebar expander (Manager+): category editor with up/down reordering, color swatches, keyword/extension rules
- NEW: 4_Review.py — Auto-Categorize tool with tabbed preview, per-document deselection, apply/cancel flow
- NEW: 4_Review.py — Production Category column added to review grid (filterable)
- NEW: 4_Review.py — Production Category dropdown in document detail pane with inline "+ New Category" creation
- NEW: 4_Review.py — Bulk Set Production Category with conflict handling (Apply all / Uncategorized only / Cancel)
- CHANGE: 5_Production.py — Document Ordering replaced checkbox with 3-option radio (Production Category / Ingestion Folder / Family Only)
- NEW: 5_Production.py — Category sort mode: groups by production category with contiguous Bates ranges, family inherits root's category
- CHANGE: 5_Production.py — Bates Range Summary generalized to handle both category and folder sort modes
- NEW: 5_Production.py — Disclosure Reference summary with per-category Bates ranges, stored in production_runs.settings_json
- NEW: 5_Production.py — Category summary display in production setup showing doc counts per category with uncategorized warning
- CHANGE: DEPENDENCY_MAP.md — added production_category column and production_categories case_setting cross-references

### Exhibits sidebar nav (2026-04-01)
- FIX: auth_manager.py — add Exhibits page link to sidebar navigation (was missing, page unreachable from nav)
- CHANGE: auth_manager.py — sidebar navigation centralized into _NAV_PAGES registry; adding pages is now a one-tuple change

### Production privilege log profile integration (2026-04-01)
- NEW: 5_Production.py — Production privilege log uses saved export profiles (columns, headers, ordering)
- NEW: 5_Production.py — Privilege log profile selector in production config UI
- CHANGE: 5_Production.py — Production privilege log switched from per-mark to per-document rows
- CHANGE: 5_Production.py — Privilege log shared functions moved to module level for reuse by both QC tab and production
- NEW: 5_Production.py — Production privilege log includes Excel (.xlsx) alongside CSV

### Privilege Log fixes (2026-04-01)
- FIX: 5_Production.py — Privilege Log query uses privilege_status column instead of tag membership; fixes zero-result bug
- FIX: 5_Production.py — "Include Needs Review" scoped to undispositioned documents only (privilege_status IS NULL)
- CHANGE: 5_Production.py — Privilege Log auto-refreshes on checkbox/basis changes without manual Refresh click
- FIX: 5_Production.py — Privilege basis sourced from redaction mark reasons first, then tags, then "(No basis specified)"; fixes incorrect AC Privilege default
- FIX: 5_Production.py — page_count and redaction_pages use None for missing values (fixes Arrow serialization warnings)
- FIX: 5_Production.py — Privilege Log description column disposition-aware (Withhold/Redact/Pending)
- FIX: 5_Production.py — mark_reasons SQL uses json_extract() instead of ->> operator for SQLite portability
- FIX: 5_Production.py — privilege basis fuzzy match defaults to "(No basis specified)" instead of guessing AC Privilege
- NEW: 5_Production.py — column reordering with up/down arrows in export profile editor
- NEW: 5_Production.py — live export preview table (first 10 rows with current profile settings)
- NEW: 5_Production.py — CSV and Excel download buttons for privilege log export
- FIX: 5_Production.py — Privilege Log Bates Range shows actual per-page Bates numbers instead of page offsets
- FIX: 5_Production.py — Switching export profiles now loads the profile's saved columns (Streamlit key/default precedence bug)

### SQL comment-in-string fix (2026-04-01)
- FIX: 3_Analytics.py — move exempt annotation out of SQL triple-quoted string (sqlite3 "unrecognized token: #")
- FIX: 4_Review.py — same fix in 3 review-reset SQL statements
- FIX: 5_Production.py — same fix in inbound-production query

### Privilege Log Auto-Load + Export Profiles (2026-04-01)
- FIX: 5_Production.py — Privilege Log tab restructured: auto-loads on tab open instead of requiring Generate button click; data persisted in session state to survive filter interactions
- FIX: 5_Production.py — Privilege Log tab wrapped in error handler to surface rendering failures
- CHANGE: 5_Production.py — Privilege Log "Generate" button replaced with "Refresh" button; auto-refreshes when basis override or needs-review toggle changes
- FIX: 5_Production.py — Privilege Log audit logging moved to query-time only (prevents duplicate entries on filter interactions)
- NEW: 5_Production.py — Export Profiles for privilege log: named column configurations with merge options and per-case persistence
- NEW: 5_Production.py — "Individuals Involved" merge: combines From/To/CC with email address stripping and deduplication
- NEW: 5_Production.py — Disposition-aware Bates formatting: Withheld docs show begdoc only, Redacted docs show specific redacted page Bates numbers
- FIX: 5_Production.py — Inbound Productions tab: replaced all st.stop() calls with guard variable pattern to prevent killing subsequent tabs (Privilege Log was unreachable)

### M-7 Widget Key Regression Fixes (2026-04-01)
- FIX: 4_Review.py — document switching infinite rerun loop caused by selectbox key conflicting with index= parameter (M-7 regression)
- FIX: 8_Exhibits.py — same pattern: sync session state before selectbox/text_input/date_input render when switching exhibit sets
- FIX: 5_Production.py — same pattern: sync prod_name, bates_prefix, bates_start session state before widgets render (prevents stale defaults on supplemental productions)

### Interactive Redaction Viewer — Custom Component (2026-03-31)
- NEW: components/redaction_viewer/__init__.py — custom Streamlit bidirectional component for interactive document redaction (React+SVG, PDF-point coordinates natively)
- CHANGE: 4_Review.py — replaced streamlit-drawable-canvas (st_canvas) with custom redaction_viewer component; removed Fabric.js conversion, deletion counter, override drawing logic
- CHANGE: requirements.txt — removed streamlit-drawable-canvas-fix==0.9.8 dependency

### Pre-Release Documentation Update (2026-03-31)
- DOCS: Technical Overview.md — added Split/Trim feature, permissions, schema columns, M-4 architecture metrics
- DOCS: PROJECT_CONTEXT.md — added Privilege Log QC Editor, view_shell_documents permission, Split/Trim schema

### M-4 Batch 9 — Defensibility Report SQL Migration (2026-03-31)
- CHANGE: db_manager.py — added 9 new get_defensibility_* functions for report data collection (overview, ingestion, processing, dedup, review, production, privilege, audit, holds)
- CHANGE: defensibility_report.py — migrated 49 raw .execute() calls across 8 _collect_* functions to db_manager; removed sqlite3 import

### M-4 Batch 8 — Exempt Annotations (2026-03-31)
- CHANGE: 4_Review.py — added db_manager: exempt annotations to 23 raw .execute() calls (review loop, dashboard read, dynamic query, schema introspection, batch status update)
- CHANGE: 5_Production.py — added db_manager: exempt annotations to 5 raw .execute() calls (production loop, dashboard read)
- CHANGE: 1_Ingestor.py — added db_manager: exempt annotations to 10 raw .execute() calls (dashboard read, ingest loop, schema introspection, custodian assignment)
- CHANGE: 7_Custodians.py — added db_manager: exempt annotations to 15 raw .execute() calls (custodian management, dynamic query, hold management)
- CHANGE: 8_Exhibits.py — added db_manager: exempt annotations to 1 raw .execute() call (dynamic query)
- CHANGE: home.py — added db_manager: exempt annotations to 13 raw .execute() calls (dashboard read, schema introspection, case reset, archive read, audit log read)
- CHANGE: 2_Processor.py — added db_manager: exempt annotations to 44 raw .execute() calls (processing loop, batch transaction, fix-up query, dashboard read, seed data)
- CHANGE: 3_Analytics.py — added db_manager: exempt annotations to 15 raw .execute() calls (batch transaction, dashboard read, analytics bulk-update, dynamic query)
- CHANGE: 6_Sync.py — added db_manager: exempt annotations to 26 raw .execute() calls (sync loop, filevine push/pull, dashboard read, dynamic query)

### Critical-Tier Audit Remediation C-1/C-2 (2026-03-31)
- FIX: auth_manager.py — C-1/C-2: Added _require_admin() caller permission guards to update_doc_visibility(), save_role_permissions(), create_custom_role(), delete_custom_role(); all admin functions now self-protecting
- DOCS: HOLISTIC_AUDIT_REMEDIATION.md — All 7 C-tier and 11 H-tier findings marked RESOLVED

### High-Tier Audit Remediation H-1 through H-11 (2026-03-31)
- FIX: auth_manager.py — H-4: Logout now clears all session state (was only popping 4 keys, leaving stale case/review state)
- FIX: auth_manager.py — H-5: Multi-hop cycle detection in role permission inheritance (A→B→A chains now caught via _visited set)
- FIX: 3_Analytics.py — H-3: EXECUTE buttons for threading and near-dupe now require has_permission('tag') before applying bulk tags
- FIX: 7_Custodians.py — H-2: Added inline has_permission('custodian_management') defense-in-depth checks at profile save, hold status, hold upload, hold delete
- FIX: 4_Review.py — H-1: Saved search share/unshare/delete buttons now gated behind _case_closed check
- FIX: 6_Sync.py — H-7: Added SYNC_REDACTION_IMPORTED and SYNC_REDACTION_OVERRIDE audit logging for previously unlogged write operations
- CHANGE: db_manager.py — H-9: Audit vocabulary docstring updated with Split/Trim and new Sync action types
- DOCS: HOLISTIC_AUDIT_REMEDIATION.md — All 11 H-tier findings marked RESOLVED with resolution details

### Privilege Log QC Editor (2026-03-31)
- NEW: 5_Production.py — Privilege Log tab replaced with QC Editor: filterable grid (disposition, custodian, basis, date range), 6-metric summary bar, "Show only Needs Disposition" convenience filter
- NEW: 5_Production.py — Per-case column picker for privilege log export: 19 available columns, EDRM defaults, saved to case_settings, permission-gated config save
- NEW: 5_Production.py — Enhanced privilege log query: adds confidentiality_designation, source_collection, page_count, reviewer notes (from document_notes), redacted page count (from redaction_marks)
- NEW: 5_Production.py — Excel export with bold headers and auto-width columns
- NEW: db_manager.py — `get_case_setting()` and `save_case_setting()` generic case_settings accessor functions

### Scoped Pre-Deployment Audit Fixes (2026-03-31)
- FIX: db_manager.py — split_document() and trim_document() now copy all legal metadata (confidentiality_designation, privilege_status, clawback_status, clawback_date, tags, source_party, dates, email metadata) from parent to children; prevents accidental disclosure of privileged/confidential material after split
- NEW: auth_manager.py — `view_shell_documents` permission (manager+admin): gates Split_Source visibility in review grid and privilege log QC tab
- FIX: 5_Production.py — Standalone Privilege Log tab conditionally excludes Split_Source based on view_shell_documents permission
- FIX: db_manager.py — get_data_reduction_stats() excludes Split_Source/Container_Scanned from total_ingested count
- FIX: db_manager.py — get_custodian_inventory_df_data() and get_custodian_doc_stats() exclude shell documents from counts
- FIX: home.py — Dashboard total document count excludes Split_Source/Container_Scanned
- FIX: 7_Custodians.py — All custodian count/collection queries exclude Split_Source/Container_Scanned
- FIX: defensibility_report.py — Privilege stats in defensibility report exclude Split_Source
- FIX: 4_Review.py — Review grid Split_Source exclusion now permission-gated via view_shell_documents
- FIX: 4_Review.py — Trim mode clears trim_input session state after execution

### Privilege Log Fixes (2026-03-31)
- FIX: 5_Production.py — Skip Split_Source documents in both production imaging loops (Pass 1 and parallel); prevents shell documents from being imaged and their annotations captured
- FIX: 5_Production.py — Gate merged privilege log on privilege_status='Redact'; documents without a formal Redact disposition no longer leak into the privilege log CSV
- FIX: 5_Production.py — Deduplicate same-page/same-reason redaction entries in merged privilege log; overlapping annotations on a single page no longer produce multiple rows
- FIX: 5_Production.py — Include privilege log (CSV/XLSX) in Opposing Counsel deliverable ZIP; was previously only in the Full Archive package

### Document Trim Feature (2026-03-30)
- NEW: db_manager.py — `trim_document()` function: removes specified pages from a PDF, creating single trimmed child with page-renumbered redaction mark migration
- NEW: 4_Review.py — "Trim pages" mode in Split tab: page range input, validation, single-child trim workflow

### Document Split Feature (2026-03-30)
- NEW: auth_manager.py — `split_document` permission: manager-only gate for document splitting
- NEW: db_manager.py — `split_document()` function: splits multi-page PDFs into independent documents with page range extraction, control number assignment, redaction mark migration, and full audit logging
- NEW: db_manager.py — `split_source_cn` column migration for tracking split document lineage
- NEW: 4_Review.py — "Split" tab in document viewer: page range definition UI, validation (overlap/gap detection), confirmation workflow, post-split Processor redirect
- CHANGE: 4_Review.py — `Split_Source` status excluded from review grid; tab indexing converted to dynamic lookup

### Redaction Nav Bug Fix (2026-03-30)
- FIX: 4_Review.py — redact tab page nav buttons crashed with StreamlitAPIException; applied deferred pending pattern

### Documentation Update — Pre-Release (2026-03-30)
- DOCS: Walkthrough.md — version bump 2.8→2.9; added closed-case protections section; added Phase 6 (security hardening & audit remediation); added Phase 7.5 (M-4 database architecture); fixed PST extraction order (libpff primary, COM fallback)
- DOCS: User_Guide.md — version bump 2.8→2.9; added Section 20.6 (closed-case protections); expanded Section 14 (clawback) with subsections and FRCP reference; fixed PST extraction order
- DOCS: Technical Overview.md — version bump 2.8→2.9; added M-4 SQL migration section (centralized data access layer); fixed PST extraction order in module table
- DOCS: PROJECT_CONTEXT.md — version bump 2.8.0→2.9.0; fixed PST extraction order in repo structure and roadmap

### M-4 SQL Migration — Batch 7: Retry Operations + Case Settings (2026-03-27)
- CHANGE: db_manager.py — added 4 new functions: retry_processing_errors, retry_sync_errors, get_sync_error_details, save_case_settings_batch
- CHANGE: 2_Processor.py — migrated error retry to db_manager.retry_processing_errors()
- CHANGE: 6_Sync.py — migrated sync error retry, error detail query, and 3 case settings save patterns to db_manager calls

### M-4 SQL Migration — Batch 6: Production Record Management (2026-03-27)
- CHANGE: db_manager.py — added 2 new functions: delete_production_volume (atomic 3-step cache restore), get_production_gap_report
- CHANGE: 5_Production.py — consolidated 2 duplicate delete-volume patterns into db_manager.delete_production_volume(); migrated gap analysis query

### M-4 SQL Migration — Batch 5: Analytics Report Queries (2026-03-27)
- CHANGE: db_manager.py — added 6 new functions: get_exact_dupe_clusters, get_near_dupe_cluster_detail, get_all_exact_dupes_detail, get_content_dupe_clusters, get_custodian_activity_data, get_timeline_data
- CHANGE: 3_Analytics.py — migrated 4 dedup cluster pd.read_sql queries, communication analysis query, and timeline query to db_manager calls; eliminated _dr_conn shared connection

### M-4 SQL Migration — Batch 4: Custodian Operations (2026-03-27)
- CHANGE: db_manager.py — added 6 new functions: get_custodian_inventory_df_data, get_custodian_doc_stats, update_custodian_fields, rename_custodian (atomic 3-table), merge_custodians (atomic 3-table+delete)
- CHANGE: 7_Custodians.py — migrated inventory chart, detail panel, profile save, rename, and merge to db_manager calls; reused existing get_custodian()

### M-4 SQL Migration — Batch 3: Document Viewer + Tags + Batch Management (2026-03-27)
- CHANGE: db_manager.py — added 17 new functions: get_document, get_document_parent, get_document_children, get_document_tags, update_document_tags, set_redaction_status, get_redaction_status, mark_document_reviewed, get_unbatched_document_count, get_unbatched_documents, create_review_batch, assign_documents_to_batch, recalculate_batch_counts, update_batch_assignment, reassign_batch_documents, delete_all_batches
- CHANGE: 4_Review.py — migrated document viewer queries, tag read/write, redaction status, mark-reviewed, and full batch management section to db_manager calls; eliminated shared _batch_conn pattern

### M-4 SQL Migration — Batch 2: Saved Searches + Bates Lookup + 8_Exhibits (2026-03-27)
- CHANGE: db_manager.py — added 8 new functions: log_recent_search, get_named_searches, get_recent_searches, delete_saved_search, toggle_search_global, save_named_search, clear_recent_searches, get_all_bates_ranges
- CHANGE: 4_Review.py — migrated saved search CRUD, recent search rotation, and Bates lookup to db_manager calls
- FIX: 8_Exhibits.py — case_caption lookup used wrong column names (key/value → setting_key/setting_value); replaced with db_manager.get_matter_profile()

### M-4 SQL Migration — Batch 1: Status Count Consolidation (2026-03-27)
- CHANGE: db_manager.py — added 7 new functions: get_document_status_counts, get_review_tag_counts, get_processing_queue_stats, get_file_type_breakdown, get_data_reduction_stats, get_sync_status_counts, get_byos_status_counts
- CHANGE: home.py — migrated ~15 raw COUNT queries to db_manager calls
- CHANGE: 2_Processor.py — migrated 9 raw SQL queries (8 COUNTs + 1 GROUP BY) to db_manager calls
- CHANGE: 3_Analytics.py — migrated 10 data reduction COUNT queries to db_manager.get_data_reduction_stats()
- CHANGE: 6_Sync.py — migrated 4 sync status + 4 BYOS status queries to db_manager calls

### Low-Priority Audit Remediation — L-1, L-2, L-4 (2026-03-27)
- FIX: auth_manager.py — added validate_password_complexity() requiring 8+ chars, uppercase, and digit
- FIX: home.py — applied password complexity validation to Create User and Reset Password flows
- CHANGE: 1_Ingestor.py — improved progress bar granularity for file scan, dedup, and DB insert steps
- CHANGE: 6_Sync.py — extracted hardcoded Filevine API URLs to module-level constants

### Case Status Race Condition Guard — Audit Finding M-5 (2026-03-27)
- FIX: 4_Review.py — added case-status re-check in _safe_write() before all routed write operations
- FIX: 3_Analytics.py — added case-status re-check before threading/near-dupe tag clear and auto-tag bulk writes
- FIX: 7_Custodians.py — added case-status re-check before rename, merge, and reassign operations

### UI Polish — Audit Findings M-7 through M-10 (2026-03-27)
- FIX: 1_Ingestor.py — added missing key= parameters to Custodian Name, Bulk Auto-Tag, and Scan & Register widgets
- FIX: 5_Production.py — added missing key= parameters to filter checkboxes, tag selectbox, and Select/Deselect All buttons
- FIX: 7_Custodians.py — added explanatory st.caption when profile and hold status fields are disabled on closed cases
- FIX: 3_Analytics.py — added empty-state st.info message for Communication Analysis when no communicator data exists
- CHANGE: container_exploder.py — made COM mutex timeout configurable via config.COM_MUTEX_TIMEOUT_MS (default 300000)

### Review Audit Logging (2026-03-27)
- FIX: 4_Review.py — added log_audit() calls for 6 unlogged write operations (coding value changes, redaction status save/clear, saved search deletion, batch status changes)

### Processor Audit Logging (2026-03-27)
- FIX: 2_Processor.py — added log_audit() calls for 13 unlogged write operations (NIST exclusion, container scanning, duplicate marking, error statuses, retry, bulk status changes)

### Sync Audit Logging (2026-03-27)
- FIX: 6_Sync.py — added log_audit() calls for 12 unlogged write operations (7 sync error statuses, 5 config/settings changes)

### PST Header CRC Repair & Extraction Notes (2026-03-27)
- NEW: container_exploder.py — `_repair_pst_header_crc()` PST header CRC validation (DISABLED — MS-PST uses non-standard CRC variant; needs correct algorithm before enabling)
- FIX: container_exploder.py — `_explode_pst_com()` finally block now removes orphaned PST store mounts when root_folder reference was never captured (prevents zombie stores accumulating in Outlook after failed extractions)
- CHANGE: container_exploder.py — `explode_pst_isolated()` now uses libpff as primary backend, COM as fallback (libpff is headless/unattended; COM requires Outlook desktop session and can show blocking dialogs)
- FIX: container_exploder.py — replaced `multiprocessing.Process` with `subprocess.Popen` + dedicated `_pst_worker.py` for libpff extraction (Windows multiprocessing.spawn re-imports Streamlit entry point, causing ScriptRunContext pollution and libpff C-library hangs)
- NEW: _pst_worker.py — standalone PST extraction subprocess worker (clean Python process, no Streamlit imports)
- NEW: container_exploder.py — `_collect_html_referenced_images()` scans HTML body for inline image filename references
- FIX: container_exploder.py — `_explode_eml()` now skips image attachments referenced by filename in HTML body (catches inline signature images without Content-ID, restores parity with COM/MSG path)
- FIX: universal_imager.py — EML imaging now substitutes inline images referenced by filename (not just CID) into the email PDF before rendering; images are base64-embedded and excluded from the Attachments header
- FIX: 1_Ingestor.py — ingest button now disables during execution via session state flag to prevent duplicate ingestion from spam-clicking
- NEW: db_manager.py — `extraction_notes` column on documents table for defensible per-document extraction quality warnings
- CHANGE: container_exploder.py — `_libpff_message_to_eml()` returns per-message warnings when attachment B-tree corruption prevents attachment extraction
- CHANGE: container_exploder.py — `_walk_pst_folder_libpff()` collects per-message warnings into `child_warnings` dict
- CHANGE: container_exploder.py — `explode_pst_isolated()` applies CRC repair before COM/libpff attempts; threads `child_warnings` and `container_notes` through return dict
- CHANGE: 2_Processor.py — `add_children_to_db()` writes per-child `extraction_notes` from container extraction warnings
- CHANGE: 2_Processor.py — PST extraction block persists `container_notes` to the container document's `extraction_notes`
- CHANGE: 4_Review.py — extraction_notes warning banner displayed in document viewer for affected documents

### Security Hardening — Auth & Permission Guards (2026-03-27)
- FIX: auth_manager.py — admin CRUD functions (create_user, update_password, update_role, delete_user, update_allowed_cases) are now self-protecting with `_require_admin()` guard; bootstrap skips check when no users exist (C-1)
- FIX: auth_manager.py — block wildcard '*' permission and validate against ALL_PERMISSIONS in save_role_permissions() and create_custom_role() (C-2)
- FIX: auth_manager.py — block custom role inheriting from admin; cycle detection in _get_role_permissions() (H-5)
- FIX: auth_manager.py — clear session state on login to prevent session fixation (H-4)
- FIX: auth_manager.py — restrict auth_config.yaml file permissions after save (H-6)
- FIX: 3_Analytics.py — bulk tag operations now require 'tag' permission (H-3)
- FIX: 7_Custodians.py — operations section requires inline 'custodian_management' permission check (H-2)
- FIX: 1_Ingestor.py, 2_Processor.py, 4_Review.py — replaced 5 bare `except:` handlers with `except Exception:` (H-11)

### Holistic Audit Remediation — Critical Fixes (2026-03-27)
- FIX: 8_Exhibits.py — wrong session state key: changed "case_folder" to "current_case_folder" (module was non-functional)
- FIX: 8_Exhibits.py — broken closed-case check: replaced session state read with db_manager.get_case_status()
- FIX: home.py — added _clear_case_state() on all 4 case-switch paths to prevent stale data bleeding between cases
- FIX: 5_Production.py — SQL injection: replaced date string interpolation with parameterized query
- DOCS: Holistic Audit Passes 3-9 complete; remediation plan in docs/HOLISTIC_AUDIT_REMEDIATION.md
- FIX: DEPLOYMENT_GUIDE.md — corrected Python version 3.12 → 3.11 (line 84 contradicted line 110)
- CHANGE: .gitignore — added .superpowers/, .mcp.json, .claude/settings* (machine-specific AI tooling)

### Module Hardening Sprint 6: Resource Cleanup (2026-03-27)
- FIX: universal_imager.py — inline image stream leak: wrapped fitz.open(stream=...) in try/finally inside _append_inline_images_to_pdf() loop
- FIX: pdf_exporter.py — DB connection leak: wrapped get_connection() in try/finally in export_pdfs_to_zip()
- FIX: container_exploder.py — COM object init guard: verified msg=None already present before try block (audit confirmation)
- DOCS: context maintenance + documentation update after Sprints 5-6

### Module Hardening Sprint 5: Function Decomposition (2026-03-27)
- CHANGE: universal_imager.py — extracted _parse_msg_headers(), _parse_msg_body(), _parse_msg_attachments() shared helpers from convert_msg_to_pdf() and extract_msg_text(); no behavior changes
- CHANGE: universal_imager.py — decomposed flatten_pdf() into _detect_pdf_interactivity(), _flatten_xfa_pdf(), _flatten_acroform_pdf() router pattern; no behavior changes
- CHANGE: container_exploder.py — decomposed _libpff_message_to_eml() into _build_eml_headers(), _attach_eml_bodies(), _attach_eml_attachment(); no behavior changes

### Module Hardening Sprints 3-4 (2026-03-27)
- NEW: config.example.py — IMAGING_WORKERS setting for Production Pass 1 parallel worker default (0 = auto-detect)
- CHANGE: 5_Production.py — imaging workers slider reads default from config.IMAGING_WORKERS
- NEW: 5_Production.py — stale-production detector: scans for orphaned TEMP_/STAGED_ files from abandoned Pass 1 runs, shows cleanup button with audit logging
- CHANGE: 5_Production.py — retry loop timing: elapsed_seconds added to PRODUCTION_RETRY audit event
- CHANGE: 5_Production.py — Pass 2 timing: pass2_elapsed_seconds added to PRODUCTION_EXPORTED audit event
- DOCS: context maintenance + documentation update after Sprints 3-4

### Phase 24c.7: Exhibit List / Trial Binder (2026-03-26)
- NEW: db_manager.py — exhibit_sets and exhibits tables with CASCADE delete, indexes
- NEW: db_manager.py — 11 exhibit CRUD functions: create/get/update/delete exhibit sets, add/get/update/remove/reorder exhibits, get_document_exhibit_sets, get_next_sort_order
- NEW: auth_manager.py — exhibit permissions: mark_exhibit, view_exhibits, manage_exhibit_sets, manage_exhibits, export_exhibit_binder added to ALL_PERMISSIONS and role defaults
- NEW: 4_Review.py — Exhibit designation section in coding panel: exhibit badges for produced docs + "Mark as Exhibit" expander with set/number/description fields
- NEW: 8_Exhibits.py — Exhibits management page: set CRUD (create/edit/delete), exhibit list with reorder/remove, add-document search for produced docs
- NEW: 8_Exhibits.py — Binder PDF export: cover sheet, index with binder page numbers, per-exhibit divider pages, assembled via pdfkit + PyMuPDF
- DOCS: DEPENDENCY_MAP.md — added exhibit_sets and exhibits table cross-references
- DOCS: CLAUDE.md — context maintenance after Phase 24c.7

### Phase 24b-c: EDRM Workflow + Differentiators (2026-03-26)
- NEW: 3_Analytics.py — Custodian Overlap tab with cross-custodian content_hash overlap matrix + Plotly heatmap
- NEW: 3_Analytics.py — Concept Explorer tab with OpenSearch significant_text aggregation for keyword expansion
- NEW: home.py — Case Archive button in Case Maintenance (ZIP of entire case folder with MANIFEST.json)
- NEW: db_manager.py — coding_fields + document_coding tables with 7 CRUD functions for custom issue coding
- NEW: 4_Review.py — dynamic custom coding fields (picklist/text/boolean) rendered in coding panel from coding_fields config
- NEW: home.py — Issue Coding Fields admin UI in Case Maintenance (create/delete fields with pick lists)
- CHANGE: 5_Production.py — custom coding fields intentionally excluded from DAT/CSV load file (attorney work product, must not leave platform)

### Phase 25: Multi-Production Junction Table (2026-03-26)
- NEW: db_manager.py — document_productions junction table with UNIQUE(control_number, production_volume), backfill migration from existing Bates data, refresh_production_cache(), get_document_productions(), get_production_volume_records()
- CHANGE: db_manager.py — recalculate_last_bates_info() now queries document_productions as authoritative source with documents fallback
- CHANGE: 5_Production.py — Pass 2 writes to document_productions junction table + cache sync; both deletion paths delete from junction table then refresh cache; gap analysis queries junction table
- NEW: 4_Review.py — Production History expander for multi-production documents; stale-production warning when processed PDF is newer than produced PDF
- NEW: defensibility_report.py — Production Detail by Type section from junction table (volume, type, doc count, Bates range, dates)

### Module Hardening Sprint 2: Shared Email Rendering Pipeline (2026-03-26)
- CHANGE: universal_imager.py — extracted 6 shared helpers from convert_eml_to_pdf/convert_msg_to_pdf: _build_email_html, _wrap_plain_text_as_html, _substitute_cid_images, _run_wkhtmltopdf, _render_fitz_story, _append_inline_images_to_pdf. EML 284→126 lines, MSG 333→215 lines, net -110 lines. No behavior changes.

### Email Imager Hardening + Selective Re-Image (2026-03-26)
- FIX: universal_imager.py — inline image MIME type fallback for extensionless Outlook attachments (root cause of 500-blank-page bug)
- NEW: universal_imager.py — _strip_blank_pages() post-conversion safety net; _neutralize_external_images() to prevent dead-URL layout cascade
- CHANGE: universal_imager.py — FITZ_STORY_MAX_PAGES lowered 500→50; wkhtmltopdf hardened with --load-error-handling ignore, --disable-javascript; warning logs on all 4 fitz.Story page cap hits
- NEW: 4_Review.py — _reimage_document() function + Re-Image UI section (admin/manager, emails only, two-click safety, full review state reset)
- NEW: auth_manager.py — 'reimage' permission added to ALL_PERMISSIONS and manager default set

### Phase 24a: EDRM Defensibility Gaps (2026-03-26)
- NEW: db_manager.py — collection_scope table + 4 CRUD functions; DEFAULT_NIST_EXTENSIONS constant + get/set_nist_extensions() functions
- NEW: 7_Custodians.py — Collection Scope tab with per-custodian per-source status tracking (Collected/Searched-No-Hit/Not-Reasonably-Accessible/Out-of-Scope) and justification
- NEW: defensibility_report.py — Section 2.2 Collection Scope & Justification table; renumbered prior 2.2/2.3 to 2.3/2.4
- NEW: auth_manager.py — session timeout / auto-logout after configurable inactivity period (default 30 min via auth_config.yaml)
- NEW: home.py — Hash Integrity Verification (re-hashes all files, flags mismatches/missing); De-NIST Filter Configuration (edit/save/reset extensions, export exclusion report)
- CHANGE: 2_Processor.py — NIST extensions loaded from case_settings (configurable per case) with hardcoded fallback

### Phase 23: Production UX Overhaul (2026-03-26)
- NEW: 5_Production.py — post-finalization screen with compact summary (Bates range, doc/privilege/redaction/error counts), QC report expander, deliverable ZIP download (opposing counsel), full archive ZIP download, individual internal work product CSV downloads, and "Start New Production" reset button
- CHANGE: 5_Production.py — case-closed gate now allows post-finalization downloads (reads) while still blocking write operations
- CHANGE: auth_manager.py, home.py, 1_Ingestor.py, 2_Processor.py, 3_Analytics.py, 4_Review.py, 5_Production.py, 6_Sync.py, 7_Custodians.py — migrated use_container_width=True → width='stretch' (139 occurrences) to clear Streamlit deprecation warnings

### Phase 22: Defensibility Essentials + Review Workflow (2026-03-25)
- NEW: home.py — Matter Profile card with 10 fields (matter #, caption, court, judge, dates, etc.); admin-editable, read-only for others
- NEW: db_manager.py — get/set_matter_profile() helpers, get_processing_exceptions(), production_runs table + 3 helpers, document_notes table + 4 helpers, confidentiality_designation column + 4 helpers
- NEW: 2_Processor.py — Processing Exception Report with 4 metrics + 3-sheet Excel export (Summary, Detail, NIST)
- NEW: 5_Production.py — production run recorded at finalization; TextLink in DAT; per-doc confidentiality endorsement override at all stamping sites
- NEW: home.py — Production History dataframe on dashboard
- NEW: 4_Review.py — date range filter (From/To) with COALESCE(date_sent, date_created) WHERE injection
- NEW: 4_Review.py — Reviewer Notes expander (per-user per-document, managers see all notes)
- NEW: 4_Review.py — Confidentiality selectbox in coding panel (None/Confidential/Highly Confidential/AEO)
- FIX: 5_Production.py — DAT column consistency across withhold/normal records; TextLink field added
- CHANGE: defensibility_report.py — matter profile in cover page + Executive Summary; production run history table in Section 6

### EDRM Gap Analysis (2026-03-25)
- NEW: EDRM_GAP_ANALYSIS.md — comprehensive gap analysis of platform features against EDRM framework; 17 identified gaps prioritized by legal exposure, 5 recommended implementation phases
- CHANGE: ROADMAP_TODO.md — fixed stale Sprint 1 checkboxes (were unchecked but completed)

### Documentation Overhaul (2026-03-25)
- DOCS: PROJECT_CONTEXT.md — comprehensive update: added Module 7 (Custodians), defensibility report, review batching, Plotly charts, OS payload fix, dedup hardening, deferred OCR, production modes, reindex utility, CLI standing orders, closed-case read-only, 4 new DB tables, 15+ new audit actions, plotly dependency, 6 new known issues
- DOCS: User_Guide.md — added 4 new sections (16: Review Batching, 17: Managing Custodians, 18: Legal Hold Tracking, 19: Generating Reports), updated audit export to 3 formats, updated permissions table
- DOCS: Technical Overview.md — added Custodian Management, Defensibility Report, Review Batching sections; updated OS schema (30 fields), Production modes/deferred OCR, dependencies table, case folder structure
- DOCS: Walkthrough.md — added Custodian Management, Review Batching, Defensibility Report sections; updated audit export capabilities; added Phase 7 (Demo Readiness) to deployment roadmap
- DOCS: ROADMAP_TODO.md — added Phase 21 (Demo Readiness) with all completed items; added Holistic Audit Passes 3-9 to backlog
- CHANGE: Deleted 8 completed spec files (audit trail, docs overhaul, expert reviewer, mass PDF export, pass2 corrections, permission system, privilege disposition, two-pass production); marked Module Hardening Sprint 1 as complete

### Manual Testing Bugfixes (2026-03-25)
- FIX: auth_config.yaml — added `custodian_management` to manager role_permissions (YAML override was missing the new permission)
- FIX: 7_Custodians.py — profile and hold form widget keys now include custodian name to prevent field persistence across custodian selection
- FIX: defensibility_report.py — `_fmt_date()` helper formats ISO timestamps to readable dates (e.g. "January 20, 1985" not "1985-01-20T20:00:27+00:00")
- FIX: 7_Custodians.py — date range display uses short date format (YYYY-MM-DD) instead of raw ISO timestamp
- FIX: home.py — Case Maintenance (Factory Reset) gated behind `user_admin` permission; was visible to all roles
- FIX: home.py — System Backend Settings gated behind `user_admin` permission; was visible to all roles
- FIX: home.py — removed duplicate case status dropdown from main page (sidebar control is the single source of truth); status banner still shows warnings
- FIX: 4_Review.py — removed st.stop() on closed cases; page now loads read-only with write buttons disabled (was blank page with only warning banner)
- FIX: 3_Analytics.py — same closed-case read-only fix; all analytics tabs now viewable on closed matters

### Review Batching (2026-03-24)
- NEW: db_manager.py — `review_batches` and `batch_documents` tables with UNIQUE(control_number) constraint; `reviewed_by`/`reviewed_at` migration on documents table
- NEW: db_manager.py — helper functions: get_user_batches(), get_all_batches(), get_batch_for_document()
- NEW: 4_Review.py — Batch Management sidebar expander (Manager+) with auto-split creation using family-aware LPT algorithm, batch list with assignment, manual editing, delete all
- NEW: 4_Review.py — batch filter toggle (All Documents / My Batch) defaulting to assigned batch for Reviewers, All Documents for Managers
- NEW: 4_Review.py — batch WHERE clause injection stacks with all existing nav/search filters
- CHANGE: 4_Review.py — "Reviewed — Next ▶" button writes `reviewed_by`/`reviewed_at` (explicit determination); plain "Save" preserves tags only (work in progress)
- NEW: 4_Review.py — batch progress banner above grid when viewing a batch
- NEW: 4_Review.py — auto-update batch status (In Progress / Complete) after each save based on reviewed_by

### Custodian Management — Sprint 2: Legal Hold Tracking (2026-03-24)
- NEW: 7_Custodians.py — hold status card with color-coded display, timeline form (issued/acknowledged/released dates, method, recipient, notes), save with HOLD_STATUS_CHANGED audit
- NEW: 7_Custodians.py — hold document upload (st.file_uploader) to Hold_Documents/{custodian}/ with type selector, duplicate filename handling, and HOLD_DOCUMENT_UPLOADED audit
- NEW: 7_Custodians.py — uploaded document list with type badges, download buttons, two-click delete with HOLD_DOCUMENT_DELETED audit
- NEW: 7_Custodians.py — case hold summary dashboard with metrics (active/released/unacknowledged) and Plotly Gantt-style hold timeline chart
- NEW: defensibility_report.py — Section 9: Legal Hold Tracking with hold metrics, unacknowledged warning, and custodian hold status table

### Custodian Management — Sprint 1 (2026-03-24)
- NEW: pages/7_Custodians.py — Custodian Management page with inventory bar chart, profile editing, and 4 operations tabs (Rename, Merge, Reassign, Collections)
- NEW: db_manager.py — `custodians` and `hold_documents` tables with auto-population migration from existing documents
- NEW: db_manager.py — helper functions: get_custodians(), get_custodian(), sync_custodians_from_documents(), get_hold_documents()
- CHANGE: auth_manager.py — added `custodian_management` permission to manager default role and ALL_PERMISSIONS list
- DOCS: db_manager.py — expanded audit action vocabulary with 9 new custodian/hold event types

### Audit Trail Export Upgrade (2026-03-24)
- NEW: defensibility_report.py — `generate_audit_export_pdf()` produces landscape PDF of filtered audit trail with repeating headers, filter criteria, and confidential stamp
- CHANGE: home.py — audit log export expanded from single CSV button to 3-column row: CSV, Excel (.xlsx with metadata sheet, frozen pane, auto-width), and PDF
- NEW: home.py — Excel audit export includes Export Metadata sheet documenting all applied filter criteria

### Defensibility Report Bugfixes (2026-03-24)
- FIX: defensibility_report.py — tag separator mismatch: split on semicolons (DB format) not just commas; compound tag strings now correctly counted individually
- FIX: defensibility_report.py — review completion >100%: tagged_count now excludes suppressed docs and only counts documents with at least one non-system tag (SYSTEM_TAGS constant)
- FIX: defensibility_report.py — white-space:nowrap on table cells prevents formatted numbers from breaking across lines in wkhtmltopdf output
- FIX: defensibility_report.py — tr page-break-inside:avoid + thead display:table-header-group prevents orphaned table rows and repeats headers across page breaks

### Dashboard & Analytics Plotly Upgrade (2026-03-24)
- NEW: home.py — pipeline funnel chart (Plotly) showing ingested→processed→reviewed→produced flow
- CHANGE: home.py — Review Decision Breakdown replaced from st.dataframe to interactive Plotly donut chart with hover tooltips
- NEW: 3_Analytics.py — population reduction waterfall chart in Dedup Report tab
- CHANGE: 3_Analytics.py — Top Communicators replaced from st.dataframe to stacked horizontal bar chart (sent/received)
- CHANGE: 3_Analytics.py — Communication Matrix replaced from st.dataframe to Plotly heatmap with intensity colorscale
- CHANGE: 3_Analytics.py — Timeline st.bar_chart replaced with Plotly bar chart with red gap region annotations
- CHANGE: 3_Analytics.py — Domain Frequency replaced from st.dataframe to internal/external pie + stacked bar; domain pairs to horizontal bar
- NEW: requirements.txt — added plotly>=5.24.0 dependency

### Defensibility Report Generator (2026-03-24)
- NEW: defensibility_report.py — court-ready PDF report assembling 8 sections (case overview, ingestion, processing, deduplication, review, production, privilege, audit trail) from existing case data via pdfkit/wkhtmltopdf
- NEW: home.py — Defensibility Report section with generate button and download, gated to `production` permission, with REPORT_GENERATED audit logging

### OpenSearch Payload Fix + Reindex Utility (2026-03-24)
- FIX: 2_Processor.py — renamed OS payload field `filename` → `file_name` and `subject` → `email_subject` to match consumer queries in Review/Analytics
- FIX: 2_Processor.py — added `source_party` and `production_volume` to OS payload; party/volume filters in Review were previously no-ops
- FIX: 4_Review.py — updated search field list and STR field map from `filename` to `file_name` to match corrected OS index
- NEW: os_manager.py — `reindex_from_sqlite()` rebuilds OS index from SQLite metadata without reprocessing source files; preserves existing content text via bulk scan
- NEW: 6_Sync.py — Search Index Maintenance section (Admin only) with SQLite/OS count metrics, rebuild button with confirmation, progress bar, and audit logging
- DOCS: DEPENDENCY_MAP.md — updated §4 indexed fields list and removed resolved known bugs

### CLI Intelligence Hardening (2026-03-24)
- NEW: DEPENDENCY_MAP.md — cross-module dependency reference mapping all shared DB columns, file paths, session state keys, OpenSearch fields, config values, and shared functions; includes known regression patterns and live bug inventory
- DOCS: CLAUDE.md — added Pre-Fix Investigation Protocol standing order (iron law: no fix without root cause, 3-strike circuit breaker)
- DOCS: CLAUDE.md — added Post-Sprint Cross-Module Impact Audit standing order (mandatory dependency verification after every sprint)
- DOCS: CLAUDE.md — added Dependency Map Maintenance standing order (keep DEPENDENCY_MAP.md current on every cross-module change)
- DOCS: CLAUDE.md — added DEPENDENCY_MAP.md to Dependency API References table
- DOCS: MEMORY.md — refreshed from stale state to current beta-2.8

### Deferred Parallel OCR (2026-03-24)
- NEW: 5_Production.py — deferred OCR post-pass with ThreadPoolExecutor; captures pixmaps inline during Pass 2 loop, runs Tesseract in parallel after sequential assembly completes
- CHANGE: 5_Production.py — inline OCR fallback replaced with pixmap capture and placeholder text file; fast-path (embedded text) unchanged
- NEW: 5_Production.py — QC report "Deferred OCR" INFO row when OCR items are queued; cancellation handler clears deferred queue memory

### Production Mode Toggle (2026-03-24)
- NEW: 5_Production.py — Simple vs Full EDRM production mode selector; Simple mode outputs Bates-stamped images + natives with privilege/redaction logs, skipping text extraction and load files

### Dedup Hardening (2026-03-24)
- FIX: 2_Processor.py — pre-seed seen_md5s from prior processing runs to catch cross-batch duplicates
- NEW: 2_Processor.py — content-hash (SHA-256) dedup layer catches identical text from different binary files; marks as `Duplicate (Content)`
- CHANGE: 4_Review.py — duplicate filters use `NOT LIKE 'Duplicate%'` to cover both MD5 and Content types
- CHANGE: 6_Sync.py — duplicate exclusions updated for new Duplicate (Content) status
- CHANGE: 3_Analytics.py — dedup report includes content-hash duplicates as separate metric, cluster section, and Excel export sheet

### Collapsible Sidebar Tree + Spacing Fix (2026-03-24)
- NEW: 4_Review.py — `_render_tree_btn()` replaces st.radio tree navigator with collapsible button-based folder tree supporting party/custodian/collection/subcollection/volume hierarchy
- CHANGE: 4_Review.py — sidebar CSS overrides collapse Streamlit default button gaps for tight tree layout

### Module Hardening Sprint 1 (2026-03-24)
- CHANGE: universal_imager.py — extracted 9 shared OLE helpers to module level; removed duplicate inner definitions from convert_msg_to_pdf() and extract_msg_text()
- FIX: universal_imager.py, container_exploder.py, pdf_exporter.py, email_imager.py — added logging to 25+ bare except:pass blocks across all four modules; no control flow changes
- CHANGE: universal_imager.py — named constants (FITZ_STORY_MAX_PAGES, XFA_EMPTY_THRESHOLD, INTERACTIVE_ANNOT_TYPES, etc.) replacing raw literals
- CHANGE: container_exploder.py — named constants (MAPI_ATTACH_EMBEDDED_MSG, PR_ATTACH_FLAGS_INLINE, OL_MSG_FORMAT, OL_DISCARD) replacing raw literals
- CHANGE: pdf_exporter.py — named constant FILENAME_MAX_LENGTH replacing raw literal
- DOCS: ROADMAP_TODO.md — added Phase 20: Module Hardening with 4 risk-ordered sprints

### RTF De-encapsulation Fix + Imager Audit (2026-03-24)
- FIX: universal_imager.py — `\par` regex was matching inside `\pard`, leaving orphan `d` chars and `\plain\f0` in rendered email PDFs; replaced inline regex chains in both `convert_msg_to_pdf()` and `extract_msg_text()` with shared `_scrub_rtf_from_html()` helper
- NEW: universal_imager.py — `_scrub_rtf_from_html()` strips 50+ RTF control word families with word-boundary safety, longest-first ordering, and catch-all safety net
- FIX: universal_imager.py — all 14 `print()` calls converted to `logger.warning()`/`logger.error()` (Streamlit silently swallows print output)
- FIX: universal_imager.py — bare `except: pass` on RTF de-encapsulation in `extract_msg_text()` now logs the error

### Review Grid & Redact Navigation Fixes (2026-03-24)
- FIX: 4_Review.py — grid pagination arrows (⏮◀▶⏭) were immediately overridden by auto-flip logic that snapped back to the current viewer document's page; auto-flip now only fires when the viewer document actually changes (sidebar/tree click), not on grid page navigation

### Redact Tab Page Navigation Fix (2026-03-24)
- FIX: 4_Review.py — Redact tab page jump text input was clobbered by pre-render sync overwriting user input before the widget rendered; arrow buttons now sync the text input directly, eliminating the extra rerun flicker

### Scrollable Multi-Page PDF Viewer (2026-03-24)
- CHANGE: 4_Review.py — `_display_pdf_viewer()` now renders ALL pages stacked in a scrollable container instead of single-page navigation; eliminates ◀/▶ page buttons
- FIX: 4_Review.py — removed `_pdf_page_navigator()` (dead code after scrollable viewer)
- NEW: 4_Review.py — per-page DPI calculation handles mixed page sizes; progress bar for 10+ page docs; graceful placeholder for corrupted pages
- NEW: 4_Review.py — page number dividers ("— Page N of M —") between every page in scrollable viewer
- FIX: 4_Review.py — theme-aware colors via CSS variables (dark/light mode compatible); defaults tuned to 1200px height / 800px width for portrait reading

### Server-Side PDF Rendering (2026-03-24)
- NEW: 4_Review.py — `_render_pdf_page_image()` renders PDF pages as PNG via PyMuPDF with optional search highlighting
- NEW: 4_Review.py — `_get_pdf_page_count()` lightweight page count with password-protected PDF detection
- NEW: 4_Review.py — `_pdf_page_navigator()` reusable page navigation widget with session state persistence
- NEW: 4_Review.py — `_display_pdf_viewer()` drop-in replacement for iframe PDF embedding
- FIX: 4_Review.py — replaced all 3 iframe `data:application/pdf;base64` embeds with server-side rendering; fixes blank viewer on complex DocuSign PDFs with many Form XObjects

### Codebase Audit Bug Fixes (2026-03-23)
- FIX: 2_Processor.py — atomic `check_and_add()` on ThreadSafeSet eliminates TOCTOU race in MD5 and content-hash deduplication
- FIX: pdf_exporter.py — Bates range family span now uses numeric suffix comparison instead of broken string comparison
- FIX: 4_Review.py — try/finally on all fitz.open() calls prevents file handle leaks on exception paths (highlight, Bates extraction, redaction)
- FIX: universal_imager.py — try/finally on fitz.open() in flatten_pdf, convert_image_to_pdf, convert_text_to_pdf, convert_pdf_to_tiff, generate_slipsheet, generate_privilege_placeholder, stamp_bates_on_pdf
- FIX: container_exploder.py — ZIP member handle wrapped in `with` statement; libpff file object properly closed in fallback path
- FIX: 5_Production.py — OCR error display capped at 10 items in UI; all errors logged to processing log
- FIX: 4_Review.py — inline open() for .msg PDF view wrapped in `with` statement
- FIX: 2_Processor.py — inline open() for container child MD5 wrapped in `with` statement
- FIX: pdf_exporter.py — try/finally on _merge_pdfs() and _convert_native_to_pdf() fitz handles
- FIX: 6_Sync.py — try/finally on fitz.open() in annotation reconciliation and scan_for_redactions
- NEW: pdf_exporter.py — `_bates_number_sort_key()` helper for numeric Bates comparison

### Context Maintenance Infrastructure (2026-03-23)
- DOCS: CLAUDE.md — added Current State section and Standing Orders for automated context maintenance
- DOCS: MEMORY.md — created current-state snapshot in Claude memory directory for cross-session continuity

### XFA-Aware PDF Flatten (2026-03-23)
- FIX: universal_imager.py — `flatten_pdf()` now detects XFA forms before stripping; XFA pages are rasterized at 200 DPI (preserves visual content) while normal pages in hybrid docs keep text selectability; fixes blank pages on DocuSign/dotloop contracts (DOC-000020)

### Flatten Interactive PDF Elements for Production (2026-03-23)
- NEW: universal_imager.py — `flatten_pdf()` helper strips form fields, JavaScript, embedded files, and interactive annotations from PDFs during production imaging
- CHANGE: universal_imager.py — PDF passthrough in `image_document()` now routes through `flatten_pdf()` instead of raw `shutil.copy2()`
- CHANGE: universal_imager.py — Bates stamping `stamp_bates_on_pdf()` now always uses full rewrite (garbage=4, clean=True) instead of incremental save to prevent interactive element survival
- CHANGE: 2_Processor.py — `process_file_worker()` now calls `flatten_pdf()` when copying PDFs to Processed/, with raw-copy fallback on flatten failure; fixes blank-page rendering in Review viewer for XFA/AcroForm documents
- FIX: 2_Processor.py — removed redundant `import universal_imager` inside `.msg` and `.eml` branches of `process_file_worker()`; local imports shadowed the module-level name causing `UnboundLocalError` on the PDF flatten path
- NEW: _migration_flatten_pdfs.py — one-time migration script to re-flatten existing processed PDFs in a case that were copied before the flatten fix

### Natural-Sort Ingestion Ordering (2026-03-21)
- NEW: 1_Ingestor.py — Natural-sort helper `_natural_sort_key()` for human-friendly file/folder ordering
- CHANGE: 1_Ingestor.py — All os.walk loops and directory listings now sort dirs and files with natural sort
- CHANGE: 1_Ingestor.py — Re-sort `new_files_batch` after parallel hashing to restore walk order before DB insertion

### Rotation-Aware Bates Stamping (2026-03-21)
- FIX: universal_imager.py — Bates stamps now render correctly on rotated PDF pages using derotation_matrix coordinate transformation

### Family Bates Range Fix (2026-03-21)
- FIX: pdf_exporter.py — Family Bates range naming now spans parent begdoc through last child enddoc when combining families

### LibreOffice Error Reporting Fix (2026-03-20)
- FIX: universal_imager.py — Surface actual LibreOffice conversion errors instead of misleading "not installed" message; replace print() with logger.warning()

### EDRM-Aligned Imaging Policy (2026-03-20)
- NEW: universal_imager.py — EDRM imaging policy constants (IMAGE_BY_POLICY, NATIVE_BY_POLICY) and helpers (should_image, is_native_by_policy)
- CHANGE: universal_imager.py — Added EDRM policy gate to image_document() refusing native-by-policy formats (spreadsheets)
- FIX: universal_imager.py — Added .rtf to LibreOffice routing (was falling through as unsupported)
- CHANGE: 5_Production.py — Replaced hardcoded DEFAULT_NATIVE_EXTENSIONS whitelist with policy-based classification via universal_imager.should_image()
- CHANGE: 5_Production.py — Pre-filter expected natives in Full EDRM pre-sort loop to skip imaging pool

### Fix Ghost Bates After Simple Production Delete (2026-03-21)
- FIX: 5_Production.py — replace CSV-based Bates clearing with direct DB query by production_volume; fixes ghost Bates when deleting Simple Productions (no loadfile)

### Clear Stale Bates Continuity on Production Delete (2026-03-20)
- NEW: db_manager.py — recalculate_last_bates_info() rebuilds Bates continuity record from remaining produced documents after deletion
- FIX: 5_Production.py — sidebar delete handler and DELETE & RE-RUN handler now recalculate Bates continuity to prevent stale gaps

### Folder-Based Bates Sorting + Disclosure Certificate Summary (2026-03-20)
- NEW: 5_Production.py — folder-based document ordering toggle sorts by source_collection/source_subcollection before family grouping
- NEW: 5_Production.py — family folder inheritance prevents family splits across folder sections
- NEW: 5_Production.py — post-production folder-to-Bates range summary table with CSV export and download button

### Bates Stamp Repaired-PDF Normalization (2026-03-20)
- FIX: universal_imager.py — stamp_bates_on_pdf() now detects fitz-repaired PDFs and rewrites to a clean copy before stamping, preventing "document closed" errors on structurally damaged PDFs

### OCR Decompression Bomb + Bates Stamp Incremental Save Fixes (2026-03-21)
- FIX: 5_Production.py — disable PIL MAX_IMAGE_PIXELS limit in _ocr_worker for large-format scans (trusted case documents)
- FIX: universal_imager.py — disable PIL MAX_IMAGE_PIXELS limit in convert_pdf_to_tiff for large-format pages
- FIX: universal_imager.py — stamp_bates_on_pdf() falls back to full save via temp file when saveIncr() fails on repaired/reconstructed PDFs

### Production Mode Toggle — Simple vs Full EDRM (2026-03-21)
- NEW: 5_Production.py — production mode radio selector (Simple Production / Full EDRM Production) in Configure Production UI
- CHANGE: 5_Production.py — Simple mode skips text extraction, OCR, Concordance DAT, Opticon OPT, cross-reference CSV, QC report, and TEXT/ directory creation; privilege log, redaction log, DB updates, and audit entries always run in both modes
- CHANGE: 5_Production.py — deferred OCR pass guarded by _is_full_edrm; PRODUCTION_EXPORTED audit entry includes mode field

### Deferred Parallel OCR in Pass 2 (2026-03-20)
- NEW: 5_Production.py — deferred OCR: capture pixmaps inline (post-redaction, pre-stamp), run Tesseract in parallel via ThreadPoolExecutor after assembly loop; progress bar, per-doc error reporting, PRODUCTION_OCR_COMPLETE audit entry
- CHANGE: 5_Production.py — inline OCR fallback replaced with pixmap capture + empty placeholder; QC report shows deferred OCR info row; cancellation handler clears deferred queue

### Parallel Pass 1 Imaging (2026-03-20)
- NEW: 5_Production.py — parallel imaging via ProcessPoolExecutor for Pass 1; configurable worker count slider; pre-classification of containers/withheld/native before pool submission
- CHANGE: 5_Production.py — _handle_retry() uses parallel workers when multiple failures; timing metrics (elapsed_seconds, workers) in PRODUCTION_PASS1_COMPLETE audit log

### Family-Aware Production Selection Grid (2026-03-20)
- NEW: 5_Production.py — family-aware selection grid with parent/child hierarchy sorting, indent display, family metrics, and expansion preview on confirm

### Retroactive Dedup Sweep Migration (2026-03-20)
- NEW: _migration_dedup_sweep.py — one-time migration script to find and mark cross-batch MD5 and content-hash duplicates from pre-hardening processing runs

### Collapsible Sidebar Document Navigator (2026-03-20)
- NEW: 4_Review.py — collapsible button-based tree replaces flat radio list; ▶/▼ arrows toggle child visibility
- CHANGE: 4_Review.py — compact CSS for ultra-tight tree spacing; selected node highlighted with blue left border
- FIX: 4_Review.py — remove wrapper div markdown calls from tree buttons; use primary/secondary button types + adjacent-sibling CSS for proper spacing

### Dedup Hardening — Pre-Seed MD5 + Content-Hash Dedup Layer (2026-03-20)
- FIX: 2_Processor.py — pre-seed seen_md5s from prior processing runs to catch cross-batch duplicates
- NEW: 2_Processor.py — content-hash (SHA-256) dedup layer catches identical text from different binary files
- CHANGE: 4_Review.py — duplicate filters use NOT LIKE 'Duplicate%' to cover both MD5 and Content types
- CHANGE: 6_Sync.py — duplicate exclusions updated for new Duplicate (Content) status
- CHANGE: 3_Analytics.py — dedup report includes content-hash duplicates as separate metric and section
- CHANGE: home.py — dashboard duplicate count includes both MD5 and Content duplicates

### Review Grid Server-Side Pagination (2026-03-20)
- NEW: 4_Review.py — server-side pagination for document grid (page size selector, navigation controls, auto-page-flip on viewer navigation)
- CHANGE: 4_Review.py — sidebar navigator: unified folder icons, compact CSS for tighter spacing between tree items

### UUID Prefix Cleanup — Preserve Original Filenames in DB (2026-03-20)
- FIX: container_exploder.py — process_msg_batch() no longer leaks UUID prefix into file_name and logical_path return tuple elements
- FIX: container_exploder.py — _walk_pst_folder_com() logical_path now uses clean subject name instead of UUID-prefixed filename
- FIX: container_exploder.py — _walk_pst_folder_libpff() logical_path now uses clean subject name instead of UUID-prefixed filename
- NEW: db_manager.py — One-time migration (uuid_prefix_strip_v1) strips leaked UUID prefixes from file_name and original_path in existing records

### Hotfix: Remove PST Mutex + Skip Non-Essential Folders (2026-03-20)
- FIX: container_exploder.py — Remove COM mutex from PST extraction (already serialized by Processor loop; mutex was timing out on large PSTs)
- FIX: container_exploder.py — Skip Deleted Items and other non-essential Outlook folders during PST COM extraction (9000+ deleted stubs in 761KB PST was causing 20-min extraction for 11 emails)

### Hotfix: COM State Recovery Between PSTs (2026-03-19)
- FIX: container_exploder.py — Add COM retry with 5s recovery delay between attempts; aggressive COM object cleanup after each PST to prevent MAPI state poisoning

### Hotfix: COM PST In Main Process (2026-03-19)
- FIX: container_exploder.py — Run COM PST extraction in main process (COM requires desktop session context and hangs in subprocess); subprocess isolation retained for libpff fallback only

### COM-Primary PST Extraction (2026-03-19)
- NEW: container_exploder.py — _explode_pst_com() and _walk_pst_folder_com(): COM-based PST extraction with stats tracking matching libpff return format
- CHANGE: container_exploder.py — _pst_subprocess_worker() now tries COM first, falls back to libpff when Outlook unavailable
- CHANGE: container_exploder.py — Renamed explode_pst() to explode_pst_libpff() (now fallback path)

### Subprocess-Isolated PST Extraction (2026-03-19)
- NEW: container_exploder.py — _pst_subprocess_worker() and explode_pst_isolated() run each PST extraction in an isolated subprocess to prevent C-level state corruption cascade between PSTs
- CHANGE: container_exploder.py — explode_container() routes PSTs through subprocess isolation; accepts optional log_path parameter
- CHANGE: 2_Processor.py — PSTs extracted sequentially in isolated subprocesses; ZIPs/EMLs remain in ThreadPoolExecutor

### libpff Attachment Count Error Handling + ES Row Bug (2026-03-19)
- FIX: container_exploder.py — Guard number_of_attachments against corrupted PST local descriptors; extract messages without attachments instead of losing them entirely
- FIX: container_exploder.py — Protect pst_file.close() against corrupted C file handles
- FIX: 2_Processor.py — Fix sqlite3.Row .get() error in OpenSearch document queuing

### Embedded Messages, Nested EML, COM Mutex (2026-03-18)
- FIX: container_exploder.py — Handle embedded MAPI messages (PR_ATTACH_METHOD=5) in libpff PST extraction via recursive EML conversion
- FIX: container_exploder.py — Handle message/rfc822 nested emails in _explode_eml() with controlled MIME walk to prevent duplicates
- NEW: container_exploder.py — _walk_mime_parts() helper stops descent into message/rfc822 to prevent duplicate extraction
- NEW: container_exploder.py — Cross-process named mutex serializes Outlook COM access to prevent concurrent session conflicts
- FIX: 2_Processor.py — Handle TimeoutError from COM mutex in MSG batch extraction

### PST Extraction Reliability (2026-03-18)
- CHANGE: container_exploder.py — Remove COM PST extraction; libpff is now sole PST backend
- NEW: container_exploder.py — Extraction validation: expected vs actual count tracking per folder
- NEW: container_exploder.py — find_scanpst() discovers Microsoft Inbox Repair Tool
- NEW: 2_Processor.py — Phase 1 extraction summary table (expected vs extracted per container)
- NEW: 2_Processor.py — Partial_Extraction status for PSTs with incomplete extraction
- NEW: 2_Processor.py — re_extract_container() deletes children and resets PST for clean re-run
- NEW: 2_Processor.py — Re-Extract UI with ScanPST integration for damaged PSTs
- FIX: 2_Processor.py — Add 300s timeout to container extraction futures

### Source Collections & Folder Organization (2026-03-18)
- NEW: db_manager.py — source_collection and source_subcollection columns with schema migration and one-time backfill from existing original_path values
- NEW: 1_Ingestor.py — structured ingestion mode toggle: auto-detects custodian, collection, and subcollection from folder hierarchy under Ingest/; flat mode preserved as default for backward compatibility
- NEW: 1_Ingestor.py — folder structure preview in structured mode shows detected custodians, collections, and subcollections with file counts
- CHANGE: 4_Review.py — Document Navigator tree expanded: Internal → custodian → collection → subcollection; external documents retain party → volume pattern
- NEW: 4_Review.py — source_collection and source_subcollection added as selectable and filterable grid columns
- CHANGE: 2_Processor.py — OpenSearch document payload includes source_collection and source_subcollection
- FIX: db_manager.py — removed automatic original_path backfill for source_collection/source_subcollection; container-exploded documents have parent filenames in their paths which were incorrectly treated as folder structure; one-time cleanup clears bad data
- FIX: home.py — call init_db() before dashboard stats queries to prevent "no such table: documents" error on newly created cases
- FIX: 3_Analytics.py — check OpenSearch index exists before scan() to prevent index_not_found crash on unprocessed cases

### Tag Display Cleanup (2026-03-18)
- CHANGE: 4_Review.py — review grid Tags column now hides system tags (NearDupe-*, Thread-*, NIST-*, Junk, Inclusive); only reviewer-applied tags (privilege, responsiveness, review status) are visible in the grid
- NEW: 4_Review.py — privilege_status added as a selectable grid column ("Privilege Disposition") showing Redact/Withhold status with emoji indicators
- CHANGE: 4_Review.py — system tags in the coding panel collapsed into an expander by default, keeping privilege and disposition controls above the fold

### Privilege Disposition System (2026-03-18)
- NEW: db_manager.py — privilege_status column (NULL/Redact/Withhold) with schema migration; get_privilege_status() and set_privilege_status() helpers
- NEW: 4_Review.py — Privilege Disposition selector in coding panel; appears when privilege tags are selected; options: "Redact & Produce" or "Withhold Entirely"
- CHANGE: 4_Review.py — _r_sync_tags() now auto-sets privilege_status='Redact' when privilege-category redaction marks are placed; never overwrites manual 'Withhold' disposition
- NEW: universal_imager.py — generate_privilege_placeholder() creates branded "DOCUMENT WITHHELD" slip sheets with privilege basis, Bates number, and optional endorsement
- REFACTOR: 5_Production.py — removed "Exclude Privileged" checkbox; privilege handling now automatic via privilege_status column; Withhold documents get placeholder slip sheets with Bates numbers; Redact documents produced with burns
- NEW: 5_Production.py — pre-production safety gate: hard-blocks production if any Redact-disposition documents have no redaction marks placed; soft-warns if privilege-tagged documents have no disposition set
- NEW: 5_Production.py — unified privilege log includes both Withheld and Redact entries with Disposition column
- CHANGE: 5_Production.py — QC checks redesigned for disposition awareness: Rogue Marks, Missing Marks, Withheld count, Privilege Log Completeness
- CHANGE: 5_Production.py — Privilege Log tab now shows disposition status and flags documents needing disposition review
- FIX: db_manager.py — get_tag_categories() now backfills is_privilege=True on "Privilege" categories saved before the flag existed; fixes disposition selector not appearing in cases created prior to this sprint

### UI Polish (2026-03-18)
- CHANGE: 4_Review.py — expanded document grid from ~10 visible rows to ~25 (height=910px)

### SECURITY: Redaction Data Leak Fix (2026-03-18)
- SECURITY: 5_Production.py — redaction burn save now uses garbage=4, clean=True, deflate=True to irrecoverably remove original unredacted content stream and redaction annotation objects from produced PDFs; previous save without garbage collection left orphaned PDF objects containing the full original text recoverable by forensic tools
- SECURITY: 5_Production.py — explicit post-apply_redactions() cleanup now deletes any remaining /Redact annotation objects from pages before save, preventing privilege basis labels (e.g., "Attorney-Client Privilege") from leaking into produced files
- DOCS: PYMUPDF_PATTERNS.md — added "Post-Redaction Save: Garbage Collection is MANDATORY" section documenting the required save pattern and explaining the forensic recovery risk

### Two-Pass Production Architecture — Sprint 2 (2026-03-18)
- REFACTOR: 5_Production.py — split monolithic production loop into Pass 1 (imaging) and Pass 2 (assembly); Bates numbers now assigned only after all page counts are known, guaranteeing continuous sequences
- NEW: 5_Production.py — imaging checkpoint UI between Pass 1 and Pass 2: summary metrics, failure detail table with retry exclusion checkboxes, Retry/Finalize/Abort buttons
- NEW: 5_Production.py — retry handler re-runs imaging on selected failures without restarting the full production; results update in-place in session state
- NEW: 5_Production.py — abort handler deletes production folder with no DB cleanup needed (no Bates assigned until Finalize)
- NEW: universal_imager.py — image_document_safe() picklable wrapper for two-pass production (future ProcessPoolExecutor support)
- CHANGE: 5_Production.py — CRIT-1 redaction burn failure safety pattern preserved in Pass 2; documents with failed redaction burns are excluded from production load files entirely
- NEW: 5_Production.py — audit events: PRODUCTION_PASS1_COMPLETE, PRODUCTION_RETRY, PRODUCTION_ABORTED

### Deployment Script Fixes (2026-03-18)
- FIX: Deploy-Platform.ps1 — added Branch key to $Config block; new branch checkout step after clone ensures config.py generation and venv setup run against the correct branch
- FIX: Deploy-Platform.ps1 — wkhtmltopdf install now tries multiple winget package IDs (wkhtmltox.wkhtmltox, wkhtmltopdf.wkhtmltopdf) with fallback to manual install instructions and download URL
- FIX: Deploy-Platform.ps1 — pre-flight execution policy detection warns user if Restricted/AllSigned policy may block execution
- FIX: Deploy-Platform.ps1 — updated version strings from 2.6 to 2.7 in header and config template
- FIX: config.example.py — updated version from 2.6.0 to 2.7.0, branch from beta-2.6 to beta-2.7
- DOCS: DEPLOYMENT_GUIDE.md — added Developer Setup (Claude Code) section covering CLAUDE_CODE_GIT_BASH_PATH env var and persistent execution policy for development machines

### Family Peek Navigation + Show Full Family (2026-03-18)
- NEW: 4_Review.py — Peek Navigation: clicking a family link (parent/child) whose target is filtered out of the current search loads it directly in the viewer with a "← Back to queue" button, preserving the reviewer's queue position
- NEW: 4_Review.py — Show Full Family: button in Family panel replaces the grid with all documents sharing the same group_id; "← Back to search results" restores prior search and column filter state
- CHANGE: 4_Review.py — Save & Next exits peek mode and returns to queue position instead of advancing; grid row clicks clear peek state
- FIX: 4_Review.py — family override query now matches parent by control_number in addition to children by group_id (parent's group_id was NULL)
- FIX: 4_Review.py — "← Back to search results" banner moved outside empty-results guard so users are never trapped
- FIX: 4_Review.py — hide_junk, hide_not_responsive, and cascade filters bypassed in family override mode so full family is always shown
- FIX: 2_Processor.py — main UPDATE now writes group_id back to DB for processed documents (was computed in memory but never persisted for parents)
- FIX: db_manager.py — one-time migration fills NULL group_id with control_number for all existing documents
- FIX: 4_Review.py — "← Back to search results" crashed with StreamlitAPIException when writing to widget keys after render; now uses deferred `_pending_search_restore` pattern (same as `_load_saved_query`)
- DOCS: Technical Overview.md, PROJECT_CONTEXT.md, User_Guide.md, Walkthrough.md — added Peek Navigation and Show Full Family documentation

### Documentation Updates (2026-03-18)
- DOCS: Technical Overview.md — updated from Beta 2.5 to Beta 2.7: permission-based RBAC, custom roles, document visibility, libpff fallback, container lifecycle, metadata enrichment columns, cancel buttons, Native Only production, supplemental production, clawback hard block, new analytics tabs (B1/B2/B3/A4), tag cascade, family view, produced PDF download, dependency API references
- DOCS: PROJECT_CONTEXT.md — updated from v2.6 to v2.7: permission-based RBAC with custom roles and document visibility, metadata enrichment columns and native email override, new analytics tabs (B1/B2/B3/A4), cancel buttons, tag cascade, family view, Native Only production, container skip, produced PDF download, synthetic CID, long-path handling
- DOCS: Walkthrough.md — updated from Beta 2.6 to Beta 2.7: permission-based access, Expert role, document visibility, metadata enrichment, communication analytics suite, tag cascade, Native Only production, supplemental production, clawback protection, cancel buttons, inline signature filtering, magic byte detection, full email address resolution; added Phase 4 roadmap section
- DOCS: ROADMAP_TODO.md — added beta-2.7d section (MSG address fix, CID leak fix, message_id key mismatch, documentation updates, manual verification tests); updated module visibility matrix to permission-based; updated deployment script branch reference
- DOCS: DEPLOYMENT_GUIDE.md — bump version header from Beta 2.6 to Beta 2.7
- DOCS: THIRD_PARTY_LICENSES.md — bump version header from Beta 2.6 to Beta 2.7; add libpff-python (pypff) LGPL v3 entry; update LGPL count from 1 to 2

### message_id Key Mismatch Fix (2026-03-18)
- FIX: 2_Processor.py — native email extractors return `message_id` key but override loop looked for `msg_id`, so message_id was never written to DB (0% coverage across all emails)

### MSG Address + CID Inline Fix (2026-03-18)
- FIX: universal_imager.py — MSG imaging and metadata paths now build full "Name <email>" sender from PR_SENDER_NAME + PR_SENDER_EMAIL_ADDRESS instead of using name-only field
- FIX: universal_imager.py — MSG To/CC/BCC now parsed from transport headers (stream 007D) for full SMTP addresses; falls back to display-name-only properties if headers unavailable
- FIX: container_exploder.py — generate synthetic Content-ID for inline-flagged attachments (PR_ATTACH_FLAGS bit 2) that lack PR_ATTACH_CONTENT_ID, preventing CID signature images from leaking through as child documents

### Regression Fixes — beta-2.7c (2026-03-17)
- FIX: universal_imager.py — HTML-escape From/To/Cc/Bcc/Subject fields before inserting into PDF header templates; angle brackets around email addresses (e.g. `<user@example.com>`) were interpreted as HTML tags by the PDF renderer and silently dropped, showing display names only
- FIX: 4_Review.py — orphaned grid indentation: children of hidden container parents (PST/ZIP) no longer display misleading `↳` indent; indentation now requires the immediate parent to be visible in the current grid
- NEW: container_exploder.py — EML attachment filename inference: multi-strategy fallback tries `get_filename()`, then Content-Type `name` param, then MIME-type extension guessing before falling back to `.bin`
- FIX: container_exploder.py — `.bin` extension override: when filename resolves to `.bin` (truthy but unhelpful), Strategy 4a checks Content-Type and 4b inspects payload magic bytes (PDF, JPEG, PNG, DOCX, etc.) to determine the real extension
- FIX: container_exploder.py — `_libpff_msg_to_eml_bytes()` no longer hardcodes `application/octet-stream` for attachments; reads libpff content_type attribute then falls back to `mimetypes.guess_type()` from filename
- FIX: container_exploder.py — `_guess_ext_from_magic()` now detects HTML content (`<html>`, `<!DOCTYPE`); `_explode_eml()` skips HTML body fragments after magic-byte detection, closing the libpff path where `text/html` Content-Type was masked as `application/octet-stream`
- FIX: container_exploder.py — `_libpff_msg_to_eml_bytes()` now resolves real filenames via `long_filename` → `name` → `short_filename` MAPI attribute chain instead of only checking `name`; Content-Type guess now uses resolved filename so `text/html` skip filters fire correctly for HTML signature blocks
- CHANGE: container_exploder.py — `_libpff_msg_to_eml_bytes()` fully rewritten to use MAPI record_set property reads instead of non-existent direct attributes; resolves filenames via PR_ATTACH_LONG_FILENAME (0x3707), MIME types via PR_ATTACH_MIME_TAG (0x370E), CID tags via PR_ATTACH_CONTENT_ID (0x3712); email headers parsed from transport_headers with PR_SENDER_EMAIL_ADDRESS (0x0C1F) fallback; fixes `.bin` filenames, wrong Content-Types, HTML fragment leakage, missing dates/recipients/sender emails, and missing CID tags
- NEW: container_exploder.py — added `_get_record_entry()`, `_get_record_string()`, `_get_record_integer()` MAPI record set helpers for reading pypff property stores
- DOCS: CLAUDE.md — added Dependency API References section with lookup table for `docs/` reference files
- NEW: docs/ — added EMAIL_MIME_REFERENCE.md, OUTLOOK_COM_REFERENCE.md, LIBPFF_API_REFERENCE.md, PYMUPDF_PATTERNS.md, TIKA_METADATA_KEYS.md, OPENSEARCH_PATTERNS.md, LIBPFF_INTROSPECTION_DUMP.md, LIBPFF_RECORD_ENTRIES_DUMP.md
- NEW: introspect_libpff.py, introspect_libpff_records.py — pypff object introspection scripts used to generate API reference docs
- FIX: 4_Review.py — gate STR tab behind has_permission('str_run'); radio option hidden entirely when user lacks permission (item 16)
- FIX: 4_Review.py — STR results now respect doc_visibility mode; produced_only users only see hits for produced documents in both summary counts and hit detail table (item 18)
- FIX: 4_Review.py — PDF ZIP single-select bug: selecting 1 document now correctly scopes export to that document instead of all filtered docs; falls back to currently-viewed document when bulk_selected_cns is empty (item 20)
- FIX: 4_Review.py — tag filter cascade: children of parents hidden by "hide Not Responsive" or "hide Junk Image" are now also hidden from the grid; attachments follow parent disposition (item 22)
- FIX: 4_Review.py — Family View no longer treats PST/ZIP container parents (Container_Scanned) as family relationships; emails extracted from PSTs now form their own email→attachment families instead of all grouping under the PST (item 23)
- FIX: 4_Review.py — ghost-parent groups now render sub-family nesting (email→attachment hierarchy) instead of a flat table (item 24)
- NEW: 4_Review.py — document-level tag cascade: applying, removing, or clearing tags on a parent document now automatically cascades to attachment children; system tags (NearDupe-, Thread-, NIST-, Junk, Inclusive) are preserved on children and not overwritten; redaction marks are unaffected (stored separately). **⚠️ COMPLIANCE REVIEW NEEDED: PM Claude should review this cascade behaviour against eDiscovery protocol standards — specifically whether attachment-level tag independence is required in any jurisdiction or workflow.**
- FIX: 2_Processor.py — queue now shows breakdown of new vs resumed (incomplete prior run) documents; added info banner when resumed docs exist so users understand why hundreds appear in queue (item 25)
- NEW: 2_Processor.py — cancel button for Phase 2 processing; cancels pending futures, drains in-flight workers, logs PROCESSING_CANCELLED audit event; unprocessed docs remain in queue for next run (item 27)
- CHANGE: 4_Review.py — saved search Load button icon changed from ↩ (undo-like) to 📂 (folder-open) for clarity (item 26)
- FIX: pdf_exporter.py — native source export now handles non-PDF files: falls back to processed PDF if available, converts images via PyMuPDF, or includes native with real extension and error note (item 28)
- CHANGE: auth_config.yaml + auth_manager.py — added saved_search_global to reviewer role defaults (item 29)
- DOCS: ROADMAP_TODO.md — added beta-2.7c regression fixes section (items 16-29) from manual acceptance testing
- FIX: ui_utils.py + 2_Processor.py + 5_Production.py — cancel button for overlay: uses streamlit.components.v1.html() to inject a real button into the overlay card via JavaScript (bypasses Streamlit's HTML sanitiser which strips `<button>` and `onclick`); MutationObserver re-injects on overlay updates and auto-cleans up when overlay is removed
- NEW: 5_Production.py — cancel button for production runs; deletes partial volume folder on cancel so no orphaned Bates assignments are written; audit log records PRODUCTION_CANCELLED event
- FIX: 4_Review.py — exclude Container_Scanned documents (PST/ZIP shells) from the review grid; these are not reviewable and were cluttering the document list
- FIX: 2_Processor.py — recover from interrupted previous runs: if a file was moved from Temp_Explode/ to Processed/ but the DB wasn't updated, the worker now checks Processed/ before failing with FileNotFoundError
- FIX: home.py — factory reset now uses SQL DROP TABLE instead of os.remove() to wipe the DB; on Windows, file deletion fails silently when SQLite connections are open (Streamlit holds them during reruns), leaving the DB intact after a "successful" reset
- FIX: 2_Processor.py — Phase 2 no longer processes Container_Scanned documents (PST/ZIP shells); previously they went through text extraction and got promoted to Master status, appearing as reviewable documents in the grid despite having no useful content
- FIX: 2_Processor.py — Phase 1 now promotes MSG/EML containers back to Ready_For_Processing after extraction so Phase 2 picks them up; PST/ZIP promoted to Processed so they exit queue permanently
- FIX: 2_Processor.py — one-time DB migration clears orphaned Container_Scanned PST/ZIP from prior runs and strips `\\?\` long-path prefixes from full_path column
- FIX: 2_Processor.py — `_long_path()` made idempotent (strips existing prefix before re-adding); added `_strip_long_path_prefix()` helper; `temp_path` no longer stores prefixed path at module level so container_exploder receives clean paths for DB storage
- FIX: 2_Processor.py — `add_children_to_db()` strips `\\?\` prefix from child paths before DB insert
- FIX: 2_Processor.py — container count UI now includes `.pst` in detection query
- FIX: container_exploder.py — logger changed from `__name__` to `ProcessorLogger` so container extraction errors appear in processing_log.txt

### MSG Inline Image Filter (2026-03-16)
- FIX: container_exploder.py — process_msg_batch now checks PR_ATTACH_FLAGS (ATT_MHTML_REF bit 4) via Outlook PropertyAccessor and skips CID-referenced inline images; these are HTML-body embeds (signature icons, decorative images) never shown in the email Attachments header, equivalent to the existing EML Content-ID skip

### Threading Family Propagation + Family View Ghost-Parent (2026-03-16)
- FIX: 3_Analytics.py — Thread-Suppressed tag now cascades to attachment children of suppressed emails after the parent bulk-tag step
- FIX: 4_Review.py — Family View now renders a "Attachments of X (parent filtered out)" expander for children whose parent is not visible in the current filter, preventing orphaned attachments from silently falling into Standalone Documents

### Long-Path COM Fix + Silent Error Elimination (2026-03-16)
- FIX: container_exploder.py — _strip_long_path_prefix() helper strips \\\\?\\ prefix before COM calls (OpenSharedItem, AddStore) that reject it; applied to process_msg_batch loop and _explode_pst_com
- FIX: container_exploder.py — explode_container() strips prefix at entry so all downstream functions (zip, eml, pst) receive clean paths
- CHANGE: container_exploder.py — all 14 print() error calls converted to logger.error()/logger.warning(); errors now appear in processing_log.txt instead of being swallowed by Streamlit
- FIX: container_exploder.py — Short-Path Proxy shutil.copy2 now uses \\\\?\\ prefix for source read so files with paths >260 chars can be copied; COM still receives the clean temp path

### Windows Long Path Fix (2026-03-16)
- NEW: 1_Ingestor.py — _long_path() helper prefixes \\\\?\\ on Windows to bypass MAX_PATH; applied to ingest_path and full_path construction; prefix stripped before DB storage
- NEW: 2_Processor.py — _long_path() helper applied to temp_path, target_path, and final_processed_path; db_processed_path used for DB writes to keep stored paths prefix-free

### Analytics Threading Fixes + New Tabs (2026-03-16)
- FIX: 3_Analytics.py — A1: threading query now uses NOT EXISTS subquery to include PST-extracted emails (parent_id = PST control number) while still excluding nested email attachments
- FIX: 3_Analytics.py — A2: added _normalize_msg_id() to strip RFC 2822 angle brackets; graph edges now connect reliably across mixed-format corpora
- CHANGE: 3_Analytics.py — A2: references_list chain added as additional graph edges alongside In-Reply-To
- NEW: 3_Analytics.py — A4: subject-line fallback threading pass for emails not reached by Message-ID graph; groups by normalized subject within 90-day window; opt-out checkbox in UI
- NEW: 3_Analytics.py — B1: Communication Analysis tab — top communicators table, sender×recipient matrix for top 15 addresses, custodian summary; read-only
- NEW: 3_Analytics.py — B2: Timeline tab — email volume bar chart with Day/Week/Month granularity, custodian filter multiselect, automated gap detection with configurable threshold
- NEW: 3_Analytics.py — B3: Domain Analysis tab — domain frequency table with Internal/External classification, top domain-to-domain communication pairs

### Metadata Enrichment Sprint (2026-03-16)
- NEW: db_manager.py — 13 new columns added to documents CREATE TABLE: title, mime_type, creating_application, extraction_method, is_encrypted, word_count, attachment_count, importance, sensitivity, conversation_topic, tika_metadata_json; migrations list completed with all previously-missing entries
- CHANGE: universal_imager.py — extract_msg_text() now returns (text, msg_meta) tuple; adds CC, BCC, date_received, importance, sensitivity, conversation_topic, conversation_index (hex), message_id, in_reply_to, references via new helpers extract_ole_int(), extract_filetime_iso(), scrape_transport_headers_field(), to_iso_date()
- NEW: universal_imager.py — extract_eml_metadata() returns (text, eml_meta) tuple for EML files using Python email module, parallel to MSG path
- CHANGE: universal_imager.py — convert_msg_to_pdf() and convert_eml_to_pdf() now render CC and BCC rows in email PDF header (only when non-empty)
- CHANGE: 2_Processor.py — MSG path unpacks (text, native_email_meta) tuple; EML path calls extract_eml_metadata(); Tika meta dict expanded with references (split from in_reply_to), date_received/modified, title, mime_type, creating_application, is_encrypted, word_count; native_email_meta overrides Tika; extraction_method, tika_metadata_json, attachment_count tracked; UPDATE SQL writes all 13 new columns
- CHANGE: 2_Processor.py — OpenSearch payload enriched with email_from/to/cc/bcc, file_extension, record_type, date_received/modified, file_size_kb, page_count, title, language, importance, has_text
- FIX: 2_Processor.py — In-Reply-To and References are now separate meta keys (were incorrectly conflated)
- NEW: _scratchpad/verify_metadata_enrichment.py — standalone audit tool for per-column NULL coverage, extraction_method distribution, and emails-missing-CC report

### MSG Email Metadata Fix (2026-03-16)
- NEW: universal_imager.py — extract_msg_metadata(): OLE-based structured metadata extraction for MSG files; returns subject, from (Name <email>), to, cc, bcc, msg_id, in_reply_to, sent, created, author, attachment_names
- FIX: 2_Processor.py — MSG files now call extract_msg_metadata() when extract_msg_text() succeeds; meta dict branches on _native_email_meta to use OLE data for MSG and Tika path for all other formats; resolves NULL email_from/to/cc/subject/date_sent for all MSG documents

### Privilege Log PrivilegeBasis Fix (2026-03-16)
- FIX: 5_Production.py — _get_priv_basis() rewritten to collect all matching privilege bases (not first-match); uses priv_members from tag category config instead of hardcoded substrings; normalizes to formal names; returns semicolon-separated multi-basis string; passes priv_members at call site

### Redaction Burn Double-Close Fix (2026-03-16)
- FIX: 5_Production.py — removed explicit redact_doc.close() inside with block; moved os.replace() and audit logging outside the with block; _redact_swap initialized before with block; eliminates "document closed" error that was falsely triggering _burn_failed=True on successful burns

### Production Bug Fixes — Redaction Burn, Container Skip, HTML Imaging (2026-03-16)
- FIX: 5_Production.py — redaction burn now saves to a swap file (.redacted) then atomically replaces the temp PDF; resolves PyMuPDF "save to original must be incremental" error
- FIX: 5_Production.py — _burn_failed initialized to False at top of per-document loop; eliminates stale flag carry-over between documents on the success path
- FIX: 5_Production.py — container files (.pst, .zip, .rar, .7z / processing_status=Container_Scanned) now skipped at the top of the production loop; no "Unsupported File Extension" errors and no Bates number consumption
- NEW: universal_imager.py — convert_html_to_pdf(): wkhtmltopdf primary renderer for .htm/.html with PyMuPDF tag-stripped fallback
- FIX: universal_imager.py — image_document() now routes .htm/.html to convert_html_to_pdf(); resolves "Unsupported File Extension: .htm" error

### Custom Role Sync Fix (2026-03-16)
- FIX: auth_manager.py — save_role_permissions() now syncs custom_roles[role].permissions when role exists in custom_roles, preventing config drift between the two YAML sections
- FIX: auth_config.yaml — corrected role_permissions.expert from [export_pdf, review, str_run] to [download_produced, review, saved_search_personal, str_run] to match custom_roles.expert and EXPERT_REVIEWER_SPEC.md

### Production Canvas Redaction Fix (2026-03-15)
- FIX: 5_Production.py — source resolution now checks Processed/{cn}.pdf before falling back to original; non-PDF natives (email, Word, etc.) now correctly use the imaged PDF which carries canvas redaction annotations
- FIX: 5_Production.py — when source is already the processed PDF, copy it directly instead of re-imaging (which would strip type-12 redaction annotations before burn step)

### Produced PDF Path Resolution Fix (2026-03-15)
- FIX: pdf_exporter.py — _resolve_source_path() "produced" branch now searches Productions/{vol}/IMAGES/ instead of broken Produced/IMAGES/ path; uses production_volume field for direct lookup, falls back to scanning all volume folders for legacy data
- FIX: 5_Production.py — Bates update SQL now writes production_volume alongside begdoc/enddoc so future exports resolve directly without scanning

### STR Hit Document Metadata Expansion (2026-03-15)
- FIX: 4_Review.py — STR SQL query corrected to use real schema columns (record_type not doc_type; no review_status/privilege_status/responsiveness_status — those live in tags)
- CHANGE: 4_Review.py — hit doc row builder adds BegBates, EndBates, DocType (record_type), Date (date_sent|date_created fallback); Tags carries privilege/review decisions
- CHANGE: 4_Review.py — removed non-existent ReviewStatus/Privilege/Responsiveness columns from row builder

### STR Field Name Fix (2026-03-15)
- FIX: 4_Review.py — STR selectbox replaced "extracted_text" (non-existent field) with "content"; added friendly label→field map; fixed _source list to fetch "content" not "extracted_text"

### In-Document Search — Quoted Phrase No-Expansion Fix (2026-03-15)
- FIX: 4_Review.py — _extract_search_terms() now tracks phrase_terms vs bare_terms separately; hyphen expansion only applied to bare (unquoted) tokens; "attorney-client" in quotes returns exact match only

### In-Document Search — Clean Display Value (2026-03-15)
- FIX: 4_Review.py — search box now displays raw module query (e.g. "attorney-client"), not expanded tokens; _doc_search_terms still uses _extract_search_terms() so highlighting remains expanded

### In-Document Search — Hyphen Tokenization Fix (2026-03-15)
- FIX: 4_Review.py — _extract_search_terms() now splits hyphenated tokens into components (mirrors OpenSearch standard analyzer); "attorney-client" expands to ["attorney-client", "attorney", "client"] so documents hit by OpenSearch actually show highlights

### In-Document Search — Shared Input Above Tabs (2026-03-15)
- CHANGE: 4_Review.py — in-document search text_input moved above st.tabs(); shared across all tabs via _doc_search_terms; _ds_badge_container.empty() holds hit count badge
- CHANGE: 4_Review.py — removed duplicate search input from Extracted Text tab; badge now writes to shared _ds_badge_container from both Native (PDF hit count) and Extracted Text tabs

### In-Document Search — PDF Preview & Redaction Canvas (2026-03-15)
- NEW: 4_Review.py — _highlight_pdf_bytes(): PyMuPDF highlight annotations on in-memory PDF copy; returns bytes for base64 iframe display
- NEW: 4_Review.py — _highlight_page_image(): renders single PDF page to PIL Image with cyan highlights baked in; for redaction canvas background
- CHANGE: 4_Review.py — _doc_search_terms pre-computed before tabs from module query; shared across Native, Extracted Text, and Redact tabs
- CHANGE: 4_Review.py — Native/Image tab PDF iframe uses _highlight_pdf_bytes when search terms active; hit count badge shown above iframe
- CHANGE: 4_Review.py — Redaction canvas _r_bg_key now includes terms hash; background generated with _highlight_page_image when terms active

### In-Document Search — Extracted Text Tab (2026-03-15)
- NEW: 4_Review.py — _extract_search_terms(): parses OpenSearch query string into plain terms (strips operators, wildcards, fuzzy markers, handles quoted phrases)
- NEW: 4_Review.py — in-document search input in Extracted Text tab; auto-populates from module search bar; key tied to current_cn for per-doc state
- NEW: 4_Review.py — cyan (#80d4ff) highlight layer applied before STR yellow highlights; hit count badge in adjacent column; no-hits badge when search has no matches

### Saved Search UX — Visual Labels & Share Toggle (2026-03-15)
- CHANGE: 4_Review.py — personal saved searches now display 🔒 icon (was plain bold); shared searches retain 🌐 + owner
- NEW: 4_Review.py — _toggle_global() helper: UPDATE saved_searches SET is_global WHERE id AND username
- NEW: 4_Review.py — share/unshare toggle buttons (🌐/🔒) in saved search list; gated by saved_search_global permission; logs SEARCH_SHARED / SEARCH_UNSHARED audit events

### Saved Search Load — StreamlitAPIException Fix (2026-03-15)
- FIX: 4_Review.py — moved _load_saved_query session-state bridge to before text_input widget render; eliminates StreamlitAPIException when loading a saved search

### sqlite3.Row .get() Fix (2026-03-15)
- FIX: 4_Review.py — replaced row.get('is_global') / row.get('username') with safe key-in-keys access; sqlite3.Row has no .get() method

### OpenSearch Highlight Limit Fix (2026-03-15)
- FIX: 4_Review.py — es.search() wrapped in try/except; retries without highlight block on max_analyzed_offset error; st.toast() warns user when fallback triggers
- NEW: os_manager.py — ensure_highlight_limit(): idempotent PUT settings call raising index highlight limit to 10M chars; called at search time in 4_Review.py

### Production — Imaging Summary Table (2026-03-15)
- NEW: 5_Production.py — imaging_failures[] accumulator collects non-imaged docs during production loop; classifies each as 'Expected Native' (xlsx/csv) or 'Imaging Failure'
- CHANGE: 5_Production.py — replaced per-document st.warning() toast on failure with imaging_failures.append(); error_count and IMAGING_ERRORS.csv logic untouched
- NEW: 5_Production.py — 📋 Imaging Summary section rendered after QC table: 3-column metrics (total/expected/actual), warning if actual failures > 0, scrollable dataframe with Bates+reason columns
- CHANGE: 5_Production.py — error_count warning now references the Imaging Summary table instead of the CSV file directly
- CHANGE: 5_Production.py — DEFAULT_NATIVE_EXTENSIONS hoisted to pre-loop scope (was defined only inside imaged path branch)

### Document Visibility System (2026-03-15)
- NEW: auth_manager.py — get_doc_visibility(): returns per-user visibility config (full | produced_only | hidden_tags); admin always returns full
- NEW: auth_manager.py — update_doc_visibility(): set visibility mode and hidden tags for a user; persisted to auth_config.yaml
- NEW: 4_Review.py — per-user visibility filter injected into Review SQL query (produced_only = begdoc filter; hidden_tags = NOT LIKE clauses)
- NEW: 4_Review.py — visibility restriction banner shown when user has non-default mode (does not reveal hidden tag names)
- CHANGE: 4_Review.py — Export PDF popover (download_produced path): pre-filters to produced docs with count feedback; disabled Generate ZIP when 0 produced docs selected
- NEW: home.py — 🔒 Document Visibility expander in User Management (admin UI for mode + hidden tags per user)
- CHANGE: db_manager.py — add USER_VISIBILITY_CHANGED to log_audit action vocabulary

### Phase 14 — Expert Role permissions (2026-03-14)
- CHANGE: auth_manager.py — added saved_search_personal + download_produced to ALL_PERMISSIONS registry
- CHANGE: auth_manager.py — _DEFAULT_PERMISSIONS: manager gains saved_search_personal + download_produced; reviewer gains saved_search_personal
- CHANGE: auth_config.yaml — role_permissions: manager gains download_produced + saved_search_personal; reviewer gains saved_search_personal
- CHANGE: 4_Review.py — entire saved search UI (📌 Saved Searches, 🕐 Recent, 💾 Save form, session state load bridge) gated behind saved_search_personal permission
- CHANGE: 4_Review.py — _log_recent() call at search execution gated behind saved_search_personal so recent history isn't written for users without the permission
- NEW: 4_Review.py — _offer_produced_download(): download button for Bates-stamped produced PDF in Production (Bates) tab, gated behind download_produced permission; logs PRODUCED_DOWNLOAD audit event on click
- CHANGE: auth_manager.py — reviewer gains download_produced (reviewing attorneys need produced PDFs for deposition prep)
- CHANGE: auth_config.yaml — reviewer role_permissions gains download_produced
- CHANGE: db_manager.py — add PRODUCED_DOWNLOAD to log_audit action vocabulary
- CHANGE: auth_manager.py — add 🔬 Expert badge to show_user_info() role_labels; unknown custom roles fall back to 🏷️ {Role}
- DOCS: DEPLOYMENT_GUIDE.md — add Tailscale remote access section (server setup, client setup, node sharing, firewall rules, security notes)
- NEW: auth_manager.py — show_user_info() renders permission-filtered page_link nav; inaccessible pages are hidden rather than blocked with an error
- CHANGE: ui_utils.py — inject CSS to hide Streamlit's auto-generated sidebar nav (replaced by filtered nav)
- CHANGE: 4_Review.py — 🗂️ Configure Columns expander hidden entirely for users without column_picker (was shown with a blocked message inside)
- CHANGE: 4_Review.py — Export PDFs popover now visible to download_produced users; source restricted to Produced (Bates-stamped) only; export_pdf users retain full source selection
- FIX: 4_Review.py — Export PDFs popover count now always matches Bulk Action bar; deferred rendering via pdf_col.empty() placeholder ensures popover reads bulk_selected_cns after the dataframe event handler updates it, eliminating the N-1 render-order lag
- FIX: 4_Review.py — bulk tag form (Apply Tag / Clear All Tags / tag selectbox) now gated behind tag permission; Cancel and Bates Extract remain visible to all users in bulk mode

### Review — Redaction reason persistence + tag sync (2026-03-14)
- FIX: 4_Review.py — _mark_reasons_ always re-read from DB on canvas init; removed `if not in SS` guard so stale session state can never shadow saved marks
- FIX: 4_Review.py — reason_sel/reason_custom widget keys now include _r_del_counter so they reset (re-init from DB) after every Save Marks or Delete Box action
- FIX: 4_Review.py — Save Marks bumps _r_del_counter_key and clears tags_{cat}_{cn}/tags_orphan_{cn} cache so Tags panel immediately reflects privilege tags written by _r_sync_tags()
- NEW: 4_Review.py — "🔒 Set via redaction marks" caption shown below privilege category multiselect when any selected tag was auto-applied by the redaction engine

### Review — Delete Selected Box in Redaction Panel (2026-03-14)
- NEW: 4_Review.py — "🗑️ Delete Selected Box" button in redact control panel (Select mode only); shows Box # number_input; in Draw mode shows "Switch to Select mode to delete a box." caption
- NEW: 4_Review.py — delete action removes object from live canvas objects, pops corresponding reason from _mark_reasons session state, clears stale per-box reason_sel/reason_custom keys, stores override drawing in session state for next render, bumps deletion counter to force canvas key change
- NEW: 4_Review.py — _r_del_counter_key tracks per-page deletion count; appended to canvas key so streamlit-drawable-canvas fully re-mounts after each delete
- NEW: 4_Review.py — _r_override_key stores the post-delete initial_drawing; consumed (popped) on next render before canvas mounts

### Processor — Processing Log Viewer (2026-03-14)
- NEW: 2_Processor.py — _render_log_viewer(log_dir): collapsible expander showing processing_log.txt + rotated backups (.1–.5); file selector, level filter (Errors Only / Warnings & Errors / All), substring search, newest-first display capped at 500 lines with count, download button
- NEW: 2_Processor.py — _read_log_lines(file_path, mtime): @st.cache_data(ttl=30) log reader; cache keyed on mtime so it refreshes on write
- NEW: 2_Processor.py — _discover_log_files(log_dir): scans Audit/ for log files, returns sorted list with friendly labels, size, and last-modified

### Review — Dynamic PDF Export Naming + begdoc_range + meta: fields (2026-03-13)
- NEW: 4_Review.py — _get_pdf_naming_options(case_folder): builds naming dropdown dynamically (curated fields → PRAGMA columns → meta:<KEY> from dynamic_metadata); @st.cache_data(ttl=60)
- NEW: 4_Review.py — begdoc_range option produces "{begdoc} - {enddoc}" filename; meta: prefix pulls from dynamic_metadata JSON
- CHANGE: 4_Review.py — naming selectbox dynamic with format_func; static list removed
- NEW: pdf_exporter.py — _build_zip_filename handles begdoc_range and meta:<KEY> naming fields; fallback to control_number on missing value or parse error

### Review — PDF Export Scope Selector (2026-03-13)
- FIX: 4_Review.py — Export PDFs popover now respects checkbox selections; when 2+ rows are checked, offers "Export selected (N)" / "Export all filtered (N)" radio defaulting to selected; audit log records scope

### Per-User Case Restrictions (2026-03-13)
- NEW: auth_manager.py — get_allowed_cases(username) returns None (unrestricted) or list of allowed paths
- NEW: auth_manager.py — update_allowed_cases(username, paths) sets or clears case restriction in auth_config.yaml
- CHANGE: auth_manager.py — check_login() enforces case restriction on every page load (stale case cleared silently); login restore also validates last_case against allowed list
- CHANGE: home.py — discover_cases filtered by allowed_cases for non-admin users; unfiltered list kept as _all_discovered_cases for admin UI
- CHANGE: home.py — on_dropdown_change/on_custom_change block selection of restricted cases; custom-path expander shows "You don't have access to this case." warning
- NEW: home.py — "Allowed Cases" multiselect in Add New User form (leave empty = unrestricted)
- NEW: home.py — "📂 Edit Case Restrictions" expander in User Management: per-user multiselect + custom path input; audits USER_CASE_RESTRICTIONS_CHANGED

### Phase 13 (2.7a) — Permission-Based Access Control ✅ 2026-03-13
- NEW: auth_manager.py — has_permission(), require_permission(), _get_role_permissions() with hardcoded defaults fallback; custom role resolution with inherits/permissions patterns
- NEW: auth_manager.py — ALL_PERMISSIONS list and admin-UI helpers: list_roles(), get_role_permissions_for_ui(), save_role_permissions(), create_custom_role(), delete_custom_role()
- CHANGE: auth_manager.py — show_user_info() generic 🏷️ badge for custom roles; list_users() sort key extended for custom roles
- CHANGE: auth_config.yaml — added role_permissions section (admin/manager/reviewer defaults) and empty custom_roles block
- CHANGE: 1_Ingestor.py — require_role('manager') → require_permission('ingest')
- CHANGE: 2_Processor.py — require_role('manager') → require_permission('process')
- CHANGE: 3_Analytics.py — require_role('manager') → require_permission('analytics')
- CHANGE: 4_Review.py — require_role('reviewer') → require_permission('review'); is_manager() gates migrated to has_permission('str_export'), has_permission('column_picker'), has_permission('case_settings')
- CHANGE: 5_Production.py — require_role('manager') → require_permission('production')
- CHANGE: 6_Sync.py — require_role('manager') → require_permission('sync')
- CHANGE: home.py — all role helpers migrated to has_permission(); role dropdowns include custom roles; Role Permission Editor UI added (tab: edit permissions + tab: custom role create/delete); audits ROLE_PERMISSIONS_CHANGED, ROLE_CREATED, ROLE_DELETED
- REMOVE: auth_manager.py — is_admin(), is_manager(), is_reviewer(), require_role() removed

### QoL — Persist Last Case Per User (2026-03-13)
- NEW: auth_manager.py — save_user_pref(username, key, value) writes per-user prefs to auth_config.yaml
- CHANGE: auth_manager.py — check_login() restores last_case into session state on login if path still exists on disk
- CHANGE: home.py — on_dropdown_change() and on_custom_change() call save_user_pref('last_case') when a case is selected
- CHANGE: home.py — no-case-selected view replaced with card grid (3-up): case name, status badge, doc count, processed count, Open button
- CHANGE: home.py — sidebar reordered: Case Selection → user badge/logout → dependency status at bottom
- FIX: home.py — dropdown now syncs dyn_case_select key when last_case is restored on login (was stuck on "Select a Case")
- CHANGE: home.py — removed redundant "System Ready" module list when case is loaded (dashboard replaces it)
- FIX: config.py — CASES_ROOT updated to correct local path (was C:\eDiscovery\Cases)
- NEW: home.py — secondary case discovery: when CASES_ROOT yields nothing but an active case path is known, scans its parent dir and rebuilds dropdown
- NEW: home.py — sidebar self-diagnosis tip when active case lives outside CASES_ROOT, suggesting the correct config.py fix
- FIX: 4_Review.py — redact zoom slider now works: bg cache key and canvas key both include zoom level, forcing re-render on change; stale zoom entries evicted to prevent memory bloat
- CHANGE: ui_utils.py — inject_custom_css() now includes browser zoom-out override (min-width: 0 on block-container and sidebar)
- FIX: 4_Review.py — Phase 13 regression: added missing sub-feature permission gates: redact tab hidden (tab not rendered) without redact permission; tag/coding panel hidden without tag; CSV exports hidden without export_csv; PDF exports hidden without export_pdf; saved search global checkbox hidden without saved_search_global

### Phase 14 (2.7b) — Expert Reviewer Role & Remote Access
*(pending — requires Phase 13 complete)*

---

## [beta-2.6] — Complete

### 2026-03-13 — Immediate Fixes Sprint (beta-2.6 close)
- FIX: db_manager.py — restored \b word boundaries in fuzzy_match_privilege_reason() (corrupt \x08 bytes); removed earlier duplicate get_case_status()/set_case_status() definitions; project_ver bumped to 2.6.0
- FIX: 5_Production.py — Native Only text extraction now falls back to OpenSearch then PyMuPDF when SQLite extracted_text is empty; project_ver bumped to 2.6.0
- FIX: requirements.txt — added openpyxl==3.1.5 (bcrypt already present)
- CHANGE: ROADMAP_TODO.md — Phase 9 marked complete; Task 5 checked off
- CHANGE: .claude/skills/version-tracking/SKILL.md — updated last_modified format to YYYY-MM-DD HH:MM

### 2026-03-12 — Fresh-machine deployment test fixes (drop-in files)
- FIX: Deploy-Platform.ps1 — rebuilt as pure ASCII; added --source winget to all installs; added Python version ceiling (3.14+ blocked); added LibreOffice optional install; fixed Windows Store python stub detection
- FIX: DEPLOYMENT_GUIDE.md — updated for Python 3.11 requirement, LibreOffice, wkhtmltopdf manual install note
- NEW: THIRD_PARTY_LICENSES.md — complete dependency license inventory covering system tools, Python packages, and transitive dependencies

### 2026-03-12 20:30 — Fresh-machine deployment fixes
- FIX: requirements.txt — complete rewrite with pinned versions from production venv; added missing bcrypt and requests dependencies; libpff-python now uncommented
- FIX: config.example.py — added `__version__` and `__branch__` fields to match production config.py
- FIX: home.py — Audit Log Viewer now shows st.warning() with remediation instructions on pre-migration databases missing the username column
- FIX: db_manager.py — migration to add username column to audit_log already present in get_connection() (verified; no change required)
- NEW: Deploy-Platform.ps1 — automated bootstrap script for fresh Windows machine deployment
- NEW: DEPLOYMENT_GUIDE.md — deployment documentation covering automated, manual, and offline installation

### 2026-03-12 19:56 — Audit Log Viewer: username column migration + graceful degradation
- FIX: db_manager.py — get_connection() now runs audit_log column migrations (username, control_number, module, old_value, new_value) on every DB open so pre-migration databases are upgraded automatically
- FIX: home.py — Audit Log Viewer username/module filter queries wrapped in try/except sqlite3.OperationalError; viewer degrades gracefully (empty filter lists) if columns not yet present

### 2026-03-12 — Automated Test Suite (beta-2.6 Item 1)
- NEW: tests/conftest.py — shared fixtures: case_folder, seeded_case, auth_config_file, sample_zip, sample_eml
- NEW: tests/test_db.py — 19 tests: schema creation, migrations, audit log (never-raise contract), case status, clawback workflow, last Bates persistence
- NEW: tests/test_auth.py — 20 tests: bcrypt hash/verify, SHA-256 legacy migration, role hierarchy, user CRUD (create/update/delete)
- NEW: tests/test_bates.py — 13 tests: Bates string formatting, continuity, overflow, supplemental-production round-trip
- NEW: tests/test_containers.py — 17 tests: ZIP extraction, EML extraction (with/without attachments), get_file_type
- NEW: tests/fixtures/sample.eml — minimal valid multipart EML with one attachment
- CHANGE: requirements.txt — pytest added as dev dependency
- FIX: requirements.txt — added missing bcrypt dependency (required by auth_manager.py)
- Result: 69/69 PASSED in 4.85s

### 2026-03-12 — PST via libpff (beta-2.6 Item 4)
- NEW: container_exploder.py — explode_pst_libpff() pure-Python PST extraction via pypff; _walk_pst_folder_libpff() recursive walker; _libpff_message_to_eml() MIME builder
- CHANGE: container_exploder.py — explode_pst() refactored to dispatch: tries COM first, falls back to libpff; raises RuntimeError if both unavailable
- CHANGE: container_exploder.py — win32com/pythoncom imports guarded with try/except (_WIN32COM_AVAILABLE flag)
- FIX: 2_Processor.py — .pst added to other_container_docs routing (was silently falling into standard_docs, never exploded)
- CHANGE: requirements.txt — libpff-python added as commented optional dependency

### 2026-03-12 — Supplemental Production (Item 3)
- NEW: db_manager.py — get_last_bates_info() and save_last_bates_info() helpers (case_settings key: last_bates_info)
- NEW: 5_Production.py — "Continue from Last Production" toggle in Configure Production; auto-populates prefix and start_num from previous run's ending Bates number
- CHANGE: 5_Production.py — save_last_bates_info() called on every successful production run

### 2026-03-12 — Clawback / Inadvertent Disclosure Workflow (Item 2)
- NEW: db_manager.py — clawback_status and clawback_date columns in documents schema + migrations
- NEW: db_manager.py — mark_clawback() helper; get_clawback_summary() for Analytics
- CHANGE: db_manager.py — add CLAWBACK_MARKED to log_audit vocabulary docstring
- NEW: 4_Review.py — Clawback panel in sidebar (Manager+); form for demand date, notes, status; routes through _safe_write
- NEW: 5_Production.py — "Exclude Clawback-Demanded" filter checkbox (default on); hard-blocks demanded docs from productions
- NEW: 3_Analytics.py — Clawback summary section in Dedup Report tab; metric cards + detail table

### 2026-03-12 — Review Sprint HIGH-Tier Remediation
- FIX: home.py — add PASSWORD_RESET audit log call after update_password() (HIGH-2)
- FIX: home.py — add USER_DELETED audit log call after delete_user() (HIGH-1)
- FIX: 6_Sync.py — add BYOS_PUSH audit log call after push commit (HIGH-3)
- FIX: 6_Sync.py — add BYOS_PULL audit log call after pull commit (HIGH-3)
- FIX: 6_Sync.py — sanitize Filevine auth exception message; remove raw exception from st.error() (HIGH-5)
- FIX: auth_manager.py — wrap _save_config() file write in try/except OSError; re-raise as RuntimeError (HIGH-6)
- FIX: universal_imager.py — replace hardcoded LIBREOFFICE_PATH with getattr(config, ...) pattern (HIGH-8)
- CHANGE: config.example.py — add LIBREOFFICE_PATH to Third-Party Tool Paths section (HIGH-8)
- CHANGE: db_manager.py — add USER_DELETED, PASSWORD_RESET, BYOS_PUSH, BYOS_PULL to log_audit vocabulary docstring (LOW-4)

### 2026-03-12 — Review Sprint 3A Fix + RBAC Adjustment
- FIX: 3_Analytics.py — guard "EXECUTE: Auto-Tag Near Dupes" button with _case_closed check (3A-01)
- CHANGE: 4_Review.py — RBAC adjusted: CSV export, PDF export, Redact tab opened to Reviewer; STR Excel export remains Manager+

### 2026-03-11 — Case Lifecycle Status Implementation
- FEAT: db_manager.py — add get_case_status() and set_case_status() (reads/writes 'case_status' in case_settings)
- FEAT: home.py — add sidebar case lifecycle badge + Manager+ status selector + CASE_SETTING_CHANGED audit logging
- FEAT: 1_Ingestor.py — add Closed case guard (st.stop() on closed matters)
- FEAT: 2_Processor.py — add Closed case guard (st.stop() on closed matters)
- FEAT: 5_Production.py — add Closed case guard (st.stop() on closed matters)
- FEAT: 6_Sync.py — add Closed case guard (st.stop() on closed matters)
- FEAT: 3_Analytics.py — add _case_closed flag; guard threading + near-dupe write buttons; read-only tabs remain accessible
- FEAT: 4_Review.py — add _case_closed flag; guard tag save, bulk actions, redact buttons, saved search save; grid/viewer/search remain accessible
- FIX: ROADMAP_TODO.md — mark items 2 (Case Lifecycle) and 6 (Phase 9 External Annotation) as [DONE]
- DOCS: CLAUDE.md — add Critical Rules section (never remove functionality in batch operations)

### 2026-03-11 — Holistic Review Sprint
- SETUP: Version tracking infrastructure added (CLAUDE.md, .claude/skills/version-tracking/SKILL.md, CHANGELOG.md)
- SETUP: __version__ = "2.5.0" and __branch__ = "beta-2.6" added to config.py
- REVIEW: Full codebase audit initiated (Pass 1 complete, Pass 2 complete) — 8 dead imports removed across 7 files

---

## [v2.5] — Prior

(Historical changes predating the changelog system)
