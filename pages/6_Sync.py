# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        6_Sync.py
# version:       1.1.11
# project:       Respondeo eDiscovery Platform
# project_ver:   2.16.0
# last_modified: 2026-06-10 14:59
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import os
import time
import requests
import json
import streamlit as st
import pandas as pd
import db_manager
import auth_manager
import ui_utils
import os_manager
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent.parent / "assets"

# --- Streamlit UI Initialization ---
st.set_page_config(page_title="Respondeo | Filevine Sync", layout="wide", page_icon=str(_ASSETS / "favicon.png"))
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()

if not auth_manager.check_login(): st.stop()
# permission: sync
auth_manager.require_permission('sync')
auth_manager.show_user_info()

case_folder = st.session_state.get('current_case_folder')
if not case_folder:
    st.error("Please select a case in 'Home' first!")
    st.stop()


# --- CASE LIFECYCLE GATE ---


_case_status = db_manager.get_case_status(case_folder)
if _case_status == 'Closed':
    st.warning('🔒 This matter is closed. Write operations are disabled.')
    st.stop()

# Ensure DB schema is up-to-date (adds new columns if missing)
db_manager.init_db(case_folder)

st.title("Module 6: Unified Sync ☁️")
st.write("Push processed documents and metadata to Filevine, local network drives, or third-party cloud storage.")

# ── Search Index Maintenance (Admin only) ─────────────────────────────────
# permission: admin
if auth_manager.has_permission('admin'):
    st.subheader("🔄 Search Index Maintenance")
    st.caption("Rebuild the OpenSearch search index from the case database. "
               "Use this after schema changes or if search filters return unexpected results. "
               "This does not reprocess source files.")

    # Metrics row: SQLite vs OS document counts
    _ri_conn = db_manager.get_connection(case_folder)
    _ri_db_count = _ri_conn.execute(  # db_manager: exempt (dashboard read)
        "SELECT COUNT(*) FROM documents WHERE processing_status IN ('Processed', 'Master')"
    ).fetchone()[0]
    _ri_conn.close()

    _ri_os_count = 0
    _ri_os_status = "Unknown"
    try:
        _ri_client, _ri_msg = os_manager.get_os_client()
        if _ri_client:
            _ri_index = os_manager.get_index_name(case_folder)
            _ri_os_count = _ri_client.count(index=_ri_index)['count']
            _ri_os_status = "Connected"
        else:
            _ri_os_status = _ri_msg
    except Exception as _ri_e:
        _ri_os_status = f"Error: {_ri_e}"

    _ri_m1, _ri_m2, _ri_m3 = st.columns(3)
    _ri_m1.metric("SQLite (Processed)", f"{_ri_db_count:,}")
    _ri_m2.metric("OpenSearch Index", f"{_ri_os_count:,}")
    _ri_delta = _ri_db_count - _ri_os_count
    _ri_m3.metric("Delta", f"{_ri_delta:,}" if _ri_delta == 0 else f"⚠️ {_ri_delta:,}")

    if st.button("🔄 Rebuild Search Index", type="secondary", width='stretch'):
        st.session_state['_reindex_confirm'] = True

    if st.session_state.get('_reindex_confirm'):
        st.warning("This will rebuild the entire search index for this case. "
                   "Search may return incomplete results during the rebuild. Continue?")
        _ri_col_yes, _ri_col_no = st.columns(2)
        if _ri_col_yes.button("✅ Yes, rebuild", width='stretch'):
            del st.session_state['_reindex_confirm']
            _ri_progress = st.progress(0)
            _ri_status_text = st.empty()

            def _ri_progress_cb(current, total):
                _ri_progress.progress(current / total)
                _ri_status_text.text(f"Reindexing: {current:,}/{total:,} documents...")

            _ri_ok, _ri_err, _ri_msgs = os_manager.reindex_from_sqlite(case_folder, progress_callback=_ri_progress_cb)

            db_manager.log_audit(case_folder, "SEARCH_INDEX_REBUILT",
                                 username=st.session_state.get('username', 'unknown'),
                                 module="Sync",
                                 details=f"Reindexed {_ri_ok} docs, {_ri_err} errors")

            if _ri_err:
                st.warning(f"⚠️ Reindex completed with {_ri_err} error(s). {_ri_ok:,} documents indexed.")
                for _ri_m in _ri_msgs[:10]:
                    st.caption(f"  {_ri_m}")
            else:
                st.success(f"✅ Search index rebuilt: {_ri_ok:,} documents indexed.")
            import time
            time.sleep(1.5)
            st.rerun()

        if _ri_col_no.button("❌ Cancel", width='stretch'):
            del st.session_state['_reindex_confirm']
            st.rerun()

    st.divider()

# --- Filevine API Configuration ---
_FILEVINE_TOKEN_URL = "https://identity.filevine.com/connect/token"
_FILEVINE_CONTEXT_URL = "https://api.filevineapp.com/fv-app/v2/utils/GetUserOrgsWithToken"


def get_fv_bearer_token(client_id, client_secret, pat):
    """Obtain the Bearer token using Filevine's PAT exchange."""
    url = _FILEVINE_TOKEN_URL
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "personal_access_token",
        "token": pat,
        "scope": "fv.api.gateway.access tenant filevine.v2.api.* email openid fv.auth.tenant.read"
    }
    response = requests.post(url, headers=headers, data=payload, timeout=15)
    response.raise_for_status()
    return response.json().get('access_token')

