# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        5_Production.py
# version:       1.23.8
# project:       Respondeo eDiscovery Platform
# project_ver:   2.16.0
# last_modified: 2026-06-01 12:00
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import os
import io
import json
import zipfile
import pandas as pd
import db_manager
import shutil
import time
import config
from datetime import datetime

import logging
logger = logging.getLogger(__name__)
# Mute Streamlit headless warnings when multiprocessing ghost-workers re-import this file on Windows
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)
import streamlit as st
import auth_manager
import ui_utils
import os_manager
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent.parent / "assets"

st.set_page_config(page_title="Respondeo | Production", layout="wide", page_icon=str(_ASSETS / "favicon.png"))
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()

if not auth_manager.check_login(): st.stop()
# permission: production
auth_manager.require_permission('production')
auth_manager.show_user_info()

try:
    import universal_imager
    IMAGER_AVAILABLE = True
except ImportError:
    IMAGER_AVAILABLE = False

# ── ZIP Builder Functions (module-level for @st.cache_data) ──────────────────

@st.cache_data(ttl=300, show_spinner="Building deliverable ZIP…")
def _build_counsel_zip(_prod_name, _prod_path):
    """ZIP containing only deliverable folders: IMAGES/, NATIVES/, TEXT/, .dat, .opt, privilege log."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for folder in ('IMAGES', 'NATIVES', 'TEXT'):
            folder_path = os.path.join(_prod_path, folder)
            if not os.path.isdir(folder_path):
                continue
            for root, _dirs, files in os.walk(folder_path):
                for fname in files:
                    full = os.path.join(root, fname)
                    arcname = os.path.relpath(full, _prod_path)
                    zf.write(full, arcname)
        # Add load files and privilege log from root (.dat, .opt, privilege log)
        for fname in os.listdir(_prod_path):
            if fname.lower().endswith(('.dat', '.opt')):
                zf.write(os.path.join(_prod_path, fname), fname)
            elif 'privilege_log' in fname.lower() and fname.lower().endswith(('.csv', '.xlsx')):
                zf.write(os.path.join(_prod_path, fname), fname)
    return buf.getvalue()


@st.cache_data(ttl=300, show_spinner="Building full archive ZIP…")
def _build_full_zip(_prod_name, _prod_path):
    """ZIP of the entire production folder for internal archival."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(_prod_path):
            for fname in files:
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, _prod_path)
                zf.write(full, arcname)
    return buf.getvalue()


# ── Privilege Log Shared Definitions (used by both QC tab and production) ────

_PL_ABBREV_MAP = {
    "ac":                   "Attorney-Client Privilege",
    "a-c":                  "Attorney-Client Privilege",
    "attorney client":      "Attorney-Client Privilege",
    "attorney-client":      "Attorney-Client Privilege",
    "ac priv":              "Attorney-Client Privilege",
    "acp":                  "Attorney-Client Privilege",
    "wp":                   "Attorney Work Product",
    "work prod":            "Attorney Work Product",
    "work product":         "Attorney Work Product",
    "awp":                  "Attorney Work Product",
    "ci":                   "Common Interest Privilege",
    "common interest":      "Common Interest Privilege",
    "ac/wp":                "Attorney-Client Privilege and Work Product",
    "acp/wp":               "Attorney-Client Privilege and Work Product",
}

def _pl_fuzzy_match_privilege_reason(raw_tag_str: str, override: str) -> str:
    import re as _re_priv
    if override != "Auto-detect from tags":
        return override
    t = str(raw_tag_str or '').lower()
    for abbrev in sorted(_PL_ABBREV_MAP, key=len, reverse=True):
        if _re_priv.search(r'\b' + _re_priv.escape(abbrev) + r'\b', t):
            return _PL_ABBREV_MAP[abbrev]
    t_orig = str(raw_tag_str or '')
    if 'Work Product' in t_orig and ('Privileged' in t_orig or 'Attorney-Client' in t_orig):
        return 'Attorney-Client Privilege and Work Product'
    if 'Work Product' in t_orig:
        return 'Attorney Work Product'
    if 'Common Interest' in t_orig:
        return 'Common Interest Privilege'
    return '(No basis specified)'

def _pl_resolve_privilege_basis(row, override, mark_reasons_str):
    """Three-tier privilege basis: mark reasons → tags → placeholder."""
    if override != "Auto-detect from tags":
        return override
    if mark_reasons_str:
        reasons = [r.strip() for r in mark_reasons_str.split(',') if r.strip()]
        if reasons:
            seen = set()
            unique = []
            for r in reasons:
                if r not in seen:
                    seen.add(r)
                    unique.append(r)
            return ', '.join(unique)
    tags = row.get('tags', '') or ''
    if tags.strip():
        return _pl_fuzzy_match_privilege_reason(tags, "Auto-detect from tags")
    return '(No basis specified)'

_PL_COLUMN_DEFS = [
    ('control_number',    'Control Number',     True),
    ('begdoc',            'BegBates',           True),
    ('enddoc',            'EndBates',           True),
    ('privilege_basis',   'Privilege Basis',    True),
    ('disposition',       'Disposition',        True),
    ('description',       'Description',        True),
    ('date_sent',         'Date',               True),
    ('email_from',        'From',               True),
    ('email_to',          'To',                 True),
    ('email_cc',          'CC',                 True),
    ('email_subject',     'Subject / Title',    True),
    ('custodian',         'Custodian',          True),
    ('record_type',       'Record Type',        False),
    ('file_name',         'File Name',          False),
    ('confidentiality',   'Confidentiality',    False),
    ('source_collection', 'Source Collection',  False),
    ('page_count',        'Page Count',         False),
    ('redaction_pages',   'Redacted Pages',     False),
    ('reviewer_notes',    'Reviewer Notes',     False),
    ('individuals',       'Individuals Involved', False),
    ('bates_display',     'Bates Range',        False),
]
_PL_COL_KEY_TO_DISPLAY = {k: d for k, d, _ in _PL_COLUMN_DEFS}
_PL_DEFAULT_COLS = [k for k, _, on in _PL_COLUMN_DEFS if on]
_PL_ALL_COL_KEYS = [k for k, _, _ in _PL_COLUMN_DEFS]

def _pl_merge_individuals(row):
    """Combine From/To/CC into a deduplicated 'Individuals Involved' string."""
    import re as _re_ind
    _people = set()
    for field in ['email_from', 'email_to', 'email_cc']:
        val = row.get(field, '')
        if not val:
            continue
        for part in str(val).split(';'):
            part = part.strip()
            cleaned = _re_ind.sub(r'<[^>]+>', '', part).strip()
            cleaned = _re_ind.sub(r'\s+', ' ', cleaned).strip(' ",\'')
            if cleaned and '@' not in cleaned:
                _people.add(cleaned)
            elif cleaned:
                _people.add(cleaned)
    return '; '.join(sorted(_people)) if _people else ''

def _pl_compute_page_bates(begdoc, page_number):
    """Given begdoc and a 0-based page number, return that page's Bates number."""
    import re as _re_bates
    if not begdoc or begdoc == '(not yet produced)':
        return None
    match = _re_bates.match(r'^([A-Za-z]+-?)(\d+)$', begdoc)
    if not match:
        return begdoc
    prefix, num_str = match.groups()
    return f"{prefix}{str(int(num_str) + page_number).zfill(len(num_str))}"

def _pl_format_bates(row):
    """Disposition-aware Bates formatting with per-page Bates numbers."""
    _beg = row.get('begdoc', '')
    _disp = row.get('_disposition_key', '')
    _redact_pages = row.get('redacted_pages_list', '')
    if not _beg or _beg == '(not yet produced)':
        if _redact_pages and _disp == 'Redact':
            _pg_count = len(str(_redact_pages).split(','))
            return f"(not yet produced — {_pg_count} pages redacted)"
        return '(not yet produced)'
    if _disp == 'Withhold':
        return str(_beg)
    if _disp == 'Redact' and _redact_pages:
        _page_nums = sorted(set(
            int(p.strip()) for p in str(_redact_pages).split(',')
            if p.strip().isdigit()
        ))
        _bates_nums = [b for pg in _page_nums if (b := _pl_compute_page_bates(_beg, pg))]
        if _bates_nums:
            return ', '.join(_bates_nums)
    return str(_beg)

# ─────────────────────────────────────────────────────────────────────────────

case_folder = st.session_state.get('current_case_folder')
if not case_folder:
    st.error("Please select a case in 'Home' first!")
    st.stop()

# --- CASE LIFECYCLE GATE ---
# permission: view_production_downloads
# beta-2.10 Commit 7: removed st.stop() so tab_privlog renders on closed
# cases. Tab-level gating (inside `with tab_outbound:`) handles the three
# outbound write-surfaces; tab_privlog is read-only, its save-profile
# buttons are already disabled-gated via `not _case_closed` at line 3795.
# Matches the warn-without-halt pattern in 4_Review.py:297-302 and
# 3_Analytics.py:81-82.
_case_status = db_manager.get_case_status(case_folder)
_case_closed = (_case_status == 'Closed')
if _case_closed and not st.session_state.get('prod_finalized'):
    st.warning('🔒 This matter is closed. Write operations are disabled.')
elif _case_closed:
    st.warning('🔒 This matter is closed. Downloads are available below.')

# ── Stale-Production Detector (DB-backed, beta-2.10) ─────────────────────────
# Consults production_runs.status to distinguish legitimately-staged Pass 1
# files (status in 'in_progress', 'pass1_complete', 'finalizing') from truly
# abandoned leftovers (no DB row, or status in 'finalized', 'aborted').
# Survives browser close — session state is no longer load-bearing.
_productions_dir = os.path.join(case_folder, "Productions")
if os.path.isdir(_productions_dir) and not _case_closed:
    # Build a name → status map from the DB for quick lookup
    _prod_status_map = dict(db_manager.get_productions_with_staging_files(case_folder))

    _stale_volumes = []
    for _vol_name in os.listdir(_productions_dir):
        _vol_path = os.path.join(_productions_dir, _vol_name)
        if not os.path.isdir(_vol_path):
            continue
        _images_dir = os.path.join(_vol_path, "IMAGES")
        _natives_dir = os.path.join(_vol_path, "NATIVES")
        _temp_count = 0
        _staged_count = 0
        if os.path.isdir(_images_dir):
            _temp_count = sum(1 for f in os.listdir(_images_dir) if f.startswith("TEMP_"))
        if os.path.isdir(_natives_dir):
            _staged_count = sum(1 for f in os.listdir(_natives_dir) if f.startswith("STAGED_"))
        if _temp_count > 0 or _staged_count > 0:
            # Only flag if DB says this production is truly abandoned.
            # Missing row OR terminal status = orphan. Active lifecycle = legitimate.
            _db_status = _prod_status_map.get(_vol_name)
            _is_orphan = (_db_status is None) or (_db_status in ('finalized', 'aborted'))
            if _is_orphan:
                _stale_volumes.append((_vol_name, _vol_path, _temp_count, _staged_count))

    if _stale_volumes:
        _stale_summary = ", ".join(
            f"**{v[0]}** ({v[2]} temp, {v[3]} staged)" for v in _stale_volumes
        )
        st.warning(
            f"Orphaned files from abandoned productions detected: {_stale_summary}. "
            f"These are leftover from a Pass 1 that did not complete."
        )
        # permission: production
        if auth_manager.has_permission('production'):
            if st.button("Clean Up Orphaned Files", key="stale_cleanup"):
                _cleaned_files = 0
                _cleaned_folders = 0
                for _vol_name, _vol_path, _tc, _sc in _stale_volumes:
                    _images_dir = os.path.join(_vol_path, "IMAGES")
                    _natives_dir = os.path.join(_vol_path, "NATIVES")
                    if os.path.isdir(_images_dir):
                        for f in os.listdir(_images_dir):
                            if f.startswith("TEMP_"):
                                os.remove(os.path.join(_images_dir, f))
                                _cleaned_files += 1
                    if os.path.isdir(_natives_dir):
                        for f in os.listdir(_natives_dir):
                            if f.startswith("STAGED_"):
                                os.remove(os.path.join(_natives_dir, f))
                                _cleaned_files += 1
                    _remaining = sum(
                        len(files) for _, _, files in os.walk(_vol_path)
                    )
                    if _remaining == 0:
                        shutil.rmtree(_vol_path)
                        _cleaned_folders += 1
                try:
                    db_manager.log_audit(
                        case_folder, "PRODUCTION_STALE_CLEANUP",
                        username=st.session_state.get('username', 'unknown'), module="Production",
                        details=json.dumps({
                            "volumes": [v[0] for v in _stale_volumes],
                            "files_removed": _cleaned_files,
                            "folders_removed": _cleaned_folders,
                        })
                    )
                except Exception:
                    pass
                st.success(
                    f"Cleaned up {_cleaned_files} orphaned files"
                    + (f" and {_cleaned_folders} empty folders" if _cleaned_folders else "")
                    + "."
                )
                st.rerun()

st.title("Module 5: Outbound Production & Privilege Log 📦")

# Inbound Productions extracted to pages/9_InboundProduction.py in beta-2.10
# Commit 6. This page now covers outbound assembly + privilege log only.
tab_outbound, tab_privlog = st.tabs([
    "📦 Outbound Production",
    "📋 Privilege Log",
])

