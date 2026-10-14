# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        db_manager.py
# version:       1.34.1
# project:       Respondeo eDiscovery Platform
# project_ver:   2.16.0
# last_modified: 2026-06-10 14:59
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import sqlite3
import os
import re
import json
import time
import hashlib
import logging
from datetime import datetime
logger = logging.getLogger(__name__)

def get_connection(case_folder):
    db_path = os.path.join(case_folder, "case.db")
    conn = sqlite3.connect(db_path, timeout=60.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    
    # Lightweight audit_log column migrations — run on every open so existing
    # databases created before username/module/etc. were added stay current.
    _audit_cols = [
        ("username", "TEXT"),
        ("control_number", "TEXT"),
        ("module", "TEXT"),
        ("old_value", "TEXT"),
        ("new_value", "TEXT"),
    ]
    for _col, _typ in _audit_cols:
        try:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {_col} {_typ}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    return conn

# ---------------------------------------------------------------------------
# OUTBOUND SOURCE FILTER — mandatory SQL fragment (beta-2.10 Commit 3)
# ---------------------------------------------------------------------------
# Every query that produces outbound-destined content (production assembly,
# privilege log, defensibility reports, STR exports) MUST include this filter.
# Inbound documents (source_party != 'Internal' AND NOT NULL) are opposing
# counsel's productions to us — they must never appear in our output.
#
# This is a non-toggleable constant by design. The pre-beta-2.10 platform
# had a user-facing "Exclude External" checkbox that allowed unchecking this
# filter; that was a defensibility hazard and was removed. If a legitimate
# subpoena-passthrough workflow is ever needed, it must be its own explicit
# feature with its own audit trail — not a checkbox that silently leaks
# inbound material.
#
# Usage:
#   - Non-aliased queries: append " AND " + OUTBOUND_SOURCE_FILTER_SQL
#   - Aliased queries (e.g. "FROM documents d"): use outbound_source_filter_sql('d')
OUTBOUND_SOURCE_FILTER_SQL = "(source_party = 'Internal' OR source_party IS NULL)"


def outbound_source_filter_sql(alias=None):
    """Return the mandatory outbound source_party filter SQL fragment.

    Args:
        alias: Optional table alias (e.g. 'd' for "FROM documents d").
            When provided, column references are prefixed with the alias.
            When None, returns the bare-column form (OUTBOUND_SOURCE_FILTER_SQL).

    Returns:
        Parenthesized SQL fragment suitable for appending after "AND" in a
        WHERE clause. Never returns an empty string — this filter is
        unconditional by design.

    Examples:
        >>> outbound_source_filter_sql()
        "(source_party = 'Internal' OR source_party IS NULL)"
        >>> outbound_source_filter_sql('d')
        "(d.source_party = 'Internal' OR d.source_party IS NULL)"
    """
    if alias:
        return f"({alias}.source_party = 'Internal' OR {alias}.source_party IS NULL)"
    return OUTBOUND_SOURCE_FILTER_SQL


def init_db(case_folder):
    conn = get_connection(case_folder)
    cursor = conn.cursor()

    # THE "FOREVER" SCHEMA — must be created BEFORE migration ALTER TABLEs
    # Includes all standard E-Discovery fields + Threading DNA
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- IDENTIFICATION
            control_number TEXT UNIQUE,  -- Internal BEGDOC
            begdoc TEXT,                 -- Production BEGDOC (Populated later)
            enddoc TEXT,                 -- Production ENDDOC
            source_party TEXT DEFAULT 'Internal', -- Party that produced this document
            production_volume TEXT,      -- Production Volume for inbound productions
            dynamic_metadata TEXT,       -- JSON string for unmapped load file fields
            begatt TEXT,                 -- Family Range Start
            endatt TEXT,                 -- Family Range End
            parent_id TEXT,              -- Parent Control Number
            group_id TEXT,               -- Family/Thread Group ID
            custodian TEXT,
            volume TEXT,                 -- Source Media/Volume Name
            
            -- BASIC METADATA
            file_name TEXT,
            file_extension TEXT,
            file_size_kb REAL,
            record_type TEXT,            -- 'Email', 'Attachment', 'Loose'
            md5_hash TEXT,
            content_hash TEXT,
            
            -- DATES (Stored as ISO8601 Strings for easy sorting)
            date_sent TEXT,              -- DATESENT + TIMESENT
            date_received TEXT,
            date_created TEXT,
            date_modified TEXT,
            
            -- EMAIL METADATA
            email_from TEXT,
            email_to TEXT,
            email_cc TEXT,
            email_bcc TEXT,
            email_subject TEXT,
            
            -- THREADING DNA (Critical for future Analytics)
            message_id TEXT,             -- The email's unique fingerprint
            in_reply_to TEXT,            -- The fingerprint of the email this replied to
            references_list TEXT,        -- List of all fingerprints in the chain
            conversation_index TEXT,     -- Microsoft specific threading code
            author TEXT,                 -- Document Author
            
            -- SYSTEM
            original_path TEXT,
            full_path TEXT,
            processing_status TEXT DEFAULT 'New', 
            has_text INTEGER DEFAULT 0,           
            opensearch_id TEXT,
            tags TEXT,
            analytics_run_date TEXT,
            
            -- FILEVINE SYNC ENGINE
            filevine_doc_id TEXT,
            filevine_collection_id TEXT,
            sync_status TEXT DEFAULT 'Pending',
            sync_timestamp TEXT,
            
            -- REDACTION ENGINE
            redaction_status TEXT,       -- NULL / Has_Redactions / Applied
            review_pulled_at TEXT,       -- Timestamp of pull-back from Filevine

            -- CLAWBACK / INADVERTENT DISCLOSURE
            clawback_status TEXT,        -- NULL / Clawback_Demanded / Clawback_Resolved
            clawback_date TEXT,          -- ISO date of clawback demand letter

            -- PROCESSING PIPELINE METADATA
            page_count INTEGER,
            language TEXT,
            title TEXT,                  -- dc:title from Tika (document title, often != filename)
            mime_type TEXT,              -- Content-Type detected by Tika
            creating_application TEXT,   -- Application name + version that created the document
            extraction_method TEXT,      -- How text was obtained: pymupdf / tika / tesseract_ocr / native_ole
            is_encrypted INTEGER DEFAULT 0, -- 1 if PDF/Office file is password-protected
            word_count INTEGER,          -- Word count from Tika (useful for QC anomaly detection)
            attachment_count INTEGER,    -- Number of child attachments (for emails/containers)
            importance TEXT,             -- Email priority: Low / Normal / High
            sensitivity TEXT,            -- Email sensitivity: Normal / Personal / Private / Confidential
            conversation_topic TEXT,     -- Normalized subject for threading (MSG OLE stream 0070)
            tika_metadata_json TEXT,     -- Full raw Tika metadata dict as JSON (catch-all)
            extraction_notes TEXT        -- Extraction quality warnings (e.g. corrupted attachments in source PST)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            action TEXT,
            details TEXT,
            username TEXT,
            control_number TEXT,
            module TEXT,
            old_value TEXT,
            new_value TEXT
        )
    ''')

    # audit_log migrations — add columns to existing DBs
    audit_migrations = [
        ("username", "TEXT"),
        ("control_number", "TEXT"),
        ("module", "TEXT"),
        ("old_value", "TEXT"),
        ("new_value", "TEXT"),
    ]
    for col_name, col_type in audit_migrations:
        try:
            cursor.execute(f"ALTER TABLE audit_log ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_control ON audit_log(control_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_module ON audit_log(module)")
    
    # ---------------------------------------------------------
    # NEW OPTIMIZATION: The Database Index (Table of Contents)
    # ---------------------------------------------------------
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_hash ON documents(content_hash, processing_status)")

    # ---------------------------------------------------------
    # CASE SETTINGS (Key-Value Store)
    # ---------------------------------------------------------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS case_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT
        )
    ''')
    
    # ---------------------------------------------------------
    # MIGRATION: Ensure all required columns exist for existing databases
    # Runs AFTER CREATE TABLE so the table is guaranteed to exist.
    # ---------------------------------------------------------
    migrations = [
        # ── Original columns (present in early schema versions) ──────────────
        ("analytics_run_date", "TEXT"),
        ("begdoc", "TEXT"),
        ("enddoc", "TEXT"),
        ("begatt", "TEXT"),
        ("endatt", "TEXT"),
        ("filevine_doc_id", "TEXT"),
        ("filevine_collection_id", "TEXT"),
        ("sync_status", "TEXT"),
        ("sync_timestamp", "TEXT"),
        ("redaction_status", "TEXT"),
        ("review_pulled_at", "TEXT"),
        ("byos_pushed_at", "TEXT"),
        ("byos_pulled_at", "TEXT"),
        ("page_count", "INTEGER"),
        ("language", "TEXT"),
        ("source_party", "TEXT DEFAULT 'Internal'"),
        ("production_volume", "TEXT"),
        ("dynamic_metadata", "TEXT"),
        ("clawback_status", "TEXT"),
        ("clawback_date", "TEXT"),
        # ── Threading DNA (added v2.x — ensure existing DBs get these) ────────
        ("content_hash", "TEXT"),
        ("author", "TEXT"),
        ("message_id", "TEXT"),
        ("in_reply_to", "TEXT"),
        ("references_list", "TEXT"),
        ("conversation_index", "TEXT"),
        # ── Email fields (added v2.x) ─────────────────────────────────────────
        ("email_bcc", "TEXT"),
        ("date_received", "TEXT"),
        ("date_modified", "TEXT"),
        # ── Metadata enrichment sprint (v2.7) ─────────────────────────────────
        ("title", "TEXT"),
        ("mime_type", "TEXT"),
        ("creating_application", "TEXT"),
        ("extraction_method", "TEXT"),
        ("is_encrypted", "INTEGER DEFAULT 0"),
        ("word_count", "INTEGER"),
        ("attachment_count", "INTEGER"),
        ("importance", "TEXT"),
        ("sensitivity", "TEXT"),
        ("conversation_topic", "TEXT"),
        ("tika_metadata_json", "TEXT"),
        ("extraction_notes", "TEXT"),
        # ── Privilege disposition (v2.7) ───────────────────────────────────────
        ("privilege_status", "TEXT"),   # NULL / Redact / Withhold
        # ── Source collections (v2.7) ────────────────────────────────────
        ("source_collection", "TEXT"),      # Level 2 folder name
        ("source_subcollection", "TEXT"),   # Level 3 folder name
        # ── Document split lineage (v2.9) ─────────────────────────────────
        ("split_source_cn", "TEXT"),        # CN of source doc this was split from
        # ── Production categories (v2.9) ──────────────────────────────────
        ("production_category", "TEXT"),    # User-assigned category for production ordering
    ]
    for col_name, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Post-migration indexes (columns must exist before indexing)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_production_category ON documents(production_category)")

    # ONE-TIME CLEANUP: Clear incorrectly backfilled source_collection/source_subcollection
    # from the original_path backfill that mistook container filenames for folder structure.
    # Guarded by a sentinel so it only runs once per database.
    try:
        _cleanup_done = cursor.execute(
            "SELECT 1 FROM case_settings WHERE setting_key = '_src_coll_cleanup_v1'"
        ).fetchone()
        if not _cleanup_done:
            cursor.execute("UPDATE documents SET source_collection = NULL, source_subcollection = NULL")
            cursor.execute(
                "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('_src_coll_cleanup_v1', '1')"
            )
            conn.commit()
    except Exception:
        pass

    # JOBS TABLE for background task tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT,
            status TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            finished_at DATETIME,
            progress INTEGER,
            total INTEGER,
            error TEXT
        )
    ''')
    # Jobs table migrations — add columns for background processing worker
    _job_migrations = [
        ("phase", "INTEGER DEFAULT 0"),
        ("phase_label", "TEXT"),
        ("details_json", "TEXT"),
        ("pid", "INTEGER"),
        ("case_folder", "TEXT"),
        ("username", "TEXT"),
        ("cancel_requested", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in _job_migrations:
        try:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # SAVED SEARCHES TABLE — per-user search history and named saves
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            search_name TEXT,            -- NULL for auto-logged recent entries
            query TEXT,
            col_filters_json TEXT,       -- JSON dict of active column filters
            is_recent INTEGER DEFAULT 0, -- 1 = auto-logged recent, 0 = named save
            is_global INTEGER DEFAULT 0, -- 1 = shared with all users
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute("ALTER TABLE saved_searches ADD COLUMN is_global INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # REDACTION MARKS TABLE — per-doc, per-page annotation storage
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS redaction_marks (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            control_number TEXT NOT NULL,
            page_number    INTEGER NOT NULL,
            marks_json     TEXT,
            created_by     TEXT,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(control_number, page_number)
        )
    ''')

    # ---------------------------------------------------------
    # MIGRATION: Fill NULL group_id with control_number for parents
    # Parents had NULL group_id because the Processor UPDATE didn't include it.
    # Children always have group_id set via add_children_to_db.
    # ---------------------------------------------------------
    cursor.execute("UPDATE documents SET group_id = control_number WHERE group_id IS NULL")

    # ---------------------------------------------------------
    # MIGRATION: Rename elastic_id -> opensearch_id for existing DBs
    # ---------------------------------------------------------
    try:
        col_info = cursor.execute("PRAGMA table_info(documents)").fetchall()
        col_names = [c[1] for c in col_info]
        if 'elastic_id' in col_names and 'opensearch_id' not in col_names:
            cursor.execute("ALTER TABLE documents RENAME COLUMN elastic_id TO opensearch_id")
    except Exception:
        pass  # Column already migrated or doesn't exist
    
    conn.commit()

    # --- One-time migration: strip UUID prefix from file_name and original_path ---
    # The container exploder historically leaked filesystem deconfliction prefixes
    # (6-hex-char UUID + underscore) into DB columns. This migration strips them.
    # Safe to run multiple times — the pattern check prevents false positives.
    _migration_key = 'uuid_prefix_strip_v1'
    _already_run = conn.execute(
        "SELECT 1 FROM case_settings WHERE setting_key=?", (_migration_key,)
    ).fetchone()

    if not _already_run:
        import re as _re
        from datetime import datetime as _datetime
        _uuid_prefix_pattern = _re.compile(r'^[0-9a-f]{6}_', _re.IGNORECASE)

        # Fix file_name column
        rows = conn.execute(
            "SELECT id, file_name FROM documents WHERE file_name IS NOT NULL"
        ).fetchall()
        for row in rows:
            fn = row['file_name'] if isinstance(row, sqlite3.Row) else row[1]
            row_id = row['id'] if isinstance(row, sqlite3.Row) else row[0]
            if fn and _uuid_prefix_pattern.match(fn):
                clean_fn = fn[7:]  # Strip 6 hex chars + underscore
                conn.execute(
                    "UPDATE documents SET file_name=? WHERE id=?",
                    (clean_fn, row_id)
                )

        # Fix original_path column — strip prefix from the last path component only
        rows = conn.execute(
            "SELECT id, original_path FROM documents WHERE original_path IS NOT NULL"
        ).fetchall()
        for row in rows:
            op = row['original_path'] if isinstance(row, sqlite3.Row) else row[1]
            row_id = row['id'] if isinstance(row, sqlite3.Row) else row[0]
            if op:
                # Split on both / and \, check last component
                parts = op.replace('\\', '/').split('/')
                last = parts[-1]
                if _uuid_prefix_pattern.match(last):
                    parts[-1] = last[7:]
                    clean_op = '/'.join(parts) if '/' in op else '\\'.join(parts)
                    conn.execute(
                        "UPDATE documents SET original_path=? WHERE id=?",
                        (clean_op, row_id)
                    )

        conn.execute(
            "INSERT INTO case_settings (setting_key, setting_value) VALUES (?, ?)",
            (_migration_key, _datetime.now().isoformat())
        )
        conn.commit()
        logging.getLogger(__name__).info("Migration uuid_prefix_strip_v1 complete — cleaned file_name and original_path columns")

    # CUSTODIANS REGISTRY TABLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS custodians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            title TEXT,
            department TEXT,
            email TEXT,
            notes TEXT,
            hold_status TEXT DEFAULT 'None',
            hold_issued_date TEXT,
            hold_acknowledged_date TEXT,
            hold_released_date TEXT,
            hold_notice_method TEXT,
            hold_notice_recipient TEXT,
            hold_notes TEXT,
            collection_start_date TEXT,
            collection_end_date TEXT,
            data_sources TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HOLD DOCUMENTS TABLE — admin records about holds, NOT case ESI
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hold_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            custodian_name TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            document_type TEXT,
            uploaded_by TEXT,
            upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')

    # NEAR-DUPE CLUSTER REVIEW TABLES (S-1b)
    # Cluster membership + per-member reviewer decisions + per-cluster attestation.
    # Suppression is provisional: NearDupe-Suppressed is applied only when a
    # reviewer confirms a member is "same" (see record_member_decision). A member
    # with family_preserved=1 (parent_id set in the Execute routing) is guarded
    # from the tag even on a "same" decision — family-integrity-over-dedup.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS near_dupe_clusters (
            cluster_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date         TEXT,
            principal_cn     TEXT,
            member_count     INTEGER DEFAULT 0,
            sim_min          REAL,
            sim_max          REAL,
            review_status    TEXT DEFAULT 'pending',
            reviewed_by      TEXT,
            reviewed_at      TEXT,
            attestation_note TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS near_dupe_cluster_members (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id             INTEGER NOT NULL,
            member_cn              TEXT NOT NULL,
            is_principal           INTEGER DEFAULT 0,
            family_preserved       INTEGER DEFAULT 0,
            similarity             REAL,
            decision               TEXT DEFAULT 'undecided',
            decided_by             TEXT,
            decided_at             TEXT,
            similarity_at_decision REAL,
            decided_in_cluster_id  INTEGER
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ndcm_cluster ON near_dupe_cluster_members(cluster_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ndcm_member ON near_dupe_cluster_members(member_cn)')
    # S-1b C8b: decided_in_cluster_id added after C8a shipped — idempotent migration
    # for existing C8a-era DBs. NULL = undecided; == this row's cluster_id = decided
    # here; differs = decided in another (overlapping) cluster -> UI lock (spec §11.7).
    try:
        cursor.execute("ALTER TABLE near_dupe_cluster_members ADD COLUMN decided_in_cluster_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists (mirrors the audit_log ADD COLUMN pattern above).

    # Auto-populate custodians from existing documents (idempotent)
    cursor.execute("""
        INSERT OR IGNORE INTO custodians (name)
        SELECT DISTINCT custodian FROM documents
        WHERE custodian IS NOT NULL AND custodian != ''
          AND custodian NOT IN (SELECT name FROM custodians)
    """)
    conn.commit()

    # REVIEW BATCHES TABLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS review_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_name TEXT NOT NULL,
            assigned_to TEXT,
            created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Open',
            doc_count INTEGER DEFAULT 0,
            page_count INTEGER DEFAULT 0,
            notes TEXT
        )
    ''')

    # BATCH DOCUMENTS JUNCTION TABLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS batch_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            control_number TEXT NOT NULL,
            UNIQUE(control_number),
            FOREIGN KEY (batch_id) REFERENCES review_batches(id) ON DELETE CASCADE
        )
    ''')

    # PRODUCTION RUNS HISTORY TABLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS production_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            production_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            format TEXT NOT NULL,
            mode TEXT NOT NULL,
            bates_prefix TEXT,
            bates_start TEXT,
            bates_end TEXT,
            document_count INTEGER DEFAULT 0,
            withheld_count INTEGER DEFAULT 0,
            redacted_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            endorsement_text TEXT,
            settings_json TEXT,
            UNIQUE(production_name)
        )
    ''')

    # ── production_runs migrations (beta-2.10) ────────────────────────────────
    # status: tracks Pass 1 lifecycle so the orphan detector can distinguish
    #   legitimately-staged files from truly abandoned ones.
    # direction: 'outbound' (we produced) vs 'inbound' (opposing counsel produced
    #   to us). Inbound ingestions get a production_runs row at ingest time with
    #   status='finalized'; single-shot, no Pass 1/Finalize distinction.
    _production_runs_migrations = [
        ("status", "TEXT DEFAULT 'in_progress'"),
        ("direction", "TEXT DEFAULT 'outbound'"),
    ]
    for col_name, col_type in _production_runs_migrations:
        try:
            cursor.execute(f"ALTER TABLE production_runs ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # ONE-TIME BACKFILL: existing production_runs rows are historical finalized
    # outbound productions. Guarded by a sentinel so it only runs once.
    #
    # IMPORTANT: SQLite `ALTER TABLE ... ADD COLUMN ... DEFAULT 'value'` populates
    # existing rows with the default immediately — not NULL. So `WHERE status
    # IS NULL` would match zero rows on upgrade (old rows already have
    # 'in_progress' from the DEFAULT). Backfill must be unconditional within the
    # sentinel guard: any rows that exist at this point are historical and need
    # to be flipped to 'finalized'/'outbound'. The sentinel ensures this only
    # runs once per DB, so new rows inserted after the first init_db() aren't
    # affected on subsequent runs.
    try:
        _pr_backfill_done = cursor.execute(
            "SELECT 1 FROM case_settings WHERE setting_key = '_production_runs_status_backfill_v1'"
        ).fetchone()
        if not _pr_backfill_done:
            cursor.execute("UPDATE production_runs SET status = 'finalized'")
            cursor.execute("UPDATE production_runs SET direction = 'outbound'")
            cursor.execute(
                "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('_production_runs_status_backfill_v1', '1')"
            )
            conn.commit()
    except Exception:
        pass

    # DOCUMENT NOTES TABLE
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS document_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            control_number TEXT NOT NULL,
            username TEXT NOT NULL,
            note_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(control_number, username)
        )
    ''')

    # MIGRATION: reviewed_by / reviewed_at columns on documents
    try:
        cursor.execute("ALTER TABLE documents ADD COLUMN reviewed_by TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE documents ADD COLUMN reviewed_at TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE documents ADD COLUMN confidentiality_designation TEXT")
    except sqlite3.OperationalError:
        pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS collection_scope (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                custodian_id INTEGER NOT NULL,
                source_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending','Collected','Searched-No-Hit',
                                      'Not-Reasonably-Accessible','Out-of-Scope')),
                justification TEXT,
                reviewed_by TEXT,
                reviewed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (custodian_id) REFERENCES custodians(id) ON DELETE CASCADE,
                UNIQUE(custodian_id, source_name)
            )
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_productions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            control_number TEXT NOT NULL,
            production_volume TEXT NOT NULL,
            begdoc TEXT NOT NULL,
            enddoc TEXT NOT NULL,
            page_count INTEGER DEFAULT 1,
            produced_at TEXT NOT NULL,
            production_type TEXT DEFAULT 'Original',
            supersedes_id INTEGER DEFAULT NULL,
            notes TEXT DEFAULT NULL,
            FOREIGN KEY (control_number) REFERENCES documents(control_number),
            FOREIGN KEY (supersedes_id) REFERENCES document_productions(id),
            UNIQUE(control_number, production_volume)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dp_control_number ON document_productions(control_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dp_production_volume ON document_productions(production_volume)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dp_begdoc ON document_productions(begdoc)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS coding_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_name TEXT NOT NULL UNIQUE,
            field_type TEXT NOT NULL DEFAULT 'picklist'
                CHECK (field_type IN ('picklist', 'text', 'boolean')),
            pick_list_json TEXT,
            display_order INTEGER DEFAULT 0,
            created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_coding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            control_number TEXT NOT NULL,
            coding_field_id INTEGER NOT NULL,
            value TEXT,
            coded_by TEXT,
            coded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (control_number) REFERENCES documents(control_number),
            FOREIGN KEY (coding_field_id) REFERENCES coding_fields(id),
            UNIQUE(control_number, coding_field_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dc_control_number ON document_coding(control_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dc_field_id ON document_coding(coding_field_id)")

    # ── Exhibit Sets & Exhibits ────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exhibit_sets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            case_folder TEXT    NOT NULL,
            set_name    TEXT    NOT NULL,
            set_type    TEXT    NOT NULL DEFAULT 'Deposition',
            proceeding_date TEXT,
            case_caption    TEXT,
            created_by  TEXT    NOT NULL,
            created_at  TEXT    NOT NULL,
            UNIQUE(case_folder, set_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exhibits (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            exhibit_set_id  INTEGER NOT NULL,
            control_number  TEXT    NOT NULL,
            exhibit_number  TEXT    NOT NULL,
            description     TEXT,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            added_by        TEXT    NOT NULL,
            added_at        TEXT    NOT NULL,
            FOREIGN KEY (exhibit_set_id) REFERENCES exhibit_sets(id) ON DELETE CASCADE,
            FOREIGN KEY (control_number) REFERENCES documents(control_number),
            UNIQUE(exhibit_set_id, exhibit_number),
            UNIQUE(exhibit_set_id, control_number)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exhibits_set_id ON exhibits(exhibit_set_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exhibits_cn ON exhibits(control_number)")

    # Backfill document_productions from existing flat columns (one-time migration)
    try:
        _dp_count = conn.execute("SELECT COUNT(*) FROM document_productions").fetchone()[0]
        _docs_with_bates = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE begdoc IS NOT NULL AND begdoc != ''"
        ).fetchone()[0]
        if _dp_count == 0 and _docs_with_bates > 0:
            _eligible = conn.execute("""
                SELECT COUNT(*) FROM documents d
                WHERE d.begdoc IS NOT NULL AND d.begdoc != ''
                  AND d.production_volume IS NOT NULL AND d.production_volume != ''
                  AND (d.source_party = 'Internal' OR d.source_party IS NULL)
            """).fetchone()[0]
            conn.execute("""
                INSERT OR IGNORE INTO document_productions
                    (control_number, production_volume, begdoc, enddoc, page_count, produced_at, production_type)
                SELECT
                    d.control_number,
                    d.production_volume,
                    d.begdoc,
                    COALESCE(d.enddoc, d.begdoc),
                    1,
                    COALESCE(pr.created_at, datetime('now')),
                    'Original'
                FROM documents d
                LEFT JOIN production_runs pr ON d.production_volume = pr.production_name
                WHERE d.begdoc IS NOT NULL AND d.begdoc != ''
                  AND d.production_volume IS NOT NULL AND d.production_volume != ''
                  AND (d.source_party = 'Internal' OR d.source_party IS NULL)
            """)
            _backfilled = conn.execute("SELECT COUNT(*) FROM document_productions").fetchone()[0]
            _dropped = _eligible - _backfilled
            if _dropped > 0:
                logger.warning(
                    "document_productions backfill dropped %d row(s) silently: "
                    "%d eligible, %d backfilled. Possible NOT NULL/UNIQUE/CHECK "
                    "violations unhandled by the current SELECT projections.",
                    _dropped, _eligible, _backfilled,
                )
            logger.info("Backfilled %d records into document_productions from existing Bates data", _backfilled)
    except Exception as _bf_err:
        logger.warning("document_productions backfill: %s", _bf_err)

    # ONE-TIME CLEANUP: remove inbound-sourced rows mistakenly inserted by the
    # pre-beta-2.11 backfill block above. The original backfill had no
    # source_party filter (authored 2026-03-26, three weeks before the
    # beta-2.10 inbound module existed), so any case DB where the user ran
    # inbound ingest before the first outbound production has defective
    # 'Original'-typed rows in document_productions for inbound control
    # numbers. The current backfill (now filtered by source_party) prevents
    # new damage; this block heals existing damage.
    #
    # Discriminator proof: outbound production flow applies
    # OUTBOUND_SOURCE_FILTER_SQL at every query (pages/5_Production.py base,
    # selection, and family-expansion paths), so no inbound document can
    # reach the legitimate document_productions INSERT. Therefore any
    # inbound-CN row in document_productions originated from the defective
    # backfill and is safe to delete. Sentinel-gated like
    # _production_runs_status_backfill_v1 above.
    try:
        _dp_cleanup_done = conn.execute(
            "SELECT 1 FROM case_settings WHERE setting_key = '_document_productions_inbound_cleanup_v1'"
        ).fetchone()
        if not _dp_cleanup_done:
            _dp_inbound_cn_filter = (
                "SELECT control_number FROM documents "
                "WHERE source_party IS NOT NULL AND source_party != 'Internal'"
            )
            _dirty_count = conn.execute(
                f"SELECT COUNT(*) FROM document_productions "
                f"WHERE control_number IN ({_dp_inbound_cn_filter})"
            ).fetchone()[0]
            if _dirty_count > 0:
                _sample_cns = [r['control_number'] for r in conn.execute(
                    f"SELECT DISTINCT dp.control_number FROM document_productions dp "
                    f"WHERE dp.control_number IN ({_dp_inbound_cn_filter}) LIMIT 5"
                ).fetchall()]
                logger.warning(
                    "document_productions inbound cleanup (Flag #12): removing %d "
                    "contaminated rows from pre-beta-2.11 backfill damage. "
                    "Sample control_numbers: %s",
                    _dirty_count, _sample_cns,
                )
                conn.execute(
                    f"DELETE FROM document_productions "
                    f"WHERE control_number IN ({_dp_inbound_cn_filter})"
                )
                logger.info(
                    "document_productions inbound cleanup: deletion complete (%d rows).",
                    _dirty_count,
                )
            conn.execute(
                "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) "
                "VALUES ('_document_productions_inbound_cleanup_v1', '1')"
            )
    except Exception as _cu_err:
        logger.warning("document_productions inbound cleanup: %s", _cu_err)

    conn.commit()

    return conn


# ---------------------------------------------------------------------------
# AUDIT TRAIL
# ---------------------------------------------------------------------------

def log_audit(case_folder, action, username=None, control_number=None,
              module=None, details=None, old_value=None, new_value=None, conn=None):
    """
    Write a single audit trail entry. Call after every user-initiated state change.
    NEVER raises — a failed audit write must not interrupt the main workflow.

    Action vocabulary (use exactly these strings):

      Pipeline / Processing:
        DOCUMENT_INGESTED, TEXT_EXTRACTED, DOCUMENT_IMAGED, DUPLICATE_MARKED,
        PROCESSING_STARTED, PROCESSING_COMPLETED, PROCESSING_ERROR,
        PROCESSING_CANCELLED, PROCESSING_RETRY, STATUS_CHANGED,
        NIST_EXCLUDED, CONTAINER_SCANNED, CONTAINER_RE_EXTRACT,
        CONTAINER_CHILD_DELETED, CONTAINER_CHILDREN_DELETED,

      Analytics:
        ANALYTICS_RUN, ANALYTICS_TAGS_CLEARED, NEARDUPE_FORCE_RERUN,

      Tags & Coding:
        TAG_APPLIED, TAG_REMOVED, TAGS_CHANGED,
        CODING_VALUE_CHANGED, CODING_FIELD_DELETED,
        CONFIDENTIALITY_DESIGNATED, PRIVILEGE_DISPOSITION_CHANGED,

      Review:
        COMMENT_ADDED, COMMENT_EDITED, SEARCH_EXECUTED, SEARCH_SAVED,
        SEARCH_DELETED, SEARCH_SHARED, SEARCH_UNSHARED,
        REVIEWER_NOTE_SAVED, REVIEWER_NOTE_DELETED,
        BATCH_CREATED, BATCH_ASSIGNED, BATCH_DOCUMENTS_MOVED,
        BATCH_STATUS_CHANGED, BATCHES_DELETED,
        NEARDUPE_DECISION, NEARDUPE_CLUSTER_APPROVED, NEARDUPE_CLUSTER_REOPENED,

      Redaction:
        REDACTION_SAVED, REDACTION_CLEARED, REDACTION_BURNED,

      Production:
        PRODUCTION_CREATED, BATES_ASSIGNED, PRODUCTION_EXPORTED,
        PRODUCTION_ABORTED, PRODUCTION_CANCELLED, PRODUCTION_RETRY,
        PRODUCTION_OCR_COMPLETE,
        INBOUND_INGESTED, PRIVILEGE_LOG_EXPORTED,
        PRODUCED_DOWNLOAD, EXCEPTION_REPORT_EXPORTED, PRIVILEGE_LOG_GENERATED,
        PRODUCTION_CATEGORY_SET, PRODUCTION_CATEGORY_BULK,
        PRODUCTION_CATEGORY_AUTO, PRODUCTION_CATEGORIES_UPDATED,

      Users & Auth:
        USER_LOGIN, USER_CREATED, USER_ROLE_CHANGED, USER_DELETED,
        PASSWORD_RESET, USER_VISIBILITY_CHANGED,

      Case Management:
        CASE_SETTING_CHANGED, MATTER_PROFILE_UPDATED,

      Custodians:
        CUSTODIAN_UPDATED, CUSTODIAN_RENAMED, CUSTODIAN_MERGED,
        CUSTODIAN_REASSIGNED, COLLECTION_RENAMED, COLLECTION_ASSIGNED,
        HOLD_STATUS_CHANGED, HOLD_DOCUMENT_UPLOADED, HOLD_DOCUMENT_DELETED,

      Exhibits:
        EXHIBIT_BINDER_EXPORTED, EXHIBIT_REMOVED, EXHIBIT_SET_DELETED,

      Split / Trim:
        DOCUMENT_SPLIT_CHILD, DOCUMENT_SPLIT_SOURCE,
        DOCUMENT_TRIM_CHILD, DOCUMENT_TRIM_SOURCE,

      Sync:
        FILEVINE_PUSH, FILEVINE_PULL, BYOS_PUSH, BYOS_PULL,
        SYNC_ERROR, SYNC_RETRY, SYNC_CONFIG_CHANGED,
        SYNC_REDACTION_IMPORTED, SYNC_REDACTION_OVERRIDE,

      Other:
        CLAWBACK_MARKED, REPORT_GENERATED, SEARCH_INDEX_REBUILT

    Conn parameter (added at C2 / Flag #18 narrow):

    If `conn` is provided, the caller's connection is used and the function
    does NOT commit and does NOT close it — the caller owns the transaction
    lifecycle. The audit row is staged into the caller's pending transaction;
    if the caller never commits, the audit entry is lost. Combined with the
    never-raise outer except, this means a caller-conn write that hits a
    SQLite error leaves the caller's transaction in a partial state with no
    audible signal — callers passing `conn` are responsible for their own
    transaction-error detection.

    If `conn` is None (default), a new connection is opened, the audit row
    is INSERTed and committed, and the connection is closed within this call
    — preserving the function's prior behavior exactly.
    """
    try:
        _own_conn = conn is None
        if _own_conn:
            conn = get_connection(case_folder)
        try:
            conn.execute(
                """INSERT INTO audit_log
                   (action, username, control_number, module, details, old_value, new_value)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (action, username, control_number, module, details, old_value, new_value)
            )
            if _own_conn:
                conn.commit()
        finally:
            if _own_conn:
                conn.close()
    except Exception:
        pass  # Audit logging must never crash the main workflow


def log_audit_batch(case_folder, entries, conn=None):
    """
    Write multiple audit entries in a single transaction. Use for high-volume
    operations (Analytics bulk tagging, Ingestor batch registration, etc.).

    Each entry is a dict with any subset of keys:
      action, username, control_number, module, details, old_value, new_value
    Missing keys default to None.

    Conn parameter (added at C2 / Flag #18 narrow): same semantics as
    `log_audit` — if `conn` is provided, caller owns commit and close; if
    `conn` is None (default), function opens, executes batch, commits, and
    closes within this call. See `log_audit` docstring for the full
    caller-conn + never-raise interaction notes.
    """
    try:
        _own_conn = conn is None
        if _own_conn:
            conn = get_connection(case_folder)
        try:
            rows = [
                {
                    'action': e.get('action'),
                    'username': e.get('username'),
                    'control_number': e.get('control_number'),
                    'module': e.get('module'),
                    'details': e.get('details'),
                    'old_value': e.get('old_value'),
                    'new_value': e.get('new_value'),
                }
                for e in entries
            ]
            conn.executemany(
                """INSERT INTO audit_log
                   (action, username, control_number, module, details, old_value, new_value)
                   VALUES (:action, :username, :control_number, :module, :details, :old_value, :new_value)""",
                rows
            )
            if _own_conn:
                conn.commit()
        finally:
            if _own_conn:
                conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TAG CATEGORY SYSTEM
# ---------------------------------------------------------------------------

DEFAULT_TAG_CATEGORIES = {
    "Privilege": {
        "is_privilege": True,
        "color": "#ff6b6b",
        "members": [
            "Attorney-Client Privilege",
            "Work Product",
            "Attorney-Client Privilege and Work Product",
            "Common Interest Privilege",
            "Joint Defense Privilege",
            "Trade Secret",
            "Marital Privilege",
            "Fifth Amendment",
            "Settlement Privilege (FRE 408)",
            "Self-Critical Analysis Privilege",
            "Executive / Deliberative Process Privilege",
            "Relevance Objection",
        ]
    },
    "Responsiveness": {
        "is_responsive": True,
        "color": "#51cf66",
        "members": [
            "Responsive",
            "Not Responsive",
            "Hot Document",
        ]
    },
    "Review Status": {
        "color": "#339af0",
        "members": [
            "Needs Review",
            "Suppressed",
        ]
    }
}


def get_tag_categories(case_folder):
    """
    Load tag category config from case_settings.
    Returns a dict of {category_name: {is_privilege, color, members:[...]}}.
    Falls back to DEFAULT_TAG_CATEGORIES if not yet configured.
    """
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT setting_value FROM case_settings WHERE setting_key='tag_categories'"
        ).fetchone()
        if row and row['setting_value']:
            cats = json.loads(row['setting_value'])
            # Backfill is_privilege for categories saved before the flag existed.
            # Match by name: any category named "Privilege" (case-insensitive)
            # that lacks the flag gets it set to True.
            for cat_name, cat_data in cats.items():
                if 'is_privilege' not in cat_data and cat_name.lower() == 'privilege':
                    cat_data['is_privilege'] = True
            return cats
    except Exception:
        pass
    finally:
        conn.close()
    return json.loads(json.dumps(DEFAULT_TAG_CATEGORIES))  # deep copy


def save_tag_categories(case_folder, categories):
    """
    Persist tag category config to case_settings.
    """
    conn = get_connection(case_folder)
    conn.execute(
        "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('tag_categories', ?)",
        (json.dumps(categories),)
    )
    conn.commit()
    conn.close()


def get_privilege_tag_members(case_folder):
    """
    Returns a flat list of all tag names that belong to categories
    with is_privilege=True. Used for dynamic privilege log queries.
    """
    cats = get_tag_categories(case_folder)
    members = []
    for cat_data in cats.values():
        if cat_data.get('is_privilege'):
            members.extend(cat_data.get('members', []))
    return members


def get_privilege_status(case_folder, control_number, conn=None):
    """Returns the privilege_status for a single document (NULL, 'Redact', or 'Withhold').

    Conn parameter (added at C2 / Flag #18 narrow):

    If `conn` is provided, the caller's connection is used and the function
    does NOT close it. If `conn` is None (default), a new connection is
    opened and closed within this call (preserves prior behavior).
    """
    _own_conn = conn is None
    if _own_conn:
        conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT privilege_status FROM documents WHERE control_number=?",
            (control_number,)
        ).fetchone()
    finally:
        if _own_conn:
            conn.close()
    return row['privilege_status'] if row else None


def set_privilege_status(case_folder, control_number, status, conn=None):
    """
    Sets privilege_status for a document.
    Status must be None, 'Redact', or 'Withhold'.

    Conn parameter (added at C2 / Flag #18 narrow):

    If `conn` is provided, the caller's connection is used and the function
    does NOT commit and does NOT close — the caller owns the transaction
    lifecycle. If `conn` is None (default), a new connection is opened, the
    UPDATE is committed, and the connection is closed within this call
    (preserves prior behavior).
    """
    assert status in (None, 'Redact', 'Withhold'), f"Invalid privilege_status: {status}"
    _own_conn = conn is None
    if _own_conn:
        conn = get_connection(case_folder)
    try:
        conn.execute(
            "UPDATE documents SET privilege_status=? WHERE control_number=?",
            (status, control_number)
        )
        if _own_conn:
            conn.commit()
    finally:
        if _own_conn:
            conn.close()


# ---------------------------------------------------------------------------
# PRODUCTION CATEGORY SYSTEM
# ---------------------------------------------------------------------------

def get_production_categories(case_folder):
    """Return list of production category dicts, sorted by sort_order.

    Each dict: {name, sort_order, color, keywords, extensions}.
    Returns empty list if no categories configured yet.
    """
    raw = get_case_setting(case_folder, 'production_categories')
    if not raw:
        return []
    try:
        data = json.loads(raw)
        cats = data.get('categories', [])
        return sorted(cats, key=lambda c: c.get('sort_order', 999))
    except (json.JSONDecodeError, TypeError):
        return []


def save_production_categories(case_folder, categories, username=None):
    """Persist production category list to case_settings.

    Detects renames by comparing old categories (matched by sort_order position)
    and propagates name changes to documents.production_category.
    """
    old_cats = get_production_categories(case_folder)
    old_names = {c['name'] for c in old_cats}
    new_names = {c['name'] for c in categories}

    # Detect renames: old name disappeared, new name appeared, same sort_order
    old_by_order = {c['sort_order']: c['name'] for c in old_cats}
    new_by_order = {c['sort_order']: c['name'] for c in categories}
    renames = {}
    for order, old_name in old_by_order.items():
        if old_name not in new_names and order in new_by_order:
            new_name = new_by_order[order]
            if new_name not in old_names:
                renames[old_name] = new_name

    # Detect deleted categories — clear from documents
    deleted_names = old_names - new_names - set(renames.keys())

    conn = get_connection(case_folder)
    try:
        # Propagate renames
        for old_name, new_name in renames.items():
            conn.execute(
                "UPDATE documents SET production_category = ? WHERE production_category = ?",
                (new_name, old_name)
            )

        # Clear deleted categories from documents
        for del_name in deleted_names:
            conn.execute(
                "UPDATE documents SET production_category = NULL WHERE production_category = ?",
                (del_name,)
            )

        # Save the category list
        conn.execute(
            "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('production_categories', ?)",
            (json.dumps({'categories': categories}),)
        )
        conn.commit()
    finally:
        conn.close()

    try:
        details = json.dumps({
            'count': len(categories),
            'names': [c['name'] for c in categories],
            'renames': renames,
            'deleted': list(deleted_names),
        })
        log_audit(case_folder, 'PRODUCTION_CATEGORIES_UPDATED',
                  username=username, module='Review', details=details)
    except Exception:
        pass


def update_document_production_category(case_folder, control_number, category_name,
                                         username=None):
    """Set production_category for a single document. Pass None to clear."""
    conn = get_connection(case_folder)
    try:
        old_row = conn.execute(
            "SELECT production_category FROM documents WHERE control_number = ?",
            (control_number,)
        ).fetchone()
        old_val = old_row['production_category'] if old_row else None

        conn.execute(
            "UPDATE documents SET production_category = ? WHERE control_number = ?",
            (category_name, control_number)
        )
        conn.commit()
    finally:
        conn.close()

    try:
        log_audit(case_folder, 'PRODUCTION_CATEGORY_SET',
                  username=username, control_number=control_number,
                  module='Review', old_value=old_val, new_value=category_name)
    except Exception:
        pass


def bulk_update_production_category(case_folder, control_numbers, category_name,
                                     username=None):
    """Set production_category for a list of documents. Audit log batch entry."""
    if not control_numbers:
        return
    conn = get_connection(case_folder)
    try:
        placeholders = ','.join('?' * len(control_numbers))
        conn.execute(
            f"UPDATE documents SET production_category = ? "
            f"WHERE control_number IN ({placeholders})",
            [category_name] + list(control_numbers)
        )
        conn.commit()
    finally:
        conn.close()

    try:
        log_audit(case_folder, 'PRODUCTION_CATEGORY_BULK',
                  username=username, module='Review',
                  details=json.dumps({
                      'count': len(control_numbers),
                      'category': category_name,
                  }),
                  new_value=category_name)
    except Exception:
        pass


def auto_categorize_documents(case_folder, dry_run=True, selected_control_numbers=None):
    """Apply keyword/extension rules to uncategorized documents.

    Returns dict: {category_name: [list of dicts with control_number, file_name,
                    record_type, date_sent, match_reason]}

    If dry_run=True, does not write to DB — returns preview for grid display.
    If dry_run=False and selected_control_numbers provided, updates ONLY those
        documents and returns results.
    If dry_run=False and selected_control_numbers is None, updates ALL matches.

    Matching priority:
    1. File extension match (highest confidence) — match_reason: "Extension: .msg"
    2. Filename keyword match (case-insensitive substring) — match_reason: "Filename: 'contract'"
    3. Email subject keyword match (for record_type='Email') — match_reason: "Subject: 'policy'"
    Documents matching multiple categories: first match by sort_order wins.
    Already-categorized documents are NEVER overwritten (WHERE production_category IS NULL).
    """
    cats = get_production_categories(case_folder)
    if not cats:
        return {}

    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT control_number, file_name, file_extension, record_type, "
            "       date_sent, email_subject "
            "FROM documents "
            "WHERE production_category IS NULL "
            "  AND processing_status IN ('Processed', 'Master')"
        ).fetchall()
    finally:
        conn.close()

    # Build results: {category_name: [matched docs]}
    results = {cat['name']: [] for cat in cats}
    # Track which control_numbers are already matched (first match wins)
    matched_cns = set()

    for cat in cats:  # iterate in sort_order (cats is pre-sorted)
        cat_name = cat['name']
        extensions = [e.lower().strip() for e in cat.get('extensions', []) if e.strip()]
        keywords = [k.lower().strip() for k in cat.get('keywords', []) if k.strip()]

        for row in rows:
            cn = row['control_number']
            if cn in matched_cns:
                continue

            file_name = (row['file_name'] or '').lower()
            file_ext = (row['file_extension'] or '').lower()
            record_type = row['record_type'] or ''
            subject = (row['email_subject'] or '').lower()
            match_reason = None

            # Priority 1: extension match
            if extensions and file_ext in extensions:
                match_reason = f"Extension: {file_ext}"

            # Priority 2: filename keyword
            if not match_reason and keywords:
                for kw in keywords:
                    if kw in file_name:
                        match_reason = f"Filename: '{kw}'"
                        break

            # Priority 3: email subject keyword
            if not match_reason and keywords and record_type == 'Email':
                for kw in keywords:
                    if kw in subject:
                        match_reason = f"Subject: '{kw}'"
                        break

            if match_reason:
                matched_cns.add(cn)
                results[cat_name].append({
                    'control_number': cn,
                    'file_name': row['file_name'],
                    'record_type': record_type,
                    'date_sent': row['date_sent'],
                    'match_reason': match_reason,
                })

    # Remove empty categories from results
    results = {k: v for k, v in results.items() if v}

    if dry_run:
        return results

    # Apply: write to DB
    total_applied = 0
    conn = get_connection(case_folder)
    try:
        for cat_name, docs in results.items():
            cns_to_update = [d['control_number'] for d in docs]
            if selected_control_numbers is not None:
                cns_to_update = [cn for cn in cns_to_update if cn in set(selected_control_numbers)]
            if not cns_to_update:
                continue
            placeholders = ','.join('?' * len(cns_to_update))
            conn.execute(
                f"UPDATE documents SET production_category = ? "
                f"WHERE control_number IN ({placeholders}) "
                f"AND production_category IS NULL",
                [cat_name] + cns_to_update
            )
            total_applied += len(cns_to_update)
        conn.commit()
    finally:
        conn.close()

    # Filter results to only show what was actually applied
    if selected_control_numbers is not None:
        sel_set = set(selected_control_numbers)
        results = {
            k: [d for d in v if d['control_number'] in sel_set]
            for k, v in results.items()
        }
        results = {k: v for k, v in results.items() if v}

    try:
        cat_counts = {k: len(v) for k, v in results.items()}
        log_audit(case_folder, 'PRODUCTION_CATEGORY_AUTO',
                  module='Review',
                  details=json.dumps({
                      'total_applied': total_applied,
                      'per_category': cat_counts,
                  }))
    except Exception:
        pass

    return results


def get_category_summary(case_folder, exclude_non_responsive=False):
    """Return dict of {category_name: doc_count} + {'Uncategorized': count}.

    Counts documents visible in the Review grid: non-container, non-duplicate,
    non-junk, non-suppressed.  When *exclude_non_responsive* is True, also
    excludes Non-Responsive / Not Responsive docs (aligns with the production
    query's default filters).
    """
    conn = get_connection(case_folder)
    try:
        sql = (
            "SELECT production_category, COUNT(*) as cnt "
            "FROM documents "
            "WHERE processing_status NOT IN ('Container_Scanned', 'Split_Source', 'Remediated') "
            "  AND processing_status NOT LIKE 'Duplicate%' "
            "  AND (tags IS NULL OR tags NOT LIKE '%Junk%') "
            "  AND (tags IS NULL OR tags NOT LIKE '%Suppressed%') "
        )
        if exclude_non_responsive:
            sql += (
                "  AND (tags IS NULL OR tags NOT LIKE '%Non-Responsive%') "
                "  AND (tags IS NULL OR tags NOT LIKE '%Not Responsive%') "
            )
        sql += "GROUP BY production_category"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()

    summary = {}
    for row in rows:
        cat = row['production_category'] if row['production_category'] else 'Uncategorized'
        summary[cat] = row['cnt']
    return summary


# ---------------------------------------------------------------------------
# REDACTION MARKS HELPERS
# ---------------------------------------------------------------------------

def save_redaction_marks(case_folder, control_number, page_number, marks_json, username):
    """
    Upsert redaction marks (JSON string) for a specific page of a document.
    """
    conn = get_connection(case_folder)
    try:
        conn.execute(
            """
            INSERT INTO redaction_marks (control_number, page_number, marks_json, created_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(control_number, page_number)
            DO UPDATE SET marks_json=excluded.marks_json, created_by=excluded.created_by,
                          created_at=CURRENT_TIMESTAMP
            """,
            (control_number, page_number, marks_json, username)
        )
        conn.commit()
    finally:
        conn.close()


def save_redaction_with_sync(case_folder, control_number, page_number, marks_json,
                             username, privilege_reasons, no_reason_sentinel,
                             target_redaction_status='Has_Redactions'):
    """
    Batched redaction save: upsert marks + sync tags/privilege/status in one connection.

    Never-raise contract: returns None on failure instead of raising.
    On success returns (old_tags, new_tags, old_priv_status, new_priv_status, old_redaction_status).
    Caller uses the return values for audit logging.
    """
    try:
        conn = get_connection(case_folder)
        try:
            # 1. Upsert marks
            conn.execute(
                """
                INSERT INTO redaction_marks (control_number, page_number, marks_json, created_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(control_number, page_number)
                DO UPDATE SET marks_json=excluded.marks_json, created_by=excluded.created_by,
                              created_at=CURRENT_TIMESTAMP
                """,
                (control_number, page_number, marks_json, username)
            )

            # 2. Read ALL marks for this document (tag sync needs cross-page view)
            all_rows = conn.execute(
                "SELECT marks_json FROM redaction_marks WHERE control_number=?",
                (control_number,)
            ).fetchall()
            mark_reasons = set()
            for row in all_rows:
                for m in (json.loads(row['marks_json']) if row['marks_json'] else []):
                    r = m.get('reason', '')
                    if r and r != no_reason_sentinel:
                        mark_reasons.add(r)

            # 3. Read current document state
            doc_row = conn.execute(
                "SELECT tags, privilege_status, redaction_status FROM documents WHERE control_number=?",
                (control_number,)
            ).fetchone()
            old_tags = (doc_row['tags'] or '') if doc_row else ''
            old_priv_status = doc_row['privilege_status'] if doc_row else None
            old_redaction_status = doc_row['redaction_status'] if doc_row else None

            # 4. Compute new tags: keep non-privilege tags, replace privilege tags with mark reasons
            all_priv = set(privilege_reasons)
            existing = [t.strip() for t in old_tags.replace(';', ',').split(',') if t.strip()]
            new_tags_list = [t for t in existing if t not in all_priv]
            new_tags_list.extend(sorted(mark_reasons))
            new_tags = ', '.join(new_tags_list)

            # 5. Compute new privilege_status (never overwrite 'Withhold')
            new_priv_status = old_priv_status
            if old_priv_status != 'Withhold':
                new_priv_status = 'Redact' if mark_reasons else None

            # 6. Compute new redaction_status
            new_redaction_status = target_redaction_status if target_redaction_status else old_redaction_status

            # 7. Single UPDATE for tags + privilege_status + redaction_status
            conn.execute(
                "UPDATE documents SET tags=?, privilege_status=?, redaction_status=? WHERE control_number=?",
                (new_tags, new_priv_status, new_redaction_status, control_number)
            )
            conn.commit()
            return (old_tags, new_tags, old_priv_status, new_priv_status, old_redaction_status)
        finally:
            conn.close()
    except Exception:
        return None


def get_redaction_marks(case_folder, control_number, page_number):
    """
    Retrieve stored redaction marks JSON for a specific page, or None.
    """
    conn = get_connection(case_folder)
    row = conn.execute(
        "SELECT marks_json FROM redaction_marks WHERE control_number=? AND page_number=?",
        (control_number, page_number)
    ).fetchone()
    conn.close()
    return row['marks_json'] if row else None


def get_all_redaction_marks(case_folder, control_number):
    """
    Retrieve all saved redaction mark rows for a document as a list of dicts.
    """
    conn = get_connection(case_folder)
    rows = conn.execute(
        "SELECT page_number, marks_json FROM redaction_marks WHERE control_number=? ORDER BY page_number",
        (control_number,)
    ).fetchall()
    conn.close()
    return [{'page_number': r['page_number'], 'marks_json': r['marks_json']} for r in rows]


def has_redaction_marks(case_folder, control_number):
    """Return True if the document has any redaction mark rows saved."""
    conn = get_connection(case_folder)
    row = conn.execute(
        "SELECT 1 FROM redaction_marks WHERE control_number=? LIMIT 1",
        (control_number,)
    ).fetchone()
    conn.close()
    return row is not None


def clear_redaction_marks(case_folder, control_number, page_number=None):
    """
    Delete redaction marks for a document. If page_number is given, only clears
    that page. Otherwise clears all pages for the document.
    """
    conn = get_connection(case_folder)
    if page_number is not None:
        conn.execute(
            "DELETE FROM redaction_marks WHERE control_number=? AND page_number=?",
            (control_number, page_number)
        )
    else:
        conn.execute(
            "DELETE FROM redaction_marks WHERE control_number=?",
            (control_number,)
        )
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# CASE LIFECYCLE STATUS
# ---------------------------------------------------------------------------

def get_case_status(case_folder):
    """
    Return the current case lifecycle status: 'Active', 'On Hold', or 'Closed'.
    Defaults to 'Active' if not set (safe for existing cases).
    """
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT setting_value FROM case_settings WHERE setting_key='case_status'"
        ).fetchone()
        if row and row['setting_value'] in ('Active', 'On Hold', 'Closed'):
            return row['setting_value']
    except Exception:
        pass
    finally:
        conn.close()
    return 'Active'


def set_case_status(case_folder, status):
    """
    Persist case lifecycle status. status must be 'Active', 'On Hold', or 'Closed'.
    """
    if status not in ('Active', 'On Hold', 'Closed'):
        raise ValueError(f'Invalid case status: {status!r}')
    conn = get_connection(case_folder)
    conn.execute(
        "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('case_status', ?)",
        (status,)
    )
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# PRIVILEGE ABBREVIATION MAP + FUZZY MATCHER (shared by Production + Sync)
# ---------------------------------------------------------------------------

PRIV_ABBREV_MAP = {
    'ac':                    'Attorney-Client Privilege',
    'a-c':                   'Attorney-Client Privilege',
    'attorney client':       'Attorney-Client Privilege',
    'attorney-client':       'Attorney-Client Privilege',
    'ac priv':               'Attorney-Client Privilege',
    'acp':                   'Attorney-Client Privilege',
    'wp':                    'Work Product',
    'work prod':             'Work Product',
    'work product':          'Work Product',
    'awp':                   'Work Product',
    'ci':                    'Common Interest Privilege',
    'common interest':       'Common Interest Privilege',
    'ac/wp':                 'Attorney-Client Privilege and Work Product',
    'acp/wp':                'Attorney-Client Privilege and Work Product',
    'jda':                   'Joint Defense Privilege',
    'joint defense':         'Joint Defense Privilege',
    'ts':                    'Trade Secret',
    'trade secret':          'Trade Secret',
    'fre 408':               'Settlement Privilege (FRE 408)',
    'settlement':            'Settlement Privilege (FRE 408)',
    'mediation':             'Settlement Privilege (FRE 408)',
    '5th':                   'Fifth Amendment',
    'fifth amendment':       'Fifth Amendment',
    'marital':               'Marital Privilege',
}


def fuzzy_match_privilege_reason(raw_text, priv_members=None):
    """
    Match raw annotation/tag text to a canonical privilege reason.
    Returns (canonical_reason, confidence) where confidence is one of:
      'exact'   - direct key match in PRIV_ABBREV_MAP
      'fuzzy'   - word-boundary regex match in PRIV_ABBREV_MAP
      'member'  - direct or substring match against priv_members list
      'orphan'  - no match; returns ('Redaction: {raw}', 'orphan')
    """
    import re as _re
    if not raw_text or not str(raw_text).strip():
        return ('Redaction: (empty)', 'orphan')

    t = str(raw_text).strip()
    t_lower = t.lower()

    # 1. Exact key match
    if t_lower in PRIV_ABBREV_MAP:
        return (PRIV_ABBREV_MAP[t_lower], 'exact')

    # 2. Word-boundary regex (longest key first to avoid 'wp' swallowing 'awp')
    for abbrev in sorted(PRIV_ABBREV_MAP, key=len, reverse=True):
        if _re.search(r'\b' + _re.escape(abbrev) + r'\b', t_lower):
            return (PRIV_ABBREV_MAP[abbrev], 'fuzzy')

    # 3. Direct match against privilege member list
    if priv_members:
        for m in priv_members:
            if t_lower == m.lower():
                return (m, 'member')
            if t_lower in m.lower() or m.lower() in t_lower:
                return (m, 'member')

    # 4. Orphan
    return (f'Redaction: {t}', 'orphan')


# ---------------------------------------------------------------------------
# CLAWBACK / INADVERTENT DISCLOSURE
# ---------------------------------------------------------------------------

def mark_clawback(case_folder, control_number, status, demand_date, notes, username):
    """
    Set clawback_status and clawback_date on a document and write audit entry.
    status: 'Clawback_Demanded' | 'Clawback_Resolved' | None (to clear)
    demand_date: ISO date string (YYYY-MM-DD) or empty string.
    Raises on DB failure — callers must handle via _safe_write or try/except.
    """
    conn = get_connection(case_folder)
    conn.execute(
        "UPDATE documents SET clawback_status=?, clawback_date=? WHERE control_number=?",
        (status or None, demand_date or None, control_number)
    )
    conn.commit()
    conn.close()
    log_audit(
        case_folder, "CLAWBACK_MARKED",
        username=username,
        control_number=control_number,
        module="Review",
        details=notes or "",
        new_value=status or "cleared",
    )


# ---------------------------------------------------------------------------
# SUPPLEMENTAL PRODUCTION — Last Bates Continuity
# ---------------------------------------------------------------------------

def get_last_bates_info(case_folder):
    """
    Return the saved Bates continuity record from the most recent production run,
    or None if no production has been completed yet.
    Returns dict: {'prefix': str, 'end_num': int, 'prod_name': str, 'padding': int}
    """
    try:
        conn = get_connection(case_folder)
        row = conn.execute(
            "SELECT setting_value FROM case_settings WHERE setting_key='last_bates_info'"
        ).fetchone()
        conn.close()
        if row and row[0]:
            import json as _json
            return _json.loads(row[0])
    except Exception:
        pass
    return None


def save_last_bates_info(case_folder, prefix, end_num, prod_name, padding=6):
    """
    Persist Bates continuity record after a successful production run.
    Called by 5_Production.py immediately after production completes.
    """
    import json as _json
    payload = _json.dumps({
        'prefix': prefix,
        'end_num': int(end_num),
        'prod_name': prod_name,
        'padding': int(padding),
    })
    conn = get_connection(case_folder)
    conn.execute(
        "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('last_bates_info', ?)",
        (payload,)
    )
    conn.commit()
    conn.close()


def recalculate_last_bates_info(case_folder):
    """
    Recalculate and persist the Bates continuity record from remaining produced documents.
    Called after a production is deleted to prevent stale continuity data.
    If no produced documents remain, the record is deleted.
    """
    import json as _json
    import re as _re
    conn = get_connection(case_folder)
    try:
        # Query junction table as authoritative source; fall back to documents cache
        try:
            rows = conn.execute(
                "SELECT begdoc, enddoc, production_volume FROM document_productions "
                "ORDER BY enddoc DESC"
            ).fetchall()
        except Exception:
            rows = conn.execute(
                "SELECT begdoc, enddoc, production_volume FROM documents "
                "WHERE enddoc IS NOT NULL AND enddoc != '' "
                "ORDER BY enddoc DESC"
            ).fetchall()

        if not rows:
            # No produced documents remain — clear the record
            conn.execute(
                "DELETE FROM case_settings WHERE setting_key='last_bates_info'"
            )
            conn.commit()
            conn.close()
            return

        # Find the highest Bates number across all remaining productions
        highest_num = 0
        highest_prefix = ''
        highest_prod = ''
        highest_padding = 6

        for row in rows:
            enddoc = row['enddoc'] or ''
            m = _re.match(r'^(.+?)-(\d+)$', enddoc)
            if m:
                prefix = m.group(1)
                num = int(m.group(2))
                padding = len(m.group(2))
                if num > highest_num:
                    highest_num = num
                    highest_prefix = prefix
                    highest_prod = row['production_volume'] or ''
                    highest_padding = padding

        if highest_num > 0:
            payload = _json.dumps({
                'prefix': highest_prefix,
                'end_num': highest_num,
                'prod_name': highest_prod,
                'padding': highest_padding,
            })
            conn.execute(
                "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('last_bates_info', ?)",
                (payload,)
            )
        else:
            conn.execute(
                "DELETE FROM case_settings WHERE setting_key='last_bates_info'"
            )

        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def get_clawback_summary(case_folder):
    """
    Return list of dicts for all documents with an active clawback status.
    Each dict has: control_number, file_name, custodian, clawback_status, clawback_date.
    """
    try:
        conn = get_connection(case_folder)
        rows = conn.execute("""
            SELECT control_number, file_name, custodian, clawback_status, clawback_date
            FROM documents
            WHERE clawback_status IS NOT NULL AND clawback_status != ''
            ORDER BY clawback_date DESC, control_number
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# CUSTODIAN MANAGEMENT
# ---------------------------------------------------------------------------

def get_custodians(case_folder):
    """Return all custodian records as list of dicts."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("SELECT * FROM custodians ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_custodian(case_folder, name):
    """Return a single custodian record by name, or None."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute("SELECT * FROM custodians WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def sync_custodians_from_documents(case_folder):
    """
    Ensure every unique custodian in documents has a matching record
    in the custodians registry. Called on page load and after ingestion.
    Idempotent — existing records are preserved.
    """
    conn = get_connection(case_folder)
    try:
        conn.execute("""
            INSERT OR IGNORE INTO custodians (name)
            SELECT DISTINCT custodian FROM documents
            WHERE custodian IS NOT NULL AND custodian != ''
              AND custodian NOT IN (SELECT name FROM custodians)
        """)
        conn.commit()
    finally:
        conn.close()


def get_hold_documents(case_folder, custodian_name):
    """Return all hold documents for a custodian as list of dicts."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT * FROM hold_documents WHERE custodian_name = ? ORDER BY upload_date DESC",
            (custodian_name,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_custodian_inventory_df_data(case_folder):
    """Return custodian inventory data for DataFrame display.

    Returns list[dict] with keys: custodian, hold_status, title, department,
    doc_count, total_size_kb.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT c.name as custodian,
                   c.hold_status,
                   c.title,
                   c.department,
                   COUNT(d.id) as doc_count,
                   COALESCE(SUM(d.file_size_kb), 0) as total_size_kb
            FROM custodians c
            LEFT JOIN documents d ON d.custodian = c.name
                AND d.processing_status NOT IN ('Container_Scanned', 'Split_Source')
            GROUP BY c.name
            ORDER BY doc_count DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_custodian_doc_stats(case_folder, name):
    """Return document statistics for a custodian.

    Returns dict with keys: doc_count, email_count, date_min, date_max.
    """
    conn = get_connection(case_folder)
    try:
        _shell_filter = " AND processing_status NOT IN ('Container_Scanned', 'Split_Source')"
        doc_count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE custodian = ?" + _shell_filter, (name,)
        ).fetchone()[0]
        email_count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE custodian = ? AND record_type = 'Email'" + _shell_filter,
            (name,)
        ).fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(date_created), MAX(date_created) FROM documents"
            " WHERE custodian = ? AND date_created IS NOT NULL" + _shell_filter,
            (name,)
        ).fetchone()
        return {
            'doc_count': doc_count,
            'email_count': email_count,
            'date_min': date_range[0] if date_range else None,
            'date_max': date_range[1] if date_range else None,
        }
    finally:
        conn.close()


def update_custodian_fields(case_folder, name, **fields):
    """Update custodian profile fields. Only whitelisted fields are accepted.

    Supported kwargs: title, department, email, notes, data_sources.
    """
    allowed = {'title', 'department', 'email', 'notes', 'data_sources'}
    filtered = {k: v for k, v in fields.items() if k in allowed}
    if not filtered:
        return
    set_clause = ', '.join(f"{k}=?" for k in filtered)
    set_clause += ', updated_at=CURRENT_TIMESTAMP'
    values = list(filtered.values()) + [name]
    conn = get_connection(case_folder)
    try:
        conn.execute(f"UPDATE custodians SET {set_clause} WHERE name = ?", values)
        conn.commit()
    finally:
        conn.close()


def rename_custodian(case_folder, old_name, new_name):
    """Rename a custodian atomically across documents, custodians, and hold_documents.

    Returns the count of affected documents. Raises on failure (no partial commit).
    """
    conn = get_connection(case_folder)
    try:
        affected = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE custodian = ?", (old_name,)
        ).fetchone()[0]
        conn.execute("UPDATE documents SET custodian = ? WHERE custodian = ?",
                     (new_name, old_name))
        conn.execute("UPDATE custodians SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                     (new_name, old_name))
        conn.execute("UPDATE hold_documents SET custodian_name = ? WHERE custodian_name = ?",
                     (new_name, old_name))
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def merge_custodians(case_folder, source_name, target_name):
    """Merge source custodian into target atomically.

    Reassigns all documents and hold documents, then deletes the source custodian record.
    Returns the count of documents moved. Raises on failure (no partial commit).
    """
    conn = get_connection(case_folder)
    try:
        moved = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE custodian = ?", (source_name,)
        ).fetchone()[0]
        conn.execute("UPDATE documents SET custodian = ? WHERE custodian = ?",
                     (target_name, source_name))
        conn.execute("UPDATE hold_documents SET custodian_name = ? WHERE custodian_name = ?",
                     (target_name, source_name))
        conn.execute("DELETE FROM custodians WHERE name = ?", (source_name,))
        conn.commit()
        return moved
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# COLLECTION SCOPE
# ---------------------------------------------------------------------------

def get_collection_scope(case_folder, custodian_id):
    """Return all collection scope rows for a given custodian."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT * FROM collection_scope WHERE custodian_id = ? ORDER BY source_name",
            (custodian_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def upsert_collection_scope(case_folder, custodian_id, source_name, status,
                            justification, reviewed_by):
    """Insert or update a collection scope entry."""
    conn = get_connection(case_folder)
    try:
        conn.execute("""
            INSERT INTO collection_scope
                (custodian_id, source_name, status, justification, reviewed_by, reviewed_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(custodian_id, source_name) DO UPDATE SET
                status = excluded.status,
                justification = excluded.justification,
                reviewed_by = excluded.reviewed_by,
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
        """, (custodian_id, source_name, status, justification, reviewed_by))
        conn.commit()
    finally:
        conn.close()


def get_all_collection_scope(case_folder):
    """Return all collection scope rows joined with custodian names (for reports)."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT c.name AS custodian, cs.source_name, cs.status,
                   cs.justification, cs.reviewed_by, cs.reviewed_at
            FROM collection_scope cs
            JOIN custodians c ON c.id = cs.custodian_id
            ORDER BY c.name, cs.source_name
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def seed_collection_scope(case_folder, custodian_id, source_names):
    """Bulk-insert Pending scope entries for sources not yet tracked."""
    conn = get_connection(case_folder)
    try:
        for src in source_names:
            conn.execute("""
                INSERT OR IGNORE INTO collection_scope (custodian_id, source_name, status)
                VALUES (?, ?, 'Pending')
            """, (custodian_id, src))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DE-NIST CONFIGURATION
# ---------------------------------------------------------------------------

# Default NIST extensions — used as fallback when no case-level config exists
DEFAULT_NIST_EXTENSIONS = [
    '.exe', '.dll', '.sys', '.drv', '.ocx', '.cpl', '.scr',
    '.msi', '.msp', '.mst', '.cab', '.cat', '.inf',
    '.tmp', '.temp', '.log', '.dmp', '.etl',
    '.lnk', '.url', '.ini', '.dat', '.db-journal',
    '.thumbs.db', '.ds_store',
    '.pf', '.mui', '.nls', '.tlb',
]


def get_nist_extensions(case_folder):
    """Return the NIST exclusion extension list for a case. Falls back to default."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT setting_value FROM case_settings WHERE setting_key='nist_extensions'"
        ).fetchone()
        if row and row['setting_value']:
            return json.loads(row['setting_value'])
        return list(DEFAULT_NIST_EXTENSIONS)
    finally:
        conn.close()


def set_nist_extensions(case_folder, extensions):
    """Save the NIST exclusion extension list for a case."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('nist_extensions', ?)",
            (json.dumps(extensions),)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CONFIDENTIALITY DESIGNATIONS
# ---------------------------------------------------------------------------

def get_confidentiality_designation(case_folder, control_number):
    """Return the confidentiality designation for a document, or None."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT confidentiality_designation FROM documents WHERE control_number = ?",
            (control_number,)
        ).fetchone()
        return row['confidentiality_designation'] if row else None
    finally:
        conn.close()


def set_confidentiality_designation(case_folder, control_number, designation):
    """Set the confidentiality designation for a document."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "UPDATE documents SET confidentiality_designation = ? WHERE control_number = ?",
            (designation, control_number)
        )
        conn.commit()
    finally:
        conn.close()


def get_confidentiality_levels(case_folder):
    """Return the list of available confidentiality levels for this case."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT setting_value FROM case_settings WHERE setting_key='confidentiality_levels'"
        ).fetchone()
        if row:
            return json.loads(row[0])
        return ['Confidential', 'Highly Confidential', 'Attorneys Eyes Only']
    finally:
        conn.close()


def set_confidentiality_levels(case_folder, levels_list):
    """Persist the confidentiality levels list."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('confidentiality_levels', ?)",
            (json.dumps(levels_list),)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DOCUMENT NOTES
# ---------------------------------------------------------------------------

def get_document_notes(case_folder, control_number):
    """Return all notes for a document, ordered by updated_at DESC."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT * FROM document_notes WHERE control_number = ? ORDER BY updated_at DESC",
            (control_number,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_document_note(case_folder, control_number, username):
    """Return single note for this user on this document, or None."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT * FROM document_notes WHERE control_number = ? AND username = ?",
            (control_number, username)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_document_note(case_folder, control_number, username, note_text):
    """INSERT OR REPLACE a note. Sets created_at on insert, updated_at always."""
    conn = get_connection(case_folder)
    try:
        now = datetime.now().isoformat()
        # Check if exists to preserve created_at
        existing = conn.execute(
            "SELECT created_at FROM document_notes WHERE control_number = ? AND username = ?",
            (control_number, username)
        ).fetchone()
        created = existing['created_at'] if existing else now
        conn.execute(
            "INSERT OR REPLACE INTO document_notes (control_number, username, note_text, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (control_number, username, note_text, created, now)
        )
        conn.commit()
    finally:
        conn.close()


def delete_document_note(case_folder, control_number, username):
    """Delete a specific note."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "DELETE FROM document_notes WHERE control_number = ? AND username = ?",
            (control_number, username)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PRODUCTION HISTORY
# ---------------------------------------------------------------------------

def record_production_run(case_folder, run_dict):
    """Record a production run. INSERT OR REPLACE by production_name.

    Accepts optional `status` (default 'in_progress') and `direction`
    (default 'outbound') in run_dict. INSERT OR REPLACE semantics mean
    calling this multiple times with the same production_name updates
    the existing row — used by the Pass 1 → pass1_complete → finalized
    state machine for outbound, and single-shot for inbound.
    """
    conn = get_connection(case_folder)
    try:
        conn.execute("""
            INSERT OR REPLACE INTO production_runs
                (production_name, created_at, created_by, format, mode,
                 bates_prefix, bates_start, bates_end, document_count,
                 withheld_count, redacted_count, error_count,
                 endorsement_text, settings_json, status, direction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_dict['production_name'], run_dict['created_at'],
            run_dict['created_by'], run_dict['format'], run_dict['mode'],
            run_dict.get('bates_prefix'), run_dict.get('bates_start'),
            run_dict.get('bates_end'), run_dict.get('document_count', 0),
            run_dict.get('withheld_count', 0), run_dict.get('redacted_count', 0),
            run_dict.get('error_count', 0), run_dict.get('endorsement_text'),
            run_dict.get('settings_json'),
            run_dict.get('status', 'in_progress'),
            run_dict.get('direction', 'outbound'),
        ))
        conn.commit()
    finally:
        conn.close()


def get_production_runs(case_folder):
    """Return all production runs ordered by created_at DESC."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT * FROM production_runs ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def get_production_run(case_folder, production_name):
    """Return a single production run by name, or None."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT * FROM production_runs WHERE production_name = ?",
            (production_name,)
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def update_production_status(case_folder, production_name, status):
    """Update the `status` column on a production_runs row. Never-raise contract.

    Valid status values (outbound lifecycle):
      in_progress, pass1_complete, finalizing, finalized, aborted
    Inbound rows are created directly with status='finalized'.
    """
    try:
        conn = get_connection(case_folder)
        try:
            conn.execute(
                "UPDATE production_runs SET status = ? WHERE production_name = ?",
                (status, production_name)
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # Never-raise; status updates must not break the production flow


def get_productions_with_staging_files(case_folder):
    """Return (production_name, status) tuples for outbound productions, for the
    orphan detector to correlate with TEMP_*/STAGED_* files on disk.

    Filtered to direction='outbound' since inbound productions never stage files.
    Returns empty list if the schema is missing (early-init defensive).
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT production_name, status FROM production_runs WHERE direction = 'outbound'"
        ).fetchall()
        return [(r['production_name'], r['status']) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def get_production_history(case_folder, direction=None):
    """Unified production history listing for both inbound and outbound.

    direction=None returns all rows. 'outbound' or 'inbound' filters.
    Ordered by created_at DESC (newest first).
    """
    conn = get_connection(case_folder)
    try:
        if direction is None:
            rows = conn.execute(
                "SELECT * FROM production_runs ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM production_runs WHERE direction = ? ORDER BY created_at DESC",
                (direction,)
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PRODUCTION JUNCTION TABLE
# ---------------------------------------------------------------------------

def refresh_production_cache(case_folder, control_number=None):
    """
    Syncs the convenience cache columns (begdoc, enddoc, production_volume) on
    the documents table from the authoritative document_productions junction table.

    If control_number is provided, updates only that document.
    If None, updates all documents.

    Cache rule: latest production record wins (highest id = most recent insert).
    """
    conn = get_connection(case_folder)
    try:
        if control_number:
            latest = conn.execute("""
                SELECT begdoc, enddoc, production_volume
                FROM document_productions
                WHERE control_number = ?
                ORDER BY id DESC LIMIT 1
            """, (control_number,)).fetchone()

            if latest:
                conn.execute(
                    "UPDATE documents SET begdoc=?, enddoc=?, production_volume=? WHERE control_number=?",
                    (latest['begdoc'], latest['enddoc'], latest['production_volume'], control_number)
                )
            else:
                conn.execute(
                    "UPDATE documents SET begdoc=NULL, enddoc=NULL, production_volume=NULL WHERE control_number=?",
                    (control_number,)
                )
        else:
            conn.execute("UPDATE documents SET begdoc=NULL, enddoc=NULL, production_volume=NULL")
            conn.execute("""
                UPDATE documents SET
                    begdoc = dp.begdoc,
                    enddoc = dp.enddoc,
                    production_volume = dp.production_volume
                FROM (
                    SELECT control_number, begdoc, enddoc, production_volume
                    FROM document_productions
                    WHERE id IN (
                        SELECT MAX(id) FROM document_productions GROUP BY control_number
                    )
                ) dp
                WHERE documents.control_number = dp.control_number
            """)
        conn.commit()
    finally:
        conn.close()


def get_document_productions(case_folder, control_number):
    """Returns all production records for a document, newest first."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT * FROM document_productions
            WHERE control_number = ?
            ORDER BY id DESC
        """, (control_number,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_production_volume_records(case_folder, volume_name):
    """Returns all production records for a volume, ordered by begdoc."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT * FROM document_productions
            WHERE production_volume = ?
            ORDER BY begdoc
        """, (volume_name,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# INBOUND PRODUCTIONS — opposing-counsel deliveries ingested via the inbound
# module. Docs tagged source_party != 'Internal' AND source_party IS NOT NULL.
# (beta-2.10 Commit 5 — migrated from inline SQL in pages/5_Production.py
# tab_inbound, in preparation for Commit 6's module extraction.)
# ---------------------------------------------------------------------------

def inbound_production_run_name(source_party, production_volume):
    """Construct the production_runs.production_name value for an inbound
    production. Single source of truth for the format — the Commit 6 ingest
    path and the Commit 5 purge path MUST both go through this helper to
    guarantee round-trip correctness. Changing the format here changes it
    in both places simultaneously.

    Format (pinned; change with a matching test update in
    tests/test_inbound_db.py):
        "INBOUND: {source_party} - {production_volume}"

    Inputs containing the ` - ` delimiter substring are rejected by
    validate_inbound_production_identifiers() below (Commit 6 Phase C)
    because two different logical (source_party, production_volume) pairs
    can otherwise produce the same composite string (e.g., ("A - B", "C")
    and ("A", "B - C") both resolve to "INBOUND: A - B - C"). Both
    ingest-side and purge-side call sites MUST validate inputs through
    that helper before using this formatter.
    """
    return f"INBOUND: {source_party} - {production_volume}"


# Reserved delimiter substring — any user input containing this is rejected
# by validate_inbound_production_identifiers(). Changing this constant
# would change the semantics of inbound_production_run_name() and force a
# data migration — do not change lightly.
_INBOUND_NAME_RESERVED_DELIMITER = ' - '


def validate_inbound_production_identifiers(source_party, production_volume):
    """Validate user-supplied identifiers before constructing an inbound
    production's composite name.

    Called from the ingest UI pre-submit (to disable the submit button and
    display field-level errors) AND from the ingest handler as a
    defense-in-depth guard before any DB writes. Both call sites MUST use
    this helper — duplicating validation logic is how drift sneaks in.

    Rules (rejected inputs):
      - Empty after strip (required fields).
      - Contains the ` - ` reserved delimiter (composite-name safety;
        see inbound_production_run_name docstring for the collision
        counterexample).
      - Length > 100 chars (UX-motivated limit, not schema-driven —
        both source_party and production_volume map to unbounded TEXT
        columns; the cap guards display readability in dashboard rows,
        audit log payloads, and composite names).

    Returns:
        list[str]: user-facing error messages (empty list = valid). Safe
        to render directly via st.error() / st.warning().
    """
    errors = []
    for label, value in (('Source Party', source_party),
                         ('Production Volume', production_volume)):
        sv = (value or '').strip()
        if not sv:
            errors.append(f"{label} is required.")
            continue
        if _INBOUND_NAME_RESERVED_DELIMITER in sv:
            errors.append(
                f"{label} cannot contain '{_INBOUND_NAME_RESERVED_DELIMITER}' "
                f"(reserved as the composite-name delimiter). Use a different "
                f"separator or remove the substring."
            )
        if len(sv) > 100:
            errors.append(
                f"{label} exceeds 100 characters. Use a shorter identifier."
            )
    return errors


def get_inbound_productions(case_folder):
    """Return a dashboard summary of existing inbound production volumes.

    One row per (source_party, production_volume) pair with the document
    count, ordered alphabetically by party then volume. Internal/custodial
    documents are excluded — only opposing-counsel deliveries appear.

    Returns:
        list[dict]: each dict has keys `source_party`, `production_volume`,
        `doc_count`. Empty list if no inbound productions exist or if the
        schema is somehow missing (defensive try/except).
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT source_party, production_volume, COUNT(*) as doc_count
            FROM documents
            WHERE source_party IS NOT NULL AND source_party != 'Internal'
            GROUP BY source_party, production_volume
            ORDER BY source_party, production_volume
        """).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def purge_inbound_volume(case_folder, source_party, production_volume):
    """Atomically purge an inbound production volume from SQLite.

    Performs three operations in a single transaction:
      1. SELECT opensearch_id list (for caller's OpenSearch cleanup)
      2. DELETE matching rows from documents
      3. DELETE the matching row from production_runs
         (identified via inbound_production_run_name() — the single source
         of truth for the composite name format)

    Failure semantics: if any step raises (FK violation, disk error,
    integrity constraint, etc.), the entire transaction rolls back. The
    function raises the underlying exception — callers get all-or-nothing.
    This is NOT a never-raise helper; failures must propagate so the caller
    knows the purge didn't complete and can avoid doing OpenSearch cleanup
    for a set that's still in SQLite.

    OpenSearch cleanup stays at the caller site — OS operations belong in
    os_manager.py, not here. This helper returns the IDs the caller needs
    for that cleanup.

    Returns:
        list[str]: opensearch_id values that were associated with the
        deleted documents (caller uses for OpenSearch bulk delete).
    """
    conn = get_connection(case_folder)
    try:
        with conn:  # auto-commit on success, rollback on any exception
            os_ids = [
                r['opensearch_id'] for r in conn.execute(
                    "SELECT opensearch_id FROM documents "
                    "WHERE source_party = ? AND production_volume = ? "
                    "AND opensearch_id IS NOT NULL",
                    (source_party, production_volume),
                ).fetchall()
            ]
            conn.execute(
                "DELETE FROM documents "
                "WHERE source_party = ? AND production_volume = ?",
                (source_party, production_volume),
            )
            conn.execute(
                "DELETE FROM production_runs "
                "WHERE production_name = ? AND direction = 'inbound'",
                (inbound_production_run_name(source_party, production_volume),),
            )
        return os_ids
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# INBOUND UPSERT TEMPLATE — module-scope SQL for batch ingest of inbound docs
# (beta-2.10 Commit 5)
# ---------------------------------------------------------------------------
# What this is: the INSERT ... ON CONFLICT DO UPDATE template consumed by
# upsert_inbound_documents_batch() below. Takes a 22-column tuple per row
# (processing_status is hardcoded to 'Imported' in the VALUES clause, so it
# is NOT part of the caller-supplied tuple; the VALUES clause has 23 columns
# but only 22 parameter placeholders).
#
# Why module-scope: this template is the single source of truth for the
# inbound-ingest SQL shape. Keeping it at module scope (not function-local)
# makes the column list visible alongside the helper's docstring, allows
# the test suite to reference it for shape assertions, and pins the schema
# contract against silent drift. If a future contributor duplicates this
# SQL into a function body to "clean up", the duplication is the bug.
#
# ON CONFLICT DO UPDATE semantics (PINNED — do not add fields without
# updating the test):
#   Updates on conflict: dynamic_metadata, full_path, has_text
#     → these are the three fields where a re-ingest is expected to
#       refresh the existing row (the load file may have updated metadata,
#       the file may have moved on disk, the text-extraction result may
#       have changed).
#   Preserves on conflict: ALL OTHER fields on the existing row, including
#     tags, privilege_status, production_category, custodian,
#     confidentiality_designation, reviewed_by, reviewed_at, begdoc, enddoc,
#     source_party, production_volume, group_id, parent_id, email_*,
#     date_sent, author, opensearch_id, file_name, file_extension,
#     record_type, original_path.
#     → these are either reviewer-applied state (must survive re-ingest per
#       Commit 4 scope boundary), outbound-production state (Bates / volume
#       assignments made downstream), or schema fields the ingest path has
#       no business overwriting on re-ingest.
#
# Contract enforcement: tests/test_inbound_db.py's TestUpsertPreservesReviewState
# explicitly asserts field-by-field preservation for 9 reviewer-applied
# fields. Adding a field to the UPDATE clause here without updating that
# test will leave reviewer state vulnerable to silent stomping on re-ingest.
# DO NOT modify the UPDATE clause without walking the preservation test in
# lockstep.
_INBOUND_UPSERT_SQL = """
INSERT INTO documents (
    control_number, group_id, parent_id, file_name, file_extension, custodian, author,
    email_from, email_to, email_cc, email_bcc, email_subject, date_sent,
    original_path, full_path, source_party, production_volume, dynamic_metadata,
    processing_status, record_type, has_text, opensearch_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Imported', ?, ?, ?)
ON CONFLICT(control_number) DO UPDATE SET
    dynamic_metadata=excluded.dynamic_metadata,
    full_path=excluded.full_path,
    has_text=excluded.has_text
"""


def upsert_inbound_documents_batch(case_folder, rows):
    """Batch insert-or-update for inbound documents.

    Each `rows` entry is a 22-tuple matching the INSERT column order:
      (control_number, group_id, parent_id, file_name, file_extension,
       custodian, author, email_from, email_to, email_cc, email_bcc,
       email_subject, date_sent, original_path, full_path, source_party,
       production_volume, dynamic_metadata, record_type, has_text,
       opensearch_id)
    (Note: `processing_status` is hardcoded to 'Imported' in the INSERT,
    NOT passed in — 22 caller-provided values, 23 columns in the VALUES clause.)

    On conflict (same control_number already exists), ONLY THREE fields
    are updated: `dynamic_metadata`, `full_path`, `has_text`. ALL OTHER
    fields on the existing row are preserved — this is load-bearing for
    the beta-2.10 Commit 4 scope boundary (reviewer-applied state on
    inbound docs like tags, privilege_status, production_category,
    custodian, confidentiality_designation, reviewed_by, etc. must survive
    a re-ingest). See tests/test_inbound_db.py TestUpsertPreservesReviewState
    for the explicit preservation-set assertion.

    Does NOT commit per row — commits once at the end after the whole
    batch. Failures propagate (no try/except swallow); caller handles
    rollback semantics via the transaction it owns. Empty rows list is a
    no-op (returns 0).

    Returns:
        int: count of rows processed.
    """
    if not rows:
        return 0
    conn = get_connection(case_folder)
    try:
        conn.executemany(_INBOUND_UPSERT_SQL, rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# ISSUE CODING / CUSTOM CODING FIELDS
# ---------------------------------------------------------------------------

def get_coding_fields(case_folder):
    """Return all custom coding fields, ordered by display_order."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT * FROM coding_fields ORDER BY display_order, id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_coding_field(case_folder, field_name, field_type, pick_list_json, created_by):
    """Create a new custom coding field. Returns the new field id."""
    conn = get_connection(case_folder)
    try:
        cursor = conn.execute(
            "INSERT INTO coding_fields (field_name, field_type, pick_list_json, created_by) "
            "VALUES (?, ?, ?, ?)",
            (field_name, field_type, pick_list_json, created_by)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_coding_field(case_folder, field_id):
    """Delete a coding field and all associated document coding records."""
    conn = get_connection(case_folder)
    try:
        conn.execute("DELETE FROM document_coding WHERE coding_field_id = ?", (field_id,))
        conn.execute("DELETE FROM coding_fields WHERE id = ?", (field_id,))
        conn.commit()
    finally:
        conn.close()
    log_audit(case_folder, "CODING_FIELD_DELETED", module="Review",
              details=f"field_id={field_id}")


def get_document_coding(case_folder, control_number):
    """Return all coding values for a document as a dict {field_id: value}."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT coding_field_id, value FROM document_coding WHERE control_number = ?",
            (control_number,)
        ).fetchall()
        return {r['coding_field_id']: r['value'] for r in rows}
    finally:
        conn.close()


def upsert_document_coding(case_folder, control_number, field_id, value, coded_by):
    """Insert or update a document coding value."""
    conn = get_connection(case_folder)
    try:
        conn.execute("""
            INSERT INTO document_coding (control_number, coding_field_id, value, coded_by, coded_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(control_number, coding_field_id) DO UPDATE SET
                value = excluded.value,
                coded_by = excluded.coded_by,
                coded_at = CURRENT_TIMESTAMP
        """, (control_number, field_id, value, coded_by))
        conn.commit()
    finally:
        conn.close()
    log_audit(case_folder, "CODING_VALUE_CHANGED", username=coded_by,
              control_number=control_number, module="Review",
              details=f"field_id={field_id}, value={value}")


def get_all_coding_for_production(case_folder, control_numbers):
    """
    Batch-fetch coding data for a list of control numbers.
    Returns dict: {control_number: {field_name: value, ...}}
    """
    if not control_numbers:
        return {}
    conn = get_connection(case_folder)
    try:
        placeholders = ','.join(['?'] * len(control_numbers))
        rows = conn.execute(f"""
            SELECT dc.control_number, cf.field_name, dc.value
            FROM document_coding dc
            JOIN coding_fields cf ON dc.coding_field_id = cf.id
            WHERE dc.control_number IN ({placeholders})
        """, control_numbers).fetchall()
        result = {}
        for r in rows:
            cn = r['control_number']
            if cn not in result:
                result[cn] = {}
            result[cn][r['field_name']] = r['value']
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PROCESSING EXCEPTIONS
# ---------------------------------------------------------------------------

def get_processing_exceptions(case_folder):
    """Return all documents with non-success processing outcomes."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT control_number, file_name, custodian, record_type,
                   file_extension, file_size_kb, processing_status,
                   is_encrypted, original_path, date_created
            FROM documents
            WHERE processing_status LIKE '%Error%'
               OR processing_status = 'Partial_Extraction'
               OR processing_status = 'NIST_Excluded'
               OR is_encrypted = 1
            ORDER BY processing_status, custodian, file_name
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# MATTER PROFILE
# ---------------------------------------------------------------------------

def get_matter_profile(case_folder):
    """Return matter profile dict, or empty defaults if not yet configured."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT setting_value FROM case_settings WHERE setting_key='matter_profile'"
        ).fetchone()
        if row:
            return json.loads(row[0])
        return {}
    finally:
        conn.close()


def set_matter_profile(case_folder, profile_dict):
    """Persist matter profile dict to case_settings."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('matter_profile', ?)",
            (json.dumps(profile_dict),)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# REVIEW BATCHING
# ---------------------------------------------------------------------------

def get_user_batches(case_folder, username):
    """Return all batches assigned to a specific user."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT * FROM review_batches WHERE assigned_to = ? ORDER BY id",
            (username,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_batches(case_folder):
    """Return all batches with progress metrics."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT rb.*,
                   (SELECT COUNT(*) FROM batch_documents bd WHERE bd.batch_id = rb.id) as actual_docs,
                   (SELECT COUNT(*) FROM batch_documents bd
                    JOIN documents d ON bd.control_number = d.control_number
                    WHERE bd.batch_id = rb.id
                      AND d.reviewed_by IS NOT NULL
                   ) as reviewed_docs
            FROM review_batches rb
            ORDER BY rb.id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_batch_for_document(case_folder, control_number):
    """Return the batch a document belongs to, or None."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT rb.* FROM review_batches rb
            JOIN batch_documents bd ON rb.id = bd.batch_id
            WHERE bd.control_number = ?
        """, (control_number,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── Exhibit Sets & Exhibits ──────────────────────────────────────────────


def create_exhibit_set(case_folder, set_name, set_type, proceeding_date,
                       case_caption, created_by):
    """Create a new exhibit set. Returns the new set id."""
    conn = get_connection(case_folder)
    try:
        cursor = conn.execute(
            "INSERT INTO exhibit_sets "
            "(case_folder, set_name, set_type, proceeding_date, case_caption, "
            " created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (case_folder, set_name, set_type, proceeding_date, case_caption,
             created_by, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_exhibit_sets(case_folder):
    """Return all exhibit sets for a case as list of dicts."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT * FROM exhibit_sets WHERE case_folder = ? ORDER BY created_at",
            (case_folder,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_exhibit_set(case_folder, set_id, **fields):
    """Update exhibit set fields (set_name, set_type, proceeding_date, case_caption)."""
    allowed = {'set_name', 'set_type', 'proceeding_date', 'case_caption'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [set_id]
    conn = get_connection(case_folder)
    try:
        conn.execute(f"UPDATE exhibit_sets SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def delete_exhibit_set(case_folder, set_id):
    """Delete an exhibit set and all its exhibits (CASCADE)."""
    conn = get_connection(case_folder)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM exhibit_sets WHERE id = ?", (set_id,))
        conn.commit()
    finally:
        conn.close()


def add_exhibit(case_folder, exhibit_set_id, control_number, exhibit_number,
                description, sort_order, added_by):
    """Add a document to an exhibit set. Returns the new exhibit id."""
    conn = get_connection(case_folder)
    try:
        cursor = conn.execute(
            "INSERT INTO exhibits "
            "(exhibit_set_id, control_number, exhibit_number, description, "
            " sort_order, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (exhibit_set_id, control_number, exhibit_number, description,
             sort_order, added_by, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_exhibits(case_folder, exhibit_set_id):
    """
    Return all exhibits in a set, ordered by sort_order.
    JOINs to documents for file_name/custodian, and to document_productions
    for the most recent Bates range and page count.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT e.*,
                   d.file_name, d.custodian, d.record_type,
                   dp.begdoc, dp.enddoc, dp.page_count AS prod_page_count,
                   dp.production_volume
            FROM exhibits e
            JOIN documents d ON e.control_number = d.control_number
            LEFT JOIN document_productions dp ON e.control_number = dp.control_number
                AND dp.produced_at = (
                    SELECT MAX(dp2.produced_at)
                    FROM document_productions dp2
                    WHERE dp2.control_number = e.control_number
                )
            WHERE e.exhibit_set_id = ?
            ORDER BY e.sort_order, e.id
        """, (exhibit_set_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_exhibit(case_folder, exhibit_id, **fields):
    """Update exhibit fields (exhibit_number, description, sort_order)."""
    allowed = {'exhibit_number', 'description', 'sort_order'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [exhibit_id]
    conn = get_connection(case_folder)
    try:
        conn.execute(f"UPDATE exhibits SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def remove_exhibit(case_folder, exhibit_id):
    """Remove an exhibit from its set."""
    conn = get_connection(case_folder)
    try:
        conn.execute("DELETE FROM exhibits WHERE id = ?", (exhibit_id,))
        conn.commit()
    finally:
        conn.close()


def reorder_exhibits(case_folder, exhibit_set_id, ordered_exhibit_ids):
    """Bulk update sort_order for all exhibits in a set."""
    conn = get_connection(case_folder)
    try:
        for idx, eid in enumerate(ordered_exhibit_ids):
            conn.execute(
                "UPDATE exhibits SET sort_order = ? WHERE id = ? AND exhibit_set_id = ?",
                (idx, eid, exhibit_set_id)
            )
        conn.commit()
    finally:
        conn.close()


def get_document_exhibit_sets(case_folder, control_number):
    """
    Return which exhibit sets a document belongs to, with exhibit numbers.
    Used by the Review coding panel to show exhibit badges.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT e.exhibit_number, es.set_name, es.id AS set_id
            FROM exhibits e
            JOIN exhibit_sets es ON e.exhibit_set_id = es.id
            WHERE e.control_number = ?
            ORDER BY es.set_name, e.exhibit_number
        """, (control_number,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_next_sort_order(case_folder, exhibit_set_id):
    """Return the next available sort_order value for an exhibit set."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM exhibits WHERE exhibit_set_id = ?",
            (exhibit_set_id,)
        ).fetchone()
        return row[0]
    finally:
        conn.close()


# ===== STATUS & COUNT QUERIES ================================================


def get_document_status_counts(case_folder):
    """Return comprehensive document status counts in a single table scan.

    Returns dict with keys: total, new, processed, duplicate, duplicate_md5,
    duplicate_content, error, error_or_partial, partial, produced, nist_excluded,
    encrypted, is_encrypted_count, container_scanned, ready.
    """
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN processing_status = 'New' THEN 1 ELSE 0 END) as new,
                SUM(CASE WHEN processing_status IN ('Processed', 'Master')
                    THEN 1 ELSE 0 END) as processed,
                SUM(CASE WHEN processing_status LIKE 'Duplicate%'
                    THEN 1 ELSE 0 END) as duplicate,
                SUM(CASE WHEN processing_status = 'Duplicate (MD5)'
                    THEN 1 ELSE 0 END) as duplicate_md5,
                SUM(CASE WHEN processing_status = 'Duplicate (Content)'
                    THEN 1 ELSE 0 END) as duplicate_content,
                SUM(CASE WHEN processing_status LIKE '%Error%'
                    THEN 1 ELSE 0 END) as error,
                SUM(CASE WHEN processing_status LIKE '%Error%'
                    OR processing_status = 'Partial_Extraction'
                    THEN 1 ELSE 0 END) as error_or_partial,
                SUM(CASE WHEN processing_status = 'Partial_Extraction'
                    THEN 1 ELSE 0 END) as partial,
                SUM(CASE WHEN begdoc IS NOT NULL AND begdoc != ''
                    THEN 1 ELSE 0 END) as produced,
                SUM(CASE WHEN processing_status = 'NIST_Excluded'
                    THEN 1 ELSE 0 END) as nist_excluded,
                SUM(CASE WHEN processing_status = 'Encrypted'
                    THEN 1 ELSE 0 END) as encrypted,
                SUM(CASE WHEN is_encrypted = 1
                    THEN 1 ELSE 0 END) as is_encrypted_count,
                SUM(CASE WHEN processing_status = 'Container_Scanned'
                    THEN 1 ELSE 0 END) as container_scanned,
                SUM(CASE WHEN processing_status = 'Ready_For_Processing'
                    THEN 1 ELSE 0 END) as ready
            FROM documents
        """).fetchone()
        return {k: (v if v is not None else 0) for k, v in dict(row).items()}
    finally:
        conn.close()


def get_review_tag_counts(case_folder):
    """Return review tag counts for dashboard display.

    Returns dict with keys: all_tagged, responsive, not_responsive, needs_review,
    suppressed, privileged, threading_done, nd_done.
    """
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT
                SUM(CASE WHEN tags IS NOT NULL AND tags != ''
                    AND processing_status IN ('Processed', 'Master')
                    THEN 1 ELSE 0 END) as all_tagged,
                SUM(CASE WHEN tags LIKE '%Responsive%'
                    THEN 1 ELSE 0 END) as responsive,
                SUM(CASE WHEN tags LIKE '%Not Responsive%'
                    THEN 1 ELSE 0 END) as not_responsive,
                SUM(CASE WHEN tags LIKE '%Needs Review%'
                    THEN 1 ELSE 0 END) as needs_review,
                SUM(CASE WHEN tags LIKE '%Suppressed%'
                    THEN 1 ELSE 0 END) as suppressed,
                SUM(CASE WHEN tags LIKE '%Thread-Suppressed%'
                    OR tags LIKE '%Inclusive%'
                    THEN 1 ELSE 0 END) as threading_tagged,
                SUM(CASE WHEN tags LIKE '%NearDupe-Suppressed%'
                    OR tags LIKE '%NearDupe-Principal%'
                    THEN 1 ELSE 0 END) as nd_tagged
            FROM documents
        """).fetchone()
        result = {k: (v if v is not None else 0) for k, v in dict(row).items()}

        # Privilege count — dynamic based on tag category members
        priv_members = get_privilege_tag_members(case_folder)
        if priv_members:
            priv_filter = ' OR '.join(["tags LIKE ?" for _ in priv_members])
            priv_params = [f'%{m}%' for m in priv_members]
            priv_row = conn.execute(
                f"SELECT COUNT(*) FROM documents WHERE {priv_filter}", priv_params
            ).fetchone()
            result['privileged'] = priv_row[0]
        else:
            priv_row = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE tags LIKE '%Privileged%'"
            ).fetchone()
            result['privileged'] = priv_row[0]

        result['threading_done'] = (result.get('threading_tagged') or 0) > 0
        result['nd_done'] = (result.get('nd_tagged') or 0) > 0

        return result
    finally:
        conn.close()


def get_processing_queue_stats(case_folder):
    """Return processing queue statistics for the Processor page.

    Returns dict with keys: queue_count, new_count, resumed_count, container_count.
    """
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT
                SUM(CASE WHEN processing_status IN ('New', 'Container_Scanned',
                    'Ready_For_Processing') THEN 1 ELSE 0 END) as queue_count,
                SUM(CASE WHEN processing_status = 'New'
                    THEN 1 ELSE 0 END) as new_count,
                SUM(CASE WHEN processing_status IN ('Container_Scanned',
                    'Ready_For_Processing') THEN 1 ELSE 0 END) as resumed_count,
                SUM(CASE WHEN file_extension IN ('.msg', '.eml', '.zip', '.pst')
                    AND processing_status = 'New'
                    THEN 1 ELSE 0 END) as container_count
            FROM documents
        """).fetchone()
        return {k: (v if v is not None else 0) for k, v in dict(row).items()}
    finally:
        conn.close()


def get_file_type_breakdown(case_folder):
    """Return file extension breakdown for processing queue (top 15).

    Returns list[dict] with keys: file_extension, cnt.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT file_extension, COUNT(*) as cnt
            FROM documents
            WHERE processing_status IN ('New', 'Container_Scanned', 'Ready_For_Processing')
              AND file_extension IS NOT NULL
            GROUP BY file_extension
            ORDER BY cnt DESC
            LIMIT 15
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_data_reduction_stats(case_folder):
    """Return data reduction statistics for the Analytics dedup report.

    Returns dict with keys: total_ingested, exact_dupes, content_dupes, processed,
    error_docs, nd_suppressed, nd_principals, thread_suppressed, thread_inclusive,
    net_reviewable.
    """
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as total_ingested,
                SUM(CASE WHEN processing_status = 'Duplicate (MD5)'
                    THEN 1 ELSE 0 END) as exact_dupes,
                SUM(CASE WHEN processing_status = 'Duplicate (Content)'
                    THEN 1 ELSE 0 END) as content_dupes,
                SUM(CASE WHEN processing_status IN ('Processed', 'Master')
                    THEN 1 ELSE 0 END) as processed,
                SUM(CASE WHEN processing_status LIKE '%Error%'
                    THEN 1 ELSE 0 END) as error_docs,
                SUM(CASE WHEN tags LIKE '%NearDupe-Suppressed%'
                    THEN 1 ELSE 0 END) as nd_suppressed,
                SUM(CASE WHEN tags LIKE '%NearDupe-Principal%'
                    THEN 1 ELSE 0 END) as nd_principals,
                SUM(CASE WHEN tags LIKE '%Thread-Suppressed%'
                    THEN 1 ELSE 0 END) as thread_suppressed,
                SUM(CASE WHEN tags LIKE '%Inclusive%'
                    THEN 1 ELSE 0 END) as thread_inclusive
            FROM documents
            WHERE processing_status NOT IN ('Container_Scanned', 'Split_Source')
        """).fetchone()
        result = {k: (v if v is not None else 0) for k, v in dict(row).items()}

        nr_row = conn.execute("""
            SELECT COUNT(*) FROM documents
            WHERE processing_status IN ('Processed', 'Master')
              AND (tags NOT LIKE '%NearDupe-Suppressed%' OR tags IS NULL)
              AND (tags NOT LIKE '%Thread-Suppressed%' OR tags IS NULL)
        """).fetchone()
        result['net_reviewable'] = nr_row[0]

        # nd_pending (S-1b C8c): suppressible near-dupe cluster members not yet
        # reviewed — un-decided, non-principal, family-preserved-exempt. Mirrors
        # the §11.6 approval-gate denominator. nd_suppressed (above) continues to
        # count currently-tagged docs = "reviewer-confirmed-suppressed" post-C8b.
        nd_pending = conn.execute("""
            SELECT COUNT(*) FROM near_dupe_cluster_members
            WHERE decision = 'undecided'
              AND is_principal = 0
              AND family_preserved = 0
        """).fetchone()[0] or 0
        result['nd_pending'] = nd_pending

        return result
    finally:
        conn.close()


def get_sync_status_counts(case_folder):
    """Return sync status counts for the Sync page Filevine tab.

    Returns dict with keys: total_valid, synced, pending, error.
    """
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT
                SUM(CASE WHEN processing_status NOT LIKE 'Duplicate%'
                    AND processing_status != 'Error'
                    THEN 1 ELSE 0 END) as total_valid,
                SUM(CASE WHEN sync_status = 'Synced'
                    THEN 1 ELSE 0 END) as synced,
                SUM(CASE WHEN sync_status = 'Pending'
                    AND processing_status NOT LIKE 'Duplicate%'
                    AND processing_status != 'Error'
                    THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN sync_status LIKE 'Error%'
                    THEN 1 ELSE 0 END) as error
            FROM documents
        """).fetchone()
        return {k: (v if v is not None else 0) for k, v in dict(row).items()}
    finally:
        conn.close()


def get_byos_status_counts(case_folder):
    """Return BYOS (Bring Your Own Storage) push/pull status counts.

    Returns dict with keys: total_pushable, already_pushed, pulled, redactions.
    """
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT
                SUM(CASE WHEN processing_status IN ('Processed', 'Master')
                    THEN 1 ELSE 0 END) as total_pushable,
                SUM(CASE WHEN byos_pushed_at IS NOT NULL AND byos_pushed_at != ''
                    THEN 1 ELSE 0 END) as already_pushed,
                SUM(CASE WHEN byos_pulled_at IS NOT NULL AND byos_pulled_at != ''
                    THEN 1 ELSE 0 END) as pulled,
                SUM(CASE WHEN byos_pulled_at IS NOT NULL
                    AND redaction_status = 'Has_Redactions'
                    THEN 1 ELSE 0 END) as redactions
            FROM documents
        """).fetchone()
        return {k: (v if v is not None else 0) for k, v in dict(row).items()}
    finally:
        conn.close()


# ===== SAVED SEARCHES ========================================================


def log_recent_search(case_folder, username, query):
    """Auto-log a recent search. Rotates to keep only the 10 most recent per user."""
    conn = get_connection(case_folder)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM saved_searches WHERE username=? AND is_recent=1",
            (username,)
        ).fetchone()[0]
        if count >= 10:
            conn.execute(
                "DELETE FROM saved_searches WHERE id IN ("
                "  SELECT id FROM saved_searches WHERE username=? AND is_recent=1"
                "  ORDER BY created_at ASC LIMIT ?)",
                (username, count - 9)
            )
        conn.execute(
            "INSERT INTO saved_searches (username, query, col_filters_json, is_recent)"
            " VALUES (?, ?, ?, 1)",
            (username, query, '{}')
        )
        conn.commit()
    finally:
        conn.close()


def get_named_searches(case_folder, username):
    """Return saved (non-recent) searches visible to the user (own + global)."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT id, search_name, query, username, is_global FROM saved_searches"
            " WHERE (username=? OR is_global=1) AND is_recent=0 ORDER BY created_at DESC",
            (username,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recent_searches(case_folder, username):
    """Return the 10 most recent searches for a user."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT id, query FROM saved_searches"
            " WHERE username=? AND is_recent=1 ORDER BY created_at DESC LIMIT 10",
            (username,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_saved_search(case_folder, search_id, username):
    """Delete a saved search owned by the given user."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "DELETE FROM saved_searches WHERE id=? AND username=?",
            (search_id, username)
        )
        conn.commit()
    finally:
        conn.close()


def toggle_search_global(case_folder, search_id, username, is_global):
    """Toggle the is_global flag on a saved search owned by the given user."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "UPDATE saved_searches SET is_global=? WHERE id=? AND username=?",
            (1 if is_global else 0, search_id, username)
        )
        conn.commit()
    finally:
        conn.close()


def save_named_search(case_folder, username, search_name, query,
                      col_filters_json='{}', is_global=False):
    """Insert a new named (non-recent) saved search."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "INSERT INTO saved_searches"
            " (username, search_name, query, col_filters_json, is_recent, is_global)"
            " VALUES (?, ?, ?, ?, 0, ?)",
            (username, search_name, query, col_filters_json, 1 if is_global else 0)
        )
        conn.commit()
    finally:
        conn.close()


def clear_recent_searches(case_folder, username):
    """Delete all recent searches for a user."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "DELETE FROM saved_searches WHERE username=? AND is_recent=1",
            (username,)
        )
        conn.commit()
    finally:
        conn.close()


# ===== BATES LOOKUP ===========================================================


def get_all_bates_ranges(case_folder):
    """Return all documents with Bates numbers for range-based lookup.

    Returns list[dict] with keys: control_number, begdoc, enddoc,
    custodian, date_sent, production_volume, source_party.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT control_number, begdoc, enddoc, custodian, date_sent,"
            "       production_volume, source_party"
            " FROM documents WHERE begdoc IS NOT NULL AND begdoc != ''"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


_BATES_TOKEN_RE = re.compile(r'^(.*?)(\d+)\s*$')

def parse_bates_token(s):
    """Parse a single Bates string to (prefix, number) or (None, None).

    Handles both hyphenated (``ABC-000700``) and concatenated (``ABC000700``)
    formats. Trailing hyphens and whitespace are stripped from the prefix and
    the prefix is uppercased so compare-by-prefix is consistent across input
    styles. Returns (None, None) for empty/null input or when the string
    contains no trailing digits — callers must skip unparseable tokens rather
    than treat two (None, None) tuples as equal.

    Two places in the Review page depend on this parser agreeing with itself:
    the Bates Lookup sidebar and the Bulk Bates popover batch search. A
    pinned-value regression test lives at tests/test_bates.py::TestParseBatesToken.
    """
    if not s:
        return None, None
    m = _BATES_TOKEN_RE.match(str(s).strip())
    if not m:
        return None, None
    prefix = m.group(1).upper().rstrip('-').rstrip()
    return prefix, int(m.group(2))


# ===== DOCUMENT ACCESS ========================================================


def get_document(case_folder, control_number):
    """Return full document row as dict, or None if not found."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT * FROM documents WHERE control_number=?",
            (control_number,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_document_parent(case_folder, parent_id):
    """Return parent document's control_number, or None."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT control_number FROM documents WHERE control_number=?",
            (parent_id,)
        ).fetchone()
        return row['control_number'] if row else None
    finally:
        conn.close()


def get_document_children(case_folder, parent_cn):
    """Return list of child document control_numbers for a parent."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT control_number FROM documents WHERE parent_id=?",
            (parent_cn,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ===== DOCUMENT SPLIT =========================================================


def split_document(case_folder, source_cn, splits, username):
    """
    Split a multi-page PDF document into multiple independent documents.

    Args:
        case_folder: Path to the active case folder
        source_cn: Control number of the source document to split
        splits: List of dicts, each with:
            - page_start (int): 0-based start page index (inclusive)
            - page_end (int): 0-based end page index (inclusive)
            - file_name (str): Display name for the new document
        username: Username performing the split

    Returns:
        dict with:
            - new_documents: list of dicts with {control_number, file_name, page_start, page_end, full_path}
            - source_cn: the source document's control number
            - error: None on success, error string on failure
    """
    import fitz  # PyMuPDF — imported locally to avoid module-level dependency

    conn = get_connection(case_folder)
    source_doc = None
    created_files = []

    try:
        # ── 1. Validate source document ──────────────────────────────────
        source_row = conn.execute(
            "SELECT * FROM documents WHERE control_number = ?", (source_cn,)
        ).fetchone()

        if not source_row:
            raise ValueError(f"Source document {source_cn} not found")
        if source_row['processing_status'] == 'Split_Source':
            raise ValueError(f"{source_cn} has already been split")
        if source_row['begdoc'] and str(source_row['begdoc']).strip():
            raise ValueError(f"{source_cn} has already been produced (Bates assigned) — cannot split")

        source_path = source_row['full_path']
        if not source_path or not source_path.lower().endswith('.pdf'):
            raise ValueError(f"{source_cn} is not a PDF — only PDF splitting is supported")
        if not os.path.exists(source_path):
            raise ValueError(f"Source PDF not found on disk: {source_path}")

        # ── 2. Validate splits ───────────────────────────────────────────
        source_doc = fitz.open(source_path)
        page_count = len(source_doc)

        if len(splits) < 2:
            raise ValueError("At least 2 split ranges are required")

        for i, s in enumerate(splits):
            if s['page_start'] < 0 or s['page_end'] >= page_count:
                raise ValueError(f"Range {i+1} ({s['page_start']}-{s['page_end']}) is outside document bounds (0-{page_count-1})")
            if s['page_start'] > s['page_end']:
                raise ValueError(f"Range {i+1}: start page ({s['page_start']}) > end page ({s['page_end']})")

        # Check for overlaps
        sorted_splits = sorted(splits, key=lambda s: s['page_start'])
        for i in range(1, len(sorted_splits)):
            if sorted_splits[i]['page_start'] <= sorted_splits[i-1]['page_end']:
                raise ValueError(
                    f"Overlapping ranges: range ending at page {sorted_splits[i-1]['page_end']} "
                    f"overlaps with range starting at page {sorted_splits[i]['page_start']}"
                )

        # ── 3. Create Split/ staging directory ───────────────────────────
        split_dir = os.path.join(case_folder, 'Split')
        os.makedirs(split_dir, exist_ok=True)

        # ── 4. Create new documents ──────────────────────────────────────
        new_documents = []
        cur = conn.cursor()

        for split in splits:
            # Extract pages into new PDF
            new_pdf = fitz.open()
            try:
                new_pdf.insert_pdf(source_doc, from_page=split['page_start'], to_page=split['page_end'])

                # Insert row with placeholder values
                file_name = split['file_name']
                if not file_name.lower().endswith('.pdf'):
                    file_name += '.pdf'

                cur.execute("""
                    INSERT INTO documents (
                        file_name, file_extension, full_path, original_path,
                        file_size_kb, processing_status, custodian, volume,
                        record_type, split_source_cn, md5_hash,
                        source_collection, source_subcollection,
                        -- Legal metadata (must inherit from parent)
                        confidentiality_designation, privilege_status,
                        clawback_status, clawback_date,
                        tags, source_party,
                        -- Dates & email metadata (needed for privilege log)
                        date_sent, date_received, date_created, date_modified,
                        email_from, email_to, email_cc, email_bcc, email_subject,
                        author, title, importance, sensitivity, conversation_topic
                    ) VALUES (
                        ?, ?, ?, ?, ?, 'New', ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?
                    )
                """, (
                    file_name, '.pdf', '',  # full_path updated below
                    f"Split from {source_cn} (pages {split['page_start']+1}-{split['page_end']+1})",
                    0,  # file_size_kb placeholder
                    source_row['custodian'], source_row['volume'],
                    'Document', source_cn, '',  # md5_hash placeholder
                    source_row['source_collection'], source_row['source_subcollection'],
                    # Legal metadata
                    source_row['confidentiality_designation'], source_row['privilege_status'],
                    source_row['clawback_status'], source_row['clawback_date'],
                    source_row['tags'], source_row['source_party'],
                    # Dates & email metadata
                    source_row['date_sent'], source_row['date_received'],
                    source_row['date_created'], source_row['date_modified'],
                    source_row['email_from'], source_row['email_to'],
                    source_row['email_cc'], source_row['email_bcc'], source_row['email_subject'],
                    source_row['author'], source_row['title'],
                    source_row['importance'], source_row['sensitivity'],
                    source_row['conversation_topic'],
                ))

                new_id = cur.lastrowid
                new_cn = f"DOC-{new_id:06d}"
                split_pdf_path = os.path.join(split_dir, f"{new_cn}.pdf")

                # Save the PDF
                new_pdf.save(split_pdf_path)
                created_files.append(split_pdf_path)

                # Compute real file_size_kb and md5_hash
                file_size_kb = round(os.path.getsize(split_pdf_path) / 1024, 2)
                with open(split_pdf_path, 'rb') as f:
                    md5 = hashlib.md5(f.read()).hexdigest()

                # Update row with real values
                cur.execute("""
                    UPDATE documents SET
                        control_number = ?, group_id = ?, full_path = ?,
                        file_size_kb = ?, md5_hash = ?
                    WHERE id = ?
                """, (new_cn, new_cn, split_pdf_path, file_size_kb, md5, new_id))

                # ── 4e. Migrate redaction marks ──────────────────────────
                existing_marks = conn.execute(
                    "SELECT page_number, marks_json, created_by FROM redaction_marks "
                    "WHERE control_number = ? AND page_number >= ? AND page_number <= ?",
                    (source_cn, split['page_start'], split['page_end'])
                ).fetchall()

                for mark_row in existing_marks:
                    new_page_num = mark_row['page_number'] - split['page_start']
                    cur.execute(
                        "INSERT OR REPLACE INTO redaction_marks "
                        "(control_number, page_number, marks_json, created_by) VALUES (?, ?, ?, ?)",
                        (new_cn, new_page_num, mark_row['marks_json'],
                         mark_row['created_by'] or username)
                    )

                # Set redaction_status if marks were migrated
                if existing_marks:
                    cur.execute(
                        "UPDATE documents SET redaction_status = 'Has_Redactions' "
                        "WHERE control_number = ?", (new_cn,)
                    )

                new_documents.append({
                    'control_number': new_cn,
                    'file_name': file_name,
                    'page_start': split['page_start'],
                    'page_end': split['page_end'],
                    'full_path': split_pdf_path,
                })

            finally:
                new_pdf.close()

        # ── 5. Mark source as Split_Source ────────────────────────────────
        cur.execute(
            "UPDATE documents SET processing_status = 'Split_Source' "
            "WHERE control_number = ?", (source_cn,)
        )

        # ── 6. Delete source redaction marks (migrated to children) ──────
        cur.execute(
            "DELETE FROM redaction_marks WHERE control_number = ?",
            (source_cn,)
        )

        # ── 7. Commit and audit log ──────────────────────────────────────
        conn.commit()

        audit_rows = []
        for doc_info in new_documents:
            audit_rows.append({
                "action": "DOCUMENT_SPLIT_CHILD",
                "username": username,
                "control_number": doc_info['control_number'],
                "module": "Review",
                "details": json.dumps({
                    "source_cn": source_cn,
                    "page_start": doc_info['page_start'],
                    "page_end": doc_info['page_end'],
                    "file_name": doc_info['file_name']
                }),
                "old_value": None,
                "new_value": "New"
            })
        audit_rows.append({
            "action": "DOCUMENT_SPLIT_SOURCE",
            "username": username,
            "control_number": source_cn,
            "module": "Review",
            "details": json.dumps({
                "child_cns": [d['control_number'] for d in new_documents],
                "child_count": len(new_documents)
            }),
            "old_value": source_row['processing_status'],
            "new_value": "Split_Source"
        })
        log_audit_batch(case_folder, audit_rows)

        return {
            "new_documents": new_documents,
            "source_cn": source_cn,
            "error": None,
        }

    except Exception as e:
        conn.rollback()
        # Clean up any PDFs already written
        for f in created_files:
            try:
                os.remove(f)
            except OSError:
                pass
        logger.error("split_document failed for %s: %s", source_cn, e)
        return {
            "new_documents": [],
            "source_cn": source_cn,
            "error": str(e),
        }

    finally:
        if source_doc:
            source_doc.close()
        conn.close()


def trim_document(case_folder, source_cn, pages_to_remove, username, new_file_name=None):
    """
    Remove specified pages from a document, creating a single trimmed child.
    Original document is preserved and hidden (Split_Source).

    Args:
        case_folder: Path to the active case folder
        source_cn: Control number of the source document
        pages_to_remove: List of 0-based page indices to remove
        username: Username performing the trim
        new_file_name: Optional display name for the trimmed doc.

    Returns:
        dict with new_document info, pages_removed, source_cn, error
    """
    import fitz

    conn = get_connection(case_folder)
    source_doc = None
    created_files = []

    try:
        # ── 1. Validate source document ──────────────────────────────────
        source_row = conn.execute(
            "SELECT * FROM documents WHERE control_number = ?", (source_cn,)
        ).fetchone()

        if not source_row:
            raise ValueError(f"Source document {source_cn} not found")
        if source_row['processing_status'] == 'Split_Source':
            raise ValueError(f"{source_cn} has already been split/trimmed")
        if source_row['begdoc'] and str(source_row['begdoc']).strip():
            raise ValueError(f"{source_cn} has already been produced — cannot trim")

        source_path = source_row['full_path']
        if not source_path or not source_path.lower().endswith('.pdf'):
            raise ValueError(f"{source_cn} is not a PDF — only PDF trimming is supported")
        if not os.path.exists(source_path):
            raise ValueError(f"Source PDF not found on disk: {source_path}")

        # ── 2. Validate pages_to_remove ──────────────────────────────────
        source_doc = fitz.open(source_path)
        source_page_count = len(source_doc)

        remove_set = set(pages_to_remove)
        if not remove_set:
            raise ValueError("No pages specified for removal")
        if len(remove_set) >= source_page_count:
            raise ValueError("Cannot remove all pages — at least one page must survive")

        invalid = [p for p in remove_set if p < 0 or p >= source_page_count]
        if invalid:
            raise ValueError(f"Page indices out of range: {invalid}")

        # ── 3. Compute surviving pages ───────────────────────────────────
        surviving_pages = sorted(set(range(source_page_count)) - remove_set)

        # ── 4. Create trimmed PDF ────────────────────────────────────────
        new_pdf = fitz.open()
        try:
            for page_num in surviving_pages:
                new_pdf.insert_pdf(source_doc, from_page=page_num, to_page=page_num)

            # ── 5. Insert new document row ───────────────────────────────
            source_file_name = source_row['file_name'] or source_cn
            if new_file_name is None:
                base = os.path.splitext(source_file_name)[0]
                new_file_name = f"{base} (trimmed).pdf"
            if not new_file_name.lower().endswith('.pdf'):
                new_file_name += '.pdf'

            cur = conn.cursor()
            cur.execute("""
                INSERT INTO documents (
                    file_name, file_extension, full_path, original_path,
                    file_size_kb, processing_status, custodian, volume,
                    record_type, split_source_cn, md5_hash,
                    source_collection, source_subcollection,
                    -- Legal metadata (must inherit from parent)
                    confidentiality_designation, privilege_status,
                    clawback_status, clawback_date,
                    tags, source_party,
                    -- Dates & email metadata (needed for privilege log)
                    date_sent, date_received, date_created, date_modified,
                    email_from, email_to, email_cc, email_bcc, email_subject,
                    author, title, importance, sensitivity, conversation_topic
                ) VALUES (
                    ?, ?, ?, ?, ?, 'New', ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
            """, (
                new_file_name, '.pdf', '',
                f"Trimmed from {source_cn} — removed {len(remove_set)} pages",
                0,
                source_row['custodian'], source_row['volume'],
                'Document', source_cn, '',
                source_row['source_collection'], source_row['source_subcollection'],
                # Legal metadata
                source_row['confidentiality_designation'], source_row['privilege_status'],
                source_row['clawback_status'], source_row['clawback_date'],
                source_row['tags'], source_row['source_party'],
                # Dates & email metadata
                source_row['date_sent'], source_row['date_received'],
                source_row['date_created'], source_row['date_modified'],
                source_row['email_from'], source_row['email_to'],
                source_row['email_cc'], source_row['email_bcc'], source_row['email_subject'],
                source_row['author'], source_row['title'],
                source_row['importance'], source_row['sensitivity'],
                source_row['conversation_topic'],
            ))

            new_id = cur.lastrowid
            new_cn = f"DOC-{new_id:06d}"

            # ── 6. Save PDF, update row ──────────────────────────────────
            split_dir = os.path.join(case_folder, 'Split')
            os.makedirs(split_dir, exist_ok=True)
            split_pdf_path = os.path.join(split_dir, f"{new_cn}.pdf")
            new_pdf.save(split_pdf_path)
            created_files.append(split_pdf_path)

            file_size_kb = round(os.path.getsize(split_pdf_path) / 1024, 2)
            with open(split_pdf_path, 'rb') as f:
                md5 = hashlib.md5(f.read()).hexdigest()

            cur.execute("""
                UPDATE documents SET
                    control_number = ?, group_id = ?, full_path = ?,
                    file_size_kb = ?, md5_hash = ?
                WHERE id = ?
            """, (new_cn, new_cn, split_pdf_path, file_size_kb, md5, new_id))

        finally:
            new_pdf.close()

        # ── 7. Migrate redaction marks with page renumbering ─────────────
        page_remap = {}
        new_idx = 0
        for old_idx in range(source_page_count):
            if old_idx not in remove_set:
                page_remap[old_idx] = new_idx
                new_idx += 1

        all_marks = conn.execute(
            "SELECT page_number, marks_json, created_by FROM redaction_marks "
            "WHERE control_number = ?", (source_cn,)
        ).fetchall()

        has_marks = False
        for mark_row in all_marks:
            old_page = mark_row['page_number']
            if old_page in page_remap:
                new_page = page_remap[old_page]
                cur.execute(
                    "INSERT OR REPLACE INTO redaction_marks "
                    "(control_number, page_number, marks_json, created_by) VALUES (?, ?, ?, ?)",
                    (new_cn, new_page, mark_row['marks_json'],
                     mark_row['created_by'] or username)
                )
                has_marks = True

        if has_marks:
            cur.execute(
                "UPDATE documents SET redaction_status = 'Has_Redactions' "
                "WHERE control_number = ?", (new_cn,)
            )

        # ── 8. Mark source as Split_Source ────────────────────────────────
        cur.execute(
            "UPDATE documents SET processing_status = 'Split_Source' "
            "WHERE control_number = ?", (source_cn,)
        )
        cur.execute(
            "DELETE FROM redaction_marks WHERE control_number = ?",
            (source_cn,)
        )

        conn.commit()

        # ── 9. Audit log ─────────────────────────────────────────────────
        audit_rows = [
            {
                "action": "DOCUMENT_TRIM_CHILD",
                "username": username,
                "control_number": new_cn,
                "module": "Review",
                "details": json.dumps({
                    "source_cn": source_cn,
                    "pages_removed": sorted(remove_set),
                    "pages_kept": surviving_pages,
                    "original_page_count": source_page_count,
                    "new_page_count": len(surviving_pages),
                }),
                "old_value": None,
                "new_value": "New",
            },
            {
                "action": "DOCUMENT_TRIM_SOURCE",
                "username": username,
                "control_number": source_cn,
                "module": "Review",
                "details": json.dumps({
                    "child_cn": new_cn,
                    "pages_removed": sorted(remove_set),
                }),
                "old_value": source_row['processing_status'],
                "new_value": "Split_Source",
            },
        ]
        log_audit_batch(case_folder, audit_rows)

        return {
            "new_document": {
                "control_number": new_cn,
                "file_name": new_file_name,
                "page_count": len(surviving_pages),
                "full_path": split_pdf_path,
            },
            "pages_removed": sorted(remove_set),
            "source_cn": source_cn,
            "error": None,
        }

    except Exception as e:
        conn.rollback()
        for f in created_files:
            try:
                os.remove(f)
            except OSError:
                pass
        logger.error("trim_document failed for %s: %s", source_cn, e)
        return {
            "new_document": None,
            "pages_removed": [],
            "source_cn": source_cn,
            "error": str(e),
        }

    finally:
        if source_doc:
            source_doc.close()
        conn.close()


# ===== DOCUMENT TAGS ==========================================================


def get_document_tags(case_folder, control_number):
    """Return the tags string for a document, or empty string."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT tags FROM documents WHERE control_number=?",
            (control_number,)
        ).fetchone()
        return (row['tags'] or '') if row else ''
    finally:
        conn.close()


def update_document_tags(case_folder, control_number, new_tags):
    """Update tags for a single document. Caller handles normalization."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "UPDATE documents SET tags=? WHERE control_number=?",
            (new_tags, control_number)
        )
        conn.commit()
    finally:
        conn.close()


def set_redaction_status(case_folder, control_number, status):
    """Set redaction_status for a document. Pass None to clear."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "UPDATE documents SET redaction_status=? WHERE control_number=?",
            (status, control_number)
        )
        conn.commit()
    finally:
        conn.close()


def get_redaction_status(case_folder, control_number):
    """Return current redaction_status for a document, or None."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT redaction_status FROM documents WHERE control_number=?",
            (control_number,)
        ).fetchone()
        return row['redaction_status'] if row else None
    finally:
        conn.close()


def mark_document_reviewed(case_folder, control_number, username):
    """Stamp reviewed_by and reviewed_at on a document."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "UPDATE documents SET reviewed_by=?, reviewed_at=? WHERE control_number=?",
            (username, datetime.now().isoformat(), control_number)
        )
        conn.commit()
    finally:
        conn.close()


# ===== REVIEW BATCH MANAGEMENT ================================================


def get_unbatched_document_count(case_folder):
    """Return count of reviewable documents not yet assigned to a batch."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM documents
            WHERE processing_status IN ('Processed', 'Master')
              AND (tags NOT LIKE '%Suppressed%' OR tags IS NULL)
              AND (tags NOT LIKE '%Junk%' OR tags IS NULL)
              AND processing_status NOT LIKE 'Duplicate%'
              AND control_number NOT IN (SELECT control_number FROM batch_documents)
        """).fetchone()
        return row[0]
    finally:
        conn.close()


def get_unbatched_documents(case_folder):
    """Return unbatched reviewable documents for batch creation.

    Returns list[dict] with keys: control_number, group_id, pages.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT control_number, group_id, COALESCE(page_count, 1) as pages
            FROM documents
            WHERE processing_status IN ('Processed', 'Master')
              AND (tags NOT LIKE '%Suppressed%' OR tags IS NULL)
              AND (tags NOT LIKE '%Junk%' OR tags IS NULL)
              AND processing_status NOT LIKE 'Duplicate%'
              AND control_number NOT IN (SELECT control_number FROM batch_documents)
            ORDER BY group_id, control_number
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_review_batch(case_folder, batch_name, created_by, doc_count, page_count):
    """Create a review batch and return its ID."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "INSERT INTO review_batches (batch_name, created_by, doc_count, page_count)"
            " VALUES (?, ?, ?, ?)",
            (batch_name, created_by, doc_count, page_count)
        )
        batch_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        return batch_id
    finally:
        conn.close()


def assign_documents_to_batch(case_folder, batch_id, control_numbers):
    """Bulk-assign documents to a batch."""
    conn = get_connection(case_folder)
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO batch_documents (batch_id, control_number) VALUES (?, ?)",
            [(batch_id, cn) for cn in control_numbers]
        )
        conn.commit()
    finally:
        conn.close()


def recalculate_batch_counts(case_folder):
    """Recalculate cached doc_count and page_count for all batches."""
    conn = get_connection(case_folder)
    try:
        conn.execute("""
            UPDATE review_batches SET
                doc_count = (SELECT COUNT(*) FROM batch_documents
                             WHERE batch_id = review_batches.id),
                page_count = (SELECT COALESCE(SUM(COALESCE(d.page_count, 1)), 0)
                              FROM batch_documents bd
                              JOIN documents d ON bd.control_number = d.control_number
                              WHERE bd.batch_id = review_batches.id)
        """)
        conn.commit()
    finally:
        conn.close()


def update_batch_assignment(case_folder, batch_id, assigned_to):
    """Update the assigned reviewer for a batch."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "UPDATE review_batches SET assigned_to=? WHERE id=?",
            (assigned_to, batch_id)
        )
        conn.commit()
    finally:
        conn.close()


def reassign_batch_documents(case_folder, control_numbers, new_batch_id):
    """Move documents to a different batch."""
    if not control_numbers:
        return
    conn = get_connection(case_folder)
    try:
        placeholders = ','.join(['?'] * len(control_numbers))
        conn.execute(
            f"DELETE FROM batch_documents WHERE control_number IN ({placeholders})",
            control_numbers
        )
        conn.executemany(
            "INSERT OR IGNORE INTO batch_documents (batch_id, control_number) VALUES (?, ?)",
            [(new_batch_id, cn) for cn in control_numbers]
        )
        conn.commit()
    finally:
        conn.close()


def delete_all_batches(case_folder):
    """Delete all review batches and their document assignments."""
    conn = get_connection(case_folder)
    try:
        conn.execute("DELETE FROM batch_documents")
        conn.execute("DELETE FROM review_batches")
        conn.commit()
    finally:
        conn.close()


# ===== ANALYTICS QUERIES =====================================================


def get_exact_dupe_clusters(case_folder):
    """Return exact (MD5) duplicate clusters for analytics display.

    Returns list[dict] with keys: md5_hash, copies, representative_cn, all_cns,
    file_name, custodians.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT md5_hash,
                   COUNT(*) as copies,
                   MIN(control_number) as representative_cn,
                   GROUP_CONCAT(control_number, ', ') as all_cns,
                   MIN(file_name) as file_name,
                   MIN(custodian) as custodians
            FROM documents
            WHERE md5_hash IS NOT NULL AND md5_hash != ''
            GROUP BY md5_hash
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 200
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_near_dupe_cluster_detail(case_folder):
    """Return near-duplicate cluster details for the Dedup Report.

    Reads from the C8a-introduced near_dupe_clusters + near_dupe_cluster_members
    tables (NOT the legacy family-group_id grouping, which never reconstructed
    similarity clusters — see spec §5.3). One row per persisted cluster.

    Returns list[dict] with keys:
        cluster_id        — surrogate cluster ID (INTEGER)
        run_date          — ISO timestamp when the cluster was minted
        principal_cn      — control number of the cluster's principal
        principal_name    — file_name of the principal (joined from documents)
        member_count      — total members in the cluster (incl. principal)
        sim_min, sim_max  — similarity range across non-principal members
        review_status     — 'pending' | 'approved'
        reviewed_by       — username who attested (NULL until approved)
        reviewed_at       — ISO timestamp of attestation (NULL until approved)
        confirmed_count   — non-principal members with decision='same'
                            (confirmed-suppressed by reviewer; counts BOTH family
                            values — family_retained_count is the fp=1 subset)
        pending_count     — non-principal members with decision='undecided'
                            AND family_preserved=0 (suppressible, not yet decided)
        family_retained_count — non-principal members with decision='same' AND
                            family_preserved=1 (confirmed dupes kept for family
                            integrity; never tagged NearDupe-Suppressed). The
                            per-cluster suppressed figure is confirmed_count
                            minus family_retained_count.
        distinct_count    — non-principal members with decision='distinct'
                            (reviewer-determined distinct; retained)

    LIMIT 200 preserved. Sort by member_count desc (biggest clusters first).
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT
                c.cluster_id,
                c.run_date,
                c.principal_cn,
                d.file_name AS principal_name,
                c.member_count,
                c.sim_min,
                c.sim_max,
                c.review_status,
                c.reviewed_by,
                c.reviewed_at,
                (SELECT COUNT(*) FROM near_dupe_cluster_members m
                 WHERE m.cluster_id = c.cluster_id
                   AND m.decision = 'same'
                   AND m.is_principal = 0) AS confirmed_count,
                (SELECT COUNT(*) FROM near_dupe_cluster_members m
                 WHERE m.cluster_id = c.cluster_id
                   AND m.decision = 'undecided'
                   AND m.is_principal = 0
                   AND m.family_preserved = 0) AS pending_count,
                (SELECT COUNT(*) FROM near_dupe_cluster_members m
                 WHERE m.cluster_id = c.cluster_id
                   AND m.decision = 'same'
                   AND m.is_principal = 0
                   AND m.family_preserved = 1) AS family_retained_count,
                (SELECT COUNT(*) FROM near_dupe_cluster_members m
                 WHERE m.cluster_id = c.cluster_id
                   AND m.decision = 'distinct'
                   AND m.is_principal = 0) AS distinct_count
            FROM near_dupe_clusters c
            LEFT JOIN documents d ON d.control_number = c.principal_cn
            ORDER BY c.member_count DESC, c.cluster_id
            LIMIT 200
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def persist_near_dupe_clusters(case_folder, clusters):
    """Replace all near-dupe clusters with a fresh run's results. Applies NO
    suppression tag (deferred to reviewer confirmation). `clusters` is a list of
    dicts: {principal_cn, sim_min, sim_max,
            members:[{cn, similarity, is_principal, family_preserved}]}.
    Single transaction (atomic multi-table write)."""
    conn = get_connection(case_folder)
    now = datetime.now().isoformat()
    try:
        conn.execute("DELETE FROM near_dupe_cluster_members")
        conn.execute("DELETE FROM near_dupe_clusters")
        for c in clusters:
            cur = conn.execute(
                """INSERT INTO near_dupe_clusters
                   (run_date, principal_cn, member_count, sim_min, sim_max, review_status)
                   VALUES (?,?,?,?,?, 'pending')""",
                (now, c["principal_cn"], len(c["members"]), c.get("sim_min"), c.get("sim_max")))
            cluster_id = cur.lastrowid
            conn.executemany(
                """INSERT INTO near_dupe_cluster_members
                   (cluster_id, member_cn, is_principal, family_preserved, similarity, decision)
                   VALUES (?,?,?,?,?, 'undecided')""",
                [(cluster_id, m["cn"], int(m.get("is_principal", 0)),
                  int(m.get("family_preserved", 0)), m.get("similarity"))
                 for m in c["members"]])
        conn.commit()
    finally:
        conn.close()


def get_near_dupe_clusters(case_folder):
    """Cluster-level summary rows for the review list, principal filename joined
    in. Includes run_date so the Analytics "Last run" banner can source the date
    from the cluster table once status detection no longer keys off the tag."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT c.cluster_id, c.run_date, c.principal_cn, c.member_count,
                   c.sim_min, c.sim_max, c.review_status, c.reviewed_by, c.reviewed_at,
                   d.file_name AS principal_name,
                   (SELECT COUNT(*) FROM near_dupe_cluster_members m
                     WHERE m.cluster_id = c.cluster_id AND m.decision != 'undecided') AS decided_count,
                   (SELECT COUNT(*) FROM near_dupe_cluster_members m
                     WHERE m.cluster_id = c.cluster_id AND m.is_principal = 0
                       AND m.family_preserved = 0) AS suppressible_count,
                   (SELECT COUNT(*) FROM near_dupe_cluster_members m
                     WHERE m.cluster_id = c.cluster_id AND m.is_principal = 0
                       AND m.family_preserved = 0 AND m.decision != 'undecided') AS suppressible_decided
            FROM near_dupe_clusters c
            LEFT JOIN documents d ON d.control_number = c.principal_cn
            ORDER BY c.member_count DESC, c.cluster_id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_cluster_members(case_folder, cluster_id):
    """Member rows for one cluster, joined to documents for display + decision state."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT m.member_cn, m.is_principal, m.family_preserved, m.similarity,
                   m.decision, m.decided_by, m.decided_at, m.decided_in_cluster_id,
                   d.file_name, d.custodian, d.date_sent
            FROM near_dupe_cluster_members m
            LEFT JOIN documents d ON d.control_number = m.member_cn
            WHERE m.cluster_id = ?
            ORDER BY m.is_principal DESC, m.similarity DESC
        """, (cluster_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def record_member_decision(case_folder, cluster_id, member_cn, decision, username):
    """Record a reviewer's Same/Distinct call on one member and synchronize its
    NearDupe-Suppressed tag — atomically (decision row + documents.tags in one
    transaction). decision in {'same','distinct'}. 'same' applies the tag;
    'distinct' ensures it is absent. A family_preserved member never receives the
    tag (the decision is still recorded) — family-integrity-over-dedup. log_audit
    is best-effort (never-raise).

    Cross-cluster fan-out (S-1b C8b, spec §11.7): a document can be a non-principal
    member of more than one near-dupe cluster. One human decision is authoritative
    for the document, so the decision (and decided_by / decided_at) is written to
    EVERY (cluster_id=*, member_cn=cn) row, and decided_in_cluster_id is stamped
    with the SOURCE cluster_id on all of them — the UI reads it to render the
    overlap-lock badge in the non-source clusters (§11.4 State 3). Each row keeps
    its own similarity snapshot (similarity_at_decision = that row's similarity).
    The tag write is a single per-doc, idempotent action regardless of how many
    cluster rows reference the cn. All in one transaction."""
    assert decision in ("same", "distinct")
    conn = get_connection(case_folder)
    now = datetime.now().isoformat()
    try:
        # Family-integrity guard is a per-document property: if the doc is
        # family_preserved in ANY cluster it must never be suppressed (spec §3.1 —
        # "a family_preserved=1 row anywhere blocks suppression for that member_cn").
        fp_row = conn.execute(
            "SELECT MAX(family_preserved) AS fp FROM near_dupe_cluster_members "
            "WHERE member_cn=?", (member_cn,)).fetchone()
        family_preserved = (fp_row["fp"] if fp_row and fp_row["fp"] is not None else 0) or 0
        # Fan the decision out to every cluster row for this document; stamp the
        # source cluster on all of them; each row snapshots its own similarity.
        conn.execute("""UPDATE near_dupe_cluster_members
                        SET decision=?, decided_by=?, decided_at=?,
                            similarity_at_decision=similarity, decided_in_cluster_id=?
                        WHERE member_cn=?""",
                     (decision, username, now, cluster_id, member_cn))
        old = conn.execute("SELECT tags FROM documents WHERE control_number=?", (member_cn,)).fetchone()
        old_tags = (old["tags"] if old else "") or ""
        if decision == "same":
            # Family-integrity guard: never suppress a family-attached member,
            # even on a confirmed "same" — suppressing it would orphan the family.
            if not family_preserved and "NearDupe-Suppressed" not in old_tags:
                new_tags = (old_tags + "NearDupe-Suppressed;") if old_tags else "NearDupe-Suppressed;"
                conn.execute("UPDATE documents SET tags=? WHERE control_number=?", (new_tags, member_cn))
        else:  # distinct -> strip the tag if present
            if "NearDupe-Suppressed" in old_tags:
                new_tags = old_tags.replace("NearDupe-Suppressed;", "").replace("NearDupe-Suppressed", "")
                conn.execute("UPDATE documents SET tags=? WHERE control_number=?", (new_tags, member_cn))
        conn.commit()
    finally:
        conn.close()
    try:
        log_audit(case_folder, "NEARDUPE_DECISION", username=username, module="Review",
                  control_number=member_cn,
                  details=json.dumps({"cluster_id": cluster_id, "decision": decision}))
    except Exception:
        pass


def approve_cluster(case_folder, cluster_id, username, note=None):
    """Record the per-cluster attestation. Caller enforces 'all members decided'."""
    conn = get_connection(case_folder)
    try:
        conn.execute("""UPDATE near_dupe_clusters
                        SET review_status='approved', reviewed_by=?, reviewed_at=?, attestation_note=?
                        WHERE cluster_id=?""",
                     (username, datetime.now().isoformat(), note, cluster_id))
        conn.commit()
    finally:
        conn.close()
    try:
        log_audit(case_folder, "NEARDUPE_CLUSTER_APPROVED", username=username, module="Review",
                  details=json.dumps({"cluster_id": cluster_id, "note": note}))
    except Exception:
        pass


def reopen_cluster(case_folder, cluster_id, username):
    """Re-open an approved cluster for re-attestation (spec §11.5). Snapshots the
    prior attestation (reviewed_by / reviewed_at / attestation_note) into a
    NEARDUPE_CLUSTER_REOPENED audit_log entry BEFORE clearing it, then reverts the
    cluster row to 'pending' and NULLs the attestation fields. Member decisions are
    NOT cleared — they survive the re-open (the cluster typically returns to READY).
    The audit_log is the immutable forensic record; current state is editable.
    log_audit is best-effort (never-raise)."""
    conn = get_connection(case_folder)
    try:
        prior = conn.execute(
            "SELECT reviewed_by, reviewed_at, attestation_note FROM near_dupe_clusters "
            "WHERE cluster_id=?", (cluster_id,)).fetchone()
        conn.execute("""UPDATE near_dupe_clusters
                        SET review_status='pending', reviewed_by=NULL,
                            reviewed_at=NULL, attestation_note=NULL
                        WHERE cluster_id=?""", (cluster_id,))
        conn.commit()
    finally:
        conn.close()
    try:
        log_audit(case_folder, "NEARDUPE_CLUSTER_REOPENED", username=username, module="Review",
                  details=json.dumps({
                      "cluster_id": cluster_id,
                      "prior_reviewed_by": prior["reviewed_by"] if prior else None,
                      "prior_reviewed_at": prior["reviewed_at"] if prior else None,
                      "prior_attestation_note": prior["attestation_note"] if prior else None,
                  }))
    except Exception:
        pass


def clear_near_dupe_clusters(case_folder):
    """Delete all near-dupe clusters + member decisions and strip the
    NearDupe-Suppressed / NearDupe-Principal tags they produced. Returns
    (n_clusters, n_decisions) measured before deletion (for the re-run warning).
    Re-run discards reviewer work by design — the caller warns first."""
    conn = get_connection(case_folder)
    try:
        n_clusters = conn.execute("SELECT COUNT(*) FROM near_dupe_clusters").fetchone()[0]
        n_decisions = conn.execute(
            "SELECT COUNT(*) FROM near_dupe_cluster_members WHERE decision != 'undecided'"
        ).fetchone()[0]
        conn.execute("DELETE FROM near_dupe_cluster_members")
        conn.execute("DELETE FROM near_dupe_clusters")
        # Strip the tags prior confirmations applied (same REPLACE pattern as the
        # Analytics re-run path). Outbound docs only — matches the tagging scope.
        conn.execute("UPDATE documents SET tags = REPLACE(tags, 'NearDupe-Suppressed', '') WHERE source_party = 'Internal' OR source_party IS NULL")
        conn.execute("UPDATE documents SET tags = REPLACE(tags, 'NearDupe-Principal', '') WHERE source_party = 'Internal' OR source_party IS NULL")
        conn.execute("UPDATE documents SET tags = REPLACE(tags, ';;', ';') WHERE tags LIKE '%;;%' AND (source_party = 'Internal' OR source_party IS NULL)")
        conn.commit()
        return (n_clusters, n_decisions)
    finally:
        conn.close()


def get_near_dupe_review_progress(case_folder):
    """Aggregate read for the Analytics confirmed/pending metric AND the
    Clear-&-Re-run type-to-confirm guard (spec §6 / §11.10). Returns a dict:
      confirmed   — non-principal members with decision='same' (suppressed)
      pending     — non-principal members with decision='undecided'
      n_decisions — members with decision != 'undecided' (the §6 guard threshold)
      n_clusters  — total cluster rows
    Counts are member-row grain (a doc in N clusters counts N times) — consistent
    with the C8a per-cluster member_count framing. Single connection, single
    aggregate query — replaces the C8a F2-dispositioned inline per-cluster loop in
    3_Analytics.py's Execute metric block."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute("""
            SELECT
              SUM(CASE WHEN is_principal=0 AND decision='same' THEN 1 ELSE 0 END) AS confirmed,
              SUM(CASE WHEN is_principal=0 AND decision='undecided' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN decision != 'undecided' THEN 1 ELSE 0 END) AS n_decisions
            FROM near_dupe_cluster_members
        """).fetchone()
        n_clusters = conn.execute("SELECT COUNT(*) FROM near_dupe_clusters").fetchone()[0]
        return {
            "confirmed":   (row["confirmed"]   if row else 0) or 0,
            "pending":     (row["pending"]     if row else 0) or 0,
            "n_decisions": (row["n_decisions"] if row else 0) or 0,
            "n_clusters":  n_clusters,
        }
    finally:
        conn.close()


def get_all_exact_dupes_detail(case_folder):
    """Return detailed exact duplicate rows with master lookups.

    Returns list[dict] with keys: control_number, file_name, custodian, md5_hash,
    master_cn, master_file_name.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT d.control_number, d.file_name, d.custodian, d.md5_hash,
                   m.control_number as master_cn, m.file_name as master_file_name
            FROM documents d
            LEFT JOIN documents m
              ON d.md5_hash = m.md5_hash
             AND m.processing_status IN ('Processed','Master')
             AND d.control_number != m.control_number
            WHERE d.processing_status = 'Duplicate (MD5)'
            ORDER BY d.md5_hash, d.control_number
            LIMIT 2000
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_content_dupe_clusters(case_folder):
    """Return content (SHA-256) duplicate clusters for analytics display.

    Returns list[dict] with keys: content_hash, copies, representative_cn, all_cns,
    file_name, custodians.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT content_hash,
                   COUNT(*) as copies,
                   MIN(control_number) as representative_cn,
                   GROUP_CONCAT(control_number, ', ') as all_cns,
                   MIN(file_name) as file_name,
                   MIN(custodian) as custodians
            FROM documents
            WHERE content_hash IS NOT NULL AND content_hash != ''
            GROUP BY content_hash
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 200
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_custodian_activity_data(case_folder):
    """Return email communication data for custodian activity analysis.

    Returns list[dict] with keys: control_number, email_from, email_to,
    email_cc, date_sent, custodian.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT control_number, email_from, email_to, email_cc, date_sent, custodian
            FROM documents
            WHERE record_type = 'Email'
              AND processing_status IN ('Processed', 'Master')
              AND (source_party = 'Internal' OR source_party IS NULL)
              AND email_from IS NOT NULL
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_timeline_data(case_folder):
    """Return document timeline data for temporal analysis.

    Returns list[dict] with keys: date_sent, custodian, record_type.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT date_sent, custodian, record_type
            FROM documents
            WHERE processing_status IN ('Processed', 'Master')
              AND date_sent IS NOT NULL
              AND (source_party = 'Internal' OR source_party IS NULL)
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ===== PRODUCTION VOLUME MANAGEMENT ==========================================


def delete_production_volume(case_folder, volume_name):
    """Atomically delete a production volume's DB records and restore cache.

    1. Deletes from document_productions junction table
    2. Clears cache columns (begdoc, enddoc, production_volume) on affected documents
    3. Restores cache from remaining productions (if a doc has multiple productions)
    """
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "DELETE FROM document_productions WHERE production_volume = ?",
            (volume_name,)
        )
        conn.execute(
            "UPDATE documents SET begdoc=NULL, enddoc=NULL, production_volume=NULL "
            "WHERE production_volume = ?",
            (volume_name,)
        )
        # Restore cache for docs that have remaining production records
        conn.execute("""
            UPDATE documents SET
                begdoc = dp.begdoc,
                enddoc = dp.enddoc,
                production_volume = dp.production_volume
            FROM (
                SELECT control_number, begdoc, enddoc, production_volume
                FROM document_productions
                WHERE id IN (
                    SELECT MAX(id) FROM document_productions GROUP BY control_number
                )
            ) dp
            WHERE documents.control_number = dp.control_number
              AND documents.begdoc IS NULL
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_production_gap_report(case_folder):
    """Return all production records ordered for gap analysis.

    Returns list[dict] with keys: control_number, begdoc, enddoc, production_volume.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT control_number, begdoc, enddoc, production_volume "
            "FROM document_productions "
            "ORDER BY production_volume, begdoc"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ===== RETRY OPERATIONS =======================================================


def retry_processing_errors(case_folder):
    """Reset all error documents to 'New' for reprocessing. Returns count affected."""
    conn = get_connection(case_folder)
    try:
        cursor = conn.execute(
            "UPDATE documents SET processing_status='New' WHERE processing_status LIKE '%Error%'"
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def retry_sync_errors(case_folder):
    """Reset all sync error documents to 'Pending'. Returns count affected."""
    conn = get_connection(case_folder)
    try:
        cursor = conn.execute(
            "UPDATE documents SET sync_status = 'Pending' WHERE sync_status LIKE 'Error%'"
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_sync_error_details(case_folder):
    """Return sync error documents for display.

    Returns list[dict] with keys: control_number, file_name, sync_status.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT control_number, file_name, sync_status FROM documents"
            " WHERE sync_status LIKE 'Error%'"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ===== CASE SETTINGS ==========================================================


def save_case_settings_batch(case_folder, settings_dict):
    """Save multiple case settings as key-value pairs.

    settings_dict: dict of {setting_key: setting_value}
    """
    conn = get_connection(case_folder)
    try:
        for k, v in settings_dict.items():
            conn.execute(
                "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES (?, ?)",
                (k, v)
            )
        conn.commit()
    finally:
        conn.close()


def get_case_setting(case_folder, key):
    """Return a single case_settings value by key, or None if not set."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT setting_value FROM case_settings WHERE setting_key = ?", (key,)
        ).fetchone()
        return row['setting_value'] if row else None
    finally:
        conn.close()


def save_case_setting(case_folder, key, value):
    """Write a single case_settings key-value pair (upsert)."""
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()
    finally:
        conn.close()


# ===== DEFENSIBILITY REPORT QUERIES ==========================================


def get_defensibility_overview(case_folder):
    """Return case overview stats for the defensibility report.

    All `documents` queries below apply the mandatory outbound source filter
    (beta-2.10 Commit 3) — defensibility reports feed court-destined PDFs and
    must not include inbound (opposing-counsel) material in our universe
    counts, custodian counts, or date ranges.
    """
    conn = get_connection(case_folder)
    try:
        _outbound = outbound_source_filter_sql()  # mandatory inbound exclusion
        # Case: bare SELECT with no WHERE — prepend WHERE.
        total_docs = conn.execute(f"SELECT COUNT(*) FROM documents WHERE {_outbound}").fetchone()[0]
        # Case: existing WHERE with AND conditions — append AND.
        total_custodians = conn.execute(
            f"SELECT COUNT(DISTINCT custodian) FROM documents "
            f"WHERE custodian IS NOT NULL AND custodian != '' AND {_outbound}"
        ).fetchone()[0]
        earliest = conn.execute(
            f"SELECT MIN(date_created) FROM documents WHERE date_created IS NOT NULL AND {_outbound}"
        ).fetchone()[0]
        latest = conn.execute(
            f"SELECT MAX(date_created) FROM documents WHERE date_created IS NOT NULL AND {_outbound}"
        ).fetchone()[0]
        status_row = conn.execute(
            "SELECT setting_value FROM case_settings WHERE setting_key='case_status'"
        ).fetchone()
        case_status = status_row[0] if status_row else 'Active'
        first_ingest = conn.execute(
            "SELECT MIN(timestamp) FROM audit_log WHERE action='DOCUMENT_INGESTED'"
        ).fetchone()[0]
        last_process = conn.execute(
            "SELECT MAX(timestamp) FROM audit_log WHERE action IN ('PROCESSING_COMPLETED','TEXT_EXTRACTED')"
        ).fetchone()[0]
        return {
            'total_documents': total_docs,
            'total_custodians': total_custodians,
            'date_range_earliest': earliest,
            'date_range_latest': latest,
            'case_status': case_status,
            'first_ingestion': first_ingest,
            'last_processing': last_process,
        }
    finally:
        conn.close()


def get_defensibility_ingestion(case_folder):
    """Return ingestion statistics for the defensibility report.

    All `documents` queries apply the mandatory outbound source filter
    (beta-2.10 Commit 3). WHERE clauses prepend the filter before GROUP BY.
    """
    conn = get_connection(case_folder)
    try:
        _outbound = outbound_source_filter_sql()
        custodian_breakdown = conn.execute(f"""
            SELECT COALESCE(custodian, '(No Custodian)') as custodian,
                   COUNT(*) as doc_count,
                   SUM(file_size_kb) as total_size_kb
            FROM documents
            WHERE {_outbound}
            GROUP BY custodian
            ORDER BY doc_count DESC
        """).fetchall()
        file_types = conn.execute(f"""
            SELECT COALESCE(LOWER(file_extension), '(none)') as ext,
                   COUNT(*) as count
            FROM documents
            WHERE {_outbound}
            GROUP BY LOWER(file_extension)
            ORDER BY count DESC
            LIMIT 20
        """).fetchall()
        record_types = conn.execute(f"""
            SELECT COALESCE(record_type, '(Unclassified)') as rtype,
                   COUNT(*) as count
            FROM documents
            WHERE {_outbound}
            GROUP BY record_type
            ORDER BY count DESC
        """).fetchall()
        source_collections = conn.execute(f"""
            SELECT COALESCE(source_collection, '(Flat Ingestion)') as collection,
                   COUNT(*) as count
            FROM documents
            WHERE {_outbound}
            GROUP BY source_collection
            ORDER BY count DESC
        """).fetchall()
        total_size = conn.execute(
            f"SELECT SUM(file_size_kb) FROM documents WHERE {_outbound}"
        ).fetchone()[0] or 0
        return {
            'custodians': [dict(r) for r in custodian_breakdown],
            'file_types': [dict(r) for r in file_types],
            'record_types': [dict(r) for r in record_types],
            'source_collections': [dict(r) for r in source_collections],
            'total_size_kb': total_size,
        }
    finally:
        conn.close()


def get_defensibility_processing(case_folder):
    """Return processing pipeline stats for the defensibility report.

    All `documents` queries apply the mandatory outbound source filter
    (beta-2.10 Commit 3).
    """
    conn = get_connection(case_folder)
    try:
        _outbound = outbound_source_filter_sql()
        status_breakdown = conn.execute(f"""
            SELECT processing_status, COUNT(*) as count
            FROM documents
            WHERE {_outbound}
            GROUP BY processing_status
            ORDER BY count DESC
        """).fetchall()
        extraction_methods = conn.execute(f"""
            SELECT COALESCE(extraction_method, '(Unknown)') as method,
                   COUNT(*) as count
            FROM documents
            WHERE processing_status IN ('Processed', 'Master')
              AND {_outbound}
            GROUP BY extraction_method
            ORDER BY count DESC
        """).fetchall()
        error_docs = conn.execute(f"""
            SELECT control_number, file_name, custodian, processing_status, file_extension
            FROM documents
            WHERE processing_status LIKE '%Error%'
              AND {_outbound}
            ORDER BY control_number
            LIMIT 500
        """).fetchall()
        encrypted_count = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE is_encrypted = 1 AND {_outbound}"
        ).fetchone()[0]
        ocr_count = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE extraction_method = 'tesseract_ocr' AND {_outbound}"
        ).fetchone()[0]
        return {
            'status_breakdown': [dict(r) for r in status_breakdown],
            'extraction_methods': [dict(r) for r in extraction_methods],
            'error_docs': [dict(r) for r in error_docs],
            'error_count': len(error_docs),
            'encrypted_count': encrypted_count,
            'ocr_count': ocr_count,
        }
    finally:
        conn.close()


def get_defensibility_dedup(case_folder):
    """Return deduplication/analytics stats for the defensibility report.

    All `documents` queries apply the mandatory outbound source filter
    (beta-2.10 Commit 3). `net_reviewable` shows the parenthesized-OR case:
    existing `(tags NOT LIKE ... OR tags IS NULL)` clauses stay wrapped, and
    the new `AND {_outbound}` appends at the end without changing operator
    precedence.
    """
    conn = get_connection(case_folder)
    try:
        _outbound = outbound_source_filter_sql()
        total_ingested = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE {_outbound}"
        ).fetchone()[0]
        exact_dupes = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE processing_status='Duplicate (MD5)' AND {_outbound}"
        ).fetchone()[0]
        content_dupes = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE processing_status='Duplicate (Content)' AND {_outbound}"
        ).fetchone()[0]
        processed = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE processing_status IN ('Processed','Master') AND {_outbound}"
        ).fetchone()[0]
        nd_suppressed = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE tags LIKE '%NearDupe-Suppressed%' AND {_outbound}"
        ).fetchone()[0]
        nd_principals = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE tags LIKE '%NearDupe-Principal%' AND {_outbound}"
        ).fetchone()[0]
        thread_suppressed = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE tags LIKE '%Thread-Suppressed%' AND {_outbound}"
        ).fetchone()[0]
        thread_inclusive = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE tags LIKE '%Inclusive%' AND {_outbound}"
        ).fetchone()[0]
        net_reviewable = conn.execute(f"""
            SELECT COUNT(*) FROM documents
            WHERE processing_status IN ('Processed','Master')
              AND (tags NOT LIKE '%NearDupe-Suppressed%' OR tags IS NULL)
              AND (tags NOT LIKE '%Thread-Suppressed%' OR tags IS NULL)
              AND {_outbound}
        """).fetchone()[0]
        # Near-dupe cluster dispositions (S-1c). Cluster tables are outbound-only by
        # construction (clusters built from source_party='Internal' corpus,
        # pages/3_Analytics.py:352) — no documents-table outbound filter applies here.
        #
        # B-1 FIX (v2): DISTINCT-DOCUMENT counts, not (cluster,member)-pair counts. Under
        # Flag #30 a doc can be a member of >1 cluster (observed on the Test(small) regression case); COUNT(*)
        # would double-count and break reconciliation with the tag-based nd_suppressed.
        #
        # B-2 FIX (v3): classify each distinct non-principal document ONCE over the FULL
        # decision×family grid (6 cells). v2 dropped (undecided, family_preserved=1) — the
        # DEFAULT post-run state of every family-attached member (decision DEFAULT
        # 'undecided') — under-reporting the unreviewed population on a court PDF. "Pending
        # review" is therefore ALL undecided (any family state), named `nd_undecided` to
        # NOT collide with the suppressibility-`pending` semantic in
        # get_data_reduction_stats/pending_count (undecided AND fp=0, kept for Analytics).
        # fp mirrors the tag guard EXACTLY: MAX(family_preserved) over ALL of the member's
        # rows (record_member_decision), not just is_principal=0 rows.
        # Disposition cells: same&fp0 -> suppressed (= nd_suppressed, tag-based, above);
        # distinct -> distinct; same&fp1 -> family-retained; undecided(any fp) -> undecided.
        _disp = conn.execute("""
            SELECT
              SUM(CASE WHEN d_distinct=1 THEN 1 ELSE 0 END)      AS dist,
              SUM(CASE WHEN d_same=1 AND fp=1 THEN 1 ELSE 0 END) AS famret,
              SUM(CASE WHEN d_undecided=1 THEN 1 ELSE 0 END)     AS undecided_n
            FROM (
              SELECT m.member_cn,
                     (SELECT MAX(a.family_preserved) FROM near_dupe_cluster_members a
                       WHERE a.member_cn = m.member_cn) AS fp,
                     MAX(CASE WHEN m.decision='same' THEN 1 ELSE 0 END)      AS d_same,
                     MAX(CASE WHEN m.decision='distinct' THEN 1 ELSE 0 END)  AS d_distinct,
                     MAX(CASE WHEN m.decision='undecided' THEN 1 ELSE 0 END) AS d_undecided
              FROM near_dupe_cluster_members m
              WHERE m.is_principal=0
              GROUP BY m.member_cn
            )
        """).fetchone()
        nd_family_retained = _disp["famret"] or 0
        nd_distinct = _disp["dist"] or 0
        nd_undecided = _disp["undecided_n"] or 0
        n_clusters = conn.execute("SELECT COUNT(*) FROM near_dupe_clusters").fetchone()[0]
        # Partition identity (pinned by tests/test_defensibility_neardupe_report.py): the
        # same&fp0 cell is carried by the tag-based `nd_suppressed` (already computed above).
        # Then nd_suppressed + nd_family_retained + nd_distinct + nd_undecided
        #   == COUNT(DISTINCT member_cn) over is_principal=0 rows.
        # All 6 decision×family cells have exactly one home.
        return {
            'total_ingested': total_ingested,
            'exact_dupes': exact_dupes,
            'content_dupes': content_dupes,
            'processed': processed,
            'nd_suppressed': nd_suppressed,
            'nd_principals': nd_principals,
            'thread_suppressed': thread_suppressed,
            'thread_inclusive': thread_inclusive,
            'net_reviewable': net_reviewable,
            'nd_family_retained': nd_family_retained,
            'nd_distinct': nd_distinct,
            'nd_undecided': nd_undecided,
            'n_clusters': n_clusters,
        }
    finally:
        conn.close()


def get_defensibility_review(case_folder):
    """Return review progress stats for the defensibility report.

    All `documents` queries apply the mandatory outbound source filter
    (beta-2.10 Commit 3). `reviewer_activity` queries audit_log, not
    documents — outbound filter does not apply there.
    """
    conn = get_connection(case_folder)
    try:
        _outbound = outbound_source_filter_sql()
        # Parenthesized-OR case: existing ORs stay wrapped; new AND appends safely.
        total_reviewable = conn.execute(f"""
            SELECT COUNT(*) FROM documents
            WHERE processing_status IN ('Processed','Master')
              AND (tags NOT LIKE '%NearDupe-Suppressed%' OR tags IS NULL)
              AND (tags NOT LIKE '%Thread-Suppressed%' OR tags IS NULL)
              AND {_outbound}
        """).fetchone()[0]
        reviewable_tags = conn.execute(f"""
            SELECT tags FROM documents
            WHERE processing_status IN ('Processed','Master')
              AND (tags NOT LIKE '%NearDupe-Suppressed%' OR tags IS NULL)
              AND (tags NOT LIKE '%Thread-Suppressed%' OR tags IS NULL)
              AND tags IS NOT NULL AND tags != ''
              AND {_outbound}
        """).fetchall()
        all_tags_raw = conn.execute(
            f"SELECT tags FROM documents WHERE tags IS NOT NULL AND tags != '' AND {_outbound}"
        ).fetchall()
        reviewer_activity = conn.execute("""
            SELECT COALESCE(username, '(System)') as reviewer,
                   COUNT(*) as actions,
                   MIN(timestamp) as first_action,
                   MAX(timestamp) as last_action
            FROM audit_log
            WHERE action IN ('TAG_APPLIED', 'TAG_REMOVED', 'TAGS_CHANGED',
                             'REDACTION_SAVED', 'REDACTION_CLEARED', 'COMMENT_ADDED')
            GROUP BY username
            ORDER BY actions DESC
        """).fetchall()
        responsive = conn.execute(
            f"SELECT COUNT(*) FROM documents "
            f"WHERE tags LIKE '%Responsive%' AND tags NOT LIKE '%Not Responsive%' "
            f"AND {_outbound}"
        ).fetchone()[0]
        not_responsive = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE tags LIKE '%Not Responsive%' AND {_outbound}"
        ).fetchone()[0]
        return {
            'total_reviewable': total_reviewable,
            'reviewable_tags': [dict(r) for r in reviewable_tags],
            'all_tags_raw': [dict(r) for r in all_tags_raw],
            'reviewer_activity': [dict(r) for r in reviewer_activity],
            'responsive_count': responsive,
            'not_responsive_count': not_responsive,
        }
    finally:
        conn.close()


def get_defensibility_production(case_folder):
    """Return production stats for the defensibility report.

    Note: this function uses the strict `source_party = 'Internal'` form
    (not `(source_party = 'Internal' OR IS NULL)`). Productions are
    definitionally outbound; a NULL source_party on a production row would
    indicate a data integrity issue, not a legacy-migration condition.
    The asymmetry with other defensibility helpers is intentional.
    """
    conn = get_connection(case_folder)
    try:
        productions = conn.execute("""
            SELECT production_volume,
                   COUNT(*) as doc_count,
                   MIN(begdoc) as first_bates,
                   MAX(enddoc) as last_bates
            FROM documents
            WHERE production_volume IS NOT NULL AND production_volume != ''
              AND source_party = 'Internal'  -- strict by design, see docstring
            GROUP BY production_volume
            ORDER BY production_volume
        """).fetchall()
        prod_events = conn.execute("""
            SELECT action, COUNT(*) as count, MIN(timestamp) as first, MAX(timestamp) as last
            FROM audit_log
            WHERE action IN ('PRODUCTION_CREATED', 'PRODUCTION_EXPORTED',
                             'BATES_ASSIGNED', 'REDACTION_BURNED',
                             'PRODUCTION_PASS1_COMPLETE')
            GROUP BY action
            ORDER BY action
        """).fetchall()
        produced_total = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE begdoc IS NOT NULL AND begdoc != ''"
        ).fetchone()[0]
        try:
            produced_total_jt = conn.execute(
                "SELECT COUNT(DISTINCT control_number) FROM document_productions"
            ).fetchone()[0]
        except Exception:
            produced_total_jt = produced_total
        try:
            prod_detail = conn.execute("""
                SELECT production_volume, production_type,
                       COUNT(*) as doc_count,
                       MIN(begdoc) as first_bates,
                       MAX(enddoc) as last_bates,
                       MIN(produced_at) as first_produced,
                       MAX(produced_at) as last_produced
                FROM document_productions
                GROUP BY production_volume, production_type
                ORDER BY production_volume, production_type
            """).fetchall()
            prod_detail = [dict(r) for r in prod_detail]
        except Exception:
            prod_detail = []
        return {
            'productions': [dict(r) for r in productions],
            'prod_events': [dict(r) for r in prod_events],
            'total_produced': produced_total,
            'total_produced_jt': produced_total_jt,
            'prod_detail': prod_detail,
        }
    finally:
        conn.close()


def get_defensibility_privilege(case_folder):
    """Return privilege disposition stats for the defensibility report."""
    conn = get_connection(case_folder)
    try:
        _shell_filter = " AND processing_status NOT IN ('Container_Scanned', 'Split_Source')"
        withheld = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE privilege_status = 'Withhold'" + _shell_filter
        ).fetchone()[0]
        redacted = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE privilege_status = 'Redact'" + _shell_filter
        ).fetchone()[0]
        no_disposition = conn.execute(
            "SELECT COUNT(*) FROM documents"
            " WHERE tags LIKE '%Privileged%'"
            "   AND (privilege_status IS NULL OR privilege_status = '')" + _shell_filter
        ).fetchone()[0]
        try:
            redaction_marks_count = conn.execute(
                "SELECT COUNT(DISTINCT control_number) FROM redaction_marks"
            ).fetchone()[0]
        except Exception:
            redaction_marks_count = 0
        redactions_applied = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE redaction_status = 'Applied'" + _shell_filter
        ).fetchone()[0]
        return {
            'withheld': withheld,
            'redacted': redacted,
            'no_disposition': no_disposition,
            'total_privileged': withheld + redacted + no_disposition,
            'redaction_marks_count': redaction_marks_count,
            'redactions_applied': redactions_applied,
        }
    finally:
        conn.close()


def get_defensibility_audit(case_folder):
    """Return audit trail summary for the defensibility report."""
    conn = get_connection(case_folder)
    try:
        total_events = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        date_range = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM audit_log"
        ).fetchone()
        by_action = conn.execute("""
            SELECT action, COUNT(*) as count
            FROM audit_log
            GROUP BY action
            ORDER BY count DESC
        """).fetchall()
        by_user = conn.execute("""
            SELECT COALESCE(username, '(System)') as user,
                   COUNT(*) as count
            FROM audit_log
            GROUP BY username
            ORDER BY count DESC
        """).fetchall()
        by_module = conn.execute("""
            SELECT COALESCE(module, '(Untagged)') as module,
                   COUNT(*) as count
            FROM audit_log
            GROUP BY module
            ORDER BY count DESC
        """).fetchall()
        return {
            'total_events': total_events,
            'earliest_event': date_range[0] if date_range else 'N/A',
            'latest_event': date_range[1] if date_range else 'N/A',
            'by_action': [dict(r) for r in by_action],
            'by_user': [dict(r) for r in by_user],
            'by_module': [dict(r) for r in by_module],
        }
    finally:
        conn.close()


def get_defensibility_holds(case_folder):
    """Return legal hold stats for the defensibility report."""
    conn = get_connection(case_folder)
    try:
        _tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='custodians'"
        ).fetchall()]
        if 'custodians' not in _tables:
            return {'holds': [], 'has_custodians_table': False}
        holds = conn.execute("""
            SELECT name, hold_status, hold_issued_date, hold_acknowledged_date,
                   hold_released_date, hold_notice_method
            FROM custodians
            WHERE hold_status IS NOT NULL AND hold_status != 'None'
            ORDER BY hold_issued_date
        """).fetchall()
        return {
            'holds': [dict(h) for h in holds],
            'has_custodians_table': True,
        }
    finally:
        conn.close()


# ── Path Repair (Case Migration) ────────────────────────────────────────────

# Known case subfolders used to identify the case root in an absolute path.
_CASE_SUBFOLDERS = ('Ingest', 'Processed', 'Split', 'Hold_Documents',
                    'Productions', 'Reviewed', 'Temp_Explode', 'Audit',
                    'Inbound')


def _normalize_path_for_compare(p):
    """Strip \\\\?\\\\ prefix if present, then normpath + normcase for Windows."""
    if p and p.startswith('\\\\?\\'):
        p = p[4:]
    return os.path.normcase(os.path.normpath(p))


def _extract_case_root(full_path):
    """Extract the case folder root from an absolute path.

    Finds the first known case subfolder in the path and returns everything
    before it.  e.g. ``G:\\eDiscovery\\MyCase\\Processed\\file.pdf``
    → ``G:\\eDiscovery\\MyCase``.

    Returns *None* if no known subfolder is found (path too ambiguous).
    """
    norm = os.path.normpath(full_path)
    parts = norm.split(os.sep)
    for i, part in enumerate(parts):
        if part in _CASE_SUBFOLDERS:
            return os.sep.join(parts[:i])
    return None


def detect_path_roots(case_folder):
    """Scan all path-storing tables and classify paths as matching or stale.

    Returns dict with per-table counts and a list of distinct roots found.
    """
    norm_cf = _normalize_path_for_compare(case_folder)
    conn = get_connection(case_folder)
    try:
        # ── documents.full_path ──────────────────────────────────────
        doc_rows = conn.execute(
            "SELECT full_path FROM documents WHERE full_path IS NOT NULL"
        ).fetchall()
        # ── hold_documents.file_path ─────────────────────────────────
        try:
            hold_rows = conn.execute(
                "SELECT file_path FROM hold_documents WHERE file_path IS NOT NULL"
            ).fetchall()
        except Exception:
            hold_rows = []
        # ── exhibit_sets.case_folder ─────────────────────────────────
        try:
            ex_rows = conn.execute(
                "SELECT case_folder FROM exhibit_sets"
            ).fetchall()
        except Exception:
            ex_rows = []
    finally:
        conn.close()

    root_counter = {}  # root → count

    def _tally(path_value, is_exhibit_cf=False):
        if is_exhibit_cf:
            root = os.path.normpath(path_value)
        else:
            root = _extract_case_root(path_value)
        if root is None:
            return
        root_norm = _normalize_path_for_compare(root)
        root_counter[root_norm] = root_counter.get(root_norm, 0) + 1

    for r in doc_rows:
        _tally(r[0])
    for r in hold_rows:
        _tally(r[0])
    for r in ex_rows:
        _tally(r[0], is_exhibit_cf=True)

    # Build per-table matched/mismatched counts
    def _count_table(rows, is_exhibit_cf=False):
        matched = mismatched = 0
        for r in rows:
            if is_exhibit_cf:
                root = os.path.normpath(r[0])
            else:
                root = _extract_case_root(r[0])
            if root is None:
                mismatched += 1
                continue
            if _normalize_path_for_compare(root) == norm_cf:
                matched += 1
            else:
                mismatched += 1
        return {'total': len(rows), 'matched': matched, 'mismatched': mismatched}

    distinct_roots = []
    for root_norm, count in sorted(root_counter.items(), key=lambda x: -x[1]):
        distinct_roots.append({
            'root': root_norm,
            'count': count,
            'matches': root_norm == norm_cf,
        })

    return {
        'case_folder': norm_cf,
        'tables': {
            'documents': _count_table(doc_rows),
            'hold_documents': _count_table(hold_rows),
            'exhibit_sets': _count_table(ex_rows, is_exhibit_cf=True),
        },
        'distinct_roots': distinct_roots,
    }


def preview_path_repair(case_folder, old_root, limit=50):
    """Dry-run preview of path replacements across all three tables.

    Returns per-table counts and a sample list of old → new mappings.
    """
    norm_old = _normalize_path_for_compare(old_root)
    conn = get_connection(case_folder)
    try:
        doc_rows = conn.execute(
            "SELECT control_number, full_path FROM documents "
            "WHERE full_path IS NOT NULL"
        ).fetchall()
        try:
            hold_rows = conn.execute(
                "SELECT id, file_path FROM hold_documents "
                "WHERE file_path IS NOT NULL"
            ).fetchall()
        except Exception:
            hold_rows = []
        try:
            ex_rows = conn.execute(
                "SELECT id, case_folder FROM exhibit_sets"
            ).fetchall()
        except Exception:
            ex_rows = []
    finally:
        conn.close()

    samples = []
    results = {
        'documents': {'would_fix': 0, 'file_exists': 0, 'file_missing': 0},
        'hold_documents': {'would_fix': 0, 'file_exists': 0, 'file_missing': 0},
        'exhibit_sets': {'would_fix': 0},
        'samples': samples,
    }

    def _process_rows(rows, table_name, is_exhibit_cf=False):
        for row in rows:
            id_val, path_val = row[0], row[1]
            if is_exhibit_cf:
                root = os.path.normpath(path_val)
            else:
                root = _extract_case_root(path_val)
            if root is None:
                continue
            if _normalize_path_for_compare(root) != norm_old:
                continue
            # This row matches the old root — compute new path
            results[table_name]['would_fix'] += 1
            if is_exhibit_cf:
                new_path = case_folder
            else:
                try:
                    rel = os.path.relpath(path_val, old_root)
                    new_path = os.path.join(case_folder, rel)
                except ValueError:
                    # Cross-drive relpath can fail on Windows
                    new_path = path_val.replace(old_root, case_folder, 1)

            if table_name != 'exhibit_sets':
                exists = os.path.isfile(new_path)
                if exists:
                    results[table_name]['file_exists'] += 1
                else:
                    results[table_name]['file_missing'] += 1
            else:
                exists = None

            if len(samples) < limit:
                samples.append({
                    'table': table_name,
                    'id': str(id_val),
                    'old_path': path_val,
                    'new_path': new_path,
                    'exists': exists,
                })

    _process_rows(doc_rows, 'documents')
    _process_rows(hold_rows, 'hold_documents')
    _process_rows(ex_rows, 'exhibit_sets', is_exhibit_cf=True)

    return results


def repair_paths(case_folder, old_root, username=None):
    """Replace old_root prefix with case_folder in all matching path columns.

    Operates on documents.full_path, hold_documents.file_path, and
    exhibit_sets.case_folder.  Uses Python-side path computation (not SQL
    REPLACE) to avoid substring false-positives.

    Returns dict with per-table update counts and any errors.
    """
    norm_old = _normalize_path_for_compare(old_root)
    conn = get_connection(case_folder)
    doc_updated = hold_updated = ex_updated = 0
    errors = []

    try:
        # ── documents.full_path ──────────────────────────────────────
        doc_rows = conn.execute(
            "SELECT rowid, full_path FROM documents "
            "WHERE full_path IS NOT NULL"
        ).fetchall()
        doc_updates = []
        for row in doc_rows:
            rowid, path_val = row[0], row[1]
            root = _extract_case_root(path_val)
            if root is None or _normalize_path_for_compare(root) != norm_old:
                continue
            try:
                rel = os.path.relpath(path_val, old_root)
                new_path = os.path.join(case_folder, rel)
            except ValueError:
                new_path = path_val.replace(old_root, case_folder, 1)
            doc_updates.append((new_path, rowid))

        if doc_updates:
            conn.executemany(
                "UPDATE documents SET full_path = ? WHERE rowid = ?",
                doc_updates
            )
            doc_updated = len(doc_updates)

        # ── hold_documents.file_path ─────────────────────────────────
        try:
            hold_rows = conn.execute(
                "SELECT id, file_path FROM hold_documents "
                "WHERE file_path IS NOT NULL"
            ).fetchall()
        except Exception:
            hold_rows = []

        hold_updates = []
        for row in hold_rows:
            hid, path_val = row[0], row[1]
            root = _extract_case_root(path_val)
            if root is None or _normalize_path_for_compare(root) != norm_old:
                continue
            try:
                rel = os.path.relpath(path_val, old_root)
                new_path = os.path.join(case_folder, rel)
            except ValueError:
                new_path = path_val.replace(old_root, case_folder, 1)
            hold_updates.append((new_path, hid))

        if hold_updates:
            conn.executemany(
                "UPDATE hold_documents SET file_path = ? WHERE id = ?",
                hold_updates
            )
            hold_updated = len(hold_updates)

        # ── exhibit_sets.case_folder ─────────────────────────────────
        try:
            ex_rows = conn.execute(
                "SELECT id, case_folder FROM exhibit_sets"
            ).fetchall()
        except Exception:
            ex_rows = []

        ex_updates = []
        for row in ex_rows:
            eid, cf_val = row[0], row[1]
            if _normalize_path_for_compare(cf_val) != norm_old:
                continue
            ex_updates.append((case_folder, eid))

        if ex_updates:
            conn.executemany(
                "UPDATE exhibit_sets SET case_folder = ? WHERE id = ?",
                ex_updates
            )
            ex_updated = len(ex_updates)

        conn.commit()
    except Exception as e:
        conn.rollback()
        errors.append(str(e))
    finally:
        conn.close()

    # Audit log
    try:
        log_audit(case_folder, "PATH_REPAIR", username=username,
                  module="Home", details=json.dumps({
                      "old_root": old_root,
                      "new_root": case_folder,
                      "documents_updated": doc_updated,
                      "hold_documents_updated": hold_updated,
                      "exhibit_sets_updated": ex_updated,
                  }))
    except Exception:
        pass

    return {
        'documents_updated': doc_updated,
        'hold_updated': hold_updated,
        'exhibits_updated': ex_updated,
        'errors': errors,
    }


# ── Background Job Management ───────────────────────────────────────────────

def create_job(case_folder, job_type, username, total=0, details=None):
    """Create a new background job record. Returns the job ID."""
    conn = get_connection(case_folder)
    try:
        cursor = conn.execute(
            """INSERT INTO jobs (job_type, status, total, case_folder, username, details_json)
               VALUES (?, 'pending', ?, ?, ?, ?)""",
            (job_type, total, case_folder, username,
             json.dumps(details) if details else None)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def start_job(case_folder, job_id, pid):
    """Mark a job as running with the worker's OS process ID."""
    _sql = """UPDATE jobs SET status = 'running', started_at = ?, pid = ?
              WHERE id = ?"""
    _params = (datetime.now().isoformat(), pid, job_id)
    conn = get_connection(case_folder)
    try:
        conn.execute(_sql, _params)
        conn.commit()
    except sqlite3.OperationalError:
        time.sleep(0.5)
        try:
            conn.execute(_sql, _params)
            conn.commit()
        except sqlite3.OperationalError as e:
            logger.warning(f"start_job skipped (DB locked): {e}")
    finally:
        conn.close()


def update_job_progress(case_folder, job_id, phase, progress, total,
                        phase_label=None, details_json=None):
    """Update progress counters for a running job. Called frequently by the worker.
    Non-fatal on DB lock — retries once, then logs warning and continues."""
    _sql = """UPDATE jobs SET phase = ?, progress = ?, total = ?,
              phase_label = ?, details_json = ?
              WHERE id = ?"""
    _params = (phase, progress, total, phase_label,
               json.dumps(details_json) if isinstance(details_json, dict) else details_json,
               job_id)
    conn = get_connection(case_folder)
    try:
        conn.execute(_sql, _params)
        conn.commit()
    except sqlite3.OperationalError:
        time.sleep(0.5)
        try:
            conn.execute(_sql, _params)
            conn.commit()
        except sqlite3.OperationalError as e:
            logger.warning(f"Job progress update skipped (DB locked): {e}")
    finally:
        conn.close()


def complete_job(case_folder, job_id, details_json=None):
    """Mark a job as successfully completed."""
    _sql = """UPDATE jobs SET status = 'completed', finished_at = ?,
              details_json = ?
              WHERE id = ?"""
    _params = (datetime.now().isoformat(),
               json.dumps(details_json) if isinstance(details_json, dict) else details_json,
               job_id)
    conn = get_connection(case_folder)
    try:
        conn.execute(_sql, _params)
        conn.commit()
    except sqlite3.OperationalError:
        time.sleep(0.5)
        try:
            conn.execute(_sql, _params)
            conn.commit()
        except sqlite3.OperationalError as e:
            logger.warning(f"complete_job skipped (DB locked): {e}")
    finally:
        conn.close()


def fail_job(case_folder, job_id, error_msg, details_json=None):
    """Mark a job as failed with an error message."""
    _sql = """UPDATE jobs SET status = 'failed', finished_at = ?,
              error = ?, details_json = ?
              WHERE id = ?"""
    _params = (datetime.now().isoformat(), str(error_msg)[:2000],
               json.dumps(details_json) if isinstance(details_json, dict) else details_json,
               job_id)
    conn = get_connection(case_folder)
    try:
        conn.execute(_sql, _params)
        conn.commit()
    except sqlite3.OperationalError:
        time.sleep(0.5)
        try:
            conn.execute(_sql, _params)
            conn.commit()
        except sqlite3.OperationalError as e:
            logger.warning(f"fail_job skipped (DB locked): {e}")
    finally:
        conn.close()


def cancel_job(case_folder, job_id):
    """Request cancellation of a running job (UI-facing)."""
    _sql = """UPDATE jobs SET cancel_requested = 1, status = 'cancelling'
              WHERE id = ? AND status IN ('pending', 'running')"""
    _params = (job_id,)
    conn = get_connection(case_folder)
    try:
        conn.execute(_sql, _params)
        conn.commit()
    except sqlite3.OperationalError:
        time.sleep(0.5)
        try:
            conn.execute(_sql, _params)
            conn.commit()
        except sqlite3.OperationalError as e:
            logger.warning(f"cancel_job skipped (DB locked): {e}")
    finally:
        conn.close()


def get_active_job(case_folder, job_type='processing'):
    """Return the most recent active job for this case, or None."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            """SELECT * FROM jobs
               WHERE case_folder = ? AND job_type = ?
                 AND status IN ('pending', 'running', 'cancelling')
               ORDER BY created_at DESC LIMIT 1""",
            (case_folder, job_type)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_job(case_folder, job_id):
    """Return a single job by ID, or None."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_last_completed_job(case_folder, job_type='processing'):
    """Return the most recently completed/failed/cancelled job, or None.
    Used to show results after the user navigates away and comes back."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            """SELECT * FROM jobs
               WHERE case_folder = ? AND job_type = ?
                 AND status IN ('completed', 'failed', 'cancelled')
               ORDER BY finished_at DESC LIMIT 1""",
            (case_folder, job_type)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def is_cancel_requested(case_folder, job_id):
    """Lightweight check for the worker's inner loop. Returns bool.
    Non-fatal on DB lock — returns False rather than crashing."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return bool(row and row['cancel_requested'])
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def cleanup_stale_jobs(case_folder):
    """Detect jobs whose worker process has died and mark them as failed.
    Called on Processor page load."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            """SELECT id, pid FROM jobs
               WHERE case_folder = ? AND status IN ('running', 'cancelling')""",
            (case_folder,)
        ).fetchall()
        for row in rows:
            pid = row['pid']
            if pid and not _is_pid_alive(pid):
                conn.execute(
                    """UPDATE jobs SET status = 'failed', finished_at = ?,
                       error = 'Worker process died unexpectedly (PID no longer exists)'
                       WHERE id = ?""",
                    (datetime.now().isoformat(), row['id'])
                )
        conn.commit()
    finally:
        conn.close()


def _is_pid_alive(pid):
    """Check if a process with the given PID is still running (Windows-compatible).
    Uses GetExitCodeProcess to detect zombie handles where OpenProcess succeeds
    but the process has already exited."""
    if not pid:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            exit_code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            # 259 = STILL_ACTIVE — process is running
            return exit_code.value == 259
        return False
    except Exception:
        # ctypes failed — assume dead rather than risk infinite "cancelling" loop
        return False
