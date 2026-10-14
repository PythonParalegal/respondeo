# Sprint: Document Trim Feature (`trim_document()`)

> **Context:** Example: DOC-001000 is a 120-page batch-scanned paper file where scattered pages (bank records) need to be removed as non-responsive. The split feature creates multiple children from defined ranges — but trim produces a **single** child with specified pages removed. Same defensibility pattern: original preserved, source hidden, child goes through pipeline.

## Why This Is Different From Split

| | Split | Trim |
|---|---|---|
| **Input** | List of page ranges to **keep** (each becomes a child) | List of pages to **remove** |
| **Output** | Multiple children (one per range) | Single child (one document minus removed pages) |
| **Use case** | Separating distinct documents scanned together | Removing irrelevant/non-responsive pages from one document |
| **Min children** | 2 (splitting into 1 is a no-op) | 1 (always produces exactly 1) |

Both use the same underlying pattern: `Split_Source` status on the original, `split_source_cn` on the child, original PDF untouched on disk, new PDF in `Split/`, child starts at `New` for Processor.

---

## What Gets Added

| Component | File | What Gets Added |
|-----------|------|-----------------|
| Backend trim logic | `db_manager.py` | `trim_document()` function |
| UI | `4_Review.py` | "Trim Pages" option inside the existing "✂️ Split" tab |

No new schema migration needed — reuses `split_source_cn` from the split feature.

---

## Backend Function: `trim_document()` (db_manager.py)

Place immediately after `split_document()`.

```python
def trim_document(case_folder, source_cn, pages_to_remove, username, new_file_name=None):
    """
    Remove specified pages from a document, creating a single trimmed child.
    Original document is preserved and hidden (Split_Source).

    Args:
        case_folder: Path to the active case folder
        source_cn: Control number of the source document
        pages_to_remove: List of 0-based page indices to remove
        username: Username performing the trim
        new_file_name: Optional display name for the trimmed doc.
                       Defaults to f"{original_name} (trimmed).pdf"

    Returns:
        dict with:
            - new_document: dict with {control_number, file_name, page_count, full_path}
            - pages_removed: list of 0-based page indices that were removed
            - source_cn: the source document's control number
            - error: None on success, error string on failure
    """
```

### Function Logic

1. **Validate source document** (same checks as `split_document()`):
   - Exists, is PDF, not already `Split_Source`, no Bates numbers (`begdoc` is NULL/empty), file exists on disk