# ==============================================================================
# TAB 1: OUTBOUND PRODUCTION (existing content)
# ==============================================================================
with tab_outbound:
    # Hide the selection grid while the Pass 1 checkpoint or post-finalization UI is active.
    # Those phases are rendered by the gates near line 2218; without this guard the grid
    # would render above them because st.stop() cannot un-render earlier output.
    _show_selection_grid = not (
        (st.session_state.get('prod_pass1_complete') and not st.session_state.get('prod_finalized'))
        or (st.session_state.get('prod_finalized') and st.session_state.get('prod_pass1'))
    )

    if _show_selection_grid:
        st.markdown("---")

        # --- MANUAL SELECTION GRID ---
        st.header("1. Select Documents for Production")
        st.caption("Auto-select by tag or manually check the boxes of the documents you want to include in this production set. Once selected, click Confirm.")

        conn_grid = db_manager.get_connection(case_folder)
        # Only show internal, processed documents.
        # Mandatory inbound exclusion (beta-2.10 Commit 3) is embedded directly
        # in the initial WHERE clause rather than appended via a user-toggleable
        # checkbox — inbound documents (opposing counsel's productions) must
        # NEVER appear in outbound assembly under any user setting.
        grid_sql = f"""
            SELECT control_number, parent_id, group_id, file_name, tags, file_size_kb,
                   custodian, privilege_status, redaction_status, file_extension, page_count,
                   production_category
            FROM documents
            WHERE processing_status IN ('Processed', 'Master')
              AND {db_manager.OUTBOUND_SOURCE_FILTER_SQL}
        """

        st.subheader("Filter Available Documents")
        # Columns rebalanced after removal of "Exclude External" checkbox
        # (beta-2.10 Commit 3): col1 = noise/dup reduction, col2 = review-state.
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            exclude_previously_produced = st.checkbox("Exclude Previously Produced", value=True, help="Prevents previously produced documents from appearing.", key="exclude_prev_produced")
            exclude_suppressed = st.checkbox("Exclude Suppressed", value=True, help="Hides known dupes/junk from the grid.", key="exclude_suppressed")
        with f_col2:
            exclude_non_responsive = st.checkbox("Exclude Non-Responsive", value=True, help="Hides documents tagged Non-Responsive from the production grid.", key="exclude_non_responsive")
            # permission: manage_production
            exclude_clawback = st.checkbox("Exclude Clawback-Demanded", value=True, help="Hard-blocks documents with an active clawback demand from this production.", key="exclude_clawback")

        st.info(
            "ℹ️ **Privilege handling is automatic.** Documents marked **Withhold** receive placeholder "
            "slip sheets. Documents marked **Redact** are produced with redaction marks burned in. "
            "Both appear on the privilege log. Set dispositions in the Review module's coding panel."
        )

        if exclude_previously_produced:
            grid_sql += " AND (begdoc IS NULL OR begdoc = '')"
        if exclude_suppressed:
            grid_sql += " AND (tags NOT LIKE '%Suppressed%' OR tags IS NULL)"
        if exclude_non_responsive:
            grid_sql += " AND (tags NOT LIKE '%Non-Responsive%' OR tags IS NULL) AND (tags NOT LIKE '%Not Responsive%' OR tags IS NULL)"
        if exclude_clawback:
            grid_sql += " AND (clawback_status != 'Clawback_Demanded' OR clawback_status IS NULL)"
        grid_df = pd.read_sql_query(grid_sql, conn_grid)

        # --- Family hierarchy for sorting and display ---
        if not grid_df.empty:
            grid_df['_family_root'] = grid_df['group_id']
            grid_df['_is_child'] = grid_df.apply(
                lambda r: pd.notna(r['parent_id']) and str(r['parent_id']).strip() != '', axis=1
            )
            grid_df = grid_df.sort_values(by=['_family_root', 'control_number']).reset_index(drop=True)
            grid_df['document_display'] = grid_df.apply(
                lambda r: f"\u21b3 {r['file_name']}" if r['_is_child'] else r['file_name'],
                axis=1
            )

        conn_grid.close()

        if grid_df.empty:
            st.info("No unproduced internal documents remain. All documents have been produced.")
            st.session_state['production_selection'] = []
        else:
            # --- Family count metrics ---
            _n_families = grid_df['_family_root'].nunique()
            _n_parents = (~grid_df['_is_child']).sum()
            _n_children = grid_df['_is_child'].sum()
            _n_redact = (grid_df['privilege_status'] == 'Redact').sum()
            _n_withhold = (grid_df['privilege_status'] == 'Withhold').sum()
            _fm1, _fm2, _fm3, _fm4, _fm5 = st.columns(5)
            _fm1.metric("Document Families", _n_families)
            _fm2.metric("Parents / Standalone", int(_n_parents))
            _fm3.metric("Children / Attachments", int(_n_children))
            _fm4.metric("Redact", int(_n_redact))
            _fm5.metric("Withhold", int(_n_withhold))

            # Build unique tags list for the auto-select/deselect dropdowns
            all_tags = set()
            for t_str in grid_df['tags'].dropna():
                for t in str(t_str).replace(',', ';').split(';'):
                    if t.strip(): all_tags.add(t.strip())

            # --- Column Filters ---
            with st.expander("Column Filters", expanded=False):
                _pf_cols = st.columns(5)
                _pf_cn = _pf_cols[0].text_input("Control #", key="prod_filter_cn", placeholder="filter...").strip()
                _pf_fn = _pf_cols[1].text_input("File Name", key="prod_filter_fn", placeholder="filter...").strip()
                _pf_cust = _pf_cols[2].text_input("Custodian", key="prod_filter_cust", placeholder="filter...").strip()
                _pf_tag = _pf_cols[3].text_input("Tags", key="prod_filter_tag", placeholder="filter...").strip()
                _pf_cat = _pf_cols[4].text_input("Prod Category", key="prod_filter_cat", placeholder="filter...").strip()

            # Apply column filters
            _filtered_df = grid_df.copy()
            if _pf_cn:
                _filtered_df = _filtered_df[_filtered_df['control_number'].str.contains(_pf_cn, case=False, na=False)]
            if _pf_fn:
                _filtered_df = _filtered_df[_filtered_df['file_name'].str.contains(_pf_fn, case=False, na=False)]
            if _pf_cust:
                _filtered_df = _filtered_df[_filtered_df['custodian'].str.contains(_pf_cust, case=False, na=False)]
            if _pf_tag:
                _filtered_df = _filtered_df[_filtered_df['tags'].str.contains(_pf_tag, case=False, na=False)]
            if _pf_cat:
                _filtered_df = _filtered_df[_filtered_df['production_category'].str.contains(_pf_cat, case=False, na=False)]

            _is_filtered = len(_filtered_df) < len(grid_df)
            if _is_filtered:
                st.caption(f"Showing {len(_filtered_df)} of {len(grid_df)} documents (filtered)")

            # --- Tag-based selection tools ---
            _tag_col1, _tag_col2 = st.columns(2)
            with _tag_col1:
                auto_tag = st.selectbox("Auto-Select by Tag:", ["-- None --"] + sorted(list(all_tags)), key="auto_select_tag")
            with _tag_col2:
                deselect_tag = st.selectbox("Deselect by Tag:", ["-- None --"] + sorted(list(all_tags)), key="auto_deselect_tag")

            # --- Category-based selection tools ---
            all_cats = sorted(set(grid_df['production_category'].dropna().astype(str).unique()))
            if all_cats:
                _cat_col1, _cat_col2 = st.columns(2)
                with _cat_col1:
                    auto_cat = st.selectbox("Auto-Select by Category:", ["-- None --"] + all_cats, key="auto_select_cat")
                with _cat_col2:
                    deselect_cat = st.selectbox("Deselect by Category:", ["-- None --"] + all_cats, key="auto_deselect_cat")
            else:
                auto_cat = "-- None --"
                deselect_cat = "-- None --"

            # Initialize Include column
            grid_df.insert(0, 'Include', False)
            if 'prod_all_selected' not in st.session_state:
                st.session_state['prod_all_selected'] = False

            # Apply Auto-Select from Dropdown (tag)
            if auto_tag != "-- None --":
                grid_df['Include'] = grid_df['tags'].apply(lambda x: auto_tag in str(x))

            # Apply Auto-Select from Dropdown (category)
            if auto_cat != "-- None --":
                grid_df['Include'] = grid_df['production_category'].apply(lambda x: str(x) == auto_cat)

            # Inject Select All / Deselect All Toggle Buttons
            col_sel1, col_sel2 = st.columns([1, 1])
            with col_sel1:
                if st.button("Select All", width='stretch', key="select_all_btn"):
                    st.session_state['prod_all_selected'] = True
                    if 'production_grid_editor' in st.session_state:
                        del st.session_state['production_grid_editor']
                    st.rerun()
            with col_sel2:
                if st.button("Deselect All", width='stretch', key="deselect_all_btn"):
                    st.session_state['prod_all_selected'] = False
                    if 'production_grid_editor' in st.session_state:
                        del st.session_state['production_grid_editor']
                    st.rerun()

            # Apply Blanket Selection State
            if st.session_state['prod_all_selected']:
                grid_df['Include'] = True

            # Apply Deselect by Tag (after Select All so it can override)
            if deselect_tag != "-- None --":
                grid_df.loc[grid_df['tags'].apply(lambda x: deselect_tag in str(x)), 'Include'] = False

            # Apply Deselect by Category
            if deselect_cat != "-- None --":
                grid_df.loc[grid_df['production_category'].apply(lambda x: str(x) == deselect_cat), 'Include'] = False

            # Build display DataFrame with the extra columns
            _display_df = grid_df.copy()
            _display_df['Type'] = _display_df['file_extension'].apply(
                lambda x: (x or '').lstrip('.').upper() if x else ''
            )
            _display_df['Pages'] = _display_df['page_count'].apply(
                lambda x: int(x) if pd.notna(x) and x else ''
            )
            _display_df['Privilege'] = _display_df['privilege_status'].fillna('')
            _display_df['Redaction'] = _display_df['redaction_status'].fillna('')
            _display_df['Category'] = _display_df['production_category'].fillna('')

            # Apply column filter to display (but keep grid_df indices for checkbox tracking)
            if _is_filtered:
                _display_df = _display_df[_display_df.index.isin(_filtered_df.index)]

            # Render Data Editor
            edited_df = st.data_editor(
                _display_df,
                column_config={
                    "Include": st.column_config.CheckboxColumn("Include", help="Select to include in production"),
                    "control_number": "Control Number",
                    "document_display": "Document",
                    "parent_id": "Parent",
                    "tags": "Tags",
                    "custodian": "Custodian",
                    "file_size_kb": st.column_config.NumberColumn("Size (KB)", format="%.1f"),
                    "Type": "Type",
                    "Pages": "Pages",
                    "Privilege": "Privilege",
                    "Redaction": "Redaction",
                    "Category": "Prod Category",
                    # Hide internal columns
                    "_family_root": None,
                    "_is_child": None,
                    "file_name": None,
                    "group_id": None,
                    "privilege_status": None,
                    "redaction_status": None,
                    "file_extension": None,
                    "page_count": None,
                    "production_category": None,
                },
                disabled=["control_number", "document_display", "parent_id", "tags", "custodian",
                           "file_size_kb", "Type", "Pages", "Privilege", "Redaction", "Category"],
                hide_index=True,
                width='stretch',
                key="production_grid_editor"
            )

            # Merge edits back to full grid_df if filtered
            if _is_filtered:
                grid_df.loc[edited_df.index, 'Include'] = edited_df['Include']
                edited_df = grid_df

            selected_cns = edited_df[edited_df['Include']]['control_number'].tolist()

            # Selection summary
            if selected_cns:
                _sel_df = edited_df[edited_df['Include']]
                _sel_redact = (_sel_df['privilege_status'] == 'Redact').sum()
                _sel_withhold = (_sel_df['privilege_status'] == 'Withhold').sum()
                _sel_clean = len(_sel_df) - _sel_redact - _sel_withhold
                _sel_summary = f"**{len(selected_cns)}** selected: {int(_sel_clean)} clean, {int(_sel_redact)} redacted, {int(_sel_withhold)} withheld"
                st.caption(_sel_summary)

            if st.button(f"Confirm Selection ({len(selected_cns)} documents)", type="primary", width='stretch', key="confirm_selection_btn"):
                # Calculate family-expanded count for transparency
                if selected_cns and not grid_df.empty:
                    selected_roots = set(grid_df[grid_df['control_number'].isin(selected_cns)]['_family_root'])
                    family_expanded_cns = grid_df[grid_df['_family_root'].isin(selected_roots)]['control_number'].tolist()
                    auto_added = len(family_expanded_cns) - len(selected_cns)
                else:
                    family_expanded_cns = selected_cns
                    auto_added = 0

                st.session_state['production_selection'] = selected_cns
                if auto_added > 0:
                    st.success(
                        f"Locked in {len(selected_cns)} selected documents for production. "
                        f"**{auto_added} additional family member(s)** will be automatically included "
                        f"to maintain family integrity ({len(family_expanded_cns)} total). Proceed to Step 2."
                    )
                else:
                    st.success(f"Locked in {len(selected_cns)} documents for production. Proceed to Step 2.")

        st.markdown("---")

    # HELPER: Get Production Sets
    def get_production_sets(case_folder):
        prod_folder = os.path.join(case_folder, "Productions")
        if not os.path.exists(prod_folder):
            os.makedirs(prod_folder)
        return [d for d in os.listdir(prod_folder) if os.path.isdir(os.path.join(prod_folder, d))]

    # ══════════════════════════════════════════════════════════════════════════
    # TWO-PASS PRODUCTION — Handler Functions
    # ══════════════════════════════════════════════════════════════════════════

    def _render_post_finalization():
        """Render the post-finalization screen: summary, downloads, and reset."""
        p1 = st.session_state['prod_pass1']
        prod_name = p1['prod_name']
        prod_path = p1['prod_path']
        prod_format = p1.get('prod_format', p1.get('format', 'PDF'))

        # Fetch authoritative stats from DB
        run_info = db_manager.get_production_run(case_folder, prod_name)

        # ── Section 1: Compact Success Summary ──────────────────────────────
        st.header(f"Production '{prod_name}' — Complete ✅")

        if run_info:
            # Defensive: finalized runs always have bates set, but use the
            # (value or '—') idiom to match the project convention and stay
            # immune to a future regression that surfaces None (Flag #13).
            bates_start = run_info.get('bates_start') or '—'
            bates_end = run_info.get('bates_end') or '—'
            st.markdown(f"**Bates Range:** `{bates_start}` through `{bates_end}`  ·  **Format:** {run_info.get('format', prod_format)}")

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Documents", run_info.get('document_count', 0))
            mc2.metric("Privileged (Withheld)", run_info.get('withheld_count', 0))
            mc3.metric("Redacted", run_info.get('redacted_count', 0))
            mc4.metric("Errors", run_info.get('error_count', 0))
        else:
            st.info("Production metadata not found in database. Files are available for download below.")

        # ── Section 2: QC Report Expander ────────────────────────────────────
        qc_path = os.path.join(prod_path, f"{prod_name}_QC_REPORT.csv")
        if os.path.isfile(qc_path):
            with st.expander("QC Report Details", expanded=False):
                try:
                    qc_df = pd.read_csv(qc_path)
                    st.dataframe(qc_df, width='stretch', hide_index=True)
                except Exception as _qc_err:
                    st.warning(f"Could not load QC report: {_qc_err}")

        # ── Section 3: Deliverable Downloads ─────────────────────────────────
        st.markdown("---")
        st.subheader("Production Deliverables")

        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            st.markdown("**📤 Opposing Counsel Package**")
            st.caption("IMAGES, NATIVES, TEXT, load files (.dat, .opt), privilege log — excludes internal work products")
            _counsel_data = _build_counsel_zip(prod_name, prod_path)
            st.download_button(
                "⬇️ Download Deliverable ZIP",
                data=_counsel_data,
                file_name=f"{prod_name}_DELIVERABLE.zip",
                mime="application/zip",
                key="dl_counsel_zip",
                width='stretch',
            )

        with dl_col2:
            st.markdown("**📁 Full Archive Package**")
            st.caption("Entire production folder including all work products and logs")
            _full_data = _build_full_zip(prod_name, prod_path)
            st.download_button(
                "⬇️ Download Full Archive ZIP",
                data=_full_data,
                file_name=f"{prod_name}_FULL.zip",
                mime="application/zip",
                key="dl_full_zip",
                width='stretch',
            )

        # ── Section 4: Internal Work Product Downloads ───────────────────────
        st.markdown("---")
        st.subheader("Internal Work Products")

        _internal_files = [
            (f"{prod_name}_PRIVILEGE_LOG.csv", "Privilege Log"),
            (f"{prod_name}_QC_REPORT.csv", "QC Report"),
            (f"{prod_name}_REDACTION_LOG.csv", "Redaction Log"),
            (f"{prod_name}_IMAGING_ERRORS.csv", "Imaging Errors"),
            (f"{prod_name}_FOLDER_SUMMARY.csv", "Folder Summary"),
            (f"{prod_name}_CROSS_REFERENCE.csv", "Cross-Reference"),
        ]

        available = [(fname, label) for fname, label in _internal_files
                     if os.path.isfile(os.path.join(prod_path, fname))]

        if available:
            int_cols = st.columns(3)
            for idx, (fname, label) in enumerate(available):
                fpath = os.path.join(prod_path, fname)
                with int_cols[idx % 3]:
                    with open(fpath, 'rb') as f:
                        data = f.read()
                    st.download_button(
                        f"⬇️ {label}",
                        data=data,
                        file_name=fname,
                        mime="text/csv",
                        key=f"dl_internal_{fname}",
                        width='stretch',
                    )
        else:
            st.caption("No internal work product files found.")

        # ── Section 5: Start New Production ──────────────────────────────────
        st.markdown("---")
        if not _case_closed:
            st.caption("Clear the current production state to configure a new production run.")
            if st.button("🔄 Start New Production", key="btn_start_new_prod"):
                for key in ('prod_pass1', 'prod_pass1_complete', 'prod_finalized', 'production_selection'):
                    st.session_state.pop(key, None)
                st.rerun()

    def _render_pass1_checkpoint():
        """Render the imaging summary + retry/finalize/abort buttons after Pass 1."""
        p1 = st.session_state['prod_pass1']
        results = p1['results']

        st.header(f"Production '{p1['prod_name']}' — Imaging Complete")
        st.info(
            "Pass 1 (imaging) is complete. Review the results below, retry any failures, "
            "then click **Finalize** to assign Bates numbers and assemble the production volume."
        )

        # ── Summary Metrics ──
        _imaged = sum(1 for r in results if r['category'] == 'Imaged')
        _expected = sum(1 for r in results if r['category'] == 'Expected Native')
        _failures = sum(1 for r in results if r['category'] == 'Imaging Failure')
        _natives = sum(1 for r in results if r['category'] == 'Native')
        _withheld = sum(1 for r in results if r['category'] == 'Withheld')

        _mc1, _mc2, _mc3, _mc4, _mc5 = st.columns(5)
        _mc1.metric("Total Documents", len(results))
        _mc2.metric("Successfully Imaged", _imaged + _natives)
        _mc3.metric("Expected Natives", _expected,
            help="File types always produced natively (e.g., .xlsx, .csv). Will get slip sheet + native.")
        _mc4.metric("Withheld", _withheld,
            help="Documents with Withhold disposition. Will receive placeholder slip sheets in Pass 2.")
        _mc5.metric("Imaging Failures", _failures,
            delta=f"-{_failures}" if _failures > 0 else None,
            delta_color="inverse",
            help="Documents that should have been imaged but failed. Review reasons below.")

        # ── Failure Detail Table (editable — retry exclusion checkboxes) ──
        if _failures > 0:
            st.subheader("Imaging Failures — Review & Retry")
            st.caption(
                "Uncheck 'Exclude from Retry' to include a document in the next retry attempt. "
                "Excluded documents will be produced as native-only with a slip sheet."
            )

            _fail_rows = [r for r in results if r['category'] == 'Imaging Failure']
            _edit_df = pd.DataFrame(_fail_rows)[
                ['control_number', 'file_name', 'file_extension', 'error_msg', 'retry_excluded']
            ]
            _edited = st.data_editor(
                _edit_df,
                column_config={
                    'control_number': 'Control Number',
                    'file_name': 'File Name',
                    'file_extension': 'Type',
                    'error_msg': st.column_config.TextColumn('Failure Reason', width='large'),
                    'retry_excluded': st.column_config.CheckboxColumn(
                        'Exclude from Retry',
                        help="Check to skip this document during retry (will be produced as native-only).",
                        default=False
                    ),
                },
                disabled=['control_number', 'file_name', 'file_extension', 'error_msg'],
                hide_index=True,
                width='stretch',
                key="imaging_retry_editor"
            )

            # Sync exclusion state back to session state
            for _, erow in _edited.iterrows():
                cn = erow['control_number']
                for r in results:
                    if r['control_number'] == cn:
                        r['retry_excluded'] = erow['retry_excluded']

        # ── Expected Natives (read-only expander) ──
        if _expected > 0:
            with st.expander(f"Expected Natives ({_expected})", expanded=False):
                _nat_df = pd.DataFrame([r for r in results if r['category'] == 'Expected Native'])
                st.dataframe(
                    _nat_df[['control_number', 'file_name', 'file_extension']],
                    column_config={
                        'control_number': 'Control Number',
                        'file_name': 'File Name',
                        'file_extension': 'Type',
                    },
                    hide_index=True, width='stretch'
                )

        # ── Action Buttons ──
        st.markdown("---")
        _btn_col1, _btn_col2, _btn_col3 = st.columns(3)

        with _btn_col1:
            _retryable = [r for r in results
                          if r['category'] == 'Imaging Failure' and not r['retry_excluded']]
            _retry_btn = st.button(
                f"Retry Failed ({len(_retryable)})",
                disabled=len(_retryable) == 0,
                width='stretch',
                key="retry_failed_btn"
            )

        with _btn_col2:
            _finalize_btn = st.button(
                "Finalize Production",
                type="primary",
                width='stretch',
                key="finalize_production_btn"
            )

        with _btn_col3:
            _abort_btn = st.button(
                "Abort Production",
                width='stretch',
                key="abort_production_btn"
            )

        # ── Button Handlers ──
        if _retry_btn:
            _handle_retry()
        elif _finalize_btn:
            _handle_finalize()
        elif _abort_btn:
            _handle_abort()

    def _handle_retry():
        """Re-run imaging on non-excluded failures, using parallel workers."""
        p1 = st.session_state['prod_pass1']
        results = p1['results']
        retryable = [r for r in results
                     if r['category'] == 'Imaging Failure' and not r['retry_excluded']]

        if not retryable:
            st.warning("No documents to retry.")
            return

        import time as _retry_time
        _retry_start = _retry_time.monotonic()
        _retry_workers = min(p1.get('imaging_workers', 1), len(retryable))

        progress_bar = st.progress(0)
        status_text = st.empty()

        if _retry_workers > 1 and len(retryable) > 1:
            # Parallel retry
            from concurrent.futures import ProcessPoolExecutor, as_completed

            with ProcessPoolExecutor(max_workers=_retry_workers) as pool:
                future_to_r = {}
                for r in retryable:
                    temp_pdf_path = os.path.join(
                        p1['prod_path'], "IMAGES", f"TEMP_{r['control_number']}.pdf"
                    )
                    future = pool.submit(
                        universal_imager.image_document_safe,
                        r['source_file'], temp_pdf_path, r['control_number'],
                    )
                    future_to_r[future] = (r, temp_pdf_path)

                completed = 0
                for future in as_completed(future_to_r):
                    r_orig, temp_pdf_path = future_to_r[future]
                    cn = r_orig['control_number']

                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {
                            'success': False,
                            'error_msg': f"Retry worker error: {exc}",
                            'page_count': 1,
                        }

                    # Update the result in-place in the session state results list
                    for orig in results:
                        if orig['control_number'] == cn:
                            orig['success'] = result['success']
                            orig['error_msg'] = result['error_msg']
                            orig['page_count'] = result['page_count']
                            orig['temp_pdf_path'] = temp_pdf_path if result['success'] else None
                            if result['success']:
                                orig['category'] = 'Imaged'
                            break

                    completed += 1
                    status_text.text(f"Retrying: {completed}/{len(retryable)}")
                    progress_bar.progress(completed / len(retryable))
        else:
            # Sequential retry (1 worker or 1 document)
            for idx, r in enumerate(retryable):
                cn = r['control_number']
                status_text.text(f"Retrying {cn} ({idx+1}/{len(retryable)})")
                temp_pdf_path = os.path.join(
                    p1['prod_path'], "IMAGES", f"TEMP_{cn}.pdf"
                )
                result = universal_imager.image_document_safe(
                    r['source_file'], temp_pdf_path, cn
                )
                for orig in results:
                    if orig['control_number'] == cn:
                        orig['success'] = result['success']
                        orig['error_msg'] = result['error_msg']
                        orig['page_count'] = result['page_count']
                        orig['temp_pdf_path'] = temp_pdf_path if result['success'] else None
                        if result['success']:
                            orig['category'] = 'Imaged'
                        break
                progress_bar.progress((idx + 1) / len(retryable))

        _newly_succeeded = sum(
            1 for r in retryable
            if any(o['control_number'] == r['control_number'] and o['success'] for o in results)
        )
        _retry_elapsed = _retry_time.monotonic() - _retry_start
        db_manager.log_audit(p1['case_folder'], "PRODUCTION_RETRY",
            username=p1['username'], module="Production",
            details=json.dumps({
                "volume": p1['prod_name'],
                "docs_retried": len(retryable),
                "newly_succeeded": _newly_succeeded,
                "workers": _retry_workers,
                "elapsed_seconds": round(_retry_elapsed, 1),
            }))

        st.rerun()

    def _handle_abort():
        """Delete production folder and clear session state. No Bates cleanup needed."""
        p1 = st.session_state['prod_pass1']

        # Flip production_runs.status to 'aborted' BEFORE folder cleanup so the
        # row persists as an audit marker even though the folder is gone.
        db_manager.update_production_status(p1['case_folder'], p1['prod_name'], 'aborted')

        try:
            if os.path.exists(p1['prod_path']):
                shutil.rmtree(p1['prod_path'])
        except Exception as e:
            st.warning(f"Could not delete production folder: {e}")

        db_manager.log_audit(p1['case_folder'], "PRODUCTION_ABORTED",
            username=p1['username'], module="Production",
            details=json.dumps({"volume": p1['prod_name']}))

        for key in ['prod_pass1', 'prod_pass1_complete', 'prod_finalized']:
            st.session_state.pop(key, None)

        st.success(f"Production '{p1['prod_name']}' aborted. No Bates numbers were assigned.")
        time.sleep(1.5)
        st.rerun()

    def _handle_finalize():
        """Pass 2 — Sequential assembly. Assigns Bates numbers, burns redactions,
        stamps, extracts text, generates load files. This is the legally significant pass."""
        import time as _pass2_time
        _pass2_start = _pass2_time.monotonic()
        p1 = st.session_state['prod_pass1']
        results = p1['results']
        prod_name = p1['prod_name']
        prod_path = p1['prod_path']
        prod_format = p1['prod_format']
        prefix = p1['prefix']
        start_num = p1['start_num']
        bates_padding = p1['bates_padding']
        stamp_enabled = p1['stamp_enabled']
        stamp_position = p1['stamp_position']
        stamp_color = p1['stamp_color']
        stamp_font_size = p1['stamp_font_size']
        endorsement_text = p1['endorsement_text']
        case_folder_path = p1['case_folder']
        _prod_username = p1['username']
        prod_mode = p1.get('prod_mode', 'Full EDRM Production')
        _is_full_edrm = (prod_mode == 'Full EDRM Production')
        _sort_by_folder = p1.get('sort_by_folder', True)
        _sort_mode = p1.get('sort_mode', 'Sort by Ingestion Folder')
        _skip_redaction_burn = p1.get('skip_redaction_burn', False)

        # Reconstruct the document DataFrame from stored rows
        df = pd.DataFrame(p1['doc_rows'])
        results_by_cn = {r['control_number']: r for r in results}
        withhold_cns = set(p1.get('withhold_cns', []))

        conn = db_manager.get_connection(case_folder_path)

        # Progress UI + cancel button
        progress_bar = st.progress(0)
        status_text = st.empty()
        _prod_cancel_placeholder = st.empty()
        st.session_state['_prod_cancel'] = False
        with _prod_cancel_placeholder.container():
            st.markdown("<div style='height:0;overflow:hidden'>", unsafe_allow_html=True)
            st.button(
                "Cancel Finalize",
                key="_prod_cancel_btn_p2",
                on_click=lambda: st.session_state.update({'_prod_cancel': True}),
                type="secondary",
            )
            st.markdown("</div>", unsafe_allow_html=True)

        lottie_placeholder = ui_utils.start_lottie_spinner(
            f"Finalizing Production '{prod_name}'... Assigning Bates numbers and assembling volume.")
        ui_utils.show_overlay_cancel_button()

        # Initialize collectors
        prod_data = []
        opt_data = []
        db_updates = []
        cross_reference_data = []
        redaction_log_data = []
        withhold_log_entries = []
        redact_log_entries = []
        parent_bates_map = {}
        _bates_audit_entries = []
        error_count = 0
        imaging_failures = []
        _deferred_ocr = []  # list of {'text_file_path': str, 'png_pages': list[bytes], 'cn': str}
        current_num = start_num

        # Helper: extract privilege basis from tags
        _priv_members_prod = db_manager.get_privilege_tag_members(case_folder_path)
        def _get_priv_basis(tags_str):
            FORMAL_NAMES = {
                'work product': 'Attorney Work Product',
                'attorney-client privilege': 'Attorney-Client Privilege',
                'attorney-client privilege and work product': 'Attorney-Client Privilege and Work Product',
                'common interest privilege': 'Common Interest Privilege',
                'joint defense privilege': 'Joint Defense Privilege',
                'trade secret': 'Trade Secret',
                'marital privilege': 'Marital Privilege',
                'fifth amendment': 'Fifth Amendment',
                'settlement privilege (fre 408)': 'Settlement Privilege (FRE 408)',
                'self-critical analysis privilege': 'Self-Critical Analysis Privilege',
                'executive / deliberative process privilege': 'Executive / Deliberative Process Privilege',
                'relevance objection': 'Relevance Objection',
            }
            priv_set = {m.lower() for m in _priv_members_prod} if _priv_members_prod else set()
            individual_tags = [
                tag.strip() for tag in str(tags_str or '').replace(';', ',').split(',')
                if tag.strip()
            ]
            bases = []
            for tag in individual_tags:
                tag_lower = tag.lower()
                if tag_lower in priv_set:
                    formal = FORMAL_NAMES.get(tag_lower, tag)
                    if formal not in bases:
                        bases.append(formal)
            return '; '.join(bases) if bases else 'Privilege Asserted'

        err_path = os.path.join(prod_path, f"{prod_name}_IMAGING_ERRORS.csv")
        pd.DataFrame(columns=['ControlNumber', 'FilePath', 'Error']).to_csv(err_path, index=False)

        _prod_was_cancelled = False
        _prod_completed_count = 0

        CONTAINER_EXTENSIONS = {'.pst', '.zip', '.rar', '.7z'}

        for i, row in df.iterrows():
            # Check cancel flag
            if st.session_state.get('_prod_cancel', False):
                _prod_was_cancelled = True
                db_manager.log_audit(case_folder_path, "PRODUCTION_CANCELLED",
                    username=_prod_username, module="Production",
                    details=json.dumps({
                        "volume": prod_name,
                        "completed": _prod_completed_count,
                        "total": len(df),
                        "phase": "Pass 2 (assembly)",
                    }))
                break

            # Skip containers and split-source shells (they have no
            # independent content — their children carry the real pages)
            if (row.get('processing_status') in ('Container_Scanned', 'Split_Source')
                    or (row.get('file_extension') or '').lower() in CONTAINER_EXTENSIONS):
                continue

            cn = row['control_number']

            # ── Withheld Document Handler ──────────────────────────────
            if cn in withhold_cns:
                status_text.text(f"Placeholder for {cn} ({_prod_completed_count+1}/{len(df)})")
                beg_bates = f"{prefix}-{str(current_num).zfill(bates_padding)}"
                end_bates = beg_bates  # Always 1 page for placeholders
                page_count = 1

                priv_basis = _get_priv_basis(row.get('tags'))
                placeholder_path = os.path.join(prod_path, "IMAGES", f"{beg_bates}.pdf")
                # Per-document confidentiality override
                _doc_conf_w = row.get('confidentiality_designation')
                _doc_endorsement_w = _doc_conf_w if _doc_conf_w else endorsement_text
                ph_ok, ph_err = universal_imager.generate_privilege_placeholder(
                    placeholder_path, beg_bates, priv_basis,
                    control_number=cn,
                    endorsement=_doc_endorsement_w
                )

                if ph_ok:
                    if stamp_enabled:
                        try:
                            universal_imager.stamp_bates_on_pdf(
                                placeholder_path, prefix, current_num,
                                position=stamp_position, font_size=stamp_font_size,
                                endorsement=_doc_endorsement_w, color=stamp_color,
                                padding=bates_padding
                            )
                        except Exception:
                            pass

                    opt_data.append({
                        'bates': beg_bates,
                        'path': f"IMAGES\\{beg_bates}.pdf",
                        'is_first': 'Y'
                    })

                    # Placeholder text file (ensure TEXT dir exists — may not in Simple mode)
                    text_file_path = os.path.join(prod_path, "TEXT", f"{beg_bates}.txt")
                    os.makedirs(os.path.dirname(text_file_path), exist_ok=True)
                    with open(text_file_path, 'w', encoding='utf-8') as tf:
                        tf.write(f"[Document withheld on basis of {priv_basis}]")

                # Load file entry
                prod_data.append({
                    'ControlNumber': cn,
                    'BegDoc': beg_bates,
                    'EndDoc': end_bates,
                    'BegAtt': '',
                    'EndAtt': '',
                    'PageCount': 1,
                    'Custodian': row.get('custodian') or '',
                    'RecordType': row.get('record_type') or '',
                    'FileExt': '',
                    'NativeLink': '',
                    'TextLink': f"TEXT\\{beg_bates}.txt",
                    'PrivilegeStatus': 'Withheld',
                    'ConfidentialityDesignation': row.get('confidentiality_designation') or '',
                })

                # Privilege log entry
                withhold_log_entries.append({
                    'ControlNumber': cn,
                    'BegBates': beg_bates,
                    'EndBates': end_bates,
                    'Date': row['date_sent'] if pd.notna(row.get('date_sent')) else '',
                    'From': row['email_from'] if pd.notna(row.get('email_from')) else '',
                    'To': row['email_to'] if pd.notna(row.get('email_to')) else '',
                    'CC': row.get('email_cc', '') if pd.notna(row.get('email_cc')) else '',
                    'Subject': row['email_subject'] if pd.notna(row.get('email_subject')) else row['file_name'],
                    'Custodian': row['custodian'] if pd.notna(row.get('custodian')) else '',
                    'RecordType': row['record_type'] if pd.notna(row.get('record_type')) else '',
                    'PrivilegeBasis': priv_basis,
                    'Disposition': 'Withheld',
                    'Description': f"Document withheld: {row['file_name']}"
                })

                # DB update for Bates assignment
                db_updates.append((cn, prod_name, beg_bates, end_bates, page_count, row['id']))
                _bates_audit_entries.append({
                    "action": "BATES_ASSIGNED", "username": _prod_username,
                    "control_number": cn, "module": "Production",
                    "details": None, "old_value": None,
                    "new_value": f"{beg_bates}-{end_bates}"
                })

                if pd.isna(row.get('parent_id')) or not str(row.get('parent_id', '')).strip():
                    parent_bates_map[cn] = beg_bates
                    parent_bates_val = beg_bates
                else:
                    parent_bates_val = parent_bates_map.get(row['parent_id'], "")

                cross_reference_data.append({
                    'Internal_Control_Number': cn,
                    'Bates_Begin': beg_bates,
                    'Bates_End': end_bates,
                    'Parent_Bates': parent_bates_val,
                    'File_Name': row['file_name']
                })

                current_num += page_count
                _prod_completed_count += 1
                progress_bar.progress((_prod_completed_count) / len(df))
                continue  # Skip the normal assembly pipeline

            # ── Normal Document Assembly ──────────────────────────────
            status_text.text(f"Assembling {cn} ({_prod_completed_count+1}/{len(df)})")

            r = results_by_cn.get(cn)
            if not r:
                continue  # document not in Pass 1 results (shouldn't happen)

            ext = r['file_extension']
            source_file = r['source_file']
            success = r['success']
            error_msg = r['error_msg']
            page_count = r['page_count']
            temp_pdf_path = r.get('temp_pdf_path')
            staged_native_path = r.get('staged_native_path')
            dest_native = None
            export_filename = os.path.basename(source_file) if source_file else row['file_name']
            _burn_failed = False

            # ── Bates Assignment (Pass 2 ONLY) ──
            beg_bates = f"{prefix}-{str(current_num).zfill(bates_padding)}"
            end_bates = f"{prefix}-{str(current_num + page_count - 1).zfill(bates_padding)}"

            # ── Redaction Burns (CRIT-1 pattern preserved) ──
            if success and prod_format != "Native Only" and temp_pdf_path:
                try:
                    import fitz as fitz_redact
                    _redact_swap = None
                    with fitz_redact.open(temp_pdf_path) as redact_doc:
                        redaction_applied = False
                        for rpage_num, rpage in enumerate(redact_doc):
                            if rpage.annots():
                                has_redact_annots = False
                                for annot in rpage.annots():
                                    if annot.type[0] == 12:  # PDF_ANNOT_REDACT
                                        has_redact_annots = True
                                        info = annot.info
                                        raw_date = info.get('creationDate', '')
                                        mark_date = ''
                                        if raw_date.startswith('D:') and len(raw_date) >= 10:
                                            mark_date = f"{raw_date[2:6]}-{raw_date[6:8]}-{raw_date[8:10]}"
                                        redaction_log_data.append({
                                            'ControlNumber': cn,
                                            'BegBates': beg_bates,
                                            'Page': rpage_num + 1,
                                            'Reason': info.get('content', ''),
                                            'MarkedBy': info.get('title', ''),
                                            'DateMarked': mark_date
                                        })
                                if has_redact_annots and not _skip_redaction_burn:
                                    rpage.apply_redactions()
                                    # Belt-and-suspenders: explicitly delete any
                                    # remaining redaction annotation objects from
                                    # the page so they don't leak privilege labels
                                    # (Contents field) into the produced PDF.
                                    _remaining = list(rpage.annots()) if rpage.annots() else []
                                    for _ra in _remaining:
                                        if _ra.type[0] == 12:  # PDF_ANNOT_REDACT
                                            rpage.delete_annot(_ra)
                                    redaction_applied = True
                        if redaction_applied:
                            # SECURITY-CRITICAL: Full rewrite with garbage=4 to
                            # irrecoverably remove redacted content. Without garbage
                            # collection, the original unredacted content stream
                            # persists as an orphaned PDF object recoverable by
                            # forensic tools. clean=True rewrites content streams
                            # to eliminate incremental update artifacts.
                            # Save to swap file while doc is open; os.replace()
                            # happens after the with block releases the file handle.
                            _redact_swap = temp_pdf_path + ".redacted"
                            redact_doc.save(
                                _redact_swap,
                                encryption=0,
                                garbage=4,    # Remove ALL unreferenced objects (orphaned streams, consumed annotations)
                                deflate=True,  # Recompress streams (smaller output)
                                clean=True,    # Rewrite content streams (eliminates incremental update artifacts)
                            )
                    if _redact_swap and os.path.exists(_redact_swap):
                        os.replace(_redact_swap, temp_pdf_path)
                        _mark_count = sum(
                            1 for e in redaction_log_data
                            if e['ControlNumber'] == cn
                        )
                        db_manager.log_audit(case_folder_path, "REDACTION_BURNED",
                            username=_prod_username, control_number=cn,
                            module="Production",
                            details=json.dumps({"beg_bates": beg_bates, "mark_count": _mark_count}))
                except Exception as redact_exc:
                    # CRIT-1: Abort this document — never ship the unredacted temp PDF.
                    success = False
                    error_msg = f"Redaction burn failed: {redact_exc}"
                    _burn_failed = True
                    st.error(
                        f"REDACTION BURN FAILED for {cn} — "
                        f"document will NOT be included in production to prevent "
                        f"shipping an unredacted privileged document. Error: {redact_exc}"
                    )

            # ── Text Extraction (after redaction, before stamping) ──
            # Only runs in Full EDRM mode — Simple mode skips text/OCR entirely.
            if success and _is_full_edrm:
                try:
                    if prod_format == "Native Only":
                        text_content = ''
                        # 1. SQLite
                        try:
                            _nat_text_conn = db_manager.get_connection(case_folder_path)
                            # Defense-in-depth (beta-2.10 Commit 3): cn is
                            # already drawn from the filtered base_df, but we
                            # add the mandatory outbound filter here too so a
                            # future refactor that changes how cn is sourced
                            # cannot silently break transitive coverage.
                            _nat_text_row = _nat_text_conn.execute(  # db_manager: exempt (production loop)
                                f"SELECT extracted_text FROM documents "
                                f"WHERE control_number = ? AND {db_manager.OUTBOUND_SOURCE_FILTER_SQL}",
                                (cn,)
                            ).fetchone()
                            _nat_text_conn.close()
                            text_content = (_nat_text_row['extracted_text'] or '') if _nat_text_row else ''
                        except Exception:
                            pass

                        # 2. OpenSearch fallback
                        if not text_content.strip():
                            try:
                                _nat_es, _ = os_manager.get_os_client()
                                if _nat_es:
                                    _nat_idx = os_manager.get_index_name(case_folder_path)
                                    _nat_os_doc = _nat_es.search(
                                        index=_nat_idx,
                                        body={"query": {"term": {"control_number": cn}}, "_source": ["content"]},
                                        size=1
                                    )
                                    _nat_hits = _nat_os_doc.get('hits', {}).get('hits', [])
                                    if _nat_hits:
                                        text_content = _nat_hits[0].get('_source', {}).get('content', '') or ''
                            except Exception:
                                pass

                        # 3. PyMuPDF fallback (source file is PDF)
                        if not text_content.strip() and source_file and os.path.exists(source_file) and source_file.lower().endswith('.pdf'):
                            try:
                                import fitz as _nat_fitz
                                with _nat_fitz.open(source_file) as _nat_doc:
                                    text_content = "\n".join(p.get_text() for p in _nat_doc)
                            except Exception:
                                pass

                        text_file_path = os.path.join(prod_path, "TEXT", f"{beg_bates}.txt")
                        with open(text_file_path, 'w', encoding='utf-8') as tf:
                            tf.write(text_content)
                    else:
                        import fitz as fitz_text
                        text_file_path = os.path.join(prod_path, "TEXT", f"{beg_bates}.txt")

                        with fitz_text.open(temp_pdf_path) as text_doc:
                            text_content = "\n".join(page.get_text() for page in text_doc)

                            if text_content.strip():
                                # Embedded text found — write immediately
                                with open(text_file_path, 'w', encoding='utf-8') as tf:
                                    tf.write(text_content)
                            else:
                                # No embedded text — capture pixmaps for deferred OCR
                                try:
                                    png_pages = []
                                    for page_num in range(len(text_doc)):
                                        page = text_doc.load_page(page_num)
                                        pix = page.get_pixmap(dpi=300)
                                        png_pages.append(pix.tobytes("png"))
                                    _deferred_ocr.append({
                                        'text_file_path': text_file_path,
                                        'png_pages': png_pages,
                                        'cn': cn,
                                    })
                                except Exception as pix_e:
                                    st.warning(f"Pixmap capture failed for {cn}: {pix_e}")

                                # Write empty placeholder so TEXT/ file count stays correct
                                with open(text_file_path, 'w', encoding='utf-8') as tf:
                                    tf.write('')
                except Exception as text_ext_fail:
                    st.warning(f"Text Extraction failed for {cn}: {text_ext_fail}")

            # ── Bates Stamping ──
            # Per-document confidentiality override
            _doc_conf = row.get('confidentiality_designation')
            _doc_endorsement = _doc_conf if _doc_conf else endorsement_text
            if success and stamp_enabled and prod_format != "Native Only" and temp_pdf_path:
                try:
                    stamp_ok, stamp_err = universal_imager.stamp_bates_on_pdf(
                        temp_pdf_path, prefix, current_num,
                        position=stamp_position, font_size=stamp_font_size,
                        endorsement=_doc_endorsement, color=stamp_color, padding=bates_padding
                    )
                    if not stamp_ok:
                        st.warning(f"Bates stamp failed for {cn}: {stamp_err}")
                except Exception as stamp_exc:
                    st.warning(f"Bates stamp exception for {cn}: {stamp_exc}")

            # ── Format Output ──
            if success:
                if prod_format == "Native Only":
                    # Rename staged native → Bates name
                    export_filename = f"{beg_bates}{ext}"
                    dest_native = os.path.join(prod_path, "NATIVES", export_filename)
                    if staged_native_path and os.path.exists(staged_native_path):
                        try:
                            os.rename(staged_native_path, dest_native)
                        except Exception:
                            try:
                                shutil.move(staged_native_path, dest_native)
                            except Exception as mv_e:
                                st.warning(f"Could not rename staged native for {cn}: {mv_e}")
                    elif source_file and os.path.exists(source_file):
                        try:
                            shutil.copy2(source_file, dest_native)
                        except Exception as cp_e:
                            st.warning(f"Native copy failed for {cn}: {cp_e}")

                    # Generate slip sheet
                    slipsheet_path = os.path.join(prod_path, "IMAGES", f"{beg_bates}.pdf")
                    try:
                        slip_ok, slip_err = universal_imager.generate_slipsheet(
                            slipsheet_path, beg_bates, export_filename, ext
                        )
                        if slip_ok and stamp_enabled:
                            try:
                                universal_imager.stamp_bates_on_pdf(
                                    slipsheet_path, prefix, current_num,
                                    position=stamp_position, font_size=stamp_font_size,
                                    endorsement=_doc_endorsement, color=stamp_color, padding=bates_padding
                                )
                            except Exception:
                                pass
                    except Exception as slip_exc:
                        slip_ok = False
                        st.warning(f"Slip sheet failed for {cn}: {slip_exc}")
                    opt_data.append({
                        'bates': beg_bates,
                        'path': f"IMAGES\\{beg_bates}.pdf" if (slip_ok if 'slip_ok' in dir() else False) else f"NATIVES\\{export_filename}",
                        'is_first': 'Y'
                    })
                elif prod_format == "PDF":
                    final_pdf_path = os.path.join(prod_path, "IMAGES", f"{beg_bates}.pdf")
                    shutil.move(temp_pdf_path, final_pdf_path)
                    opt_data.append({
                        'bates': beg_bates,
                        'path': f"IMAGES\\{beg_bates}.pdf",
                        'is_first': 'Y'
                    })
                else:  # TIFF
                    tiffs, _ = universal_imager.convert_pdf_to_tiff(temp_pdf_path, os.path.join(prod_path, "IMAGES"), prefix, current_num)
                    if os.path.exists(temp_pdf_path):
                        os.remove(temp_pdf_path)
                    for tif in tiffs:
                        opt_data.append({
                            'bates': tif['bates'],
                            'path': f"IMAGES\\{os.path.basename(tif['path'])}",
                            'is_first': 'Y' if tif['is_first_page'] else ''
                        })
            else:
                # Failure path
                _is_expected_native = not universal_imager.should_image(ext)
                # Enrich reason for native-by-policy documents
                if _is_expected_native and universal_imager.is_native_by_policy(ext):
                    error_msg = f"Native by EDRM policy: {ext} (spreadsheet/tabular data)"
                imaging_failures.append({
                    'ControlNumber': cn,
                    'BegBates': beg_bates,
                    'FileName': row['file_name'],
                    'FileType': ext,
                    'Category': 'Expected Native' if _is_expected_native else 'Imaging Failure',
                    'Reason': error_msg,
                    'SourcePath': source_file,
                })
                error_count += 1
                error_row = pd.DataFrame([{
                    'ControlNumber': cn,
                    'FilePath': source_file,
                    'Error': error_msg
                }])
                error_row.to_csv(err_path, mode='a', header=False, index=False)

                # CRIT-1: Redaction burn failures are excluded from load files entirely.
                if not _burn_failed:
                    # Rename staged native → Bates name for non-burn failures
                    export_filename = f"{beg_bates}{ext}"
                    dest_native = os.path.join(prod_path, "NATIVES", export_filename)
                    if staged_native_path and os.path.exists(staged_native_path):
                        try:
                            os.rename(staged_native_path, dest_native)
                        except Exception:
                            try:
                                shutil.move(staged_native_path, dest_native)
                            except Exception:
                                pass
                    elif source_file and os.path.exists(source_file):
                        try:
                            shutil.copy2(source_file, dest_native)
                        except Exception:
                            pass

                    slipsheet_path = os.path.join(prod_path, "IMAGES", f"{beg_bates}.pdf")
                    try:
                        slip_ok, slip_err = universal_imager.generate_slipsheet(
                            slipsheet_path, beg_bates, export_filename, ext
                        )
                        if slip_ok:
                            opt_data.append({
                                'bates': beg_bates,
                                'path': f"IMAGES\\{beg_bates}.pdf",
                                'is_first': 'Y'
                            })
                        else:
                            opt_data.append({
                                'bates': beg_bates,
                                'path': f"NATIVES\\{export_filename}",
                                'is_first': 'Y'
                            })
                    except Exception:
                        opt_data.append({
                            'bates': beg_bates,
                            'path': f"NATIVES\\{export_filename}",
                            'is_first': 'Y'
                        })

            # ── Collect data for batch operations ──
            if not _burn_failed:
                db_updates.append((cn, prod_name, beg_bates, end_bates, page_count, row['id']))
                _bates_audit_entries.append({
                    "action": "BATES_ASSIGNED", "username": _prod_username,
                    "control_number": cn, "module": "Production",
                    "details": None, "old_value": None,
                    "new_value": f"{beg_bates}-{end_bates}"
                })

                if pd.isna(row['parent_id']) or not str(row['parent_id']).strip():
                    parent_bates_map[cn] = beg_bates
                    parent_bates_val = beg_bates
                else:
                    parent_bates_val = parent_bates_map.get(row['parent_id'], "")

                cross_reference_data.append({
                    'Internal_Control_Number': cn,
                    'Bates_Begin': beg_bates,
                    'Bates_End': end_bates,
                    'Parent_Bates': parent_bates_val,
                    'File_Name': export_filename
                })

                prod_data.append({
                    'ControlNumber': cn,
                    'BegDoc': beg_bates,
                    'EndDoc': end_bates,
                    'BegAtt': '',
                    'EndAtt': '',
                    'PageCount': page_count,
                    'Custodian': row['custodian'],
                    'RecordType': row.get('record_type') or '',
                    'FileExt': ext,
                    'NativeLink': os.path.join("NATIVES", export_filename) if dest_native else "",
                    'TextLink': f"TEXT\\{beg_bates}.txt",
                    'PrivilegeStatus': row.get('privilege_status') or '',
                    'ConfidentialityDesignation': row.get('confidentiality_designation') or '',
                })

            current_num += page_count
            _prod_completed_count += 1
            progress_bar.progress((_prod_completed_count) / len(df))

        # ── Handle cancellation ──
        _prod_cancel_placeholder.empty()
        if _prod_was_cancelled:
            lottie_placeholder.empty()
            try:
                shutil.rmtree(prod_path)
            except Exception as _rm_err:
                st.warning(f"Could not clean up partial production folder: {_rm_err}")
            st.warning(
                f"Production '{prod_name}' cancelled during assembly after {_prod_completed_count}/{len(df)} documents. "
                f"The partial volume has been deleted — no Bates numbers were committed to the database. "
                f"You can re-run the production when ready."
            )
            _deferred_ocr.clear()
            st.session_state.pop('_prod_cancel', None)
            for key in ['prod_pass1', 'prod_pass1_complete', 'prod_finalized']:
                st.session_state.pop(key, None)
            conn.close()
            time.sleep(2)
            st.rerun()
            return

        # ── Post-assembly: Batch DB update ──
        def batched(iterable, n):
            for bi in range(0, len(iterable), n):
                yield iterable[bi:bi + n]
        # Write to authoritative junction table
        _produced_at = datetime.now().isoformat()
        dp_inserts = [
            (item[0], item[1], item[2], item[3], item[4], _produced_at, 'Original')
            for item in db_updates
        ]
        dp_sql = """
            INSERT OR IGNORE INTO document_productions
            (control_number, production_volume, begdoc, enddoc, page_count, produced_at, production_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        for batch in batched(dp_inserts, 3000):
            conn.executemany(dp_sql, batch)

        # Sync cache columns on documents table
        update_sql = "UPDATE documents SET begdoc=?, enddoc=?, production_volume=? WHERE id=?"
        cache_updates = [(item[2], item[3], item[1], item[5]) for item in db_updates]
        for batch in batched(cache_updates, 3000):
            conn.executemany(update_sql, batch)
        conn.commit()
        if _bates_audit_entries:
            db_manager.log_audit_batch(case_folder_path, _bates_audit_entries)

        # ── Load Files (Full EDRM only) ──
        if _is_full_edrm:
            # NOTE: Custom coding fields are intentionally excluded from the
            # production load file (DAT/CSV). Issue coding is attorney work
            # product and must never leave the platform in a deliverable.
            # Coding data is accessible via the database for internal reports.

            load_file_df = pd.DataFrame(prod_data)
            # Strip internal ControlNumber from deliverable load files —
            # Bates numbers (BegDoc/EndDoc) are sufficient for document identification.
            # ControlNumber is retained in cross_reference.csv (internal work product).
            _internal_only_cols = {'ControlNumber', 'PrivilegeStatus'}
            _deliverable_cols = [c for c in load_file_df.columns if c not in _internal_only_cols]
            load_file_df[_deliverable_cols].to_csv(os.path.join(prod_path, f"{prod_name}_LOADFILE.csv"), index=False)
            pd.DataFrame(cross_reference_data).to_csv(os.path.join(prod_path, "cross_reference.csv"), index=False)

            # Concordance .DAT (same deliverable columns, no ControlNumber)
            _dat_df = load_file_df[_deliverable_cols]
            dat_path = os.path.join(prod_path, f"{prod_name}_LOADFILE.DAT")
            with open(dat_path, 'w', encoding='utf-8') as f:
                header = ['\u00fe' + col + '\u00fe' for col in _dat_df.columns]
                f.write('\u00b6'.join(header) + '\n')
                for _, dl in _dat_df.iterrows():
                    row_vals = []
                    for val in dl:
                        val_str = str(val).replace('\u00fe', '').replace('\u00b6', '') if pd.notnull(val) else ""
                        row_vals.append('\u00fe' + val_str + '\u00fe')
                    f.write('\u00b6'.join(row_vals) + '\n')

            # Opticon .OPT
            opt_path = os.path.join(prod_path, f"{prod_name}_IMAGES.OPT")
            with open(opt_path, 'w', encoding='utf-8') as f:
                for rec in opt_data:
                    f.write(f"{rec['bates']},VOL001,{rec['path']},{rec['is_first']},,,1\n")

        if error_count > 0:
            st.warning(f"{error_count} documents were not imaged — see the Imaging Summary table below for a full breakdown.")

        # ── Unified Privilege Log ──
        # Collect Redact-disposition entries (produced with marks burned)
        for _, _rlog_row in df.iterrows():
            if _rlog_row.get('privilege_status') == 'Redact':
                _rlog_cn = _rlog_row['control_number']
                # Find the Bates assignment for this CN from prod_data
                _rlog_bates = next((d for d in prod_data if d['ControlNumber'] == _rlog_cn), None)
                if _rlog_bates:
                    # Pull privilege basis from redaction mark reasons (not tags)
                    _rlog_reasons = set()
                    for _rld in redaction_log_data:
                        if _rld['ControlNumber'] == _rlog_cn and _rld.get('Reason'):
                            _rlog_reasons.add(_rld['Reason'])
                    _rlog_basis = '; '.join(sorted(_rlog_reasons)) if _rlog_reasons else _get_priv_basis(_rlog_row.get('tags'))

                    redact_log_entries.append({
                        'ControlNumber': _rlog_cn,
                        'BegBates': _rlog_bates['BegDoc'],
                        'EndBates': _rlog_bates['EndDoc'],
                        'Date': _rlog_row['date_sent'] if pd.notna(_rlog_row.get('date_sent')) else '',
                        'From': _rlog_row['email_from'] if pd.notna(_rlog_row.get('email_from')) else '',
                        'To': _rlog_row['email_to'] if pd.notna(_rlog_row.get('email_to')) else '',
                        'CC': _rlog_row.get('email_cc', '') if pd.notna(_rlog_row.get('email_cc')) else '',
                        'Subject': _rlog_row['email_subject'] if pd.notna(_rlog_row.get('email_subject')) else _rlog_row['file_name'],
                        'Custodian': _rlog_row['custodian'] if pd.notna(_rlog_row.get('custodian')) else '',
                        'RecordType': _rlog_row['record_type'] if pd.notna(_rlog_row.get('record_type')) else '',
                        'PrivilegeBasis': _rlog_basis,
                        'Disposition': 'Produced with redactions',
                        'Description': f"Document produced with privileged content redacted"
                    })

        # ── Merged Privilege Log (withheld + redacted, per-document, profile-aware) ──
        _doc_meta_lookup = {}
        for _, _ml_row in df.iterrows():
            _doc_meta_lookup[_ml_row['control_number']] = _ml_row

        # Pre-aggregate redaction page numbers per document (0-based)
        _rd_pages_by_cn = {}
        for _rd in redaction_log_data:
            _rd_cn = _rd['ControlNumber']
            _rd_pages_by_cn.setdefault(_rd_cn, set()).add(int(_rd.get('Page', 1)) - 1)

        merged_priv_log = []

        # Withheld documents: one row per document (QC-compatible keys)
        for _wh in withhold_log_entries:
            _wh_meta = _doc_meta_lookup.get(_wh['ControlNumber'])
            _wh_row = {
                'control_number':    _wh['ControlNumber'],
                'begdoc':            _wh['BegBates'],
                'enddoc':            _wh['EndBates'],
                'privilege_basis':   _wh['PrivilegeBasis'],
                'disposition':       'Withheld',
                '_disposition_key':  'Withhold',
                'description':       f"Document withheld on grounds of privilege: {_wh.get('Subject', '')}",
                'date_sent':         _wh['Date'],
                'email_from':        _wh['From'],
                'email_to':          _wh['To'],
                'email_cc':          _wh['CC'],
                'email_subject':     _wh['Subject'],
                'custodian':         _wh['Custodian'],
                'record_type':       _wh.get('RecordType', ''),
                'file_name':         _wh_meta.get('file_name', '') if _wh_meta is not None else '',
                'confidentiality':   _wh_meta.get('confidentiality_designation', '') if _wh_meta is not None else '',
                'source_collection': _wh_meta.get('source_collection', '') if _wh_meta is not None else '',
                'page_count':        1,
                'redaction_pages':   None,
                'redacted_pages_list': '',
                'reviewer_notes':    '',
            }
            _wh_row['individuals'] = _pl_merge_individuals(_wh_row)
            _wh_row['bates_display'] = _pl_format_bates(_wh_row)
            merged_priv_log.append(_wh_row)

        # Redacted documents: one row per document (from redact_log_entries)
        for _re in redact_log_entries:
            _re_cn = _re['ControlNumber']
            _re_meta = _doc_meta_lookup.get(_re_cn)
            _re_pages = _rd_pages_by_cn.get(_re_cn, set())
            _re_pages_str = ','.join(str(p) for p in sorted(_re_pages)) if _re_pages else ''
            _re_row = {
                'control_number':    _re_cn,
                'begdoc':            _re['BegBates'],
                'enddoc':            _re['EndBates'],
                'privilege_basis':   _re['PrivilegeBasis'],
                'disposition':       'Produced with redactions',
                '_disposition_key':  'Redact',
                'description':       f"Produced with redactions on grounds of privilege: {_re.get('Subject', '')}",
                'date_sent':         _re['Date'],
                'email_from':        _re['From'],
                'email_to':          _re['To'],
                'email_cc':          _re['CC'],
                'email_subject':     _re['Subject'],
                'custodian':         _re['Custodian'],
                'record_type':       _re.get('RecordType', ''),
                'file_name':         _re_meta.get('file_name', '') if _re_meta is not None else '',
                'confidentiality':   _re_meta.get('confidentiality_designation', '') if _re_meta is not None else '',
                'source_collection': _re_meta.get('source_collection', '') if _re_meta is not None else '',
                'page_count':        _re_meta.get('page_count') if _re_meta is not None else None,
                'redaction_pages':   len(_re_pages) if _re_pages else None,
                'redacted_pages_list': _re_pages_str,
                'reviewer_notes':    '',
            }
            _re_row['individuals'] = _pl_merge_individuals(_re_row)
            _re_row['bates_display'] = _pl_format_bates(_re_row)
            merged_priv_log.append(_re_row)

        if merged_priv_log:
            # Load the selected privilege log profile
            _pl_pname = p1.get('pl_profile_name', 'EDRM Standard')
            _pl_prof_raw = db_manager.get_case_setting(case_folder_path, 'privilege_log_profiles')
            _pl_prof_all = {}
            if _pl_prof_raw:
                try:
                    _pl_prof_all = json.loads(_pl_prof_raw)
                except (json.JSONDecodeError, TypeError):
                    pass
            if "EDRM Standard" not in _pl_prof_all:
                _pl_prof_all["EDRM Standard"] = {"columns": _PL_DEFAULT_COLS[:], "headers": {}, "merges": []}
            _pl_prof = _pl_prof_all.get(_pl_pname, _pl_prof_all.get("EDRM Standard"))
            _pl_cols = _pl_prof.get('columns', _PL_DEFAULT_COLS)
            _pl_hdrs = _pl_prof.get('headers', {})

            # Build DataFrame and apply profile
            priv_log_df = pd.DataFrame(merged_priv_log)
            _pl_export_keys = [c for c in _pl_cols if c in priv_log_df.columns]
            if not _pl_export_keys:
                _pl_export_keys = [c for c in _PL_DEFAULT_COLS if c in priv_log_df.columns]
            priv_log_export = priv_log_df[_pl_export_keys].copy()
            priv_log_export.columns = [
                _pl_hdrs.get(c, _PL_COL_KEY_TO_DISPLAY.get(c, c))
                for c in _pl_export_keys
            ]

            # Write CSV
            priv_log_export.to_csv(
                os.path.join(prod_path, f"{prod_name}_PRIVILEGE_LOG.csv"),
                index=False
            )

            # Write Excel alongside CSV
            try:
                _xl_path = os.path.join(prod_path, f"{prod_name}_PRIVILEGE_LOG.xlsx")
                _xl_buf = io.BytesIO()
                with pd.ExcelWriter(_xl_buf, engine='openpyxl') as _xl_w:
                    priv_log_export.to_excel(_xl_w, index=False, sheet_name='Privilege Log')
                    _xl_ws = _xl_w.sheets['Privilege Log']
                    from openpyxl.styles import Font as _xl_Font
                    for cell in _xl_ws[1]:
                        cell.font = _xl_Font(bold=True)
                    for col_cells in _xl_ws.columns:
                        max_len = max(len(str(cell.value or '')) for cell in col_cells)
                        _xl_ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 50)
                with open(_xl_path, 'wb') as _xl_f:
                    _xl_f.write(_xl_buf.getvalue())
            except Exception:
                pass  # openpyxl not available; CSV is sufficient

            n_withheld = len(withhold_log_entries)
            n_redacted = len(redact_log_entries)
            msg_parts = []
            if n_withheld: msg_parts.append(f"{n_withheld} withheld")
            if n_redacted: msg_parts.append(f"{n_redacted} redacted")
            st.info(f"Privilege Log generated ({_pl_pname} profile): "
                    f"{', '.join(msg_parts)} (saved to production folder).")

        # ── QC Report (Full EDRM only) ──
        if _is_full_edrm:
            qc_results = []
            # Check 1: Bates continuity
            try:
                bates_ranges = []
                for d in prod_data:
                    if '-' in str(d['BegDoc']) and '-' in str(d['EndDoc']):
                        b_num = int(d['BegDoc'].rsplit('-', 1)[-1])
                        e_num = int(d['EndDoc'].rsplit('-', 1)[-1])
                        bates_ranges.append((b_num, e_num))

                bates_ranges.sort(key=lambda x: x[0])
                bates_continuous = True
                for j in range(len(bates_ranges) - 1):
                    current_end = bates_ranges[j][1]
                    next_beg = bates_ranges[j+1][0]
                    if next_beg != current_end + 1:
                        bates_continuous = False
                        break

                qc_results.append({'Check': 'Bates Continuity', 'Status': 'PASS' if bates_continuous and bates_ranges else 'FAIL', 'Detail': f'{len(bates_ranges)} Bates numbers mapped'})
            except Exception as e:
                qc_results.append({'Check': 'Bates Continuity', 'Status': 'ERROR', 'Detail': f'Could not parse sequence: {e}'})

            # Check 2: Image file count vs OPT records
            image_files = os.listdir(os.path.join(prod_path, 'IMAGES'))
            first_page_opt = sum(1 for o in opt_data if o['is_first'] == 'Y')
            qc_results.append({'Check': 'Image File Count', 'Status': 'PASS' if len(image_files) > 0 else 'FAIL', 'Detail': f'{len(image_files)} files, {first_page_opt} OPT doc entries'})

            # Check 3: Text file coverage
            text_files = os.listdir(os.path.join(prod_path, 'TEXT'))
            text_coverage = len(text_files) >= len(prod_data)
            qc_results.append({'Check': 'Text File Coverage', 'Status': 'PASS' if text_coverage else 'WARN', 'Detail': f'{len(text_files)} text files for {len(prod_data)} documents'})

            if _deferred_ocr:
                qc_results.append({
                    'Check': 'Deferred OCR',
                    'Status': 'INFO',
                    'Detail': f'{len(_deferred_ocr)} documents queued for parallel OCR (text files will be populated after QC)'
                })

            # Check 4: Error rate
            error_rate = (error_count / len(df) * 100) if len(df) > 0 else 0
            qc_results.append({'Check': 'Imaging Error Rate', 'Status': 'PASS' if error_rate < 5 else 'WARN', 'Detail': f'{error_rate:.1f}% ({error_count}/{len(df)})'})

            # Check 5: Rogue Marks — physical redaction marks on docs without Redact disposition
            physically_redacted_cns = set(
                r['ControlNumber'] for r in redaction_log_data
            ) if redaction_log_data else set()
            redact_disposition_cns = set(
                row['control_number'] for _, row in df.iterrows()
                if row.get('privilege_status') == 'Redact'
            )
            withhold_cns_set = set(
                row['control_number'] for _, row in df.iterrows()
                if row.get('privilege_status') == 'Withhold'
            )
            rogue_marks = physically_redacted_cns - redact_disposition_cns - withhold_cns_set
            qc_results.append({
                'Check': 'Redaction QC: Rogue Marks',
                'Status': 'PASS' if not rogue_marks else 'WARN',
                'Detail': f'{len(rogue_marks)} docs have redaction marks but no privilege disposition'
            })

            # Check 6: Missing Marks — Redact-disposition docs without physical marks
            missing_marks = redact_disposition_cns - physically_redacted_cns
            qc_results.append({
                'Check': 'Redaction QC: Missing Marks',
                'Status': 'PASS' if not missing_marks else 'WARN',
                'Detail': f'{len(missing_marks)} Redact-disposition docs missing physical marks'
            })

            # Check 7: Withheld docs confirmation (informational)
            qc_results.append({
                'Check': 'Privilege: Withheld Documents',
                'Status': 'INFO',
                'Detail': f'{len(withhold_cns_set)} documents withheld with placeholder slip sheets'
            })

            # Check 8: Privilege log completeness
            priv_log_count = len(withhold_log_entries) + len(redact_log_entries)
            total_priv_docs = len(withhold_cns_set) + len(redact_disposition_cns)
            qc_results.append({
                'Check': 'Privilege Log Completeness',
                'Status': 'PASS' if priv_log_count == total_priv_docs else 'WARN',
                'Detail': f'{priv_log_count} log entries for {total_priv_docs} privileged documents'
            })

            qc_df = pd.DataFrame(qc_results)
            qc_df.to_csv(os.path.join(prod_path, f"{prod_name}_QC_REPORT.csv"), index=False)
            st.subheader("QC Summary")
            st.dataframe(qc_df, width='stretch', hide_index=True)

        # ── Imaging Failure Summary (read-only, post-finalize) ──
        if imaging_failures:
            st.markdown("---")
            st.subheader("Imaging Summary")

            _fail_df = pd.DataFrame(imaging_failures)
            _expected_count = _fail_df[_fail_df['Category'] == 'Expected Native'].shape[0]
            _actual_fail_count = _fail_df[_fail_df['Category'] == 'Imaging Failure'].shape[0]

            _fc1, _fc2, _fc3 = st.columns(3)
            _fc1.metric("Total Non-Imaged", len(_fail_df))
            _fc2.metric("Expected Natives", _expected_count,
                        help="File types that cannot be imaged (e.g., .xlsx, .csv). Produced with slip sheet + native file.")
            _fc3.metric("Actual Failures", _actual_fail_count,
                        delta=f"-{_actual_fail_count}" if _actual_fail_count > 0 else None,
                        delta_color="inverse",
                        help="Documents that should have been imaged but failed. Check the error reason.")

            if _actual_fail_count > 0:
                st.warning(
                    f"{_actual_fail_count} document(s) failed imaging unexpectedly. "
                    f"Review the 'Imaging Failure' rows below and check "
                    f"{prod_name}_IMAGING_ERRORS.csv for details."
                )

            st.dataframe(
                _fail_df[['ControlNumber', 'BegBates', 'FileName', 'FileType', 'Category', 'Reason']],
                column_config={
                    'ControlNumber': 'Control Number',
                    'BegBates': 'Bates Number',
                    'FileName': 'File Name',
                    'FileType': 'Type',
                    'Category': 'Category',
                    'Reason': st.column_config.TextColumn('Reason', width='large'),
                },
                width='stretch',
                hide_index=True,
                height=min(400, 35 * (len(_fail_df) + 1)),
            )

        # ── Bates Range Summary (Category or Folder) ──
        _show_summary = (_sort_mode == "Sort by Production Category" or _sort_by_folder) and prod_data
        if _show_summary:
            st.markdown("---")
            _is_category_sort = (_sort_mode == "Sort by Production Category")

            if _is_category_sort:
                st.subheader("📋 Disclosure Reference — Bates Ranges by Category")
                # Build mapping from control_number to production category
                _cn_to_group = {}
                for _, _frow in df.iterrows():
                    _cn = _frow['control_number']
                    _cn_to_group[_cn] = (_frow.get('production_category') or 'Uncategorized', '')
            else:
                st.subheader("📋 Folder / Category — Bates Range Summary")
                # Build mapping from control_number to folder info
                _cn_to_group = {}
                for _, _frow in df.iterrows():
                    _cn = _frow['control_number']
                    _coll = _frow.get('source_collection') or '(Uncategorized)'
                    _subcoll = _frow.get('source_subcollection') or ''
                    _cn_to_group[_cn] = (_coll, _subcoll)

            # Walk prod_data in order (it's in Bates order) and detect group boundaries
            _group_ranges = []
            _current_group = None
            _current_start = None
            _current_end = None
            _current_count = 0

            for _pd in prod_data:
                _cn = _pd['ControlNumber']
                _group = _cn_to_group.get(_cn, ('(Uncategorized)', ''))

                if _group != _current_group:
                    if _current_group is not None:
                        _group_ranges.append({
                            'Category': _current_group[0],
                            'Subcategory': _current_group[1],
                            'Bates Start': _current_start,
                            'Bates End': _current_end,
                            'Documents': _current_count,
                        })
                    _current_group = _group
                    _current_start = _pd['BegDoc']
                    _current_end = _pd['EndDoc']
                    _current_count = 1
                else:
                    _current_end = _pd['EndDoc']
                    _current_count += 1

            if _current_group is not None:
                _group_ranges.append({
                    'Category': _current_group[0],
                    'Subcategory': _current_group[1],
                    'Bates Start': _current_start,
                    'Bates End': _current_end,
                    'Documents': _current_count,
                })

            if _group_ranges:
                _summary_df = pd.DataFrame(_group_ranges)
                _col_config = {
                    'Category': st.column_config.TextColumn('Category', width='medium'),
                    'Bates Start': 'Bates Start',
                    'Bates End': 'Bates End',
                    'Documents': st.column_config.NumberColumn('Docs', width='small'),
                }
                if not _is_category_sort:
                    _col_config['Subcategory'] = st.column_config.TextColumn('Subcategory', width='medium')
                else:
                    _summary_df = _summary_df.drop(columns=['Subcategory'], errors='ignore')
                st.dataframe(
                    _summary_df,
                    column_config=_col_config,
                    width='stretch',
                    hide_index=True,
                )

                _summary_suffix = "CATEGORY_SUMMARY" if _is_category_sort else "FOLDER_SUMMARY"
                _summary_path = os.path.join(prod_path, f"{prod_name}_{_summary_suffix}.csv")
                _summary_df.to_csv(_summary_path, index=False)
                st.caption(f"Saved to `{prod_name}_{_summary_suffix}.csv`")

                _summary_csv_bytes = _summary_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    f"⬇️ Download {'Category' if _is_category_sort else 'Folder'} Summary",
                    data=_summary_csv_bytes,
                    file_name=f"{prod_name}_{_summary_suffix}.csv",
                    mime="text/csv",
                    key="dl_group_summary"
                )

                # Store summary in settings_json for later retrieval
                if _is_category_sort:
                    _disclosure_summary = _group_ranges

        # ── Final audit + cleanup ──
        _bates_start = prod_data[0]['BegDoc'] if prod_data else ''
        _bates_end = prod_data[-1]['EndDoc'] if prod_data else ''
        _pass2_elapsed = _pass2_time.monotonic() - _pass2_start
        db_manager.log_audit(case_folder_path, "PRODUCTION_EXPORTED", username=_prod_username,
            module="Production", details=json.dumps({
                "volume": prod_name, "format": prod_format,
                "mode": prod_mode,
                "sort_by_folder": _sort_by_folder,
                "sort_mode": _sort_mode,
                "output_path": prod_path, "doc_count": len(prod_data),
                "bates_start": _bates_start, "bates_end": _bates_end,
                "pass2_elapsed_seconds": round(_pass2_elapsed, 1),
            }))

        if prod_data:
            db_manager.save_last_bates_info(
                case_folder_path, prefix, current_num - 1, prod_name, bates_padding
            )

        # ── Record production run in history table ────────────────────
        # INSERT OR REPLACE semantics: overwrites the Pass-1-seeded row (which
        # had status='in_progress' or 'pass1_complete') with complete info and
        # status='finalized'. This is the terminal write for an outbound run.
        try:
            db_manager.record_production_run(case_folder_path, {
                'production_name': prod_name,
                'created_at': datetime.now().isoformat(),
                'created_by': _prod_username,
                'format': prod_format,
                'mode': prod_mode,
                'bates_prefix': prefix,
                'bates_start': _bates_start,
                'bates_end': _bates_end,
                'document_count': len(prod_data),
                'withheld_count': len(withhold_log_entries),
                'redacted_count': len(redaction_log_data),
                'error_count': _img_fail if '_img_fail' in dir() else 0,
                'endorsement_text': endorsement_text,
                'status': 'finalized',
                'direction': 'outbound',
                'settings_json': json.dumps({
                    'stamp_position': stamp_position if 'stamp_position' in dir() else '',
                    'bates_padding': bates_padding,
                    'sort_mode': _sort_mode,
                    'category_family_mode': 'strict' if st.session_state.get('cat_family_mode', '').startswith('Strict') else 'family',
                    'category_order': [c['name'] for c in db_manager.get_production_categories(case_folder_path)] if _sort_mode == 'Sort by Production Category' else [],
                    'disclosure_summary': _disclosure_summary if '_disclosure_summary' in dir() else [],
                }),
            })
        except Exception as _pr_err:
            logger.warning(f"Failed to record production run: {_pr_err}")

        # ── Deferred OCR Pass (parallel) ──────────────────────────────
        if _is_full_edrm and _deferred_ocr:
            import time as _ocr_perf_time
            _ocr_start = _ocr_perf_time.monotonic()

            _ocr_worker_count = min(
                p1.get('imaging_workers', 4),
                len(_deferred_ocr)
            )

            st.info(
                f"🔍 Running OCR on {len(_deferred_ocr)} document(s) with no embedded text "
                f"({_ocr_worker_count} workers)..."
            )
            _ocr_progress = st.progress(0)
            _ocr_status = st.empty()

            def _ocr_worker(item):
                """
                OCR a single document's pages from captured PNG bytes.
                Writes the result directly to the text file.
                Returns (cn, success, error_msg).
                """
                import pytesseract
                from PIL import Image as PILImage
                import io as _ocr_io
                PILImage.MAX_IMAGE_PIXELS = None  # Safe: trusted case documents, not untrusted web content

                tesseract_path = getattr(config, 'TESSERACT_PATH', r"C:\Tesseract-OCR\tesseract.exe")
                if os.path.exists(tesseract_path):
                    pytesseract.pytesseract.tesseract_cmd = tesseract_path

                try:
                    ocr_pages = []
                    for png_bytes in item['png_pages']:
                        img = PILImage.open(_ocr_io.BytesIO(png_bytes))
                        page_text = pytesseract.image_to_string(img)
                        ocr_pages.append(page_text)
                        img.close()

                    text_content = "\n".join(ocr_pages).strip()
                    with open(item['text_file_path'], 'w', encoding='utf-8') as tf:
                        tf.write(text_content)

                    return (item['cn'], True, '')
                except Exception as e:
                    return (item['cn'], False, str(e))

            from concurrent.futures import ThreadPoolExecutor, as_completed

            _ocr_completed = 0
            _ocr_errors = []

            with ThreadPoolExecutor(max_workers=_ocr_worker_count) as ocr_pool:
                future_to_cn = {
                    ocr_pool.submit(_ocr_worker, item): item['cn']
                    for item in _deferred_ocr
                }

                for future in as_completed(future_to_cn):
                    cn_done = future_to_cn[future]
                    try:
                        _cn, _ok, _err = future.result()
                        if not _ok:
                            _ocr_errors.append((_cn, _err))
                    except Exception as exc:
                        _ocr_errors.append((cn_done, str(exc)))

                    _ocr_completed += 1
                    _ocr_status.text(
                        f"OCR: {_ocr_completed}/{len(_deferred_ocr)} documents processed"
                    )
                    _ocr_progress.progress(_ocr_completed / len(_deferred_ocr))

            _ocr_elapsed = _ocr_perf_time.monotonic() - _ocr_start

            if _ocr_errors:
                st.warning(
                    f"⚠️ OCR failed for {len(_ocr_errors)} document(s): "
                    + ", ".join(f"{cn}" for cn, _ in _ocr_errors[:10])
                    + ("..." if len(_ocr_errors) > 10 else "")
                )
                _OCR_DISPLAY_LIMIT = 10
                for _ocr_cn, _ocr_err in _ocr_errors[:_OCR_DISPLAY_LIMIT]:
                    st.caption(f"  {_ocr_cn}: {_ocr_err}")
                if len(_ocr_errors) > _OCR_DISPLAY_LIMIT:
                    st.caption(f"  ... and {len(_ocr_errors) - _OCR_DISPLAY_LIMIT} more (see processing log for full list)")
                for _ocr_cn, _ocr_err in _ocr_errors:
                    logger.warning(f"OCR failed for {_ocr_cn}: {_ocr_err}")
            else:
                st.success(
                    f"✅ OCR completed: {len(_deferred_ocr)} documents in "
                    f"{_ocr_elapsed:.1f}s ({_ocr_worker_count} workers)"
                )

            # Free captured PNG data
            _deferred_ocr.clear()

            db_manager.log_audit(case_folder_path, "PRODUCTION_OCR_COMPLETE",
                username=_prod_username, module="Production",
                details=json.dumps({
                    "volume": prod_name,
                    "documents_ocred": _ocr_completed,
                    "ocr_errors": len(_ocr_errors),
                    "workers": _ocr_worker_count,
                    "elapsed_seconds": round(_ocr_elapsed, 1),
                }))

        # Clean up TEMP_ and STAGED_ files
        _images_dir = os.path.join(prod_path, "IMAGES")
        for f in os.listdir(_images_dir):
            if f.startswith("TEMP_"):
                try:
                    os.remove(os.path.join(_images_dir, f))
                except Exception:
                    pass
        _natives_dir = os.path.join(prod_path, "NATIVES")
        if os.path.exists(_natives_dir):
            for f in os.listdir(_natives_dir):
                if f.startswith("STAGED_"):
                    try:
                        os.remove(os.path.join(_natives_dir, f))
                    except Exception:
                        pass

        lottie_placeholder.empty()
        st.success(f"Production '{prod_name}' completed! Exported to {prod_format}.")
        st.balloons()

        st.session_state['prod_finalized'] = True
        st.session_state.pop('prod_pass1_complete', None)

        conn.close()

    def _render_outbound_production():
        """
        Render the outbound production body: sidebar management, config
        form, Run Production button handler (Pass 1 imaging), and Gap
        Analysis. Called from the else-branch of the state-gate chain
        when no checkpoint/finalized state is active.

        Extracted in beta-2.10 Commit 7 Phase A from the inline tab body
        (former lines 2267-3369). Phase B converts the three inner
        st.stop() calls to return, dissolving the script-halt side-effect
        that previously blanked tab_privlog on any error path.
        """

        st.header("2. Configure & Run")

        # --- SIDEBAR: Manage Existing Productions ---
        st.sidebar.markdown("---")
        st.sidebar.header("📁 Production Details")
        existing_prods = get_production_sets(case_folder)
        with st.sidebar.expander("🗑️ Manage Existing Productions", expanded=False):
            if not existing_prods:
                st.info("No productions found.")
            else:
                for ep in existing_prods:
                    st.write(f"**{ep}**")
                    confirm_del = st.text_input(f"Type **DELETE** to confirm deletion of {ep}:", key=f"confirm_{ep}")
                    if st.button(f"Delete {ep}", key=f"del_prod_{ep}"):
                        if confirm_del == "DELETE":
                            prod_path = os.path.join(case_folder, "Productions", ep)
                            try:
                                # 0. Clear Database Bates records to prevent Ghost Bates Numbers
                                try:
                                    db_manager.delete_production_volume(case_folder, ep)
                                except Exception as db_err:
                                    st.warning(f"Could not clear database Bates records: {db_err}")

                                # 1. Delete Folder
                                shutil.rmtree(prod_path)

                                # 2. Recalculate Bates continuity from remaining productions
                                db_manager.recalculate_last_bates_info(case_folder)

                                st.success(f"Deleted {ep} and cleared database Bates records.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to delete {ep}: {e}")
                        else:
                            st.error("⚠️ You must type exactly 'DELETE' (all caps) to confirm.")
                    st.markdown("---")

        # --- UI ---
        col1, col2 = st.columns([1, 2])

        with col1:
            st.header("Configure Production")

            # Auto-increment default production name
            default_prod_name = "PRODUCTION_001"
            if existing_prods:
                max_num = 0
                base_name = "PRODUCTION"
                for p in existing_prods:
                    parts = p.rsplit("_", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        max_num = max(max_num, int(parts[1]))
                        base_name = parts[0]
                if max_num > 0:
                    default_prod_name = f"{base_name}_{max_num + 1:03d}"

            if "prod_name_input" not in st.session_state:
                st.session_state["prod_name_input"] = default_prod_name
            prod_name = st.text_input("Production Name", key="prod_name_input")

            st.subheader("Production Type")
            prod_mode = st.radio(
                "Production Mode",
                ["Simple Production", "Full EDRM Production"],
                index=0,
                help=(
                    "**Simple Production** — Bates stamps, redaction burns, and privilege log only. "
                    "Fast output suitable for internal review, Filevine, or simple opposing counsel exchange. "
                    "No text files, load files, or OCR.\n\n"
                    "**Full EDRM Production** — Complete deliverable with text extraction, OCR, "
                    "Concordance DAT, Opticon OPT, and QC report. Required when the receiving party "
                    "needs load files for ingestion into a review platform."
                ),
                key="prod_mode_select"
            )
            _is_full_edrm = (prod_mode == "Full EDRM Production")
            if not _is_full_edrm:
                st.caption(
                    "Output: Bates-stamped images + natives, privilege log, redaction log. "
                    "No text extraction, no load files."
                )

            # Supplemental Production — continue Bates sequence from last run
            _last_bates = db_manager.get_last_bates_info(case_folder)
            if _last_bates:
                _continue = st.toggle(
                    "🔗 Continue from Last Production",
                    value=True,
                    help=(
                        f"When on, auto-populates the Bates prefix and starting number from "
                        f"the end of '{_last_bates['prod_name']}'. Toggle off to enter manually."
                    ),
                    key="_bates_continue_toggle"
                )
                if _continue:
                    _last_end_fmt = f"{_last_bates['prefix']}-{str(_last_bates['end_num']).zfill(_last_bates.get('padding', 6))}"
                    st.caption(f"Last production: **{_last_bates['prod_name']}** — ended at **{_last_end_fmt}**")
                    _default_prefix = _last_bates['prefix']
                    _default_start = _last_bates['end_num'] + 1
                else:
                    _default_prefix = "ABC"
                    _default_start = 1
                # Force-update prefix/start when toggle changes
                _prev_continue = st.session_state.get('_bates_continue_prev')
                if _prev_continue is not None and _prev_continue != _continue:
                    st.session_state["bates_prefix_input"] = _default_prefix
                    st.session_state["bates_start_number"] = _default_start
                st.session_state['_bates_continue_prev'] = _continue
            else:
                _continue = False
                _default_prefix = "ABC"
                _default_start = 1

            if "bates_prefix_input" not in st.session_state:
                st.session_state["bates_prefix_input"] = _default_prefix
            prefix = st.text_input("Bates Prefix", key="bates_prefix_input")
            if "bates_start_number" not in st.session_state:
                st.session_state["bates_start_number"] = _default_start
            start_num = st.number_input("Starting Number", min_value=1, step=1, key="bates_start_number")

            prod_format = st.radio(
                "Production Format",
                ["PDF", "TIFF", "Native Only"],
                index=0,
                key="prod_format_select",
                help=(
                    "**PDF** — multi-page PDFs. "
                    "**TIFF** — single-page TIFFs + Opticon load file. "
                    "**Native Only** — skips imaging; produces original files renamed to Bates numbers with slip-sheet placeholders."
                )
            )
            if prod_format == "Native Only":
                st.info(
                    "ℹ️ **Native Only mode** — documents will be produced in their original format (renamed to Bates). "
                    "Bates stamps appear on slip sheets only. Text files are populated from existing extracted text."
                )

            st.subheader("Bates Stamp Options")
            bates_padding = st.slider("Bates Padding Digits", min_value=4, max_value=12, value=6, help="Number of digits for Bates numbers (e.g., 6 = ABC-000001).", key="bates_padding")
            stamp_enabled = st.checkbox("Stamp Bates on Pages", value=True, help="Burns the Bates number directly onto each page of the produced document.", key="stamp_enabled")
            if stamp_enabled:
                stamp_position = st.selectbox("Stamp Position", ["bottom-right", "bottom-left", "bottom-center"], key="stamp_position_select")
                stamp_color = st.selectbox("Stamp Color", ["black", "red"], key="stamp_color_select")
                stamp_font_size = st.slider("Stamp Font Size", min_value=7, max_value=14, value=12, key="stamp_font_size")
            else:
                stamp_position = "bottom-right"
                stamp_color = "black"
                stamp_font_size = 12

            st.subheader("Redaction Options")
            skip_redaction_burn = st.checkbox(
                "Skip redaction burn (co-counsel preview)",
                value=False,
                help=(
                    "When checked, redaction marks are NOT burned into the produced PDFs — "
                    "red annotation boxes remain visible but content is NOT removed. "
                    "Use this ONLY for co-counsel review copies. NEVER use for disclosures to opposing counsel."
                ),
                key="skip_redaction_burn"
            )
            if skip_redaction_burn:
                st.warning(
                    "**REDACTION BURN DISABLED.** Produced documents will contain visible redaction "
                    "boxes but privileged content will NOT be removed. These documents are NOT safe "
                    "for disclosure to opposing counsel."
                )

            st.subheader("Confidentiality Endorsement")
            endorsement_options = ["None", "CONFIDENTIAL", "HIGHLY CONFIDENTIAL", "HIGHLY CONFIDENTIAL — ATTORNEYS' EYES ONLY", "Custom"]
            endorsement_choice = st.selectbox("Confidentiality Designation", endorsement_options, index=0, key="endorsement_choice")
            if endorsement_choice == "Custom":
                endorsement_text = st.text_input("Custom Endorsement Text", value="", key="custom_endorsement_text")
            elif endorsement_choice == "None":
                endorsement_text = None
            else:
                endorsement_text = endorsement_choice

            st.subheader("Date Range Culling")
            use_date_range = st.checkbox("Filter by Date Range", value=False, key="use_date_range")
            if use_date_range:
                date_col1, date_col2 = st.columns(2)
                with date_col1:
                    date_start = st.date_input("Start Date", value=None, key="date_range_start")
                with date_col2:
                    date_end = st.date_input("End Date", value=None, key="date_range_end")
            else:
                date_start = None
                date_end = None

            st.subheader("Document Ordering")
            # Check if production categories exist to determine default
            _setup_prod_cats = db_manager.get_production_categories(case_folder)
            _sort_options = ["Sort by Production Category", "Sort by Ingestion Folder", "Sort by Family Only"]
            _sort_default = 0 if _setup_prod_cats else 1
            sort_mode = st.radio(
                "Production sort order",
                options=_sort_options,
                index=_sort_default,
                help=(
                    "**Production Category** — Groups documents by their assigned category "
                    "(Correspondence, Contracts, etc.) in the order you defined. "
                    "Produces contiguous Bates ranges per category — ideal for 26(a)(1) disclosures.\n\n"
                    "**Ingestion Folder** — Groups by source folder structure, then family.\n\n"
                    "**Family Only** — Sorts by document family group and control number only."
                ),
                key="prod_sort_mode"
            )
            sort_by_folder = (sort_mode == "Sort by Ingestion Folder")

            # Category family-handling sub-option
            _cat_strict = False
            if sort_mode == "Sort by Production Category":
                _cat_family_mode = st.radio(
                    "Family handling",
                    ["Keep families together (parent's category)",
                     "Strict category grouping (split families)"],
                    index=0,
                    help=(
                        "**Keep families together** — a parent and its attachments stay adjacent "
                        "in the Bates sequence, sorted by the parent's category. Category ranges "
                        "may not be contiguous.\n\n"
                        "**Strict category grouping** — each document sorts by its own category "
                        "regardless of family. Produces contiguous Bates ranges per category, but "
                        "a parent and child may end up in different Bates ranges."
                    ),
                    key="cat_family_mode"
                )
                _cat_strict = _cat_family_mode.startswith("Strict")
                if _cat_strict:
                    st.warning(
                        "Strict mode will separate parent documents from their attachments "
                        "if they have different production categories. Bates ranges will be "
                        "contiguous per category, but document families may be split across ranges."
                    )

            # Category summary display when category sort selected
            if sort_mode == "Sort by Production Category":
                _setup_cat_summary = db_manager.get_category_summary(case_folder, exclude_non_responsive=True)
                if _setup_cat_summary:
                    st.caption("**Category Breakdown:**")
                    for _scat in _setup_prod_cats:
                        _scat_count = _setup_cat_summary.get(_scat['name'], 0)
                        st.caption(f"  {_scat['name']} — {_scat_count:,} docs")
                    _scat_uncat = _setup_cat_summary.get('Uncategorized', 0)
                    if _scat_uncat > 0:
                        st.warning(
                            f"⚠️ {_scat_uncat:,} documents have no production category assigned. "
                            "They will be placed at the end of the production. "
                            "Consider running Auto-Categorize in the Review page first."
                        )

            # ── Privilege Log Profile ──
            st.subheader("Privilege Log")
            _prod_pl_raw = db_manager.get_case_setting(case_folder, 'privilege_log_profiles')
            _prod_pl_profiles = {}
            if _prod_pl_raw:
                try:
                    _prod_pl_profiles = json.loads(_prod_pl_raw)
                except (json.JSONDecodeError, TypeError):
                    pass
            if "EDRM Standard" not in _prod_pl_profiles:
                _prod_pl_profiles["EDRM Standard"] = {"columns": _PL_DEFAULT_COLS[:], "headers": {}, "merges": []}

            _prod_pl_profile_name = st.selectbox(
                "Privilege Log Profile",
                options=list(_prod_pl_profiles.keys()),
                help="Controls columns, headers, and ordering in the production privilege log. "
                     "Profiles are configured in the Privilege Log tab.",
                key="prod_pl_profile"
            )
            _prod_pl_preview = _prod_pl_profiles.get(_prod_pl_profile_name, {})
            _prod_pl_cols = _prod_pl_preview.get('columns', _PL_DEFAULT_COLS)
            st.caption(f"{len(_prod_pl_cols)} columns: {', '.join(_PL_COL_KEY_TO_DISPLAY.get(c, c) for c in _prod_pl_cols[:6])}{'...' if len(_prod_pl_cols) > 6 else ''}")

            # ── Performance (parallel imaging) ──
            if prod_format != "Native Only":
                st.subheader("Performance")
                import os as _os_perf
                _available_cores = _os_perf.cpu_count() or 4
                _max_imaging_workers = max(1, _available_cores - 1)

                _config_workers = getattr(config, 'IMAGING_WORKERS', 0)
                _default_workers = _config_workers if 0 < _config_workers <= _max_imaging_workers else min(4, _max_imaging_workers)
                imaging_workers = st.slider(
                    "Imaging Workers (Pass 1)",
                    min_value=1,
                    max_value=_max_imaging_workers,
                    value=_default_workers,
                    help=(
                        f"Number of parallel processes for document imaging. "
                        f"Your system has {_available_cores} CPU cores. "
                        f"Higher values speed up Pass 1 but use more memory. "
                        f"Each worker may spawn a COM subprocess for Office files. "
                        f"Recommended: 2–4 for most systems."
                    ),
                    key="prod_imaging_workers"
                )
            else:
                imaging_workers = 1  # not used, but define for downstream reference

            # Near-dupe pending-review FYI (non-blocking — does NOT gate the burn).
            # Spec §5.4: the defensibility report (S-1c) distinguishes confirmed-
            # suppressed from pending; this surfaces the gap before the user commits.
            _prod_nd_progress = db_manager.get_near_dupe_review_progress(case_folder)
            if _prod_nd_progress["n_clusters"] > 0 and _prod_nd_progress["pending"] > 0:
                st.info(
                    f"ℹ️ {_prod_nd_progress['pending']:,} near-duplicate documents across "
                    f"{_prod_nd_progress['n_clusters']:,} clusters await reviewer confirmation. "
                    f"Production will not be blocked, but the defensibility report (S-1c) "
                    f"will distinguish confirmed from pending. Consider completing review in "
                    f"**Review → 🧬 Near-Dupe Clusters** before burning."
                )

            if st.button("Run Production", key="run_production_btn"):
                # Safety: Prevent duplicate production names
                existing_prods = get_production_sets(case_folder)
                # If Pass 1 already completed for this production, the checkpoint UI handles it
                _p1_state = st.session_state.get('prod_pass1')
                if prod_name in existing_prods:
                    if _p1_state and _p1_state.get('prod_name') == prod_name and st.session_state.get('prod_pass1_complete'):
                        pass  # checkpoint UI will render on rerun
                    else:
                        st.error(f"Production '{prod_name}' already exists! Choose a unique name or use the DELETE & RE-RUN option on the right.")
                        return

                conn = db_manager.get_connection(case_folder)

                # User-toggleable exclusion clauses shared by the base-set query
                # AND the FIX #8 family expansion query below. Without reuse,
                # family expansion silently overrides user exclusions (non-responsive
                # attachments of responsive parents leak into production).
                #
                # NOTE: the inbound/external source_party filter used to live here
                # behind a user-toggleable `exclude_external` checkbox; in
                # beta-2.10 Commit 3 that filter was hoisted to a mandatory,
                # non-toggleable clause on every outbound query (via
                # db_manager.OUTBOUND_SOURCE_FILTER_SQL) to eliminate the
                # defensibility hazard of user-facing opt-out.
                _exclusion_clauses = []
                if exclude_previously_produced:
                    _exclusion_clauses.append("(begdoc IS NULL OR begdoc = '')")
                if exclude_suppressed:
                    _exclusion_clauses.append("(tags NOT LIKE '%Suppressed%' OR tags IS NULL)")
                if exclude_non_responsive:
                    _exclusion_clauses.append(
                        "(tags NOT LIKE '%Non-Responsive%' OR tags IS NULL) "
                        "AND (tags NOT LIKE '%Not Responsive%' OR tags IS NULL)"
                    )
                _exclusion_sql = (" AND " + " AND ".join(_exclusion_clauses)) if _exclusion_clauses else ""

                # Build Query — mandatory inbound exclusion on every path
                _mandatory_outbound = db_manager.OUTBOUND_SOURCE_FILTER_SQL
                if st.session_state.get('production_selection'):
                    cns = st.session_state['production_selection']
                    placeholders = ','.join(['?'] * len(cns))
                    query = (
                        f"SELECT * FROM documents WHERE control_number IN ({placeholders}) "
                        f"AND {_mandatory_outbound}"
                    )
                    base_df = pd.read_sql_query(query, conn, params=cns)
                else:
                    query = (
                        "SELECT * FROM documents WHERE processing_status IN ('Processed', 'Master') "
                        f"AND {_mandatory_outbound}" + _exclusion_sql
                    )
                    _query_params = []
                    if use_date_range and date_start and date_end:
                        query += " AND (date_sent BETWEEN ? AND ?)"
                        _query_params.extend([str(date_start), str(date_end)])
                    base_df = pd.read_sql_query(query, conn, params=_query_params or None)

                # FIX #8: Universal Lineage Mapping for Family Integrity
                if not base_df.empty:
                    cn_to_group = dict(pd.read_sql_query("SELECT control_number, group_id FROM documents", conn).itertuples(index=False, name=None))

                    affected_roots = set(base_df['group_id'])

                    all_target_cns = []
                    for cn in cn_to_group.keys():
                        if cn_to_group[cn] in affected_roots:
                            all_target_cns.append(cn)

                    all_family_dfs = []
                    chunk_size = 900
                    for i in range(0, len(all_target_cns), chunk_size):
                        chunk = all_target_cns[i:i + chunk_size]
                        placeholders = ','.join(['?'] * len(chunk))
                        family_sql = (
                            f"SELECT * FROM documents WHERE control_number IN ({placeholders}) "
                            f"AND processing_status IN ('Processed', 'Master') "
                            f"AND {_mandatory_outbound}{_exclusion_sql}"
                        )
                        family_chunk_df = pd.read_sql_query(family_sql, conn, params=chunk)
                        all_family_dfs.append(family_chunk_df)

                    family_df = pd.concat(all_family_dfs) if all_family_dfs else pd.DataFrame()
                    df = pd.concat([base_df, family_df]).drop_duplicates(subset='id')
                    df['sort_group'] = df['group_id']

                    df['_is_parent'] = df['parent_id'].isna() | (df['parent_id'].astype(str).str.strip() == '')

                    if sort_mode == "Sort by Production Category":
                        # Category-based sort: category order → family → parent-first → control_number
                        _prod_cats_sort = db_manager.get_production_categories(case_folder)
                        _cat_order = {cat['name']: cat['sort_order'] for cat in _prod_cats_sort}
                        _max_order = max(_cat_order.values(), default=0) + 1  # uncategorized sorts last

                        if _cat_strict:
                            # Strict: each doc sorts by its own category
                            df['_family_category'] = df['production_category']
                        else:
                            # Family mode: inherit root parent's category
                            _root_cats = df[df['_is_parent'] & df['control_number'].notna()].set_index('control_number')['production_category']
                            df['_family_category'] = df['sort_group'].map(_root_cats).fillna(df['production_category'])
                        df['_cat_sort_order'] = df['_family_category'].map(_cat_order).fillna(_max_order)

                        # Uncategorized docs sub-sort by folder for structure
                        _root_folders = df[df['_is_parent'] & df['control_number'].notna()].set_index('control_number')[['source_collection', 'source_subcollection']]
                        df['_family_collection'] = df['sort_group'].map(_root_folders['source_collection']).fillna(df['source_collection'])
                        df['_sort_collection'] = df['_family_collection'].fillna('\uffff')

                        df = df.sort_values(
                            by=['_cat_sort_order', '_family_category', '_sort_collection',
                                'sort_group', '_is_parent', 'control_number'],
                            ascending=[True, True, True, True, False, True]
                        )
                        df = df.drop(columns=[
                            '_cat_sort_order', '_family_category', '_is_parent',
                            '_family_collection', '_sort_collection'
                        ], errors='ignore')

                    elif sort_by_folder:
                        # Folder-based sort: collection → subcollection → family → parent-first → control_number
                        # Inherit parent's folder for entire family so families don't split across folders
                        _root_folders = df[df['_is_parent'] & df['control_number'].notna()].set_index('control_number')[['source_collection', 'source_subcollection']]
                        df['_family_collection'] = df['sort_group'].map(_root_folders['source_collection']).fillna(df['source_collection'])
                        df['_family_subcollection'] = df['sort_group'].map(_root_folders['source_subcollection']).fillna(df['source_subcollection'])
                        # NULL collections sort to the end via \uffff (highest Unicode char)
                        df['_sort_collection'] = df['_family_collection'].fillna('\uffff')
                        df['_sort_subcollection'] = df['_family_subcollection'].fillna('\uffff')
                        df = df.sort_values(
                            by=['_sort_collection', '_sort_subcollection', 'sort_group', '_is_parent', 'control_number'],
                            ascending=[True, True, True, False, True]  # _is_parent desc: parents (1) before children (0)
                        )
                        df = df.drop(columns=[
                            '_sort_collection', '_sort_subcollection', '_is_parent',
                            '_family_collection', '_family_subcollection'
                        ], errors='ignore')
                    else:
                        df = df.drop(columns=['_is_parent'], errors='ignore')
                        df = df.sort_values(by=['sort_group', 'control_number'])
                else:
                    df = base_df

                conn.close()

                if df.empty:
                    st.warning("No documents found matching the criteria. If you have already produced all your dataset, there are no new internal documents to produce in this set.")
                else:
                    st.info(f"Found {len(df)} documents to produce.")

                    # ── Pre-Production Privilege Audit ──────────────────────────
                    # Hard block: Redact-disposition docs must have redaction marks
                    _redact_docs = df[df['privilege_status'] == 'Redact']
                    if not _redact_docs.empty:
                        _missing_marks_cns = []
                        _audit_conn = db_manager.get_connection(case_folder)
                        for _, _rd_row in _redact_docs.iterrows():
                            _rd_marks = _audit_conn.execute(  # db_manager: exempt (production loop)
                                "SELECT COUNT(*) as cnt FROM redaction_marks WHERE control_number = ?",
                                (_rd_row['control_number'],)
                            ).fetchone()
                            if not _rd_marks or _rd_marks['cnt'] == 0:
                                _missing_marks_cns.append(_rd_row['control_number'])
                        _audit_conn.close()

                        if _missing_marks_cns:
                            st.error(
                                f"⛔ **Production Blocked — {len(_missing_marks_cns)} document(s) marked 'Redact & Produce' "
                                f"have NO redaction marks placed.** These documents would be produced with privileged "
                                f"content fully visible.\n\n"
                                f"**Affected documents:** {', '.join(_missing_marks_cns[:10])}"
                                f"{'...' if len(_missing_marks_cns) > 10 else ''}\n\n"
                                f"Return to the Review module and either:\n"
                                f"- Draw redaction marks on these documents, OR\n"
                                f"- Change their disposition to 'Withhold Entirely'"
                            )
                            return

                    # Soft warning: privilege tags but no disposition set
                    _priv_members = db_manager.get_privilege_tag_members(case_folder)
                    if _priv_members:
                        _no_disp_cns = []
                        for _, _nd_row in df.iterrows():
                            _doc_tags = str(_nd_row.get('tags') or '')
                            _has_priv_tag = any(m in _doc_tags for m in _priv_members)
                            _has_disp = _nd_row.get('privilege_status') in ('Redact', 'Withhold')
                            if _has_priv_tag and not _has_disp:
                                _no_disp_cns.append(_nd_row['control_number'])

                        if _no_disp_cns:
                            st.error(
                                f"**Production blocked:** {len(_no_disp_cns)} document(s) have privilege tags "
                                f"but no disposition (Withhold/Redact). Producing these documents without a "
                                f"privilege disposition decision risks inadvertent privilege waiver.\n\n"
                                f"**Affected documents:** {', '.join(_no_disp_cns[:10])}"
                                f"{'...' if len(_no_disp_cns) > 10 else ''}\n\n"
                                f"Return to the Review module and set a disposition for each "
                                f"privilege-tagged document, or remove the privilege tags if they "
                                f"were applied in error."
                            )
                            return

                    # Create Production Folder
                    prod_path = os.path.join(case_folder, "Productions", prod_name)
                    if os.path.exists(prod_path):
                        st.error(f"Production folder '{prod_name}' already exists.")
                        if st.button(f"DELETE & RE-RUN '{prod_name}'", key="delete_rerun_prod_btn"):
                            try:
                                try:
                                    db_manager.delete_production_volume(case_folder, prod_name)
                                except Exception as db_err:
                                    st.warning(f"Could not clear database Bates records: {db_err}")
                                shutil.rmtree(prod_path)

                                # Recalculate Bates continuity from remaining productions
                                db_manager.recalculate_last_bates_info(case_folder)

                                st.success(f"Deleted {prod_name} and cleared database Bates records. Click 'Run Production' to re-execute.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to delete: {e}")
                    else:
                        os.makedirs(prod_path)
                        os.makedirs(os.path.join(prod_path, "IMAGES"))
                        if _is_full_edrm:
                            os.makedirs(os.path.join(prod_path, "TEXT"))
                        os.makedirs(os.path.join(prod_path, "NATIVES"))

                        _prod_username = st.session_state.get('username', 'unknown')
                        db_manager.log_audit(case_folder, "PRODUCTION_CREATED", username=_prod_username,
                            module="Production", details=json.dumps({
                                "volume": prod_name, "format": prod_format,
                                "doc_count": len(df), "prefix": prefix
                            }))

                        # ── PASS 1: Imaging Only ──────────────────────────────────────
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        _prod_cancel_placeholder = st.empty()
                        st.session_state['_prod_cancel'] = False
                        with _prod_cancel_placeholder.container():
                            st.markdown("<div style='height:0;overflow:hidden'>", unsafe_allow_html=True)
                            st.button(
                                "Cancel Imaging",
                                key="_prod_cancel_btn",
                                on_click=lambda: st.session_state.update({'_prod_cancel': True}),
                                type="secondary",
                            )
                            st.markdown("</div>", unsafe_allow_html=True)

                        lottie_placeholder = ui_utils.start_lottie_spinner(
                            f"Pass 1: Imaging documents for '{prod_name}'... Please wait.")
                        ui_utils.show_overlay_cancel_button()

                        df = df[~df['tags'].str.contains('Junk Image', na=False, case=False)]
                        # Only apply family-only sort if no category/folder sort was already done
                        if 'sort_group' in df.columns and sort_mode == "Sort by Family Only":
                            df = df.sort_values(by=['sort_group', 'control_number'])
                        df = df.reset_index(drop=True)

                        if len(df) > 9500:
                            st.warning(
                                f"**Large Production Set ({len(df):,} documents)** — this approaches the "
                                "OpenSearch `index.max_result_window` limit (10,000). "
                                "The current SQLite-based fetch is unaffected, but any future "
                                "OpenSearch-driven export should use `os_manager.scan_all()` to avoid silent truncation."
                            )

                        _prod_was_cancelled = False
                        _prod_completed_count = 0
                        results_list = []
                        CONTAINER_EXTENSIONS = {'.pst', '.zip', '.rar', '.7z'}

                        # Identify Withhold-disposition documents (skip imaging in Pass 1)
                        _withhold_cns = set(
                            df[df['privilege_status'] == 'Withhold']['control_number'].tolist()
                        )

                        import time as _perf_time
                        _pass1_start = _perf_time.monotonic()

                        # ── Seed production_runs row with status='in_progress' ──
                        # Creates the DB marker before any staging files hit disk,
                        # so the orphan detector correctly identifies this production
                        # as legitimately in-flight if the browser is closed mid-Pass 1.
                        # INSERT OR REPLACE means Finalize (or Abort) later overwrites
                        # this row with complete info + terminal status.
                        #
                        # State machine: 'in_progress' -> 'pass1_complete' -> 'finalized'
                        # (or 'aborted' from any state). The 'finalizing' state defined
                        # in db_manager is reserved for a future long-running Finalize
                        # phase (e.g., multi-minute PDF burn) — not emitted today because
                        # current Finalize is effectively atomic from the detector's
                        # perspective. Do not remove 'finalizing' from predicates.
                        try:
                            db_manager.record_production_run(case_folder, {
                                'production_name': prod_name,
                                'created_at': datetime.now().isoformat(),
                                'created_by': _prod_username,
                                'format': prod_format,
                                'mode': prod_mode,
                                'status': 'in_progress',
                                'direction': 'outbound',
                            })
                        except Exception as _pr_seed_err:
                            logger.warning(f"Failed to seed production_runs row at Pass 1 start: {_pr_seed_err}")

                        # ── Pre-classify documents ──
                        _containers_skipped = 0
                        _to_image = []  # list of item dicts for imaging/copying

                        for i, row in df.iterrows():
                            cn = row['control_number']
                            ext = row.get('file_extension', '') or ''

                            # Skip containers and split-source shells
                            if (row.get('processing_status') in ('Container_Scanned', 'Split_Source')
                                    or ext.lower() in CONTAINER_EXTENSIONS):
                                _containers_skipped += 1
                                continue

                            # Withheld → immediate result, no imaging needed
                            if cn in _withhold_cns:
                                results_list.append({
                                    'control_number': cn,
                                    'file_name': row['file_name'],
                                    'file_extension': ext,
                                    'source_file': row['full_path'],
                                    'temp_pdf_path': None,
                                    'success': True,
                                    'error_msg': '',
                                    'page_count': 1,
                                    'is_expected_native': False,
                                    'category': 'Withheld',
                                    'staged_native_path': None,
                                    'retry_excluded': False,
                                })
                                continue

                            # Resolve source file (same logic as before)
                            orig_path = row['full_path']
                            reviewed_path_local = os.path.join(case_folder, "Reviewed", f"{cn}.pdf")
                            processed_pdf_local = os.path.join(case_folder, "Processed", f"{cn}.pdf")
                            if os.path.exists(reviewed_path_local):
                                source_file = reviewed_path_local
                            elif os.path.exists(processed_pdf_local):
                                source_file = processed_pdf_local
                            else:
                                source_file = orig_path

                            is_expected_native = not universal_imager.should_image(ext)
                            temp_pdf_path = os.path.join(prod_path, "IMAGES", f"TEMP_{cn}.pdf")

                            _to_image.append({
                                'row': row.to_dict(),
                                'source_file': source_file,
                                'temp_pdf_path': temp_pdf_path,
                                'ext': ext,
                                'is_expected_native': is_expected_native,
                                'processed_pdf_local': processed_pdf_local,
                            })

                        # ── Native Only Mode — Sequential Path (No Pool) ──
                        if prod_format == "Native Only":
                            for idx, item in enumerate(_to_image):
                                if st.session_state.get('_prod_cancel', False):
                                    _prod_was_cancelled = True
                                    db_manager.log_audit(case_folder, "PRODUCTION_CANCELLED",
                                        username=_prod_username, module="Production",
                                        details=json.dumps({
                                            "volume": prod_name,
                                            "completed": _prod_completed_count,
                                            "total": len(_to_image),
                                            "phase": "Pass 1 (native copy)",
                                        }))
                                    break

                                row = item['row']
                                cn = row['control_number']
                                ext = item['ext']
                                source_file = item['source_file']
                                status_text.text(f"Copying {cn} ({idx+1}/{len(_to_image)})")

                                staged_native_path = os.path.join(
                                    prod_path, "NATIVES", f"STAGED_{cn}{ext}"
                                )
                                try:
                                    shutil.copy2(source_file, staged_native_path)
                                    success = True
                                    error_msg = ""
                                except Exception as e:
                                    success = False
                                    error_msg = f"Native copy failed: {e}"
                                    staged_native_path = None

                                results_list.append({
                                    'control_number': cn,
                                    'file_name': row['file_name'],
                                    'file_extension': ext,
                                    'source_file': source_file,
                                    'temp_pdf_path': None,
                                    'success': success,
                                    'error_msg': error_msg,
                                    'page_count': 1,
                                    'is_expected_native': False,
                                    'category': 'Native',
                                    'staged_native_path': staged_native_path,
                                    'retry_excluded': False,
                                })
                                _prod_completed_count += 1
                                progress_bar.progress((_prod_completed_count) / max(len(_to_image), 1))

                        # ── PDF/TIFF Mode — Parallel Imaging via ProcessPoolExecutor ──
                        else:
                            from concurrent.futures import ProcessPoolExecutor, as_completed

                            _total_to_image = len(_to_image)
                            _pool_workers = min(imaging_workers, _total_to_image) if _total_to_image > 0 else 1

                            status_text.text(f"Imaging {_total_to_image} documents with {_pool_workers} workers...")

                            # Separate pre-copied processed PDFs from docs needing imaging
                            _needs_imaging = []
                            for item in _to_image:
                                cn = item['row']['control_number']
                                source_file = item['source_file']
                                temp_pdf_path = item['temp_pdf_path']
                                processed_pdf_local = item['processed_pdf_local']

                                if source_file == processed_pdf_local and source_file.lower().endswith('.pdf'):
                                    # Pre-copy processed PDFs in main process (fast I/O, no imaging needed)
                                    try:
                                        shutil.copy2(source_file, temp_pdf_path)
                                        _p_count = universal_imager.get_pdf_page_count(temp_pdf_path)
                                        results_list.append({
                                            'control_number': cn,
                                            'file_name': item['row']['file_name'],
                                            'file_extension': item['ext'],
                                            'source_file': source_file,
                                            'temp_pdf_path': temp_pdf_path,
                                            'success': True,
                                            'error_msg': '',
                                            'page_count': _p_count,
                                            'is_expected_native': item['is_expected_native'],
                                            'category': 'Expected Native' if item['is_expected_native'] else 'Imaged',
                                            'staged_native_path': None,
                                            'retry_excluded': False,
                                        })
                                        # Stage native for expected natives
                                        if item['is_expected_native']:
                                            _sn = os.path.join(prod_path, "NATIVES", f"STAGED_{cn}{item['ext']}")
                                            try:
                                                shutil.copy2(source_file, _sn)
                                                results_list[-1]['staged_native_path'] = _sn
                                            except Exception:
                                                pass
                                        _prod_completed_count += 1
                                        progress_bar.progress(_prod_completed_count / max(_total_to_image, 1))
                                    except Exception as _cp_e:
                                        # Copy failed — fall through to imaging pool
                                        _needs_imaging.append(item)
                                elif not os.path.exists(source_file):
                                    # Source file missing — record failure immediately
                                    results_list.append({
                                        'control_number': cn,
                                        'file_name': item['row']['file_name'],
                                        'file_extension': item['ext'],
                                        'source_file': source_file,
                                        'temp_pdf_path': None,
                                        'success': False,
                                        'error_msg': f"Source file not found at {source_file}",
                                        'page_count': 1,
                                        'is_expected_native': item['is_expected_native'],
                                        'category': 'Imaging Failure',
                                        'staged_native_path': None,
                                        'retry_excluded': False,
                                    })
                                    _prod_completed_count += 1
                                    progress_bar.progress(_prod_completed_count / max(_total_to_image, 1))
                                elif item['is_expected_native']:
                                    # Expected native — skip imaging pool, stage native directly
                                    staged_native_path = os.path.join(
                                        prod_path, "NATIVES", f"STAGED_{cn}{item['ext']}"
                                    )
                                    try:
                                        shutil.copy2(source_file, staged_native_path)
                                    except Exception:
                                        staged_native_path = None

                                    _reason = (
                                        f"Native by EDRM policy: {item['ext']} (spreadsheet/tabular data)"
                                        if universal_imager.is_native_by_policy(item['ext'])
                                        else f"No imaging path for extension: {item['ext']}"
                                    )

                                    results_list.append({
                                        'control_number': cn,
                                        'file_name': item['row']['file_name'],
                                        'file_extension': item['ext'],
                                        'source_file': source_file,
                                        'temp_pdf_path': None,
                                        'success': False,
                                        'error_msg': _reason,
                                        'page_count': 1,
                                        'is_expected_native': True,
                                        'category': 'Expected Native',
                                        'staged_native_path': staged_native_path,
                                        'retry_excluded': False,
                                    })
                                    _prod_completed_count += 1
                                    progress_bar.progress(_prod_completed_count / max(_total_to_image, 1))
                                else:
                                    _needs_imaging.append(item)

                            # Submit imaging jobs to the pool
                            if _needs_imaging and not _prod_was_cancelled:
                                if not IMAGER_AVAILABLE:
                                    # No imager — record all as failures
                                    for item in _needs_imaging:
                                        cn = item['row']['control_number']
                                        results_list.append({
                                            'control_number': cn,
                                            'file_name': item['row']['file_name'],
                                            'file_extension': item['ext'],
                                            'source_file': item['source_file'],
                                            'temp_pdf_path': None,
                                            'success': False,
                                            'error_msg': 'Universal Imager Not Available',
                                            'page_count': 1,
                                            'is_expected_native': item['is_expected_native'],
                                            'category': 'Imaging Failure',
                                            'staged_native_path': None,
                                            'retry_excluded': False,
                                        })
                                        _prod_completed_count += 1
                                        progress_bar.progress(_prod_completed_count / max(_total_to_image, 1))
                                else:
                                    _pool_workers = min(_pool_workers, len(_needs_imaging))
                                    with ProcessPoolExecutor(max_workers=_pool_workers) as pool:
                                        # Build futures map: future → item dict
                                        future_to_item = {}
                                        for item in _needs_imaging:
                                            future = pool.submit(
                                                universal_imager.image_document_safe,
                                                item['source_file'],
                                                item['temp_pdf_path'],
                                                item['row']['control_number'],
                                            )
                                            future_to_item[future] = item

                                        # Collect results as they complete
                                        for future in as_completed(future_to_item):
                                            # Check cancel flag between completions
                                            if st.session_state.get('_prod_cancel', False):
                                                _prod_was_cancelled = True
                                                # Cancel remaining futures (best-effort — running workers finish)
                                                for f in future_to_item:
                                                    f.cancel()
                                                db_manager.log_audit(case_folder, "PRODUCTION_CANCELLED",
                                                    username=_prod_username, module="Production",
                                                    details=json.dumps({
                                                        "volume": prod_name,
                                                        "completed": _prod_completed_count,
                                                        "total": _total_to_image,
                                                        "phase": "Pass 1 (parallel imaging)",
                                                    }))
                                                break

                                            item = future_to_item[future]
                                            row = item['row']
                                            cn = row['control_number']
                                            ext = item['ext']
                                            source_file = item['source_file']
                                            is_expected_native = item['is_expected_native']
                                            temp_pdf_path = item['temp_pdf_path']

                                            # Get result from the worker
                                            try:
                                                result = future.result()
                                                success = result['success']
                                                error_msg = result['error_msg']
                                                page_count = result['page_count']
                                            except Exception as exc:
                                                success = False
                                                error_msg = f"Worker process error: {exc}"
                                                page_count = 1

                                            # If imaging succeeded and source was a processed PDF, get accurate page count
                                            if success and page_count == 1 and source_file == item['processed_pdf_local']:
                                                page_count = universal_imager.get_pdf_page_count(temp_pdf_path)

                                            # Stage native for expected natives or failed images
                                            staged_native_path = None
                                            if is_expected_native or not success:
                                                staged_native_path = os.path.join(
                                                    prod_path, "NATIVES", f"STAGED_{cn}{ext}"
                                                )
                                                try:
                                                    shutil.copy2(source_file, staged_native_path)
                                                except Exception:
                                                    staged_native_path = None

                                            # Classify category
                                            if success and not is_expected_native:
                                                category = 'Imaged'
                                            elif is_expected_native:
                                                category = 'Expected Native'
                                            else:
                                                category = 'Imaging Failure'

                                            results_list.append({
                                                'control_number': cn,
                                                'file_name': row['file_name'],
                                                'file_extension': ext,
                                                'source_file': source_file,
                                                'temp_pdf_path': temp_pdf_path if success else None,
                                                'success': success,
                                                'error_msg': error_msg,
                                                'page_count': page_count,
                                                'is_expected_native': is_expected_native,
                                                'category': category,
                                                'staged_native_path': staged_native_path,
                                                'retry_excluded': False,
                                            })

                                            _prod_completed_count += 1
                                            status_text.text(
                                                f"Imaging: {_prod_completed_count}/{_total_to_image} documents processed"
                                            )
                                            progress_bar.progress(_prod_completed_count / max(_total_to_image, 1))

                        _pass1_elapsed = _perf_time.monotonic() - _pass1_start

                        # ── Handle Pass 1 cancellation ──
                        _prod_cancel_placeholder.empty()
                        if _prod_was_cancelled:
                            lottie_placeholder.empty()
                            # Flip production_runs.status to 'aborted' before folder
                            # cleanup so the row persists as an audit marker even
                            # though the folder is gone.
                            db_manager.update_production_status(case_folder, prod_name, 'aborted')
                            try:
                                shutil.rmtree(prod_path)
                            except Exception as _rm_err:
                                st.warning(f"Could not clean up partial production folder: {_rm_err}")
                            for key in ['prod_pass1', 'prod_pass1_complete', 'prod_finalized']:
                                st.session_state.pop(key, None)
                            st.session_state.pop('_prod_cancel', None)
                            st.warning(
                                f"Production '{prod_name}' cancelled during imaging after {_prod_completed_count}/{len(df)} documents. "
                                f"The partial volume has been deleted. You can re-run the production when ready."
                            )
                            time.sleep(2)
                            st.rerun()

                        # ── Pass 1 complete — store results and transition to checkpoint ──
                        lottie_placeholder.empty()
                        st.session_state.pop('_prod_cancel', None)

                        # Flip production_runs.status from 'in_progress' to
                        # 'pass1_complete' so the orphan detector knows this
                        # production is legitimately awaiting Finalize.
                        db_manager.update_production_status(case_folder, prod_name, 'pass1_complete')

                        db_manager.log_audit(case_folder, "PRODUCTION_PASS1_COMPLETE",
                            username=_prod_username, module="Production",
                            details=json.dumps({
                                "volume": prod_name,
                                "total": len(results_list),
                                "imaged": sum(1 for r in results_list if r['category'] == 'Imaged'),
                                "expected_natives": sum(1 for r in results_list if r['category'] == 'Expected Native'),
                                "failures": sum(1 for r in results_list if r['category'] == 'Imaging Failure'),
                                "withheld": sum(1 for r in results_list if r['category'] == 'Withheld'),
                                "workers": _pool_workers if prod_format != "Native Only" else 1,
                                "elapsed_seconds": round(_pass1_elapsed, 1),
                            }))

                        st.session_state['prod_pass1'] = {
                            'prod_name': prod_name,
                            'prod_path': prod_path,
                            'prod_format': prod_format,
                            'prefix': prefix,
                            'start_num': start_num,
                            'bates_padding': bates_padding,
                            'stamp_enabled': stamp_enabled,
                            'stamp_position': stamp_position,
                            'stamp_color': stamp_color,
                            'stamp_font_size': stamp_font_size,
                            'endorsement_text': endorsement_text,
                            'case_folder': case_folder,
                            'username': _prod_username,
                            'doc_rows': df.to_dict('records'),
                            'results': results_list,
                            'withhold_cns': list(_withhold_cns),
                            'imaging_workers': imaging_workers,
                            'prod_mode': prod_mode,
                            'sort_by_folder': sort_by_folder,
                            'sort_mode': sort_mode,
                            'skip_redaction_burn': skip_redaction_burn,
                            'pl_profile_name': _prod_pl_profile_name,
                        }
                        st.session_state['prod_pass1_complete'] = True
                        st.session_state['prod_finalized'] = False
                        st.rerun()

        with col2:
            st.header("Previous Productions")
            if os.path.exists(case_folder):
                prods = get_production_sets(case_folder)
                if prods:
                    for p in prods:
                        st.markdown(f"📁 **{p}**")
                else:
                    st.info("No productions found.")

        # --------------------------------------------------------------------------
        # BATES RANGE GAP DETECTION
        # --------------------------------------------------------------------------
        with st.expander("🔍 Validate Production — Bates Range Gap Detection", expanded=False):
            st.markdown(
                "Scans all produced documents for sequence discontinuities within each production volume. "
                "A gap means one document's EndBates + 1 does not equal the next document's BegBates."
            )
            if st.button("Run Gap Analysis", key="gap_run"):
                import re as _re

                def _bates_num(bates_str):
                    """Extract the trailing integer from a Bates string like 'ABC-000042' → 42."""
                    if not bates_str:
                        return None
                    m = _re.search(r'(\d+)\s*$', str(bates_str))
                    return int(m.group(1)) if m else None

                _gap_rows = db_manager.get_production_gap_report(case_folder)

                # Group by volume
                from collections import defaultdict as _dd
                _vol_docs = _dd(list)
                for _r in _gap_rows:
                    _vol_docs[_r['production_volume']].append({
                        'cn': _r['control_number'],
                        'begdoc': _r['begdoc'],
                        'enddoc': _r['enddoc'],
                        'beg_num': _bates_num(_r['begdoc']),
                        'end_num': _bates_num(_r['enddoc']),
                    })

                _gap_records = []
                for _vol, _docs in sorted(_vol_docs.items()):
                    # Sort by numeric beg
                    _docs_sorted = sorted(
                        [d for d in _docs if d['beg_num'] is not None],
                        key=lambda d: d['beg_num']
                    )
                    for _i in range(len(_docs_sorted) - 1):
                        _curr = _docs_sorted[_i]
                        _next = _docs_sorted[_i + 1]
                        if _curr['end_num'] is not None and _next['beg_num'] is not None:
                            _expected_next = _curr['end_num'] + 1
                            if _next['beg_num'] != _expected_next:
                                _gap_records.append({
                                    'Volume': _vol,
                                    'Gap Start': _curr['enddoc'],
                                    'Gap End': _next['begdoc'],
                                    'Gap Size': _next['beg_num'] - _curr['end_num'] - 1,
                                    'Before CN': _curr['cn'],
                                    'After CN': _next['cn'],
                                })

                if not _gap_records:
                    st.success("✅ No Bates range gaps detected across all production volumes.")
                else:
                    _gap_df = pd.DataFrame(_gap_records)
                    st.warning(f"⚠️ {len(_gap_records)} gap(s) detected:")
                    st.dataframe(_gap_df, width='stretch', hide_index=True)
                    _gap_csv = _gap_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "⬇️ Export Gap Report (CSV)",
                        data=_gap_csv,
                        file_name="bates_gap_report.csv",
                        mime="text/csv",
                        key="gap_download"
                    )

            else:
                st.caption("Click **Run Gap Analysis** to scan all produced documents for Bates sequence discontinuities.")


    # ══════════════════════════════════════════════════════════════════════════
    # MAIN UI — Checkpoint gate or normal config
    # ══════════════════════════════════════════════════════════════════════════
    # Single if/elif/else chain: each branch renders its own UI without
    # halting the script, so tab_privlog below always renders. Closed-case
    # cases render a caption only — the three write-surfaces
    # (_render_outbound_production, _render_pass1_checkpoint,
    # _render_post_finalization) are skipped on closed+not-finalized.

    if _case_closed and not st.session_state.get('prod_finalized'):
        st.caption("🔒 New outbound productions cannot be started on closed cases. "
                   "The Privilege Log tab remains available for review.")
    elif st.session_state.get('prod_pass1_complete') and not st.session_state.get('prod_finalized'):
        _render_pass1_checkpoint()
    elif st.session_state.get('prod_finalized') and st.session_state.get('prod_pass1'):
        _render_post_finalization()
    else:
        _render_outbound_production()


# ==============================================================================
# TAB 2: PRIVILEGE LOG
# ==============================================================================
with tab_privlog:
    try:
        st.header("Privilege Log")
        st.caption(
            "QC privilege assertions, filter and review dispositions, configure export columns, "
            "and download the log — no production run required."
        )
        st.markdown("---")

        # ── Control Panel ─────────────────────────────────────────────────────
        _pl_ctrl_col, _pl_info_col = st.columns([1, 2])

        with _pl_ctrl_col:
            _pl_basis_options = [
                "Auto-detect from tags",
                "Attorney-Client Privilege",
                "Attorney Work Product",
                "Attorney-Client Privilege and Work Product",
                "Common Interest Privilege",
                "Custom (see Description column)",
            ]
            _pl_override_basis = st.selectbox(
                "Privilege Basis",
                options=_pl_basis_options,
                help="'Auto-detect' reads the document's tags. Select a basis to override all entries.",
                key="pl_override_basis"
            )
            _pl_include_needs_review = st.checkbox(
                "Include 'Needs Review' documents",
                value=False,
                help="Also include documents tagged 'Needs Review' as potentially privileged.",
                key="pl_include_needs_review"
            )
            _pl_refresh_btn = st.button("Refresh Privilege Log", type="primary", width='stretch', key="pl_refresh")

        with _pl_info_col:
            st.info(
                "**Tip:** This log reflects the current state of privilege tagging in the review database. "
                "Bates numbers are shown as `(not yet produced)` for documents that have not yet been produced. "
                "Data loads automatically on first visit. Click **Refresh** to update after tagging changes."
            )

        st.markdown("---")

        # ── Auto-Load + Refresh Logic ─────────────────────────────────────────
        _pl_cache_key = f"pl_data_{os.path.basename(case_folder)}"
        _pl_prev_needs_review = st.session_state.get('_pl_last_needs_review')
        _pl_prev_basis = st.session_state.get('_pl_last_basis')
        _pl_settings_changed = (
            _pl_prev_needs_review is not None and _pl_prev_needs_review != _pl_include_needs_review
        ) or (
            _pl_prev_basis is not None and _pl_prev_basis != _pl_override_basis
        )
        _pl_need_query = _pl_refresh_btn or (_pl_cache_key not in st.session_state) or _pl_settings_changed

        if _pl_need_query:
            _pl_conn = db_manager.get_connection(case_folder)

            # Source of truth: privilege_status column, not tag membership
            _pl_base_conditions = "d.privilege_status IN ('Withhold', 'Redact')"
            _pl_base_params = []

            if _pl_include_needs_review:
                _pl_base_conditions += " OR (d.tags LIKE '%Needs Review%' AND d.privilege_status IS NULL)"

            # permission: view_shell_documents
            _pl_shell_filter = ""
            if not auth_manager.has_permission('view_shell_documents'):
                _pl_shell_filter = " AND processing_status NOT IN ('Container_Scanned', 'Split_Source')"

            # Mandatory outbound source filter (beta-2.10 Commit 3): privilege
            # log is court-destined output. An inbound document with an
            # accidental privilege tag must never appear here — 26(g) hazard.
            # Aliased form because this query uses `FROM documents d`.
            _pl_outbound = db_manager.outbound_source_filter_sql('d')

            _pl_query = f"""
                SELECT d.control_number, d.begdoc, d.enddoc, d.file_name, d.custodian,
                       d.record_type, d.date_sent, d.email_from, d.email_to, d.email_cc,
                       d.email_subject, d.tags, d.privilege_status,
                       d.confidentiality_designation, d.source_collection, d.page_count,
                       d.reviewed_by,
                       (SELECT dn.note_text FROM document_notes dn
                        WHERE dn.control_number = d.control_number
                        ORDER BY dn.updated_at DESC LIMIT 1) AS reviewer_note,
                       (SELECT COUNT(DISTINCT rm.page_number) FROM redaction_marks rm
                        WHERE rm.control_number = d.control_number) AS redacted_page_count,
                       (SELECT GROUP_CONCAT(DISTINCT rm.page_number) FROM redaction_marks rm
                        WHERE rm.control_number = d.control_number) AS redacted_pages_list,
                       (SELECT GROUP_CONCAT(DISTINCT reason_val)
                        FROM (
                          SELECT json_extract(json_each.value, '$.reason') AS reason_val
                          FROM redaction_marks rm2, json_each(rm2.marks_json)
                          WHERE rm2.control_number = d.control_number
                            AND json_extract(json_each.value, '$.reason') IS NOT NULL
                            AND json_extract(json_each.value, '$.reason') != '[Redact — No Privilege Reason]'
                        )
                       ) AS mark_reasons
                FROM documents d
                WHERE ({_pl_base_conditions}){_pl_shell_filter} AND {_pl_outbound}
                ORDER BY d.date_sent ASC, d.control_number ASC
            """
            _pl_df = pd.read_sql_query(_pl_query, _pl_conn, params=_pl_base_params if _pl_base_params else None)
            _pl_conn.close()

            st.session_state[_pl_cache_key] = _pl_df
            st.session_state['_pl_last_needs_review'] = _pl_include_needs_review
            st.session_state['_pl_last_basis'] = _pl_override_basis

            # Audit log on query only (not on filter changes)
            db_manager.log_audit(case_folder, "PRIVILEGE_LOG_GENERATED",
                username=st.session_state.get('username', 'unknown'), module="Privilege Log",
                details=json.dumps({"total": len(_pl_df), "source": "auto-load" if not _pl_refresh_btn else "refresh"}))
        else:
            _pl_df = st.session_state[_pl_cache_key]

        if _pl_df.empty:
            st.warning("No privileged documents found. Set a privilege disposition (Withhold or Redact) in the Review module first.")
        else:
            # ── Build display DataFrame ─────────────────────────────────────
            _pl_priv_rows = []
            for _, r in _pl_df.iterrows():
                _pl_ps = r.get('privilege_status')
                if _pl_ps == 'Withhold':
                    _pl_disp = 'Withheld'
                    _pl_disp_key = 'Withhold'
                elif _pl_ps == 'Redact':
                    _pl_disp = 'Produced with redactions'
                    _pl_disp_key = 'Redact'
                else:
                    _pl_disp = 'Needs disposition'
                    _pl_disp_key = 'Needs Disposition'

                if _pl_disp_key == 'Withhold':
                    _pl_desc = f"Document withheld on grounds of privilege: {r['file_name']}"
                elif _pl_disp_key == 'Redact':
                    _pl_desc = f"Produced with redactions on grounds of privilege: {r['file_name']}"
                else:
                    _pl_desc = f"Privilege review pending: {r['file_name']}"

                _pl_row_data = {
                    'control_number':    r['control_number'],
                    'begdoc':            r['begdoc'] if pd.notna(r['begdoc']) else '(not yet produced)',
                    'enddoc':            r['enddoc'] if pd.notna(r['enddoc']) else '',
                    'privilege_basis':   _pl_resolve_privilege_basis(r, _pl_override_basis, r.get('mark_reasons')),
                    'disposition':       _pl_disp,
                    '_disposition_key':  _pl_disp_key,
                    'description':       _pl_desc,
                    'date_sent':         r['date_sent'] if pd.notna(r['date_sent']) else '',
                    'email_from':        r['email_from'] if pd.notna(r['email_from']) else '',
                    'email_to':          r['email_to'] if pd.notna(r['email_to']) else '',
                    'email_cc':          r['email_cc'] if pd.notna(r['email_cc']) else '',
                    'email_subject':     r['email_subject'] if pd.notna(r['email_subject']) else r['file_name'],
                    'custodian':         r['custodian'] if pd.notna(r['custodian']) else '',
                    'record_type':       r['record_type'] if pd.notna(r['record_type']) else '',
                    'file_name':         r['file_name'] if pd.notna(r['file_name']) else '',
                    'confidentiality':   r['confidentiality_designation'] if pd.notna(r['confidentiality_designation']) else '',
                    'source_collection': r['source_collection'] if pd.notna(r['source_collection']) else '',
                    'page_count':        int(r['page_count']) if pd.notna(r['page_count']) else None,
                    'redaction_pages':   int(r['redacted_page_count']) if pd.notna(r['redacted_page_count']) and r['redacted_page_count'] > 0 else None,
                    'redacted_pages_list': str(r['redacted_pages_list']) if pd.notna(r.get('redacted_pages_list')) else '',
                    'reviewer_notes':    r['reviewer_note'] if pd.notna(r['reviewer_note']) else '',
                }
                # Computed merge columns
                _pl_row_data['individuals'] = _pl_merge_individuals(_pl_row_data)
                _pl_row_data['bates_display'] = _pl_format_bates(_pl_row_data)

                _pl_priv_rows.append(_pl_row_data)

            _pl_all_df = pd.DataFrame(_pl_priv_rows)

            # ── Filter Bar ──────────────────────────────────────────────────
            st.subheader("Filters")
            _pl_f1, _pl_f2, _pl_f3, _pl_f4 = st.columns(4)

            _pl_disp_options = sorted(_pl_all_df['_disposition_key'].unique().tolist())
            _pl_disp_filter = _pl_f1.multiselect(
                "Disposition", _pl_disp_options, default=_pl_disp_options, key="pl_disp_filter"
            )

            _pl_basis_vals = sorted(_pl_all_df['privilege_basis'].unique().tolist())
            _pl_basis_filter = _pl_f2.multiselect(
                "Privilege Basis", _pl_basis_vals, default=_pl_basis_vals, key="pl_basis_filter"
            )

            _pl_cust_vals = sorted([c for c in _pl_all_df['custodian'].unique() if c])
            _pl_cust_filter = _pl_f3.multiselect(
                "Custodian", _pl_cust_vals, default=[], key="pl_cust_filter",
                placeholder="All custodians"
            )

            _pl_needs_only = _pl_f4.checkbox(
                "Show only Needs Disposition", value=False, key="pl_needs_only"
            )

            # Date range filter
            _pl_d1, _pl_d2, _pl_d_spacer = st.columns([1, 1, 2])
            _pl_date_start = _pl_d1.date_input("Date from", value=None, key="pl_date_start")
            _pl_date_end = _pl_d2.date_input("Date to", value=None, key="pl_date_end")

            # Apply filters
            _pl_filtered = _pl_all_df.copy()
            if _pl_needs_only:
                _pl_filtered = _pl_filtered[_pl_filtered['_disposition_key'] == 'Needs Disposition']
            elif _pl_disp_filter:
                _pl_filtered = _pl_filtered[_pl_filtered['_disposition_key'].isin(_pl_disp_filter)]
            if _pl_basis_filter and len(_pl_basis_filter) < len(_pl_basis_vals):
                _pl_filtered = _pl_filtered[_pl_filtered['privilege_basis'].isin(_pl_basis_filter)]
            if _pl_cust_filter:
                _pl_filtered = _pl_filtered[_pl_filtered['custodian'].isin(_pl_cust_filter)]
            if _pl_date_start:
                _pl_filtered = _pl_filtered[_pl_filtered['date_sent'] >= str(_pl_date_start)]
            if _pl_date_end:
                _pl_filtered = _pl_filtered[_pl_filtered['date_sent'] <= str(_pl_date_end)]

            st.markdown("---")

            # ── Metrics Bar ─────────────────────────────────────────────────
            _pl_m1, _pl_m2, _pl_m3, _pl_m4, _pl_m5, _pl_m6 = st.columns(6)
            _pl_m1.metric("Privileged Documents", len(_pl_filtered))
            _pl_withheld_n = (_pl_filtered['_disposition_key'] == 'Withhold').sum()
            _pl_m2.metric("Withheld", _pl_withheld_n)
            _pl_redacted_n = (_pl_filtered['_disposition_key'] == 'Redact').sum()
            _pl_m3.metric("Redact & Produce", _pl_redacted_n)
            _pl_needs_n = (_pl_filtered['_disposition_key'] == 'Needs Disposition').sum()
            _pl_m4.metric("Needs Disposition", _pl_needs_n)
            _pl_has_bates = (_pl_filtered['begdoc'] != '(not yet produced)').sum()
            _pl_m5.metric("With Bates", _pl_has_bates)
            _pl_m6.metric("Without Bates", len(_pl_filtered) - _pl_has_bates)

            if _pl_needs_n > 0:
                st.warning(f"**{_pl_needs_n} documents** tagged as privileged but lacking a Withhold/Redact disposition. "
                           "Set dispositions in the Review module before finalizing the privilege log.")

            # ── QC Grid ─────────────────────────────────────────────────────
            # Show all standard columns in the QC grid (grid is for review, picker is for export)
            _pl_qc_keys = [k for k in _PL_ALL_COL_KEYS if k in _pl_filtered.columns]
            _pl_grid_display = _pl_filtered[_pl_qc_keys].copy()
            _pl_grid_display.columns = [_PL_COL_KEY_TO_DISPLAY.get(c, c) for c in _pl_qc_keys]

            st.dataframe(
                _pl_grid_display,
                width='stretch', hide_index=True,
                column_config={
                    'Control Number': st.column_config.TextColumn(width='small'),
                    'BegBates': st.column_config.TextColumn(width='small'),
                    'EndBates': st.column_config.TextColumn(width='small'),
                    'Disposition': st.column_config.TextColumn(width='medium'),
                    'Privilege Basis': st.column_config.TextColumn(width='medium'),
                    'Description': st.column_config.TextColumn(width='large'),
                    'Reviewer Notes': st.column_config.TextColumn(width='large'),
                }
            )

            st.markdown("---")

            # ── Export Profiles ──────────────────────────────────────────────
            st.subheader("Export Profiles & Download")

            # Profile data model: stored in case_settings as privilege_log_profiles
            # Each profile: {"name": str, "columns": [col_keys], "headers": {col_key: custom_header}, "merges": [merge_keys]}
            _pl_profiles_raw = db_manager.get_case_setting(case_folder, 'privilege_log_profiles')
            _pl_profiles = {}
            if _pl_profiles_raw:
                try:
                    _pl_profiles = json.loads(_pl_profiles_raw)
                except (json.JSONDecodeError, TypeError):
                    _pl_profiles = {}

            # Migrate from old privilege_log_columns format if profiles are empty
            if not _pl_profiles:
                _pl_old_cols_raw = db_manager.get_case_setting(case_folder, 'privilege_log_columns')
                if _pl_old_cols_raw:
                    try:
                        _pl_old_cols = json.loads(_pl_old_cols_raw)
                        _pl_old_cols = [c for c in _pl_old_cols if c in _PL_ALL_COL_KEYS]
                        if _pl_old_cols:
                            _pl_profiles["Migrated"] = {
                                "columns": _pl_old_cols,
                                "headers": {},
                                "merges": []
                            }
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Always include EDRM Standard as a builtin
            if "EDRM Standard" not in _pl_profiles:
                _pl_profiles["EDRM Standard"] = {
                    "columns": _PL_DEFAULT_COLS[:],
                    "headers": {},
                    "merges": []
                }

            # Profile selector
            _pl_profile_names = list(_pl_profiles.keys())
            _pl_profile_col1, _pl_profile_col2 = st.columns([3, 1])

            with _pl_profile_col1:
                _pl_active_profile_name = st.selectbox(
                    "Export Profile",
                    options=_pl_profile_names,
                    key="pl_active_profile"
                )

            _pl_active_profile = _pl_profiles.get(_pl_active_profile_name, _pl_profiles.get("EDRM Standard", {}))
            _pl_profile_cols = _pl_active_profile.get("columns", _PL_DEFAULT_COLS)
            _pl_profile_headers = _pl_active_profile.get("headers", {})
            _pl_profile_merges = _pl_active_profile.get("merges", [])

            # Initialize or update column selection on profile switch
            _pl_valid_profile_cols = [c for c in _pl_profile_cols if c in _PL_ALL_COL_KEYS]
            _pl_prev_profile = st.session_state.get('_pl_last_profile')
            if _pl_prev_profile != _pl_active_profile_name or "pl_export_cols" not in st.session_state:
                st.session_state["pl_export_cols"] = _pl_valid_profile_cols
                _pl_co_key = f"pl_col_order_{os.path.basename(case_folder)}"
                st.session_state[_pl_co_key] = _pl_valid_profile_cols
            st.session_state['_pl_last_profile'] = _pl_active_profile_name

            # Column picker for active profile
            _pl_export_cols = st.multiselect(
                "Columns to include in export",
                options=_PL_ALL_COL_KEYS,
                format_func=lambda k: _PL_COL_KEY_TO_DISPLAY.get(k, k),
                key="pl_export_cols"
            )

            # ── Column Reorder (up/down arrows) ─────────────────────────
            _pl_co_key = f"pl_col_order_{os.path.basename(case_folder)}"
            _pl_col_order = st.session_state.get(_pl_co_key, list(_pl_export_cols))
            # Sync: remove deselected, append newly selected
            _pl_col_order = [c for c in _pl_col_order if c in _pl_export_cols]
            for c in _pl_export_cols:
                if c not in _pl_col_order:
                    _pl_col_order.append(c)
            st.session_state[_pl_co_key] = _pl_col_order

            if _pl_col_order:
                with st.expander("Column Order", expanded=False):
                    st.caption("Use arrows to reorder columns in the export.")
                    for _pl_oi, _pl_ok in enumerate(_pl_col_order):
                        _oc1, _oc2, _oc3 = st.columns([0.6, 0.6, 5])
                        with _oc1:
                            if st.button("⬆️", key=f"pl_up_{_pl_ok}", disabled=(_pl_oi == 0)):
                                _pl_col_order[_pl_oi], _pl_col_order[_pl_oi - 1] = _pl_col_order[_pl_oi - 1], _pl_col_order[_pl_oi]
                                st.session_state[_pl_co_key] = _pl_col_order
                                st.rerun()
                        with _oc2:
                            if st.button("⬇️", key=f"pl_dn_{_pl_ok}", disabled=(_pl_oi == len(_pl_col_order) - 1)):
                                _pl_col_order[_pl_oi], _pl_col_order[_pl_oi + 1] = _pl_col_order[_pl_oi + 1], _pl_col_order[_pl_oi]
                                st.session_state[_pl_co_key] = _pl_col_order
                                st.rerun()
                        with _oc3:
                            st.write(f"{_pl_oi + 1}. {_PL_COL_KEY_TO_DISPLAY.get(_pl_ok, _pl_ok)}")

            # ── Build Export DataFrame ───────────────────────────────────
            # Use _pl_col_order (ordered) instead of _pl_export_cols (unordered)
            _pl_export_ordered = _pl_col_order if _pl_col_order else _pl_export_cols
            _pl_export_keys = [c for c in _pl_export_ordered if c in _pl_filtered.columns]
            if _pl_export_keys:
                _pl_export_df = _pl_filtered[_pl_export_keys].copy()
                # Apply custom header renames from profile
                _pl_final_headers = {}
                for _ek in _pl_export_keys:
                    if _ek in _pl_profile_headers and _pl_profile_headers[_ek]:
                        _pl_final_headers[_ek] = _pl_profile_headers[_ek]
                    else:
                        _pl_final_headers[_ek] = _PL_COL_KEY_TO_DISPLAY.get(_ek, _ek)
                _pl_export_df.columns = [_pl_final_headers[c] for c in _pl_export_keys]
            else:
                _pl_export_df = pd.DataFrame()

            # ── Export Preview ───────────────────────────────────────────
            if not _pl_export_df.empty:
                st.subheader("Export Preview")
                st.caption(f"Showing first 10 of {len(_pl_export_df)} rows with current column settings.")
                st.dataframe(_pl_export_df.head(10), hide_index=True, use_container_width=True)

                # ── Download Buttons ────────────────────────────────────
                _pl_dl1, _pl_dl2 = st.columns(2)
                with _pl_dl1:
                    _pl_csv_bytes = _pl_export_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "⬇️ Download CSV",
                        data=_pl_csv_bytes,
                        file_name=f"PRIVILEGE_LOG_{os.path.basename(case_folder)}.csv",
                        mime="text/csv",
                        key="pl_dl_csv"
                    )
                with _pl_dl2:
                    try:
                        _pl_xl_buf = io.BytesIO()
                        _pl_export_df.to_excel(_pl_xl_buf, index=False, engine='openpyxl')
                        _pl_xl_buf.seek(0)
                        st.download_button(
                            "⬇️ Download Excel",
                            data=_pl_xl_buf.getvalue(),
                            file_name=f"PRIVILEGE_LOG_{os.path.basename(case_folder)}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="pl_dl_xlsx"
                        )
                    except Exception:
                        st.caption("Excel export requires openpyxl.")
            else:
                if _pl_export_cols:
                    st.info("Selected columns not found in data. Try different columns.")

            st.markdown("---")

            # ── Save / Profile Management ────────────────────────────────
            # permission: production (only managers/admins save config)
            _pl_can_save_config = auth_manager.has_permission('production') and not _case_closed

            if st.button("💾 Save Profile", disabled=not _pl_can_save_config,
                         key="pl_save_profile", help="Save current column selection and order to the active profile"):
                _pl_save_order = list(_pl_col_order) if _pl_col_order else list(_pl_export_cols)
                _pl_profiles[_pl_active_profile_name] = {
                    "columns": _pl_save_order,
                    "headers": _pl_profile_headers,
                    "merges": _pl_profile_merges
                }
                db_manager.save_case_setting(
                    case_folder, 'privilege_log_profiles', json.dumps(_pl_profiles)
                )
                st.success(f"Profile '{_pl_active_profile_name}' saved.")

            # New / Delete profile row
            _pl_new_col, _pl_del_col = st.columns(2)
            with _pl_new_col:
                _pl_new_name = st.text_input("New profile name", key="pl_new_profile_name", placeholder="Custom Profile")
                if st.button("Create Profile", disabled=not _pl_can_save_config, key="pl_create_profile"):
                    if _pl_new_name and _pl_new_name.strip():
                        _pl_profiles[_pl_new_name.strip()] = {
                            "columns": _pl_export_cols,
                            "headers": {},
                            "merges": []
                        }
                        db_manager.save_case_setting(
                            case_folder, 'privilege_log_profiles', json.dumps(_pl_profiles)
                        )
                        st.success(f"Profile '{_pl_new_name.strip()}' created.")
                        st.rerun()
            with _pl_del_col:
                # Only allow deleting non-builtin profiles
                _pl_deletable = [n for n in _pl_profiles if n != "EDRM Standard"]
                if _pl_deletable:
                    _pl_del_name = st.selectbox("Delete a profile", options=_pl_deletable, key="pl_del_profile_name")
                    if st.button("Delete Profile", disabled=not _pl_can_save_config, key="pl_delete_profile"):
                        if _pl_del_name in _pl_profiles:
                            del _pl_profiles[_pl_del_name]
                            db_manager.save_case_setting(
                                case_folder, 'privilege_log_profiles', json.dumps(_pl_profiles)
                            )
                            st.success(f"Profile '{_pl_del_name}' deleted.")
                            st.rerun()
                else:
                    st.caption("No custom profiles to delete.")

    except Exception as _pl_err:
        st.error(f"Privilege Log error: {_pl_err}")
        import traceback
        st.expander("Error details").code(traceback.format_exc())
