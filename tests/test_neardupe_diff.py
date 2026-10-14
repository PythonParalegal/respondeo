"""
Regression tests for the pure side-by-side diff helper (beta-2.16 C8b / S-1b).

`neardupe_diff.build_side_by_side_diff_html` is pure (no Streamlit / OpenSearch),
so it unit-tests directly. It backs the Review → Near-Dupe Clusters diff pane:
LINE-based rows with difflib's intra-line character highlighting, so a single
changed token (invoice #, date, amount — the Flag #22 case) shows highlighted in
its surrounding context line.

Assertion notes:
  - The helper prepends a CSS block that defines `.diff_add/.diff_chg/.diff_sub`,
    so a bare `"diff_add" in html` substring check is meaningless. Change markup
    is asserted via the TABLE usage `class="diff_*"` instead.
  - difflib.HtmlDiff does NOT emit a literal "..." collapse marker; context-mode
    collapse is asserted by a far-from-change line being OMITTED in context mode
    but PRESENT in full mode.
"""
from neardupe_diff import build_side_by_side_diff_html

_CHANGE_CLASSES = ('class="diff_add"', 'class="diff_chg"', 'class="diff_sub"')


def test_diff_marks_changes_in_context():
    a = "Invoice INV-1041 Amount 4200"
    b = "Invoice INV-1042 Amount 3750"
    html = build_side_by_side_diff_html(a, b)
    assert isinstance(html, str)
    assert "table" in html.lower()
    assert "#ffffff" in html                       # forced white background (theme-safe)
    assert any(c in html for c in _CHANGE_CLASSES)  # the change is highlighted
    assert "Invoice" in html and "Amount" in html   # unchanged context renders intact


def test_diff_identical_has_no_change_markers():
    html = build_side_by_side_diff_html("same line here\nsecond line", "same line here\nsecond line")
    assert not any(c in html for c in _CHANGE_CLASSES)  # nothing highlighted


def test_diff_context_mode_collapses_unchanged():
    # A change (ALPHA→BETA) buried in long identical runs, with FARTOKEN far from
    # it. context=True must collapse the far region away.
    a = "\n".join([f"line {i}" for i in range(40)] + ["ALPHA"] + [f"tail {i}" for i in range(40)] + ["FARTOKEN"])
    b = "\n".join([f"line {i}" for i in range(40)] + ["BETA"] + [f"tail {i}" for i in range(40)] + ["FARTOKEN"])
    html = build_side_by_side_diff_html(a, b, context=True, numlines=2)
    assert "ALPHA" in html and "BETA" in html      # the change hunk is shown
    assert "FARTOKEN" not in html                  # collapsed away (far from change)


def test_diff_full_mode_renders_all_text():
    a = "\n".join([f"line {i}" for i in range(40)] + ["ALPHA"] + [f"tail {i}" for i in range(40)] + ["FARTOKEN"])
    b = "\n".join([f"line {i}" for i in range(40)] + ["BETA"] + [f"tail {i}" for i in range(40)] + ["FARTOKEN"])
    html = build_side_by_side_diff_html(a, b, context=False)
    assert "ALPHA" in html and "BETA" in html
    assert "FARTOKEN" in html                       # full mode renders everything


def test_diff_empty_inputs_return_blank():
    # Image-only docs (no extracted text) → "" so the caller shows a "no text"
    # notice instead of a misleading "No Differences Found" table.
    assert build_side_by_side_diff_html("", "") == ""
    assert build_side_by_side_diff_html("   ", "\n\n") == ""
