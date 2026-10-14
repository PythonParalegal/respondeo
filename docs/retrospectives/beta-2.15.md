# beta-2.15 Retrospective

**Sprint:** `beta-2.15`
**Version tag cut:** `v2.15.0` (pending merge to main + tag cut)
**Commit range:** Commit 1 (sprint-open hygiene) through this addendum (Commit 8)
**Written:** 2026-05-21 by CLI Claude (WARP tab)
**Author:** CLI Claude (drafted at execution time per PM Appendix A nit (c) — PM provided content plan in §1.A.1; CLI filled in narrative prose during the sprint-close addendum execution).

---

## 1. Sprint Scope

Beta-2.15 was planned per `docs/archive/specs/beta_2_15_roadmap_proposal.md` (drafted at beta-2.14 C7) as a cleanup-audit sprint targeting beta-2.14's deferred backlog. The roadmap enumerated 10 candidates across 4 priority tiers: Must-do M-1 Flag #5 Class B sub-span A (3 error-path sites in `6_Sync.py:328, 341, 354`, commit-restructuring required) + M-2 Flag #5 Pattern A consolidation (3 surfaces across 2-3 commits). Should-do S-1 Flag #22 near-dupe false-positive sensitivity + S-2 CI secrets/PII guard + S-3 stale `TestProductionInboundExclusion` doc reference. Nice-to-have N-tier hygiene including 3 PM grep-count discipline observations awaiting 2+ recurrences before canonization. Defer-further tier: none carried in this tree.

The sprint pivoted heavily during execution. Only M-1 shipped from the original roadmap; the remainder of the sprint absorbed four out-of-roadmap hot patches surfaced during re-ingest testing plus one docs hygiene commit. M-2 + most S-tier and N-tier work carries forward to beta-2.16.

## 2. What Shipped

8 commits total. 1 sprint-open + 1 roadmap + 4 hot patches + 1 docs hygiene commit + 1 sprint-close addendum:

