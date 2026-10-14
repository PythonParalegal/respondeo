# CLAUDE.md — Respondeo eDiscovery Platform

This file provides Claude Code with project context and standing instructions.

## Current State

| Field | Value |
|-------|-------|
| **Active branch** | `beta-2.17` (DB-hygiene sprint; cut from `main` on 2026-06-10. The post-v2.16.0 hook-contract fix rides on this branch — unpushed to `main`, will reach `main` at 2.17 ff-merge) |
| **Project version** | `2.16.0` (`__version__` in `config.py`; bumped at the beta-2.16 C10 sprint-close addendum) |
| **Last CHANGELOG date** | 2026-06-10 (post-v2.16.0 self-correction hook-contract fix) |
| **Last completed sprint** | Beta-2.16 (`v2.16.0`). Two arcs: **Phase 1** (library self-correction infrastructure per `docs/specs/library_self_correction_design.md`, originally "beta-2.16-meta") — triggers.py + refresher.md + 3 hooks + 3 Tier 4 promotions (commits 1–3). **Phase 2+ product arc (C4–C9):** S-3 stale test ref; S-2 Flag #28 closure + canonical OS-id helpers; S-1a Flag #22 NearDupe k-gram shingling; C7 mid-sprint debt absorption; S-1b near-dupe **Cluster Review workflow** — persistence/UI/reporting-glue (C8a–C8c); S-1c defensibility report **§4.2 near-dupe attestation**. Flags #22 + #28 closed; #30 registered (deferred). Notable: the S-1c B-1→B-2 double-catch at the preflight gate (partition-enumeration discipline). Retrospective `docs/retrospectives/beta-2.16.md`; audit corpus archived to `docs/archive/audits/beta-2.16/`. |
| **What's next** | **Beta-2.17 — DB-hygiene sprint.** Lead: **M-1 / Flag #5 Pattern A** (3 long-span page-held-connection orchestration sites) — resolve the Approach 1 (narrow `conn=None` threading) vs Approach 3 (page-scoped connection refactor) fork in a **design pass first** (characterized in beta-2.11 Commit 3; beta-2.16 retrospective P2.2/P2.5). Carryover: **Flag #30** union-find/connected-components cluster merge over the LSH candidate graph (S-1c reports overlap honestly but does not merge); **family-grouped native export** spec (UNSHIPPED since beta-2.15 C8); promote the **partition-enumeration** lesson to `docs/lessons/` on recurrence. Defer-further: Flag #25/#26/#27 latent defects. |

> **Keep this table current.** After every sprint, update these values before committing. See Standing Orders at the bottom of this file.

## Project Overview

Self-hosted Python/Streamlit eDiscovery platform for small law firms. Single-machine Windows deployment. Entry point is `home.py`; processing modules live in `pages/`.

## Key Architecture Rules

- RBAC: admin > manager > reviewer role hierarchy, gated by named permissions. Every page checks access at top via `auth_manager.require_permission('<name>')` annotated with a `# permission:` comment (see §Access Gate Convention below). The legacy `require_role()` API was removed in beta-2.7a Phase 13.
- Closed cases must block ALL write operations; reads must stay open. `case_status` checked at top of every page. **Do not use `st.stop()`** when a case is closed — that produces a blank page and hides the content the user came to see. Instead, render the full UI with write-capable widgets disabled (`disabled=True` on `st.button`, `st.selectbox`, `st.text_input`, etc.) and a banner explaining the case is closed.
- `log_audit()` and `log_audit_batch()` in `db_manager.py` are "never-raise" contracts — always wrapped in try/except in callers.
- All paths (wkhtmltopdf, tesseract, OpenSearch port, Tika port) must come from `config.py` only.
- Direct SQL in page files is a smell — queries should be in `db_manager.py`.
- `config.py` is gitignored (machine-specific paths). `config.example.py` is the template.
- **Hold Documents are NOT case ESI.** Files in `{case_folder}/Hold_Documents/` are attorney work product (hold notices, acknowledgments, retention policies) and must never enter the ingestion pipeline, receive control numbers, or be indexed in OpenSearch. The path is reserved for the Custodians module's legal hold tracking and is explicitly skipped by Ingestor directory scans.

## Branch Model

`main` (stable) → `beta-X.Y` (sprint) → `debug/...` (review/bugfix)

## Version Tracking — Mandatory on Every Edit

Every `.py` source file has a metadata header block. **You must maintain it on every edit.** Full rules are also in `.claude/skills/version-tracking/SKILL.md`, but the essential rules are inlined here so they are always in your context.

### Header Format

```
# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        <filename>.py
# version:       <major>.<minor>.<patch>
# project:       Respondeo eDiscovery Platform
# project_ver:   <current project version — must match __version__ in config.py>
# last_modified: <YYYY-MM-DD HH:MM>
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
```

### Rules (follow on EVERY file you touch):

1. **`last_modified`** — Set to current date AND time in `YYYY-MM-DD HH:MM` format (24-hour, local time). Every edit, no exceptions. We move through multiple sprints per day — date alone is not granular enough.
2. **`modified_by`** — Set to `claude-code`.
3. **`last_commit`** — Always write `pending`. NEVER fabricate a git hash.
4. **`version` (file-level version)** — This tracks individual file change history, independent of the project version.
   - **Patch bump** (e.g., 1.0.3 → 1.0.4): When changing behavior — bug fixes, logic changes, modifying existing functions.
   - **Minor bump** (e.g., 1.1.4 → 1.2.0, reset patch to 0): When adding a new function, class, or feature to the file.
   - **No bump**: Formatting-only or comment-only changes.
