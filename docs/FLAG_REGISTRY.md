# Flag Registry — Respondeo eDiscovery Platform

<!-- Last audited: 2026-06-10 (beta-2.17 C-d — Flag #32 registered + closed (BYOS pull/push write-lock collision, per-iteration commit); Flag #31 registered Active/Deferred (custodian-rename stale hold_documents.file_path, fix scheduled at C-c); both discovered in the C1 design pass. Prior: 2026-06-01 beta-2.16 C10 — Flag #22 closed; Flag #5 Pattern A deferred to 2.17; Flag #30 S-1c note; cross-ref backfilled C4–C9) -->

**Purpose.** Durable single-source-of-truth registry for all numbered flags/issues/hypotheses tracked across sprints. Replaces ad-hoc tracking in session memory (PM-side) and commit audit docs (CLI-side). Numbering is monotonic and never reused.

**Maintenance.** This file is CLI-maintained (mirrors the `DEPENDENCY_MAP.md` convention — CLI updates on every sprint that touches a flag's state). Per the PM Claude write boundaries in `docs/roles/pm_claude.md`, PM does not write to this file directly; when PM discovers a new flag during planning, PM documents it in the preflight or auto-memory and CLI adds the row to this registry in the commit that registers the flag. This preserves the "registry mutations happen at commit time" invariant. See `CLAUDE.md` §Standing Orders for adjacent authoritative rules.

**Numbering conventions.**
- Flag numbers increment monotonically. Once assigned, a number is never reused.
- When a flag is resolved, move its row from the Active table to the Dormant/Closed table with the closing commit hash noted.
- When a flag's severity changes or a characterization reframes it, update the "Last updated" field and add a short status-change note in the Notes column.
- Active flags that are explicitly deferred (Flag #5 → beta-2.12) stay in the Active table with `Deferred` in the State column.

**Numbering authority established:** this registry, as of beta-2.11 Commit 6a, is the authoritative source for flag numbers. Prior to this commit, #1–#21 were tracked informally in PM-side session memory and CLI-side audit docs; this registry reconciles them into a single list. Future flags (#22+) are assigned here first, then cross-referenced from audit docs as needed.

---

## Known drift reconciled

Prior to this registry, a numbering inconsistency existed between PM's running memory and CLI's sprint reporting:

- PM-side session memory referenced flags #1–#13 loosely by name.
- CLI-side beta-2.11 audit docs registered #16 (Commit 2), #17 (Commit 3), #18 (Commit 3), #19 (Commit 5), #20 (Commit 5b), #21 (PM QA-technique placeholder for "defensibility-PDF moment").
- No canonical list existed for #14 or #15 until this commit.
- #14 was unassigned; retroactively assigned here to the M-4 SQL migration completion record for numbering continuity.
- #15 is this commit (the retrospective itself).

After this commit, the registry below is the single source. Future sprint-retrospective flags pick up at #22.

---

## Active flags

| # | Title | State | First registered | Last updated | Sprint origin | Related commits / docs |
|---|---|---|---|---|---|---|
| 1 | Zombie `in_progress` production_runs rows from crashed Pass 1 runs (admin-console surface) | Deferred | 2026-04-17 | 2026-04-17 | beta-2.10 retrospective | `~/.claude/.../project_beta210_sprint.md` |
| 2 | Silent Pass 1 seed failure — make loud-fail | Deferred | 2026-04-17 | 2026-04-17 | beta-2.10 retrospective | Same |
| 3 | `auth_manager.require_permission()` migration — actual function migration still pending | Deferred | 2026-04-17 | 2026-04-17 | beta-2.10 retrospective | Same |
| 4 | Inbound document privilege-tagging UX polish — dedicated inbound-review mode | Deferred | 2026-04-17 | 2026-04-17 | beta-2.10 retrospective | Same |
| 5 | Page-held connection + nested db_manager call pattern — 61 sites, 9 latent-risky, log_audit silent-drop surface | Characterized / Deferred to 2.17 | 2026-04-17 | 2026-06-01 | beta-2.10 retro; characterized in 2.11 | commit audit. **Pattern A (3 long-span orchestration sites) deferred to a dedicated beta-2.17 DB-hygiene sprint** — resolve the Approach 1 (narrow `conn=None` threading) vs Approach 3 (page-scoped connection refactor) fork in a design pass first (see beta-2.16 retrospective P2.2 + P2.5). |
| 6 | Stale `privilege_status` on inbound rows rendering in grid — UX polish sweep | Deferred | 2026-04-17 | 2026-04-17 | beta-2.10 retrospective | `~/.claude/.../project_beta210_sprint.md` |
| 9 | PST/ZIP containers stored with NULL `control_number` — schema/design question about `record_type='container'` marker | Architectural; deferred | 2026-04-17 | 2026-04-17 | beta-2.10 retro; root cause confirmed in 2.11 Commit 5b | `docs/archive/audits/beta-2.11/commit_5b_*.md`; §3.B Pattern 13 in `docs/archive/audits/beta-2.11/commit_6a_*.md` |
| 10 | `production_selection` session-state ghost-bug — defensibility implication, Run vs Confirm flow UX | Deferred | 2026-04-17 | 2026-04-17 | beta-2.10 retrospective | Same |
| 15 | Instruction-corpus retrospective inventory (THIS) | In Progress (6a landed; 6b pending) | 2026-04-17 | 2026-04-17 | beta-2.11 | commit audit (this commit) |
| 18 | `db_manager` API lacks `conn=None` parameter convention — 0 of 163 public functions accept an explicit conn | Deferred to 2.12 DB-hygiene | 2026-04-17 | 2026-04-17 | beta-2.11 Commit 3 | commit audit §2.3 |
| 19 | Downstream consumers of `document_productions` apply no inbound filter — 10 reader sites | Dormant (after 5b source-side fix + cleanup migration) | 2026-04-17 | 2026-04-17 | beta-2.11 Commit 5 | commit audit §14; `docs/archive/audits/beta-2.11/commit_5b_*.md` |
| 21 | QA technique: validate beta builds by running end-to-end + inspecting outputs ("defensibility-PDF moment") | Pending PM context | 2026-04-17 | 2026-04-17 | beta-2.11 planning | PM to supply context for 6b |
| 25 | `pages/4_Review.py` STR view branch (L335-628) references `_vis_mode` at L438/L450 before module-level assignment at L1459 — undefined-name when STR view is active | Active / Deferred | 2026-05-07 | 2026-05-07 | beta-2.15 Commit 3 mid-execution finding | commit audit (post-execution finding); pre-existing since beta-2.7c; surfaced when CLI was extending L438/L450 with `_session_produced_only_ux` and discovered both names were undefined at that scope; Path 3 disposition rolled back the planned 4-site SQL extension to 2 sites (L2496 main grid + L3012 export/helper) and registered the latent bug for dedicated fix |
| 26 | Archive-container coverage beyond .pst/.zip — `ARCHIVE_EXTS = frozenset({'.pst', '.zip'})` does not include `.rar`, `.7z`, `.tar`, `.gz`, `.mbox`. If any of these are ever added to `container_exploder.explode_container`, the new family-model rule will treat them as email-propagating (since they wouldn't match `ARCHIVE_EXTS`), reintroducing the mega-family bug for that type. | Active / Deferred | 2026-05-15 | 2026-05-15 | beta-2.15 Commit 4 (out-of-roadmap insert) | commit audit §6.5; defer until first reported case or until `container_exploder` gains support for additional archive types; fix pattern when needed: extend `ARCHIVE_EXTS` in `processing_engine.py` in the same commit that adds the new container handler |
| 27 | EML inline-classification coverage gap — `.msg` path. Commit 5 fixed the .eml path via the shared `is_part_inline_image()` predicate. The `.msg` path (Outlook COM via `container_exploder._parse_msg_attachments`) uses MAPI properties (`PR_ATTACH_FLAGS`, `PR_ATTACHMENT_HIDDEN`) rather than Content-ID, so it does NOT share the over-skip defect today. If `.msg` extraction is ever rewritten to flow through Python's `email` module (e.g., to retire the win32com dependency), the shared predicate must apply there too — otherwise the libpff-style over-skip can reappear in the new path. | Active / Deferred | 2026-05-18 | 2026-05-18 | beta-2.15 Commit 5 (out-of-roadmap insert) | commit audit §6.2 + §6.8b "Known Coverage Gap"; defer until `.msg` path rewrite is contemplated; fix pattern when needed: have `_parse_msg_attachments` consume the same `is_part_inline_image` predicate (or its MAPI-equivalent) so the rule lives in one place |
| 30 | `pages/3_Analytics.py:run_near_dupe()` clustering loop uses single-query-per-doc with no transitive closure — for a chain A~B~C where A↔C estimates below threshold, produces overlapping clusters [A,B] + [B,C] rather than one [A,B,C] | Active / Deferred | 2026-05-24 | 2026-06-01 | beta-2.16 S-1a v4 delta-check | commit audit (CLI bonus discovery during fixture pre-measurement) — pre-existing behavior, NOT an S-1a regression; not triggered by the narrow-preamble S-1a test fixtures; fix would require a connected-components / union-find grouping pass over the LSH candidate graph. **Empirically material (beta-2.16 C8a):** documents in more than one cluster were observed on the Test(small) set, and the overlap exposed a dual-selection family-integrity leak in the C8a Execute payload (since fixed by unifying principal selection in `_build_cluster_payload`). **Overlap-coherence deferred to C8b cluster-review design** (the maintainer's Option A — fail-open keeps it safe: family members are `family_preserved` in every cluster, suppressible members un-suppress back to review); full transitive-merge (union-find) still deferred. **S-1c (C9):** the defensibility report §4.2 reports overlap honestly (document-level summary reconciliation + per-cluster table with a multi-cluster footnote) but does NOT merge clusters; union-find merge remains the deferred beta-2.17 carryover (retrospective P2.5). |
| 31 | Custodian **rename** never remaps `hold_documents.file_path` — `rename_custodian` updates `custodian_name` but not `file_path`; the page renames the custodian folder and orphans every absolute path stored at insert time. Hold-doc panel shows "Missing"; downloads break. | Active / Deferred | 2026-06-10 | 2026-06-10 | beta-2.17 design pass (R-4) | Discovery record `docs/specs/flag5_pattern_a_design_pass.md` (landed C1); registered at C-d alongside #32 to keep visible numbering monotonic under the C-d-first landing order. **Fix scheduled at C-c** — `rename_custodian` + `merge_custodians` remap `file_path` inside the atomic db_manager transaction. |

---

## Dormant / Closed flags

| # | Title | State | Closed at | Sprint origin | Resolution reference |
|---|---|---|---|---|---|
| 32 | BYOS pull/push write-lock collision — `pull_conn` holds an uncommitted write transaction across the pull loop (single commit after the loop); from the 2nd annotated PDF onward the nested `_ae_conn`/`save_redaction_marks` writers in `_annot_extract_to_marks` block ~60s on the held lock, then `OperationalError` aborts the batch, leaking the lock and losing all `byos_pulled_at` state while files sit already-copied in `Reviewed/`. The push loop holds the lock across the whole copy loop (cross-session contention). | CLOSED (fixed) | beta-2.17 C-d (`pending`) | beta-2.17 design pass (R-5) | Per-iteration commit in both BYOS loops (`pages/6_Sync.py` pull loop + push loop). commit audit (v2) + `_check_v1`/`_check_v2`; AST structural pin `tests/test_byos_commit_discipline.py`; discovery record `flag5_pattern_a_design_pass.md` @ C1. Registered + closed in one commit (precedent: #23, #24). |
| 22 | Near-dupe analytics clusters template-similar-but-content-distinct documents under NearDupe-Suppressed (false-positive on invoice-style templates) | CLOSED (fixed) | beta-2.16 Commit 6 (2026-05-24) | beta-2.13 near-dupe design review follow-up | commit audit (+ `_check_v1..v5`). Closed via the S-1a NearDupe k-gram shingling fix (`pages/3_Analytics.py` MinHash signature now uses sliding-window k=5 shingles preserving phrase structure, replacing word-level k=1 that conflated template-similar/content-distinct docs). Sensitivity-tuning spec scope shipped; spec archived to `docs/archive/specs/neardupe_false_positive_sensitivity.md` at this sprint-close. The adjacent cluster-review/reporting work (S-1b/S-1c) built atop the fix but is not the spec's scope. |
| 7 | Pre-existing dead `import sqlite3` in `pages/5_Production.py:12` | CLOSED (fixed) | beta-2.11 Commit 1 (2026-04-17) | beta-2.10 retrospective | commit audit |
| 8 | Duplicate `def get_root(cn):` at `pages/5_Production.py:394` and `:2630` — rename or comment-disambiguate | CLOSED (consolidated to `_walk_family_root`) | beta-2.11 Commit 2 (2026-04-17) | beta-2.10 retrospective | commit audit. Flag premise ("silently shadowed") proved factually wrong; actual fix was lift-to-module-level helper. |
| 11 | `pages/4_Review.py:442` potential silent data loss on `.set_index().to_dict('index')` | CLOSED (fixed) | beta-2.11 Commit 4b (2026-04-17) | beta-2.10 retrospective | `docs/archive/audits/beta-2.11/commit_4_*.md` + `docs/archive/audits/beta-2.11/commit_4b_*.md`. Flag premise ("silent loss") proved factually wrong; actual behavior was `ValueError` hard-crash. Fixed via `dropna` + `drop_duplicates` pre-filter. |
| 12 | `db_manager.py:731` `document_productions` backfill LEFT JOIN may pair inbound docs with inbound `production_runs` | CLOSED (fixed) | beta-2.11 Commit 5b (2026-04-17) | beta-2.10 retrospective | `docs/archive/audits/beta-2.11/commit_5_*.md` + `docs/archive/audits/beta-2.11/commit_5b_*.md`. Fix: source-party filter on backfill WHERE + guarded cleanup migration. |
| 13 | `production_runs` rows with None Bates range + `document_count=0` render as `None — None` / `0 docs` in history displays — aborted-run UX hygiene | CLOSED (fixed) | beta-2.14 Commit 10 (2026-04-30) | beta-2.10 retrospective | commit audit (v3) — asymmetric fix: home.py grid gets render hygiene + Status column; defensibility_report.py section 6.2 filters aborted rows out (court-facing PDF stays clean per the maintainer's Stage 1 decision); pages/5_Production.py banner gets defensive `(value or '—')` substitution. `TestAbortedRunRenderContract` (3 tests) pins the asymmetric contract. |
| 16 | `tests/test_bates.py:185` duplicate `get_root` fixture copy (third project copy of the walk-family-root algorithm) | CLOSED (WONTFIX) | beta-2.14 Commit 13 (2026-04-30) | beta-2.11 Commit 2 | commit audit. PM reconnaissance 2026-04-30 + the maintainer's ratification: test-inlining-by-design serves as a regression-snapshot decoupled from production drift; the original Flag #8 preflight already considered + deferred cross-file consolidation; consolidating would defeat the broader inline-mirror convention. WONTFIX preserves the snapshot intent; future renames stay safe at production-call-sites without test re-writes. |
| 14 | M-4 SQL migration completion record (retroactive numbering for continuity) | CLOSED (completed) | beta-2.9 sprint close | beta-2.9 | `CHANGELOG.md` beta-2.9 section; `CLAUDE.md` §Audit Remediation Status |
| 17 | Raw `sqlite3.connect` in `home.py:522` bypasses `db_manager.get_connection()` — skipped WAL pragma and audit_log migration loop | CLOSED (fixed) | beta-2.12 Commit 1 (2026-04-20) | beta-2.11 Commit 3 (characterized) | commit audit |
| 20 | `INSERT OR IGNORE` silently drops rows on NOT NULL constraint violation — `document_productions.enddoc NOT NULL` interaction with backfill | CLOSED (fixed) | beta-2.13 Commit 1 (2026-04) | beta-2.11 Commit 5b fixture debug | commit audit (v2); closed via COALESCE(d.enddoc, d.begdoc) in backfill SELECT + pre/post eligibility-diff observability warning + regression pin |
| 24 | `db_manager.log_audit()` `user=` kwarg typo at 3 sites — silent no-op since written (TypeError swallowed by surrounding try/except) | CLOSED (fixed) | beta-2.14 Commit 5 (2026-04-28) | beta-2.14 C3a CLI v1 H-1 finding | commit audit. 3 sites: `pages/7_Custodians.py:545` (COLLECTION_SCOPE_UPDATED), `home.py:761` (INTEGRITY_VERIFICATION), `home.py:807` (NIST_CONFIG_UPDATED). PM grep-sweep 2026-04-28 confirmed bounded scope — only 3 of 156 log_audit calls affected. |
| 23 | CHANGELOG.md section ordering inversion — `[beta-2.13]` block at L8-L82 incorrectly preceded `[beta-2.14]` at L83, violating newest-at-top convention | CLOSED (fixed) | beta-2.14 Commit 13 (2026-04-30) | bookmarked in PM auto-memory during beta-2.14; registered + closed at sprint-close | commit audit (v3). Block-relocation fix: the entire `[beta-2.13]` block (~75 lines) moved to immediately after `[beta-2.14]`; `## [beta-2.14]` heading converted from "In Progress" to "Shipped 2026-04-30 (v2.14.0)"; L87 "section above" prose reference flipped to "section below" post-relocation. |
| 28 | Review text-search drops inbound hits + reindex content-preservation drops inbound content — `_id` vs `control_number` ambiguity across OS consumer paths | CLOSED (fixed) | beta-2.16 Commit 5 | beta-2.15 Commit 7 | commit audit — symptom-patched in beta-2.15 C7 at `pages/4_Review.py:2313`; full closure here: shared `cn_from_hit()` + `compute_os_id()` helpers in `os_manager.py`; consumer migrations at `pages/4_Review.py` (search loop) + `pages/9_InboundProduction.py:453`; `reindex_from_sqlite` content-preservation lookup fixed (`existing_content` keyed by `cn_from_hit(hit)`); `scan_all` docstring + `OPENSEARCH_PATTERNS.md` example updated; regression test pinned at `tests/test_os_id_canonical.py` (9 tests). |

**Note on #13:** originally listed as "Dormant — Deferred (open)" because it was from the beta-2.10 retrospective's thirteen-flag inventory but had not been picked up by a sprint. Closed in beta-2.14 Commit 10 (2026-04-30) per the asymmetric render-hygiene fix described in the row above; the state transitioned in-place from Deferred to Closed without row movement.

---

## Numbering history (for registry archaeology)

- **#1–#13** — enumerated in the beta-2.10 sprint retrospective (`~/.claude/projects/C--Users-<user>-Projects-ediscovery/memory/project_beta210_sprint.md`). Four have been closed in beta-2.11 (#7, #8, #11, #12); nine remain open.
- **#14** — retroactive; reserved here for the M-4 SQL migration completion record (which was tracked informally in CLAUDE.md §Audit Remediation Status and CHANGELOG but never assigned a flag number).
- **#15** — assigned to the instruction-corpus retrospective (this commit, 6a).
- **#16–#20** — registered by CLI in beta-2.11 audit docs (Commits 2, 3, 5, 5b).
- **#21** — placeholder for PM's "defensibility-PDF moment" QA pattern; context pending.
- **#22** — near-dupe analytics false-positive sensitivity (registered 2026-04 during beta-2.13 sprint close; surfaced in a design review of near-dupe clustering on invoice-style documents).
- **#23** — CHANGELOG.md section ordering inversion (registered + closed 2026-04-30 in beta-2.14 Commit 13 sprint-close addendum; surfaced as PM auto-memory bookmark during beta-2.14; register-and-close pattern matching Flag #24 precedent).
- **#24** — log_audit `user=` kwarg typo (registered + closed 2026-04-28 in beta-2.14 Commit 5; surfaced during C3a CLI v1 H-1 finding).
- **#25** — STR view `_vis_mode` undefined-name scope bug (registered 2026-05-07 mid-execution during beta-2.15 Commit 3; pre-existing latent bug since beta-2.7c; CLI-discovered while extending L438/L450 with the produced_only UX-filter, then rolled back per the maintainer's Path 3; deferred to a dedicated commit).
- **#26** — Archive-container coverage beyond .pst/.zip (registered 2026-05-15 in beta-2.15 Commit 4; surfaced during PM v1 §6.5 scope-expansion probe; deferred — preemptive `ARCHIVE_EXTS` expansion would be dead code until `container_exploder` gains handlers for those types).
- **#27** — EML inline-classification coverage gap on the .msg path (registered 2026-05-18 in beta-2.15 Commit 5; surfaced during PM v1 §6.2 probe verifying that the .msg COM path uses MAPI properties rather than Content-ID; deferred — .msg path doesn't share the defect today; flag exists so a future .msg-path rewrite remembers to consume the shared predicate).
- **#13 closure** — Flag #13 (originally registered in beta-2.10 retrospective; Deferred until beta-2.14) closed 2026-04-30 in beta-2.14 Commit 10 (roadmap C5) via the asymmetric render-hygiene fix. State transitioned from Deferred (open) to Closed (fixed) in-place; row stayed in the Dormant/Closed table.
- **#16 closure** — Flag #16 (`tests/test_bates.py:185` duplicate `get_root` fixture, originally registered beta-2.11 Commit 2; Deferred until beta-2.14) closed 2026-04-30 in beta-2.14 Commit 13 sprint-close addendum as WONTFIX per the maintainer's ratification (test-inlining-by-design serves as regression-snapshot decoupled from production drift). Row moved from Active to Dormant/Closed table.
- **#28** — Review text-search drops inbound hits (registered 2026-05-20 in beta-2.15 Commit 7; surfaced during inbound re-ingest testing; symptom patched same commit, full cross-codebase audit + regression test deferred).
- **#28 closure** — Flag #28 closed 2026-05-24 in beta-2.16 Commit 5 (pending) via shared `cn_from_hit()` + `compute_os_id()` helpers in `os_manager.py`, consumer-site migrations (`pages/4_Review.py` search loop + `pages/9_InboundProduction.py:453`), the `reindex_from_sqlite` content-preservation bug fix (was keyed by composite `_id`, now by `cn_from_hit(hit)`), `scan_all`/`OPENSEARCH_PATTERNS.md` doc-example updates, and a 9-test regression pin (`tests/test_os_id_canonical.py`). Cross-codebase audit confirmed `pages/4_Review.py` was the only vulnerable consumer; `pages/3_Analytics.py` already canonical (reads `_source.control_number` under projection); zero bulk re-fetch sites. Row moved from Active to Dormant/Closed.
- **2026-05-21 sprint-close cross-reference table backfill** — beta-2.15 Commits 1-7 added to the cross-reference table at the sprint-close addendum (rows for Commits 1, 2, 6, 7, 8 appended; existing rows for Commits 3, 4, 5 updated in-place with hash backfill + path remaps to `docs/archive/audits/beta-2.15/`). Cross-ref backfill scope: just beta-2.15 commits; the longstanding beta-2.12/beta-2.13 cross-ref table drift flagged in beta-2.13 retrospective §6 L98 stays bookmarked for future cleanup audit (no urgency; the main Active/Dormant flag tables carry current state).
- **#30** — production non-transitive NearDupe clustering (registered 2026-05-24 in beta-2.16 S-1a; surfaced during CLI's v4 delta-check pre-measurement of the shingling fix; pre-existing behavior, not an S-1a regression; deferred — fix needs a connected-components/union-find grouping pass over the LSH candidate graph; candidate for S-1b).
- **#22 closure** — Flag #22 (near-dupe false-positive sensitivity; registered 2026-04 in beta-2.13) closed 2026-05-24 in beta-2.16 Commit 6 via the S-1a NearDupe k-gram shingling fix. Row moved Active → Dormant/Closed at the C10 sprint-close addendum; sensitivity-tuning spec archived to `docs/archive/specs/neardupe_false_positive_sensitivity.md` (SHIPPED per the maintainer's Stage-1 ratification 2026-06-01 — the adjacent S-1b/S-1c cluster-review/reporting work built atop the fix but is not the spec's scope).
- **#31** — custodian-rename stale `hold_documents.file_path` (R-4; registered 2026-06-10 in beta-2.17 C-d, discovered in the C1 design pass). Active/Deferred; fix scheduled at C-c. Registered at C-d rather than its discovery commit (C1) because C1 landed registry-untouched — registering both #31 and #32 at the sprint's first registry-touching commit is the earliest repair and keeps visible numbering monotonic with no reserved-number gap (FLAG_REGISTRY maintenance rule 1, earliest-repair reading).
- **#32** — BYOS pull/push write-lock collision (R-5; registered + closed 2026-06-10 in beta-2.17 C-d via per-iteration commit in both BYOS loops). Discovered in the C1 design pass. Register-and-close-in-one-commit precedent: #23, #24.
- **#33+** — next assignment.

---

## Maintenance rules (proposal — to be codified in CLAUDE.md Commit 6b)

1. **Add a new flag only when:** a hypothesis or defect is discovered but fix is out of current-commit scope. Surface in the landing summary; register here in the same commit that discovers it.
2. **State field values:** `Active` / `Deferred` / `Characterized` / `Dormant` / `Closed` / `Pending PM context`.
3. **"Last updated"** must be bumped whenever severity or status changes, even if Title text doesn't change.
4. **Moving between tables** (Active → Dormant/Closed) is a registry edit, not a numbering change. The number persists.
5. **When closing a flag** attribute the closing commit's short hash and the audit doc that proved resolution (or the fix commit's preflight doc).
6. **Registry audits** — the maintainer or CLI should spot-check annually (or at major-version cuts) that no Active flag has gone stale. Update `<!-- Last audited: -->` comment at top when performed.

---

## Cross-reference: audit doc → flag list

Per-commit audit docs are internal working notes and are not part of this repository; the names below are kept for traceability.

| Sprint | Commit | Audit doc | Flags registered / closed |
| --- | --- | --- | --- |
| 2.11 | 1 | `commit_1_sqlite3_dead_import_preflight.md` | Closed: #7 |
| 2.11 | 2 | `commit_2_duplicate_get_root_consolidation_preflight.md` | Closed: #8; Registered: #16 |
| 2.11 | 3 | `commit_3_page_held_conn_characterization.md` | Characterized: #5; Registered: #17, #18 |
| 2.11 | 4 | `commit_4_review_to_dict_silent_loss_characterization.md` | Characterized: #11 |
| 2.11 | 4b | `commit_4b_to_dict_fix_preflight.md` | Closed: #11 |
| 2.11 | 5 | `commit_5_left_join_backfill_characterization.md` | Characterized: #12; Registered: #19 |
| 2.11 | 5b | `commit_5b_left_join_backfill_fix_preflight.md` | Closed: #12; Dormant: #19; Registered: #20 |
| 2.11 | 6a | `commit_6a_instruction_corpus_retrospective.md` | Registered: #15, #21 (placeholder); retroactive: #14 |
| 2.14 | 5 | commit audit | Registered + Closed: #24 |
| 2.14 | 10 | commit audit (v3) | Closed: #13 |
| 2.14 | 13 | commit audit (v3) | Closed: #16 (WONTFIX); Registered + Closed: #23 |
| 2.15 | 1 | (no preflight — sprint-open hygiene) | — |
| 2.15 | 2 | commit audit + `commit_2_flag5_class_b_sub_span_a_check_v1.md` + `_check_v2.md` | (Flag #5 Pattern X Class B sub-span A — partial closure, full Flag #5 still active) |
| 2.15 | 3 | commit audit (v2) + commit audit | Registered: #25 |
| 2.15 | 4 | commit audit (v3) + commit audit + `_check_v2.md` + `_check_v3.md` | Registered: #26 |
| 2.15 | 5 | commit audit (v3.1) + commit audit + `_check_v3.md` + `_check_v3_1.md` | Registered: #27 |
| 2.15 | 6 | commit audit (v3) + `_check_v1.md` + `_check_v2.md` + `_check_v3.md` | — (hygiene sweep, no flag) |
| 2.15 | 7 | (no preflight — Flag #28 maintainer-directed) | Registered: #28 |
| 2.15 | 8 | commit audit (v3) + `_check_v1.md` + `_check_v2.md` + `_check_v3.md` | — |
| 2.16 | 4 (S-3) | commit audit + `_check_v1.md` + `_check_v2.md` | — |
| 2.16 | 5 (S-2) | commit audit + `_check_v1.md` + `_check_v2.md` | Closed: #28 |
| 2.16 | 6 (S-1a) | commit audit + `_check_v1..v5.md` + `commit_6_s1a_execution_abort_report.md` | Closed: #22; Registered: #30 |
| 2.16 | 7 | commit audit + `_check_v1.md` + `_check_v3.md` | — |
| 2.16 | 8a (S-1b α) | commit audit + `_check_v1..v3.md` | — |
| 2.16 | 8b (S-1b β) | commit audit + `_check_v1..v3.md` | — |
| 2.16 | 8c (S-1b γ) | commit audit + `_check_v1.md` + `_check_v2.md` | — |
| 2.16 | 9 (S-1c) | commit audit + `_check_v1..v3.md` | — |
| 2.16 | 10 (sprint close) | commit audit + `_check_v1.md` | Closed: #22 (archival); Updated: #5, #30 |
| 2.17 | 1 (sprint-open) | (no preflight — sprint-open hygiene; tracks the design pass + AGPL brief) | — |
| 2.17 | 2 (C-d) | commit audit (v2) + `_check_v1.md` + `_check_v2.md` | Registered: #31 (Active/Deferred, closes at C-c); Registered + Closed: #32 |
