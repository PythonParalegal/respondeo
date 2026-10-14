# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        defensibility_report.py
# version:       1.7.0
# project:       Respondeo eDiscovery Platform
# project_ver:   2.16.0
# last_modified: 2026-06-01 12:00
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
"""
Defensibility Report Generator — assembles existing case data into a
court-ready PDF. No Streamlit dependency; pure data collection + PDF output.
"""
import os
import json
import logging
from datetime import datetime

import db_manager

logger = logging.getLogger(__name__)


def _fmt_date(val):
    """Format an ISO date/timestamp string to a readable date. Returns 'N/A' for empty/invalid."""
    if not val or val == 'N/A':
        return 'N/A'
    try:
        s = str(val)[:10]  # Take just YYYY-MM-DD
        parts = s.split('-')
        if len(parts) == 3:
            from datetime import date as _d
            d = _d(int(parts[0]), int(parts[1]), int(parts[2]))
            return d.strftime('%B %d, %Y')
    except Exception:
        pass
    return str(val)[:10]


# System-generated tags — not evidence of human review
SYSTEM_TAGS = {
    'NearDupe-Principal', 'NearDupe-Suppressed',
    'Inclusive', 'Thread-Suppressed',
    'Junk Image', 'Duplicate (MD5)', 'Duplicate (Content)',
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA COLLECTION — each function opens/closes its own DB connection
# ═══════════════════════════════════════════════════════════════════════════════

def _collect_case_overview(case_folder, case_name, generated_by):
    """Cover page and executive summary data."""
    try:
        stats = db_manager.get_defensibility_overview(case_folder)
        return {
            'case_name': case_name,
            'case_status': stats['case_status'],
            'generated_by': generated_by,
            'generated_at': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
            'total_documents': stats['total_documents'],
            'total_custodians': stats['total_custodians'],
            'date_range_earliest': _fmt_date(stats['date_range_earliest']),
            'date_range_latest': _fmt_date(stats['date_range_latest']),
            'first_ingestion': _fmt_date(stats['first_ingestion']),
            'last_processing': _fmt_date(stats['last_processing']),
            'matter_profile': db_manager.get_matter_profile(case_folder),
        }
    except Exception as e:
        logger.error(f"Case overview collection failed: {e}")
        return {
            'case_name': case_name, 'case_status': 'Unknown',
            'generated_by': generated_by,
            'generated_at': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
            'total_documents': 0, 'total_custodians': 0,
            'date_range_earliest': 'N/A', 'date_range_latest': 'N/A',
            'first_ingestion': 'N/A', 'last_processing': 'N/A',
        }


def _collect_ingestion_stats(case_folder):
    """Collection sources, custodian breakdown, file type distribution."""
    try:
        return db_manager.get_defensibility_ingestion(case_folder)
    except Exception as e:
        logger.error(f"Ingestion stats collection failed: {e}")
        return {'custodians': [], 'file_types': [], 'record_types': [],
                'source_collections': [], 'total_size_kb': 0}


def _collect_processing_stats(case_folder):
    """Processing pipeline results, error rates, extraction methods."""
    try:
        return db_manager.get_defensibility_processing(case_folder)
    except Exception as e:
        logger.error(f"Processing stats collection failed: {e}")
        return {'status_breakdown': [], 'extraction_methods': [], 'error_docs': [],
                'error_count': 0, 'encrypted_count': 0, 'ocr_count': 0}


def _collect_dedup_stats(case_folder):
    """Deduplication methodology and results."""
    try:
        stats = db_manager.get_defensibility_dedup(case_folder)
        total_ingested = stats['total_ingested']
        net_reviewable = stats['net_reviewable']
        reduction_pct = ((total_ingested - net_reviewable) / total_ingested * 100) if total_ingested > 0 else 0
        stats['reduction_pct'] = round(reduction_pct, 1)
        stats['exact_dupe_pct'] = round((stats['exact_dupes'] / total_ingested * 100) if total_ingested > 0 else 0, 1)
        stats['content_dupe_pct'] = round((stats['content_dupes'] / total_ingested * 100) if total_ingested > 0 else 0, 1)
        stats['nd_pct'] = round((stats['nd_suppressed'] / total_ingested * 100) if total_ingested > 0 else 0, 1)
        stats['thread_pct'] = round((stats['thread_suppressed'] / total_ingested * 100) if total_ingested > 0 else 0, 1)
        return stats
    except Exception as e:
        logger.error(f"Dedup stats collection failed: {e}")
        return {k: 0 for k in ['total_ingested', 'exact_dupes', 'content_dupes', 'processed',
                'nd_suppressed', 'nd_principals', 'thread_suppressed', 'thread_inclusive',
                'net_reviewable', 'reduction_pct', 'exact_dupe_pct', 'content_dupe_pct',
                'nd_pct', 'thread_pct',
                'nd_family_retained', 'nd_distinct', 'nd_undecided', 'n_clusters']}


def _collect_review_stats(case_folder):
    """Review progress, tag distribution, reviewer activity."""
    try:
        stats = db_manager.get_defensibility_review(case_folder)

        # Count human-reviewed docs: must have at least one non-system tag
        tagged_count = 0
        for row in stats['reviewable_tags']:
            doc_tags = {t.strip() for t in str(row['tags']).replace(';', ',').split(',') if t.strip()}
            if doc_tags - SYSTEM_TAGS:
                tagged_count += 1

        # Tag distribution across all documents
        tag_counts = {}
        for row in stats['all_tags_raw']:
            for tag in str(row['tags']).replace(';', ',').split(','):
                tag = tag.strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        tag_distribution = sorted(tag_counts.items(), key=lambda x: -x[1])

        total_reviewable = stats['total_reviewable']
        return {
            'total_reviewable': total_reviewable,
            'tagged_count': tagged_count,
            'review_completion_pct': round((tagged_count / total_reviewable * 100) if total_reviewable > 0 else 0, 1),
            'tag_distribution': tag_distribution,
            'reviewer_activity': stats['reviewer_activity'],
            'responsive_count': stats['responsive_count'],
            'not_responsive_count': stats['not_responsive_count'],
        }
    except Exception as e:
        logger.error(f"Review stats collection failed: {e}")
        return {'total_reviewable': 0, 'tagged_count': 0, 'review_completion_pct': 0,
                'tag_distribution': [], 'reviewer_activity': [],
                'responsive_count': 0, 'not_responsive_count': 0}


def _collect_production_stats(case_folder):
    """Production volumes, Bates ranges, QC results."""
    try:
        stats = db_manager.get_defensibility_production(case_folder)
        stats['bates_info'] = db_manager.get_last_bates_info(case_folder)
        stats['clawbacks'] = db_manager.get_clawback_summary(case_folder)
        stats['clawback_count'] = len(stats['clawbacks'])
        stats['production_runs'] = db_manager.get_production_history(case_folder, direction='outbound')
        return stats
    except Exception as e:
        logger.error(f"Production stats collection failed: {e}")
        return {'productions': [], 'bates_info': None, 'clawbacks': [],
                'clawback_count': 0, 'prod_events': [], 'total_produced': 0,
                'total_produced_jt': 0, 'prod_detail': [],
                'production_runs': []}


def _collect_privilege_stats(case_folder):
    """Privilege disposition summary."""
    try:
        return db_manager.get_defensibility_privilege(case_folder)
    except Exception as e:
        logger.error(f"Privilege stats collection failed: {e}")
        return {'withheld': 0, 'redacted': 0, 'no_disposition': 0,
                'total_privileged': 0, 'redaction_marks_count': 0, 'redactions_applied': 0}


def _collect_audit_summary(case_folder):
    """Audit trail event counts, date range, user activity."""
    try:
        return db_manager.get_defensibility_audit(case_folder)
    except Exception as e:
        logger.error(f"Audit summary collection failed: {e}")
        return {'total_events': 0, 'earliest_event': 'N/A', 'latest_event': 'N/A',
                'by_action': [], 'by_user': [], 'by_module': []}


def _collect_hold_stats(case_folder):
    """Legal hold tracking summary."""
    try:
        stats = db_manager.get_defensibility_holds(case_folder)
        if not stats['has_custodians_table']:
            return {'holds': [], 'active_count': 0, 'released_count': 0,
                    'unacknowledged_count': 0, 'total_on_hold': 0}

        holds = stats['holds']
        active = sum(1 for h in holds if h['hold_status'] == 'Active')
        released = sum(1 for h in holds if h['hold_status'] == 'Released')
        unack = sum(1 for h in holds if not h['hold_acknowledged_date'])

        return {
            'holds': holds,
            'active_count': active,
            'released_count': released,
            'unacknowledged_count': unack,
            'total_on_hold': len(holds),
        }
    except Exception as e:
        logger.error(f"Hold stats collection failed: {e}")
        return {'holds': [], 'active_count': 0, 'released_count': 0,
                'unacknowledged_count': 0, 'total_on_hold': 0}


def _collect_collection_scope(case_folder):
    """Collect all collection scope data for the defensibility report."""
    try:
        return db_manager.get_all_collection_scope(case_folder)
    except Exception:
        return []


def _collect_near_dupe_clusters(case_folder):
    """Per-cluster near-dupe disposition rows for §4.2 (court-facing roll-up).
    Returns [] on any error or when no clusters exist."""
    try:
        return db_manager.get_near_dupe_cluster_detail(case_folder)
    except Exception as e:
        logger.error(f"Near-dupe cluster detail collection failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════════

def _render_html(data):
    """Build the complete HTML report from collected data sections."""

    import config

    overview = data['overview']
    ingestion = data['ingestion']
    processing = data['processing']
    dedup = data['dedup']
    review = data['review']
    production = data['production']
    privilege = data['privilege']
    audit = data['audit']
    holds = data.get('holds', {})
    collection_scope = data.get('collection_scope', [])

    # Pre-compute values that can't use dict literals inside f-strings
    _cover_name = (overview.get('matter_profile') or {}).get('case_caption') or overview['case_name']

    def _fmt_size(kb):
        if kb is None:
            return '0 KB'
        if kb < 1024:
            return f"{kb:,.0f} KB"
        if kb < 1048576:
            return f"{kb / 1024:,.1f} MB"
        return f"{kb / 1048576:,.1f} GB"

    # Build the HTML document
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: letter;
        margin: 1in 0.85in;
    }}
    body {{
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 11pt;
        color: #2d3748;
        line-height: 1.6;
        margin: 0;
        padding: 0;
    }}

    /* --- Cover Page --- */
    .cover {{
        text-align: center;
        padding-top: 2.5in;
        page-break-after: always;
    }}
    .cover h1 {{
        font-size: 28pt;
        color: #1a365d;
        margin-bottom: 8px;
        font-weight: 700;
        letter-spacing: -0.5px;
    }}
    .cover .case-name {{
        font-size: 18pt;
        color: #2b6cb0;
        margin: 24px 0 48px 0;
        font-style: italic;
    }}
    .cover .meta {{
        font-size: 11pt;
        color: #718096;
        margin: 6px 0;
    }}
    .cover .confidential {{
        margin-top: 60px;
        padding: 12px 24px;
        border: 2px solid #e53e3e;
        color: #e53e3e;
        font-weight: 700;
        font-size: 11pt;
        display: inline-block;
        letter-spacing: 2px;
        text-transform: uppercase;
    }}

    /* --- Section Headings --- */
    h2 {{
        font-size: 16pt;
        color: #1a365d;
        border-bottom: 2px solid #2b6cb0;
        padding-bottom: 6px;
        margin-top: 36px;
        margin-bottom: 16px;
        page-break-after: avoid;
    }}
    h3 {{
        font-size: 13pt;
        color: #2c5282;
        margin-top: 24px;
        margin-bottom: 10px;
        page-break-after: avoid;
    }}

    /* --- Tables --- */
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 12px 0 20px 0;
        font-size: 10pt;
        page-break-inside: auto;
    }}
    th {{
        background-color: #ebf8ff;
        color: #1a365d;
        font-weight: 700;
        text-align: left;
        padding: 8px 10px;
        border-bottom: 2px solid #2b6cb0;
    }}
    td {{
        padding: 6px 10px;
        border-bottom: 1px solid #e2e8f0;
        white-space: nowrap;
    }}
    tr {{
        page-break-inside: avoid;
    }}
    tr:nth-child(even) td {{
        background-color: #f7fafc;
    }}
    thead {{
        display: table-header-group;
    }}

    /* --- Metric Cards --- */
    .metrics {{
        display: table;
        width: 100%;
        margin: 16px 0;
    }}
    .metric {{
        display: table-cell;
        text-align: center;
        padding: 12px 8px;
        border: 1px solid #e2e8f0;
        background: #f7fafc;
    }}
    .metric .value {{
        font-size: 22pt;
        font-weight: 700;
        color: #1a365d;
        display: block;
    }}
    .metric .label {{
        font-size: 9pt;
        color: #718096;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    /* --- Narrative Blocks --- */
    .narrative {{
        background: #f0fff4;
        border-left: 4px solid #38a169;
        padding: 12px 16px;
        margin: 16px 0;
        font-size: 10.5pt;
    }}
    .warning-block {{
        background: #fffaf0;
        border-left: 4px solid #dd6b20;
        padding: 12px 16px;
        margin: 16px 0;
        font-size: 10.5pt;
    }}

    /* --- Footer --- */
    .footer {{
        font-size: 8pt;
        color: #a0aec0;
        text-align: center;
        margin-top: 40px;
        border-top: 1px solid #e2e8f0;
        padding-top: 8px;
    }}

    /* --- Page Break Utility --- */
    .page-break {{
        page-break-before: always;
    }}
</style>
</head>
<body>

<!-- COVER PAGE -->
<div class="cover">
    <h1>eDiscovery Defensibility Report</h1>
    <div class="case-name">{_cover_name}</div>
    <div class="meta">Generated: {overview['generated_at']}</div>
    <div class="meta">Prepared by: {overview['generated_by']}</div>
    <div class="meta">Platform: Respondeo v{getattr(config, '__version__', 'N/A')}</div>
    <div class="meta">Case Status: {overview['case_status']}</div>
    <div class="confidential">Privileged &amp; Confidential &mdash; Attorney Work Product</div>
</div>

<!-- 1. EXECUTIVE SUMMARY -->
<h2>1. Executive Summary</h2>
<div class="metrics">
    <div class="metric">
        <span class="value">{overview['total_documents']:,}</span>
        <span class="label">Total Documents</span>
    </div>
    <div class="metric">
        <span class="value">{overview['total_custodians']}</span>
        <span class="label">Custodians</span>
    </div>
    <div class="metric">
        <span class="value">{dedup['net_reviewable']:,}</span>
        <span class="label">Net Reviewable</span>
    </div>
    <div class="metric">
        <span class="value">{production['total_produced']:,}</span>
        <span class="label">Produced</span>
    </div>
    <div class="metric">
        <span class="value">{dedup['reduction_pct']}%</span>
        <span class="label">Dedup Reduction</span>
    </div>
</div>"""

    # Matter Profile table (only render rows with values)
    _mp = overview.get('matter_profile', {})
    _mp_rows = [
        ('Matter Number', _mp.get('matter_number')),
        ('Case Caption', _mp.get('case_caption')),
        ('Court', _mp.get('court')),
        ('Case/Docket Number', _mp.get('case_number')),
        ('Judge', _mp.get('judge')),
        ('Opposing Counsel', _mp.get('opposing_counsel')),
        ('Complaint Filed', _fmt_date(_mp.get('date_complaint_filed'))),
        ('Discovery Cutoff', _fmt_date(_mp.get('date_discovery_cutoff'))),
        ('Trial Date', _fmt_date(_mp.get('date_trial'))),
    ]
    _mp_filled = [(k, v) for k, v in _mp_rows if v and v != 'N/A']
    if _mp_filled:
        html += '<table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>'
        for _k, _v in _mp_filled:
            html += f'<tr><td>{_k}</td><td>{_v}</td></tr>'
        html += '</tbody></table>'

    html += f"""<p>This report documents the electronically stored information (&ldquo;ESI&rdquo;) collection,
processing, review, and production methodology employed in <em>{overview['case_name']}</em>.
The collection spans {overview['total_custodians']} custodian(s) comprising
{overview['total_documents']:,} documents totaling {_fmt_size(ingestion['total_size_kb'])}.
Processing first began on {overview['first_ingestion']} with the most recent
processing activity on {overview['last_processing']}.</p>

<!-- 2. COLLECTION & INGESTION -->
<h2 class="page-break">2. Collection &amp; Ingestion</h2>
<p>Documents were collected from {overview['total_custodians']} custodian source(s)
totaling {_fmt_size(ingestion['total_size_kb'])} of source data.
The date range of collected materials spans from {overview['date_range_earliest']}
to {overview['date_range_latest']}.</p>

<h3>2.1 Custodian Breakdown</h3>"""

    html += '<table><thead><tr><th>Custodian</th><th>Documents</th><th>Size</th></tr></thead><tbody>'
    for c in ingestion['custodians']:
        html += f"<tr><td>{c['custodian']}</td><td>{c['doc_count']:,}</td><td>{_fmt_size(c['total_size_kb'])}</td></tr>"
    html += '</tbody></table>'

    # Section 2.2 — Collection Scope
    html += '<h3>2.2 Collection Scope &amp; Justification</h3>'
    if collection_scope:
        # Summary counts
        _scope_counts = {}
        for s in collection_scope:
            _scope_counts[s['status']] = _scope_counts.get(s['status'], 0) + 1
        html += '<p><strong>Summary:</strong> '
        html += ', '.join(f"{ct} {st}" for st, ct in sorted(_scope_counts.items()))
        html += '</p>'

        html += ('<table><thead><tr>'
                 '<th>Custodian</th><th>Source</th><th>Status</th>'
                 '<th>Justification</th></tr></thead><tbody>')
        for s in collection_scope:
            html += (f"<tr><td>{s['custodian']}</td>"
                     f"<td>{s['source_name']}</td>"
                     f"<td>{s['status']}</td>"
                     f"<td>{s['justification'] or '—'}</td></tr>")
        html += '</tbody></table>'
    else:
        html += '<p><em>No collection scope data has been documented.</em></p>'

    html += '<h3>2.3 File Type Distribution</h3>'
    html += '<table><thead><tr><th>Extension</th><th>Count</th></tr></thead><tbody>'
    for ft in ingestion['file_types']:
        html += f"<tr><td>{ft['ext']}</td><td>{ft['count']:,}</td></tr>"
    html += '</tbody></table>'

    html += '<h3>2.4 Record Type Classification</h3>'
    html += '<table><thead><tr><th>Type</th><th>Count</th></tr></thead><tbody>'
    for rt in ingestion['record_types']:
        html += f"<tr><td>{rt['rtype']}</td><td>{rt['count']:,}</td></tr>"
    html += '</tbody></table>'

    # 3. PROCESSING
    html += '<h2 class="page-break">3. Processing Protocol</h2>'
    html += """<p>All collected ESI was processed through the platform's automated pipeline,
which performs text extraction, metadata population, container explosion (PST, ZIP, RAR, 7Z),
deduplication, and document imaging. The following table summarizes processing outcomes.</p>"""

    html += '<h3>3.1 Processing Status</h3>'
    html += '<table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>'
    for s in processing['status_breakdown']:
        html += f"<tr><td>{s['processing_status']}</td><td>{s['count']:,}</td></tr>"
    html += '</tbody></table>'

    html += '<h3>3.2 Text Extraction Methods</h3>'
    html += '<table><thead><tr><th>Method</th><th>Documents</th></tr></thead><tbody>'
    for m in processing['extraction_methods']:
        html += f"<tr><td>{m['method']}</td><td>{m['count']:,}</td></tr>"
    html += '</tbody></table>'

    if processing['encrypted_count'] > 0:
        html += f"""<div class="warning-block">
            <strong>{processing['encrypted_count']}</strong> encrypted/password-protected document(s)
            were identified during processing. These documents could not be fully text-extracted
            and are flagged in the review population.
        </div>"""

    if processing['ocr_count'] > 0:
        html += f"""<p>Optical Character Recognition (OCR) was applied to
        <strong>{processing['ocr_count']:,}</strong> image-based document(s) using
        Tesseract OCR to ensure searchability of scanned content.</p>"""

    # 4. DEDUPLICATION
    html += '<h2 class="page-break">4. Deduplication Methodology</h2>'
    html += f"""<p>The platform employs a multi-layer deduplication strategy to reduce the
review population while maintaining defensibility:</p>
<ol>
    <li><strong>Binary Deduplication (MD5)</strong> &mdash; Files with identical MD5 hash values are
    identified as exact duplicates. One copy is retained as the Master; duplicates are suppressed
    from review but preserved in the database with full chain-of-custody metadata.</li>
    <li><strong>Content Deduplication (SHA-256)</strong> &mdash; Files with different binary content but
    identical extracted text are identified by SHA-256 hash of the extracted text content.</li>
    <li><strong>Near-Duplicate Analysis (MinHash LSH)</strong> &mdash; Documents with 90%+ textual
    similarity are grouped into clusters. One representative (Principal) is retained; similar
    documents are suppressed but available for manual review if needed.</li>
    <li><strong>Email Thread Analysis</strong> &mdash; Inclusive email threading identifies the most
    complete message in each thread chain. Non-inclusive (superseded) messages are suppressed.</li>
</ol>

<div class="narrative">
    <strong>Defensibility Summary:</strong>
    Of <strong>{dedup['total_ingested']:,}</strong> total files ingested,
    <strong>{dedup['exact_dupes']:,}</strong> exact duplicates were identified by MD5 hash
    ({dedup['exact_dupe_pct']}% of collection),
    <strong>{dedup['content_dupes']:,}</strong> content duplicates were identified by text hash
    ({dedup['content_dupe_pct']}%),
    <strong>{dedup['nd_suppressed']:,}</strong> near-duplicate documents were suppressed in favor
    of {dedup['nd_principals']:,} representative principals ({dedup['nd_pct']}%),
    and <strong>{dedup['thread_suppressed']:,}</strong> thread-suppressed emails were removed as
    non-inclusive ({dedup['thread_pct']}%).
    The resulting net review population of <strong>{dedup['net_reviewable']:,}</strong> documents
    represents an overall reduction of <strong>{dedup['reduction_pct']}%</strong>.
    All suppressed documents remain in the database with complete metadata and can be recalled
    at any time.
</div>"""

    html += """<div class="narrative">
    <strong>Reviewer-Gated Near-Duplicate Suppression:</strong>
    Near-duplicate candidates are identified algorithmically (MinHash LSH, 90%+
    textual similarity), but suppression is not automatic. A reviewer confirms each
    candidate: documents confirmed as duplicates are suppressed and attested;
    documents still awaiting review remain in the active review population;
    documents a reviewer determines to be distinct are retained; and documents
    attached to a family are retained to preserve family integrity even when
    confirmed as duplicates. Only reviewer-confirmed, non-family documents are
    removed from the review population. Per-cluster dispositions and reviewer
    attestation are detailed in &sect;4.2.
    </div>"""

    html += """<h3>4.1 Suppression Breakdown</h3>
<table><thead><tr><th>Category</th><th>Count</th><th>% of Total</th></tr></thead><tbody>"""
    _di = dedup['total_ingested']
    _rows = [
        ('Total Files Ingested', dedup['total_ingested'], '100.0'),
        ('Unique Processed Documents', dedup['processed'], f"{dedup['processed']/_di*100:.1f}" if _di else '0.0'),
        ('Binary Duplicates (MD5)', dedup['exact_dupes'], str(dedup['exact_dupe_pct'])),
        ('Content Duplicates (SHA-256)', dedup['content_dupes'], str(dedup['content_dupe_pct'])),
        ('Near-Duplicate Confirmed-Suppressed (reviewer-attested)', dedup['nd_suppressed'], str(dedup['nd_pct'])),
        ('Thread-Suppressed Emails', dedup['thread_suppressed'], str(dedup['thread_pct'])),
        ('Net Review Population', dedup['net_reviewable'], f"{dedup['net_reviewable']/_di*100:.1f}" if _di else '0.0'),
    ]
    for label, count, pct in _rows:
        html += f"<tr><td>{label}</td><td>{count:,}</td><td>{pct}%</td></tr>"
    html += '</tbody></table>'

    # 4.2 Near-Duplicate Cluster Review & Attestation (S-1c)
    html += '<h3>4.2 Near-Duplicate Cluster Review &amp; Attestation</h3>'
    _nd_clusters = data.get('near_dupe_clusters', [])
    _n_clusters = dedup.get('n_clusters', 0)
    if _n_clusters == 0:
        html += """<p>No near-duplicate clusters were identified for this matter;
        accordingly, no near-duplicate suppressions were applied.</p>"""
    else:
        _n_attested = sum(1 for c in _nd_clusters if c.get('review_status') == 'approved')
        html += f"""<p>The platform identified <strong>{_n_clusters:,}</strong> near-duplicate
        cluster(s). Of the non-principal documents within them:
        <strong>{dedup['nd_suppressed']:,}</strong> were reviewer-confirmed as duplicates and
        suppressed; <strong>{dedup['nd_family_retained']:,}</strong> were confirmed duplicates but
        retained to preserve family integrity; <strong>{dedup['nd_distinct']:,}</strong> were
        reviewed and determined distinct (retained); and
        <strong>{dedup['nd_undecided']:,}</strong> remain pending review (retained pending
        confirmation). <strong>{_n_attested:,} of {_n_clusters:,}</strong> cluster(s) have been
        reviewer-attested as of report generation. Documents shown below are identified by
        internal control number; suppressed documents are excluded from production and therefore
        bear no Bates number.</p>"""
        if _n_clusters > len(_nd_clusters):
            html += f"""<p><em>The table lists the {len(_nd_clusters):,} largest clusters;
            {_n_clusters:,} clusters were identified in total. The aggregate counts above and in
            &sect;4.1 reflect all clusters.</em></p>"""
        html += """<table><thead><tr>
            <th>Cluster</th><th>Principal (control #)</th><th>Members</th>
            <th>Suppressed</th><th>Family-Ret.</th><th>Distinct</th><th>Pending</th>
            <th>Similarity</th><th>Attestation</th></tr></thead><tbody>"""
        for c in _nd_clusters:
            _supp = c.get('confirmed_count', 0) - c.get('family_retained_count', 0)
            # B-2 (v3): per-row Pending = ALL undecided (any family state), derived so the
            # row self-audits: Suppressed + Family-Ret + Distinct + Pending + 1 principal =
            # Members. Do NOT use pending_count (undecided & fp0) — it drops undecided-family
            # members and breaks the per-row sum. = member_count - 1 - confirmed - distinct.
            _pending = c.get('member_count', 0) - 1 - c.get('confirmed_count', 0) - c.get('distinct_count', 0)
            _sim = (f"{c['sim_min']*100:.0f}&ndash;{c['sim_max']*100:.0f}%"
                    if c.get('sim_min') is not None and c.get('sim_max') is not None else '&mdash;')
            if c.get('review_status') == 'approved':
                _att = f"&#10003; {c.get('reviewed_by') or ''} {(c.get('reviewed_at') or '')[:10]}".strip()
            else:
                _att = 'Pending'
            html += (f"<tr><td>{c.get('cluster_id')}</td><td>{c.get('principal_cn') or '&mdash;'}</td>"
                     f"<td>{c.get('member_count', 0):,}</td><td>{_supp:,}</td>"
                     f"<td>{c.get('family_retained_count', 0):,}</td>"
                     f"<td>{c.get('distinct_count', 0):,}</td><td>{_pending:,}</td>"
                     f"<td>{_sim}</td><td>{_att}</td></tr>")
        html += '</tbody></table>'
        # B-1 FIX (v2): Flag #30 multi-cluster footnote. The per-cluster columns above
        # are per-(cluster, document); a document may belong to more than one cluster, so
        # they may sum to more than the distinct-document totals in the summary paragraph.
        html += """<p><em>Note: a document may belong to more than one near-duplicate
        cluster. Per-cluster counts in the table above may therefore sum to more than the
        distinct-document totals stated in the summary; each document is counted once in the
        summary (suppressed, retained, or pending), and may appear in more than one row
        here.</em></p>"""

    # 5. REVIEW
    html += f"""<h2 class="page-break">5. Review Summary</h2>
<p>Document review was conducted using the platform's integrated review interface with
role-based access controls. All tagging, annotation, and redaction actions are recorded
in the immutable audit trail.</p>

<div class="metrics">
    <div class="metric">
        <span class="value">{review['total_reviewable']:,}</span>
        <span class="label">Reviewable Docs</span>
    </div>
    <div class="metric">
        <span class="value">{review['tagged_count']:,}</span>
        <span class="label">Reviewed (Tagged)</span>
    </div>
    <div class="metric">
        <span class="value">{review['review_completion_pct']}%</span>
        <span class="label">Completion</span>
    </div>
    <div class="metric">
        <span class="value">{review['responsive_count']:,}</span>
        <span class="label">Responsive</span>
    </div>
    <div class="metric">
        <span class="value">{review['not_responsive_count']:,}</span>
        <span class="label">Not Responsive</span>
    </div>
</div>"""

    if review['tag_distribution']:
        html += '<h3>5.1 Tag Distribution</h3>'
        html += '<table><thead><tr><th>Tag</th><th>Documents</th></tr></thead><tbody>'
        for tag_name, count in review['tag_distribution'][:30]:
            html += f"<tr><td>{tag_name}</td><td>{count:,}</td></tr>"
        html += '</tbody></table>'

    if review['reviewer_activity']:
        html += '<h3>5.2 Reviewer Activity</h3>'
        html += '<table><thead><tr><th>Reviewer</th><th>Actions</th><th>First Activity</th><th>Last Activity</th></tr></thead><tbody>'
        for r in review['reviewer_activity']:
            html += f"<tr><td>{r['reviewer']}</td><td>{r['actions']:,}</td><td>{r['first_action'] or '—'}</td><td>{r['last_action'] or '—'}</td></tr>"
        html += '</tbody></table>'

    # 6. PRODUCTION
    html += '<h2 class="page-break">6. Production Summary</h2>'

    if production['productions']:
        html += '<h3>6.1 Production Volumes</h3>'
        html += '<table><thead><tr><th>Volume</th><th>Documents</th><th>First Bates</th><th>Last Bates</th></tr></thead><tbody>'
        for p in production['productions']:
            html += f"<tr><td>{p['production_volume']}</td><td>{p['doc_count']:,}</td><td>{p['first_bates'] or '—'}</td><td>{p['last_bates'] or '—'}</td></tr>"
        html += '</tbody></table>'

        # Production detail from junction table (includes production dates and types)
        if production.get('prod_detail'):
            html += '<h4>Production Detail (by Type)</h4>'
            html += ('<table><thead><tr>'
                     '<th>Volume</th><th>Type</th><th>Documents</th>'
                     '<th>First Bates</th><th>Last Bates</th>'
                     '<th>First Produced</th><th>Last Produced</th>'
                     '</tr></thead><tbody>')
            for pd in production['prod_detail']:
                html += (f"<tr><td>{pd['production_volume']}</td>"
                         f"<td>{pd['production_type']}</td>"
                         f"<td>{pd['doc_count']:,}</td>"
                         f"<td>{pd['first_bates'] or '—'}</td>"
                         f"<td>{pd['last_bates'] or '—'}</td>"
                         f"<td>{(pd['first_produced'] or '')[:10]}</td>"
                         f"<td>{(pd['last_produced'] or '')[:10]}</td></tr>")
            html += '</tbody></table>'

        if production['bates_info']:
            bi = production['bates_info']
            html += f"""<div class="narrative">
                <strong>Bates Range Certification:</strong>
                The current Bates sequence uses prefix <strong>{bi.get('prefix', 'N/A')}</strong>
                with the highest assigned number being
                <strong>{bi.get('prefix', '')}-{str(bi.get('end_num', 0)).zfill(bi.get('padding', 6))}</strong>
                (assigned in volume &ldquo;{bi.get('prod_name', 'N/A')}&rdquo;).
                Bates numbering is sequential and gapless within each production volume,
                verified by the platform's automated QC check.
            </div>"""
    else:
        html += '<p style="color:#718096;">No productions have been completed for this matter.</p>'

    # Production run history. Aborted runs (status='aborted') are excluded
    # from the court-facing PDF — they're internal process churn that's not
    # material to opposing counsel (Flag #13).
    _pr_runs = production.get('production_runs', [])
    _pr_runs_visible = [r for r in _pr_runs if r.get('status') != 'aborted']
    if _pr_runs_visible:
        html += '<h3>6.2 Production Run History</h3>'
        html += '<table><thead><tr><th>Volume</th><th>Date</th><th>Format</th><th>Mode</th><th>Bates Range</th><th>Docs</th><th>Withheld</th><th>Redacted</th></tr></thead><tbody>'
        for _pr in _pr_runs_visible:
            _pr_range = f"{(_pr.get('bates_start') or '—')} — {(_pr.get('bates_end') or '—')}"
            html += f"<tr><td>{_pr['production_name']}</td><td>{_pr['created_at'][:10]}</td><td>{_pr['format']}</td><td>{_pr['mode']}</td><td>{_pr_range}</td><td>{_pr['document_count']:,}</td><td>{_pr.get('withheld_count', 0):,}</td><td>{_pr.get('redacted_count', 0):,}</td></tr>"
        html += '</tbody></table>'

    if production['clawback_count'] > 0:
        html += f"""<h3>6.2 Clawback / Inadvertent Disclosure</h3>
        <div class="warning-block">
            <strong>{production['clawback_count']}</strong> document(s) have been marked for
            clawback under FRE 502(b) / applicable clawback agreement.
        </div>"""
        html += '<table><thead><tr><th>Control #</th><th>File</th><th>Custodian</th><th>Status</th><th>Demand Date</th></tr></thead><tbody>'
        for c in production['clawbacks']:
            html += f"<tr><td>{c['control_number']}</td><td>{c['file_name'] or '—'}</td><td>{c['custodian'] or '—'}</td><td>{c['clawback_status']}</td><td>{c['clawback_date'] or '—'}</td></tr>"
        html += '</tbody></table>'

    # 7. PRIVILEGE
    html += '<h2 class="page-break">7. Privilege Handling</h2>'

    if privilege['total_privileged'] > 0:
        html += f"""<div class="metrics">
            <div class="metric">
                <span class="value">{privilege['total_privileged']:,}</span>
                <span class="label">Total Privileged</span>
            </div>
            <div class="metric">
                <span class="value">{privilege['withheld']:,}</span>
                <span class="label">Withheld</span>
            </div>
            <div class="metric">
                <span class="value">{privilege['redacted']:,}</span>
                <span class="label">Redacted</span>
            </div>
            <div class="metric">
                <span class="value">{privilege['redaction_marks_count']:,}</span>
                <span class="label">Docs w/ Marks</span>
            </div>
        </div>
        <p>Privileged documents were handled according to a two-disposition system:
        <strong>Withhold</strong> (document replaced with a branded placeholder slip sheet in production)
        and <strong>Redact</strong> (privilege-protected content removed with visible redaction marks
        and privilege reason annotation). All privilege determinations are recorded in the audit trail.</p>"""

        if privilege['no_disposition'] > 0:
            html += f"""<div class="warning-block">
                <strong>{privilege['no_disposition']}</strong> document(s) are tagged as Privileged
                but have not yet received a Withhold/Redact disposition.
                These documents should be reviewed before the next production.
            </div>"""
    else:
        html += '<p>No documents have been designated as privileged in this matter.</p>'

    # 8. AUDIT TRAIL
    html += f"""<h2 class="page-break">8. Audit Trail Summary</h2>
<p>The platform maintains an immutable, append-only audit trail recording every user action
on every document. Audit entries are never modified or deleted by any user action, including
administrators. The trail spans from {audit['earliest_event']} to
{audit['latest_event']}, comprising <strong>{audit['total_events']:,}</strong>
total recorded events.</p>"""

    html += '<h3>8.1 Events by Type</h3>'
    html += '<table><thead><tr><th>Event</th><th>Count</th></tr></thead><tbody>'
    for a in audit['by_action']:
        html += f"<tr><td>{a['action']}</td><td>{a['count']:,}</td></tr>"
    html += '</tbody></table>'

    html += '<h3>8.2 Activity by User</h3>'
    html += '<table><thead><tr><th>User</th><th>Events</th></tr></thead><tbody>'
    for u in audit['by_user']:
        html += f"<tr><td>{u['user']}</td><td>{u['count']:,}</td></tr>"
    html += '</tbody></table>'

    # 9. LEGAL HOLD TRACKING
    if holds.get('total_on_hold', 0) > 0:
        html += f"""<h2 class="page-break">9. Legal Hold Tracking</h2>
<p>The platform tracks legal hold status for all custodians, including hold issuance dates,
acknowledgment dates, release dates, and notice methods. This section summarizes the current
hold posture for this matter.</p>

<div class="metrics">
    <div class="metric">
        <span class="value">{holds['active_count']}</span>
        <span class="label">Active Holds</span>
    </div>
    <div class="metric">
        <span class="value">{holds['released_count']}</span>
        <span class="label">Released</span>
    </div>
    <div class="metric">
        <span class="value">{holds['unacknowledged_count']}</span>
        <span class="label">Unacknowledged</span>
    </div>
    <div class="metric">
        <span class="value">{holds['total_on_hold']}</span>
        <span class="label">Total Custodians</span>
    </div>
</div>"""

        if holds.get('unacknowledged_count', 0) > 0:
            html += f"""<div class="warning-block">
                <strong>{holds['unacknowledged_count']}</strong> custodian(s) have not yet acknowledged
                their preservation hold. Follow-up is recommended to document compliance.
            </div>"""

        html += '<table><thead><tr><th>Custodian</th><th>Status</th><th>Issued</th><th>Acknowledged</th><th>Released</th><th>Method</th></tr></thead><tbody>'
        for h in holds['holds']:
            html += f"<tr><td>{h['name']}</td><td>{h['hold_status']}</td><td>{h['hold_issued_date'] or '—'}</td><td>{h['hold_acknowledged_date'] or '—'}</td><td>{h['hold_released_date'] or '—'}</td><td>{h['hold_notice_method'] or '—'}</td></tr>"
        html += '</tbody></table>'

    # APPENDIX: PROCESSING ERRORS
    if processing['error_count'] > 0:
        html += f"""<h2 class="page-break">Appendix A: Processing Errors</h2>
<p>{processing['error_count']} document(s) encountered errors during processing.
These documents were flagged for manual review and are excluded from text search results
but remain in the database with all available metadata preserved.</p>"""
        html += '<table><thead><tr><th>Control #</th><th>File Name</th><th>Custodian</th><th>Status</th><th>Extension</th></tr></thead><tbody>'
        for e in processing['error_docs']:
            html += f"<tr><td>{e['control_number']}</td><td>{e['file_name'] or '—'}</td><td>{e['custodian'] or '—'}</td><td>{e['processing_status']}</td><td>{e['file_extension'] or '—'}</td></tr>"
        html += '</tbody></table>'

    # FOOTER
    html += f"""
<div class="footer">
    Generated by Respondeo v{getattr(config, '__version__', 'N/A')} |
    {overview['generated_at']} |
    This report is computer-generated. Verify all figures against the platform database.
</div>

</body>
</html>"""

    return html


# ═══════════════════════════════════════════════════════════════════════════════
# PDF GENERATION — main entry point
# ═══════════════════════════════════════════════════════════════════════════════

def generate_report(case_folder, case_name, generated_by):
    """
    Main entry point. Collects all data and generates the PDF.
    Returns PDF bytes on success, None on failure.
    """
    try:
        import pdfkit
        import config

        data = {
            'overview': _collect_case_overview(case_folder, case_name, generated_by),
            'ingestion': _collect_ingestion_stats(case_folder),
            'processing': _collect_processing_stats(case_folder),
            'dedup': _collect_dedup_stats(case_folder),
            'review': _collect_review_stats(case_folder),
            'production': _collect_production_stats(case_folder),
            'privilege': _collect_privilege_stats(case_folder),
            'audit': _collect_audit_summary(case_folder),
            'holds': _collect_hold_stats(case_folder),
        }
        data['collection_scope'] = _collect_collection_scope(case_folder)
        data['near_dupe_clusters'] = _collect_near_dupe_clusters(case_folder)

        html = _render_html(data)

        wk_config = pdfkit.configuration(wkhtmltopdf=config.WKHTMLTOPDF_PATH)
        options = {
            'page-size': 'Letter',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': 'UTF-8',
            'no-outline': None,
            'enable-local-file-access': None,
            'footer-center': 'Page [page] of [topage]',
            'footer-font-size': '8',
            'footer-font-name': 'Georgia',
        }

        pdf_bytes = pdfkit.from_string(html, False, options=options, configuration=wk_config)
        return pdf_bytes

    except Exception as e:
        logger.error(f"Defensibility report generation failed: {e}", exc_info=True)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT TRAIL PDF EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

def generate_audit_export_pdf(case_folder, case_name, generated_by, filters, rows):
    """
    Generate a formatted PDF of audit trail entries.

    Args:
        case_folder: path to case folder
        case_name: display name of the case
        generated_by: username/display name of the person generating the report
        filters: dict of applied filters, e.g. {'User': 'All', 'Module': 'All', ...}
        rows: list of dicts, each with keys: timestamp, username, module, action,
              control_number, details, old_value, new_value

    Returns:
        PDF bytes on success, None on failure.
    """
    try:
        import pdfkit
        import config

        generated_at = datetime.now().strftime('%B %d, %Y at %I:%M %p')

        # Build filter summary for header
        filter_lines = []
        for key, val in filters.items():
            if val and val != 'All' and val != 'None':
                filter_lines.append(f"<strong>{key}:</strong> {val}")
        filter_summary = ' &nbsp;|&nbsp; '.join(filter_lines) if filter_lines else 'No filters applied (showing all events)'

        # Build table rows
        table_rows = ''
        for r in rows:
            table_rows += '<tr>'
            table_rows += f"<td style=\"white-space:nowrap;\">{r.get('timestamp', '')}</td>"
            table_rows += f"<td>{r.get('username', '')}</td>"
            table_rows += f"<td>{r.get('module', '')}</td>"
            table_rows += f"<td>{r.get('action', '')}</td>"
            table_rows += f"<td>{r.get('control_number', '')}</td>"
            table_rows += f"<td style=\"max-width:200px;overflow:hidden;text-overflow:ellipsis;\">{r.get('details', '')}</td>"
            table_rows += f"<td>{r.get('old_value', '')}</td>"
            table_rows += f"<td>{r.get('new_value', '')}</td>"
            table_rows += '</tr>'

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: letter landscape;
        margin: 0.6in 0.5in;
    }}
    body {{
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 9pt;
        color: #2d3748;
        line-height: 1.4;
        margin: 0;
        padding: 0;
    }}
    .header {{
        border-bottom: 2px solid #2b6cb0;
        padding-bottom: 10px;
        margin-bottom: 16px;
    }}
    .header h1 {{
        font-size: 18pt;
        color: #1a365d;
        margin: 0 0 4px 0;
    }}
    .header .meta {{
        font-size: 9pt;
        color: #718096;
        margin: 2px 0;
    }}
    .filters {{
        background: #f7fafc;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
        padding: 8px 12px;
        margin-bottom: 16px;
        font-size: 8.5pt;
        color: #4a5568;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 8pt;
        page-break-inside: auto;
    }}
    th {{
        background-color: #ebf8ff;
        color: #1a365d;
        font-weight: 700;
        text-align: left;
        padding: 5px 6px;
        border-bottom: 2px solid #2b6cb0;
        white-space: nowrap;
    }}
    td {{
        padding: 4px 6px;
        border-bottom: 1px solid #e2e8f0;
        vertical-align: top;
    }}
    tr:nth-child(even) td {{
        background-color: #f7fafc;
    }}
    tr {{
        page-break-inside: avoid;
    }}
    thead {{
        display: table-header-group;
    }}
    .footer {{
        font-size: 7pt;
        color: #a0aec0;
        text-align: center;
        margin-top: 20px;
        border-top: 1px solid #e2e8f0;
        padding-top: 6px;
    }}
    .confidential {{
        float: right;
        font-size: 8pt;
        color: #e53e3e;
        font-weight: 700;
        letter-spacing: 1px;
    }}
</style>
</head>
<body>

<div class="header">
    <span class="confidential">PRIVILEGED &amp; CONFIDENTIAL</span>
    <h1>Audit Trail Export &mdash; {case_name}</h1>
    <div class="meta">Generated: {generated_at} &nbsp;|&nbsp; Prepared by: {generated_by} &nbsp;|&nbsp; Platform: Respondeo v{getattr(config, '__version__', 'N/A')}</div>
    <div class="meta">Total events in export: {len(rows):,}</div>
</div>

<div class="filters">
    <strong>Applied Filters:</strong> {filter_summary}
</div>

<table>
<thead>
<tr>
    <th>Timestamp</th>
    <th>User</th>
    <th>Module</th>
    <th>Action</th>
    <th>Control #</th>
    <th>Details</th>
    <th>Old Value</th>
    <th>New Value</th>
</tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>

<div class="footer">
    Generated by Respondeo v{getattr(config, '__version__', 'N/A')} |
    {generated_at} |
    This export reflects the audit trail as of the generation timestamp. The audit log is immutable and append-only.
</div>

</body>
</html>"""

        wk_config = pdfkit.configuration(wkhtmltopdf=config.WKHTMLTOPDF_PATH)
        options = {
            'page-size': 'Letter',
            'orientation': 'Landscape',
            'margin-top': '0.5in',
            'margin-right': '0.4in',
            'margin-bottom': '0.5in',
            'margin-left': '0.4in',
            'encoding': 'UTF-8',
            'no-outline': None,
            'enable-local-file-access': None,
            'footer-center': 'Page [page] of [topage]',
            'footer-font-size': '7',
            'footer-font-name': 'Georgia',
        }

        pdf_bytes = pdfkit.from_string(html, False, options=options, configuration=wk_config)
        return pdf_bytes

    except Exception as e:
        logger.error(f"Audit trail PDF export failed: {e}", exc_info=True)
        return None