| Commit | Summary |
| -------- | --------- |
| 1 (sprint-open) | Sprint-open hygiene. ROADMAP_TODO header refresh; FLAG_REGISTRY last-audited timestamp refresh; CLAUDE.md Current State table re-aligned with beta-2.14 close + v2.15.0-pending posture. |
| 2 (roadmap M-1 / Flag #5 Class B sub-span A) | FIX: Flag #5 Pattern X Class B sub-span A — 3 error-path sites in `6_Sync.py:328, 341, 354` hardened. Commit-restructuring delivered: each error-path UPDATE+audit pair now flushes via `conn.commit()` before `continue`. |
| 3 (out-of-roadmap / family-expansion UX) | FIX: Review module family-expansion toggles + UX-filter. Family grouping in the Review grid extended with a session-scoped produced-only UX filter at the main grid + export/helper paths. Path 3 disposition mid-execution rolled back planned 4-site extension to 2 sites (L2496 + L3012) after CLI discovered `_vis_mode` undefined-name latent bug (Flag #25 registered). |
| 4 (out-of-roadmap / PST-as-family-root) | FIX: PST-as-family-root architectural fix. Container-family model rewritten so emails extracted from PST/ZIP archives root families at the email envelope rather than the container. Two-layer fix: ingestion model (root-pinning) + family-walk consumers (group_id-aware traversal). New lesson `docs/lessons/container-family-model.md`. Flag #26 (archive-container coverage beyond .pst/.zip) registered. |
| 5 (out-of-roadmap / EML CID over-skip) | FIX: EML attachment Content-ID over-skip in libpff-extracted .eml files. `_explode_eml` previously dropped every PST-extracted attachment because libpff stamps Content-ID on all attachments regardless of inline status. New shared predicate `is_part_inline_image(part, html_cids, html_filenames)` consumed by both extraction (`container_exploder._explode_eml`) and rendering (`universal_imager.convert_eml_to_pdf`). New lesson `docs/lessons/extraction-rendering-symmetry.md`. Flag #27 (.msg-path coverage gap) registered. |
| 6 (out-of-roadmap / docs hygiene) | DOCS: living-doc hygiene across 5 files (CLAUDE.md, roadmap proposal, beta-2.13/2.14 retros, grep-count-discipline.md). |
| 7 (out-of-roadmap / Flag #28 inbound search) | FIX: Review text-search OS hits on inbound-production documents silently dropped from the Review grid. `hit['_id']` consumed the volume-prefixed composite ID while the downstream filter used unprefixed `control_number`. Fix reads `_source.control_number` with `_id` defensive fallback. Maintainer-directed without preflight (matching Flag #24 precedent); renumber sub-scope folded in via Appendix B of Commit 6 preflight + PM Gap 1 expansion (3 additional FLAG_REGISTRY sites CLI surfaced during pre-execution scope check). Flag #28 registered + symptom patched same commit. |
| 8 (sprint-close addendum, this commit) | DOCS: beta-2.15 sprint-close. Retrospective + audit-doc archival (17 files + this preflight + 3 check files → `docs/archive/audits/beta-2.15/`) + tier-README + living-doc ref updates (R1-R5) + spec lifecycle (archive `beta_2_15_roadmap_proposal.md`, track `family_grouped_native_export_preflight.md`) + CLAUDE.md Current State refresh + `__version__` 2.14.0 → 2.15.0 + project_ver cascade across 6 .py files + retrospectives/README.md catalogue backfill + FLAG_REGISTRY current-state refresh (cross-ref table backfill for beta-2.15 Commits 1-8 per Q3 Option A; Gap 2 deeper backfill deferred) + ROADMAP_TODO.md update + user-facing doc updates per Q4 Brief scope. Self-archives this preflight. |

## 3. Goals vs. Outcomes

### Achieved as planned

- **M-1 Flag #5 Class B sub-span A** (Commit 2). 3 error-path sites hardened in `6_Sync.py`; commit-restructuring delivered as planned in the roadmap.
- **Tag identity decision (`v2.15.0`).** The maintainer confirmed natural increment from `v2.14.0`; no skipping. Beta-2.15's 8 substantive commits including 4 hot patches recognizably 2.15.x scope.

### Achieved with adjustment

- **Out-of-roadmap insertions absorbed mid-sprint.** Four hot patches (Commits 3/4/5/7) surfaced during re-ingest testing. Two carried lessons that canonized: `docs/lessons/container-family-model.md` from Commit 4 (PST-as-family-root architectural fix) and `docs/lessons/extraction-rendering-symmetry.md` from Commit 5 (EML CID over-skip / shared predicate). Three new flags registered (#25 `_vis_mode` undefined-name in STR view; #26 archive-container coverage gap beyond .pst/.zip; #27 .msg-path EML inline-classification coverage gap).
- **Commit 6 docs hygiene + Commit 7 Flag #28 chronological renumber.** The Flag #28 hot patch was originally numbered Commit 6 in the working tree (registered in FLAG_REGISTRY + drafted in CHANGELOG); the maintainer's mid-sprint decision to insert the docs hygiene commit ahead of Flag #28 produced a Commit 6 → Commit 7 renumber across CHANGELOG L10 header + FLAG_REGISTRY L3/L53/L92. Renumber scope was expanded mid-execution per CLI pre-execution scope check (Gap 1: 2 mid-row L53 references) + PM extension (Gap 1 site 3: L3 last-audited annotation).
- **Docs-hygiene preflight 4-catch chain.** Commit 6 preflight cycled v1→v3 with three CLI catches (F-1 L57 retro, F-2 L179 spec See-also, scope-extension for L53 PM-extended L3) plus one PM self-catch at draft time (L87 roadmap proposal). Each catch followed the same pattern: comprehensive grep against the in-scope surface surfaced what the prior round inventoried against a partial mental model. Bookmarked as the "broaden-without-reinventory" defect family; convergence toward 5th `grep-count-discipline.md` family pending one more empirical recurrence.
- **Sprint-close (Commit 8) preflight v1→v3.** CLI v1 surfaced three findings (F-3 Blocking on `git mv` failing against untracked `docs/audits/`, F-1 Hygiene on missed hash backfill, F-2 Hygiene on misordered verification grep). CLI v2 surfaced two prose-clarity nits (H-1 header label drift, H-2 Step 11 contradictory parenthetical) — both meta-recursive: the v2 patches closing v1 findings introduced fresh prose ambiguity inside their own fixes. PM v3 explicitly named the meta-recursive pattern and closed the loop. Sixth grep-count recurrence in the sprint.

### Deferred

- **M-2 Flag #5 Pattern A consolidation** (3 surfaces, 2-3 commit arc) — bookmarked as beta-2.16 M-1.
- **S-1 Flag #22 near-dupe false-positive sensitivity** — spec at `docs/archive/specs/neardupe_false_positive_sensitivity.md` ready; bookmarked as beta-2.16 S-1.
- **S-2 CI secrets/PII guard** — priority elevated given the sprint's 4 grep-count catches; bookmarked as beta-2.16 M-2.
- **S-3 stale `TestProductionInboundExclusion` doc reference** at `tests/test_bates.py:331` — bookmarked.
- **Flag #28 cross-codebase audit + regression test** — symptom patched in Commit 7; full audit of other OS consumer paths with `_id`-vs-`control_number` ambiguity (3_Analytics.py, os_manager.reindex_from_sqlite, bulk-action re-fetch sites) + mock-OS regression test deferred.
- **Flag #25 / #26 / #27 latent defects** (STR view `_vis_mode` undefined; archive-container coverage gap; .msg-path EML inline-classification coverage gap) — all Active / Deferred; bookmarked for future sprints.
- **Family-grouped native export feature execution** — spec at `docs/specs/family_grouped_native_export_preflight.md` (tracked this sprint); UNSHIPPED, carries to beta-2.16+.
- **N-tier nice-to-haves** (3 grep-count discipline observations awaiting empirical recurrence; PM auto-memory disposition; transitive-wrapper threading; auto-memory hygiene-sweep Standing Order) — carryover.
- **Cross-ref table Gap 2 deeper backfill** (beta-2.12/beta-2.13 drift per beta-2.13 retro §6 L98) — per Q3 Option A, only beta-2.15 commits backfilled this sprint; deeper drift remains bookmarked.

## 4. Surprises and Learnings

The sprint that was planned isn't the sprint that shipped. The original roadmap was a cleanup-audit thesis: Flag #5 Pattern A consolidation, analytics quality (Flag #22), and discipline canonization (grep-count observations from beta-2.14). What actually consumed beta-2.15 was four out-of-roadmap hot patches surfaced during re-ingest testing, plus a docs hygiene commit.

The hot-patch dominance was the first surprise. Commits 3 (family-expansion UX), 4 (PST-as-family-root architectural fix), and 5 (EML CID over-skip) emerged in close succession from maintainer-side re-ingest testing. Each one surfaced an architectural defect that had been latent through prior sprints. Commit 4 in particular — the PST-as-family-root fix — rewrote the container-family model in a way the planned M-1 work didn't touch; the defect had silently shipped through beta-2.7 onward and only surfaced when reviewers tried to walk attachment families from PST-extracted emails. Commit 5 followed days later when re-ingest under Commit 4's new family model exposed that libpff stamps Content-ID on every PST attachment regardless of inline status, and the extraction path had been silently dropping every non-image attachment as "inline." Both fixes canonized new lessons (`container-family-model.md` and `extraction-rendering-symmetry.md`). The pattern is consistent: hot-patch commits under real-world verification produce durable patterns more reliably than scheduled roadmap commits in some sprints.


The third surprise was the preflight cycle dynamics at Commit 6 and Commit 8. Commit 6 produced a four-catch chain — PM self-catch at draft time (L87 roadmap proposal), CLI v1 F-1 (L57 retrospective), CLI v2 F-2 (L179 spec See-also), and a mixed PM+CLI catch during Commit 7 prep (L53/L3 FLAG_REGISTRY scope expansion). Each catch followed the same shape: comprehensive grep against the in-scope surface surfaced what the prior round inventoried against a partial mental model. The defect family is now bookmarked as "broaden-without-reinventory" — every pattern update needs to be paired with a re-inventory against the broadened pattern, otherwise the broadening fixes the detection but not the inventory. The fifth recurrence came at Commit 8's preflight v1→v2 cycle: PM acknowledged that v1's Check 1 "verified tracked via `ls`" had conflated filesystem existence with git-tracked status — the same `not-in-git-tracked-not-existent.md` lesson canonized in beta-2.11 (precedent: C6e.1 scratchpad move + C8 in-session-drafted spec). Second recurrence of the gap, despite the canonized lesson; the Check 1 discipline needs to use `git ls-files` and `git status --short`, not `ls`. The sixth recurrence came at Commit 8's v2→v3 cycle, where the v2 patches closing F-1/F-2/F-3 introduced two fresh prose ambiguities (H-1 §1.B.1 header label drift + H-2 Step 11 contradictory parenthetical). v3 named the meta-recursive pattern explicitly, invoking `feedback_meta_recursive_defect.md`, and closed the loop.

The N-Stage Gate held up across all six recurrences. Every catch came from CLI's pre-flight check pass running comprehensive grep on the patched surface — exactly the second-opinion function the gate was designed to provide. The maintainer's intervention at Stage 1 (Q1-Q5 ratification for Commit 8) and Stage 2 greenlight after CLI's clean v3 report followed the doctrine cleanly. Patch + greenlight never collapsed into a single message; each revision triggered a fresh delta-scoped re-check.

The sprint-close also produced a small Commit 7 scope-expansion moment worth recording. CLI's pre-execution scope check on Appendix B (Commit 6 preflight's guidance for Commit 7's working-tree pass) surfaced two L53 FLAG_REGISTRY mid-row "Commit 6" references not enumerated in PM's original Appendix B. PM concurred with the recommended Option C (expand to fix Gap 1 in Commit 7, defer Gap 2 cross-ref-table backfill to Commit 8) and surfaced a third missed site at L3 (last-audited annotation). The pattern — PM's enumeration against a partial mental model, CLI's pre-execution scope check catching the gap, PM's extension adding one more missed site — is itself another data point for the "broaden-without-reinventory" defect family.

## 5. Lessons Canonized

- `docs/lessons/container-family-model.md` (NEW, Commit 4) — durable pattern for how PST/ZIP archive containers root family relationships. Email envelope (not container) is the family root; family-walk consumers must traverse via `group_id` from the email row.
- `docs/lessons/extraction-rendering-symmetry.md` (NEW, Commit 5) — when two code paths classify the same thing (e.g., "is this attachment inline?"), they must use the same predicate. Shared `is_part_inline_image()` between `_explode_eml` and `convert_eml_to_pdf` enforces single source of truth.
- **Bookmark (not yet canonized):** "broaden-without-reinventory" — pattern updates and per-commit content lists must both pass a final comprehensive-grep gate before declaring inventory complete. Single empirical family in this sprint (6 recurrences across Commit 6 + Commit 7 + Commit 8 preflight cycles) — folds naturally into `docs/lessons/grep-count-discipline.md` as a 5th defect family on the next recurrence in a future sprint, OR canonized at beta-2.16 sprint-open per Lesson Integration Decision Tree.
- **Bookmark (not yet canonized):** Check 1 (Not-in-git verification) discipline gap — `git ls-files` and `git status --short` are authoritative; `ls` is not. Second project-wide recurrence (precedent: beta-2.11 C6e.1 + C8). Worth folding into preflight-drafting-checklist Check 1 wording revision in a future canonization commit.

## 6. Gotchas for Future Sprints

- **Flag #5 Pattern A consolidation (M-2)** — 3 surfaces, 2-3 commit arc with new `db_manager.run_*` helpers. Bookmarked as beta-2.16 M-1.
- **Flag #22 near-dupe sensitivity (S-1)** — spec at `docs/archive/specs/neardupe_false_positive_sensitivity.md` ready for execution. Bookmarked as beta-2.16 S-1.
- **S-2 CI secrets/PII guard** — priority elevation: manual hand-grep checks are not sustainable.
- **Flag #28 cross-codebase audit + regression test** — symptom patched in Commit 7; cross-codebase scan for other `_id`-vs-`control_number` ambiguities in OS consumer paths (3_Analytics.py, os_manager.reindex_from_sqlite, bulk-action re-fetch sites) + regression test pinning behavior with mock OS responses of both shapes. Bookmarked.
- **Flag #25 (`_vis_mode` STR view undefined-name)** — surfaced during Commit 3 mid-execution; pre-existing since beta-2.7c. Active / Deferred.
- **Flag #26 (archive-container coverage gap beyond .pst/.zip)** — surfaced during Commit 4; if `container_exploder.explode_container` ever gains .rar/.7z/.tar/.gz/.mbox support, the new family-model rule will treat them as email-propagating. Active / Deferred.
- **Flag #27 (.msg-path EML inline-classification coverage gap)** — surfaced during Commit 5; .msg path uses MAPI properties rather than Content-ID, so doesn't share the over-skip defect today, but a future .msg-path rewrite must consume the shared predicate. Active / Deferred.
- **Family-grouped native export feature** — spec `docs/specs/family_grouped_native_export_preflight.md` UNSHIPPED, tracked this sprint. Carries to beta-2.16+. Q5 disposition: defer rename until feature executes.
- **Cross-ref table Gap 2 deeper backfill** (beta-2.12 / beta-2.13 drift per beta-2.13 retro §6 L98) — only beta-2.15 backfilled this sprint per Q3 Option A. Bookmarked for future cleanup-audit commit.
- **"Broaden-without-reinventory" + Check 1 gap bookmarks** — 6 recurrences this sprint of the comprehensive-grep / re-inventory failure mode. Beta-2.16 should plan to canonize OR fold into `docs/lessons/grep-count-discipline.md` as a 5th defect family.

---

## Provenance

This retrospective was drafted by CLI Claude during the sprint-close documentation cascade for `beta-2.15`. PM provided the content plan in the sprint-close preflight; CLI authored narrative prose at execution time per Stage 2 greenlight + Q1-Q5 Stage 1 ratification. The maintainer reviewed at commit-staging time before the addendum landed.
