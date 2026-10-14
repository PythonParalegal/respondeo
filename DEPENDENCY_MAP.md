# Cross-Module Dependency Map
<!-- Last audited: 2026-04-17 against beta-2.10 codebase -->
<!-- UPDATE THIS FILE whenever you add a cross-module dependency -->

This document maps every shared data surface in the platform. "Shared" means
the data is written by one module and read by a different module. Claude Code
must consult this map during the Post-Sprint Impact Audit (see CLAUDE.md
Standing Orders).

## How to Use This File

After every sprint, before the final commit:
1. Check if any change targets (DB columns, file paths, session state keys,
   OpenSearch fields, config values) were added or modified.
2. Look up that target in the relevant section below.
3. Verify every listed consumer still works with the new format/value.
4. If you added a NEW cross-module dependency, add it to this file.

---

## 1. Database Columns — Cross-Module Surface

These columns are written by one module and read by others. A schema change,
rename, or format change in the writer breaks every reader.

### HIGH RISK — Referenced by 4+ modules

| Column | Writer(s) | Reader(s) | Notes |
|--------|-----------|-----------|-------|
| `processing_status` | 1_Ingestor, 2_Processor, db_manager (split) | 3_Analytics, 4_Review, 5_Production, 6_Sync, home.py | Values: New, Container_Scanned, Split_Source, Ready_For_Processing, Processed, Master, Error, Duplicate, Duplicate (Content), Retry. Every module filters on this. |
| `split_source_cn` | db_manager (split_document) | 4_Review | CN of the source document a split child was created from. Defensibility lineage only — NOT a family relationship. |
| `control_number` | 1_Ingestor (generates) | ALL modules, pdf_exporter, universal_imager | Primary key for document identity. Format: `DOC-NNNNNN`. Never change the format. |
| `tags` | 4_Review (user tagging), 2_Processor (auto-tags) | 3_Analytics, 4_Review, 5_Production, 6_Sync, auth_manager (visibility), home.py | Comma-separated string. System tags: NearDupe, Thread, Junk. Tag categories stored in case_settings. |
| `full_path` | 1_Ingestor, 2_Processor | 4_Review, 5_Production, 6_Sync, db_manager | Absolute Windows path to file in Processed/. MUST NOT contain `\\?\` prefix (long-path bug, fixed in 2.7). |
| `record_type` | 2_Processor | 3_Analytics, 4_Review, 5_Production, 6_Sync | Values: Email, Attachment, Loose. Set during processing based on file extension. |
| `group_id` | processing_engine.add_children_to_db (ingestion-time), 2_Processor | 3_Analytics, 4_Review, 5_Production, 6_Sync, pdf_exporter | Family root identifier. For email-rooted families = the email's `DOC-{id:06d}` form. For loose top-level docs = the doc's own `DOC-{id:06d}` form. Archive containers (.pst/.zip) at top-of-family DO NOT define a family — their direct children each start their own family. Archive containers nested in an email family propagate the email's group_id to their children. See `docs/lessons/container-family-model.md` (canonized beta-2.15 Commit 4). |
| `parent_id` | 2_Processor | 3_Analytics, 4_Review, 5_Production, 6_Sync, pdf_exporter | Control number of parent document. NULL for top-level documents. |
| `page_count` | 2_Processor, universal_imager | 4_Review, 5_Production | Integer. Extracted from Tika metadata or PyMuPDF during processing. |

### MEDIUM RISK — Referenced by 2-3 modules

| Column | Writer(s) | Reader(s) | Notes |
|--------|-----------|-----------|-------|
| `begdoc` / `enddoc` | 5_Production | 4_Review, pdf_exporter, home.py | Bates number strings (e.g., `ABC-000001`). NULL until produced. |
| `has_text` | 2_Processor | 4_Review, 5_Production | Integer 0/1. Set during processing. |
| `opensearch_id` | 2_Processor | 4_Review, 5_Production | Always equals control_number. Legacy column from Elasticsearch migration. |
| `content_hash` | 2_Processor | 3_Analytics, 4_Review | SHA-256 of extracted text. Used for content-based dedup. |
| `redaction_status` | 4_Review | 6_Sync | Values: NULL, Has_Redactions, Applied. |
| `redaction_marks` (table) | 4_Review, components/redaction_viewer | 5_Production (burn + priv log), defensibility_report | JSON blob per page with pdf_x0/y0/x1/y1, reason, author, created_at. Read by burn pipeline, priv log Bates formatting, and defensibility queries. |
| `privilege_log_profiles` | 5_Production.py (Priv Log tab) | 5_Production.py (Priv Log tab) | JSON object with named export profiles (column selection, merge rules, Bates format). Per-case. Replaces old `privilege_log_columns` key. |
| `production_categories` | 4_Review (category editor) | 4_Review (dropdown, auto-categorize), 5_Production (sort order, summary) | JSON object: `{categories: [{name, sort_order, color, keywords, extensions}]}`. Per-case. Defines production category list and matching rules. |
| `privilege_status` | 4_Review (via db_manager) | 5_Production | Values: NULL, Redact, Withhold. |
| `production_category` | 4_Review (dropdown + bulk), db_manager (auto-categorize) | 5_Production (sort key for Bates assignment), 4_Review (grid display, filter) | User-assigned category for production ordering. Values: category name string or NULL (uncategorized). Single-value per document. |
| `production_volume` | 5_Production | 4_Review, pdf_exporter | Production volume name string. NULL until produced. |
| `source_collection` / `source_subcollection` | 1_Ingestor | 4_Review, 2_Processor | Folder hierarchy from structured ingestion. May be NULL for flat ingestion. |
| `reviewed_by` / `reviewed_at` | 4_Review (Reviewed-Next) | batch progress queries | Username + ISO timestamp of review determination. Only written by "Reviewed — Next" button. |
| `confidentiality_designation` | 4_Review (coding panel) | 5_Production (per-doc endorsement stamp) | Values: NULL, Confidential, Highly Confidential, Attorneys Eyes Only. |
| `extraction_notes` | 2_Processor (container extraction) | 4_Review (warning banner) | TEXT. Per-document extraction quality warnings (e.g. corrupted PST attachments, CRC repair applied). NULL when extraction was clean. Written during Phase 1 container extraction for both container rows and affected children. |
| `production_runs.direction` | 5_Production (outbound writes), 9_InboundProduction (inbound writes), db_manager (migration default) | home.py (Production History), defensibility_report.py (§6.2), db_manager.get_production_history / get_productions_with_staging_files | Values: `outbound`, `inbound`. Default `outbound` on legacy backfill; inbound rows tagged at ingest time. All outbound-semantics readers MUST filter by `direction = 'outbound'` — leaving the filter off surfaces inbound rows in contexts that imply outbound productions (see §7 "silent cross-module filter drift" pattern). Added beta-2.10 Commit 1. |
| `production_runs.status` | 5_Production (state machine: in_progress → pass1_complete → finalized / aborted), 9_InboundProduction (direct-write finalized for inbound) | pages/5_Production.py orphan detector (via get_productions_with_staging_files filtered to `direction='outbound'`), db_manager.update_production_status | Outbound values: `in_progress`, `pass1_complete`, `finalizing` (reserved, not yet written), `finalized`, `aborted`. Inbound rows always `finalized`. Orphan detector at pages/5_Production.py:239-264 relies on this column to distinguish legitimately-staged Pass 1 from abandoned volumes. Added beta-2.10 Commit 1. |

### TABLES — Cross-Module Surface

| Table | Writer(s) | Reader(s) | Notes |
|-------|-----------|-----------|-------|
| `collection_scope` | 7_Custodians | defensibility_report.py | Per-custodian per-source collection status tracking. FK to custodians.id. |
| `case_settings` key `nist_extensions` | home.py (config UI) | 2_Processor (NIST filter) | JSON array of excluded extensions. Falls back to DEFAULT_NIST_EXTENSIONS in db_manager.py. |
| `case_settings` key `privilege_log_columns` | 5_Production.py (Priv Log tab) | 5_Production.py (Priv Log tab) | JSON array of column keys for privilege log export format. Per-case. |

### exhibit_sets
| Column | Consumers | Notes |
|--------|-----------|-------|
| `id` | `exhibits.exhibit_set_id` (FK), `8_Exhibits.py`, `4_Review.py` | PK, auto-increment |
| `case_folder` | `8_Exhibits.py` | Used for all queries |
| `set_name` | `8_Exhibits.py`, `4_Review.py` (badge display) | UNIQUE with case_folder |

### exhibits
| Column | Consumers | Notes |
|--------|-----------|-------|
| `exhibit_set_id` | `db_manager.get_exhibits()`, `8_Exhibits.py` | FK → exhibit_sets, CASCADE delete |
| `control_number` | `4_Review.py` (badge lookup), `8_Exhibits.py` (binder PDF path resolution) | FK → documents |
| `exhibit_number` | `4_Review.py` (badge), `8_Exhibits.py` (list + binder) | Freeform text, UNIQUE per set |
| `sort_order` | `8_Exhibits.py` (reorder), `db_manager.get_exhibits()` (ORDER BY) | Determines binder sequence |

---

## 2. File Path Conventions

Every module that reads or writes files depends on these directory contracts.
Changing a directory name or structure breaks file resolution downstream.

| Directory | Writer | Reader(s) | Convention |
|-----------|--------|-----------|------------|
| `{case}/Ingest/` | 1_Ingestor | 2_Processor, pdf_exporter | Raw ingested files. Cleared after processing moves files to Processed/. |
| `{case}/Processed/{cn}.pdf` | 2_Processor (imaging) | 4_Review, 5_Production, 6_Sync, pdf_exporter | Imaged PDF. Always named by control_number. |
| `{case}/Processed/{cn}{ext}` | 2_Processor (native move) | pdf_exporter | Native file relocated with control_number prefix. Original extension preserved. |
| `{case}/Productions/{volume}/IMAGES/{bates}.pdf` | 5_Production | 4_Review, pdf_exporter | Bates-stamped production image. |
| `{case}/Productions/{volume}/IMAGES/{bates}.tif` | 5_Production | (load file references) | TIFF production images when TIFF mode selected. |
| `{case}/Productions/{volume}/NATIVES/{filename}` | 5_Production | 4_Review, pdf_exporter | Native files included in production. |
| `{case}/Split/{cn}.pdf` | db_manager (split_document) | 2_Processor | Staging directory for split document PDFs. Processor moves to Processed/ during Phase 2. |
| `{case}/Temp_Explode/` | container_exploder | 2_Processor | Temporary extraction directory for PST/ZIP/EML containers. Cleaned after processing. |
| `{case}/Hold_Documents/{custodian}/` | 7_Custodians | 7_Custodians (download/delete) | Legal hold admin records. NOT case ESI — never processed/produced. |
| `{case}/Productions/{volume}/TEXT/{bates}.txt` | 5_Production | DAT load file (TextLink column) | Extracted text files per document. Referenced by TextLink in DAT. |

**Critical rule:** All paths stored in the `full_path` database column must be
plain Windows paths. Never store the `\\?\` extended-length prefix — it breaks
Outlook COM (`OpenSharedItem` / `AddStore`).

---

## 2.5 Module-Level Registries

Module-level data structures that function as cross-module contracts —
not shared state, but shared schema.

| Registry | Defined In | Read By | Contract |
|----------|-----------|---------|----------|
| `_NAV_PAGES` | `auth_manager.py:22` | `auth_manager.show_user_info()` sidebar renderer. The contract is sprint-wide — every page file added to `pages/` must have a matching tuple or the page is unreachable from the post-login sidebar. | List of `(file_path, label, permission_required)` tuples. `permission=None` means always visible. Filesystem-to-registry parity enforced by `tests/test_nav_registry_consistency.py`. Post-sprint audit step (CLAUDE.md §Post-Sprint step 6, added beta-2.10 Commit 8) reconciles registry against filesystem. |

---

## 3. Session State Keys — Cross-Module Surface

Most session state keys are module-scoped. Only keys shared across modules
are listed here.

| Key | Writer | Reader(s) | Notes |
|-----|--------|-----------|-------|
| `current_case_folder` | home.py | ALL page modules (1-6), auth_manager | The single most critical session state key. Absolute path to active case folder. Set on case selection. |
| `last_activity_time` | auth_manager.py (check_login) | auth_manager.py (timeout check) | Float timestamp. Set on login and updated on every check_login() call. Used for session timeout enforcement. |

| `active_job_id` | 2_Processor.py (launch) | 2_Processor.py (monitor) | Integer job ID. Set when background processing is launched. Used to track the active job across reruns. |

All other session state keys (e.g., `_prod_cancel`, `_proc_cancel`,
`review_search`, `_page_number`) are scoped to a single module and are safe
to modify without cross-module impact.

---

## 4. OpenSearch Index Schema

The Processor (2_Processor.py, line ~1036) defines the indexed document
payload. Every field queried in Review or Analytics MUST exist in this payload.

### Indexed Fields (written by Processor)

```
file_name, control_number, path, content, group_id, parent_id,
custodian, email_subject, author, date, email_from, email_to, email_cc,
email_bcc, file_extension, record_type, date_sent, date_created,
date_received, date_modified, file_size_kb, page_count, title,
language, importance, has_text, source_collection, source_subcollection,
source_party, production_volume, production_category
```

> **History:** Prior to beta-2.8 OS Payload Fix sprint, the index used
> `filename` (no underscore) and `subject` (no `email_` prefix), and was
> missing `source_party` and `production_volume`. These were fixed in
> 2_Processor.py and a reindex utility was added to os_manager.py.
> `production_category` was added in beta-2.9 (was missing from both
> processing_engine.py and os_manager.py reindex payloads).
> Existing cases need a reindex via 6_Sync.py to pick up the corrected fields.

### .keyword Suffix Convention

OpenSearch auto-generates `.keyword` sub-fields for text fields. Use
`.keyword` for exact-match term filters (e.g., `custodian.keyword`).
Use the base field name for full-text search (e.g., `content`).

---

## 5. Config Values (config.py)

| Value | Used By | Notes |
|-------|---------|-------|
| `TIKA_ENDPOINT` | 2_Processor | HTTP endpoint for Tika server |
| `TIKA_TIMEOUT` | 2_Processor | Timeout in seconds for Tika calls |
| `OS_HOST` | os_manager | OpenSearch connection URL |
| `WKHTMLTOPDF_PATH` | universal_imager (×3 call sites) | Path to wkhtmltopdf binary. Fallback hardcoded if missing. |
| `TESSERACT_PATH` | 2_Processor, 5_Production | Path to Tesseract OCR binary. Fallback hardcoded if missing. |
| `CASES_ROOT` | home.py | Root directory scanned for case folders |
| `FILEVINE_SUBDOMAIN` | 6_Sync | Filevine tenant subdomain |
| `__version__` | home.py (display) | Human-managed. Never change without instruction. |
| `__branch__` | (informational) | Should match active git branch. |

---

## 6. Shared Functions — Import Surface

Functions imported by multiple modules. Signature changes break callers.

| Function | Defined In | Called By | Signature Notes |
|----------|-----------|-----------|-----------------|
| `get_connection(case_folder)` | db_manager | ALL modules | Returns sqlite3.Connection with WAL mode and Row factory |
| `init_db(case_folder)` | db_manager | home.py, 1_Ingestor | Creates tables and runs migrations. Idempotent. |
| `log_audit(...)` | db_manager | ALL modules | Never-raise contract. 7 params: case_folder, action, username, control_number, module, old_value, new_value, details |
| `log_audit_batch(...)` | db_manager | 4_Review, 5_Production | Never-raise. Takes list of dicts. |
| `get_os_client()` | os_manager | 2_Processor, 3_Analytics, 4_Review | Returns (client, status_msg) tuple |
| `get_index_name(folder)` | os_manager | 2_Processor, 3_Analytics, 4_Review | Deterministic index name from case folder path |
| `has_permission(name)` | auth_manager | ALL page modules | Boolean check. Permission names are snake_case. |
| `require_permission(name)` | auth_manager | ALL page modules | Calls st.stop() if denied. |
| `get_case_status(case_folder)` | db_manager | ALL page modules | Returns 'Open' or 'Closed'. Used for write-gate at top of every page. |
| `inject_custom_css()` | ui_utils | ALL page modules | Must be called early in page render. |
| `explode_container(filepath, output_dir, log_path)` | container_exploder | processing_engine | Returns list of extracted file paths |
| `run_phase_1/2/3(...)` | processing_engine | 2_Processor, _processing_worker | Phase orchestration. Callbacks: on_progress(phase, completed, total, msg), check_cancel() -> bool |
| `create_job / get_active_job / ...` | db_manager | 2_Processor, _processing_worker | Job CRUD for background processing. Jobs table columns: phase, phase_label, details_json, pid, case_folder, username, cancel_requested |
| `cleanup_stale_jobs(case_folder)` | db_manager | 2_Processor (page load) | Checks PID liveness, marks dead workers as failed |
| `get_document_exhibit_sets(case_folder, control_number)` | db_manager | `4_Review.py` (coding panel badge display) | Returns list of `(set_name, exhibit_number)` tuples for a document |
| `get_exhibit_sets(case_folder)` | db_manager | `4_Review.py` (set dropdown), `8_Exhibits.py` | Returns all exhibit sets for the case |
| `cn_from_hit(hit)` | os_manager | `4_Review.py` (search loop), `os_manager.reindex_from_sqlite`; `3_Analytics.py` could adopt (already canonical) | Returns canonical control_number from an OS hit dict. Handles both internal-shape (`_id == control_number`) and inbound-shape (`_id == composite`; `_source.control_number` carries raw cn) responses. Prefers `_source.control_number`, falls back to `_id`. Pairs with `compute_os_id()` for the inverse direction. Added beta-2.16 S-2 (Flag #28 closure). |
| `compute_os_id(source_party, production_volume, control_number)` | os_manager | `9_InboundProduction.py` (ingest write); future inbound-OCR feature (spec at `docs/superpowers/specs/2026-05-24-inbound-ocr-design.md`) | Returns the OS `_id` for a doc. Internal (`source_party == "Internal"`): `_id = control_number`. Inbound: `_id = f"{production_volume}-{control_number}"`. Raises `ValueError` if source_party non-Internal but production_volume is None/empty. Added beta-2.16 S-2 (Flag #28 closure). |
| `persist_near_dupe_clusters(case_folder, clusters)` | db_manager | `3_Analytics.py` (NearDupe Execute) | Replaces all rows in the two new tables `near_dupe_clusters` + `near_dupe_cluster_members` (added beta-2.16 C8a). Applies NO suppression tag — deferred. Payload member dicts carry `family_preserved` (1 for family-attached children → guarded from suppression). |
| `get_near_dupe_clusters(case_folder)` / `get_cluster_members(case_folder, cluster_id)` | db_manager | `3_Analytics.py` (status/metrics + view-mode radio gate); `4_Review.py` (C8b cluster-review surface) | Cluster summaries / member rows joined to `documents`. `get_near_dupe_clusters` includes `run_date` plus (beta-2.16 C8b) `suppressible_count` / `suppressible_decided` (drive the §11.8 left-list badge denominator, which excludes family-preserved members). `get_cluster_members` includes (C8b) `decided_in_cluster_id` (drives the §11.4 overlap-lock). |
| `record_member_decision(case_folder, cluster_id, member_cn, decision, username)` | db_manager | `4_Review.py` (C8b cluster-review surface) | Atomic decision-row + `documents.tags` write in one txn. `decision ∈ {same,distinct}`; `same` applies `NearDupe-Suppressed` EXCEPT for `family_preserved` members; `distinct` strips it. **Per-document decision propagation (C8b, spec §11.7):** the decision fans out to EVERY `near_dupe_cluster_members` row with the same `member_cn` (a doc can be a non-principal member of multiple clusters), stamping `decided_in_cluster_id` = the source cluster on all of them. The family guard is per-document: a `family_preserved=1` row in ANY cluster blocks suppression. The tag write is a single idempotent per-doc action. `log_audit` best-effort outside the txn. |
| `approve_cluster(case_folder, cluster_id, username, note=None)` / `clear_near_dupe_clusters(case_folder)` | db_manager | `4_Review.py` (approve, C8b); `3_Analytics.py` (clear on re-run) | Attestation write / wipe-both-tables-and-strip-NearDupe-tags (returns `(n_clusters, n_decisions)` measured pre-delete). All six original near-dupe helpers added beta-2.16 C8a. **Deferred-tagging semantic:** post-C8a, `NearDupe-Suppressed` means "reviewer-confirmed," not "algorithm-detected" — consumers that filter on the tag are unchanged in code but now see fewer suppressed docs until reviewers act (intended fail-open). |
| `reopen_cluster(case_folder, cluster_id, username)` | db_manager | `4_Review.py` (C8b attestation row, §11.5) | Re-opens an approved cluster: snapshots the prior `(reviewed_by, reviewed_at, attestation_note)` into a `NEARDUPE_CLUSTER_REOPENED` `audit_log` entry, then reverts the cluster row to `pending` and NULLs the attestation fields. Member decisions are NOT cleared. Current state is editable; `audit_log` is the immutable forensic record. Added beta-2.16 C8b. |
| `get_near_dupe_review_progress(case_folder)` | db_manager | `3_Analytics.py` (confirmed/pending metric + Clear & Re-run guard); `5_Production.py` (C8c non-blocking pending-review FYI above Run Production) | Single aggregate query → `{confirmed, pending, n_decisions, n_clusters}` (member-row grain). `n_decisions` drives the type-to-confirm re-run guard threshold (spec §6); subsumes the C8a F2-dispositioned inline per-cluster metric loop. Added beta-2.16 C8b; second consumer (Production FYI) added C8c. |
| `get_document_content(case_folder, control_number)` | os_manager | `4_Review.py` (C8b diff pane, via the cached `_nd_cached_diff_html` wrapper) | Fetches `_source.content` for one doc via an exact `term` query on `control_number.keyword` (mirrors the `4_Review.py` precedent; the analyzed `control_number` text field would not match reliably). Returns `""` if offline / not found / on any error (diff degrades gracefully). Added beta-2.16 C8b. |
| `get_near_dupe_cluster_detail(case_folder)` | db_manager | `3_Analytics.py:879` (Dedup Report tab); `defensibility_report.py` (`_collect_near_dupe_clusters` → §4.2 per-cluster roll-up, added beta-2.16 C9) | **C8c: body repointed at the cluster tables** (`near_dupe_clusters` + `near_dupe_cluster_members`), replacing the legacy family-`group_id` grouping. **C9: 2 additive fields** → 14-col shape: `cluster_id, run_date, principal_cn, principal_name, member_count, sim_min, sim_max, review_status, reviewed_by, reviewed_at, confirmed_count, pending_count, family_retained_count, distinct_count`. Per-cluster suppressed = `confirmed_count − family_retained_count`. The Dedup Report dataframe + the Excel "Near-Dupe Clusters" sheet auto-flow this shape (additive — extra cols harmless). **External-facing Excel schema change** (14 cols, was 12). |
| `get_data_reduction_stats(case_folder)` → `nd_pending` | db_manager | `3_Analytics.py` (Dedup Report metric caption, waterfall caption, defensibility narrative, Suppression Breakdown "Pending Review" row) | **C8c new field:** count of un-reviewed suppressible cluster members (`decision='undecided' AND is_principal=0 AND family_preserved=0` on `near_dupe_cluster_members`) — mirrors the §11.6 approval-gate denominator. Sibling to the existing `nd_suppressed` (= reviewer-confirmed-suppressed post-C8b). **Distinct from `get_defensibility_dedup.nd_undecided` (C9):** that field counts ALL undecided (any family state) for the court report; this one keeps the `fp=0` suppressibility semantic for the Analytics dashboard. Do not conflate. |
| `get_defensibility_dedup(case_folder)` → `nd_family_retained` / `nd_distinct` / `nd_undecided` / `n_clusters` | db_manager | `defensibility_report.py` (`_collect_dedup_stats` → §4.2 disposition summary, added beta-2.16 C9) | **C9 new fields, all DISTINCT-DOCUMENT counts** (`COUNT(DISTINCT member_cn)` over `is_principal=0`, classified once by fan-out decision + per-document `MAX(family_preserved)`). The 6-cell decision×family partition: `same&fp0` → tag-based `nd_suppressed` (existing); `same&fp1` → `nd_family_retained`; `distinct` → `nd_distinct`; `undecided`(any fp) → `nd_undecided`. **§4.2 reconciliation invariant:** `nd_suppressed + nd_family_retained + nd_distinct + nd_undecided == COUNT(DISTINCT member_cn)` over non-principal rows (pinned by `tests/test_defensibility_neardupe_report.py`). The invariant depends on `clear_near_dupe_clusters` remaining the SOLE tag-stripping gateway before any re-`persist` (it atomically deletes cluster rows AND strips `NearDupe-Suppressed` tags) — a future re-persist path that skips the tag-strip would leave stale tags and break the identity. Cluster tables are outbound-only by construction (built from `source_party='Internal'`), so NO `documents`-table outbound filter applies to these counts. |

### Exhibit Cross-Module Dependencies

- `db_manager.get_document_exhibit_sets()` → consumed by `4_Review.py` coding panel
- `db_manager.get_exhibit_sets()` → consumed by `4_Review.py` (set dropdown) and `8_Exhibits.py`
- `document_productions.production_volume` + `begdoc` → consumed by `8_Exhibits.py` binder export for PDF path resolution
- `auth_manager.ALL_PERMISSIONS` → `mark_exhibit`, `view_exhibits`, `manage_exhibit_sets`, `manage_exhibits`, `export_exhibit_binder`

### Split/Trim Cross-Module Dependencies

- `db_manager.split_document()` / `db_manager.trim_document()` → children inherit all legal metadata from parent: `confidentiality_designation`, `privilege_status`, `clawback_status`, `clawback_date`, `tags`, `source_party`, dates, email metadata
- `processing_status = 'Split_Source'` → excluded from: review grid (4_Review), production imaging (5_Production Pass 1 & 2), count queries (home.py, 7_Custodians, defensibility_report), data reduction stats (db_manager). **Production exclusion is HARD (unconditional); grid exclusion is permission-gated via `view_shell_documents`.**
- `auth_manager.ALL_PERMISSIONS` → `view_shell_documents` (manager+admin): gates Split_Source visibility in review grid and privilege log QC tab. Does NOT gate production queries — those always hard-exclude.

---

## 7. Known Regression Patterns (Scar Tissue)

These are real bugs that occurred due to cross-module dependency drift.
They are documented here so you never repeat them.

| Bug | Root Cause | Modules Affected | Lesson |
|-----|-----------|-----------------|--------|
| Long-path prefix in DB | `\\?\` prefix stored in `full_path` column | Ingestor → Processor → container_exploder (Outlook COM rejected prefixed paths) | Always strip extended-path prefixes before DB writes |
| Threading tab zero results | `message_id IS NOT NULL` filter excluded all MSG files (Exchange-routed, no SMTP headers) | 3_Analytics | Don't assume email metadata fields are populated for all email types |
| Timeline tab TypeError | `.resample()` failed after custodian filter because mixed-timezone datetimes lost dtype | 3_Analytics | Always normalize to UTC with `pd.to_datetime(..., utc=True)` after any filter |
| Redaction burn path mismatch | Production resolved source by original extension instead of processed `.pdf` | 5_Production | Production must use the imaged PDF path, not the original file path |
| 91 MSG files silently failed | `print()` used instead of `logger.error()` in Streamlit context | container_exploder, universal_imager | Streamlit swallows print(). ALL diagnostics must use logger. |
| STR `content` vs `extracted_text` | Analytics/STR queried wrong OpenSearch field name | 3_Analytics, 4_Review | Always verify field names against OPENSEARCH_PATTERNS.md before querying |
| Schema column name confusion | Sprint prompts referenced `doc_type`, `review_status`, `privilege_status` — correct names are `record_type` and `tags` | Multiple | Always verify column names against db_manager.py schema before writing SQL |
| Silent cross-module filter drift | Shared query function (`db_manager.get_production_runs`) returned a superset after beta-2.10 Commit 6 added rows with `direction='inbound'` to `production_runs`, but legacy call sites at `home.py` Production History and `defensibility_report.py §6.2` continued to treat the result as outbound-only — surfacing inbound ingests under "Productions we performed" labels with FRCP 26(g) certification risk | 5_Production, 9_InboundProduction, home.py, defensibility_report.py | When adding a new row-kind (new `direction`, new `record_type`, new status value) to a table whose queries spread across modules, grep every existing caller BEFORE the sprint lands. If any caller's output is rendered under a semantics label ("Production History", "Productions we performed"), the filter must be added at the same commit that introduces the new rows. Fix landed beta-2.10 Commit 7.6. |
| Navigation registry drift | `_NAV_PAGES` in `auth_manager.py` is a separate registry from Streamlit's filesystem-based page routing. Adding `pages/9_InboundProduction.py` in Commit 6 without updating the registry made Module 9 invisible in the post-login sidebar until Commit 7.7 | auth_manager.py, pages/ | Every new/renamed/removed page file requires a corresponding `_NAV_PAGES` tuple edit. Contract pinned by `tests/test_nav_registry_consistency.py`. Post-sprint audit step 6 reconciles registry and filesystem. |
| Custodian rename/merge OS desync | `rename_custodian()` and `merge_custodians()` in `db_manager.py` update SQLite in a single transaction, but the OpenSearch index is written separately by Processor and never updated by the rename/merge path. After either operation, the OS index still shows the pre-rename custodian names. | db_manager.py, 7_Custodians.py, os_manager.py, 6_Sync.py | Any custodian rename/merge must be followed by a manual OpenSearch reindex via Sync → Search Index Maintenance. No automated trigger — enforce by procedure and by the banner in the Custodians page that notifies the user. Candidate for a background reindex hook in a future sprint. |
| PST family-collapse via container ingestion | `add_children_to_db` propagated archive containers' `group_id` to every descendant; "Combine families" PDF export merged whole PSTs into mega-PDFs (one ~500-doc PST → one ~500-page PDF). Production family-sort and Review family-expansion same root cause. | processing_engine.py (ingestion), pdf_exporter.py (combine_families branch), pages/5_Production.py (_walk_family_root), pages/4_Review.py (_expand_to_families) | Containers don't make families; emails do. Archive containers (.pst/.zip) at top-of-family must not propagate group_id — each child starts its own family. Fixed beta-2.15 Commit 4. Full narrative + migration paths: `docs/lessons/container-family-model.md`. |
| libpff EML attachment over-skip | `_explode_eml` treated all Content-ID'd MIME parts as inline; libpff stamps Content-ID on every PST-extracted attachment, so all non-image attachments (Office, PDF, etc.) were silently dropped during extraction. `universal_imager.convert_eml_to_pdf` had the same defect on the rendering side. | container_exploder.py (_explode_eml), universal_imager.py (convert_eml_to_pdf), 4_Review.py (family-expansion showed no children), 5_Production.py (no family stamping) | Use a shared `is_part_inline_image()` predicate based on actual HTML body references (CID matched by `<img src="cid:...">` OR filename matched by `<img src="...">`), not raw Content-ID presence. Non-images are never inline. Fixed beta-2.15 Commit 5. Full narrative: `docs/lessons/extraction-rendering-symmetry.md`. |
