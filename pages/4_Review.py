# pyre-ignore-all-errors
# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        4_Review.py
# version:       1.35.0
# project:       Respondeo eDiscovery Platform
# project_ver:   2.16.0
# last_modified: 2026-06-01 12:00
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
import pandas as pd
import os
import sqlite3
import base64
import io
import time
import json
from datetime import datetime
from opensearchpy import OpenSearch
import db_manager
import config
import os_manager
import auth_manager
import neardupe_diff
import pdf_exporter

try:
    import universal_imager
    IMAGER_AVAILABLE = True
except ImportError:
    IMAGER_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    from components.redaction_viewer import redaction_viewer
    VIEWER_AVAILABLE = True
except ImportError:
    VIEWER_AVAILABLE = False

import logging
_reimage_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Inbound-document predicate (beta-2.10 Commit 4)
# ---------------------------------------------------------------------------

def _is_inbound_doc(source_party):
    """Return True when a document's `source_party` indicates it came from an
    inbound production (opposing counsel's delivery to us).

    Used to gate privilege disposition writes in Review: Withhold/Redact/Clear
    writes on inbound docs are meaningless (they're already produced by the
    other side) and a confusion hazard. Tagging, notes, annotations, redaction
    marks, category assignment, custodian assignment, and confidentiality
    designation all continue to apply to inbound docs — scope is narrow on
    purpose.

    Mirrors the predicate used by db_manager.OUTBOUND_SOURCE_FILTER_SQL
    (beta-2.10 Commit 3) at the SQL layer:
        (source_party = 'Internal' OR source_party IS NULL)  → custodial
        otherwise                                            → inbound
    """
    if source_party is None:
        return False
    sp = str(source_party).strip()
    if not sp:
        return False
    return sp != 'Internal'


# ---------------------------------------------------------------------------
# Re-image helper — regenerate PDF from original source email
# ---------------------------------------------------------------------------

def _reimage_document(case_folder, control_number, username):
    """
    Re-images a single document from its original source file.

    This is a FULL RESET operation:
    1. Deletes Processed/{cn}.pdf (the bad image)
    2. Deletes Reviewed/{cn}.pdf (invalidated review markings)
    3. Resets tags, reviewed_by, reviewed_at, privilege_status in the database
    4. Re-runs image_document() on the original source file from full_path
    5. Logs a detailed audit entry

    Returns (success: bool, message: str)
    """
    try:
        conn = db_manager.get_connection(case_folder)
        row_ri = conn.execute(  # db_manager: exempt (review loop)
            "SELECT full_path, file_extension, tags, reviewed_by FROM documents WHERE control_number = ?",
            (control_number,)
        ).fetchone()

        if not row_ri:
            conn.close()
            return False, f"Document {control_number} not found in database."

        source_path = row_ri['full_path']
        ext = row_ri['file_extension']
        old_tags = row_ri['tags'] or ''
        old_reviewed_by = row_ri['reviewed_by'] or ''

        if ext.lower() not in ('.msg', '.eml'):
            conn.close()
            return False, f"Re-image is only supported for email files (.msg/.eml). This document is {ext}."

        if not os.path.exists(source_path):
            conn.close()
            return False, f"Original source file not found: {source_path}"

        processed_pdf = os.path.join(case_folder, "Processed", f"{control_number}.pdf")
        reviewed_pdf = os.path.join(case_folder, "Reviewed", f"{control_number}.pdf")

        had_reviewed_pdf = os.path.exists(reviewed_pdf)
        had_processed_pdf = os.path.exists(processed_pdf)

        if had_processed_pdf:
            try:
                os.remove(processed_pdf)
            except OSError as e:
                conn.close()
                return False, f"Failed to delete processed PDF: {e}"

        if had_reviewed_pdf:
            try:
                os.remove(reviewed_pdf)
            except OSError as e:
                _reimage_logger.warning("Failed to delete reviewed PDF for %s during re-image: %s", control_number, e)

        # Preserve system-computed tags (unaffected by re-imaging).
        # Tags are stored semicolon-separated (e.g. "Inclusive; Thread-Suppressed;")
        _SYSTEM_TAGS = {'Inclusive', 'Thread-Suppressed', 'NearDupe-Suppressed', 'Inclusive-Attachments'}
        _all_tags = [t.strip().rstrip(';').strip() for t in old_tags.replace(',', ';').split(';') if t.strip()] if old_tags else []
        _kept_tags = [t for t in _all_tags if t in _SYSTEM_TAGS]
        _new_tags = '; '.join(t + ';' for t in _kept_tags) if _kept_tags else None

        conn.execute(  # db_manager: exempt (review loop)
            """
            UPDATE documents
            SET tags = ?,
                reviewed_by = NULL,
                reviewed_at = NULL
            WHERE control_number = ?
            """, (_new_tags, control_number))

        try:
            conn.execute(  # db_manager: exempt (review loop)
                """
                UPDATE documents SET privilege_status = NULL
                WHERE control_number = ? AND privilege_status IS NOT NULL
                """, (control_number,))
        except Exception:
            pass

        try:
            conn.execute(  # db_manager: exempt (review loop)
                """
                UPDATE documents SET confidentiality_designation = NULL
                WHERE control_number = ? AND confidentiality_designation IS NOT NULL
                """, (control_number,))
        except Exception:
            pass

        conn.commit()
        conn.close()

        if not IMAGER_AVAILABLE:
            return False, "Universal imager is not available. Cannot re-image."

        success, err = universal_imager.image_document(source_path, processed_pdf)

        if not success:
            return False, f"Re-imaging failed: {err}"

        audit_details = json.dumps({
            "source_file": source_path,
            "old_tags": old_tags,
            "old_reviewed_by": old_reviewed_by,
            "reviewed_pdf_deleted": had_reviewed_pdf,
            "processed_pdf_deleted": had_processed_pdf,
            "reason": "Manual re-image triggered from Review module",
        })
        db_manager.log_audit(
            case_folder, "DOCUMENT_REIMAGED",
            username=username,
            control_number=control_number,
            module="Review",
            details=audit_details
        )

        return True, "Document re-imaged successfully. All tags and review state have been reset."

    except Exception as e:
        _reimage_logger.error("Re-image failed for %s: %s", control_number, e)
        return False, f"Re-image error: {e}"


# ---------------------------------------------------------------------------
# PDF naming field discovery — cached per case, refreshed every 60 s
# ---------------------------------------------------------------------------

# Curated common fields shown first in the naming dropdown.
_PDF_NAMING_COMMON = [
    "control_number", "file_name", "begdoc", "begdoc_range",
    "email_subject", "custodian", "date_sent",
]

# System/internal columns never surfaced in the naming dropdown.
_PDF_NAMING_EXCLUDE = {
    "id", "full_path", "original_path", "processing_status", "opensearch_id",
    "has_text", "filevine_doc_id", "filevine_collection_id", "sync_status",
    "sync_timestamp", "analytics_run_date", "content_hash", "dynamic_metadata",
}
_PDF_NAMING_EXCLUDE.update(_PDF_NAMING_COMMON)  # common list already added above

# Friendly display labels for common fields.
_PDF_NAMING_LABELS = {
    "control_number": "Control Number",
    "file_name":      "File Name",
    "begdoc":         "Beg Doc (Bates)",
    "begdoc_range":   "Beg–End Doc Range (Bates)",
    "email_subject":  "Email Subject",
    "custodian":      "Custodian",
    "date_sent":      "Date Sent",
}


@st.cache_data(ttl=60)
def _get_pdf_naming_options(case_folder: str) -> list:
    """
    Return the ordered list of naming field options for the PDF export dropdown.
    Order: curated common fields → additional DB columns → meta:<KEY> fields.
    Cached per case_folder with a 60-second TTL so dynamic_metadata changes surface quickly.
    """
    options = list(_PDF_NAMING_COMMON)
    try:
        conn = db_manager.get_connection(case_folder)
        # Append any DB columns not already covered
        for col_row in conn.execute("PRAGMA table_info(documents)").fetchall():  # db_manager: exempt (schema introspection)
            col_name = col_row[1]
            if col_name not in _PDF_NAMING_EXCLUDE and col_name not in options:
                options.append(col_name)
        # Discover dynamic_metadata keys across all documents in this case
        meta_rows = conn.execute(  # db_manager: exempt (dynamic query)
            "SELECT DISTINCT dynamic_metadata FROM documents "
            "WHERE dynamic_metadata IS NOT NULL AND dynamic_metadata != '{}'"
        ).fetchall()
        conn.close()
        meta_keys: set = set()
        for (meta_str,) in meta_rows:
            try:
                meta_keys.update(json.loads(meta_str).keys())
            except (json.JSONDecodeError, TypeError):
                pass
        for key in sorted(meta_keys):
            options.append(f"meta:{key}")
    except Exception:
        pass
    return options


def _fmt_pdf_naming(field: str) -> str:
    """Display label for the naming field selectbox."""
    if field in _PDF_NAMING_LABELS:
        return _PDF_NAMING_LABELS[field]
    if field.startswith("meta:"):
        return f"[meta] {field[5:]}"
    return field.replace("_", " ").title()


from pathlib import Path
_ASSETS = Path(__file__).resolve().parent.parent / "assets"
st.set_page_config(page_title="Respondeo | Review", layout="wide", page_icon=str(_ASSETS / "favicon.png"))

import ui_utils
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()

if not auth_manager.check_login(): st.stop()
# permission: review
auth_manager.require_permission('review')
auth_manager.show_user_info()

case_folder = st.session_state.get('current_case_folder')
if not case_folder:
    st.error("Please select a case in 'Home' first!")
    st.stop()


# --- CASE LIFECYCLE GATE ---
_case_status = db_manager.get_case_status(case_folder)
_case_closed = (_case_status == 'Closed')
if _case_closed:
    st.warning('🔒 This matter is closed. Write operations are disabled. '
               'Read-only access is available below.')


# --- OPENSEARCH CONNECTION ---

es, es_status = os_manager.get_os_client()

# Filevine subdomain — configured in config.py
fv_firm_subdomain = getattr(config, 'FILEVINE_SUBDOMAIN', "")

st.title("Module 3: Document Review 📝")

# --- Ensure DB schema is up-to-date (adds new columns if missing) ---
# (DC-1: schema setup must precede ANY page-level DB read. The near-dupe
#  cluster-review view-mode gate below reads near_dupe_clusters, which only
#  init_db creates — get_connection migrates audit_log columns only.)
db_manager.init_db(case_folder)

# ── Top-level view selector ───────────────────────────────────────────────────
# permission: str_run
_rv_view_options = ["📋 Review Grid"]
if auth_manager.has_permission('str_run'):
    _rv_view_options.append("📊 Search Term Reports")
# permission: tag — the read-only viewing surface is open to any reviewer; the
#  write actions inside (Same/Distinct/Approve/Re-open) are tag-gated. Surface the
#  option only when clusters exist — mirrors STR's "only when applicable" gate
#  (which keys off has_permission('str_run')). Schema is guaranteed present here
#  because init_db ran above (DC-1 ordering fix).
if db_manager.get_near_dupe_clusters(case_folder):
    _rv_view_options.append("🧬 Near-Dupe Clusters")

_rv_view_col, _ = st.columns([3, 5])
with _rv_view_col:
    _rv_page_view = st.radio(
        "View mode", _rv_view_options,
        horizontal=True, label_visibility="collapsed",
        key="_review_page_view"
    )

# ════════════════════════════════════════════════════════════════════════════
# NEAR-DUPE CLUSTER REVIEW SURFACE (S-1b C8b) — spec §11
# A top-level view mode (the "🧬 Near-Dupe Clusters" radio option above), rendered
# symmetric with the STR view: the branch after STR's st.stop() calls
# _render_neardupe_cluster_review_surface(...) then st.stop()s, so the Review Grid
# does not render beneath it. These definitions live HERE (before the view-mode
# branches) because Streamlit executes top-to-bottom and the branch below calls
# these names — defining them later (near the other page helpers) would NameError.
# ════════════════════════════════════════════════════════════════════════════
NEARDUPE_PANE_HEIGHT = 700

_ND_TAB_CSS = """
<style>
.nd-badge { display:inline-block; padding:2px 9px; border-radius:10px;
            font-size:0.78rem; font-weight:600; line-height:1.6; }
.nd-pend  { background:rgba(245,158,11,0.22); color:#fde68a; }
.nd-prog  { background:rgba(99,102,241,0.22); color:#c7d2fe; }
.nd-ready { background:rgba(34,197,94,0.22);  color:#bbf7d0; border:1px solid rgba(34,197,94,0.45); }
.nd-appr  { background:rgba(34,197,94,0.85);  color:#ffffff; }
.nd-lock  { background:rgba(148,163,184,0.22); color:#cbd5e1; }
.nd-fam   { background:rgba(245,158,11,0.16); color:#fde68a;
            border:1px solid rgba(245,158,11,0.40); padding:12px; border-radius:8px; }
</style>
"""


def _nd_cluster_badge(cluster):
    """Return (label, css_class) for the left-list status badge (spec §11.8).
    Denominator is the suppressible count (family-preserved members are exempt
    per §11.6), so a cluster whose only non-principals are family-preserved reads
    READY rather than being stuck at a fraction that can never close."""
    if cluster.get("review_status") == "approved":
        return ("APPR", "nd-appr")
    n = cluster.get("suppressible_count") or 0
    m = cluster.get("suppressible_decided") or 0
    if n == 0:
        return ("READY", "nd-ready")          # nothing suppressible to decide
    if m == 0:
        return ("PEND", "nd-pend")
    if m >= n:
        return (f"{n}/{n} ✓", "nd-ready")
    return (f"{m}/{n}", "nd-prog")


@st.cache_data(ttl=600)
def _nd_cached_diff_html(case_folder_path, cluster_id, member_cn, principal_cn, context_mode):
    """Cached side-by-side diff HTML, keyed by (case_folder, cluster_id, member_cn,
    context_mode). Fetches both docs' text via os_manager and renders through the
    pure builder. The pure builder (neardupe_diff) stays uncached so it remains
    trivially unit-testable (spec §1.4)."""
    p_text = os_manager.get_document_content(case_folder_path, principal_cn)
    m_text = os_manager.get_document_content(case_folder_path, member_cn)
    return neardupe_diff.build_side_by_side_diff_html(p_text, m_text, context=context_mode)


@st.dialog("Side-by-side diff", width="large")
def _nd_diff_dialog(diff_html):
    st.components.v1.html(diff_html, height=900, scrolling=True)


def _render_diff_pane(case_folder_path, cluster, member):
    """Diff pane (spec §11.3): context-collapsed by default; "Show full text"
    toggle flips to full; "⤢ Expand diff" opens an st.dialog modal. Toggle state
    carries into the modal (same context_mode)."""
    cid = cluster["cluster_id"]
    cn = member["member_cn"]
    _h1, _h2, _h3 = st.columns([2, 1.2, 1.1])
    with _h2:
        full = st.toggle("Show full text", key=f"nd_full_{cid}_{cn}")
    context_mode = not full
    diff_html = _nd_cached_diff_html(case_folder_path, cid, cn, cluster["principal_cn"], context_mode)
    with _h3:
        if st.button("⤢ Expand diff", key=f"nd_expand_{cid}_{cn}", width='stretch'):
            _nd_diff_dialog(diff_html)
    if not (diff_html or "").strip():
        st.info("No extracted text available for one or both documents (diff unavailable).")
        return
    st.components.v1.html(diff_html, height=NEARDUPE_PANE_HEIGHT, scrolling=True)


def _nd_next_to_review(others, current, count):
    """Next member index after `current` that still needs a reviewer decision —
    undecided AND suppressible (family-preserved are auto-exempt; overlap-locked
    members already carry a fanned-out decision, so decision!='undecided' excludes
    them). Falls back to current+1, then stays. Drives the Bug-2 auto-advance and
    realizes the §11.2/§11.4 skip-over-family/locked behavior."""
    for j in range(current + 1, count):
        m = others[j]
        if not m.get("family_preserved") and m.get("decision") == "undecided":
            return j
    return min(current + 1, count - 1)


def _render_member_action_panel(case_folder_path, cid, member, principal_elsewhere_cid,
                                can_write, others, idx):
    """Per-member action area — three visual states (spec §11.4). On a decision it
    records, toasts, and auto-advances to the next member needing review (Bug 2)."""
    cn = member["member_cn"]
    _idx_key = f"nd_midx_{cid}"
    _n = len(others)
    # State 2 — family-preserved: resolved panel, NO buttons (auto-exempt §11.6).
    if member.get("family_preserved"):
        st.markdown(
            "<div class='nd-fam'>🛡 <b>Family-preserved</b> ✓ &nbsp; Attachment context — "
            "no decision needed. Continue to the next member.</div>",
            unsafe_allow_html=True)
        st.caption("Family-attached documents are never auto-suppressed "
                   "(family-integrity-over-dedup) and are exempt from the approval gate.")
        return
    # State 3 — overlap-locked (decided elsewhere, or principal of another cluster).
    _locked_src = None
    decided_in = member.get("decided_in_cluster_id")
    if decided_in is not None and decided_in != cid:
        _locked_src = ("Decided in", decided_in, f"nd_open_src_{cid}_{decided_in}")
    elif principal_elsewhere_cid is not None:
        _locked_src = ("Principal of", principal_elsewhere_cid, f"nd_open_prin_{cid}_{principal_elsewhere_cid}")
    if _locked_src:
        _verb, _src, _btn_key = _locked_src
        st.markdown(f"<span class='nd-badge nd-lock'>🔒 {_verb} Cluster {_src}</span>",
                    unsafe_allow_html=True)
        _b1, _b2, _b3 = st.columns([1, 1, 1.4])
        _b1.button("✓ Same", key=f"nd_same_{cid}_{cn}", disabled=True, width='stretch')
        _b2.button("✗ Distinct", key=f"nd_dist_{cid}_{cn}", disabled=True, width='stretch')
        if _b3.button(f"↗ Open Cluster {_src}", key=_btn_key, width='stretch'):
            st.session_state["nd_selected_cluster_id"] = _src
            st.rerun()
        st.caption("This document's decision was authored in another cluster and propagates here "
                   "(it counts as decided for this cluster's approval).")
        return
    # State 1 — normal suppressible member.
    _fname = member.get('file_name') or cn
    st.markdown(f"**Decide on {_fname}:**")
    _c1, _c2 = st.columns(2)
    _same = _c1.button("✓ Same as principal", key=f"nd_same_{cid}_{cn}",
                       disabled=not can_write, width='stretch', type="secondary")
    _dist = _c2.button("✗ Distinct (keep in review)", key=f"nd_dist_{cid}_{cn}",
                       disabled=not can_write, width='stretch', type="secondary")
    if _same or _dist:
        _decision = "same" if _same else "distinct"
        db_manager.record_member_decision(case_folder_path, cid, cn, _decision,
                                           st.session_state.get('username', 'unknown'))
        st.toast(
            f"{_fname}: {'Same → suppressed' if _same else 'Distinct → kept in review'}",
            icon="✅" if _same else "↩️")
        # Auto-advance to the next member needing review (Bug 2). Sets the plain-int
        # nav state (NOT the picker widget key) so it's safe even though the picker
        # was already instantiated this run. App-scope rerun refreshes left badges.
        st.session_state[_idx_key] = _nd_next_to_review(others, idx, _n)
        st.rerun()
    if member.get("decision") in ("same", "distinct"):
        st.caption(f"Current decision: **{member['decision']}** "
                   + ("→ suppressed" if member["decision"] == "same" else "→ kept in review"))


def _render_cluster_attestation_row(case_folder_path, cluster, members, can_write):
    """Cluster attestation row — three states PENDING / READY / APPROVED, with the
    two-click Re-open affordance on APPROVED (spec §11.5 / §11.6)."""
    cid = cluster["cluster_id"]
    suppressible = [m for m in members if not m["is_principal"] and not m.get("family_preserved")]
    decided = [m for m in suppressible if m["decision"] in ("same", "distinct")]
    all_decided = len(decided) == len(suppressible)
    if cluster.get("review_status") == "approved":
        st.markdown(
            f"<span class='nd-badge nd-appr'>FINALIZED</span> &nbsp; ✅ "
            f"<b>{cluster.get('reviewed_by') or '—'}</b> · attested {cluster.get('reviewed_at') or '—'}",
            unsafe_allow_html=True)
        if cluster.get("attestation_note"):
            st.caption(f"Note: {cluster['attestation_note']}")
        _armed = st.session_state.get(f"nd_reopen_armed_{cid}", False)
        if not _armed:
            if st.button("↺ Re-open", key=f"nd_reopen_{cid}", disabled=not can_write,
                         help="Re-open this cluster to change a decision or re-attest. "
                              "The prior attestation is preserved in the audit log."):
                st.session_state[f"nd_reopen_armed_{cid}"] = True
                st.rerun()
        else:
            st.warning("Click again to confirm re-open — the prior attestation is snapshotted to the audit log.")
            _r1, _r2 = st.columns(2)
            if _r1.button("Confirm re-open", key=f"nd_reopen_confirm_{cid}",
                          type="primary", disabled=not can_write):
                db_manager.reopen_cluster(case_folder_path, cid,
                                          st.session_state.get('username', 'unknown'))
                st.session_state.pop(f"nd_reopen_armed_{cid}", None)
                st.rerun()
            if _r2.button("Cancel", key=f"nd_reopen_cancel_{cid}"):
                st.session_state.pop(f"nd_reopen_armed_{cid}", None)
                st.rerun()
        return
    if all_decided:
        st.markdown("<span class='nd-badge nd-ready'>READY</span>", unsafe_allow_html=True)
        _note = st.text_input("Attestation note (optional)", key=f"nd_note_{cid}",
                              placeholder="Attestation note (optional)")
        if st.button("✅ Finalize review", key=f"nd_approve_{cid}", type="primary",
                     disabled=not can_write,
                     help="Attest that you reviewed every suppressible member of this cluster. "
                          "Re-openable afterward — the attestation is recorded in the audit log."):
            db_manager.approve_cluster(case_folder_path, cid,
                                       st.session_state.get('username', 'unknown'), _note or None)
            st.toast("Cluster review finalized.", icon="✅")
            st.rerun()
    else:
        st.markdown("<span class='nd-badge nd-pend'>PENDING</span>", unsafe_allow_html=True)
        st.text_input("Attestation note", key=f"nd_note_{cid}", disabled=True,
                      placeholder="Decide all suppressible members to enable finalizing…")
        st.button("✅ Finalize review", key=f"nd_approve_{cid}", disabled=True)
        st.caption(f"{len(decided)}/{len(suppressible)} suppressible members decided.")


def _render_cluster_detail(case_folder_path, cluster, principal_map, can_write):
    """Right-pane detail. NOT a fragment: because the near-dupe branch st.stop()s
    before the Review Grid, a full rerun in this mode only re-executes the
    lightweight surface (not the 5700-line grid), so a fragment buys little while
    adding rerun-scope ambiguity to the member nav. Member nav (§11.2) → diff
    (§11.3) → per-member action (§11.4) → cluster attestation (§11.5). Diff HTML is
    cached, so re-rendering on each nav/toggle is cheap."""
    cid = cluster["cluster_id"]
    members = db_manager.get_cluster_members(case_folder_path, cid)
    principal = next((m for m in members if m["is_principal"]), None)
    others = [m for m in members if not m["is_principal"]]
    _sim_lo = cluster.get("sim_min") or 0
    _sim_hi = cluster.get("sim_max") or 0
    st.markdown(
        f"**Principal:** {(principal or {}).get('file_name') or cluster.get('principal_cn')} "
        f"&nbsp;·&nbsp; similarity {_sim_lo:.2f}–{_sim_hi:.2f} &nbsp;·&nbsp; {len(others)} member(s)")
    if not others:
        st.info("This cluster has no non-principal members to review.")
        _render_cluster_attestation_row(case_folder_path, cluster, members, can_write)
        return
    n = len(others)
    # Source of truth for the selected member index is a PLAIN session-state int
    # (NOT a widget key) — so Prev/Next/auto-advance can set it from anywhere
    # (including the decision handler, which renders after the picker) without the
    # "modify widget state after instantiation" exception.
    _idx_key = f"nd_midx_{cid}"
    idx = st.session_state.get(_idx_key, 0)
    if not isinstance(idx, int) or idx < 0 or idx >= n:
        idx = 0
        st.session_state[_idx_key] = 0

    _icons = {"same": "✓", "distinct": "✗", "undecided": "⏳"}

    def _label(i):
        m = others[i]
        if m.get("family_preserved"):
            tag = "🛡 family"
        elif m.get("decided_in_cluster_id") not in (None, cid):
            tag = f"🔒 C-{m.get('decided_in_cluster_id')}"
        else:
            tag = f"{_icons.get(m['decision'], '⏳')} {m['decision']}"
        # Position-prefix makes EVERY label unique even when many members share a
        # filename (common for near-dupe copies). Non-unique labels make
        # st.selectbox resolve a stored value to the wrong option (the Bug-1
        # "1→18 / jumps to last duplicate" defect — confirmed root cause).
        return f"{i + 1}. {m.get('file_name') or m['member_cn']} · {tag}"

    _nav1, _nav2, _nav3, _nav4 = st.columns([1.1, 3, 0.9, 1.1])
    if _nav1.button("◀ Prev", key=f"nd_prev_{cid}", disabled=(idx <= 0), width='stretch'):
        st.session_state[_idx_key] = idx - 1
        st.rerun()
    with _nav2:
        # Controlled selectbox: the key varies with idx so each value is a FRESH
        # widget that honors index=idx (defeats the M-7 index/key persistence trap
        # without external widget-key mutation). Unique labels (above) make the
        # value→option resolution unambiguous.
        _picked = st.selectbox("Member", list(range(n)), index=idx, format_func=_label,
                               key=f"nd_pick_{cid}_{idx}", label_visibility="collapsed")
    _nav3.markdown(f"<div style='text-align:center;padding-top:8px'>{idx + 1} / {n}</div>",
                   unsafe_allow_html=True)
    if _nav4.button("Next ▶", key=f"nd_next_{cid}", disabled=(idx >= n - 1), width='stretch'):
        st.session_state[_idx_key] = idx + 1
        st.rerun()
    if _picked != idx:  # user jumped via the picker
        st.session_state[_idx_key] = _picked
        st.rerun()
    member = others[idx]
    _render_diff_pane(case_folder_path, cluster, member)
    _principal_elsewhere = principal_map.get(member["member_cn"])
    if _principal_elsewhere == cid:
        _principal_elsewhere = None
    _render_member_action_panel(case_folder_path, cid, member, _principal_elsewhere,
                                can_write, others, idx)
    st.divider()
    _render_cluster_attestation_row(case_folder_path, cluster, members, can_write)


