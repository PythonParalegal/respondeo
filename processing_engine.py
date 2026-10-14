# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        processing_engine.py
# version:       1.0.5
# project:       Respondeo eDiscovery Platform
# project_ver:   2.15.0
# last_modified: 2026-05-21 15:33
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
"""
Processing engine — shared logic for document processing pipeline.

This module contains all processing logic extracted from 2_Processor.py so it
can be used by both the Streamlit UI (inline) and the background worker
(_processing_worker.py). No Streamlit imports allowed.

Three phases:
  Phase 1 — Container extraction (PST/MSG/EML/ZIP → child documents)
  Phase 2 — Parallel text extraction + OpenSearch indexing + dedup
  Phase 3 — Email imaging (MSG/EML → PDF via universal_imager)
"""
import os
import sys
import shutil
import sqlite3
import json
import time
import logging
import threading
import hashlib
import queue
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # PyMuPDF
import pandas as pd
from tika import parser as tika_parser
from dateutil import parser as dateparser

import db_manager
import config
import container_exploder
import os_manager

logger = logging.getLogger("ProcessorLogger")

# Conditional imports — availability flags
try:
    import win32com.client
    import pythoncom
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    import universal_imager
    IMAGER_AVAILABLE = True
except ImportError:
    IMAGER_AVAILABLE = False

TIKA_ENDPOINT = config.TIKA_ENDPOINT
TIKA_TIMEOUT = config.TIKA_TIMEOUT
OCR_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff']


# ── Utility Functions ───────────────────────────────────────────────────────

def _long_path(p):
    """On Windows, prefix absolute paths with \\\\?\\ to bypass the 260-char MAX_PATH limit."""
    if sys.platform != 'win32':
        return p
    if p and p.startswith('\\\\?\\'):
        p = p[4:]
    p = os.path.abspath(p)
    return '\\\\?\\' + p


def _strip_long_path_prefix(p):
    """Remove the \\\\?\\ extended-length prefix so paths are safe for DB storage and COM calls."""
    if p and p.startswith('\\\\?\\'):
        return p[4:]
    return p


def calculate_content_hash(text):
    if not text:
        return None
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sanitize_date(date_obj):
    if not date_obj:
        return None
    if isinstance(date_obj, list):
        date_obj = date_obj[0] if date_obj else None
    if not date_obj:
        return None
    try:
        if isinstance(date_obj, datetime):
            return date_obj.isoformat()
        return dateparser.parse(str(date_obj)).isoformat()
    except Exception:
        return None


class ThreadSafeSet:
    def __init__(self):
        self._set, self._lock = set(), threading.Lock()

    def __contains__(self, item):
        with self._lock:
            return item in self._set

    def add(self, item):
        with self._lock:
            self._set.add(item)

    def check_and_add(self, item):
        """Atomically check membership and add. Returns True if item was newly added,
        False if already present."""
        with self._lock:
            if item in self._set:
                return False
            self._set.add(item)
            return True


# ── Text Extraction ─────────────────────────────────────────────────────────

def _ocr_fallback(filepath):
    """
    Last-resort OCR using Tesseract via PyMuPDF rendering + pytesseract.
    Only called when PyMuPDF and Tika both return empty text for a file with pages.
    """
    try:
        import pytesseract
        from PIL import Image as PILImage
        import io
        tesseract_path = getattr(config, 'TESSERACT_PATH', r"C:\Tesseract-OCR\tesseract.exe")
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
    except ImportError:
        logger.warning("pytesseract or Pillow not installed — OCR fallback unavailable")
        return ""

    ext = os.path.splitext(filepath)[1].lower()
    ocr_pages = []

    try:
        if ext == '.pdf':
            doc = fitz.open(filepath)
            try:
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap(dpi=300)
                    mode = "RGBA" if pix.alpha else "RGB"
                    img = PILImage.frombytes(mode, [pix.width, pix.height], pix.samples)
                    page_text = pytesseract.image_to_string(img)
                    ocr_pages.append(page_text)
                    img.close()
                    del pix
            finally:
                doc.close()
        elif ext in OCR_EXTENSIONS:
            img = PILImage.open(filepath)
            page_text = pytesseract.image_to_string(img)
            ocr_pages.append(page_text)
            img.close()

        result = "\n".join(ocr_pages).strip()
        if result:
            logger.info(f"OCR recovered {len(result)} chars from {filepath}")
        return result
    except Exception as e:
        logger.warning(f"OCR fallback failed for {filepath}: {e}")
        return ""


