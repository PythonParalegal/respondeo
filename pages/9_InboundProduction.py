# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        9_InboundProduction.py
# version:       1.0.1
# project:       Respondeo eDiscovery Platform
# project_ver:   2.16.0
# last_modified: 2026-06-01 12:00
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
"""Module 9: Inbound Productions.

Ingest opposing counsel's structured productions (load file + natives/images/
text) with clean isolation from internal custodial documents. Each ingested
document is tagged source_party != 'Internal' and production_volume; the
outbound production filter (beta-2.10 Commit 3,
db_manager.OUTBOUND_SOURCE_FILTER_SQL) guarantees these never leak into our
own court-destined output.

Extracted from pages/5_Production.py's `tab_inbound` block in beta-2.10
Commit 6. Module extraction motivated by two defensibility concerns in the
original shared-page layout (documented in the sprint plan at
docs/archive/specs/Inbound_Production_Module_Spec.md):

  1. Phase-gating st.stop() calls in the outbound tab were blanking the
     inbound tab entirely during Pass 1 checkpoint state.
  2. Inbound ingest is semantically an *input* workflow; housing it next
     to outbound assembly invited category confusion and produced
     workflow hazards (a user mid-Pass-1 on outbound could not switch
     to inbound ingest without first resolving the checkpoint).

Access: reuses the existing 'production' permission for this sprint — same
access tier as outbound Module 5 today. The `# permission: ingest_inbound_production`
annotation above the gate marks the intent for a future permission-
granularity sprint that splits these into distinct permissions.
"""
import os
import shutil
import sqlite3
import json
import time
import pandas as pd
from datetime import datetime
from pathlib import Path

import streamlit as st
import db_manager
import os_manager
import auth_manager
import ui_utils
from opensearchpy import helpers

_ASSETS = Path(__file__).resolve().parent.parent / "assets"

st.set_page_config(
    page_title="Respondeo | Inbound Productions",
    layout="wide",
    page_icon=str(_ASSETS / "favicon.png"),
)
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()

if not auth_manager.check_login(): st.stop()
# permission: ingest_inbound_production
auth_manager.require_permission('production')
auth_manager.show_user_info()

# --- CASE GUARD ---
case_folder = st.session_state.get('current_case_folder')
if not case_folder:
    st.error("Please select a case in 'Home' first!")
    st.stop()

# --- CASE LIFECYCLE GATE ---
# Pattern mirrors pages/4_Review.py:297-302 — banner at top, page continues
# rendering, individual write actions gated inline by `if not _case_closed:`
# and `disabled=_case_closed` parameters below.
_case_status = db_manager.get_case_status(case_folder)
_case_closed = (_case_status == 'Closed')
if _case_closed:
    st.warning('🔒 This matter is closed. Document ingestion is disabled; '
               'previously-ingested productions remain visible read-only.')

st.title("Module 9: Inbound Productions 📥")

# ============================================================================
# BODY LIFTED FROM pages/5_Production.py lines 3370-3789 (beta-2.10 Commit 6).
# Content unchanged except:
#   - 4-space de-indent (was inside `with tab_inbound:`)
#   - Removed the redundant `st.header("Inbound Productions 📥")` (replaced
#     by the st.title() above — title + identical header was visual noise)
#   - Wrapped the ingest form (Steps 1-4) in `if not _case_closed:` so
#     closed-case users see a muted placeholder instead of an empty page
#   - Added `disabled=_case_closed` to the purge-execute button
# No product behavior changes — all 425 lines of the lifted body execute
# exactly as they did inside tab_inbound.
# ============================================================================

st.markdown("Safely ingest third-party structured productions (load files + natives/images/text) without mixing them into your internal processing pipeline.")

with st.expander("Configuration Guide", expanded=False):
    st.info("""
    1. **Data Isolation:** This module tags ingested documents with a `Source Party` to keep them cleanly separated from your internal documents.
    2. **Dynamism:** Any fields in the load file that you don't explicitly map to system columns will be saved as JSON in `dynamic_metadata`.
    3. **Paths:** For 'Native Link' and 'Text Link', ensure the load file contains relative paths (e.g., `NATIVES\\001\\file.pdf`). The tool will resolve them against the Production Root Folder you specify.
    """)

