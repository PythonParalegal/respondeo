# Respondeo — Project Context Document
**Version:** 2.15.0 (branch: main, beta-2.15 merged)
**Last updated:** May 2026
**Recent Updates (Beta 2.15):** Two new architecture lessons canonized — `docs/lessons/container-family-model.md` (emails extracted from PST/ZIP archives root families at the email envelope, not the container) and `docs/lessons/extraction-rendering-symmetry.md` (shared `is_part_inline_image()` predicate used by both extraction and rendering paths so they can't disagree about what's inline vs. attachment).
**Purpose:** Comprehensive architectural reference for AI-assisted development sessions.
This document is intended to be uploaded to a Claude.ai Project as persistent knowledge.

---

## 1. PROJECT OVERVIEW

A self-hosted, multi-user e-discovery platform built in Python/Streamlit. It ingests, processes, reviews, and produces legal document collections — the core workflow of litigation document review — without reliance on expensive SaaS platforms (Relativity, Everlaw, etc.).

**Target user:** A small litigation law firm managing its own document review in-house.
**Deployment:** Single Windows machine (local LAN), accessible from multiple workstations via browser.
**Current scale:** Designed for collections up to ~100,000 documents. Not architected for enterprise-scale.

### Core Workflow (in order)
1. **Ingest** — Scan a folder, compute MD5 hashes, register every file into the case database.
2. **Process** — Extract text (Tika), image documents to PDF, deduplicate, index to OpenSearch.
3. **Analytics** — Thread emails by message-ID graph; detect near-duplicates via MinHash LSH.
4. **Review** — Tag documents (privilege, responsiveness), add comments, search full text, view PDF images.
5. **Redact** — Draw redaction boxes on PDF pages, assign per-box privilege reasons, write annotations to disk.
6. **Produce** — Select documents, assign Bates numbers, burn redactions, export load files + images.

---

## 2. REPOSITORY STRUCTURE

```
PythonProject/
├── home.py                   # Streamlit entry point; case selector, user admin, matter profile, case archive, coding field admin, audit log viewer (Admin)
├── config.py                 # Machine-specific paths (gitignored — see config.example.py)
├── config.example.py         # Template for config.py
├── db_manager.py             # ALL database access — schema, migrations, CRUD, log_audit(), log_audit_batch()
├── auth_manager.py           # Authentication + permission-based RBAC (bcrypt; custom roles; document visibility; session timeout)
├── os_manager.py             # OpenSearch client singleton + index utilities; scan_all() scroll helper
├── ui_utils.py               # Shared CSS injection, autocomplete suppression, overlay cancel button
├── container_exploder.py     # Extracts attachments from PST/ZIP/MSG/EML; libpff-primary PST (isolated subprocess, headless) with COM fallback (retry+recovery); non-essential folder skip; MAPI record set helpers; magic byte detection
├── universal_imager.py       # Converts EML/MSG/DOCX/RTF/Office to PDF images; shared email rendering pipeline (6 helpers); hardening guards
├── email_imager.py           # Legacy email imager (partially superseded by universal_imager.py)
├── pdf_exporter.py           # Mass PDF export — builds ZIP archives for Review bulk action bar (Manager+)
├── auth_config.yaml          # User credentials store (gitignored)
├── defensibility_report.py    # Court-ready PDF report generator (9 sections) + collection scope + production detail by type + audit trail PDF export
├── pages/
│   ├── 1_Ingestor.py         # File registration
│   ├── 2_Processor.py        # Text extraction + imaging pipeline (3-phase)
│   ├── 3_Analytics.py        # Email threading + near-dupe detection + 🔍 Dedup Report + 👥 Communication + 📅 Timeline + 🌐 Domain + 👥 Custodian Overlap + 💡 Concept Explorer tabs (Plotly charts)
│   ├── 4_Review.py           # Document review grid + ✏️ Redact tab + 📊 STR radio view + 📦 Batch management + exhibit designation + production history + re-image + custom coding + reviewer notes
│   ├── 5_Production.py       # Outbound Production (Simple/Full EDRM, junction table) + 📥 Inbound Productions + 📋 Privilege Log tabs
│   ├── 6_Sync.py             # Search Index Maintenance + Filevine push/pull-back sync engine
│   ├── 7_Custodians.py       # Custodian management, legal hold tracking, hold document storage, collection scope
│   └── 8_Exhibits.py         # Exhibit set management, exhibit list, add-document search, binder PDF export
├── DEPENDENCY_MAP.md          # Cross-module dependency map (DB columns, file paths, session state, OS fields, shared functions)
├── docs/                     # Dependency API references (EMAIL_MIME, OUTLOOK_COM, LIBPFF_API, PYMUPDF, TIKA_METADATA, OPENSEARCH)
├── _scratchpad/              # Diagnostic/debug scripts — never imported by main app
├── tests/                    # pytest headless regression suite (beta-2.6)
│   ├── conftest.py           # Fixtures: case_folder, seeded_case, auth_config_file, sample_zip, sample_eml
│   ├── test_db.py            # Schema, migrations, audit log, case status, clawback, Bates persistence
│   ├── test_auth.py          # bcrypt + SHA-256 legacy, role hierarchy, user CRUD
│   ├── test_bates.py         # Bates format math + supplemental production continuity
│   ├── test_containers.py    # ZIP + EML container extraction; get_file_type helper
│   └── fixtures/
│       └── sample.eml        # Minimal multipart/mixed EML with one base64 attachment
└── requirements.txt          # pip dependencies (libpff-python commented optional; pytest for dev)
```

**Deleted in v2.3 (merged into parent modules):**
- `6_STR.py` → merged into `4_Review.py` as 📊 Search Term Reports radio view
- `7_Dedup_Report.py` → merged into `3_Analytics.py` as 🔍 Dedup Report tab
- `8_InboundProd.py` → merged into `5_Production.py` as 📥 Inbound Productions tab
- `9_Privilege_Log.py` → merged into `5_Production.py` as 📋 Privilege Log tab
- `10_Redaction.py` → merged into `4_Review.py` as ✏️ Redact tab

### Case Folder Structure (on disk, per case)
```
<CASES_ROOT>\<CaseName>\
├── case.db                   # SQLite database for this case
├── Ingest\                   # Drop files here before ingesting
├── Processed\                # Imaged PDFs (one per document, named by control_number)
├── Productions\              # Output volumes (IMAGES/, NATIVES/, TEXT/, load files)
│   └── {volume_name}\        # One subfolder per production run
├── Hold_Documents\           # Admin records for legal holds (NOT case ESI — never processed/produced)
│   └── {custodian_name}\     # One subfolder per custodian
├── Audit\                    # processing_log.txt (rotating, 10MB max)
└── Temp_Explode\             # Transient extraction workspace (auto-cleaned)
```

---

## 3. TECHNOLOGY STACK

### Framework
- **Streamlit** — UI framework. Multi-page app via `pages/` directory convention.
  - Pinned to a version compatible with `streamlit-drawable-canvas`.
  - `st.set_page_config(layout="wide")` on every page.
  - `st.session_state` is the primary cross-rerun state mechanism.
  - One known manual patch applied to `streamlit_drawable_canvas/__init__.py` to fix a Streamlit 1.55 incompatibility (the library is unmaintained upstream).

### Database
- **SQLite** via Python's built-in `sqlite3` module.
  - `PRAGMA journal_mode=WAL` — enables concurrent readers with a single writer (essential for multi-user Streamlit).
  - `conn.row_factory = sqlite3.Row` — enables column-name access on results.
  - `timeout=60.0` — prevents immediate lock errors under load.
  - One `case.db` file per case, stored in the case folder.
  - Schema managed entirely in `db_manager.py` via `init_db()`.
  - Migration strategy: `ALTER TABLE ADD COLUMN` with `try/except OperationalError` (idempotent, safe on existing DBs).

### Full-Text Search
- **OpenSearch** (self-hosted, local, security plugin disabled — no auth required).
  - Library: `opensearchpy`
  - One index per case, named by sanitizing the case folder name (lowercase, special chars → underscores).
  - Security plugin explicitly disabled (`plugins.security.disabled: true` in opensearch.yml).
  - `os_manager.scan_all()` — custom generator wrapping the scroll API to bypass the 10,000-hit `max_result_window` limit.
  - Client is a cached singleton in `os_manager.py`. For multiprocessing contexts, `get_os_args()` returns a serializable dict instead.

### PDF Engine
- **PyMuPDF (fitz)** — primary PDF library for rendering, annotation, and manipulation.
  - `page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))` — renders page to image at target DPI.
  - `page.add_redact_annot(rect, fill=(0,0,0))` — adds a visible black redaction annotation (PDF type 12) WITHOUT destroying content. `apply_redactions()` is intentionally NOT called here; content destruction is reserved for the production burn step.
  - `doc.saveIncr()` — incremental in-place save; fast and preserves file integrity.
  - **Windows file locking**: `fitz.open()` holds an exclusive lock on Windows. Any document must be `.close()`d before another part of the code tries to open the same file.

### Text Extraction
- **Apache Tika** (Java, runs as a local server on port 9998).
  - Library: `tika` Python client.
  - Started automatically by the Processor; `TIKA_JAR` path configured in `config.py`.
  - Handles: PDF, DOCX, XLSX, PPTX, RTF, HTML, and most other formats.
  - Timeout: 1800 seconds (30 min) for large files.

### Email/Office Imaging (universal_imager.py)
Custom pipeline — no COM automation for EML or MSG. Shared OLE helpers (`_ole_extract_string`, `_ole_extract_binary`, `_ole_extract_filetime`, etc.) at module level serve both `convert_msg_to_pdf()` and `extract_msg_text()`. RTF de-encapsulation cleaned by shared `_scrub_rtf_from_html()` helper. **Sprint 5:** MSG OLE parsing further decomposed into `_parse_msg_headers()`, `_parse_msg_body()`, and `_parse_msg_attachments()` — shared by both conversion and text-extraction paths (~150 line reduction). `flatten_pdf()` decomposed into `_detect_pdf_interactivity()` / `_flatten_xfa_pdf()` / `_flatten_acroform_pdf()` router pattern. **Sprint 6:** Inline image stream leak fixed — `fitz.open(stream=...)` in `_append_inline_images_to_pdf()` wrapped in `try/finally`.

| Format | Method |
|--------|--------|
| EML | Python `email` module (stdlib) — parses headers/body natively; renders to PDF via `fitz.Story` (HTML→PDF) |
| MSG | `olefile` — reads Outlook compound binary directly; decompresses RTF body via `compressed_rtf`; de-encapsulated HTML scrubbed of 50+ RTF control word families; renders via `fitz.Story` |
| DOCX | LibreOffice headless (`soffice --headless --convert-to pdf`) with `python-docx`/`mammoth` fallback for HTML→PDF |
| RTF | LibreOffice headless |
| Office (XLS, PPTX, etc.) | `win32com.client` (Excel/PowerPoint COM automation) — only where LibreOffice is insufficient |
| PDF | Pass-through (already in target format) |

**Shared email rendering pipeline (beta-2.9):** Six extracted helpers consolidate the EML and MSG rendering paths into a single pipeline, eliminating the "fix it twice" pattern:
- `_build_email_html(sender, date, to, cc, bcc, subject, attachments_html, html_body)` — assembles the full email HTML document with header table and body content.
- `_wrap_plain_text_as_html(plain_body)` — converts plain-text email bodies to HTML with `<pre>` wrapping.
- `_substitute_cid_images(html_body, inline_images)` — resolves CID references to embedded base64 data-URIs; returns the modified HTML and a dict of unresolved images.
- `_run_wkhtmltopdf(rendered_html, output_pdf_path)` — renders HTML to PDF via wkhtmltopdf with safety flags (`--disable-javascript`).
- `_render_fitz_story(html, output_pdf_path)` — renders HTML to PDF via PyMuPDF Story API with `FITZ_STORY_MAX_PAGES = 50` safety cap to prevent runaway page generation from layout pathology.
- `_append_inline_images_to_pdf(output_pdf_path, images_dict)` — appends unresolvable CID images as separate pages at the end of the PDF.

**Hardening (beta-2.9):**
- `_strip_blank_pages(pdf_path, min_text_chars=5)` — post-conversion safety net that removes blank pages from rendered PDFs (common artifact from wkhtmltopdf with sparse HTML).
- `_neutralize_external_images(html_str)` — strips external image URLs from HTML before rendering, preventing network calls during imaging and ensuring reproducible output.
- `FITZ_STORY_MAX_PAGES = 50` — safety cap for the `fitz.Story` page loop; logs a warning and truncates if hit.
- wkhtmltopdf safety flags: `--disable-javascript` to prevent script execution in email HTML content.

Inline CID image handling (EML/MSG): CID references in HTML body are resolved to embedded image data and substituted as base64 data-URIs before rendering. Unresolvable images are appended as separate pages at end of PDF.

Base64 image stripping: `_strip_base64_images()` removes large data-URI images from HTML before `fitz.Story` processes it — prevents infinite loop in `story.place()` caused by atomic image blocks that cannot be split across pages.

**Selective Re-Image (beta-2.9):** `_reimage_document()` in `4_Review.py` — Manager+ function to regenerate the PDF image for a single email document. Calls `universal_imager` to re-render, then resets `reviewed_by`, `reviewed_at`, and `redaction_status` (full review state reset). Exposed via a `🔄 Re-Image This Document` expander in the Review document panel. Gated to emails only (MSG/EML) since those are the formats most likely to need re-imaging after pipeline improvements.