def get_fv_context(bearer_token):
    """Retrieve the User ID and Org ID via the Token Context endpoint."""
    url = _FILEVINE_CONTEXT_URL
    headers = {"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
    # The endpoint sometimes requires an empty body
    response = requests.post(url, headers=headers, json={}, timeout=15)
    response.raise_for_status()
    data = response.json()
    return data.get('userId'), data.get('orgId')

def get_fv_headers(bearer_token, user_id, org_id):
    """Build the global header dict required for API Gateway calls."""
    return {
        "Authorization": f"Bearer {bearer_token}",
        "x-fv-userid": str(user_id),
        "x-fv-orgid": str(org_id),
        "Content-Type": "application/json"
    }

def safe_request(method, url, max_retries=3, **kwargs):
    """Helper to execute requests with exponential backoff for transient/rate-limiting errors."""
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code in (401, 403):
                response.raise_for_status() # Raise immediately for Auth failures
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    raise Exception(f"Max retries ({max_retries}) exceeded for {url}")

def get_presigned_url(filename, api_url, headers):
    """
    Step 1: Request a pre-signed AWS S3 URL from Filevine for the physical document upload.
    Returns the pre-signed S3 URL and any required Filevine upload context.
    """
    url = f"{api_url}/core/documents/uploadurl"
    payload = {"filename": filename}
    
    try:
        response = safe_request('POST', url, headers=headers, json=payload, timeout=15)
        data = response.json()
        return data.get('url'), data.get('uploadContext')
    except Exception as e:
        print(f"Error requesting pre-signed URL: {e}")
        return None, None

def upload_to_s3(presigned_url, file_path):
    """
    Step 2: Stream the physical PDF binary directly to the AWS S3 bucket.
    """
    try:
        with open(file_path, 'rb') as f:
            headers = {"Content-Type": "application/octet-stream"}
            for attempt in range(3):
                try:
                    response = requests.put(presigned_url, headers=headers, data=f, timeout=300)
                    response.raise_for_status()
                    return True
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        f.seek(0)
                        continue
                    raise
            return False
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return False

def finalize_fv_document(upload_context, original_filename, project_id, api_url, headers):
    """
    Step 3: Tell Filevine that the S3 upload finished so it can ingest the file into the project.
    Returns the permanent Filevine Document ID.
    """
    url = f"{api_url}/core/documents"
    payload = {
        "projectId": project_id,
        "uploadContext": upload_context,
        "filename": original_filename
    }
    
    try:
        response = safe_request('POST', url, headers=headers, json=payload, timeout=30)
        data = response.json()
        return data.get('id') # The permanent filevine_doc_id
    except Exception as e:
        print(f"Error finalizing document in Filevine: {e}")
        return None

def create_ediscovery_collection_item(fv_doc_id, metadata_row, project_id, collection_selector, api_url, headers):
    """
    Step 4: Map the local e-discovery metadata to Filevine's Customs Editor (Collection endpoint).
    """
    url = f"{api_url}/core/projects/{project_id}/custom/{collection_selector}"
    
    # Map the local SQLite fields to the exact field selectors in Filevine
    payload = {
        "documents": [fv_doc_id], # Attach the newly uploaded document
        "control_number": str(metadata_row.get('control_number') or ""),
        "group_id": str(metadata_row.get('group_id') or ""),
        "parent_id": str(metadata_row.get('parent_id') or ""),
        "record_type": str(metadata_row.get('record_type') or ""),
        "email_from": str(metadata_row.get('email_from') or ""),
        "email_to": str(metadata_row.get('email_to') or ""),
        "email_subject": str(metadata_row.get('email_subject') or ""),
        "date_sent": str(metadata_row.get('date_sent') or "")
    }
    
    try:
        response = safe_request('POST', url, headers=headers, json=payload, timeout=15)
        data = response.json()
        return data.get('id') # The Collection Item ID
    except Exception as e:
        print(f"Error creating Customs Collection Item: {e}")
        return None

def sync_pending_documents(case_folder, api_url, project_id, collection_selector, headers):
    """
    Master sync loop. Processes documents marked as 'Ready_For_Sync' or 'Pending'.
    """
    conn = db_manager.get_connection(case_folder)
    try:
    
        # 1. Fetch documents that need to be synced (e.g., Master records that have been processed)
        # Exclude duplicates or entirely suppressed items
        # db_manager: exempt (sync loop)
        pending_docs = conn.execute("""
            SELECT * FROM documents
            WHERE sync_status = 'Pending'
            AND processing_status NOT LIKE 'Duplicate%' AND processing_status != 'Error'
            LIMIT 50
        """).fetchall()
    
        if not pending_docs:
            print("No pending documents to sync.")
            return 0
        
        success_count = 0
    
        for doc in pending_docs:
            doc_id = doc['id']
            control_num = doc['control_number']
        
            # Assumption: The physical file to upload is the Imaged PDF in the Processed folder
            # For native-only files, this path logic would need to adjust to target the NATIVES folder
            upload_path = os.path.join(case_folder, "Processed", f"{control_num}.pdf")
        
            if not os.path.exists(upload_path):
                 # Fallback to the original path if imaging failed or wasn't attempted
                 upload_path = doc['full_path']
                 if not os.path.exists(upload_path):
                     conn.execute("UPDATE documents SET sync_status='Error: File Missing' WHERE id=?", (doc_id,))  # db_manager: exempt (sync loop)
                     conn.commit()
                     try:
                         db_manager.log_audit(case_folder, "SYNC_ERROR",
                             username=st.session_state.get('username', 'system'),
                             control_number=control_num, module="Sync",
                             details="Error: File Missing", conn=conn)
                     except Exception:
                         pass
                     continue
                 
            filename = os.path.basename(upload_path)
            print(f"Syncing [{control_num}] -> {filename}...")
        
            try:
                # STEP 1: Get Pre-Signed URL
                presigned_url, upload_context = get_presigned_url(filename, api_url, headers)
                if not presigned_url:
                    conn.execute("UPDATE documents SET sync_status='Error: API S3 Auth Failed' WHERE id=?", (doc_id,))  # db_manager: exempt (sync loop)
                    try:
                        db_manager.log_audit(case_folder, "SYNC_ERROR",
                            username=st.session_state.get('username', 'system'),
                            control_number=control_num, module="Sync",
                            details="Error: API S3 Auth Failed", conn=conn)
                    except Exception:
                        pass
                    conn.commit()
                    continue
                
                # STEP 2: Stream AWS Binary
                upload_success = upload_to_s3(presigned_url, upload_path)
                if not upload_success:
                    conn.execute("UPDATE documents SET sync_status='Error: S3 Upload Failed' WHERE id=?", (doc_id,))  # db_manager: exempt (sync loop)
                    try:
                        db_manager.log_audit(case_folder, "SYNC_ERROR",
                            username=st.session_state.get('username', 'system'),
                            control_number=control_num, module="Sync",
                            details="Error: S3 Upload Failed", conn=conn)
                    except Exception:
                        pass
                    conn.commit()
                    continue
                
                # STEP 3: Finalize Document
                fv_doc_id = finalize_fv_document(upload_context, filename, project_id, api_url, headers)
                if not fv_doc_id:
                    conn.execute("UPDATE documents SET sync_status='Error: Finalize Failed' WHERE id=?", (doc_id,))  # db_manager: exempt (sync loop)
                    try:
                        db_manager.log_audit(case_folder, "SYNC_ERROR",
                            username=st.session_state.get('username', 'system'),
                            control_number=control_num, module="Sync",
                            details="Error: Finalize Failed", conn=conn)
                    except Exception:
                        pass
                    conn.commit()
                    continue
                
                # STEP 4: Map Metadata Collection
                fv_collection_id = create_ediscovery_collection_item(fv_doc_id, doc, project_id, collection_selector, api_url, headers)
            
                if fv_collection_id:
                     sync_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                     # db_manager: exempt (sync loop)
                     conn.execute("""
                         UPDATE documents
                         SET sync_status='Synced', filevine_doc_id=?, filevine_collection_id=?, sync_timestamp=?
                         WHERE id=?
                     """, (fv_doc_id, fv_collection_id, sync_timestamp, doc_id))
                     success_count += 1
                     db_manager.log_audit(case_folder, "FILEVINE_PUSH",
                         username=st.session_state.get('username', 'unknown'),
                         control_number=control_num, module="Sync", conn=conn)
                else:
                     conn.execute("UPDATE documents SET sync_status='Error: Collection Map Failed', filevine_doc_id=? WHERE id=?", (fv_doc_id, doc_id))  # db_manager: exempt (sync loop)
                     try:
                         db_manager.log_audit(case_folder, "SYNC_ERROR",
                             username=st.session_state.get('username', 'system'),
                             control_number=control_num, module="Sync",
                             details="Error: Collection Map Failed", conn=conn)
                     except Exception:
                         pass
                 
                # CRIT-8: Wrap commit — if DB update fails after successful API push,
                # warn the user rather than silently allowing a duplicate re-push on next run.
                try:
                    conn.commit()
                except Exception as commit_err:
                    db_manager.log_audit(
                        case_folder, "FILEVINE_PUSH",
                        username=st.session_state.get('username', 'unknown'),
                        control_number=control_num, module="Sync",
                        details=f"WARNING: API push succeeded but DB commit failed: {commit_err}. Document may re-push on next sync."
                    )
                    st.warning(f"⚠️ {control_num}: API push succeeded but local database could not be updated. This document may re-push on the next run.")
            
            except Exception as e:
                err_msg = str(e)
                if "401" in err_msg or "403" in err_msg or "Unauthorized" in err_msg:
                    conn.execute("UPDATE documents SET sync_status='Error: Token Expired' WHERE id=?", (doc_id,))  # db_manager: exempt (sync loop)
                    try:
                        db_manager.log_audit(case_folder, "SYNC_ERROR",
                            username=st.session_state.get('username', 'system'),
                            control_number=control_num, module="Sync",
                            details="Error: Token Expired", conn=conn)
                    except Exception:
                        pass
                else:
                    conn.execute("UPDATE documents SET sync_status=? WHERE id=?", (f"Error: {err_msg[:30]}", doc_id))  # db_manager: exempt (sync loop)
                    try:
                        db_manager.log_audit(case_folder, "SYNC_ERROR",
                            username=st.session_state.get('username', 'system'),
                            control_number=control_num, module="Sync",
                            details=f"Error: {err_msg[:80]}", conn=conn)
                    except Exception:
                        pass
                conn.commit()

        return success_count
    finally:
        conn.close()



# ---------------------------------------------------------------------------
# ANNOTATION EXTRACTION + MARKS WRITER (Phase 9)
# ---------------------------------------------------------------------------

def _annot_extract_to_marks(case_folder, pdf_path, control_number, priv_members, username='system'):
    """
    Scan a PDF for PDF_ANNOT_REDACT annotations (type 12).
    For each annotation:
      - Read subject/content field as the raw privilege label
      - Fuzzy-match to a canonical privilege reason via db_manager
      - Accumulate per-page mark dicts, write to redaction_marks table
      - Apply matched privilege tags to documents.tags
    Returns a list of reconciliation row dicts (one per annotation).
    """
    import fitz as _fitz
    import json as _json_ae

    rows = []
    marks_by_page = {}

    pdoc = None
    try:
        pdoc = _fitz.open(pdf_path)
        for pg_num in range(len(pdoc)):
            page = pdoc[pg_num]
            for annot in page.annots():
                if annot.type[0] != 12:   # PDF_ANNOT_REDACT = 12
                    continue
                raw = (annot.info.get('subject') or annot.info.get('content') or '').strip()
                reason, confidence = db_manager.fuzzy_match_privilege_reason(raw, priv_members)
                rect = annot.rect
                mark = {
                    'pdf_x0': round(rect.x0, 2), 'pdf_y0': round(rect.y0, 2),
                    'pdf_x1': round(rect.x1, 2), 'pdf_y1': round(rect.y1, 2),
                    'reason': reason,
                }
                marks_by_page.setdefault(pg_num, []).append(mark)
                rows.append({
                    'control_number': control_number,
                    'page': pg_num + 1,        # 1-based for display
                    'raw_text': raw or '(no label)',
                    'matched_reason': reason,
                    'confidence': confidence,
                })
    except Exception:
        pass
    finally:
        if pdoc:
            try: pdoc.close()
            except Exception: pass

    if marks_by_page:
        for pg, marks in marks_by_page.items():
            db_manager.save_redaction_marks(
                case_folder, control_number, pg, _json_ae.dumps(marks), username
            )
        _ae_conn = db_manager.get_connection(case_folder)
        try:
            _ae_conn.execute(  # db_manager: exempt (sync loop)
                "UPDATE documents SET redaction_status='Has_Redactions' WHERE control_number=?",
                (control_number,)
            )
            # Apply matched non-orphan reasons as privilege tags
            tags_to_add = list({
                r['matched_reason'] for r in rows
                if not r['matched_reason'].startswith('Redaction:')
            })
            if tags_to_add:
                doc_row = _ae_conn.execute(  # db_manager: exempt (sync loop)
                    "SELECT tags FROM documents WHERE control_number=?", (control_number,)
                ).fetchone()
                existing = [t.strip() for t in (doc_row['tags'] or '').split(',') if t.strip()] if doc_row else []
                merged = list(dict.fromkeys(existing + tags_to_add))
                _ae_conn.execute(  # db_manager: exempt (sync loop)
                    "UPDATE documents SET tags=? WHERE control_number=?",
                    (','.join(merged), control_number)
                )
            _ae_conn.commit()
        finally:
            _ae_conn.close()
        try:
            db_manager.log_audit(case_folder, "SYNC_REDACTION_IMPORTED",
                username=username, control_number=control_number, module="Sync",
                details=_json_ae.dumps({"pages": len(marks_by_page), "tags_added": tags_to_add if tags_to_add else []}))
        except Exception:
            pass

    return rows


# --- Streamlit Presentation Layer ---

conn = db_manager.get_connection(case_folder)

# Load existing user settings from the database
try:
    settings_rows = conn.execute("SELECT setting_key, setting_value FROM case_settings").fetchall()  # db_manager: exempt (dashboard read)
    db_settings = {row['setting_key']: row['setting_value'] for row in settings_rows}
except Exception:
    db_settings = {} # Fallback if table doesn't exist yet on an old case

v_url = db_settings.get('FV_API_URL', 'https://api.filevine.io')
v_proj = db_settings.get('FV_PROJECT_ID', '')
v_client = db_settings.get('FV_CLIENT_ID', '')
v_secret = db_settings.get('FV_CLIENT_SECRET', '')
v_pat = db_settings.get('FV_PAT', '')
v_schema = db_settings.get('FV_COLLECTION_SCHEMA', 'ediscovery_log')
v_network = db_settings.get('NETWORK_DEST_PATH', '')
v_cloud_prov = db_settings.get('CLOUD_PROVIDER', 'Select Provider...')
v_cloud_client = db_settings.get('CLOUD_CLIENT_ID', '')
v_cloud_secret = db_settings.get('CLOUD_CLIENT_SECRET', '')

# --- Main UI Tabs ---
sync_tabs = st.tabs(["🏛️ Filevine", "📁 Network Drives", "☁️ Cloud Storage", "📥 Pull Reviewed (Filevine)"])

with sync_tabs[0]:
    st.header("🔑 Filevine API Config")
    
    with st.form("fv_config_form"):
        FILEVINE_API_URL = st.text_input("API URL", value=v_url)
        FILEVINE_PROJECT_ID = st.text_input("Project ID", value=v_proj)
        
        col_fv1, col_fv2 = st.columns(2)
        with col_fv1:
            FV_CLIENT_ID = st.text_input("Client ID", value=v_client, type="password")
            FV_CLIENT_SECRET = st.text_input("Client Secret", value=v_secret, type="password")
        with col_fv2:
            FV_PAT = st.text_input("Personal Access Token (PAT)", value=v_pat, type="password")
            collection_schema = st.text_input("Customs Collection Name", value=v_schema)
            
        if st.form_submit_button("💾 Save Filevine Settings"):
            updates = [
                ('FV_API_URL', FILEVINE_API_URL),
                ('FV_PROJECT_ID', FILEVINE_PROJECT_ID),
                ('FV_CLIENT_ID', FV_CLIENT_ID),
                ('FV_CLIENT_SECRET', FV_CLIENT_SECRET),
                ('FV_PAT', FV_PAT),
                ('FV_COLLECTION_SCHEMA', collection_schema)
            ]
            db_manager.save_case_settings_batch(case_folder, dict(updates))
            try:
                db_manager.log_audit(case_folder, "SYNC_CONFIG_CHANGED",
                    username=st.session_state.get('username', 'system'),
                    module="Sync",
                    details="Filevine API settings saved")
            except Exception:
                pass
            st.success("Configuration explicitly bounded to this Case Database!")


with sync_tabs[0]:
    st.write("---")
    
    # Get Sync Metrics
    _sync_counts = db_manager.get_sync_status_counts(case_folder)
    total_docs = _sync_counts['total_valid']
    synced_docs = _sync_counts['synced']
    pending_docs = _sync_counts['pending']
    error_docs = _sync_counts['error']

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Valid Documents", total_docs)
    col2.metric("Successfully Synced", synced_docs)
    col3.metric("Pending Queue", pending_docs)
    col4.metric("Sync Errors", error_docs)

    st.write("---")
    
    if st.button("🚀 Start Data Sync to Filevine (Batch of 50)", width='stretch'):
        if not (FILEVINE_PROJECT_ID and FV_CLIENT_ID and FV_CLIENT_SECRET and FV_PAT):
            st.error("Please provide your Filevine Project ID and API credentials in the setup block above.")
        elif pending_docs == 0:
            st.info("The sync queue is empty! All valid documents have been uploaded.")
        else:
            auth_success = False
            with ui_utils.lottie_spinner("Authenticating with Filevine API Gateway..."):
                try:
                    bearer_token = get_fv_bearer_token(FV_CLIENT_ID, FV_CLIENT_SECRET, FV_PAT)
                    user_id, org_id = get_fv_context(bearer_token)
                    fv_headers = get_fv_headers(bearer_token, user_id, org_id)
                    auth_success = True
                except Exception as e:
                    st.error("Authentication Failed: could not connect to Filevine API. Check credentials and network connectivity.")
                    
            if auth_success:
                with ui_utils.lottie_spinner("Initiating secure upload to AWS S3 and mapping metadata to Filevine..."):
                    synced_count = sync_pending_documents(case_folder, FILEVINE_API_URL, FILEVINE_PROJECT_ID, collection_schema, fv_headers)
                    
                if synced_count > 0:
                    st.success(f"Successfully pushed {synced_count} documents to Filevine!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Sync pass completed, but 0 documents were finalized. Check the logs for API errors.")

    st.write("### 📉 Sync Error Log")
    error_df = pd.DataFrame(db_manager.get_sync_error_details(case_folder))
    st.dataframe(error_df, width='stretch')

    if not error_df.empty:
        if st.button("🔄 Retry Failed Syncs"):
            db_manager.retry_sync_errors(case_folder)
            try:
                db_manager.log_audit(case_folder, "SYNC_RETRY",
                    username=st.session_state.get('username', 'system'),
                    module="Sync",
                    details=f"Retried {len(error_df)} failed sync(s)")
            except Exception:
                pass
            st.success("Requeued all failed syncs! Click 'Start Data Sync' to try again.")
            time.sleep(1)
            st.rerun()

with sync_tabs[1]:
    st.header("📁 Local / Network Folder Sync (BYOS)")
    st.caption(
        "Copy processed PDFs to any local or mapped network folder — OneDrive, Google Drive sync folder, "
        "Dropbox, Z: drive, etc. Reviewers mark documents externally (Adobe, PowerPDF) then you pull them back."
    )

    # ── Settings ──────────────────────────────────────────────────────
    with st.expander("⚙️ Sync Folder Settings", expanded=not bool(v_network)):
        with st.form("byos_config_form"):
            byos_path = st.text_input(
                "Destination Folder Path",
                value=v_network,
                placeholder=r"X:\Cases\SMITH_v_JONES\Review  or  C:\Users\you\OneDrive\Cases\Review"
            )
            byos_subfolders = st.checkbox(
                "Organize by Custodian (create one subfolder per custodian)",
                value=True,
                help="e.g. Destination/Smith_John/ABC-000001.pdf"
            )
            if st.form_submit_button("💾 Save BYOS Settings"):
                db_manager.save_case_settings_batch(case_folder, {
                    'NETWORK_DEST_PATH': byos_path,
                    'BYOS_SUBFOLDERS': '1' if byos_subfolders else '0',
                })
                try:
                    db_manager.log_audit(case_folder, "SYNC_CONFIG_CHANGED",
                        username=st.session_state.get('username', 'system'),
                        module="Sync",
                        details=f"BYOS settings saved (path={byos_path}, subfolders={'1' if byos_subfolders else '0'})")
                except Exception:
                    pass
                st.success("✅ Settings saved to case database.")
    
    byos_path = db_settings.get('NETWORK_DEST_PATH', v_network)
    byos_subfolders = db_settings.get('BYOS_SUBFOLDERS', '1') == '1'

    # ── Push Status Metrics ────────────────────────────────────────────
    _byos = db_manager.get_byos_status_counts(case_folder)
    total_pushable = _byos['total_pushable']
    already_pushed = _byos['already_pushed']
    byos_pulled = _byos['pulled']
    byos_redactions = _byos['redactions']

    bm1, bm2, bm3, bm4 = st.columns(4)
    bm1.metric("Pushable Docs", f"{total_pushable:,}")
    bm2.metric("Pushed to Folder", f"{already_pushed:,}")
    bm3.metric("Pulled Back", f"{byos_pulled:,}")
    bm4.metric("Has Redactions", f"{byos_redactions:,}")

    st.markdown("---")
    push_tab, pull_tab = st.tabs(["🚀 Push to Folder", "📥 Pull Reviewed Back"])

    # ── PUSH ───────────────────────────────────────────────────────────────
    with push_tab:
        import shutil
        st.caption("Copy processed PDFs to the sync folder for external review and redaction marking.")

        push_scope = st.radio(
            "Which documents to push?",
            ["All processed (not yet pushed)", "All processed (re-push everything)", "Specific custodian"],
            horizontal=True
        )

        push_custodian = None
        if push_scope == "Specific custodian":
            cust_conn = db_manager.get_connection(case_folder)
            all_custodians = [r[0] for r in cust_conn.execute(  # db_manager: exempt (dashboard read)
                "SELECT DISTINCT custodian FROM documents WHERE processing_status IN ('Processed','Master') "
                "AND custodian IS NOT NULL ORDER BY custodian"
            ).fetchall()]
            cust_conn.close()
            push_custodian = st.selectbox("Custodian", all_custodians)

        if st.button("🚀 Push to Folder", type="primary", width='stretch', disabled=not byos_path):
            if not byos_path or not os.path.isdir(byos_path):
                st.error(f"Destination folder does not exist: `{byos_path}`")
            else:
                push_conn = db_manager.get_connection(case_folder)
                try:
                    query = "SELECT control_number, file_name, custodian FROM documents WHERE processing_status IN ('Processed','Master')"
                    params = []
                    if push_scope == "All processed (not yet pushed)":
                        query += " AND (byos_pushed_at IS NULL OR byos_pushed_at = '')"
                    if push_custodian:
                        query += " AND custodian = ?"
                        params.append(push_custodian)
                    docs_to_push = push_conn.execute(query, params).fetchall()  # db_manager: exempt (dynamic query)

                    if not docs_to_push:
                        st.info("Nothing to push with current filter.")
                    else:
                        progress = st.progress(0)
                        status_msg = st.empty()
                        pushed_ok = 0
                        push_errors = []
                        now_ts = time.strftime('%Y-%m-%d %H:%M:%S')

                        for i, doc in enumerate(docs_to_push):
                            cn = doc['control_number']
                            cust = (doc['custodian'] or 'Unknown').replace('/', '_').replace('\\', '_')
                            src = os.path.join(case_folder, 'Processed', f'{cn}.pdf')
                            if not os.path.exists(src):
                                push_errors.append(f"{cn}: source PDF not found")
                                continue
                            # CRIT-9: Path traversal guard — custodian strings must not escape byos_path
                            dest_dir = os.path.join(byos_path, cust) if byos_subfolders else byos_path
                            dest_dir_real = os.path.realpath(dest_dir)
                            byos_root_real = os.path.realpath(byos_path)
                            if not dest_dir_real.startswith(byos_root_real + os.sep) and dest_dir_real != byos_root_real:
                                push_errors.append(f"{cn}: path traversal rejected (custodian value escaped BYOS root)")
                                continue
                            dest = os.path.realpath(os.path.join(dest_dir, f'{cn}.pdf'))
                            if not dest.startswith(byos_root_real + os.sep):
                                push_errors.append(f"{cn}: path traversal rejected (destination escaped BYOS root)")
                                continue
                            os.makedirs(dest_dir_real, exist_ok=True)
                            try:
                                shutil.copy2(src, dest)
                                push_conn.execute(  # db_manager: exempt (sync loop)
                                    "UPDATE documents SET byos_pushed_at=? WHERE control_number=?",
                                    (now_ts, cn)
                                )
                                pushed_ok += 1
                            except Exception as ex:
                                push_errors.append(f"{cn}: {ex}")
                            progress.progress((i + 1) / len(docs_to_push))
                            status_msg.text(f"Copying {i+1}/{len(docs_to_push)}: {cn}")
                            push_conn.commit()  # per-iteration: release the write lock so concurrent sessions don't queue behind the full copy loop (Flag #32)

                        db_manager.log_audit(
                            case_folder, "BYOS_PUSH",
                            username=st.session_state.get("username"),
                            module="Sync",
                            details=json.dumps({"pushed": pushed_ok, "errors": len(push_errors), "scope": push_scope})
                        )
                        progress.empty()
                        status_msg.empty()
                        st.success(f"✅ Pushed {pushed_ok} documents to `{byos_path}`.")
                        if push_errors:
                            with st.expander(f"⚠️ {len(push_errors)} errors"):
                                for e in push_errors:
                                    st.text(e)
                        st.rerun()
                finally:
                    push_conn.close()

        if not byos_path:
            st.info("⬅️ Configure a destination folder in Settings above first.")

    # ── PULL ──────────────────────────────────────────────────────────────────
    with pull_tab:
        st.caption(
            "Scan the sync folder for modified PDFs returned by reviewers. "
            "Redaction annotations are extracted into the redaction engine and privilege tags are applied."
        )
        import_tags = st.checkbox(
            "Import redaction annotation text as privilege tags",
            value=True,
            help="Reads each annotation subject/content field and fuzzy-matches to your privilege tag categories."
        )

        if st.button("📥 Scan & Pull Reviewed Documents", type="primary", width='stretch', disabled=not byos_path):
            if not byos_path or not os.path.isdir(byos_path):
                st.error(f"Sync folder does not exist: `{byos_path}`")
            else:
                import shutil as _byos_shutil
                reviewed_dir = os.path.join(case_folder, 'Reviewed')
                os.makedirs(reviewed_dir, exist_ok=True)
                priv_members = db_manager.get_privilege_tag_members(case_folder)
                pull_conn = db_manager.get_connection(case_folder)
                try:
                    progress = st.progress(0)
                    status_msg = st.empty()

                    all_pdfs = []
                    for root, _, files in os.walk(byos_path):
                        for fn in files:
                            if fn.lower().endswith('.pdf'):
                                all_pdfs.append(os.path.join(root, fn))

                    pulled_ok = 0
                    has_redact = 0
                    all_recon_rows = []
                    now_ts = time.strftime('%Y-%m-%d %H:%M:%S')
                    _uname = st.session_state.get('username', 'system')

                    for i, pdf_path in enumerate(all_pdfs):
                        cn = os.path.splitext(os.path.basename(pdf_path))[0]
                        doc_row = pull_conn.execute(  # db_manager: exempt (sync loop)
                            "SELECT id FROM documents WHERE control_number=?", (cn,)
                        ).fetchone()
                        if not doc_row:
                            progress.progress((i + 1) / max(len(all_pdfs), 1))
                            continue

                        dest = os.path.join(reviewed_dir, f'{cn}.pdf')
                        _byos_shutil.copy2(pdf_path, dest)

                        if import_tags:
                            recon_rows = _annot_extract_to_marks(case_folder, dest, cn, priv_members, _uname)
                            if recon_rows:
                                has_redact += 1
                                all_recon_rows.extend(recon_rows)
                            elif scan_for_redactions(dest) > 0:
                                pull_conn.execute(  # db_manager: exempt (sync loop)
                                    "UPDATE documents SET redaction_status='Has_Redactions' WHERE id=?",
                                    (doc_row['id'],)
                                )
                                has_redact += 1
                        else:
                            if scan_for_redactions(dest) > 0:
                                pull_conn.execute(  # db_manager: exempt (sync loop)
                                    "UPDATE documents SET redaction_status='Has_Redactions' WHERE id=?",
                                    (doc_row['id'],)
                                )
                                has_redact += 1

                        pull_conn.execute(  # db_manager: exempt (sync loop)
                            "UPDATE documents SET byos_pulled_at=? WHERE id=?",
                            (now_ts, doc_row['id'])
                        )
                        pull_conn.commit()  # per-iteration: release the write lock before the next iteration's _annot_extract_to_marks writer acquires it (Flag #32)
                        pulled_ok += 1
                        progress.progress((i + 1) / max(len(all_pdfs), 1))
                        status_msg.text(f"Processing {i+1}/{len(all_pdfs)}: {cn}")

                    db_manager.log_audit(
                        case_folder, "BYOS_PULL",
                        username=st.session_state.get("username"),
                        module="Sync",
                        details=json.dumps({"pulled": pulled_ok, "has_redact": has_redact})
                    )
                    progress.empty()
                    status_msg.empty()

                    st.success(f"✅ {pulled_ok} documents pulled. {has_redact} had redaction marks.")
                    if all_recon_rows:
                        st.session_state['_byos_recon_rows'] = all_recon_rows
                    db_manager.log_audit(case_folder, 'FILEVINE_PULL',
                        username=st.session_state.get('username', 'system'), module='Sync')
                    st.rerun()
                finally:
                    pull_conn.close()

        if not byos_path:
            st.info("⬅️ Configure a sync folder in Settings above first.")

        # ── 📋 Annotation Reconciliation (persists after pull via session_state) ───────
        _recon_rows = st.session_state.get('_byos_recon_rows', [])
        if _recon_rows:
            _priv_opts = db_manager.get_privilege_tag_members(case_folder)
            _orphan_opts = sorted({r['matched_reason'] for r in _recon_rows if r['matched_reason'].startswith('Redaction:')})
            _all_reason_opts = sorted(set(_priv_opts)) + _orphan_opts

            with st.expander("📋 Annotation Reconciliation", expanded=True):
                st.caption(
                    f"{len(_recon_rows)} annotation(s) extracted from pulled documents. "
                    "Override any incorrect privilege matches, then click **Apply Overrides** or export for attorney sign-off."
                )
                import io as _recon_io
                _recon_df = pd.DataFrame(_recon_rows)[['control_number', 'page', 'raw_text', 'matched_reason', 'confidence']]
                _recon_df.columns = ['Control #', 'Page', 'Raw Annotation Text', 'Matched Reason', 'Confidence']

                _edited_df = st.data_editor(
                    _recon_df,
                    column_config={
                        'Matched Reason': st.column_config.SelectboxColumn(
                            'Matched Reason',
                            options=_all_reason_opts,
                            required=True
                        ),
                    },
                    disabled=['Control #', 'Page', 'Raw Annotation Text', 'Confidence'],
                    width='stretch',
                    hide_index=True,
                    key='_byos_recon_editor'
                )

                _rc1, _rc2, _rc3 = st.columns([2, 2, 1])
                with _rc1:
                    if st.button("✅ Apply Overrides", key="_byos_apply_overrides", width='stretch'):
                        import json as _json_ov2
                        for _oi, _orig in enumerate(_recon_rows):
                            _new_reason = _edited_df.iloc[_oi]['Matched Reason']
                            if _new_reason != _orig['matched_reason']:
                                _pg0 = _orig['page'] - 1
                                _ex_json = db_manager.get_redaction_marks(
                                    case_folder, _orig['control_number'], _pg0
                                )
                                if _ex_json:
                                    _marks = _json_ov2.loads(_ex_json)
                                    for _m in _marks:
                                        if _m.get('reason') == _orig['matched_reason']:
                                            _m['reason'] = _new_reason
                                    db_manager.save_redaction_marks(
                                        case_folder, _orig['control_number'], _pg0,
                                        _json_ov2.dumps(_marks),
                                        st.session_state.get('username', 'system')
                                    )
                        st.session_state.pop('_byos_recon_rows', None)
                        try:
                            db_manager.log_audit(case_folder, "SYNC_REDACTION_OVERRIDE",
                                username=st.session_state.get('username', 'system'), module="Sync",
                                details=_json_ov2.dumps({"overrides_applied": True}))
                        except Exception:
                            pass
                        st.success("✅ Overrides applied to redaction marks.")
                        st.rerun()
                with _rc2:
                    _xl_buf = _recon_io.BytesIO()
                    with pd.ExcelWriter(_xl_buf, engine='openpyxl') as _xl_wr:
                        _recon_df.to_excel(_xl_wr, index=False, sheet_name='Reconciliation')
                    _xl_buf.seek(0)
                    st.download_button(
                        "⬇️ Export Coding Sheet",
                        data=_xl_buf.read(),
                        file_name=f"{os.path.basename(case_folder)}_ANNOTATION_RECONCILIATION.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="_byos_export_coding",
                        width='stretch'
                    )
                with _rc3:
                    if st.button("✕ Dismiss", key="_byos_dismiss_recon", width='stretch'):
                        st.session_state.pop('_byos_recon_rows', None)
                        st.rerun()


with sync_tabs[2]:
    st.header("☁️ Cloud Storage Sync")
    st.write("Export documents to third-party cloud storage providers.")
    
    with st.form("cloud_config_form"):
        provider_options = ["Select Provider...", "Google Drive", "DropBox", "Box", "OneDrive"]
        try:
            prov_index = provider_options.index(v_cloud_prov)
        except ValueError:
            prov_index = 0
            
        provider = st.selectbox("Select Provider", provider_options, index=prov_index)
        client_id_cloud = st.text_input("Cloud Client ID", value=v_cloud_client)
        client_secret_cloud = st.text_input("Cloud Client Secret", value=v_cloud_secret, type="password")
        
        if st.form_submit_button("💾 Save Cloud Settings"):
            updates = [
                ('CLOUD_PROVIDER', provider),
                ('CLOUD_CLIENT_ID', client_id_cloud),
                ('CLOUD_CLIENT_SECRET', client_secret_cloud)
            ]
            db_manager.save_case_settings_batch(case_folder, dict(updates))
            try:
                db_manager.log_audit(case_folder, "SYNC_CONFIG_CHANGED",
                    username=st.session_state.get('username', 'system'),
                    module="Sync",
                    details=f"Cloud storage settings saved (provider={provider})")
            except Exception:
                pass
            st.success("Cloud Storage configuration saved!")
    
    if provider != "Select Provider...":
        if st.button(f"🚀 Sync to {provider}", width='stretch'):
            st.info(f"{provider} integration logic coming soon in v1.1. 🚧")

with sync_tabs[3]:
    st.header("📥 Pull Reviewed Documents from Filevine")
    st.write("After review and redaction marking in Filevine, pull documents back for production.")

def batch_download_fv_documents(doc_ids, api_url, headers):
    """
    Request pre-signed S3 download URLs for a list of Filevine Document IDs.
    Uses the Filevine v2 Batch Document Download endpoint.
    Returns dict mapping DocID -> DownloadLink.
    """
    url = f"{api_url}/fv-app/v2/Documents/batch/download"
    payload = [{"DocID": did} for did in doc_ids]
    try:
        response = safe_request('POST', url, headers=headers, json=payload, timeout=60)
        results = response.json()
        return {item['DocID']: item['DownloadLink'] for item in results if 'DownloadLink' in item}
    except Exception as e:
        print(f"Error requesting batch download URLs: {e}")
        return {}

def download_from_s3_url(download_url):
    """Download binary content from a pre-signed S3 URL."""
    try:
        response = requests.get(download_url, timeout=300)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"Error downloading from S3: {e}")
        return None