2. **Validate pages_to_remove:**
   - Open source PDF with `fitz.open()` to get page count
   - Check all page indices are within range `[0, page_count - 1]`
   - Check that at least 1 page is being removed
   - Check that at least 1 page will survive (can't remove ALL pages)
   - Deduplicate and sort the removal list

3. **Compute surviving pages:**
   ```python
   all_pages = set(range(source_doc.page_count))
   remove_set = set(pages_to_remove)
   surviving_pages = sorted(all_pages - remove_set)
   ```

4. **Create trimmed PDF:**
   ```python
   new_doc = fitz.open()  # empty document
   for page_num in surviving_pages:
       new_doc.insert_pdf(source_doc, from_page=page_num, to_page=page_num)
   ```

   This preserves all page content including any PDF annotations on surviving pages.

5. **Insert new document row** (same pattern as `split_document()`):
   ```python
   cur = conn.cursor()
   cur.execute("""
       INSERT INTO documents (
           file_name, file_extension, full_path, original_path,
           file_size_kb, processing_status, custodian, volume,
           record_type, split_source_cn, md5_hash
       ) VALUES (?, ?, ?, ?, ?, 'New', ?, ?, ?, ?, ?)
   """, (
       new_file_name or f"{source_file_name} (trimmed).pdf",
       '.pdf', '',  # full_path placeholder, updated after save
       f"Trimmed from {source_cn} — removed pages {pages_to_remove}",
       0,  # placeholder, updated after save
       source_row['custodian'], source_row['volume'],
       'Document', source_cn, ''  # md5 placeholder
   ))
   new_id = cur.lastrowid
   new_cn = f"DOC-{new_id:06d}"
   ```

6. **Set CN, save PDF, update row** (same ordering as `split_document()`):
   ```python
   split_dir = os.path.join(case_folder, 'Split')
   os.makedirs(split_dir, exist_ok=True)
   split_pdf_path = os.path.join(split_dir, f"{new_cn}.pdf")
   new_doc.save(split_pdf_path)
   new_doc.close()

   # Compute actual file size and md5
   file_size_kb = round(os.path.getsize(split_pdf_path) / 1024, 2)
   md5_hash = compute_md5(split_pdf_path)

   cur.execute("""
       UPDATE documents
       SET control_number = ?, group_id = ?, full_path = ?,
           file_size_kb = ?, md5_hash = ?
       WHERE id = ?
   """, (new_cn, new_cn, split_pdf_path, file_size_kb, md5_hash, new_id))
   ```

7. **Migrate redaction marks with page renumbering:**

   This is the key difference from split. When pages are removed, surviving pages shift down. Build a mapping:

   ```python
   # Build old_page → new_page mapping for surviving pages
   page_remap = {}
   new_idx = 0
   for old_idx in range(source_page_count):
       if old_idx not in remove_set:
           page_remap[old_idx] = new_idx
           new_idx += 1

   # Migrate marks for surviving pages
   all_marks = conn.execute(
       "SELECT page_number, marks_json, created_by FROM redaction_marks WHERE control_number = ?",
       (source_cn,)
   ).fetchall()

   has_marks = False
   for mark_row in all_marks:
       old_page = mark_row['page_number']
       if old_page in page_remap:
           new_page = page_remap[old_page]
           conn.execute(
               "INSERT OR REPLACE INTO redaction_marks (control_number, page_number, marks_json, created_by) VALUES (?, ?, ?, ?)",
               (new_cn, new_page, mark_row['marks_json'], mark_row['created_by'] or username)
           )
           has_marks = True
       # Pages being removed: their marks are simply not migrated

   if has_marks:
       conn.execute(
           "UPDATE documents SET redaction_status = 'Has_Redactions' WHERE control_number = ?",
           (new_cn,)
       )
   ```

8. **Mark source as Split_Source and clean up** (same as `split_document()`):
   ```python
   conn.execute(
       "UPDATE documents SET processing_status = 'Split_Source' WHERE control_number = ?",
       (source_cn,)
   )
   conn.execute(
       "DELETE FROM redaction_marks WHERE control_number = ?",
       (source_cn,)
   )
   conn.commit()
   ```

9. **Audit log:**
   ```python
   audit_rows = [
       {
           "action": "DOCUMENT_TRIM_CHILD",
           "username": username,
           "control_number": new_cn,
           "module": "Review",
           "details": json.dumps({
               "source_cn": source_cn,
               "pages_removed": pages_to_remove,
               "pages_kept": surviving_pages,
               "original_page_count": source_page_count,
               "new_page_count": len(surviving_pages)
           }),
           "old_value": None,
           "new_value": "New"
       },
       {
           "action": "DOCUMENT_TRIM_SOURCE",
           "username": username,
           "control_number": source_cn,
           "module": "Review",
           "details": json.dumps({
               "child_cn": new_cn,
               "pages_removed": pages_to_remove
           }),
           "old_value": source_row['processing_status'],
           "new_value": "Split_Source"
       }
   ]
   log_audit_batch(case_folder, audit_rows)
   ```

10. **Close source PDF handle** in `finally` block.

### Error Handling

Same as `split_document()`: try/except wrapping entire operation, rollback on failure, clean up any written PDFs, try/finally on all `fitz.open()` calls.

---

## UI: Add Trim Mode to Split Tab (4_Review.py)

Inside the existing "✂️ Split" tab, add a toggle or sub-section:

```python
_split_mode = st.radio(
    "Mode",
    ["✂️ Split into ranges", "🔪 Trim pages"],
    key=f"_split_mode_{current_cn}",
    horizontal=True
)
```

### Trim Mode UI

When "Trim pages" is selected:

1. **Page count display:** "This document has N pages"

2. **Pages to remove input:** A text area where the user enters page numbers/ranges in human-readable format (1-based):
   ```
   Example: 3-4, 8, 20-24
   ```

   Parse this into a list of 0-based page indices. Support both individual pages and ranges with `-`.

3. **Validation display:**
   - Total pages to remove vs total pages
   - Pages that will survive (show count)
   - Warn if removing more than 50% of pages
   - Block if removing ALL pages

4. **"🔪 Trim Document" button** (type="primary"):
   - Disabled until valid input
   - Requires confirmation: `st.warning(f"This will remove {len(pages)} pages and create a new {surviving} page document. The original will be preserved but hidden. Continue?")`
   - On confirm, calls `db_manager.trim_document()`

5. **Post-trim behavior:** Same as post-split — success message with new CN, "Go to Processor" button, clear selection, rerun.

### Page Range Parser

```python
def parse_page_ranges(text, max_page):
    """
    Parse human-readable page ranges (1-based) into 0-based page indices.
    Input: "3-4, 8, 20-24"
    Output: [2, 3, 7, 19, 20, ..., 23]
    """
    pages = set()
    for part in text.replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start, end = part.split('-', 1)
            start, end = int(start.strip()), int(end.strip())
            pages.update(range(start - 1, end))  # Convert 1-based to 0-based
        else:
            pages.add(int(part.strip()) - 1)  # Convert 1-based to 0-based

    # Validate
    invalid = [p for p in pages if p < 0 or p >= max_page]
    if invalid:
        raise ValueError(f"Page numbers out of range: {[p+1 for p in invalid]}")

    return sorted(pages)
```

---

## Module Metadata Updates

### db_manager.py header
Bump `version` (minor bump — new function). Current version is whatever it is after the split sprint.

### 4_Review.py header
Bump `version` (minor bump — trim mode in split tab).

### CHANGELOG.md
```
- NEW: db_manager.py — `trim_document()` function: removes specified pages from a PDF, creating single trimmed child with page-renumbered redaction mark migration
- NEW: 4_Review.py — "Trim pages" mode in Split tab: page range input, validation, single-child trim workflow
```

---

## What NOT To Do

- Do NOT modify the source PDF on disk. It is preserved for defensibility.
- Do NOT reuse the source control number for the trimmed document. It gets a new CN.
- Do NOT forget page renumbering for redaction marks. When pages are removed, all subsequent page numbers shift down.
- Do NOT create multiple children from a trim operation. Trim always produces exactly one child.
- Do NOT use `doc.delete_pages()` on the source — build a new document from surviving pages using `insert_pdf()`.

---

## Testing Checklist

1. **Basic trim:** Remove pages 5-6 from a 10-page doc. Confirm:
   - New 8-page document created with correct content
   - Source marked `Split_Source` and hidden from review grid
   - Original PDF untouched on disk

2. **Redaction mark migration:** Trim a document with marks on pages 3, 5, 8 (0-based). Remove page 4. Confirm:
   - Page 3 mark → stays page 3 on child
   - Page 5 mark → becomes page 4 on child (shifted down by 1)
   - Page 8 mark → becomes page 7 on child (shifted down by 1)
   - No mark for removed page 4

3. **DOC-001000 test case:** Remove pages 3-4, 8, 20-24 (1-based) from a 120-page document. Confirm the new document has 112 pages (120 minus the 8 removed) and the right content.

4. **Guard rails:** Try removing all pages → blocked. Try removing 0 pages → blocked. Try page numbers out of range → error message.
