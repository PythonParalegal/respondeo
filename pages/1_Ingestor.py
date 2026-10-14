# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        1_Ingestor.py
# version:       1.2.7
# project:       Respondeo eDiscovery Platform
# project_ver:   2.9.0
# last_modified: 2026-04-15 14:30
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
import os
import sys
import re
import hashlib
from pathlib import Path
import json
import pandas as pd
import db_manager


def _natural_sort_key(text):
    """Sort key that treats embedded numbers as integers, so '2. Foo' < '10. Bar'."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r'(\d+)', text)]


def _long_path(p):
    """On Windows, prefix absolute paths with \\\\?\\ to bypass the 260-char MAX_PATH limit."""
    if sys.platform != 'win32':
        return p
    p = os.path.abspath(p)
    if not p.startswith('\\\\?\\'):
        p = '\\\\?\\' + p
    return p


_ASSETS = Path(__file__).resolve().parent.parent / "assets"
st.set_page_config(page_title="Respondeo | Ingest", layout="wide", page_icon=str(_ASSETS / "favicon.png"))

import ui_utils
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()

import auth_manager
if not auth_manager.check_login(): st.stop()
# permission: ingest
auth_manager.require_permission('ingest')
auth_manager.show_user_info()

# Get Active Case from Home
case_folder = st.session_state.get('current_case_folder')

if not case_folder:
    st.error("Please select a case in 'Home' first!")
    st.stop()


# --- CASE LIFECYCLE GATE ---


_case_status = db_manager.get_case_status(case_folder)
if _case_status == 'Closed':
    st.warning('🔒 This matter is closed. Write operations are disabled.')
    st.stop()

# Helper: Hash Calculation
def calculate_md5(file_path):
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def main():
    st.title("Module 1: Ingestor 📥")
    st.caption("Scan a collection folder, compute MD5 hashes in parallel, and register every document into the case database — ready for the Processor.")

    db_manager.init_db(case_folder)

    ingest_path = _long_path(os.path.join(case_folder, "Ingest"))

    # ── Case Stats ─────────────────────────────────────────────────────────
    conn_s = db_manager.get_connection(case_folder)
    total_registered = conn_s.execute("SELECT COUNT(*) FROM documents").fetchone()[0]  # db_manager: exempt (dashboard read)
    already_processed = conn_s.execute("SELECT COUNT(*) FROM documents WHERE processing_status NOT IN ('New','Error')").fetchone()[0]  # db_manager: exempt (dashboard read)
    custodian_count = conn_s.execute("SELECT COUNT(DISTINCT custodian) FROM documents WHERE custodian IS NOT NULL AND custodian != ''").fetchone()[0]  # db_manager: exempt (dashboard read)
    in_queue = conn_s.execute("SELECT COUNT(*) FROM documents WHERE processing_status='New'").fetchone()[0]  # db_manager: exempt (dashboard read)
    conn_s.close()

    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric("Registered in DB",   f"{total_registered:,}")
    cs2.metric("⏳ Awaiting Process", f"{in_queue:,}")
    cs3.metric("✅ Processed",        f"{already_processed:,}")
    cs4.metric("👤 Custodians",       f"{custodian_count:,}")

    st.markdown("---")

    # ── Ingest Folder Preview ──────────────────────────────────────────────
    if not os.path.exists(ingest_path):
        st.error(f"❌ No `Ingest` folder found at `{ingest_path}`.")
        st.info("Create an `Ingest` subfolder inside your case folder and place source documents there.")
        st.stop()

    # Walk the folder to get a file-type preview
    preview_files = []
    for root, dirs, files in os.walk(ingest_path):
        dirs[:] = sorted([d for d in dirs if d != 'Processed'], key=_natural_sort_key)
        for fn in sorted(files, key=_natural_sort_key):
            fp = os.path.join(root, fn)
            try:
                size_kb = os.path.getsize(fp) / 1024
            except OSError:
                size_kb = 0
            ext = os.path.splitext(fn)[1].lower() or "(none)"
            preview_files.append((fp, ext, size_kb))

    total_files   = len(preview_files)
    total_size_mb = sum(f[2] for f in preview_files) / 1024

    left_col, right_col = st.columns([1.1, 1])

    with left_col:
        st.subheader("📂 Ingest Folder Contents")
        st.caption(f"`{ingest_path}`")
        if total_files == 0:
            st.info("The Ingest folder is empty. Copy source documents there before scanning.")
        else:
            st.markdown(f"**{total_files:,} files** &nbsp;·&nbsp; {total_size_mb:.1f} MB total", unsafe_allow_html=True)
            # Extension breakdown
            from collections import Counter
            ext_counts = Counter(f[1] for f in preview_files)
            ext_df = pd.DataFrame(
                [{"Extension": k, "Count": v, "Total Size (MB)": round(sum(f[2] for f in preview_files if f[1] == k) / 1024, 2)}
                 for k, v in sorted(ext_counts.items(), key=lambda x: -x[1])]
            )
            st.dataframe(ext_df, width='stretch', hide_index=True,
                         height=min(38 * len(ext_df) + 38, 340))

            # Container warning
            container_exts = {'.msg', '.eml', '.zip'}
            container_count_preview = sum(v for k, v in ext_counts.items() if k in container_exts)
            if container_count_preview > 0:
                st.info(f"📦 {container_count_preview} container files (.msg/.eml/.zip) — attachments will be extracted during processing (Module 2).")

    with right_col:
        st.subheader("⚙️ Scan Settings")
        # Performance sidebar already has max_workers, but show it inline too
        st.sidebar.header("⚙️ Performance")
        max_workers = st.sidebar.slider("Scanner Threads", 1, 8, 4)

        structured_mode = st.toggle(
            "📁 Auto-detect custodian & collections from folder structure",
            value=False,
            help=(
                "When enabled, first-level subfolders under Ingest/ are treated as custodian names. "
                "Second-level folders become collections, third-level become subcollections. "
                "When disabled, all files use the manually entered custodian name below."
            )
        )

        if structured_mode:
            # --- Structured mode: show folder tree preview ---
            custodian_name = None

            def _walk_files(path):
                """Yield all files under path recursively, skipping 'Processed' dirs."""
                for _root, _dirs, _files in os.walk(path):
                    _dirs[:] = sorted([d for d in _dirs if d != 'Processed'], key=_natural_sort_key)
                    for _fn in sorted(_files, key=_natural_sort_key):
                        yield os.path.join(_root, _fn)

            st.subheader("📂 Detected Structure")
            custodian_dirs = sorted([
                d for d in os.listdir(ingest_path)
                if os.path.isdir(os.path.join(ingest_path, d)) and d != 'Processed'
            ], key=_natural_sort_key)

            # Warn about loose files at ingest root
            loose_files = [f for f in os.listdir(ingest_path)
                           if os.path.isfile(os.path.join(ingest_path, f))]
            if loose_files:
                st.warning(
                    f"⚠️ {len(loose_files)} file(s) found directly in the Ingest root, not inside a custodian folder. "
                    f"These will be assigned custodian 'Unassigned' with no collection."
                )

            if not custodian_dirs and not loose_files:
                st.warning(
                    "No custodian folders found. In structured mode, place files inside "
                    "subfolders named after each custodian.\n\n"
                    "Example: `Ingest/JohnSmith/InitialDisclosures/Communications/email.msg`"
                )
                can_scan = False
            else:
                for cust_dir in custodian_dirs:
                    cust_path = os.path.join(ingest_path, cust_dir)
                    cust_file_count = sum(1 for _ in _walk_files(cust_path))

                    st.markdown(f"**👤 {cust_dir}** ({cust_file_count} files)")

                    # Level 2: collections
                    collections = sorted([
                        d for d in os.listdir(cust_path)
                        if os.path.isdir(os.path.join(cust_path, d))
                    ], key=_natural_sort_key)
                    for coll in collections:
                        coll_path = os.path.join(cust_path, coll)
                        coll_file_count = sum(1 for _ in _walk_files(coll_path))
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;📦 {coll} ({coll_file_count} files)")

                        # Level 3: subcollections
                        subcollections = sorted([
                            d for d in os.listdir(coll_path)
                            if os.path.isdir(os.path.join(coll_path, d))
                        ], key=_natural_sort_key)
                        for subcoll in subcollections:
                            subcoll_path = os.path.join(coll_path, subcoll)
                            subcoll_file_count = sum(1 for _ in _walk_files(subcoll_path))
                            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;📄 {subcoll} ({subcoll_file_count} files)")

                can_scan = total_files > 0
        else:
            # --- Flat mode: manual custodian entry ---
            custodian_name = st.text_input(
                "👤 Custodian Name *",
                placeholder="e.g. John Smith",
                help="The person or entity whose documents are in this collection. Required — used in review, analytics, and privilege logs.",
                key="custodian_name_input"
            )

            if not custodian_name:
                st.warning("Enter a Custodian Name to enable scanning.")

            can_scan = bool(custodian_name) and total_files > 0

        auto_tags_input = st.text_input(
            "🏷️ Bulk Auto-Tag (optional)",
            placeholder="e.g. Insurance, Key_Witness",
            help="Comma-separated tags applied to every document in this batch.",
            key="auto_tags_input"
        )

        st.markdown("")  # spacer

        launch_label = f"🚀 Scan & Register  ({total_files:,} files)" if total_files > 0 else "🚀 Scan & Register"
        _ingest_running = st.session_state.get('_ingest_running', False)
        scan_clicked = st.button(
            launch_label, type="primary", width='stretch',
            disabled=not can_scan or _ingest_running,
            key="scan_register_btn"
        )

    if not scan_clicked:
        st.markdown("---")
        # Custodian Backfill even before scan
        _render_custodian_backfill()
        return

    # ── Scan execution ─────────────────────────────────────────────────────
    st.session_state['_ingest_running'] = True

    formatted_tags = ""
    if auto_tags_input:
        tag_list = [t.strip() for t in auto_tags_input.split(",") if t.strip()]
        if tag_list:
            formatted_tags = ";".join(tag_list) + ";"

    st.markdown("---")
    step_banner = st.empty()
    progress_bar = st.progress(0)
    status_text  = st.empty()

    def _step(label, color="#4dabf7"):
        step_banner.markdown(
            f"<div style='background:rgba(255,255,255,0.05);border-left:4px solid {color};"
            f"border-radius:6px;padding:8px 14px;margin:4px 0'><b style='color:{color}'>{label}</b></div>",
            unsafe_allow_html=True
        )

    # Step 1: walk folder
    _step("① Scanning folder tree...", "#4dabf7")
    status_text.text("Walking directory structure...")
    all_files = []
    for root, dirs, files in os.walk(ingest_path):
        dirs[:] = sorted([d for d in dirs if d != 'Processed'], key=_natural_sort_key)
        for fn in sorted(files, key=_natural_sort_key):
            full_path = _long_path(os.path.join(root, fn))
            all_files.append((full_path, root, fn))
    progress_bar.progress(0.15)

    if not all_files:
        step_banner.empty()
        st.info("No files found in Ingest folder.")
        return

    # Step 2: check which are already in DB
    _step("② Deduplicating against existing database entries...", "#4dabf7")
    status_text.text(f"Checking {len(all_files):,} paths against the database...")
    conn = db_manager.get_connection(case_folder)
    cursor = conn.cursor()
    new_files_to_process = []

    def batched(iterable, n):
        for i in range(0, len(iterable), n):
            yield iterable[i:i + n]

    _dedup_batches = list(batched(all_files, 900))
    _dedup_total = len(_dedup_batches)
    for _dedup_idx, batch in enumerate(_dedup_batches):
        # Strip \\?\ prefix for DB comparison — paths are stored without it
        paths_in_batch = [f[0][4:] if f[0].startswith('\\\\?\\') else f[0] for f in batch]
        placeholders = ','.join(['?'] * len(paths_in_batch))
        existing_rows = cursor.execute(  # db_manager: exempt (ingest loop)
            f"SELECT full_path FROM documents WHERE full_path IN ({placeholders})", paths_in_batch
        ).fetchall()
        existing_paths = {row[0] for row in existing_rows}
        for ft in batch:
            db_path = ft[0][4:] if ft[0].startswith('\\\\?\\') else ft[0]
            if db_path not in existing_paths:
                new_files_to_process.append(ft)
        progress_bar.progress(0.15 + 0.15 * (_dedup_idx + 1) / _dedup_total)
    conn.close()

    already_registered_count = len(all_files) - len(new_files_to_process)

    if not new_files_to_process:
        st.session_state['_ingest_running'] = False
        step_banner.empty()
        progress_bar.empty()
        status_text.empty()
        st.success(f"✅ All {len(all_files):,} files are already registered. Nothing new to add.")
        _render_custodian_backfill()
        return

    # Step 3: parallel MD5 + metadata
    _step(f"③ Computing MD5 hashes in parallel ({max_workers} threads)...", "#51cf66")
    status_text.text(f"Hashing {len(new_files_to_process):,} new files...")

    new_files_batch = []
    list_lock = threading.Lock()
    hash_errors = []

    def process_file_worker(file_info):
        full_path, root, fn = file_info
        try:
            size_kb = round(os.path.getsize(full_path) / 1024, 2)
            file_hash = calculate_md5(full_path)
            ext = os.path.splitext(fn)[1].lower()
            original_path = os.path.relpath(root, ingest_path)
            db_full_path = full_path[4:] if full_path.startswith('\\\\?\\') else full_path

            # Parse structure from folder hierarchy
            if structured_mode:
                path_parts = original_path.replace('\\', '/').split('/')
                path_parts = [p for p in path_parts if p and p != '.']
                _cust = path_parts[0] if len(path_parts) > 0 else 'Unassigned'
                _coll = path_parts[1] if len(path_parts) > 1 else None
                _subcoll = path_parts[2] if len(path_parts) > 2 else None
            else:
                _cust = custodian_name  # from the manual text input
                _coll = None
                _subcoll = None

            return (fn, original_path, db_full_path, ext, size_kb, file_hash,
                    "New", _cust, formatted_tags, _coll, _subcoll)
        except Exception as e:
            return e

    processed_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_file_worker, f): f for f in new_files_to_process}
        for future in as_completed(futures):
            result = future.result()
            processed_count += 1
            if isinstance(result, tuple):
                with list_lock:
                    new_files_batch.append(result)
            else:
                hash_errors.append(str(result))
            if processed_count % 10 == 0 or processed_count == len(new_files_to_process):
                pct = 0.30 + 0.40 * (processed_count / len(new_files_to_process))
                progress_bar.progress(pct)
                status_text.text(f"Hashed {processed_count:,} / {len(new_files_to_process):,} files...")

    # Restore natural-sort folder order after parallel hashing scrambled it
    _path_order = {info[0]: idx for idx, info in enumerate(new_files_to_process)}
    _stripped_order = {}
    for info in new_files_to_process:
        fp = info[0]
        stripped = fp[4:] if fp.startswith('\\\\?\\') else fp
        _stripped_order[stripped] = _path_order[fp]
    new_files_batch.sort(key=lambda row: _stripped_order.get(row[2], float('inf')))

    # Step 4: bulk insert
    _step("④ Writing to database...", "#845ef7")
    status_text.text(f"Inserting {len(new_files_batch):,} records...")

    insert_count = 0
    db_error = None
    _ingest_audit = []
    _ingest_username = st.session_state.get('username', 'unknown')
    if new_files_batch:
        conn = db_manager.get_connection(case_folder)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")  # db_manager: exempt (schema introspection)
            insert_sql = """
                INSERT INTO documents (file_name, original_path, full_path, file_extension,
                                      file_size_kb, md5_hash, processing_status, custodian,
                                      tags, source_collection, source_subcollection)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            _insert_batches = list(batched(new_files_batch, 3000))
            _insert_total = len(_insert_batches)
            for _ins_idx, batch in enumerate(_insert_batches):
                conn.executemany(insert_sql, batch)
                progress_bar.progress(0.70 + 0.30 * (_ins_idx + 1) / _insert_total)
            conn.commit()
            insert_count = len(new_files_batch)
            # Query back inserted control numbers for audit log
            inserted_paths = [row[2] for row in new_files_batch]  # full_path is index 2
            for i in range(0, len(inserted_paths), 1000):
                chunk = inserted_paths[i:i+1000]
                plchs = ','.join(['?'] * len(chunk))
                for ar in conn.execute(  # db_manager: exempt (ingest loop)
                    f"SELECT control_number, file_name, original_path FROM documents WHERE full_path IN ({plchs})",
                    chunk
                ).fetchall():
                    _ingest_audit.append({
                        "action": "DOCUMENT_INGESTED", "username": _ingest_username,
                        "control_number": ar['control_number'], "module": "Ingestor",
                        "details": json.dumps({"file_name": ar['file_name'], "original_path": ar['original_path']}),
                        "old_value": None, "new_value": None
                    })
        except Exception as e:
            db_error = str(e)
            conn.rollback()
        finally:
            conn.close()

    if _ingest_audit:
        db_manager.log_audit_batch(case_folder, _ingest_audit)

    progress_bar.progress(1.0)
    step_banner.empty()
    progress_bar.empty()
    status_text.empty()

    # ── Results card ───────────────────────────────────────────────────────
    if db_error:
        st.error(f"❌ Database write failed: {db_error}")
    else:
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("✅ Registered",     f"{insert_count:,}")
        r2.metric("⏭️ Already in DB",  f"{already_registered_count:,}")
        r3.metric("❌ Hash Errors",    f"{len(hash_errors):,}")
        r4.metric("📂 Total Scanned",  f"{len(all_files):,}")

        if structured_mode:
            _cust_names = set(row[7] for row in new_files_batch)  # index 7 = custodian
            st.success(
                f"✅ Added **{insert_count:,}** new documents across "
                f"**{len(_cust_names)}** custodian(s): {', '.join(sorted(_cust_names))}. "
                f"Head to Module 2 to process them."
            )
        else:
            st.success(f"✅ Added **{insert_count:,}** new documents to the database for custodian **{custodian_name}**. Head to Module 2 to process them.")

        if hash_errors:
            with st.expander(f"⚠️ {len(hash_errors)} files had errors"):
                for e in hash_errors[:50]:
                    st.text(e)

        # Extension breakdown of what was just added
        if new_files_batch:
            from collections import Counter
            added_exts = Counter(row[3] for row in new_files_batch)
            added_df = pd.DataFrame([{"Extension": k, "Files Added": v}
                                      for k, v in sorted(added_exts.items(), key=lambda x: -x[1])])
            with st.expander("📊 Breakdown of newly registered files"):
                st.dataframe(added_df, width='stretch', hide_index=True)

    st.session_state['_ingest_running'] = False
    st.markdown("---")
    _render_custodian_backfill()


