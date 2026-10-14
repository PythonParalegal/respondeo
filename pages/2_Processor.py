# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        2_Processor.py
# version:       2.0.4
# project:       Respondeo eDiscovery Platform
# project_ver:   2.12.0
# last_modified: 2026-04-28 11:45
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
import auth_manager
import os
import json
import time
import logging
import pandas as pd
from datetime import datetime
import db_manager
import config
import container_exploder
import sys
import os_manager
import ui_utils
import processing_engine
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Re-export from processing_engine for local use
_strip_long_path_prefix = processing_engine._strip_long_path_prefix
IMAGER_AVAILABLE = processing_engine.IMAGER_AVAILABLE

st.set_page_config(page_title="Respondeo | Processor", layout="wide", page_icon=str(_ASSETS / "favicon.png"))
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()

if not auth_manager.check_login(): st.stop()
# permission: process
auth_manager.require_permission('process')
auth_manager.show_user_info()

# --- CONFIGURATION (from config.py) ---
TIKA_ENDPOINT = config.TIKA_ENDPOINT
TIKA_TIMEOUT = config.TIKA_TIMEOUT

case_folder = st.session_state.get('current_case_folder')
if not case_folder:
    st.error("Please select a case in 'Home' first!")
    st.stop()


# --- CASE LIFECYCLE GATE ---


_case_status = db_manager.get_case_status(case_folder)
if _case_status == 'Closed':
    st.warning('🔒 This matter is closed. Write operations are disabled.')
    st.stop()

ingest_path = os.path.join(case_folder, "Ingest")
processed_path = os.path.join(case_folder, "Processed")
audit_path = os.path.join(case_folder, "Audit")
temp_path = os.path.join(case_folder, "Temp_Explode")

if not os.path.exists(processed_path):
    os.makedirs(processed_path)

# Ensure old handlers are closed if the case changed
if 'last_case_for_logger' in st.session_state and st.session_state['last_case_for_logger'] != case_folder:
    old_logger = logging.getLogger("ProcessorLogger")
    for handler in old_logger.handlers[:]:
        handler.close()
        old_logger.removeHandler(handler)

st.session_state['last_case_for_logger'] = case_folder
logger = processing_engine.setup_logger(audit_path)
        
st.sidebar.header("⚙️ Performance")
max_threads = st.sidebar.slider("Worker Threads", min_value=1, max_value=max(1, (os.cpu_count() or 4) - 1), value=min(4, max(1, (os.cpu_count() or 4) - 1)))
st.sidebar.markdown(f"**Selected Threads:** {max_threads}")

# --- OPENSEARCH CONNECTION ---
os_connected = False
os_client = None

os_client, os_msg = os_manager.get_os_client()
if os_client:
    os_connected = True
    if auth_manager.get_user_role() == 'admin':
        st.sidebar.success("✅ OpenSearch Connected")
else:
    st.sidebar.error(f"❌ OpenSearch Error: {os_msg}")

# --- HELPERS (processing logic in processing_engine.py) ---

def _show_scanpst_option(case_folder, pst_problems):
    """Show ScanPST repair option for PSTs with extraction issues."""
    scanpst_path = container_exploder.find_scanpst()

    if scanpst_path:
        st.divider()
        st.caption(
            "**PST Repair Tool:** If a PST file is damaged, Microsoft's ScanPST "
            "tool can often repair it. Repair the file, then re-extract above."
        )
        for pc in pst_problems:
            conn = db_manager.get_connection(case_folder)
            pst_row = conn.execute(  # db_manager: exempt (processing loop)
                "SELECT full_path FROM documents WHERE id=?", (pc['id'],)
            ).fetchone()
            conn.close()

            if pst_row:
                scan_key = f"scanpst_{pc['id']}"
                if st.button(f"Repair {pc['file_name']} with ScanPST", key=scan_key):
                    try:
                        import subprocess
                        pst_path = _strip_long_path_prefix(pst_row['full_path'])
                        subprocess.Popen([scanpst_path, pst_path])
                        st.info(
                            f"ScanPST opened for **{pc['file_name']}**. "
                            f"Complete the repair in the Microsoft tool, then click "
                            f"**Re-Extract** above."
                        )
                    except Exception as e:
                        st.error(f"Failed to launch ScanPST: {e}")
    else:
        st.caption(
            "If a PST is damaged, Microsoft's ScanPST.exe tool can repair it. "
            "It ships with Office but was not found on this machine. Check your "
            "Office installation directory."
        )


