# Exhibit List / Trial Binder — Design Spec

**Date:** 2026-03-26
**Phase:** 24c.7 (final EDRM item)
**Estimated complexity:** ~400 lines new code across db_manager, 4_Review, 8_Exhibits

---

## Problem

Attorneys reviewing produced documents need to designate specific documents as exhibits for depositions, motions, hearings, and trial. Currently this requires external tracking (spreadsheets, handwritten lists). The platform should let reviewers mark exhibits during review and give managers a dedicated page to organize exhibit sets and export assembled binder PDFs.

## Key Constraint

**Exhibits are always produced documents.** A document cannot be designated as an exhibit if it has not been produced (no production history in `document_productions`). The binder PDF uses the Bates-stamped produced copy, not the processed version.

---

## Data Model

### `exhibit_sets` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `case_folder` | TEXT NOT NULL | FK to case |
| `set_name` | TEXT NOT NULL | e.g., "Deposition of John Smith" |
| `set_type` | TEXT NOT NULL | Picklist: Deposition, Motion, Hearing, Trial |
| `proceeding_date` | TEXT | Date of the proceeding (YYYY-MM-DD) |
| `case_caption` | TEXT | Optional override; falls back to case-level caption |
| `created_by` | TEXT NOT NULL | Username |
| `created_at` | TEXT NOT NULL | ISO datetime |
| UNIQUE | | (`case_folder`, `set_name`) |

### `exhibits` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `exhibit_set_id` | INTEGER NOT NULL | FK → exhibit_sets.id |
| `control_number` | TEXT NOT NULL | FK → documents.control_number |
| `exhibit_number` | TEXT NOT NULL | Freeform — attorney types whatever convention applies |
| `description` | TEXT | Attorney-written description for the index |
| `sort_order` | INTEGER NOT NULL | Explicit display/binder ordering |
| `added_by` | TEXT NOT NULL | Username |
| `added_at` | TEXT NOT NULL | ISO datetime |
| UNIQUE | | (`exhibit_set_id`, `exhibit_number`) — no duplicate exhibit numbers within a set |
| UNIQUE | | (`exhibit_set_id`, `control_number`) — same doc can't appear twice in same set |

**Cross-set behavior:** The same document CAN appear in multiple exhibit sets (e.g., Exhibit 3 in the Smith Deposition and Exhibit A in the MSJ). The unique constraints are per-set.

---

## DB Helper Functions (db_manager.py)

All functions follow existing patterns: connection managed internally, never-raise where appropriate.

### Exhibit Sets CRUD

- `create_exhibit_set(case_folder, set_name, set_type, proceeding_date, case_caption, created_by)` → set_id
- `get_exhibit_sets(case_folder)` → list of dicts
- `update_exhibit_set(set_id, **fields)` → None (update set_name, set_type, proceeding_date, case_caption)
- `delete_exhibit_set(set_id)` → None (CASCADE deletes exhibits in the set)

### Exhibits CRUD

- `add_exhibit(exhibit_set_id, control_number, exhibit_number, description, sort_order, added_by)` → exhibit_id
- `get_exhibits(exhibit_set_id)` → list of dicts ordered by sort_order (JOIN to documents for file_name, custodian, and JOIN to document_productions for Bates range, page_count, production_volume)
- `update_exhibit(exhibit_id, **fields)` → None (update exhibit_number, description, sort_order)
- `remove_exhibit(exhibit_id)` → None
- `reorder_exhibits(exhibit_set_id, ordered_exhibit_ids)` → None (bulk update sort_order)
- `get_document_exhibit_sets(case_folder, control_number)` → list of dicts (which sets this document belongs to, with exhibit numbers — for Review panel display)

---

## Permissions

| Action | Minimum Role | Permission Name |
|--------|-------------|-----------------|
| Mark exhibit in Review | Reviewer (1) | `mark_exhibit` |
| View exhibit lists | Reviewer (1) | `view_exhibits` |
| Create/rename/delete exhibit sets | Manager (2) | `manage_exhibit_sets` |
| Reorder/edit exhibits on management page | Manager (2) | `manage_exhibits` |
| Export binder PDF | Manager (2) | `export_exhibit_binder` |

---

## Review Module Integration (4_Review.py)

### Coding Panel Addition

Below the existing custom coding fields section, add an **Exhibits** section:

- **Gate:** Only visible for documents that have production history (`document_productions` records exist for this control_number).
- **Display:** If the document is already in one or more exhibit sets, show badges: "Exhibit 3 — Smith Depo", "Exhibit A — MSJ".
- **"Mark as Exhibit" button** (Reviewer+):
  - Opens a popover/expander with:
    - Dropdown: select an exhibit set (populated from `get_exhibit_sets`)
    - Text input: exhibit number (freeform)
    - Text input: description
    - "Add" button
  - If no exhibit sets exist, show a message: "No exhibit sets created yet. A manager can create one on the Exhibits page."
  - On success: refresh the badges, log audit event.

### Audit Logging

- `log_audit()` call on every add/remove: module="Review", action="exhibit_added" / "exhibit_removed", control_number, details includes set name and exhibit number.

---

## Exhibits Management Page (8_Exhibits.py)

New Streamlit page: `pages/8_Exhibits.py`
Module title: "Module 7: Exhibits"

### Access

- Page visible to Reviewer+ (role >= 1)
- Write operations (create set, edit, export) gated to Manager+ (role >= 2)
- Closed-case check at top blocks all writes

### Layout

#### Top Section: Exhibit Set Selector + Management