5. **`project_ver`** — Must match `__version__` in `config.py`. When the project version is bumped, update this field in every file you touch. `__version__` bumps in config.py are PM/CLI-autonomous engineering mechanics (per Standing Orders — Decision Routing): execute the bump and surface it in the landing summary + diff rather than proposing-and-waiting. Escalate only if a specific bump carries release/legal signaling (e.g., a public version a court filing references).
6. **CHANGELOG.md** — Add a one-line entry for every functional change. Format: `- ACTION: file.py — description`. Actions: `FIX`, `NEW`, `CHANGE`, `DOCS`, `RELEASE`.
7. **New files** — Must include the full header block with version `1.0.0`. Set `project_ver` to match current `__version__` in config.py. Add CHANGELOG entry: `NEW: filename.py — purpose`.
8. **Header preservation** — When editing a file, update fields in place. Do NOT delete or reformat the decorative border lines.

### Files That Do NOT Get Version Headers
- `__init__.py`, `config.example.py`, anything in `_scratchpad/`, anything in `tests/`, and non-Python files (`.md`, `.yaml`, `.json`, `.txt`).

### Self-Check Before Committing

Before you commit changes to ANY `.py` file, verify:
- [ ] `last_modified` is current date and time (`YYYY-MM-DD HH:MM`)
- [ ] `version` patch/minor was bumped appropriately (if behavior changed)
- [ ] `project_ver` matches `config.py __version__`
- [ ] `last_commit` says `pending`
- [ ] CHANGELOG.md has an entry for the change

## Access Gate Convention

When adding or modifying any access gate, annotate it with a `# permission:` comment naming the logical permission being enforced. This makes future migration to a permission-based access system a grep-and-replace operation.

```python
# permission: export_csv
if not auth_manager.is_manager():
    ...

# permission: redact_document
if _case_closed:
    ...
```

Use snake_case permission names that describe the action, not the role. Examples:
`export_csv`, `export_pdf`, `redact_document`, `run_analytics`, `manage_production`, `sync_filevine`, `manage_users`, `change_case_status`, `configure_columns`, `export_str_report`

## PST Extraction Architecture

- **libpff is primary**, COM is fallback. libpff runs headless in a subprocess via `_pst_worker.py`.
- **Never use `multiprocessing.Process`** for libpff — Windows spawn re-imports Streamlit's entry point, causing C-library hangs. Use `subprocess.Popen` with `_pst_worker.py`.
- **Outlook COM is not headless** — requires desktop session, shows blocking modal dialogs. Only used as fallback when libpff fails.
- **COM `AddStore()` cleanup is critical** — failed extractions leave zombie PST stores in Outlook that lock files. The `finally` block must scan by filepath to remove orphaned mounts.
- **MS-PST CRC algorithm** — Python's `binascii.crc32` does NOT match the MS-PST spec CRC. The `_repair_pst_header_crc()` function exists but is DISABLED until the correct algorithm is implemented.
- **libpff attachment B-tree corruption** — `msg.number_of_attachments` throws IOError/RuntimeError (not AttributeError). Must use explicit `try/except Exception`, not `getattr()`.
- **`extraction_notes`** column on documents table records per-document extraction quality warnings (corrupted attachments, etc). Displayed as warning banner in Review page.
- **`process_msg_batch` is Windows/Outlook-only.** It calls `pythoncom.CoInitialize()` directly without a guard. Only reachable for `.msg` files on Windows, which is an accepted platform constraint — the function must not be invoked from any non-Windows code path or any code path that has already initialized COM for a different apartment model.

## Redaction Discipline

Redaction is **non-destructive until production**. Two functions with very
different semantics:

- `add_redact_annot()` (in `4_Review.py`) writes a visible black annotation
  box. The underlying content remains in the PDF. Reviewers see the mark;
  the data is still there.
- `apply_redactions()` (called only in `5_Production.py` at burn time)
  destroys the content under every redaction annotation. This is
  irreversible — see `docs/references/PYMUPDF_PATTERNS.md` Known Gotcha #2.

**Iron law:** Never call `apply_redactions()` outside of the Production burn
path. Review, preview, and any other code that displays a marked document
must rely on the annotation overlay. The production pipeline copies the
source PDF to a temp file, burns redactions on the copy, then replaces the
original only after a successful burn — so the pre-burn PDF is preserved
under the Processed directory as the forensic record.

## Inline Image Detection (EML Explosion)

Three layers of inline image detection in `_explode_eml()`, checked in order:
1. **Content-ID header** — authoritative signal, skips the attachment
2. **HTML body filename match** — `_collect_html_referenced_images()` scans `<img src="...">` tags
3. **Orphaned images** (no CID, no HTML ref) — currently pass through as regular attachments; would need cross-document dedup to catch

`universal_imager.py` mirrors this: CID images get base64-substituted, filename-referenced images get substituted, orphans listed in Attachments header.

## Development Environment

- **Always use project venv**: `.venv/Scripts/python.exe` (system Python lacks dependencies)
- **Running tests from CLI**: `/c/Projects/ediscovery/.venv/Scripts/python.exe script.py`
- **Streamlit subprocess quirk**: `multiprocessing.Process` on Windows re-imports `home.py` — use `subprocess.Popen` for any subprocess work

## Audit Remediation Status

All 32 findings from the holistic audit (`docs/HOLISTIC_AUDIT_REMEDIATION.md`) are resolved except:
- **M-4**: SQL migration — **COMPLETE.** All 9 batches landed: 58 new db_manager functions, ~180 page-file calls migrated, 153 retained calls exempt-annotated, 49 defensibility_report.py queries migrated.
- **L-3**: Widget key naming convention (snake_case already consistent, prefix convention deferred)

## Dependency API References