def re_extract_container(case_folder, doc_id):
    """
    Atomically re-extract a container (PST) by deleting all its children
    and resetting its status to 'New'. On the next processing run, it will
    re-enter Phase 1 naturally.

    Steps:
    1. Find all children (parent_id matches this doc's control number)
    2. Delete their OpenSearch entries
    3. Delete their physical extracted files
    4. Delete their DB rows (recursively for grandchildren)
    5. Reset the container's status to 'New'
    """
    conn = db_manager.get_connection(case_folder)
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()  # db_manager: exempt (processing loop)
        if not doc:
            logger.error(f"Re-extract: doc_id {doc_id} not found")
            return False, "Document not found"

        parent_id_str = f"DOC-{doc_id:06d}"

        # Set up OpenSearch client once for all deletions
        index_name = os_manager.get_index_name(case_folder)
        os_client = None
        try:
            os_client, _ = os_manager.get_os_client()
        except Exception as e:
            logger.warning(f"Re-extract: OpenSearch client unavailable — {e}")

        def _delete_descendants(pid_str):
            """Recursively delete all descendants of a document."""
            descendants = conn.execute(  # db_manager: exempt (processing loop)
                "SELECT id, control_number, full_path FROM documents WHERE parent_id=?",
                (pid_str,)
            ).fetchall()
            for desc in descendants:
                desc_parent_str = f"DOC-{desc['id']:06d}"
                _delete_descendants(desc_parent_str)  # Recurse first
                # Delete OpenSearch entry
                if os_client:
                    try:
                        os_client.delete(index=index_name, id=desc['control_number'], ignore=[404])
                    except Exception:
                        pass
                # Delete physical file
                if desc['full_path'] and os.path.exists(desc['full_path']):
                    try:
                        os.remove(desc['full_path'])
                    except Exception:
                        pass
                # Delete processed PDF
                processed_dir = os.path.join(case_folder, "Processed")
                if desc['control_number']:
                    pdf_path = os.path.join(processed_dir, f"{desc['control_number']}.pdf")
                    if os.path.exists(pdf_path):
                        try:
                            os.remove(pdf_path)
                        except Exception:
                            pass
                # Delete DB row
                conn.execute("DELETE FROM documents WHERE id=?", (desc['id'],))  # db_manager: exempt (processing loop)
                try:
                    db_manager.log_audit(case_folder, "CONTAINER_CHILD_DELETED",
                        username=st.session_state.get('username', 'system'),
                        control_number=desc['control_number'] or f"DOC-{desc['id']:06d}",
                        module="Processor",
                        details=f"Descendant deleted during re-extract of {parent_id_str}", conn=conn)
                except Exception:
                    pass

        # Get direct children
        children = conn.execute(  # db_manager: exempt (processing loop)
            "SELECT id, control_number, full_path FROM documents WHERE parent_id=?",
            (parent_id_str,)
        ).fetchall()

        # Delete direct children and all their descendants
        for child in children:
            child_parent_str = f"DOC-{child['id']:06d}"
            _delete_descendants(child_parent_str)
            # Delete OpenSearch entry for the direct child
            if os_client:
                try:
                    os_client.delete(index=index_name, id=child['control_number'], ignore=[404])
                except Exception:
                    pass
            # Delete physical file for the direct child
            if child['full_path'] and os.path.exists(child['full_path']):
                try:
                    os.remove(child['full_path'])
                except Exception:
                    pass
            if child['control_number']:
                processed_dir = os.path.join(case_folder, "Processed")
                pdf_path = os.path.join(processed_dir, f"{child['control_number']}.pdf")
                if os.path.exists(pdf_path):
                    try:
                        os.remove(pdf_path)
                    except Exception:
                        pass

        # Delete the direct children DB rows
        conn.execute("DELETE FROM documents WHERE parent_id=?", (parent_id_str,))  # db_manager: exempt (processing loop)
        try:
            db_manager.log_audit(case_folder, "CONTAINER_CHILDREN_DELETED",
                username=st.session_state.get('username', 'system'),
                control_number=doc['control_number'] or f"DOC-{doc_id:06d}",
                module="Processor",
                details=f"Deleted {len(children)} direct children of {parent_id_str}", conn=conn)
        except Exception:
            pass

        # Reset container status
        conn.execute(  # db_manager: exempt (processing loop)
            "UPDATE documents SET processing_status='New' WHERE id=?",
            (doc_id,)
        )
        conn.commit()

        logger.info(
            f"Re-extract: Reset {doc['file_name']} (id={doc_id}), "
            f"deleted {len(children)} direct children"
        )
        db_manager.log_audit(case_folder, "CONTAINER_RE_EXTRACT",
            username=st.session_state.get('username', 'unknown'),
            control_number=doc['control_number'],
            module="Processor",
            details=json.dumps({
                'file_name': doc['file_name'],
                'children_deleted': len(children)
            })
        )
        return True, f"Reset {doc['file_name']} — {len(children)} children removed"
    except Exception as e:
        logger.error(f"Re-extract failed for doc_id {doc_id}: {e}")
        return False, str(e)
    finally:
        conn.close()