def get_tika_data(filepath):
    """Extract text and metadata using PyMuPDF (PDF) → Tika → OCR fallback chain."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        doc = None
        try:
            doc = fitz.open(filepath)
            text = "\n".join(page.get_text() for page in doc)
            if text.strip():
                return text.strip(), {"extracted_with": "pymupdf"}
        except Exception as e:
            logger.warning(f"PyMuPDF failed for {filepath}: {e}")
        finally:
            if doc:
                try:
                    doc.close()
                except Exception:
                    pass

    tika_text = ""
    tika_metadata = {}
    attempts = 0
    last_error = None
    while attempts < 3:
        try:
            parsed = tika_parser.from_file(
                filepath,
                serverEndpoint=TIKA_ENDPOINT,
                headers={'X-Tika-Skip-Embedded': 'true'},
                requestOptions={'timeout': TIKA_TIMEOUT}
            )
            if not parsed:
                raise Exception("Tika returned None")
            content = parsed.get("content", "")
            tika_metadata = parsed.get("metadata", {})
            tika_text = content.strip() if content else ""
            if tika_text and os.path.splitext(filepath)[1].lower() in ('.eml', '.msg'):
                import re
                tika_text = re.sub(r'(?:[A-Za-z0-9+/]{40,}\s*){50,}', '\n[Embedded Base64 Data Removed]\n', tika_text)
                if len(tika_text) > 1500000:
                    tika_text = tika_text[:1500000] + "\n\n[TEXT TRUNCATED DUE TO EXCESSIVE LENGTH]"
            break
        except Exception as e:
            attempts += 1
            last_error = e
            time.sleep(1.0)

    if tika_text:
        return tika_text, tika_metadata

    if ext in OCR_EXTENSIONS:
        ocr_text = _ocr_fallback(filepath)
        if ocr_text:
            meta = tika_metadata if tika_metadata else {}
            meta["extracted_with"] = "tesseract_ocr"
            return ocr_text, meta

    if last_error:
        logger.error(f"Tika extraction completely failed for {filepath}: {last_error}")
        return "", {"Extraction-Error": str(last_error)}
    return "", tika_metadata


# ── Database Helpers ────────────────────────────────────────────────────────

# Container family-model classification.
# Email containers (.eml, .msg) DEFINE families — their direct children
# (typically attachments) inherit the email's group_id.
# Archive containers (.pst, .zip) DO NOT define families on their own —
# when an archive is at the top of its family (no email ancestor), its
# direct children each START a new family rooted at themselves. When an
# archive is nested inside an email family (e.g., a .zip attached to an
# email), the email's group_id propagates DOWN through the archive to
# the archive's children, preserving the email-rooted family.
# See docs/lessons/container-family-model.md for the full pattern.
ARCHIVE_EXTS = frozenset({'.pst', '.zip'})


def add_children_to_db(conn, parent_row, children, child_warnings=None):
    """
    Insert extracted child documents into the database.

    Args:
        child_warnings: Optional dict {logical_path: warning_str} from
            container extraction.
    """
    new_rows = []
    parent_id_str = f"DOC-{parent_row['id']:06d}"
    parent_ext = (parent_row['file_extension'] or '').lower()
    parent_is_archive = parent_ext in ARCHIVE_EXTS

    # Top-of-family detection: parent is at top of its family if it has no
    # group_id of its own (NULL/empty at extraction time before processing)
    # OR if its group_id is its own DOC-id form (self-rooted post-processing
    # or post-migration).
    _parent_gid = parent_row['group_id']
    parent_is_top_of_family = (not _parent_gid) or (_parent_gid == parent_id_str)

    # Top-level archive children start a new family. All other parents
    # (emails OR archives nested in an email family) propagate group_id.
    top_level_archive_parent = parent_is_archive and parent_is_top_of_family
    inherited_group_id = _parent_gid or parent_id_str

    child_warnings = child_warnings or {}

    for i, (child_name, child_physical_path, child_logical_path) in enumerate(children):
        child_physical_path = _strip_long_path_prefix(child_physical_path)
        try:
            child_ext = os.path.splitext(child_name)[1].lower()
            file_size = round(os.path.getsize(child_physical_path) / 1024, 2)
            with open(child_physical_path, 'rb') as _f:
                md5 = hashlib.md5(_f.read()).hexdigest()

            temp_control_number = f"{parent_id_str}.{i+1:03d}"
            custodian = parent_row['custodian']
            volume = parent_row['volume']
            record_type = "Attachment"
            if child_ext in ['.msg', '.eml']:
                record_type = "Email"

            ext_note = child_warnings.get(child_logical_path)

            # Initial group_id: NULL placeholder for top-level archive
            # children (filled post-INSERT once lastrowid is known); all
            # other children inherit the family from the parent chain.
            initial_group_id = None if top_level_archive_parent else inherited_group_id

            cur = conn.cursor()
            cur.execute("""  -- db_manager: exempt (processing loop)
                INSERT INTO documents (control_number, file_name, full_path, original_path, file_extension, file_size_kb, md5_hash, processing_status, parent_id, group_id, custodian, volume, record_type, extraction_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (temp_control_number, child_name, child_physical_path, child_logical_path, child_ext, file_size, md5, 'New', parent_id_str, initial_group_id, custodian, volume, record_type, ext_note))
            new_id = cur.lastrowid

            # Post-INSERT: top-level archive children get their own
            # DOC-id form as group_id (each child is its own family root).
            if top_level_archive_parent:
                own_group_id = f"DOC-{new_id:06d}"
                cur.execute("UPDATE documents SET group_id = ? WHERE id = ?", (own_group_id, new_id))  # db_manager: exempt (processing loop)

            conn.commit()

            new_row = conn.execute("SELECT * FROM documents WHERE id=?", (new_id,)).fetchone()  # db_manager: exempt (processing loop)
            new_rows.append(new_row)
        except sqlite3.IntegrityError:
            logger.warning(f"Child with MD5 {md5} likely already exists. Skipping insertion.")
        except Exception as e:
            logger.error(f"Failed to add child {child_name} to DB: {e}")

    return new_rows


def execute_bulk_update(conn, updates):
    """Batch SQL updates into a single transaction."""
    cursor = conn.cursor()
    sql_batches = {}
    for sql, params in updates:
        if sql not in sql_batches:
            sql_batches[sql] = []
        sql_batches[sql].append(params)

    try:
        conn.execute("BEGIN TRANSACTION")  # db_manager: exempt (batch transaction)
        for sql, param_list in sql_batches.items():
            cursor.executemany(sql, param_list)
        conn.commit()
    except Exception as e:
        logger.error(f"Bulk Commit Error: {e}")
        conn.rollback()


def generate_batch_report(case_folder, audit_path):
    """Generate processing audit CSV. Returns (report_path, suspicious_count)."""
    conn = db_manager.get_connection(case_folder)
    df = pd.read_sql_query("""
        SELECT control_number, file_name, processing_status, has_text, file_size_kb,
               md5_hash, content_hash, parent_id, group_id, custodian,
               email_from, email_subject, date_sent, record_type
        FROM documents
    """, conn)
    df['Suspicious_Zero_Text'] = ((df['file_size_kb'] > 50) & (df['has_text'] == 0))
    conn.close()

    report_name = f"Processing_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    report_path = os.path.join(audit_path, report_name)
    df.to_csv(report_path, index=False)

    suspicious_count = int(df['Suspicious_Zero_Text'].sum())
    logger.info(f"Generated report with {len(df)} documents. Found {suspicious_count} suspicious (large, no text) files.")
    return report_path, suspicious_count


# ── COM / Imaging Helpers ───────────────────────────────────────────────────

