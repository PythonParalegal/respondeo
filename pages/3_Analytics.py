# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        3_Analytics.py
# version:       1.8.2
# project:       Respondeo eDiscovery Platform
# project_ver:   2.16.0
# last_modified: 2026-06-01 12:00
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import streamlit as st
import os
import re
import json
import pandas as pd
import networkx as nx
from datetime import datetime
from datasketch import MinHash, MinHashLSH
from opensearchpy import OpenSearch
from opensearchpy.helpers import scan
import os_manager
import time

import db_manager
import auth_manager
import plotly.graph_objects as go
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
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
        ),
    )
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.06)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.06)')
    return fig

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
st.set_page_config(page_title="Respondeo | Analytics", layout="wide", page_icon=str(_ASSETS / "favicon.png"))

import ui_utils
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()

if not auth_manager.check_login(): st.stop()
# permission: analytics
auth_manager.require_permission('analytics')
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


# --- OPENSEARCH CLIENT ---
es, es_status = os_manager.get_os_client()
if es:
    st.sidebar.success(es_status)
else:
    st.sidebar.error(es_status)

# --- ANALYTICS ENGINE FUNCTIONS ---

_EMAIL_ADDR_RE = re.compile(r'[\w.+\-]+@[\w.\-]+\.\w+')

def _extract_addresses(field_value):
    """Extract individual email addresses from a From/To/CC field."""
    if not field_value:
        return []
    return list(set(addr.lower() for addr in _EMAIL_ADDR_RE.findall(str(field_value))))


def _normalize_subject(subj):
    """Strip RE:/FW:/FWD:/AW:/WG: prefixes and return lowercase subject."""
    if not subj:
        return ''
    s = str(subj).strip()
    while True:
        m = re.match(r'^(RE|FW|FWD|AW|WG)\s*:\s*', s, re.IGNORECASE)
        if m:
            s = s[m.end():]
        else:
            break
    return s.strip().lower()


