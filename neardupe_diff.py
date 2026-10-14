# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        neardupe_diff.py
# version:       1.0.0
# project:       Respondeo eDiscovery Platform
# project_ver:   2.16.0
# last_modified: 2026-06-01 12:00
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
"""Pure helpers for the near-dupe cluster-review diff pane (S-1b C8b).

No Streamlit or OpenSearch dependencies — kept pure for unit testing. The Review
tab fetches document text (via os_manager.get_document_content) and feeds it here
for rendering. The Review page caches the rendered HTML with @st.cache_data on a
thin call-site wrapper; this module stays uncached so it remains trivially
testable (spec §1.4).

Rendering is LINE-based (rows = lines), not word-based: difflib.HtmlDiff already
highlights changed characters *within* each line, so a single changed token
(invoice #, date, amount — the Flag #22 case) shows highlighted in its
surrounding context line rather than as an isolated one-word row. make_table()
emits no <style>, so we prepend our own CSS with a forced white background, dark
text, and colored change highlights (works on any Streamlit theme — the diff
renders inside a components.html iframe).
"""
import difflib
import re

# difflib.HtmlDiff.make_table emits fragment-only nav anchors
# (<a href="#difflib_chg_…">n/t</a>) whose targets only exist in make_file()'s
# wrapper. Inside a components.html iframe they resolve to "/" and load the whole
# app into the diff pane ("turtles all the way down"). Strip them entirely — the
# "n"/"t" glyphs are difflib-internal nav cruft with no value to our reviewers.
_ANCHOR_RE = re.compile(r'<a href="#difflib_chg_[^"]*">.*?</a>')

# White-background, theme-independent diff styling injected ahead of the table
# (difflib's make_table emits the diff_add/diff_chg/diff_sub CLASSES but no CSS).
_DIFF_CSS = """
<style>
  .nd-diff-wrap { background:#ffffff; color:#1f2937; padding:10px 12px;
                  border-radius:6px; box-sizing:border-box; }
  table.diff { width:100%; border-collapse:collapse;
               font-family:ui-monospace, "Cascadia Code", Consolas, monospace;
               font-size:0.82rem; line-height:1.45; }
  /* difflib emits 6 columns: [nav][lineno][content] x2. The nav columns are empty
     (their anchors were stripped) — hide them so the content gets the width. */
  table.diff th.diff_next, table.diff td.diff_next { display:none; }
  table.diff td, table.diff th { padding:2px 8px; vertical-align:top;
               white-space:pre-wrap !important;   /* override difflib's nowrap attr */
               word-break:break-word; overflow-wrap:anywhere; }
  table.diff th { background:#e2e8f0; color:#0f172a; font-weight:700;
               position:sticky; top:0; z-index:1; }
  /* line-number columns shrink to content; content columns split the rest 50/50 */
  table.diff td.diff_header { color:#94a3b8; text-align:right; padding-right:10px;
               width:1%; white-space:nowrap !important; user-select:none; background:#f8fafc; }
  table.diff td[nowrap] { width:49%; }
  .diff_add { background:#bbf7d0; }   /* member-side addition  — green  */
  .diff_chg { background:#fde68a; }   /* in-place change       — amber  */
  .diff_sub { background:#fecaca; }   /* principal-side removal — red    */
</style>
"""


def build_side_by_side_diff_html(
    principal_text: str,
    member_text: str,
    *,
    context: bool = True,
    numlines: int = 4,
) -> str:
    """Return an HTML side-by-side diff table (principal | member) with changed
    text highlighted IN CONTEXT (changed characters highlighted within their
    surrounding line). Returns "" when both inputs are empty/whitespace (e.g. an
    image-only document with no extracted text), so the caller can show a
    "no text to diff" notice rather than a misleading "No Differences Found".

    Args:
        principal_text: the principal document's extracted text.
        member_text: the member document's extracted text being compared.
        context: when True (default), collapse unchanged stretches with `numlines`
            of surrounding context around each change hunk (keeps long documents
            tractable). When False, the full text renders with change highlights
            only (drives the §11.3 "Show full text" toggle and Expand modal).
        numlines: lines of context around each change hunk when `context=True`.

    Returns:
        An HTML string (CSS + wrapped `<table>`), or "" when there is nothing to diff.
    """
    if not (principal_text or "").strip() and not (member_text or "").strip():
        return ""
    a = (principal_text or "").splitlines() or [""]
    b = (member_text or "").splitlines() or [""]
    differ = difflib.HtmlDiff(wrapcolumn=80)
    table = differ.make_table(
        a, b,
        fromdesc="Principal", todesc="Member",
        context=context, numlines=numlines,
    )
    table = _ANCHOR_RE.sub("", table)  # strip the iframe-breaking nav anchors
    return _DIFF_CSS + f'<div class="nd-diff-wrap">{table}</div>'
