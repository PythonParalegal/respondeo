# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        home.py
# version:       1.14.6
# project:       Respondeo eDiscovery Platform
# project_ver:   2.12.0
# last_modified: 2026-04-30 14:00
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
import pandas as pd
import os
import subprocess
import socket
import sqlite3
from datetime import datetime
import json
import db_manager
import os_manager
import config
import auth_manager
import ui_utils
import plotly.graph_objects as go
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent / "assets"

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

st.set_page_config(page_title="Respondeo | Home", layout="wide", page_icon=str(_ASSETS / "favicon.png"))
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()

# --- AUTH GATE ---
if not auth_manager.setup_initial_admin():
    st.stop()
if not auth_manager.check_login():
    st.stop()
# permission: review
auth_manager.require_permission('review')

# --- SERVICE PATHS (from config.py) ---
TIKA_JAR = config.TIKA_JAR
OS_HOME = config.OPENSEARCH_HOME
OS_BAT = f'cd /d {OS_HOME}\\bin && set "OPENSEARCH_JAVA_HOME={OS_HOME}\\jdk" && opensearch.bat'

def is_port_open(port):
    import ssl
    context = ssl._create_unverified_context()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        # First check raw connection
        if s.connect_ex(('localhost', port)) == 0:
            if port == 9200:
                # OpenSearch on localhost, port check is sufficient. connect_ex returning 0 is enough for "Online"
                return True
            return True
    return False