The `docs/` directory contains curated API references for dependencies where our code has been bitten by incorrect attribute names, masked types, or undocumented behaviors. **Always consult the relevant reference before writing or modifying code that touches these systems:**

| Reference | Covers | Consult When Touching |
|-----------|--------|-----------------------|
| `docs/references/EMAIL_MIME_REFERENCE.md` | Python `email` module, MIME parsing, `get_filename()` behaviors, synthesized EML construction | `_explode_eml()`, `universal_imager.py` EML imaging, any MIME part handling |
| `docs/references/OUTLOOK_COM_REFERENCE.md` | `win32com` / Outlook MAPI COM, attachment types, property tags, threading rules | `process_msg_batch()`, `_explode_pst_com()`, `_walk_pst_folder()` |
| `docs/references/LIBPFF_API_REFERENCE.md` | `pypff` objects: file, folder, message, attachment attributes and methods | `explode_pst_libpff()`, `_libpff_msg_to_eml_bytes()`, `_walk_pst_folder_libpff()` |
| `docs/references/PYMUPDF_PATTERNS.md` | PyMuPDF (`fitz`): text extraction, redaction annotations, Story API, pixmap rendering | `2_Processor.py` text/OCR, `4_Review.py` redaction, `5_Production.py` burn, `universal_imager.py` |
| `docs/references/TIKA_METADATA_KEYS.md` | Apache Tika metadata key names and fallback chains by file format | `get_tika_data()`, `process_file_worker()` metadata mapping block |
| `docs/references/OPENSEARCH_PATTERNS.md` | Index schema, `_source` field names, query DSL patterns, `.keyword` suffix rules | `4_Review.py` search, `3_Analytics.py` scan/near-dupe, `2_Processor.py` bulk indexing |
| `DEPENDENCY_MAP.md` | Cross-module data surfaces: DB columns, file paths, session state, OpenSearch fields, config values, shared functions | Any change to shared data — schema migration, path convention, session state key, OpenSearch field, function signature |
| `docs/references/README.md` | Index of the dependency API reference library. The six `*_REFERENCE.md` / `*_PATTERNS.md` files above live here as of Commit 6c.1; this index is the "where do I look for X" entrypoint. | When you need a dependency reference whose exact filename you don't remember, or when adding a new dependency reference. |
| `docs/lessons/README.md` | Durable patterns, gotchas, and principles extracted from sprint retrospectives (substring-replace ordering, SQLite version floor, fragment-scope rule, atomic multi-table writes, zero-risk data-layer rollback, etc.). | Before writing code that resembles a past footgun, and when a sprint retrospective surfaces a lesson worth keeping. Classify new candidates against the Lesson Integration Decision Tree below. |
| `docs/templates/README.md` | Reusable workflow templates (preflight structure, defect-triage format, scoped-audit pattern). | When starting a preflight, defect triage, or scoped audit — reach for the template instead of reinventing the structure. |
| `docs/templates/preflight_template.md` | 8-section preflight scaffold for non-trivial commits. | Starting a preflight for a refactor, behavior change, or any commit with >1 file or >50 lines. |
| `docs/templates/preflight_drafting_checklist.md` | 10-item PM-side self-check run against every preflight before handoff. Strategic/hygienic split on permission-gated edits. | When drafting any preflight — run all 10 checks before presenting to the maintainer. |
| `docs/templates/preflight_lightweight.md` | 3-section preflight scaffold for doc-only and tiny hygiene commits (content plan / insertion points / rollback). | Starting a preflight for a doc-only commit, lesson canonization, Standing Order install, or tiny hygiene commit (≤3 files, ≤20 LOC) where the 8-section template would inflate discipline without reducing risk. |
| `docs/templates/defect_triage_template.md` | 8-section defect triage scaffold with diagnosis-before-fix discipline. | Triaging a mid-sprint defect scoped for a deferred fix commit. |
| `docs/templates/scoped_audit_template.md` | 6-pass scoped audit scaffold with read-only discipline. | Auditing a bounded code surface before deployment or after a set of sprints. |
| `docs/templates/pm_cli_collaboration_workflow.md` | Durable doc of the PM–CLI collaboration workflow (role split, preflight structure, review gate, compaction-survival design). | Onboarding a new Claude session to the project's collaboration model, or when Standing Orders reference "the collaboration workflow." |
| `docs/roles/README.md` | Role definitions for the two-WARP-tab collaboration model (PM Claude + Execution CLI). Each role runs in a dedicated tab, activated via `/pm` or `/cli` slash command. Write-scoped boundaries enforce the planning-tier vs. execution-tier split. | When starting a fresh WARP tab for planning (PM) or execution (CLI); when modifying role guardrails; when onboarding a new Claude session to the dual-tab collaboration model. |
| `docs/retrospectives/README.md` | Sprint retrospectives — durable records of each sprint's dead ends, course corrections, and lessons canonized. | When opening a new sprint (to see what was learned last time) and when closing a sprint (to write the current one). |
| `.claude/triggers.py`, `.claude/refresher.md`, `docs/discipline_graveyard.md` | Living self-correction infrastructure: keyword-trigger map (16 MVP entries incl. `drift-correction-language` meta-trigger), session-start refresher (top recurring misses, 5-slot cap), and promotion graveyard log. | When catching yourself drifting (update `triggers.py` inline per Standing Order A); at sprint-close (refresh `refresher.md` per Standing Order B); at Tier 4 promotion (log to graveyard per `docs/specs/library_self_correction_design.md` §4). |

