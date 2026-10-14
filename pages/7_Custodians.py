# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        7_Custodians.py
# version:       1.3.6
# project:       Respondeo eDiscovery Platform
# project_ver:   2.12.0
# last_modified: 2026-04-28 14:30
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import os
import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import db_manager
import auth_manager
import ui_utils
from pathlib import Path

# ── Plotly Chart Theme ────────────────────────────────────────────────────────
_CHART_COLORS = {
    'primary': '#2b6cb0',
    'secondary': '#4299e1',
    'success': '#38a169',
    'warning': '#dd6b20',
    'danger': '#e53e3e',
    'muted': '#a0aec0',
    'purple': '#805ad5',
    'teal': '#319795',
}

def _apply_chart_layout(fig, height=None):
    """Apply consistent layout to all Plotly figures."""
    fig.update_layout(
        font_family="system-ui, -apple-system, sans-serif",
        font_size=12,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=40, b=20),
        height=height,
    )
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.06)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.06)')
    return fig

_ASSETS = Path(__file__).resolve().parent.parent / "assets"

# ── Streamlit UI Initialization ──────────────────────────────────────────────
st.set_page_config(page_title="Respondeo | Custodians", layout="wide", page_icon=str(_ASSETS / "favicon.png"))
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()

if not auth_manager.check_login(): st.stop()
# permission: custodian_management
auth_manager.require_permission('custodian_management')
auth_manager.show_user_info()

case_folder = st.session_state.get('current_case_folder')
if not case_folder:
    st.error("Please select a case in 'Home' first!")
    st.stop()

db_manager.init_db(case_folder)

# Case lifecycle gate
_case_closed = db_manager.get_case_status(case_folder) == 'Closed'
if _case_closed:
    st.warning('🔒 This matter is closed. Write operations are disabled.')

# Sync custodians from documents table (idempotent)
db_manager.sync_custodians_from_documents(case_folder)

st.title("Module 7: Custodian Management 👤")

# ═══════════════════════════════════════════════════════════════════════════════
# CUSTODIAN INVENTORY CHART
# ═══════════════════════════════════════════════════════════════════════════════

conn = db_manager.get_connection(case_folder)

_inv_df = pd.DataFrame(db_manager.get_custodian_inventory_df_data(case_folder))

custodian_names = _inv_df['custodian'].tolist()