### Data Visualization
- **Plotly** (`plotly>=5.24.0`) — interactive charts via `st.plotly_chart()`. Used for: dashboard pipeline funnel, review decision donut chart, dedup waterfall, communicator stacked bars, communication heatmap, timeline with gap annotations, domain pie/bar charts, custodian inventory bar, hold Gantt timeline. Consistent theme: transparent backgrounds (`rgba(0,0,0,0)`) for light/dark mode compatibility, navy/green/orange/red/purple/teal color palette.

### Analytics
- **NetworkX** — directed graph for email thread analysis. Each `message_id` is a node; `in_reply_to` and `references_list` edges define the reply chain. `_normalize_msg_id()` strips angle brackets. Leaf nodes (out-degree = 0) are "Inclusive" emails.
- **datasketch** (MinHashLSH) — near-duplicate detection via MinHash signatures over **k-gram shingles** (5-token sliding windows, not bare tokens — preserves phrase structure, fixes Flag #22 template-collision false positives; beta-2.16 C6). 128 permutations, configurable Jaccard threshold (default 0.90). Runs against OpenSearch-stored content.
- **Deferred-tagging near-dupe workflow (beta-2.16 C8a–C9, fail-open).** The near-dupe run no longer auto-applies `NearDupe-Suppressed`; it persists candidate clusters to two tables (`near_dupe_clusters`, `near_dupe_cluster_members`) with `decision DEFAULT 'undecided'`. A reviewer dispositions each member (Same/Distinct) in the `4_Review.py` cluster-review surface (side-by-side diff via `neardupe_diff.py`); `db_manager.record_member_decision()` writes the decision + `documents.tags` atomically (`same` → tag, except `family_preserved` members; `distinct` → strip), fanning the decision across all cluster rows sharing the `member_cn`. `approve_cluster()` records attestation; `clear_near_dupe_clusters()` wipes tables + strips tags before re-run (type-to-confirm guard). The defensibility report's §4.2 (`defensibility_report._collect_near_dupe_clusters` + `get_defensibility_dedup` distinct-document disposition counts) reports this for the court. Flag #30 (overlapping clusters) deferred — reported honestly, not merged.

### Authentication & Authorization
- **PyYAML** — stores user credentials in `auth_config.yaml` (gitignored).
- Passwords hashed with **bcrypt** (upgraded from SHA-256 in beta-2.4). Transparent migration: existing SHA-256 hashes (64-char hex, no `$2b$` prefix) are detected at login, verified against SHA-256, then immediately re-hashed to bcrypt and written back — zero-downtime upgrade. New passwords and resets always use bcrypt.
- **Permission-based RBAC** — replaces three-tier numeric role hierarchy. Named permissions (`has_permission()` / `require_permission()`) enforce access gates throughout the platform. All gates annotated with `# permission: <name>` comments.
  - **Admin**: wildcard `*` (all permissions).
  - **Manager**: ingest, process, analytics, review, tag, redact, export, production, sync, column picker, saved search (global + personal), custodian_management.
  - **Reviewer**: review, tag, redact, personal saved searches, download produced, mark_exhibit, view_exhibits.
  - **Expert**: review, tag, STR run, personal saved searches, download produced (no export, redact, or column picker).
  - **Custom roles**: Admins can create via UI. Defined in `auth_config.yaml` under `custom_roles` with `inherits` and `additional` fields.
- **Exhibit permissions** (beta-2.9): `view_exhibits` and `mark_exhibit` (Reviewer+); `manage_exhibit_sets`, `manage_exhibits`, `export_exhibit_binder` (Manager+). Defined in `ALL_PERMISSIONS` and `_DEFAULT_PERMISSIONS` in `auth_manager.py`.
- **`view_shell_documents`** permission: Controls visibility of `Container_Scanned` and `Split_Source` shell documents in the Review grid. Default off for reviewers, on for managers+.
- **Session timeout** (beta-2.9): Configurable inactivity auto-logout. Default 30 minutes, controlled via `session_timeout_minutes` in `auth_config.yaml`. `check_login()` compares the last activity timestamp against the configured timeout; expired sessions are cleared and the user is prompted to re-authenticate.
- **Document visibility**: Three modes per user (`full` / `produced_only` / `hidden_tags`), managed by Admin. Applied as SQL `WHERE` clauses in the Review grid. Admin users always have full visibility.
- Pages are hidden entirely from sidebar if user lacks the required permission.
- `auth_manager.check_login()` and `auth_manager.require_permission()` called at the top of every page.

### Canvas / Redaction UI
- **streamlit-drawable-canvas** — HTML5 canvas overlay for drawing redaction rectangles on PDF page images.
  - One manual patch applied to fix Streamlit 1.55 incompatibility (upstream library is unmaintained).
  - `drawing_mode="rect"` for drawing; `"transform"` for moving/resizing existing boxes.
  - Canvas key includes `{control_number}_{page_index}` to force re-mount on document/page change.
  - `canvas_mode` must be read from `st.session_state` before `st_canvas` is called (previous rerun's value), because the radio widget that controls it renders in a column after the canvas.

### Container Extraction
`container_exploder.py` handles these container types:
- **ZIP** — recursive extraction via `zipfile`.
- **EML** — attachment extraction via Python `email` stdlib. CID inline images explicitly skipped. Magic byte detection (`_guess_ext_from_magic()`) resolves `.bin` attachments to real extensions (PDF, JPEG, PNG, DOCX, HTML, etc.).
- **PST** — `explode_pst()` is a dispatch function: tries Outlook COM first (`_explode_pst_com()`, requires Outlook installed), falls back to `explode_pst_libpff()` (pure Python via `pypff` / `libpff-python`), raises `RuntimeError` if both are unavailable. COM path saves each mail item as a `.msg` file; libpff path converts each message to `.eml` format using MAPI record set helpers (`_get_record_entry()`, `_get_record_string()`, `_get_record_integer()`). Both flow into the existing downstream pipeline. The `_WIN32COM_AVAILABLE` flag (set at import time via `try/except ImportError`) guards all COM usage.
- **Synthetic CID generation** — inline-flagged attachments (PR_ATTACH_FLAGS bit 2 / ATT_MHTML_REF) that lack a Content-ID get a synthetic CID assigned, preventing signature images from leaking through as child documents.

**Sprint 5:** `_libpff_message_to_eml()` decomposed into an orchestrator pattern — `_build_eml_headers(msg)`, `_attach_eml_bodies(msg, mime_msg)`, and `_attach_eml_attachment(msg, mime_msg, idx)` — called in sequence by the orchestrator. **Sprint 6:** COM object init guard (`pythoncom.CoInitialize()` call in `process_msg_batch()`) verified present.

MSG attachments are handled separately via `process_msg_batch()` in `container_exploder.py` using `win32com.client` / Outlook COM. Includes synthetic CID generation for inline attachments. Note: `process_msg_batch` calls `pythoncom.CoInitialize()` directly and is only valid on Windows with Outlook.

**Container lifecycle:** `New` → `Container_Scanned` (after child extraction) → skipped by Phase 2 → excluded from Review grid. Long-path handling: `\\?\` prefix on Windows to bypass 260-char MAX_PATH; stripped before DB storage.

---

## 4. DATABASE SCHEMA (db_manager.py)

### `documents` table (primary)

Full schema (from `db_manager.py` `init_db()`):

```sql
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- IDENTIFICATION
    control_number TEXT UNIQUE,     -- Internal BEGDOC (e.g. ABC000001), assigned at ingest
    begdoc TEXT,                    -- Production BEGDOC (populated by Production module)
    enddoc TEXT,                    -- Production ENDDOC
    source_party TEXT DEFAULT 'Internal', -- 'Internal' or producing party name for inbound
    production_volume TEXT,         -- Volume label for inbound productions
    dynamic_metadata TEXT,          -- JSON string for unmapped load file fields
    begatt TEXT,                    -- Family range start Bates
    endatt TEXT,                    -- Family range end Bates
    parent_id TEXT,                 -- Control number of parent document (attachments + split/trim lineage)
    group_id TEXT,                  -- Family/thread group ID
    custodian TEXT,
    volume TEXT,                    -- Source media/volume name

    -- BASIC METADATA
    file_name TEXT,
    file_extension TEXT,
    file_size_kb REAL,
    record_type TEXT,               -- 'Email', 'Attachment', 'Loose'
    md5_hash TEXT,
    content_hash TEXT,              -- Hash of extracted text content (for content dedup)
    page_count INTEGER,
    language TEXT,

    -- DATES (stored as ISO8601 strings for sorting)
    date_sent TEXT,                 -- DATESENT + TIMESENT combined
    date_received TEXT,
    date_created TEXT,
    date_modified TEXT,

    -- EMAIL METADATA
    email_from TEXT,
    email_to TEXT,
    email_cc TEXT,
    email_bcc TEXT,
    email_subject TEXT,

    -- THREADING DNA
    message_id TEXT,                -- Email's unique Message-ID header
    in_reply_to TEXT,               -- Message-ID this email replied to
    references_list TEXT,           -- All Message-IDs in the chain (semicolon-delimited)
    conversation_index TEXT,        -- Microsoft-specific threading code (hex-encoded)
    conversation_topic TEXT,        -- Normalized subject for threading (MSG OLE stream 0070)
    author TEXT,                    -- Document author (non-email)
    title TEXT,                     -- Document title (dc:title from Tika)

    -- ENRICHMENT METADATA (beta-2.7)
    mime_type TEXT,                 -- Content-Type detected by Tika
    creating_application TEXT,      -- Application name + version
    extraction_method TEXT,         -- 'pymupdf' / 'tika' / 'tesseract_ocr' / 'native_ole'
    is_encrypted INTEGER DEFAULT 0, -- 1 if PDF/Office file is password-protected
    word_count INTEGER,             -- Word count from Tika
    attachment_count INTEGER,       -- Number of child attachments
    importance TEXT,                -- Email priority: Low / Normal / High
    sensitivity TEXT,               -- Email sensitivity: Normal / Personal / Private / Confidential
    tika_metadata_json TEXT,        -- Full raw Tika metadata dict as JSON

    -- SYSTEM
    original_path TEXT,             -- Path before processing
    full_path TEXT,                 -- Current path on disk
    processing_status TEXT DEFAULT 'New',  -- 'New','Processed','Master','Duplicate (MD5)','Duplicate (Content)','Error'
    has_text INTEGER DEFAULT 0,     -- 1 if text was successfully extracted
    opensearch_id TEXT,             -- OpenSearch document ID
    tags TEXT,                      -- Comma-separated applied tags
    analytics_run_date TEXT,        -- Timestamp of last analytics pass

    -- FILEVINE SYNC
    filevine_doc_id TEXT,
    filevine_collection_id TEXT,
    sync_status TEXT DEFAULT 'Pending',
    sync_timestamp TEXT,
    byos_pushed_at TEXT,
    byos_pulled_at TEXT,
    review_pulled_at TEXT,          -- Timestamp of pull-back from Filevine

    -- REDACTION
    redaction_status TEXT,          -- NULL / 'Has_Redactions' / 'Applied'

    -- CLAWBACK
    clawback_status TEXT,           -- NULL / 'Clawback_Demanded' / 'Clawback_Resolved'
    clawback_date TEXT,             -- ISO date of clawback demand letter

    -- REVIEW TRACKING (beta-2.8)
    reviewed_by TEXT,               -- Username who reviewed (NULL = not yet reviewed)
    reviewed_at TEXT,               -- ISO timestamp of review determination

    -- SPLIT/TRIM (beta-2.9)
    split_page_ranges TEXT,         -- Extracted page ranges for split children (e.g., '1-5,8')

    -- CONFIDENTIALITY (beta-2.9)
    confidentiality_designation TEXT -- Confidentiality level override (NULL = not designated)
)
```

Index: `CREATE INDEX IF NOT EXISTS idx_content_hash ON documents(content_hash, processing_status)`

Key enum values:
- `processing_status`: `'New'` | `'Processed'` | `'Master'` | `'Duplicate (MD5)'` | `'Duplicate (Content)'` | `'Error'` | `'Container_Scanned'` | `'Ready_For_Processing'` | `'Split_Source'` (original doc after split/trim; children inherit redaction marks with page-number remapping)
- `redaction_status`: `NULL` | `'Has_Redactions'` | `'Applied'`
- `clawback_status`: `NULL` (normal) | `'Clawback_Demanded'` | `'Clawback_Resolved'`
- `source_party`: `'Internal'` (default) | any string for inbound productions
- `record_type`: `'Email'` | `'Attachment'` | `'Loose'`

### `redaction_marks` table
- `(control_number, page_number)` — unique constraint; one row per page per document.
- `marks_json` — JSON array of mark objects, each with `{pdf_x0, pdf_y0, pdf_x1, pdf_y1, reason}`.
- Coordinate system: PDF points (not screen pixels); scale factor stored at draw time.

### `case_settings` table
- Key-value store for per-case configuration.
- Key `'tag_categories'` — JSON blob defining privilege/responsiveness tag categories and members.
- Key `'case_status'` — `'Active'` | `'On Hold'` | `'Closed'`; default `'Active'`.
- Key `'last_bates_info'` — JSON blob `{prefix, end_num, prod_name, padding}` written at end of every successful production run; used by supplemental production to auto-populate next starting Bates number.

### `saved_searches` table
- Per-user search history (auto-logged) and named saved searches.
- `is_global` flag for searches shared across all users.

### `jobs` table
- Background job tracking for long-running processor tasks.
- Core columns: `job_type`, `status` (pending/running/completed/failed/cancelled), `progress`, `total`, `error`, `created_at`, `started_at`, `finished_at`.
- Worker columns (added for background processing): `phase`, `phase_label`, `details_json` (JSON: per-phase stats, recent warnings), `pid` (OS process ID for zombie detection), `case_folder`, `username`, `cancel_requested` (polled by worker).

### `custodians` table (beta-2.8)
- Registry table for custodian-level metadata (not a foreign key — `documents.custodian` remains plain text).
- Identity: `name` (UNIQUE), `title`, `department`, `email`, `notes`.
- Legal hold: `hold_status` (None/Active/Released/Expired), `hold_issued_date`, `hold_acknowledged_date`, `hold_released_date`, `hold_notice_method`, `hold_notice_recipient`, `hold_notes`.
- Collection metadata: `collection_start_date`, `collection_end_date`, `data_sources` (JSON list).
- Auto-populated from `documents.custodian` via `INSERT OR IGNORE` on every page load.

### `hold_documents` table (beta-2.8)
- Stores uploaded hold-related files (notices, acknowledgments, letters) — **NOT case ESI**.
- Fields: `custodian_name`, `file_name`, `file_path`, `document_type`, `uploaded_by`, `upload_date`, `notes`.
- Files stored in `{case_folder}/Hold_Documents/{custodian}/` — completely separate from Ingest/Processed/Productions.

### `review_batches` table (beta-2.8)
- Review batch assignments for distributing work among reviewers.
- Fields: `batch_name`, `assigned_to`, `created_by`, `status` (Open/In Progress/Complete), `doc_count`, `page_count`, `notes`.

### `batch_documents` table (beta-2.8)
- Junction table linking batches to documents. `UNIQUE(control_number)` — a document belongs to at most one batch.
- `FOREIGN KEY (batch_id) REFERENCES review_batches(id) ON DELETE CASCADE`.

### `document_notes` table (beta-2.9)
- Per-document, per-user reviewer notes. `UNIQUE(control_number, username)` — one note per reviewer per document.
- Fields: `control_number`, `username`, `note_text`, `created_at`, `updated_at`.

### `collection_scope` table (beta-2.9)
- Per-custodian, per-source collection status tracking with defensibility justification.
- Fields: `custodian_id` (FK CASCADE to `custodians`), `source_name`, `status` (CHECK: `'Pending'`/`'Collected'`/`'Searched-No-Hit'`/`'Not-Reasonably-Accessible'`/`'Out-of-Scope'`), `justification`, `reviewed_by`, `reviewed_at`, `created_at`, `updated_at`.
- `UNIQUE(custodian_id, source_name)`.

### `document_productions` table (beta-2.9)
- Junction table tracking every production event per document across multiple volumes — replaces the flat `begdoc`/`enddoc`/`production_volume` columns on `documents` for multi-production support.
- Fields: `control_number` (FK to `documents`), `production_volume`, `begdoc`, `enddoc`, `page_count`, `produced_at`, `production_type` (`'Original'`/`'Supplemental'`/`'Replacement'`), `supersedes_id` (FK self-referencing for replacements), `notes`.
- `UNIQUE(control_number, production_volume)`.
- Indexes: `idx_dp_control_number`, `idx_dp_production_volume`, `idx_dp_begdoc`.
- One-time backfill migration: on `init_db()`, if the junction table is empty but `documents.begdoc` has data, existing flat Bates data is copied into the junction table via `INSERT OR IGNORE`.
- `refresh_production_cache()` syncs the flat `documents.begdoc`/`enddoc`/`production_volume` columns from the junction table (latest production per document) — maintains backward compatibility with modules that read the flat columns.

### `coding_fields` table (beta-2.9)
- Admin-defined custom coding fields for issue coding during review.
- Fields: `field_name` (UNIQUE), `field_type` (CHECK: `'picklist'`/`'text'`/`'boolean'`), `pick_list_json` (JSON array of choices for picklist type), `display_order`, `created_by`, `created_at`.

### `document_coding` table (beta-2.9)
- Junction table storing per-document values for custom coding fields.
- Fields: `control_number` (FK to `documents`), `coding_field_id` (FK to `coding_fields`), `value`, `coded_by`, `coded_at`.
- `UNIQUE(control_number, coding_field_id)`.
- Indexes: `idx_dc_control_number`, `idx_dc_field_id`.
- Intentionally excluded from DAT/CSV production load files (attorney work product).

### `exhibit_sets` table (beta-2.9)
- Groups of exhibits organized by proceeding type.
- Fields: `case_folder`, `set_name`, `set_type` (`'Deposition'`/`'Motion'`/`'Hearing'`/`'Trial'`), `proceeding_date`, `case_caption`, `created_by`, `created_at`.
- `UNIQUE(case_folder, set_name)`.

### `exhibits` table (beta-2.9)
- Individual exhibits within a set, linking to produced documents.
- Fields: `exhibit_set_id` (FK CASCADE to `exhibit_sets`), `control_number` (FK to `documents`), `exhibit_number`, `description`, `sort_order`, `added_by`, `added_at`.
- `UNIQUE(exhibit_set_id, exhibit_number)`, `UNIQUE(exhibit_set_id, control_number)`.
- Indexes: `idx_exhibits_set_id`, `idx_exhibits_cn`.
- CASCADE delete: deleting an exhibit set removes all its exhibits.

### `near_dupe_clusters` / `near_dupe_cluster_members` tables (beta-2.16 C8a)
- Persist algorithm-identified near-duplicate clusters for the **deferred-tagging (fail-open) review workflow** — the near-dupe run writes these tables but applies NO `NearDupe-Suppressed` tag; suppression is deferred to reviewer confirmation.
- **`near_dupe_clusters`**: one row per cluster. Fields: `cluster_id` (PK), `run_date`, `principal_cn`, `member_count`, `sim_min`, `sim_max`, `review_status` (`'pending'`/`'approved'`), `reviewed_by`, `reviewed_at`.
- **`near_dupe_cluster_members`**: one row per (cluster, member). Fields: `cluster_id` (FK), `member_cn`, `is_principal`, `family_preserved`, `similarity`, `decision` (`DEFAULT 'undecided'`; `'same'`/`'distinct'`), `decided_by`, `decided_at`, `similarity_at_decision`, `decided_in_cluster_id` (source cluster of a fanned-out decision — a `member_cn` can be a non-principal member of multiple clusters; one decision is authoritative per document).
- Helpers (`db_manager.py`): `persist_near_dupe_clusters` (atomic replace), `get_near_dupe_clusters`/`get_cluster_members`/`get_near_dupe_cluster_detail` (reads), `record_member_decision` (atomic decision + tag write, family-guarded), `approve_cluster` (attestation), `clear_near_dupe_clusters` (wipe tables + strip tags, returns counts). The `get_defensibility_dedup` distinct-document disposition counts (`nd_family_retained`/`nd_distinct`/`nd_undecided`/`n_clusters`) and `get_near_dupe_cluster_detail` feed the defensibility report §4.2 (beta-2.16 C9).

### `audit_log` table
Full schema (migrated in `init_db()` via `ALTER TABLE ADD COLUMN` pattern):

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    action TEXT,          -- Standardized verb (see vocabulary below)
    details TEXT,         -- Free-text / JSON context
    username TEXT,        -- Logged-in user who performed the action
    control_number TEXT,  -- Document affected (NULL for case-level actions)
    module TEXT,          -- Page/module where action originated
    old_value TEXT,       -- State before the change (NULL for creates)
    new_value TEXT        -- State after the change (NULL for deletes)
)
```

Indexes: `idx_audit_control (control_number)`, `idx_audit_user (username)`, `idx_audit_timestamp (timestamp)`, `idx_audit_module (module)`.

**Central logging functions in `db_manager.py`:**
- `log_audit(case_folder, action, username, control_number, module, details, old_value, new_value)` — single-row insert; never raises (audit failures must not crash workflows).
- `log_audit_batch(case_folder, entries)` — `executemany` in a single transaction for high-volume operations (Ingestor, Analytics, Production, InboundProd).

**Standard action vocabulary** (all modules use these exact strings):
`DOCUMENT_INGESTED` | `PROCESSING_STARTED` | `PROCESSING_COMPLETED` | `PROCESSING_ERROR` | `PROCESSING_CANCELLED` | `TEXT_EXTRACTED` | `DOCUMENT_IMAGED` | `DOCUMENT_REIMAGED` | `DUPLICATE_MARKED` | `ANALYTICS_RUN` | `TAG_APPLIED` | `TAG_REMOVED` | `TAGS_CHANGED` | `COMMENT_ADDED` | `COMMENT_EDITED` | `SEARCH_EXECUTED` | `SEARCH_SAVED` | `PDF_EXPORTED` | `PRODUCED_DOWNLOAD` | `REDACTION_SAVED` | `REDACTION_CLEARED` | `PRODUCTION_CREATED` | `PRODUCTION_CANCELLED` | `PRODUCTION_RETRY` | `PRODUCTION_STALE_CLEANUP` | `BATES_ASSIGNED` | `REDACTION_BURNED` | `PRODUCTION_EXPORTED` | `PRODUCTION_OCR_COMPLETE` | `INBOUND_INGESTED` | `PRIVILEGE_LOG_EXPORTED` | `USER_LOGIN` | `USER_CREATED` | `USER_ROLE_CHANGED` | `USER_DELETED` | `PASSWORD_RESET` | `CASE_SETTING_CHANGED` | `FILEVINE_PUSH` | `FILEVINE_PULL` | `BYOS_PUSH` | `BYOS_PULL` | `CLAWBACK_MARKED` | `USER_VISIBILITY_CHANGED` | `REPORT_GENERATED` | `SEARCH_INDEX_REBUILT` | `CUSTODIAN_UPDATED` | `CUSTODIAN_RENAMED` | `CUSTODIAN_MERGED` | `CUSTODIAN_REASSIGNED` | `COLLECTION_RENAMED` | `COLLECTION_ASSIGNED` | `HOLD_STATUS_CHANGED` | `HOLD_DOCUMENT_UPLOADED` | `HOLD_DOCUMENT_DELETED` | `BATCH_CREATED` | `BATCH_ASSIGNED` | `BATCH_DOCUMENTS_MOVED` | `BATCHES_DELETED` | `MATTER_PROFILE_UPDATED` | `EXHIBIT_SET_CREATED` | `EXHIBIT_SET_DELETED` | `EXHIBIT_ADDED` | `EXHIBIT_REMOVED` | `EXHIBIT_BINDER_EXPORTED` | `REVIEWER_NOTE_SAVED` | `REVIEWER_NOTE_DELETED`

**Audit log viewer:** Admin-only expander on `home.py` (visible only when a case is selected). Filters by username, module, action, control number, and date. Returns up to 2,000 rows ordered by timestamp DESC. Three export formats: CSV download, Excel (.xlsx with metadata sheet, frozen pane, auto-width columns), and PDF (landscape layout via `defensibility_report.generate_audit_export_pdf()` with repeating headers and filter criteria documentation).

**Additional helpers in `db_manager.py` (beta-2.6):**
- `mark_clawback(case_folder, control_number, status, demand_date, notes, username)` — updates `clawback_status` and `clawback_date` on a document and writes a `CLAWBACK_MARKED` audit entry. Raises on DB failure (caller must handle).
- `get_clawback_summary(case_folder)` — returns a list of dicts for all documents with a non-NULL `clawback_status` (`Clawback_Demanded` or `Clawback_Resolved`).
- `get_last_bates_info(case_folder)` — reads the `last_bates_info` JSON blob from `case_settings`; returns `None` if no prior production exists.
- `save_last_bates_info(case_folder, prefix, end_num, prod_name, padding=6)` — writes the `last_bates_info` JSON blob to `case_settings` via `INSERT OR REPLACE`. Called at the end of every successful production run.

**NIST de-junk helpers in `db_manager.py` (beta-2.9):**
- `DEFAULT_NIST_EXTENSIONS` — constant list of file extensions considered system/junk files (e.g., `.dll`, `.exe`, `.sys`). Used as the default when no per-case override exists.
- `get_nist_extensions(case_folder)` — reads the `nist_extensions` key from `case_settings`; returns `DEFAULT_NIST_EXTENSIONS` if unset.
- `set_nist_extensions(case_folder, extensions)` — writes the extension list to `case_settings` as JSON.

**Matter profile helpers in `db_manager.py` (beta-2.9):**
- `get_matter_profile(case_folder)` — reads the `matter_profile` JSON blob from `case_settings`; returns `None` if unset.
- `set_matter_profile(case_folder, profile_dict)` — writes the profile dict to `case_settings` as JSON via `INSERT OR REPLACE`.

**Document note functions in `db_manager.py` (beta-2.9):**
- `upsert_document_note(case_folder, control_number, username, note_text)` — creates or updates a reviewer note (one per user per document). Preserves original `created_at` on update.
- `get_document_notes(case_folder, control_number)` — returns all notes for a document, ordered by `updated_at DESC`.
- `delete_document_note(case_folder, control_number, username)` — removes a specific user's note.

**Production junction table functions in `db_manager.py` (beta-2.9):**
- `refresh_production_cache(case_folder, control_number=None)` — syncs flat `documents.begdoc`/`enddoc`/`production_volume` columns from the `document_productions` junction table. If `control_number` is provided, updates only that document; otherwise updates all documents with production records.
- `get_document_productions(case_folder, control_number)` — returns all production records for a single document, ordered by `produced_at`.
- `get_production_volume_records(case_folder, volume_name)` — returns all production records for a given volume.

**Collection scope functions in `db_manager.py` (beta-2.9):**
- `get_collection_scope(case_folder, custodian_id)` — returns all scope entries for a custodian.
- `upsert_collection_scope(case_folder, custodian_id, source_name, status, justification, reviewed_by)` — creates or updates a collection scope entry with timestamp.
- `get_all_collection_scope(case_folder)` — returns all scope entries JOINed to `custodians` for the case.
- `seed_collection_scope(case_folder, custodian_id, source_names)` — bulk-inserts `Pending` scope entries for a list of data sources (uses `INSERT OR IGNORE`).

**Coding field functions in `db_manager.py` (beta-2.9):**
- `create_coding_field(case_folder, field_name, field_type, pick_list_json, created_by)` — inserts a new custom coding field.
- `get_coding_fields(case_folder)` — returns all coding fields ordered by `display_order, id`.
- `delete_coding_field(case_folder, field_id)` — cascading delete: removes all `document_coding` rows for the field, then the field itself.
- `get_document_coding(case_folder, control_number)` — returns a dict mapping `coding_field_id` → `value` for a document.
- `upsert_document_coding(case_folder, control_number, field_id, value, coded_by)` — creates or updates a single coding value with `ON CONFLICT DO UPDATE`.
- `get_all_coding_for_production(case_folder, control_numbers)` — bulk retrieval of coding values JOINed to field names for a list of control numbers. Used by production module (intentionally excluded from DAT export — work product).

**Exhibit functions in `db_manager.py` (beta-2.9):**
- `create_exhibit_set(case_folder, set_name, set_type, proceeding_date, case_caption, created_by)` — creates a new exhibit set.
- `get_exhibit_sets(case_folder)` — returns all exhibit sets for the case ordered by `created_at`.
- `update_exhibit_set(case_folder, set_id, **fields)` — updates specified fields on an exhibit set.
- `delete_exhibit_set(case_folder, set_id)` — deletes an exhibit set with scoped `PRAGMA foreign_keys = ON` to enable CASCADE deletion of child exhibits.
- `add_exhibit(case_folder, exhibit_set_id, control_number, exhibit_number, description, added_by)` — adds a document as an exhibit in a set.
- `get_exhibits(case_folder, exhibit_set_id)` — returns all exhibits in a set with JOINs to `documents` (for `file_name`, `custodian`) and to `document_productions` (for latest production Bates numbers), ordered by `sort_order`.
- `update_exhibit(case_folder, exhibit_id, **fields)` — updates specified fields on an exhibit.
- `remove_exhibit(case_folder, exhibit_id)` — deletes a single exhibit.
- `reorder_exhibits(case_folder, exhibit_set_id, ordered_exhibit_ids)` — bulk-updates `sort_order` for all exhibits in a set based on the provided ID ordering.
- `get_document_exhibit_sets(case_folder, control_number)` — returns all exhibit sets a document appears in (JOIN `exhibits` → `exhibit_sets`). Used by the Review coding panel to show exhibit badges.
- `get_next_sort_order(case_folder, exhibit_set_id)` — returns `MAX(sort_order) + 1` for appending new exhibits.

---

## 5. MODULE-BY-MODULE BREAKDOWN

### Entry Point: Home (`home.py`)
Case selector, user administration, audit log viewer. Admin-only sections gated behind `user_admin` permission.

- **Matter Profile Card:** 10-field case summary (matter name, matter number, client, court, case number, judge, opposing counsel, opposing firm, description, notes). Stored as a JSON blob in `case_settings` via `get_matter_profile()`/`set_matter_profile()`. Displayed as a read-only card with an edit expander.
- **Case Archive:** Generates a ZIP file containing `case.db`, all produced volumes, the defensibility report, and a `MANIFEST.json` with archive metadata (case folder, creation timestamp, file inventory). Downloadable via a button. Intended for long-term case preservation or transfer.
- **Issue Coding Fields:** Admin UI for managing custom coding fields (`coding_fields` table). Create new fields (picklist with custom choices, free text, or boolean). View existing fields with type badges. Delete fields (cascading to all `document_coding` entries). Fields appear in the Review coding panel for per-document issue coding.
- **Audit Log Viewer:** Admin-only expander (documented above in audit_log section).
- **Defensibility Report:** Generation button (gated: `production`).

### Module 1: Ingestor (`1_Ingestor.py`)
- Scans `<case_folder>/Ingest/` recursively.
- Computes MD5 hashes in parallel (ThreadPoolExecutor).
- Registers files in `documents` table with `processing_status='New'`.
- Calls `db_manager.init_db()` to ensure schema is current.
- Permission gate: `ingest`.

### Module 2: Processor (`2_Processor.py` + `processing_engine.py` + `_processing_worker.py`)

**Background worker architecture:** Processing runs as a detached subprocess (`_processing_worker.py`) launched via `Popen` with `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`. The worker calls shared logic in `processing_engine.py` (no Streamlit imports) and reports progress to the `jobs` table. The UI (`2_Processor.py`) polls the `jobs` table every 2s to render the job monitor. If subprocess launch fails, falls back to inline execution. Zombie PID detection via `GetExitCodeProcess` on Windows.

Three sequential phases:
- **Phase 1** — Container explosion: Recursively extracts containers (`New` status) → children registered in DB → repeat until none remain (50-pass circuit breaker). Containers promoted to `Container_Scanned`. PSTs extracted sequentially via `explode_pst_isolated()` — COM in main process (primary, with retry + 5s recovery delay) or libpff in isolated subprocess (fallback). ZIPs/EMLs use ThreadPoolExecutor. MSGs use batched COM via `process_msg_batch()` with cross-process mutex.
- **Phase 2** — Text extraction + metadata enrichment: Tika extracts content; stored in OpenSearch. Populates all enrichment columns (`mime_type`, `creating_application`, `extraction_method`, `word_count`, `is_encrypted`, `importance`, `sensitivity`, `conversation_topic`, `attachment_count`, `tika_metadata_json`). Native email metadata override for MSG/EML via `extract_msg_metadata()` / `extract_eml_metadata()`. MD5 exact-match dedup. OCR fallback via Tesseract. Marks `has_text=1`.
- **Phase 3** — Email imaging: Calls `universal_imager` to produce a PDF for each email. No COM dependency — uses `olefile` for MSG and Python `email` stdlib for EML.

**Cancel:** Worker polls `cancel_requested` flag in `jobs` table. UI sets flag via `db_manager.cancel_job()`. Worker finishes current item then stops cleanly. Logs `PROCESSING_CANCELLED`.

**SQLite contention:** `conn.commit()` before every `log_audit()` call to release write lock (log_audit opens a separate connection). NIST, standard docs, and duplicate container audit entries batched to single BULK entries instead of per-document to reduce lock contention.

Threading model: Worker threads write to a shared queue; a dedicated writer thread drains it to SQLite (avoids SQLite write contention from multiple threads). Processor has a configurable drain timeout. Permission gate: `process`.

### Module 3: Analytics (`3_Analytics.py`)
Nine tabs in two groups. Permission gate: `analytics`.

**Suppression Analytics:**
- **📧 Email Threading** tab (A1–A4): NetworkX directed graph. A1 builds graph via `message_id` → `in_reply_to` edges with `references_list` chain as additional edges. `_normalize_msg_id()` strips RFC 2822 angle brackets. Tags leaf nodes `'Inclusive'`, others `'Thread-Suppressed'` (cascades to attachment children). A4 subject-line fallback groups emails unreached by Message-ID within a 90-day window. Two-step: RUN → EXECUTE.
- **📑 Near-Duplicate Detection** tab: MinHashLSH over OpenSearch document content. Requires OpenSearch. Tags cluster principals `'NearDupe-Principal'`, others `'NearDupe-Suppressed'`. Respects family integrity — attachments preserved.
- **🔍 Dedup Report** tab (formerly `7_Dedup_Report.py`, merged v2.3): collection overview metrics, prose defensibility summary, suppression breakdown, exact duplicate clusters (top 200 MD5 groups), near-dupe cluster detail (top 200 families), Excel/CSV export. Also displays a **Clawback Summary** section.

**Exploratory Analytics (beta-2.7):**
- **👥 Communication Analysis** (B1): top communicators table, sender × recipient matrix, custodian summary.
- **📅 Timeline** (B2): email volume bar chart (Day/Week/Month), custodian filter, automated gap detection.
- **🌐 Domain Analysis** (B3): domain frequency, Internal/External classification, top domain-to-domain pairs.

**Exploratory Analytics (beta-2.9):**
- **👥 Custodian Overlap** (B4): Cross-custodian content overlap matrix. Computes `content_hash` intersection between every custodian pair. Plotly heatmap visualization showing percentage of shared documents. Helps identify custodians with redundant collections.
- **💡 Concept Explorer** (B5): Keyword expansion tool using OpenSearch `significant_text` aggregation. Given a seed term, identifies statistically significant co-occurring terms in matching documents — surfaces related concepts the reviewer may not have considered. Graceful degradation if the `significant_text` aggregation is unavailable on the installed OpenSearch version.

- Both suppression analyses are one-time operations with re-run capability hidden behind an expander warning.
- Analytics MUST run after all documents are processed (not mid-ingestion).

### Module 4: Review (`4_Review.py`)
Two top-level views gated by a radio selector at page top. Permission gate: `review`.

**📋 Review Grid view** (default):
- Full-text search via OpenSearch with Boolean/fuzzy/wildcard/field-scoped syntax. Pre-validation regex prevents 400 errors.
- Column filter row above each grid column (SQL WHERE). Dynamic column picker (gated: `column_picker`).
- Document navigator sidebar tree: party → volume/custodian.
- **Family View:** Container-origin parents (PST/ZIP with `Container_Scanned` status) excluded from grid. Emails extracted from PSTs form email → attachment families. Ghost-parent groups render sub-family nesting.
- **Peek Navigation:** Family links (parent/child buttons) whose target is filtered out of the current search load the document directly in the viewer without modifying the grid. "← Back to queue" returns to original position. Chained peeks preserve original return index. Grid clicks and Save & Next exit peek mode.
- **Show Full Family:** Button in Family panel replaces grid with all documents sharing the same `group_id`, bypassing search/column/display filters. "← Back to search results" banner restores prior state via deferred `_pending_search_restore` pattern. Banner renders outside empty-results guard so users are never trapped.
- PDF viewer: server-side rendering via PyMuPDF pixmaps — all pages stacked in a scrollable container with page dividers ("— Page N of M —") and theme-aware styling. Replaced iframe base64 embedding (which failed on complex DocuSign PDFs). Three viewer tabs: 📄 Native/Image, 📝 Extracted Text (STR highlighting via `re.sub` + `<mark>` tags), 📦 Production (Bates-stamped final).
- **Produced PDF Download:** download button for Bates-stamped produced PDFs (gated: `download_produced`). Logs `PRODUCED_DOWNLOAD`.
- Tag panel: configurable tag categories with color coding. Tags written to `documents.tags`. **Tag cascade to attachments:** applying/removing/clearing tags on parents cascades to children via `_cascade_tag_to_children()`. System tags (`NearDupe-*`, `Thread-*`, `NIST-*`, `Junk`, `Inclusive`) preserved on children.
- Comment panel: free-text notes per document.
- Saved searches: recent history (auto-logged, 10-deep) + named saves, optionally global (gated: `saved_search_global`). Personal searches always available (gated: `saved_search_personal`).
- Bulk Action Bar: appears when 2+ rows selected → mass tag/clear/CSV export/ZIP PDF package.
- Bates Batch Engine: parses dirty multiline interrogatory citations, expands ranges, filters grid. Micro-PDF extraction: isolates specific pages into single-page PDFs in a ZIP.
- Bates Lookup: `🔎 Bates Lookup` sidebar expander resolves any Bates number (internal or inbound) to control number + metadata.
- **Review Batching:** `📦 Review Batches` sidebar expander (Manager+). Auto-split creation using family-aware LPT algorithm (groups by `group_id`, balances by doc or page count). Batch list with progress %, per-batch assignment to reviewers. Manual editing (move docs between batches). Delete all batches. Batch filter radio toggle above search bar (defaults to assigned batch for Reviewers, All Documents for Managers). WHERE clause injection stacks with all existing nav/search filters. Progress banner above grid when viewing a batch. Auto-status update (In Progress / Complete) after each review.
- **Reviewed — Next workflow:** "Reviewed — Next ▶" button writes `reviewed_by` and `reviewed_at` (explicit review determination). Plain "Save" preserves tags only (work in progress — does NOT stamp reviewed_by). Progress tracking uses `reviewed_by IS NOT NULL`.
- Mass PDF Export: `pdf_exporter.py` builds ZIP archives of full document PDFs (gated: `export_pdf`).
- Export CSV gated to `export_csv`.
- **⚠️ Clawback panel**: displayed in the document sidebar after the tag panel. Shows a colored status badge when active. Respects `_case_closed` gate.
- **Exhibit Designation:** Badge display in the coding panel showing which exhibit sets the current document belongs to (via `get_document_exhibit_sets()`). "Mark as Exhibit" expander for produced documents — lets reviewers add the document to an exhibit set with an exhibit number and description. Permission gate: `mark_exhibit` (Reviewer+).
- **Production History:** Expander in the document detail panel showing all production events for multi-production documents (via `get_document_productions()`). Displays volume, Bates range, date, and production type for each entry.
- **Home Production History grid (asymmetric Flag #13 fix, beta-2.14 Commit 10):** Home dashboard's outbound production history grid (`home.py:553-569`, paralegal-visible) renders ALL outbound runs including `status='aborted'`, with a `Status` column and `fillna('—').replace({None: '—'})` on Bates fields so aborted runs surface cleanly with `—` placeholders. The court-facing defensibility report's section 6.2 (`defensibility_report.py:705-714`) filters `status='aborted'` rows out before HTML iteration — internal process churn excluded from opposing-counsel-facing artifacts. Asymmetric scope is intentional per attorney decision.
- **Re-Image Document:** `_reimage_document()` helper (Manager+, emails only). Calls `universal_imager` to regenerate the PDF image for a document. Resets `reviewed_by`/`reviewed_at` and `redaction_status` (review state reset). Available via a `🔄 Re-Image This Document` expander in the document panel.
- **Custom Coding Fields:** Per-document picklist/text/boolean fields defined via `coding_fields` table (Admin creates in home.py). Rendered in the coding panel below tags. Values stored in `document_coding` junction table via `upsert_document_coding()`. Intentionally excluded from production DAT/CSV exports (attorney work product).
- **Reviewer Notes:** Per-document, per-user free-text notes via `document_notes` table. Each reviewer sees their own note with create/edit/delete capability via `upsert_document_note()`/`delete_document_note()`.
- **Confidentiality Designation:** Override selector for `documents.confidentiality_designation` column. Allows reviewers to stamp confidentiality levels on documents during review.
- **Document visibility** applied: `produced_only` users only see produced docs; `hidden_tags` users have matching docs filtered out.

**📊 Search Term Reports view** (gated: `str_run`; via radio; `st.stop()` prevents Review Grid from rendering):
- Formerly `6_STR.py`. All variables/keys prefixed `_str_`.
- CSV or manual term entry → batch OpenSearch `query_string` execution → hit-count summary.
- Per-term document preview with custodian/date metadata.
- Excel export (2 sheets: STR Summary + Hit Documents, gated: `str_export`) and CSV export.
- Terms cached in `st.session_state['active_str_terms']` (plain-text only); wired to Review Grid's Extracted Text tab yellow highlight feature.
- Results respect `doc_visibility` mode.

**✏️ Redact tab** (4th tab inside the document viewer panel — Reviewer+ role):
- `10_Redaction.py` was deleted in v2.3. Redaction lives in the document viewer as tab 4.
- Layout: Two-column `[3, 7]`: control panel (nav bar ◀ text_input / N ▶, Draw/Select radio, per-box reason selectors, Save/Clear buttons) | canvas (`st_canvas` with PDF page background). Canvas renders first so its result is available to the control panel.
- Canvas init: `🖊️ Load Redaction Canvas` checkbox (key: `enable_redact_{cn}`, no page index). Required because `st_canvas` React component does not display `background_image` on first mount without user-triggered rerun.
- DPI: `max(36, int(1000 * 72 / page_width_pt))` — targets 1000px canvas width (~105 DPI for letter pages).
- Background image: PIL Image stored in `st.session_state[f"_redact_bg_{cn}_{page_idx}"]`.
- Per-box privilege reasons from tag category system. Custom reason via sentinel `_REDACT_CUSTOM`.
- On Save: writes `marks_json` to `redaction_marks`; writes `add_redact_annot()` to PDF on disk; calls `_r_sync_tags()` to sync `documents.tags` privilege subset to current mark reasons.
- `apply_redactions()` NOT called here — content destruction is Production-only.
- Helper functions in `4_Review.py`: `_r_write_page_annotations()`, `_r_write_all_annotations()`, `_r_sync_tags()`.

### Module 5: Production (`5_Production.py`)
Three tabs. Permission gate: `production`.

**📦 Outbound Production tab** (original `5_Production.py` content):
- **Production Mode Toggle:** Simple Production (Bates stamps + natives with privilege/redaction logs, no text files or load files) vs Full EDRM Production (complete deliverable with text extraction, OCR, load files).
- Grid of processed, unproduced **internal** documents. Inbound productions (source_party != 'Internal') are excluded unconditionally via the mandatory `db_manager.OUTBOUND_SOURCE_FILTER_SQL` filter — no user-toggleable "exclude external" checkbox (removed beta-2.10 Commit 3 for defensibility). Remaining user-toggleable filters: exclude previously produced, suppressed, non-responsive, clawback-demanded.
- **Three output formats:** PDF (standard), TIFF (300 DPI), Native Only (original files renamed to Bates numbers with slip-sheet placeholders; redactions not applicable).
- **Deferred Parallel OCR:** Text extraction captures pixmaps inline during Pass 2 loop; Tesseract OCR runs in parallel ThreadPoolExecutor after sequential assembly completes. Progress bar + per-document error reporting. Eliminates OCR blocking of Bates/stamp/move operations.
- **Clawback filter** — "Exclude Clawback-Demanded" checkbox (default on), hard-blocking clawed-back documents.
- **Supplemental Production** — "🔗 Continue from Last Production" toggle. Auto-populates prefix and starting number from `last_bates_info`. `db_manager.save_last_bates_info()` called after every successful run.
- **Container skip** — PST/ZIP/RAR/7Z files and `Container_Scanned` documents automatically skipped to prevent Bates consumption.
- Manual selection or auto-select by tag. Family-aware Bates assignment (BEGDOC/ENDDOC/BEGATT/ENDATT contiguous).
- Burns redaction annotations: calls `apply_redactions()` only at production time. Saves to swap file (`.redacted`) then atomically replaces temp PDF.
- **Junction table writes:** Production now writes to `document_productions` junction table instead of (or in addition to) the flat `documents` columns. Each production run creates one row per document in the junction table with volume, Bates range, page count, timestamp, and production type. `refresh_production_cache()` syncs flat columns for backward compatibility. Gap analysis queries the junction table.
- **Custom coding exclusion:** Custom coding field values (from `document_coding` table) are intentionally excluded from DAT/CSV load files — they represent attorney work product and must not appear in deliverables.
- Output: renamed PDFs + LOADFILE.csv + LOADFILE.DAT (Concordance) + IMAGES.OPT (Opticon). PRIVILEGE_LOG.csv in output.
- Configurable Bates prefix, starting number, padding, format, endorsement stamp.
- **Cancel button:** overlay cancel button aborts mid-run; deletes partial volume folder to prevent orphaned Bates. Logs `PRODUCTION_CANCELLED`.
- **Stale-production detector:** On page load, scans `Productions/` for files/folders prefixed `TEMP_` or `STAGED_` (orphans from abandoned Pass 1 runs). If found, shows a warning banner with affected volumes and a "Clean Up Orphaned Files" button (Manager+). Logs `PRODUCTION_STALE_CLEANUP`.
- **IMAGING_WORKERS config setting:** `config.py` / `config.example.py` `IMAGING_WORKERS` integer — default parallel worker count for Pass 1 imaging. `0` = auto-detect (`min(4, cpu_count-1)`). Production UI slider reads this as its initial value.
- **Timing metrics:** `elapsed_seconds` on `PRODUCTION_RETRY` (retry phase duration); `pass2_elapsed_seconds` on `PRODUCTION_EXPORTED` (Pass 2 duration). Complements existing Pass 1 timing on `PRODUCTION_CREATED`.
- Warning banner if selection > 9,500 docs (approaching OpenSearch `max_result_window`).

**📥 Inbound Productions tab** (formerly `8_InboundProd.py` — gated: `inbound_production`; all variables prefixed `_ib_`):
- Receives opposing counsel productions via DAT/CSV load file.
- Configurable delimiter (default `\x14` Concordance) and quote char (default `þ`). Pandas `read_csv()` with malformed row handling.
- Column mapping UI: each load file column → system field dropdown. Unmapped columns → `dynamic_metadata` JSON blob.
- Source party name + production volume label.
- Existing productions listing with purge UI (type DELETE to confirm).
- All docs tagged `source_party` + `production_volume`; analytics scoped to `source_party = 'Internal'`.

**📋 Privilege Log tab** (formerly `9_Privilege_Log.py` — gated: `privilege_log`; all variables prefixed `_pl_`):
- Queries `documents` table for privilege-tagged records.
- `_PL_ABBREV_MAP` + `_pl_fuzzy_match_privilege_reason()` — normalizes reviewer shorthand (`AC`, `WP`, `ACP`, `CI`, `AC/WP`, `A-C`) to canonical descriptions via word-boundary regex (longest-first).
- Privilege basis override selector + "Include Needs Review" toggle.
- 3-metric summary: Total Privileged / With Bates / Not Yet Produced.
- CSV + Excel export. Audit: `PRIVILEGE_LOG_EXPORTED`.
- **Privilege Log QC Editor** (Manager+, `privilege_log` permission): Built-in editor that replaced the earlier standalone page concept. Filterable grid with disposition, custodian, privilege basis, and date range filters. 6-metric summary bar (total privileged, withheld, redacted, needs disposition, redaction marks, applied). "Show only Needs Disposition" quick filter. Configurable column picker (19 available columns). Excel export.

### Module 6: Sync (`6_Sync.py`)
- **Search Index Maintenance** (Admin-only): SQLite vs OpenSearch document count comparison with delta warning. "Rebuild Search Index" button with confirmation dialog, progress bar, and audit logging (`SEARCH_INDEX_REBUILT`). Uses `os_manager.reindex_from_sqlite()` — rebuilds OS index from SQLite metadata without reprocessing source files; preserves existing content text via bulk scan before rebuild.
- Filevine document sync engine (subdomain configured via `FILEVINE_SUBDOMAIN` in `config.py`).
- Push: `POST /core/documents` → create → pre-signed S3 URL → PUT → finalize → store `filevine_doc_id`.
- Pull-back: query modified docs → download to `Reviewed/` → scan for `PDF_ANNOT_REDACT` → update `redaction_status`.
- Resilience: exponential backoff on HTTP 429/500/502/503. Token expiration → flag for re-sync.

### Module 7: Custodians (`7_Custodians.py`)
Permission gate: `custodian_management` (Manager+). Case lifecycle gate: closed = read-only.

- **Custodian Inventory Chart:** Plotly horizontal bar chart showing doc count per custodian, colored by hold status (green=Active, gray=None, orange=Released, red=Expired).
- **Custodian Detail Panel:** Profile editing (title, department, email, notes, data sources multiselect). Collection summary metrics (doc count, email count, date range). Save with `CUSTODIAN_UPDATED` audit.
- **Operations Tabs:**
  - **Rename:** Updates `documents.custodian` + `custodians.name` + `hold_documents.custodian_name` + renames `Hold_Documents/` subfolder. Audit: `CUSTODIAN_RENAMED`.
  - **Merge:** Type-to-confirm safety. Moves documents + hold files to target. Deletes source custodian record. Warns about active holds. Audit: `CUSTODIAN_MERGED`.
  - **Reassign:** Three selection methods (control number list, file extension, date range). Audit: `CUSTODIAN_REASSIGNED`.
  - **Collections:** Rename source_collection, assign collection to unorganized docs. Audit: `COLLECTION_RENAMED` / `COLLECTION_ASSIGNED`.
  - **📋 Collection Scope:** Per-custodian, per-data-source status tracking. Each source has a status (`Pending`/`Collected`/`Searched-No-Hit`/`Not-Reasonably-Accessible`/`Out-of-Scope`) and a justification field. Status values documented for defensibility (e.g., why a source was deemed out of scope). Uses `collection_scope` table via `upsert_collection_scope()`, `get_collection_scope()`, `get_all_collection_scope()`, `seed_collection_scope()`. Data sources seeded from the custodian's `data_sources` multiselect.
- All modify operations show OS reindex warning.
- **Legal Hold Tracking:**
  - Hold status card with color-coded display.
  - Timeline form: issued/acknowledged/released dates, notice method, recipient, notes. Save with `HOLD_STATUS_CHANGED` audit.
  - Hold document upload to `Hold_Documents/{custodian}/` (completely separate from case ESI). Type selector, duplicate filename handling. Audit: `HOLD_DOCUMENT_UPLOADED`.
  - Document list with type badges, download buttons, two-click delete. Audit: `HOLD_DOCUMENT_DELETED`.
- **Case Hold Summary:** Metrics (active/released/unacknowledged/total) + Plotly Gantt-style hold timeline chart.

### Module 9: Inbound Productions (`9_InboundProduction.py`)
Permission gate: `production`. Case lifecycle gate: closed = form hidden with muted caption; purge button disabled.

- **Extracted from** `5_Production.py` tab_inbound in beta-2.10 Commit 6 as a 424-line lift. Motivation: outbound production's phase-gating `st.stop()` was locking inbound ingest out during Pass 1 checkpoint state; extraction made inbound workflow-independent.
- **Registered in** `auth_manager._NAV_PAGES` as tuple `("pages/9_InboundProduction.py", "📨 Inbound Productions", "production")` — added in Commit 7.7 after the extraction missed the registry update. Smoke test `tests/test_nav_registry_consistency.py` now pins the registry-filesystem contract.
- **Flow:** Load File (.dat/.csv) → Column Mapping → Auto Image Discovery → Row Processing → `production_runs` row (`direction='inbound'`, `status='finalized'`) → Documents in Review.
- **Input validation:** `db_manager.validate_inbound_production_identifiers(source_party, production_volume)` rejects empty/whitespace inputs, inputs containing the reserved ` - ` composite-name delimiter, and inputs > 100 chars.
- **Production run recording:** Non-blocking contract — documents table is primary provenance, `production_runs` is secondary history. Narrow `except sqlite3.Error` guard with user-facing warning + recovery instructions.
- **Purge utility:** `db_manager.purge_inbound_volume(case_folder, source_party, production_volume)` performs atomic 3-op transaction (SELECT os_ids + DELETE docs + DELETE production_runs row) with rollback on any failure.
- **Audit events:** `INBOUND_INGESTED` (per-document) and `INBOUND_PRODUCTION_RECORDED` (per-volume with settings JSON). Distinct from the outbound `PRODUCTION_*` family.
- **Isolation:** Inbound docs tagged `source_party` + `production_volume`; threading/near-dupe scoped to `source_party='Internal'`; outbound production queries filter via `db_manager.OUTBOUND_SOURCE_FILTER_SQL`; history displays (home, defensibility §6.2, archive manifest) filter `production_runs` by `direction='outbound'` (beta-2.10 Commit 7.6 fix).

### Module 8: Exhibits (`8_Exhibits.py`)
Permission gates: `view_exhibits` (Reviewer+), `mark_exhibit` (Reviewer+), `manage_exhibit_sets` / `manage_exhibits` / `export_exhibit_binder` (Manager+). Case lifecycle gate: closed = read-only.

- **Exhibit Set Management:** CRUD for exhibit sets (Deposition/Motion/Hearing/Trial types). Each set has a name, proceeding type, proceeding date, and case caption. Uses `create_exhibit_set()`, `get_exhibit_sets()`, `update_exhibit_set()`, `delete_exhibit_set()`.
- **Exhibit List:** Ordered list of exhibits within a set showing exhibit number, description, control number, file name, custodian, and latest production Bates range (via JOIN to `document_productions`). Drag-to-reorder via `reorder_exhibits()`. Remove individual exhibits via `remove_exhibit()`.
- **Add Document Search:** Search interface scoped to produced documents only. Lets the user find and add documents to the current exhibit set with an exhibit number and description. Uses `add_exhibit()` and `get_next_sort_order()` for auto-positioning.
- **Binder PDF Export:** Generates a single PDF combining all exhibits in a set. Built with pdfkit (wkhtmltopdf) for cover page, table of contents/index page, and exhibit divider pages, plus PyMuPDF (`fitz`) for merging the actual produced document PDFs. Output is a downloadable PDF file.

### Defensibility Report (`defensibility_report.py`)
Standalone module — no Streamlit dependency. Called from `home.py` (gated: `production`).

- **9-section court-ready PDF** via pdfkit/wkhtmltopdf:
  1. Executive Summary (metrics: total docs, custodians, net reviewable, produced, dedup reduction)
  2. Collection & Ingestion (custodian breakdown, file type distribution, record types)
     - **2.2 Collection Scope & Justification** — pulls from `collection_scope` table via `get_all_collection_scope()`. Documents per-custodian, per-source collection decisions and justifications for defensibility.
  3. Processing Protocol (status breakdown, extraction methods, encrypted docs, OCR usage)
  4. Deduplication Methodology (4-layer narrative: MD5, SHA-256, MinHash, threading; suppression waterfall)
  5. Review Summary (completion %, tag distribution, reviewer activity, responsive/not responsive)
  6. Production Summary (volumes with Bates ranges, Bates certification, clawback section)
     - **Production Detail by Type** — queries `document_productions` junction table to break down production volumes by `production_type` (Original/Supplemental/Replacement) with dates and document counts.
  7. Privilege Handling (withheld/redacted metrics, no-disposition warning)
  8. Audit Trail Summary (event counts by type/user, date range)
  9. Legal Hold Tracking (hold metrics, unacknowledged warning, custodian status table)
  - Appendix A: Processing Errors (capped at 500)
- Professional legal formatting: serif fonts, navy headers, alternating row colors, page breaks, "Privileged & Confidential" cover stamp.
- `SYSTEM_TAGS` constant excludes system-generated tags from review completion calculation.
- `_fmt_date()` helper formats ISO timestamps to readable dates.
- **Audit Trail PDF Export:** `generate_audit_export_pdf()` produces landscape PDF with filter criteria documentation, repeating headers, and confidential stamp.

---

## 6. TAG CATEGORY SYSTEM

Defined in `db_manager.py` as `DEFAULT_TAG_CATEGORIES`. Stored per-case in `case_settings` as JSON.

Default categories:
- **Privilege** (`is_privilege: true`, color: red) — Attorney-Client Privilege, Work Product, Attorney-Client Privilege and Work Product, Common Interest Privilege, Joint Defense Privilege, Trade Secret, Marital Privilege, Fifth Amendment, Settlement Privilege (FRE 408), Self-Critical Analysis Privilege, Executive / Deliberative Process Privilege, Relevance Objection.
- **Responsiveness** (`is_responsive: true`, color: green) — Responsive, Not Responsive, Hot Document.
- **Review Status** (color: blue) — Needs Review, Suppressed.

The Redaction module reads privilege categories from this same system to populate the per-box reason dropdown. When marks are saved or cleared, `_sync_document_tags()` replaces the document's privilege tags with exactly the set of reasons currently on its redaction marks — no orphaned privilege tags can persist after marks are removed.

---

## 7. LIBRARIES USED AND REJECTED

### In Use

| Library | Purpose | Notes |
|---------|---------|-------|
| `streamlit` | UI framework | Pinned for canvas compatibility |
| `streamlit-drawable-canvas` | Redaction drawing UI | Manually patched for Streamlit 1.55 |
| `PyMuPDF (fitz)` | PDF render, annotate, write | Primary PDF engine |
| `sqlite3` | Database | stdlib, WAL mode |
| `opensearchpy` | OpenSearch client | Security disabled locally |
| `tika` | Text extraction | Java server, port 9998 |
| `pandas` | Data manipulation | Used throughout |
| `networkx` | Email threading graph | |
| `datasketch` | MinHash near-dupe | |
| `olefile` | MSG binary parsing | For imaging (not extraction) |
| `compressed_rtf` | MSG RTF body decompression | |
| `email` (stdlib) | EML parsing | For imaging |
| `win32com.client` / `pythoncom` | COM automation | Office formats where LibreOffice insufficient |
| `python-dateutil` | Date parsing | Flexible ISO/RFC date handling |
| `PyYAML` | Auth config | |
| `python-docx` / `mammoth` | DOCX fallback imaging | When LibreOffice unavailable |
| `pdfkit` | HTML→PDF conversion | Defensibility report + audit trail PDF export |
| `plotly` | Interactive charts | Dashboard funnel/donut, analytics waterfall/heatmap/timeline/bars, custodian inventory, hold Gantt |
| `Pillow (PIL)` | Image processing | |
| `pytesseract` | OCR fallback for image-only PDFs | Wraps Tesseract; triggered automatically when Tika returns no text; path configured via `TESSERACT_PATH` in `config.py` |
| `libpff-python` (pypff) | PST extraction fallback | Optional; used only when Outlook COM unavailable; runs in isolated subprocess to contain C-level state corruption; imported inside `explode_pst_libpff()` only; LGPL v3 |

### Explicitly Rejected / Avoided

| Library / Tool | Reason Rejected |
|---------------|----------------|
| **Elasticsearch** | Replaced with OpenSearch — same API, no licensing restrictions. Elastic's licensing changed (SSPL) making it unsuitable for this use case. |
| **win32com for EML imaging** | COM automation requires Outlook installed and causes file lock/threading issues in multiprocess environments. Replaced with native Python `email` module. |
| **win32com for MSG imaging** | Same COM issues. Replaced with `olefile` + `compressed_rtf` for direct binary parsing. |
| **`extract-msg` for imaging** | `extract-msg` is designed for extraction/parsing, not rendering. Produces incomplete output for imaging purposes. `olefile` gives direct access to the RTF body needed for PDF conversion. |
| **Relativity / Everlaw / etc.** | Cost. This project exists to replace them. |
| **`apply_redactions()` during review** | Permanently destroys PDF content — must be deferred to production burn step only. Redaction module only writes annotations. |
| **Burning to download (client-side)** | Was originally a "Burn & Download" button in the Redaction module. Removed — production module handles all burning. Download-before-production creates uncontrolled copies. |
| **Global redaction reason** | Original design had one privilege reason for all boxes on a page. Replaced with per-box individual reason assignment at draw time. |
| **Third-party PDF redaction review** (Filevine/Google Drive) | Original plan to push PDFs out to Filevine/Google Drive for external redaction, then pull back. Abandoned in favor of in-platform redaction module. Filevine sync still exists for document review but not for redaction workflow. |

---

## 8. KEY ARCHITECTURAL DECISIONS

### "Forever Schema" approach
The `documents` table is designed as the final schema from the start. New columns are added via `ALTER TABLE` migrations, never by dropping and recreating. The table includes columns for features not yet fully implemented (e.g., `byos_pushed_at`, `language`). This prevents data loss when upgrading existing case databases.

### No ORM
All database access is raw SQL via `sqlite3`. No SQLAlchemy or similar. The schema is simple and well-understood; an ORM adds complexity without benefit here.

### Tika as a service (not in-process)
Tika runs as a persistent local server rather than being invoked per-file. This avoids JVM startup overhead on every extraction and allows the Python app to restart without losing the Tika process.

### OpenSearch is optional at runtime
The Review and Analytics modules degrade gracefully when OpenSearch is unavailable (full-text search is disabled, near-dupe is disabled). The Processor can run Phase 1 (text extraction) and Phase 2 (dedup) without OpenSearch if needed — though indexing to OpenSearch is the normal path.

### Redaction annotations are non-destructive until production
`add_redact_annot()` marks are visible black boxes in any PDF viewer, but the underlying text is preserved until `apply_redactions()` is called. This allows review of redacted pages in the Review module without locking content prematurely.

### Tag coupling to redaction marks
Privilege tags on a document must exactly reflect its current redaction marks. `_sync_document_tags()` is called on every save and every clear operation. It derives the authoritative tag set from the DB marks, not the UI state. This prevents a lazy reviewer from removing redaction boxes but leaving privilege tags that would incorrectly exclude documents from production.

### Windows-first
The platform runs on Windows (primary machine is Windows 11 Pro). COM automation is available for Office formats where needed. File paths use `os.path.join()` throughout for portability, but some features (win32com) are Windows-only.

### config.py is machine-local
`config.py` is gitignored. `config.example.py` is the template. This keeps absolute paths (Tika JAR, OpenSearch home, cases root) off the repository.

---

## 9. PLANNED WORK (ROADMAP)

### Completed ✅

- ~~Fix Processor TypeError~~ — `get_meta_str()` guards against nested list Tika metadata (v2.3)
- ~~Fix audit_log schema~~ — Full schema + `log_audit()` / `log_audit_batch()` in `db_manager.py`; all modules wired; Admin audit viewer on `home.py` (v2.2)
- ~~PST container support~~ — `explode_pst_isolated()` in `container_exploder.py`; libpff primary, COM fallback (v2.2→2.9)
- ~~Centralize hardcoded paths~~ — `WKHTMLTOPDF_PATH`, `TESSERACT_PATH`, `FILEVINE_SUBDOMAIN` in `config.py` (v2.3)
- ~~Merge Redaction into Review~~ — `10_Redaction.py` deleted; ✏️ Redact tab in `4_Review.py` (v2.3)
- ~~OCR pipeline~~ — `pytesseract` automatic fallback in Processor when Tika returns no text (v2.3)
- ~~Mass PDF Export~~ — `pdf_exporter.py` + bulk action ZIP in Review (v2.3)
- ~~Module consolidation~~ — sidebar reduced from 10 → 6 pages; STR/Dedup/InboundProd/PrivLog merged into parent modules (v2.3)
- ~~Production burn step~~ — `apply_redactions()` called in `5_Production.py` at production time only
- ~~Filevine subdomain configuration~~ — now in `config.py`

### beta-2.4 Sprint ✅

1. ~~**PROJECT_CONTEXT.md overhaul**~~ — ✅ done
2. ~~**Case Lifecycle Status**~~ — ✅ `get_case_status()`/`set_case_status()` in `db_manager.py`; sidebar badge + Manager+ selectbox + `CASE_SETTING_CHANGED` audit in `home.py`; `st.stop()` guard on write-only pages (1,2,5,6); `_case_closed` flag + per-operation guards on mixed-access pages (3,4)
3. ~~**Bates Range Gap Detection**~~ — ✅ `🔍 Validate Production` expander in `5_Production.py` outbound tab; numeric sort per volume; CSV export
4. ~~**Inbound Bates Cross-Reference Lookup**~~ — ✅ `🔎 Bates Lookup` sidebar expander in `4_Review.py`; Go-to-CN grid filter injection
5. ~~**bcrypt password hardening**~~ — ✅ `auth_manager.py`; `_verify_password()` dual-format; transparent re-hash on login
6. ~~**Phase 9 External Annotation Reconciliation**~~ — ✅ `ABBREV_MAP`, `PDF_ANNOT_REDACT` parsing, fuzzy subject→privilege matching, reconciliation UI present in `6_Sync.py`

### beta-2.6 Sprint ✅

1. ~~**Automated Test Suite**~~ — ✅ `tests/` directory; `conftest.py` + 4 test modules (69 tests); `pytest` headless (no Streamlit/Tika/OpenSearch required). Covers schema, audit, case status, clawback, Bates math, auth, user CRUD, ZIP/EML extraction.
2. ~~**Clawback / Inadvertent Disclosure Workflow**~~ — ✅ `clawback_status`/`clawback_date` columns added; `mark_clawback()` + `get_clawback_summary()` in `db_manager.py`; clawback panel in `4_Review.py` (Manager+); hard filter in `5_Production.py`; dashboard in `3_Analytics.py`.
3. ~~**Supplemental Production**~~ — ✅ `last_bates_info` JSON in `case_settings`; `get_last_bates_info()`/`save_last_bates_info()` in `db_manager.py`; "Continue from Last Production" toggle in `5_Production.py`.
4. ~~**PST via libpff**~~ — ✅ `explode_pst_libpff()` + `_walk_pst_folder_libpff()` + `_libpff_message_to_eml()` added as fallback backend; `_WIN32COM_AVAILABLE` flag guards COM imports. Architecture refined in beta-2.8: COM primary (main process), libpff fallback (isolated subprocess).

### beta-2.7 Sprint ✅

1. ~~**Permission-Based Access Control**~~ — ✅ `has_permission()` / `require_permission()` system; role-permissions YAML with custom roles + `inherits`/`additional`; Admin UI checkbox grid; all gate points migrated from role-level to permission checks; Expert Reviewer role added; document visibility modes (`full`/`produced_only`/`hidden_tags`).
2. ~~**Metadata Enrichment**~~ — ✅ 13 new columns populated from Tika and native extractors; `tika_metadata_json` stores raw metadata; `extraction_method` tracked; native email metadata override for MSG/EML.
3. ~~**New Analytics Tabs**~~ — ✅ Communication Analysis (B1), Timeline (B2), Domain Analysis (B3), Subject-Line Fallback Threading (A4).
4. ~~**Cancel Buttons**~~ — ✅ Overlay cancel button for Processor (Phase 2) and Production via `ui_utils.show_overlay_cancel_button()`.
5. ~~**Tag Cascade**~~ — ✅ Tag apply/remove/clear cascades to attachment children; system tags preserved.
6. ~~**Family View Improvements**~~ — ✅ Container parents excluded; ghost-parent sub-family nesting; PST-extracted emails form own families.
7. ~~**Native Only Production**~~ — ✅ Third output format option; slip-sheet placeholders.
8. ~~**MSG Address Fix**~~ — ✅ Full sender address from `PR_SENDER_NAME` + `PR_SENDER_EMAIL_ADDRESS`; To/CC/BCC from transport headers (stream 007D).
9. ~~**CID Inline Image Leak Fix**~~ — ✅ Synthetic CID for `PR_ATTACH_FLAGS` bit 2 attachments without `PR_ATTACH_CONTENT_ID`.
10. ~~**Produced PDF Download**~~ — ✅ Download button for Bates-stamped PDFs in Review; gated to `download_produced` permission.

### beta-2.8 Sprint ✅

1. ~~**PST Extraction Reliability**~~ — ✅ libpff attachment count guard for corrupted local descriptors; `pst_file.close()` protection; extraction validation with expected-vs-actual counts per folder; `Partial_Extraction` status; re-extract UI with ScanPST integration.
2. ~~**Embedded Message Extraction**~~ — ✅ Embedded MAPI messages (`PR_ATTACH_METHOD=5`) recursively converted to EML in libpff path; `message/rfc822` nested emails handled in `_explode_eml()` with `_walk_mime_parts()` to prevent duplicate extraction.
3. ~~**COM Mutex**~~ — ✅ Cross-process named mutex (`Global\DIYeDiscovery_OutlookCOM`) serializes Outlook COM access for MSG batch extraction across Streamlit sessions.
4. ~~**Subprocess-Isolated PST Extraction**~~ — ✅ Each PST extracted in its own `multiprocessing.Process` to prevent libpff C-level state corruption cascade. PSTs processed sequentially in Processor; ZIPs/EMLs remain in ThreadPoolExecutor.
5. ~~**COM-Primary PST Extraction**~~ — ✅ `_explode_pst_com()` + `_walk_pst_folder_com()` added; COM runs in main process (requires desktop session context); libpff demoted to subprocess fallback. Retry with 5s recovery delay between attempts; aggressive COM object cleanup; non-essential folder skip (Deleted Items, Calendar, Contacts, etc.).
6. ~~**Privilege Disposition System**~~ — ✅ Two-pass production; privilege disposition column in Review grid.
7. ~~**Codebase Audit Bug Fixes**~~ — ✅ Resource leak fixes (try/finally on all fitz.open), TOCTOU race elimination (atomic ThreadSafeSet.check_and_add for dedup), Bates range sort correction (numeric vs string comparison).
8. ~~**XFA-Aware PDF Flattening**~~ — ✅ `flatten_pdf()` detects XFA forms before stripping; XFA pages rasterized at 200 DPI while normal pages keep text selectability.
9. ~~**Server-Side PDF Rendering**~~ — ✅ Replaced all 3 iframe `data:application/pdf;base64` embeds in Review with PyMuPDF pixmap rendering. Scrollable multi-page viewer with page dividers, theme-aware CSS variables, progress bar for large docs.
10. ~~**RTF De-encapsulation Fix**~~ — ✅ `\par` regex was matching inside `\pard`, leaving orphan chars in rendered email PDFs. Created shared `_scrub_rtf_from_html()` helper stripping 50+ RTF control word families.
11. ~~**Module Hardening Sprint 1**~~ — ✅ Extracted 9 shared OLE helpers to module level (eliminates "fix it twice" duplication); added logging to 25+ bare `except: pass` blocks across 4 modules; named constants for magic numbers.
12. ~~**Dedup Hardening**~~ — ✅ Pre-seed `seen_md5s` from prior processing runs (cross-batch dedup). Content-hash (SHA-256) dedup layer. Duplicate filters updated to `NOT LIKE 'Duplicate%'` across Review/Sync/Analytics.
13. ~~**Deferred Parallel OCR**~~ — ✅ Production OCR post-pass with ThreadPoolExecutor; captures pixmaps inline, runs Tesseract in parallel after sequential assembly.
14. ~~**Production Mode Toggle**~~ — ✅ Simple vs Full EDRM production mode selector.
15. ~~**OpenSearch Payload Fix**~~ — ✅ Renamed `filename`→`file_name`, `subject`→`email_subject`; added `source_party` and `production_volume` to OS payload. Reindex utility in `os_manager.reindex_from_sqlite()` with UI in `6_Sync.py`.
16. ~~**CLI Intelligence Hardening**~~ — ✅ `DEPENDENCY_MAP.md` cross-module dependency reference. Three standing orders in CLAUDE.md: Pre-Fix Investigation Protocol, Post-Sprint Impact Audit, Dependency Map Maintenance.
17. ~~**Defensibility Report Generator**~~ — ✅ 9-section court-ready PDF via pdfkit/wkhtmltopdf. Button on home.py gated to `production` permission.
18. ~~**Dashboard & Analytics Plotly Upgrade**~~ — ✅ Pipeline funnel, review decision donut, dedup waterfall, communicator bars, communication heatmap, timeline with gap annotations, domain pie/bar charts. `plotly>=5.24.0` dependency.
19. ~~**Audit Trail Export Upgrade**~~ — ✅ Three-format export (CSV, Excel with metadata sheet, PDF with landscape layout and filter criteria).
20. ~~**Custodian Management**~~ — ✅ New Module 7 (`7_Custodians.py`). Custodians + hold_documents tables. Inventory chart, profile editing, rename/merge/reassign/collections tabs. Legal hold tracking with document upload, Gantt timeline, case hold summary. `custodian_management` permission.
21. ~~**Review Batching**~~ — ✅ `review_batches` + `batch_documents` tables. Family-aware LPT auto-split. Sidebar batch management (Manager+). Batch filter toggle + WHERE clause injection. "Reviewed — Next" vs "Save" distinction. Progress banner + auto-status.
22. ~~**Closed-Case Read-Only**~~ — ✅ Review and Analytics show full UI with writes disabled on closed cases (was: blank page with st.stop()). Admin-only sections (Factory Reset, System Backend) gated behind `user_admin` permission.

### beta-2.9 Sprint ✅

1. ~~**Multi-Production Junction Table**~~ — ✅ `document_productions` table replaces flat Bates columns for multi-production tracking. `refresh_production_cache()` syncs flat columns for backward compatibility. `get_document_productions()`, `get_production_volume_records()`. One-time backfill migration. Gap analysis + Production module write to junction table.
2. ~~**EDRM Workflow + Differentiators**~~ — ✅ DAT load file security (custom coding fields excluded as work product). Production writes to junction table with production_type tracking.
3. ~~**Exhibit Management**~~ — ✅ New Module 8 (`8_Exhibits.py`). `exhibit_sets` + `exhibits` tables. Exhibit set CRUD, exhibit list with reorder, add-document search against produced documents, binder PDF export (pdfkit + PyMuPDF). 5 new permissions (`view_exhibits`, `mark_exhibit`, `manage_exhibit_sets`, `manage_exhibits`, `export_exhibit_binder`).
4. ~~**Shared Email Rendering Pipeline**~~ — ✅ 6 extracted helpers in `universal_imager.py` (`_build_email_html`, `_wrap_plain_text_as_html`, `_substitute_cid_images`, `_run_wkhtmltopdf`, `_render_fitz_story`, `_append_inline_images_to_pdf`). Eliminates EML/MSG "fix it twice" duplication.
5. ~~**Email Imager Hardening**~~ — ✅ `_strip_blank_pages()`, `_neutralize_external_images()`, `FITZ_STORY_MAX_PAGES=50`, wkhtmltopdf `--disable-javascript` safety flag.
6. ~~**Custom Issue Coding**~~ — ✅ `coding_fields` + `document_coding` tables. Admin UI on home.py (create/delete picklist/text/boolean fields). Rendered in Review coding panel. Excluded from production DAT (work product). `create_coding_field()`, `get_coding_fields()`, `delete_coding_field()`, `get_document_coding()`, `upsert_document_coding()`, `get_all_coding_for_production()`.
7. ~~**Reviewer Notes**~~ — ✅ `document_notes` table. Per-user, per-document notes in Review. `upsert_document_note()`, `get_document_notes()`, `delete_document_note()`.
8. ~~**Collection Scope**~~ — ✅ `collection_scope` table. Per-custodian, per-source status tracking with justification. New tab in 7_Custodians.py. 4 CRUD functions. Feeds Section 2.2 of defensibility report.
9. ~~**Matter Profile**~~ — ✅ 10-field case summary card on home.py. Stored as JSON in `case_settings`. `get_matter_profile()`, `set_matter_profile()`.
10. ~~**Case Archive**~~ — ✅ ZIP export of case.db + productions + defensibility report + MANIFEST.json. Button on home.py.
11. ~~**Session Timeout**~~ — ✅ Configurable inactivity auto-logout (default 30 min via `session_timeout_minutes` in `auth_config.yaml`).
12. ~~**Analytics Expansion**~~ — ✅ Custodian Overlap tab (content_hash intersection matrix, Plotly heatmap) + Concept Explorer tab (OpenSearch `significant_text` aggregation for keyword expansion).
13. ~~**Review Enhancements**~~ — ✅ Exhibit designation badges + mark-as-exhibit expander, Production History expander, Re-Image button (Manager+, emails only), custom coding fields, reviewer notes, confidentiality designation override.
14. ~~**Defensibility Report Expansion**~~ — ✅ Section 2.2 Collection Scope & Justification, Production Detail by Type from junction table.
15. ~~**NIST De-Junk Configuration**~~ — ✅ `DEFAULT_NIST_EXTENSIONS` constant + `get_nist_extensions()`/`set_nist_extensions()` for per-case override.

### beta-2.10 Sprint ✅

1. ~~**Inbound Production Module Extraction**~~ — ✅ `pages/9_InboundProduction.py` is now a dedicated sidebar module (Commits 6, 7.7). Extracted from `5_Production.py` tab_inbound to eliminate the workflow hazard where outbound's phase-gating `st.stop()` locked inbound ingest out during Pass 1 checkpoint state. Registered in `auth_manager._NAV_PAGES`; smoke test `tests/test_nav_registry_consistency.py` pins the filesystem-to-registry contract.
2. ~~**Mandatory Outbound `source_party` Filter**~~ — ✅ `db_manager.OUTBOUND_SOURCE_FILTER_SQL` constant + alias-aware `outbound_source_filter_sql(alias=None)` helper applied to 34 defensibility + production queries (Commit 3). Removes the beta-2.9 `exclude_external` checkbox — no toggle; unconditional filter. Pinned-value contract test.
3. ~~**Phase-Gating Refactor**~~ — ✅ Extracted `_render_outbound_production()` helper from `5_Production.py` (Commit 7). Converted three inner `st.stop()` calls to `return`; outer state gates rewritten as `if/elif/else`. Dissolves the tab_privlog blanking defect where `st.stop()` killed the entire Streamlit script (not just the current tab). Collateral: closed-case privilege-log access restored by removing the module-level `st.stop()` at line 233.
4. ~~**Sort-Path NULL-CN Resilience**~~ — ✅ Defensive narrowing of three `df[df['_is_parent']].set_index('control_number')` filter sites in `_render_outbound_production()` (Commit 7.5). Pre-existing latent defect surfaced during post-Commit-7 manual verification — NULL `control_number` on legitimate PST container rows produced a non-unique NaN index that raised `pandas.InvalidIndexError` on downstream `.map()`.
5. ~~**`production_runs` Direction-Filter Regression**~~ — ✅ Migrated three outbound-context readers (Home Production History `home.py:551`, defensibility report §6.2 `defensibility_report.py:167`, case archive manifest `home.py:1017`) to filter `direction='outbound'` (Commit 7.6). Defensibility-class fix — the court-facing report had been listing inbound ingests as firm productions under "6.2 Production Run History".
6. ~~**Orphan Detector + State Machine**~~ — ✅ `production_runs.status` + `.direction` columns with idempotent migrations + one-time backfill (Commits 1, 2). Orphan detector now consults DB status instead of filesystem heuristics; new state transitions `in_progress → pass1_complete → finalized | aborted`.
7. ~~**Inbound Privilege-Tagging Suppression**~~ — ✅ `4_Review.py` write paths skip inbound documents via module-local `_is_inbound_doc()` predicate (Commit 4). Privilege disposition on opposing counsel's production is meaningless and a confusion hazard.
8. ~~**Inline SQL Migration (Pre-Extraction)**~~ — ✅ Four inbound queries lifted into `db_manager` helpers before the module extraction (Commit 5): `inbound_production_run_name`, `get_inbound_productions`, `purge_inbound_volume`, `upsert_inbound_documents_batch`. Clean-before-move discipline.
9. ~~**Navigation Registry Smoke Test**~~ — ✅ `tests/test_nav_registry_consistency.py` asserts every `pages/*.py` appears in `_NAV_PAGES` and every tuple points at an existing file (Commit 7.7). Prevents the Module-9-invisible-for-one-commit failure from recurring.
10. ~~**Sprint Teaching Moments**~~ — ✅ Three patterns codified in `DEPENDENCY_MAP.md §7` and CLAUDE.md Standing Orders: silent cross-module filter drift (when a shared table gains new row-kinds, every caller must be audited for superset-vs-subset assumption), nav-registry reconciliation (`pages/` additions require a matching `_NAV_PAGES` tuple), commit bundling criteria (same root cause + same fix + same hazard class).

### beta-2.11 Sprint ✅ (Documentation Architecture Reorganization)

Non-functional sprint. No page/engine code changed. Purpose: install the documentation infrastructure that future AI sessions read at the start of every context window. Seven commits (`6b → 6c → 6c.2 → 6d → 6e.1 → 6e.2 → 6e.3`) plus the standing-orders relaxation (`6f/9`).

1. ~~**Four-Tier Documentation Architecture**~~ — ✅ `docs/{references,lessons,templates,archive}/` directory scaffolding (Commit 6b). Each tier has a `README.md` index; each index is cross-referenced from `CLAUDE.md` §Dependency API References.
2. ~~**Dependency Reference Migration**~~ — ✅ six pre-existing `*_REFERENCE.md` / `*_PATTERNS.md` files (EMAIL_MIME, LIBPFF_API, OPENSEARCH_PATTERNS, OUTLOOK_COM, PYMUPDF_PATTERNS, TIKA_METADATA_KEYS) relocated from `docs/` root into `docs/references/` (Commit 6c.1). AGENTS.md fold-in (Redaction Discipline, disabled-widget pattern, process_msg_batch constraint, Hold Documents isolation rule) applied to CLAUDE.md in the same commit.
3. ~~**Durable Lesson Extraction**~~ — ✅ 19 lessons extracted from sprint retrospectives, scratchpad specs, and AGENTS.md fold-in into `docs/lessons/` as standalone files with the canonical 5-section structure (Commit 6c.2). Covers data integrity, data-layer discipline, code patterns, and workflow. Four additional lessons added in Commit 6e.3 (predictive-scaffold-staleness, chain-of-moves-stale-refs, grep-by-stem-not-spec-name, substance-over-specifics-redaction).
4. ~~**Template Extraction**~~ — ✅ three reusable templates in `docs/templates/`: preflight, defect-triage, scoped-audit (Commit 6d). Extracted from beta-2.10's outbound-extraction-preflight, sort-path-triage, and a scoped pre-deployment audit prompt respectively. PM–CLI collaboration workflow doc promoted from `docs/audits/` to `docs/templates/` in the same commit.
5. ~~**Spec Intake + Archive Sweep**~~ — ✅ to-do blueprints consolidated under `docs/specs/` (Commit 6e.1); 14 shipped specs swept to `docs/archive/specs/` (Commit 6e.2). Superpowers-skill outputs stay at `docs/superpowers/` per skill mandate (see Commit 6e.3).
6. ~~**Standing Orders — Save-Location Coordination + Spec Lifecycle Discipline**~~ — ✅ installed in CLAUDE.md (Commit 6e.3). Defines the dual-convention layout (`docs/specs/` hand-written + `docs/superpowers/` skill-mandated) and the complete→archive symmetry for shipped specs.
7. ~~**Standing Order Relaxation — Permission-Gated Edits**~~ — ✅ the "NEVER touch human-authored files" iron law relaxed to "propose + wait for greenlight + execute" (Commit 6f/9). The gate is visibility, not prohibition. Applies to `ROADMAP_TODO.md` and `config.py __version__`; does not relax safety/legal/ethical iron laws.
8. ~~**Post-Sprint Doc Cascade**~~ — ✅ this commit (Commit 7). PROJECT_CONTEXT.md / Technical Overview.md / CLAUDE.md / auto-memory refreshes; `__version__` bump 2.9.0 → 2.11.0; ROADMAP_TODO.md header refresh.

Teaching moments codified as lessons:
- **Predictive scaffold staleness.** A README written before a file migration that specifies what the directory "will contain" is a time bomb. If the migration deviates, the scaffold lies. Fix: check scaffolds written in prior arc commits during reconciliation.
- **Chain-of-moves stale refs.** When a multi-commit arc moves files through multiple homes (source → holding area → final location), refs accumulate stale pointers. Fix: broad reconciliation grep during packet execution's reconciliation phase, not just against the packet's enumerated targets.
- **Grep by behavior stem, not spec-proposed function name.** Codebases abbreviate. A shipping-status audit that greps only for `save_user_preferences` misses `save_user_pref`. Fix: grep stems.

### Holistic Audit Remediation Backlog

Passes 3-9 completed 2026-03-27. Full findings and prioritized remediation plan in `docs/HOLISTIC_AUDIT_REMEDIATION.md` (32 findings: 7 critical — 4 fixed, 2 downgraded, 1 false positive; 11 high; 10 medium; 4 low). Key remaining items:
- Auth function hardening (defense-in-depth guards on update_role, delete_user, etc.)
- Case-closed gate consistency (st.stop() vs warning-only across 3 modules)
- Missing permission checks on 7_Custodians.py write operations
- Unlogged write operations in 6_Sync.py (12 items)
- Audit vocabulary docstring update in db_manager.py

### Long-term / Future Consideration

- **Internet-facing deployment** — HTTPS, secret management, Streamlit auth hardening
- **PyMuPDF → Artifex commercial OEM license** — required at commercialization (AGPL v3 exposure)

---

## 10. KNOWN ISSUES AND CONSTRAINTS

- **`streamlit-drawable-canvas` is unmaintained upstream.** The Streamlit 1.55 incompatibility required a manual patch to the installed package file. **This patch will be lost if the venv is rebuilt** — must be re-applied. Document patch location: `_scratchpad/` or as a pip post-install note.
- **Windows file locking with PyMuPDF** — `fitz.open()` holds an exclusive lock on Windows. Any PDF opened for rendering must be explicitly `.close()`d before button handlers try to reopen the same file for writing. This is a recurring gotcha in the Processor and the Redact tab in `4_Review.py` (the render open and the button-handler write open are deliberately separated for this reason).
- **`st_canvas` first-render background blank** — `streamlit-drawable-canvas` is a React component. When first mounted, it does not reliably display its `background_image` prop on the initial render. **Workaround in place:** `🖊️ Load Redaction Canvas` checkbox (key: `enable_redact_{cn}`, no page index) requires one user click before the canvas renders, triggering the rerun needed for the background to display. Persists across page navigation within the same document.
- **Redact tab cursor does not change to crosshair in Draw mode** — Fabric.js sets `cursor: crosshair` in rect mode but the canvas iframe prevents it from propagating to the outer page. Fixing requires patching `streamlit-drawable-canvas` frontend JS (similar to the Streamlit 1.55 patch). Deferred — cosmetic issue only.
- **Filevine subdomain is firm-specific** — `FILEVINE_SUBDOMAIN` now in `config.py` (no longer hardcoded). All other Filevine API logic is generalized.
- **Analytics requires a complete corpus** — Threading and near-dupe give wrong results if run mid-ingestion. No guard in the UI — enforce by operator procedure.
- **Near-dupe requires OpenSearch** — Cannot run offline.
- **`process_msg_batch` is Windows/Outlook-only** — This function calls `pythoncom.CoInitialize()` directly and is not guarded by `_WIN32COM_AVAILABLE`. It is only reached for `.msg` files which only exist post-extraction on Windows, so this is an accepted constraint rather than a bug.
- **bcrypt password hashing** — Upgraded from SHA-256 in beta-2.4. Existing SHA-256 hashes auto-migrate to bcrypt on first successful login. New hashes and resets always use bcrypt.
- **Windows 260-char path limit** — Mitigated via `\\?\` long-path prefix on all file operations. Prefix stripped before DB storage and COM calls. One-time migration clears orphaned prefixes from `full_path` column.
- **Streamlit .exe AppLocker block** — Windows Application Control policies may block `streamlit.exe`. Workaround: run via `python -m streamlit run home.py` instead.
- **Hold documents are NOT case ESI** — Files in `Hold_Documents/` must never enter the ingestion pipeline, get control numbers, or be indexed in OpenSearch. Any future folder scanning logic must explicitly exclude this directory.
- **Custodian rename requires OS reindex** — Rename/merge/reassign operations update SQLite but not the OpenSearch index. Users must rebuild the index via Sync → Search Index Maintenance after bulk custodian changes.
- **Review batching and SQLite foreign keys** — SQLite does not enforce FOREIGN KEY constraints by default. `batch_documents.ON DELETE CASCADE` may not fire; code handles cascade manually with explicit DELETE before batch deletion.
- **Exhibit set CASCADE deletion** — `delete_exhibit_set()` uses scoped `PRAGMA foreign_keys = ON` within the connection to enable CASCADE deletion of child exhibits. This is set per-call because SQLite does not enforce foreign keys by default.
- **Custom coding fields excluded from production** — `document_coding` values are intentionally omitted from DAT/CSV load files in production output. They represent attorney work product and must not be included in deliverables to opposing counsel.
- **Concept Explorer OpenSearch version dependency** — The `significant_text` aggregation used by the Concept Explorer tab requires a sufficiently recent OpenSearch version. The UI degrades gracefully with an informational message if the aggregation is unavailable.
- **Re-image resets review state** — Using the Re-Image button clears `reviewed_by`, `reviewed_at`, and `redaction_status` for the document. The reviewer must re-review the document after re-imaging.

---

## 11. beta-2.10 TEACHING MOMENTS (future-Claude reference)

Three patterns from the beta-2.10 sprint worth internalizing before touching similar surfaces.

### Sort-Path NaN-Index (Commit 7.5)

`df[df['_is_parent']].set_index('control_number')` produces a non-unique index when multiple rows share a NULL `control_number` (e.g., PST container artifacts — legitimate data, not corruption). Downstream `.map()` against the resulting Series raises `pandas.InvalidIndexError: Reindexing only valid with uniquely valued Index objects`.

Fix: narrow the filter to `df['_is_parent'] & df['control_number'].notna()` at each site. Do NOT narrow the `_is_parent` definition globally — sort-key usages at `pages/5_Production.py:2692` and `:2710` legitimately want "structural root of a family" regardless of CN. Option-A scope discipline held: three discrete filter-site edits, zero touch to the predicate definition.

Test: `tests/test_production_sort_path.py` pins the fix pattern verbatim with a mixed fixture (real email parents + PST container + children) to prevent inline-code drift.

### Silent Cross-Module Filter Drift (Commit 7.6)

When a sprint adds rows with a new `direction` / `status` / `record_type` value to a shared table, every existing caller of that table's query helpers must be audited for "does this consumer still want the superset, or was it implicitly assuming subset?"

Example: Commit 6 added `direction='inbound'` rows to `production_runs`, but legacy callers at `home.py:551`, `defensibility_report.py:167`, and the archive-manifest inline SQL at `home.py:1017` rendered the result under labels implying outbound-only ("Production History", "Productions we performed") — with FRCP 26(g) certification risk at the defensibility-report site.

Fix: migrate each legacy reader to an explicit `direction='outbound'` filter — either via `db_manager.get_production_history(case_folder, direction='outbound')` (the helper introduced in Commit 1 for exactly this purpose) or via an inline `WHERE direction = 'outbound'` clause where the call site already uses direct SQL.

Pattern also added to `DEPENDENCY_MAP.md §7 Known Regression Patterns` so it's surfaced in future sprint audits.

### Nav Registry Gap (Commit 7.7)

Streamlit's `pages/` directory auto-registers pages with the runtime, but the post-login sidebar in this app is built from `auth_manager._NAV_PAGES` — a separate registry. A new page file without a registry tuple is reachable by direct URL (if auth passes) but invisible in the sidebar. Commit 6's Module 9 extraction hit this: one commit of invisibility before 7.7 added the tuple.

Procedural safeguard: CLAUDE.md §Post-Sprint audit step 6 (new in beta-2.10 Commit 8) reconciles registry against filesystem. Test: `tests/test_nav_registry_consistency.py` pins the contract bidirectionally (every page file has a tuple; every tuple points at an existing file).