**Rules:**
- Before using any attribute, method, or metadata key from these dependencies in new code, verify the correct name in the reference. Do not guess from training data.
- If you discover a new gotcha or undocumented behavior during a sprint, add it to the relevant reference file's "Known Gotchas" section.
- The libpff reference (`LIBPFF_API_REFERENCE.md`) includes a TODO section — check it before assuming any attribute exists on a pypff object.

## Critical Rules

- NEVER remove existing functionality unless the user explicitly instructs you to delete a specific feature. When adding headers, metadata, formatting, or performing refactoring operations across multiple files, preserve ALL existing code. If you encounter code you don't understand or think might be dead, ASK before removing it.
- When editing multiple files in a batch operation (like adding headers to all files), review each file's diff before committing to ensure no functional code was lost.

## Standing Orders — Decision Routing: Maintainer-Judgment vs Engineering-Mechanics

The maintainer is a legal-domain practitioner using AI to build this platform, not a full-time software engineer. Route decisions accordingly.

Maintainer ratification required (Stage 1 judgment):
- Legal/defensibility semantics — anything affecting what is produced, withheld, redacted, audit-logged, or represented to a court.
- EDRM/workflow correctness — whether platform behavior matches discovery practice.
- UI/usability — the maintainer is the end user.
- Scope/priority — what gets built, what gets deferred, anything changing deliverables.

PM/CLI autonomous (decide per engineering best practice; report in the landing summary; do not ask):
- Commit naming, numbering, bundling/splitting, branch management, tag and merge mechanics (the sprint-close ordering Standing Orders still govern how).
- Registry/roadmap/CHANGELOG bookkeeping mechanics and doc-filing tier decisions.
- Implementation choices within ratified scope (idioms, refactor shape, test structure).
- `__version__` bump mechanics — amends Version Tracking rule 5 and Context Maintenance item 4: visibility is now satisfied by the landing summary + diff, not propose-and-wait.

Escalation rule: a mechanics decision with legal or usability implications (what a tag name represents to opposing counsel, what the defensibility PDF shows) crosses into maintainer-judgment — escalate. When genuinely unsure which side a decision falls on, make the best-practice call and flag it prominently in the landing summary rather than blocking on a question.

The PM↔CLI N-Stage Gate is unchanged — it is the second-opinion model between the two AI roles, not maintainer-review burden. What narrows is what requires the maintainer's explicit ratification inside it.

## Standing Orders — Pre-Fix Investigation Protocol

Before implementing ANY bug fix, complete these steps. Skipping investigation
to jump straight to a fix is prohibited.

**Iron Law: No fix without confirmed root cause.**

1. **Trace the data flow.** Starting from the origin of the affected data
   (ingestion, user input, or DB read), trace its path through every function
   and module until the failure point. Document the chain in a brief comment
   at the top of the commit message.

2. **Identify all consumers.** For any database column, file path, session
   state key, or shared data structure involved in the bug, look it up in
   `DEPENDENCY_MAP.md` and identify every module that reads from or writes
   to it. List them explicitly.

3. **Confirm root cause before writing code.** State the root cause as a
   single sentence. If you cannot state it clearly, you have not found it
   yet — keep investigating.

4. **Three-strike circuit breaker.** If a fix attempt fails validation three
   times, STOP. Do not attempt a fourth fix. Instead, report:
   - What was tried
   - What failed and why
   - What remains unknown
   The human will reassess the approach before continuing.

5. **Verify no collateral damage.** After implementing the fix, check that
   every consumer identified in step 2 still works correctly with the changed
   data. This is not optional — sprint-introduced regressions are the #1
   recurring defect pattern in this project.

## Standing Orders — Post-Sprint Cross-Module Impact Audit

After every sprint's functional changes are complete (but BEFORE Context
Maintenance and before the final commit), perform a cross-module impact check.

1. **List every change target.** Enumerate every database column, file path
   pattern, session state key, config value, OpenSearch field, or shared
   function signature that was added, modified, or removed during this sprint.

2. **Consult DEPENDENCY_MAP.md.** For each change target, look up its entry
   in the dependency map. If the target is not listed, grep the codebase:
   - All `.py` files in the project root
   - SQL strings (including f-strings and parameterized queries)
   - OpenSearch field references in query DSL
   - Session state keys (`st.session_state["..."]` and `st.session_state['...']`)
   - File path construction (`os.path.join`, pathlib, f-string paths)

3. **Verify or fix each cross-reference.** For each consumer found:
   - If it already matches the new schema/format: note as verified
   - If it uses a stale name or format: fix it in this sprint
   - If ambiguous: flag for the human

4. **Update DEPENDENCY_MAP.md.** If this sprint added a NEW cross-module
   dependency (new shared DB column, new session state key read by another
   module, new OpenSearch field, new shared function), add it to the
   appropriate section of `DEPENDENCY_MAP.md` in the same commit.

5. **Report the audit in the commit message:**
   ```
   Impact audit: N change targets, M cross-refs verified, K fixes applied,
   J items flagged for human review.
   ```

6. **Reconcile the sidebar navigation registry.** For every new or renamed
   page file in `pages/` this sprint, verify the corresponding tuple exists
   in `auth_manager._NAV_PAGES`. For every removed page file, verify the
   tuple is gone. Silent drift between filesystem and registry hides pages
   from the post-login sidebar (Module 9 was invisible to logged-in users
   for one commit between the extraction and the registry fix — see
   beta-2.10 Commits 6 and 7.7). `tests/test_nav_registry_consistency.py`
   pins this contract at test-time; the audit step catches it during
   sprint review.