def com_worker(ext, source_path, dest_pdf_path, result_queue):
    """Worker function for COM-based Office-to-PDF conversion (runs in subprocess)."""
    import pythoncom
    import win32com.client
    try:
        pythoncom.CoInitialize()
        if ext in ['.doc', '.docx']:
            word = win32com.client.Dispatch("Word.Application")
            try:
                word.Visible = False
                doc = word.Documents.Open(os.path.abspath(source_path))
                doc.ExportAsFixedFormat(os.path.abspath(dest_pdf_path), 17)
                doc.Close()
            finally:
                word.Quit()
            result_queue.put(True)
        elif ext in ['.xls', '.xlsx']:
            excel = win32com.client.Dispatch("Excel.Application")
            try:
                excel.Visible = False
                wb = excel.Workbooks.Open(os.path.abspath(source_path))
                wb.ExportAsFixedFormat(0, os.path.abspath(dest_pdf_path))
                wb.Close()
            finally:
                excel.Quit()
            result_queue.put(True)
        elif ext in ['.ppt', '.pptx']:
            ppt = win32com.client.Dispatch("PowerPoint.Application")
            try:
                pres = ppt.Presentations.Open(os.path.abspath(source_path), WithWindow=False)
                pres.ExportAsFixedFormat(os.path.abspath(dest_pdf_path), 32)
                pres.Close()
            finally:
                ppt.Quit()
            result_queue.put(True)
        else:
            result_queue.put(False)
    except Exception as e:
        result_queue.put(e)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def image_to_pdf(source_path, dest_pdf_path, case_folder=None):
    """Convert Office documents to PDF via COM automation with timeout/retry."""
    if not WIN32_AVAILABLE:
        return False

    import multiprocessing
    ext = os.path.splitext(source_path)[1].lower()
    max_attempts = 3
    timeout_seconds = 60
    last_error = None
    for attempt in range(1, max_attempts + 1):
        result_queue = multiprocessing.Queue()

        p = multiprocessing.Process(target=com_worker, args=(ext, source_path, dest_pdf_path, result_queue))
        p.start()
        p.join(timeout_seconds)

        if p.is_alive():
            logger.error(f"COM imaging timeout for {source_path} (attempt {attempt}). Terminating process.")
            p.terminate()
            p.join()
            last_error = TimeoutError(f"COM imaging timeout for {source_path}")
            continue

        try:
            result = result_queue.get_nowait()
        except multiprocessing.queues.Empty:
            result = False

        if result is True:
            return True
        elif isinstance(result, Exception):
            last_error = result
            logger.error(f"Imaging Error for {source_path} (attempt {attempt}): {result}")
        else:
            last_error = Exception("Unknown COM imaging failure")

    logger.error(f"Imaging failed for {source_path} after {max_attempts} attempts: {last_error}")
    if case_folder and os.path.exists(source_path):
        try:
            conn = db_manager.get_connection(case_folder)
            conn.execute("UPDATE documents SET processing_status='Error' WHERE full_path=?", (source_path,))  # db_manager: exempt (processing loop)
            conn.commit()
            db_manager.log_audit(case_folder, "PROCESSING_ERROR",
                username='system', control_number="UNKNOWN", module="Processor",
                details=f"COM imaging failed after {max_attempts} attempts: {os.path.basename(source_path)}")
            conn.close()
        except Exception as e:
            logger.error(f"Failed to flag Processing Error in DB for {source_path}: {e}")
    return False


# ── Phase 2 Worker ──────────────────────────────────────────────────────────

