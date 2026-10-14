# Project Roadmap & TODO Checklist
*Last updated: 2026-06-10 — beta-2.17 open (DB-hygiene sprint, sprint-open hygiene), version 2.16.0*

---

## Active Specs

> **Source of truth for to-do blueprints.** Every spec below lives in `docs/specs/`.
> When a spec's work ships, it moves to `docs/archive/specs/` (or the appropriate archive tier)
> AND its bookmark here gets checked off in the same commit. See CLAUDE.md Standing Orders —
> Spec Lifecycle Discipline (added in Commit 6e.3).

### Pattern docs — permanent reference, not archival candidates

- [`Spec_Intake_Inbox_Pattern.md`](docs/specs/Spec_Intake_Inbox_Pattern.md) — seeded the docs/specs/ convention in beta-2.10; describes the intake-inbox pattern for sprint spec management

### Unshipped — awaiting implementation

- [ ] [`BUG_privilege_status_cleared_on_save.md`](docs/specs/BUG_privilege_status_cleared_on_save.md) — two defects in `4_Review.py` save handler: privilege/responsiveness/review-status multiselects don't pre-populate from DB on load; save handler's `else` branch nulls `privilege_status` when no privilege tags in form even on unrelated edits
- [ ] [`Respondeo_License_System_Spec.md`](docs/specs/Respondeo_License_System_Spec.md) — licensing/activation system (phone-home, hardware fingerprinting, zip-based updates). Post-beta-2.9 work per memory.
- [ ] [`Spec_Batch_Remediation_and_Admin_Module.md`](docs/specs/Spec_Batch_Remediation_and_Admin_Module.md) — Batch Remediation (quarantine+remove wrong-case documents) and Admin Module. "Target Version: TBD (post beta-2.9)".
- [ ] [`SPEC_interactive_redaction_viewer.md`](docs/specs/SPEC_interactive_redaction_viewer.md) — interactive redaction viewer spec.
- [ ] [`USER_PREFERENCES_SPEC.md`](docs/specs/USER_PREFERENCES_SPEC.md) — review grid column layout persistence + per-user `column_picker` permission delegation. `save_user_pref` primitive already shipped in auth_manager.py for `last_case` persistence, but the spec's main use case (Review column persistence) is not wired up.
- [ ] [`family_grouped_native_export_preflight.md`](docs/specs/family_grouped_native_export_preflight.md) — Family-grouped hybrid native export (parents as imaged PDFs, attachments in native format, filename-prefixed family clustering for downstream upload to case-management systems like Filevine). Forward-looking strategic feature. Tracked at beta-2.15 C8 sprint-close. UNSHIPPED, awaiting beta-2.16+ execution slot.
- [ ] `flag5_pattern_a_design_pass.md` — **beta-2.17 lead.** Flag #5 Pattern A DB-hygiene design pass: settles the Approach 1 (narrow `conn=None` threading) vs Approach 3 (page-scoped connection refactor) fork and defines the C-a/C-b/C-c/C-d commit arc (incl. new latent defects R-4 Flag #31 custodian-rename stale `file_path`, R-5 Flag #32 BYOS pull write-lock collision). Maintainer-ratified 2026-06-10; tracked at beta-2.17 sprint-open. C-d is in flight (preflight drafted).
- [ ] `pymupdf_agpl_isolation_decision_brief.md` — PyMuPDF (AGPL-3.0) license-or-isolate decision brief: buy the Artifex commercial license (Option 1) vs free-path hybrid swapping `fitz`→`pypdfium2`+`Pillow` on the render/search path and isolating fitz-only ops behind a subprocess worker (Option 2). UNSHIPPED — deferred pending the maintainer's license-vs-free decision + IP counsel. Target beta-2.17+.
- [x] [`neardupe_false_positive_sensitivity.md`](docs/archive/specs/neardupe_false_positive_sensitivity.md) — **SHIPPED beta-2.16 C6, Flag #22 CLOSED, spec archived.** Near-dupe false-positive sensitivity tuning landed via the S-1a NearDupe k-gram shingling fix.
- [x] **beta-2.16 roadmap** — **CLOSED `v2.16.0` (2026-06-01).** Shipped: S-3 (stale test ref, C4) · S-2 Flag #28 closure + canonical OS-id helpers (C5) · S-1a Flag #22 k-gram shingling (C6) · mid-sprint debt absorption (C7) · S-1b near-dupe Cluster Review workflow — persistence/UI/reporting-glue (C8a/b/c) · S-1c defensibility report §4.2 near-dupe attestation (C9). **Deferred to beta-2.17:** M-1 Flag #5 Pattern A.

  **beta-2.17 — DB-hygiene sprint (seed).** Lead: **M-1 / Flag #5 Pattern A** (3 long-span page-held-connection orchestration sites) — resolve the Approach 1 (narrow `conn=None` threading) vs Approach 3 (page-scoped connection refactor) fork in a **design pass first** (characterized in beta-2.11 Commit 3; see beta-2.16 retrospective P2.2/P2.5). Carryover: **Flag #30** union-find/connected-components merge over the LSH candidate graph (S-1c reports overlap honestly but does not merge); **family-grouped native export** spec (UNSHIPPED since beta-2.15 C8); promote the **partition-enumeration** lesson to `docs/lessons/` if it recurs.

  **S-2 (CI secrets/PII guard)** — **SHIPPED beta-2.16.** `.claude/hooks/precommit_pii_guard.py` (Phase-1-meta Commit 2): blocks keys/tokens, real-looking emails and phone numbers, plus an optional local deny-list.

### Superpowers-origin specs

Phase 3 self-reflection (6e.1) concluded skill-mandated location: the Superpowers
`brainstorming` and `writing-plans` skills save to `docs/superpowers/specs/` and
`docs/superpowers/plans/` respectively, and reference that path in downstream
skill prompts. No files migrated; the 10 files under `docs/superpowers/` stay
where the skills put them. See `docs/superpowers/README.md` for the convention
and CLAUDE.md Standing Orders — Save-Location Coordination (added in Commit 6e.3).

---

## Phase 1: Stabilization & Performance ✅

- [x] SQLite WAL mode, `.executemany()` batch inserts, parameterized queries
- [x] OpenSearch bulk operations via `helpers.bulk` with chunking
- [x] Rotating file handler logging

---

## Phase 2: UI & Processing Resilience ✅

- [x] Background processing — `ThreadPoolExecutor`, `jobs` table, progress polling
- [x] Outlook COM hardening — retry logic, timeouts, COM cleanup
- [x] PDF text extraction — PyMuPDF primary, Tika fallback

---

## Phase 3: Core E-Discovery Features ✅

- [x] **Batch Actions UI** — multi-row select + bulk tag bar in `4_Review.py`
- [x] Production export — slip-sheeting, load files (.DAT / .OPT), Concordance delimiters

---

## Phase 4: Paralegal Workflow Wins ✅

- [x] **4.1 — CSV Export from Review Grid** — `st.download_button` + `df.to_csv()` *(Manager+ only)*
- [x] **4.2 — Privilege Log Generator** — query tagged `Privileged` docs → `.xlsx` export
- [x] **4.3 — Search Term Reports** — `6_STR.py` module; CSV term upload, OpenSearch batch, hit-count summary, per-term doc preview, Excel export
- [x] **4.4 — Matter Dashboard** — per-case stats (ingested, processed, produced, errors) on `home.py`
- [x] **4.5 — Deduplication Report** — `7_Dedup_Report.py`; MD5 clusters, near-dupe families, thread suppression breakdown, defensibility narrative

---

## Phase 5: Module — BYOS Local/Cloud Sync ✅

- [x] `6_Sync.py` — Filevine push/pull-back + BYOS Dropbox-style sync
- [x] `byos_pushed_at` column migration added to schema

---

## Phase 6: Advanced Search ✅ (Scoped)

- [x] Fuzzy (`~`) and wildcard (`*`) — native `query_string`
- [x] Pre-validation regex — prevents 400 errors
- [x] Syntax Tips popover on search bar
- [x] **DROP**: W/5 proximity (`span_near`) — deferred, out of scope

---

## Phase 7 (This Sprint): Quality of Life & Security ✅

### UI Enhancements
- [x] **Ingestor (`1_Ingestor.py`)** — case stats header, interactive folder preview, file type/size breakdown, two-column settings layout, step-by-step progress, post-scan results card
- [x] **Processor (`2_Processor.py`)** — pipeline phase cards, queue stats dashboard, dynamic colored status banners, improved retry/backfill UI
- [x] **Review (`4_Review.py`)** — dynamic column picker (Manager+), per-column SQL filter row, expanded EDRM field set

### Database
- [x] `page_count` (INTEGER) and `language` (TEXT) added to schema via migration
- [x] Tika extracts and populates both fields during processing
- [x] `saved_searches` table — per-user, per-case search history and named saves