if custodian_names:
    # Inventory bar chart
    _inv_sorted = _inv_df.sort_values('doc_count', ascending=True)
    _hold_color_map = {
        'Active': _CHART_COLORS['success'],
        'Released': _CHART_COLORS['warning'],
        'Expired': _CHART_COLORS['danger'],
        'None': _CHART_COLORS['muted'],
    }
    _inv_colors = [_hold_color_map.get(h or 'None', _CHART_COLORS['muted']) for h in _inv_sorted['hold_status']]

    _inv_fig = go.Figure(go.Bar(
        y=_inv_sorted['custodian'],
        x=_inv_sorted['doc_count'],
        orientation='h',
        marker_color=_inv_colors,
        hovertemplate='%{y}<br>Documents: %{x:,}<extra></extra>',
        text=[f'{v:,}' for v in _inv_sorted['doc_count']],
        textposition='outside',
    ))
    _inv_fig = _apply_chart_layout(_inv_fig, height=max(250, len(_inv_sorted) * 28))
    _inv_fig.update_layout(
        title=dict(text='Documents per Custodian', font_size=14),
        xaxis_title='Documents',
        showlegend=False,
    )
    st.plotly_chart(_inv_fig, width='stretch')

    # ═══════════════════════════════════════════════════════════════════════════
    # CUSTODIAN DETAIL PANEL
    # ═══════════════════════════════════════════════════════════════════════════

    _sel_cust = st.selectbox("Select Custodian", custodian_names, key="cust_selector")

    if _sel_cust:
        _cust_row = db_manager.get_custodian(case_folder, _sel_cust)

        if _cust_row:
            _detail_left, _detail_right = st.columns(2)

            with _detail_left:
                st.markdown("**📋 Custodian Profile**")
                if _case_closed:
                    st.caption("Fields are read-only because this matter is closed.")
                _title = st.text_input("Title", value=_cust_row['title'] or '', key=f"cust_title_{_sel_cust}",
                                       disabled=_case_closed)
                _dept = st.text_input("Department", value=_cust_row['department'] or '', key=f"cust_dept_{_sel_cust}",
                                      disabled=_case_closed)
                _email = st.text_input("Email", value=_cust_row['email'] or '', key=f"cust_email_{_sel_cust}",
                                       disabled=_case_closed)
                _notes = st.text_area("Notes", value=_cust_row['notes'] or '', key=f"cust_notes_{_sel_cust}",
                                      height=100, disabled=_case_closed)

            with _detail_right:
                st.markdown("**📊 Collection Summary**")
                _cust_stats = db_manager.get_custodian_doc_stats(case_folder, _sel_cust)
                _doc_count = _cust_stats['doc_count']
                _email_count = _cust_stats['email_count']

                st.metric("Documents", f"{_doc_count:,}")
                st.metric("Emails", f"{_email_count:,}")
                def _fmt_date_short(val):
                    if not val: return 'N/A'
                    return str(val)[:10]
                st.caption(f"Date range: {_fmt_date_short(_cust_stats['date_min'])} — {_fmt_date_short(_cust_stats['date_max'])}")

                # Data sources
                _existing_sources = json.loads(_cust_row['data_sources'] or '[]')
                _source_options = ['Exchange Mailbox', 'Network Share', 'Laptop', 'Mobile Device',
                                   'Cloud Storage', 'Paper Records', 'Backup Tape', 'Third-Party System', 'Other']
                # Combine options with any custom entries already saved
                _all_options = sorted(set(_source_options + _existing_sources))
                _sources = st.multiselect("Data Sources", _all_options,
                                          default=_existing_sources, key=f"cust_sources_{_sel_cust}",
                                          disabled=_case_closed)

            # permission: custodian_profile_update
            if not _case_closed and auth_manager.has_permission('custodian_management'):
                if st.button("💾 Save Custodian Profile", width='stretch'):
                    db_manager.update_custodian_fields(
                        case_folder, _sel_cust,
                        title=_title, department=_dept, email=_email,
                        notes=_notes, data_sources=json.dumps(_sources))
                    db_manager.log_audit(case_folder, "CUSTODIAN_UPDATED",
                        username=st.session_state.get('username'),
                        module="Custodians",
                        details=json.dumps({"custodian": _sel_cust, "fields_updated": True}))
                    st.success(f"✅ Profile updated for {_sel_cust}")
                    st.rerun()

            # ═══════════════════════════════════════════════════════════════════
            # OPERATIONS TABS
            # ═══════════════════════════════════════════════════════════════════

            # permission: custodian_management (inline check — defense-in-depth)
            if not _case_closed and auth_manager.has_permission('custodian_management'):
                st.divider()
                st.subheader("🔧 Operations")
                rename_tab, merge_tab, reassign_tab, collections_tab, scope_tab = st.tabs(
                    ["✏️ Rename", "🔀 Merge", "📦 Reassign", "📁 Collections", "📋 Collection Scope"]
                )

                # ── TAB 1: RENAME ─────────────────────────────────────────────
                with rename_tab:
                    st.markdown("**Rename a custodian across all documents.**")
                    st.caption("This updates the custodian name in every document record, the custodian registry, "
                               "and the sidebar tree. The old name is recorded in the audit trail.")

                    _rename_from = st.selectbox("Current Name", custodian_names, key="rename_from")
                    _rename_to = st.text_input("New Name", placeholder="e.g. Jane Smith", key="rename_to")

                    if _rename_from and _rename_to and _rename_to.strip() and _rename_to.strip() != _rename_from:
                        _rename_to = _rename_to.strip()
                        _exists = db_manager.get_custodian(case_folder, _rename_to)
                        if _exists:
                            st.error(f"'{_rename_to}' already exists. Use the Merge tab to combine custodians.")
                        else:
                            _cust_doc_stats = db_manager.get_custodian_doc_stats(case_folder, _rename_from)
                            _affected = _cust_doc_stats['doc_count']
                            st.info(f"This will rename '{_rename_from}' to '{_rename_to}' across {_affected:,} documents.")

                            if st.button(f"✅ Rename {_affected:,} documents", type="primary"):
                                # Re-verify case is still open before writing (race condition guard — M-5)
                                if db_manager.get_case_status(case_folder) == 'Closed':
                                    st.error("Case was closed by another user. Please refresh the page.")
                                    st.stop()
                                _affected = db_manager.rename_custodian(case_folder, _rename_from, _rename_to)
                                _old_hold_dir = os.path.join(case_folder, "Hold_Documents", _rename_from)
                                _new_hold_dir = os.path.join(case_folder, "Hold_Documents", _rename_to)
                                if os.path.isdir(_old_hold_dir):
                                    try:
                                        os.rename(_old_hold_dir, _new_hold_dir)
                                    except OSError as _e:
                                        st.warning(f"Hold documents folder could not be renamed: {_e}")
                                db_manager.log_audit(case_folder, "CUSTODIAN_RENAMED",
                                    username=st.session_state.get('username'),
                                    module="Custodians",
                                    old_value=_rename_from, new_value=_rename_to,
                                    details=json.dumps({"documents_affected": _affected}))
                                st.success(f"✅ Renamed '{_rename_from}' → '{_rename_to}' ({_affected:,} documents)")
                                st.warning("⚠️ The search index may contain stale custodian values. "
                                           "Go to **Sync → Search Index Maintenance** to rebuild the index.")
                                st.rerun()

                # ── TAB 2: MERGE ──────────────────────────────────────────────
                with merge_tab:
                    st.markdown("**Merge two custodians into one.** All documents from the source custodian "
                                "will be reassigned to the target. The source custodian record is deleted.")

                    _merge_target = st.selectbox("Keep (target)", custodian_names, key="merge_target")
                    _merge_source_options = [n for n in custodian_names if n != _merge_target]
                    _merge_source = st.selectbox("Merge into target (will be deleted)", _merge_source_options, key="merge_source")

                    if _merge_target and _merge_source:
                        _src_stats = db_manager.get_custodian_doc_stats(case_folder, _merge_source)
                        _src_count = _src_stats['doc_count']
                        # Check if source has active hold
                        _src_hold = db_manager.get_custodian(case_folder, _merge_source)
                        if _src_hold and _src_hold['hold_status'] == 'Active':
                            st.error(f"⚠️ '{_merge_source}' has an **Active hold**. Hold data will be deleted on merge. "
                                     f"Transfer hold data manually before merging, or release the hold first.")

                        st.warning(f"⚠️ {_src_count:,} documents will move from '{_merge_source}' → '{_merge_target}'. "
                                   f"The custodian record for '{_merge_source}' (including hold data) will be deleted. "
                                   f"This cannot be undone.")

                        _confirm = st.text_input(f"Type '{_merge_source}' to confirm:", key="merge_confirm")
                        if st.button("🔀 Merge Custodians", type="primary") and _confirm == _merge_source:
                            # Re-verify case is still open before writing (race condition guard — M-5)
                            if db_manager.get_case_status(case_folder) == 'Closed':
                                st.error("Case was closed by another user. Please refresh the page.")
                                st.stop()
                            db_manager.merge_custodians(case_folder, _merge_source, _merge_target)
                            # Move hold document files on disk
                            import shutil
                            _src_hold_dir = os.path.join(case_folder, "Hold_Documents", _merge_source)
                            _tgt_hold_dir = os.path.join(case_folder, "Hold_Documents", _merge_target)
                            if os.path.isdir(_src_hold_dir):
                                os.makedirs(_tgt_hold_dir, exist_ok=True)
                                for _fname in os.listdir(_src_hold_dir):
                                    _src_file = os.path.join(_src_hold_dir, _fname)
                                    _tgt_file = os.path.join(_tgt_hold_dir, _fname)
                                    if os.path.isfile(_src_file):
                                        _b, _e = os.path.splitext(_fname)
                                        _c = 1
                                        while os.path.exists(_tgt_file):
                                            _tgt_file = os.path.join(_tgt_hold_dir, f"{_b} ({_c}){_e}")
                                            _c += 1
                                        shutil.move(_src_file, _tgt_file)
                                        conn.execute("UPDATE hold_documents SET file_path = ? WHERE file_path = ?",  # db_manager: exempt (custodian management)
                                                    (_tgt_file, _src_file))
                                try:
                                    os.rmdir(_src_hold_dir)
                                except OSError:
                                    pass
                                conn.commit()
                            db_manager.log_audit(case_folder, "CUSTODIAN_MERGED",
                                username=st.session_state.get('username'),
                                module="Custodians",
                                old_value=_merge_source, new_value=_merge_target,
                                details=json.dumps({"documents_moved": _src_count}))
                            st.success(f"✅ Merged '{_merge_source}' into '{_merge_target}'")
                            st.warning("⚠️ The search index may contain stale custodian values. "
                                       "Go to **Sync → Search Index Maintenance** to rebuild the index.")
                            st.rerun()

                # ── TAB 3: REASSIGN ───────────────────────────────────────────
                with reassign_tab:
                    st.markdown("**Reassign specific documents to a different custodian.**")
                    st.caption("Use this when a subset of documents was ingested under the wrong custodian.")

                    _ra_from = st.selectbox("From custodian", custodian_names, key="reassign_from")
                    _ra_to = st.selectbox("To custodian", [n for n in custodian_names if n != _ra_from], key="reassign_to")

                    _ra_method = st.radio("Selection method",
                        ["Control number list", "Filter by file extension", "Filter by date range"],
                        key="reassign_method")

                    _ra_count = 0
                    _ra_where = ""
                    _ra_params = []

                    if _ra_method == "Control number list":
                        _ra_cns_raw = st.text_area("Control numbers (one per line or comma-separated)", key="reassign_cns")
                        _ra_cns = [cn.strip() for cn in _ra_cns_raw.replace(',', '\n').split('\n') if cn.strip()]
                        if _ra_cns:
                            _placeholders = ','.join(['?'] * len(_ra_cns))
                            _ra_where = f"custodian = ? AND control_number IN ({_placeholders}) AND processing_status NOT IN ('Container_Scanned', 'Split_Source')"
                            _ra_params = [_ra_from] + _ra_cns
                            _ra_count = conn.execute(  # db_manager: exempt (dynamic query)
                                f"SELECT COUNT(*) FROM documents WHERE {_ra_where}", _ra_params
                            ).fetchone()[0]
                            st.info(f"{_ra_count:,} matching documents found.")

                    elif _ra_method == "Filter by file extension":
                        _ra_ext = st.text_input("Extension (e.g. .msg, .pdf)", key="reassign_ext")
                        if _ra_ext:
                            _ra_where = "custodian = ? AND LOWER(file_extension) = ? AND processing_status NOT IN ('Container_Scanned', 'Split_Source')"
                            _ra_params = [_ra_from, _ra_ext.lower().strip()]
                            _ra_count = conn.execute(  # db_manager: exempt (dynamic query)
                                f"SELECT COUNT(*) FROM documents WHERE {_ra_where}", _ra_params
                            ).fetchone()[0]
                            st.info(f"{_ra_count:,} matching documents found.")

                    elif _ra_method == "Filter by date range":
                        _ra_d1, _ra_d2 = st.columns(2)
                        _ra_start = _ra_d1.date_input("From date", value=None, key="reassign_start")
                        _ra_end = _ra_d2.date_input("To date", value=None, key="reassign_end")
                        if _ra_start and _ra_end:
                            _ra_where = "custodian = ? AND date_created >= ? AND date_created <= ? AND processing_status NOT IN ('Container_Scanned', 'Split_Source')"
                            _ra_params = [_ra_from, str(_ra_start), str(_ra_end)]
                            _ra_count = conn.execute(  # db_manager: exempt (dynamic query)
                                f"SELECT COUNT(*) FROM documents WHERE {_ra_where}", _ra_params
                            ).fetchone()[0]
                            st.info(f"{_ra_count:,} matching documents found.")

                    if _ra_count > 0 and _ra_where:
                        if st.button(f"📦 Reassign {_ra_count:,} documents to {_ra_to}", type="primary"):
                            # Re-verify case is still open before writing (race condition guard — M-5)
                            if db_manager.get_case_status(case_folder) == 'Closed':
                                st.error("Case was closed by another user. Please refresh the page.")
                                st.stop()
                            conn.execute(  # db_manager: exempt (dynamic query)
                                f"UPDATE documents SET custodian = ? WHERE {_ra_where}",
                                [_ra_to] + _ra_params
                            )
                            conn.commit()
                            db_manager.log_audit(case_folder, "CUSTODIAN_REASSIGNED",
                                username=st.session_state.get('username'),
                                module="Custodians",
                                old_value=_ra_from, new_value=_ra_to,
                                details=json.dumps({"documents_moved": _ra_count, "method": _ra_method}))
                            st.success(f"✅ Reassigned {_ra_count:,} documents from '{_ra_from}' to '{_ra_to}'")
                            st.warning("⚠️ The search index may contain stale custodian values. "
                                       "Go to **Sync → Search Index Maintenance** to rebuild the index.")
                            st.rerun()

                # ── TAB 4: COLLECTIONS ────────────────────────────────────────
                with collections_tab:
                    st.markdown("**Rename or reassign source collections and subcollections.**")

                    _coll_cust = st.selectbox("Custodian", custodian_names, key="coll_custodian")
                    _colls = conn.execute("""  -- db_manager: exempt (custodian management)
                        SELECT source_collection, source_subcollection, COUNT(*) as cnt
                        FROM documents
                        WHERE custodian = ? AND (source_party = 'Internal' OR source_party IS NULL)
                          AND processing_status NOT IN ('Container_Scanned', 'Split_Source')
                        GROUP BY source_collection, source_subcollection
                        ORDER BY source_collection, source_subcollection
                    """, (_coll_cust,)).fetchall()

                    if _colls:
                        st.dataframe(
                            pd.DataFrame([{
                                'Collection': r['source_collection'] or '(None)',
                                'Subcollection': r['source_subcollection'] or '(None)',
                                'Documents': r['cnt'],
                            } for r in _colls]),
                            width='stretch', hide_index=True,
                        )

                        _existing_colls = sorted(set(r['source_collection'] for r in _colls if r['source_collection']))
                        if _existing_colls:
                            _coll_from = st.selectbox("Rename collection", _existing_colls, key="coll_rename_from")
                            _coll_to = st.text_input("New collection name", key="coll_rename_to")
                            if _coll_from and _coll_to and _coll_to.strip() and _coll_from != _coll_to.strip():
                                _coll_to = _coll_to.strip()
                                _coll_count = conn.execute(  # db_manager: exempt (custodian management)
                                    "SELECT COUNT(*) FROM documents WHERE custodian = ? AND source_collection = ? AND processing_status NOT IN ('Container_Scanned', 'Split_Source')",
                                    (_coll_cust, _coll_from)
                                ).fetchone()[0]
                                if st.button(f"Rename '{_coll_from}' → '{_coll_to}' ({_coll_count:,} docs)"):
                                    conn.execute(  # db_manager: exempt (custodian management)
                                        "UPDATE documents SET source_collection = ? WHERE custodian = ? AND source_collection = ?",
                                        (_coll_to, _coll_cust, _coll_from))
                                    conn.commit()
                                    db_manager.log_audit(case_folder, "COLLECTION_RENAMED",
                                        username=st.session_state.get('username'),
                                        module="Custodians",
                                        old_value=_coll_from, new_value=_coll_to,
                                        details=json.dumps({"custodian": _coll_cust, "documents_affected": _coll_count}))
                                    st.success(f"✅ Renamed collection")
                                    st.warning("⚠️ The search index may contain stale values. "
                                               "Go to **Sync → Search Index Maintenance** to rebuild the index.")
                                    st.rerun()

                        # Assign collection to unorganized docs
                        _no_coll = conn.execute(  # db_manager: exempt (custodian management)
                            "SELECT COUNT(*) FROM documents WHERE custodian = ? AND (source_collection IS NULL OR source_collection = '') AND (source_party = 'Internal' OR source_party IS NULL) AND processing_status NOT IN ('Container_Scanned', 'Split_Source')",
                            (_coll_cust,)
                        ).fetchone()[0]
                        if _no_coll > 0:
                            st.warning(f"{_no_coll:,} documents have no collection assigned.")
                            _assign_coll = st.text_input("Assign collection name", key="assign_coll_name")
                            if _assign_coll and _assign_coll.strip():
                                if st.button(f"Assign to {_no_coll:,} documents"):
                                    conn.execute(  # db_manager: exempt (custodian management)
                                        "UPDATE documents SET source_collection = ? WHERE custodian = ? AND (source_collection IS NULL OR source_collection = '') AND (source_party = 'Internal' OR source_party IS NULL)",
                                        (_assign_coll.strip(), _coll_cust))
                                    conn.commit()
                                    db_manager.log_audit(case_folder, "COLLECTION_ASSIGNED",
                                        username=st.session_state.get('username'),
                                        module="Custodians",
                                        details=json.dumps({"custodian": _coll_cust, "collection": _assign_coll.strip(), "documents": _no_coll}))
                                    st.rerun()
                    else:
                        st.info(f"No documents found for {_coll_cust}.")

                # ── TAB 5: COLLECTION SCOPE ───────────────────────────────────
                with scope_tab:
                    if not _sel_cust:
                        st.info("Select a custodian above to manage collection scope.")
                    else:
                        # Get custodian ID
                        _scope_cust_row = conn.execute(  # db_manager: exempt (custodian management)
                            "SELECT id, data_sources FROM custodians WHERE name = ?",
                            (_sel_cust,)
                        ).fetchone()
                        if not _scope_cust_row:
                            st.warning("Custodian not found in database.")
                        else:
                            _cust_id = _scope_cust_row['id']
                            _data_sources = json.loads(_scope_cust_row['data_sources'] or '[]')

                            # Auto-seed any data_sources not yet in collection_scope
                            if _data_sources:
                                db_manager.seed_collection_scope(case_folder, _cust_id, _data_sources)

                            # Load current scope entries
                            _scope_rows = db_manager.get_collection_scope(case_folder, _cust_id)

                            if not _scope_rows:
                                st.info(
                                    "No collection sources configured. Add data sources in the "
                                    "custodian detail panel above, or enter sources manually below."
                                )
                                # Manual add form
                                with st.form("add_scope_source", clear_on_submit=True):
                                    _new_src = st.text_input("Source Name (e.g., 'Exchange Mailbox')")
                                    if st.form_submit_button("Add Source", width='stretch'):
                                        if _new_src.strip():
                                            db_manager.upsert_collection_scope(
                                                case_folder, _cust_id, _new_src.strip(),
                                                'Pending', '', st.session_state.get('username', '')
                                            )
                                            st.rerun()
                            else:
                                _status_options = [
                                    'Pending', 'Collected', 'Searched-No-Hit',
                                    'Not-Reasonably-Accessible', 'Out-of-Scope'
                                ]

                                # Completeness indicator
                                _documented = sum(1 for r in _scope_rows if r['status'] != 'Pending')
                                _total_src = len(_scope_rows)
                                if _documented == _total_src:
                                    st.success(f"All {_total_src} sources documented.")
                                else:
                                    st.warning(f"{_documented} of {_total_src} sources documented. "
                                               f"{_total_src - _documented} still pending.")

                                # Editable form for each source
                                with st.form("scope_form"):
                                    _updates = []
                                    for row in _scope_rows:
                                        st.markdown(f"**{row['source_name']}**")
                                        _col_s, _col_j = st.columns([1, 2])
                                        with _col_s:
                                            _new_status = st.selectbox(
                                                "Status",
                                                _status_options,
                                                index=_status_options.index(row['status']),
                                                key=f"scope_status_{row['id']}",
                                                label_visibility="collapsed",
                                            )
                                        with _col_j:
                                            _new_just = st.text_area(
                                                "Justification",
                                                value=row['justification'] or '',
                                                key=f"scope_just_{row['id']}",
                                                height=68,
                                                label_visibility="collapsed",
                                                placeholder="Justification / notes…",
                                            )
                                        _updates.append((row['source_name'], _new_status, _new_just))
                                        if row['reviewed_by']:
                                            st.caption(
                                                f"Last reviewed by {row['reviewed_by']} "
                                                f"on {row['reviewed_at'] or '—'}"
                                            )
                                        st.markdown("---")

                                    _save_col, _add_col = st.columns(2)
                                    with _save_col:
                                        _save = st.form_submit_button(
                                            "💾 Save All", width='stretch'
                                        )
                                    with _add_col:
                                        _new_manual = st.text_input(
                                            "Add source:",
                                            placeholder="New source name…",
                                            label_visibility="collapsed",
                                        )

                                if _save:
                                    _username = st.session_state.get('username', '')
                                    for src_name, status, justification in _updates:
                                        db_manager.upsert_collection_scope(
                                            case_folder, _cust_id, src_name,
                                            status, justification, _username
                                        )
                                    if _new_manual and _new_manual.strip():
                                        db_manager.upsert_collection_scope(
                                            case_folder, _cust_id, _new_manual.strip(),
                                            'Pending', '', _username
                                        )
                                    try:
                                        db_manager.log_audit(
                                            case_folder,
                                            action="COLLECTION_SCOPE_UPDATED",
                                            username=_username,
                                            module="Custodians",
                                            details=json.dumps({
                                                "custodian": _sel_cust,
                                                "sources_updated": len(_updates),
                                            })
                                        )
                                    except Exception:
                                        pass
                                    st.success("Collection scope saved.")
                                    st.rerun()

            # ═══════════════════════════════════════════════════════════════════
            # LEGAL HOLD MANAGEMENT
            # ═══════════════════════════════════════════════════════════════════

            st.divider()
            st.subheader("⚖️ Legal Hold Status")

            # Hold status card
            _hold_status = _cust_row['hold_status'] or 'None'
            _hold_style = {
                'None':     ('#a0aec0', '⬜'),
                'Active':   ('#38a169', '🟢'),
                'Released': ('#dd6b20', '🟡'),
                'Expired':  ('#e53e3e', '🔴'),
            }
            _hc, _hi = _hold_style.get(_hold_status, ('#a0aec0', '⬜'))

            st.markdown(f"""
            <div style="border: 2px solid {_hc}; border-radius: 8px; padding: 16px; margin: 8px 0;">
                <div style="font-size: 1.2em; font-weight: 700;">{_hi} Hold Status: {_hold_status}</div>
            </div>
            """, unsafe_allow_html=True)

            # Helper to safely parse ISO date strings for st.date_input
            def _parse_date(val):
                if not val:
                    return None
                try:
                    from datetime import date as _date_type
                    parts = str(val)[:10].split('-')
                    return _date_type(int(parts[0]), int(parts[1]), int(parts[2]))
                except Exception:
                    return None

            def _safe_index(options, value):
                try:
                    return options.index(value)
                except (ValueError, TypeError):
                    return 0

            if _case_closed:
                st.caption("Hold settings are read-only because this matter is closed.")

            _hold_col1, _hold_col2 = st.columns(2)

            with _hold_col1:
                _h_status = st.selectbox("Hold Status", ['None', 'Active', 'Released', 'Expired'],
                    index=['None', 'Active', 'Released', 'Expired'].index(_hold_status),
                    key=f"hold_status_sel_{_sel_cust}", disabled=_case_closed)
                _h_issued = st.date_input("Hold Notice Issued",
                    value=_parse_date(_cust_row['hold_issued_date']),
                    key=f"hold_issued_{_sel_cust}", disabled=_case_closed)
                _h_ack = st.date_input("Custodian Acknowledged",
                    value=_parse_date(_cust_row['hold_acknowledged_date']),
                    key=f"hold_ack_{_sel_cust}", disabled=_case_closed)
                _h_released = st.date_input("Hold Released",
                    value=_parse_date(_cust_row['hold_released_date']),
                    key=f"hold_released_{_sel_cust}", disabled=_case_closed)

            with _hold_col2:
                _notice_methods = ['Email', 'Letter', 'In-Person', 'Portal', 'Other']
                _h_method = st.selectbox("Notice Method", _notice_methods,
                    index=_safe_index(_notice_methods, _cust_row['hold_notice_method']),
                    key=f"hold_method_{_sel_cust}", disabled=_case_closed)
                _h_recipient = st.text_input("Notice Recipient",
                    value=_cust_row['hold_notice_recipient'] or '',
                    key=f"hold_recipient_{_sel_cust}", disabled=_case_closed)
                _h_notes = st.text_area("Hold Notes",
                    value=_cust_row['hold_notes'] or '',
                    key=f"hold_notes_{_sel_cust}", height=120, disabled=_case_closed)

            # permission: hold_status_update
            if not _case_closed and auth_manager.has_permission('custodian_management'):
                if st.button("💾 Save Hold Status", width='stretch'):
                    _old_status = _cust_row['hold_status'] or 'None'
                    conn.execute("""  -- db_manager: exempt (hold management)
                        UPDATE custodians SET
                            hold_status=?, hold_issued_date=?, hold_acknowledged_date=?,
                            hold_released_date=?, hold_notice_method=?, hold_notice_recipient=?,
                            hold_notes=?, updated_at=CURRENT_TIMESTAMP
                        WHERE name = ?
                    """, (_h_status,
                          str(_h_issued) if _h_issued else None,
                          str(_h_ack) if _h_ack else None,
                          str(_h_released) if _h_released else None,
                          _h_method, _h_recipient, _h_notes, _sel_cust))
                    conn.commit()
                    db_manager.log_audit(case_folder, "HOLD_STATUS_CHANGED",
                        username=st.session_state.get('username'),
                        module="Custodians", old_value=_old_status, new_value=_h_status,
                        details=json.dumps({"custodian": _sel_cust}))
                    st.success(f"✅ Hold status updated for {_sel_cust}")
                    st.rerun()

            # ═══════════════════════════════════════════════════════════════════
            # HOLD DOCUMENT UPLOAD + LIST
            # ═══════════════════════════════════════════════════════════════════

            st.divider()
            st.markdown("**📎 Hold Documentation**")
            st.caption(
                "Upload hold notices, acknowledgment emails, signed letters, and other preservation "
                "records for this custodian. These files are stored as administrative records — "
                "they are NOT added to the case document population and cannot be produced."
            )

            # permission: hold_document_upload
            if not _case_closed and auth_manager.has_permission('custodian_management'):
                _hold_uploads = st.file_uploader(
                    "Upload hold documents",
                    type=['msg', 'eml', 'pdf', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'tiff', 'txt', 'htm', 'html'],
                    accept_multiple_files=True,
                    key=f"hold_upload_{_sel_cust}",
                )

                if _hold_uploads:
                    _doc_type = st.selectbox(
                        "Document type for this upload",
                        ['Hold Notice', 'Acknowledgment', 'Release Letter', 'Reminder', 'Correspondence', 'Other'],
                        key="hold_upload_type",
                    )
                    _upload_notes = st.text_input("Notes (optional)", key="hold_upload_notes",
                                                   placeholder="e.g. Signed copy returned via certified mail")

                    if st.button(f"📤 Save {len(_hold_uploads)} file(s)", type="primary", width='stretch'):
                        _hold_dir = os.path.join(case_folder, "Hold_Documents", _sel_cust)
                        os.makedirs(_hold_dir, exist_ok=True)
                        _upload_username = st.session_state.get('username', 'unknown')

                        for _uf in _hold_uploads:
                            _save_path = os.path.join(_hold_dir, _uf.name)
                            _base, _ext = os.path.splitext(_uf.name)
                            _counter = 1
                            while os.path.exists(_save_path):
                                _save_path = os.path.join(_hold_dir, f"{_base} ({_counter}){_ext}")
                                _counter += 1

                            with open(_save_path, 'wb') as _f:
                                _f.write(_uf.getbuffer())

                            conn.execute("""  -- db_manager: exempt (hold management)
                                INSERT INTO hold_documents
                                    (custodian_name, file_name, file_path, document_type, uploaded_by, notes)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (_sel_cust, os.path.basename(_save_path), _save_path,
                                  _doc_type, _upload_username, _upload_notes))

                            db_manager.log_audit(case_folder, "HOLD_DOCUMENT_UPLOADED",
                                username=_upload_username,
                                module="Custodians",
                                details=json.dumps({
                                    "custodian": _sel_cust,
                                    "file_name": os.path.basename(_save_path),
                                    "document_type": _doc_type,
                                }),
                                conn=conn)

                        conn.commit()
                        st.success(f"✅ {len(_hold_uploads)} file(s) uploaded for {_sel_cust}")
                        st.rerun()

            # Display existing hold documents
            _hold_docs = conn.execute("""  -- db_manager: exempt (hold management)
                SELECT id, file_name, file_path, document_type, uploaded_by, upload_date, notes
                FROM hold_documents
                WHERE custodian_name = ?
                ORDER BY upload_date DESC
            """, (_sel_cust,)).fetchall()

            if _hold_docs:
                st.markdown(f"**{len(_hold_docs)} document(s) on file:**")
                for _hd in _hold_docs:
                    _hd_col1, _hd_col2, _hd_col3 = st.columns([4, 1, 1])
                    _type_badge = {
                        'Hold Notice': '📋', 'Acknowledgment': '✅',
                        'Release Letter': '📤', 'Reminder': '🔔',
                        'Correspondence': '💬', 'Other': '📄',
                    }.get(_hd['document_type'], '📄')

                    _hd_col1.markdown(
                        f"{_type_badge} **{_hd['file_name']}** — {_hd['document_type']} "
                        f"<br><small>Uploaded by {_hd['uploaded_by']} on {_hd['upload_date'][:10] if _hd['upload_date'] else 'N/A'}"
                        f"{' — ' + _hd['notes'] if _hd['notes'] else ''}</small>",
                        unsafe_allow_html=True,
                    )

                    if os.path.exists(_hd['file_path']):
                        with open(_hd['file_path'], 'rb') as _f:
                            _hd_col2.download_button(
                                "⬇️", data=_f.read(),
                                file_name=_hd['file_name'],
                                key=f"hold_dl_{_hd['id']}",
                                width='stretch',
                            )
                    else:
                        _hd_col2.caption("Missing")

                    # permission: hold_document_delete
                    if not _case_closed and auth_manager.has_permission('custodian_management'):
                        _del_key = f"hold_del_confirm_{_hd['id']}"
                        if st.session_state.get(_del_key):
                            if _hd_col3.button("⚠️ Confirm", key=f"hold_del_yes_{_hd['id']}", width='stretch'):
                                try:
                                    if os.path.exists(_hd['file_path']):
                                        os.remove(_hd['file_path'])
                                except Exception:
                                    pass
                                conn.execute("DELETE FROM hold_documents WHERE id = ?", (_hd['id'],))  # db_manager: exempt (hold management)
                                conn.commit()
                                db_manager.log_audit(case_folder, "HOLD_DOCUMENT_DELETED",
                                    username=st.session_state.get('username'),
                                    module="Custodians",
                                    details=json.dumps({
                                        "custodian": _sel_cust,
                                        "file_name": _hd['file_name'],
                                    }))
                                st.session_state[_del_key] = False
                                st.rerun()
                        else:
                            if _hd_col3.button("🗑️", key=f"hold_del_{_hd['id']}", width='stretch'):
                                st.session_state[_del_key] = True
                                st.rerun()
            else:
                st.info("No hold documents uploaded for this custodian yet.")

    # ═══════════════════════════════════════════════════════════════════════════
    # CASE HOLD SUMMARY (outside custodian selection, inside custodian_names check)
    # ═══════════════════════════════════════════════════════════════════════════

    st.divider()
    st.subheader("📊 Case Hold Summary")

    _hold_df = pd.read_sql_query("""
        SELECT name as Custodian, hold_status as Status,
               hold_issued_date as Issued, hold_acknowledged_date as Acknowledged,
               hold_released_date as Released, hold_notice_method as Method
        FROM custodians
        WHERE hold_status != 'None' AND hold_status IS NOT NULL
        ORDER BY hold_issued_date
    """, conn)

    if not _hold_df.empty:
        _hm1, _hm2, _hm3, _hm4 = st.columns(4)
        _hm1.metric("Active Holds", len(_hold_df[_hold_df['Status'] == 'Active']))
        _hm2.metric("Released", len(_hold_df[_hold_df['Status'] == 'Released']))
        _hm3.metric("Unacknowledged", len(_hold_df[_hold_df['Acknowledged'].isna() | (_hold_df['Acknowledged'] == '')]))
        _hm4.metric("Total Custodians on Hold", len(_hold_df))

        st.dataframe(_hold_df, width='stretch', hide_index=True)

        # Plotly Gantt-style hold timeline
        from datetime import date as _date_type
        _gantt_rows = []
        for _, _hr in _hold_df.iterrows():
            _start = _hr['Issued']
            if not _start:
                continue
            _finish = _hr['Released'] if _hr['Released'] else str(_date_type.today())
            _gantt_rows.append({
                'Custodian': _hr['Custodian'],
                'Start': _start,
                'Finish': _finish,
                'Status': _hr['Status'],
            })

        if _gantt_rows:
            import plotly.express as px
            _gantt_df = pd.DataFrame(_gantt_rows)
            _gantt_df['Start'] = pd.to_datetime(_gantt_df['Start'])
            _gantt_df['Finish'] = pd.to_datetime(_gantt_df['Finish'])

            _gantt_color_map = {
                'Active': _CHART_COLORS['success'],
                'Released': _CHART_COLORS['warning'],
                'Expired': _CHART_COLORS['danger'],
            }

            _gantt_fig = px.timeline(
                _gantt_df,
                x_start='Start', x_end='Finish', y='Custodian',
                color='Status',
                color_discrete_map=_gantt_color_map,
            )
            _gantt_fig = _apply_chart_layout(_gantt_fig, height=max(250, len(_gantt_rows) * 40))
            _gantt_fig.update_layout(
                title=dict(text='Legal Hold Timeline', font_size=14),
                xaxis_title='Date',
                showlegend=True,
            )
            _gantt_fig.update_yaxes(autorange='reversed')
            st.plotly_chart(_gantt_fig, width='stretch')
    else:
        st.info("No legal holds have been tracked for this matter.")

else:
    st.info("No custodians found. Ingest documents first, then return here to manage custodians.")

conn.close()
