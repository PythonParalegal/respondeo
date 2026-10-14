# Sprint: Document Split Feature

> **Audit status:** Spec reviewed against live codebase on 2026-03-30. Corrections marked with `[AUDIT CORRECTION]`. Original spec by Browser Claude; audit by Cowork Claude. Permission decision by the maintainer on 2026-03-30.

## Context

Law firms frequently receive hard-copy document collections that were batch-scanned — a letter, an invoice, and a check all scanned into a single PDF. These need to be separated into individual documents, each with its own control number, independent review decisions, and independent Bates ranges at production.

This sprint adds a **Document Split** capability: a UI in the Review module and backend functions in `db_manager.py` that take a multi-document PDF, let the user define page ranges, and create new independent documents in the database ready to flow through the normal pipeline (Processor → Review → Production).

**This is a permanent platform feature — full module metadata headers, CHANGELOG entries, CLAUDE.md/MEMORY.md updates, and standing orders apply.**

---

## How Control Numbers Work (Critical Background)

Control number generation is NOT in the database (no triggers, no DEFAULT). It happens in application code:

1. `1_Ingestor.py` inserts documents WITHOUT a `control_number` (left NULL). The row gets an auto-increment `id`. The INSERT uses these columns only: `file_name, original_path, full_path, file_extension, file_size_kb, md5_hash, processing_status, custodian, tags, source_collection, source_subcollection`.
2. `2_Processor.py` Phase 2 generates the CN from the row's `id`: `control_number = f"DOC-{doc_id_int:06d}"` (line 981).
3. The Processor writes it back via UPDATE at the same time as text extraction/metadata.
4. Duplicates get `DUPE-{id:06d}` prefix instead.
5. `[AUDIT CORRECTION]` Container children get a **dot-notation temp CN** at INSERT time: `f"DOC-{parent_id:06d}.{i+1:03d}"` (e.g., `DOC-000007.001`). The Processor later overwrites this with the flat `DOC-{id:06d}`. Split children should NOT use dot-notation — they get the flat `DOC-{id:06d}` directly at insert time.

**Implication for split documents:** Insert the row → read `lastrowid` → immediately set `control_number = f"DOC-{lastrowid:06d}"`. When the Processor later processes the document (status `New`), it derives the same CN from the same `id` — no conflict. We need the CN at split time for redaction mark migration.

---

## Architecture Overview

### Data Flow

```
Source document (DOC-000007, 12 pages, batch scan)
    ↓ User defines: pages 1-4 = "Insurance Bill", pages 5-12 = "Bank Statement"
    ↓
    ├── New PDF: Split/{DOC-002700}.pdf (pages 1-4)  →  New DB row (id=2700, CN=DOC-002700)
    ├── New PDF: Split/{DOC-002701}.pdf (pages 5-12)  →  New DB row (id=2701, CN=DOC-002701)
    └── Source DOC-000007: processing_status → 'Split_Source'
    ↓
    User runs Processor (Module 2) on new documents
    ↓
    Processor: text extraction, metadata, moves to Processed/, sets status='Master'
    ↓
    New documents appear in Review grid as independent documents
```

### What Goes Where

| Component | File | What Gets Added |
|-----------|------|-----------------|
| Permission registration | `auth_manager.py` | `split_document` permission added to `ALL_PERMISSIONS` + manager defaults |
| Backend split logic | `db_manager.py` | `split_document()` function + `split_source_cn` migration |
| UI | `4_Review.py` | New "✂️ Split" tab in the document viewer |
| Schema migration | `db_manager.py` `init_db()` | `ALTER TABLE documents ADD COLUMN split_source_cn TEXT` |

---

## Step 0: Register `split_document` Permission (auth_manager.py)

**This step must be completed before Step 4.** Splitting is a structural operation on the document inventory — it creates and destroys reviewable documents. This is a manager-level action, not a reviewer action. An attorney can review and redact, but should not be splitting documents.

`auth_manager.py` uses a role-based permission system. Three places need updating:

### 0a. Add to `ALL_PERMISSIONS` list (~lines 51-66)

This is the authoritative registry of valid permission names. `save_role_permissions()` validates against this list, so the permission must be registered here first.

```python
ALL_PERMISSIONS = [
    # ... existing entries ...
    'split_document',          # ← ADD — structural: split batch-scanned PDFs into independent documents
]
```

### 0b. Add to `_DEFAULT_PERMISSIONS` for the `manager` role (~lines 29-48)