### Search
- [x] **Saved Searches** — `📌 Saved Searches` named saves + `🕐 Recent` (10-deep auto-log), `💾 Save` widget inline
- [x] **Browser autocomplete suppressed** — CSS + MutationObserver JS across all inputs

### Role-Based Access Control (3-Tier) — *New architecture*
- [x] `auth_manager.py` rewritten — `admin (3) > manager (2) > reviewer (1)` numeric hierarchy
- [x] Convenience helpers: `is_admin()`, `is_manager()`, `is_reviewer()`
- [x] User CRUD: `create_user`, `delete_user`, `update_role`, `update_password`, `list_users`
- [x] Sidebar badges: 👑 Admin, 🏢 Manager, 📋 Reviewer
- [x] Page gates updated across all 9 modules *(see matrix below)*
- [x] User Management panel on `home.py` — Admin-only; create/change-role/reset-password/delete

### Review & Production
- [x] **Tag Category System** — Grouped UI layout; system tags (NearDupe, Thread, Junk) visually badged and protected from bulk overwrites
- [x] **Bulk Action Bar** — Multi-row append tags, clear tags, and CSV grid export
- [x] **Privilege Log Generator** — Integrated into Production module; dynamic queries from category definitions to Excel output
- [x] **Bates Batch Search** — Popover parser handles dirty interrogatory responses and extracts matching documents using mathematical range intersections
- [x] **Global Saved Searches** — Database schema updated with `is_global` column; UI supports team-wide shared searches
- [x] **Micro-PDF Extraction** — PyMuPDF (`fitz`) mathematically isolates Bates Batch hits into individual single-page PDFs packaged into a ZIP download

### Processing Stability Enhancements
- [x] Phase 1 `ThreadPoolExecutor` deadlock resolved by wrapping container logic in tight `try/except`
- [x] Phase 2 db_writer string queue drain deadlock resolved via thread-liveness checks and timeouts
- [x] Pipeline instantiation logic dedented into main execution thread

### Module Visibility Matrix (post-sprint — superseded by Phase 13 permission-based access)

> **Note:** This matrix reflects the original Phase 7 role-based gates. As of beta-2.7a (Phase 13), all gates have been migrated to named permissions via `has_permission()` / `require_permission()`. See the beta-2.7a section and `PERMISSION_SYSTEM_SPEC.md` for the current permission table.

| Module | Permission Gate | Notes |
|---|---|---|
| Home | *(any role)* | User Management gated to `user_admin`; Audit Log to `audit_view` |
| 1 Ingestor | `ingest` | |
| 2 Processor | `process` | |
| 3 Analytics | `analytics` | |
| 4 Review | `review` | Sub-features: `export_csv`, `column_picker`, `export_pdf`, `str_run`, `str_export`, `redact`, `saved_search_global`, `saved_search_personal`, `download_produced` |
| 5 Production | `production` | Tabs: `inbound_production`, `privilege_log` |
| 6 BYOS Sync | `sync` | |

### Elasticsearch → OpenSearch Migration
- [x] `es_manager.py` deleted, replaced by `os_manager.py`
- [x] All `elasticsearch-py` calls ported to `opensearch-py`
- [x] Index naming, bulk helpers, query DSL verified against OpenSearch 3.x

---

## Phase 10: Audit Trail *(Complete — v2.2)* ✅

- [x] `audit_log` schema migration — added `username`, `control_number`, `module`, `old_value`, `new_value` + 4 indexes
- [x] `log_audit()` and `log_audit_batch()` central functions in `db_manager.py` (never raises)
- [x] All modules wired: `home.py`, `1_Ingestor.py`, `2_Processor.py` (writer-thread-safe via queue), `3_Analytics.py` (batch), `4_Review.py` (incl. ✏️ Redact tab + 📊 STR view), `5_Production.py` (incl. 📥 Inbound + 📋 Privilege Log tabs), `6_Sync.py`
- [x] Admin-only audit log viewer on `home.py` — filter by user/module/action/control number/date, 2,000-row cap, CSV export
- [x] PST container extraction via Outlook COM (`explode_pst()` + `_walk_pst_folder()` in `container_exploder.py`)

---

## Currently Open — beta-2.3 Sprint *(Complete — v2.3)* ✅

```
1. [DONE]    Fix Processor TypeError — get_meta_str() crashes when Tika metadata value is a nested list
2. [DONE]    Mass PDF Export — pdf_exporter.py + bulk action bar in 4_Review.py (Manager+ only)
3. [DONE]    Redact tab UX overhaul — [3,7] control/canvas split, nav bar in control panel, canvas init checkbox
4. [DONE]    Centralize hardcoded paths — WKHTMLTOPDF_PATH, TESSERACT_PATH, FILEVINE_SUBDOMAIN → config.py
5. [DONE]    Move STR into Review AND fix duplicate 6_ prefix — STR merged as radio-gated view in 4_Review.py; 6_STR.py deleted
6. [DONE]    Consolidate Production pages — 8_InboundProd.py + 9_Privilege_Log.py merged as tabs into 5_Production.py; source files deleted
7. [DONE]    Consolidate Analytics pages — 7_Dedup_Report.py merged as tab into 3_Analytics.py; source file deleted
```

---

## Currently Open — beta-2.4 Sprint

```
1. [DONE]    PROJECT_CONTEXT.md overhaul — update repository structure, module breakdown, known issues to reflect v2.3 merges
2. [DONE]    Case Lifecycle Status — Active / On Hold / Closed gate; write-protection banner on closed matters; Manager+ to change
3. [DONE]    Bates Range Gap Detection — production validation expander in 5_Production.py; detects sequence discontinuities per volume; CSV report
4. [DONE]    Inbound Bates Cross-Reference Lookup — 🔎 Bates Lookup sidebar expander in 4_Review.py; prefix+numeric parse; Go-to-CN grid filter injection
5. [DONE]    bcrypt password hardening — replace SHA-256 in auth_manager.py; incremental migration (re-hash on successful login)
6. [DONE]    Phase 9 — External Annotation Reconciliation — parse PDF_ANNOT_REDACT from Filevine pull-back; fuzzy-match subject text to privilege categories; populate redaction_marks; reconciliation UI
```

### beta-2.4 Item Detail

#### Item 1 — PROJECT_CONTEXT.md Overhaul
Update the canonical project context document to reflect v2.3 reality:
- Repository structure: remove `6_STR.py`, `7_Dedup_Report.py`, `8_InboundProd.py`, `9_Privilege_Log.py`, `10_Redaction.py`; add `pdf_exporter.py`
- Module breakdown: update all cross-references to merged locations
- Known issues: close "duplicate 6_ prefix" (fixed); add canvas cursor crosshair issue (known, deferred)
- Planned work section: cross off all completed items

#### Item 2 — Case Lifecycle Status
**Goal:** Prevent accidental modification of concluded matters.
- New `case_settings` key: `case_status` — values: `Active` | `On Hold` | `Closed`
- `home.py`: Status selector widget (Manager+ only), displayed as colored badge in sidebar and Home dashboard
- All write-capable module pages (`1_Ingestor.py`, `2_Processor.py`, `3_Analytics.py`, `4_Review.py` tagging/redact/STR, `5_Production.py` outbound/inbound, `6_Sync.py`): check `case_status` at page load; if `Closed`, render `st.warning("🔒 This matter is closed. Write operations are disabled.")` and `st.stop()` before any write UI renders
- Read-only modules (Review grid/search/viewer, Analytics report tabs, Audit log) remain accessible when Closed
- Audit: log `CASE_SETTING_CHANGED` when status changes
- DB helper: `db_manager.get_case_status(case_folder)` → returns `'Active'` if unset (safe default)

