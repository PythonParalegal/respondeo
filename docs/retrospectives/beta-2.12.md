# beta-2.12 Retrospective

**Sprint:** `beta-2.12`
**Version tag cut:** `v2.12.0` (pending merge to main after this commit)
**Commit range:** sprint start (Flag #17 fix) through the sprint-close addendum (this commit) — 5 commits total including this one.
**Written:** `2026-04-20` by CLI Claude (during sprint-close housekeeping)
**Author:** CLI Claude

---

## 1. Sprint Scope

Beta-2.12 was originally scoped as a DB-hygiene mini-sprint: Flag #17 (raw `sqlite3.connect` in `home.py:522` → `db_manager.get_connection()`) as Commit 1, followed by Flag #20 (INSERT OR IGNORE silent drop), narrow-scope Flag #18 (`conn=None` convention), and Flag #5 (9 latent-risky page-held-conn sites). Per CLAUDE.md Current State "What's next" set during beta-2.11 C10: *"beta-2.12 Commit 1 — Flag #17 (raw `sqlite3.connect` in `home.py:522` bypassing `db_manager.get_connection()`). Preflight already drafted."*

The sprint did not follow that plan. Only Flag #17 shipped as planned. The remaining three commits were meta/process work that surfaced in reaction to events inside the sprint itself — the premature-tag recovery from beta-2.11 and the preflight-iteration overhead on C2's doc-only commit. Flag #20 / Flag #18 / Flag #5 carry over to beta-2.13.

Sprint theme in retrospect: **premature-tag recovery + proportionality discipline.**

## 2. What Shipped

| Commit | Summary |
| -------- | --------- |
| 1 — Flag #17 | Swap raw `sqlite3.connect(_db_path)` at `home.py:522` to `db_manager.get_connection(_case_path)`; remove dead `_db_path` local at line 519; move Flag #17 from Active to Dormant/Closed. Dashboard reads now under canonical connection path (WAL pragma + audit_log migration loop + 60s timeout). The only code-change commit of the sprint. |
| 2 — Premature Release Tag lesson | Canonize `docs/lessons/premature-release-tag.md` (recovery procedure for tags cut before sprint-close addendum lands) + install CLAUDE.md **Tag-cut ordering** subsection under the Audit-Doc Archival Standing Order. Triggered by the 2026-04-20 discovery that `v2.11.0` had been cut at beta-2.11 C7 two days before the sprint actually closed at C10, forcing a force-retag. Four-iteration preflight cycle (v1→v4). |
| 3 — Sprint-transition hygiene | Backfill three `<pending>` placeholders in `docs/FLAG_REGISTRY.md` (Flag #17 row + two beta-2.11 C6a historical refs) and close three CHANGELOG sprint-header staleness windows (beta-2.11/2.10/2.9 all still labeled `— In Progress`). Scope expanded inline by the maintainer during pre-flight-check after PM's original preflight missed the multi-occurrence count for both grep predictions. |
| 4 — Preflight Proportionality | Canonize `docs/lessons/preflight-proportionality.md` + install `docs/templates/preflight_lightweight.md` (3-section scaffold). Surfaced directly from C2's four-iteration cycle: applying the 8-section template to a doc-only commit inflated discipline without reducing risk. C3+C4 shared a single lightweight preflight (self-demonstrating) rather than each getting their own 8-section document. |
| 5 — Sprint-close addendum | Archive the four preflights to `docs/archive/audits/beta-2.12/`, write this retrospective, refresh CLAUDE.md Current State, update MEMORY.md, bump `__version__` 2.11.0 → 2.12.0. Runs the Tag-cut ordering rule installed in C2 (merge + tag happen on main, after this commit lands). |

## 3. Goals vs. Outcomes

### Achieved as planned

- **Flag #17 fix.** The one code-change commit the sprint set out to do. Landed cleanly in C1. Preflight went through one Stage-1 → Stage-2 cycle with no CLI findings.

### Achieved with adjustment

- **Sprint-close discipline itself was stress-tested and hardened.** The sprint arc (C2 → C3 → C4) was a reactive cycle: discovering the premature v2.11.0 tag forced a force-retag, which triggered canonizing the premature-release-tag lesson, which triggered a four-iteration preflight cycle, which surfaced the proportionality problem, which produced the lightweight template. Each was a real improvement to process discipline — but none was in the original sprint plan.

### Deferred

- **Flag #20** (INSERT OR IGNORE silent drop on NOT NULL constraint violation) — still Active in FLAG_REGISTRY. Not touched this sprint. First candidate for beta-2.13.
- **Flag #18** (narrow-scope `conn=None` convention where needed for Flag #5) — still Active. Deferred to beta-2.13 after Flag #20.
- **Flag #5** (9 latent-risky page-held-conn sites) — still Characterized / Deferred. Beta-2.13 tail end.
- **Cleanup audit** (a full-sprint scoped audit pass called out in the beta-2.11 close notes) — still flagged for a later sprint.

## 4. Surprises and Learnings

The sprint was supposed to open with Flag #17 and roll through three or four code-change commits. Instead, the first commit landed cleanly and then three consecutive meta/process commits followed — none of which were on the roadmap when the sprint started.

The trigger was the premature-tag discovery. The maintainer cut `v2.11.0` at beta-2.11 C7 on 2026-04-18, reasonably thinking the sprint was closing at the doc-cascade-plus-version-bump commit. But C7 wasn't the end — C8 (preflight-drafting checklist), C9 (sprint-close hardening), and C10 (audit-doc archival addendum) all landed afterward. On 2026-04-20, during beta-2.12 planning, PM noticed the tag was still at C7 and the sprint's final three commits were untagged. A force-retag was possible because the Respondeo repo is private and has a single maintainer (verified zero downstream consumers). The correction landed cleanly — `git push --force-with-lease=refs/tags/v2.11.0:<old-hash>` moved the tag from C7 to C10 without incident. But the failure mode was exactly the kind of thing that could silently ship in a public repo with no recovery path. The premature-release-tag lesson canonizes both the failure mode and the correction procedure.

Drafting that lesson's preflight is where the second surprise surfaced. The preflight went through four iteration cycles (v1 → v4) with CLI delta-checks at each stage. v3 caught a real execution bug (Finding D — §7.4's literal CHANGELOG markdown block included a duplicate section header that would have failed Phase C). But v2's Findings B and C, and v4's Finding F, were cleanup-level convention-compliance rather than execution bugs. Finding F surfaced only when CLI broadened its review to "any execution-ordering assumption still undeclared" — i.e., when CLI went looking for something to find. The token spend across four iterations was disproportionate to a doc-only commit's actual risk surface. The maintainer flagged the imbalance at ~95% context budget: *"The discipline we put in place is becoming a massive token burn... we are on version 5 of a preflight just trying to fix a relatively small pedantic issue."* The correct response was to accept v4 as-is, resolve Finding F with a one-line execution note in the Stage 2 greenlight message, and canonize the lesson for future commits.

The third surprise was PM memory drift. C3's preflight made two factually-wrong grep predictions (`<pending>` → 0 and `— In Progress` → 1) without checking current file state. Each was a simple fact-lookup that PM didn't run, so both predictions would have failed post-execution verification and confused CLI. The maintainer's response was short: *"PM's memory seems to be drifting and is causing a lot of small errors that are causing compute churn in the back and forth."* CLI expanded C3 scope inline to close all three staleness windows (not just beta-2.11's) and all three `<pending>` placeholders (not just Flag #17's), which simultaneously fixed the predictions and closed pre-existing historical drift in the CHANGELOG and FLAG_REGISTRY. No further PM iteration required.

Three scope-expansion probes fired naturally this sprint: two from the premature-tag story (C2 → CLAUDE.md Tag-cut ordering subsection; C3's hygiene bundling) and one from the C2 iteration overhead (C4's proportionality lesson + lightweight template). All three probes passed the three-criteria test when applied — same cognitive root cause in each case, same sprint-close discipline surface. The probes that did NOT fire were the ones the maintainer caught and corrected: C3's multi-occurrence grep predictions and C4's self-consistency gap (template scaffold missing §0 that the preflight using it had). Both were caught in pre-flight check, not at draft time.

## 5. Lessons Canonized

New `docs/lessons/` entries:

- `docs/lessons/premature-release-tag.md` — Tag cut waits for the sprint-close addendum commit; force-retag is only safe on solo/private repos with verified zero downstream consumers.
- `docs/lessons/preflight-proportionality.md` — The 8-section preflight fits code refactors; doc-only and tiny hygiene commits warrant the 3-section lightweight template instead.

New `docs/templates/` entries:

- `docs/templates/preflight_lightweight.md` — 3-section scaffold (content plan / insertion points / rollback) with §0 Greenlight Gate placeholder for N-Stage Gate posture boilerplate.

New `CLAUDE.md` Standing Order subsections:

- **Tag-cut ordering** subsection added to the existing "Audit-Doc Archival at Sprint Close" Standing Order. Codifies the sprint-close sequence (retrospective → archival → context maintenance → merge → tag cut → push) as enforceable iron-law text alongside the lesson's forensic discussion.

## 6. Gotchas for Future Sprints

- **Flag #20, #18, #5 all deferred to beta-2.13.** Original beta-2.12 scope. Still Active in FLAG_REGISTRY. beta-2.13's Commit 1 is naturally Flag #20 (INSERT OR IGNORE silent drop) per the registry.
- **PM memory drift as a recurring failure pattern.** This sprint had three separate PM-side misses caught at pre-flight check: wrong uniqueness claim (Finding A), wrong grep prediction count (Finding B), scaffold/preflight self-inconsistency (Finding C). The pattern is small pedantic errors that inflate iteration count. Candidate for a dedicated lesson in beta-2.13 or later — something like "PM-side fact-checking before handoff" — or a checklist item in `preflight_drafting_checklist.md` explicitly requiring a grep-count verification step at draft time. Not urgent but worth tracking.
- **The lightweight template's first real use was this sprint's own C3+C4 preflight** (self-demonstrating). Its second real use will be beta-2.13 Commit 1 or any doc-only commit in that sprint — that's where the proportionality principle actually gets tested across sessions rather than within one.
- **beta-2.9 never got a `v2.9.0` git tag.** The `__version__` variable went 2.9.0 during that sprint, then jumped to 2.11.0 at beta-2.11 C7 (skipping 2.10.0 intentionally). The `v2.10.0` tag exists but `v2.9.0` does not. C3's CHANGELOG header fix explicitly notes this (`Shipped 2026-04-16 (internal __version__ 2.9.0; no git tag cut)`). Not a live problem, but archaeology-class information worth preserving.
- **CHANGELOG `— In Progress` staleness is a recurring pattern.** Beta-2.10 and beta-2.9 both shipped with their headers left as `— In Progress` for long after their tags were cut. C3 closed those retroactively this sprint. The new Tag-cut ordering subsection's sprint-close sequence (step 3: context maintenance refresh) should catch this going forward — but worth a grep-for-stale-headers check at next sprint close to verify the pattern is actually broken.
- **Post-tag Current State refresh always trails the sprint-close commit.** Both beta-2.11 ("Current State table refresh — hygienic cleanup caught post-C9") and beta-2.12 (this sprint's analogous commit at the head of beta-2.13) needed a small follow-up commit to refresh CLAUDE.md Current State after the tag was cut. The structural reason: the sprint-close commit itself is authored before the merge/tag steps run, so its "What's next" field can't reference its own just-shipped tag without lying about ordering. The "Active branch" field also can't flip to the next sprint until that sprint's branch is cut, which only happens after the tag lands. Pattern: every sprint-close generates a small post-tag housekeeping commit on the *next* sprint's branch. Could be operationalized as a sprint-OPEN checklist item in CLAUDE.md (mirroring the Tag-cut ordering subsection's sprint-CLOSE sequence) — candidate for beta-2.13 if a natural slot opens, or a future hygiene sweep.

---

## Provenance

This retrospective was written by CLI Claude during the beta-2.12 sprint-close documentation cascade on 2026-04-20. Scope expansion authority throughout the sprint came from the maintainer in response to PM memory drift; the retrospective captures the resulting arc faithfully. Second use of the `docs/retrospectives/template.md` scaffold (first use was beta-2.11).