# --- OPENSEARCH CONNECTION ---
_ib_es, _ib_es_status = os_manager.get_os_client()
if _ib_es:
    if auth_manager.get_user_role() == 'admin':
        st.sidebar.success("✅ OpenSearch Connected")
else:
    st.sidebar.error(f"❌ OpenSearch Error: {_ib_es_status}")

# --- Ensure DB schema is up-to-date ---
db_manager.init_db(case_folder)

# --- Existing Ingested Productions ---
st.header("📋 Previously Ingested Productions")
# Migrated from inline SQL to db_manager helper in beta-2.10 Commit 5.
_ib_existing_prods = db_manager.get_inbound_productions(case_folder)

if _ib_existing_prods:
    _ib_prod_data = [{"Party": r['source_party'], "Volume": r['production_volume'], "Documents": r['doc_count']} for r in _ib_existing_prods]
    st.dataframe(_ib_prod_data, width='stretch', hide_index=True)

    # Purge UI
    with st.expander("🗑️ Purge a Production Volume", expanded=False):
        st.warning("This will permanently delete all documents, ES entries, and copied files for the selected volume.")
        _ib_purge_options = [f"{r['source_party']} — {r['production_volume']} ({r['doc_count']} docs)" for r in _ib_existing_prods]
        _ib_purge_selection = st.selectbox("Select Production to Purge", _ib_purge_options, key="ib_purge_selection")

        if _ib_purge_selection:
            _ib_sel_idx = _ib_purge_options.index(_ib_purge_selection)
            _ib_purge_party = _ib_existing_prods[_ib_sel_idx]['source_party']
            _ib_purge_volume = _ib_existing_prods[_ib_sel_idx]['production_volume']

            _ib_col_purge1, _ib_col_purge2 = st.columns(2)
            _ib_delete_files = _ib_col_purge1.checkbox("Also delete copied files from Inbound folder", value=True, key="ib_delete_files")
            _ib_confirm_text = _ib_col_purge2.text_input("Type PURGE to confirm", key="ib_purge_confirm")

            if st.button("🗑️ Execute Purge", type="primary", disabled=(_ib_confirm_text != "PURGE" or _case_closed), key="ib_execute_purge"):
                _ib_purge_status = st.empty()
                _ib_purge_status.info("Purging from database...")

                # Migrated to db_manager helper in beta-2.10 Commit 5. The
                # helper performs SELECT-ids + DELETE-docs + DELETE-production_runs-row
                # atomically in one SQLite transaction and returns the
                # opensearch_ids for the OS cleanup below.
                _ib_opensearch_ids = db_manager.purge_inbound_volume(
                    case_folder, _ib_purge_party, _ib_purge_volume
                )

                if _ib_es and _ib_opensearch_ids:
                    _ib_purge_status.info(f"Purging {len(_ib_opensearch_ids)} documents from OpenSearch...")
                    _ib_index_name = os_manager.get_index_name(case_folder)
                    _ib_os_delete_batch = [{"_op_type": "delete", "_index": _ib_index_name, "_id": eid} for eid in _ib_opensearch_ids]
                    try:
                        helpers.bulk(_ib_es, _ib_os_delete_batch, raise_on_error=False, raise_on_exception=False)
                    except Exception:
                        pass

                if _ib_delete_files:
                    _ib_inbound_dir = os.path.join(case_folder, "Inbound", _ib_purge_party, _ib_purge_volume)
                    if os.path.isdir(_ib_inbound_dir):
                        _ib_purge_status.info(f"Deleting files from {_ib_inbound_dir}...")
                        shutil.rmtree(_ib_inbound_dir, ignore_errors=True)

                _ib_purge_status.empty()
                st.success(f"✅ Purged **{_ib_purge_party} / {_ib_purge_volume}** — {len(_ib_opensearch_ids)} documents removed from DB & OS.")
                time.sleep(2)
                st.rerun()
else:
    st.info("No third-party productions have been ingested yet. Use the steps below to import one.")