# Processing functions (recursively_extract_all, com_worker, image_to_pdf,
# process_file_worker, etc.) have been extracted to processing_engine.py.


# ---------------------------------------------------------------------------
# Processing Log Viewer
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _read_log_lines(file_path: str, mtime: float) -> list:
    """Read all lines from a log file. mtime arg busts cache when file changes."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def _discover_log_files(log_dir: str) -> list:
    """Return [{path, label, mtime}] sorted newest-first for up to 6 log files."""
    names = [("processing_log.txt", "Current Log")]
    for i in range(1, 6):
        names.append((f"processing_log.txt.{i}", f"Backup {i}"))
    found = []
    for fname, friendly in names:
        path = os.path.join(log_dir, fname)
        if os.path.exists(path):
            stat = os.stat(path)
            size_mb = stat.st_size / (1024 * 1024)
            mtime_dt = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            found.append({
                "path": path,
                "fname": fname,
                "label": f"{friendly} ({fname}) — {size_mb:.1f} MB  ·  {mtime_dt}",
                "mtime": stat.st_mtime,
            })
    return sorted(found, key=lambda x: -x["mtime"])


def _render_log_viewer(log_dir: str):
    log_files = _discover_log_files(log_dir)

    with st.expander("📋 Processing Logs", expanded=False):
        if not log_files:
            st.info("No processing logs found for this case.")
            return

        # ── File selector ────────────────────────────────────────────────────
        selected_label = st.selectbox(
            "Log file",
            options=[lf["label"] for lf in log_files],
            index=0,
            key="log_viewer_file_select",
            label_visibility="collapsed",
        )
        selected = next(lf for lf in log_files if lf["label"] == selected_label)

        # ── Filter controls ──────────────────────────────────────────────────
        col_filter, col_search = st.columns([1, 2])
        with col_filter:
            level_filter = st.radio(
                "Level",
                options=["Errors Only", "Warnings & Errors", "All"],
                index=0,
                horizontal=True,
                key="log_viewer_level",
            )
        with col_search:
            search_term = st.text_input(
                "Filter by filename or control number",
                placeholder="e.g. DOC-000042  or  contract.pdf",
                key="log_viewer_search",
            )

        # ── Read & filter ────────────────────────────────────────────────────
        all_lines = _read_log_lines(selected["path"], selected["mtime"])

        # Reverse so newest lines come first
        lines = list(reversed(all_lines))

        if level_filter == "Errors Only":
            lines = [l for l in lines if " - ERROR - " in l]
        elif level_filter == "Warnings & Errors":
            lines = [l for l in lines if " - ERROR - " in l or " - WARNING - " in l]

        if search_term:
            term_lower = search_term.lower()
            lines = [l for l in lines if term_lower in l.lower()]

        total_matching = len(lines)
        display_lines = lines[:500]

        # ── Display ──────────────────────────────────────────────────────────
        st.caption(
            f"Showing {len(display_lines):,} of {total_matching:,} matching lines "
            f"(newest first){' — truncated to 500' if total_matching > 500 else ''}"
        )

        if display_lines:
            st.code("".join(display_lines), language=None)
        else:
            st.info("No lines match the current filter.")

        # ── Download ─────────────────────────────────────────────────────────
        with open(selected["path"], "rb") as f:
            st.download_button(
                label=f"⬇️ Download {selected['fname']}",
                data=f,
                file_name=selected["fname"],
                mime="text/plain",
                key="log_viewer_download",
            )


def _show_job_monitor(job, case_folder):
    """Display the progress monitor for a running background job."""
    st.caption("Processing is running in the background. You can close this tab — processing will continue.")

    phase_colors = {0: "#888", 1: "#4dabf7", 2: "#51cf66", 3: "#845ef7"}
    phase = job.get('phase') or 0
    color = phase_colors.get(phase, "#888")
    label = job.get('phase_label') or 'Starting...'
    progress = job.get('progress') or 0
    total = job.get('total') or 1
    status = job.get('status') or 'running'

    st.markdown(
        f"<div style='background:rgba(255,255,255,0.05);border-left:4px solid {color};"
        f"border-radius:6px;padding:8px 14px;margin:8px 0'>"
        f"<b style='color:{color}'>Phase {phase}</b> — {label}</div>",
        unsafe_allow_html=True
    )

    if total > 0:
        st.progress(min(1.0, progress / total))
        st.text(f"{progress:,} / {total:,} — Status: {status}")
    else:
        # Phase 1: total unknown (recursive extraction) — show indeterminate
        st.progress(0)
        st.text(f"Status: {status}")

    # Show recent warnings from details_json
    details_raw = job.get('details_json')
    if details_raw:
        try:
            details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
            warnings = details.get('recent_warnings', [])
            if warnings:
                with st.expander(f"⚠️ Recent warnings ({len(warnings)})"):
                    for w in warnings:
                        st.text(w)
        except (json.JSONDecodeError, TypeError):
            pass

    if status in ('running', 'pending'):
        if st.button("⛔ Cancel Processing", key="cancel_bg_job"):
            db_manager.cancel_job(case_folder, job['id'])
            st.warning("Cancel requested — waiting for worker to finish current item...")
            st.rerun()

    if status == 'cancelling':
        st.warning("⛔ Cancellation in progress — waiting for worker to finish current item...")

    # Auto-refresh every 2 seconds
    time.sleep(2)
    st.rerun()


def _show_job_result(job):
    """Show completion banner for a recently finished background job."""
    status = job.get('status', '')
    details_raw = job.get('details_json')
    details = {}
    if details_raw:
        try:
            details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
        except (json.JSONDecodeError, TypeError):
            pass

    if status == 'completed':
        p2_total = details.get('phase2_total', 0)
        img_ok = details.get('phase3_imaged', 0)
        img_fail = details.get('phase3_failed', 0)
        suspicious = details.get('suspicious_count', 0)
        st.success(f"✅ Background processing completed: {p2_total:,} docs processed, "
                   f"{img_ok} emails imaged, {suspicious} suspicious files.")
        if img_fail > 0:
            st.warning(f"📧 {img_fail} email(s) failed imaging.")
        report_path = details.get('report_path')
        if report_path and os.path.exists(report_path):
            with open(report_path, "rb") as f:
                st.download_button(
                    label="📥 Download Processing Audit (CSV)",
                    data=f,
                    file_name=os.path.basename(report_path),
                    mime="text/csv",
                    key="bg_report_download"
                )
    elif status == 'failed':
        error_msg = job.get('error', 'Unknown error')
        st.error(f"❌ Background processing failed: {error_msg}")
    elif status == 'cancelled':
        p2_completed = details.get('phase2_completed', 0)
        p2_total = details.get('phase2_total', 0)
        st.warning(f"⛔ Processing was cancelled ({p2_completed}/{p2_total} docs completed). "
                   f"Resume by launching processing again.")


def main():
    import subprocess as _sp

    st.title("Module 2: Document Processor ⚡")

    # ── Background Job Detection (before any other UI) ────────────────────
    db_manager.cleanup_stale_jobs(case_folder)
    _active_job = db_manager.get_active_job(case_folder, 'processing')
    if _active_job:
        _show_job_monitor(_active_job, case_folder)
        st.stop()  # Prevent any further rendering below

    st.caption(
        "Three-phase processing pipeline: container extraction → parallel text & metadata extraction "
        "(multi-threaded Tika + PyMuPDF) → OpenSearch indexing & email imaging."
    )

    if not os_connected:
        st.error("❌ OpenSearch must be running before processing. Start it from the Home page.")
        return

    # Check for recently completed job to show results
    _last_job = db_manager.get_last_completed_job(case_folder, 'processing')
    if _last_job and _last_job['status'] in ('completed', 'failed', 'cancelled'):
        _show_job_result(_last_job)

    # One-time migration: fix orphaned Container_Scanned PST/ZIP + strip \\?\ prefixes from prior runs
    _fix_conn = db_manager.get_connection(case_folder)
    _fix_conn.execute("""  -- db_manager: exempt (fix-up query)
        UPDATE documents
        SET processing_status = 'Processed'
        WHERE processing_status = 'Container_Scanned'
          AND LOWER(file_extension) IN ('.pst', '.zip')
    """)
    _fix_conn.execute(r"""  -- db_manager: exempt (fix-up query)
        UPDATE documents
        SET full_path = SUBSTR(full_path, 5)
        WHERE full_path LIKE '\\?\%'
    """)
    _fix_conn.commit()
    _fix_conn.close()

    _status = db_manager.get_document_status_counts(case_folder)
    _queue = db_manager.get_processing_queue_stats(case_folder)
    type_rows = db_manager.get_file_type_breakdown(case_folder)

    initial_queue_count = _queue['queue_count']
    _new_count          = _queue['new_count']
    _resumed_count      = _queue['resumed_count']
    already_processed   = _status['processed']
    duplicate_count     = _status['duplicate_md5']
    error_count         = _status['error_or_partial']
    total_count         = _status['total']
    container_count     = _queue['container_count']

    # ── Top Metrics ─────────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    p_m1, p_m2, p_m3, p_m4, p_m5 = m1.empty(), m2.empty(), m3.empty(), m4.empty(), m5.empty()
    
    def _draw_metrics(t, q, p, d, e):
        p_m1.metric("Total Ingested", f"{t:,}")
        p_m2.metric("⏳ In Queue", f"{q:,}")
        p_m3.metric("✅ Processed", f"{p:,}")
        p_m4.metric("📋 Duplicates", f"{d:,}")
        p_m5.metric("❌ Errors", f"{e:,}", delta="⚠️ Retry available" if e > 0 else None, delta_color="inverse" if e > 0 else "off")
        
    _draw_metrics(total_count, initial_queue_count, already_processed, duplicate_count, error_count)

    if error_count > 0:
        if st.button("🔄 Retry Failed Documents", key="retry_failed_docs_btn"):
            db_manager.retry_processing_errors(case_folder)
            try:
                db_manager.log_audit(case_folder, "PROCESSING_RETRY",
                    username=st.session_state.get('username', 'system'),
                    control_number="BULK",
                    module="Processor",
                    details=f"Retry: {error_count} failed documents reset to 'New' for reprocessing")
            except Exception:
                pass
            st.success("Failed docs reset to 'New'. Re-run the processor to retry.")
            st.rerun()

    # ── Processing Exception Report ─────────────────────────────────────────
    _nist_count = _status['nist_excluded']
    _encrypted_count = _status['is_encrypted_count']
    _partial_count = _status['partial']

    _exc_total = error_count + _nist_count + _encrypted_count + _partial_count
    st.markdown("### 📋 Processing Exception Report")
    if _exc_total > 0:
        _exc_m1, _exc_m2, _exc_m3, _exc_m4 = st.columns(4)
        _exc_m1.metric("Errors", f"{error_count:,}")
        _exc_m2.metric("NIST Excluded", f"{_nist_count:,}")
        _exc_m3.metric("Encrypted", f"{_encrypted_count:,}")
        _exc_m4.metric("Partial Extraction", f"{_partial_count:,}")

        _exc_rows = db_manager.get_processing_exceptions(case_folder)
        if _exc_rows:
            try:
                import io as _exc_io
                import openpyxl
                _exc_buf = _exc_io.BytesIO()
                _exc_wb = openpyxl.Workbook()

                # Sheet 1: Summary
                _ws1 = _exc_wb.active
                _ws1.title = 'Exception Summary'
                _ws1.append(['Category', 'Count'])
                _ws1.append(['Processing Errors', error_count])
                _ws1.append(['NIST Excluded', _nist_count])
                _ws1.append(['Encrypted Files', _encrypted_count])
                _ws1.append(['Partial Extraction', _partial_count])
                _ws1.append(['Total Exceptions', _exc_total])
                _ws1.append([])
                _ws1.append(['Generated', datetime.now().strftime('%Y-%m-%d %H:%M')])
                _ws1.append(['Case', os.path.basename(case_folder)])
                _ws1.append(['Generated By', st.session_state.get('username', 'unknown')])
                _ws1.freeze_panes = 'A2'

                # Sheet 2: Detail
                _ws2 = _exc_wb.create_sheet('Exception Detail')
                _exc_headers = ['Control Number', 'File Name', 'Custodian', 'Record Type',
                                'Extension', 'Size (KB)', 'Status', 'Encrypted', 'Original Path', 'Date']
                _ws2.append(_exc_headers)
                for _er in _exc_rows:
                    _ws2.append([_er.get('control_number'), _er.get('file_name'), _er.get('custodian'),
                                 _er.get('record_type'), _er.get('file_extension'), _er.get('file_size_kb'),
                                 _er.get('processing_status'), 'Yes' if _er.get('is_encrypted') else 'No',
                                 _er.get('original_path'), _er.get('date_created')])
                _ws2.freeze_panes = 'A2'
                for _col in _ws2.columns:
                    _max_len = max(len(str(_c.value or '')) for _c in _col)
                    _ws2.column_dimensions[_col[0].column_letter].width = min(_max_len + 4, 50)

                # Sheet 3: NIST Only
                _ws3 = _exc_wb.create_sheet('NIST Exclusions')
                _ws3.append(_exc_headers)
                for _er in _exc_rows:
                    if _er.get('processing_status') == 'NIST_Excluded':
                        _ws3.append([_er.get('control_number'), _er.get('file_name'), _er.get('custodian'),
                                     _er.get('record_type'), _er.get('file_extension'), _er.get('file_size_kb'),
                                     _er.get('processing_status'), 'No', _er.get('original_path'), _er.get('date_created')])
                _ws3.freeze_panes = 'A2'

                _exc_wb.save(_exc_buf)
                st.download_button(
                    "⬇️ Export Exception Report (Excel)",
                    data=_exc_buf.getvalue(),
                    file_name=f"{os.path.basename(case_folder)}_PROCESSING_EXCEPTIONS.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="proc_exception_export",
                    width='stretch',
                )
                db_manager.log_audit(case_folder, "EXCEPTION_REPORT_EXPORTED",
                    username=st.session_state.get('username'), module="Processor")
            except Exception as _exc_err:
                st.caption(f"Excel export unavailable: {_exc_err}")
    else:
        st.success("✅ No processing exceptions. All documents processed successfully.")

    st.markdown("---")

    # ── Pre-run Queue Breakdown ─────────────────────────────────────────────
    if initial_queue_count > 0:
        left, right = st.columns([1.2, 1])

        with left:
            st.subheader("📋 Queue Breakdown")
            if type_rows:
                type_df = pd.DataFrame([{"Extension": r["file_extension"] or "(none)", "Count": r["cnt"]} for r in type_rows])
                st.dataframe(type_df, width='stretch', hide_index=True, height=min(35 * len(type_rows) + 38, 340))
            if container_count > 0:
                st.info(f"📦 {container_count} container files detected (.msg / .eml / .zip) — attachments will be extracted first in Phase 1.")

        with right:
            st.subheader("🔬 Processing Pipeline")
            st.markdown("""