def process_file_worker(row, index_name, os_host_args, update_queue,
                        seen_md5s, seen_content_hashes, processed_path):
    """
    Worker to process a single file: text extraction, metadata, dedup, OpenSearch queuing.
    Runs in ThreadPoolExecutor — no COM, no Streamlit.
    """
    doc_id_int = row['id']
    target_path = _long_path(row['full_path'])
    original_filename = row['file_name']

    try:
        _, ext = os.path.splitext(original_filename)
        ext = ext.lower()
        control_number = f"DOC-{doc_id_int:06d}"

        # Recover from interrupted previous runs
        if not os.path.exists(target_path) and "Temp_Explode" in row['full_path']:
            processed_candidate = _long_path(os.path.join(processed_path, f"{control_number}{ext}"))
            if os.path.exists(processed_candidate):
                logger.info(f"Recovered {control_number} from Processed/ (prior run moved it)")
                target_path = processed_candidate
            else:
                raise FileNotFoundError(
                    f"Source file missing from both Temp_Explode and Processed: {row['full_path']}"
                )
        group_id = row['group_id'] or control_number
        md5 = row['md5_hash']

        parent_id = row['parent_id']
        is_attachment = parent_id is not None and str(parent_id).strip() != ''

        if not is_attachment and not seen_md5s.check_and_add(md5):
            dupe_c_num = f"DUPE-{doc_id_int:06d}"
            update_queue.put(("UPDATE documents SET processing_status='Duplicate (MD5)', control_number=? WHERE id=?", (dupe_c_num, doc_id_int)))
            update_queue.put(("AUDIT_LOG", {
                "action": "DUPLICATE_MARKED", "username": None,
                "control_number": dupe_c_num, "module": "Processor",
                "details": None, "old_value": None, "new_value": "Duplicate (MD5)"
            }))
            if "Temp_Explode" in target_path and os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception as e:
                    logger.warning(f"Failed to delete duplicate file {target_path}: {e}")
            return
        if is_attachment:
            seen_md5s.add(md5)

        # 2. TEXT EXTRACTION & METADATA
        text = ""
        tika_meta = {}
        native_email_meta = {}

        if ext == '.msg':
            try:
                text, native_email_meta = universal_imager.extract_msg_text(target_path)
            except Exception as e:
                logger.warning(f"Native MSG text extraction failed for {target_path}: {e}")
        elif ext == '.eml':
            try:
                text, native_email_meta = universal_imager.extract_eml_metadata(target_path)
            except Exception as e:
                logger.warning(f"Native EML metadata extraction failed for {target_path}: {e}")

        if not text:
            text, tika_meta = get_tika_data(target_path)

        content_hash = calculate_content_hash(text)

        if content_hash and not is_attachment and not seen_content_hashes.check_and_add(content_hash):
            dupe_c_num = f"DUPE-{doc_id_int:06d}"
            update_queue.put(("UPDATE documents SET processing_status='Duplicate (Content)', control_number=?, content_hash=? WHERE id=?",
                               (dupe_c_num, content_hash, doc_id_int)))
            update_queue.put(("AUDIT_LOG", {
                "action": "DUPLICATE_MARKED", "username": None,
                "control_number": dupe_c_num, "module": "Processor",
                "details": "content_hash match", "old_value": None, "new_value": "Duplicate (Content)"
            }))
            if "Temp_Explode" in target_path and os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception as e:
                    logger.warning(f"Failed to delete content-duplicate file {target_path}: {e}")
            return
        if content_hash and is_attachment:
            seen_content_hashes.add(content_hash)

        auto_tags = row['tags'] or ""
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico'] and not is_attachment:
            try:
                size_kb = os.path.getsize(target_path) / 1024
                if size_kb < 30.0:
                    auto_tags = f"{auto_tags}Junk Image;"
                else:
                    from PIL import Image
                    with Image.open(target_path) as img:
                        if img.width <= 150 and img.height <= 150:
                            auto_tags = f"{auto_tags}Junk Image (<150px);"
            except Exception:
                pass
        if auto_tags == "":
            auto_tags = None

        def get_meta_str(keys):
            for k in keys:
                val = tika_meta.get(k)
                if val:
                    if isinstance(val, list):
                        flat = []
                        for item in val:
                            if isinstance(item, list):
                                flat.extend(str(i).strip() for i in item)
                            else:
                                flat.append(str(item).strip())
                        return "; ".join(flat)
                    return str(val).strip()
            return None

        meta = {
            'subject':      get_meta_str(["dc:subject", "subject", "Message:Subject"]),
            'from':         get_meta_str(["Message-From", "Message:From-Email", "creator", "Author", "Sender"]),
            'to':           get_meta_str(["Message-To", "Message:To-Email"]),
            'cc':           get_meta_str(["Message-Cc", "Message:CC-Email"]),
            'bcc':          get_meta_str(["Message-Bcc"]),
            'msg_id':       get_meta_str(["Message-ID", "identifier", "Message:Raw-Header:Message-ID"]),
            'in_reply_to':  get_meta_str(["In-Reply-To", "Message:Raw-Header:In-Reply-To"]),
            'references':   get_meta_str(["references", "Message:Raw-Header:References"]),
            'created':      sanitize_date(tika_meta.get("Creation-Date") or tika_meta.get("meta:creation-date") or tika_meta.get("dcterms:created")),
            'sent':         sanitize_date(tika_meta.get("dcterms:created")),
            'received':     sanitize_date(tika_meta.get("Message:Received-Date") or tika_meta.get("dcterms:modified")),
            'modified':     sanitize_date(tika_meta.get("Last-Modified") or tika_meta.get("Last-Save-Date") or tika_meta.get("dcterms:modified")),
            'language':     get_meta_str(["dc:language", "Content-Language", "language"]),
            'title':        get_meta_str(["dc:title", "title"]),
            'mime_type':    get_meta_str(["Content-Type"]),
            'creating_app': get_meta_str(["Application-Name", "Application-Version", "producer", "pdf:docinfo:producer"]),
            'is_encrypted': 1 if (tika_meta.get("pdf:encrypted") == "true" or tika_meta.get("pdf:encrypted") is True) else 0,
            'word_count':   None,
        }
        meta_author = get_meta_str(["Author", "creator"])

        _wc_raw = tika_meta.get("meta:word-count") or tika_meta.get("Word-Count")
        if isinstance(_wc_raw, list):
            _wc_raw = _wc_raw[0] if _wc_raw else None
        try:
            meta['word_count'] = int(str(_wc_raw).strip()) if _wc_raw else None
        except (ValueError, TypeError):
            meta['word_count'] = None

        if native_email_meta:
            for key in ['subject', 'from', 'to', 'cc', 'bcc', 'in_reply_to', 'references']:
                if native_email_meta.get(key):
                    meta[key] = native_email_meta[key]
            if native_email_meta.get('message_id'):
                meta['msg_id'] = native_email_meta['message_id']
            if native_email_meta.get('date_sent'):
                meta['sent'] = sanitize_date(native_email_meta['date_sent'])
            if native_email_meta.get('date_received'):
                meta['received'] = sanitize_date(native_email_meta['date_received'])
            meta_author = native_email_meta.get('from') or meta_author

        attachment_count = native_email_meta.get('attachment_count') if native_email_meta else None

        if native_email_meta:
            extraction_method = 'native_ole'
        elif tika_meta.get("extracted_with") == "pymupdf":
            extraction_method = 'pymupdf'
        elif tika_meta.get("extracted_with") == "tesseract_ocr":
            extraction_method = 'tesseract_ocr'
        else:
            extraction_method = 'tika'

        tika_metadata_json = json.dumps(tika_meta, default=str) if tika_meta else None

        _pg_raw = (tika_meta.get("xmpTPg:NPages") or tika_meta.get("meta:page-count")
                   or tika_meta.get("Page-Count") or tika_meta.get("pdf:docinfo:custom:NPages"))
        if isinstance(_pg_raw, list):
            _pg_raw = _pg_raw[0] if _pg_raw else None
        try:
            meta_page_count = int(str(_pg_raw).strip()) if _pg_raw else None
        except (ValueError, TypeError):
            meta_page_count = None

        # 3. OPENSEARCH AND DB UPDATE
        opensearch_id = control_number
        try:
            os_doc = {
                "_index": index_name,
                "_id": control_number,
                "_source": {
                    "file_name":     original_filename,
                    "control_number": control_number,
                    "path":          target_path,
                    "content":       text,
                    "group_id":      group_id,
                    "parent_id":     row['parent_id'],
                    "custodian":     row['custodian'],
                    "email_subject": meta['subject'],
                    "author":        meta_author,
                    "date":          meta['sent'] or meta['created'],
                    "email_from":    meta['from'],
                    "email_to":      meta['to'],
                    "email_cc":      meta['cc'],
                    "email_bcc":     meta['bcc'],
                    "file_extension": ext,
                    "record_type":   "Email" if ext in ['.msg', '.eml'] else "Document",
                    "date_sent":     meta['sent'],
                    "date_created":  meta['created'],
                    "date_received": meta.get('received'),
                    "date_modified": meta.get('modified'),
                    "file_size_kb":  row['file_size_kb'],
                    "page_count":    meta_page_count,
                    "title":         meta.get('title'),
                    "language":      meta.get('language'),
                    "importance":    native_email_meta.get('importance') if native_email_meta else None,
                    "has_text":      1 if text else 0,
                    "source_collection": (row["source_collection"] if row["source_collection"] is not None else ""),
                    "source_subcollection": (row["source_subcollection"] if row["source_subcollection"] is not None else ""),
                    "source_party":     row['source_party'] if row['source_party'] is not None else "Internal",
                    "production_volume": row['production_volume'] if row['production_volume'] is not None else "",
                    "production_category": row['production_category'] if row['production_category'] is not None else "",
                }
            }
            update_queue.put(("OPENSEARCH_DOC", os_doc))
        except Exception as es_err:
            logger.error(f"ES queuing failed for {control_number}: {es_err}")

        # Move file to Processed directory
        processed_filename = f"{control_number}{ext}"
        final_processed_path = _long_path(os.path.join(processed_path, processed_filename))
        db_processed_path = final_processed_path[4:] if final_processed_path.startswith('\\\\?\\') else final_processed_path

        if os.path.abspath(target_path) != os.path.abspath(final_processed_path):
            move_attempts = 0
            moved = False
            while move_attempts < 3 and not moved:
                try:
                    if ext == '.pdf' and IMAGER_AVAILABLE:
                        _flat_ok, _flat_err = universal_imager.flatten_pdf(
                            target_path, final_processed_path)
                        if not _flat_ok:
                            logger.warning(f"PDF flatten failed for {control_number}, "
                                           f"falling back to raw copy: {_flat_err}")
                            if "Temp_Explode" in target_path:
                                shutil.move(target_path, final_processed_path)
                            else:
                                shutil.copy2(target_path, final_processed_path)
                        else:
                            if "Temp_Explode" in target_path:
                                try:
                                    os.remove(target_path)
                                except OSError:
                                    pass
                        moved = True
                    elif "Temp_Explode" in target_path:
                        shutil.move(target_path, final_processed_path)
                        moved = True
                    else:
                        shutil.copy2(target_path, final_processed_path)
                        moved = True
                except PermissionError:
                    move_attempts += 1
                    time.sleep(0.5)
            if not moved:
                raise Exception(f"Failed to move file due to OS lock: {target_path}")

        new_record_type = "Email" if ext in ['.msg', '.eml'] else "Document"

        sql = """UPDATE documents SET
                    control_number=?,
                    group_id=?,
                    processing_status='Master',
                    has_text=?,
                    opensearch_id=?,
                    content_hash=?,
                    tags=?,
                    email_from=?,
                    email_to=?,
                    email_cc=?,
                    email_bcc=?,
                    email_subject=?,
                    date_sent=?,
                    date_created=?,
                    date_received=?,
                    date_modified=?,
                    author=?,
                    message_id=?,
                    in_reply_to=?,
                    references_list=?,
                    conversation_index=?,
                    conversation_topic=?,
                    full_path=?,
                    record_type=COALESCE(NULLIF(record_type, ''), ?),
                    page_count=COALESCE(page_count, ?),
                    language=COALESCE(language, ?),
                    title=?,
                    mime_type=?,
                    creating_application=?,
                    extraction_method=?,
                    is_encrypted=?,
                    word_count=?,
                    attachment_count=?,
                    importance=?,
                    sensitivity=?,
                    tika_metadata_json=?
                 WHERE id = ?"""
        params = (
            control_number, group_id, 1 if text else 0, opensearch_id, content_hash, auto_tags,
            meta['from'], meta['to'], meta['cc'], meta['bcc'], meta['subject'],
            meta['sent'], meta['created'],
            meta.get('received'),
            meta.get('modified'),
            meta_author, meta['msg_id'], meta['in_reply_to'],
            meta.get('references'),
            native_email_meta.get('conversation_index') if native_email_meta else None,
            native_email_meta.get('conversation_topic') if native_email_meta else None,
            db_processed_path, new_record_type, meta_page_count,
            meta.get('language'),
            meta.get('title'),
            meta.get('mime_type'),
            meta.get('creating_app'),
            extraction_method,
            meta.get('is_encrypted', 0),
            meta.get('word_count'),
            attachment_count,
            native_email_meta.get('importance') if native_email_meta else None,
            native_email_meta.get('sensitivity') if native_email_meta else None,
            tika_metadata_json,
            doc_id_int
        )
        update_queue.put((sql, params))
        update_queue.put(("AUDIT_LOG", {
            "action": "TEXT_EXTRACTED", "username": None,
            "control_number": control_number, "module": "Processor",
            "details": json.dumps({"method": extraction_method}), "old_value": None, "new_value": None
        }))

    except Exception as e:
        logger.error(f"Thread Error on {original_filename}: {e}", exc_info=True)
        update_queue.put(("UPDATE documents SET processing_status='Error' WHERE id=?", (doc_id_int,)))
        update_queue.put(("AUDIT_LOG", {
            "action": "PROCESSING_ERROR", "username": None,
            "control_number": f"DOC-{doc_id_int:06d}", "module": "Processor",
            "details": str(e)[:500], "old_value": None, "new_value": None
        }))