**This audit is mandatory.** It exists because prior sprints introduced
silent downstream failures (see DEPENDENCY_MAP.md §7 "Known Regression
Patterns"). The five minutes this takes prevents hours of debugging.

## Standing Orders — Dependency Map Maintenance

`DEPENDENCY_MAP.md` is a living document. Keep it current:

- **On every sprint:** If you add, rename, or remove a database column, file
  path convention, session state key, OpenSearch indexed field, config value,
  or shared function signature, update the relevant section of
  `DEPENDENCY_MAP.md` in the same commit as the code change.
- **On schema migrations:** When adding an `ALTER TABLE` migration to
  `db_manager.py`, add the new column to the appropriate risk tier in §1.
- **On regression fixes:** When fixing a bug caused by cross-module drift,
  add it to §7 "Known Regression Patterns" so the pattern is never repeated.
- **Audit date:** Update the `<!-- Last audited: -->` comment at the top of
  the file whenever you perform a full-file review of accuracy.

## Standing Orders — Context Maintenance

After **every sprint** (before the final commit), CLI Claude must perform these updates so that Browser Claude (project planning sessions) always starts with current state:

1. **Update the Current State table** (top of this file):
   - `Active branch` — output of `git branch --show-current`
   - `Project version` — `__version__` from `config.py`
   - `Last CHANGELOG date` — date of the topmost CHANGELOG.md entry
   - `Last completed sprint` — name of the sprint just finished
   - `What's next` — brief pointer to the next roadmap item or open work

2. **Update MEMORY.md** (in the Claude memory directory):
   - Keep it under ~40 lines total
   - Reflect current branch, last sprint, what's next, and any changed user preferences or project context
   - Remove stale information that no longer applies

3. **Update user-facing and technical documentation** for any features added or changed in this sprint:
   - `Walkthrough.md` — executive overview for partners and supervising attorneys
   - `Technical Overview.md` — internal engineering reference (architecture, schema, modules)
   - `User_Guide.md` — end-user manual for paralegals, case managers, attorneys
   - `PROJECT_CONTEXT.md` — comprehensive AI development context reference
   - For each new feature: add the appropriate section(s) to each doc, matching the existing style and depth
   - For changed features: update the relevant sections to reflect new behavior

4. **Request permission before updating** `ROADMAP_TODO.md`'s *substantive* content during context maintenance — it is normally human-authored:
   - `ROADMAP_TODO.md` — priority shifts, new roadmap items, and deferred-item reshuffling are scope/priority decisions = maintainer-judgment (per Standing Orders — Decision Routing); Claude may propose edits and execute after explicit greenlight. Bookmark-row and spec-lifecycle bookkeeping is autonomous per `feedback_durable_doc_write_directly`.

   `config.py __version__` bumps are **no longer gated here** — they are PM/CLI-autonomous engineering mechanics per Standing Orders — Decision Routing (visibility via landing summary + diff, not propose-and-wait). The permission gate that remains is "don't surprise the maintainer" on scope/priority, not "never touch."

5. **CHANGELOG.md** — add a `DOCS:` entry if the context maintenance changed anything substantive (not for routine table updates)


## Standing Orders — Lesson Integration Decision Tree

When a sprint produces a new lesson, pattern, gotcha, or reusable workflow,
classify it against this decision tree BEFORE the sprint closes. The
classification determines where the content lives permanently. Misfiling is
the failure mode that caused the beta-2.11 documentation reorg.

1. **Is this a rule I must follow on every turn?** → Add to CLAUDE.md as
   an iron law or Standing Order. Keep terse (one paragraph max, prefer
   pointer over prose). Examples: the "never-raise" contract on audit
   logging, the "closed cases block all writes" rule.

1.5. **Is this a recurring drift pattern that should be wired into
   self-correction?** → Add an entry to `.claude/triggers.py`. This
   catches the pattern in real-time on future sessions via the
   UserPromptSubmit / PreToolUse hooks. If pattern recurs despite
   triggers, promote to `.claude/refresher.md` per the Sprint-Close
   Refresher Review Standing Order. See
   `docs/specs/library_self_correction_design.md` §3.1 and §4.

2. **Is this a body of knowledge I need when I touch dependency X?** →
   Add to `docs/references/<NAME>_REFERENCE.md`. If the reference doesn't exist,
   create it. Examples: PyMuPDF redaction gotchas, libpff attribute names,
   Tika metadata keys.

3. **Is this a reusable workflow template?** → Add to `docs/templates/`.
   Strip sprint-specific details; keep the pattern. Examples: the preflight
   structure, the defect-triage format, the scoped-audit 6-pass.

4. **Is this a durable lesson or pattern extracted from a sprint?** →
   Add to `docs/lessons/` as a single focused file. Examples:
   substring-replace ordering footgun, SQLite version floor, atomic
   multi-table write pattern, zero-risk data-layer rollback principle.

4.5. **Is this a sprint-specific story or texture worth preserving as a
   forensic record?** → Write into `docs/retrospectives/<branch>.md` at
   sprint close using the template at `docs/retrospectives/template.md`.
   Retrospectives are promoted from mid-sprint discussions and capture
   the dead ends, course corrections, and lessons canonized during a
   sprint. If a retrospective surfaces a durable pattern, promote the
   pattern to `docs/lessons/` (step 4) in the same or next commit; the
   retrospective itself stays in place as the forensic record.

5. **Is this a completed one-shot artifact (spec, sprint doc, prompt)
   with no ongoing value beyond forensic record?** → Move to
   `docs/archive/{sprints,specs,prompts,m4}/`. Do not delete — git
   history and archive let future readers trace what happened.

6. **Is this stale and redundant with current docs?** → Delete with a
   CHANGELOG note explaining why. This is the only case where deletion
   is appropriate. Default is archive, not delete.

**Sprint-close checklist item:** Before cutting the version tag, grep
`CHANGELOG.md` for this sprint's entries. For each functional change,
verify the associated lesson (if any) has been classified against this
tree and filed in the correct tier. If a lesson exists but hasn't been
filed, file it in the sprint-close commit.

**Index maintenance:** Whenever a file is added to `docs/lessons/`,
`docs/templates/`, or `docs/references/`, update the README.md index
in that directory AND the pointer table in CLAUDE.md's Dependency API
References section. A reference file without an index entry is a file
I cannot find.


## Standing Orders — Sprint-Close Retrospective

At the close of every sprint (before the version tag is cut and before
merge to main), write a retrospective at `docs/retrospectives/<branch>.md`
using the template at `docs/retrospectives/template.md`.

**Mandatory for any sprint that:**

- Touched more than 3 files across more than 3 commits
- Produced at least one new `docs/lessons/` entry
- Required the maintainer's intervention on a scope or design question
- Revealed a failure mode in the PM–CLI collaboration workflow

For smaller sprints, a retrospective is optional — default to writing
one if uncertain. The cost is low and future Claude sessions benefit
from the texture that commit history alone doesn't capture.

**The retrospective is the forensic record** of the sprint. Commit
history records what landed; CHANGELOG records why each commit
happened; the retrospective records the dead ends, course corrections,
patterns that surfaced, and lessons worth canonizing. It is the layer
where institutional knowledge lives when it isn't yet (or isn't ever)
a durable lesson in `docs/lessons/`.