def _render_neardupe_cluster_review_surface(case_folder_path):
    """Entry point for the Near-Dupe Cluster Review view mode (spec §11). Master/
    detail: left = selectable cluster list with status badges; right = the
    fragment-scoped detail (diff + decisions + attestation)."""
    st.markdown(_ND_TAB_CSS, unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("🧬 Near-Dupe Cluster Review")
    st.caption("Review each near-dupe group against its principal. Confirm true duplicates "
               "(suppress) or mark distinct (keep in review). Nothing is suppressed until you confirm.")
    # permission: tag — viewing is open to any reviewer; write actions require 'tag'
    #  and an open case.
    _nd_can_write = auth_manager.has_permission('tag') and not _case_closed
    if _case_closed:
        st.warning("⚠️ This matter is closed — cluster decisions are read-only.")
    elif not auth_manager.has_permission('tag'):
        st.info("ℹ️ Review-only: you can inspect clusters and diffs, but confirming or attesting "
                "requires the 'tag' permission.")
    _clusters = db_manager.get_near_dupe_clusters(case_folder_path)
    if not _clusters:
        st.info("No near-dupe clusters staged. Run Near-Duplicate Detection in Analytics first.")
        return
    _principal_map = {c["principal_cn"]: c["cluster_id"] for c in _clusters}
    _collapsed = st.checkbox("◀ Collapse list", key="nd_list_collapsed",
                             help="Collapse the cluster list to give the diff more room.")
    _ratio = [0.05, 0.95] if _collapsed else [0.18, 0.82]
    _left, _right = st.columns(_ratio)
    with _left:
        _grid = pd.DataFrame([{
            "Cluster": c["cluster_id"],
            "Docs": c["member_count"],
            "Status": _nd_cluster_badge(c)[0],
        } for c in _clusters])
        _evt = st.dataframe(_grid, hide_index=True, width='stretch',
                            height=NEARDUPE_PANE_HEIGHT, on_select="rerun",
                            selection_mode="single-row", key="nd_cluster_select")
    _sel_rows = _evt.selection.rows if (_evt and _evt.selection) else []
    if _sel_rows and _sel_rows[0] < len(_clusters):
        # Honor a genuine dataframe selection change; a programmatic jump
        # (nd_selected_cluster_id set by an "Open Cluster X" button) is not clobbered
        # until the user clicks a different list row.
        if st.session_state.get("nd_last_df_row") != _sel_rows[0]:
            st.session_state["nd_selected_cluster_id"] = _clusters[_sel_rows[0]]["cluster_id"]
            st.session_state["nd_last_df_row"] = _sel_rows[0]
    _active = st.session_state.get("nd_selected_cluster_id")
    _sel_cluster = next((c for c in _clusters if c["cluster_id"] == _active), None)
    with _right:
        if _sel_cluster is None:
            st.info("Select a cluster on the left to review its members.")
        else:
            _render_cluster_detail(case_folder_path, _sel_cluster, _principal_map, _nd_can_write)


# =
# SEARCH TERM REPORTS VIEW — renders in full-page mode; st.stop() prevents the
# Review Grid from loading when this view is active.
# =
if _rv_page_view == "📊 Search Term Reports":
    st.markdown("---")
    st.caption(
        "Run a list of search terms against the document collection and generate a hit-count summary report. "
        "Use this to validate search terms before production, or to respond to opposing counsel's STR requests."
    )

    _str_es, _str_es_status = os_manager.get_os_client()
    _str_index_name = os_manager.get_index_name(case_folder)

    if not _str_es:
        st.error("❌ OpenSearch is offline. Please start OpenSearch from the Home page.")
        st.stop()

    st.subheader("1. Enter Search Terms")
    _str_input_col, _str_opt_col = st.columns([2, 1])

    with _str_input_col:
        _str_terms_text = st.text_area(
            "Search Terms (one per line)",
            height=200,
            placeholder="attorney-client\nprivileged\nwork product\nconfidential settlement\nfoo AND bar\n...",
            help="Supports OpenSearch query_string syntax: AND, OR, NOT, wildcards (*), phrases (\"exact phrase\"), fuzzy (term~)",
            key="str_terms_text"
        )
        _str_uploaded_file = st.file_uploader(
            "Or upload a .txt or .csv file of terms",
            type=["txt", "csv"],
            help="One term per line (.txt) or first column = term (.csv)",
            key="str_file_upload"
        )

    with _str_opt_col:
        st.markdown("**Options**")
        _STR_FIELD_OPTIONS = {
            "Document Text": "content",
            "File Name": "file_name",
            "Email Subject": "email_subject",
            "Email From": "email_from",
            "Email To": "email_to",
        }
        _str_field_label = st.selectbox(
            "Search field",
            list(_STR_FIELD_OPTIONS.keys()),
            help="Field to search. Document Text covers full extracted content.",
            key="str_search_field"
        )
        _str_search_field = _STR_FIELD_OPTIONS[_str_field_label]
        _str_case_sensitive = st.checkbox("Case-sensitive", value=False, key="str_case_sensitive")
        _str_include_suppressed = st.checkbox("Include Suppressed docs", value=False, key="str_include_suppressed")
        _str_max_hits_per_term = st.number_input(
            "Max hits to preview per term",
            min_value=5, max_value=500, value=50,
            help="Controls the preview grid. Hit COUNTS are always exact.",
            key="str_max_hits"
        )

    # Merge terms from text area and file upload
    _str_raw_terms = []
    if _str_terms_text:
        _str_raw_terms += [t.strip() for t in _str_terms_text.splitlines() if t.strip()]
    if _str_uploaded_file:
        try:
            if _str_uploaded_file.name.endswith('.csv'):
                _str_up_df = pd.read_csv(_str_uploaded_file, header=None)
                _str_raw_terms += _str_up_df.iloc[:, 0].dropna().astype(str).tolist()
            else:
                _str_content = _str_uploaded_file.read().decode('utf-8', errors='replace')
                _str_raw_terms += [t.strip() for t in _str_content.splitlines() if t.strip()]
        except Exception as e:
            st.warning(f"Could not read uploaded file: {e}")

    _str_seen = set()
    _str_terms = []
    for t in _str_raw_terms:
        if t.lower() not in _str_seen:
            _str_seen.add(t.lower())
            _str_terms.append(t)

    st.markdown("---")

    if st.button("🔍 Run Search Term Report", type="primary", disabled=not _str_terms, key="str_run_btn"):
        if not _str_terms:
            st.warning("Please enter at least one search term.")
            st.stop()

        _str_must_not_clauses = []
        if not _str_include_suppressed:
            _str_must_not_clauses.append({"wildcard": {"tags": "*Suppressed*"}})

        _str_progress = st.progress(0)
        _str_status_txt = st.empty()

        _str_results = []
        _str_hit_doc_rows = []

        _str_conn = db_manager.get_connection(case_folder)
        _str_vis_sql = (
            "SELECT control_number, file_name, custodian, tags, date_sent, date_created,"
            " begdoc, enddoc, record_type"
            " FROM documents"
        )
        # permission: doc_visibility — restrict STR metadata to visible documents only
        if _vis_mode == 'produced_only':
            _str_vis_sql += " WHERE begdoc IS NOT NULL AND begdoc != ''"
        _str_meta_df = pd.read_sql_query(_str_vis_sql, _str_conn)
        _str_conn.close()
        _str_meta_map = (
            _str_meta_df
            .dropna(subset=['control_number'])
            .drop_duplicates(subset=['control_number'], keep='first')
            .set_index('control_number')
            .to_dict('index')
        )
        # Build allowlist of visible control numbers for filtering OpenSearch hits
        _str_visible_cns = set(_str_meta_map.keys()) if _vis_mode == 'produced_only' else None

        for _str_idx, _str_term in enumerate(_str_terms):
            _str_status_txt.text(f"Running term {_str_idx+1}/{len(_str_terms)}: {_str_term}")

            _str_qs_term = _str_term if _str_case_sensitive else _str_term.lower()

            _str_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "query_string": {
                                    "query": _str_qs_term,
                                    "fields": [_str_search_field],
                                    "default_operator": "AND",
                                    "analyze_wildcard": True
                                }
                            }
                        ],
                        "must_not": _str_must_not_clauses
                    }
                },
                "size": int(_str_max_hits_per_term),
                "_source": ["control_number", "file_name", "content"]
            }

            try:
                _str_resp = _str_es.search(index=_str_index_name, body=_str_body)
                _str_total_hits = _str_resp['hits']['total']['value']
                _str_hits = _str_resp['hits']['hits']

                _str_visible_hit_count = 0
                for h in _str_hits:
                    _str_cn = h['_source'].get('control_number', h['_id'])
                    # permission: doc_visibility — skip hits for documents not visible to this user
                    if _str_visible_cns is not None and _str_cn not in _str_visible_cns:
                        continue
                    _str_visible_hit_count += 1
                    _str_meta = _str_meta_map.get(_str_cn, {})
                    # Use date_sent for emails, fall back to date_created for other doc types
                    _str_date = _str_meta.get('date_sent') or _str_meta.get('date_created') or ''
                    _str_hit_doc_rows.append({
                        'Term': _str_term,
                        'ControlNumber': _str_cn,
                        'BegBates': _str_meta.get('begdoc', ''),
                        'EndBates': _str_meta.get('enddoc', ''),
                        'FileName': _str_meta.get('file_name', h['_source'].get('file_name', '')),
                        'DocType': _str_meta.get('record_type', ''),
                        'Custodian': _str_meta.get('custodian', ''),
                        'Date': _str_date,
                        'Tags': _str_meta.get('tags', ''),
                    })

                # Use filtered count when doc_visibility restricts the view
                _str_report_hits = _str_visible_hit_count if _str_visible_cns is not None else _str_total_hits
                _str_results.append({
                    'Term': _str_term,
                    'Hit Count': _str_report_hits,
                    'Unique Docs (preview)': _str_visible_hit_count,
                    'Note': '' if _str_report_hits <= int(_str_max_hits_per_term) else f'Showing first {int(_str_max_hits_per_term)} of {_str_report_hits}'
                })

            except Exception as e:
                _str_results.append({
                    'Term': _str_term,
                    'Hit Count': 'ERROR',
                    'Unique Docs (preview)': 0,
                    'Note': str(e)
                })

            _str_progress.progress((_str_idx + 1) / len(_str_terms))

        _str_status_txt.empty()
        _str_progress.empty()

        st.session_state['str_summary'] = _str_results
        st.session_state['str_hit_docs'] = _str_hit_doc_rows
        st.session_state['str_terms_run'] = _str_terms

        db_manager.log_audit(case_folder, "SEARCH_EXECUTED",
            username=st.session_state.get('username', 'unknown'),
            module="STR", details=json.dumps({"terms": _str_terms}))

        import re as _re_str
        _str_safe_terms = [
            t for t in _str_terms
            if not _re_str.search(r'[\*\?\~\^\|]|\bAND\b|\bOR\b|\bNOT\b', t, _re_str.IGNORECASE)
        ]
        st.session_state['active_str_terms'] = _str_safe_terms

    # ── Results ────────────────────────────────────────────────────────────────
    if 'str_summary' in st.session_state and st.session_state['str_summary']:
        _str_summary_df = pd.DataFrame(st.session_state['str_summary'])
        _str_hit_df = pd.DataFrame(st.session_state['str_hit_docs'])
        _str_terms_run = st.session_state.get('str_terms_run', [])

        _str_total_unique_cns = _str_hit_df['ControlNumber'].nunique() if not _str_hit_df.empty else 0
        _str_total_hits_all = _str_summary_df[_str_summary_df['Hit Count'] != 'ERROR']['Hit Count'].astype(int).sum() if not _str_summary_df.empty else 0

        st.markdown("---")
        st.subheader("2. Results Summary")

        _str_m1, _str_m2, _str_m3, _str_m4 = st.columns(4)
        _str_m1.metric("Terms Run", len(_str_terms_run))
        _str_m2.metric("Total Hits (all terms)", f"{_str_total_hits_all:,}")
        _str_m3.metric("Unique Responsive Docs", f"{_str_total_unique_cns:,}")

        _str_active = st.session_state.get('active_str_terms', [])
        if _str_active:
            if _str_m4.button("🧹 Clear STR Highlights", width='stretch',
                              help="Remove persistent highlights from the Review viewer",
                              key="str_clear_highlights"):
                st.session_state.pop('active_str_terms', None)
                st.toast("STR highlights cleared from Review viewer.", icon="🧹")
                st.rerun()
        else:
            _str_m4.empty()

        def _str_style_hits(val):
            if val == 0 or val == '0':
                return 'color: #888; font-style: italic'
            if val == 'ERROR':
                return 'color: #ff4b4b; font-weight: bold'
            return 'font-weight: bold; color: #51cf66'

        st.dataframe(
            _str_summary_df.style.map(_str_style_hits, subset=['Hit Count']),
            width='stretch',
            hide_index=True
        )

        st.subheader("3. Export")
        _str_dl1, _str_dl2 = st.columns(2)

        _str_summary_csv = _str_summary_df.to_csv(index=False).encode('utf-8')
        _str_dl1.download_button(
            "⬇️ Download STR Summary (CSV)",
            data=_str_summary_csv,
            file_name=f"{os.path.basename(case_folder)}_STR_SUMMARY.csv",
            mime="text/csv",
            width='stretch',
            key="str_dl_summary"
        )

        # permission: str_export
        if auth_manager.has_permission('str_export'):
            try:
                from openpyxl import Workbook as _str_wb
                _str_xlsx_buf = io.BytesIO()
                with pd.ExcelWriter(_str_xlsx_buf, engine='openpyxl') as _str_writer:
                    _str_summary_df.to_excel(_str_writer, index=False, sheet_name='STR Summary')
                    if not _str_hit_df.empty:
                        _str_hit_df.to_excel(_str_writer, index=False, sheet_name='Hit Documents')
                _str_dl2.download_button(
                    "⬇️ Download Full Report (Excel)",
                    data=_str_xlsx_buf.getvalue(),
                    file_name=f"{os.path.basename(case_folder)}_STR_REPORT.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width='stretch',
                    key="str_dl_excel"
                )
            except ImportError:
                _str_dl2.info("Install `openpyxl` for Excel export.")
        else:
            _str_dl2.info("STR Excel export requires Manager or Admin access.")

        if not _str_hit_df.empty:
            st.markdown("---")
            st.subheader("4. Hit Document Preview")
            _str_filter_term = st.selectbox(
                "Filter by term",
                ["All Terms"] + list(_str_summary_df['Term']),
                key="str_term_filter"
            )
            _str_view_df = _str_hit_df if _str_filter_term == "All Terms" else _str_hit_df[_str_hit_df['Term'] == _str_filter_term]
            st.dataframe(_str_view_df, width='stretch', hide_index=True)

    st.stop()  # Don't render the Review Grid when STR view is active

# =
# NEAR-DUPE CLUSTER REVIEW VIEW — full-page mode, symmetric with STR above.
# st.stop() prevents the Review Grid from loading when this view is active.
# =
if _rv_page_view == "🧬 Near-Dupe Clusters":
    _render_neardupe_cluster_review_surface(case_folder)
    st.stop()

# ─── Redaction constants ──────────────────────────────────────────────────────
_REDACT_NO_REASON = "[Redact — No Privilege Reason]"
_REDACT_CUSTOM = "[Custom Reason...]"

# --- FOLDER HIERARCHY NAVIGATION ---
# Collapsible tree state
if '_nav_selected_key' not in st.session_state:
    st.session_state['_nav_selected_key'] = ("all", None, None, None, None)
if '_tree_expanded' not in st.session_state:
    st.session_state['_tree_expanded'] = set()

# Ultra-compact sidebar tree button styling
st.sidebar.markdown("""<style>
    /* ── Ultra-compact sidebar tree ──────────────────────────────── */

    /* All sidebar secondary buttons: compact, left-aligned, borderless */
    section[data-testid="stSidebar"] button[kind="secondary"] {
        padding: 2px 8px !important;
        margin: 0 !important;
        min-height: unset !important;
        height: auto !important;
        font-size: 0.82rem !important;
        line-height: 1.4 !important;
        text-align: left !important;
        display: flex !important;
        justify-content: flex-start !important;
        border: none !important;
        border-radius: 3px !important;
        background: transparent !important;
        color: inherit !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    section[data-testid="stSidebar"] button[kind="secondary"]:hover {
        background: rgba(151, 166, 195, 0.15) !important;
    }

    /* Active/selected node — uses type="primary" */
    section[data-testid="stSidebar"] button[kind="primary"] {
        padding: 2px 8px !important;
        margin: 0 !important;
        min-height: unset !important;
        height: auto !important;
        font-size: 0.82rem !important;
        line-height: 1.4 !important;
        text-align: left !important;
        display: flex !important;
        justify-content: flex-start !important;
        border: none !important;
        border-left: 3px solid #4a9eff !important;
        border-radius: 3px !important;
        background: rgba(74, 158, 255, 0.18) !important;
        color: inherit !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    section[data-testid="stSidebar"] button[kind="primary"]:hover {
        background: rgba(74, 158, 255, 0.28) !important;
    }

    /* Collapse Streamlit's button container wrapper margins */
    section[data-testid="stSidebar"] [data-testid="stButton"] {
        margin: 0 !important;
        padding: 0 !important;
    }

    /* Nuclear: force left-align on ALL elements inside sidebar buttons */
    section[data-testid="stSidebar"] [data-testid="stButton"] * {
        text-align: left !important;
        justify-content: flex-start !important;
    }

    /* Collapse between consecutive buttons (adjacent sibling) */
    section[data-testid="stSidebar"] [data-testid="stButton"] + [data-testid="stButton"] {
        margin-top: -8px !important;
    }

    /* Collapse the element-container wrappers */
    section[data-testid="stSidebar"] [data-testid="element-container"] {
        margin: 0 !important;
        padding: 0 !important;
    }
</style>""", unsafe_allow_html=True)

# Build hierarchy data from DB
conn_tree = db_manager.get_connection(case_folder)
try:
    tree_rows = conn_tree.execute("""  -- db_manager: exempt (dashboard read)
        SELECT source_party, production_volume, custodian,
               source_collection, source_subcollection,
               COUNT(*) as cnt
        FROM documents
        WHERE processing_status NOT LIKE 'Duplicate%'
        GROUP BY source_party, production_volume, custodian,
                 source_collection, source_subcollection
    """).fetchall()
except Exception:
    tree_rows = []

# Also get total count
try:
    total_docs = conn_tree.execute("SELECT COUNT(*) as cnt FROM documents WHERE processing_status NOT LIKE 'Duplicate%'").fetchone()['cnt']  # db_manager: exempt (dashboard read)
except Exception:
    total_docs = 0
conn_tree.close()

# Organize into nested tree structure
# Internal: party → custodian → collection → subcollection
# External: party → volume
_tree_parties = {}   # {party: total_count}
_tree_internal = {}  # {party: {custodian: {"_count": N, collections: {coll: {"_count": N, subcollections: {subcoll: N}}}}}}
_tree_external = {}  # {party: {volume: count}}

for r in tree_rows:
    party = r['source_party'] or 'Internal'
    vol = r['production_volume'] or None
    cust = r['custodian'] or 'Unknown Custodian'
    coll = r['source_collection'] or None
    subcoll = r['source_subcollection'] or None
    cnt = r['cnt']

    _tree_parties[party] = _tree_parties.get(party, 0) + cnt

    if party == 'Internal' or not vol:
        # Internal docs — group by custodian → collection → subcollection
        if party not in _tree_internal:
            _tree_internal[party] = {}
        if cust not in _tree_internal[party]:
            _tree_internal[party][cust] = {"_count": 0, "collections": {}}
        _tree_internal[party][cust]["_count"] += cnt

        if coll:
            colls = _tree_internal[party][cust]["collections"]
            if coll not in colls:
                colls[coll] = {"_count": 0, "subcollections": {}}
            colls[coll]["_count"] += cnt
            if subcoll:
                colls[coll]["subcollections"][subcoll] = colls[coll]["subcollections"].get(subcoll, 0) + cnt
    else:
        # External docs — group by volume
        if party not in _tree_external:
            _tree_external[party] = {}
        _tree_external[party][vol] = _tree_external[party].get(vol, 0) + cnt

# Default expansion: open party-level nodes on first load
if not st.session_state['_tree_expanded']:
    for party in _tree_parties:
        st.session_state['_tree_expanded'].add(("party", party))

# Validate that the stored selection still exists in the current data
_sel = st.session_state.get('_nav_selected_key', ("all", None, None, None, None))
_valid = True
if _sel[0] == "party" and _sel[1] not in _tree_parties:
    _valid = False
elif _sel[0] == "custodian" and (_sel[1] not in _tree_internal or _sel[2] not in _tree_internal.get(_sel[1], {})):
    _valid = False
elif _sel[0] == "volume" and (_sel[1] not in _tree_external or _sel[2] not in _tree_external.get(_sel[1], {})):
    _valid = False
elif _sel[0] == "collection":
    _cust_data = _tree_internal.get(_sel[1], {}).get(_sel[2], {})
    if not _cust_data or _sel[3] not in _cust_data.get("collections", {}):
        _valid = False
elif _sel[0] == "subcollection":
    _cust_data = _tree_internal.get(_sel[1], {}).get(_sel[2], {})
    _coll_data = _cust_data.get("collections", {}).get(_sel[3], {}) if _cust_data else {}
    if not _coll_data or _sel[4] not in _coll_data.get("subcollections", {}):
        _valid = False

if not _valid:
    st.session_state['_nav_selected_key'] = ("all", None, None, None, None)

# ── Build and render collapsible button tree ──────────────────────────────
st.sidebar.markdown("### 📂 Document Navigator")

_nav_selected = st.session_state.get('_nav_selected_key', ("all", None, None, None, None))
_expanded = st.session_state['_tree_expanded']

def _render_tree_btn(label, key_tuple, indent=0):
    """Render a single tree node as a button. Returns True if clicked."""
    prefix = "\u2002\u2002" * indent  # 2 en-spaces per indent level
    is_selected = (key_tuple == _nav_selected)
    clicked = st.sidebar.button(
        f"{prefix}{label}",
        key=f"_nav_{'::'.join(str(k) for k in key_tuple if k is not None)}",
        width='stretch',
        type="primary" if is_selected else "secondary",
    )
    return clicked

def _is_expanded(node_key):
    return node_key in _expanded

def _toggle_expand(node_key):
    if node_key in st.session_state['_tree_expanded']:
        st.session_state['_tree_expanded'].discard(node_key)
    else:
        st.session_state['_tree_expanded'].add(node_key)

# ── Render tree ───────────────────────────────────────────────────────────
_nav_clicked_key = None

# Root: All Documents
if _render_tree_btn(f"📂 All Documents ({total_docs})", ("all", None, None, None, None), indent=0):
    _nav_clicked_key = ("all", None, None, None, None)

sorted_parties = sorted(_tree_parties.keys(), key=lambda p: (0 if p == 'Internal' else 1, p))
for party in sorted_parties:
    p_count = _tree_parties[party]
    p_expand_key = ("party", party)
    has_children = (party in _tree_internal and _tree_internal[party]) or (party in _tree_external and _tree_external[party])

    arrow = "▼ " if (has_children and _is_expanded(p_expand_key)) else ("▶ " if has_children else "  ")
    if _render_tree_btn(f"{arrow}📁 {party} ({p_count})", ("party", party, None, None, None), indent=1):
        _nav_clicked_key = ("party", party, None, None, None)
        if has_children:
            _toggle_expand(p_expand_key)

    if has_children and _is_expanded(p_expand_key):

        # Internal party → custodians
        if party in _tree_internal:
            for cust in sorted(_tree_internal[party].keys()):
                cust_data = _tree_internal[party][cust]
                c_expand_key = ("custodian", party, cust)
                has_colls = bool(cust_data["collections"])

                arrow = "▼ " if (has_colls and _is_expanded(c_expand_key)) else ("▶ " if has_colls else "  ")
                if _render_tree_btn(f"{arrow}📁 {cust} ({cust_data['_count']})", ("custodian", party, cust, None, None), indent=2):
                    _nav_clicked_key = ("custodian", party, cust, None, None)
                    if has_colls:
                        _toggle_expand(c_expand_key)

                if has_colls and _is_expanded(c_expand_key):
                    for coll in sorted(cust_data["collections"].keys()):
                        coll_data = cust_data["collections"][coll]
                        co_expand_key = ("collection", party, cust, coll)
                        has_subs = bool(coll_data["subcollections"])

                        arrow = "▼ " if (has_subs and _is_expanded(co_expand_key)) else ("▶ " if has_subs else "  ")
                        if _render_tree_btn(f"{arrow}📁 {coll} ({coll_data['_count']})", ("collection", party, cust, coll, None), indent=3):
                            _nav_clicked_key = ("collection", party, cust, coll, None)
                            if has_subs:
                                _toggle_expand(co_expand_key)

                        if has_subs and _is_expanded(co_expand_key):
                            for subcoll in sorted(coll_data["subcollections"].keys()):
                                sc_count = coll_data["subcollections"][subcoll]
                                if _render_tree_btn(f"  📁 {subcoll} ({sc_count})", ("subcollection", party, cust, coll, subcoll), indent=4):
                                    _nav_clicked_key = ("subcollection", party, cust, coll, subcoll)

        # External party → volumes
        if party in _tree_external:
            for vol in sorted(_tree_external[party].keys()):
                v_count = _tree_external[party][vol]
                if _render_tree_btn(f"  📁 {vol} ({v_count})", ("volume", party, vol, None, None), indent=2):
                    _nav_clicked_key = ("volume", party, vol, None, None)

# ── Handle selection ──────────────────────────────────────────────────────
if _nav_clicked_key is not None:
    st.session_state['_nav_selected_key'] = _nav_clicked_key
    st.session_state['_page_number'] = 0  # Reset pagination on tree nav change
    st.rerun()

st.sidebar.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)

# --- BATES LOOKUP ---
import re as _bl_re_mod
with st.sidebar.expander("🔎 Bates Lookup", expanded=False):
    st.caption("Resolve Bates numbers to control numbers.")
    _bl_input = st.text_area(
        "Bates Numbers",
        height=80,
        placeholder="ABC-001234\nABC-001238",
        key="bates_lookup_input",
        label_visibility="collapsed"
    )
    if st.button("Look Up", key="bates_lookup_btn"):
        _bl_terms = [t.strip() for t in _bl_re_mod.split(r'[,\n;]+', _bl_input or '') if t.strip()]
        if _bl_terms:
            _bl_all = db_manager.get_all_bates_ranges(case_folder)

            _bl_results = []
            for _term in _bl_terms:
                _tp, _tn = db_manager.parse_bates_token(_term)
                if _tn is None:
                    continue
                for _doc in _bl_all:
                    _bp, _bn = db_manager.parse_bates_token(_doc['begdoc'])
                    _ep, _en = db_manager.parse_bates_token(_doc['enddoc'] or _doc['begdoc'])
                    if _bn is None or _en is None:
                        continue
                    if _tp == _bp and _bn <= _tn <= _en:
                        _bl_results.append({
                            'input': _term,
                            'cn': _doc['control_number'],
                            'volume': _doc['production_volume'] or '',
                            'party': _doc['source_party'] or 'Internal',
                            'custodian': _doc['custodian'] or '',
                            'date': _doc['date_sent'] or '',
                        })

            st.session_state['_bates_lookup_results'] = _bl_results
        else:
            st.session_state.pop('_bates_lookup_results', None)
        st.rerun()

    _bl_prior = st.session_state.get('_bates_lookup_results')
    if _bl_prior is not None:
        if _bl_prior:
            for _res in _bl_prior:
                st.markdown(f"**{_res['input']}** → `{_res['cn']}`")
                st.caption(f"{_res['volume']} · {_res['custodian']} · {_res['date'][:10] if _res['date'] else ''}")
                if st.button(f"Go to {_res['cn']}", key=f"bl_jump_{_res['cn']}_{_res['input']}"):
                    st.session_state['_bates_lookup_jump_cn'] = _res['cn']
                    st.session_state.pop('_bates_lookup_results', None)
                    st.rerun()
        else:
            st.warning("No document found.")

# ── Batch Management (Manager+) ──────────────────────────────────────────
# permission: production (Manager+ gate)
if auth_manager.has_permission('production') and not _case_closed:
    with st.sidebar.expander("📦 Review Batches", expanded=False):
        # Count unbatched reviewable documents
        _unbatched = db_manager.get_unbatched_document_count(case_folder)

        st.markdown("**Create Batches**")
        st.caption(f"{_unbatched:,} documents not yet assigned to a batch.")

        _split_method = st.radio("Split by", ["Document count", "Page count"], key="batch_split_method", horizontal=True)
        _num_batches = st.number_input("Number of batches", min_value=1, max_value=20, value=3, key="batch_num")
        _batch_prefix = st.text_input("Batch name prefix", value="Batch", key="batch_prefix")

        def _create_batches(_cf, _nb, _sm, _pfx):
            """Create N batches from unbatched reviewable documents, keeping families together."""
            from collections import OrderedDict
            rows = db_manager.get_unbatched_documents(_cf)
            if not rows:
                return

            families = OrderedDict()
            for r in rows:
                gid = r['group_id'] or r['control_number']
                if gid not in families:
                    families[gid] = {'docs': [], 'total_pages': 0, 'doc_count': 0}
                families[gid]['docs'].append(r['control_number'])
                families[gid]['total_pages'] += r['pages']
                families[gid]['doc_count'] += 1

            _metric_key = 'total_pages' if _sm == 'Page count' else 'doc_count'
            sorted_families = sorted(families.values(), key=lambda f: -f[_metric_key])

            batch_loads = [0] * _nb
            batch_families = [[] for _ in range(_nb)]

            for fam in sorted_families:
                metric = fam[_metric_key]
                lightest = min(range(_nb), key=lambda i: batch_loads[i])
                batch_loads[lightest] += metric
                batch_families[lightest].append(fam)

            _un = st.session_state.get('username', 'unknown')
            _audit_entries = []

            for i in range(_nb):
                batch_name = f"{_pfx} {i + 1}"
                _dc = sum(f['doc_count'] for f in batch_families[i])
                _pc = sum(f['total_pages'] for f in batch_families[i])

                _bid = db_manager.create_review_batch(_cf, batch_name, _un, _dc, _pc)
                _cns = [cn for fam in batch_families[i] for cn in fam['docs']]
                db_manager.assign_documents_to_batch(_cf, _bid, _cns)

                _audit_entries.append({
                    'action': 'BATCH_CREATED', 'username': _un, 'module': 'Review',
                    'details': json.dumps({
                        'batch_name': batch_name, 'doc_count': _dc,
                        'page_count': _pc, 'split_method': _sm,
                    }),
                })

            db_manager.log_audit_batch(_cf, _audit_entries)
            st.success(f"Created {_nb} batches.")

        def _recalc_batch_counts():
            """Recalculate cached doc_count and page_count for all batches."""
            db_manager.recalculate_batch_counts(case_folder)

        if _unbatched > 0 and st.button(f"Create {_num_batches} batches", type="primary", width='stretch', key="batch_create_btn"):
            _create_batches(case_folder, _num_batches, _split_method, _batch_prefix)
            st.rerun()

        # Existing batches list + assignment
        st.markdown("---")
        st.markdown("**Existing Batches**")

        _batches = db_manager.get_all_batches(case_folder)

        _all_users = auth_manager.list_users()
        _reviewer_names = ['(Unassigned)'] + [u['username'] for u in _all_users]

        for _b in _batches:
            _pct = round((_b['reviewed_docs'] / _b['actual_docs'] * 100) if _b['actual_docs'] > 0 else 0)
            _status_icon = '✅' if _pct == 100 else '🔄' if _pct > 0 else '⬜'
            st.markdown(f"{_status_icon} **{_b['batch_name']}** — {_b['actual_docs']:,} docs · {_pct}%")

            _bc1, _bc2 = st.columns([3, 1])
            _current_assignee = _b['assigned_to'] or '(Unassigned)'
            _new_assignee = _bc1.selectbox(
                "Assigned to", _reviewer_names,
                index=_reviewer_names.index(_current_assignee) if _current_assignee in _reviewer_names else 0,
                key=f"batch_assign_{_b['id']}", label_visibility="collapsed",
            )
            if _new_assignee != _current_assignee:
                _actual = _new_assignee if _new_assignee != '(Unassigned)' else None
                if _bc2.button("Assign", key=f"batch_save_{_b['id']}", width='stretch'):
                    db_manager.update_batch_assignment(case_folder, _b['id'], _actual)
                    db_manager.log_audit(case_folder, "BATCH_ASSIGNED",
                        username=st.session_state.get('username'), module="Review",
                        old_value=_b['assigned_to'], new_value=_actual,
                        details=json.dumps({"batch_name": _b['batch_name'], "batch_id": _b['id']}))
                    st.rerun()

        # Manual batch editing
        with st.expander("✏️ Manual Batch Editing"):
            st.caption("Move specific documents between batches.")
            _batch_names = [(b['id'], b['batch_name']) for b in _batches]
            if not _batch_names:
                st.info("Create batches first.")
            else:
                _target_batch = st.selectbox(
                    "Target batch", _batch_names,
                    format_func=lambda x: x[1], key="manual_target_batch",
                )
                _cns_raw = st.text_area("Control numbers (one per line or comma-separated)", key="manual_batch_cns")
                if _cns_raw and _target_batch:
                    _cns = [cn.strip() for cn in _cns_raw.replace(',', '\n').split('\n') if cn.strip()]
                    st.caption(f"{len(_cns)} control numbers entered.")
                    if st.button(f"Move to '{_target_batch[1]}'", key="manual_batch_move"):
                        db_manager.reassign_batch_documents(case_folder, _cns, _target_batch[0])
                        _recalc_batch_counts()
                        db_manager.log_audit(case_folder, "BATCH_DOCUMENTS_MOVED",
                            username=st.session_state.get('username'), module="Review",
                            details=json.dumps({"target_batch": _target_batch[1], "documents_moved": len(_cns)}))
                        st.rerun()

        # Delete all batches
        if _batches:
            st.markdown("---")
            if st.button("🗑️ Delete All Batches", key="batch_delete_all"):
                db_manager.delete_all_batches(case_folder)
                db_manager.log_audit(case_folder, "BATCHES_DELETED",
                    username=st.session_state.get('username'), module="Review",
                    details=json.dumps({"batches_deleted": len(_batches)}))
                st.rerun()

# ── Production Categories (Manager+) ───────────────────────────────────────
# permission: manage_production_categories
if auth_manager.has_permission('production') and not _case_closed:
    with st.sidebar.expander("📂 Production Categories", expanded=False):
        _pc_cats = db_manager.get_production_categories(case_folder)
        _pc_summary = db_manager.get_category_summary(case_folder)

        if not _pc_cats and 'pc_editing' not in st.session_state:
            st.caption("No production categories defined yet.")
            if st.button("➕ Create Default Categories", key="pc_create_defaults"):
                _defaults = [
                    {"name": "Correspondence", "sort_order": 1, "color": "#339af0", "keywords": ["letter", "email", "memo"], "extensions": [".msg", ".eml"]},
                    {"name": "Contracts", "sort_order": 2, "color": "#51cf66", "keywords": ["agreement", "contract", "addendum"], "extensions": []},
                    {"name": "Development File", "sort_order": 3, "color": "#ff922b", "keywords": ["permit", "inspection", "plan", "survey"], "extensions": []},
                    {"name": "Insurance", "sort_order": 4, "color": "#845ef7", "keywords": ["policy", "claim", "coverage", "insured"], "extensions": []},
                    {"name": "Expert Reports", "sort_order": 5, "color": "#f06595", "keywords": ["expert", "report", "opinion"], "extensions": []},
                    {"name": "Financial Records", "sort_order": 6, "color": "#20c997", "keywords": ["invoice", "payment", "receipt", "ledger"], "extensions": [".xlsx", ".csv"]},
                    {"name": "Pleadings", "sort_order": 7, "color": "#e64980", "keywords": ["complaint", "answer", "motion", "order"], "extensions": []},
                    {"name": "Discovery", "sort_order": 8, "color": "#fab005", "keywords": ["interrogat", "request for", "subpoena", "deposition"], "extensions": []},
                ]
                db_manager.save_production_categories(case_folder, _defaults,
                    username=st.session_state.get('username'))
                st.rerun()
        else:
            # ── Category list display with counts ──
            for _pc_cat in _pc_cats:
                _pc_count = _pc_summary.get(_pc_cat['name'], 0)
                _pc_color = _pc_cat.get('color', '#888888')
                st.markdown(
                    f"<span style='display:inline-block;width:12px;height:12px;"
                    f"background:{_pc_color};border-radius:3px;margin-right:6px;'></span>"
                    f"**{_pc_cat['name']}** — {_pc_count:,} docs",
                    unsafe_allow_html=True
                )
            _pc_uncat = _pc_summary.get('Uncategorized', 0)
            if _pc_uncat > 0:
                st.caption(f"Uncategorized: {_pc_uncat:,} docs")

            st.markdown("---")

            # ── Edit categories ──
            if st.button("✏️ Edit Categories", key="pc_edit_btn"):
                st.session_state['pc_editing'] = True
                st.session_state['pc_draft'] = [dict(c) for c in _pc_cats]
                st.rerun()

            if st.session_state.get('pc_editing'):
                _pc_draft = st.session_state.get('pc_draft', [])
                _pc_kv = st.session_state.get('_pc_key_ver', 0)

                for _pci, _pc_item in enumerate(_pc_draft):
                    _pc_c1, _pc_c2, _pc_c3 = st.columns([4, 1, 1])
                    with _pc_c1:
                        _pc_item['name'] = st.text_input(
                            "Name", value=_pc_item['name'],
                            key=f"pc_name_{_pc_kv}_{_pci}", label_visibility="collapsed")
                    with _pc_c2:
                        _pc_item['color'] = st.color_picker(
                            "Color", value=_pc_item.get('color', '#888888'),
                            key=f"pc_color_{_pc_kv}_{_pci}", label_visibility="collapsed")
                    with _pc_c3:
                        _pc_order_cols = st.columns(2)
                        if _pci > 0:
                            if _pc_order_cols[0].button("▲", key=f"pc_up_{_pci}"):
                                _pc_draft[_pci], _pc_draft[_pci - 1] = _pc_draft[_pci - 1], _pc_draft[_pci]
                                for _j, _d in enumerate(_pc_draft):
                                    _d['sort_order'] = _j + 1
                                st.session_state['_pc_key_ver'] = _pc_kv + 1
                                st.rerun()
                        if _pci < len(_pc_draft) - 1:
                            if _pc_order_cols[1].button("▼", key=f"pc_down_{_pci}"):
                                _pc_draft[_pci], _pc_draft[_pci + 1] = _pc_draft[_pci + 1], _pc_draft[_pci]
                                for _j, _d in enumerate(_pc_draft):
                                    _d['sort_order'] = _j + 1
                                st.session_state['_pc_key_ver'] = _pc_kv + 1
                                st.rerun()

                    _pc_item['keywords'] = [
                        k.strip() for k in st.text_input(
                            "Keywords (comma-separated)",
                            value=", ".join(_pc_item.get('keywords', [])),
                            key=f"pc_kw_{_pc_kv}_{_pci}"
                        ).split(",") if k.strip()
                    ]
                    _pc_item['extensions'] = [
                        e.strip() for e in st.text_input(
                            "Extensions (comma-separated)",
                            value=", ".join(_pc_item.get('extensions', [])),
                            key=f"pc_ext_{_pc_kv}_{_pci}"
                        ).split(",") if e.strip()
                    ]
                    if st.button("🗑️ Remove", key=f"pc_del_{_pci}"):
                        _pc_draft.pop(_pci)
                        for _j, _d in enumerate(_pc_draft):
                            _d['sort_order'] = _j + 1
                        st.session_state['_pc_key_ver'] = _pc_kv + 1
                        st.rerun()
                    st.markdown("---")

                # Add new category
                if st.button("➕ Add Category", key="pc_add"):
                    _pc_draft.append({
                        'name': f"Category {len(_pc_draft) + 1}",
                        'sort_order': len(_pc_draft) + 1,
                        'color': '#888888',
                        'keywords': [],
                        'extensions': [],
                    })
                    st.rerun()

                # Save / Cancel
                _pc_save_col, _pc_cancel_col = st.columns(2)
                if _pc_save_col.button("💾 Save", key="pc_save", type="primary"):
                    # Validate: no duplicate names
                    _pc_names = [c['name'].strip() for c in _pc_draft]
                    if len(_pc_names) != len(set(_pc_names)):
                        st.error("Category names must be unique.")
                    elif any(not n for n in _pc_names):
                        st.error("Category names cannot be empty.")
                    else:
                        for _j, _d in enumerate(_pc_draft):
                            _d['name'] = _d['name'].strip()
                            _d['sort_order'] = _j + 1
                        db_manager.save_production_categories(case_folder, _pc_draft,
                            username=st.session_state.get('username'))
                        st.session_state.pop('pc_editing', None)
                        st.session_state.pop('pc_draft', None)
                        st.session_state.pop('_pc_key_ver', None)
                        st.success("Categories saved.")
                        st.rerun()
                if _pc_cancel_col.button("Cancel", key="pc_cancel"):
                    st.session_state.pop('pc_editing', None)
                    st.session_state.pop('pc_draft', None)
                    st.session_state.pop('_pc_key_ver', None)
                    st.rerun()

            # ── Auto-Categorize Tool ──
            st.markdown("---")
            st.markdown("**Auto-Categorize**")
            _pc_uncat_count = _pc_summary.get('Uncategorized', 0)
            st.caption(f"{_pc_uncat_count:,} uncategorized documents")

            if _pc_cats and _pc_uncat_count > 0:
                if st.button("🤖 Preview Auto-Categorize", key="pc_auto_preview"):
                    with st.spinner("Matching documents against category rules..."):
                        _ac_results = db_manager.auto_categorize_documents(case_folder, dry_run=True)
                    st.session_state['pc_auto_results'] = _ac_results
                    # Pre-check all matched control numbers
                    _ac_all_cns = set()
                    for _ac_docs in _ac_results.values():
                        for _ac_doc in _ac_docs:
                            _ac_all_cns.add(_ac_doc['control_number'])
                    st.session_state['pc_auto_selected'] = _ac_all_cns
                    st.rerun()

                if 'pc_auto_results' in st.session_state:
                    _ac_results = st.session_state['pc_auto_results']
                    _ac_selected = st.session_state.get('pc_auto_selected', set())

                    if not _ac_results:
                        st.info("No matches found. Consider adjusting keyword/extension rules.")
                        if st.button("Dismiss", key="pc_auto_dismiss"):
                            st.session_state.pop('pc_auto_results', None)
                            st.session_state.pop('pc_auto_selected', None)
                            st.rerun()
                    else:
                        _ac_total_matched = sum(len(v) for v in _ac_results.values())
                        _ac_total_selected = len(_ac_selected)
                        st.info(f"Ready to categorize: **{_ac_total_selected:,}** of "
                                f"{_ac_total_matched:,} matched documents "
                                f"({_ac_total_matched - _ac_total_selected:,} deselected)")

                        # Tabbed preview — one tab per category
                        _ac_tab_names = list(_ac_results.keys())
                        _ac_tabs = st.tabs([f"{name} ({len(_ac_results[name])})" for name in _ac_tab_names])
                        for _ac_tab, _ac_cat_name in zip(_ac_tabs, _ac_tab_names):
                            with _ac_tab:
                                _ac_docs = _ac_results[_ac_cat_name]
                                _ac_df = pd.DataFrame(_ac_docs)
                                _ac_df['selected'] = _ac_df['control_number'].isin(_ac_selected)
                                _ac_edited = st.data_editor(
                                    _ac_df[['selected', 'control_number', 'file_name', 'record_type',
                                            'date_sent', 'match_reason']],
                                    column_config={
                                        'selected': st.column_config.CheckboxColumn("✓", width="small"),
                                        'control_number': 'Control #',
                                        'file_name': 'File Name',
                                        'record_type': 'Type',
                                        'date_sent': 'Date',
                                        'match_reason': 'Match Reason',
                                    },
                                    hide_index=True,
                                    use_container_width=True,
                                    key=f"pc_auto_grid_{_ac_cat_name}",
                                )
                                # Update selection state from edits
                                for _, _ac_row in _ac_edited.iterrows():
                                    _ac_cn = _ac_row['control_number']
                                    if _ac_row['selected']:
                                        _ac_selected.add(_ac_cn)
                                    else:
                                        _ac_selected.discard(_ac_cn)
                                st.session_state['pc_auto_selected'] = _ac_selected

                        # Apply / Cancel buttons
                        _ac_btn_col1, _ac_btn_col2 = st.columns(2)
                        if _ac_btn_col1.button("✅ Apply Selected", key="pc_auto_apply", type="primary"):
                            if _ac_selected:
                                with st.spinner("Applying categories..."):
                                    db_manager.auto_categorize_documents(
                                        case_folder, dry_run=False,
                                        selected_control_numbers=list(_ac_selected))
                                st.session_state.pop('pc_auto_results', None)
                                st.session_state.pop('pc_auto_selected', None)
                                _remaining = _pc_uncat_count - len(_ac_selected)
                                st.success(f"Categorized {len(_ac_selected):,} documents. "
                                          f"{_remaining:,} remain uncategorized.")
                                st.rerun()
                            else:
                                st.warning("No documents selected.")
                        if _ac_btn_col2.button("Cancel", key="pc_auto_cancel"):
                            st.session_state.pop('pc_auto_results', None)
                            st.session_state.pop('pc_auto_selected', None)
                            st.rerun()
            elif _pc_cats and _pc_uncat_count == 0:
                st.success("All documents are categorized.")

