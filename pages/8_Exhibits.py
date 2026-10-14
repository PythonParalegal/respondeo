# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        8_Exhibits.py
# version:       1.1.4
# project:       Respondeo eDiscovery Platform
# project_ver:   2.9.0
# last_modified: 2026-04-15 14:30
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import os
import sqlite3
from datetime import datetime, date
from pathlib import Path
import ui_utils

import db_manager
import config
import auth_manager
import fitz  # PyMuPDF

try:
    import pdfkit
    PDFKIT_AVAILABLE = True
except ImportError:
    PDFKIT_AVAILABLE = False


def _generate_binder_pdf(case_folder, exhibit_set, exhibits_list):
    """
    Assemble a binder PDF: cover sheet -> index -> (divider + document) per exhibit.
    Returns (pdf_bytes, warnings_list).
    """
    wk_cfg = pdfkit.configuration(wkhtmltopdf=config.WKHTMLTOPDF_PATH)
    wk_opts = {
        'page-size': 'Letter',
        'orientation': 'Portrait',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': 'UTF-8',
        'no-outline': None,
        'enable-local-file-access': None,
    }
    warnings = []

    # ── Resolve produced PDF paths and page counts ────────────────────
    exhibit_pages = []  # list of (exhibit, pdf_path, page_count)
    for ex in exhibits_list:
        vol = ex.get('production_volume')
        begdoc = ex.get('begdoc')
        if not vol or not begdoc:
            warnings.append(f"Exhibit {ex['exhibit_number']}: no production record found")
            exhibit_pages.append((ex, None, 0))
            continue
        pdf_path = os.path.join(case_folder, "Productions", vol, "IMAGES", f"{begdoc}.pdf")
        if not os.path.exists(pdf_path):
            warnings.append(f"Exhibit {ex['exhibit_number']}: PDF not found at {pdf_path}")
            exhibit_pages.append((ex, None, 0))
            continue
        src = fitz.open(pdf_path)
        pc = src.page_count
        src.close()
        exhibit_pages.append((ex, pdf_path, pc))

    # ── Calculate page numbers for index ──────────────────────────────
    cover_pages = 1
    index_pages_est = max(1, (len(exhibits_list) + 24) // 25)
    binder_page = cover_pages + index_pages_est + 1  # +1 for first divider
    index_entries = []
    for ex, pdf_path, pc in exhibit_pages:
        bates = f"{ex.get('begdoc', '')} \u2013 {ex.get('enddoc', '')}" if ex.get('begdoc') else "N/A"
        index_entries.append({
            'exhibit_number': ex['exhibit_number'],
            'description': ex.get('description') or '',
            'bates': bates,
            'binder_page': binder_page,
        })
        binder_page += pc + 1  # document pages + next divider

    # ── Build case caption ────────────────────────────────────────────
    caption = exhibit_set.get('case_caption') or ''
    if not caption:
        _mp = db_manager.get_matter_profile(case_folder)
        caption = _mp.get('case_caption') or os.path.basename(case_folder)

    proc_date = exhibit_set.get('proceeding_date') or ''

    # ── Render Cover HTML ─────────────────────────────────────────────
    cover_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  @page {{ size: letter portrait; margin: 1in; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #000;
         text-align: center; padding-top: 2.5in; margin: 0; }}
  .rule {{ width: 40%; height: 1px; background: #000; margin: 28px auto; }}
  .caption {{ font-size: 18pt; font-weight: bold; margin-bottom: 6px; }}
  .sub {{ font-size: 12pt; color: #333; margin-bottom: 28px; }}
  .set-name {{ font-size: 15pt; font-weight: bold; margin-bottom: 4px; }}
  .date {{ font-size: 12pt; color: #333; margin-bottom: 28px; }}
  .label {{ font-size: 12pt; letter-spacing: 2px; text-transform: uppercase; }}
  .conf {{ font-size: 9pt; color: #555; font-style: italic; margin-top: 120px; }}
</style></head><body>
  <div class="caption">{caption}</div>
  <div class="rule"></div>
  <div class="set-name">{exhibit_set['set_name']}</div>
  <div class="date">{proc_date}</div>
  <div class="rule"></div>
  <div class="label">Exhibit Binder</div>
  <div class="conf">Confidential \u2014 Subject to Protective Order</div>
</body></html>"""

    # ── Render Index HTML ─────────────────────────────────────────────
    index_rows = ""
    for ie in index_entries:
        index_rows += (
            f"<tr><td style='padding:5px 8px; font-weight:bold;'>{ie['exhibit_number']}</td>"
            f"<td style='padding:5px 8px;'>{ie['description']}</td>"
            f"<td style='padding:5px 8px; font-family:Courier New,monospace; font-size:9pt;'>{ie['bates']}</td>"
            f"<td style='padding:5px 8px; text-align:right;'>{ie['binder_page']}</td></tr>\n"
        )

    index_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  @page {{ size: letter portrait; margin: 0.75in; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #000; margin: 0; padding: 0; }}
  h2 {{ text-align: center; font-size: 14pt; margin-bottom: 4px; }}
  .sub {{ text-align: center; font-size: 10pt; color: #555; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10pt; }}
  th {{ text-align: left; padding: 5px 8px; border-bottom: 2px solid #000; }}
  th:last-child {{ text-align: right; }}
  td {{ border-bottom: 1px solid #ccc; }}
</style></head><body>
  <h2>INDEX OF EXHIBITS</h2>
  <div class="sub">{exhibit_set['set_name']} \u2014 {proc_date}</div>
  <table>
    <thead><tr>
      <th style="width:10%;">Exhibit</th>
      <th style="width:45%;">Description</th>
      <th style="width:25%;">Bates Range</th>
      <th style="width:20%;">Binder Page</th>
    </tr></thead>
    <tbody>{index_rows}</tbody>
  </table>
</body></html>"""

    # ── Divider HTML template ─────────────────────────────────────────
    def _divider_html(ex, pc):
        bates = f"{ex.get('begdoc', '')} \u2013 {ex.get('enddoc', '')}" if ex.get('begdoc') else "N/A"
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  @page {{ size: letter portrait; margin: 1in; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #000;
         display: flex; flex-direction: column; justify-content: center;
         align-items: center; text-align: center; min-height: 8in;
         margin: 0; padding: 0; }}
  .set {{ font-size: 10pt; letter-spacing: 2px; text-transform: uppercase;
          color: #555; margin-bottom: 24px; }}
  .rule {{ width: 60px; height: 2px; background: #000; margin-bottom: 24px; }}
  .exnum {{ font-size: 28pt; font-weight: bold; margin-bottom: 12px; }}
  .rule2 {{ width: 60px; height: 1px; background: #555; margin: 14px auto; }}
  .desc {{ font-size: 12pt; color: #333; max-width: 400px; line-height: 1.5; }}
  .bates {{ font-size: 10pt; font-family: 'Courier New', monospace; color: #555; margin-top: 12px; }}
  .pages {{ font-size: 9pt; color: #555; margin-top: 4px; }}
</style></head><body>
  <div class="set">{exhibit_set['set_name']}</div>
  <div class="rule"></div>
  <div class="exnum">Exhibit {ex['exhibit_number']}</div>
  <div class="rule2"></div>
  <div class="desc">{ex.get('description') or ''}</div>
  <div class="bates">{bates}</div>
  <div class="pages">{pc} page{'s' if pc != 1 else ''}</div>
</body></html>"""

    # ── Placeholder for missing documents ─────────────────────────────
    def _placeholder_html(ex):
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  @page {{ size: letter portrait; margin: 1in; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #000;
         display: flex; flex-direction: column; justify-content: center;
         align-items: center; text-align: center; min-height: 8in; margin: 0; }}
</style></head><body>
  <div style="font-size:16pt; font-weight:bold; margin-bottom:16px;">
    Exhibit {ex['exhibit_number']}</div>
  <div style="font-size:12pt; color:#555;">Document Not Available</div>
  <div style="font-size:10pt; color:#888; margin-top:8px;">
    {ex['control_number']}</div>
</body></html>"""

    # ── Assemble PDF ──────────────────────────────────────────────────
    merged = fitz.open()
    try:
        # Cover
        cover_bytes = pdfkit.from_string(cover_html, False, options=wk_opts, configuration=wk_cfg)
        cover_doc = fitz.open(stream=cover_bytes, filetype="pdf")
        merged.insert_pdf(cover_doc)
        cover_doc.close()

        # Index
        index_bytes = pdfkit.from_string(index_html, False, options=wk_opts, configuration=wk_cfg)
        index_doc = fitz.open(stream=index_bytes, filetype="pdf")
        merged.insert_pdf(index_doc)
        index_doc.close()

        # Exhibits
        for ex, pdf_path, pc in exhibit_pages:
            # Divider
            div_bytes = pdfkit.from_string(
                _divider_html(ex, pc if pdf_path else 0),
                False, options=wk_opts, configuration=wk_cfg
            )
            div_doc = fitz.open(stream=div_bytes, filetype="pdf")
            merged.insert_pdf(div_doc)
            div_doc.close()

            # Document (or placeholder)
            if pdf_path:
                src = fitz.open(pdf_path)
                merged.insert_pdf(src)
                src.close()
            else:
                ph_bytes = pdfkit.from_string(
                    _placeholder_html(ex), False, options=wk_opts, configuration=wk_cfg
                )
                ph_doc = fitz.open(stream=ph_bytes, filetype="pdf")
                merged.insert_pdf(ph_doc)
                ph_doc.close()

        return merged.tobytes(), warnings
    finally:
        merged.close()


_ASSETS = Path(__file__).resolve().parent.parent / "assets"
st.set_page_config(page_title="Respondeo | Exhibits", layout="wide", page_icon=str(_ASSETS / "favicon.png"))
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()
st.title("Module 7: Exhibits")

# ── Auth & Case Gate ─────────────────────────────────────────────────────────
# permission: view_exhibits
if not auth_manager.check_login(): st.stop()

_username = st.session_state.get("username", "unknown")
auth_manager.require_permission('view_exhibits')
auth_manager.show_user_info()

case_folder = st.session_state.get("current_case_folder")
if not case_folder:
    st.info("Select a case from the Home page first.")
    st.stop()

_case_closed = db_manager.get_case_status(case_folder) == 'Closed'
_can_manage_sets = auth_manager.has_permission('manage_exhibit_sets')
_can_manage_exhibits = auth_manager.has_permission('manage_exhibits')
_can_export = auth_manager.has_permission('export_exhibit_binder')

# ── Exhibit Set Selector ─────────────────────────────────────────────────────
exhibit_sets = db_manager.get_exhibit_sets(case_folder)
set_names = [es['set_name'] for es in exhibit_sets]

col_sel, col_new = st.columns([3, 1])

with col_sel:
    if set_names:
        selected_set_name = st.selectbox(
            "Exhibit Set",
            options=set_names,
            key="exhibits_set_selector",
        )
        selected_set = next(es for es in exhibit_sets if es['set_name'] == selected_set_name)
    else:
        st.info("No exhibit sets yet. Create one below to get started.")
        selected_set = None

# ── Create New Set (Manager+) ────────────────────────────────────────────────
# permission: manage_exhibit_sets
if _can_manage_sets and not _case_closed:
    with col_new:
        st.write("")  # vertical spacer
        _show_create = st.button("New Set", use_container_width=True)

    if _show_create or not set_names:
        with st.expander("Create Exhibit Set", expanded=(not set_names)):
            _new_name = st.text_input("Set Name", placeholder="e.g., Deposition of John Smith")
            _type_col, _date_col = st.columns(2)
            with _type_col:
                _new_type = st.selectbox("Type", ["Deposition", "Motion", "Hearing", "Trial"])
            with _date_col:
                _new_date = st.date_input("Proceeding Date", value=None)
            _new_caption = st.text_input(
                "Case Caption Override (optional)",
                placeholder="Leave blank to use case-level caption",
            )
            if st.button("Create Set"):
                if not _new_name.strip():
                    st.error("Set name is required.")
                else:
                    try:
                        _new_id = db_manager.create_exhibit_set(
                            case_folder, _new_name.strip(), _new_type,
                            _new_date.isoformat() if _new_date else None,
                            _new_caption.strip() or None, _username
                        )
                        try:
                            db_manager.log_audit(
                                case_folder, "EXHIBIT_SET_CREATED",
                                username=_username, module="Exhibits",
                                details=f"Created set: {_new_name.strip()} ({_new_type})"
                            )
                        except Exception:
                            pass
                        st.success(f"Created exhibit set: {_new_name.strip()}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("An exhibit set with this name already exists.")

if not selected_set:
    st.stop()

# ── Set Details (Manager+ can edit) ──────────────────────────────────────────
# permission: manage_exhibit_sets
with st.expander("Set Details"):
    if _can_manage_sets and not _case_closed:
        # Sync widget values before render to prevent stale session state
        # from overriding programmatic value= / index= parameters (M-7 fix).
        st.session_state["edit_set_name"] = selected_set['set_name']
        _edit_name = st.text_input("Set Name", key="edit_set_name")
        _e_col1, _e_col2 = st.columns(2)
        with _e_col1:
            _type_options = ["Deposition", "Motion", "Hearing", "Trial"]
            st.session_state["edit_set_type"] = selected_set['set_type'] if selected_set['set_type'] in _type_options else _type_options[0]
            _edit_type = st.selectbox("Type", _type_options, key="edit_set_type")
        with _e_col2:
            _existing_date = None
            if selected_set.get('proceeding_date'):
                try:
                    _existing_date = date.fromisoformat(selected_set['proceeding_date'])
                except ValueError:
                    pass
            if _existing_date is not None:
                st.session_state["edit_set_date"] = _existing_date
            _edit_date = st.date_input("Proceeding Date", key="edit_set_date")
        st.session_state["edit_set_caption"] = selected_set.get('case_caption') or ''
        _edit_caption = st.text_input(
            "Case Caption Override",
            key="edit_set_caption",
        )

        _btn_col1, _btn_col2 = st.columns([1, 1])
        with _btn_col1:
            if st.button("Save Changes", key="save_set_details"):
                db_manager.update_exhibit_set(
                    case_folder, selected_set['id'],
                    set_name=_edit_name.strip(),
                    set_type=_edit_type,
                    proceeding_date=_edit_date.isoformat() if _edit_date else None,
                    case_caption=_edit_caption.strip() or None,
                )
                st.success("Set details updated.")
                st.rerun()
        with _btn_col2:
            if st.button("Delete Set", type="secondary", key="delete_set_btn"):
                st.session_state['_confirm_delete_set'] = True

            if st.session_state.get('_confirm_delete_set'):
                st.warning(f"Delete **{selected_set['set_name']}** and all its exhibits?")
                _dc1, _dc2 = st.columns(2)
                if _dc1.button("Yes, Delete", key="confirm_delete_yes"):
                    db_manager.delete_exhibit_set(case_folder, selected_set['id'])
                    try:
                        db_manager.log_audit(
                            case_folder, "EXHIBIT_SET_DELETED",
                            username=_username, module="Exhibits",
                            details=f"Deleted set: {selected_set['set_name']}"
                        )
                    except Exception:
                        pass
                    st.session_state.pop('_confirm_delete_set', None)
                    st.success("Exhibit set deleted.")
                    st.rerun()
                if _dc2.button("Cancel", key="confirm_delete_no"):
                    st.session_state.pop('_confirm_delete_set', None)
                    st.rerun()
    else:
        st.write(f"**Name:** {selected_set['set_name']}")
        st.write(f"**Type:** {selected_set['set_type']}")
        st.write(f"**Proceeding Date:** {selected_set.get('proceeding_date') or 'Not set'}")
        if selected_set.get('case_caption'):
            st.write(f"**Case Caption:** {selected_set['case_caption']}")

# ── Exhibit List ─────────────────────────────────────────────────────────────
st.subheader(f"Exhibits — {selected_set['set_name']}")

exhibits = db_manager.get_exhibits(case_folder, selected_set['id'])

if exhibits:
    for idx, ex in enumerate(exhibits):
        _bates = f"{ex.get('begdoc', '')} – {ex.get('enddoc', '')}" if ex.get('begdoc') else "N/A"
        _cols = st.columns([0.5, 1, 2.5, 2, 0.5, 1, 1])
        _cols[0].write(f"**{idx + 1}**")
        _cols[1].write(f"**{ex['exhibit_number']}**")
        _cols[2].write(ex.get('description') or '')
        _cols[3].code(_bates, language=None)
        _cols[4].write(str(ex.get('prod_page_count') or ex.get('page_count', '')))
        _cols[5].write(ex.get('custodian') or '')

        # Action buttons (Manager+)
        # permission: manage_exhibits
        if _can_manage_exhibits and not _case_closed:
            with _cols[6]:
                _act_col1, _act_col2, _act_col3 = st.columns(3)
                if idx > 0:
                    if _act_col1.button("↑", key=f"up_{ex['id']}", help="Move up"):
                        _ordered = [e['id'] for e in exhibits]
                        _ordered[idx], _ordered[idx - 1] = _ordered[idx - 1], _ordered[idx]
                        db_manager.reorder_exhibits(case_folder, selected_set['id'], _ordered)
                        st.rerun()
                if idx < len(exhibits) - 1:
                    if _act_col2.button("↓", key=f"dn_{ex['id']}", help="Move down"):
                        _ordered = [e['id'] for e in exhibits]
                        _ordered[idx], _ordered[idx + 1] = _ordered[idx + 1], _ordered[idx]
                        db_manager.reorder_exhibits(case_folder, selected_set['id'], _ordered)
                        st.rerun()
                if _act_col3.button("✕", key=f"rm_{ex['id']}", help="Remove"):
                    db_manager.remove_exhibit(case_folder, ex['id'])
                    try:
                        db_manager.log_audit(
                            case_folder, "EXHIBIT_REMOVED",
                            username=_username, control_number=ex['control_number'],
                            module="Exhibits",
                            details=f"Removed Exhibit {ex['exhibit_number']} from {selected_set['set_name']}"
                        )
                    except Exception:
                        pass
                    st.rerun()

        st.markdown("<hr style='margin:2px 0; border:none; border-top:1px solid #e2e8f0;'>",
                    unsafe_allow_html=True)
else:
    st.info("No exhibits in this set yet. Add documents using the section below or mark them during Review.")

# ── Add Document to Set (Manager+) ───────────────────────────────────────────
# permission: manage_exhibits
if _can_manage_exhibits and not _case_closed:
    with st.expander("Add Document to Set"):
        _search_q = st.text_input(
            "Search produced documents",
            placeholder="File name, custodian, or Bates number...",
            key="ex_doc_search",
        )
        if _search_q.strip():
            _existing_cns = {ex['control_number'] for ex in exhibits}
            conn = db_manager.get_connection(case_folder)
            try:
                # Build NOT IN clause safely
                if _existing_cns:
                    _not_in = f"AND d.control_number NOT IN ({','.join('?' * len(_existing_cns))})"
                    _not_in_params = list(_existing_cns)
                else:
                    _not_in = ""
                    _not_in_params = []

                _search_results = conn.execute(f"""  -- db_manager: exempt (dynamic query)
                    SELECT d.control_number, d.file_name, d.custodian,
                           dp.begdoc, dp.enddoc, dp.page_count
                    FROM documents d
                    JOIN document_productions dp ON d.control_number = dp.control_number
                        AND dp.produced_at = (
                            SELECT MAX(dp2.produced_at)
                            FROM document_productions dp2
                            WHERE dp2.control_number = d.control_number
                        )
                    WHERE 1=1 {_not_in}
                      AND (d.file_name LIKE ? OR d.custodian LIKE ?
                           OR dp.begdoc LIKE ? OR d.control_number LIKE ?)
                    LIMIT 25
                """, (
                    *_not_in_params,
                    f"%{_search_q}%", f"%{_search_q}%",
                    f"%{_search_q}%", f"%{_search_q}%",
                )).fetchall()
            finally:
                conn.close()

            if _search_results:
                for _sr in _search_results:
                    _sr_dict = dict(_sr)
                    _sr_bates = f"{_sr_dict.get('begdoc', '')} – {_sr_dict.get('enddoc', '')}"
                    _sr_cols = st.columns([2, 2, 2, 1.5, 1.5])
                    _sr_cols[0].write(_sr_dict['control_number'])
                    _sr_cols[1].write(_sr_dict.get('file_name', ''))
                    _sr_cols[2].code(_sr_bates, language=None)
                    _add_num = _sr_cols[3].text_input(
                        "Ex #", key=f"add_num_{_sr_dict['control_number']}",
                        label_visibility="collapsed", placeholder="Ex #",
                    )
                    if _sr_cols[4].button("Add", key=f"add_btn_{_sr_dict['control_number']}"):
                        if not _add_num.strip():
                            st.error("Exhibit number required.")
                        else:
                            _next_order = db_manager.get_next_sort_order(
                                case_folder, selected_set['id']
                            )
                            try:
                                db_manager.add_exhibit(
                                    case_folder, selected_set['id'],
                                    _sr_dict['control_number'], _add_num.strip(),
                                    '', _next_order, _username,
                                )
                                try:
                                    db_manager.log_audit(
                                        case_folder, "EXHIBIT_ADDED",
                                        username=_username,
                                        control_number=_sr_dict['control_number'],
                                        module="Exhibits",
                                        details=f"Exhibit {_add_num.strip()} in {selected_set['set_name']}"
                                    )
                                except Exception:
                                    pass
                                st.success(f"Added as Exhibit {_add_num.strip()}")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error(
                                    "Exhibit number already used in this set, "
                                    "or document already in this set."
                                )
            else:
                st.caption("No matching produced documents found.")

# ── Export Binder PDF (Manager+) ─────────────────────────────────────────────
# permission: export_exhibit_binder
if _can_export and not _case_closed and exhibits:
    st.markdown("---")
    st.subheader("Export")

    if not PDFKIT_AVAILABLE:
        st.error("pdfkit is not installed. Binder export requires pdfkit and wkhtmltopdf.")
    else:
        if st.button("Generate Binder PDF", type="primary"):
            with st.spinner("Assembling binder PDF..."):
                try:
                    pdf_bytes, warnings = _generate_binder_pdf(
                        case_folder, selected_set, exhibits
                    )
                    if warnings:
                        for w in warnings:
                            st.warning(w)
                    st.session_state['_binder_pdf'] = pdf_bytes
                    st.session_state['_binder_name'] = selected_set['set_name']
                    try:
                        db_manager.log_audit(
                            case_folder, "EXHIBIT_BINDER_EXPORTED",
                            username=_username, module="Exhibits",
                            details=f"Binder for {selected_set['set_name']} — {len(exhibits)} exhibits"
                        )
                    except Exception:
                        pass
                    st.success(
                        f"Binder ready — {len(exhibits)} exhibits, "
                        f"{len([w for w in warnings])} warnings."
                    )
                except Exception as e:
                    st.error(f"Binder generation failed: {e}")

        if st.session_state.get('_binder_pdf'):
            _safe_name = "".join(
                c if c.isalnum() or c in (' ', '-', '_') else '_'
                for c in st.session_state.get('_binder_name', 'Exhibit_Binder')
            ).strip().replace(' ', '_')
            st.download_button(
                "Download Binder PDF",
                data=st.session_state['_binder_pdf'],
                file_name=f"{_safe_name}_Exhibit_Binder.pdf",
                mime="application/pdf",
            )