#### Item 3 — Bates Range Gap Detection
**Goal:** Court-ready validation of production sequence integrity.
- Located in `5_Production.py` → Outbound Production tab, as a collapsible **🔍 Validate Production** expander below the main production UI
- Query: for each production volume, collect all `(begdoc, enddoc)` pairs with assigned Bates; sort numerically; detect gaps where one doc's `enddoc + 1 ≠ next doc's begdoc`
- Report: table showing Volume | Gap Start | Gap End | Gap Size | Adjacent Control Numbers
- Export: CSV download
- Edge cases: accounts for family-range gaps (BEGATT/ENDATT), prefix variations, non-numeric suffixes

#### Item 4 — Inbound Bates Cross-Reference Lookup
**Goal:** During deposition prep, instantly resolve "ABC-00012345" to an internal document.
- UI location: new **🔎 Bates Lookup** expander in the Review page sidebar (below the folder tree)
- Input: text field accepting one or more Bates numbers (one per line, or comma-separated)
- Logic: parse prefix + number; SQL query `WHERE begdoc <= input AND enddoc >= input` across all documents; returns control number, custodian, date, tags, production volume
- Result: clickable control numbers that jump the Review grid to that document (populate the search bar / set selection)
- Handles both internal productions and inbound opposing party Bates numbers

#### Item 5 — bcrypt Password Hardening
**Goal:** Upgrade from unsalted SHA-256 to bcrypt for deployment security headroom.
- Install `bcrypt` library (or use `passlib[bcrypt]`)
- `auth_manager.py` changes:
  - `hash_password(plain)` → `bcrypt.hashpw(plain.encode(), bcrypt.gensalt())`
  - `check_login()` detects old format (SHA-256 = 64 hex chars, no `$2b$` prefix) vs new; if old, verifies SHA-256 then immediately re-hashes to bcrypt and writes back — zero-downtime migration
  - New password resets always use bcrypt
- No schema changes; hashes stored the same way in auth_config.yaml

#### Item 6 — Phase 9 External Annotation Reconciliation
**Goal:** When a PDF comes back from Filevine with externally-drawn redaction annotations (Adobe/PowerPDF), automatically extract those annotations, fuzzy-match the annotation subject/label to privilege categories, and populate `redaction_marks` so the platform treats them as native marks.
- **Trigger:** `6_Sync.py` pull-back flow and Inbound Production load (BYOS import with pre-annotated PDFs)
- **Extraction:** `fitz.Page.annots()` → filter `type == PDF_ANNOT_REDACT` → read `info["subject"]` or `info["content"]` for the privilege label text
- **Fuzzy matching:** `_pl_fuzzy_match_privilege_reason()` from the Privilege Log tab — reuse the `_PL_ABBREV_MAP` already present in `5_Production.py`. Move map + function to `db_manager.py` so it's importable everywhere. Fallback: `"Redaction: {raw_text}"` (orphan, flagged for review)
- **Population:** Write extracted marks + matched reasons to `redaction_marks` table; update `redaction_status = 'Has_Redactions'`; call `_sync_document_tags()` to apply matched privilege tags
- **Reconciliation UI:** New expander in `6_Sync.py` pull-back section — "📋 Annotation Reconciliation" — shows table of: control number | page | raw annotation text | matched reason | confidence (exact/fuzzy/orphan) | override dropdown
- **Export:** "Export Coding Sheet" → Excel with the reconciliation table, suitable for attorney sign-off before burning

---

## ❌ Dropped from Scope

### ~~TAR / Active Learning (Machine Learning)~~
**Decision: OUT OF SCOPE — Do not implement.**
- CAL requires court validation protocols; half-implemented = liability
- Target firms (500–10k docs/matter) don't benefit vs. linear review
- Near-dupe + thread suppression already delivers the population reduction benefit

---

## ⚖️ Licensing Notes (Commercial Distribution)

| Dependency | License | Status |
|---|---|---|
| `streamlit` | Apache 2.0 | ✅ Safe |
| `opensearch-py` | Apache 2.0 | ✅ Safe |
| `OpenSearch` (server) | Apache 2.0 | ✅ Safe |
| `PyMuPDF` (fitz) | AGPL v3 | ⚠️ Requires Artifex commercial license for proprietary distribution |
| `pdfkit` / `wkhtmltopdf` | LGPL | 🟡 OK with dynamic linking acknowledgement |
| `libpff-python` (pypff) | LGPL v3 | 🟡 OK as dynamically imported library; requires attribution + LGPL text inclusion |
| `openpyxl` | MIT | ✅ Safe |

**PyMuPDF Decision**: Deploy via firm-owned server (not SaaS) reduces scope of AGPL exposure, but commercial licensing should be obtained at commercialization. Treat as COGS.

---

## Phase 8: Native In-App Redaction Viewer *(Complete — v2.3)* ✅

> **Goal:** Draw redaction boxes directly in the browser. Uses `streamlit-drawable-canvas` + PyMuPDF annotations. Privilege reason picker = existing tag category system. Burn step unchanged.

### Implementation Steps
- [x] Page renderer — `fitz.Page.get_pixmap()` at ~105 DPI (target 1000px canvas width) → PNG → PIL Image → `st_canvas` background
- [x] Drawable canvas overlay (`streamlit-drawable-canvas`)
- [x] Coordinate math — canvas px → PDF pt
- [x] Multi-page nav — ◀ / text_input / N / ▶ bar in control panel; per-document page state in session state
- [x] Reason picker from tag category system (`is_privilege` categories)
- [x] Save marks — `PDF_ANNOT_REDACT` via PyMuPDF (non-destructive; `apply_redactions()` only at production burn)
- [x] View existing marks on load
- [x] Clear/undo (per-page and all-pages)
- [x] **Merged into Review module** — `10_Redaction.py` deleted; redaction is now the "✏️ Redact" tab inside `4_Review.py` (reviewer role gate — attorneys mark their own redactions without losing grid position)
- [x] **Layout refactor** — two-column `[3, 7]` split: control panel (nav, tool selector, per-box reasons, save/clear buttons) left of canvas; summary table full-width below. Eliminates need to scroll past canvas to reach controls.
- [x] **Canvas init workaround** — `🖊️ Load Redaction Canvas` per-document checkbox (key has no page index, persists across navigation). Required because `st_canvas` React component does not display `background_image` on first mount without a user-triggered rerun.

---

## Phase 9: External Annotation Import & Reconciliation *(After Phase 8)* ✅ COMPLETE

> **Goal:** Parse redaction annotations from externally-marked PDFs (Adobe, PowerPDF) → fuzzy match to tag categories → reconciliation report.

| Reviewer types | System maps to |
|---|---|
| `AC`, `attorney client`, `AC Priv` | `Attorney-Client Privilege` |
| `WP`, `work prod` | `Work Product` |
| `CI`, `common interest` | `Common Interest Privilege` |
| *anything else* | `Redaction: [raw text]` (orphan, flagged) |

### Implementation Steps
- [x] `abbreviation_map` dictionary in `db_manager.py`
- [x] `fuzzy_match_privilege_reason()` helper
- [x] Hook into Filevine pull-back and BYOS import
- [x] Reconciliation UI + export redaction coding sheet

---

## Phase 11: Near-term *(Complete — v2.5)* ✅

- [x] **Canvas Patch Preservation** — `_scratchpad/post_install_patch.py` re-applies the `streamlit-drawable-canvas` patch automatically after venv rebuild. README note in `PROJECT_CONTEXT.md`.
- [x] **Setup Validation Script** — `setup_check.py` verifies Tika, OpenSearch, wkhtmltopdf, Tesseract, Outlook COM, and cases root accessibility. Pass/fail table with exit codes and quick-fix hints.
- [x] **Native File Production** — "Native Only" added as third production format in `5_Production.py`. Skips imaging; Bates-names natives, generates slip sheets, pulls text from SQLite `extracted_text`.
- [x] **Family Group Visualization** — "👪 Family View" toggle (Manager+) in `4_Review.py`. Renders root documents as collapsible expanders containing attachment sub-tables. Standalone docs in a flat section below.

---

## Currently Open — beta-2.6 Sprint *(Complete — v2.6)* ✅

```
1. [DONE]    Automated Test Suite — minimum viable pytest; ingest 5-10 files, process, assert controls/text/Bates
2. [DONE]    Clawback / Inadvertent Disclosure Workflow — mark doc, log demand date, suppress from future productions, generate clawback letter
3. [DONE]    Supplemental Production — "Volume II" logic; track previously produced docs and next Bates number for continuity
4. [DONE]    PST via libpff — pure-Python fallback for PST extraction on machines without Outlook
```

### beta-2.6 Item Detail

#### Item 1 — Automated Test Suite
**Goal:** A minimum-viable regression harness that can run headlessly (CI-friendly) to catch regressions before each release.
- New `tests/` directory at repo root
- `conftest.py` — pytest fixtures: temp case folder, seeded `case.db`, mock OpenSearch (or real local instance)
- `test_ingest.py` — copy 5–10 sample files into a temp ingest folder; call `container_exploder` and `db_manager.init_db`; assert rows created in `documents` table
- `test_process.py` — call Tika/PyMuPDF extraction path directly; assert `extracted_text` and `page_count` populated
- `test_bates.py` — call production Bates-math logic; assert `begdoc`/`enddoc` assigned correctly and sequence is continuous
- `test_auth.py` — bcrypt round-trip; role hierarchy comparisons
- Sample files: 1 PDF, 1 DOCX, 1 XLSX, 1 EML, 1 MSG — stored in `tests/fixtures/`

#### Item 2 — Clawback / Inadvertent Disclosure Workflow
**Goal:** After a production goes out, if an attorney realises a privileged document was included, the platform must track the clawback demand and prevent the document from appearing in future productions.
- New `documents` column: `clawback_status TEXT` — values: `NULL` (normal) | `Clawback_Demanded` | `Clawback_Resolved`
- New `documents` column: `clawback_date TEXT` — ISO date of demand letter
- `db_manager.py`: `mark_clawback(case_folder, control_number, demand_date)` helper
- `4_Review.py` — new **⚠️ Clawback** button in the document viewer action bar (Manager+); opens a mini-form: demand date, notes, confirm; sets status + audits
- `5_Production.py` — add `clawback_status != 'Clawback_Demanded'` filter to all production queries (hard block)
- `3_Analytics.py` — Clawback summary card on the dashboard: count of clawback-demanded docs, list with demand dates
- Letter generation: plain-text template rendered via `st.text_area` for copy/paste (no PDF generation required)
- Audit: `CLAWBACK_MARKED` event with `control_number`, `demand_date`, `notes`

#### Item 3 — Supplemental Production
**Goal:** "Volume II" continuity — the platform must remember where the last production left off and auto-initialise the next starting Bates number.
- New `case_settings` key: `last_bates_prefix` and `last_bates_end_num` — written at the end of every successful production run
- `5_Production.py` Configure Production section:
  - New **🔗 Continue from Last Production** toggle (default on when a prior production exists)
  - When on: auto-populates `prefix` from `last_bates_prefix` and `start_num` from `last_bates_end_num + 1`
  - Shows last production name and ending Bates number as a caption below the toggle
- Also respects manual override (toggle off → user enters arbitrary prefix/start)
- Safe default: if no prior production exists, behaves exactly as today

#### Item 4 — PST via libpff
**Goal:** Allow PST ingestion on machines without Microsoft Outlook installed (Linux, headless CI, attorney laptops without Office).
- Add `libpff-python` to `requirements.txt` (pip package: `libpff-python`)
- `container_exploder.py`: new `explode_pst_libpff(pst_path, output_dir)` function
  - Opens PST with `pypff.file()`; walks `root_folder` recursively
  - For each message: extract subject, sender, recipients, body (HTML preference, plain fallback), attachments
  - Write `.eml` or `.msg`-ish temp files to `output_dir` for downstream processing
- Detection logic: `explode_pst()` tries Outlook COM first (Windows + Outlook present); falls back to `explode_pst_libpff()` on `ImportError` or `COMError`
- Graceful degradation: if neither is available, surface a clear `st.error` in the Ingestor

---

### Deployment Script (Deploy-Platform.ps1) — Known Issues from Fresh-Machine Test
- [x] wkhtmltopdf winget package ID not found on fresh Windows 11 — needs manual install or updated package ID
- [x] config.py generation runs before branch checkout — if cloning defaults to main, config gets created then deleted on checkout to beta branch. Move config generation to after branch selection.
- [x] Script should prompt for which branch to checkout after cloning (default to beta-2.7 or latest release)
- [x] Set-ExecutionPolicy RemoteSigned should be documented as a prerequisite or handled by the script
- [x] CLAUDE_CODE_GIT_BASH_PATH environment variable may need to be set for Claude Code on fresh installs — add to DEPLOYMENT_GUIDE.md
- [x] Consider adding a --branch flag to the deployment script configuration block

---

## Immediate Fixes Sprint — Pre-Demo Blockers (Next Up)

> **Source:** `Claude_Code_Immediate_Fixes_Prompt.md` — run this prompt to execute the sprint.

**Priority:** Run before any firm demo; these are crash-level bugs.
**Branch:** `beta-2.6` (fixes apply in-place; no new feature branch needed)

```
Task 0  [x]  CLAUDE.md + SKILL.md: inline version tracking rules, update timestamp format to YYYY-MM-DD HH:MM, mass-update all existing headers
Task 1  [x]  5_Production.py: fix extracted_text crash in Native Only production — pull from OpenSearch with PyMuPDF fallback
Task 2  [x]  requirements.txt: add bcrypt and openpyxl (used throughout, never listed)
Task 3  [x]  db_manager.py: fix corrupt \x08 bytes in fuzzy_match_privilege_reason() regex — restore \b word boundaries
Task 4  [x]  db_manager.py: remove duplicate get_case_status() / set_case_status() definitions (keep validated versions)
Task 5  [x]  ROADMAP_TODO.md: mark Phase 9 (External Annotation Reconciliation) as complete
Task 6  [x]  Version bump all files to 2.6.0 (config.py __version__ + all project_ver headers + CHANGELOG header + Technical_Overview.md)
```

---

## Currently Open — beta-2.7 Sprint

**Branch:** `beta-2.7`
**Structure:** Two sequential sub-phases with a clean commit checkpoint between them.
**Prerequisite:** beta-2.6 complete and stable ✅

---

### beta-2.7a — Phase 13: Permission-Based Access Control 🔐

> **Spec:** `PERMISSION_SYSTEM_SPEC.md`
> **Commit checkpoint required before starting 2.7b.**

```
1. [DONE]    auth_manager.py — add has_permission(), require_permission(), _get_role_permissions() with hardcoded defaults fallback
2. [DONE]    auth_config.yaml — add role_permissions section (zero-downtime; falls back to hardcoded defaults if absent)
3. [DONE]    Gate migration — replace all require_role()/is_admin()/is_manager()/is_reviewer() calls across all modules (see mapping table in spec)
4. [DONE]    home.py — Role Permission Editor UI (checkbox grid + custom role management + audit ROLE_PERMISSIONS_CHANGED)
5. [DONE]    auth_manager.py — remove deprecated helpers: is_admin(), is_manager(), is_reviewer(), require_role()
6. [DONE]    Regression — 69/69 tests passed
7. [ ]       Test — create custom role, assign user, verify access matches permission set (manual, post-commit)
```

---

### beta-2.7b — Phase 14: Expert Reviewer Role & Remote Access 🔬

> **Spec:** `EXPERT_REVIEWER_SPEC.md`
> **Requires beta-2.7a committed and passing regression.**

```
8.  [DONE]   auth_manager.py + auth_config.yaml — add saved_search_personal and download_produced permissions to defaults and all three default roles
9.  [DONE]   auth_config.yaml — add expert custom role (no inherits; explicit minimal set: review, str_run, saved_search_personal, download_produced)
10. [DONE]   4_Review.py — gate saved search save/load behind saved_search_personal
11. [DONE]   4_Review.py — implement _offer_produced_download() and gate behind download_produced
12. [DONE]   db_manager.py — add PRODUCED_DOWNLOAD audit event to log_audit vocabulary
13. [DONE]   home.py — add 🔬 Expert sidebar badge; generic fallback badge for unknown custom roles
14. [DONE]   DEPLOYMENT_GUIDE.md — Tailscale remote access setup instructions
15. [ ]      Full regression: expert login → browse/search/STR → save search → download produced → verify audit trail
```

---

### beta-2.7c — Regression Fixes (2026-03-17)

> **Source:** Manual regression test findings from beta-2.7 acceptance testing.

**Critical — permission gates:**
```
16. [DONE]   4_Review.py — gate STR tab behind has_permission('str_run'); radio option hidden when user lacks permission
17. [DONE]   4_Review.py — STR Summary CSV implicitly gated (tab is hidden without str_run; CSV is inside the tab)
18. [DONE]   4_Review.py — STR results respect doc_visibility; produced_only users only see hits for produced docs in both counts and detail table
```

**High — expert download scoping:**
```
19. [DONE]   4_Review.py — PDF ZIP export already hides Native/Processed radio when user lacks export_pdf; forces Produced (Bates-stamped) source (verified lines 1713-1723)
20. [DONE]   4_Review.py — PDF ZIP single-select: falls back to currently-viewed document when bulk_selected_cns is empty and one grid row is selected
21. [DONE]   4_Review.py — PDF ZIP already filters to produced-only docs when user has download_produced but not export_pdf; shows count/warning for unproduced selections (verified lines 1730-1760)
```

**High — Family View:**
```
22. [DONE]   4_Review.py — tag filter cascade: children of filtered-out parents (hide Not Responsive / hide Junk Image) are also hidden from grid
23. [DONE]   4_Review.py — Family View: PST/ZIP container parents (Container_Scanned) excluded from family grouping; PST-sourced emails now form their own email→attachment families
24. [DONE]   4_Review.py — ghost-parent groups render sub-family nesting (email→attachment hierarchy) instead of flat table
```

**Tag cascade to children (⚠️ COMPLIANCE REVIEW NEEDED):**
```
30. [DONE]   4_Review.py — _cascade_tag_to_children() helper: applying, removing, or clearing document-level tags on a parent cascades to attachment children. System tags preserved. Redaction marks unaffected.
    ⚠️ PM Claude must review against eDiscovery protocol:
      - Does any jurisdiction require attachment-level tag independence?
      - Should cascade be opt-in (checkbox) rather than automatic?
      - Should cascade be logged differently for defensibility?
      - What happens when a child has been independently reviewed and tagged by a different reviewer?