def _render_custodian_backfill():
    """Renders the custodian backfill utility section."""
    conn_bf = db_manager.get_connection(case_folder)
    unassigned = conn_bf.execute(  # db_manager: exempt (dashboard read)
        "SELECT COUNT(*) FROM documents WHERE (custodian IS NULL OR custodian = '') AND (source_party = 'Internal' OR source_party IS NULL)"
    ).fetchone()[0]

    # Custodian distribution table
    cust_rows = conn_bf.execute(  # db_manager: exempt (dashboard read)
        "SELECT COALESCE(custodian,'(unassigned)') as custodian, COUNT(*) as doc_count "
        "FROM documents GROUP BY custodian ORDER BY doc_count DESC LIMIT 20"
    ).fetchall()
    conn_bf.close()

    with st.expander("👤 Custodian Overview & Backfill", expanded=(unassigned > 0)):
        if cust_rows:
            st.dataframe(
                pd.DataFrame([{"Custodian": r["custodian"], "Documents": r["doc_count"]} for r in cust_rows]),
                width='stretch', hide_index=True
            )

        if unassigned > 0:
            st.warning(f"**{unassigned:,}** internal documents have no custodian assigned.")
            bf_col1, bf_col2 = st.columns([2, 1])
            with bf_col1:
                backfill_name = st.text_input(
                    "Assign custodian to all unassigned internal docs:",
                    placeholder="e.g. John Smith",
                    key="backfill_custodian"
                )
            with bf_col2:
                st.markdown("<br>", unsafe_allow_html=True)
                if backfill_name and st.button(f"✅ Assign to {unassigned:,} docs", width='stretch', key="backfill_assign_btn"):
                    conn_bf2 = db_manager.get_connection(case_folder)
                    conn_bf2.execute(  # db_manager: exempt (custodian assignment)
                        "UPDATE documents SET custodian = ? WHERE (custodian IS NULL OR custodian = '') AND (source_party = 'Internal' OR source_party IS NULL)",
                        (backfill_name,)
                    )
                    conn_bf2.commit()
                    conn_bf2.close()
                    st.success(f"✅ Assigned '{backfill_name}' to {unassigned:,} documents.")
                    import time; time.sleep(1)
                    st.rerun()
        else:
            st.success("✅ All internal documents have a custodian assigned.")


main()