def launch_service(command, name):
    try:
        # Launch as background process
        subprocess.Popen(command, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        st.success(f"🚀 {name} launch command sent!")
    except Exception as e:
        st.error(f"Failed to launch {name}: {e}")

st.title("Respondeo")
st.caption("E-Discovery Platform")

st.sidebar.header("📁 Case Selection")

# --- SCAN FOR EXISTING CASES ---
def discover_cases(root_dir):
    """Scan CASES_ROOT for subdirectories that contain a case.db file."""
    cases = []
    if not os.path.isdir(root_dir):
        return cases
    try:
        for entry in os.scandir(root_dir):
            if entry.is_dir():
                db_path = os.path.join(entry.path, "case.db")
                if os.path.exists(db_path):
                    cases.append(entry.path)
    except PermissionError:
        pass
    return sorted(cases)

cases_root = getattr(config, 'CASES_ROOT', r"C:\eDiscovery")
_all_discovered_cases = discover_cases(cases_root)  # unfiltered — used by admin UI

# Filter to only cases the logged-in user is allowed to access.
_current_username = st.session_state.get('username', '')
_allowed_cases = auth_manager.get_allowed_cases(_current_username)
if _allowed_cases is not None:
    discovered_cases = [p for p in _all_discovered_cases if p in _allowed_cases]
else:
    discovered_cases = list(_all_discovered_cases)

# Build options: discovered cases + manual entry option
case_labels = {path: os.path.basename(path) for path in discovered_cases}
options = ["— Select a Case —"] + discovered_cases
format_func = lambda x: case_labels.get(x, x) if x != "— Select a Case —" else x

# SESSION STATE
if 'current_case_folder' not in st.session_state:
    st.session_state['current_case_folder'] = None

# Keys that hold case-specific data and must be cleared on case switch
# to prevent stale data from one case bleeding into another.
_CASE_SPECIFIC_KEYS = [
    # Analytics
    'inclusive_docs', 'suppressed_docs', 'threading_done', 'nd_clusters',
    'ca_df_cache', 'str_terms_run', 'str_hit_docs', 'str_summary', 'active_str_terms',
    # Review
    'review_search', '_peek_cn', '_peek_return_idx', 'current_doc_idx',
    '_grid_last_viewer_idx', 'bulk_selected_cns', '_page_number', '_page_size',
    '_family_view_on', '_family_override_group_id', '_nav_selected_key',
    '_bates_lookup_results', '_bates_batch_text', '_bates_lookup_jump_cn',
    'bates_hit_details', '_pre_family_search_state', '_pending_search_restore',
    '_load_saved_query', 'review_grid_columns',
    # Production
    'prod_pass1', 'prod_pass1_complete', 'prod_finalized', 'prod_all_selected',
    'production_selection', 'production_grid_editor',
    'pending_pdf_zip', 'pending_pdf_zip_count', 'pending_pdf_zip_errors',
    'pending_bates_zip', '_prod_cancel',
    # Exhibits
    '_binder_pdf', '_binder_name', '_confirm_delete_set', 'exhibits_set_selector',
]

def _clear_case_state():
    """Remove all case-specific session state keys when switching cases."""
    for _key in _CASE_SPECIFIC_KEYS:
        st.session_state.pop(_key, None)

# Callbacks for sync
def on_dropdown_change():
    v = st.session_state.get("dyn_case_select")
    if v and v != "— Select a Case —":
        _uname = st.session_state.get('username', '')
        _allowed = auth_manager.get_allowed_cases(_uname)
        if _allowed is not None and v not in _allowed:
            st.session_state["dyn_case_select"] = "— Select a Case —"
            return
        _clear_case_state()
        st.session_state['current_case_folder'] = v
        st.session_state["dyn_case_custom"] = ""
        if _uname:
            auth_manager.save_user_pref(_uname, 'last_case', v)

def on_custom_change():
    v = st.session_state.get("dyn_case_custom")
    if v and os.path.isdir(v):
        _uname = st.session_state.get('username', '')
        _allowed = auth_manager.get_allowed_cases(_uname)
        if _allowed is not None and v not in _allowed:
            return  # silently block; warning rendered in expander body below
        _clear_case_state()
        st.session_state['current_case_folder'] = v
        st.session_state["dyn_case_select"] = "— Select a Case —"
        if _uname:
            auth_manager.save_user_pref(_uname, 'last_case', v)

current = st.session_state.get('current_case_folder')

# Secondary discovery: if CASES_ROOT yielded nothing but we have an active case path,
# scan its parent directory so the dropdown isn't silently empty on machines where
# CASES_ROOT doesn't match the actual case location.
if not discovered_cases and current and os.path.isdir(current):
    _sec_root = os.path.dirname(current)
    if os.path.normcase(_sec_root) != os.path.normcase(cases_root):
        _sec_cases = discover_cases(_sec_root)
        if _sec_cases:
            discovered_cases.extend(_sec_cases)
            discovered_cases = sorted(set(discovered_cases))
            case_labels = {p: os.path.basename(p) for p in discovered_cases}
            options = ["— Select a Case —"] + discovered_cases

# Keep the dropdown widget's session-state key in sync with current_case_folder.
# This is needed because Streamlit uses the stored key value (not the index param)
# when a widget has been rendered before — e.g. after last_case is restored on login.
if current in discovered_cases:
    if st.session_state.get("dyn_case_select") != current:
        st.session_state["dyn_case_select"] = current
elif not current:
    if st.session_state.get("dyn_case_select") not in (None, "— Select a Case —"):
        st.session_state["dyn_case_select"] = "— Select a Case —"

st.sidebar.selectbox("Active Case", options, format_func=format_func, key="dyn_case_select", on_change=on_dropdown_change)

with st.sidebar.expander("➕ New Case / Custom Path"):
    custom_val = current if current and current not in discovered_cases else ""
    if "dyn_case_custom" not in st.session_state:
        st.session_state["dyn_case_custom"] = custom_val
        
    custom_path = st.text_input("Case Folder Path", placeholder=f"{cases_root}\\NewCaseName", key="dyn_case_custom", on_change=on_custom_change)
    
    if custom_path and _allowed_cases is not None and custom_path not in _allowed_cases:
        st.warning("You don't have access to this case.")
    elif custom_path and not os.path.isdir(custom_path):
        st.warning("Path does not exist yet.")
        if st.button("📂 Create Case Folder", key="create_case_folder_btn"):
            os.makedirs(os.path.join(custom_path, "Ingest"), exist_ok=True)
            os.makedirs(os.path.join(custom_path, "Reviewed"), exist_ok=True)
            _clear_case_state()
            st.session_state['current_case_folder'] = custom_path
            st.success(f"Created: {custom_path}")
            st.rerun()

# Self-diagnosis tip: if current case is outside CASES_ROOT, nudge the user to fix it.
if (current and os.path.isdir(current)
        and os.path.normcase(os.path.dirname(current)) != os.path.normcase(cases_root)):
    _suggested_root = os.path.dirname(current)
    st.sidebar.info(
        f"💡 **Tip:** Your cases appear to be in `{_suggested_root}` — "
        f"not the configured `CASES_ROOT`. Update `CASES_ROOT` in `config.py` "
        f"to `{_suggested_root}` to auto-discover all cases on this machine."
    )

auth_manager.show_user_info()

selected_folder = st.session_state.get('current_case_folder')

if selected_folder and os.path.isdir(selected_folder):
    # Check for Database
    db_path = os.path.join(selected_folder, "case.db")
    
    if not os.path.exists(db_path):
        st.warning(f"⚠️ No database found in: {os.path.basename(selected_folder)}")
        if st.button("✨ Initialize New Case Database", key="init_case_db_btn"):
            # Always clear any orphaned OpenSearch data from previous deleted runs
            index_name = os_manager.get_index_name(selected_folder)
            try:
                es, _ = os_manager.get_os_client()
                if es and es.indices.exists(index=index_name):
                    es.indices.delete(index=index_name)
            except Exception as e:
                pass # OpenSearch might be offline, ignore safely

            db_manager.init_db(selected_folder)
            st.success("Database created! Reloading...")
            st.rerun()
        st.stop()  # No DB yet — don't let code below try to query it
    else:
        st.sidebar.success(f"✅ Active: {os.path.basename(selected_folder)}")
        _cs_sidebar = db_manager.get_case_status(selected_folder)
        _sb_badge = {"Active": "Status: Active", "On Hold": "Status: On Hold", "Closed": "Status: CLOSED"}
        st.sidebar.caption(_sb_badge.get(_cs_sidebar, "Status: Active"))

        # Log USER_LOGIN once per session per case (login happens before case selection,
        # so we defer logging until the first time this case is confirmed active)
        _login_flag = f"_login_logged_{selected_folder}"
        if not st.session_state.get(_login_flag):
            db_manager.log_audit(
                selected_folder, "USER_LOGIN",
                username=st.session_state.get("username"),
                module="home"
            )
            st.session_state[_login_flag] = True

        # ── Case Lifecycle Status ────────────────────────────────────────────
        _current_status = db_manager.get_case_status(selected_folder)
        _status_color = {"Active": "green", "On Hold": "orange", "Closed": "red"}.get(_current_status, "gray")
        st.sidebar.markdown(
            f'<span style="color:{_status_color};font-weight:bold;">⬤ {_current_status}</span>',
            unsafe_allow_html=True
        )
        # permission: change_case_status
        if auth_manager.has_permission('case_settings'):
            _new_status = st.sidebar.selectbox(
                "Matter Status",
                ["Active", "On Hold", "Closed"],
                index=["Active", "On Hold", "Closed"].index(_current_status),
                key="case_lifecycle_status"
            )
            if _new_status != _current_status:
                db_manager.set_case_status(selected_folder, _new_status)
                try:
                    db_manager.log_audit(
                        selected_folder, "CASE_SETTING_CHANGED",
                        username=st.session_state.get("username"),
                        module="home",
                        old_value=_current_status,
                        new_value=_new_status,
                    )
                except Exception:
                    pass
                st.rerun()

        # Ensure schema exists (handles cases where case.db was created but init_db never ran)
        db_manager.init_db(selected_folder)

        # Show Dashboard Stats
        try:
            _status = db_manager.get_document_status_counts(selected_folder)
            _tags = db_manager.get_review_tag_counts(selected_folder)

            total_docs     = _status['total']
            new_docs       = _status['new']
            processed_docs = _status['processed']
            duplicate_docs = _status['duplicate']
            error_docs     = _status['error']
            produced_docs  = _status['produced']

            all_tagged     = _tags['all_tagged']
            responsive     = _tags['responsive']
            not_resp       = _tags['not_responsive']
            needs_review   = _tags['needs_review']
            suppressed     = _tags['suppressed']
            privileged     = _tags['privileged']
            threading_done = _tags['threading_done']
            nd_done        = _tags['nd_done']

            # ── Case Status banner (control is in sidebar) ──────────────
            _case_status = db_manager.get_case_status(selected_folder)
            if _case_status == 'Closed':
                st.error("🔴 **Matter Status: Closed** — write operations are locked in all modules.")
            elif _case_status == 'On Hold':
                st.warning("🟡 **Matter Status: On Hold**")

            # ── Matter Profile ────────────────────────────────────────────────
            _mp = db_manager.get_matter_profile(selected_folder)
            if _mp:
                st.markdown("### 📋 Matter Profile")
                _mp_l, _mp_r = st.columns(2)
                with _mp_l:
                    if _mp.get('matter_number'):
                        st.markdown(f"**Matter #:** {_mp['matter_number']}")
                    if _mp.get('case_caption'):
                        st.markdown(f"**Caption:** {_mp['case_caption']}")
                    if _mp.get('court'):
                        st.markdown(f"**Court:** {_mp['court']}")
                    if _mp.get('case_number'):
                        st.markdown(f"**Case #:** {_mp['case_number']}")
                with _mp_r:
                    if _mp.get('judge'):
                        st.markdown(f"**Judge:** {_mp['judge']}")
                    if _mp.get('opposing_counsel'):
                        st.markdown(f"**Opposing Counsel:** {_mp['opposing_counsel']}")
                    if _mp.get('description'):
                        st.markdown(f"**Description:** {_mp['description']}")
                _date_parts = []
                if _mp.get('date_complaint_filed'):
                    _date_parts.append(f"Complaint Filed: {_mp['date_complaint_filed']}")
                if _mp.get('date_discovery_cutoff'):
                    _date_parts.append(f"Discovery Cutoff: {_mp['date_discovery_cutoff']}")
                if _mp.get('date_trial'):
                    _date_parts.append(f"Trial: {_mp['date_trial']}")
                if _date_parts:
                    st.caption(" · ".join(_date_parts))
            else:
                st.info("📋 No matter profile configured. Managers can set case details below.")

            # permission: case_settings
            if auth_manager.has_permission('case_settings') and _case_status != 'Closed':
                with st.expander("✏️ Edit Matter Profile"):
                    _ep_l, _ep_r = st.columns(2)
                    with _ep_l:
                        _ep_matter = st.text_input("Matter Number", value=_mp.get('matter_number', ''), key="mp_matter_num")
                        _ep_caption = st.text_input("Case Caption", value=_mp.get('case_caption', ''), key="mp_caption")
                        _ep_court = st.text_input("Court", value=_mp.get('court', ''), key="mp_court")
                        _ep_casenum = st.text_input("Case/Docket Number", value=_mp.get('case_number', ''), key="mp_casenum")
                    with _ep_r:
                        _ep_judge = st.text_input("Judge", value=_mp.get('judge', ''), key="mp_judge")
                        _ep_opposing = st.text_input("Opposing Counsel", value=_mp.get('opposing_counsel', ''), key="mp_opposing")
                        _ep_desc = st.text_area("Description", value=_mp.get('description', ''), key="mp_desc", height=100)
                    _ep_d1, _ep_d2, _ep_d3 = st.columns(3)
                    _ep_complaint = _ep_d1.text_input("Complaint Filed (YYYY-MM-DD)", value=_mp.get('date_complaint_filed', ''), key="mp_complaint")
                    _ep_cutoff = _ep_d2.text_input("Discovery Cutoff (YYYY-MM-DD)", value=_mp.get('date_discovery_cutoff', ''), key="mp_cutoff")
                    _ep_trial = _ep_d3.text_input("Trial Date (YYYY-MM-DD)", value=_mp.get('date_trial', ''), key="mp_trial")
                    if st.button("💾 Save Matter Profile", width='stretch', key="mp_save"):
                        _new_mp = {
                            'matter_number': _ep_matter, 'case_caption': _ep_caption,
                            'court': _ep_court, 'case_number': _ep_casenum,
                            'judge': _ep_judge, 'opposing_counsel': _ep_opposing,
                            'description': _ep_desc,
                            'date_complaint_filed': _ep_complaint,
                            'date_discovery_cutoff': _ep_cutoff,
                            'date_trial': _ep_trial,
                        }
                        db_manager.set_matter_profile(selected_folder, _new_mp)
                        db_manager.log_audit(selected_folder, "MATTER_PROFILE_UPDATED",
                            username=st.session_state.get('username'), module="home",
                            details=json.dumps({k: v for k, v in _new_mp.items() if v}))
                        st.success("✅ Matter profile saved.")
                        st.rerun()

            # ── Top metrics row ───────────────────────────────────────────────
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Files", f"{total_docs:,}")
            m2.metric("Processed", f"{processed_docs:,}",
                      delta=f"-{duplicate_docs:,} dupes suppressed" if duplicate_docs else None,
                      delta_color="off")
            m3.metric("Reviewed (tagged)", f"{all_tagged:,}")
            m4.metric("Produced", f"{produced_docs:,}")

            # ── Pipeline Funnel ───────────────────────────────────────────────
            if total_docs > 0:
                _funnel_fig = go.Figure(go.Funnel(
                    y=['Ingested', 'Processed', 'Reviewed', 'Produced'],
                    x=[total_docs, processed_docs, all_tagged, produced_docs],
                    textinfo="value+percent initial",
                    texttemplate='%{value:,} (%{percentInitial:.0%})',
                    marker=dict(color=[
                        _CHART_COLORS['primary'],
                        _CHART_COLORS['success'],
                        _CHART_COLORS['teal'],
                        _CHART_COLORS['purple'],
                    ]),
                    connector=dict(line=dict(color='rgba(0,0,0,0.1)', width=1)),
                    hovertemplate='%{y}: %{x:,} documents<extra></extra>',
                ))
                _funnel_fig.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=180,
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(family="system-ui, -apple-system, sans-serif", size=12),
                )
                st.plotly_chart(_funnel_fig, width='stretch')

            st.markdown("### 📊 Matter Dashboard")

            dash_left, dash_right = st.columns(2)

            with dash_left:
                # Processing progress bar
                st.markdown("**⚙️ Processing Progress**")
                proc_pct = (processed_docs / total_docs) if total_docs > 0 else 0
                st.progress(proc_pct, text=f"{processed_docs:,} of {total_docs:,} documents processed ({proc_pct*100:.0f}%)")
                if error_docs > 0:
                    st.caption(f"⚠️ {error_docs} processing errors — retry in Module 2")

                # Review progress bar
                st.markdown("**📝 Review Progress**")
                reviewable = processed_docs
                review_pct = (all_tagged / reviewable) if reviewable > 0 else 0
                st.progress(review_pct, text=f"{all_tagged:,} of {reviewable:,} reviewed ({review_pct*100:.0f}%)")

                # Production progress bar
                st.markdown("**📦 Production Progress**")
                prod_pct = (produced_docs / processed_docs) if processed_docs > 0 else 0
                st.progress(prod_pct, text=f"{produced_docs:,} of {processed_docs:,} produced ({prod_pct*100:.0f}%)")

            with dash_right:
                # Coding breakdown
                st.markdown("**🏷️ Review Decision Breakdown**")
                if all_tagged > 0:
                    _bd_labels = ['Responsive', 'Not Responsive', 'Privileged', 'Needs Review', 'Suppressed']
                    _bd_values = [responsive, not_resp, privileged, needs_review, suppressed]
                    _bd_filtered = [(l, v) for l, v in zip(_bd_labels, _bd_values) if v > 0]
                    if _bd_filtered:
                        _bd_l, _bd_v = zip(*_bd_filtered)
                        _bd_color_map = {
                            'Responsive': _CHART_COLORS['success'],
                            'Not Responsive': _CHART_COLORS['muted'],
                            'Privileged': _CHART_COLORS['purple'],
                            'Needs Review': _CHART_COLORS['warning'],
                            'Suppressed': _CHART_COLORS['danger'],
                        }
                        _bd_fig = go.Figure(data=[go.Pie(
                            labels=list(_bd_l),
                            values=list(_bd_v),
                            hole=0.45,
                            marker=dict(colors=[_bd_color_map.get(l, _CHART_COLORS['muted']) for l in _bd_l]),
                            textinfo='label+value',
                            textposition='outside',
                            hovertemplate='%{label}: %{value:,} docs (%{percent})<extra></extra>',
                        )])
                        _bd_fig.update_layout(
                            showlegend=False,
                            margin=dict(l=10, r=10, t=40, b=40),
                            height=320,
                            plot_bgcolor='rgba(0,0,0,0)',
                            paper_bgcolor='rgba(0,0,0,0)',
                            font=dict(family="system-ui, -apple-system, sans-serif", size=12),
                        )
                        st.plotly_chart(_bd_fig, width='stretch')
                    else:
                        st.info("No documents have been tagged yet.")
                else:
                    st.info("No documents have been tagged yet.")

                # Analytics status
                st.markdown("**🔬 Analytics Status**")
                sts = {
                    "Email Threading": threading_done,
                    "Near-Duplicate Detection": nd_done
                }
                for label, done in sts.items():
                    icon = "✅" if done else "⬜"
                    st.write(f"{icon} {label}")

        except Exception as e:
            st.error(f"Error reading database: {e}")