```

**Medium — processor re-run behavior:**
```
25. [DONE]   2_Processor.py — NOT a bug: Phase 1 only processes 'New' docs; Phase 2 processes 'Container_Scanned' + 'Ready_For_Processing'. Leftover docs from incomplete prior runs are legitimate queue items. Added new/resumed breakdown and info banner for clarity.
```

**Medium — UX improvements:**
```
26. [DONE]   4_Review.py — saved search Load button icon changed from ↩ to 📂
27. [DONE]   2_Processor.py — cancel button for Phase 2; cancels pending futures, drains in-flight, logs PROCESSING_CANCELLED. Phase 3 (imaging) and Phase 1 do not yet have cancel support.
28. [DONE]   pdf_exporter.py — native export: falls back to processed PDF, converts images via PyMuPDF, or includes native with real extension + error note
```

**Config — permission adjustments:**
```
29. [DONE]   auth_config.yaml — add saved_search_global to reviewer role (user decision: reviewers should be able to share searches with the team)
```

**Not a bug — audit log (verified):**
```
Audit logging IS working correctly for all users. Expert actions are written to the case-specific DB (case.db). To see them, admin must select the same case in the Audit Log Viewer. Consider adding a case indicator label to the Audit Log Viewer header for clarity.
```

---

### beta-2.7d — MSG Address Fix, CID Leak Fix, Metadata Key Fix (2026-03-18)

> **Source:** Verification script output (metadata enrichment coverage) + manual regression testing.

**Critical — email metadata accuracy:**
```
31. [DONE]   universal_imager.py — MSG imaging and metadata paths now build full "Name <email>" sender from PR_SENDER_NAME (0C1A) + PR_SENDER_EMAIL_ADDRESS (0C1F) instead of using name-only field
32. [DONE]   universal_imager.py — MSG To/CC/BCC now parsed from transport headers (stream 007D) for full SMTP addresses; falls back to display-name-only properties (0E04/0E03/0E02) if headers unavailable
33. [DONE]   container_exploder.py — generate synthetic Content-ID for inline-flagged MSG attachments (PR_ATTACH_FLAGS bit 2 / ATT_MHTML_REF) that lack PR_ATTACH_CONTENT_ID, preventing CID signature images from leaking through as child documents
34. [DONE]   2_Processor.py — fix message_id key mismatch: native email extractors return 'message_id' key but override loop looked for 'msg_id', so message_id was never written to DB (0% coverage across all emails)
```

**Documentation updates:**
```
35. [DONE]   User_Guide.md — updated from v2.3 to v2.7 (permission-based access, custom roles, expert role, document visibility, libpff fallback, container lifecycle, cancel button, family view, tag cascade, Native Only production, supplemental production, clawback workflow, dedup report renumbering)
36. [DONE]   Technical Overview.md — updated from Beta 2.5 to Beta 2.7 (full rewrite of auth section, database schema enrichment columns, container lifecycle, metadata enrichment pipeline, new analytics tabs, production formats, dependency API references)
37. [DONE]   PROJECT_CONTEXT.md — updated from v2.6 to v2.7 (permission-based RBAC, metadata enrichment, new analytics tabs, cancel buttons, tag cascade, family view, Native Only production, container skip, synthetic CID, long-path handling)
38. [DONE]   Walkthrough.md — updated from Beta 2.6 to Beta 2.7 (permission-based access, expert role, communication analytics suite, tag cascade, Native Only production, supplemental production, clawback protection, cancel buttons, inline signature filtering, full email address resolution)
39. [DONE]   ROADMAP_TODO.md — add beta-2.7d items, update module visibility matrix (this task)
40. [DONE]   DEPLOYMENT_GUIDE.md — bump version header from 2.6 to 2.7
41. [DONE]   THIRD_PARTY_LICENSES.md — bump version header from 2.6 to 2.7; added libpff-python (pypff) entry
```

### beta-2.7e — Family Peek Navigation + Show Full Family (2026-03-18)

> **Source:** Real-world review workflow gap — clicking family links failed when target was filtered out.

**New features:**
```
42. [DONE]   4_Review.py — Peek Navigation: family links for filtered-out targets load document directly in viewer with "← Back to queue" return; chained peeks preserve original return index
43. [DONE]   4_Review.py — Show Full Family: button replaces grid with all documents in family group, bypassing search/column/display filters; "← Back to search results" restores prior state
```

**Bug fixes (stacking bugs in Show Full Family):**
```
44. [DONE]   4_Review.py — family override query: added OR control_number=? to capture parent whose group_id was NULL
45. [DONE]   4_Review.py — "← Back to search results" banner moved outside empty-results guard so users are never trapped
46. [DONE]   4_Review.py — hide_junk, hide_not_responsive, and cascade filters bypassed in family override mode
47. [DONE]   2_Processor.py — main UPDATE now writes group_id back to DB (was computed in memory but never persisted for parents)
48. [DONE]   db_manager.py — one-time migration fills NULL group_id with control_number for all existing documents
49. [DONE]   4_Review.py — fix StreamlitAPIException on "← Back to search results": deferred widget-key restore via _pending_search_restore pattern
```

**Documentation updates:**
```
50. [DONE]   Technical Overview.md, PROJECT_CONTEXT.md, User_Guide.md, Walkthrough.md, ROADMAP_TODO.md — added Peek Navigation and Show Full Family documentation
```

**Manual verification tests (user-side, completed):**
```
V1. [PASS]  Factory reset + reprocess: libpff record sets — real filenames, no HTML fragments, correct PDF headers
V2. [PASS]  Factory reset + reprocess: MSG sender/recipient full SMTP addresses in both PDF headers and DB fields
V3. [KNOWN] Factory reset + reprocess: CID inline image leak prevention — known EML limitation, no current fix; minor annoyance, revisit in future sprint
V4. [PASS]  Queue clearing / container lifecycle — Container_Scanned docs stay out of Phase 2 queue
V5. [PASS]  Long-path prefix elimination — no \\?\ prefixes in full_path column (0 matches confirmed)
V6. [PASS]  HTML escaping in email PDFs — angle brackets in addresses render correctly
V7. [PASS]  message_id population after reprocess — 66 emails at 13.4% coverage (confirmed populated)
```

---

## Phase 13: Permission-Based Access Control *(Complete — see beta-2.7a above)* ✅

> **Spec:** See `PERMISSION_SYSTEM_SPEC.md` for full architecture, permission table, YAML schema, admin UI mockup, and migration path.

---

## Phase 14: Expert Reviewer Role & Remote Access *(Complete — see beta-2.7b above; regression fixes in 2.7c)* ✅

> **Spec:** See `EXPERT_REVIEWER_SPEC.md` for full architecture, permission definitions, produced document download interface, remote access strategy, and testing checklist.

---

## Phase 15: Dependency Vendoring & Offline Install 📦

**Priority:** Required before first client deployment
**Estimated effort:** Half-day task
**Prerequisite:** Stable post-2.7 release

> **Early bootstrap (2026-03-14):** `vendor/wheels/` has been created and committed with
> `libpff_python-20231205-cp311-cp311-win_amd64.whl` — the PST extraction library that
> requires C++ Build Tools to compile from source. This resolves the most common blocker
> on client machines. Full vendoring of all remaining dependencies is still Phase 15 scope.

```
1. [x]   Create vendor/wheels/ directory at repo root
1a.[x]   Add libpff_python-20231205-cp311-cp311-win_amd64.whl (bootstrapped early — no C++ build tools required on client machines)
2. [ ]   Run pip download -r requirements.txt -d vendor/wheels/ from a known-good venv and commit all .whl files
3. [ ]   Create vendor/installers/ directory with versioned copies of:
             Tika server .jar, OpenSearch distribution ZIP,
             wkhtmltopdf installer, Tesseract installer, Java 21 Temurin installer