def bulk_tag_documents(control_numbers, tag_name):
    """Applies a specific tag to a list of documents.
    
    CRIT-4: The entire operation runs inside a single explicit transaction.
    If any chunk fails, the whole batch is rolled back — preventing a half-tagged corpus.
    """
    conn = db_manager.get_connection(case_folder)
    now_str = datetime.now().isoformat()
    tag_with_sep = tag_name + ';'
    tag_pattern = f'%{tag_name}%'
    
    def batched(iterable, n):
        for i in range(0, len(iterable), n):
            yield iterable[i:i + n]
    
    try:
        conn.execute("BEGIN")  # db_manager: exempt (batch transaction)
        for chunk in batched(control_numbers, 900):
            placeholders = ','.join(['?'] * len(chunk))
            sql = f"""
                UPDATE documents 
                SET tags = CASE 
                    WHEN tags IS NULL OR tags = '' THEN ?
                    WHEN tags NOT LIKE ? THEN tags || ?
                    ELSE tags
                END,
                analytics_run_date = ?
                WHERE control_number IN ({placeholders})
            """
            params = [tag_with_sep, tag_pattern, tag_with_sep, now_str] + list(chunk)
            conn.execute(sql, params)  # db_manager: exempt (batch transaction)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def run_threading(use_subject_fallback=True):
    """Identifies the last-in-time email of a conversation thread.

    A1: Excludes only emails whose parent is another email (nested MSG attachments).
        PST-extracted emails (parent = PST container) are correctly included.
    A2: Normalizes Message-ID angle brackets so graph edges connect reliably.
    A4: Subject-line fallback groups unthreaded emails by normalized subject.
    """
    def _normalize_msg_id(raw):
        if not raw or str(raw).strip() in ('', 'None'):
            return None
        s = str(raw).strip()
        if s.startswith('<') and s.endswith('>'):
            s = s[1:-1]
        return s.strip() if s else None

    conn = db_manager.get_connection(case_folder)
    # A1: fixed parent_id filter — only exclude emails whose parent is also an email
    query = """
        SELECT d.control_number, d.message_id, d.in_reply_to, d.references_list,
               d.email_subject, d.date_sent
        FROM documents d
        WHERE d.record_type = 'Email'
          AND d.processing_status IN ('Processed', 'Master')
          AND (d.source_party = 'Internal' OR d.source_party IS NULL)
          AND (
              d.parent_id IS NULL
              OR d.parent_id = ''
              OR NOT EXISTS (
                  SELECT 1 FROM documents p
                  WHERE p.control_number = d.parent_id
                    AND p.record_type = 'Email'
              )
          )
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        st.warning("No emails with message IDs found in the database. Threading yielded 0 results.")
        st.session_state['inclusive_docs'] = []
        st.session_state['suppressed_docs'] = []
        st.session_state['threading_done'] = True
        return

    # A2 + references chain: build graph with normalized IDs
    G = nx.DiGraph()
    for _, row in df.iterrows():
        msg_id = _normalize_msg_id(row['message_id'])
        if not msg_id:
            continue
        cnum = row['control_number']
        G.add_node(msg_id, control_number=cnum)

        in_reply = _normalize_msg_id(row['in_reply_to'])
        if in_reply:
            G.add_edge(in_reply, msg_id)

        refs_raw = row.get('references_list') or ''
        if refs_raw:
            for ref in str(refs_raw).split():
                ref_clean = _normalize_msg_id(ref)
                if ref_clean and ref_clean != msg_id:
                    G.add_edge(ref_clean, msg_id)

    inclusive_docs = []
    suppressed_docs = []

    for node in G.nodes():
        node_attr = G.nodes[node]
        if 'control_number' not in node_attr:
            continue
        cnum = node_attr['control_number']
        if G.out_degree(node) == 0:
            inclusive_docs.append(cnum)
        else:
            suppressed_docs.append(cnum)

    # A4: Subject-line fallback for emails not reached by Message-ID threading
    if use_subject_fallback:
        threaded_cnums = set(inclusive_docs) | set(suppressed_docs)
        unthreaded = df[~df['control_number'].isin(threaded_cnums)].copy()

        if not unthreaded.empty:
            unthreaded['_norm_subj'] = unthreaded['email_subject'].apply(_normalize_subject)
            unthreaded['_date_parsed'] = pd.to_datetime(unthreaded['date_sent'], errors='coerce')

            for norm_subj, grp in unthreaded.groupby('_norm_subj'):
                grp_sorted = grp.sort_values('_date_parsed', ascending=True)
                cnums_list = list(grp_sorted['control_number'])

                if not norm_subj:
                    # No usable subject — mark all inclusive
                    inclusive_docs.extend(cnums_list)
                    continue

                # If span > 90 days, likely unrelated conversations — all inclusive
                dates = grp_sorted['_date_parsed'].dropna()
                if len(dates) >= 2 and (dates.max() - dates.min()).days > 90:
                    inclusive_docs.extend(cnums_list)
                    continue

                # Suppress all but the last (most recent)
                if len(cnums_list) == 1:
                    inclusive_docs.append(cnums_list[0])
                else:
                    suppressed_docs.extend(cnums_list[:-1])
                    inclusive_docs.append(cnums_list[-1])

    # ── Phase A5: Un-suppress emails that carry attachments ──────────────
    # Emails with child documents (attachments) must not be suppressed,
    # because suppression propagates to children and orphans the attachments.
    # Move any attachment-bearing email from suppressed → inclusive.
    _att_promoted = []
    if suppressed_docs:
        _conn_att = db_manager.get_connection(case_folder)
        try:
            for _i in range(0, len(suppressed_docs), 900):
                _chunk = suppressed_docs[_i:_i+900]
                _ph = ','.join(['?'] * len(_chunk))
                _parents_with_children = {r[0] for r in _conn_att.execute(
                    f"SELECT DISTINCT parent_id FROM documents WHERE parent_id IN ({_ph})",
                    _chunk
                ).fetchall()}  # db_manager: exempt (read-only analytics query)
                _att_promoted.extend([cn for cn in _chunk if cn in _parents_with_children])
        finally:
            _conn_att.close()

        if _att_promoted:
            _promoted_set = set(_att_promoted)
            suppressed_docs = [cn for cn in suppressed_docs if cn not in _promoted_set]
            inclusive_docs.extend(_att_promoted)

    st.session_state['att_promoted_docs'] = _att_promoted
    st.session_state['att_promoted_count'] = len(_att_promoted)
    st.session_state['inclusive_docs'] = inclusive_docs
    st.session_state['suppressed_docs'] = suppressed_docs
    st.session_state['threading_done'] = True
    st.rerun()

def _compute_minhash_signature(content: str, k: int = 5, num_perm: int = 128) -> MinHash:
    """
    Compute a MinHash signature for document content using k-gram shingling.

    Each shingle is a sliding window of k consecutive whitespace-split tokens
    joined with a single space. This preserves local word-order and content
    structure, which word-level (k=1) shingling discards. The k=5 default is
    calibrated to keep template-similar but content-distinct documents (e.g.,
    invoices from the same vendor with different invoice numbers / amounts)
    out of the same MinHash cluster, while still clustering true near-dupes
    (e.g., FW/RE email copies with identical body text).

    Args:
        content: Document text. Coerced via str() + lower() before tokenizing.
        k: Shingle window size in tokens. Default 5; pinned by regression test.
        num_perm: MinHash permutation count. Default 128 (current project value).

    Returns:
        A MinHash signature with shingles added. Caller is responsible for
        LSH indexing and threshold-based clustering. Returns an empty MinHash
        (no shingles added) if the tokenized content has fewer than k tokens;
        the caller's len(tokens) < 5 guard skips those before LSH insertion.

    Raises:
        ValueError if k < 1.
    """
    if k < 1:
        raise ValueError(f"_compute_minhash_signature: k must be >= 1, got {k!r}.")
    tokens = str(content).lower().split()
    m = MinHash(num_perm=num_perm)
    if len(tokens) < k:
        return m  # Empty signature — caller filters via the existing len(tokens) < 5 guard.
    for i in range(len(tokens) - k + 1):
        shingle = " ".join(tokens[i:i + k])
        m.update(shingle.encode("utf8"))
    return m


def run_near_dupe(sim_threshold):
    """Indexes ES text to find documents that are highly similar but not exact duplicates."""
    if not es:
        st.error("OpenSearch connection required for near-duplicate analysis.")
        return

    index_name = os_manager.get_index_name(case_folder)
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    status_text.text("Fetching documents from OpenSearch...")
    lsh = MinHashLSH(threshold=sim_threshold, num_perm=128)
    minhashes = {}
    
    query = {
        "query": {
            "bool": {
                "should": [{"term": {"source_party.keyword": "Internal"}}, {"bool": {"must_not": {"exists": {"field": "source_party"}}}}]
            }
        },
        "_source": ["control_number", "content"]
    }
    
    try:
        # Verify index exists before scanning — scan() is a generator so errors
        # surface during iteration, not at creation time.
        if not es.indices.exists(index=index_name):
            st.warning("OpenSearch index not found. Process documents in Module 2 first.")
            return
        results = scan(es, query=query, index=index_name)
    except Exception as e:
        st.error(f"Failed to query OpenSearch: {e}")
        return

    count = 0
    for hit in results:
        cnum = hit['_source'].get('control_number')
        content = hit['_source'].get('content', '')
        
        if not cnum or not pd.notna(content) or str(content).strip() == '':
            continue
            
        if cnum in minhashes:
            continue
            
        tokens = str(content).lower().split()
        if len(tokens) < 5:  # Need at least k=5 tokens for one shingle (see _compute_minhash_signature)
            continue
            
        m = _compute_minhash_signature(content)  # Flag #22: k-gram shingling preserves content structure
            
        lsh.insert(cnum, m)
        minhashes[cnum] = m
        
        count += 1
        if count % 100 == 0:
            status_text.text(f"Processed {count} signatures...")

    status_text.text(f"Grouping {count} documents into clusters...")
    visited = set()
    clusters = []
    
    for cnum, m in minhashes.items():
        if cnum in visited:
            continue
            
        result = lsh.query(m)
        if len(result) > 1:
            clusters.append(result)
            for r in result:
                visited.add(r)
        else:
            visited.add(cnum)
            
    st.session_state['nd_clusters'] = clusters
    st.session_state['nd_minhashes'] = minhashes  # principal↔member Jaccard at persist time (S-1b)
    status_text.empty()
    progress_bar.empty()
    st.rerun()


def _build_cluster_payload(sorted_members, minhashes):
    """Build one near-dupe cluster's persist payload from its members, where
    `sorted_members` is the cluster's documents already sorted so [0] is the
    principal (highest metadata score / size / lowest control number).

    Pure (no Streamlit / DB) so it can be unit-tested. The SINGLE iloc[0]
    principal drives `is_principal` AND `family_preserved`, so the two cannot
    disagree under Flag #30 overlapping clusters: a non-principal member with a
    real parent_id is always family_preserved=1 here (S-1b v3 — this is the
    dual-selection leak fix; the prior `next()` re-derivation could leave a
    family member unguarded). `minhashes` is {control_number: MinHash};
    similarity is the principal↔member Jaccard, or None when a signature is absent.
    """
    if not sorted_members:
        return None
    principal = sorted_members[0]['control_number']
    members, sims = [], []
    for m in sorted_members:
        cn = m['control_number']
        is_principal = (cn == principal)
        parent = m.get('parent_id')
        # parent may be None, NaN (pandas null; NaN != NaN), '', or whitespace —
        # all mean "no parent"; only a real non-empty string is a family link.
        has_parent = parent is not None and parent == parent and str(parent).strip() != ''
        family_preserved = (not is_principal) and has_parent
        sim = None
        if principal in minhashes and cn in minhashes:
            sim = float(minhashes[principal].jaccard(minhashes[cn]))
        members.append({
            "cn": cn,
            "similarity": sim,
            "is_principal": 1 if is_principal else 0,
            "family_preserved": 1 if family_preserved else 0,
        })
        if not is_principal and sim is not None:
            sims.append(sim)
    return {
        "principal_cn": principal,
        "members": members,
        "sim_min": min(sims) if sims else None,
        "sim_max": max(sims) if sims else None,
    }


# --- TABBED INTERFACE ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📧 Email Threading",
    "📑 Near-Duplicate Detection",
    "🔍 Dedup Report",
    "🌐 Communication Analysis",
    "📅 Timeline",
    "🏢 Domain Analysis",
    "👥 Custodian Overlap",
    "💡 Concept Explorer",
])

# =
# TAB 1: EMAIL THREADING
# =
with tab1:
    st.header("Email Threading")
    st.caption("Goal: Identify the 'Inclusive' emails (the last ones in the chain) and suppress the rest.")

    col1, col2 = st.columns([1, 3])
    
    with col1:
        # --- CHECK STATUS ---
        conn = db_manager.get_connection(case_folder)
        last_threading = conn.execute("SELECT analytics_run_date FROM documents WHERE (tags LIKE '%Thread-Suppressed%' OR tags LIKE '%Inclusive%') AND (source_party = 'Internal' OR source_party IS NULL) LIMIT 1").fetchone()  # db_manager: exempt (dashboard read)
        conn.close()

        has_run = last_threading and last_threading['analytics_run_date']

        if has_run:
            st.success(f"✅ Threading complete (Last run: {last_threading['analytics_run_date'][:10]})")
            with st.expander("🛠️ Re-run Options"):
                st.warning("Re-running will recalculate threads and re-apply tags. Existing 'Thread-Suppressed' and 'Inclusive' tags will be cleared first.")
                if _case_closed:
                    st.warning("Write operations are disabled on closed matters.")
                elif not auth_manager.has_permission('tag'):
                    # permission: tag
                    st.warning("Tag modification requires the 'tag' permission.")
                elif st.button("⚠️ Clear & Re-run Threading", key="clear_rerun_threading_btn"):
                    # Re-verify case is still open before writing (race condition guard — M-5)
                    if db_manager.get_case_status(case_folder) == 'Closed':
                        st.error("Case was closed by another user. Please refresh the page.")
                        st.stop()
                    conn = db_manager.get_connection(case_folder)
                    # Clear tags
                    conn.execute("UPDATE documents SET tags = REPLACE(tags, 'Inclusive-Attachments', '') WHERE source_party = 'Internal' OR source_party IS NULL")  # db_manager: exempt (analytics bulk-update) — must precede Inclusive to avoid substring corruption
                    conn.execute("UPDATE documents SET tags = REPLACE(tags, 'Thread-Suppressed', '') WHERE source_party = 'Internal' OR source_party IS NULL")  # db_manager: exempt (analytics bulk-update)
                    conn.execute("UPDATE documents SET tags = REPLACE(tags, 'Inclusive', '') WHERE source_party = 'Internal' OR source_party IS NULL")  # db_manager: exempt (analytics bulk-update)
                    conn.execute("UPDATE documents SET tags = REPLACE(tags, ';;', ';') WHERE tags LIKE '%;;%' AND (source_party = 'Internal' OR source_party IS NULL)")  # db_manager: exempt (analytics bulk-update) # Cleanup separators
                    conn.commit()
                    conn.close()
                    db_manager.log_audit(case_folder, "ANALYTICS_TAGS_CLEARED",
                                         username=st.session_state.get('username', 'system'),
                                         module="Analytics",
                                         details="Cleared Thread-Suppressed and Inclusive tags before re-run")
                    st.success("Threading tags cleared. Re-running..."); time.sleep(1); st.rerun()
        else:
            st.info("💡 Threading has not been run for this case yet.")

        # Hide main RUN button if already run, unless in expander above? 
        # Actually, let's just keep the button but make it clear.
        if not has_run:
            use_subj_fallback = st.checkbox(
                "Include subject-line grouping (for emails without Message-ID chains)",
                value=True,
                key="threading_subj_fallback",
                help="Groups emails by normalized subject when Message-ID threading can't "
                     "link them. Standard in Relativity and other platforms.",
            )
            if _case_closed:
                st.warning("Write operations are disabled on closed matters.")
            elif not auth_manager.has_permission('tag'):
                # permission: tag
                st.warning("Tag modification requires the 'tag' permission.")
            elif st.button("RUN: Analyze Threads", key="run_threading_btn"):
                run_threading(use_subject_fallback=use_subj_fallback)
    
    with col2:
        if st.session_state.get('threading_done'):
            inc = len(st.session_state.get('inclusive_docs', []))
            sup = len(st.session_state.get('suppressed_docs', []))
            total = inc + sup
            
            if total > 0:
                st.metric("Reduction Opportunity", f"{sup} Emails ({round(sup/total*100, 1)}%)")
                st.write(f"**Inclusive (Read These):** {inc}")
                st.write(f"**Redundant (Skip These):** {sup}")
                _att_promo = st.session_state.get('att_promoted_count', 0)
                if _att_promo > 0:
                    st.write(f"**↳ Retained for Attachments:** {_att_promo}")
                    st.caption("These emails would have been suppressed but were retained because they carry attachments.")
            else:
                st.metric("Reduction Opportunity", "0 Emails")
                st.info("No threadable emails discovered.")
            
            if _case_closed:
                st.warning("Write operations are disabled on closed matters.")
            # permission: bulk_tag_analytics
            elif not auth_manager.has_permission('tag'):
                st.warning("You do not have permission to modify document tags.")
            elif st.button("🚀 EXECUTE: Auto-Tag Database", key="execute_auto_tag_db_btn"):
                # Re-verify case is still open before writing (race condition guard — M-5)
                if db_manager.get_case_status(case_folder) == 'Closed':
                    st.error("Case was closed by another user. Please refresh the page.")
                    st.stop()
                # Apply Tags or at least mark the run date so the system knows we finished
                now_str = datetime.now().isoformat()
                _an_username = st.session_state.get('username', 'unknown')
                conn = db_manager.get_connection(case_folder)

                # Capture old tags for audit BEFORE bulk update
                _all_affected_th = list(set(
                    st.session_state.get('suppressed_docs', []) + st.session_state.get('inclusive_docs', [])
                ))
                _old_tags_th = {}
                for i in range(0, len(_all_affected_th), 900):
                    chunk = _all_affected_th[i:i+900]
                    ph = ','.join(['?'] * len(chunk))
                    for r in conn.execute(f"SELECT control_number, tags FROM documents WHERE control_number IN ({ph})", chunk).fetchall():  # db_manager: exempt (dynamic query)
                        _old_tags_th[r['control_number']] = r['tags'] or ''

                # If there's literally no emails, let's just mark *all* emails as having been processed,
                # or just set a dummy flag so `has_run` detects it next time.
                # A better approach: update analytics_run_date for all emails.
                if sup > 0:
                    try:
                        bulk_tag_documents(st.session_state['suppressed_docs'], "Thread-Suppressed")
                    except Exception as _btd_err:
                        st.error(f"❌ Threading tag operation failed and was rolled back: {_btd_err}")
                    # Propagate Thread-Suppressed to attachment children of suppressed emails
                    _sup_list = st.session_state['suppressed_docs']
                    if _sup_list:
                        try:
                            _prop_conn = db_manager.get_connection(case_folder)
                            _child_cnums: list = []
                            for _i in range(0, len(_sup_list), 900):
                                _chunk = _sup_list[_i:_i+900]
                                _ph = ','.join('?' * len(_chunk))
                                _child_cnums += [r[0] for r in _prop_conn.execute(  # db_manager: exempt (dynamic query)
                                    f"SELECT control_number FROM documents WHERE parent_id IN ({_ph})",
                                    _chunk
                                ).fetchall()]
                            _prop_conn.close()
                            if _child_cnums:
                                bulk_tag_documents(_child_cnums, "Thread-Suppressed")
                        except Exception as _prop_err:
                            st.warning(f"⚠️ Threading child propagation failed: {_prop_err}")
                if inc > 0:
                    try:
                        bulk_tag_documents(st.session_state['inclusive_docs'], "Inclusive")
                    except Exception as _btd_err:
                        st.error(f"❌ Threading tag operation failed and was rolled back: {_btd_err}")

                # Tag attachment-promoted emails for reviewer visibility
                _att_promo_list = st.session_state.get('att_promoted_docs', [])
                if _att_promo_list:
                    try:
                        bulk_tag_documents(_att_promo_list, "Inclusive-Attachments")
                    except Exception as _att_tag_err:
                        st.warning(f"⚠️ Attachment-promotion tagging failed: {_att_tag_err}")

                # Ensure the run date is saved even if 0 results
                if total == 0:
                    conn.execute("UPDATE documents SET analytics_run_date = ? WHERE record_type = 'Email' AND (source_party = 'Internal' OR source_party IS NULL)", (now_str,))  # db_manager: exempt (analytics bulk-update)
                    conn.commit()
                conn.close()

                db_manager.log_audit(case_folder, "ANALYTICS_RUN", username=_an_username,
                    module="Analytics", details=json.dumps({
                        "type": "email_threading", "inclusive_count": inc, "suppressed_count": sup,
                        "attachment_promoted_count": st.session_state.get('att_promoted_count', 0)
                    }))

                # Batch log per-document tag changes
                _th_audit = []
                for cn, tag, docs in [("Thread-Suppressed", "Thread-Suppressed;", st.session_state.get('suppressed_docs', [])),
                                      ("Inclusive", "Inclusive;", st.session_state.get('inclusive_docs', []))]:
                    for doc_cn in docs:
                        old_t = _old_tags_th.get(doc_cn, '')
                        if cn not in old_t:
                            new_t = (old_t + ';' + cn + ';') if old_t else (cn + ';')
                            _th_audit.append({"action": "TAGS_CHANGED", "username": _an_username,
                                "control_number": doc_cn, "module": "Analytics",
                                "details": None, "old_value": old_t, "new_value": new_t})
                if _th_audit:
                    db_manager.log_audit_batch(case_folder, _th_audit)

                st.success(f"✅ Database updated! {sup} documents tagged.")

# =
# TAB 2: NEAR DUPE (MINHASH)
# =
with tab2:
    st.header("Near-Duplicate Detection")
    st.caption("Goal: Group documents that are 90%+ similar and mark non-principal versions as suppressed.")
    
    threshold = st.slider("Similarity Threshold", 0.5, 1.0, 0.90, key="nd_similarity_threshold")
    
    # --- CHECK STATUS (S-1b: key off the persisted cluster table, not the
    # suppressed tag — suppression now lags reviewer confirmation, so a fresh
    # run with zero confirmations yet would otherwise read as "not run") ---
    _nd_status_clusters = db_manager.get_near_dupe_clusters(case_folder)
    has_nd_run = bool(_nd_status_clusters)
    # F3: source the "Last run" date from near_dupe_clusters.run_date, not
    # documents.analytics_run_date (detection no longer keys off the tag).
    _nd_last_run = _nd_status_clusters[0]['run_date'] if has_nd_run else None

    if has_nd_run:
        _nd_run_disp = _nd_last_run[:10] if _nd_last_run else "unknown"
        st.success(f"✅ Near-Duplicate analysis complete (Last run: {_nd_run_disp})")
        with st.expander("🛠️ Re-run Options"):
            st.warning("Re-running will re-index and re-cluster documents. Existing 'NearDupe-Suppressed' / 'NearDupe-Principal' tags **and all cluster review decisions** will be discarded first.")
            if _case_closed:
                st.warning("Write operations are disabled on closed matters.")
            elif not auth_manager.has_permission('tag'):
                # permission: tag
                st.warning("Tag modification requires the 'tag' permission.")
            else:
                # § 6 / §11.10 re-run type-to-confirm guard. If reviewer decisions
                # exist, a single click must NOT fire — the reviewer types an exact
                # phrase first (Re-open handles single-cluster fixes; Clear & Re-run
                # is the destructive re-cluster path). Zero decisions → original flow.
                _rerun_progress = db_manager.get_near_dupe_review_progress(case_folder)
                _n_dec = _rerun_progress["n_decisions"]
                if _n_dec == 0:
                    if st.button("⚠️ Clear & Re-run Near-Duplicate", key="clear_rerun_near_dupe_btn"):
                        # Re-verify case is still open before writing (race guard — M-5)
                        if db_manager.get_case_status(case_folder) == 'Closed':
                            st.error("Case was closed by another user. Please refresh the page.")
                            st.stop()
                        # clear_near_dupe_clusters wipes the cluster tables AND strips
                        # the NearDupe-Suppressed/Principal tags (one owner now).
                        _n_clusters, _n_decisions = db_manager.clear_near_dupe_clusters(case_folder)
                        db_manager.log_audit(case_folder, "ANALYTICS_TAGS_CLEARED",
                                             username=st.session_state.get('username', 'system'),
                                             module="Analytics",
                                             details=f"Cleared {_n_clusters} near-dupe clusters and NearDupe-Suppressed/Principal tags before re-run (no reviewer decisions to discard)")
                        st.success("Near-Dupe clusters and tags cleared. Re-running..."); time.sleep(1); st.rerun()
                else:
                    st.error(
                        f"⚠️ This will discard **{_n_dec} reviewer decision(s)** across "
                        f"**{_rerun_progress['n_clusters']} cluster(s)**, including any granular "
                        f"Re-open work. Type the exact phrase below to confirm — or cancel.")
                    _required = f"CLEAR {_n_dec} DECISIONS"
                    _typed = st.text_input(f"Type `{_required}` to enable Clear & Re-run:",
                                           key="nd_clear_confirm_text", placeholder=_required)
                    _g_go, _g_cancel = st.columns(2)
                    if _g_cancel.button("Cancel", key="nd_clear_cancel"):
                        st.session_state.pop("nd_clear_confirm_text", None)
                        st.rerun()
                    if _g_go.button("Clear & Re-run Near-Duplicate", type="primary",
                                    disabled=(_typed != _required), key="nd_clear_rerun_armed"):
                        # Re-verify case is still open before writing (race guard — M-5)
                        if db_manager.get_case_status(case_folder) == 'Closed':
                            st.error("Case was closed by another user. Please refresh the page.")
                            st.stop()
                        _n_clusters, _n_decisions = db_manager.clear_near_dupe_clusters(case_folder)
                        db_manager.log_audit(case_folder, "NEARDUPE_FORCE_RERUN",
                                             username=st.session_state.get('username', 'system'),
                                             module="Analytics",
                                             details=json.dumps({"discarded_decisions": _n_decisions,
                                                                  "discarded_clusters": _n_clusters}))
                        st.session_state.pop("nd_clear_confirm_text", None)
                        st.success(f"Cleared {_n_clusters} cluster(s) and {_n_decisions} reviewer decision(s). Re-running..."); time.sleep(1); st.rerun()
    else:
        st.info("💡 Near-Duplicate analysis has not been run for this case yet.")

    if not has_nd_run:
        if _case_closed:
            st.warning("Write operations are disabled on closed matters.")
        elif not auth_manager.has_permission('tag'):
            # permission: tag
            st.warning("Tag modification requires the 'tag' permission.")
        elif st.button("RUN: Analyze Text Similarity", key="run_text_similarity_btn"):
            run_near_dupe(threshold)

    if st.session_state.get('nd_clusters'):
        clusters = st.session_state['nd_clusters']
        
        # Calculate stats with DB lookups to determine family integrity
        total_dupes = sum([len(c) for c in clusters])
        
        st.write("### Analysis Results")
        st.write(f"Found **{len(clusters)}** groups of highly similar documents (totaling **{total_dupes}** files).")
        
        # We need to pre-calculate the actual suppression count vs family preserved count
        # to show accurate metrics to the user before they click execute.
        # S-1b v3: build the persist payload HERE, from the same iloc[0] principal
        # that drives the tag + the family split, so is_principal and
        # family_preserved cannot disagree under Flag #30 overlapping clusters.
        suppressed_ids = []
        principal_ids = []
        preserved_family_ids = []
        _mh = st.session_state.get('nd_minhashes', {})
        _persist_payload = []

        conn = db_manager.get_connection(case_folder)
        for cluster in clusters:
            placeholders = ','.join(['?'] * len(cluster))
            sql = f"""
                SELECT control_number, file_size_kb, parent_id,
                       ( (email_from IS NOT NULL) + (date_sent IS NOT NULL) + (author IS NOT NULL) ) as meta_score
                FROM documents
                WHERE control_number IN ({placeholders})
            """
            # Read data and sort: Metadata Score -> File Size -> Control Number (Lowest first)
            meta_df = pd.read_sql_query(sql, conn, params=cluster)
            meta_df = meta_df.sort_values(by=['meta_score', 'file_size_kb', 'control_number'], ascending=[False, False, True])

            if not meta_df.empty:
                _sorted_members = meta_df[['control_number', 'parent_id']].to_dict('records')
                _entry = _build_cluster_payload(_sorted_members, _mh)
                _persist_payload.append(_entry)
                # Derive the display/tag id lists from the SAME payload (single source of truth).
                principal_ids.append(_entry['principal_cn'])
                for _mem in _entry['members']:
                    if _mem['is_principal']:
                        continue
                    if _mem['family_preserved']:
                        preserved_family_ids.append(_mem['cn'])  # family child — guarded from suppression
                    else:
                        suppressed_ids.append(_mem['cn'])
        conn.close()
        
        # S-1b: suppression is provisional. col1/col2 reflect THIS run's
        # in-memory projection; col3 + caption reflect persisted reviewer
        # progress from the cluster tables via a single aggregate query
        # (get_near_dupe_review_progress — subsumes the C8a F2-dispositioned
        # inline per-cluster get_cluster_members loop now that the guard above
        # is a second caller).
        _ndm = db_manager.get_near_dupe_review_progress(case_folder)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Duplicate Texts", total_dupes - len(principal_ids))
        col2.metric("Preserved (Attachments)", len(preserved_family_ids), help="Attachments that share text but cannot be suppressed without breaking family metadata.")
        col3.metric("Confirmed suppressed", _ndm["confirmed"], help="Members a reviewer has confirmed as true duplicates in Review → Near-Dupe Clusters.")
        st.caption(f"⏳ {_ndm['pending']} members staged, awaiting reviewer confirmation in Review → Near-Dupe Clusters.")
        
        if _case_closed:
            st.button("🚀 EXECUTE: Auto-Tag Near Dupes", disabled=True, key="execute_auto_tag_dupes_btn")
        # permission: bulk_tag_analytics
        elif not auth_manager.has_permission('tag'):
            st.warning("You do not have permission to modify document tags.")
        elif st.button("🚀 EXECUTE: Auto-Tag Near Dupes", key="execute_auto_tag_dupes_active_btn"):
            # Re-verify case is still open before writing (race condition guard — M-5)
            if db_manager.get_case_status(case_folder) == 'Closed':
                st.error("Case was closed by another user. Please refresh the page.")
                st.stop()
            _an_username = st.session_state.get('username', 'unknown')
            _all_nd = list(set(suppressed_ids + principal_ids))

            # Capture old tags before bulk update
            _old_tags_nd = {}
            _nd_conn = db_manager.get_connection(case_folder)
            for i in range(0, len(_all_nd), 900):
                chunk = _all_nd[i:i+900]
                ph = ','.join(['?'] * len(chunk))
                for r in _nd_conn.execute(f"SELECT control_number, tags FROM documents WHERE control_number IN ({ph})", chunk).fetchall():  # db_manager: exempt (dynamic query)
                    _old_tags_nd[r['control_number']] = r['tags'] or ''
            _nd_conn.close()

            # S-1b: provisional suppression. Persist the clusters built above in
            # the metrics loop (one iloc[0] principal per cluster) + apply ONLY the
            # informational NearDupe-Principal tag. NearDupe-Suppressed is applied
            # later, per-member, when a reviewer confirms "Same as principal" in the
            # Review → Near-Dupe Clusters tab (db_manager.record_member_decision).
            db_manager.persist_near_dupe_clusters(case_folder, _persist_payload)
            if principal_ids:
                try:
                    bulk_tag_documents(principal_ids, "NearDupe-Principal")
                except Exception as _btd_err:
                    st.error(f"❌ Near-duplicate principal tag failed and was rolled back: {_btd_err}")

            db_manager.log_audit(case_folder, "ANALYTICS_RUN", username=_an_username,
                module="Analytics", details=json.dumps({
                    "type": "near_duplicate", "clusters": len(clusters),
                    "suppressed_count": len(suppressed_ids)
                }))

            _nd_audit = []
            for tag_name, docs in [("NearDupe-Principal", principal_ids)]:  # S-1b: suppressed-tag audit deferred to record_member_decision (per-decision)
                for doc_cn in docs:
                    old_t = _old_tags_nd.get(doc_cn, '')
                    if tag_name not in old_t:
                        new_t = (old_t + ';' + tag_name + ';') if old_t else (tag_name + ';')
                        _nd_audit.append({"action": "TAGS_CHANGED", "username": _an_username,
                            "control_number": doc_cn, "module": "Analytics",
                            "details": None, "old_value": old_t, "new_value": new_t})
            if _nd_audit:
                db_manager.log_audit_batch(case_folder, _nd_audit)

            st.success(f"✅ {len(clusters)} clusters staged for review. Suppression is applied as reviewers confirm duplicates in Review → Near-Dupe Clusters.")

# =
# TAB 3: DEDUP REPORT
# =
with tab3:
    st.header("Deduplication Report")
    st.caption(
        "Audit the deduplication results for this matter. "
        "Use this report to justify billable collection size, demonstrate defensibility, "
        "and provide opposing counsel or court with a transparent account of the review population."
    )
    st.markdown("---")

    _dr = db_manager.get_data_reduction_stats(case_folder)
    _dr_total_ingested    = _dr['total_ingested']
    _dr_exact_dupes       = _dr['exact_dupes']
    _dr_content_dupes     = _dr['content_dupes']
    _dr_processed         = _dr['processed']
    _dr_error_docs        = _dr['error_docs']
    _dr_nd_suppressed     = _dr['nd_suppressed']
    _dr_nd_principals     = _dr['nd_principals']
    _dr_nd_pending        = _dr['nd_pending']
    _dr_thread_suppressed = _dr['thread_suppressed']
    _dr_thread_inclusive   = _dr['thread_inclusive']
    _dr_net_reviewable    = _dr['net_reviewable']

    import pandas as _dr_pd
    _dr_exact_dupe_clusters = _dr_pd.DataFrame(db_manager.get_exact_dupe_clusters(case_folder))
    _dr_nd_cluster_detail = _dr_pd.DataFrame(db_manager.get_near_dupe_cluster_detail(case_folder))
    _dr_all_exact_dupes_df = _dr_pd.DataFrame(db_manager.get_all_exact_dupes_detail(case_folder))
    _dr_content_dupe_clusters = _dr_pd.DataFrame(db_manager.get_content_dupe_clusters(case_folder))

    _dr_reduction_pct  = ((_dr_total_ingested - _dr_net_reviewable) / _dr_total_ingested * 100) if _dr_total_ingested > 0 else 0
    _dr_exact_dupe_pct   = (_dr_exact_dupes / _dr_total_ingested * 100) if _dr_total_ingested > 0 else 0
    _dr_content_dupe_pct = (_dr_content_dupes / _dr_total_ingested * 100) if _dr_total_ingested > 0 else 0
    _dr_nd_pct           = (_dr_nd_suppressed / _dr_total_ingested * 100) if _dr_total_ingested > 0 else 0
    _dr_thread_pct     = (_dr_thread_suppressed / _dr_total_ingested * 100) if _dr_total_ingested > 0 else 0

    _dr_m1, _dr_m2, _dr_m2b, _dr_m3, _dr_m4 = st.columns(5)
    _dr_m1.metric("Total Ingested", f"{_dr_total_ingested:,}")
    _dr_m2.metric("Binary Duplicates (MD5)", f"{_dr_exact_dupes:,}", delta=f"-{_dr_exact_dupe_pct:.1f}%", delta_color="off")
    _dr_m2b.metric("Content Duplicates (SHA-256)", f"{_dr_content_dupes:,}", delta=f"-{_dr_content_dupe_pct:.1f}%", delta_color="off")
    _dr_m3.metric("Near-Dupe Confirmed", f"{_dr_nd_suppressed:,}", delta=f"-{_dr_nd_pct:.1f}%", delta_color="off")
    _dr_m4.metric("Net Review Population", f"{_dr_net_reviewable:,}", delta=f"-{_dr_reduction_pct:.1f}% reduction", delta_color="off")
    # S-1b C8c: near-dupe suppression is reviewer-confirmed (deferred-tagging). The
    # metric counts confirmed-suppressed; surface the un-reviewed remainder.
    if _dr_nd_pending > 0:
        st.caption(f"⏳ {_dr_nd_pending:,} near-duplicate documents pending reviewer confirmation in Review → 🧬 Near-Dupe Clusters")

    # ── Suppression Waterfall Chart ──────────────────────────────────────
    _wf_fig = go.Figure(go.Waterfall(
        orientation='v',
        measure=['absolute', 'relative', 'relative', 'relative', 'relative', 'total'],
        x=['Ingested', 'Binary Dupes', 'Content Dupes', 'Near-Dupes', 'Thread Suppress', 'Net Reviewable'],
        y=[_dr_total_ingested, -_dr_exact_dupes, -_dr_content_dupes, -_dr_nd_suppressed, -_dr_thread_suppressed, _dr_net_reviewable],
        text=[f'{_dr_total_ingested:,}', f'-{_dr_exact_dupes:,}', f'-{_dr_content_dupes:,}',
              f'-{_dr_nd_suppressed:,}', f'-{_dr_thread_suppressed:,}', f'{_dr_net_reviewable:,}'],
        textposition='outside',
        connector=dict(line=dict(color='rgba(0,0,0,0.15)', width=1)),
        decreasing=dict(marker=dict(color=_CHART_COLORS['danger'])),
        increasing=dict(marker=dict(color=_CHART_COLORS['success'])),
        totals=dict(marker=dict(color=_CHART_COLORS['primary'])),
        hovertemplate='%{x}: %{text}<extra></extra>',
    ))
    _wf_fig = _apply_chart_layout(_wf_fig, height=350)
    _wf_fig.update_layout(
        title=dict(text='Population Reduction Waterfall', font_size=14),
        showlegend=False,
    )
    _wf_fig.update_yaxes(title_text='Documents')
    if _dr_nd_pending > 0:
        st.caption(f"Near-dupe bar reflects reviewer-confirmed suppressions only; ⏳ {_dr_nd_pending:,} additional clustered documents await review and are not yet counted in the reduction.")
    st.plotly_chart(_wf_fig, width='stretch')

    # S-1b C8c: pending-confirmation sibling bullet, shown only when un-reviewed
    # clustered documents exist (deferred-suppression honesty).
    _dr_nd_pending_li = (
        f'<li><strong>{_dr_nd_pending:,}</strong> additional documents in '
        f'near-duplicate clusters await reviewer confirmation</li>'
    ) if _dr_nd_pending > 0 else ''
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1a2a1a 0%, #1e3a1e 100%);
                    border-radius: 10px; padding: 16px 24px; border-left: 4px solid #51cf66; margin-bottom: 12px;">
            <div style="color: #51cf66; font-size: 1.05em; font-weight: 700; margin-bottom: 6px;">
                📄 Defensibility Summary
            </div>
            <div style="color: #cce8cc; line-height: 1.7;">
                Of <strong>{_dr_total_ingested:,}</strong> total files ingested:
                <ul style="margin: 6px 0 0 0;">
                    <li><strong>{_dr_exact_dupes:,}</strong> exact duplicates identified by MD5 hash and removed from review
                        ({_dr_exact_dupe_pct:.1f}% of collection)</li>
                    <li><strong>{_dr_content_dupes:,}</strong> content duplicates identified by text hash
                        (identical extracted text, different file metadata) and removed from review
                        ({_dr_content_dupe_pct:.1f}% of collection)</li>
                    <li><strong>{_dr_nd_suppressed:,}</strong> near-duplicate documents confirmed-suppressed by reviewer attestation in favor of
                        <strong>{_dr_nd_principals:,}</strong> representative principals ({_dr_nd_pct:.1f}% of collection)</li>
                    {_dr_nd_pending_li}
                    <li><strong>{_dr_thread_suppressed:,}</strong> thread-suppressed emails removed as non-inclusive
                        ({_dr_thread_pct:.1f}%)</li>
                    <li><strong>{_dr_net_reviewable:,}</strong> net unique documents reviewed
                        — an overall reduction of <strong>{_dr_reduction_pct:.1f}%</strong></li>
                </ul>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")
    st.subheader("📊 Suppression Breakdown")
    _dr_breakdown_rows = [
        {"Category": "Total Files Ingested", "Count": _dr_total_ingested, "% of Total": "100.0%"},
        {"Category": "✅ Unique Processed Documents", "Count": _dr_processed, "% of Total": f"{_dr_processed/_dr_total_ingested*100:.1f}%" if _dr_total_ingested else "—"},
        {"Category": "❌ Exact Duplicates (MD5)", "Count": _dr_exact_dupes, "% of Total": f"{_dr_exact_dupe_pct:.1f}%"},
        {"Category": "❌ Content Duplicates (SHA-256)", "Count": _dr_content_dupes, "% of Total": f"{_dr_content_dupe_pct:.1f}%"},
        {"Category": "🔶 Near-Duplicate Confirmed (Suppressed)", "Count": _dr_nd_suppressed, "% of Total": f"{_dr_nd_pct:.1f}%"},
        {"Category": "🔶 Near-Duplicate Pending Review", "Count": _dr_nd_pending, "% of Total": f"{_dr_nd_pending/_dr_total_ingested*100:.1f}%" if _dr_total_ingested else "—"},
        {"Category": "📧 Thread-Suppressed Emails", "Count": _dr_thread_suppressed, "% of Total": f"{_dr_thread_pct:.1f}%"},
        {"Category": "⚠️ Processing Errors", "Count": _dr_error_docs, "% of Total": f"{_dr_error_docs/_dr_total_ingested*100:.1f}%" if _dr_total_ingested else "—"},
        {"Category": "🎯 Net Review Population", "Count": _dr_net_reviewable, "% of Total": f"{_dr_net_reviewable/_dr_total_ingested*100:.1f}%" if _dr_total_ingested else "—"},
    ]
    st.dataframe(_dr_pd.DataFrame(_dr_breakdown_rows), width='stretch', hide_index=True)

    st.markdown("---")
    st.subheader(f"🔁 Exact Duplicate Clusters ({len(_dr_exact_dupe_clusters)} groups shown, max 200)")
    if _dr_exact_dupe_clusters.empty:
        st.info("No exact duplicate groups found in this collection.")
    else:
        st.caption("Each row is a cluster of documents with identical MD5 hashes. The representative_cn was retained; all others were suppressed.")
        st.dataframe(_dr_exact_dupe_clusters, width='stretch', hide_index=True)

    st.markdown("---")
    st.subheader(f"🔀 Near-Duplicate Clusters ({len(_dr_nd_cluster_detail)} groups shown, max 200)")
    if _dr_nd_cluster_detail.empty:
        st.info("Near-duplicate analytics have not been run yet, or no near-duplicate clusters were found. Run Near-Dupe Detection first.")
    else:
        st.caption("Each row is a near-duplicate cluster. Status reflects reviewer attestation: pending (cluster awaits review), approved (reviewer attested all suppressible members). 'Confirmed' = members the reviewer marked Same; 'Pending' = members not yet decided.")
        st.dataframe(_dr_nd_cluster_detail, width='stretch', hide_index=True)

    st.markdown("---")
    st.subheader(f"🔁 Content-Hash Duplicate Clusters ({len(_dr_content_dupe_clusters)} groups shown, max 200)")
    if _dr_content_dupe_clusters.empty:
        st.info("No content-hash duplicate groups found in this collection.")
    else:
        st.caption("Each row is a cluster of documents with identical extracted text (SHA-256 match) but different binary files. This catches cross-custodian duplicates missed by MD5.")
        st.dataframe(_dr_content_dupe_clusters, width='stretch', hide_index=True)

    st.markdown("---")
    st.subheader("⬇️ Export Report")
    _dr_summary_df = _dr_pd.DataFrame(_dr_breakdown_rows)
    _dr_case_name  = os.path.basename(case_folder)
    _dr_dl1, _dr_dl2 = st.columns(2)
    _dr_summary_csv = _dr_summary_df.to_csv(index=False).encode('utf-8')
    _dr_dl1.download_button(
        "⬇️ Download Summary (CSV)",
        data=_dr_summary_csv,
        file_name=f"{_dr_case_name}_DEDUP_REPORT.csv",
        mime="text/csv",
        width='stretch'
    )
    try:
        import openpyxl as _dr_openpyxl  # noqa: F401
        import io as _dr_io
        _dr_xlsx_buf = _dr_io.BytesIO()
        with _dr_pd.ExcelWriter(_dr_xlsx_buf, engine='openpyxl') as _dr_writer:
            _dr_summary_df.to_excel(_dr_writer, index=False, sheet_name='Summary')
            if not _dr_exact_dupe_clusters.empty:
                _dr_exact_dupe_clusters.to_excel(_dr_writer, index=False, sheet_name='MD5 Duplicates')
            if not _dr_all_exact_dupes_df.empty:
                _dr_all_exact_dupes_df.to_excel(_dr_writer, index=False, sheet_name='All Exact Dupes')
            if not _dr_content_dupe_clusters.empty:
                _dr_content_dupe_clusters.to_excel(_dr_writer, index=False, sheet_name='Content Duplicates')
            if not _dr_nd_cluster_detail.empty:
                _dr_nd_cluster_detail.to_excel(_dr_writer, index=False, sheet_name='Near-Dupe Clusters')
        _dr_dl2.download_button(
            "⬇️ Download Full Report (Excel)",
            data=_dr_xlsx_buf.getvalue(),
            file_name=f"{_dr_case_name}_DEDUP_REPORT.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch'
        )
    except ImportError:
        _dr_dl2.info("Install `openpyxl` for Excel export with multiple sheets.")

    # ── Clawback / Inadvertent Disclosure Summary ──────────────────────────
    st.markdown("---")
    st.subheader("⚠️ Clawback / Inadvertent Disclosure")
    _cb_rows = db_manager.get_clawback_summary(case_folder)
    _cb_demanded = [r for r in _cb_rows if r.get('clawback_status') == 'Clawback_Demanded']
    _cb_resolved = [r for r in _cb_rows if r.get('clawback_status') == 'Clawback_Resolved']
    _cb_c1, _cb_c2 = st.columns(2)
    _cb_c1.metric("Active Clawback Demands", len(_cb_demanded))
    _cb_c2.metric("Resolved", len(_cb_resolved))
    if _cb_rows:
        import pandas as _cb_pd
        _cb_df = _cb_pd.DataFrame(_cb_rows)
        _cb_df = _cb_df.rename(columns={
            'control_number': 'Control #',
            'file_name': 'File Name',
            'custodian': 'Custodian',
            'clawback_status': 'Status',
            'clawback_date': 'Demand Date',
        })
        st.dataframe(_cb_df, width='stretch', hide_index=True)
    else:
        st.info("No clawback demands on record for this matter.")

# =
# TAB 4: COMMUNICATION ANALYSIS
# =
with tab4:
    st.header("Communication Analysis")
    st.caption("Analyze email communication patterns between parties.")

    _ca_key = 'ca_df_cache'
    if st.button("🔄 Refresh Communication Data", key="ca_refresh") or _ca_key not in st.session_state:
        st.session_state[_ca_key] = pd.DataFrame(db_manager.get_custodian_activity_data(case_folder))

    _ca_df = st.session_state.get(_ca_key, pd.DataFrame())

    if _ca_df.empty:
        st.info("No internal email documents found. Process some emails first.")
    else:
        # Build per-address sent/received counts
        _sent_counts = {}
        _recv_counts = {}
        for _, _row in _ca_df.iterrows():
            for _a in _extract_addresses(_row['email_from']):
                _sent_counts[_a] = _sent_counts.get(_a, 0) + 1
            for _a in (_extract_addresses(_row['email_to']) + _extract_addresses(_row['email_cc'])):
                _recv_counts[_a] = _recv_counts.get(_a, 0) + 1

        _all_addrs = set(_sent_counts) | set(_recv_counts)
        _comm_rows = [
            {'Email Address': a, 'Sent': _sent_counts.get(a, 0),
             'Received': _recv_counts.get(a, 0),
             'Total Activity': _sent_counts.get(a, 0) + _recv_counts.get(a, 0)}
            for a in _all_addrs
        ]
        _comm_df = pd.DataFrame(_comm_rows).sort_values('Total Activity', ascending=False).head(50)

        st.subheader("Top Communicators (up to 50)")
        if _comm_df.empty:
            st.info("No communication data available. Process email documents first.")
        else:
            _cc_top = _comm_df.head(20).sort_values('Total Activity', ascending=True)
            _cc_fig = go.Figure()
            _cc_fig.add_trace(go.Bar(
                y=_cc_top['Email Address'],
                x=_cc_top['Sent'],
                name='Sent',
                orientation='h',
                marker_color=_CHART_COLORS['primary'],
                hovertemplate='%{y}<br>Sent: %{x:,}<extra></extra>',
            ))
            _cc_fig.add_trace(go.Bar(
                y=_cc_top['Email Address'],
                x=_cc_top['Received'],
                name='Received',
                orientation='h',
                marker_color=_CHART_COLORS['secondary'],
                hovertemplate='%{y}<br>Received: %{x:,}<extra></extra>',
            ))
            _cc_fig = _apply_chart_layout(_cc_fig, height=max(350, len(_cc_top) * 22))
            _cc_fig.update_layout(
                barmode='stack',
                title=dict(text='Top 20 communicators by volume', font_size=14),
                xaxis_title='Emails',
            )
            st.plotly_chart(_cc_fig, width='stretch')

            with st.expander("📋 Full data table"):
                st.dataframe(_comm_df, width='stretch', hide_index=True)

        # Communication matrix for top 15 addresses
        _top_addrs = set(_comm_df.head(15)['Email Address'].tolist())
        _matrix_rows = []
        for _, _row in _ca_df.iterrows():
            for _fa in _extract_addresses(_row['email_from']):
                if _fa in _top_addrs:
                    for _ta in (_extract_addresses(_row['email_to']) + _extract_addresses(_row['email_cc'])):
                        if _ta in _top_addrs and _ta != _fa:
                            _matrix_rows.append({'From': _fa, 'To': _ta})
        if _matrix_rows:
            st.subheader("Communication Matrix (Top 15 Addresses)")
            st.caption("Cell intensity = number of emails sent from row address to column address.")
            _pivot = pd.DataFrame(_matrix_rows).pivot_table(
                index='From', columns='To', aggfunc='size', fill_value=0
            )
            _hm_fig = go.Figure(data=go.Heatmap(
                z=_pivot.values,
                x=_pivot.columns.tolist(),
                y=_pivot.index.tolist(),
                colorscale=[
                    [0, 'rgba(43,108,176,0.05)'],
                    [0.5, 'rgba(43,108,176,0.4)'],
                    [1, 'rgba(43,108,176,1.0)'],
                ],
                hovertemplate='From: %{y}<br>To: %{x}<br>Emails: %{z:,}<extra></extra>',
                texttemplate='%{z}',
                textfont=dict(size=10),
            ))
            _hm_fig = _apply_chart_layout(_hm_fig, height=max(400, len(_pivot) * 28 + 100))
            _hm_fig.update_layout(
                xaxis=dict(tickangle=-45, side='bottom'),
                yaxis=dict(autorange='reversed'),
            )
            st.plotly_chart(_hm_fig, width='stretch')

        # Custodian summary
        st.subheader("Custodian Summary")
        _cust_df = (
            _ca_df.groupby('custodian')
            .agg(total_emails=('control_number', 'count'))
            .reset_index()
            .sort_values('total_emails', ascending=False)
            .rename(columns={'custodian': 'Custodian', 'total_emails': 'Total Emails'})
        )
        st.dataframe(_cust_df, width='stretch', hide_index=True)

# =
# TAB 5: TIMELINE
# =
with tab5:
    st.header("Timeline Analysis")
    st.caption("Visualize email activity over time to identify spikes and potential preservation gaps.")

    _tl_key = 'tl_df_cache'
    if st.button("🔄 Refresh Timeline Data", key="tl_refresh") or _tl_key not in st.session_state:
        st.session_state[_tl_key] = pd.DataFrame(db_manager.get_timeline_data(case_folder))

    _tl_df = st.session_state.get(_tl_key, pd.DataFrame())

    if _tl_df.empty:
        st.info("No dated documents found.")
    else:
        _tl_df = _tl_df.copy()
        _tl_df['_date'] = pd.to_datetime(_tl_df['date_sent'], errors='coerce')
        _tl_df = _tl_df.dropna(subset=['_date'])

        _tl_col1, _tl_col2 = st.columns([2, 3])
        with _tl_col1:
            _granularity = st.radio("Group by", ["Day", "Week", "Month"], horizontal=True, key="tl_granularity")
            _gap_threshold = st.number_input("Flag gaps longer than (days)", min_value=1, value=14, key="tl_gap_days")
        with _tl_col2:
            _custodians = sorted(_tl_df['custodian'].dropna().unique().tolist())
            _selected_custs = st.multiselect("Filter by custodian", _custodians, default=_custodians, key="tl_custodians")

        _freq_map = {"Day": "D", "Week": "W", "Month": "ME"}
        _tl_filtered = _tl_df[_tl_df['custodian'].isin(_selected_custs)] if _selected_custs else _tl_df
        _tl_filtered = _tl_filtered.copy()
        _tl_filtered['_date'] = pd.to_datetime(_tl_filtered['_date'], utc=True)

        _grouped = (
            _tl_filtered.set_index('_date')
            .resample(_freq_map[_granularity])
            .size()
            .reset_index(name='Count')
            .rename(columns={'_date': 'Date'})
        )
        st.subheader(f"Email Volume by {_granularity}")
        _tl_fig = go.Figure()
        _tl_fig.add_trace(go.Bar(
            x=_grouped['Date'],
            y=_grouped['Count'],
            marker_color=_CHART_COLORS['primary'],
            hovertemplate='%{x|%Y-%m-%d}<br>Documents: %{y:,}<extra></extra>',
        ))

        # Gap detection with chart annotations
        _dates_with_activity = _grouped[_grouped['Count'] > 0]['Date'].sort_values().reset_index(drop=True)
        _gaps = []
        if len(_dates_with_activity) > 1:
            for _i in range(1, len(_dates_with_activity)):
                _delta = (_dates_with_activity.iloc[_i] - _dates_with_activity.iloc[_i - 1]).days
                if _delta > _gap_threshold:
                    _gap_start = _dates_with_activity.iloc[_i - 1]
                    _gap_end = _dates_with_activity.iloc[_i]
                    _gaps.append({
                        'Gap Start': _gap_start.date(),
                        'Gap End': _gap_end.date(),
                        'Duration (days)': _delta,
                    })
                    _tl_fig.add_vrect(
                        x0=_gap_start, x1=_gap_end,
                        fillcolor=_CHART_COLORS['danger'],
                        opacity=0.08,
                        line_width=0,
                        annotation_text=f"{_delta}d gap",
                        annotation_position="top left",
                        annotation_font_size=10,
                        annotation_font_color=_CHART_COLORS['danger'],
                    )

        if _gaps:
            st.warning(f"{len(_gaps)} potential collection gap(s) detected (>{_gap_threshold} days with no activity):")
            st.dataframe(pd.DataFrame(_gaps), width='stretch', hide_index=True)
        else:
            st.success(f"No gaps longer than {_gap_threshold} days detected in the email timeline.")

        _tl_fig = _apply_chart_layout(_tl_fig, height=380)
        _tl_fig.update_layout(
            title=dict(text=f'Document volume by {_granularity.lower()}', font_size=14),
            xaxis_title='Date',
            yaxis_title='Documents',
            showlegend=False,
        )
        st.plotly_chart(_tl_fig, width='stretch')

# =
# TAB 6: DOMAIN ANALYSIS
# =
with tab6:
    st.header("Domain Analysis")
    st.caption("Aggregate email communication by organization domain to identify key external parties.")

    _da_key = 'da_df_cache'
    if st.button("🔄 Refresh Domain Data", key="da_refresh") or _da_key not in st.session_state:
        _da_conn = db_manager.get_connection(case_folder)
        st.session_state[_da_key] = pd.read_sql_query("""
            SELECT email_from, email_to, email_cc, custodian
            FROM documents
            WHERE record_type = 'Email'
              AND processing_status IN ('Processed', 'Master')
              AND (source_party = 'Internal' OR source_party IS NULL)
        """, _da_conn)
        _da_conn.close()

    _da_df = st.session_state.get(_da_key, pd.DataFrame())

    if _da_df.empty:
        st.info("No email documents found.")
    else:
        _domain_sent = {}
        _domain_recv = {}
        _domain_addrs = {}   # domain → set of unique addresses

        for _, _row in _da_df.iterrows():
            _from_addrs = _extract_addresses(_row['email_from'])
            _to_addrs = _extract_addresses(_row['email_to']) + _extract_addresses(_row['email_cc'])

            for _a in _from_addrs:
                if '@' in _a:
                    _d = _a.split('@')[1]
                    _domain_sent[_d] = _domain_sent.get(_d, 0) + 1
                    _domain_addrs.setdefault(_d, set()).add(_a)
            for _a in _to_addrs:
                if '@' in _a:
                    _d = _a.split('@')[1]
                    _domain_recv[_d] = _domain_recv.get(_d, 0) + 1
                    _domain_addrs.setdefault(_d, set()).add(_a)

        _all_domains = set(_domain_sent) | set(_domain_recv)
        _domain_rows = [
            {
                'Domain': _d,
                'Total Mentions': _domain_sent.get(_d, 0) + _domain_recv.get(_d, 0),
                'As Sender': _domain_sent.get(_d, 0),
                'As Recipient': _domain_recv.get(_d, 0),
                'Unique Addresses': len(_domain_addrs.get(_d, set())),
            }
            for _d in _all_domains
        ]
        _domain_df = pd.DataFrame(_domain_rows).sort_values('Total Mentions', ascending=False)

        # Internal vs external heuristic: top sender domain = internal
        _internal_domains = set()
        if not _domain_df.empty:
            _top_sender_domain = _domain_df.sort_values('As Sender', ascending=False).iloc[0]['Domain']
            _internal_domains.add(_top_sender_domain)
            # Also flag custodian email domains if parseable
            for _cust in _da_df['custodian'].dropna().unique():
                for _a in _extract_addresses(str(_cust)):
                    if '@' in _a:
                        _internal_domains.add(_a.split('@')[1])

        _domain_df['Type'] = _domain_df['Domain'].apply(
            lambda d: 'Internal' if d in _internal_domains else 'External'
        )

        _n_internal = (_domain_df['Type'] == 'Internal').sum()
        _n_external = (_domain_df['Type'] == 'External').sum()
        _da_m1, _da_m2, _da_m3 = st.columns(3)
        _da_m1.metric("Internal Domains", _n_internal)
        _da_m2.metric("External Domains", _n_external)
        _da_m3.metric("Total Unique Domains", len(_domain_df))

        st.subheader("Domain Frequency")

        _da_pie_col, _da_bar_col = st.columns([1, 2])

        with _da_pie_col:
            _ie_counts = _domain_df['Type'].value_counts()
            _ie_fig = go.Figure(data=[go.Pie(
                labels=_ie_counts.index.tolist(),
                values=_ie_counts.values.tolist(),
                hole=0.45,
                marker=dict(colors=[
                    _CHART_COLORS['primary'] if t == 'Internal' else _CHART_COLORS['muted']
                    for t in _ie_counts.index
                ]),
                textinfo='label+value',
                hovertemplate='%{label}: %{value} domains (%{percent})<extra></extra>',
            )])
            _ie_fig.update_layout(
                showlegend=False,
                margin=dict(l=10, r=10, t=30, b=10),
                height=250,
                title=dict(text='Internal vs external', font_size=13),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(family="system-ui, -apple-system, sans-serif", size=11),
            )
            st.plotly_chart(_ie_fig, width='stretch')

        with _da_bar_col:
            _da_top = _domain_df.head(15).sort_values('Total Mentions', ascending=True)
            _da_fig = go.Figure()
            _da_fig.add_trace(go.Bar(
                y=_da_top['Domain'],
                x=_da_top['As Sender'],
                name='As Sender',
                orientation='h',
                marker_color=_CHART_COLORS['primary'],
                hovertemplate='%{y}<br>Sent: %{x:,}<extra></extra>',
            ))
            _da_fig.add_trace(go.Bar(
                y=_da_top['Domain'],
                x=_da_top['As Recipient'],
                name='As Recipient',
                orientation='h',
                marker_color=_CHART_COLORS['secondary'],
                hovertemplate='%{y}<br>Received: %{x:,}<extra></extra>',
            ))
            _da_fig = _apply_chart_layout(_da_fig, height=max(300, len(_da_top) * 22))
            _da_fig.update_layout(
                barmode='stack',
                title=dict(text='Top 15 domains by email volume', font_size=13),
                xaxis_title='Emails',
            )
            st.plotly_chart(_da_fig, width='stretch')

        with st.expander("📋 Full domain table"):
            st.dataframe(_domain_df, width='stretch', hide_index=True)

        # Top domain pairs
        st.subheader("Top Domain-to-Domain Communication")
        _pair_counts = {}
        for _, _row in _da_df.iterrows():
            _from_domains = [_a.split('@')[1] for _a in _extract_addresses(_row['email_from']) if '@' in _a]
            _to_domains = [_a.split('@')[1] for _a in (_extract_addresses(_row['email_to']) + _extract_addresses(_row['email_cc'])) if '@' in _a]
            for _fd in _from_domains:
                for _td in _to_domains:
                    if _fd != _td:
                        _pair = f"{_fd} → {_td}"
                        _pair_counts[_pair] = _pair_counts.get(_pair, 0) + 1
        if _pair_counts:
            _pairs_sorted = sorted(_pair_counts.items(), key=lambda x: -x[1])[:10]
            _pairs_labels = [p[0] for p in _pairs_sorted]
            _pairs_values = [p[1] for p in _pairs_sorted]
            _pairs_labels.reverse()
            _pairs_values.reverse()

            _dp_fig = go.Figure(go.Bar(
                y=_pairs_labels,
                x=_pairs_values,
                orientation='h',
                marker_color=_CHART_COLORS['teal'],
                hovertemplate='%{y}<br>Emails: %{x:,}<extra></extra>',
                text=[f'{v:,}' for v in _pairs_values],
                textposition='outside',
            ))
            _dp_fig = _apply_chart_layout(_dp_fig, height=max(300, len(_pairs_labels) * 28))
            _dp_fig.update_layout(
                title=dict(text='Top 10 cross-domain email routes', font_size=13),
                xaxis_title='Emails',
            )
            st.plotly_chart(_dp_fig, width='stretch')

# ==============================================================================
# TAB 7: CUSTODIAN OVERLAP ANALYSIS
# ==============================================================================
with tab7:
    st.subheader("Cross-Custodian Document Overlap")
    st.caption(
        "Identifies documents shared between custodians based on content hash (SHA-256). "
        "High overlap between custodians may indicate duplicative review effort."
    )

    _ov_conn = db_manager.get_connection(case_folder)
    try:
        _ov_rows = _ov_conn.execute(  # db_manager: exempt (dashboard read)
            """
            SELECT d1.custodian AS custodian_a, d2.custodian AS custodian_b,
                   COUNT(DISTINCT d1.content_hash) AS shared_docs
            FROM documents d1
            JOIN documents d2 ON d1.content_hash = d2.content_hash
            WHERE d1.custodian < d2.custodian
              AND d1.content_hash IS NOT NULL AND d1.content_hash != ''
              AND d1.processing_status = 'Processed' AND d2.processing_status = 'Processed'
            GROUP BY d1.custodian, d2.custodian
            ORDER BY shared_docs DESC
        """).fetchall()
    finally:
        _ov_conn.close()

    if not _ov_rows:
        st.info("No cross-custodian document overlap detected. This analysis requires processed documents with content hashes from at least 2 custodians.")
    else:
        _ov_data = [dict(r) for r in _ov_rows]
        _ov_total = sum(r['shared_docs'] for r in _ov_data)
        _ov_pairs = len(_ov_data)

        ov_c1, ov_c2 = st.columns(2)
        ov_c1.metric("Total Shared Documents", f"{_ov_total:,}")
        ov_c2.metric("Custodian Pairs with Overlap", _ov_pairs)

        # Overlap table
        _ov_df = pd.DataFrame(_ov_data)
        _ov_df.columns = ['Custodian A', 'Custodian B', 'Shared Documents']
        st.dataframe(_ov_df, width='stretch', hide_index=True)

        # Heatmap
        if len(_ov_data) >= 1:
            # Build symmetric matrix
            custodians = sorted(set(
                [r['custodian_a'] for r in _ov_data] +
                [r['custodian_b'] for r in _ov_data]
            ))
            import numpy as np
            matrix = np.zeros((len(custodians), len(custodians)))
            cust_idx = {c: i for i, c in enumerate(custodians)}
            for r in _ov_data:
                i, j = cust_idx[r['custodian_a']], cust_idx[r['custodian_b']]
                matrix[i][j] = r['shared_docs']
                matrix[j][i] = r['shared_docs']

            import plotly.graph_objects as go
            _hm_fig = go.Figure(data=go.Heatmap(
                z=matrix,
                x=custodians,
                y=custodians,
                colorscale='Blues',
                text=matrix.astype(int).astype(str),
                texttemplate='%{text}',
                hovertemplate='%{y} \u2194 %{x}<br>Shared: %{z:,}<extra></extra>',
            ))
            _hm_fig.update_layout(
                title=dict(text='Custodian Document Overlap Heatmap', font_size=13),
                height=max(400, len(custodians) * 50),
                xaxis_title='',
                yaxis_title='',
                yaxis=dict(autorange='reversed'),
            )
            st.plotly_chart(_hm_fig, width='stretch')

# ==============================================================================
# TAB 8: CONCEPT EXPLORER
# ==============================================================================
with tab8:
    st.subheader("Concept Explorer")
    st.caption(
        "Enter a seed query to discover statistically significant terms in matching documents. "
        "Useful for keyword expansion, search term negotiation, and identifying unexpected themes."
    )

    _ce_col1, _ce_col2 = st.columns([3, 1])
    with _ce_col1:
        _ce_query = st.text_input(
            "Seed Query",
            placeholder="e.g., contract breach damages",
            key="concept_explorer_query",
            label_visibility="collapsed",
        )
    with _ce_col2:
        _ce_size = st.selectbox(
            "Results",
            [10, 20, 30, 50],
            index=1,
            key="concept_explorer_size",
            label_visibility="collapsed",
        )

    if _ce_query and _ce_query.strip():
        try:
            _ce_client = os_manager.get_os_client()
            _ce_index = os_manager.get_index_name(os.path.basename(case_folder))

            # Use significant_text aggregation (works on analyzed text fields)
            _ce_body = {
                "query": {
                    "query_string": {
                        "query": _ce_query,
                        "default_field": "content",
                        "default_operator": "AND",
                    }
                },
                "aggs": {
                    "significant_concepts": {
                        "significant_text": {
                            "field": "content",
                            "size": _ce_size,
                            "min_doc_count": 2,
                        }
                    }
                },
                "size": 0,
            }

            _ce_resp = _ce_client.search(index=_ce_index, body=_ce_body)
            _ce_hit_count = _ce_resp['hits']['total']['value']
            _ce_buckets = _ce_resp.get('aggregations', {}).get('significant_concepts', {}).get('buckets', [])

            st.metric("Documents Matching Query", f"{_ce_hit_count:,}")

            if _ce_buckets:
                _ce_terms = []
                for b in _ce_buckets:
                    _ce_terms.append({
                        'Term': b['key'],
                        'Doc Count': b['doc_count'],
                        'Score': round(b.get('score', 0), 4),
                        'Background Count': b.get('bg_count', 0),
                    })

                _ce_df = pd.DataFrame(_ce_terms)
                st.dataframe(_ce_df, width='stretch', hide_index=True)

                # Bar chart of top terms
                import plotly.graph_objects as go
                _ce_fig = go.Figure(go.Bar(
                    x=[t['Score'] for t in _ce_terms[:15]],
                    y=[t['Term'] for t in _ce_terms[:15]],
                    orientation='h',
                    marker_color='#339af0',
                    hovertemplate='%{y}<br>Score: %{x:.4f}<extra></extra>',
                ))
                _ce_fig.update_layout(
                    title=dict(text='Significant Terms (by relevance score)', font_size=13),
                    height=max(300, min(len(_ce_terms), 15) * 28),
                    xaxis_title='Significance Score',
                    yaxis=dict(autorange='reversed'),
                    margin=dict(l=10, r=10, t=40, b=40),
                )
                st.plotly_chart(_ce_fig, width='stretch')
            else:
                st.info("No significant terms found for this query. Try a broader search or different terms.")

        except Exception as _ce_err:
            _ce_err_str = str(_ce_err)
            if 'significant_text' in _ce_err_str or 'aggregation' in _ce_err_str.lower():
                # Fallback: try significant_terms on email_subject.keyword
                st.warning(
                    "The `significant_text` aggregation is not available on this OpenSearch version. "
                    "Showing basic term frequency instead."
                )
                try:
                    _ce_body_fallback = {
                        "query": {
                            "query_string": {
                                "query": _ce_query,
                                "default_field": "content",
                                "default_operator": "AND",
                            }
                        },
                        "aggs": {
                            "top_terms": {
                                "terms": {
                                    "field": "email_subject.keyword",
                                    "size": _ce_size,
                                }
                            }
                        },
                        "size": 0,
                    }
                    _ce_resp_fb = _ce_client.search(index=_ce_index, body=_ce_body_fallback)
                    _ce_buckets_fb = _ce_resp_fb.get('aggregations', {}).get('top_terms', {}).get('buckets', [])
                    if _ce_buckets_fb:
                        _ce_fb_data = [{'Subject': b['key'], 'Count': b['doc_count']} for b in _ce_buckets_fb]
                        st.dataframe(pd.DataFrame(_ce_fb_data), width='stretch', hide_index=True)
                    else:
                        st.info("No terms found.")
                except Exception as _fb_err:
                    st.error(f"Fallback aggregation also failed: {_fb_err}")
            else:
                st.error(f"OpenSearch query failed: {_ce_err}")
    else:
        st.info("Enter a seed query above to discover related concepts in your document collection.")