- **Dropdown:** Select an exhibit set (or "Create New...")
- **Set details** (editable by Manager+):
  - Set name (text input)
  - Set type (selectbox: Deposition, Motion, Hearing, Trial)
  - Proceeding date (date input)
  - Case caption override (text input, optional)
  - Delete set button (with confirmation)

#### Main Section: Exhibit List for Selected Set

- **Table columns:** Sort Order | Exhibit Number | Description | Bates Range | Pages | Custodian | File Name
- **Reorder:** Up/down arrow buttons per row to adjust sort_order (Manager+)
- **Inline edit:** Exhibit number and description editable in-place (Manager+)
- **Remove:** Remove button per row with confirmation (Manager+)
- **Add exhibits:** "Add Document" section (Manager+):
  - Search/browse produced documents not already in this set
  - Mini search bar that queries documents with production history
  - Results grid showing: control_number, file_name, Bates range, custodian
  - Select + assign exhibit number + description → add to set

#### Export Section (Manager+)

- **"Export Binder PDF" button**
  - Assembles the full binder PDF (see Binder PDF Structure below)
  - Returns as `st.download_button` with the PDF bytes
  - Filename: `{set_name}_Exhibit_Binder.pdf` (sanitized)
  - Audit log: action="exhibit_binder_exported", details includes set name and exhibit count

---

## Binder PDF Structure

Generated using `pdfkit` (wkhtmltopdf) for cover/index/dividers + PyMuPDF (`fitz`) for merging produced PDFs.

### Page Order

1. **Cover sheet** (1 page)
2. **Index** (1+ pages, depending on exhibit count)
3. For each exhibit in sort_order:
   - **Divider page** (1 page)
   - **Produced document pages** (from Productions/{volume}/IMAGES/{begdoc}.pdf)

### Cover Sheet Content

- Case caption (from set or case-level fallback)
- Exhibit set name (e.g., "Deposition of John Smith")
- Proceeding date
- "EXHIBIT BINDER" label
- Confidentiality line (if confidentiality_designation is set at case level)

**Style:** Black and white, portrait, no background fills. Georgia serif font. Simple horizontal rules as dividers. Printer-friendly.

### Index Page Content

- Title: "INDEX OF EXHIBITS"
- Subtitle: set name + proceeding date
- Table columns: Exhibit | Description | Bates Range | Binder Page
- Binder page numbers calculated after assembly (cover + index pages + cumulative document pages + divider pages)

**Style:** Black and white, portrait. Table with thin borders. Monospace for Bates ranges.

### Divider Page Content

- Set name (small, uppercase, top)
- Exhibit number (large, bold, centered)
- Description (below exhibit number)
- Bates range (monospace)
- Page count

**Style:** Black and white, portrait. Centered vertically. Clean typographic hierarchy.

### PDF Assembly Process

1. Render cover HTML → PDF bytes via pdfkit (Letter, portrait)
2. For each exhibit, resolve the produced PDF path:
   - Query `document_productions` for the document's production volume and begdoc
   - Path: `{case_folder}/Productions/{production_volume}/IMAGES/{begdoc}.pdf`
   - If multiple productions exist, use the most recent one
3. Two-pass page numbering:
   - **Pass 1:** Render index HTML to PDF with placeholder page numbers, measure how many pages the index occupies
   - **Pass 2:** Recalculate binder page numbers using actual index page count (cover=1 + index pages + cumulative divider+document pages), re-render index with final numbers
   - Each exhibit contributes: 1 divider page + document page count (from `document_productions.page_count`)
4. Render index HTML → PDF bytes via pdfkit (final pass with correct page numbers)
5. Render each divider HTML → PDF bytes via pdfkit
6. Assemble final PDF using PyMuPDF:
   - `fitz.open()` new document
   - `insert_pdf()` cover
   - `insert_pdf()` index
   - For each exhibit: `insert_pdf()` divider, then `insert_pdf()` produced document
   - Return bytes

### Error Handling

- If a produced PDF is missing (file not found), insert a placeholder page: "Exhibit {number} — Document Not Available — {control_number}"
- Log warning but don't fail the entire binder for one missing document
- Report missing documents in a summary after export

---

## Implementation Notes

### New File

- `pages/8_Exhibits.py` — new Streamlit page with full version header

### Modified Files

- `db_manager.py` — schema migration (exhibit_sets + exhibits tables), 8 CRUD functions
- `4_Review.py` — exhibit badges + "Mark as Exhibit" popover in coding panel
- `auth_manager.py` — new permissions: mark_exhibit, view_exhibits, manage_exhibit_sets, manage_exhibits, export_exhibit_binder
- `DEPENDENCY_MAP.md` — new tables, new cross-module references

### Patterns to Follow

- **PDF generation:** `defensibility_report.py` pattern — HTML string → `pdfkit.from_string()` with wkhtmltopdf config from `config.py`
- **PDF merging:** `pdf_exporter.py` pattern — `fitz.open()` + `insert_pdf()` for concatenation
- **DB helpers:** existing CRUD pattern in `db_manager.py` (connection managed internally, parameterized queries)
- **Audit logging:** `log_audit()` / `log_audit_batch()` with never-raise contract
- **Permission gates:** `# permission: <name>` annotation convention

### Production Volume Resolution

When a document has been produced in multiple volumes, the binder uses the **most recent** production (latest `produced_at` from `document_productions`). This matches the expectation that the latest production reflects the most current state of the document.

---

## Out of Scope

- Exhibit stickers/labels on the actual document pages (physical stickering is a separate workflow)
- Video exhibit linking
- Exhibit exchange tracking between parties
- Automated exhibit numbering schemes (freeform only)