# ── Phase Orchestration ─────────────────────────────────────────────────────

def run_phase_1(case_folder, temp_path, username='system',
                on_progress=None, check_cancel=None):
    """
    Phase 1: Recursive container extraction.

    Args:
        on_progress: callback(phase, completed, total, message)
        check_cancel: callback() -> bool

    Returns:
        extraction_summary: list of dicts with PST extraction stats
    """
    if not os.path.exists(temp_path):
        os.makedirs(temp_path)

    conn = db_manager.get_connection(case_folder)
    total_found = 0
    extraction_summary = []
    PST_EXTRACTION_TIMEOUT = 300
    _seen_container_hashes = set()
    _max_extraction_passes = 50  # Circuit breaker — prevent infinite container nesting

    _pass_num = 0
    while True:
        _pass_num += 1
        if _pass_num > _max_extraction_passes:
            logger.error(f"Phase 1: Hit max extraction passes ({_max_extraction_passes}). Breaking loop.")
            break

        if check_cancel and check_cancel():
            break

        docs_to_scan = conn.execute("SELECT * FROM documents WHERE processing_status='New'").fetchall()  # db_manager: exempt (processing loop)
        if not docs_to_scan:
            break

        container_found_in_this_pass = False

        if on_progress:
            conn.commit()  # Release write lock before progress callback
            on_progress(1, _pass_num, 0, f"Phase 1: Pass {_pass_num} — {len(docs_to_scan):,} new documents...")

        # 0. De-NIST filtering
        NIST_EXTENSIONS = set(db_manager.get_nist_extensions(case_folder))
        nist_filtered = [d for d in docs_to_scan if (d['file_extension'] or '').lower() in NIST_EXTENSIONS]
        if nist_filtered:
            for nd in nist_filtered:
                conn.execute("UPDATE documents SET processing_status='NIST_Excluded', tags=COALESCE(tags || ', ', '') || 'NIST-Filtered' WHERE id=?", (nd['id'],))  # db_manager: exempt (processing loop)
            conn.commit()  # Release write lock BEFORE log_audit (separate conn)
            try:
                db_manager.log_audit(case_folder, "NIST_EXCLUDED",
                    username=username,
                    control_number="BULK",
                    module="Processor",
                    details=f"NIST-filtered {len(nist_filtered)} system files")
            except Exception:
                pass
            total_found += len(nist_filtered)
            logger.info(f"De-NIST: Excluded {len(nist_filtered)} system files")
            docs_to_scan = [d for d in docs_to_scan if d not in nist_filtered]
            if not docs_to_scan:
                break

        # 1. Separate container types
        msg_docs = [d for d in docs_to_scan if (d['file_extension'] or "").lower() == '.msg']
        pst_docs = [d for d in docs_to_scan if (d['file_extension'] or "").lower() == '.pst']
        other_container_docs = [d for d in docs_to_scan if (d['file_extension'] or "").lower() in ['.zip', '.eml']]
        standard_docs = [d for d in docs_to_scan if (d['file_extension'] or "").lower() not in ['.zip', '.eml', '.msg', '.pst']]

        # 2. Process MSG files in ONE true batch
        if msg_docs:
            msg_paths = [doc['full_path'] for doc in msg_docs]
            try:
                batch_results = container_exploder.process_msg_batch(msg_paths, temp_path)
            except TimeoutError as te:
                logger.error(f"MSG batch extraction timed out waiting for COM access: {te}")
                for doc_row in msg_docs:
                    conn.execute(
                        "UPDATE documents SET processing_status='Error_Timeout' WHERE id=?",
                        (doc_row['id'],)
                    )
                conn.commit()
                batch_results = {}

            for doc_row in msg_docs:
                doc_id = doc_row['id']
                doc_path = doc_row['full_path']
                children = batch_results.get(doc_path, [])

                if children == "ERROR":
                    conn.execute("UPDATE documents SET processing_status='Error' WHERE id=?", (doc_id,))  # db_manager: exempt (processing loop)
                    conn.commit()  # Release write lock before log_audit (separate conn)
                    try:
                        db_manager.log_audit(case_folder, "PROCESSING_ERROR",
                            username=username,
                            control_number=f"DOC-{doc_id:06d}",
                            module="Processor",
                            details=f"MSG batch extraction error: {doc_row['file_name']}")
                    except Exception:
                        pass
                else:
                    conn.execute("UPDATE documents SET processing_status='Container_Scanned' WHERE id=?", (doc_id,))  # db_manager: exempt (processing loop)
                    conn.commit()  # Release write lock before log_audit (separate conn)
                    try:
                        db_manager.log_audit(case_folder, "CONTAINER_SCANNED",
                            username=username,
                            control_number=f"DOC-{doc_id:06d}",
                            module="Processor",
                            details=f"MSG container scanned: {doc_row['file_name']}")
                    except Exception:
                        pass
                    if children:
                        container_found_in_this_pass = True
                        new_children = add_children_to_db(conn, doc_row, children)
                        total_found += len(new_children)

            conn.commit()

        # 3a. Process PSTs sequentially in isolated subprocesses
        if pst_docs:
            _log_path = os.path.join(
                os.path.join(case_folder, "Audit"),
                f"processing_{datetime.now().strftime('%Y%m%d')}.log"
            )
            for doc_row in pst_docs:
                if check_cancel and check_cancel():
                    break

                doc_id = doc_row['id']
                pst_name = doc_row['file_name']
                _container_hash = doc_row['md5_hash']
                if _container_hash and _container_hash in _seen_container_hashes:
                    logger.warning(f"Skipping duplicate container {pst_name} (MD5 {_container_hash} already extracted)")
                    conn.execute("UPDATE documents SET processing_status='Duplicate (MD5)' WHERE id=?", (doc_id,))  # db_manager: exempt (processing loop)
                    conn.commit()  # Release write lock before log_audit (separate conn)
                    try:
                        db_manager.log_audit(case_folder, "DUPLICATE_MARKED",
                            username=username,
                            control_number=f"DOC-{doc_id:06d}",
                            module="Processor",
                            details=f"Duplicate PST container (MD5): {pst_name}")
                    except Exception:
                        pass
                    continue
                if _container_hash:
                    _seen_container_hashes.add(_container_hash)

                if on_progress:
                    conn.commit()  # Release write lock before progress callback
                    on_progress(1, 0, 0, f"Phase 1: Extracting {pst_name}...")

                try:
                    result = container_exploder.explode_container(
                        doc_row['full_path'], temp_path, log_path=_log_path
                    )

                    if isinstance(result, dict):
                        children = result['children']
                        expected = result['expected_count']
                        extracted = result['extracted_count']
                        failed_folders = result['failed_folders']
                        child_warnings = result.get('child_warnings', {})
                        container_notes = result.get('container_notes')

                        extraction_summary.append({
                            'file_name': pst_name,
                            'doc_id': doc_id,
                            'expected': expected,
                            'extracted': extracted,
                            'failed_folders': failed_folders
                        })

                        _is_partial = bool(failed_folders) or (expected > 0 and extracted < expected)
                        if _is_partial:
                            conn.execute(
                                "UPDATE documents SET processing_status='Partial_Extraction' WHERE id=?",
                                (doc_id,)
                            )
                            logger.warning(
                                f"Partial extraction for {pst_name}: "
                                f"{extracted}/{expected} items extracted"
                                f"{' — failed folders: ' + str(failed_folders) if failed_folders else ''}"
                            )
                        else:
                            conn.execute(
                                "UPDATE documents SET processing_status='Container_Scanned' WHERE id=?",
                                (doc_id,)
                            )

                        if container_notes:
                            conn.execute(
                                "UPDATE documents SET extraction_notes=? WHERE id=?",
                                (container_notes, doc_id)
                            )

                        if children:
                            container_found_in_this_pass = True
                            new_children = add_children_to_db(conn, doc_row, children, child_warnings=child_warnings)
                            total_found += len(new_children)
                    else:
                        conn.execute(
                            "UPDATE documents SET processing_status='Container_Scanned' WHERE id=?",
                            (doc_id,)
                        )
                except RuntimeError as e:
                    if "timed out" in str(e).lower():
                        logger.error(f"PST extraction timeout for {pst_name}")
                        conn.execute(
                            "UPDATE documents SET processing_status='Error_Timeout' WHERE id=?",
                            (doc_id,)
                        )
                    else:
                        logger.error(f"PST extraction failed for {pst_name}: {e}")
                        conn.execute(
                            "UPDATE documents SET processing_status='Error' WHERE id=?",
                            (doc_id,)
                        )
                    conn.commit()  # Release write lock before log_audit (separate conn)
                    try:
                        db_manager.log_audit(case_folder, "PROCESSING_ERROR",
                            username=username,
                            control_number=f"DOC-{doc_id:06d}",
                            module="Processor",
                            details=f"PST extraction failed: {pst_name} — {str(e)[:200]}")
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"PST extraction failed for {pst_name}: {e}")
                    conn.execute(
                        "UPDATE documents SET processing_status='Error' WHERE id=?",
                        (doc_id,)
                    )
                    conn.commit()  # Release write lock before log_audit (separate conn)
                    try:
                        db_manager.log_audit(case_folder, "PROCESSING_ERROR",
                            username=username,
                            control_number=f"DOC-{doc_id:06d}",
                            module="Processor",
                            details=f"PST extraction error: {pst_name} — {str(e)[:200]}")
                    except Exception:
                        pass
            conn.commit()

        # 3b. Process ZIPs and EMLs using a ThreadPoolExecutor
        _fresh_containers = []
        _dup_container_names = []
        for _oc in other_container_docs:
            _oc_hash = _oc['md5_hash']
            if _oc_hash and _oc_hash in _seen_container_hashes:
                logger.warning(f"Skipping duplicate container {_oc['file_name']} (MD5 already extracted)")
                conn.execute("UPDATE documents SET processing_status='Duplicate (MD5)' WHERE id=?", (_oc['id'],))  # db_manager: exempt (processing loop)
                _dup_container_names.append(_oc['file_name'])
            else:
                if _oc_hash:
                    _seen_container_hashes.add(_oc_hash)
                _fresh_containers.append(_oc)
        other_container_docs = _fresh_containers
        conn.commit()  # Release write lock before log_audit (separate conn)
        if _dup_container_names:
            try:
                db_manager.log_audit(case_folder, "DUPLICATE_MARKED",
                    username=username,
                    control_number="BULK",
                    module="Processor",
                    details=f"Duplicate containers (MD5): {len(_dup_container_names)} skipped")
            except Exception:
                pass

        if other_container_docs:
            def _extract_other(doc_row):
                result = container_exploder.explode_container(doc_row['full_path'], temp_path)
                return doc_row, result

            with ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) + 4)) as executor:
                future_to_doc = {executor.submit(_extract_other, doc): doc for doc in other_container_docs}
                for future in as_completed(future_to_doc):
                    doc_row = future_to_doc[future]
                    doc_id = doc_row['id']
                    try:
                        _, result = future.result(timeout=PST_EXTRACTION_TIMEOUT)

                        if isinstance(result, dict):
                            children = result['children']
                        else:
                            children = result
                        conn.execute(
                            "UPDATE documents SET processing_status='Container_Scanned' WHERE id=?",
                            (doc_id,)
                        )

                        if children:
                            container_found_in_this_pass = True
                            new_children = add_children_to_db(conn, doc_row, children)
                            total_found += len(new_children)
                    except TimeoutError:
                        logger.error(f"Extraction timeout for {doc_row['file_name']} after {PST_EXTRACTION_TIMEOUT}s")
                        conn.execute(
                            "UPDATE documents SET processing_status='Error_Timeout' WHERE id=?",
                            (doc_id,)
                        )
                    except Exception as e:
                        logger.error(f"Error extracting {doc_row['file_name']}: {e}")
                        conn.execute("UPDATE documents SET processing_status='Error' WHERE id=?", (doc_id,))  # db_manager: exempt (processing loop)
            conn.commit()

        # 4. Mark non-containers as ready (bulk — no per-doc audit to avoid SQLite self-deadlock)
        for doc_row in standard_docs:
            conn.execute("UPDATE documents SET processing_status='Ready_For_Processing' WHERE id=?", (doc_row['id'],))  # db_manager: exempt (processing loop)
        conn.commit()  # Release write lock BEFORE log_audit (separate conn)
        if standard_docs:
            try:
                db_manager.log_audit(case_folder, "STATUS_CHANGED",
                    username=username,
                    control_number="BULK",
                    module="Processor",
                    details=f"Bulk status change: {len(standard_docs)} non-container docs set to Ready_For_Processing")
            except Exception:
                pass

        if container_found_in_this_pass:
            if on_progress:
                conn.commit()  # Release write lock before progress callback
                on_progress(1, total_found, 0, f"Phase 1: Pass {_pass_num} complete — {total_found:,} children found")

        if not container_found_in_this_pass:
            break

    # Final cleanup
    conn.execute("UPDATE documents SET processing_status='Ready_For_Processing' WHERE processing_status='New'")  # db_manager: exempt (processing loop)
    try:
        db_manager.log_audit(case_folder, "STATUS_CHANGED",
            username=username,
            control_number="BULK",
            module="Processor",
            details="Bulk status change: remaining 'New' docs set to Ready_For_Processing")
    except Exception:
        pass
    conn.execute("""  -- db_manager: exempt (processing loop)
        UPDATE documents
        SET processing_status = 'Ready_For_Processing'
        WHERE processing_status = 'Container_Scanned'
          AND LOWER(file_extension) IN ('.msg', '.eml')
    """)
    # Note: PST/ZIP containers stay Container_Scanned — they have no
    # extractable text content and must not enter Phase 2 or the Review grid.
    # The Container_Scanned status already excludes them from both.
    conn.commit()
    conn.close()
    return extraction_summary