```python
_DEFAULT_PERMISSIONS: dict[str, set] = {
    'admin': {'*'},            # Wildcard — already gets everything
    'manager': {
        # ... existing entries ...
        'split_document',      # ← ADD
    },
    'reviewer': {
        # ... existing entries ...
        # Do NOT add split_document here — reviewers should not split documents
    },
}
```

### 0c. If `auth_config.yaml` exists for the active case

The YAML config's `role_permissions` section also needs the new permission added to the manager role. If no YAML exists, the `_DEFAULT_PERMISSIONS` fallback covers it. Check whether the active case uses YAML config — if so, add `split_document` to the manager's permission list there too.

### Module metadata

Bump `auth_manager.py` version (minor bump — new permission), update `last_modified`, `modified_by`.

### CHANGELOG entry

```
- NEW: auth_manager.py — `split_document` permission: manager-only gate for document splitting (not tied to `redact`)
```

### Access gate annotation

When using this permission in `4_Review.py`, annotate per the project convention:
```python
# permission: split_document
_can_split = auth_manager.has_permission('split_document')
```

---

## Step 1: Schema Migration (db_manager.py)

Add to the `migrations` list in `init_db()` (around line 185-236), which is a list of `(col_name, col_type)` tuples iterated with the standard try/except pattern:

```python
# In the migrations list (near the end, after the last existing entry):
("split_source_cn", "TEXT"),           # Lineage tracking for split documents
```

`[AUDIT CORRECTION]` The original spec showed a standalone try/except block. The actual `init_db()` uses a **list-based batch pattern** — a `migrations` list of tuples iterated in a for loop. Add the new column to that list, don't create a standalone block:

```python
# Existing pattern (lines ~185-241 of db_manager.py):
migrations = [
    ("analytics_run_date", "TEXT"),
    ("begdoc", "TEXT"),
    # ... 30+ existing entries ...
    ("source_collection", "TEXT"),
    ("source_subcollection", "TEXT"),
    ("split_source_cn", "TEXT"),        # ← ADD HERE
]
for col_name, col_type in migrations:
    try:
        cursor.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}")
    except sqlite3.OperationalError:
        pass  # Column already exists
```

**Purpose:** `split_source_cn` on a child document stores the control number of the original batch-scanned document it was split from. This is for defensibility audit trail only — NOT for family relationships. Do NOT use `parent_id` or `group_id` for this.

---

## Step 2: Backend Function (db_manager.py)

`[AUDIT CORRECTION]` **New pattern alert:** As of this sprint, **no function in db_manager.py performs INSERT INTO the `documents` table.** All existing document functions are SELECT/UPDATE only. Document insertion currently happens in `1_Ingestor.py` (line 407) and `2_Processor.py` (line 336 for container children). Adding `split_document()` here is consistent with the M-4 migration direction of centralizing SQL into db_manager.py, but Claude Code should know it's establishing a new pattern, not following an existing one.

Add a new function `split_document()`. Place it near the document CRUD functions (after `get_document_children` at ~line 2556).

```python
def split_document(case_folder, source_cn, splits, username):
    """
    Split a multi-page PDF document into multiple independent documents.

    Args:
        case_folder: Path to the active case folder
        source_cn: Control number of the source document to split
        splits: List of dicts, each with:
            - page_start (int): 0-based start page index (inclusive)
            - page_end (int): 0-based end page index (inclusive)
            - file_name (str): Display name for the new document (e.g. "Insurance Bill.pdf")
        username: Username performing the split

    Returns:
        dict with:
            - new_documents: list of dicts with {control_number, file_name, page_range, full_path}
            - source_cn: the source document's control number
            - error: None on success, error string on failure

    Raises:
        ValueError: if source document not found, not a PDF, already produced, or page ranges invalid
    """
```

### Function Logic:

1. **Validate source document:**
   - Query `SELECT * FROM documents WHERE control_number = ?` for the source
   - Reject if not found
   - Reject if `processing_status` is `Split_Source` (already split)
   - Reject if `begdoc IS NOT NULL AND begdoc != ''` (already produced — can't split after Bates assignment)
   - Reject if `full_path` doesn't end with `.pdf` (only PDF splitting supported)
   - Reject if file doesn't exist on disk

2. **Validate splits:**
   - Open source PDF with `fitz.open()` to get page count
   - Check that every split's `page_start` and `page_end` are within range `[0, page_count - 1]`
   - Check that `page_start <= page_end` for each split
   - Check that page ranges don't overlap (sort by page_start, check each end < next start)
   - Check that splits cover ALL pages of the source document (warn if gaps, but don't block — some pages might genuinely be blank separators the user wants to discard)
   - Require at least 2 splits (splitting into 1 document is a no-op)

3. **Create Split/ staging directory:**
   ```python
   split_dir = os.path.join(case_folder, 'Split')
   os.makedirs(split_dir, exist_ok=True)
   ```

4. **For each split range, in a single transaction:**

   a. Extract pages into a new PDF:
   ```python
   new_doc = fitz.open()  # empty document
   new_doc.insert_pdf(source_doc, from_page=split['page_start'], to_page=split['page_end'])
   ```

   b. Insert the new document row (WITHOUT control_number — let the id auto-assign):
   ```python
   cur = conn.cursor()
   cur.execute("""
       INSERT INTO documents (
           file_name, file_extension, full_path, original_path,
           file_size_kb, processing_status, custodian, volume,
           record_type, split_source_cn, md5_hash
       ) VALUES (?, ?, ?, ?, ?, 'New', ?, ?, ?, ?, ?)
   """, (
       split['file_name'], '.pdf', split_pdf_path, f"Split from {source_cn}",
       round(os.path.getsize(split_pdf_path) / 1024, 2),
       source_row['custodian'], source_row['volume'],
       'Document',  # record_type — always 'Document' for split children
       source_cn,
       md5_hash_of_new_pdf
   ))
   new_id = cur.lastrowid
   new_cn = f"DOC-{new_id:06d}"
   ```

   c. Immediately set the control number and group_id:
   ```python
   cur.execute(
       "UPDATE documents SET control_number = ?, group_id = ? WHERE id = ?",
       (new_cn, new_cn, new_id)
   )
   ```

   `[AUDIT CORRECTION]` **Why `group_id = new_cn`:** Split children are independent documents — each is its own family head. This is intentionally different from container explosion, where children get `group_id = parent_cn` to form a family. Do NOT set `group_id` to `source_cn`.

   d. Save the new PDF using the control number as filename:
   ```python
   split_pdf_path = os.path.join(split_dir, f"{new_cn}.pdf")
   new_doc.save(split_pdf_path)
   new_doc.close()
   # Update full_path to the saved location
   cur.execute("UPDATE documents SET full_path = ? WHERE id = ?", (split_pdf_path, new_id))
   ```

   **Important ordering note:** You need the `new_id` before you can compute the path and save. So the actual sequence is:
   - INSERT the row (gets `lastrowid`)
   - Compute `new_cn` and `split_pdf_path`
   - Save the PDF to `split_pdf_path`
   - Compute `file_size_kb` and `md5_hash` from the saved file
   - UPDATE the row with `control_number`, `group_id`, `full_path`, `file_size_kb`, `md5_hash`

   For the INSERT, use placeholder values for `file_size_kb` and `md5_hash` (0 and '' respectively), then UPDATE them after saving.

   e. Migrate redaction marks for pages in this range:
   ```python
   # Get existing marks for source document that fall in this split's page range
   existing_marks = conn.execute(
       "SELECT page_number, marks_json, created_by FROM redaction_marks WHERE control_number = ? AND page_number >= ? AND page_number <= ?",
       (source_cn, split['page_start'], split['page_end'])
   ).fetchall()

   for mark_row in existing_marks:
       # Adjust page number: subtract the split's start offset
       new_page_num = mark_row['page_number'] - split['page_start']
       conn.execute(
           "INSERT OR REPLACE INTO redaction_marks (control_number, page_number, marks_json, created_by) VALUES (?, ?, ?, ?)",
           (new_cn, new_page_num, mark_row['marks_json'], mark_row['created_by'] or username)
       )
   ```

   f. Set redaction_status on the new document if it has marks:
   ```python
   if existing_marks:
       conn.execute(
           "UPDATE documents SET redaction_status = 'Has_Redactions' WHERE control_number = ?",
           (new_cn,)
       )
   ```

5. **Mark source document as Split_Source:**
   ```python
   conn.execute(
       "UPDATE documents SET processing_status = 'Split_Source' WHERE control_number = ?",
       (source_cn,)
   )
   ```

6. **Delete source document's redaction marks** (they've been migrated to children):
   ```python
   conn.execute(
       "DELETE FROM redaction_marks WHERE control_number = ?",
       (source_cn,)
   )
   ```

7. **Commit the transaction and audit log:**
   ```python
   conn.commit()

   # Audit: one entry per new document + one for the source
   audit_rows = []
   for new_doc_info in new_documents:
       audit_rows.append({
           "action": "DOCUMENT_SPLIT_CHILD",
           "username": username,
           "control_number": new_doc_info['control_number'],
           "module": "Review",
           "details": json.dumps({
               "source_cn": source_cn,
               "page_start": new_doc_info['page_start'],
               "page_end": new_doc_info['page_end'],
               "file_name": new_doc_info['file_name']
           }),
           "old_value": None,
           "new_value": "New"
       })
   audit_rows.append({
       "action": "DOCUMENT_SPLIT_SOURCE",
       "username": username,
       "control_number": source_cn,
       "module": "Review",
       "details": json.dumps({
           "child_cns": [d['control_number'] for d in new_documents],
           "child_count": len(new_documents)
       }),
       "old_value": source_row['processing_status'],
       "new_value": "Split_Source"
   })
   log_audit_batch(case_folder, audit_rows)
   ```

   `[AUDIT NOTE]` `log_audit_batch()` (lines 715-747 of db_manager.py) accepts exactly these dict keys: `action, username, control_number, module, details, old_value, new_value`. It uses `executemany` with named placeholders. It is a "never-raise" function (wrapped in try/except pass). Verified.

8. **Close the source PDF handle** in a `finally` block.

### Error Handling

Wrap the entire operation in a try/except. If ANY step fails:
- Rollback the database transaction
- Clean up any PDFs already written to `Split/` for this operation
- Return the error string

Use `try/finally` on all `fitz.open()` calls to prevent file handle leaks.

---

## Step 3: Filter Split_Source from Review Grid (4_Review.py)

`[AUDIT CORRECTION]` The actual Review grid queries use `processing_status != 'Container_Scanned'` (not a `NOT IN` clause). There are **four** locations that reference `Container_Scanned`:

1. **Line ~2131** — Family override mode query:
   ```sql
   WHERE processing_status != 'Container_Scanned'
     AND (group_id = ? OR control_number = ?)
   ```

2. **Line ~2139** — Base review grid query:
   ```sql
   WHERE 1=1
       AND processing_status != 'Container_Scanned'
   ```

3. **Line ~2514** — DataFrame filtering for Family View (Python-side):
   ```python
   df.loc[df['processing_status'] == 'Container_Scanned', 'control_number']
   ```

4. **Line ~2520** — Direct DB query for container origins:
   ```python
   "SELECT control_number FROM documents WHERE processing_status = 'Container_Scanned'"
   ```

**For locations 1 and 2:** Convert from `!=` to `NOT IN` to add `Split_Source`:
```sql
WHERE processing_status NOT IN ('Container_Scanned', 'Split_Source')
```

**For locations 3 and 4:** These are specifically about container family logic (finding PST/ZIP parents to show as family heads). Split_Source documents are NOT containers and do NOT have family relationships, so these two should **stay as-is** — don't add Split_Source to the container-specific queries.

Also verify that the Processor's document selection query (in `2_Processor.py`, line ~533) only selects `processing_status='New'`, which means split children will be picked up automatically and `Split_Source` documents will be ignored. **Confirmed:** `SELECT * FROM documents WHERE processing_status='New'`.

---

## Step 4: UI — Split Tab in Review Module (4_Review.py)

`[AUDIT CORRECTION]` **Tab structure is conditional — use dynamic indexing, not hardcoded tab numbers.**

The existing tab creation (lines ~3151-3168):
```python
_can_redact = auth_manager.has_permission('redact')
_viewer_tabs = ["📄 Native / Image", "📝 Extracted Text", "📦 Production (Bates)"]
if _can_redact:
    _viewer_tabs.append("✏️ Redact")
```

Add the Split tab conditionally, AFTER the Redact tab append:
```python
# permission: split_document
_can_split = auth_manager.has_permission('split_document')
if _can_split:
    _viewer_tabs.append("✂️ Split")
```

Then use `tabs` by label lookup or dynamic index, NOT `tabs[3]` or `tabs[4]`:
```python
tabs = st.tabs(_viewer_tabs)

# Derive indices dynamically
_tab_idx = {label: i for i, label in enumerate(_viewer_tabs)}

# Later, to enter each tab:
if _can_redact:
    with tabs[_tab_idx["✏️ Redact"]]:
        ...
if _can_split:
    with tabs[_tab_idx["✂️ Split"]]:
        ...
```

**Why dynamic indexing matters:** A manager without `redact` permission but with `split_document` permission would have 4 tabs (Native, Text, Production, Split), and the Split tab would be `tabs[3]`. A manager with both permissions would have 5 tabs, with Split at `tabs[4]`. Hardcoding breaks one of these cases.

### Tab Content

The Split tab should be gated on:
- A document is selected (`current_cn` is set)
- The document's `processing_status` is NOT `Split_Source` (already split)
- The document's `begdoc` is NULL or empty (not yet produced)
- The document is a PDF (`.pdf` extension)
- The case is not closed (`_case_closed` flag)

If any gate fails, show a contextual info message explaining why splitting isn't available.

### UI Layout

`[AUDIT CORRECTION]` **Column ratio is responsive in the existing Redact tab.** The actual pattern (line ~3698):
```python
_r_col_ratio = [2.5, 7.5] if _r_zoom_pct >= 100 else [3, 7]
_r_ctrl_col, _r_canvas_col = st.columns(_r_col_ratio, gap="small")
```

The Split tab doesn't have a zoom-dependent canvas, so use the default `[3, 7]` ratio:
```python
_s_ctrl_col, _s_preview_col = st.columns([3, 7], gap="small")
```

**Left column (controls):**

1. **Page count display:** "This document has N pages"

2. **Split definition form:** A dynamic list of split ranges. Each range has:
   - Start page (number_input, 1-based for display, converted to 0-based internally)
   - End page (number_input, 1-based for display, converted to 0-based internally)
   - File name (text_input, with `.pdf` auto-appended if missing)
   - A "🗑 Remove" button to delete this range

3. **"➕ Add Range" button** — adds a new empty range to the list

4. **"Auto-Split: One Page Each" button** — convenience for single-page-per-document scenarios. Populates N ranges, each covering one page. File names default to `{source_file_name}_Page_{N}.pdf`.

5. **Validation display:** Before execution, show:
   - Total pages covered vs total pages in document
   - Any gaps (uncovered pages) highlighted in yellow with a warning: "Pages X-Y are not assigned to any split range. These pages will be discarded."
   - Any overlaps highlighted in red (blocking error)
   - Green checkmark if all pages are covered with no overlaps

6. **"✂️ Execute Split" button** (type="primary"):
   - Disabled until validation passes (no overlaps, at least 2 ranges)
   - Requires confirmation: `st.warning("This will create N new documents and mark the source as Split_Source. The source will no longer appear in the review grid. Continue?")`
   - On confirm, calls `db_manager.split_document()` and displays results

**Right column (preview):**

Page thumbnail strip — render each page of the source PDF at low DPI (~72 DPI) using `page.get_pixmap(matrix=fitz.Matrix(72/72, 72/72))`. Display as a vertical scrollable strip with page numbers. Color-code the page borders based on which split range they belong to (use Streamlit's column background or colored borders via markdown).

This preview is a nice-to-have — if it's too complex for the initial implementation, skip it and just show the page count. The validation display is more important.

### Post-Split Behavior

After successful split:
- Show a success message with the new control numbers
- Show a "⚙️ Go to Processor" button that links to Module 2
- Clear the current document selection (the source is no longer in the reviewable set)
- Trigger `st.rerun()` to refresh the grid

### Session State Keys

Use the prefix `_split_` for all session state keys related to this feature:
- `_split_ranges_{cn}` — list of current range definitions
- `_split_confirmed_{cn}` — boolean confirmation flag

---

## Step 5: Wire Existing Annotations to Split Children

When the source document has redaction marks from the annotation import, the `split_document()` function already migrates them (Step 2, item 4e). However, the marks were written with coordinates relative to the SOURCE PDF's pages. Since we're extracting those exact pages into the new PDF, the coordinates remain valid — no coordinate transformation needed. The only adjustment is the page NUMBER (offset by the split's start page).

The PDF annotations (the actual `PDF_ANNOT_REDACT` objects in the file) are embedded in the source PDF and will be carried over by `fitz.insert_pdf()` automatically — PyMuPDF copies all page content including annotations when extracting page ranges. So the new PDFs will have the visual black boxes already present. The `redaction_marks` table migration (Step 2, item 4e) ensures the platform's database records match.

---

## Step 6: Update Module Metadata and Documentation

### auth_manager.py header
Bump `version` (minor bump — new permission) and update `last_modified`, `modified_by`.

### 4_Review.py header
Bump `version` (minor bump — new feature) and update `last_modified`, `modified_by`. Current version: `1.27.1`.

### db_manager.py header
Bump `version` (minor bump — new function + new migration column) and update `last_modified`, `modified_by`. Current version: `1.17.0`.

### CHANGELOG.md
Add entry under current date:
```
### Document Split Feature (YYYY-MM-DD)
- NEW: auth_manager.py — `split_document` permission: manager-only gate for document splitting
- NEW: db_manager.py — `split_document()` function: splits multi-page PDFs into independent documents with page range extraction, control number assignment, redaction mark migration, and full audit logging
- NEW: db_manager.py — `split_source_cn` column migration for tracking split document lineage
- NEW: 4_Review.py — "✂️ Split" tab in document viewer: page range definition UI, validation (overlap/gap detection), confirmation workflow, post-split Processor redirect
- CHANGE: 4_Review.py — `Split_Source` status excluded from review grid (same pattern as Container_Scanned)
```

### DEPENDENCY_MAP.md
Add `split_source_cn` to the documents table column section. Add `Split_Source` to the processing_status enum values. Add `Split/` to the file path conventions section.

---

## What NOT To Do

- Do NOT set `parent_id` or `group_id` on split children to reference the source document. These fields are reserved for email family relationships (parent emails and their attachments). Split children are independent documents — each gets `group_id = its_own_cn`. Use `split_source_cn` for lineage tracking.
- Do NOT modify the source PDF file on disk. It's preserved for defensibility audit trail.
- Do NOT attempt to assign Bates numbers during the split. That's the Production module's job.
- Do NOT change the Processor's control number generation logic. Split children follow the normal `DOC-{id:06d}` path.
- Do NOT skip the Processor step for split children. They need text extraction, page counts, metadata population, and OpenSearch indexing.
- Do NOT copy `tags` or `privilege_status` from the source to children. Each child needs independent review decisions. However, DO migrate `redaction_marks` since those are positional (tied to specific pages that moved to the child).
- Do NOT add this feature to a new page file. It belongs in the existing `4_Review.py` as a new tab.
- Do NOT use `print()` for errors — use `logger.error()` / `logger.warning()` in backend code and `st.error()` / `st.warning()` in UI code.
- Do NOT use dot-notation control numbers (e.g., `DOC-000007.001`) for split children. That pattern is for container explosion children only. Split children get flat `DOC-{id:06d}`.
- Do NOT hardcode tab indices (e.g., `tabs[3]`, `tabs[4]`). The Redact tab is conditionally appended based on permissions, so tab indices shift. Use dynamic index lookup.
- Do NOT create a standalone `ALTER TABLE` block for `split_source_cn`. Add it to the existing `migrations` list in `init_db()`.
- Do NOT add `Split_Source` to the container-origin queries at lines ~2514 and ~2520 in `4_Review.py` — those are specifically for PST/ZIP family logic.
- Do NOT gate the Split tab on the `redact` permission. Use `split_document` — splitting is a manager-level structural operation, not a review action.

---

## Testing Checklist

After implementation, manually verify:

1. **Basic split:** Open a multi-page PDF, define 2+ ranges, execute. Confirm:
   - New documents appear in the database with correct control numbers
   - Source document has `processing_status = 'Split_Source'` and is hidden from review grid
   - New PDFs exist in `Split/` folder with correct page content
   - Audit log has `DOCUMENT_SPLIT_CHILD` and `DOCUMENT_SPLIT_SOURCE` entries

2. **Processor integration:** Run Module 2 on the new documents. Confirm:
   - They get processed normally (text extraction, metadata)
   - `processing_status` changes from `New` to `Master`
   - They appear in the Review grid after processing
   - `full_path` updates to `Processed/` location

3. **Redaction mark migration:** Split a document that has existing redaction marks spanning multiple pages. Confirm:
   - Marks are correctly distributed to the right child documents
   - Page numbers are adjusted (page 5 of source becomes page 0 of second child if split at page 5)
   - Source document's marks are deleted after migration

4. **Validation:** Try overlapping ranges → should be blocked. Try a single range → should be blocked. Try ranges that don't cover all pages → should warn but allow.

5. **Guard rails:** Try splitting an already-produced document → should be blocked with explanation. Try splitting a Split_Source document → should be blocked. Try splitting a non-PDF → should be blocked.

6. **Tab indexing:** Verify the Split tab renders correctly both when the user has redact permission (4 base tabs + split = 5) and when they don't (3 base tabs). If using dynamic index lookup, confirm no index errors in either case.

7. **Permission gate:** Log in as a reviewer (no `split_document` permission) — the Split tab should not appear. Log in as a manager — the Split tab should appear. Log in as admin — the Split tab should appear (wildcard `*` grants all).