# --- MAIN INSTRUCTIONS ---
if not st.session_state['current_case_folder']:
    st.subheader("📂 Select a Case")
    if discovered_cases:
        _status_badge = {
            "Active":  "🟢 Active",
            "On Hold": "🟡 On Hold",
            "Closed":  "🔴 Closed",
        }
        cols = st.columns(3)
        for _i, _case_path in enumerate(discovered_cases):
            _case_name = os.path.basename(_case_path)
            # Pull lightweight stats
            try:
                _conn = db_manager.get_connection(_case_path)
                _cur = _conn.cursor()
                _total = _cur.execute("SELECT COUNT(*) FROM documents WHERE processing_status NOT IN ('Container_Scanned', 'Split_Source')").fetchone()[0]  # db_manager: exempt (dashboard read)
                _processed = _cur.execute(  # db_manager: exempt (dashboard read)
                    "SELECT COUNT(*) FROM documents WHERE processing_status IN ('Processed','Master')"
                ).fetchone()[0]
                _cs = db_manager.get_case_status(_case_path)
                _conn.close()
            except Exception:
                _total, _processed, _cs = 0, 0, "Unknown"

            _badge = _status_badge.get(_cs, f"⬜ {_cs}")
            with cols[_i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{_case_name}**")
                    st.caption(f"{_badge} &nbsp;·&nbsp; {_total:,} docs &nbsp;·&nbsp; {_processed:,} processed")
                    if st.button("Open", key=f"open_case_{_i}", width='stretch'):
                        _clear_case_state()
                        st.session_state['current_case_folder'] = _case_path
                        username = st.session_state.get('username')
                        if username:
                            auth_manager.save_user_pref(username, 'last_case', _case_path)
                        st.rerun()
    else:
        st.info(f"No cases found in `{cases_root}`. Use **➕ New Case / Custom Path** in the sidebar to get started.")
else:
    # --- PRODUCTION HISTORY ---
    # permission: production
    if auth_manager.has_permission('production'):
        _prod_runs = db_manager.get_production_history(selected_folder, direction='outbound')
        if _prod_runs:
            st.divider()
            st.subheader("📦 Production History")
            _pr_df = pd.DataFrame(_prod_runs)[
                ['production_name', 'created_at', 'format', 'mode', 'bates_start',
                 'bates_end', 'document_count', 'withheld_count', 'redacted_count',
                 'created_by', 'status']
            ].rename(columns={
                'production_name': 'Volume', 'created_at': 'Date', 'format': 'Format',
                'mode': 'Mode', 'bates_start': 'First Bates', 'bates_end': 'Last Bates',
                'document_count': 'Docs', 'withheld_count': 'Withheld',
                'redacted_count': 'Redacted', 'created_by': 'By', 'status': 'Status',
            })
            _pr_df['Date'] = _pr_df['Date'].str[:10]
            # Aborted runs have NULL bates_start/bates_end — render as '—'
            # instead of the literal Python string 'None' (Flag #13).
            for _col in ('First Bates', 'Last Bates'):
                _pr_df[_col] = _pr_df[_col].fillna('—').replace({None: '—'})
            st.dataframe(_pr_df, width='stretch', hide_index=True)

    # --- DEFENSIBILITY REPORT ---
    # permission: production
    if auth_manager.has_permission('production'):
        st.divider()
        st.subheader("📋 Defensibility Report")
        st.caption(
            "Generate a court-ready PDF documenting collection methodology, "
            "processing protocol, deduplication rationale, review statistics, "
            "production certification, and audit trail summary."
        )
        if st.button("📄 Generate Defensibility Report", width='stretch', key="gen_defensibility_report_btn"):
            with st.spinner("Assembling report data..."):
                import defensibility_report
                pdf_bytes = defensibility_report.generate_report(
                    case_folder=selected_folder,
                    case_name=os.path.basename(selected_folder),
                    generated_by=st.session_state.get('display_name',
                                 st.session_state.get('username', 'Unknown')),
                )
            if pdf_bytes:
                _report_filename = f"Defensibility_Report_{os.path.basename(selected_folder)}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                st.download_button(
                    "⬇️ Download Report",
                    data=pdf_bytes,
                    file_name=_report_filename,
                    mime="application/pdf",
                    width='stretch',
                )
                db_manager.log_audit(
                    selected_folder, "REPORT_GENERATED",
                    username=st.session_state.get('username'),
                    module="home",
                    details=f"Defensibility report: {_report_filename}"
                )
            else:
                st.error("Report generation failed. Check that wkhtmltopdf is installed.")

    # --- CASE MAINTENANCE (Admin Only) ---
    # permission: user_admin
    if auth_manager.has_permission('user_admin'):
      st.divider()
      with st.expander("🛠️ Case Maintenance (Advanced)"):
        st.error("### 🔥 Factory Reset Case")
        st.write("This will permanently delete ALL data for this case (DB, Text Index, Images, Logs).")
        
        case_name = os.path.basename(selected_folder)
        reset_confirm = st.text_input(f"Type '{case_name}' to confirm TOTAL RESET:", placeholder=case_name, key="factory_reset_confirm")
        
        if st.button("🚀 Perform Factory Reset", type="primary", width='stretch', key="factory_reset_btn"):
            if reset_confirm == case_name:
                with st.status("Performing deep reset...") as status:
                    # 1. Purge OpenSearch index
                    status.write("Purging OpenSearch index...")
                    index_name = os_manager.get_index_name(case_name)
                    try:
                        os_client, _ = os_manager.get_os_client()
                        if os_client and os_client.indices.exists(index=index_name):
                            os_client.indices.delete(index=index_name)
                    except: pass
                    
                    # 2. Delete Folder Contents (Handling Locks)
                    folders_to_clear = ["Processed", "Audit", "Temp_Explode", "Productions", "Reviewed"]
                    import shutil
                    import time
                    
                    for sub in folders_to_clear:
                        status.write(f"Clearing {sub} folder...")
                        p = os.path.join(selected_folder, sub)
                        if os.path.exists(p):
                            # Attempt to delete and recreate
                            for _ in range(3): # Retry loop for lazy locks
                                try:
                                    shutil.rmtree(p)
                                    os.makedirs(p)
                                    break
                                except Exception as e:
                                    time.sleep(1)
                                    status.write(f"Waiting for lock on {sub}...")
                    
                    # 3. Wipe DB — use SQL DROP+recreate instead of file delete.
                    # On Windows, os.remove() fails if ANY SQLite connection is open
                    # (Streamlit pages hold connections during reruns). DROP TABLE
                    # works regardless of other connections.
                    status.write("Wiping database...")
                    try:
                        _reset_conn = db_manager.get_connection(selected_folder)
                        _reset_tables = [r[0] for r in _reset_conn.execute(  # db_manager: exempt (schema introspection)
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()]
                        for _tbl in _reset_tables:
                            if _tbl != 'sqlite_sequence':
                                _reset_conn.execute(f"DROP TABLE IF EXISTS [{_tbl}]")  # db_manager: exempt (case reset)
                        _reset_conn.commit()
                        _reset_conn.close()
                        db_manager.init_db(selected_folder)
                    except Exception as e:
                        st.error(f"Failed to wipe DB: {e}")
                    
                    status.update(label="✅ Factory Reset Complete!", state="complete")
                    st.success("Case has been reset to factory defaults.")
                    time.sleep(2)
                    st.rerun()
            else:
                st.error("Confirmation text does not match.")

        # ── Hash Integrity Verification ──────────────────────────────
        st.divider()
        st.subheader("🔍 Verify Document Integrity")
        st.caption(
            "Re-compute MD5 hashes for all ingested files and compare against "
            "stored values. Detects accidental modification, corruption, or "
            "missing files."
        )
        # permission: verify_integrity
        if st.button("Run Integrity Check", key="btn_verify_integrity",
                     width='stretch'):
            import hashlib
            _conn_v = db_manager.get_connection(selected_folder)
            try:
                _docs = _conn_v.execute(  # db_manager: exempt (dashboard read)
                    "SELECT control_number, file_name, full_path, md5_hash "
                    "FROM documents WHERE full_path IS NOT NULL AND md5_hash IS NOT NULL"
                ).fetchall()
            finally:
                _conn_v.close()

            if not _docs:
                st.info("No documents with stored hashes found.")
            else:
                _total = len(_docs)
                _matches = 0
                _mismatches = []
                _missing = []
                _progress = st.progress(0, text="Verifying…")

                for idx, doc in enumerate(_docs):
                    _progress.progress(
                        (idx + 1) / _total,
                        text=f"Verifying {idx + 1} / {_total}…"
                    )
                    fpath = doc['full_path']
                    if not os.path.isfile(fpath):
                        _missing.append({
                            'Control Number': doc['control_number'],
                            'File Name': doc['file_name'],
                            'Expected Path': fpath,
                        })
                        continue
                    # Compute MD5
                    _h = hashlib.md5()
                    try:
                        with open(fpath, 'rb') as _f:
                            for _chunk in iter(lambda: _f.read(8192), b''):
                                _h.update(_chunk)
                        _actual = _h.hexdigest()
                    except Exception:
                        _actual = None

                    if _actual == doc['md5_hash']:
                        _matches += 1
                    else:
                        _mismatches.append({
                            'Control Number': doc['control_number'],
                            'File Name': doc['file_name'],
                            'Expected Hash': doc['md5_hash'],
                            'Actual Hash': _actual or 'ERROR',
                        })

                _progress.empty()

                # Display results
                rc1, rc2, rc3, rc4 = st.columns(4)
                rc1.metric("Total Verified", _total)
                rc2.metric("Matches ✅", _matches)
                rc3.metric("Mismatches ⚠️", len(_mismatches))
                rc4.metric("Missing Files ❌", len(_missing))

                if _mismatches:
                    st.error(f"{len(_mismatches)} file(s) have been modified since ingestion!")
                    st.dataframe(pd.DataFrame(_mismatches), width='stretch',
                                 hide_index=True)

                if _missing:
                    st.warning(f"{len(_missing)} file(s) are missing from disk!")
                    st.dataframe(pd.DataFrame(_missing), width='stretch',
                                 hide_index=True)

                if not _mismatches and not _missing:
                    st.success("All files verified — no integrity issues detected.")

                # Audit log
                try:
                    db_manager.log_audit(
                        selected_folder,
                        action="INTEGRITY_VERIFICATION",
                        username=st.session_state.get('username', ''),
                        module="Home",
                        details=json.dumps({
                            'total': _total, 'matches': _matches,
                            'mismatches': len(_mismatches),
                            'missing': len(_missing),
                        })
                    )
                except Exception:
                    pass

        # ── De-NIST Filter Configuration ─────────────────────────────
        st.divider()
        st.subheader("🚫 De-NIST Filter Configuration")
        st.caption(
            "File extensions excluded during processing (system/application files). "
            "One extension per line, including the leading dot."
        )

        _current_nist = db_manager.get_nist_extensions(selected_folder)
        _nist_text = st.text_area(
            "NIST Extensions",
            value='\n'.join(sorted(_current_nist)),
            height=200,
            key="nist_ext_editor",
            label_visibility="collapsed",
        )
        st.caption(f"{len(_current_nist)} extensions currently configured.")

        _nist_c1, _nist_c2 = st.columns(2)
        with _nist_c1:
            # permission: configure_nist
            if st.button("💾 Save Extensions", key="btn_save_nist",
                         width='stretch'):
                _parsed = [
                    line.strip().lower()
                    for line in _nist_text.strip().splitlines()
                    if line.strip()
                ]
                # Ensure all start with '.'
                _parsed = [ext if ext.startswith('.') else f'.{ext}' for ext in _parsed]
                db_manager.set_nist_extensions(selected_folder, _parsed)
                try:
                    db_manager.log_audit(
                        selected_folder,
                        action="NIST_CONFIG_UPDATED",
                        username=st.session_state.get('username', ''),
                        module="Home",
                        details=json.dumps({'extension_count': len(_parsed)})
                    )
                except Exception:
                    pass
                st.success(f"Saved {len(_parsed)} extensions.")
                st.rerun()

        with _nist_c2:
            if st.button("🔄 Reset to Default", key="btn_reset_nist",
                         width='stretch'):
                db_manager.set_nist_extensions(
                    selected_folder, list(db_manager.DEFAULT_NIST_EXTENSIONS)
                )
                st.success("Reset to default extensions.")
                st.rerun()

        # Export exclusion report
        _conn_nist = db_manager.get_connection(selected_folder)
        try:
            _excluded = _conn_nist.execute("""  -- db_manager: exempt (dashboard read)
                SELECT control_number, file_name, file_extension, custodian
                FROM documents WHERE processing_status = 'NIST_Excluded'
                ORDER BY file_extension, file_name
            """).fetchall()
        finally:
            _conn_nist.close()

        if _excluded:
            _excl_df = pd.DataFrame([dict(r) for r in _excluded])
            st.download_button(
                f"⬇️ Export Exclusion Report ({len(_excluded)} files)",
                data=_excl_df.to_csv(index=False).encode('utf-8'),
                file_name="NIST_Exclusion_Report.csv",
                mime="text/csv",
                key="dl_nist_report",
                width='stretch',
            )

        # ── Path Repair (Case Migration) ────────────────────────────
        st.divider()
        st.subheader("🔧 Path Repair (Case Migration)")
        st.caption(
            "After migrating a case to a different drive or folder structure, "
            "file paths in the database may still point to the old location. "
            "This tool detects stale paths and rebases them to the current case folder."
        )
        st.markdown(f"**Current case folder:** `{selected_folder}`")

        if st.button("🔍 Scan Path Roots", key="btn_pr_scan", width='stretch'):
            with st.spinner("Scanning paths..."):
                st.session_state['_pr_scan_result'] = db_manager.detect_path_roots(selected_folder)
            st.session_state.pop('_pr_preview_result', None)

        _pr_scan = st.session_state.get('_pr_scan_result')
        if _pr_scan:
            _tbl = _pr_scan['tables']
            _total_mismatch = sum(t['mismatched'] for t in _tbl.values())
            _total_match = sum(t['matched'] for t in _tbl.values())

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Paths", _total_match + _total_mismatch)
            c2.metric("Matched", _total_match)
            c3.metric("Mismatched", _total_mismatch,
                       delta=f"-{_total_mismatch}" if _total_mismatch else None,
                       delta_color="inverse")

            if _total_mismatch == 0:
                st.success("All paths match the current case folder. No repair needed.")
            else:
                # Show per-table breakdown
                for tname, counts in _tbl.items():
                    if counts['mismatched'] > 0:
                        st.write(f"**{tname}**: {counts['mismatched']} mismatched "
                                 f"/ {counts['total']} total")

                # Root selection
                _stale_roots = [r for r in _pr_scan['distinct_roots'] if not r['matches']]
                if len(_stale_roots) == 1:
                    _selected_old_root = _stale_roots[0]['root']
                    st.info(f"**Old root detected:** `{_selected_old_root}` "
                            f"({_stale_roots[0]['count']} paths)")
                elif len(_stale_roots) > 1:
                    _root_options = [f"{r['root']}  ({r['count']} paths)" for r in _stale_roots]
                    _root_choice = st.selectbox("Select old root to repair",
                                                _root_options, key="sb_pr_root")
                    _selected_old_root = _stale_roots[_root_options.index(_root_choice)]['root']
                else:
                    _selected_old_root = None

                if _selected_old_root:
                    st.markdown(f"**Mapping:** `{_selected_old_root}` → `{selected_folder}`")

                    # Preview button
                    if st.button("👁️ Preview Repair", key="btn_pr_preview",
                                 width='stretch'):
                        with st.spinner("Computing path mappings..."):
                            st.session_state['_pr_preview_result'] = (
                                db_manager.preview_path_repair(
                                    selected_folder, _selected_old_root))
                            st.session_state['_pr_old_root'] = _selected_old_root

                    _pr_preview = st.session_state.get('_pr_preview_result')
                    if _pr_preview:
                        st.write("---")
                        # Per-table summary
                        for tname in ('documents', 'hold_documents', 'exhibit_sets'):
                            info = _pr_preview.get(tname, {})
                            _wf = info.get('would_fix', 0)
                            if _wf > 0:
                                _fe = info.get('file_exists', '')
                                _fm = info.get('file_missing', '')
                                _detail = f" — {_fe} exist on disk, {_fm} missing" if _fe != '' else ""
                                st.write(f"**{tname}**: {_wf} paths to update{_detail}")

                        # File-missing warning
                        _total_missing = (
                            _pr_preview['documents'].get('file_missing', 0) +
                            _pr_preview['hold_documents'].get('file_missing', 0))
                        if _total_missing > 0:
                            st.warning(
                                f"{_total_missing} target file(s) not found on disk. "
                                "The case folder contents may not have been fully copied. "
                                "Paths will still be updated — you can copy files later.")

                        # Sample table
                        _samples = _pr_preview.get('samples', [])
                        if _samples:
                            import pandas as _pr_pd
                            _sample_df = _pr_pd.DataFrame(_samples)
                            _sample_df.columns = ['Table', 'ID', 'Old Path',
                                                   'New Path', 'Exists on Disk']
                            st.dataframe(_sample_df, use_container_width=True,
                                         hide_index=True)

                        # Confirmation + apply
                        _pr_confirm = st.text_input(
                            "Type **REPAIR** to confirm path update",
                            key="ti_pr_confirm")
                        if st.button("⚡ Apply Path Repair", key="btn_pr_apply",
                                     width='stretch',
                                     type="primary"):
                            if _pr_confirm.strip().upper() != 'REPAIR':
                                st.error("Please type REPAIR to confirm.")
                            else:
                                _pr_old = st.session_state.get(
                                    '_pr_old_root', _selected_old_root)
                                with st.spinner("Repairing paths..."):
                                    _pr_result = db_manager.repair_paths(
                                        selected_folder, _pr_old,
                                        username=st.session_state.get('username'))
                                if _pr_result.get('errors'):
                                    st.error(f"Errors: {_pr_result['errors']}")
                                else:
                                    st.success(
                                        f"Path repair complete — "
                                        f"documents: {_pr_result['documents_updated']}, "
                                        f"hold docs: {_pr_result['hold_updated']}, "
                                        f"exhibit sets: {_pr_result['exhibits_updated']}")
                                # Clear scan/preview state so re-scan shows fresh data
                                st.session_state.pop('_pr_scan_result', None)
                                st.session_state.pop('_pr_preview_result', None)
                                st.session_state.pop('_pr_old_root', None)
                                st.rerun()

        # ── Case Archive / Export ────────────────────────────────────
        st.divider()
        st.subheader("📦 Archive Case")
        st.caption(
            "Create a complete archive ZIP of this case for long-term storage or transfer. "
            "Includes the database, all ingested/processed files, productions, and a manifest."
        )

        if st.button("📦 Generate Case Archive", key="btn_case_archive",
                     width='stretch'):
            import zipfile
            _archive_buf = io.BytesIO()
            _case_name = os.path.basename(selected_folder)

            # Build manifest
            _manifest = {
                "case_name": _case_name,
                "case_path": selected_folder,
                "archived_at": datetime.now().isoformat(),
                "archived_by": st.session_state.get('username', ''),
            }

            # Add matter profile if available
            try:
                _mp = db_manager.get_matter_profile(selected_folder)
                if _mp:
                    _manifest["matter_profile"] = _mp
            except Exception:
                pass

            # Add document count
            try:
                _arc_conn = db_manager.get_connection(selected_folder)
                _manifest["document_count"] = _arc_conn.execute(  # db_manager: exempt (archive read)
                    "SELECT COUNT(*) FROM documents"
                ).fetchone()[0]
                _manifest["custodian_count"] = _arc_conn.execute(  # db_manager: exempt (archive read)
                    "SELECT COUNT(*) FROM custodians"
                ).fetchone()[0]
                # Production history
                try:
                    _prods = _arc_conn.execute(  # db_manager: exempt (archive read)
                        "SELECT production_name, created_at, format, document_count "
                        "FROM production_runs WHERE direction = 'outbound' ORDER BY created_at"
                    ).fetchall()
                    _manifest["productions"] = [dict(p) for p in _prods]
                except Exception:
                    pass
                _arc_conn.close()
            except Exception:
                pass

            _manifest_json = json.dumps(_manifest, indent=2, default=str)

            with st.spinner("Building case archive ZIP..."):
                with zipfile.ZipFile(_archive_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # Add manifest
                    zf.writestr("MANIFEST.json", _manifest_json)

                    # Walk entire case folder
                    for root, dirs, files in os.walk(selected_folder):
                        # Skip temp directories
                        rel_root = os.path.relpath(root, selected_folder)
                        if rel_root.startswith(('Temp_Explode', '__pycache__', '.git')):
                            continue
                        for fname in files:
                            full = os.path.join(root, fname)
                            arcname = os.path.relpath(full, selected_folder)
                            zf.write(full, arcname)

            st.download_button(
                "⬇️ Download Case Archive",
                data=_archive_buf.getvalue(),
                file_name=f"{_case_name}_ARCHIVE.zip",
                mime="application/zip",
                key="dl_case_archive",
                width='stretch',
            )

            try:
                db_manager.log_audit(
                    selected_folder,
                    action="CASE_ARCHIVED",
                    username=st.session_state.get('username', ''),
                    module="Home",
                    details=json.dumps({"case_name": _case_name})
                )
            except Exception:
                pass

        # ── Issue Coding Field Management ────────────────────────────
        st.divider()
        st.subheader("🏷️ Issue Coding Fields")
        st.caption(
            "Configure custom coding fields that appear in the Review module's coding panel. "
            "Reviewers can assign values per document. Fields export in production load files."
        )

        _cf_list = db_manager.get_coding_fields(selected_folder)
        if _cf_list:
            for _cf in _cf_list:
                _cf_col1, _cf_col2, _cf_col3 = st.columns([3, 2, 1])
                with _cf_col1:
                    st.markdown(f"**{_cf['field_name']}**")
                with _cf_col2:
                    _cf_type_label = {'picklist': 'Pick List', 'text': 'Free Text', 'boolean': 'Yes/No'}
                    st.caption(_cf_type_label.get(_cf['field_type'], _cf['field_type']))
                    if _cf['field_type'] == 'picklist' and _cf.get('pick_list_json'):
                        _opts = json.loads(_cf['pick_list_json'])
                        st.caption(f"Options: {', '.join(_opts)}")
                with _cf_col3:
                    if st.button("🗑️", key=f"del_cf_{_cf['id']}"):
                        db_manager.delete_coding_field(selected_folder, _cf['id'])
                        st.rerun()
        else:
            st.info("No custom coding fields configured. Add one below.")

        with st.form("add_coding_field", clear_on_submit=True):
            _ncf_col1, _ncf_col2 = st.columns(2)
            with _ncf_col1:
                _ncf_name = st.text_input("Field Name", placeholder="e.g., Relates to Contract Breach", key="new_coding_field_name")
            with _ncf_col2:
                _ncf_type = st.selectbox("Field Type", ['picklist', 'text', 'boolean'], key="new_coding_field_type")
            _ncf_options = st.text_input(
                "Pick List Options (comma-separated)",
                placeholder="e.g., Yes, No, Partially",
                help="Only used for picklist type. Leave empty for text/boolean.",
                key="new_coding_field_options",
            )
            if st.form_submit_button("➕ Add Coding Field", width='stretch'):
                if _ncf_name and _ncf_name.strip():
                    _ncf_pick_json = None
                    if _ncf_type == 'picklist' and _ncf_options:
                        _ncf_pick_json = json.dumps([o.strip() for o in _ncf_options.split(',') if o.strip()])
                    db_manager.create_coding_field(
                        selected_folder, _ncf_name.strip(), _ncf_type,
                        _ncf_pick_json, st.session_state.get('username', '')
                    )
                    st.success(f"Created coding field: {_ncf_name}")
                    st.rerun()
                else:
                    st.warning("Field name is required.")

# --- USER MANAGEMENT ---
# permission: user_admin
if auth_manager.has_permission('user_admin'):
    st.markdown("---")
    st.header("👥 User Management")
    st.caption("Add, modify, or remove platform users. Only Admins can access this panel.")

    all_users = auth_manager.list_users()
    _all_roles = auth_manager.list_roles()
    _ROLE_BADGE = {'admin': '👑 Admin', 'manager': '🏢 Manager', 'reviewer': '📋 Reviewer'}

    if all_users:
        user_rows = [{'Username': u['username'], 'Display Name': u['name'],
                      'Role': _ROLE_BADGE.get(u['role'], u['role'])} for u in all_users]
        st.dataframe(user_rows, width='stretch', hide_index=True)

    st.subheader("➕ Add New User")
    with st.form("add_user_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("Username", key="new_user_username")
            new_password = st.text_input("Password", type="password", key="new_user_password")
        with col2:
            new_display = st.text_input("Display Name", key="new_user_display_name")
            new_role = st.selectbox("Role", _all_roles,
                                    format_func=lambda r: _ROLE_BADGE.get(r, r.capitalize()),
                                    key="new_user_role")
        new_allowed_cases = st.multiselect(
            "Allowed Cases",
            options=_all_discovered_cases,
            format_func=lambda p: os.path.basename(p),
            key="new_user_allowed_cases",
        )
        st.caption("Leave empty for unrestricted access to all cases.")
        if st.form_submit_button("Create User", width='stretch'):
            if not new_username or not new_password or not new_display:
                st.error("All fields are required.")
            elif (pw_err := auth_manager.validate_password_complexity(new_password)):
                st.error(pw_err)
            else:
                auth_manager.create_user(new_username, new_password, new_display, new_role)
                if new_allowed_cases:
                    auth_manager.update_allowed_cases(new_username, new_allowed_cases)
                if selected_folder and os.path.isdir(selected_folder):
                    import json as _json
                    db_manager.log_audit(
                        selected_folder, "USER_CREATED",
                        username=st.session_state.get("username"),
                        module="home",
                        details=_json.dumps({"new_user": new_username, "role": new_role})
                    )
                st.success(f"✅ User '{new_username}' created as {new_role}.")
                st.rerun()

    with st.expander("🔑 Reset Password / Change Role / Delete User"):
        current_user = st.session_state.get('username', '')
        other_users = [u['username'] for u in all_users if u['username'] != current_user]
        if not other_users:
            st.info("No other users to manage.")
        else:
            target = st.selectbox("Select User", other_users, key="manage_user_select")
            action = st.radio("Action", ["Reset Password", "Change Role", "Delete User"], horizontal=True, key="manage_user_action")

            if action == "Reset Password":
                new_pw = st.text_input("New Password", type="password", key="mgmt_pw")
                if st.button("Apply Reset", key="mgmt_pw_btn"):
                    pw_err = auth_manager.validate_password_complexity(new_pw)
                    if pw_err:
                        st.error(pw_err)
                    else:
                        auth_manager.update_password(target, new_pw)
                        # permission: manage_users
                        if selected_folder and os.path.isdir(selected_folder):
                            import json as _json
                            db_manager.log_audit(
                                selected_folder, "PASSWORD_RESET",
                                username=st.session_state.get("username"),
                                module="home",
                                details=_json.dumps({"target_user": target})
                            )
                        st.success(f"✅ Password for '{target}' updated.")

            elif action == "Change Role":
                new_r = st.selectbox("New Role", _all_roles,
                                     format_func=lambda r: _ROLE_BADGE.get(r, r.capitalize()), key="mgmt_role")
                if st.button("Apply Role Change", key="mgmt_role_btn"):
                    # Capture old role before updating
                    old_role = next((u['role'] for u in all_users if u['username'] == target), None)
                    auth_manager.update_role(target, new_r)
                    if selected_folder and os.path.isdir(selected_folder):
                        import json as _json
                        db_manager.log_audit(
                            selected_folder, "USER_ROLE_CHANGED",
                            username=st.session_state.get("username"),
                            module="home",
                            details=_json.dumps({"target_user": target}),
                            old_value=old_role,
                            new_value=new_r
                        )
                    st.success(f"✅ '{target}' is now {new_r}.")
                    st.rerun()

            elif action == "Delete User":
                st.warning(f"⚠️ This will permanently delete user '{target}'.")
                if st.button("🗑️ Confirm Delete", key="mgmt_del_btn", type="primary"):
                    auth_manager.delete_user(target)
                    # permission: manage_users
                    if selected_folder and os.path.isdir(selected_folder):
                        import json as _json
                        db_manager.log_audit(
                            selected_folder, "USER_DELETED",
                            username=st.session_state.get("username"),
                            module="home",
                            details=_json.dumps({"deleted_user": target})
                        )
                    st.success(f"User '{target}' deleted.")
                    st.rerun()

    with st.expander("📂 Edit Case Restrictions"):
        st.caption("Restrict a user to specific cases. Leave empty for unrestricted access to all cases.")
        _all_usernames = [u['username'] for u in all_users]
        _restrict_target = st.selectbox("Select User", _all_usernames, key="restrict_user_select")
        _current_allowed = auth_manager.get_allowed_cases(_restrict_target) or []
        # Offer all known cases (unfiltered admin view) plus any already-stored paths as options
        _restrict_options = sorted(set(_all_discovered_cases) | set(_current_allowed))
        _selected_cases = st.multiselect(
            "Allowed Cases",
            options=_restrict_options,
            default=_current_allowed,
            format_func=lambda p: os.path.basename(p),
            key="restrict_cases_select",
        )
        _extra_path = st.text_input(
            "Add custom path not listed above",
            placeholder=rf"{cases_root}\CaseName",
            key="restrict_extra_path",
        )
        if st.button("💾 Save Case Restrictions", key="restrict_save_btn"):
            _final = list(_selected_cases)
            if _extra_path and _extra_path not in _final:
                _final.append(_extra_path)
            auth_manager.update_allowed_cases(_restrict_target, _final)
            if selected_folder and os.path.isdir(selected_folder):
                import json as _json
                db_manager.log_audit(
                    selected_folder, "USER_CASE_RESTRICTIONS_CHANGED",
                    username=st.session_state.get("username"),
                    module="home",
                    details=_json.dumps({"target_user": _restrict_target, "allowed_cases": _final}),
                )
            if _final:
                st.success(f"✅ '{_restrict_target}' restricted to {len(_final)} case(s).")
            else:
                st.success(f"✅ '{_restrict_target}' now has unrestricted case access.")
            st.rerun()

    with st.expander("🔒 Document Visibility"):
        st.caption(
            "Control which documents this user can see in the Review module. "
            "Default is Full Universe (no restriction)."
        )
        _vis_all_usernames = [u['username'] for u in all_users]
        _vis_target = st.selectbox("Select User", _vis_all_usernames, key="vis_user_select")
        _vis_target_role = next((u['role'] for u in all_users if u['username'] == _vis_target), '')

        # Admin users cannot be restricted
        if _vis_target_role == 'admin':
            st.info("Admin users always have full document visibility.")
        else:
            _current_vis = auth_manager.get_doc_visibility(_vis_target)
            _current_mode = _current_vis['mode']
            _current_hidden = _current_vis['hidden_tags']

            _mode_options = ["full", "produced_only", "hidden_tags"]
            _mode_labels = {
                "full": "Full Universe — all processed documents",
                "produced_only": "Produced Only — Bates-stamped documents only",
                "hidden_tags": "Hidden Tags — full universe minus specified tags",
            }
            _vis_mode_choice = st.radio(
                "Visibility mode",
                _mode_options,
                index=_mode_options.index(_current_mode),
                format_func=lambda x: _mode_labels[x],
                key=f"vis_mode_{_vis_target}",
            )

            _vis_new_hidden_tags = []
            if _vis_mode_choice == "hidden_tags":
                _vis_case = selected_folder
                if _vis_case and os.path.isdir(_vis_case):
                    _all_tag_cats = db_manager.get_tag_categories(_vis_case)
                    _all_tag_members = [
                        m for _cat in _all_tag_cats.values()
                        for m in _cat.get('members', [])
                    ]
                    _vis_new_hidden_tags = st.multiselect(
                        "Tags to hide from this user",
                        options=_all_tag_members,
                        default=[t for t in _current_hidden if t in _all_tag_members],
                        help="Documents carrying ANY of these tags will be invisible to this user in Review.",
                        key=f"vis_hidden_{_vis_target}",
                    )
                else:
                    st.warning("Select a case first to see available tags.")

            if st.button("💾 Save Visibility Settings", key=f"vis_save_{_vis_target}"):
                auth_manager.update_doc_visibility(
                    _vis_target,
                    mode=_vis_mode_choice,
                    hidden_tags=_vis_new_hidden_tags if _vis_mode_choice == "hidden_tags" else None,
                )
                if selected_folder and os.path.isdir(selected_folder):
                    db_manager.log_audit(
                        selected_folder,
                        "USER_VISIBILITY_CHANGED",
                        username=st.session_state.get('username'),
                        module="Home",
                        details=f"Set {_vis_target} to {_vis_mode_choice}" +
                                (f" (hidden: {', '.join(_vis_new_hidden_tags)})" if _vis_new_hidden_tags else ""),
                        old_value=_current_mode,
                        new_value=_vis_mode_choice,
                    )
                st.success(f"✅ Visibility updated for {_vis_target}.")
                st.rerun()

# --- ROLE PERMISSION EDITOR ---
# permission: user_admin
if auth_manager.has_permission('user_admin'):
    import json as _json_perms
    st.markdown("---")
    st.header("🔐 Role Permissions")
    st.caption("Configure which permissions each role has. Changes take effect on next page load for affected users.")

    _PERM_CATEGORIES = {
        "Pipeline": ['ingest', 'process', 'analytics'],
        "Review": ['review', 'tag', 'redact', 'export_csv', 'export_pdf',
                   'str_run', 'str_export', 'column_picker', 'saved_search_global'],
        "Production": ['production', 'inbound_production', 'privilege_log'],
        "Admin": ['user_admin', 'case_settings', 'audit_view', 'sync'],
    }

    _rpe_tab_editor, _rpe_tab_custom = st.tabs(["✏️ Edit Role Permissions", "➕ Custom Roles"])

    with _rpe_tab_editor:
        _edit_role = st.selectbox("Role to configure", _all_roles, key="rpe_role_select",
                                  format_func=lambda r: _ROLE_BADGE.get(r, r.capitalize()))
        if _edit_role == 'admin':
            st.info("👑 Admin role always has all permissions (`*` wildcard). Cannot be edited.")
        else:
            _current_perms = auth_manager.get_role_permissions_for_ui(_edit_role)
            _is_wildcard = '*' in _current_perms

            _new_perms: set = set()
            _cat_cols = st.columns(len(_PERM_CATEGORIES))
            for _ci, (_cat, _cat_perms) in enumerate(_PERM_CATEGORIES.items()):
                with _cat_cols[_ci]:
                    st.markdown(f"**{_cat}**")
                    for _p in _cat_perms:
                        _checked = _is_wildcard or _p in _current_perms
                        if st.checkbox(_p, value=_checked, key=f"rpe_{_edit_role}_{_p}"):
                            _new_perms.add(_p)

            if st.button("💾 Save Permissions", key="rpe_save_btn", type="primary"):
                _old_perms_list = sorted(_current_perms)
                auth_manager.save_role_permissions(_edit_role, sorted(_new_perms))
                if selected_folder and os.path.isdir(selected_folder):
                    db_manager.log_audit(
                        selected_folder, "ROLE_PERMISSIONS_CHANGED",
                        username=st.session_state.get("username"),
                        module="home",
                        details=_json_perms.dumps({"role": _edit_role}),
                        old_value=_json_perms.dumps(_old_perms_list),
                        new_value=_json_perms.dumps(sorted(_new_perms))
                    )
                st.success(f"✅ Permissions for **{_edit_role}** saved.")
                st.rerun()

    with _rpe_tab_custom:
        _custom_roles_list = [r for r in _all_roles if r not in ('admin', 'manager', 'reviewer')]

        st.subheader("Create New Role")
        with st.form("create_custom_role_form"):
            _cr_name = st.text_input("Role name (lowercase, no spaces)", placeholder="e.g. contract_reviewer", key="create_role_name")
            st.markdown("**Permissions:**")
            _cr_new_perms: list = []
            _cr_cols = st.columns(len(_PERM_CATEGORIES))
            for _ci2, (_cat2, _cat_perms2) in enumerate(_PERM_CATEGORIES.items()):
                with _cr_cols[_ci2]:
                    st.markdown(f"**{_cat2}**")
                    for _p2 in _cat_perms2:
                        if st.checkbox(_p2, value=False, key=f"cr_{_p2}"):
                            _cr_new_perms.append(_p2)
            if st.form_submit_button("➕ Create Role", width='stretch'):
                _cr_name_clean = _cr_name.strip().lower().replace(' ', '_')
                if not _cr_name_clean:
                    st.error("Role name is required.")
                elif _cr_name_clean in _all_roles:
                    st.error(f"Role '{_cr_name_clean}' already exists.")
                else:
                    auth_manager.create_custom_role(_cr_name_clean, _cr_new_perms)
                    if selected_folder and os.path.isdir(selected_folder):
                        db_manager.log_audit(
                            selected_folder, "ROLE_CREATED",
                            username=st.session_state.get("username"),
                            module="home",
                            details=_json_perms.dumps({"role": _cr_name_clean, "permissions": _cr_new_perms})
                        )
                    st.success(f"✅ Custom role '{_cr_name_clean}' created.")
                    st.rerun()

        if _custom_roles_list:
            st.subheader("Delete Custom Role")
            _del_role = st.selectbox("Role to delete", _custom_roles_list, key="del_custom_role")
            if st.button("🗑️ Delete Role", key="del_custom_role_btn", type="primary"):
                _del_ok, _del_err = auth_manager.delete_custom_role(_del_role)
                if _del_ok:
                    if selected_folder and os.path.isdir(selected_folder):
                        db_manager.log_audit(
                            selected_folder, "ROLE_DELETED",
                            username=st.session_state.get("username"),
                            module="home",
                            details=_json_perms.dumps({"role": _del_role})
                        )
                    st.success(f"✅ Role '{_del_role}' deleted.")
                    st.rerun()
                else:
                    st.error(f"❌ {_del_err}")
        else:
            st.info("No custom roles defined yet.")

# --- AUDIT LOG VIEWER ---
# permission: audit_view
if auth_manager.has_permission('audit_view') and selected_folder and os.path.isdir(selected_folder):
    st.divider()
    with st.expander("🔍 Audit Log Viewer (Admin)"):
        import json as _json_audit
        st.caption("Full audit trail of all user actions in this case. Filter and export as needed.")

        _audit_conn = db_manager.get_connection(selected_folder)
        try:
            _audit_users = [r[0] for r in _audit_conn.execute(  # db_manager: exempt (audit log read)
                "SELECT DISTINCT username FROM audit_log WHERE username IS NOT NULL ORDER BY username"
            ).fetchall()]
            _audit_modules = [r[0] for r in _audit_conn.execute(  # db_manager: exempt (audit log read)
                "SELECT DISTINCT module FROM audit_log WHERE module IS NOT NULL ORDER BY module"
            ).fetchall()]
            _audit_actions = [r[0] for r in _audit_conn.execute(  # db_manager: exempt (audit log read)
                "SELECT DISTINCT action FROM audit_log WHERE action IS NOT NULL ORDER BY action"
            ).fetchall()]
        except sqlite3.OperationalError:
            # Pre-migration DB missing username/module columns — degrade gracefully.
            st.warning(
                "This database is missing one or more audit log columns (`username`, `module`). "
                "Re-open the case to trigger the schema migration, then refresh this page."
            )
            _audit_users = []
            _audit_modules = []
            try:
                _audit_actions = [r[0] for r in _audit_conn.execute(  # db_manager: exempt (audit log read)
                    "SELECT DISTINCT action FROM audit_log WHERE action IS NOT NULL ORDER BY action"
                ).fetchall()]
            except sqlite3.OperationalError:
                _audit_actions = []
        finally:
            _audit_conn.close()

        _af1, _af2, _af3, _af4, _af5 = st.columns([2, 2, 2, 2, 2])
        _flt_user = _af1.selectbox("User", ["All"] + _audit_users, key="audit_flt_user")
        _flt_module = _af2.selectbox("Module", ["All"] + _audit_modules, key="audit_flt_module")
        _flt_action = _af3.selectbox("Action", ["All"] + _audit_actions, key="audit_flt_action")
        _flt_cn = _af4.text_input("Control Number", placeholder="e.g. ABC000001", key="audit_flt_cn")
        _flt_date = _af5.date_input("Since Date", value=None, key="audit_flt_date")

        _audit_sql = "SELECT timestamp, username, module, action, control_number, details, old_value, new_value FROM audit_log WHERE 1=1"
        _audit_params = []
        if _flt_user != "All":
            _audit_sql += " AND username=?"; _audit_params.append(_flt_user)
        if _flt_module != "All":
            _audit_sql += " AND module=?"; _audit_params.append(_flt_module)
        if _flt_action != "All":
            _audit_sql += " AND action=?"; _audit_params.append(_flt_action)
        if _flt_cn:
            _audit_sql += " AND control_number LIKE ?"; _audit_params.append(f"%{_flt_cn}%")
        if _flt_date:
            _audit_sql += " AND timestamp >= ?"; _audit_params.append(str(_flt_date))
        _audit_sql += " ORDER BY timestamp DESC LIMIT 2000"

        _audit_conn2 = db_manager.get_connection(selected_folder)
        try:
            _audit_df = pd.read_sql_query(_audit_sql, _audit_conn2, params=_audit_params or None)
        finally:
            _audit_conn2.close()

        st.caption(f"Showing {len(_audit_df):,} rows (capped at 2,000).")
        st.dataframe(_audit_df, width='stretch', hide_index=True, height=400)

        # ── Export Buttons ────────────────────────────────────────────────────
        _exp1, _exp2, _exp3 = st.columns(3)

        # CSV (existing)
        _audit_csv = _audit_df.to_csv(index=False).encode('utf-8')
        _exp1.download_button(
            "⬇️ CSV",
            data=_audit_csv,
            file_name=f"{os.path.basename(selected_folder)}_AUDIT_LOG.csv",
            mime="text/csv",
            key="audit_export_csv",
            width='stretch',
        )

        # Excel (new)
        try:
            import io as _audit_io
            _audit_xlsx_buf = _audit_io.BytesIO()
            with pd.ExcelWriter(_audit_xlsx_buf, engine='openpyxl') as _xw:
                _audit_df.to_excel(_xw, index=False, sheet_name='Audit Log')
                _meta_rows = [
                    {'Field': 'Case', 'Value': os.path.basename(selected_folder)},
                    {'Field': 'Generated', 'Value': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'Field': 'Generated By', 'Value': st.session_state.get('display_name',
                                 st.session_state.get('username', 'Unknown'))},
                    {'Field': 'User Filter', 'Value': _flt_user},
                    {'Field': 'Module Filter', 'Value': _flt_module},
                    {'Field': 'Action Filter', 'Value': _flt_action},
                    {'Field': 'Control # Filter', 'Value': _flt_cn or 'None'},
                    {'Field': 'Date Filter', 'Value': str(_flt_date) if _flt_date else 'None'},
                    {'Field': 'Total Rows', 'Value': str(len(_audit_df))},
                ]
                pd.DataFrame(_meta_rows).to_excel(_xw, index=False, sheet_name='Export Metadata')

                _ws = _xw.sheets['Audit Log']
                for _col_cells in _ws.columns:
                    _max_len = max(len(str(_cell.value or '')) for _cell in _col_cells)
                    _col_letter = _col_cells[0].column_letter
                    _ws.column_dimensions[_col_letter].width = min(_max_len + 4, 50)
                _ws.freeze_panes = 'A2'

            _exp2.download_button(
                "⬇️ Excel",
                data=_audit_xlsx_buf.getvalue(),
                file_name=f"{os.path.basename(selected_folder)}_AUDIT_LOG.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="audit_export_xlsx",
                width='stretch',
            )
        except Exception as _xlsx_err:
            _exp2.caption(f"Excel export unavailable: {_xlsx_err}")

        # PDF (new)
        if _exp3.button("⬇️ PDF", key="audit_export_pdf", width='stretch'):
            with st.spinner("Generating audit trail PDF..."):
                import defensibility_report
                _audit_filters = {
                    'User': _flt_user,
                    'Module': _flt_module,
                    'Action': _flt_action,
                    'Control Number': _flt_cn or 'None',
                    'Since Date': str(_flt_date) if _flt_date else 'None',
                }
                _audit_rows = _audit_df.to_dict('records')
                _audit_pdf = defensibility_report.generate_audit_export_pdf(
                    case_folder=selected_folder,
                    case_name=os.path.basename(selected_folder),
                    generated_by=st.session_state.get('display_name',
                                 st.session_state.get('username', 'Unknown')),
                    filters=_audit_filters,
                    rows=_audit_rows,
                )
            if _audit_pdf:
                st.download_button(
                    "⬇️ Download Audit PDF",
                    data=_audit_pdf,
                    file_name=f"{os.path.basename(selected_folder)}_AUDIT_LOG.pdf",
                    mime="application/pdf",
                    key="audit_pdf_download",
                    width='stretch',
                )
                db_manager.log_audit(
                    selected_folder, "REPORT_GENERATED",
                    username=st.session_state.get('username'),
                    module="home",
                    details="Audit trail PDF export"
                )
            else:
                st.error("PDF generation failed. Check that wkhtmltopdf is installed.")

# --- SYSTEM SETTINGS (Admin Only) ---
# permission: user_admin
if auth_manager.has_permission('user_admin'):
    st.divider()
    with st.expander("🔐 System Backend Settings"):
        st.subheader("OpenSearch Credentials")
        st.info("OpenSearch is running locally without authentication (`plugins.security.disabled: true`). No password or CA fingerprint is required.")


        st.subheader("Tika Server")
        st.write(f"Endpoint: `{config.TIKA_ENDPOINT}`")
        if not is_port_open(9998):
            if st.button("🚀 Launch Tika Server", key="main_launch_tika"):
                launch_service(f'java -Xmx8g -jar "{TIKA_JAR}"', "Tika Server")

# --- SIDEBAR: DEPENDENCY STATUS (bottom) ---
st.sidebar.markdown("---")
st.sidebar.header("🛠️ Dependencies")
_tika_online = is_port_open(9998)
_os_online = is_port_open(9200)
if _tika_online:
    st.sidebar.success("✅ Tika: Online")
else:
    st.sidebar.error("❌ Tika: Offline")
    if st.sidebar.button("Launch Tika", key="sb_launch_tika"):
        launch_service(f'java -Xmx8g -jar "{TIKA_JAR}"', "Tika Server")
if _os_online:
    st.sidebar.success("✅ OpenSearch: Online")
else:
    st.sidebar.error("❌ OpenSearch: Offline")
    if st.sidebar.button("Launch OpenSearch", key="sb_launch_os"):
        launch_service(OS_BAT, "OpenSearch")