def db_writer_worker(case_folder, update_queue, stop_event):
    """
    Background thread that consumes from update_queue and batches writes
    to SQLite and OpenSearch. Must run as daemon=True thread.
    """
    conn = db_manager.get_connection(case_folder)

    from opensearchpy import helpers
    local_os, _ = os_manager.get_os_client()
    os_batch = []

    def flush_os_batch():
        if not os_batch:
            return
        max_retries = 3
        for attempt in range(max_retries):
            try:
                helpers.bulk(local_os, os_batch, chunk_size=len(os_batch), max_chunk_bytes=10*1024*1024, request_timeout=60)
                os_batch.clear()
                return
            except Exception as os_e:
                reason = str(os_e)
                if hasattr(os_e, 'errors'):
                    error_reasons = []
                    for err in os_e.errors:
                        for op_type, info in err.items():
                            if 'error' in info:
                                doc_id = info.get('_id', 'unknown')
                                err_reason = info['error'].get('reason', str(info['error']))
                                error_reasons.append(f"Doc {doc_id}: {err_reason}")
                    if error_reasons:
                        reason = " | ".join(error_reasons[:5]) + ("..." if len(error_reasons) > 5 else "")

                logger.error(f"OpenSearch Bulk Writer Error (Attempt {attempt+1}): {reason}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                else:
                    failed_cns = [(doc.get('_source', {}).get('control_number'),) for doc in os_batch if doc.get('_source', {}).get('control_number')]
                    if failed_cns:
                        try:
                            conn.executemany("UPDATE documents SET processing_status='OS_Error' WHERE control_number=?", failed_cns)
                            conn.commit()
                        except Exception as db_err:
                            logger.error(f"Failed to flag OS_Error in DB: {db_err}")
                    os_batch.clear()

    while not stop_event.is_set() or not update_queue.empty():
        try:
            item = update_queue.get(timeout=0.2)
            batch = []
            audit_batch = []
            if item[0] == "OPENSEARCH_DOC":
                os_batch.append(item[1])
            elif item[0] == "AUDIT_LOG":
                audit_batch.append(item[1])
            else:
                batch.append(item)

            while len(batch) + len(os_batch) < 500 and not update_queue.empty():
                next_item = update_queue.get_nowait()
                if next_item[0] == "OPENSEARCH_DOC":
                    os_batch.append(next_item[1])
                elif next_item[0] == "AUDIT_LOG":
                    audit_batch.append(next_item[1])
                else:
                    batch.append(next_item)

            # CRIT-3: Flush OpenSearch BEFORE writing the SQLite Master status.
            if len(os_batch) >= 25 or (stop_event.is_set() and os_batch):
                flush_os_batch()

            if batch:
                execute_bulk_update(conn, batch)
            if audit_batch:
                db_manager.log_audit_batch(case_folder, audit_batch)
        except queue.Empty:
            if stop_event.is_set() and os_batch:
                flush_os_batch()
            if stop_event.is_set() and not os_batch:
                break
            continue
        except Exception as e:
            logger.error(f"DB/ES Writer Error: {e}")
    conn.close()


def run_phase_2(case_folder, processed_path, max_threads, username='system',
                on_progress=None, check_cancel=None):
    """
    Phase 2: Parallel text extraction + OpenSearch indexing.

    Args:
        on_progress: callback(phase, completed, total, message)
        check_cancel: callback() -> bool

    Returns:
        (completed_count, total_count, errors_list, was_cancelled)
    """
    conn = db_manager.get_connection(case_folder)
    docs_to_process = conn.execute("SELECT * FROM documents WHERE processing_status = 'Ready_For_Processing'").fetchall()  # db_manager: exempt (processing loop)
    conn.close()

    if not docs_to_process:
        return 0, 0, [], False

    total_docs_to_process = len(docs_to_process)

    db_manager.log_audit(case_folder, "PROCESSING_STARTED", username=username,
        module="Processor", details=json.dumps({"phase": 2, "doc_count": total_docs_to_process}))

    index_name = os_manager.get_index_name(case_folder)
    os_args = os_manager.get_os_args()

    update_queue_obj = queue.Queue()
    stop_event = threading.Event()
    writer_thread = threading.Thread(
        target=db_writer_worker,
        args=(case_folder, update_queue_obj, stop_event),
        daemon=True
    )
    writer_thread.start()

    # Pre-seed dedup sets
    seen_md5s = ThreadSafeSet()
    _seed_conn = db_manager.get_connection(case_folder)
    _seed_hashes = _seed_conn.execute(
        "SELECT DISTINCT md5_hash FROM documents WHERE processing_status IN ('Processed', 'Master') AND md5_hash IS NOT NULL"
    ).fetchall()
    _seed_conn.close()
    for _h in _seed_hashes:
        seen_md5s.add(_h['md5_hash'])
    if _seed_hashes:
        logger.info(f"Pre-seeded {len(_seed_hashes)} MD5 hashes from prior processing runs")

    seen_content_hashes = ThreadSafeSet()
    _seed_conn2 = db_manager.get_connection(case_folder)
    _seed_chashes = _seed_conn2.execute(
        "SELECT DISTINCT content_hash FROM documents WHERE processing_status IN ('Processed', 'Master') AND content_hash IS NOT NULL"
    ).fetchall()
    _seed_conn2.close()
    for _ch in _seed_chashes:
        seen_content_hashes.add(_ch['content_hash'])
    if _seed_chashes:
        logger.info(f"Pre-seeded {len(_seed_chashes)} content hashes from prior processing runs")

    _was_cancelled = False
    completed = 0
    thread_errors = []

    try:
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_doc = {
                executor.submit(
                    process_file_worker, doc, index_name, os_args,
                    update_queue_obj, seen_md5s, seen_content_hashes, processed_path
                ): doc for doc in docs_to_process
            }

            for future in as_completed(future_to_doc):
                if check_cancel and check_cancel():
                    _was_cancelled = True
                    for f in future_to_doc:
                        f.cancel()
                    db_manager.log_audit(case_folder, "PROCESSING_CANCELLED", username=username,
                        module="Processor", details=f"Cancelled after {completed}/{total_docs_to_process} documents")
                    break

                completed += 1
                try:
                    future.result()
                except Exception as worker_exc:
                    failed_doc = future_to_doc[future]
                    failed_cn = failed_doc.get('control_number', 'unknown')
                    thread_errors.append(f"{failed_cn}: {worker_exc}")
                    db_manager.log_audit(case_folder, "PROCESSING_ERROR",
                        username=username,
                        control_number=failed_cn,
                        module="Processor",
                        details=f"Worker thread exception: {worker_exc}")

                # Report progress every 50 docs (batched to reduce DB writes)
                if on_progress and (completed % 50 == 0 or completed == total_docs_to_process):
                    on_progress(2, completed, total_docs_to_process,
                                f"Phase 2: Processed {completed}/{total_docs_to_process}")
    finally:
        # Drain writer thread
        stop_event.set()
        drain_start = time.time()
        drain_timeout = 120
        while writer_thread.is_alive() and (time.time() - drain_start) < drain_timeout:
            remaining = update_queue_obj.qsize()
            if remaining > 0 and on_progress:
                elapsed = int(time.time() - drain_start)
                on_progress(2, completed, total_docs_to_process,
                            f"Flushing {remaining:,} queued updates to DB/OpenSearch... ({elapsed}s)")
            time.sleep(1.0)
        writer_thread.join(timeout=5.0)
        if writer_thread.is_alive():
            logger.error("Writer thread hung on exit after drain timeout. Performing emergency flush.")

        # Emergency flush
        orphan_sql = []
        while not update_queue_obj.empty():
            try:
                item = update_queue_obj.get_nowait()
                if item[0] != "OPENSEARCH_DOC":
                    orphan_sql.append(item)
            except queue.Empty:
                break
        if orphan_sql:
            logger.warning(f"Emergency flush: writing {len(orphan_sql)} orphaned DB updates.")
            try:
                emergency_conn = db_manager.get_connection(case_folder)
                execute_bulk_update(emergency_conn, orphan_sql)
                emergency_conn.close()
            except Exception as e:
                logger.error(f"Emergency flush failed: {e}")

    # Clean up Temp_Explode
    temp_path = os.path.join(case_folder, "Temp_Explode")
    if os.path.exists(temp_path):
        for root, dirs, files in os.walk(temp_path, topdown=False):
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass

    return completed, total_docs_to_process, thread_errors, _was_cancelled


def run_phase_3(case_folder, processed_path, username='system',
                on_progress=None, check_cancel=None):
    """
    Phase 3: Email imaging — convert .msg/.eml to PDF for review.

    Args:
        on_progress: callback(phase, completed, total, message)
        check_cancel: callback() -> bool

    Returns:
        (success_count, fail_count, total_count)
    """
    conn_img = db_manager.get_connection(case_folder)
    emails_to_image = conn_img.execute("""  -- db_manager: exempt (processing loop)
        SELECT id, control_number, full_path, file_extension
        FROM documents
        WHERE processing_status = 'Master'
        AND file_extension IN ('.msg', '.eml')
        AND (source_party = 'Internal' OR source_party IS NULL)
    """).fetchall()
    conn_img.close()

    if not emails_to_image:
        return 0, 0, 0

    img_total = len(emails_to_image)
    img_success = 0
    img_fail = 0

    for idx, email_row in enumerate(emails_to_image):
        if check_cancel and check_cancel():
            break

        ctrl_num = email_row['control_number']
        email_source = email_row['full_path']
        pdf_dest = os.path.join(processed_path, f"{ctrl_num}.pdf")

        if os.path.exists(pdf_dest):
            img_success += 1
            continue

        if on_progress:
            on_progress(3, idx + 1, img_total, f"Phase 3: Imaging email {idx+1}/{img_total} — {ctrl_num}")

        try:
            if IMAGER_AVAILABLE:
                success, err = universal_imager.image_document(email_source, pdf_dest)
                if success:
                    img_success += 1
                    db_manager.log_audit(case_folder, "DOCUMENT_IMAGED",
                        username=username, control_number=ctrl_num, module="Processor")
                else:
                    img_fail += 1
                    logger.warning(f"Email imaging failed for {ctrl_num}: {err}")
            else:
                img_fail += 1
                logger.warning(f"Universal imager not available, cannot image {ctrl_num}")
        except Exception as img_e:
            img_fail += 1
            logger.error(f"Email imaging error for {ctrl_num}: {img_e}")

    return img_success, img_fail, img_total


# ── Logger Setup ────────────────────────────────────────────────────────────

def setup_logger(folder_path):
    """Initialize rotating file logger for processing. Returns logger instance."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    proc_logger = logging.getLogger("ProcessorLogger")
    proc_logger.setLevel(logging.INFO)
    if proc_logger.hasHandlers():
        proc_logger.handlers.clear()

    if not proc_logger.handlers:
        from logging.handlers import RotatingFileHandler
        log_path = os.path.join(folder_path, "processing_log.txt")
        try:
            fh = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5)
            fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            proc_logger.addHandler(fh)
        except Exception as e:
            # Log to stderr if file logger fails (locked by another process)
            logging.warning(f"Could not initialize file logger (likely locked): {e}")

        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        proc_logger.addHandler(sh)

    return proc_logger