4. [ ]   Add install-offline.ps1 script (or flag in Deploy-Platform.ps1) that installs from vendor/ instead of downloading from the internet
5. [ ]   Verify full offline install on a clean Windows machine with no internet access
6. [ ]   Add "Vendored Dependencies" section to THIRD_PARTY_LICENSES.md noting local copies are kept for business continuity with original license files preserved alongside each wheel
7. [ ]   Add .gitattributes entry to treat vendor/ as binary/LFS if repo size becomes a concern
```

---

## Phase 16: Metadata Enrichment — "Capture Everything" ✅

**Priority:** High — must run before any case that will go to production; metadata omitted here cannot be recovered without full reprocessing
**Sprint prompt:** `Metadata_Enrichment_Sprint_Prompt.md`

> **Philosophy:** Capture everything the source data provides and write it to the database, whether or not we display it today. What gets shown in review or included in productions is a downstream, per-case decision.

```
Task 1  [DONE]   db_manager.py — add 13 new columns to documents table + complete migration list audit
Task 2  [DONE]   universal_imager.py — refactor extract_msg_text() to return (text, metadata_dict); OLE extraction for CC/BCC/received date/importance/sensitivity/conversation topic/index; CC/BCC in PDF headers
Task 3  [DONE]   2_Processor.py — handle new return signature; fix In-Reply-To/References; Tika metadata mappings; merge native OLE over Tika; tika_metadata_json; expanded UPDATE SQL
Task 4  [DONE]   2_Processor.py — enrich OpenSearch document payload with full metadata fields
Task 5  [DONE]   universal_imager.py — add extract_eml_metadata() for EML files parallel to MSG path
Task 6  [DONE]   _scratchpad/verify_metadata_enrichment.py — verification script
```

---

## Phase 17: Two-Pass Production Architecture 🏭

**Priority:** HIGH — resolves imaging retry, defensible Bates continuity, QC checkpoint, and parallel performance in one refactor
**Estimated effort:** 3–4 sessions (4 sprints as specified)
**Prerequisite:** Phase 14 (Expert Reviewer) complete; `5_Production.py` stable at v1.2.0+
**Sprint spec:** `TWO_PASS_PRODUCTION_SPEC.md` — feed this file to Claude Code to execute the sprints in order; the spec defines all 4 sprints, session state schema, worker function, and Windows-specific gotchas
**Files affected:** `5_Production.py` (major refactor), `universal_imager.py` (minor — add `image_document_safe()` wrapper)

> **Why this matters:** The current single-pass loop assigns Bates numbers during imaging, making retry impossible without gaps or collisions. Two-pass separates "expensive format conversion" (parallelizable, no legal ordering requirement) from "legally significant assembly" (sequential: Bates assignment, burns, stamps). The retry window creates an auditable QC checkpoint — the user reviewed imaging results and affirmatively finalized. Opposing counsel can challenge Bates gaps; they cannot challenge a documented QC review.

> **Note:** Sprint 1 (imaging summary table) was already implemented as a standalone improvement (`Production_Imaging_Summary_Prompt.md`, 2026-03-15). The two-pass architecture builds on that foundation.

```
Sprint 1  [x]   5_Production.py — imaging_failures[] accumulator + 📋 Imaging Summary table after QC (DONE 2026-03-15)
Sprint 2  [x]   universal_imager.py — add image_document_safe() picklable wrapper
          [x]   5_Production.py — extract Pass 1 (pre-imaging) and Pass 2 (assembly) as separate code paths
          [x]   Store Pass 1 results in st.session_state['prod_pass1']
          [x]   Add Retry / Finalize / Abort buttons with st.data_editor retry exclusion checkboxes
          [x]   Wire retry logic (re-run imaging on non-excluded failures, update session state)
          [x]   Wire Pass 2 (Finalize) — relocate existing assembly code, not rewrite
          [x]   Add PRODUCTION_PASS1_COMPLETE, PRODUCTION_RETRY, PRODUCTION_ABORTED audit events