elif auth_manager.has_permission('production') and _case_closed:
    with st.sidebar.expander("📂 Production Categories", expanded=False):
        _pc_cats = db_manager.get_production_categories(case_folder)
        _pc_summary = db_manager.get_category_summary(case_folder)
        if _pc_cats:
            for _pc_cat in _pc_cats:
                _pc_count = _pc_summary.get(_pc_cat['name'], 0)
                _pc_color = _pc_cat.get('color', '#888888')
                st.markdown(
                    f"<span style='display:inline-block;width:12px;height:12px;"
                    f"background:{_pc_color};border-radius:3px;margin-right:6px;'></span>"
                    f"**{_pc_cat['name']}** — {_pc_count:,} docs",
                    unsafe_allow_html=True
                )
            _pc_uncat = _pc_summary.get('Uncategorized', 0)
            if _pc_uncat > 0:
                st.caption(f"Uncategorized: {_pc_uncat:,} docs")
        else:
            st.caption("No production categories defined.")
        st.caption("🔒 Case closed — read-only")

# Derive filter values from the tree selection
_nav_sel = st.session_state.get('_nav_selected_key', ("all", None, None, None, None))
nav_level = _nav_sel[0]

selected_party = "All Parties"
selected_custodian = None
selected_volume = None
selected_collection = None
selected_subcollection = None

if nav_level == "party":
    selected_party = _nav_sel[1]
elif nav_level == "custodian":
    selected_party = _nav_sel[1]
    selected_custodian = _nav_sel[2]
elif nav_level == "volume":
    selected_party = _nav_sel[1]
    selected_volume = _nav_sel[2]
elif nav_level == "collection":
    selected_party = _nav_sel[1]
    selected_custodian = _nav_sel[2]
    selected_collection = _nav_sel[3]
elif nav_level == "subcollection":
    selected_party = _nav_sel[1]
    selected_custodian = _nav_sel[2]
    selected_collection = _nav_sel[3]
    selected_subcollection = _nav_sel[4]

# --- INTEGRATED SEARCH BAR ---
import re as _re
import html as _html

_SYNTAX_TIPS = """
**Supported Search Syntax**

| Syntax | Example | Meaning |
|--------|---------|----------|
| Plain terms | `invoice settlement` | Both words anywhere in doc |
| AND / OR / NOT | `invoice AND 2023` | Boolean operators |
| Exact phrase | `\"attorney client\"` | Must appear together |
| Wildcard | `settl*` | settle, settlement, settling… |
| Single char | `te?t` | test, text |
| Fuzzy | `priviledge~` | Typo / misspelling tolerance |
| Fuzzy distance | `privilege~2` | Up to 2 character edits |
| Field search | `email_subject:invoice` | Search one specific field |
| Grouping | `(fraud OR deceit) AND 2023` | Parens for grouping |
| Bates | `ABC-000123` | Also searched in SQLite directly |

**Not supported:** W/N proximity (dtSearch-style). Use `\"phrase\"~5` slop instead.
"""

# ── Session-state bridge: load a saved query BEFORE the widget renders ──
if st.session_state.get('_load_saved_query'):
    st.session_state['review_search'] = st.session_state.pop('_load_saved_query')
    st.rerun()

# ── Restore search state from family override exit (before widget render) ──
if '_pending_search_restore' in st.session_state:
    _restore = st.session_state.pop('_pending_search_restore')
    st.session_state['review_search'] = _restore.get('search_query', '')
    for _col_name, _val in _restore.get('col_filters', {}).items():
        st.session_state[f"col_filter_{_col_name}"] = _val
    st.rerun()

# ── Batch Filter ──────────────────────────────────────────────────────────
_current_user = st.session_state.get('username')
_active_batch_id = None
_user_batches_conn = db_manager.get_connection(case_folder)
_user_batches = _user_batches_conn.execute(  # db_manager: exempt (dashboard read)
    "SELECT id, batch_name, doc_count FROM review_batches WHERE assigned_to = ? ORDER BY id",
    (_current_user,)
).fetchall()
_user_batches_conn.close()

if _user_batches:
    _batch_options = [('all', 'All Documents')] + [(b['id'], f"📦 {b['batch_name']} ({b['doc_count']:,} docs)") for b in _user_batches]
    _default_idx = 1 if not auth_manager.has_permission('production') else 0
    _batch_sel = st.radio(
        "View", _batch_options, index=_default_idx,
        format_func=lambda x: x[1], key="review_batch_filter", horizontal=True,
    )
    _active_batch_id = _batch_sel[0] if _batch_sel[0] != 'all' else None

# ── Date Range Filter ─────────────────────────────────────────────────────
_dr_col1, _dr_col2 = st.columns(2)
_date_from = _dr_col1.date_input("Date From", value=None, key="review_date_from")
_date_to = _dr_col2.date_input("Date To", value=None, key="review_date_to")
if _date_from or _date_to:
    st.caption("Filters on date_sent (emails) or date_created (other documents).")

search_col, bates_col, tips_col = st.columns([7, 1.5, 1])
with search_col:
    search_query = st.text_input(
        "🔍 Search",
        placeholder='e.g.  \"attorney client\"  OR  settl*  OR  privilege~',
        key="review_search",
        label_visibility="collapsed"
    )
    st.checkbox("📎 Include families in results", value=False, key="search_include_families")

with bates_col:
    with st.popover("📋 Bulk Bates", width='stretch'):
        st.markdown("**Bates Batch Search**")
        st.caption("Paste a comma/semicolon separated list of Bates or Ranges (e.g. `ABC 001-005, 010, XYZ 003`).")
        batch_text = st.text_area("Bates List", height=150, label_visibility="collapsed", key="bates_batch_input")
        bates_include_families = st.checkbox("📎 Include families in results", value=False, key="bates_batch_include_families")
        if st.button("Parse & Search", width='stretch', type="primary", key="bates_parse_search_btn"):
            if batch_text.strip():
                st.session_state['_bates_batch_text'] = batch_text
                st.session_state['_bates_batch_include_families'] = bool(bates_include_families)
                st.rerun()

with tips_col:
    with st.popover("💡 Tips", width='stretch'):
        st.markdown(_SYNTAX_TIPS)


# ── Saved & Recent Searches ───────────────────────────────────────────────────
_username = st.session_state.get('username', 'anonymous')

# Per-user document visibility config (admin always gets full universe)
_doc_visibility = auth_manager.get_doc_visibility(_username)
_vis_mode = _doc_visibility['mode']
_vis_hidden_tags = _doc_visibility['hidden_tags']

# User-toggleable produced_only UX-filter (col_filter cluster checkbox).
# Defense-in-depth: gate on _vis_mode != 'produced_only' so the toggle is a no-op
# for security-restricted users (they're already filtered by the security gate).
_session_produced_only_ux = bool(st.session_state.get('filter_produced_only_ux', False)) and _vis_mode != 'produced_only'


def _log_recent(query: str):
    """Auto-log a non-empty search. Rotates to keep only the 10 most recent per user."""
    if not query.strip():
        return
    db_manager.log_recent_search(case_folder, _username, query.strip())

def _get_named_saves():
    return db_manager.get_named_searches(case_folder, _username)

def _get_recent():
    return db_manager.get_recent_searches(case_folder, _username)

def _delete_saved(row_id: int):
    db_manager.delete_saved_search(case_folder, row_id, _username)

def _toggle_global(row_id: int, new_value: bool):
    """Toggle is_global on a saved search owned by the current user."""
    db_manager.toggle_search_global(case_folder, row_id, _username, new_value)

# CRIT-5: Single write helper for all Review module DB operations.
# API: _safe_write(operation, success_msg, error_msg, audit_params=None)
#   operation      — zero-arg callable that performs the DB write
#   success_msg    — string shown in st.toast on success (pass None to suppress)
#   error_msg      — prefix shown in st.error on failure
#   audit_params   — dict with keys: action, control_number, module, and optional
#                    old_value, new_value, details. Audit logged ONLY on success.
def _cascade_tag_to_children(case_folder_path, parent_cn, tag_str, username, action="add"):
    """
    Cascade a document-level tag change to all attachment children of a parent.
    action='add'    — ensure tag_str is present on each child
    action='remove' — ensure tag_str is absent from each child
    action='set'    — overwrite each child's tags with tag_str (used by single-doc save)

    Redaction marks are stored separately and are NOT affected.
    NOTE: PM Claude should review this cascade behaviour for eDiscovery protocol compliance.
    """
    _cc = db_manager.get_connection(case_folder_path)
    _children = _cc.execute(  # db_manager: exempt (review loop)
        "SELECT control_number, tags FROM documents WHERE parent_id = ?", (parent_cn,)
    ).fetchall()
    if not _children:
        _cc.close()
        return
    _audit_rows = []
    for _ch in _children:
        _ch_cn = _ch['control_number']
        _ch_old = _ch['tags'] or ''
        _ch_tags = [t.strip() for t in _ch_old.replace(';', ',').split(',') if t.strip()]
        if action == 'add':
            if tag_str not in _ch_tags:
                _ch_tags.append(tag_str)
            else:
                continue  # already has it
        elif action == 'remove':
            if tag_str in _ch_tags:
                _ch_tags.remove(tag_str)
            else:
                continue  # doesn't have it
        elif action == 'set':
            # Preserve system tags on children, apply user's tag set
            _SYS = ("NearDupe-", "Thread-", "NIST-", "Junk ", "Inclusive")
            _child_sys = [t for t in _ch_tags if any(t.startswith(p) for p in _SYS)]
            _parent_user = [t.strip() for t in tag_str.replace(';', ',').split(',') if t.strip()
                           and not any(t.strip().startswith(p) for p in _SYS)]
            _ch_tags = _parent_user + _child_sys
        _ch_new = ', '.join(_ch_tags)
        if _ch_old != _ch_new:
            _cc.execute("UPDATE documents SET tags=? WHERE control_number=?", (_ch_new, _ch_cn))  # db_manager: exempt (review loop)
            _audit_rows.append({
                "action": "TAGS_CHANGED", "username": username,
                "control_number": _ch_cn, "module": "Review",
                "details": f"cascaded from parent {parent_cn}",
                "old_value": _ch_old, "new_value": _ch_new,
            })
    _cc.commit()
    _cc.close()
    if _audit_rows:
        db_manager.log_audit_batch(case_folder_path, _audit_rows)


def _safe_write(operation, success_msg, error_msg, audit_params=None):
    # Re-verify case is still open before writing (race condition guard — M-5)
    if db_manager.get_case_status(case_folder) == 'Closed':
        st.error("Case was closed by another user. Please refresh the page.")
        return False
    try:
        operation()
        if audit_params:
            db_manager.log_audit(
                case_folder,
                audit_params['action'],
                username=_username,
                control_number=audit_params.get('control_number'),
                module=audit_params.get('module', 'Review'),
                old_value=audit_params.get('old_value'),
                new_value=audit_params.get('new_value'),
                details=audit_params.get('details'),
            )
        if success_msg:
            st.toast(success_msg, icon="✅")
        return True
    except Exception as _sw_err:
        st.error(f"{error_msg}: {_sw_err}")
        return False

def _offer_produced_download(produced_pdf: str, control_number: str, begdoc: str):
    """
    Render a download button for the Bates-stamped produced PDF.
    Only shown to users with the download_produced permission.
    No-ops silently if the file is missing or is a TIFF.
    """
    # permission: download_produced
    if not auth_manager.has_permission('download_produced'):
        return
    if not produced_pdf or not produced_pdf.lower().endswith('.pdf'):
        return
    if not os.path.exists(produced_pdf):
        return
    with open(produced_pdf, 'rb') as _f:
        _pdf_bytes = _f.read()
    if st.download_button(
        label=f"⬇️ Download Produced PDF ({begdoc})",
        data=_pdf_bytes,
        file_name=f"{begdoc}.pdf",
        mime="application/pdf",
        key=f"dl_produced_{control_number}",
    ):
        db_manager.log_audit(
            case_folder, "PRODUCED_DOWNLOAD",
            username=_username,
            control_number=control_number,
            module="Review",
            details=begdoc,
        )


def _save_named(name: str, query: str, is_global: bool = False):
    def _op():
        db_manager.save_named_search(
            case_folder, _username, name.strip(), query.strip(), '{}', is_global
        )
    _safe_write(
        _op,
        f"✅ Search saved as \u2018{name}\u2019",
        "❌ Failed to save named search",
        audit_params={"action": "SEARCH_SAVED", "control_number": None, "module": "Review", "details": name}
    )

# permission: saved_search_personal
if auth_manager.has_permission('saved_search_personal'):
    named_saves = _get_named_saves()
    recent_searches = _get_recent()

    saved_col, recent_col = st.columns([1, 1])
    with saved_col:
        with st.expander(f"📌 Saved Searches ({len(named_saves)})", expanded=False):
            if not named_saves:
                st.caption("No named searches yet. Run a search and click **💾 Save** below.")
            for row in named_saves:
                row_id, sname, squery = row['id'], row['search_name'], row['query']
                _row_keys = row.keys() if hasattr(row, 'keys') else []
                is_global = row['is_global'] if 'is_global' in _row_keys else 0
                owner = row['username'] if 'username' in _row_keys else ''

                s1, s2 = st.columns([5, 1])
                if is_global:
                    s1.markdown(f"**🌐 {sname}** *(by {owner})*")
                else:
                    s1.markdown(f"**🔒 {sname}**")
                s1.caption(f"`{squery[:72]}{'…' if len(squery) > 72 else ''}`")

                if s2.button("📂", key=f"load_named_{row_id}", help="Load this search"):
                    st.session_state['_load_saved_query'] = squery
                    st.rerun()

                if owner == _username:
                    # permission: saved_search_global
                    if auth_manager.has_permission('saved_search_global') and not _case_closed:
                        if is_global:
                            if s2.button("🔒", key=f"unshare_{row_id}", help="Make private"):
                                _toggle_global(row_id, False)
                                db_manager.log_audit(case_folder, "SEARCH_UNSHARED", username=_username,
                                    module="Review", details=json.dumps({"name": sname}))
                                st.rerun()
                        else:
                            if s2.button("🌐", key=f"share_{row_id}", help="Share with team"):
                                _toggle_global(row_id, True)
                                db_manager.log_audit(case_folder, "SEARCH_SHARED", username=_username,
                                    module="Review", details=json.dumps({"name": sname}))
                                st.rerun()

                    if not _case_closed and s2.button("🗑", key=f"del_named_{row_id}", help="Delete"):
                        _delete_saved(row_id)
                        try:
                            db_manager.log_audit(case_folder, "SEARCH_DELETED", username=_username,
                                module="Review", details=json.dumps({"name": sname, "query": squery[:200]}))
                        except Exception:
                            pass
                        st.rerun()

    with recent_col:
        with st.expander(f"🕐 Recent ({len(recent_searches)})", expanded=False):
            if not recent_searches:
                st.caption("No searches run yet.")
            else:
                if st.button("🧹 Clear All", key="clear_recent", width='stretch'):
                    db_manager.clear_recent_searches(case_folder, _username)
                    st.rerun()
                for row in recent_searches:
                    row_id, rquery = row['id'], row['query']
                    r1, r2 = st.columns([5, 1])
                    r1.caption(f"`{rquery[:72]}{'…' if len(rquery) > 72 else ''}`")
                    if r2.button("📂", key=f"load_recent_{row_id}", help="Load this search"):
                        st.session_state['_load_saved_query'] = rquery
                        st.rerun()

    # Save widget — shown only while a query is active
    _current_query = st.session_state.get('review_search', '').strip()
    if _current_query:
        with st.form("save_search_form", clear_on_submit=True):
            sv1, sv2, sv3 = st.columns([3, 2, 1])
            save_name_input = sv1.text_input("Name", placeholder="e.g. Smith privilege emails", label_visibility="collapsed")
            # permission: saved_search_global
            if auth_manager.has_permission('saved_search_global'):
                is_global_check = sv2.checkbox("🌍 Share with Team", value=False)
            else:
                is_global_check = False
            if sv3.form_submit_button("💾 Save", width='stretch'):
                if _case_closed:
                    st.warning("Write operations are disabled on closed matters.")
                elif save_name_input.strip():
                    _save_named(save_name_input, _current_query, is_global_check)
                    db_manager.log_audit(case_folder, "SEARCH_SAVED", username=_username, module="Review",
                        details=json.dumps({"name": save_name_input, "query": _current_query}))
                    st.success(f"✅ Saved as **{save_name_input}**")
                    st.rerun()
                else:
                    st.warning("Enter a name first.")


def _validate_search_query(q: str):
    q_clean = _re.sub(r'\\.', '', q)

    if q_clean.count('"') % 2 != 0:
        return False, 'Unbalanced double quotes — close all `\"` pairs.'
    depth = 0
    for ch in q_clean:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if depth < 0:
            return False, 'Unbalanced parentheses — unexpected `)`.'
    if depth != 0:
        return False, f'Unbalanced parentheses — {depth} unclosed `(`.'
    stripped = q.strip().upper()
    if stripped in ('AND', 'OR', 'NOT'):
        return False, f'Query cannot be just `{q.strip()}`.'
    if _re.match(r'^(AND|OR)\s', q.strip(), _re.IGNORECASE):
        return False, 'Query cannot start with AND or OR.'
    if _re.search(r'\s(AND|OR|NOT)$', q.strip(), _re.IGNORECASE):
        return False, 'Query cannot end with AND, OR, or NOT.'
    return True, ''

def _extract_search_terms(query: str) -> list:
    """
    Extract plain-text search terms from an OpenSearch query string.
    Strips operators (AND, OR, NOT), fuzzy markers (~), wildcards (*),
    and extracts quoted phrases as single terms.
    Unquoted hyphenated terms are expanded to match OpenSearch's standard
    analyzer behavior. Quoted phrases are kept exact — no expansion.
    Returns a list of clean terms suitable for regex highlighting.
    """
    if not query or not query.strip():
        return []
    import re as _re_ext
    phrase_terms = []   # from quoted phrases — exact, no expansion
    bare_terms = []     # from unquoted tokens — eligible for expansion

    # Extract quoted phrases first, then remove them from the string
    for match in _re_ext.finditer(r'"([^"]+)"', query):
        phrase_terms.append(match.group(1).strip())
    remainder = _re_ext.sub(r'"[^"]*"', '', query)

    _OPERATORS = {'AND', 'OR', 'NOT', 'TO'}
    for token in remainder.split():
        # Strip trailing fuzzy/boost markers: term~ or term~2 or term^2
        clean = _re_ext.sub(r'[~^]\d*$', '', token)
        clean = clean.replace('*', '').replace('?', '')
        clean = clean.strip('()')
        if not clean or clean.upper() in _OPERATORS or ':' in clean:
            continue
        bare_terms.append(clean)

    # Expand only bare (unquoted) hyphenated terms to mirror OpenSearch tokenization
    expanded = []
    for t in bare_terms:
        if len(t) < 2:
            continue
        expanded.append(t)  # keep original (e.g. "attorney-client")
        if '-' in t:
            for part in t.split('-'):
                part = part.strip()
                if len(part) >= 2 and part not in expanded:
                    expanded.append(part)  # add components (e.g. "attorney", "client")

    # Quoted phrases first (exact match priority), then expanded bare terms
    result = []
    for t in phrase_terms:
        if len(t) >= 2 and t not in result:
            result.append(t)
    for t in expanded:
        if t not in result:
            result.append(t)
    return result


def _highlight_pdf_bytes(pdf_path: str, search_terms: list, pages=None):
    """
    Opens a PDF, highlights all occurrences of search_terms in cyan, and returns
    the modified PDF as bytes. Does NOT modify the original file.
    Returns None if the file can't be opened.
    """
    import fitz
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None

    try:
        target_pages = pages if pages is not None else range(len(doc))
        _HL_COLOR = (0.5, 0.83, 1.0)  # cyan matching #80d4ff

        for page_idx in target_pages:
            if page_idx >= len(doc):
                continue
            page = doc[page_idx]
            for term in search_terms:
                if not term.strip():
                    continue
                for rect in page.search_for(term):
                    annot = page.add_highlight_annot(rect)
                    annot.set_colors(stroke=_HL_COLOR)
                    annot.set_opacity(0.4)
                    annot.update()

        pdf_bytes = doc.tobytes()
        return pdf_bytes
    except Exception:
        return None
    finally:
        doc.close()


def _highlight_page_image(pdf_path: str, page_idx: int, search_terms: list, zoom: float = 1.0):
    """
    Renders a single PDF page to a PIL Image with search term highlights baked in.
    Used for the redaction canvas background. Returns None on failure.
    """
    import fitz
    from PIL import Image
    import io as _io

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None

    try:
        if page_idx >= len(doc):
            return None

        page = doc[page_idx]
        _HL_COLOR = (0.5, 0.83, 1.0)

        for term in search_terms:
            if not term.strip():
                continue
            for rect in page.search_for(term):
                annot = page.add_highlight_annot(rect)
                annot.set_colors(stroke=_HL_COLOR)
                annot.set_opacity(0.4)
                annot.update()

        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(_io.BytesIO(pix.tobytes("png")))
        return img
    except Exception:
        return None
    finally:
        doc.close()


def _get_pdf_page_count(pdf_path: str):
    """Returns (page_count, error_msg). error_msg is None on success,
    'password' for encrypted PDFs, or a string for other failures."""
    import fitz
    doc = None
    try:
        doc = fitz.open(pdf_path)
        return len(doc), None
    except Exception as e:
        err_msg = str(e).lower()
        if 'password' in err_msg or 'encrypted' in err_msg or 'decrypt' in err_msg:
            return 0, 'password'
        return 0, str(e)
    finally:
        if doc:
            doc.close()


def _render_pdf_page_image(pdf_path: str, page_idx: int, search_terms: list = None, target_width: int = 900):
    """
    Renders a single PDF page as a PNG byte string for display via st.image().
    Optionally highlights search terms. Returns (png_bytes, page_count) or (None, 0).
    """
    import fitz

    doc = None
    try:
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        if page_count == 0:
            return None, 0
        page_idx = max(0, min(page_idx, page_count - 1))

        page = doc[page_idx]

        # Apply search highlights before rendering (in-memory only, never saved)
        if search_terms:
            _HL_COLOR = (0.5, 0.83, 1.0)
            for term in search_terms:
                if not term.strip():
                    continue
                for rect in page.search_for(term):
                    annot = page.add_highlight_annot(rect)
                    annot.set_colors(stroke=_HL_COLOR)
                    annot.set_opacity(0.4)
                    annot.update()

        # Calculate DPI from target_width (same math as Redact tab)
        page_w_pt = page.rect.width
        dpi = max(72, min(200, int(target_width * 72 / page_w_pt))) if page_w_pt > 0 else 150
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")
        return png_bytes, page_count
    except Exception:
        return None, 0
    finally:
        if doc:
            doc.close()