def scan_for_redactions(pdf_path):
    """Scan a PDF for redaction annotations. Returns count of pages with marks."""
    doc = None
    try:
        import fitz
        doc = fitz.open(pdf_path)
        marked_pages = 0
        for page_num in range(len(doc)):
            page = doc[page_num]
            annots = page.annots()
            if annots:
                for annot in annots:
                    if annot.type[0] == 12:  # fitz.PDF_ANNOT_REDACT = 12
                        marked_pages += 1
                        break
        return marked_pages
    except Exception as e:
        print(f"Error scanning {pdf_path}: {e}")
        return 0
    finally:
        if doc:
            try: doc.close()
            except Exception: pass

def pull_reviewed_documents(case_folder, api_url, headers):
    """Pull back synced documents from Filevine, scan for redaction marks."""
    reviewed_path = os.path.join(case_folder, "Reviewed")
    os.makedirs(reviewed_path, exist_ok=True)
    
    conn = db_manager.get_connection(case_folder)
    try:
    
        # Get all synced documents that haven't been pulled back yet
        # db_manager: exempt (filevine push/pull)
        synced_docs = conn.execute("""
            SELECT * FROM documents
            WHERE sync_status = 'Synced'
            AND filevine_doc_id IS NOT NULL
            AND (review_pulled_at IS NULL OR review_pulled_at = '')
        """).fetchall()
    
        if not synced_docs:
            return 0, 0
    
        # Batch request all download URLs at once
        doc_id_map = {doc['filevine_doc_id']: doc for doc in synced_docs}
        download_links = batch_download_fv_documents(list(doc_id_map.keys()), api_url, headers)
    
        pull_count = 0
        redact_count = 0
    
        for fv_doc_id, download_url in download_links.items():
            doc = doc_id_map.get(fv_doc_id)
            if not doc:
                continue
        
            control_num = doc['control_number']
        
            # Download binary from S3
            file_bytes = download_from_s3_url(download_url)
            if not file_bytes:
                continue
        
            # Save to Reviewed/ folder
            reviewed_file = os.path.join(reviewed_path, f"{control_num}.pdf")
            with open(reviewed_file, 'wb') as f:
                f.write(file_bytes)
        
            # Scan for redaction annotations
            marked_pages = scan_for_redactions(reviewed_file)
            pull_timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        
            if marked_pages > 0:
                conn.execute(  # db_manager: exempt (filevine push/pull)
                    "UPDATE documents SET redaction_status='Has_Redactions', review_pulled_at=? WHERE id=?",
                    (pull_timestamp, doc['id'])
                )
                redact_count += 1
            else:
                conn.execute(  # db_manager: exempt (filevine push/pull)
                    "UPDATE documents SET redaction_status='Reviewed', review_pulled_at=? WHERE id=?",
                    (pull_timestamp, doc['id'])
                )
        
            pull_count += 1
            conn.commit()
            db_manager.log_audit(case_folder, "FILEVINE_PULL",
                username=st.session_state.get('username', 'unknown'),
                control_number=control_num, module="Sync")

    finally:
        conn.close()
    return pull_count, redact_count