st.markdown("---")

# --- Ingest form (Steps 1-4) — hidden on closed cases with an explanatory placeholder ---
if _case_closed:
    st.info(
        "📝 Document ingestion is disabled while this matter is closed. "
        "Reopen the case from **Home** to resume ingestion. Previously "
        "ingested productions remain visible above (read-only)."
    )
else:
    # --- UI Step 1: Identify Production ---
    st.header("Step 1: Production Details")
    _ib_col_s1, _ib_col_s2 = st.columns(2)
    _ib_source_party = _ib_col_s1.text_input("Source Party Name (e.g., 'Opposing Counsel A')", placeholder="Opposing Counsel A", key="ib_source_party")
    _ib_production_volume = _ib_col_s2.text_input("Production Volume Name (e.g., 'OCA001')", placeholder="OCA001", key="ib_production_volume")

    _ib_prod_root = st.text_input("Local Path to Production Root Folder", placeholder="C:\\Data\\Cases\\Smith\\Inbound\\OCA001", key="ib_prod_root")

    _ib_halt = False
    if not _ib_source_party or not _ib_production_volume or not _ib_prod_root:
        st.warning("Please fill out the Source Party, Volume, and Root Folder to continue.")
        _ib_halt = True

    # Composite-name safety validation (beta-2.10 Commit 6 Phase C).
    # Runs even when required-field check above already halted — showing the
    # delimiter/length errors alongside the "please fill out" warning lets the
    # user fix everything in one pass rather than iterating one error at a time.
    _ib_id_errors = db_manager.validate_inbound_production_identifiers(
        _ib_source_party, _ib_production_volume
    )
    # Filter out the "is required" messages on fields the user hasn't filled
    # yet — those duplicate the warning above. Show only delimiter/length
    # errors while fields are mid-entry; show everything once values exist.
    _ib_id_errors_to_display = [
        e for e in _ib_id_errors if 'is required' not in e
    ]
    for _ib_err_msg in _ib_id_errors_to_display:
        st.error(f"❌ {_ib_err_msg}")
    if _ib_id_errors:
        _ib_halt = True

    if not _ib_halt and not os.path.isdir(_ib_prod_root):
        st.error("The specified Root Folder does not exist or is not a directory.")
        _ib_halt = True

    # --- Find Load Files ---
    _ib_load_files = []
    _ib_df = None
    if not _ib_halt:
        for _ib_file in os.listdir(_ib_prod_root):
            if _ib_file.lower().endswith('.dat') or _ib_file.lower().endswith('.csv') or _ib_file.lower().endswith('.txt'):
                _ib_load_files.append(_ib_file)

        if not _ib_load_files:
            st.error(f"No valid load files (.dat, .csv, .txt) found in the root of {_ib_prod_root}.")
            _ib_halt = True

    if not _ib_halt:
        # --- UI Step 2: Load File Configuration ---
        st.header("Step 2: Parse Load File")
        _ib_col_lf1, _ib_col_lf2, _ib_col_lf3 = st.columns(3)
        _ib_selected_load_file = _ib_col_lf1.selectbox("Select Load File", _ib_load_files, key="ib_load_file")

        _ib_preset_options = {
            "Concordance Standard": {"sep": "\\x14", "quote": "\\xfe"},
            "Comma Separated (, and \")": {"sep": ",", "quote": "\""},
            "Pipe Separated (| and ^)": {"sep": "|", "quote": "^"},
            "Tab Separated (\\t and none)": {"sep": "\\t", "quote": ""},
            "Custom": {"sep": "", "quote": ""}
        }
        _ib_preset = _ib_col_lf2.selectbox("Format Preset", list(_ib_preset_options.keys()), key="ib_preset")

        _ib_custom_sep = _ib_preset_options[_ib_preset]["sep"]
        _ib_custom_quote = _ib_preset_options[_ib_preset]["quote"]
        if _ib_preset == "Custom":
            _ib_custom_sep = _ib_col_lf3.text_input("Custom Delimiter", value=",", key="ib_custom_sep")
            _ib_custom_quote = _ib_col_lf3.text_input("Custom Quote Char", value="\"", key="ib_custom_quote")

        try:
            _ib_sep_actual = chr(20) if _ib_custom_sep == "\\x14" else ('\t' if _ib_custom_sep == "\\t" else _ib_custom_sep)
            _ib_quote_actual = chr(254) if _ib_custom_quote == "\\xfe" else _ib_custom_quote

            _ib_file_path = os.path.join(_ib_prod_root, _ib_selected_load_file)
            if not _ib_quote_actual:
                _ib_df = pd.read_csv(_ib_file_path, sep=_ib_sep_actual, dtype=str, quoting=3)
            else:
                _ib_df = pd.read_csv(_ib_file_path, sep=_ib_sep_actual, quotechar=_ib_quote_actual, dtype=str)
            _ib_df = _ib_df.fillna("")
        except Exception as e:
            st.error(f"Failed to parse load file: {e}")
            _ib_halt = True

    if not _ib_halt and _ib_df is not None:
        st.success(f"Successfully loaded {len(_ib_df)} rows and {len(_ib_df.columns)} columns.")
        with st.expander("Preview Data", expanded=False):
            st.dataframe(_ib_df.head(10), width='stretch')

        # --- UI Step 3: Column Mapping ---
        st.header("Step 3: Column Mapping")
        st.markdown("Map load file columns to our system fields. Unmapped columns will be stored as dynamic metadata JSON.")

        _ib_lf_columns = ["<Not Mapped>"] + list(_ib_df.columns)

        def _ib_recommend_col(target):
            target_lower = target.lower()
            for c in list(_ib_df.columns):
                if target_lower in c.lower() or c.lower() in target_lower:
                    return _ib_lf_columns.index(c)
            return 0

        _ib_cc1, _ib_cc2, _ib_cc3 = st.columns(3)

        _ib_mapped_fields = {}
        st.subheader("Required Fields")
        _ib_mapped_fields['control_number'] = _ib_cc1.selectbox("Control Number / BegDoc *", _ib_lf_columns, index=_ib_recommend_col("begdoc"), key="ib_map_cn")
        _ib_mapped_fields['group_id'] = _ib_cc2.selectbox("Group Identifier (Family ID)", _ib_lf_columns, index=_ib_recommend_col("group"), key="ib_map_group")
        _ib_mapped_fields['parent_id'] = _ib_cc3.selectbox("Parent Document ID", _ib_lf_columns, index=_ib_recommend_col("parent"), key="ib_map_parent")

        st.subheader("Path Links")
        st.info("These columns should contain the relative paths to the actual files inside the production folder.")
        _ib_mapped_fields['native_path'] = _ib_cc1.selectbox("Native Link", _ib_lf_columns, index=_ib_recommend_col("native"), key="ib_map_native")
        _ib_mapped_fields['image_path'] = _ib_cc2.selectbox("Image/PDF Link (fallback if no native)", _ib_lf_columns, index=_ib_recommend_col("image"), key="ib_map_image")
        _ib_mapped_fields['text_path'] = _ib_cc3.selectbox("Text Link", _ib_lf_columns, index=_ib_recommend_col("text"), key="ib_map_text")

        st.subheader("Standard Metadata")
        _ib_col_m1, _ib_col_m2, _ib_col_m3, _ib_col_m4 = st.columns(4)
        _ib_mapped_fields['file_name'] = _ib_col_m1.selectbox("File Name", _ib_lf_columns, index=_ib_recommend_col("filename"), key="ib_map_fn")
        _ib_mapped_fields['file_extension'] = _ib_col_m2.selectbox("File Extension", _ib_lf_columns, index=_ib_recommend_col("ext"), key="ib_map_ext")
        _ib_mapped_fields['custodian'] = _ib_col_m3.selectbox("Custodian", _ib_lf_columns, index=_ib_recommend_col("custodian"), key="ib_map_cust")
        _ib_mapped_fields['author'] = _ib_col_m4.selectbox("Author", _ib_lf_columns, index=_ib_recommend_col("author"), key="ib_map_author")

        _ib_mapped_fields['email_from'] = _ib_col_m1.selectbox("Email From", _ib_lf_columns, index=_ib_recommend_col("from"), key="ib_map_from")
        _ib_mapped_fields['email_to'] = _ib_col_m2.selectbox("Email To", _ib_lf_columns, index=_ib_recommend_col("to"), key="ib_map_to")
        _ib_mapped_fields['email_cc'] = _ib_col_m3.selectbox("Email CC", _ib_lf_columns, index=_ib_recommend_col("cc"), key="ib_map_cc")
        _ib_mapped_fields['email_bcc'] = _ib_col_m4.selectbox("Email BCC", _ib_lf_columns, index=_ib_recommend_col("bcc"), key="ib_map_bcc")

        _ib_mapped_fields['email_subject'] = _ib_col_m1.selectbox("Email Subject", _ib_lf_columns, index=_ib_recommend_col("subject"), key="ib_map_subj")
        _ib_mapped_fields['date_sent'] = _ib_col_m2.selectbox("Date Sent / Created", _ib_lf_columns, index=_ib_recommend_col("date"), key="ib_map_date")

        if _ib_mapped_fields['control_number'] == "<Not Mapped>":
            st.warning("You must map at least the Control Number field to proceed.")
            _ib_halt = True

    if not _ib_halt and _ib_df is not None:
        # --- UI Step 4: Execution ---
        st.header("Step 4: Execute Ingestion")

        if st.button("🚀 Start Ingestion", type="primary", key="ib_start"):
            # Defense-in-depth: re-validate identifiers on submit. The pre-
            # submit validator above already runs on every rerender and halts
            # Steps 2-4 rendering if errors exist, so under normal UI flow this
            # button is unreachable with invalid inputs. This second check
            # guards against any future code path that bypasses the pre-submit
            # halt (e.g., a programmatic trigger or a refactor that moves the
            # button earlier). Failure here hard-stops the ingest with an
            # explicit error rather than letting invalid data reach the DB.
            _ib_submit_errors = db_manager.validate_inbound_production_identifiers(
                _ib_source_party, _ib_production_volume
            )
            if _ib_submit_errors:
                for _ib_err_msg in _ib_submit_errors:
                    st.error(f"❌ {_ib_err_msg}")
                st.stop()

            if not _ib_es:
                st.error("Cannot ingest without OpenSearch connection. Please configure in the sidebar.")
            else:
                _ib_status_text = st.empty()
                _ib_progress_bar = st.progress(0)

                _ib_inbound_storage_dir = os.path.join(case_folder, "Inbound", _ib_source_party, _ib_production_volume)
                os.makedirs(_ib_inbound_storage_dir, exist_ok=True)

                _ib_total_rows = len(_ib_df)
                _ib_username = st.session_state.get('username', 'unknown')
                _ib_audit = []
                # _ib_conn removed in beta-2.10 Commit 5 — batch upserts now go
                # through db_manager.upsert_inbound_documents_batch() which owns
                # its own connection lifecycle.
                _ib_index_name = os_manager.get_index_name(case_folder)

                _ib_status_text.text("Scanning production folder for image files...")
                _ib_image_lookup = {}
                _ib_image_extensions = {'.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg'}
                for _ib_scan_root, _ib_scan_dirs, _ib_scan_files in os.walk(_ib_prod_root):
                    for _ib_sf in _ib_scan_files:
                        _ib_sf_ext = os.path.splitext(_ib_sf)[1].lower()
                        if _ib_sf_ext in _ib_image_extensions:
                            _ib_sf_key = os.path.splitext(_ib_sf)[0]
                            _ib_image_lookup[_ib_sf_key] = os.path.join(_ib_scan_root, _ib_sf)
                _ib_status_text.text(f"Found {len(_ib_image_lookup)} image files in production folder. Starting ingestion...")

                _ib_mapped_keys = [k for k, v in _ib_mapped_fields.items() if v != "<Not Mapped>"]
                _ib_mapped_vals = [v for k, v in _ib_mapped_fields.items() if v != "<Not Mapped>"]
                _ib_unmapped_columns = [c for c in _ib_df.columns if c not in _ib_mapped_vals]

                _ib_os_batch = []
                _ib_db_batch = []
                _ib_successful_inserts = 0
                _ib_os_errors = []
                _ib_errors = []

                if not _ib_es.indices.exists(index=_ib_index_name):
                    _ib_es.indices.create(index=_ib_index_name, settings={"number_of_shards": 1, "number_of_replicas": 0})

                # Inline INSERT template removed in beta-2.10 Commit 5 — now
                # lives in db_manager as _INBOUND_UPSERT_SQL and is consumed
                # via db_manager.upsert_inbound_documents_batch(). ON CONFLICT
                # preservation set is pinned by tests/test_inbound_db.py.

                def _ib_flush_es(batch):
                    if not batch:
                        return
                    success_count, fail_items = helpers.bulk(_ib_es, batch, raise_on_error=False, raise_on_exception=False)
                    if fail_items:
                        for item in fail_items:
                            action = list(item.keys())[0]
                            detail = item[action]
                            doc_id = detail.get("_id", "unknown")
                            err = detail.get("error", {})
                            reason = err.get("reason", str(err)) if isinstance(err, dict) else str(err)
                            _ib_os_errors.append(f"ES [{doc_id}]: {reason}")

                for _ib_i, _ib_row in _ib_df.iterrows():
                    try:
                        def _ib_get_val(key):
                            if _ib_mapped_fields[key] == "<Not Mapped>": return None
                            return _ib_row.get(_ib_mapped_fields[key], None)

                        _ib_ctrl = _ib_get_val('control_number')
                        if not _ib_ctrl: continue

                        _ib_dyn_meta = {c: str(_ib_row[c]) for c in _ib_unmapped_columns if pd.notna(_ib_row[c]) and _ib_row[c]}
                        _ib_dyn_meta_json = json.dumps(_ib_dyn_meta)

                        _ib_native_rel = _ib_get_val('native_path')
                        _ib_image_rel = _ib_get_val('image_path')
                        _ib_text_rel = _ib_get_val('text_path')

                        _ib_new_full_path = None
                        _ib_extracted_text = ""

                        if _ib_text_rel:
                            _ib_source_text_path = os.path.join(_ib_prod_root, _ib_text_rel)
                            if os.path.exists(_ib_source_text_path):
                                with open(_ib_source_text_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    _ib_extracted_text = f.read()

                        if _ib_native_rel:
                            _ib_source_native_path = os.path.join(_ib_prod_root, _ib_native_rel)
                            if os.path.exists(_ib_source_native_path):
                                _ib_ext = os.path.splitext(_ib_source_native_path)[1].lower()
                                _ib_dest_native_path = os.path.abspath(os.path.join(_ib_inbound_storage_dir, f"{_ib_ctrl}{_ib_ext}"))
                                if not os.path.exists(_ib_dest_native_path):
                                    shutil.copy2(_ib_source_native_path, _ib_dest_native_path)
                                _ib_new_full_path = _ib_dest_native_path

                        if not _ib_new_full_path:
                            _ib_source_image_path = None
                            if _ib_image_rel:
                                _ib_candidate = os.path.join(_ib_prod_root, _ib_image_rel)
                                if os.path.exists(_ib_candidate):
                                    _ib_source_image_path = _ib_candidate
                            if not _ib_source_image_path and _ib_ctrl in _ib_image_lookup:
                                _ib_source_image_path = _ib_image_lookup[_ib_ctrl]
                            if _ib_source_image_path:
                                _ib_ext = os.path.splitext(_ib_source_image_path)[1].lower()
                                _ib_dest_image_path = os.path.abspath(os.path.join(_ib_inbound_storage_dir, f"{_ib_ctrl}{_ib_ext}"))
                                if not os.path.exists(_ib_dest_image_path):
                                    shutil.copy2(_ib_source_image_path, _ib_dest_image_path)
                                _ib_new_full_path = _ib_dest_image_path

                        _ib_record_type = "Document"
                        _ib_file_ext = _ib_get_val('file_extension')
                        if _ib_file_ext and _ib_file_ext.lower() in ['msg', 'eml']:
                            _ib_record_type = "Email"

                        _ib_opensearch_id = os_manager.compute_os_id(_ib_source_party, _ib_production_volume, _ib_ctrl)

                        _ib_params = (
                            _ib_ctrl,
                            _ib_get_val('group_id') or _ib_ctrl,
                            _ib_get_val('parent_id'),
                            _ib_get_val('file_name'),
                            _ib_file_ext,
                            _ib_get_val('custodian'),
                            _ib_get_val('author'),
                            _ib_get_val('email_from'),
                            _ib_get_val('email_to'),
                            _ib_get_val('email_cc'),
                            _ib_get_val('email_bcc'),
                            _ib_get_val('email_subject'),
                            _ib_get_val('date_sent'),
                            _ib_native_rel,
                            _ib_new_full_path,
                            _ib_source_party,
                            _ib_production_volume,
                            _ib_dyn_meta_json,
                            _ib_record_type,
                            1 if _ib_extracted_text else 0,
                            _ib_opensearch_id
                        )
                        _ib_db_batch.append(_ib_params)

                        _ib_es_source = {
                            "control_number": _ib_ctrl,
                            "source_party": _ib_source_party,
                            "production_volume": _ib_production_volume
                        }
                        if _ib_get_val('file_name'): _ib_es_source["filename"] = _ib_get_val('file_name')
                        if _ib_new_full_path: _ib_es_source["path"] = _ib_new_full_path
                        if _ib_extracted_text: _ib_es_source["content"] = _ib_extracted_text
                        if _ib_get_val('group_id'): _ib_es_source["group_id"] = _ib_get_val('group_id')
                        if _ib_get_val('parent_id'): _ib_es_source["parent_id"] = _ib_get_val('parent_id')
                        if _ib_get_val('custodian'): _ib_es_source["custodian"] = _ib_get_val('custodian')
                        if _ib_get_val('email_subject'): _ib_es_source["subject"] = _ib_get_val('email_subject')
                        if _ib_get_val('author'): _ib_es_source["author"] = _ib_get_val('author')
                        _ib_raw_date = _ib_get_val('date_sent')
                        if _ib_raw_date:
                            try:
                                from dateutil import parser as dateparser
                                _ib_parsed_dt = dateparser.parse(_ib_raw_date)
                                _ib_es_source["date"] = _ib_parsed_dt.isoformat()
                            except Exception:
                                _ib_es_source["date_text"] = str(_ib_raw_date)

                        _ib_os_doc = {
                            "_index": _ib_index_name,
                            "_id": _ib_opensearch_id,
                            "_source": _ib_es_source
                        }
                        for k, v in _ib_dyn_meta.items():
                            if k not in _ib_os_doc["_source"] and v:
                                _ib_os_doc["_source"][f"dyn_{k}"] = str(v)

                        _ib_os_batch.append(_ib_os_doc)
                        _ib_successful_inserts += 1
                        _ib_audit.append({
                            "action": "INBOUND_INGESTED", "username": _ib_username,
                            "control_number": _ib_ctrl, "module": "InboundProd",
                            "details": json.dumps({"source_party": _ib_source_party, "production_volume": _ib_production_volume}),
                            "old_value": None, "new_value": None
                        })

                    except Exception as _ib_iter_e:
                        _ib_errors.append(f"Row {_ib_i} ({_ib_ctrl if '_ib_ctrl' in dir() else '?'}): {_ib_iter_e}")

                    if len(_ib_db_batch) >= 500:
                        db_manager.upsert_inbound_documents_batch(case_folder, _ib_db_batch)
                        _ib_db_batch.clear()
                        _ib_flush_es(_ib_os_batch)
                        _ib_os_batch.clear()

                    if _ib_i % 50 == 0:
                        _ib_progress = (_ib_i + 1) / _ib_total_rows
                        _ib_progress_bar.progress(_ib_progress)
                        _ib_status_text.text(f"Processed {_ib_i+1} / {_ib_total_rows} documents...")

                if _ib_db_batch:
                    db_manager.upsert_inbound_documents_batch(case_folder, _ib_db_batch)
                if _ib_os_batch:
                    _ib_flush_es(_ib_os_batch)

                if _ib_audit:
                    db_manager.log_audit_batch(case_folder, _ib_audit)

                # ── Record production_runs row (beta-2.10 Commit 6 Phase B) ──
                # Creates the unified production-history entry for this inbound
                # volume. Placement is AFTER the final batch flush + audit log
                # and BEFORE the success banner — so partial-ingest failures
                # (upsert_inbound_documents_batch raising mid-stream) never
                # reach this line, guaranteeing no production_runs row is
                # created for an incomplete ingest. The row's document_count
                # reflects the actual successful_inserts (not total_rows),
                # and settings_json captures the ingest parameters for
                # future audit/replay.
                try:
                    db_manager.record_production_run(case_folder, {
                        'production_name': db_manager.inbound_production_run_name(
                            _ib_source_party, _ib_production_volume
                        ),
                        'created_at': datetime.utcnow().isoformat() + 'Z',
                        'created_by': _ib_username,
                        'format': 'Native',
                        'mode': 'Inbound Ingest',
                        'document_count': _ib_successful_inserts,
                        'direction': 'inbound',
                        'status': 'finalized',
                        'settings_json': json.dumps({
                            'source_party': _ib_source_party,
                            'production_volume': _ib_production_volume,
                            'load_file': _ib_selected_load_file,
                            'field_mapping': _ib_mapped_fields,
                            'row_count': _ib_total_rows,
                            'error_count': len(_ib_errors),
                        }),
                    })
                    # Dedicated audit entry for the production_runs write
                    # (distinct from the per-document INBOUND_INGESTED entries
                    # already flushed above).
                    db_manager.log_audit(
                        case_folder,
                        "INBOUND_PRODUCTION_RECORDED",
                        username=_ib_username,
                        module="InboundProd",
                        details=json.dumps({
                            'source_party': _ib_source_party,
                            'production_volume': _ib_production_volume,
                            'document_count': _ib_successful_inserts,
                        }),
                    )
                except sqlite3.Error as _ib_rec_err:
                    # Narrow catch — only SQLite-level failures (disk full,
                    # DB locked, integrity violation, connection error) are
                    # absorbed into the non-blocking warning path. Programming
                    # bugs (TypeError, KeyError, etc.) propagate normally so
                    # they aren't swallowed under a "history record failed"
                    # banner.
                    #
                    # The ingest documents + OpenSearch entries are in place
                    # and production-quality; only the history-row side effect
                    # failed. User can recover by re-running the ingest — the
                    # upsert helper is idempotent (ON CONFLICT DO UPDATE on
                    # the three pinned fields) and record_production_run is
                    # INSERT OR REPLACE on production_name, so the re-run
                    # writes the missing row without duplicating documents.
                    st.warning(
                        f"⚠️ Your documents are in place and ingested successfully "
                        f"({_ib_successful_inserts} docs). However, the production "
                        f"history entry could not be recorded: {_ib_rec_err}. "
                        f"**Recovery:** re-run this same ingest (same Source Party, "
                        f"Volume, and load file). It is safe and idempotent — the "
                        f"upsert won't duplicate documents, and the history row "
                        f"will be written on the second attempt."
                    )

                _ib_progress_bar.progress(1.0)
                _ib_status_text.empty()

                st.success(f"✅ Ingestion Complete! {_ib_successful_inserts} documents imported into {_ib_source_party} / {_ib_production_volume}.")
                if _ib_os_errors:
                    with st.expander(f"⚠️ {len(_ib_os_errors)} OpenSearch Indexing Issues", expanded=True):
                        for e in _ib_os_errors[:50]:
                            st.write(e)
                        if len(_ib_os_errors) > 50:
                            st.write(f"...and {len(_ib_os_errors) - 50} more.")
                if _ib_errors:
                    with st.expander(f"⚠️ {len(_ib_errors)} Row Processing Errors", expanded=False):
                        for e in _ib_errors[:100]:
                            st.write(e)
                        if len(_ib_errors) > 100:
                            st.write("...and more.")