def _display_pdf_viewer(pdf_path: str, key_prefix: str, current_cn: str,
                        search_terms: list = None, height: int = 1200, target_width: int = 800):
    """
    Renders all pages of a PDF as images stacked in a scrollable container.
    Optionally highlights search terms on each page.
    Height default is 1200px — tall portrait viewport that fills most of the screen.
    Target width is 800px — narrower for a natural portrait reading feel.
    """
    import fitz

    page_count, err = _get_pdf_page_count(pdf_path)
    if err == 'password':
        st.error("This PDF is password-protected and cannot be rendered.")
        return
    if page_count == 0:
        if err:
            st.warning(f"This PDF has no renderable pages: {err}")
        else:
            st.warning("This PDF has no renderable pages.")
        return

    if page_count > 100:
        st.caption(f"Rendering {page_count} pages — this may take a moment for large documents.")

    progress_bar = None
    if page_count > 10:
        progress_bar = st.progress(0, text=f"Rendering page 1 of {page_count}...")

    doc = None
    try:
        doc = fitz.open(pdf_path)
        _HL_COLOR = (0.5, 0.83, 1.0)
        img_tags = []

        for page_idx in range(len(doc)):
            try:
                page = doc[page_idx]

                # Apply search highlights (in-memory only)
                if search_terms:
                    for term in search_terms:
                        if not term.strip():
                            continue
                        for rect in page.search_for(term):
                            annot = page.add_highlight_annot(rect)
                            annot.set_colors(stroke=_HL_COLOR)
                            annot.set_opacity(0.4)
                            annot.update()

                # Per-page DPI calculation (handles mixed page sizes)
                page_w_pt = page.rect.width
                dpi = max(72, min(200, int(target_width * 72 / page_w_pt))) if page_w_pt > 0 else 150
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                png_bytes = pix.tobytes("png")

                import base64
                b64 = base64.b64encode(png_bytes).decode('ascii')
                img_tags.append(
                    f'<div style="text-align:center; padding:6px 0; font-size:0.8em; '
                    f'color:var(--text-color); opacity:0.5;">'
                    f'\u2014 Page {page_idx + 1} of {page_count} \u2014</div>'
                    f'<img src="data:image/png;base64,{b64}" '
                    f'style="width:100%; display:block; '
                    f'box-shadow:0 2px 8px rgba(0,0,0,0.15);" />'
                )
            except Exception as page_err:
                img_tags.append(
                    f'<div style="text-align:center; padding:6px 0; font-size:0.8em; '
                    f'color:var(--text-color); opacity:0.5;">'
                    f'\u2014 Page {page_idx + 1} of {page_count} \u2014</div>'
                    f'<div style="width:100%; min-height:200px; '
                    f'border:2px solid #cc3333; background:#fff5f5; padding:20px; '
                    f'text-align:center; color:#cc3333; font-family:sans-serif;">'
                    f'Page {page_idx + 1} failed to render: {page_err}</div>'
                )

            if progress_bar:
                progress_bar.progress(
                    (page_idx + 1) / page_count,
                    text=f"Rendering page {page_idx + 1} of {page_count}..."
                )

    except Exception as e:
        st.error(f"Failed to open PDF: {e}")
        return
    finally:
        if doc:
            doc.close()

    if progress_bar:
        progress_bar.empty()

    html = (
        f'<div style="height:{height}px; overflow-y:auto; background:var(--secondary-background-color); padding:10px; border-radius:6px;">'
        f'<div style="max-width:{target_width}px; margin:0 auto;">'
        + '\n'.join(img_tags)
        + '</div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _expand_to_families(matched_cns: set[str], conn) -> set[str]:
    """Expand a set of control_numbers to include all family-group siblings.

    Reads ``group_id`` from the documents table for each input control_number,
    then unions in every control_number sharing those group_ids. Documents
    with NULL or empty group_id are returned as-is (no expansion possible).
    Caller manages the connection lifecycle.
    """
    if not matched_cns:
        return matched_cns
    placeholders = ",".join("?" * len(matched_cns))
    rows = conn.execute(
        f"SELECT DISTINCT group_id FROM documents "
        f"WHERE control_number IN ({placeholders}) "
        f"  AND group_id IS NOT NULL AND group_id != ''",
        list(matched_cns),
    ).fetchall()
    group_ids = [r['group_id'] for r in rows]
    if not group_ids:
        return matched_cns
    placeholders2 = ",".join("?" * len(group_ids))
    fam_rows = conn.execute(
        f"SELECT control_number FROM documents "
        f"WHERE group_id IN ({placeholders2})",
        group_ids,
    ).fetchall()
    return matched_cns | {r['control_number'] for r in fam_rows}


def _parse_bates(raw_text: str):
    import re
    text = re.sub(r'[\n\r,;&]', ' ', raw_text)
    text = re.sub(r'\band\b', ' ', text, flags=re.IGNORECASE)
    tokens = [t.strip() for t in text.split() if t.strip()]
    
    parsed_bates = set()
    current_prefix = ''
    
    for token in tokens:
        if re.match(r'^[A-Za-z_]+$', token):
            current_prefix = token
            continue
            
        match = re.match(r'^([A-Za-z_]+)?(\d+)(?:-(\d+))?$', token)
        if match:
            prefix, start_num, end_num = match.groups()
            if prefix:
                current_prefix = prefix
            
            if start_num:
                width = len(start_num)
                start_int = int(start_num)
                end_int = int(end_num) if end_num else start_int
                
                if end_int >= start_int and end_int - start_int < 10000:
                    for i in range(start_int, end_int + 1):
                        num_str = str(i).zfill(width)
                        parsed_bates.add(f'{current_prefix}{num_str}')
        else:
            match2 = re.match(r'^([A-Za-z_]+)?(\d+)-([A-Za-z_]+)?(\d+)$', token)
            if match2:
                p1, start_num, p2, end_num = match2.groups()
                p = p1 or p2 or current_prefix
                current_prefix = p
                width = len(start_num)
                start_int = int(start_num)
                end_int = int(end_num)
                if end_int >= start_int and end_int - start_int < 10000:
                    for i in range(start_int, end_int + 1):
                        num_str = str(i).zfill(width)
                        parsed_bates.add(f'{current_prefix}{num_str}')
            else:
                parsed_bates.add(f'{current_prefix}{token}')
                
    return sorted(list(parsed_bates))

def _generate_bates_zip(bulk_cns, target_details, case_folder):
    import fitz
    import zipfile
    import io
    import re
    
    zip_buffer = io.BytesIO()
    bz_conn = db_manager.get_connection(case_folder)
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for cn in bulk_cns:
            if cn not in target_details: continue
            
            row = bz_conn.execute("SELECT begdoc, full_path FROM documents WHERE control_number=?", (cn,)).fetchone()  # db_manager: exempt (review loop)
            if not row or not row['begdoc']: continue
            
            pdf_path = row['full_path']
            if not pdf_path or not pdf_path.lower().endswith('.pdf'):
                continue
                
            try:
                doc = fitz.open(pdf_path)
                try:
                    m = re.match(r'^([A-Za-z_]+)?(\d+)$', row['begdoc'])
                    if not m: continue
                    doc_start = int(m.group(2))

                    for target_bates in target_details[cn]:
                        tm = re.match(r'^([A-Za-z_]+)?(\d+)$', target_bates)
                        if not tm: continue
                        target_num = int(tm.group(2))

                        page_idx = target_num - doc_start
                        if 0 <= page_idx < len(doc):
                            out_pdf = fitz.open()
                            try:
                                out_pdf.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
                                pdf_bytes = out_pdf.write()
                                zf.writestr(f"{target_bates}.pdf", pdf_bytes)
                            finally:
                                out_pdf.close()
                finally:
                    doc.close()
            except Exception as e:
                print(f"Failed to extract from {pdf_path}: {e}")
    bz_conn.close()
    return zip_buffer.getvalue()

# If search query is provided, get matching control numbers from OpenSearch
search_hit_ids = set()
search_highlights = {}

bates_batch_text = st.session_state.get('_bates_batch_text')
# When a Bates batch is active the user has named specific documents to
# retrieve; bypass hygiene view filters (Hide Junk / Hide Not Responsive /
# Show Suppressed) downstream so the grid count matches the banner. Scope
# filters (date, custodian, party, volume, visibility mode) still apply.
_bates_batch_override = bool(bates_batch_text)

if bates_batch_text:
    parsed_bates = _parse_bates(bates_batch_text)

    bz_rows = db_manager.get_all_bates_ranges(case_folder)

    # Pre-parse all DB rows for fast mathematical intersection. Skip any row
    # whose begdoc has no parseable trailing digits — without this guard
    # unparseable tokens collapse to (None, None) and compare equal, so every
    # input matched every row-with-unparseable-Bates (see db_manager.parse_bates_token).
    db_ranges = []
    for r in bz_rows:
        if not r['begdoc']: continue
        p1, n1 = db_manager.parse_bates_token(r['begdoc'])
        if n1 is None: continue
        if r['enddoc']:
            p2, n2 = db_manager.parse_bates_token(r['enddoc'])
            if n2 is None:
                p2, n2 = p1, n1
        else:
            p2, n2 = p1, n1
        if p1 == p2:
            db_ranges.append((r['control_number'], p1, n1, n2))
        else:
            db_ranges.append((r['control_number'], p1, n1, n1))

    # Identify hits crossing over into mid-document ranges
    matched_cns = set()
    bates_hit_details = {} # Map CN to specific target bates hits
    for pb in parsed_bates:
        pp, pn = db_manager.parse_bates_token(pb)
        if pn is None: continue
        for cn, r_p, r_start, r_end in db_ranges:
            if pp == r_p and r_start <= pn <= r_end:
                matched_cns.add(cn)
                if cn not in bates_hit_details:
                    bates_hit_details[cn] = []
                bates_hit_details[cn].append(pb)

    search_hit_ids = matched_cns

    # Family-expansion (📎 Include families in results toggle in the popover)
    _bates_include_fams = bool(st.session_state.get('_bates_batch_include_families', False))
    _bates_family_added = 0
    if _bates_include_fams and matched_cns:
        _fam_conn = db_manager.get_connection(case_folder)
        try:
            _expanded = _expand_to_families(matched_cns, _fam_conn)
        finally:
            _fam_conn.close()
        _bates_family_added = len(_expanded) - len(matched_cns)
        search_hit_ids = _expanded

    st.session_state['bates_hit_details'] = bates_hit_details

    b_col1, b_col2 = st.columns([8, 1])
    if _bates_include_fams and _bates_family_added > 0:
        b_col1.success(
            f"**Bates Batch Search** — extracted {len(parsed_bates)} required pages mathematically. "
            f"Identified {len(matched_cns)} containing documents + {_bates_family_added} family members "
            f"({len(matched_cns) + _bates_family_added} total)."
        )
    else:
        b_col1.success(f"**Bates Batch Search** — extracted {len(parsed_bates)} required pages mathematically. Identified {len(search_hit_ids)} containing documents.")
    if b_col2.button("✖ Clear"):
        del st.session_state['_bates_batch_text']
        if 'bates_hit_details' in st.session_state:
            del st.session_state['bates_hit_details']
        st.session_state.pop('_bates_batch_include_families', None)
        st.rerun()

elif search_query and search_query.strip():
    is_valid, validation_msg = _validate_search_query(search_query.strip())
    if not is_valid:
        st.error(f"⚠️ Invalid query: {validation_msg}")
        search_query = ""
    elif not es:
        st.warning("⚠️ OpenSearch is offline. Start it from the Home page to enable full-text search.")
    else:
        # permission: saved_search_personal
        if auth_manager.has_permission('saved_search_personal'):
            _log_recent(search_query)  # Auto-save to recent history
        db_manager.log_audit(case_folder, "SEARCH_EXECUTED", username=_username, module="Review", details=search_query)
        index_name = os_manager.get_index_name(case_folder)
        os_manager.ensure_highlight_limit(es, index_name)

        try:
            es_query = {
                "query_string": {
                    "query": search_query,
                    "fields": ["content", "file_name", "email_subject", "email_from", "email_to"],
                    "default_operator": "AND",
                    "analyze_wildcard": True,
                    "fuzziness": "AUTO",
                    "allow_leading_wildcard": False
                }
            }

            # Dual-Search: also hit SQLite for Bates numbers / file names
            sqlite_matches = set()
            bz_conn = db_manager.get_connection(case_folder)
            bz_rows = bz_conn.execute(  # db_manager: exempt (dynamic query)
                "SELECT control_number FROM documents WHERE begdoc LIKE ? OR enddoc LIKE ? OR file_name LIKE ?",
                (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%")
            ).fetchall()
            for br in bz_rows:
                sqlite_matches.add(br['control_number'])
                search_hit_ids.add(br['control_number'])
            bz_conn.close()

            # Build ES filter from tree selection
            es_filters = []
            if selected_party != "All Parties":
                if selected_party == "Internal":
                    es_filters.append({"bool": {"should": [
                        {"term": {"source_party.keyword": "Internal"}},
                        {"bool": {"must_not": {"exists": {"field": "source_party"}}}}
                    ]}})
                else:
                    es_filters.append({"term": {"source_party.keyword": selected_party}})
            if selected_custodian:
                es_filters.append({"term": {"custodian.keyword": selected_custodian}})
            if selected_volume:
                es_filters.append({"term": {"production_volume.keyword": selected_volume}})
            if selected_collection:
                es_filters.append({"term": {"source_collection.keyword": selected_collection}})
            if selected_subcollection:
                es_filters.append({"term": {"source_subcollection.keyword": selected_subcollection}})

            if es_filters:
                es_query = {"bool": {"must": [es_query], "filter": es_filters}}

            # --- Attempt search WITH highlighting; fall back to no-highlight on oversized content ---
            _highlight_block = {
                "fields": {"content": {"number_of_fragments": 3, "fragment_size": 150}},
                "pre_tags": ["<mark style='background-color:#ffe066;color:black;border-radius:2px;padding:0 2px'>"],
                "post_tags": ["</mark>"]
            }
            _search_body = {"query": es_query, "highlight": _highlight_block, "size": 500}

            try:
                response = es.search(index=index_name, body=_search_body)
            except Exception as _highlight_err:
                if "max_analyzed_offset" in str(_highlight_err):
                    # Retry without highlighting — results still come back, just no snippets
                    _search_body.pop("highlight", None)
                    response = es.search(index=index_name, body=_search_body)
                    st.toast("⚠️ Some documents exceed the highlight size limit. Search results returned without term highlighting.", icon="⚠️")
                else:
                    raise
            for hit in response['hits']['hits']:
                # Flag #28: cn_from_hit normalizes internal vs inbound _id shapes
                cn = os_manager.cn_from_hit(hit)
                search_hit_ids.add(cn)
                search_highlights[cn] = {
                    'score': hit['_score'],
                    'snippets': hit.get('highlight', {}).get('content', [])
                }

            # Compute pre-expansion content_matches BEFORE family-expansion mutates search_hit_ids.
            content_matches = len(search_hit_ids) - len(sqlite_matches)

            # Family-expansion (📎 Include families toggle below the search bar)
            _search_include_fams = bool(st.session_state.get('search_include_families', False))
            _search_family_added = 0
            if _search_include_fams and search_hit_ids:
                _pre_expand_count = len(search_hit_ids)
                _sf_conn = db_manager.get_connection(case_folder)
                try:
                    search_hit_ids = _expand_to_families(search_hit_ids, _sf_conn)
                finally:
                    _sf_conn.close()
                _search_family_added = len(search_hit_ids) - _pre_expand_count

            if search_hit_ids:
                parts = []
                if content_matches > 0:
                    parts.append(f"{content_matches} content match{'es' if content_matches != 1 else ''}")
                if sqlite_matches:
                    parts.append(f"{len(sqlite_matches)} Bates/filename match{'es' if len(sqlite_matches) != 1 else ''}")
                if _search_include_fams and _search_family_added > 0:
                    parts.append(f"{_search_family_added} family member{'s' if _search_family_added != 1 else ''}")
                st.success(f"**{len(search_hit_ids)} documents** found — {', '.join(parts)}.")
            else:
                st.info("No results found. Try a broader term, wildcard (`settl*`), or fuzzy (`privilege~`).")

        except Exception as e:
            err = str(e)
            if "index_not_found" in err:
                st.warning("⚠️ Index not found — process files in Module 2 first.")
            elif "parse_exception" in err or "query_shard_exception" in err:
                st.error("🔴 OpenSearch could not parse that query. Check syntax (unmatched quotes, bad operators).")
            else:
                st.error(f"Search error: {err}")

# ═══════════════════════════════════════════════════════════════════
# COLUMN PICKER
# ═══════════════════════════════════════════════════════════════════

# All available columns with user-friendly labels
ALL_GRID_COLUMNS = {
    "control_number":    "Control #",
    "begdoc":            "Beg Bates",
    "enddoc":            "End Bates",
    "begatt":            "Beg Attach",
    "endatt":            "End Attach",
    "file_name":         "File Name",
    "file_extension":    "Extension",
    "record_type":       "Doc Type",
    "custodian":         "Custodian",
    "source_party":      "Source Party",
    "processing_status": "Status",
    "email_subject":     "Subject",
    "email_from":        "From",
    "email_to":          "To",
    "author":            "Author",
    "date_sent":         "Date Sent",
    "date_created":      "Date Created",
    "date_modified":     "Date Modified",
    "file_size_kb":      "Size (KB)",
    "page_count":        "Pages",
    "language":          "Language",
    "tags":              "Tags",
    "privilege_status":  "Privilege Disposition",
    "source_collection":    "Collection",
    "source_subcollection": "Subcollection",
    "production_volume": "Volume",
    "production_category": "Prod Category",
    "md5_hash":          "MD5",
}

# Filter-capable columns (subset — only text/date make sense to filter inline)
FILTERABLE_COLS = {
    "control_number", "begdoc", "enddoc", "file_name", "file_extension",
    "record_type", "custodian", "source_party", "processing_status",
    "email_subject", "email_from", "email_to", "author",
    "date_sent", "date_created", "tags", "privilege_status",
    "source_collection", "source_subcollection",
    "production_volume", "production_category", "language",
}

DEFAULT_COLS = [
    "control_number", "begdoc", "enddoc", "file_name", "record_type",
    "custodian", "date_sent", "email_subject", "author", "tags",
    "privilege_status", "processing_status",
]

if "review_grid_columns" not in st.session_state:
    st.session_state["review_grid_columns"] = DEFAULT_COLS

# permission: column_picker
if auth_manager.has_permission('column_picker'):
    with st.expander("🗂️ Configure Columns", expanded=False):
        st.caption("Choose which fields appear in the document grid. Changes apply immediately.")
        col_pick_all, col_pick_reset = st.columns([3, 1])
        selected_cols = col_pick_all.multiselect(
            "Visible Columns (drag to reorder)",
            options=list(ALL_GRID_COLUMNS.keys()),
            default=st.session_state["review_grid_columns"],
            format_func=lambda c: ALL_GRID_COLUMNS.get(c, c),
            key="_col_picker_widget",
            label_visibility="collapsed",
        )
        if col_pick_reset.button("↩ Reset to Default", width='stretch'):
            st.session_state["review_grid_columns"] = DEFAULT_COLS
            st.rerun()
        if selected_cols:
            st.session_state["review_grid_columns"] = selected_cols

active_cols = st.session_state["review_grid_columns"] or DEFAULT_COLS

# ── Per-column Filter Row ────────────────────────────────────────────────────
filter_row_cols  = [c for c in active_cols if c in FILTERABLE_COLS]
col_filters: dict = {}

if filter_row_cols:
    st.markdown(
        "<p style='font-size:0.78rem;color:#aaa;margin:6px 0 2px'>🔍 Column Filters — type below to filter (case-insensitive, supports %wildcard%, type (none) for empty)</p>",
        unsafe_allow_html=True
    )
    filter_ui_cols = st.columns(len(filter_row_cols))
    for i, col_name in enumerate(filter_row_cols):
        val = filter_ui_cols[i].text_input(
            ALL_GRID_COLUMNS.get(col_name, col_name),
            key=f"col_filter_{col_name}",
            placeholder="filter…",
            label_visibility="visible",
        ).strip()
        if val:
            col_filters[col_name] = val

# --- Filter & Sort ---
col_filter, col_sort = st.columns([1, 1])
with col_filter:
    show_suppressed = st.checkbox("Show Suppressed Items (Duplicates & Threads)", value=False, key="show_suppressed_items")
    hide_junk = st.checkbox("Hide Junk Images (<30KB)", value=True, key="hide_junk_images")
    hide_not_responsive = st.checkbox("Hide Not Responsive", value=False, key="hide_not_responsive")
    if _vis_mode != 'produced_only':
        st.checkbox("📋 Produced docs only (Bates-stamped)", value=False, key="filter_produced_only_ux")
with col_sort:
    sort_col = st.selectbox("Sort By", ["Family Group", "control_number", "date_sent", "file_name", "record_type"], index=0, key="sort_column_select")
    sort_asc = st.radio("Order", ["Ascending", "Descending"], horizontal=True, key="sort_order_radio") == "Ascending"

# ── Pagination Controls ──────────────────────────────────────────────────
_PAGE_SIZE_OPTIONS = [10, 15, 25, 50, 100, 200, 500, 1000]
_DEFAULT_PAGE_SIZE = 50

if '_page_size' not in st.session_state:
    st.session_state['_page_size'] = _DEFAULT_PAGE_SIZE
if '_page_number' not in st.session_state:
    st.session_state['_page_number'] = 0

# 1. FETCH & FILTER DATA
conn = db_manager.get_connection(case_folder)
_family_override_gid = st.session_state.get('_family_override_group_id')

# Always SELECT the full set needed for family-sort + row-selection; display cols filtered later
_select_cols = """
    SELECT id, control_number, begdoc, enddoc, begatt, endatt,
           file_name, file_extension, record_type,
           custodian, source_party, processing_status,
           email_subject, email_from, email_to,
           author, date_sent, date_created, date_modified,
           file_size_kb, page_count, language,
           tags, privilege_status, production_volume, production_category,
           md5_hash, source_collection, source_subcollection,
           group_id, parent_id
    FROM documents
"""

query_params = []

# permission: view_shell_documents
_can_view_shells = auth_manager.has_permission('view_shell_documents')
_shell_exclusion = "('Container_Scanned')" if _can_view_shells else "('Container_Scanned', 'Split_Source')"

# Always pop so the key doesn't persist across reruns; only applied in normal mode below
_bl_jump_cn = st.session_state.pop('_bates_lookup_jump_cn', None)
if _bl_jump_cn:
    st.session_state['_page_number'] = 0

if _family_override_gid:
    # Family override mode — show all docs with this group_id,
    # bypassing search and column filters but keeping view-quality filters
    base_query = _select_cols + f"""
        WHERE processing_status NOT IN {_shell_exclusion}
          AND (group_id = ? OR control_number = ?)
    """
    query_params = [_family_override_gid, _family_override_gid]
    search_hit_ids = None  # No search highlighting in family override mode
else:
    base_query = _select_cols + f"""
        WHERE 1=1
            AND processing_status NOT IN {_shell_exclusion}
    """

    if selected_party != "All Parties":
        base_query += " AND (source_party = ? OR (source_party IS NULL AND ? = 'Internal'))"
        query_params.extend([selected_party, selected_party])

    if selected_custodian:
        base_query += " AND custodian = ?"
        query_params.append(selected_custodian)

    if selected_volume:
        base_query += " AND production_volume = ?"
        query_params.append(selected_volume)

    if selected_collection:
        base_query += " AND source_collection = ?"
        query_params.append(selected_collection)

    if selected_subcollection:
        base_query += " AND source_subcollection = ?"
        query_params.append(selected_subcollection)

    # ── Batch filter ──────────────────────────────────────────────────
    if _active_batch_id:
        base_query += " AND control_number IN (SELECT control_number FROM batch_documents WHERE batch_id = ?)"
        query_params.append(_active_batch_id)

    # ── Date range filter ──────────────────────────────────────────
    if _date_from:
        base_query += " AND COALESCE(date_sent, date_created) >= ?"
        query_params.append(str(_date_from))
    if _date_to:
        base_query += " AND COALESCE(date_sent, date_created) <= ?"
        query_params.append(str(_date_to) + ' 23:59:59')

    # Bates Lookup jump: filter grid to a specific control number
    if _bl_jump_cn:
        base_query += " AND control_number = ?"
        query_params.append(_bl_jump_cn)

    if not show_suppressed and not _bates_batch_override:
        base_query += """
            AND processing_status NOT LIKE 'Duplicate%'
            AND (tags IS NULL OR tags NOT LIKE '%Junk%')
            AND (tags IS NULL OR tags NOT LIKE '%Suppressed%')
        """

    # Apply per-column filters to SQL for indexed columns
    for col_name, fval in col_filters.items():
        if col_name not in FILTERABLE_COLS:
            continue  # Defense-in-depth: reject unexpected column names
        # Use LIKE for text matching; wrap with % if no wildcard present
        # Special keyword (none) matches NULL or empty values
        if fval.strip().lower() in ('(none)', '__empty__'):
            base_query += f" AND ({col_name} IS NULL OR {col_name} = '')"
        else:
            pattern = fval if "%" in fval else f"%{fval}%"
            base_query += f" AND COALESCE({col_name}, '') LIKE ?"
            query_params.append(pattern)

# --- Document Visibility Filter (per-user) --- (applies in both normal and family modes)
if _vis_mode == 'produced_only' or _session_produced_only_ux:
    base_query += " AND begdoc IS NOT NULL AND begdoc != ''"
elif _vis_mode == 'hidden_tags' and _vis_hidden_tags:
    # Hide documents carrying ANY of the specified tags.
    # Documents with NULL tags always pass through.
    _tag_clauses = []
    for _ht in _vis_hidden_tags:
        _tag_clauses.append("tags NOT LIKE ?")
        query_params.append(f"%{_ht}%")
    base_query += f" AND (tags IS NULL OR ({' AND '.join(_tag_clauses)}))"

df = pd.read_sql_query(base_query, conn, params=query_params)

if hide_junk and not _family_override_gid and not _bates_batch_override and not df.empty:
    df = df[~df['tags'].str.contains('Junk Image', na=False, case=False)]

if hide_not_responsive and not _family_override_gid and not _bates_batch_override and not df.empty:
    df = df[~df['tags'].str.contains('Not Responsive', na=False, case=False)]

# Cascade tag-based exclusions to children: if a parent was filtered out, hide its
# children too — attachments follow the parent's disposition unless independently reviewed.
if (hide_junk or hide_not_responsive) and not _family_override_gid and not _bates_batch_override and not df.empty and not col_filters:
    _visible_cns = set(df['control_number'].astype(str))
    _excluded_children = df[
        df['parent_id'].notna()
        & (df['parent_id'].astype(str).str.strip() != '')
        & (~df['parent_id'].astype(str).str.strip().isin(_visible_cns))
    ]
    if not _excluded_children.empty:
        # Only cascade if the parent is actually in the DB (not just a missing reference)
        _all_db_cns = set(
            pd.read_sql_query("SELECT control_number FROM documents", conn)['control_number'].astype(str)
        )
        _orphaned_pids = set(_excluded_children['parent_id'].astype(str).str.strip()) & _all_db_cns
        if _orphaned_pids:
            df = df[
                ~(
                    df['parent_id'].astype(str).str.strip().isin(_orphaned_pids)
                    & (~df['control_number'].astype(str).isin(_orphaned_pids))
                )
            ]

# Apply search filter if a query was entered.
# search_hit_ids is populated by EITHER the text-search path (which also
# sets search_query) OR the Bates batch path (which leaves search_query
# empty) — filter on either signal so bates-batch-only searches narrow the grid.
# Family-override mode sets search_hit_ids to None as a skip sentinel (see
# the `_family_override_gid` branch above); guard against that explicitly so
# a bates batch left in session state cannot drive `.isin(None)` when the
# user pivots to Show-Family.
if ((search_query and search_hit_ids) or bates_batch_text) and not _family_override_gid:
    df = df[df['control_number'].isin(search_hit_ids)]
    st.session_state['_page_number'] = 0

if not df.empty:
    if sort_col == "Family Group":
        # Hierarchical Lineage Sort Logic
        hierarchy_df = pd.read_sql_query("SELECT control_number, parent_id FROM documents", conn)
        parent_map = dict(zip(hierarchy_df['control_number'], hierarchy_df['parent_id']))

        def get_lineage(cn):
            path = [str(cn)]
            curr = cn
            visited = set()
            while curr in parent_map and pd.notna(parent_map[curr]) and str(parent_map[curr]).strip() != '':
                parent = str(parent_map[curr]).strip()
                if parent in visited: break
                visited.add(parent)
                path.insert(0, parent)
                curr = parent
            return "/".join(path)

        df['_sort_lineage'] = df['control_number'].apply(get_lineage)
        df = df.sort_values(by=['_sort_lineage'], ascending=[True])
    else:
        df = df.sort_values(by=sort_col, ascending=sort_asc)

conn.close()

# 2. VISUAL INDENTATION LOGIC
_visible_cns = set(df['control_number'].tolist()) if not df.empty else set()

def format_hierarchy(row):
    """Indent only when the immediate parent is visible in the current grid."""
    if '_sort_lineage' in row and pd.notna(row['_sort_lineage']):
        lineage_parts = str(row['_sort_lineage']).split('/')
        if len(lineage_parts) > 1:
            immediate_parent_cn = lineage_parts[-2]
            if immediate_parent_cn in _visible_cns:
                depth = len(lineage_parts) - 1
                return (depth * "    ") + "↳ " + str(row['file_name'])
    return str(row['file_name'])

# ── Family Override Banner (always rendered, even on empty results) ──────────
if st.session_state.get('_family_override_group_id'):
    _fam_cols = st.columns([5, 2])
    with _fam_cols[0]:
        st.info(f"Showing all documents in family group `{st.session_state['_family_override_group_id']}`")
    with _fam_cols[1]:
        if st.button("← Back to search results", key="_exit_family_override", type="primary", width='stretch'):
            _prev = st.session_state.pop('_pre_family_search_state', None)
            st.session_state.pop('_family_override_group_id', None)
            st.session_state['_page_number'] = 0
            if _prev:
                # Can't write to widget keys after they've rendered — stash for next rerun
                st.session_state['_pending_search_restore'] = _prev
            st.rerun()

if not df.empty:
    queue_list = df['control_number'].tolist()

    # ── Pagination calculation ────────────────────────────────────────────
    _page_size = st.session_state.get('_page_size', _DEFAULT_PAGE_SIZE)
    _total_docs = len(queue_list)
    _total_pages = max(1, (_total_docs + _page_size - 1) // _page_size)

    # Clamp page number to valid range (filters may have reduced the result set)
    _page_number = st.session_state.get('_page_number', 0)
    _page_number = max(0, min(_page_number, _total_pages - 1))
    st.session_state['_page_number'] = _page_number

    # ── Auto-flip page to match viewer's current document ─────────────────
    # Only auto-flip when the VIEWER document changed (e.g., sidebar tree click),
    # not when the user is manually navigating grid pages. Track the last viewer
    # index to detect viewer-initiated changes vs grid-pagination changes.
    _viewer_idx = st.session_state.get('current_doc_idx', 0)
    _prev_viewer_idx = st.session_state.get('_grid_last_viewer_idx', -1)
    if 0 <= _viewer_idx < _total_docs and _viewer_idx != _prev_viewer_idx:
        _viewer_page = _viewer_idx // _page_size
        if _viewer_page != _page_number:
            st.session_state['_page_number'] = _viewer_page
            _page_number = _viewer_page
    st.session_state['_grid_last_viewer_idx'] = _viewer_idx

    _page_start = _page_number * _page_size
    _page_end = min(_page_start + _page_size, _total_docs)

    # ── Batch progress banner ────────────────────────────────────────────
    if _active_batch_id:
        _bp_conn = db_manager.get_connection(case_folder)
        _bp_info = _bp_conn.execute(  # db_manager: exempt (batch status update)
            "SELECT batch_name, doc_count FROM review_batches WHERE id = ?",
            (_active_batch_id,)
        ).fetchone()
        _bp_reviewed = _bp_conn.execute("""  -- db_manager: exempt (batch status update)
            SELECT COUNT(*) FROM batch_documents bd
            JOIN documents d ON bd.control_number = d.control_number
            WHERE bd.batch_id = ? AND d.reviewed_by IS NOT NULL
        """, (_active_batch_id,)).fetchone()[0]
        _bp_conn.close()
        if _bp_info:
            _bp_pct = round((_bp_reviewed / _bp_info['doc_count'] * 100) if _bp_info['doc_count'] > 0 else 0)
            st.progress(_bp_pct / 100, text=f"📦 {_bp_info['batch_name']}: {_bp_reviewed:,} / {_bp_info['doc_count']:,} reviewed ({_bp_pct}%)")

    # Format the df for display but keep the original queue
    disp_df = df.copy()
    if '_sort_lineage' in disp_df.columns:
        disp_df['file_name'] = disp_df.apply(format_hierarchy, axis=1)
        disp_df = disp_df.drop(columns=['_sort_lineage'])
    else:
        disp_df['file_name'] = disp_df.apply(format_hierarchy, axis=1)

    # Strip system tags from the Tags display column — these are analytics/dedup
    # artifacts that clutter the reviewer's view. They remain in the DB untouched.
    _SYS_TAG_PREFIXES = ("NearDupe-", "Thread-", "NIST-", "Junk ", "Inclusive-")
    _SYS_TAG_EXACT = {"Inclusive"}

    def _clean_tags_for_display(tag_str):
        """Remove system tags from display, keep user-meaningful tags only."""
        if not tag_str or pd.isna(tag_str):
            return ''
        tags = [t.strip() for t in str(tag_str).replace(';', ',').split(',') if t.strip()]
        user_tags = [
            t for t in tags
            if not any(t.startswith(p) for p in _SYS_TAG_PREFIXES)
            and t not in _SYS_TAG_EXACT
        ]
        return ', '.join(user_tags)

    if 'tags' in disp_df.columns:
        disp_df['tags'] = disp_df['tags'].apply(_clean_tags_for_display)

    # Human-friendly privilege disposition display
    if 'privilege_status' in disp_df.columns:
        disp_df['privilege_status'] = disp_df['privilege_status'].map({
            'Redact': '✏️ Redact',
            'Withhold': '🚫 Withhold',
        }).fillna('')

    # Inbound-production badge on source_party column (beta-2.10 Commit 4):
    # visual cue so reviewers recognize inbound docs at a glance. The underlying
    # value is the opposing-counsel party name; we prepend 📥 and leave
    # Internal / NULL rows blank so internal docs stay visually quiet.
    if 'source_party' in disp_df.columns:
        def _badge_source_party(val):
            if _is_inbound_doc(val):
                return f"📥 {val}"
            return ''
        disp_df['source_party'] = disp_df['source_party'].apply(_badge_source_party)

    # Trim to only the user-selected columns (plus internal ones needed for selection)
    internal_cols = {'id', 'parent_id', 'group_id'}  # kept for logic, dropped from display
    display_col_list = [c for c in active_cols if c in disp_df.columns]
    disp_df = disp_df[display_col_list + [c for c in internal_cols if c in disp_df.columns]]

    # Rename columns for display
    rename_map = {k: v for k, v in ALL_GRID_COLUMNS.items() if k in disp_df.columns}
    disp_df = disp_df.rename(columns=rename_map)
    # Drop internal helper cols for display
    disp_df = disp_df.drop(columns=[c for c in ['id', 'parent_id', 'group_id'] if c in disp_df.columns])

    # ── Slice for pagination ──────────────────────────────────────────────
    # Keep full disp_df available for CSV export; slice only for grid display
    _full_disp_df = disp_df  # Reference to full set (used by CSV export)
    disp_df = disp_df.iloc[_page_start:_page_end].reset_index(drop=True)

    # Display the refined grid with interactive row selection
    grid_header_col, pdf_col, csv_col = st.columns([3, 1, 1])
    grid_header_col.markdown("### 🗂️ Document Grid")
    # Visibility restriction banner — shown when admin has configured a non-default mode.
    # Does NOT reveal which specific tags are hidden (work-product concern).
    if _vis_mode == 'produced_only':
        st.caption("🔒 Your view is restricted to produced (Bates-stamped) documents.")
    elif _vis_mode == 'hidden_tags' and _vis_hidden_tags:
        _hidden_count = len(_vis_hidden_tags)
        st.caption(
            f"🔒 {_hidden_count} tag categor{'ies are' if _hidden_count != 1 else 'y is'} "
            f"hidden from your view by administrator policy."
        )
    # permission: export_csv
    if auth_manager.has_permission('export_csv'):
        csv_export = _full_disp_df.to_csv(index=False).encode('utf-8')
        csv_col.download_button(
            label="⬇️ Export CSV",
            data=csv_export,
            file_name=f"{os.path.basename(case_folder)}_review_export.csv",
            mime="text/csv",
            help="Downloads the current filtered view as a CSV spreadsheet",
            width='stretch',
        )
    # Reserve space for the export popover — rendered AFTER the dataframe updates
    # bulk_selected_cns so the count is always in sync with the actual selection.
    # permission: export_pdf (full source options) or download_produced (produced docs only)
    _pdf_export_placeholder = pdf_col.empty() if (auth_manager.has_permission('export_pdf') or auth_manager.has_permission('download_produced')) else None

    if 'pending_pdf_zip' in st.session_state and (auth_manager.has_permission('export_pdf') or auth_manager.has_permission('download_produced')):
        _pdf_errors = st.session_state.get('pending_pdf_zip_errors', [])
        if _pdf_errors:
            st.warning(f"{len(_pdf_errors)} document(s) could not be packaged and were skipped.")
            with st.expander("View errors"):
                st.dataframe(_pdf_errors)
        _pdf_count = st.session_state.get('pending_pdf_zip_count', 0)
        st.download_button(
            label=f"⬇️ Download PDF ZIP ({_pdf_count} docs)",
            data=st.session_state['pending_pdf_zip'],
            file_name=f"PDF_Export_{_pdf_count}_docs.zip",
            mime="application/zip",
            key="download_pdf_zip_grid",
            width='stretch',
            on_click=lambda: [
                st.session_state.pop('pending_pdf_zip', None),
                st.session_state.pop('pending_pdf_zip_count', None),
                st.session_state.pop('pending_pdf_zip_errors', None),
            ],
        )

    # ── Family Group Visualization toggle ───────────────────────────────────
    # permission: column_picker
    _fv_enabled = False
    if auth_manager.has_permission('column_picker'):
        _fv_enabled = st.checkbox(
            "👪 Family View",
            value=st.session_state.get('_family_view_on', False),
            help="Renders parent documents as collapsible expanders containing their attachments. Disabled for bulk-action selection.",
            key="_family_view_toggle",
        )
        st.session_state['_family_view_on'] = _fv_enabled

    # ── Pagination Navigation Bar ────────────────────────────────────────
    if not _fv_enabled:
        _pg_info_col, _pg_size_col, _pg_nav_col = st.columns([3, 2, 4])
        with _pg_info_col:
            st.caption(f"Showing {_page_start + 1}–{_page_end} of {_total_docs} documents")
        with _pg_size_col:
            _new_page_size = st.selectbox(
                "Rows per page",
                options=_PAGE_SIZE_OPTIONS,
                index=_PAGE_SIZE_OPTIONS.index(st.session_state['_page_size']),
                key="_page_size_selector",
                label_visibility="collapsed",
            )
            if _new_page_size != st.session_state['_page_size']:
                st.session_state['_page_size'] = _new_page_size
                st.session_state['_page_number'] = 0
                st.rerun()

        with _pg_nav_col:
            _nav_cols = st.columns([1, 1, 2, 1, 1])
            with _nav_cols[0]:
                if st.button("⏮", key="_pg_first", disabled=(_page_number == 0), width='stretch', help="First page"):
                    st.session_state['_page_number'] = 0
                    st.rerun()
            with _nav_cols[1]:
                if st.button("◀", key="_pg_prev", disabled=(_page_number == 0), width='stretch', help="Previous page"):
                    st.session_state['_page_number'] = _page_number - 1
                    st.rerun()
            with _nav_cols[2]:
                st.markdown(
                    f"<div style='text-align:center;padding-top:6px;font-size:0.9em;'>Page {_page_number + 1} of {_total_pages}</div>",
                    unsafe_allow_html=True,
                )
            with _nav_cols[3]:
                if st.button("▶", key="_pg_next", disabled=(_page_number >= _total_pages - 1), width='stretch', help="Next page"):
                    st.session_state['_page_number'] = _page_number + 1
                    st.rerun()
            with _nav_cols[4]:
                if st.button("⏭", key="_pg_last", disabled=(_page_number >= _total_pages - 1), width='stretch', help="Last page"):
                    st.session_state['_page_number'] = _total_pages - 1
                    st.rerun()

    if _fv_enabled:
        # Build parent→children map from the current filtered dataframe
        _fv_children_of: dict = {}   # root_cn → [child rows]
        _fv_standalone: list = []    # rows with no parent and no children
        _fv_child_cns: set = set()

        _fv_parent_ids = set(df['parent_id'].dropna().astype(str).str.strip()) - {''}
        _fv_cn_to_row  = {str(r['control_number']): r for _, r in df.iterrows()}

        # Identify container-origin parents (PST/ZIP with Container_Scanned status).
        # These are archive containers, not document families — their parent_id
        # represents extraction origin, not a reviewable family relationship.
        _fv_container_cns: set = set()
        if 'processing_status' in df.columns:
            _fv_container_cns = set(
                df.loc[df['processing_status'] == 'Container_Scanned', 'control_number'].astype(str)
            )
        # Also check the DB for container parents not in the current df
        _fv_db_container_cns = set()
        try:
            _fv_cont_rows = conn.execute(  # db_manager: exempt (dynamic query)
                "SELECT control_number FROM documents WHERE processing_status = 'Container_Scanned'"
            ).fetchall()
            _fv_db_container_cns = {str(r['control_number']) for r in _fv_cont_rows}
        except Exception:
            pass
        _fv_all_containers = _fv_container_cns | _fv_db_container_cns

        # Collect all parent_ids from the DB for children in the current view
        # so we can identify "ghost parents" — parents filtered out of the current df.
        _fv_ghost_children: dict = {}  # parent_cn → [child rows] where parent not in df

        for _, _fv_row in df.iterrows():
            _pid = str(_fv_row.get('parent_id') or '').strip()
            # Skip container-origin parent_ids — treat these children as roots/standalone
            if _pid and _pid in _fv_all_containers:
                continue  # child of PST/ZIP — not a family relationship
            if _pid and _pid in _fv_cn_to_row:
                _fv_children_of.setdefault(_pid, []).append(_fv_row)
                _fv_child_cns.add(str(_fv_row['control_number']))
            elif _pid and _pid not in _fv_cn_to_row:
                # Parent exists in DB but is filtered out of current view
                _fv_ghost_children.setdefault(_pid, []).append(_fv_row)
                _fv_child_cns.add(str(_fv_row['control_number']))

        _fv_display_cols = [c for c in ['control_number', 'file_name', 'date_sent', 'custodian', 'tags'] if c in df.columns]
        _fv_rename = {k: v for k, v in ALL_GRID_COLUMNS.items() if k in _fv_display_cols}

        _fv_roots    = [r for _, r in df.iterrows() if str(r['control_number']) not in _fv_child_cns and str(r['control_number']) in _fv_children_of]
        _fv_orphans  = [r for _, r in df.iterrows() if str(r['control_number']) not in _fv_child_cns and str(r['control_number']) not in _fv_children_of]

        st.markdown(f"### 👪 Family View &nbsp;<span style='font-size:0.8em;color:#aaa;'>({len(_fv_roots)} families &bull; {len(_fv_ghost_children)} filtered-parent groups &bull; {len(_fv_orphans)} standalone docs)</span>", unsafe_allow_html=True)

        if _fv_roots:
            for _fv_root in _fv_roots:
                _cn  = str(_fv_root['control_number'])
                _fn  = str(_fv_root.get('file_name') or _cn)
                _tag = str(_fv_root.get('tags') or '')
                _kids = _fv_children_of.get(_cn, [])
                _label = f"📧 {_fn} &nbsp;·&nbsp; `{_cn}`  —  {len(_kids)} attachment{'s' if len(_kids) != 1 else ''}"
                with st.expander(_label, expanded=False):
                    # Parent row summary
                    _p_date = str(_fv_root.get('date_sent') or '')[:10]
                    _p_cust = str(_fv_root.get('custodian') or '')
                    st.caption(f"📅 {_p_date} &nbsp;&nbsp; 👤 {_p_cust} &nbsp;&nbsp; 🏷️ {_tag}")
                    st.markdown("**Attachments:**")
                    # Children sub-table
                    _kid_df = pd.DataFrame([dict(k) for k in _kids])[_fv_display_cols].rename(columns=_fv_rename)
                    st.dataframe(_kid_df, width='stretch', hide_index=True)
                    # Jump button for parent
                    if st.button(f"Open {_cn} in viewer", key=f"_fv_open_{_cn}"):
                        _fv_idx = queue_list.index(_cn) if _cn in queue_list else 0
                        st.session_state.current_doc_idx = _fv_idx
                        st.session_state['_family_view_on'] = False
                        st.rerun()

        # Ghost-parent groups: children whose parent was filtered out of the current view
        if _fv_ghost_children:
            for _ghost_pid, _ghost_kids in sorted(_fv_ghost_children.items()):
                _glabel = f"📎 Attachments of `{_ghost_pid}` *(parent filtered out)*  —  {len(_ghost_kids)} item{'s' if len(_ghost_kids) != 1 else ''}"
                with st.expander(_glabel, expanded=False):
                    st.caption(f"Parent document `{_ghost_pid}` is not visible in the current filter. Showing its attachments only.")
                    # Build sub-families within the ghost group (email→attachment nesting)
                    _ghost_cn_set = {str(k['control_number']) for k in _ghost_kids}
                    _ghost_sub_parents = {}   # cn → [child rows] within this ghost group
                    _ghost_sub_child_cns = set()
                    for _gk in _ghost_kids:
                        _gk_pid = str(_gk.get('parent_id') or '').strip()
                        _gk_cn = str(_gk['control_number'])
                        # Check if this child's parent is another child in the same ghost group
                        if _gk_pid in _ghost_cn_set and _gk_pid != _ghost_pid:
                            _ghost_sub_parents.setdefault(_gk_pid, []).append(_gk)
                            _ghost_sub_child_cns.add(_gk_cn)
                    if _ghost_sub_parents:
                        # Render sub-families: top-level items first, then nested
                        _ghost_tops = [k for k in _ghost_kids if str(k['control_number']) not in _ghost_sub_child_cns]
                        for _gt in _ghost_tops:
                            _gt_cn = str(_gt['control_number'])
                            _gt_fn = str(_gt.get('file_name') or _gt_cn)
                            _gt_subs = _ghost_sub_parents.get(_gt_cn, [])
                            if _gt_subs:
                                st.markdown(f"**{_gt_fn}** (`{_gt_cn}`) — {len(_gt_subs)} attachment{'s' if len(_gt_subs) != 1 else ''}")
                                _gt_sub_df = pd.DataFrame([dict(s) for s in _gt_subs])[_fv_display_cols].rename(columns=_fv_rename)
                                st.dataframe(_gt_sub_df, width='stretch', hide_index=True)
                            else:
                                st.markdown(f"**{_gt_fn}** (`{_gt_cn}`)")
                    else:
                        # Flat group — no sub-families
                        _ghost_df = pd.DataFrame([dict(k) for k in _ghost_kids])[_fv_display_cols].rename(columns=_fv_rename)
                        st.dataframe(_ghost_df, width='stretch', hide_index=True)

        if _fv_orphans:
            with st.expander(f"📄 Standalone Documents ({len(_fv_orphans)})", expanded=len(_fv_roots) == 0 and len(_fv_ghost_children) == 0):
                _orp_df = pd.DataFrame([dict(r) for r in _fv_orphans])[_fv_display_cols].rename(columns=_fv_rename)
                st.dataframe(_orp_df, width='stretch', hide_index=True)

        # In family view, disable grid-based viewer selection
        selected_rows = []
        st.session_state.bulk_selected_cns = []
    else:
        # ── Normal flat grid ─────────────────────────────────────────────────
        event = st.dataframe(disp_df, width='stretch', hide_index=True, on_select="rerun", selection_mode="multi-row", height=910)

        selected_rows = event.selection.rows
        if len(selected_rows) == 1:
            # Single selection → drive the three-pane viewer.
            # Skip if a family-button navigation just fired (it already set
            # current_doc_idx or entered peek mode). Without this guard,
            # Streamlit's st.dataframe persists its selection across reruns,
            # so after a paperclip click the grid handler re-fires with the
            # stale selection and stomps the freshly-set _peek_cn before the
            # viewer reads it — leaving the user on the original doc instead
            # of the peeked attachment.
            if not st.session_state.pop('family_nav', False):
                st.session_state.current_doc_idx = _page_start + selected_rows[0]
                # Grid click exits peek mode — user is explicitly navigating in the queue
                st.session_state.pop('_peek_cn', None)
                st.session_state.pop('_peek_return_idx', None)
            st.session_state.bulk_selected_cns = []
        elif len(selected_rows) > 1:
            # Multi-selection → store the selected control numbers for bulk action
            st.session_state.bulk_selected_cns = [
                queue_list[_page_start + i] for i in selected_rows
                if (_page_start + i) < len(queue_list)
            ]
            # Drive the viewer to the last selected row so the detail pane
            # remains visible below the bulk actions panel
            st.session_state.current_doc_idx = _page_start + selected_rows[-1]
        else:
            st.session_state.bulk_selected_cns = []

    # --- Deferred PDF Export Popover ---
    # Rendered here (after the dataframe event handler) so bulk_selected_cns reflects
    # the CURRENT selection. This eliminates the N-1 count mismatch.
    if _pdf_export_placeholder is not None:
        _pdf_pre_bulk = st.session_state.get('bulk_selected_cns', [])
        # Single-click drives the viewer (bulk_selected_cns is empty), so fall back
        # to the currently-viewed document when no bulk selection exists.
        if not _pdf_pre_bulk and len(selected_rows) == 1 and queue_list:
            _current_idx = st.session_state.get('current_doc_idx', 0)
            if 0 <= _current_idx < len(queue_list):
                _pdf_pre_bulk = [queue_list[_current_idx]]
        _has_selection = len(_pdf_pre_bulk) >= 1
        with _pdf_export_placeholder:
            with st.popover("📥 Export PDFs", width='stretch'):
                # Scope selector — only shown when rows are checked
                if _has_selection:
                    _scope_opts = [
                        f"Export selected ({len(_pdf_pre_bulk)} document{'s' if len(_pdf_pre_bulk) != 1 else ''})",
                        f"Export all filtered ({len(queue_list)} documents)",
                    ]
                    _scope_choice = st.radio(
                        "Export scope",
                        _scope_opts,
                        index=0,
                        key="pdf_exp_grid_scope",
                    )
                    _export_cns = _pdf_pre_bulk if _scope_choice == _scope_opts[0] else queue_list
                else:
                    st.caption(f"Export all {len(queue_list)} filtered documents as PDFs")
                    _export_cns = queue_list

                if len(_export_cns) > 1000:
                    st.warning(f"Large export ({len(_export_cns)} documents) — this may take several minutes.")
                # permission: export_pdf allows all sources; download_produced restricts to produced only
                if auth_manager.has_permission('export_pdf'):
                    file_source_grid = st.radio(
                        "File source",
                        ["Processed (imaged PDF)", "Native file", "Produced (Bates-stamped)"],
                        index=0,
                        help="Which version of each document to include in the ZIP",
                        horizontal=True,
                        key="pdf_exp_grid_source",
                    )
                else:
                    file_source_grid = "Produced (Bates-stamped)"
                    if _vis_mode == 'produced_only' or _session_produced_only_ux:
                        # Grid already filtered to produced docs — no additional check needed
                        st.caption("📦 Source: Produced (Bates-stamped)")
                    else:
                        # User has download_produced but sees full universe or hidden_tags mode.
                        # They may have selected unproduced docs — pre-filter to produced only.
                        _produced_conn = db_manager.get_connection(case_folder)
                        _produced_check = set()
                        for _pc_i in range(0, len(_export_cns), 900):
                            _pc_batch = _export_cns[_pc_i:_pc_i + 900]
                            _pc_phs = ','.join(['?'] * len(_pc_batch))
                            _pc_rows = _produced_conn.execute(  # db_manager: exempt (dynamic query)
                                f"SELECT control_number FROM documents "
                                f"WHERE control_number IN ({_pc_phs}) "
                                f"AND begdoc IS NOT NULL AND begdoc != ''",
                                _pc_batch
                            ).fetchall()
                            _produced_check.update(r['control_number'] for r in _pc_rows)
                        _produced_conn.close()

                        _produced_count = len(_produced_check)
                        _total_selected = len(_export_cns)

                        if _produced_count == 0:
                            st.warning(
                                f"⚠️ 0 of {_total_selected} selected document"
                                f"{'s have' if _total_selected != 1 else ' has'} "
                                f"been produced. Run Production (Module 5) first."
                            )
                        elif _produced_count < _total_selected:
                            st.info(
                                f"📦 {_produced_count} of {_total_selected} selected have been produced. "
                                f"Only produced documents will be included."
                            )
                            _export_cns = [cn for cn in _export_cns if cn in _produced_check]
                        else:
                            st.caption(f"📦 Source: Produced (Bates-stamped) — all {_produced_count} available")
                _naming_opts = _get_pdf_naming_options(case_folder)
                naming_field_grid = st.selectbox(
                    "Name files by",
                    _naming_opts,
                    index=0,
                    format_func=_fmt_pdf_naming,
                    help="Which metadata field to use as the PDF filename in the ZIP",
                    key="pdf_exp_grid_naming",
                )
                gc_a, gc_b, gc_c = st.columns(3)
                append_ext_grid = gc_a.checkbox("Append file extension", value=False, key="pdf_exp_grid_ext")
                prefix_seq_grid = gc_b.checkbox("Sequential prefix", value=False, key="pdf_exp_grid_seq")
                combine_fam_grid = gc_c.checkbox(
                    "Combine families",
                    value=False,
                    key="pdf_exp_grid_fam",
                    help="Merges selected members of each document family into one PDF. Only the documents in the current filtered view are combined.",
                )
                _can_generate = len(_export_cns) > 0
                if st.button("Generate ZIP", type="primary", key="gen_pdf_zip_grid", disabled=not _can_generate):
                    source_map_grid = {
                        "Processed (imaged PDF)": "processed",
                        "Native file": "native",
                        "Produced (Bates-stamped)": "produced",
                    }
                    fsk_grid = source_map_grid[file_source_grid]
                    with st.spinner(f"Packaging {len(_export_cns)} documents…"):
                        zip_bytes_g, export_errors_g = pdf_exporter.export_pdfs_to_zip(
                            case_folder=case_folder,
                            control_numbers=_export_cns,
                            file_source=fsk_grid,
                            naming_field=naming_field_grid,
                            append_extension=append_ext_grid,
                            prefix_sequential=prefix_seq_grid,
                            combine_families=combine_fam_grid,
                        )
                    exported_count_g = len(_export_cns) - len(export_errors_g)
                    db_manager.log_audit(
                        case_folder, "PDF_EXPORTED", username=_username, module="Review",
                        details=f"{exported_count_g} docs exported as ZIP (grid) | scope={'selected' if _has_selection and _export_cns is _pdf_pre_bulk else 'filtered'} | source={fsk_grid} | naming={naming_field_grid} | families={combine_fam_grid}",
                    )
                    st.session_state['pending_pdf_zip'] = zip_bytes_g
                    st.session_state['pending_pdf_zip_count'] = exported_count_g
                    st.session_state['pending_pdf_zip_errors'] = export_errors_g
                    st.rerun()

else:
    queue_list = []

# --- BULK ACTION BAR ---
# Shown when 2+ rows are selected; replaces the three-pane viewer
if not queue_list:
    st.info("No documents found matching the current filters.")
    st.stop()

bulk_cns = st.session_state.get('bulk_selected_cns', [])
# Validate that bulk_cns still exist in current queue (filters may have changed)
bulk_cns = [cn for cn in bulk_cns if cn in queue_list]

if len(bulk_cns) >= 2:
    st.write("---")
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5986 100%);
                    border-radius: 10px; padding: 16px 20px; margin-bottom: 12px;
                    border-left: 4px solid #4a9eff;">
            <span style="color: #4a9eff; font-size: 1.1em; font-weight: 700;">⚡ Bulk Action Mode</span>
            <span style="color: #cce4ff; margin-left: 12px;">{len(bulk_cns)} documents selected</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    # permission: tag — Apply/Clear Tag only shown to users with tag permission;
    # Cancel and Bates Extract remain available to all users in bulk mode.
    _can_tag = auth_manager.has_permission('tag')
    _bulk_cats = db_manager.get_tag_categories(case_folder) if _can_tag else {}
    tag_options_bulk = [m for cat in _bulk_cats.values() for m in cat.get('members', [])]

    with st.form("bulk_tag_form"):
        if _can_tag:
            st.caption("Select a tag to apply to all selected documents:")
            # We use a selectbox so the form can be submitted with a single chosen action
            chosen_tag = st.selectbox(
                "Tag to apply",
                options=[""] + tag_options_bulk,
                format_func=lambda x: "— Choose a tag —" if x == "" else x,
                key="bulk_tag_apply_select"
            )
            # Check if selected tag belongs to a privilege category
            _bulk_is_priv_tag = any(
                chosen_tag in cat_data.get('members', [])
                for cat_data in _bulk_cats.values()
                if cat_data.get('is_privilege')
            )
            _bulk_disp_choice = None
            if _bulk_is_priv_tag and chosen_tag:
                st.markdown(
                    "<span style='color:#ff6b6b; font-size:0.78em; font-weight:700; "
                    "text-transform:uppercase; letter-spacing:0.08em;'>"
                    "▸ Privilege Disposition</span>",
                    unsafe_allow_html=True
                )
                _bulk_disp_options = [
                    "Withhold (exclude from production)",
                    "Redact (produce with redactions)"
                ]
                _bulk_disp_choice = st.radio(
                    "Bulk Privilege Disposition",
                    options=_bulk_disp_options,
                    index=0,  # Withhold default for document-level bulk determination
                    label_visibility="collapsed",
                    key="bulk_priv_disp_radio"
                )
        else:
            chosen_tag = ""
            _bulk_is_priv_tag = False
            _bulk_disp_choice = None
        # --- Privilege conflict detection (pre-scan on render) ---
        _bulk_conflict_cns = []
        _bulk_unset_cns = []
        _bulk_match_cns = []
        if _bulk_is_priv_tag and chosen_tag and _bulk_disp_choice:
            _bulk_disp_val = 'Withhold' if 'Withhold' in _bulk_disp_choice else 'Redact'
            for _pc_cn in bulk_cns:
                _pc_existing = db_manager.get_privilege_status(case_folder, _pc_cn)
                if _pc_existing is None:
                    _bulk_unset_cns.append(_pc_cn)
                elif _pc_existing != _bulk_disp_val:
                    _bulk_conflict_cns.append((_pc_cn, _pc_existing))
                else:
                    _bulk_match_cns.append(_pc_cn)

        _has_priv_conflicts = bool(_bulk_conflict_cns)

        # Show conflict warning if applicable
        if _has_priv_conflicts:
            st.warning(
                f"**Disposition conflict:** {len(_bulk_conflict_cns)} of {len(bulk_cns)} "
                f"selected document(s) already have a different disposition:\n\n"
                + "\n".join(f"- **{cn}**: currently {disp}" for cn, disp in _bulk_conflict_cns[:10])
                + (f"\n- ...and {len(_bulk_conflict_cns) - 10} more" if len(_bulk_conflict_cns) > 10 else "")
            )

        # --- Action buttons ---
        if _has_priv_conflicts:
            action_cols = st.columns([1, 1, 1, 1])
            if _can_tag:
                btn_override = action_cols[0].form_submit_button(
                    f"Override All → {_bulk_disp_val}", type="primary", width='stretch')
                btn_unset_only = action_cols[1].form_submit_button(
                    f"Apply to {len(_bulk_unset_cns)} Unset Only", width='stretch')
                btn_clear = False
                btn_apply = False
                btn_cancel = action_cols[2].form_submit_button("✖ Cancel", width='stretch')
            else:
                btn_override = btn_unset_only = btn_apply = btn_clear = False
                btn_cancel = action_cols[0].form_submit_button("✖ Cancel", width='stretch')
        else:
            btn_override = False
            btn_unset_only = False
            action_cols = st.columns([1, 1, 1, 2])
            if _can_tag:
                btn_apply = action_cols[0].form_submit_button("✅ Apply Tag", type="primary", width='stretch')
                btn_clear = action_cols[1].form_submit_button("🗑️ Clear All Tags", width='stretch')
                btn_cancel = action_cols[2].form_submit_button("✖ Cancel", width='stretch')
            else:
                btn_apply = btn_clear = False
                btn_cancel = action_cols[0].form_submit_button("✖ Cancel", width='stretch')

        btn_extract = False
        if 'bates_hit_details' in st.session_state:
            _extract_col = action_cols[3] if not _has_priv_conflicts else action_cols[3]
            btn_extract = _extract_col.form_submit_button("📑 Extract Exact Pages & ZIP", width='stretch')
        elif not _has_priv_conflicts:
            action_cols[3].empty()

        if btn_extract:
            with st.spinner("Extracting specified pages from PDFs..."):
                zip_bytes = _generate_bates_zip(bulk_cns, st.session_state['bates_hit_details'], case_folder)
                if zip_bytes:
                    st.session_state['pending_bates_zip'] = zip_bytes
                else:
                    st.warning("No PDF pages could be extracted. Are these native non-PDF files?")

        if btn_cancel:
            st.session_state.bulk_selected_cns = []
            st.rerun()

        # Determine apply mode based on which button was pressed
        _do_apply = False
        _apply_mode = 'all'  # 'all' = normal or override, 'unset_only' = skip conflicts
        if btn_apply:
            _do_apply = True
            _apply_mode = 'all'
        elif btn_override:
            _do_apply = True
            _apply_mode = 'all'
        elif btn_unset_only:
            _do_apply = True
            _apply_mode = 'unset_only'

        if _do_apply:
            if _case_closed:
                st.warning("Write operations are disabled on closed matters.")
            elif not chosen_tag:
                st.warning("Please choose a tag to apply.")
            else:
                # CRIT-5: Route bulk-apply through _safe_write
                # beta-2.10 Commit 4: tag writes apply to ALL bulk docs (inbound
                # included); privilege disposition writes skip inbound docs —
                # privilege on opposing counsel's production is meaningless.
                _bulk_audit = []
                _bulk_inbound_skipped = []
                def _bulk_apply_op():
                    _conn = db_manager.get_connection(case_folder)
                    for cn in bulk_cns:
                        _row = _conn.execute(
                            "SELECT tags, source_party FROM documents WHERE control_number=?",
                            (cn,)
                        ).fetchone()  # db_manager: exempt (review loop)
                        _old = _row['tags'] or ''
                        _tags = [t.strip() for t in _old.replace(';', ',').split(',') if t.strip()]
                        if chosen_tag not in _tags:
                            _tags.append(chosen_tag)
                        _new = ', '.join(_tags)
                        _conn.execute("UPDATE documents SET tags=? WHERE control_number=?", (_new, cn))  # db_manager: exempt (review loop)
                        if _old != _new:
                            _bulk_audit.append({"action": "TAGS_CHANGED", "username": _username,
                                "control_number": cn, "module": "Review",
                                "details": None, "old_value": _old, "new_value": _new})
                        # Set privilege disposition when applying a privilege tag.
                        # Skip inbound docs — privilege dispositions do not apply.
                        if _bulk_is_priv_tag and _bulk_disp_choice:
                            if _is_inbound_doc(_row['source_party']):
                                _bulk_inbound_skipped.append(cn)
                            else:
                                _disp_val = 'Withhold' if 'Withhold' in _bulk_disp_choice else 'Redact'
                                _old_priv = db_manager.get_privilege_status(case_folder, cn, conn=_conn)
                                # Skip conflicts when user chose "Apply to Unset Only"
                                if _apply_mode == 'unset_only' and _old_priv is not None:
                                    pass  # preserve existing disposition
                                elif _old_priv != _disp_val:
                                    db_manager.set_privilege_status(case_folder, cn, _disp_val, conn=_conn)
                                    _bulk_audit.append({
                                        "action": "PRIVILEGE_DISPOSITION_CHANGED",
                                        "username": _username,
                                        "control_number": cn, "module": "Review",
                                        "details": f"bulk_tag_apply ({'override' if _old_priv else 'initial'})",
                                        "old_value": _old_priv or 'NULL',
                                        "new_value": _disp_val
                                    })
                    _conn.commit(); _conn.close()
                    if _bulk_audit:
                        db_manager.log_audit_batch(case_folder, _bulk_audit)
                if _safe_write(_bulk_apply_op, f"Tagged {len(bulk_cns)} documents as '{chosen_tag}'",
                               "❌ Bulk tag apply failed"):
                    if _bulk_inbound_skipped:
                        st.info(
                            f"📥 Skipped {len(_bulk_inbound_skipped)} inbound document(s) "
                            f"from the privilege disposition apply (privilege does not apply "
                            f"to opposing counsel's productions). Tag change was still applied "
                            f"to all selected documents."
                        )
                    # Cascade applied tag to children of each selected document
                    for _bc_cn in bulk_cns:
                        _cascade_tag_to_children(case_folder, _bc_cn, chosen_tag, _username, action='add')
                    st.session_state.bulk_selected_cns = []
                    st.rerun()

        if btn_clear:
            # CRIT-5: Route bulk-clear through _safe_write
            if _case_closed:
                st.warning("Write operations are disabled on closed matters.")
            else:
                _SYS_PREFIXES = ("NearDupe-", "Thread-", "NIST-", "Junk ")
                _clear_audit = []
                def _bulk_clear_op():
                    _conn = db_manager.get_connection(case_folder)
                    for cn in bulk_cns:
                        _row = _conn.execute("SELECT tags FROM documents WHERE control_number=?", (cn,)).fetchone()  # db_manager: exempt (review loop)
                        _old = _row['tags'] or ''
                        _tags = [t.strip() for t in _old.replace(';', ',').split(',') if t.strip()]
                        _surviving = [t for t in _tags if any(t.startswith(p) for p in _SYS_PREFIXES)]
                        _new = ', '.join(_surviving)
                        _conn.execute("UPDATE documents SET tags=? WHERE control_number=?", (_new, cn))  # db_manager: exempt (review loop)
                        if _old != _new:
                            _clear_audit.append({"action": "TAGS_CHANGED", "username": _username,
                                "control_number": cn, "module": "Review",
                                "details": None, "old_value": _old, "new_value": _new})
                    _conn.commit(); _conn.close()
                    if _clear_audit:
                        db_manager.log_audit_batch(case_folder, _clear_audit)
                if _safe_write(_bulk_clear_op, f"Cleared user tags on {len(bulk_cns)} documents (preserved system tags)",
                               "❌ Bulk tag clear failed"):
                    # Cascade clear to children — pass empty string so 'set' mode preserves only system tags
                    for _bc_cn in bulk_cns:
                        _cascade_tag_to_children(case_folder, _bc_cn, '', _username, action='set')
                    st.session_state.bulk_selected_cns = []
                    st.rerun()
            
    if 'pending_bates_zip' in st.session_state:
        st.download_button(
            "📥 Download Extracted Bates ZIP",
            data=st.session_state['pending_bates_zip'],
            file_name="Bates_Extraction.zip",
            mime="application/zip",
            type="primary",
            width='stretch',
            on_click=lambda: st.session_state.pop('pending_bates_zip', None)
        )

    # ── Bulk Set Production Category (outside form) ─────────────────────
    # permission: assign_production_category (Reviewer+)
    _bulk_prod_cats = db_manager.get_production_categories(case_folder)
    if _bulk_prod_cats and not _case_closed:
        with st.expander("📂 Set Production Category", expanded=False):
            _bpc_names = [c['name'] for c in _bulk_prod_cats]
            _bpc_choice = st.selectbox(
                "Category", _bpc_names,
                key="bulk_prod_cat_select"
            )
            if st.button("Apply to Selected", key="bulk_prod_cat_apply", type="primary"):
                # Check for conflicts — docs that already have a category
                _bpc_conn = db_manager.get_connection(case_folder)
                _bpc_placeholders = ','.join('?' * len(bulk_cns))
                _bpc_existing = _bpc_conn.execute(
                    f"SELECT control_number, production_category FROM documents "
                    f"WHERE control_number IN ({_bpc_placeholders}) "
                    f"AND production_category IS NOT NULL",
                    list(bulk_cns)
                ).fetchall()
                _bpc_conn.close()

                if _bpc_existing:
                    # Persist conflict state so resolution buttons survive reruns
                    _bpc_cat_counts = {}
                    for _bpc_r in _bpc_existing:
                        _bpc_c = _bpc_r['production_category']
                        _bpc_cat_counts[_bpc_c] = _bpc_cat_counts.get(_bpc_c, 0) + 1
                    st.session_state['_bpc_conflict'] = {
                        'category': _bpc_choice,
                        'conflict_count': len(_bpc_existing),
                        'total': len(bulk_cns),
                        'summary': ", ".join(f"{v} {k}" for k, v in _bpc_cat_counts.items()),
                        'existing_cns': [r['control_number'] for r in _bpc_existing],
                        'all_cns': list(bulk_cns),
                    }
                    st.rerun()
                else:
                    # No conflicts — apply directly
                    db_manager.bulk_update_production_category(
                        case_folder, bulk_cns, _bpc_choice,
                        username=_username)
                    st.session_state.bulk_selected_cns = []
                    st.session_state.pop('_bpc_conflict', None)
                    st.rerun()

            # ── Conflict resolution (persisted across reruns) ──────────
            if '_bpc_conflict' in st.session_state:
                _bpc_cf = st.session_state['_bpc_conflict']
                st.warning(
                    f"⚠️ {_bpc_cf['conflict_count']} of {_bpc_cf['total']} selected documents "
                    f"already have a category ({_bpc_cf['summary']})."
                )
                _bpc_c1, _bpc_c2, _bpc_c3 = st.columns(3)
                if _bpc_c1.button("Apply to all", key="bpc_all"):
                    db_manager.bulk_update_production_category(
                        case_folder, _bpc_cf['all_cns'], _bpc_cf['category'],
                        username=_username)
                    st.session_state.bulk_selected_cns = []
                    st.session_state.pop('_bpc_conflict', None)
                    st.rerun()
                if _bpc_c2.button("Uncategorized only", key="bpc_uncat"):
                    _bpc_uncat_cns = [
                        cn for cn in _bpc_cf['all_cns']
                        if cn not in set(_bpc_cf['existing_cns'])
                    ]
                    if _bpc_uncat_cns:
                        db_manager.bulk_update_production_category(
                            case_folder, _bpc_uncat_cns, _bpc_cf['category'],
                            username=_username)
                    st.session_state.bulk_selected_cns = []
                    st.session_state.pop('_bpc_conflict', None)
                    st.rerun()
                if _bpc_c3.button("Cancel", key="bpc_cancel"):
                    st.session_state.pop('_bpc_conflict', None)
                    st.rerun()

    # Export selected rows as CSV (outside the form so it works independently)
    # permission: export_csv
    if auth_manager.has_permission('export_csv'):
        st.markdown("---")
        selected_export_df = disp_df[disp_df['control_number'].isin(bulk_cns)] if 'control_number' in disp_df.columns else disp_df.iloc[[]]
        export_selected_csv = selected_export_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label=f"⬇️ Export {len(bulk_cns)} Selected Documents as CSV",
            data=export_selected_csv,
            file_name=f"{os.path.basename(case_folder)}_selected_{len(bulk_cns)}_docs.csv",
            mime="text/csv",
            width='stretch',
            help="Downloads only the currently selected rows as a CSV spreadsheet"
        )

    # Continue to render the three-pane viewer below bulk actions,
    # showing the most recently selected document for reference.

# --- THREE-PANE LAYOUT ---
# ── Peek Mode Check ──────────────────────────────────────────────────────
_peek_cn = st.session_state.get('_peek_cn')
if _peek_cn:
    current_cn = _peek_cn
else:
    if 'current_doc_idx' not in st.session_state:
        st.session_state.current_doc_idx = 0
    if st.session_state.current_doc_idx >= len(queue_list):
        st.session_state.current_doc_idx = 0
    elif st.session_state.current_doc_idx < 0:
        st.session_state.current_doc_idx = 0
    current_cn = queue_list[st.session_state.current_doc_idx]

# Fetch full row data for the current document
row = db_manager.get_document(case_folder, current_cn)

# Fetch family data
if row and row['parent_id']:
    _parent_cn = db_manager.get_document_parent(case_folder, row['parent_id'])
    parent_row = {'control_number': _parent_cn} if _parent_cn else None
else:
    parent_row = None

children_rows = db_manager.get_document_children(case_folder, current_cn)

st.write("---")

# Two-column layout: narrow sidebar (queue + coding stacked) | wide viewer
col_sidebar, col_viewer = st.columns([2, 7])

# 
# PANE 1: Queue & Family (Sidebar, top)
# 
with col_sidebar:
    if st.session_state.get('_peek_cn'):
        st.subheader(f"Peek: {st.session_state['_peek_cn']}")
        st.caption("Viewing a document outside the current search results.")
        if st.button("← Back to queue", key="_peek_back", width='stretch', type="primary"):
            _return_idx = st.session_state.pop('_peek_return_idx', 0)
            st.session_state.pop('_peek_cn', None)
            st.session_state.current_doc_idx = _return_idx
            st.rerun()
    else:
        st.subheader(f"Queue ({st.session_state.current_doc_idx + 1} of {len(queue_list)})")
        # Sync selectbox value to current document BEFORE widget renders.
        # Without this, the selectbox's stale session state value overrides
        # the index= parameter, causing an infinite rerun loop when the grid
        # changes current_doc_idx.
        st.session_state["active_doc_jump_select"] = current_cn
        jump_cn = st.selectbox(
            "Active Document",
            options=queue_list,
            label_visibility="collapsed",
            key="active_doc_jump_select"
        )
        if jump_cn != current_cn:
            st.session_state.current_doc_idx = queue_list.index(jump_cn)
            st.rerun()

    st.divider()
    
    with st.expander("Family & Related Items", expanded=True):
        if parent_row:
            st.caption("Parent:")
            if st.button(f"📧 {parent_row['control_number']}", key="jump_parent", width='stretch'):
                target_cn = parent_row['control_number']
                if target_cn in queue_list:
                    # Normal in-queue navigation — clear any active peek
                    st.session_state.pop('_peek_cn', None)
                    st.session_state.pop('_peek_return_idx', None)
                    st.session_state.family_nav = True
                    st.session_state.current_doc_idx = queue_list.index(target_cn)
                    st.rerun()
                else:
                    # Target is filtered out — enter peek mode. Set family_nav
                    # so the grid handler does not treat Streamlit's persistent
                    # dataframe selection as a fresh click and stomp _peek_cn.
                    st.session_state['_peek_cn'] = target_cn
                    if st.session_state.get('_peek_return_idx') is None:
                        st.session_state['_peek_return_idx'] = st.session_state.get('current_doc_idx', 0)
                    st.session_state.family_nav = True
                    st.rerun()

        if children_rows:
            st.caption("Attachments:")
            for c_idx, child in enumerate(children_rows):
                if st.button(f"📎 {child['control_number']}", key=f"jump_child_{c_idx}", width='stretch'):
                    target_cn = child['control_number']
                    if target_cn in queue_list:
                        # Normal in-queue navigation — clear any active peek
                        st.session_state.pop('_peek_cn', None)
                        st.session_state.pop('_peek_return_idx', None)
                        st.session_state.family_nav = True
                        st.session_state.current_doc_idx = queue_list.index(target_cn)
                        st.rerun()
                    else:
                        # Target is filtered out — enter peek mode. Set family_nav
                        # so the grid handler does not treat Streamlit's persistent
                        # dataframe selection as a fresh click and stomp _peek_cn.
                        st.session_state['_peek_cn'] = target_cn
                        if st.session_state.get('_peek_return_idx') is None:
                            st.session_state['_peek_return_idx'] = st.session_state.get('current_doc_idx', 0)
                        st.session_state.family_nav = True
                        st.rerun()

        if not parent_row and not children_rows:
            st.info("No family members.")

        # ── Show Full Family button ──────────────────────────────────────
        if (parent_row or children_rows) and row and row['group_id']:
            _current_override = st.session_state.get('_family_override_group_id')
            if _current_override == row['group_id']:
                st.caption("Showing full family in grid.")
            else:
                if st.button("Show Full Family in Grid", key="_show_full_family", width='stretch'):
                    # Stash current search state for restoration
                    st.session_state['_pre_family_search_state'] = {
                        'search_query': st.session_state.get('review_search', ''),
                        'col_filters': {k: v for k, v in col_filters.items()},
                    }
                    st.session_state['_family_override_group_id'] = row['group_id']
                    st.session_state['_page_number'] = 0
                    # Clear peek mode — family is now in the grid
                    st.session_state.pop('_peek_cn', None)
                    st.session_state.pop('_peek_return_idx', None)
                    st.rerun()


# ─── Redaction helpers (used by ✏️ Redact tab) ───────────────────────────────

def _r_write_page_annotations(pdf_path, page_number, marks, no_reason_sentinel):
    """Replaces redact annotations on one PDF page. Empty marks list clears the page."""
    doc = None
    try:
        doc = fitz.open(pdf_path)
        p = doc[page_number]
        for annot in list(p.annots()):
            if annot.type[0] == 12:  # PDF_ANNOT_REDACT
                p.delete_annot(annot)
        for mark in marks:
            rect = fitz.Rect(mark['pdf_x0'], mark['pdf_y0'], mark['pdf_x1'], mark['pdf_y1'])
            annot = p.add_redact_annot(rect, fill=(0, 0, 0))
            reason = mark.get('reason', '')
            if reason and reason != no_reason_sentinel:
                annot.set_info(content=reason)
        doc.saveIncr()
        return True
    except Exception as _e:
        st.warning(f"Could not write PDF annotations: {_e}")
        return False
    finally:
        if doc:
            doc.close()


def _r_write_all_annotations(pdf_path, all_mark_rows, no_reason_sentinel):
    """Clears and rewrites redact annotations for every page."""
    doc = None
    try:
        doc = fitz.open(pdf_path)
        page_marks = {r['page_number']: json.loads(r['marks_json'] or '[]') for r in all_mark_rows}
        for p_num in range(len(doc)):
            p = doc[p_num]
            for annot in list(p.annots()):
                if annot.type[0] == 12:
                    p.delete_annot(annot)
            for mark in page_marks.get(p_num, []):
                rect = fitz.Rect(mark['pdf_x0'], mark['pdf_y0'], mark['pdf_x1'], mark['pdf_y1'])
                annot = p.add_redact_annot(rect, fill=(0, 0, 0))
                reason = mark.get('reason', '')
                if reason and reason != no_reason_sentinel:
                    annot.set_info(content=reason)
        doc.saveIncr()
        return True
    except Exception as _e:
        st.warning(f"Could not write PDF annotations: {_e}")
        return False
    finally:
        if doc:
            doc.close()


def _r_sync_tags(case_folder_path, control_number, privilege_reasons, no_reason_sentinel):
    """Syncs privilege tags to exactly match current redaction mark reasons."""
    all_marks = db_manager.get_all_redaction_marks(case_folder_path, control_number)
    mark_reasons = set()
    for _row in all_marks:
        for _m in (json.loads(_row['marks_json']) if _row['marks_json'] else []):
            _r = _m.get('reason', '')
            if _r and _r != no_reason_sentinel:
                mark_reasons.add(_r)
    all_priv = set(privilege_reasons)
    old_tags_str = db_manager.get_document_tags(case_folder_path, control_number)
    existing = [t.strip() for t in old_tags_str.replace(';', ',').split(',') if t.strip()]
    new_tags = [t for t in existing if t not in all_priv]
    new_tags.extend(sorted(mark_reasons))
    new_tags_str = ', '.join(new_tags)
    db_manager.update_document_tags(case_folder_path, control_number, new_tags_str)

    # Sync privilege_status based on redaction marks
    # Auto-set to 'Redact' when ANY marks with reasons exist (not just privilege category members).
    # NEVER overwrite 'Withhold' — that is a manual reviewer decision.
    # SKIP for inbound documents (beta-2.10 Commit 4): privilege disposition is
    # meaningless on opposing counsel's production. Redaction marks themselves
    # are preserved — only the privilege_status auto-sync is suppressed.
    has_any_marks = bool(mark_reasons)
    old_status = db_manager.get_privilege_status(case_folder_path, control_number)

    _doc_row = db_manager.get_document(case_folder_path, control_number)
    _is_inbound = _is_inbound_doc(_doc_row.get('source_party') if _doc_row else None)

    if old_status != 'Withhold' and not _is_inbound:
        new_status = 'Redact' if has_any_marks else None
        if old_status != new_status:
            db_manager.set_privilege_status(case_folder_path, control_number, new_status)

    return old_tags_str, new_tags_str


# 
# PANE 2: Document Viewer (Center)
# 
with col_viewer:
    st.subheader(f"Viewer: {current_cn}")

    # Extraction quality warning banner — surfaces PST corruption and
    # other extraction degradation notes for defensible review.
    if row and row['extraction_notes']:
        st.warning(f"⚠️ **Extraction Note:** {row['extraction_notes']}")

    if row:
        # Tabbed Viewer Modes
        # permission: redact
        _can_redact = auth_manager.has_permission('redact')
        # permission: split_document
        _can_split = auth_manager.has_permission('split_document')
        _viewer_tabs = ["📄 Native / Image", "📝 Extracted Text", "📦 Production (Bates)"]
        if _can_redact:
            _viewer_tabs.append("✏️ Redact")
        if _can_split:
            _viewer_tabs.append("✂️ Split")

        # ── In-Document Search (above tabs, always visible) ───────────
        _module_query_pre = st.session_state.get('review_search', '').strip()
        _ds_col1, _ds_col2 = st.columns([5, 1])
        _doc_search_input = _ds_col1.text_input(
            "🔎 Search in document",
            value=_module_query_pre,  # show raw query, not expanded tokens
            placeholder="Type to find terms in this document…",
            key=f"doc_search_{current_cn}",
            label_visibility="collapsed"
        )
        _doc_search_terms = _extract_search_terms(_doc_search_input) if _doc_search_input else []
        _ds_badge_container = _ds_col2.empty()

        tabs = st.tabs(_viewer_tabs)
        _tab_idx = {label: i for i, label in enumerate(_viewer_tabs)}

        full_path = row['full_path']
        ext = row['file_extension'].lower() if row['file_extension'] else ""
        
        # -----------------------------
        # TAB 0: Native / Image Preview
        # -----------------------------
        with tabs[_tab_idx["📄 Native / Image"]]:
            if not full_path or not os.path.exists(full_path):
                if not full_path:
                    st.info("No native file available for this document. It may be an imaged-only production.")
                else:
                    st.error(f"File not found at: {full_path}")
            else:
                import glob
                reviewed_pdf = os.path.join(case_folder, "Reviewed", f"{current_cn}.pdf")
                processed_pdf = os.path.join(case_folder, "Processed", f"{current_cn}.pdf")
                
                target_pdf = None
                internal_pdf = None
                actual_ext = os.path.splitext(full_path)[1].lower() if full_path else ""
                
                # Determine Internal Fallback PDF
                if os.path.exists(reviewed_pdf):
                    internal_pdf = reviewed_pdf
                elif os.path.exists(processed_pdf):
                    internal_pdf = processed_pdf
                elif ext == '.pdf' or actual_ext == '.pdf':
                    internal_pdf = full_path

                target_pdf = internal_pdf
                if internal_pdf == reviewed_pdf:
                    st.info("⚠️ Viewing Local Redacted Image (Not Yet Produced)")
                
                # Check for standard display logic
                if target_pdf:
                    if _doc_search_terms:
                        import fitz as _fitz_count
                        try:
                            _cnt_doc = _fitz_count.open(target_pdf)
                            _pdf_hit_count = sum(
                                len(_cnt_doc[p].search_for(term))
                                for p in range(len(_cnt_doc))
                                for term in _doc_search_terms
                            )
                            _cnt_doc.close()
                            if _pdf_hit_count:
                                _ds_badge_container.markdown(
                                    f"<span style='background:#80d4ff;color:#1a1a1a;padding:4px 10px;"
                                    f"border-radius:12px;font-weight:600;font-size:0.85em'>"
                                    f"🔎 {_pdf_hit_count} hit{'s' if _pdf_hit_count != 1 else ''} in PDF</span>",
                                    unsafe_allow_html=True
                                )
                        except Exception:
                            pass
                    _display_pdf_viewer(target_pdf, "viewer", current_cn, search_terms=_doc_search_terms)
                
                elif ext in ['.doc', '.docx']:
                    st.info(f"Native Office Document: `{ext}`")
                    st.warning("No PDF preview exists yet.")
                    if IMAGER_AVAILABLE:
                        if st.button(f"⚙️ Generate PDF Preview from Native Processor", key=f"gen_doc_{current_cn}"):
                            with st.spinner("Calling Office Extractor to render PDF..."):
                                success, err = universal_imager.image_document(full_path, processed_pdf)
                                if success:
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Imaging failed: {err}")
                    else:
                        st.warning("Universal Imager not available.")
                elif ext in ['.png', '.jpg', '.jpeg', '.gif']:
                    st.image(full_path)
                
                elif ext in ['.txt', '.log']:
                    with open(full_path, "r", errors='ignore') as f:
                        st.markdown(f'<div style="background-color: white; color: black; padding: 20px; border: 1px solid #ccc; font-family: monospace; white-space: pre-wrap; height: 800px; overflow-y: scroll;">{f.read()}</div>', unsafe_allow_html=True)
                        
                elif ext in ['.xlsx', '.xls', '.csv']:
                    tabs_inner = st.tabs(["📊 Interactive Data", "📄 PDF Preview"])
                    with tabs_inner[0]:
                        try:
                            if ext == '.csv':
                                preview_df = pd.read_csv(full_path, nrows=500)
                            else:
                                preview_df = pd.read_excel(full_path, nrows=500)
                            st.dataframe(preview_df, width='stretch')
                            st.info("Showing first 500 rows. Use Native or generate a PDF for full review.")
                        except Exception as e:
                            st.error(f"Failed to read spreadsheet data: {e}")
                    with tabs_inner[1]:
                        if IMAGER_AVAILABLE:
                            if st.button("⚙️ Generate PDF Preview (COM)", key=f"gen_pdf_{current_cn}"):
                                with st.spinner("Calling Office COM to render PDF..."):
                                    success, err = universal_imager.image_document(full_path, processed_pdf)
                                    if success:
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"Imaging failed: {err}")
                        else:
                            st.warning("Universal Imager not available.")
                            
                elif ext in ['.ppt', '.pptx']:
                    st.info(f"Native Office Document: `{ext}`")
                    if IMAGER_AVAILABLE:
                        if st.button(f"⚙️ Generate PDF Preview from Native Processor", key=f"gen_doc_{current_cn}"):
                            with st.spinner("Calling Office Extractor to render PDF..."):
                                success, err = universal_imager.image_document(full_path, processed_pdf)
                                if success:
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Imaging failed: {err}")
                    else:
                        st.warning("Universal Imager not available.")
                        
                elif ext in ['.msg', '.eml'] and not target_pdf:
                    st.info(f"Native Email Message: `{ext}` — Rendering built-in HTML preview.")
                    try:
                        # Display metadata
                        st.write(f"**From:** {row['email_from']}")
                        st.write(f"**To:** {row['email_to']}")
                        st.write(f"**Subject:** {row['email_subject']}")
                        st.write(f"**Date:** {row['date_sent']}")
                        
                        if ext == '.msg':
                            if os.path.exists(processed_pdf):
                                _display_pdf_viewer(processed_pdf, "msg_viewer", current_cn, search_terms=_doc_search_terms)
                            else:
                                st.info("No imaged PDF available for this MSG. View extracted text, or generate it.")
                                if IMAGER_AVAILABLE:
                                    if st.button("⚙️ Generate PDF Preview (COM)", key=f"gen_msg_{current_cn}"):
                                        with st.spinner("Rendering MSG..."):
                                            success, err = universal_imager.image_document(full_path, processed_pdf)
                                            if success:
                                                time.sleep(1)
                                                st.rerun()
                                            else:
                                                st.error(f"Imaging failed: {err}")
                        else: # .eml
                            import email as email_lib
                            from email import policy as email_policy
                            with open(full_path, 'rb') as f:
                                msg = email_lib.message_from_binary_file(f, policy=email_policy.default)

                            body = None
                            try:
                                body = msg.get_body(preferencelist=('html', 'plain'))
                            except Exception:
                                pass

                            if body:
                                try:
                                    if body.get_content_type() == 'text/html':
                                        html_content = f"""<div style="background-color: white; color: black; padding: 20px; font-family: sans-serif; height: 800px; overflow-y: scroll;">{body.get_content()}</div>"""
                                        st.components.v1.html(html_content, height=800, scrolling=True)
                                    else:
                                        st.markdown(f'<div style="background-color: white; color: black; padding: 20px; border: 1px solid #ccc; font-family: monospace; white-space: pre-wrap; height: 800px; overflow-y: scroll;">{body.get_content()}</div>', unsafe_allow_html=True)
                                except Exception as e:
                                    st.warning("Could not render email body format.")
                            else:
                                st.info("No body content found in this email.")
                    except Exception as e:
                        st.error(f"Error rendering email: {e}")
                
                elif ext in ['.htm', '.html']:
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                            html_content = f.read()
                        st.components.v1.html(html_content, height=800, scrolling=True)
                    except Exception as e:
                        st.error(f"Error rendering HTML file: {e}")

                else:
                    st.warning(f"Visual preview not yet implemented for `{ext}` files.")
                    st.info("💡 You can view the extracted text in the next tab.")
                    if st.button("📂 Open File Externally (Windows Only)", key=f"open_ext_{current_cn}"):
                        os.startfile(full_path)

        # -----------------------------
        # TAB 1: Extracted Text
        # -----------------------------
        with tabs[_tab_idx["📝 Extracted Text"]]:
            os_content = None
            if es:
                index_name = os_manager.get_index_name(case_folder)
                try:
                    res = es.search(
                        index=index_name,
                        body={
                            "query": {"term": {"control_number.keyword": current_cn}},
                            "_source": ["content"],
                            "size": 1
                        }
                    )
                    hits = res['hits']['hits']
                    if hits:
                        os_content = hits[0]['_source'].get('content', 'No text found.')
                    else:
                        os_content = "Document not found in OpenSearch index."
                except Exception as e:
                    os_content = f"Error fetching from OpenSearch: {str(e)}"
            else:
                os_content = "Connect to OpenSearch in the sidebar to view extracted text."

            # ── Persistent STR Highlighting ───────────────────────────────
            import re as _re_hl
            active_str_terms = st.session_state.get('active_str_terms', [])

            # Escape the raw text content for safe HTML rendering
            rendered_content = _html.escape(str(os_content or ''))

            # ── In-Document Search Highlighting (cyan) ────────────────────
            _doc_hit_count = 0
            if _doc_search_terms:
                _DOC_MARK_OPEN  = "<mark style='background-color:#80d4ff;color:#1a1a1a;border-radius:2px;padding:0 2px'>"
                _DOC_MARK_CLOSE = "</mark>"
                _doc_skipped = []
                for term in _doc_search_terms:
                    try:
                        pattern = _re_hl.compile(r'(?i)(' + _re_hl.escape(term) + r')')
                        matches = pattern.findall(rendered_content)
                        _doc_hit_count += len(matches)
                        rendered_content = pattern.sub(
                            _DOC_MARK_OPEN + r'\1' + _DOC_MARK_CLOSE,
                            rendered_content
                        )
                    except _re_hl.error:
                        _doc_skipped.append(term)

            if _doc_search_terms:
                if _doc_hit_count > 0:
                    _ds_badge_container.markdown(
                        f"<span style='background:#80d4ff;color:#1a1a1a;padding:4px 10px;"
                        f"border-radius:12px;font-weight:600;font-size:0.85em'>"
                        f"🔎 {_doc_hit_count} hit{'s' if _doc_hit_count != 1 else ''}</span>",
                        unsafe_allow_html=True
                    )
                else:
                    _ds_badge_container.markdown(
                        "<span style='background:#555;color:#ccc;padding:4px 10px;"
                        "border-radius:12px;font-size:0.85em'>No hits</span>",
                        unsafe_allow_html=True
                    )

            if active_str_terms:
                # Show badge of active terms (separate complex terms that can't be regex'd)
                _safe_hl   = [t for t in active_str_terms if t.strip()]
                _skipped   = []  # any that survive the STR filter but still fail re.compile

                _MARK_OPEN  = "<mark style='background-color:#ffe066;color:#1a1a1a;border-radius:2px;padding:0 2px;font-weight:600'>"
                _MARK_CLOSE = "</mark>"

                for term in _safe_hl:
                    try:
                        pattern = _re_hl.compile(
                            r'(?i)(' + _re_hl.escape(term) + r')'
                        )
                        rendered_content = pattern.sub(
                            _MARK_OPEN + r'\1' + _MARK_CLOSE,
                            rendered_content
                        )
                    except _re_hl.error:
                        _skipped.append(term)

                applied_terms = [t for t in _safe_hl if t not in _skipped]
                badge_terms   = ', '.join(f'`{t}`' for t in applied_terms[:10])
                if len(applied_terms) > 10:
                    badge_terms += f' … +{len(applied_terms) - 10} more'

                badge_msg = f"🔍 **STR Terms Active** — {badge_terms}"
                if _skipped:
                    badge_msg += f"  *(skipped {len(_skipped)} complex terms)*"
                st.info(badge_msg)

            # Render — use unsafe_allow_html so <mark> tags survive
            st.markdown(
                f'<div style="background-color:white;color:black;padding:20px;border:1px solid #ccc;'
                f'font-family:sans-serif;white-space:pre-wrap;">'
                f'{rendered_content}</div>',
                unsafe_allow_html=True
            )


        # -----------------------------
        # TAB 2: Production (Bates)
        # -----------------------------
        with tabs[_tab_idx["📦 Production (Bates)"]]:
            produced_pdf = None
            produced_text = None
            
            if dict(row).get('begdoc'):
                prod_base_dir = os.path.join(case_folder, "Productions")
                if os.path.exists(prod_base_dir):
                    prod_folders = [os.path.join(prod_base_dir, d) for d in os.listdir(prod_base_dir) if os.path.isdir(os.path.join(prod_base_dir, d))]
                    prod_folders.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    
                    for prod_dir in prod_folders:
                        # Image priority
                        potential_img = os.path.join(prod_dir, "IMAGES", f"{row['begdoc']}.pdf")
                        if os.path.exists(potential_img) and not produced_pdf:
                            produced_pdf = potential_img
                        else:
                            potential_tif = os.path.join(prod_dir, "IMAGES", f"{row['begdoc']}.tif")
                            if os.path.exists(potential_tif) and not produced_pdf:
                                produced_pdf = potential_tif
                        
                        # Text priority
                        potential_txt = os.path.join(prod_dir, "TEXT", f"{row['begdoc']}.txt")
                        if os.path.exists(potential_txt) and not produced_text:
                            with open(potential_txt, 'r', encoding='utf-8', errors='ignore') as f:
                                produced_text = f.read()

            if produced_pdf or produced_text:
                is_redacted = 'redaction_status' in row.keys() and row['redaction_status'] == 'Has_Redactions'
                p_tabs = st.tabs(["🖼️ Final Image", "📄 Final Text"])
                
                with p_tabs[0]:
                    if produced_pdf:
                        if produced_pdf.lower().endswith('.tif') or produced_pdf.lower().endswith('.tiff'):
                            st.info("ℹ️ Produced as a TIFF image. Your browser cannot render TIFFs inline.")
                            _offer_produced_download(produced_pdf, current_cn, row['begdoc'])
                        else:
                            _offer_produced_download(produced_pdf, current_cn, row['begdoc'])
                            if is_redacted:
                                st.warning("🔒 Safe Produced Image (Redacted & Bates Stamped)")
                            # ── Stale production check ──
                            _processed_pdf = os.path.join(case_folder, "Processed", f"{current_cn}.pdf")
                            _produced_pdf_path = produced_pdf
                            if _produced_pdf_path and os.path.isfile(_processed_pdf) and os.path.isfile(_produced_pdf_path):
                                _proc_mtime = os.path.getmtime(_processed_pdf)
                                _prod_mtime = os.path.getmtime(_produced_pdf_path)
                                if _proc_mtime > _prod_mtime:
                                    st.warning(
                                        "⚠️ This document was re-imaged after production. "
                                        "The produced version may be outdated. Consider re-producing this volume."
                                    )
                            _display_pdf_viewer(produced_pdf, "prod_viewer", current_cn)
                    else:
                        st.info("No produced image found on disk.")

                with p_tabs[1]:
                    if produced_text:
                        if is_redacted:
                            st.warning("🔒 Safe Produced Text (Redactions Scrubbed)")
                        st.markdown(f'<div style="background-color: white; color: black; padding: 20px; border: 1px solid #ccc; font-family: sans-serif; white-space: pre-wrap; height: 700px; overflow-y: scroll;">{produced_text}</div>', unsafe_allow_html=True)
                    else:
                        st.info("No produced text file found on disk.")

                # ── Production History ──
                _prod_records = db_manager.get_document_productions(case_folder, current_cn)
                if _prod_records and len(_prod_records) > 1:
                    with st.expander(f"📋 Production History ({len(_prod_records)} records)", expanded=False):
                        for _pr in _prod_records:
                            _pr_type_icon = {
                                'Original': '🟢',
                                'Supplemental': '🔵',
                                'Replacement': '🟠'
                            }.get(_pr.get('production_type', ''), '⚪')
                            st.markdown(
                                f"{_pr_type_icon} **{_pr['production_volume']}** — "
                                f"`{_pr['begdoc']}` to `{_pr['enddoc']}` "
                                f"({_pr.get('page_count', 1)} pg) — "
                                f"{_pr.get('production_type', 'Original')} — "
                                f"{(_pr.get('produced_at') or '')[:10]}"
                            )
                            if _pr.get('supersedes_id'):
                                st.caption(f"Supersedes production record #{_pr['supersedes_id']}")
                            if _pr.get('notes'):
                                st.caption(_pr['notes'])
            else:
                st.info("This document has not been produced yet.")

        # ----------------------------
        # TAB 3: Redaction (permission: redact)
        # ----------------------------
        if _can_redact:
         with tabs[_tab_idx["✏️ Redact"]]:
            if not FITZ_AVAILABLE:
                st.error("❌ PyMuPDF (fitz) is not installed. Run `pip install PyMuPDF`.")
            elif not VIEWER_AVAILABLE:
                st.error("❌ Redaction viewer component not found. Ensure `components/redaction_viewer/` exists.")
            else:
                @st.fragment
                def _redact_tab_fragment():
                    # Resolve the processed PDF to annotate
                    _r_processed = os.path.join(case_folder, "Processed", f"{current_cn}.pdf")
                    _r_native_is_pdf = full_path and full_path.lower().endswith('.pdf')

                    if os.path.exists(_r_processed):
                        _r_pdf_path = _r_processed
                    elif _r_native_is_pdf and os.path.exists(full_path):
                        _r_pdf_path = full_path
                    else:
                        _r_pdf_path = None

                    if not _r_pdf_path:
                        st.info("📂 No processed PDF found for this document. Process it first to enable redaction.")
                    else:
                        # Privilege reason options from tag category system
                        _r_tag_cats = db_manager.get_tag_categories(case_folder)
                        _r_priv_reasons = []
                        for _cat_data in _r_tag_cats.values():
                            if _cat_data.get('is_privilege'):
                                _r_priv_reasons.extend(_cat_data.get('members', []))
                        if not _r_priv_reasons:
                            _r_priv_reasons = ["Attorney-Client Privilege", "Work Product", "Trade Secret"]
                        _r_reason_opts = [_REDACT_NO_REASON] + _r_priv_reasons + [_REDACT_CUSTOM]

                        # Page count — cached in session state (PDF doesn't change during review)
                        _r_pgcount_key = f"_r_pgcount_{current_cn}"
                        _r_total_pages = st.session_state.get(_r_pgcount_key, 0)

                        if _r_total_pages > 0:
                            # Page navigation state
                            _r_page_key = f"redact_page_{current_cn}"
                            if st.session_state.get('_redact_last_doc') != current_cn:
                                st.session_state[_r_page_key] = 0
                                st.session_state['_redact_last_doc'] = current_cn
                            _r_page_idx = max(0, min(st.session_state.get(_r_page_key, 0), _r_total_pages - 1))

                            # Apply pending nav BEFORE pixmap render (relocated from control panel)
                            _r_jump_key = f"redact_jump_{current_cn}"
                            _r_nav_pending_key = f"_redact_nav_pending_{current_cn}"
                            _r_nav_pending = st.session_state.pop(_r_nav_pending_key, None)
                            if _r_nav_pending is not None:
                                _r_page_idx = max(0, min(_r_nav_pending, _r_total_pages - 1))
                                st.session_state[_r_page_key] = _r_page_idx
                                st.session_state[_r_jump_key] = str(_r_page_idx + 1)
                            elif _r_jump_key not in st.session_state:
                                st.session_state[_r_jump_key] = str(_r_page_idx + 1)

                            _r_enable_key = f"enable_redact_{current_cn}"
                            st.checkbox("🖊️ Load Redaction Canvas", key=_r_enable_key,
                                        help="Click once to initialize the annotation canvas for this document.")
                            if not st.session_state.get(_r_enable_key):
                                st.caption("Check the box above to load the redaction tools.")
                            else:
                                # Zoom selector (persisted in session state)
                                _r_zoom_pct = st.select_slider(
                                    "🔍 Zoom", options=[50, 75, 100, 125, 150],
                                    value=st.session_state.get("redact_zoom", 75),
                                    format_func=lambda x: f"{x}%",
                                    key="redact_zoom",
                                )
                                _r_target_w = {50: 500, 75: 680, 100: 816, 125: 1020, 150: 1224}[_r_zoom_pct]

                                # Render current page — cached by (cn, page, zoom) to avoid
                                # re-opening the PDF and re-rendering the pixmap on every rerun.
                                # Page count is also captured on the same open (single fitz.open).
                                _r_pixmap_cache_key = f"_r_pixmap_{current_cn}_{_r_page_idx}_{_r_zoom_pct}"
                                _r_cached = st.session_state.get(_r_pixmap_cache_key)
                                if _r_cached:
                                    _r_img_bytes = _r_cached['img_bytes']
                                    _r_page_w_pt = _r_cached['page_w_pt']
                                    _r_page_h_pt = _r_cached['page_h_pt']
                                    _r_scale = _r_cached['scale']
                                    _r_dpi = _r_cached['dpi']
                                else:
                                    _r_doc_render = None
                                    try:
                                        _r_doc_render = fitz.open(_r_pdf_path)
                                        # Capture page count on same open (avoids a separate fitz.open)
                                        st.session_state[_r_pgcount_key] = len(_r_doc_render)
                                        _r_page_obj = _r_doc_render[_r_page_idx]
                                        _r_page_w_pt = _r_page_obj.rect.width
                                        _r_page_h_pt = _r_page_obj.rect.height
                                        _r_dpi = max(36, int(_r_target_w * 72 / _r_page_w_pt))
                                        _r_scale = _r_dpi / 72.0
                                        _r_mat = fitz.Matrix(_r_dpi / 72, _r_dpi / 72)
                                        _r_pix = _r_page_obj.get_pixmap(matrix=_r_mat, alpha=False)
                                        _r_img_bytes = _r_pix.tobytes("png")
                                        # Cache current + evict stale (keep current ± 1 for pre-caching)
                                        _keep_pages = {_r_page_idx, _r_page_idx - 1, _r_page_idx + 1}
                                        _keep_keys = {f"_r_pixmap_{current_cn}_{p}_{_r_zoom_pct}" for p in _keep_pages}
                                        for _rck in [k for k in st.session_state
                                                     if k.startswith(f"_r_pixmap_{current_cn}_") and k not in _keep_keys]:
                                            del st.session_state[_rck]
                                        st.session_state[_r_pixmap_cache_key] = {
                                            'img_bytes': _r_img_bytes,
                                            'page_w_pt': _r_page_w_pt,
                                            'page_h_pt': _r_page_h_pt,
                                            'scale': _r_scale,
                                            'dpi': _r_dpi,
                                        }
                                        # Pre-cache adjacent pages while PDF handle is open
                                        for _adj_offset in [-1, 1]:
                                            _adj_idx = _r_page_idx + _adj_offset
                                            _adj_ck = f"_r_pixmap_{current_cn}_{_adj_idx}_{_r_zoom_pct}"
                                            if 0 <= _adj_idx < len(_r_doc_render) and not st.session_state.get(_adj_ck):
                                                try:
                                                    _adj_pg = _r_doc_render[_adj_idx]
                                                    _adj_w, _adj_h = _adj_pg.rect.width, _adj_pg.rect.height
                                                    _adj_dpi = max(36, int(_r_target_w * 72 / _adj_w))
                                                    _adj_mat = fitz.Matrix(_adj_dpi / 72, _adj_dpi / 72)
                                                    _adj_pix = _adj_pg.get_pixmap(matrix=_adj_mat, alpha=False)
                                                    st.session_state[_adj_ck] = {
                                                        'img_bytes': _adj_pix.tobytes("png"),
                                                        'page_w_pt': _adj_w, 'page_h_pt': _adj_h,
                                                        'scale': _adj_dpi / 72.0, 'dpi': _adj_dpi,
                                                    }
                                                except Exception:
                                                    pass
                                    except Exception as _e:
                                        st.error(f"❌ Could not render page: {_e}")
                                        _r_img_bytes = None
                                    finally:
                                        if _r_doc_render:
                                            _r_doc_render.close()

                                _viewer_result = None
                                if _r_img_bytes:
                                    # Apply search term highlights if active (cached)
                                    if _doc_search_terms:
                                        _hl_terms_key = str(sorted(_doc_search_terms))
                                        _hl_cache_key = f"_r_hl_{current_cn}_{_r_page_idx}_{_r_zoom_pct}_{hash(_hl_terms_key)}"
                                        _hl_cached = st.session_state.get(_hl_cache_key)
                                        if _hl_cached:
                                            _r_img_bytes = _hl_cached
                                        else:
                                            _hl_img = _highlight_page_image(
                                                _r_pdf_path, _r_page_idx, _doc_search_terms,
                                                zoom=_r_dpi / 72
                                            )
                                            if _hl_img:
                                                _hl_buf = io.BytesIO()
                                                _hl_img.save(_hl_buf, "PNG")
                                                _r_img_bytes = _hl_buf.getvalue()
                                                st.session_state[_hl_cache_key] = _r_img_bytes

                                    # Load existing marks from DB
                                    _r_existing_json = db_manager.get_redaction_marks(case_folder, current_cn, _r_page_idx)
                                    _r_existing_marks = json.loads(_r_existing_json) if _r_existing_json else []

                                    # Counter embedded in component key — bump to force component
                                    # to re-initialize from DB after a mark deletion.
                                    _r_reset_key = f"_rv_reset_{current_cn}_{_r_page_idx}"
                                    if _r_reset_key not in st.session_state:
                                        st.session_state[_r_reset_key] = 0
                                    _r_reset_counter = st.session_state[_r_reset_key]

                                    # Build privilege color map from tag categories
                                    _PRIV_PALETTE = ["#cc0000", "#0066cc", "#008844", "#cc6600", "#8800aa", "#aa0044", "#006688", "#884400"]
                                    _priv_color_map = {}
                                    for _pi, _pr in enumerate(_r_priv_reasons):
                                        _priv_color_map[_pr] = _PRIV_PALETTE[_pi % len(_PRIV_PALETTE)]

                                    _r_mode_key = f"redact_mode_{current_cn}"
                                    _r_draw_mode_ss = st.session_state.get(_r_mode_key, "✏️ Draw")

                                    _r_reasons_key = f"_mark_reasons_{current_cn}_{_r_page_idx}"

                                    # Two-column layout: control panel | viewer (wider at high zoom)
                                    _r_col_ratio = [2.5, 7.5] if _r_zoom_pct >= 100 else [3, 7]
                                    _r_ctrl_col, _r_viewer_col = st.columns(_r_col_ratio, gap="small")

                                    # Viewer column — render component
                                    with _r_viewer_col:
                                        _viewer_result = redaction_viewer(
                                            page_image_bytes=_r_img_bytes,
                                            marks=_r_existing_marks,
                                            scale=_r_scale,
                                            page_width_pt=_r_page_w_pt,
                                            page_height_pt=_r_page_h_pt,
                                            mode="draw" if _r_draw_mode_ss == "✏️ Draw" else "select",
                                            case_closed=_case_closed,
                                            privilege_colors=_priv_color_map,
                                            zoom_pct=_r_zoom_pct,
                                            key=f"rv_{current_cn}_{_r_page_idx}_{_r_zoom_pct}_{_r_reset_counter}",
                                        )

                                # Determine active marks: from component result (if user interacted) or DB
                                _r_active_marks = _viewer_result["marks"] if _viewer_result else _r_existing_marks
                                _r_n_boxes = len(_r_active_marks)

                                # Sync reason tracking with current mark count
                                _r_cur_reasons = [_m.get("reason", _REDACT_NO_REASON) for _m in _r_active_marks]
                                st.session_state[_r_reasons_key] = _r_cur_reasons

                                def _r_resolve_reason(_r_i):
                                    _sel = st.session_state.get(f"reason_sel_{current_cn}_{_r_page_idx}_{_r_n_boxes}_{_r_i}", _REDACT_NO_REASON)
                                    if _sel == _REDACT_CUSTOM:
                                        _custom = st.session_state.get(f"reason_custom_{current_cn}_{_r_page_idx}_{_r_n_boxes}_{_r_i}", "").strip()
                                        return _custom if _custom else _REDACT_NO_REASON
                                    return _sel

                                # Control panel (status, nav, tool, reasons, actions)
                                with _r_ctrl_col:
                                    # Status badge
                                    _r_rs = row['redaction_status'] if row and 'redaction_status' in row.keys() else None
                                    _r_badge = {"Applied": "🔒 Redactions Applied", "Has_Redactions": "✏️ Marks Pending"}.get(_r_rs, "No Marks")
                                    st.caption(f"Status: **{_r_badge}** | {_r_total_pages} pg")

                                    # Navigation (pending nav already applied before pixmap render)
                                    _r_nc1, _r_nc2, _r_nc3, _r_nc4 = st.columns([1, 1, 1, 1], gap="small")
                                    if _r_nc1.button("◀", key=f"redact_prev_{current_cn}", disabled=(_r_page_idx == 0), width='stretch'):
                                        st.session_state[_r_nav_pending_key] = _r_page_idx - 1
                                        st.rerun(scope="fragment")
                                    _r_jump_str = _r_nc2.text_input(
                                        "Page", value=str(_r_page_idx + 1),
                                        key=_r_jump_key, label_visibility="collapsed",
                                    )
                                    try:
                                        _r_jump = int(_r_jump_str)
                                        if 1 <= _r_jump <= _r_total_pages and _r_jump - 1 != _r_page_idx:
                                            st.session_state[_r_page_key] = _r_jump - 1
                                            st.rerun(scope="fragment")
                                    except (ValueError, TypeError):
                                        pass
                                    _r_nc3.markdown(
                                        f"<div style='text-align:center;padding-top:6px;color:#aaa'>/ {_r_total_pages}</div>",
                                        unsafe_allow_html=True
                                    )
                                    if _r_nc4.button("▶", key=f"redact_next_{current_cn}", disabled=(_r_page_idx == _r_total_pages - 1), width='stretch'):
                                        st.session_state[_r_nav_pending_key] = _r_page_idx + 1
                                        st.rerun(scope="fragment")

                                    st.divider()

                                    # Tool selector
                                    st.radio(
                                        "Tool", ["✏️ Draw", "🖱️ Select"], horizontal=True,
                                        key=_r_mode_key, label_visibility="collapsed",
                                        help=(
                                            "**Draw** — click and drag on the document to draw a redaction box.  \n"
                                            "**Select** — click an existing box to select it, then drag to reposition "
                                            "or drag its corner/edge handles to resize it."
                                        ),
                                    )
                                    st.markdown(
                                        "<p style='font-size:0.82rem;color:#aaa;margin:2px 0 4px'>"
                                        "Draw: click and drag to place a box. "
                                        "Select: click a box to move or resize it."
                                        "</p>",
                                        unsafe_allow_html=True,
                                    )

                                    # Per-box reason selectors with delete buttons
                                    # Wrapped in @st.fragment so dropdown/text changes only
                                    # rerun the panel, not the entire page (avoids canvas redraw).
                                    @st.fragment
                                    def _render_reason_panel():
                                        if _r_n_boxes > 0:
                                            st.divider()
                                            st.markdown("**Mark Reasons**")
                                            _r_mark_deleted = False
                                            for _r_i in range(_r_n_boxes):
                                                _r_saved_rsn = st.session_state[_r_reasons_key][_r_i]
                                                _r_def_idx = (
                                                    _r_reason_opts.index(_r_saved_rsn)
                                                    if _r_saved_rsn in _r_reason_opts
                                                    else _r_reason_opts.index(_REDACT_CUSTOM)
                                                )
                                                _r_label_col, _r_del_col = st.columns([5, 1])
                                                _r_label_col.markdown(f"<div style='font-weight:600;font-size:0.85rem'>Box {_r_i+1}</div>", unsafe_allow_html=True)
                                                if not _case_closed and _r_del_col.button(
                                                    "🗑", key=f"del_mark_{current_cn}_{_r_page_idx}_{_r_n_boxes}_{_r_i}",
                                                    help=f"Delete box {_r_i+1}",
                                                ):
                                                    # Remove this mark and save immediately (batched DB)
                                                    _del_marks = [m for j, m in enumerate(_r_active_marks) if j != _r_i]
                                                    _del_json = json.dumps(_del_marks)
                                                    _del_result = db_manager.save_redaction_with_sync(
                                                        case_folder, current_cn, _r_page_idx, _del_json,
                                                        _username, _r_priv_reasons, _REDACT_NO_REASON,
                                                        target_redaction_status=row.get('redaction_status') or 'Has_Redactions')
                                                    _r_write_page_annotations(_r_pdf_path, _r_page_idx, _del_marks, _REDACT_NO_REASON)
                                                    if _del_result:
                                                        _dt_old, _dt_new, _, _, _ = _del_result
                                                        if _dt_old != _dt_new:
                                                            db_manager.log_audit(case_folder, "TAGS_CHANGED", username=_username,
                                                                control_number=current_cn, module="Review", old_value=_dt_old, new_value=_dt_new)
                                                    try:
                                                        db_manager.log_audit(case_folder, "REDACTION_SAVED", username=_username,
                                                            control_number=current_cn, module="Review",
                                                            details=json.dumps({"page": _r_page_idx + 1, "mark_count": len(_del_marks), "action": "delete_single"}))
                                                    except Exception:
                                                        pass
                                                    if _r_reasons_key in st.session_state:
                                                        del st.session_state[_r_reasons_key]
                                                    # Bump reset counter so component key changes,
                                                    # forcing it to re-read marks from DB on next render.
                                                    st.session_state[_r_reset_key] = _r_reset_counter + 1
                                                    _r_mark_deleted = True
                                                    # Signal outer fragment to rerun (can't reach outer scope from inner fragment)
                                                    st.session_state['_redact_delete_pending'] = True
                                                    return  # exit inner fragment; outer fragment handles rerun
                                                if not _r_mark_deleted:
                                                    _r_chosen = st.selectbox(
                                                        f"Box {_r_i+1}",
                                                        options=_r_reason_opts,
                                                        index=_r_def_idx,
                                                        key=f"reason_sel_{current_cn}_{_r_page_idx}_{_r_n_boxes}_{_r_i}",
                                                        label_visibility="collapsed",
                                                    )
                                                    st.session_state[_r_reasons_key][_r_i] = _r_chosen
                                                    # Always render custom text_input (stable widget tree avoids rerun on show/hide)
                                                    _r_custom_ctr = st.container()
                                                    _r_prev_custom = _r_saved_rsn if _r_saved_rsn not in _r_reason_opts else ""
                                                    with _r_custom_ctr:
                                                        st.text_input(
                                                            f"Custom {_r_i+1}",
                                                            value=_r_prev_custom,
                                                            key=f"reason_custom_{current_cn}_{_r_page_idx}_{_r_n_boxes}_{_r_i}",
                                                            placeholder="Enter reason...",
                                                            label_visibility="collapsed",
                                                        )
                                                    if _r_chosen != _REDACT_CUSTOM:
                                                        _r_custom_ctr.empty()
                                    _render_reason_panel()

                                    # Handle delete signal from inner fragment
                                    if st.session_state.pop('_redact_delete_pending', False):
                                        st.rerun(scope="fragment")

                                    st.divider()

                                    # Action buttons (stacked vertically)
                                    if _case_closed:
                                        st.warning("Write operations are disabled on closed matters.")
                                    elif st.button("💾 Save Marks", key=f"redact_save_{current_cn}", width='stretch', type="primary"):
                                        from datetime import datetime as _dt_now
                                        _r_mark_objects = []
                                        for _r_i, _r_m in enumerate(_r_active_marks):
                                            _r_mark_objects.append({
                                                "canvas_x": _r_m["pdf_x0"] * _r_scale,
                                                "canvas_y": _r_m["pdf_y0"] * _r_scale,
                                                "canvas_w": (_r_m["pdf_x1"] - _r_m["pdf_x0"]) * _r_scale,
                                                "canvas_h": (_r_m["pdf_y1"] - _r_m["pdf_y0"]) * _r_scale,
                                                "pdf_x0": round(_r_m["pdf_x0"], 2),
                                                "pdf_y0": round(_r_m["pdf_y0"], 2),
                                                "pdf_x1": round(_r_m["pdf_x1"], 2),
                                                "pdf_y1": round(_r_m["pdf_y1"], 2),
                                                "reason": _r_resolve_reason(_r_i),
                                                "author": _r_m.get("author") or _username,
                                                "created_at": _r_m.get("created_at") or _dt_now.now().isoformat(),
                                            })
                                        # CRIT-5: Route save-redaction-marks through _safe_write
                                        _rm_objs = _r_mark_objects
                                        _rm_page = _r_page_idx
                                        _rm_cn = current_cn
                                        def _save_marks_op():
                                            _target_rs = 'Has_Redactions' if row['redaction_status'] != 'Applied' else row['redaction_status']
                                            _sync_result = db_manager.save_redaction_with_sync(
                                                case_folder, _rm_cn, _rm_page, json.dumps(_rm_objs),
                                                _username, _r_priv_reasons, _REDACT_NO_REASON,
                                                target_redaction_status=_target_rs)
                                            _r_write_page_annotations(_r_pdf_path, _rm_page, _rm_objs, _REDACT_NO_REASON)
                                            if _sync_result:
                                                _rt_old, _rt_new, _, _, _old_rs = _sync_result
                                                if _rt_old != _rt_new:
                                                    db_manager.log_audit(case_folder, "TAGS_CHANGED", username=_username,
                                                        control_number=_rm_cn, module="Review", old_value=_rt_old, new_value=_rt_new)
                                                if _old_rs != 'Applied' and _old_rs != _target_rs:
                                                    try:
                                                        db_manager.log_audit(case_folder, "REDACTION_SAVED",
                                                            username=_username, control_number=_rm_cn,
                                                            module="Review", old_value=_old_rs or 'NULL',
                                                            new_value=_target_rs)
                                                    except Exception:
                                                        pass
                                        if _safe_write(
                                            _save_marks_op,
                                            f"Saved {len(_rm_objs)} mark(s) on page {_rm_page+1}.",
                                            f"❌ Failed to save redaction marks for {_rm_cn}",
                                            audit_params={"action": "REDACTION_SAVED", "control_number": _rm_cn,
                                                "module": "Review",
                                                "details": json.dumps({"page": _rm_page + 1, "mark_count": len(_rm_objs),
                                                    "reasons": [m["reason"] for m in _rm_objs if m.get("reason") and m["reason"] != _REDACT_NO_REASON]})}
                                        ):
                                            if _r_reasons_key in st.session_state:
                                                del st.session_state[_r_reasons_key]
                                            st.session_state[_r_reset_key] = _r_reset_counter + 1
                                            # Clear tag multiselect cache so Tags panel re-reads from
                                            # DB and reflects privilege tags synced by _r_sync_tags()
                                            for _cat_nm in _r_tag_cats:
                                                st.session_state.pop(f"tags_{_cat_nm}_{_rm_cn}", None)
                                            st.session_state.pop(f"tags_orphan_{_rm_cn}", None)
                                            st.rerun(scope="fragment")

                                    if not _case_closed and st.button("🗑 Clear This Page", key=f"redact_clear_pg_{current_cn}", width='stretch'):
                                        # CRIT-5: Route clear-page through _safe_write
                                        _cp_page = _r_page_idx
                                        _cp_cn = current_cn
                                        def _clear_page_op():
                                            db_manager.clear_redaction_marks(case_folder, _cp_cn, page_number=_cp_page)
                                            _r_write_page_annotations(_r_pdf_path, _cp_page, [], _REDACT_NO_REASON)
                                            _ct_old, _ct_new = _r_sync_tags(case_folder, _cp_cn, _r_priv_reasons, _REDACT_NO_REASON)
                                            if _ct_old != _ct_new:
                                                db_manager.log_audit(case_folder, "TAGS_CHANGED", username=_username,
                                                    control_number=_cp_cn, module="Review", old_value=_ct_old, new_value=_ct_new)
                                        if _safe_write(
                                            _clear_page_op,
                                            f"Marks cleared for page {_cp_page+1}.",
                                            f"❌ Failed to clear redaction marks for page {_cp_page+1}",
                                            audit_params={"action": "REDACTION_CLEARED", "control_number": _cp_cn,
                                                "module": "Review", "old_value": json.dumps({"page": _cp_page + 1})}
                                        ):
                                            if _r_reasons_key in st.session_state:
                                                del st.session_state[_r_reasons_key]
                                            st.rerun(scope="fragment")

                                    if not _case_closed and st.button("🗑🗑 Clear All Pages", key=f"redact_clear_all_{current_cn}", width='stretch'):
                                        # CRIT-5: Route clear-all through _safe_write
                                        _ca_cn = current_cn
                                        _ca_all_rows = db_manager.get_all_redaction_marks(case_folder, _ca_cn)
                                        def _clear_all_op():
                                            db_manager.clear_redaction_marks(case_folder, _ca_cn)
                                            _r_write_all_annotations(_r_pdf_path, _ca_all_rows, _REDACT_NO_REASON)
                                            _cat_old, _cat_new = _r_sync_tags(case_folder, _ca_cn, _r_priv_reasons, _REDACT_NO_REASON)
                                            if _cat_old != _cat_new:
                                                db_manager.log_audit(case_folder, "TAGS_CHANGED", username=_username,
                                                    control_number=_ca_cn, module="Review", old_value=_cat_old, new_value=_cat_new)
                                            _ca_old_status_val = db_manager.get_redaction_status(case_folder, _ca_cn) or 'NULL'
                                            db_manager.set_redaction_status(case_folder, _ca_cn, None)
                                            try:
                                                db_manager.log_audit(case_folder, "REDACTION_CLEARED",
                                                    username=_username, control_number=_ca_cn,
                                                    module="Review", old_value=_ca_old_status_val,
                                                    new_value='NULL')
                                            except Exception:
                                                pass
                                        if _safe_write(
                                            _clear_all_op,
                                            "All redaction marks cleared.",
                                            f"❌ Failed to clear all redaction marks for {_ca_cn}",
                                            audit_params={"action": "REDACTION_CLEARED", "control_number": _ca_cn,
                                                "module": "Review", "old_value": json.dumps({"scope": "all_pages"})}
                                        ):
                                            for _k in list(st.session_state.keys()):
                                                if _k.startswith(f"_redact_bg_{_ca_cn}_") or _k.startswith(f"_mark_reasons_{_ca_cn}_"):
                                                    del st.session_state[_k]
                                            st.rerun(scope="fragment")

                            # Marks summary table (full width, below both columns)
                            st.divider()
                            st.markdown("#### 📋 Redaction Summary")
                            _r_all_summary = db_manager.get_all_redaction_marks(case_folder, current_cn)
                            if not _r_all_summary:
                                st.info("No marks saved yet for this document.")
                            else:
                                _r_display_rows = []
                                for _r_sum_row in _r_all_summary:
                                    for _r_m in (json.loads(_r_sum_row['marks_json']) if _r_sum_row['marks_json'] else []):
                                        _r_display_rows.append({
                                            "Page": _r_sum_row['page_number'] + 1,
                                            "Reason": _r_m.get('reason', ''),
                                            "X (pt)": round(_r_m.get('pdf_x0', 0), 1),
                                            "Y (pt)": round(_r_m.get('pdf_y0', 0), 1),
                                            "W (pt)": round(_r_m.get('pdf_x1', 0) - _r_m.get('pdf_x0', 0), 1),
                                            "H (pt)": round(_r_m.get('pdf_y1', 0) - _r_m.get('pdf_y0', 0), 1),
                                        })
                                if _r_display_rows:
                                    st.dataframe(pd.DataFrame(_r_display_rows), width='stretch', hide_index=True)
                                else:
                                    st.info("No mark data to display.")

                        elif not _r_total_pages:
                            # First load — need to open PDF to get page count
                            try:
                                _r_doc_info = fitz.open(_r_pdf_path)
                                try:
                                    _r_total_pages = len(_r_doc_info)
                                finally:
                                    _r_doc_info.close()
                                st.session_state[_r_pgcount_key] = _r_total_pages
                                if _r_total_pages > 0:
                                    st.rerun()  # re-enter with page count cached (no scope — first load may not be a fragment rerun)
                            except Exception as _e:
                                st.error(f"❌ Could not open PDF: {_e}")


                _redact_tab_fragment()

        # ----------------------------
        # ✂️ SPLIT TAB
        # ----------------------------
        if _can_split:
         with tabs[_tab_idx["✂️ Split"]]:
            _s_pdf_path = full_path if ext == '.pdf' else None
            _s_status = row['processing_status']
            _s_has_bates = bool(row['begdoc'] and str(row['begdoc']).strip())

            # Gate checks
            if _case_closed:
                st.warning("Write operations are disabled on closed matters.")
            elif _s_status == 'Split_Source':
                st.info(f"This document has already been split. Check the Review grid for its child documents (split_source_cn = {current_cn}).")
            elif _s_has_bates:
                st.warning("This document has already been produced (Bates assigned). Splitting after production is not supported.")
            elif not _s_pdf_path or ext != '.pdf':
                st.info("Document splitting is only available for PDF documents.")
            elif not os.path.exists(_s_pdf_path):
                st.error(f"Source PDF not found on disk: {_s_pdf_path}")
            else:
                # Get page count
                _s_page_count = 0
                try:
                    _s_tmp_doc = fitz.open(_s_pdf_path)
                    _s_page_count = len(_s_tmp_doc)
                    _s_tmp_doc.close()
                except Exception as _e:
                    st.error(f"Could not read PDF: {_e}")

                if _s_page_count > 0:
                    st.caption(f"This document has **{_s_page_count} pages**.")

                    _split_mode = st.radio(
                        "Mode", ["✂️ Split into ranges", "🔪 Trim pages"],
                        key=f"_split_mode_{current_cn}", horizontal=True,
                    )

                    _s_is_trim_mode = (_split_mode == "🔪 Trim pages")

                if not _s_is_trim_mode and _s_page_count > 0:
                    # Session state for split ranges
                    _s_ranges_key = f"_split_ranges_{current_cn}"
                    if _s_ranges_key not in st.session_state:
                        st.session_state[_s_ranges_key] = []

                    _s_ctrl_col, _s_preview_col = st.columns([3, 7], gap="small")

                    with _s_ctrl_col:
                        # Auto-split button
                        if st.button("⚡ Auto-Split: One Page Each", key=f"split_auto_{current_cn}", width='stretch'):
                            _base_name = os.path.splitext(row['file_name'] or current_cn)[0]
                            st.session_state[_s_ranges_key] = [
                                {"page_start": i + 1, "page_end": i + 1,
                                 "file_name": f"{_base_name}_Page_{i+1}.pdf"}
                                for i in range(_s_page_count)
                            ]
                            st.rerun()

                        if st.button("➕ Add Range", key=f"split_add_{current_cn}", width='stretch'):
                            st.session_state[_s_ranges_key].append(
                                {"page_start": 1, "page_end": _s_page_count, "file_name": ""}
                            )
                            st.rerun()

                        st.divider()

                        # Display current ranges
                        _s_ranges = st.session_state[_s_ranges_key]
                        _s_to_remove = None
                        for _s_i, _s_r in enumerate(_s_ranges):
                            st.markdown(f"**Range {_s_i + 1}**")
                            _s_c1, _s_c2 = st.columns(2)
                            _s_ranges[_s_i]["page_start"] = _s_c1.number_input(
                                "Start", min_value=1, max_value=_s_page_count,
                                value=_s_r.get("page_start", 1),
                                key=f"split_start_{current_cn}_{_s_i}",
                            )
                            _s_ranges[_s_i]["page_end"] = _s_c2.number_input(
                                "End", min_value=1, max_value=_s_page_count,
                                value=_s_r.get("page_end", _s_page_count),
                                key=f"split_end_{current_cn}_{_s_i}",
                            )
                            _s_ranges[_s_i]["file_name"] = st.text_input(
                                "File name",
                                value=_s_r.get("file_name", ""),
                                placeholder=f"Document_{_s_i+1}.pdf",
                                key=f"split_name_{current_cn}_{_s_i}",
                            )
                            if st.button("🗑 Remove", key=f"split_rm_{current_cn}_{_s_i}"):
                                _s_to_remove = _s_i

                            st.divider()

                        if _s_to_remove is not None:
                            st.session_state[_s_ranges_key].pop(_s_to_remove)
                            st.rerun()

                    with _s_preview_col:
                        # Validation
                        if _s_ranges:
                            # Convert to 0-based for validation
                            _s_validated = []
                            _s_errors = []
                            _s_warnings = []

                            for _s_i, _s_r in enumerate(_s_ranges):
                                ps = _s_r["page_start"] - 1  # 0-based
                                pe = _s_r["page_end"] - 1
                                fn = _s_r.get("file_name", "").strip() or f"Document_{_s_i+1}.pdf"
                                if ps > pe:
                                    _s_errors.append(f"Range {_s_i+1}: start page ({ps+1}) > end page ({pe+1})")
                                if ps < 0 or pe >= _s_page_count:
                                    _s_errors.append(f"Range {_s_i+1}: pages out of bounds")
                                _s_validated.append({"page_start": ps, "page_end": pe, "file_name": fn})

                            # Check overlaps
                            _s_sorted = sorted(_s_validated, key=lambda x: x["page_start"])
                            for _s_j in range(1, len(_s_sorted)):
                                if _s_sorted[_s_j]["page_start"] <= _s_sorted[_s_j-1]["page_end"]:
                                    _s_errors.append(
                                        f"Overlap: pages {_s_sorted[_s_j-1]['page_end']+1} and "
                                        f"{_s_sorted[_s_j]['page_start']+1}"
                                    )

                            # Check for gaps
                            _s_covered = set()
                            for _s_v in _s_validated:
                                for _s_p in range(_s_v["page_start"], _s_v["page_end"] + 1):
                                    _s_covered.add(_s_p)
                            _s_all_pages = set(range(_s_page_count))
                            _s_gaps = sorted(_s_all_pages - _s_covered)
                            if _s_gaps:
                                _s_gap_display = ", ".join(str(g+1) for g in _s_gaps[:10])
                                if len(_s_gaps) > 10:
                                    _s_gap_display += f" ... (+{len(_s_gaps)-10} more)"
                                _s_warnings.append(f"Pages not assigned: {_s_gap_display}. These will be discarded.")

                            if len(_s_ranges) < 2:
                                _s_errors.append("At least 2 split ranges are required.")

                            # Display validation
                            st.markdown("#### Validation")
                            if _s_errors:
                                for _s_e in _s_errors:
                                    st.error(_s_e)
                            if _s_warnings:
                                for _s_w in _s_warnings:
                                    st.warning(_s_w)
                            if not _s_errors and not _s_warnings:
                                st.success(f"All {_s_page_count} pages assigned across {len(_s_ranges)} ranges. Ready to split.")
                            elif not _s_errors:
                                st.info(f"{len(_s_covered)} of {_s_page_count} pages assigned across {len(_s_ranges)} ranges.")

                            # Range summary table
                            st.markdown("#### Split Ranges")
                            _s_table = []
                            for _s_i, _s_v in enumerate(_s_validated):
                                _s_table.append({
                                    "#": _s_i + 1,
                                    "Pages": f"{_s_v['page_start']+1}-{_s_v['page_end']+1}",
                                    "Count": _s_v['page_end'] - _s_v['page_start'] + 1,
                                    "File Name": _s_v['file_name'],
                                })
                            st.dataframe(pd.DataFrame(_s_table), hide_index=True, width='stretch' if len(_s_table) > 0 else None)

                            # Execute button
                            _s_can_execute = not _s_errors and len(_s_ranges) >= 2
                            _s_confirm_key = f"_split_confirmed_{current_cn}"

                            if _s_can_execute:
                                if not st.session_state.get(_s_confirm_key):
                                    st.warning(
                                        f"This will create **{len(_s_ranges)} new documents** and mark "
                                        f"**{current_cn}** as Split_Source. The source will no longer appear "
                                        f"in the review grid. This cannot be undone."
                                    )
                                    if st.button("✂️ Execute Split", key=f"split_exec_{current_cn}",
                                                 type="primary", width='stretch'):
                                        st.session_state[_s_confirm_key] = True
                                        st.rerun()
                                else:
                                    # Confirmed — execute the split
                                    with st.spinner("Splitting document..."):
                                        result = db_manager.split_document(
                                            case_folder, current_cn, _s_validated, _username
                                        )

                                    st.session_state.pop(_s_confirm_key, None)
                                    st.session_state.pop(_s_ranges_key, None)

                                    if result["error"]:
                                        st.error(f"Split failed: {result['error']}")
                                    else:
                                        st.success(
                                            f"Split complete! Created {len(result['new_documents'])} new documents:"
                                        )
                                        for _s_nd in result["new_documents"]:
                                            st.write(
                                                f"- **{_s_nd['control_number']}** — "
                                                f"{_s_nd['file_name']} "
                                                f"(pages {_s_nd['page_start']+1}-{_s_nd['page_end']+1})"
                                            )
                                        st.info(
                                            "Run **Module 2 (Processor)** on the new documents to extract "
                                            "text, metadata, and index them for search."
                                        )
                        else:
                            st.info("Add page ranges using the controls on the left, or click **Auto-Split** to create one document per page.")

                if _s_is_trim_mode and _s_page_count > 0:
                    # ── TRIM MODE ──────────────────────────────────────────
                    _t_ctrl_col, _t_preview_col = st.columns([3, 7], gap="small")

                    with _t_ctrl_col:
                        _t_input = st.text_area(
                            "Pages to remove (1-based)",
                            placeholder="e.g. 3-4, 8, 20-24, 30-31",
                            key=f"trim_input_{current_cn}",
                            height=120,
                        )
                        st.caption("Enter page numbers and/or ranges separated by commas. Example: `3-4, 8, 20-24`")

                    with _t_preview_col:
                        _t_pages = []
                        _t_error = None

                        if _t_input and _t_input.strip():
                            try:
                                _t_parsed = set()
                                for part in _t_input.replace(';', ',').split(','):
                                    part = part.strip()
                                    if not part:
                                        continue
                                    if '-' in part:
                                        start_s, end_s = part.split('-', 1)
                                        start_v, end_v = int(start_s.strip()), int(end_s.strip())
                                        _t_parsed.update(range(start_v - 1, end_v))  # 1-based to 0-based
                                    else:
                                        _t_parsed.add(int(part.strip()) - 1)

                                invalid = [p for p in _t_parsed if p < 0 or p >= _s_page_count]
                                if invalid:
                                    _t_error = f"Page numbers out of range: {sorted(p+1 for p in invalid)}"
                                elif len(_t_parsed) >= _s_page_count:
                                    _t_error = "Cannot remove all pages -- at least one must survive."
                                elif not _t_parsed:
                                    _t_error = "No valid page numbers entered."
                                else:
                                    _t_pages = sorted(_t_parsed)
                            except ValueError as _ve:
                                _t_error = f"Invalid input: {_ve}"

                        st.markdown("#### Validation")
                        if _t_error:
                            st.error(_t_error)
                        elif _t_pages:
                            _t_surviving = _s_page_count - len(_t_pages)
                            st.success(
                                f"Will remove **{len(_t_pages)}** pages, "
                                f"keeping **{_t_surviving}** of {_s_page_count}."
                            )
                            if len(_t_pages) > _s_page_count // 2:
                                st.warning(f"Removing more than half the document ({len(_t_pages)}/{_s_page_count} pages).")

                            # Page list preview
                            _t_page_display = ", ".join(str(p+1) for p in _t_pages[:20])
                            if len(_t_pages) > 20:
                                _t_page_display += f" ... (+{len(_t_pages)-20} more)"
                            st.caption(f"Removing pages: {_t_page_display}")

                            # Execute
                            _t_confirm_key = f"_trim_confirmed_{current_cn}"
                            if not st.session_state.get(_t_confirm_key):
                                st.warning(
                                    f"This will remove **{len(_t_pages)} pages** and create a new "
                                    f"**{_t_surviving}-page** document. The original will be preserved "
                                    f"but hidden. This cannot be undone."
                                )
                                if st.button("🔪 Trim Document", key=f"trim_exec_{current_cn}",
                                             type="primary", width='stretch'):
                                    st.session_state[_t_confirm_key] = True
                                    st.rerun()
                            else:
                                with st.spinner("Trimming document..."):
                                    _t_result = db_manager.trim_document(
                                        case_folder, current_cn, _t_pages, _username
                                    )

                                st.session_state.pop(_t_confirm_key, None)
                                st.session_state.pop(f"trim_input_{current_cn}", None)

                                if _t_result["error"]:
                                    st.error(f"Trim failed: {_t_result['error']}")
                                else:
                                    _t_nd = _t_result["new_document"]
                                    st.success(
                                        f"Trim complete! Created **{_t_nd['control_number']}** — "
                                        f"{_t_nd['file_name']} ({_t_nd['page_count']} pages)"
                                    )
                                    st.info(
                                        "Run **Module 2 (Processor)** on the new document to extract "
                                        "text, metadata, and index it for search."
                                    )
                        else:
                            st.info("Enter page numbers to remove in the text area on the left.")