# Pull-back metrics
conn2 = db_manager.get_connection(case_folder)
pulled_count = conn2.execute("SELECT COUNT(*) FROM documents WHERE review_pulled_at IS NOT NULL").fetchone()[0]  # db_manager: exempt (dashboard read)
has_redactions = conn2.execute("SELECT COUNT(*) FROM documents WHERE redaction_status = 'Has_Redactions'").fetchone()[0]  # db_manager: exempt (dashboard read)
reviewed_clean = conn2.execute("SELECT COUNT(*) FROM documents WHERE redaction_status = 'Reviewed'").fetchone()[0]  # db_manager: exempt (dashboard read)
conn2.close()

pcol1, pcol2, pcol3 = st.columns(3)
pcol1.metric("Pulled Back", pulled_count)
pcol2.metric("Has Redactions", has_redactions)
pcol3.metric("Reviewed (Clean)", reviewed_clean)

if st.button("📥 Pull Reviewed Documents from Filevine", width='stretch'):
    if not (FILEVINE_PROJECT_ID and FV_CLIENT_ID and FV_CLIENT_SECRET and FV_PAT):
        st.error("Please provide your Filevine API credentials in the sidebar.")
    elif synced_docs == 0:
        st.info("No synced documents ready for pull-back.")
    else:
        pull_auth_success = False
        with ui_utils.lottie_spinner("Authenticating with Filevine..."):
            try:
                bearer_token = get_fv_bearer_token(FV_CLIENT_ID, FV_CLIENT_SECRET, FV_PAT)
                user_id, org_id = get_fv_context(bearer_token)
                fv_headers = get_fv_headers(bearer_token, user_id, org_id)
                pull_auth_success = True
            except Exception as e:
                st.error("Authentication Failed: could not connect to Filevine API. Check credentials and network connectivity.")

        if pull_auth_success:
            with ui_utils.lottie_spinner("Downloading reviewed documents and scanning for redaction marks..."):
                pulled, redacted = pull_reviewed_documents(case_folder, FILEVINE_API_URL, fv_headers)
            
            if pulled > 0:
                st.success(f"✅ Pulled {pulled} documents. {redacted} have redaction marks.")
                time.sleep(1)
                st.rerun()
            else:
                st.info("No new documents to pull. All synced documents have already been retrieved.")
                st.info("No new documents to pull. All synced documents have already been retrieved.")


conn.close()