**Promotion from retrospective to lesson.** Durable patterns surfaced
in a retrospective should be classified against the Lesson Integration
Decision Tree (see above) and, if appropriate, promoted to
`docs/lessons/`, `docs/templates/`, `docs/references/`, or CLAUDE.md.
The retrospective itself remains in place as the forensic record of
how the lesson was derived.

**Authorship.** Retrospectives are synthesis/architectural work and
default to PM Claude's scope. PM drafts the retrospective in the days
leading up to sprint-close and saves it to
`docs/retrospectives/<branch>.md` directly. If PM has not drafted the
retrospective by the time CLI is executing the sprint-close addendum
commit, CLI may draft it inline during that commit as a fallback —
faster than pinballing back to PM mid-sprint-close. In the fallback
case, PM reviews the CLI-drafted retrospective in the sprint-close
commit diff before the maintainer approves the commit landing. Either way, the
retrospective lands in the sprint-close addendum commit and is subject
to the Audit-Doc Archival + Tag-cut ordering rules that govern that
commit.


## Standing Orders — Audit-Doc Archival at Sprint Close

At the close of every sprint (after the retrospective is written and
before the version tag is cut), all per-commit audit docs produced
during the sprint must be archived.

**Scope — what gets archived:**

- Preflight files for commits in this sprint (`docs/audits/commit_N_*_preflight.md`).
- Characterization docs (`docs/audits/commit_N_*_characterization.md`).
- Execution packets (`docs/audits/commit_N_*_execution_packet.md`).
- Instruction-corpus or similar retrospective files (`docs/audits/commit_N_*_retrospective.md`).
- This addendum's own preflight (self-archiving).

**Destination:** `docs/archive/audits/<branch-name>/` (e.g., `docs/archive/audits/beta-2.11/`). Create the tier directory if it doesn't exist; add a tier-README indexing the files chronologically with one-line purposes.