#
# PANE 3: Coding & Metadata (Sidebar, below queue)
#
with col_sidebar:
    st.subheader("Tags")
    
    # Hidden Metadata Popover
    row_dict = dict(row) if row else {}
    with st.popover("👁️ View Full Metadata", width='stretch'):
        st.write(f"**Unified Title:** {row_dict.get('file_name', '')}")
        if row_dict.get('begdoc'):
            st.write(f"**Bates Range:** {row_dict.get('begdoc')} - {row_dict.get('enddoc', '')}")
        st.write(f"**Custodian:** {row_dict.get('custodian', '')}")
        st.write(f"**Record Type:** {row_dict.get('record_type', '')}")
        
        dyn_meta_raw = row_dict.get('dynamic_metadata')
        if dyn_meta_raw:
            try:
                import json
                dyn_meta = json.loads(dyn_meta_raw)
                if dyn_meta:
                    st.divider()
                    st.caption("Extracted Properties:")
                    for k, v in dyn_meta.items():
                        st.write(f"**{k}:** {v}")
            except Exception:
                pass
                
        fv_doc_id = row_dict.get('filevine_doc_id')
        if fv_doc_id and fv_firm_subdomain:
            fv_link = f"https://{fv_firm_subdomain}.filevineapp.com/docwebviewer/edit/{fv_doc_id}"
            st.markdown("---")
            st.markdown(f"🔗 **[Open in Filevine]({fv_link})**")

    # Coding Panel logic
    def coding_layout():
        import json as _json

        # Load tag categories from DB (case-level config)
        tag_cats = db_manager.get_tag_categories(case_folder)

        # Build flat list of all known tags from categories
        all_category_tags = []
        for cat_data in tag_cats.values():
            all_category_tags.extend(cat_data.get('members', []))

        current_tags_str = row_dict.get('tags', '')
        # Safety split standardizing on comma
        current_tags = [t.strip() for t in (current_tags_str or '').replace(';', ',').split(',') if t.strip()]

        # Identify System Tags (analytics, dedup, junk, etc - things users shouldn't edit)
        SYSTEM_TAG_PREFIXES = ("NearDupe-", "Thread-", "NIST-", "Junk ", "Inclusive-")
        system_tags = [t for t in current_tags if any(t.startswith(p) for p in SYSTEM_TAG_PREFIXES)]
        user_tags = [t for t in current_tags if t not in system_tags]

        # Merge any user tags already on the doc that aren't in any category (legacy or custom)
        orphan_tags = [t for t in user_tags if t not in all_category_tags]

        with st.form("coding_form", border=False):
            st.caption("Review Decisions")

            if system_tags:
                with st.expander(f"⚙️ System Tags ({len(system_tags)})", expanded=False):
                    badges = " ".join([
                        f"<span style='display:inline-block; background-color:rgba(0,123,255,0.1); "
                        f"color:#007bff; border:1px solid #007bff; border-radius:12px; "
                        f"padding:2px 8px; margin:2px 4px 6px 0; font-size:0.85em;'>{str(t)}</span>"
                        for t in system_tags
                    ])
                    st.markdown(badges, unsafe_allow_html=True)

            # Privilege tags auto-applied by the redaction engine — used for the indicator below
            _coding_redact_tags = set()
            try:
                _coding_all_rm = db_manager.get_all_redaction_marks(case_folder, current_cn)
                for _coding_rm_row in _coding_all_rm:
                    for _coding_m in (json.loads(_coding_rm_row['marks_json']) if _coding_rm_row['marks_json'] else []):
                        _coding_r = _coding_m.get('reason', '')
                        if _coding_r and _coding_r != _REDACT_NO_REASON:
                            _coding_redact_tags.add(_coding_r)
            except Exception:
                _coding_redact_tags = set()

            # Render each category as a labeled group
            selected_tags = []
            for cat_name, cat_data in tag_cats.items():
                cat_members = cat_data.get('members', [])
                cat_color = cat_data.get('color', '#888888')
                cat_defaults = [t for t in user_tags if t in cat_members]

                st.markdown(
                    f"<span style='color:{cat_color}; font-size:0.78em; font-weight:700; "
                    f"text-transform:uppercase; letter-spacing:0.08em;'>▸ {cat_name}</span>",
                    unsafe_allow_html=True
                )
                chosen = st.multiselect(
                    cat_name,
                    options=cat_members,
                    default=cat_defaults,
                    label_visibility="collapsed",
                    key=f"tags_{cat_name}_{current_cn}"
                )
                selected_tags.extend(chosen)
                if cat_data.get('is_privilege') and any(t in _coding_redact_tags for t in chosen):
                    st.caption("🔒 Set via redaction marks")

                # ── Privilege Disposition (appears after privilege category when tags selected)
                if cat_data.get('is_privilege') and chosen:
                    st.markdown(
                        "<span style='color:#ff6b6b; font-size:0.78em; font-weight:700; "
                        "text-transform:uppercase; letter-spacing:0.08em;'>▸ Privilege Disposition</span>",
                        unsafe_allow_html=True
                    )
                    # beta-2.10 Commit 4: inbound docs don't get a privilege disposition.
                    # Opposing counsel's production is already produced; Withhold/Redact on
                    # our side is meaningless. Show a banner instead of the radio and skip
                    # the write in the save handler below.
                    if _is_inbound_doc(row_dict.get('source_party')):
                        _sp_label = row_dict.get('source_party') or 'opposing counsel'
                        st.info(
                            f"📥 This document is from an inbound production by "
                            f"**{_sp_label}**. Privilege dispositions do not apply — "
                            f"they've already produced it to us. Tags are still saved."
                        )
                    else:
                        _current_priv_status = db_manager.get_privilege_status(case_folder, current_cn)
                        _disposition_options = ["Redact (produce with redactions)", "Withhold (exclude from production)"]
                        # Context-aware default: preserve existing, or Redact if marks exist, Withhold if not
                        if _current_priv_status == 'Withhold':
                            _default_disp_idx = 1
                        elif _current_priv_status == 'Redact':
                            _default_disp_idx = 0
                        else:
                            _has_marks = db_manager.has_redaction_marks(case_folder, current_cn)
                            _default_disp_idx = 0 if _has_marks else 1
                        _disposition_choice = st.radio(
                            "Privilege Disposition",
                            options=_disposition_options,
                            index=_default_disp_idx,
                            label_visibility="collapsed",
                            key=f"priv_disp_{current_cn}"
                        )

            # ── Confidentiality Designation ────────────────────────────
            _conf_levels = db_manager.get_confidentiality_levels(case_folder)
            _conf_options = ['(None — use production default)'] + _conf_levels
            _current_conf = db_manager.get_confidentiality_designation(case_folder, current_cn)
            _conf_idx = _conf_options.index(_current_conf) if _current_conf in _conf_options else 0
            _conf_choice = st.selectbox(
                "🔒 Confidentiality",
                _conf_options,
                index=_conf_idx,
                key=f"conf_desig_{current_cn}",
                disabled=_case_closed,
            )

            # ── Production Category ────────────────────────────────
            # permission: assign_production_category (Reviewer+)
            _prod_cats = db_manager.get_production_categories(case_folder)
            if _prod_cats:
                _prod_cat_names = [c['name'] for c in _prod_cats]
                _prod_cat_options = ['(Uncategorized)'] + _prod_cat_names + ['+ New Category']
                _current_prod_cat = row_dict.get('production_category')
                _prod_cat_idx = _prod_cat_options.index(_current_prod_cat) if _current_prod_cat in _prod_cat_options else 0
                _prod_cat_colors = {c['name']: c.get('color', '#888') for c in _prod_cats}
                _prod_cat_choice = st.selectbox(
                    "📂 Production Category",
                    _prod_cat_options,
                    index=_prod_cat_idx,
                    key=f"prod_cat_{current_cn}",
                    disabled=_case_closed,
                )
                if _prod_cat_choice == '+ New Category' and not _case_closed:
                    _new_cat_name = st.text_input("New category name", key=f"new_prod_cat_{current_cn}")
                    _new_cat_color = st.color_picker("Color", value="#888888", key=f"new_prod_cat_color_{current_cn}")
                    st.caption("Click **Save** to create and assign the new category.")

            # ── Custom Coding Fields ──────────────────────────
            _coding_fields = db_manager.get_coding_fields(case_folder)
            if _coding_fields:
                _doc_coding = db_manager.get_document_coding(case_folder, current_cn)
                st.markdown("---")
                st.caption("Issue Coding")
                _coding_values = {}
                for _cf in _coding_fields:
                    _cf_id = _cf['id']
                    _cf_current = _doc_coding.get(_cf_id, '')
                    if _cf['field_type'] == 'picklist':
                        _cf_options = json.loads(_cf['pick_list_json'] or '[]')
                        _cf_options_with_blank = [''] + _cf_options
                        _cf_idx = _cf_options_with_blank.index(_cf_current) if _cf_current in _cf_options_with_blank else 0
                        _coding_values[_cf_id] = st.selectbox(
                            _cf['field_name'],
                            _cf_options_with_blank,
                            index=_cf_idx,
                            key=f"coding_{_cf_id}_{current_cn}",
                        )
                    elif _cf['field_type'] == 'boolean':
                        _coding_values[_cf_id] = st.checkbox(
                            _cf['field_name'],
                            value=(_cf_current == 'True'),
                            key=f"coding_{_cf_id}_{current_cn}",
                        )
                    elif _cf['field_type'] == 'text':
                        _coding_values[_cf_id] = st.text_input(
                            _cf['field_name'],
                            value=_cf_current or '',
                            key=f"coding_{_cf_id}_{current_cn}",
                        )

            # Build list of privilege-category tags currently selected (for save handler)
            _priv_members_set = set()
            for _pc_name, _pc_data in tag_cats.items():
                if _pc_data.get('is_privilege'):
                    _priv_members_set.update(_pc_data.get('members', []))
            _priv_tags_on_doc = [t for t in selected_tags if t in _priv_members_set]

            # Orphan tags bucket (user tags on the doc not in any category)
            if orphan_tags:
                st.markdown(
                    "<span style='color:#aaa; font-size:0.78em; font-weight:700; "
                    "text-transform:uppercase; letter-spacing:0.08em;'>▸ Other</span>",
                    unsafe_allow_html=True
                )
                chosen_orphans = st.multiselect(
                    "Other",
                    options=orphan_tags,
                    default=[t for t in user_tags if t in orphan_tags],
                    label_visibility="collapsed",
                    key=f"tags_orphan_{current_cn}"
                )
                selected_tags.extend(chosen_orphans)

            st.write("")
            submit_cols = st.columns(2)
            btn_save = submit_cols[0].form_submit_button("Save", width='stretch')
            btn_next = submit_cols[1].form_submit_button("Reviewed — Next ▶", width='stretch', type="primary")

            if (btn_save or btn_next) and _case_closed:
                st.warning("Write operations are disabled on closed matters.")
            elif btn_save or btn_next:
                _category_changed = False
                # CRIT-5: Route individual tag save through _safe_write
                final_tags = selected_tags + system_tags
                tag_str = ", ".join(final_tags)
                _old_tags_str = current_tags_str or ''
                _ts_cn = current_cn
                def _tag_save_op():
                    db_manager.update_document_tags(case_folder, _ts_cn, tag_str)
                    # Only stamp reviewed_by when reviewer explicitly marks as reviewed (not on plain Save)
                    if btn_next:
                        db_manager.mark_document_reviewed(case_folder, _ts_cn, _username)
                _audit_kw = ({"action": "TAGS_CHANGED", "control_number": _ts_cn, "module": "Review",
                              "old_value": _old_tags_str, "new_value": tag_str}
                             if _old_tags_str != tag_str else None)
                if _safe_write(_tag_save_op, f"Saved {_ts_cn}!", f"❌ Failed to save tags for {_ts_cn}",
                               audit_params=_audit_kw):
                    # Cascade user-tag changes to attachment children
                    _cascade_tag_to_children(case_folder, _ts_cn, tag_str, _username, action='set')
                    st.session_state[f"tags_{_ts_cn}"] = tag_str

                    # ── Save privilege disposition ──────────────────────────
                    # beta-2.10 Commit 4: skip all privilege_status writes for
                    # inbound documents. Tags, notes, redaction marks, and
                    # confidentiality designations are still saved — only the
                    # privilege disposition (Withhold/Redact/Clear) is suppressed.
                    # The UI shows a banner instead of the disposition radio, so
                    # this guard is belt-and-suspenders against any code path
                    # that would otherwise reach here (e.g., _priv_tags_on_doc
                    # true because of a stale tag on an inbound doc).
                    _ts_is_inbound = _is_inbound_doc(row_dict.get('source_party'))
                    if _ts_is_inbound:
                        pass  # privilege writes suppressed for inbound docs
                    elif _priv_tags_on_doc:
                        # Guard: disposition radio only renders when privilege tags are
                        # selected in the form — fall back to DB value if not rendered
                        if '_disposition_choice' not in dir():
                            _new_disp = db_manager.get_privilege_status(case_folder, _ts_cn) or 'Redact'
                        else:
                            _new_disp = 'Withhold' if 'Withhold' in _disposition_choice else 'Redact'
                        _old_disp = db_manager.get_privilege_status(case_folder, _ts_cn)
                        if _old_disp != _new_disp:
                            db_manager.set_privilege_status(case_folder, _ts_cn, _new_disp)
                            try:
                                db_manager.log_audit(case_folder, "PRIVILEGE_DISPOSITION_CHANGED",
                                    username=_username, control_number=_ts_cn,
                                    module="Review", old_value=_old_disp or 'NULL', new_value=_new_disp)
                            except Exception:
                                pass
                    else:
                        # No privilege tags in current selection — only clear
                        # privilege_status if user explicitly removed privilege tags
                        # AND no redaction marks exist (redaction engine owns the
                        # disposition when marks are present)
                        _old_priv_tags = [t.strip() for t in (_old_tags_str or '').replace(';', ',').split(',')
                                          if t.strip() and t.strip() in _priv_members_set]
                        if _old_priv_tags and not db_manager.has_redaction_marks(case_folder, _ts_cn):
                            _old_disp = db_manager.get_privilege_status(case_folder, _ts_cn)
                            if _old_disp is not None:
                                db_manager.set_privilege_status(case_folder, _ts_cn, None)
                                try:
                                    db_manager.log_audit(case_folder, "PRIVILEGE_DISPOSITION_CHANGED",
                                        username=_username, control_number=_ts_cn,
                                        module="Review", old_value=_old_disp, new_value='NULL')
                                except Exception:
                                    pass

                    # ── Save confidentiality designation ──────────────
                    _new_conf = _conf_choice if _conf_choice != '(None — use production default)' else None
                    _old_conf = db_manager.get_confidentiality_designation(case_folder, _ts_cn)
                    if _new_conf != _old_conf:
                        db_manager.set_confidentiality_designation(case_folder, _ts_cn, _new_conf)
                        try:
                            db_manager.log_audit(case_folder, "CONFIDENTIALITY_DESIGNATED",
                                username=_username, control_number=_ts_cn,
                                module="Review", old_value=_old_conf or 'NULL', new_value=_new_conf or 'NULL')
                        except Exception:
                            pass

                    # ── Save production category ──────────────────────
                    if _prod_cats and _prod_cat_choice == '+ New Category':
                        # Inline new category creation (inputs are inside the form)
                        _new_cat_name_val = st.session_state.get(f"new_prod_cat_{_ts_cn}", '').strip()
                        _new_cat_color_val = st.session_state.get(f"new_prod_cat_color_{_ts_cn}", '#888888')
                        if _new_cat_name_val:
                            _new_cat = {
                                'name': _new_cat_name_val,
                                'sort_order': len(_prod_cats) + 1,
                                'color': _new_cat_color_val,
                                'keywords': [],
                                'extensions': [],
                            }
                            _updated_cats = list(_prod_cats) + [_new_cat]
                            db_manager.save_production_categories(case_folder, _updated_cats,
                                username=_username)
                            db_manager.update_document_production_category(
                                case_folder, _ts_cn, _new_cat_name_val,
                                username=_username)
                            _category_changed = True
                    elif _prod_cats:
                        _new_prod_cat = _prod_cat_choice if _prod_cat_choice != '(Uncategorized)' else None
                        _old_prod_cat = row_dict.get('production_category')
                        if _new_prod_cat != _old_prod_cat:
                            db_manager.update_document_production_category(
                                case_folder, _ts_cn, _new_prod_cat,
                                username=_username)
                            _category_changed = True

                    # ── Save custom coding fields ─────────────────────
                    if _coding_fields:
                        for _cf in _coding_fields:
                            _cf_val = _coding_values.get(_cf['id'], '')
                            if _cf['field_type'] == 'boolean':
                                _cf_val = str(_cf_val)
                            if _cf_val:  # Only save non-empty values
                                db_manager.upsert_document_coding(
                                    case_folder, _ts_cn, _cf['id'],
                                    _cf_val, _username
                                )
                                try:
                                    db_manager.log_audit(case_folder, "CODING_VALUE_CHANGED",
                                        username=_username, control_number=_ts_cn,
                                        module="Review",
                                        details=json.dumps({"field": _cf['name'], "value": str(_cf_val)}))
                                except Exception:
                                    pass

                    # ── Auto-update batch status ──────────────────────
                    if _active_batch_id:
                        try:
                            _bs_conn = db_manager.get_connection(case_folder)
                            _bs_remaining = _bs_conn.execute("""  -- db_manager: exempt (batch status update)
                                SELECT COUNT(*) FROM batch_documents bd
                                JOIN documents d ON bd.control_number = d.control_number
                                WHERE bd.batch_id = ? AND d.reviewed_by IS NULL
                            """, (_active_batch_id,)).fetchone()[0]
                            _bs_new_status = 'Complete' if _bs_remaining == 0 else 'In Progress'
                            _bs_conn.execute("UPDATE review_batches SET status = ? WHERE id = ?",  # db_manager: exempt (batch status update)
                                            (_bs_new_status, _active_batch_id))
                            _bs_conn.commit()
                            _bs_conn.close()
                            try:
                                db_manager.log_audit(case_folder, "BATCH_STATUS_CHANGED",
                                    username=_username, control_number=_ts_cn,
                                    module="Review",
                                    details=json.dumps({"batch_id": _active_batch_id, "new_status": _bs_new_status}))
                            except Exception:
                                pass
                        except Exception:
                            pass

                    if btn_next:
                        if st.session_state.get('_peek_cn'):
                            # Exit peek mode, return to queue
                            _return_idx = st.session_state.pop('_peek_return_idx', 0)
                            st.session_state.pop('_peek_cn', None)
                            st.session_state.current_doc_idx = _return_idx
                            st.rerun()
                        elif st.session_state.current_doc_idx < len(queue_list) - 1:
                            st.session_state.current_doc_idx += 1
                            st.rerun()
                        else:
                            st.toast("End of Queue reached!", icon="🛑")
                    elif _category_changed:
                        # Sidebar rendered before save — rerun so it reads fresh counts
                        st.rerun()

        # ── Exhibit Designation ──────────────────────────────────────
        # permission: mark_exhibit
        _prod_records = db_manager.get_document_productions(case_folder, current_cn)
        if _prod_records:
            st.markdown("---")
            st.caption("Exhibits")

            # Show existing exhibit badges
            _doc_exhibits = db_manager.get_document_exhibit_sets(case_folder, current_cn)
            if _doc_exhibits:
                _badge_parts = []
                for _de in _doc_exhibits:
                    _badge_parts.append(
                        f"<span style='background:#e2e8f0; color:#2d3748; "
                        f"padding:2px 8px; border-radius:4px; font-size:0.8em; "
                        f"margin-right:4px; display:inline-block; margin-bottom:4px;'>"
                        f"Exhibit {_de['exhibit_number']} — {_de['set_name']}</span>"
                    )
                st.markdown("".join(_badge_parts), unsafe_allow_html=True)

            # Mark as Exhibit popover (Reviewer+)
            if not _case_closed and auth_manager.has_permission('mark_exhibit'):
                _exhibit_sets = db_manager.get_exhibit_sets(case_folder)
                if _exhibit_sets:
                    with st.expander("Mark as Exhibit"):
                        _set_options = {es['set_name']: es['id'] for es in _exhibit_sets}
                        _selected_set_name = st.selectbox(
                            "Exhibit Set",
                            options=list(_set_options.keys()),
                            key=f"ex_set_{current_cn}",
                        )
                        _ex_num = st.text_input(
                            "Exhibit Number",
                            key=f"ex_num_{current_cn}",
                            placeholder="e.g., 1, A-3, Plaintiff's 12",
                        )
                        _ex_desc = st.text_input(
                            "Description",
                            key=f"ex_desc_{current_cn}",
                            placeholder="e.g., Employment agreement dated 3/15/2025",
                        )
                        if st.button("Add as Exhibit", key=f"ex_add_{current_cn}"):
                            if not _ex_num.strip():
                                st.error("Exhibit number is required.")
                            else:
                                _set_id = _set_options[_selected_set_name]
                                _next_order = db_manager.get_next_sort_order(
                                    case_folder, _set_id
                                )
                                try:
                                    db_manager.add_exhibit(
                                        case_folder, _set_id, current_cn,
                                        _ex_num.strip(), _ex_desc.strip(),
                                        _next_order, _username
                                    )
                                    try:
                                        db_manager.log_audit(
                                            case_folder, "EXHIBIT_ADDED",
                                            username=_username,
                                            control_number=current_cn,
                                            module="Review",
                                            details=f"Exhibit {_ex_num.strip()} in {_selected_set_name}"
                                        )
                                    except Exception:
                                        pass
                                    st.success(
                                        f"Marked as Exhibit {_ex_num.strip()} "
                                        f"in {_selected_set_name}"
                                    )
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error(
                                        "This exhibit number is already used in this set, "
                                        "or this document is already in this set."
                                    )
                else:
                    st.caption(
                        "No exhibit sets created yet. "
                        "A manager can create one on the Exhibits page."
                    )

        # ── Inline New Tag Creator ──────────────────────────────────────────
        with st.expander("➕ Add New Tag to This Document"):
            st.caption(
                "Type a new tag and assign it to a category. "
                "It will be saved permanently and applied to this document immediately."
            )
            new_tag_name = st.text_input(
                "Tag name",
                placeholder="e.g. Joint Defense Privilege",
                key=f"new_tag_input_{current_cn}"
            )
            cat_names = list(tag_cats.keys())
            cat_choice = st.selectbox(
                "Category",
                options=cat_names + ["➕ Create New Category"],
                key=f"new_tag_cat_{current_cn}"
            )
            new_cat_name = ""
            if cat_choice == "➕ Create New Category":
                new_cat_name = st.text_input(
                    "New category name",
                    placeholder="e.g. Protective Order",
                    key=f"new_cat_input_{current_cn}"
                )

            if st.button("✅ Add Tag & Apply to This Document", key=f"add_tag_btn_{current_cn}"):
                tag_to_add = new_tag_name.strip()
                if _case_closed:
                    st.warning("Write operations are disabled on closed matters.")
                elif not tag_to_add:
                    st.warning("Please enter a tag name.")
                else:
                    target_cat = new_cat_name.strip() if cat_choice == "➕ Create New Category" else cat_choice
                    if not target_cat:
                        st.warning("Please enter a category name.")
                    else:
                        # CRIT-5: Route new-tag-creation + apply through _safe_write
                        updated_cats = db_manager.get_tag_categories(case_folder)
                        if target_cat not in updated_cats:
                            is_priv = any(w in target_cat.lower() for w in ['privilege', 'work product', 'protection', 'objection'])
                            updated_cats[target_cat] = {"is_privilege": is_priv, "color": "#f0a500", "members": []}
                        if tag_to_add not in updated_cats[target_cat]['members']:
                            updated_cats[target_cat]['members'].append(tag_to_add)
                        _nt_cn = current_cn
                        _nt_tag = tag_to_add
                        _nt_cat = target_cat
                        _nt_cats = updated_cats
                        def _new_tag_op():
                            db_manager.save_tag_categories(case_folder, _nt_cats)
                            _doc_tags = [t.strip() for t in (row_dict.get('tags') or '').split(',') if t.strip()]
                            if _nt_tag not in _doc_tags:
                                _doc_tags.append(_nt_tag)
                            db_manager.update_document_tags(case_folder, _nt_cn, ", ".join(_doc_tags))
                        is_priv_cat = _nt_cats[_nt_cat].get('is_privilege', False)
                        priv_note = " It will appear in the Privilege Log." if is_priv_cat else ""
                        if _safe_write(
                            _new_tag_op,
                            f"'{_nt_tag}' added to '{_nt_cat}' and applied.{priv_note}",
                            f"❌ Failed to add tag '{_nt_tag}'",
                            audit_params={"action": "TAG_APPLIED", "control_number": _nt_cn,
                                          "module": "Review", "new_value": _nt_tag}
                        ):
                            # Cascade new tag to children
                            _cascade_tag_to_children(case_folder, _nt_cn, _nt_tag, _username, action='add')
                            st.rerun()

    if row:
        # permission: tag
        if auth_manager.has_permission('tag'):
            coding_layout()

        # ── Clawback / Inadvertent Disclosure ──────────────────────────────
        # permission: case_settings
        if auth_manager.has_permission('case_settings'):
            st.divider()
            _cb_status = row_dict.get('clawback_status') or ''
            _cb_date = row_dict.get('clawback_date') or ''

            if _cb_status == 'Clawback_Demanded':
                st.markdown(
                    f"<span style='color:#ff6b6b; font-weight:700;'>⚠️ CLAWBACK DEMANDED</span> "
                    f"<span style='color:#aaa; font-size:0.85em;'>{_cb_date}</span>",
                    unsafe_allow_html=True
                )
                st.caption("This document is blocked from all future productions.")
            elif _cb_status == 'Clawback_Resolved':
                st.markdown(
                    "<span style='color:#51cf66; font-weight:700;'>✅ Clawback Resolved</span>",
                    unsafe_allow_html=True
                )

            with st.expander(
                "⚠️ Clawback / Inadvertent Disclosure" if not _cb_status else "⚠️ Manage Clawback",
                expanded=(_cb_status == 'Clawback_Demanded')
            ):
                if _case_closed:
                    st.warning("Write operations are disabled on closed matters.")
                else:
                    with st.form(f"clawback_form_{current_cn}", border=False):
                        _cb_new_status = st.selectbox(
                            "Status",
                            options=["— No clawback —", "Clawback_Demanded", "Clawback_Resolved"],
                            index=(
                                1 if _cb_status == 'Clawback_Demanded'
                                else 2 if _cb_status == 'Clawback_Resolved'
                                else 0
                            ),
                            key=f"cb_status_{current_cn}"
                        )
                        _cb_new_date = st.date_input(
                            "Demand Date",
                            value=None,
                            help="Date the clawback demand letter was sent.",
                            key=f"cb_date_{current_cn}"
                        )
                        _cb_notes = st.text_area(
                            "Notes",
                            placeholder="Opposing counsel name, letter reference, etc.",
                            key=f"cb_notes_{current_cn}",
                            height=80
                        )
                        if st.form_submit_button("Save Clawback Status", type="primary", width='stretch'):
                            _new_s = None if _cb_new_status == "— No clawback —" else _cb_new_status
                            _new_d = str(_cb_new_date) if _cb_new_date else ''
                            _cb_cn = current_cn
                            _cb_usr = _username
                            def _cb_op():
                                db_manager.mark_clawback(
                                    case_folder, _cb_cn, _new_s, _new_d,
                                    _cb_notes.strip(), _cb_usr
                                )
                            if _safe_write(
                                _cb_op,
                                f"Clawback status updated for {current_cn}.",
                                f"❌ Failed to save clawback status for {current_cn}.",
                            ):
                                st.rerun()

        # ── Re-Image Document (admin/manager only, emails only) ──────────
        if (auth_manager.has_permission('reimage')
            and IMAGER_AVAILABLE
            and (row['file_extension'] or '').lower() in ('.msg', '.eml')
            and not _case_closed):

            with st.expander("🔄 Re-Image This Document", expanded=False):
                st.caption(
                    "Re-generates the PDF image from the original source email file. "
                    "This is a **full reset** — all tags, review status, redaction marks, "
                    "privilege disposition, and confidentiality designation will be cleared. "
                    "The document will need to be re-reviewed."
                )

                _ri_cn = current_cn
                _ri_reviewed_exists = os.path.exists(
                    os.path.join(case_folder, "Reviewed", f"{_ri_cn}.pdf")
                )
                _ri_raw_tags = (row['tags'] or '').replace(',', ';')
                _ri_all_tags = [t.strip().rstrip(';').strip() for t in _ri_raw_tags.split(';') if t.strip()]
                _ri_system_tags_set = {'Inclusive', 'Thread-Suppressed', 'NearDupe-Suppressed', 'Inclusive-Attachments'}
                _ri_system_tags = [t for t in _ri_all_tags if t in _ri_system_tags_set]
                _ri_user_tags = [t for t in _ri_all_tags if t not in _ri_system_tags_set]
                _ri_has_reviewed_by = bool(row['reviewed_by'])

                _ri_warnings = []
                if _ri_has_reviewed_by:
                    _ri_warnings.append(f"Reviewed by **{row['reviewed_by']}** — review status will be cleared")
                if _ri_user_tags:
                    _ri_warnings.append(f"Tags: `{', '.join(_ri_user_tags)}` — will be cleared")
                if _ri_system_tags:
                    _ri_warnings.append(f"System tags (`{', '.join(_ri_system_tags)}`) will be **preserved**")
                if _ri_reviewed_exists:
                    _ri_warnings.append("Reviewed PDF with redaction marks exists — will be deleted")

                if _ri_warnings:
                    st.warning("**The following will be permanently cleared:**\n\n" + "\n\n".join(f"- {w}" for w in _ri_warnings))

                _ri_confirm = st.checkbox(
                    "I understand this will reset all review work on this document",
                    key=f"reimage_confirm_{_ri_cn}",
                    value=False,
                )

                if st.button(
                    "🔄 Re-Image Document",
                    key=f"reimage_btn_{_ri_cn}",
                    disabled=not _ri_confirm,
                    type="primary",
                    width='stretch',
                ):
                    with st.spinner("Re-imaging from source file..."):
                        _ri_ok, _ri_msg = _reimage_document(case_folder, _ri_cn, _username)
                    if _ri_ok:
                        st.success(_ri_msg)
                        for _sk in list(st.session_state.keys()):
                            if _ri_cn in str(_sk):
                                try:
                                    del st.session_state[_sk]
                                except Exception:
                                    pass
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error(_ri_msg)

        # ── Reviewer Notes (all roles) ────────────────────────────────
        with st.expander("📝 Reviewer Notes", expanded=False):
                _note_username = st.session_state.get('username', '')
                _my_note = db_manager.get_document_note(case_folder, current_cn, _note_username)
                _note_text = st.text_area(
                    "Your note",
                    value=_my_note['note_text'] if _my_note else '',
                    key=f"note_{current_cn}_{_note_username}",
                    height=100,
                    disabled=_case_closed,
                    label_visibility="collapsed",
                    placeholder="Add a note about this document (work product — not exported with production)...",
                )
                if not _case_closed:
                    _note_c1, _note_c2 = st.columns([3, 1])
                    if _note_c1.button("💾 Save Note", key=f"note_save_{current_cn}", width='stretch'):
                        if _note_text.strip():
                            db_manager.upsert_document_note(case_folder, current_cn, _note_username, _note_text.strip())
                            db_manager.log_audit(case_folder, "REVIEWER_NOTE_SAVED",
                                username=_note_username, control_number=current_cn, module="Review")
                            st.success("Note saved.")
                        else:
                            st.warning("Note is empty — use Clear to remove.")
                    if _my_note and _note_c2.button("🗑️ Clear", key=f"note_clear_{current_cn}", width='stretch'):
                        db_manager.delete_document_note(case_folder, current_cn, _note_username)
                        db_manager.log_audit(case_folder, "REVIEWER_NOTE_DELETED",
                            username=_note_username, control_number=current_cn, module="Review")
                        # Clear the cached text area value so it doesn't show stale text
                        st.session_state.pop(f"note_{current_cn}_{_note_username}", None)
                        st.rerun()

                # Other reviewers' notes (visible to managers/admins)
                if auth_manager.has_permission('production'):
                    _all_notes = db_manager.get_document_notes(case_folder, current_cn)
                    _other_notes = [n for n in _all_notes if n['username'] != _note_username]
                    if _other_notes:
                        st.markdown("**Other Reviewer Notes:**")
                        for _on in _other_notes:
                            st.caption(f"**{_on['username']}** ({_on['updated_at'][:10]}): {_on['note_text']}")