# Privilege Log — Per-Page Bates Calculation Fix

**Date:** 2026-04-01
**Priority:** HIGH — Privilege log Bates column shows page offsets instead of actual Bates numbers
**Branch:** `beta-2.9`
**Files affected:** `5_Production.py`

---

## Problem

The Bates Range column currently shows: `ABC-000200 (redacted pp. 5)`

This tells you a page number offset but not the actual Bates number. For TIFF productions (each page = separate file with its own Bates), page offsets are meaningless to opposing counsel. The privilege log needs to show: `ABC-000204` (the actual Bates stamp on page 5).

For multi-page redactions, show each redacted page's Bates number: `ABC-000204, ABC-000206`

---

## Fix

Replace the current `_pl_format_bates()` function (or wherever Bates Range is computed) with proper per-page Bates number calculation.

### Bates number math

```python
import re

def _pl_compute_page_bates(begdoc, page_number):
    """
    Given begdoc like 'ABC-000200' and a 1-based page number,
    return the Bates number for that page.
    Page 1 = begdoc itself, page 2 = begdoc+1, etc.
    """
    if not begdoc or begdoc == '(not yet produced)':
        return None
    match = re.match(r'^([A-Za-z]+-?)(\d+)$', begdoc)
    if not match:
        return begdoc  # can't parse, return as-is
    prefix, num_str = match.groups()
    base_num = int(num_str)
    padding = len(num_str)
    page_bates_num = base_num + (page_number - 1)
    return f"{prefix}{str(page_bates_num).zfill(padding)}"
```

### Updated Bates Range formatting

```python
def _pl_format_bates(row):
    """
    Disposition-aware Bates formatting:
    - Withhold: single Bates number (slip sheet = 1 page)
    - Redact: list the actual Bates numbers of redacted pages
    - Needs Disposition: begdoc or "(not yet produced)"
    """
    begdoc = row.get('begdoc', '')
    disp_key = row.get('_disposition_key', '')

    if not begdoc or begdoc == '(not yet produced)':
        redacted_pages = row.get('redacted_pages_list', '')
        if redacted_pages and disp_key == 'Redact':
            page_count = len(str(redacted_pages).split(','))
            return f"(not yet produced — {page_count} pages redacted)"
        return '(not yet produced)'

    if disp_key == 'Withhold':
        # Slip sheet = single page, single Bates
        return begdoc

    if disp_key == 'Redact':
        # Compute actual Bates numbers for each redacted page
        redacted_pages_str = row.get('redacted_pages_list', '')
        if redacted_pages_str:
            page_nums = sorted(set(
                int(p.strip()) for p in str(redacted_pages_str).split(',')
                if p.strip().isdigit()
            ))
            bates_numbers = []
            for pg in page_nums:
                page_bates = _pl_compute_page_bates(begdoc, pg)
                if page_bates:
                    bates_numbers.append(page_bates)
            if bates_numbers:
                return ', '.join(bates_numbers)
        # Fallback: just show begdoc if no page info
        return begdoc

    # Needs Disposition or unknown
    return begdoc
```

### Important note on page numbering

The `redacted_pages_list` from the SQL query contains page numbers from `redaction_marks.page_number`. Verify whether these are **0-based** (as stored in the redaction canvas) or **1-based**. If 0-based, the formula needs `page_number` instead of `page_number - 1`:

```python
# If redaction_marks.page_number is 0-based:
page_bates_num = base_num + page_number  # page 0 = begdoc, page 1 = begdoc+1

# If redaction_marks.page_number is 1-based:
page_bates_num = base_num + (page_number - 1)  # page 1 = begdoc, page 2 = begdoc+1
```

**Check the redaction_marks table to confirm.** The redaction canvas in Review typically uses 0-based page indices (matching PyMuPDF's 0-based page numbers). If so, the formula is:

```python
page_bates_num = base_num + page_number  # 0-based: page 0 → begdoc, page 4 → begdoc+4
```

---

## CHANGELOG

```
- FIX: 5_Production.py — Privilege Log Bates Range shows actual per-page Bates numbers (e.g., "ABC-000204") instead of page offsets (e.g., "ABC-000200 (redacted pp. 5)")
```

---

## Testing

```
[ ] Redact doc with begdoc ABC-000200, redaction on page 5 → shows "ABC-000204" (if 0-based) or "ABC-000205" (if 1-based)
[ ] Redact doc with multiple redacted pages → shows comma-separated Bates numbers
[ ] Withhold doc → shows single Bates number (begdoc only)
[ ] Not-yet-produced doc → shows "(not yet produced)"
[ ] Export CSV/Excel Bates column matches preview
[ ] Verify against actual production output: open the produced TIFF/PDF for page 5 and confirm its Bates stamp matches the privilege log value
```