**Ref-update obligation:** Before archiving, grep the living-doc tier (`docs/lessons/`, `docs/templates/`, `docs/FLAG_REGISTRY.md`, `CLAUDE.md`, `ROADMAP_TODO.md`, any active preflights in `docs/audits/`) for refs to the moving files. Update every ref to the new archive path. Historical archives (`CHANGELOG.md`, `docs/archive/specs/`, the moving files' internal cross-refs to each other) stay stale by design per `docs/lessons/chain-of-moves-stale-refs.md`.

**Rename collision:** The next sprint will begin with its own `commit_1_*` preflight. Archival must complete before the new sprint's first preflight is drafted. If a beta-X.Y+1 preflight was drafted ahead (using a `commit_bX_Y+1_N_*` prefix as a collision-avoidance workaround), rename it to `commit_N_*` as part of the same archive commit.

**Commit packaging:** The addendum ships as a dedicated sprint-close commit (e.g., Commit 10) with its own preflight. That preflight self-archives in the same commit (git mv to `docs/archive/audits/<branch>/`). Phase A = file moves; Phase B = ref updates; Phase C = tier-README creation + Standing Order install (if not yet installed — one-time per project) + Current State table refresh + retrospective addendum + CHANGELOG entry.

**Tag-cut ordering:** The version tag for a sprint must not be cut until the audit-doc archival commit has landed on the sprint branch and been verified. Sprint-close sequence: (1) retrospective written; (2) audit docs archived + living-doc refs updated; (3) context maintenance refresh (CLAUDE.md Current State table, memory files, user-facing docs, CHANGELOG); (4) merge sprint branch to main (`git merge --ff-only <sprint-branch>`); (5) cut version tag on main at the ff-merge-final commit; (6) push main then push tag. Cutting the tag earlier produces the premature-release-tag failure mode captured in `docs/lessons/premature-release-tag.md` — the tag points at an intermediate state that does not include the sprint's final housekeeping, and correcting it requires either force-retagging (safe only on solo/private repos) or cutting a patch release.

**Why this is codified:** The beta-2.11 sprint closed without this step despite the sprint's theme being "doc architecture cleanup" — the sprint's own housekeeping got missed. That produced Commit 10 of 2.11 as a corrective addendum. See `docs/retrospectives/beta-2.11.md` §7 for the full story. The failure mode is cognitive — at sprint-close the reviewer is focused on the big artifact (CHANGELOG, retrospective, Current State table) and the per-commit preflights become invisible. The Standing Order forces the archival step into the sprint-close checklist explicitly.


## Standing Orders — N-Stage Gate Revision-Handling Doctrine

The PM–CLI collaboration model is an N-stage gate, not a two-stage gate.
A patched preflight is a new preflight. Every PM revision to a preflight,
made in response to CLI's pre-flight check findings, requires a fresh
delta-scoped CLI pre-flight check before Stage 2 greenlight opens.
Greenlight and patch never ship in the same message.

**Iron rule:** If PM modifies a preflight after CLI has begun its
pre-flight check pass, PM must send the revised preflight back to CLI
with a delta-scoped re-check request and hold Stage 2 greenlight
pending CLI's clean report. Every revision adds a gate rather than
collapsing one.

**Delta-check scope** is typically:

1. Structural verification on the patched content (re-run affected
   grep counts, re-verify markers if the patch touched anything in an
   extraction range).
2. Scope-expansion second opinion on the new text (look for new
   factual claims, new file enumerations, new paths).
3. Grep-count predictions affected by the patch.
4. Confirm the fix actually addresses the original flag.

Everything CLI already verified and PM did not touch stays verified.
Don't re-run the full pre-flight pass each round.

**Why this is codified as an iron law:** The failure mode is PM
cognitive — the temptation to collapse patch + greenlight into one
message is natural and happens quietly. The scenarios where the gate
matters most are precisely the ones where PM feels confident the patch
is small / contained / structurally safe. That confidence is the exact
failure mode the gate was built to catch. See
`docs/lessons/n-stage-gate-revision-handling.md` for the canonized
pattern and `docs/templates/pm_cli_collaboration_workflow.md` §5.4
for the operational protocol.


## Standing Orders — PM–CLI Collaboration Workflow

All non-trivial commits follow the preflight-before-execution workflow
documented at `docs/templates/pm_cli_collaboration_workflow.md`. That
document defines the PM Claude / CLI Claude / maintainer role split, the
mandatory preflight structure, the investigation and execution protocols,
the review-and-proceed gate, and the compaction-survival design. Do not
deviate from that workflow without explicit instruction.


## Standing Orders — Save-Location Coordination

PM Claude (Cowork planner) and CLI Claude (WARP executor) must write
specs and planning docs to the same canonical locations so neither drifts
from the other's mental model. Two conventions operate side-by-side — do
not collapse them to one:

1. **Hand-written specs, preflights, sprint plans, design docs, defect
   triage docs** → `docs/specs/` (if active/unshipped) or
   `docs/archive/{specs,prompts,m4,sprints}/` (if shipped/superseded).

2. **Skill-generated artifacts from the superpowers skill system
   (`brainstorming`, `writing-plans`, `subagent-driven-development`,
   `requesting-code-review`)** → `docs/superpowers/{specs,plans}/YYYY-MM-DD-<topic>.md`
   per the skill's mandate. These filename patterns are skill-enforced
   and are NOT save-location drift — leave them alone.

**Rules:**

- When drafting a spec or preflight, save directly to `docs/specs/` with
  a descriptive filename. Do not stage in `_scratchpad/` unless the
  content is genuinely ephemeral (and `_scratchpad/` is gitignored so
  nothing there becomes a durable record).
- When a skill writes to `docs/superpowers/`, do not relocate the output.
  The skill chain depends on the path; downstream skills read from there.
- When a spec ships (behavior lands, tests pass), move the spec from
  `docs/specs/` to `docs/archive/specs/` in the next sprint-close commit.
  See Standing Order §Spec Lifecycle Discipline below.
- `ROADMAP_TODO.md`'s §Active Specs section lists bookmarks for
  `docs/specs/` entries only. Archived specs are pruned from that list
  at archive time. Never bookmark files under `docs/superpowers/`
  (they're skill outputs, not sprint deliverables).

**Why this matters:** In beta-2.11 6e.1, PM discovered `docs/superpowers/`
existed with 10 files and almost relocated them thinking they were CLI
save-location drift. Hard evidence from SKILL.md line numbers showed they
were skill-mandated outputs. The dual-convention must be explicit in
Standing Orders so a future session doesn't make the same mistake.


## Standing Orders — Spec Lifecycle Discipline

Every spec in `docs/specs/` has one of three statuses at any given time:
ACTIVE (being worked on this sprint), UNSHIPPED (written but not yet
implemented), or SHIPPED (behavior has landed, file awaiting archive).

**Sprint-close rule:** Before cutting the version tag for a sprint, for
every spec that shipped during the sprint:

1. Verify the behavior is in main-branch code (grep, runtime test).
2. Confirm a CHANGELOG entry exists for the shipping commit.
3. `git mv docs/specs/<spec>.md docs/archive/specs/<spec>.md`.
4. Delete the spec's bookmark from `ROADMAP_TODO.md` §Active Specs.

All four steps or none. Partial lifecycle transitions (shipped code but
spec still in `docs/specs/` and still bookmarked) cause the Active Specs
list to silently grow beyond the actual active work, which is how
`docs/specs/` accumulated 20 entries before the beta-2.11 cleanup.

**Exception — NUANCED status:** If only part of a spec shipped (a
primitive exists but the broader scope is not yet wired up), the spec
stays at UNSHIPPED with a one-line "Partial shipping note" at the top
describing what subset has shipped and under what name. The spec does
NOT archive until the broader scope lands. Example:
`USER_PREFERENCES_SPEC.md` — `save_user_pref` primitive shipped for
`last_case` persistence but Review-grid-column-persistence and per-user
`column_picker` are unshipped; spec stays in `docs/specs/` as UNSHIPPED.


## Standing Orders — Supply Chain Security

Before installing, upgrading, or adding ANY Python package, complete these checks. This protocol exists because of real-world supply chain attacks (e.g., LiteLLM compromise, March 2026) where transitive dependencies exfiltrated credentials from developer machines via hijacked `.pth` files.

**Iron Law: No new dependency without explicit human approval.**

1. **No silent installs.** Never run `pip install <package>` for a package not already in `requirements.txt` without asking the human first. This includes transitive dependencies pulled in by a new package — run `pip install --dry-run <package>` first and report what would be installed.

2. **Vet before adding.** Before recommending any new package to the human, check:
   - PyPI download count and project age (is it established or brand new?)
   - Does it pull in a large transitive dependency tree? (flag anything that would add 10+ sub-dependencies)
   - Is it an LLM orchestration layer (litellm, langchain, llama-index, etc.)? These carry massive dependency trees and are high-value targets — require extra justification.

3. **Post-install .pth audit.** After any `pip install` operation, scan the venv's `site-packages/` directory for `.pth` files. The only expected `.pth` file is `distutils-precedence.pth`. Any other `.pth` file is suspicious and must be reported to the human immediately — do NOT proceed with further work until acknowledged.

4. **Vulnerability scan after any dependency change.** After any `pip install`, `pip upgrade`, or `requirements.txt` change, run `pip-audit` against the venv and report any findings to the human before continuing. If `pip-audit` is not installed, install it first (it is the ONE exception to the "ask first" rule — it is a dev-only security tool maintained by PyPA with minimal dependencies).

5. **Pin everything.** When adding a new dependency to `requirements.txt`, always pin to an exact version (`package==X.Y.Z`), never use `>=` or unpinned specifiers. This prevents auto-upgrading to a compromised release.

6. **No MCP servers without approval.** Never add entries to `.mcp.json` or install MCP server packages (via pip or npx) without explicit human approval. Report what the server does and what dependencies it requires.

7. **Credential hygiene.** Never store API keys, tokens, or secrets in any tracked file. If a package or tool requests credentials during setup, stop and ask the human how they want to handle it.


## Standing Orders — Triggers & Refresher Living Documents

`.claude/triggers.py` is updated continuously, not on a schedule. When
you catch yourself drifting (or the maintainer catches you), update the file in
the same turn as the correction. Add a `TRIGGERS` entry with the
keyword(s) that should have fired and the reminder you needed. The
trigger map is the durable record of recurring drift patterns; the goal
is to make every miss caught once never miss again.

`.claude/refresher.md` is updated at sprint-close per Standing Order
§Sprint-Close Refresher Review (below).

See `docs/specs/library_self_correction_design.md` §3.1 and §11.


## Standing Orders — Sprint-Close Refresher Review

Slots into the existing sprint-close sequence between the retrospective
(Standing Order §Sprint-Close Retrospective) and audit-doc archival
(Standing Order §Audit-Doc Archival at Sprint Close).

For each slot in `.claude/refresher.md`:

1. Increment recurrence counter if pattern recurred this sprint.
2. Check promotion criteria (3+ recurrences across 2+ sprints AND
   binary-checkable OR reducible to single checklist question).
3. If criteria met → **implement Tier 4 promotion in this sprint-close
   commit**:
   - Binary-checkable → add hook script + settings.json registration
   - Judgment-required → add preflight-drafting-checklist item
   - Log to `docs/discipline_graveyard.md` (date, pattern, mechanism,
     recurrence count at promotion)
   - Vacate slot in refresher.md
4. If slot has zero recurrence for 2 consecutive sprints → demote (keep
   triggers.py entry, vacate refresher slot).
5. Cap at 5 slots forces hard prioritization: cannot add a new pattern
   unless you promote or demote.

See `docs/specs/library_self_correction_design.md` §4 for the
promotion ladder.


## Standing Orders — Sprint-Close Triggers Audit

This is Layer B of the meta-recursive bootstrap-closure defined in
`docs/specs/library_self_correction_design.md` §11.

**Triggers Audit (hard gate — required for sprint-close addendum
commit to land).** For every miss documented in this sprint's
retrospective §4 (or equivalent "dead ends," "corrections," "misses
canonized" sections), list:

- The miss (one line)
- The `triggers.py` entry that would have caught it (by ID)
- If no entry caught it: "ADDED → <new entry ID>" with the entry
  appearing in the same commit diff
- If intentionally not adding (e.g., one-off): "NOT ADDED because
  <reason>"

Paste this table as a section of the sprint-close commit message.
Without it, the addendum commit cannot land. This closes the bootstrap
hole: if Layer A's real-time drift-correction trigger missed the
in-session update, this audit catches it post-hoc.

## Standing Orders — Preflight-Drafting-Checklist Check 11 + Check 12

`docs/templates/preflight_drafting_checklist.md` carries two judgment-required
checks for grep-count discipline:

- **Check 11 (Grep-count cross-verification)** — installed beta-2.14 C6 with
  five empirical sprint examples; the authoritative grep-count discipline
  surface. Canonized in `docs/lessons/grep-count-discipline.md`.
- **Check 12 (Broaden-without-reinventory re-scan)** — Tier 4 promotion
  added in beta-2.16-meta after 6 recurrences in beta-2.14-2.15 of the
  meta-recursive defect (patch closes a class then commits same class
  elsewhere). Pinned here per `docs/specs/library_self_correction_design.md`
  §4 promotion ladder. See `docs/discipline_graveyard.md` for the
  promotion record.

Both checks are hard-gated in the preflight: a preflight that cites a
count or broadens a scope MUST paste verification output (grep command +
result) inline. The gate is structural, not advisory.