Sprint 3  [x]   Replace sequential Pass 1 loop with ProcessPoolExecutor (max_workers = min(6, cpu_count//2))
          [x]   Update progress reporting to use as_completed() pattern
          [x]   Test on production-scale document set; monitor memory + COM subprocess count
          [x]   Optionally expose max_workers as config.py setting
Sprint 4  [x]   Stale-production detector (orphaned temp files from abandoned Pass 1)
          [x]   Timing metrics (Pass 1 / retry / Pass 2 durations) in audit log
          [x]   Update DEPLOYMENT_GUIDE.md and User_Guide.md with new workflow
```

---

## Phase 18: Privilege Disposition System ⚖️

**Priority:** HIGH — Defensibility-critical
**Completed:** 2026-03-18
**Spec:** `PRIVILEGE_DISPOSITION_PLAN.md`
**Files affected:** `db_manager.py`, `4_Review.py`, `5_Production.py`, `universal_imager.py`

```
Part 1  [x]   Container exclusion fix — PST/ZIP/RAR/7Z routed correctly (already done)
Part 2  [x]   privilege_status column (NULL/Redact/Withhold) + get/set helpers in db_manager.py
Part 3  [x]   Review UI — Privilege Disposition selector in coding panel; _r_sync_tags() auto-sets Redact, never overwrites Withhold
Part 4  [x]   generate_privilege_placeholder() in universal_imager.py — branded "DOCUMENT WITHHELD" slip sheets
Part 5  [x]   Production pipeline — two-pass adaptation: Withhold docs skip imaging → placeholder in Pass 2; Redact docs burned normally; pre-production safety gate (hard block for Redact without marks, soft warn for no disposition)
Part 6  [x]   QC checks redesigned: Rogue Marks, Missing Marks, Withheld count, Privilege Log Completeness
Part 7  [x]   Privilege Log tab — Disposition column, flags "Needs disposition review"
```

---

## Phase 19: Source Collections & Folder Organization 📂

**Priority:** MEDIUM — Organizational metadata for structured ingestion
**Completed:** 2026-03-18
**Files affected:** `db_manager.py`, `1_Ingestor.py`, `4_Review.py`, `2_Processor.py`

```
Task 1  [x]   Schema — source_collection and source_subcollection columns + backfill migration from original_path
Task 2  [x]   Ingestor — structured ingestion mode toggle with folder tree preview; flat mode default preserved
Task 3  [x]   Document Navigator — tree expanded to custodian → collection → subcollection for internal docs
Task 4  [x]   Review grid — Collection and Subcollection added as selectable/filterable columns
Task 5  [x]   OpenSearch — source_collection and source_subcollection in indexed document payload
Task 6  [x]   CHANGELOG and ROADMAP updated
```

---

## Phase 21: Demo Readiness ✅

**Priority:** CRITICAL — Features needed to demonstrate the platform as a complete review management system.

### Tier 1 — Core Demo Features ✅
- [x] **Defensibility Report Generator** — One-click, 9-section court-ready PDF (case overview, ingestion, processing, dedup, review, production, privilege, audit, legal holds)
- [x] **Dashboard & Analytics Plotly Upgrade** — Interactive charts: pipeline funnel, review decision donut, dedup waterfall, communicator bars, heatmap, timeline with gap annotations, domain pie/bar
- [x] **Audit Trail Export Upgrade** — Three-format export (CSV, Excel with metadata sheet, PDF with landscape layout and filter criteria)

### Tier 2 — Workflow Features ✅
- [x] **Custodian Management (Module 7)** — Custodian registry, profile editing, rename/merge/reassign/collections with audit trail
- [x] **Legal Hold Tracking** — Hold lifecycle (issuance, acknowledgment, release), hold document upload, case hold summary with Gantt timeline
- [x] **Review Batching** — Family-aware LPT auto-split, reviewer assignment, batch filter, "Reviewed — Next" workflow, progress tracking

### Infrastructure Fixes ✅
- [x] **OpenSearch Payload Fix** — Renamed `filename`→`file_name`, `subject`→`email_subject`; added `source_party`, `production_volume` to index
- [x] **Search Index Reindex Utility** — `os_manager.reindex_from_sqlite()` + Admin UI in Sync module
- [x] **CLI Intelligence Hardening** — `DEPENDENCY_MAP.md` + 3 standing orders (Pre-Fix Investigation, Impact Audit, Dep Map Maintenance)
- [x] **Dedup Hardening** — Pre-seed MD5/content-hash from prior runs; content-hash dedup layer
- [x] **Deferred Parallel OCR** — Production OCR post-pass with ThreadPoolExecutor
- [x] **Production Mode Toggle** — Simple vs Full EDRM selector
- [x] **Closed-Case Read-Only** — Review/Analytics load read-only on closed cases instead of blank page

---

## Phase 20: Module Hardening — Non-Page Module Technical Debt 🔧

**Priority:** MEDIUM — Safe incremental improvements that reduce debugging time and prevent "fix it twice" bugs
**Prerequisite:** None — each sprint is independent
**Modules affected:** `universal_imager.py`, `container_exploder.py`, `pdf_exporter.py`, `email_imager.py`

> **Background:** A comprehensive read-only audit of the non-page modules identified five systemic patterns: massive code duplication between MSG functions, 25+ silent `except: pass` blocks, functions exceeding 300 lines with 4-6 mixed concerns, scattered magic numbers, and residual resource cleanup gaps. This phase addresses them in risk-ordered sprints.

**Sprint 1 — Safe Hardening (no behavior changes): ✅ COMPLETE (2026-03-24)**
```
1. [x]   universal_imager.py — Extracted 9 shared OLE helpers to module-level
2. [x]   All four modules — Added logging to 25+ bare except:pass blocks
3. [x]   All four modules — Named constants replacing magic numbers
```

**Sprint 2 — Shared Rendering Pipeline: ✅ COMPLETE (2026-03-26)**
```
4. [x]   universal_imager.py — Extract shared HTML email template builder (_build_email_html)
5. [x]   universal_imager.py — Extract shared fitz.Story page-loop renderer (_render_fitz_story), wkhtmltopdf runner (_run_wkhtmltopdf), CID substitution (_substitute_cid_images)
6. [x]   universal_imager.py — Extract shared inline image processing (_append_inline_images_to_pdf, _wrap_plain_text_as_html). EML 284→126 lines, MSG 333→215 lines, net -110 lines.
```

**Sprint 3 — Function Decomposition (higher risk — requires full regression testing):**
```
7. [x]   universal_imager.py — Decompose convert_msg_to_pdf() (~350 lines) into: OLE parsing, body extraction, template rendering, PDF generation
8. [x]   universal_imager.py — Decompose extract_msg_text() (~285 lines) into: OLE parsing, body extraction, metadata collection
9. [x]   universal_imager.py — Decompose flatten_pdf() (~245 lines) into: annotation scrubbing, form flattening, normalization
10. [x]  container_exploder.py — Decompose _libpff_message_to_eml() (~216 lines) into: header construction, body extraction, attachment processing
```

**Sprint 4 — Resource Cleanup + Remaining Gaps:**
```
11. [x]  container_exploder.py — COM object cleanup: replace bare `del msg` with explicit .Close() calls; add try/finally around all COM loops
12. [x]  universal_imager.py — Inline image stream leak: wrap fitz.open(stream=img_bytes) in try/finally inside image processing loops
13. [x]  pdf_exporter.py — DB connection cleanup: add try/finally around db_manager.get_connection() usage
```

---

## Phase 22: Defensibility Essentials + Review Workflow ✅

**Priority:** HIGH — Closes most visible gaps before firm demo.
```
1. [x]   Case/Matter Metadata Profile — matter_profile in case_settings, home.py card, defensibility report
2. [x]   Processing Exception Report — 3-sheet Excel export from Processor page
3. [x]   Production History Table — production_runs table, recorded at finalization, dashboard + defensibility report
4. [x]   Date Range Filter in Review Grid — COALESCE(date_sent, date_created) WHERE injection
5. [x]   TextLink in DAT Load File — added to both prod_data blocks + column consistency fix
6. [x]   Document-Level Reviewer Notes — document_notes table, notes expander, manager visibility
7. [x]   Per-Document Confidentiality Designations — column, coding panel, per-doc endorsement override in production
```

---

## Phase 23: Production UX Overhaul ✅

**Completed:** 2026-03-26

```
1. [x]   Post-finalization state — compact summary (Bates range, doc/privilege/redaction/error counts) + expandable QC report
2. [x]   Download ZIP (opposing counsel) — on-demand ZIP of IMAGES/ + NATIVES/ + TEXT/ + DAT + OPT only
3. [x]   Download Full Package (internal) — on-demand ZIP of entire production folder
4. [x]   Separate internal downloads — individual CSV download buttons for privilege log, QC report, redaction log, imaging errors, folder summary, cross-reference
5. [x]   "Start New Production" button — clears session state and returns to Configure & Run
6. [x]   Streamlit use_container_width deprecation — migrated 139 occurrences across 9 files to width='stretch'
```

---

## Phase 24: EDRM Remaining Gaps 🔍

**Reference:** `EDRM_GAP_ANALYSIS.md`

### Phase 24a: Defensibility ✅ (2026-03-26)
```
1. [x]   Collection Scope Documentation — collection_scope junction table, Custodians UI tab, defensibility report Section 2.2
2. [x]   Hash Integrity Verification — "Verify Integrity" button in Case Maintenance, re-hashes all files, flags mismatches/missing
3. [x]   Session Timeout / Auto-Logout — 30 min default via auth_config.yaml, enforced in check_login()
4. [x]   De-NIST Configurability — per-case extension list in case_settings, UI editor in Case Maintenance, exclusion report export
```

### Phase 24b: Workflow ✅ (2026-03-26)
```
5. [x]   Issue Coding / Custom Coding Fields — coding_fields + document_coding tables, dynamic Review panel UI, DAT export, admin config in Case Maintenance
6. [x]   Case Archive / Export — "Archive Case" button in Case Maintenance with ZIP + MANIFEST.json
```

### Phase 24c: Differentiators (partially complete)
```
7. [x]   Exhibit List / Trial Binder — exhibits table with exhibit numbers, descriptions, deposition names; ordered PDF binder export with cover sheet and index
8. [x]   Concept Explorer — OpenSearch significant_text aggregation for keyword expansion and search term negotiation
9. [x]   Custodian Overlap Analysis — cross-custodian content_hash overlap matrix + Plotly heatmap
```

---

## Email Imager Hardening + Selective Re-Image ✅

**Completed:** 2026-03-26 — Critical production-breaking bug fix

```
1. [x]   MIME type fallback for extensionless inline Outlook images (root cause of 500-blank-page bug)
2. [x]   _strip_blank_pages() post-conversion safety net
3. [x]   _neutralize_external_images() to prevent dead-URL layout cascade
4. [x]   FITZ_STORY_MAX_PAGES lowered 500→50; wkhtmltopdf hardened with --load-error-handling ignore, --disable-javascript
5. [x]   Selective Re-Image in Review module — _reimage_document() with full review state reset (preserves system tags), two-click safety UI, reimage permission (admin/manager only)
6. [x]   Stale-production warning on Production tab when processed PDF is newer than produced PDF
```

---

## Phase 25: Multi-Production Junction Table ✅

**Completed:** 2026-03-26 — Architectural prerequisite for supplemental/replacement productions

```
1. [x]   document_productions junction table with UNIQUE(control_number, production_volume), backfill migration
2. [x]   refresh_production_cache(), get_document_productions(), get_production_volume_records() helpers
3. [x]   Production Pass 2 writes to junction table + syncs cache columns
4. [x]   Both deletion paths delete from junction table then refresh cache
5. [x]   Gap analysis queries junction table as authoritative source
6. [x]   Review module: production history expander for multi-production documents
7. [x]   Defensibility report: production detail by type section
```

---

## Holistic Codebase Audit — Remaining Passes 🔍

**Priority:** LOW — Quality assurance, not blocking features
**Status:** All passes complete. Remediation plan in `docs/HOLISTIC_AUDIT_REMEDIATION.md`. Critical fixes applied (4/5 real criticals fixed, 1 false positive). High/Medium/Low items in backlog.
**Files:** `Holistic_Review_Playbook.md` (playbook), `review_sprint.md` (findings log), `docs/HOLISTIC_AUDIT_REMEDIATION.md` (32 findings)

```
3. [x]   RBAC & Security Audit — verify all permission gates, role escalation paths, auth bypass risks
4. [x]   SQL & Data Integrity — parameterized queries, injection surface, migration safety
5. [x]   Config & Deployment — config.py coverage, hardcoded paths, env-specific assumptions
6. [x]   Session State — key collision risks, stale state, cross-page leakage
7. [x]   Audit Trail Coverage — verify every write operation logs; test never-raise contract
8. [x]   UI/UX Consistency — widget key patterns, disabled states, error messages, empty states
9. [x]   Synthesis & Remediation — compile all findings into prioritized action plan
```

---

## Phase 26: Background Processing Worker ⚙️

**Priority:** HIGH — Eliminates session-timeout failures on large cases
**Completed:** 2026-04-02
**Branch:** `testing/background-worker` → merged to `beta-2.9`
**Spec:** See `_processing_worker.py` module header and memory file `project_background_processing.md`
**Files affected:** `processing_engine.py` (new), `_processing_worker.py` (new), `db_manager.py`, `2_Processor.py`, `1_Ingestor.py`, `.streamlit/config.toml`

> **Why this matters:** Processing large PST/document sets previously required the Streamlit browser tab to stay open for the entire run. Session timeouts, network interruptions, or closing the laptop killed processing mid-flight. The background worker runs processing in a separate Python subprocess that survives session disconnects, with progress tracked in the database and a polling UI for reconnection.

```
1. [x]   processing_engine.py — extracted processing pipeline (Phases 1-3) from 2_Processor.py into importable module
2. [x]   _processing_worker.py — subprocess entry point, writes progress to processing_jobs table
3. [x]   db_manager.py — processing_jobs table, job lifecycle helpers (create/update/get/cleanup)
4. [x]   2_Processor.py — launch worker via subprocess.Popen, poll progress from DB, reconnect to running jobs
5. [x]   SQLite WAL self-deadlock fix — separate connections for worker vs. polling
6. [x]   Zombie PID detection — stale job cleanup on worker startup
```

---

## Phase 27: Batch Remediation 🗑️

**Priority:** HIGH — Defensibility-critical; no current way to undo wrong-case ingestion
**Status:** Specced, not implemented
**Spec:** [`Spec_Batch_Remediation_and_Admin_Module.md`](docs/specs/Spec_Batch_Remediation_and_Admin_Module.md)
**Files affected:** `db_manager.py`, `os_manager.py`, `home.py`, `4_Review.py`, `5_Production.py`, `auth_manager.py`

> **Why this matters:** Documents ingested into the wrong case cannot currently be removed. They sit in the database and could be reviewed, tagged, or produced to the wrong opposing party — a privilege and confidentiality breach risk. Quarantine-based remediation with full audit trail is the standard eDiscovery approach.
>
> **UI location decision (2026-04-14):** Remediation UI lives as an admin-gated tab on `home.py`, not a separate Admin Module page. The spec's Part 2 (Admin Module) is deferred indefinitely — all admin features remain in their current locations.

### Phase 1 (Core remediation)
```
1. [ ]   db_manager.py — schema: remediation columns on documents (remediation_id, remediation_reason, remediated_by, remediated_at), remediation_log table, 'Remediated' processing_status value
2. [ ]   db_manager.py — helpers: remediate_documents(), restore_remediation(), get_remediation_log(), recursive family walker (extend get_document_children for full tree)
3. [ ]   os_manager.py — add delete_documents(case_folder, control_numbers) helper (no existing delete-by-id function)
4. [ ]   Quarantine file mover — original, processed PDF, split fragments → {case}/Quarantine/{remediation_id}/ with MANIFEST.json
5. [ ]   Query filter propagation — grep ALL 'Container_Scanned'/'Split_Source' exclusions (~15-17 locations), add 'Remediated' to each. HIGHEST REGRESSION RISK.
6. [ ]   Family-aware remediation — walk parent_id relationships, remediate full document family atomically
7. [ ]   home.py — Admin tab with Remediation subtab: selection UI (date range, collection, custodian, CN range, parent container), scope preview, "REMEDIATE" confirmation gate
8. [ ]   home.py — Admin tab with Retired CNs subtab: gap report from remediation_log
9. [ ]   auth_manager.py — add 'remediate' permission (admin-only default)
10.[ ]   Audit trail — DOCUMENT_REMEDIATED, DOCUMENT_RESTORED events via log_audit_batch()
11.[ ]   review_batches recalculation — update doc_count/page_count after removing remediated docs from batch_documents
```

### Phase 2 (When Phase 1 is proven stable)
```
12.[ ]   home.py — Admin tab with Quarantine Manager subtab: view quarantined batches, restore, permanent purge
13.[ ]   Two-step approval workflow — manager initiates, admin confirms
```

### Implementation Notes (from spec review, 2026-04-14)

These discrepancies between the spec and the current codebase must be addressed during implementation:

- **Stale API:** Spec uses `require_role(3)` — removed in Phase 13. Use `require_permission('remediate')` instead.
- **Page numbering:** Spec proposes `7_Admin.py` — conflicts with existing `7_Custodians.py` and `8_Exhibits.py`. Decision: no separate page; use home.py Admin tab.
- **Restore capability:** Spec Section 1.10 says restore sets status "back to the value it had before remediation (stored in `details_json`)" but the execution flow (Section 1.7) never saves the old status. Implementation must store previous `processing_status` in `details_json` at remediation time.
- **Batch count staleness:** When docs are removed from `batch_documents`, `review_batches.doc_count` and `page_count` become stale. Not in spec — must recalculate.
- **OpenSearch deletion:** No `os_manager.py` delete function exists. `2_Processor.py` calls `os_client.delete()` inline (lines ~174, 216) — formalize as an `os_manager` helper.
- **Filter count:** Exploration found ~15-17 locations filtering on `processing_status` across `db_manager.py`, `home.py`, `4_Review.py`, `5_Production.py`, `7_Custodians.py`. Each must exclude `'Remediated'`. Test every location.

---

## Phase 28: Respondeo License & Distribution System 🔑

**Priority:** MEDIUM — Required before first commercial deployment
**Status:** Specced, not implemented
**Spec:** [`Respondeo_License_System_Spec.md`](docs/specs/Respondeo_License_System_Spec.md)
**Files affected:** new `license_manager.py`, `home.py` (startup gate), `config.example.py`, `.gitignore`, `requirements.txt`, `DEPENDENCY_MAP.md`
**Server repo:** Separate `respondeo-license-server` repo (Flask + SQLite on PythonAnywhere)

> **Why this matters:** Commercialization requires license enforcement, hardware fingerprinting, update distribution, and subscription management. The spec defines a PythonAnywhere-hosted Flask server with offline grace periods and encrypted local caching.
>
> **Scope decision (2026-04-14):** Phase 28 covers both client and server end-to-end. Server code lives in a separate repo but is built in the same sprint for testability.

```
1. [ ]   license_manager.py — hardware fingerprint (Machine GUID + hostname + MAC → SHA-256), Fernet-encrypted cache, validate() entry point
2. [ ]   home.py — license gate before auth gate (between CSS injection and setup_initial_admin)
3. [ ]   config.example.py — add LICENSE_SERVER_URL setting
4. [ ]   .gitignore — add license.key
5. [ ]   requirements.txt — add cryptography==44.0.0 (Supply Chain: dry-run, .pth audit, pip-audit required)
6. [ ]   DEPENDENCY_MAP.md — add _license_valid session state key
7. [ ]   auth_manager.py — add require_valid_license() for optional page-level hardening
8. [ ]   Server repo — Flask app with /validate and /version endpoints, SQLite schema, admin API endpoints
9. [ ]   Deploy to PythonAnywhere — WSGI config, ADMIN_API_KEY env var, schema init, HTTPS verification
10.[ ]   End-to-end test — activate license, verify phone-home, test offline grace period, test expired/revoked states
11.[ ]   Verify _parse_version() tuple comparison in both server and client (spec revised 2026-04-14 to fix this — confirm during implementation)
```

### Implementation Notes (from spec review, 2026-04-14)

- **Version comparison:** ~~Bug~~ Fixed in spec revision (2026-04-14). `_parse_version()` helper added to both server and client. Verify during implementation that all comparison sites use it.
- **Windows-only fingerprinting:** ~~Crash risk~~ Fixed in spec revision (2026-04-14). `winreg` import now wrapped in try/except with clear RuntimeError. Verify during implementation.
- **Supply Chain Security:** `cryptography` is a new dependency with C extensions. Standing orders require: `pip install --dry-run`, `.pth` file audit post-install, `pip-audit` scan. Pin exact version. Pair with Phase 15 (vendoring) to include the wheel in `vendor/wheels/`.
- **Release checklist gap:** No automated sync between client `__version__` and server `LATEST_VERSION`. Document a manual release checklist: bump config.py → update server app.py → cut zip → upload to distribution channel.
- **Cache location:** `{CASES_ROOT}/.respondeo/license_cache.enc` — outside code directory, survives updates. Good design, no changes needed.

---

## Phase 29: User Profile Preferences 👤

**Priority:** MEDIUM — Quality-of-life; reduces per-session friction for reviewers
**Status:** Specced, not implemented
**Estimated effort:** Half-sprint (1 session)
**Spec:** [`USER_PREFERENCES_SPEC.md`](docs/specs/USER_PREFERENCES_SPEC.md)
**Files affected:** `auth_manager.py`, `pages/4_Review.py`, `home.py`, `auth_config.yaml`

> **Why this matters:** Review grid column preferences reset every session. Reviewers doing privilege review need different columns than those doing responsiveness coding, but column configuration is Manager+ only. This feature adds persistent per-user layout preferences with a two-tier permission model: managers control the allowed column pool, individual users personalize within that pool.

```
1. [ ]   auth_manager.py — add get_user_pref(username, key, default) reader; update save_user_pref() to nest under 'preferences' sub-key
2. [ ]   auth_manager.py — add 'personalize_columns' permission (Reviewer+ default)
3. [ ]   4_Review.py — load saved review_columns on session init (filter against ALL_GRID_COLUMNS)
4. [ ]   4_Review.py — "💾 Save as My Default" and "🗑️ Clear My Default" buttons (personalize_columns permission)
5. [ ]   4_Review.py — split Configure Columns expander into manager pool section + personal save section
6. [ ]   Audit trail — USER_PREF_SAVED and USER_PREF_CLEARED events
7. [ ]   Testing — full checklist in spec (default fallback, pool filtering, concurrent sessions, custom roles)
```

---

## Long-term / Commercialization Prep 🚀

- [ ] **PyMuPDF Commercial License** — Formal checklist item before commercial deployment.
- [ ] **Automated Integration Tests** — Full coverage before public release.
- [ ] **HTTPS / Internet-facing Hardening** — TLS, secrets management, auth hardening.