<style>
.phase-card {
    background: rgba(255,255,255,0.04);
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 8px;
    border-left: 4px solid;
}
</style>
<div class="phase-card" style="border-color:#4dabf7">
    <b>⚙️ Phase 1 — Container Extraction</b><br>
    <small>Recursively explodes .msg, .eml, .zip files. Attachments are registered as new documents before text extraction begins.</small>
</div>
<div class="phase-card" style="border-color:#51cf66">
    <b>🚀 Phase 2 — Parallel Text Extraction</b><br>
    <small>Multi-threaded: PyMuPDF for PDFs, Apache Tika for Office/email, Tesseract OCR fallback for image-only files. MD5 deduplication on-the-fly. All text bulk-indexed to OpenSearch.</small>
</div>
<div class="phase-card" style="border-color:#845ef7">
    <b>📧 Phase 3 — Email Imaging</b><br>
    <small>Converts .msg/.eml files to PDF using the Universal Imager (COM automation) so every document is reviewable in the document viewer.</small>
</div>
""", unsafe_allow_html=True)

            # OCR check
            try:
                import pytesseract
                st.success("🔍 Tesseract OCR: Available (scanned PDF fallback active)")
            except ImportError:
                st.warning("🔍 Tesseract OCR: Not installed — image-only PDFs may have no searchable text")

            imager_status = "✅ Available" if IMAGER_AVAILABLE else "⚠️ Unavailable — emails won't be imaged to PDF"
            st.markdown(f"**Universal Imager:** {imager_status}")
            st.markdown(f"**Worker Threads:** {max_threads} (set in sidebar)")

        st.markdown("---")

    # ── Processing Log Viewer ────────────────────────────────────────────────
    _render_log_viewer(audit_path)

    # ── Containers Needing Attention ──────────────────────────────────────
    conn_check = db_manager.get_connection(case_folder)
    problem_containers = conn_check.execute("""  -- db_manager: exempt (dashboard read)
        SELECT id, file_name, control_number, processing_status, file_extension
        FROM documents
        WHERE processing_status IN ('Partial_Extraction', 'Error', 'Error_Timeout')
          AND LOWER(file_extension) IN ('.pst', '.zip')
    """).fetchall()
    conn_check.close()

    if problem_containers:
        st.warning(f"{len(problem_containers)} container(s) have extraction issues")
        with st.expander("Container Extraction Issues", expanded=True):
            for pc in problem_containers:
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    st.text(f"{pc['file_name']}")
                with col2:
                    status_color = "Partial" if pc['processing_status'] == 'Partial_Extraction' else "Error"
                    st.text(f"{status_color}: {pc['processing_status']}")
                with col3:
                    re_key = f"re_extract_{pc['id']}"
                    if st.button("Re-Extract", key=re_key):
                        with st.spinner(f"Re-extracting {pc['file_name']}..."):
                            success, msg = re_extract_container(case_folder, pc['id'])
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(f"Re-extraction failed: {msg}")

            # ScanPST integration — show for PSTs only
            pst_problems = [pc for pc in problem_containers if (pc['file_extension'] or '').lower() == '.pst']
            if pst_problems:
                _show_scanpst_option(case_folder, pst_problems)

    # ── Launch Button ───────────────────────────────────────────────────────
    if initial_queue_count == 0:
        if already_processed > 0:
            st.success(f"✅ All {already_processed:,} documents in this case have been processed. Nothing left in queue.")
        else:
            st.info("📂 No documents in queue. Go to Module 1 (Ingestor) to scan files into the database.")
        return

    if _resumed_count > 0 and _new_count > 0:
        st.info(f"📋 Queue contains **{_new_count:,} new** documents and **{_resumed_count:,} resumed** from a previous incomplete run.")
    elif _resumed_count > 0:
        st.info(f"📋 Queue contains **{_resumed_count:,} documents** resumed from a previous incomplete run (no new files).")
    btn_label = f"🚀 Launch Processing Pipeline  ({initial_queue_count:,} documents)"
    if not st.button(btn_label, type="primary", width='stretch', key="launch_processing_btn"):
        return

    # ── Launch background processing worker ───────────────────────────────
    _proc_username = st.session_state.get('username', 'unknown')
    try:
        job_id = db_manager.create_job(case_folder, 'processing', _proc_username, total=initial_queue_count)
        worker_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '_processing_worker.py')
        python_exe = sys.executable
        cmd = [python_exe, worker_script, case_folder, str(job_id), '--threads', str(max_threads)]
        _sp.Popen(
            cmd,
            creationflags=_sp.CREATE_NO_WINDOW | _sp.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        logger.info(f"Launched background processing worker: job_id={job_id}")
        st.session_state['active_job_id'] = job_id
        time.sleep(0.5)  # Give worker a moment to register
        st.rerun()
    except Exception as launch_err:
        logger.error(f"Failed to launch background worker: {launch_err}")
        st.warning(f"Background worker failed to launch: {launch_err}. Falling back to inline processing.")
        # Clean up the failed job
        try:
            db_manager.fail_job(case_folder, job_id, f"Launch failed: {launch_err}")
        except Exception:
            pass

    # ── Inline fallback (only reached if subprocess launch failed) ────────
    status_text   = st.empty()
    progress_bar  = st.progress(0)
    phase_banner  = st.empty()
    _cancel_placeholder = st.empty()
    st.session_state['_proc_cancel'] = False
    with _cancel_placeholder.container():
        st.markdown("<div style='height:0;overflow:hidden'>", unsafe_allow_html=True)
        st.button(
            "⛔ Cancel Processing",
            key="_proc_cancel_btn",
            on_click=lambda: st.session_state.update({'_proc_cancel': True}),
            type="secondary",
        )
        st.markdown("</div>", unsafe_allow_html=True)
    lottie_placeholder = ui_utils.start_lottie_spinner(
        "Processing Execution Pipeline — Please Wait...")
    ui_utils.show_overlay_cancel_button()

    def _phase(n, label, color):
        phase_banner.markdown(
            f"<div style='background:rgba(255,255,255,0.05);border-left:4px solid {color};"
            f"border-radius:6px;padding:8px 14px;margin:4px 0'>"
            f"<b style='color:{color}'>Phase {n}</b> — {label}</div>",
            unsafe_allow_html=True
        )

    def _ui_progress(phase, completed, total, message):
        """Callback wired to Streamlit widgets for inline processing."""
        if total > 0:
            progress_bar.progress(completed / total)
        status_text.text(message)
        if phase == 1:
            ui_utils.update_lottie_spinner(lottie_placeholder, "Processing Execution Pipeline — Please Wait...", message)
        elif phase == 2:
            ui_utils.update_lottie_spinner(lottie_placeholder, "Processing Execution Pipeline — Please Wait...", f"Phase 2: Text Extraction & Indexing — {completed:,} / {total:,}")
        elif phase == 3:
            ui_utils.update_lottie_spinner(lottie_placeholder, "Processing Execution Pipeline — Please Wait...", message)

    def _check_cancel():
        return st.session_state.get('_proc_cancel', False)

    _proc_username = st.session_state.get('username', 'unknown')

    # --- PHASE 1: RECURSIVE EXTRACTION ---
    _phase(1, "Container Extraction — recursively exploding .msg/.eml/.zip attachments...", "#4dabf7")
    status_text.text("Phase 1: Extracting attachments...")
    db_manager.log_audit(case_folder, "PROCESSING_STARTED", username=_proc_username,
        module="Processor", details=json.dumps({"phase": 1}))

    extraction_summary = processing_engine.run_phase_1(
        case_folder, temp_path, username=_proc_username,
        on_progress=_ui_progress, check_cancel=_check_cancel
    )

    # Show extraction summary if any PSTs were processed
    if extraction_summary:
        has_partial = any(
            s['failed_folders'] or (s['expected'] > 0 and s['extracted'] < s['expected'])
            for s in extraction_summary
        )
        if has_partial:
            st.warning("One or more containers had partial extraction — some items could not be read.")

        with st.expander("Phase 1: Container Extraction Summary", expanded=has_partial):
            summary_data = []
            for s in extraction_summary:
                _is_partial = bool(s['failed_folders']) or (s['expected'] > 0 and s['extracted'] < s['expected'])
                if _is_partial:
                    status = f"⚠️ Partial ({s['extracted']}/{s['expected']})"
                elif s['expected'] == 0 and s['extracted'] == 0:
                    status = "Empty"
                else:
                    status = f"✅ Complete ({s['extracted']}/{s['expected']})"
                summary_data.append({
                    'Container': s['file_name'],
                    'Expected': s['expected'],
                    'Extracted': s['extracted'],
                    'Status': status
                })
            st.dataframe(summary_data, width='stretch', hide_index=True)

    status_text.success("Phase 1 complete — all attachments extracted.")

    # --- PHASE 2: PARALLEL PROCESSING ---
    _phase(2, f"Parallel Text Extraction — {max_threads} threads...", "#51cf66")
    status_text.text("Phase 2: Processing files in parallel...")

    completed, total_docs_to_process, thread_errors, _was_cancelled = processing_engine.run_phase_2(
        case_folder, processed_path, max_threads, username=_proc_username,
        on_progress=_ui_progress, check_cancel=_check_cancel
    )

    if total_docs_to_process == 0:
        st.success("✅ All documents processed and extracted. No new files to process.")

    if thread_errors:
        st.error(f"❌ {len(thread_errors)} document(s) failed during parallel processing. See audit log for details.")
        with st.expander(f"⚠️ {len(thread_errors)} worker errors"):
            for err in thread_errors:
                st.text(err)

    _cancel_placeholder.empty()

    if _was_cancelled:
        st.warning(f"⛔ Processing cancelled after {completed}/{total_docs_to_process} documents. "
                   f"Unprocessed documents remain in the queue and will be picked up on the next run.")
        st.session_state.pop('_proc_cancel', None)
        st.rerun()
        return

    # --- PHASE 3: EMAIL IMAGING ---
    _phase(3, "Email Imaging — converting .msg/.eml to PDF for review...", "#845ef7")
    status_text.text("Phase 3: Imaging emails to PDF for review...")

    img_success, img_fail, img_total = processing_engine.run_phase_3(
        case_folder, processed_path, username=_proc_username,
        on_progress=_ui_progress, check_cancel=_check_cancel
    )

    if img_total > 0:
        status_text.text(f"Phase 3 complete: {img_success} emails imaged, {img_fail} failures.")
    else:
        status_text.text("Phase 3: No emails to image.")

    status_text.empty()
    report_path, suspicious_count = processing_engine.generate_batch_report(case_folder, audit_path)
    st.info(f"Generated report with suspicious file count: {suspicious_count}")
    lottie_placeholder.empty()

    db_manager.log_audit(case_folder, "PROCESSING_COMPLETED", username=_proc_username,
        module="Processor", details=json.dumps({
            "processed": total_docs_to_process,
            "images_ok": img_success, "images_fail": img_fail
        }))

    st.success(f"✅ Batch Complete! Found {suspicious_count} suspicious files.")
    if img_total > 0:
        st.info(f"📧 Email Imaging: {img_success} emails converted to PDF, {img_fail} failed.")

    # Refresh live metrics
    m_conn = db_manager.get_connection(case_folder)
    try:
        t = m_conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]  # db_manager: exempt (dashboard read)
        q = m_conn.execute("SELECT COUNT(*) FROM documents WHERE processing_status IN ('New','Container_Scanned','Ready_For_Processing')").fetchone()[0]  # db_manager: exempt (dashboard read)
        p = m_conn.execute("SELECT COUNT(*) FROM documents WHERE processing_status IN ('Processed','Master')").fetchone()[0]  # db_manager: exempt (dashboard read)
        d = m_conn.execute("SELECT COUNT(*) FROM documents WHERE processing_status='Duplicate (MD5)'").fetchone()[0]  # db_manager: exempt (dashboard read)
        e = m_conn.execute("SELECT COUNT(*) FROM documents WHERE processing_status LIKE '%Error%' OR processing_status='Partial_Extraction'").fetchone()[0]  # db_manager: exempt (dashboard read)
        _draw_metrics(t, q, p, d, e)
    finally:
        m_conn.close()
    st.balloons()

    with open(report_path, "rb") as f:
        st.download_button(
            label="📥 Download Processing Audit (CSV)",
            data=f,
            file_name=os.path.basename(report_path),
            mime="text/csv"
        )

main()
