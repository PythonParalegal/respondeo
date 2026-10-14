# Sprint Spec: Production Categories & Disclosure Ordering

**Date:** 2026-04-02
**Branch:** beta-2.8 → new sprint branch
**Priority:** Demo Readiness — Tier 2 (Differentiator)
**Modules Touched:** `db_manager.py`, `4_Review.py`, `5_Production.py`

---

## Problem Statement

Documents ingested without organizational structure receive control numbers (DOC-IDs) in scan order, resulting in productions where correspondence, contracts, development files, and other document types are interleaved randomly. This makes 26(a)(1) initial disclosure certificates difficult to organize ("Correspondence, Bates 1–150; Contracts, Bates 151–240…") and presents unprofessionally to opposing counsel.

## Solution Overview

Add a **Production Category** system that allows users to group documents into logical categories (e.g., "Correspondence," "Contracts," "Development File," "Insurance," "Expert Reports") during review, then use that grouping as the primary sort key during production. Bates numbers are assigned sequentially through the category-sorted order, producing contiguous Bates ranges per category — exactly what disclosure certificates need.

### Key Design Decisions

- **Per-case category lists** — stored in `case_settings` like tag categories
- **Assignment during Review** — dropdown in detail pane + bulk assignment via batch action bar
- **Auto-categorization tool** — keyword/extension rules engine for bulk initial pass, then manual cleanup
- **Manual drag-and-drop sort priority** — user defines the category order for production
- **New sort mode in Production** — "Sort by Production Category" alongside existing folder/family options

---

## Item 1 — Database Schema

### 1A. New column on `documents` table

```sql
ALTER TABLE documents ADD COLUMN production_category TEXT;
```

- Nullable — uncategorized documents are valid (sort to end of production)
- Single value per document (not multi-value like tags)
- Stores the category name string directly (e.g., `"Correspondence"`)

Add migration to `_apply_migrations()` in `db_manager.py`:

```python
# Migration: production_category column
cursor.execute("PRAGMA table_info(documents)")
cols = {row[1] for row in cursor.fetchall()}
if 'production_category' not in cols:
    cursor.execute("ALTER TABLE documents ADD COLUMN production_category TEXT")
```

### 1B. Case setting: `production_categories`

Stored in `case_settings` as JSON. Structure:

```json
{
  "categories": [
    {"name": "Correspondence", "sort_order": 1, "color": "#339af0", "keywords": ["letter", "email", "memo"], "extensions": [".msg", ".eml"]},
    {"name": "Contracts", "sort_order": 2, "color": "#51cf66", "keywords": ["agreement", "contract", "addendum"], "extensions": []},
    {"name": "Development File", "sort_order": 3, "color": "#ff922b", "keywords": ["permit", "inspection", "plan", "survey"], "extensions": []},
    {"name": "Insurance", "sort_order": 4, "color": "#845ef7", "keywords": ["policy", "claim", "coverage", "insured"], "extensions": []},
    {"name": "Expert Reports", "sort_order": 5, "color": "#f06595", "keywords": ["expert", "report", "opinion"], "extensions": []},
    {"name": "Financial Records", "sort_order": 6, "color": "#20c997", "keywords": ["invoice", "payment", "receipt", "ledger"], "extensions": [".xlsx", ".csv"]},
    {"name": "Pleadings", "sort_order": 7, "color": "#e64980", "keywords": ["complaint", "answer", "motion", "order"], "extensions": []},
    {"name": "Discovery", "sort_order": 8, "color": "#fab005", "keywords": ["interrogat", "request for", "subpoena", "deposition"], "extensions": []}
  ]
}
```

### 1C. New `db_manager.py` functions

```python
def get_production_categories(case_folder):
    """Return list of production category dicts, sorted by sort_order."""

def save_production_categories(case_folder, categories):
    """Persist production category list to case_settings."""

def update_document_production_category(case_folder, control_number, category_name):
    """Set production_category for a single document."""

def bulk_update_production_category(case_folder, control_numbers, category_name):
    """Set production_category for a list of documents. Audit log batch entry."""

def auto_categorize_documents(case_folder, dry_run=True, selected_control_numbers=None):
    """Apply keyword/extension rules to uncategorized documents.

    Returns dict: {category_name: [list of dicts with control_number, file_name,
                    record_type, date_sent, match_reason]}
    If dry_run=True, does not write to DB — returns preview for grid display.
    If dry_run=False and selected_control_numbers provided, updates ONLY those
        documents and returns results. This allows the UI to pass back only the
        user-approved matches after they deselect false positives in the preview grid.
    If dry_run=False and selected_control_numbers is None, updates ALL matches.

    Matching priority:
    1. File extension match (highest confidence) — match_reason: "Extension: .msg"
    2. Filename keyword match (case-insensitive substring) — match_reason: "Filename: 'contract'"
    3. Email subject keyword match (for record_type='Email') — match_reason: "Subject: 'policy'"
    Documents matching multiple categories: first match by sort_order wins.
    Already-categorized documents are NEVER overwritten (WHERE production_category IS NULL).
    """

def get_category_summary(case_folder):
    """Return dict of {category_name: doc_count} + {'Uncategorized': count}.
    Used for the category management dashboard and production setup display."""
```

### 1D. DEPENDENCY_MAP.md update

Add `production_category` to §1 (documents table columns) with consumers:
- `4_Review.py` — display, edit, bulk assign
- `5_Production.py` — sort key for Bates assignment
- `db_manager.py` — CRUD + auto-categorize

---

## Item 2 — Category Management UI

Location: **`4_Review.py`** — new **"📂 Production Categories"** expander in the sidebar settings area (Manager+ permission, below the tag category config).

Also accessible from **`5_Production.py`** — read-only summary display in the production setup panel showing category counts.

### 2A. Category List Editor (Review sidebar)

- **Permission gate:** `# permission: manage_production_categories` — Manager+
- **Closed case check:** Read-only if case is closed
- Displays current categories as an ordered list with:
  - Color swatch
  - Category name (editable inline)
  - Keyword rules (editable, comma-separated)
  - Extension rules (editable, comma-separated)
  - Document count badge (from `get_category_summary()`)
- **Drag-and-drop reordering:** Use `st.data_editor` with row reordering enabled, OR number-input sort_order fields. Streamlit doesn't have native drag-and-drop, so use a numbered sort_order column in a `st.data_editor` — user changes the numbers, system re-sorts on save. (Alternative: up/down arrow buttons per row.)
- **Add / Remove** category buttons
- **Save** button persists to `case_settings`
- **Audit:** `log_audit(action='PRODUCTION_CATEGORIES_UPDATED', ...)`

### 2B. Auto-Categorize Tool

Location: Button within the Category Management expander — **"🤖 Auto-Categorize Uncategorized Documents"**

**Scope rule:** Auto-categorize ONLY operates on documents where `production_category IS NULL`. Documents that already have a category assigned are **never touched** — the user already made a deliberate decision about those.

Flow:
1. User clicks button → system calls `auto_categorize_documents(dry_run=True)`
2. Results display as a **tabbed preview** — one tab per category that matched documents
3. Each tab contains a **selectable document grid** (checkboxes, pre-checked) showing: Control #, File Name, Doc Type, Date Sent, Match Reason (which keyword/extension triggered the match)
4. User reviews each tab, **deselects false positives** (e.g., an email that mentions "policy" but isn't an insurance document)
5. Summary bar at top shows: "Ready to categorize: 330 of 350 matched documents (20 deselected)"
6. User clicks **"✅ Apply Selected"** to commit only the checked documents, or **"Cancel"** to discard all
7. On apply: `auto_categorize_documents(dry_run=False, selected_control_numbers=...)` + audit log batch entry
8. Success message: "Categorized 330 of 1,000 documents. 670 remain uncategorized."

**Why the grid matters:** Keyword matching is inherently fuzzy. "Policy" catches insurance policies but also emails discussing company policy. "Report" catches expert reports but also status report emails. The preview grid with deselection gives the user final say over every match — turning an 80% accurate automation into a 100% accurate one with minimal effort.

---

## Item 3 — Review Page Integration

### 3A. Production Category column in Review Grid

- Add `production_category` to the Review grid's column set
- Display with color-coded badge (like tags)
- Filterable via the SQL filter row (dropdown of known categories + "Uncategorized")

### 3B. Single-document category assignment

- In the document detail pane (right panel), add a **Production Category** dropdown below the tags section
- Populated from `get_production_categories()` + "Uncategorized" option + **"+ New Category"** option at the bottom
- **"+ New Category":** Selecting this opens an inline text input + color picker. On submit, the new category is created in `case_settings` (appended with the next sort_order value) AND immediately assigned to the current document. This allows organic category discovery during review — no need to leave the review workflow to go define categories in a settings panel first.
- On change: `update_document_production_category()` + audit log
- Changing a category on a single document is a **direct replacement** — no confirmation needed. The user is looking right at the document and making a deliberate choice. They can always change it again.
- **Permission:** `# permission: assign_production_category` — Reviewer+
- **Closed case:** Disabled if closed

### 3C. Bulk category assignment via Batch Action Bar

- Add **"📂 Set Category"** button to the existing bulk action bar (appears when multiple rows are selected)
- Clicking opens a dropdown/selectbox of categories
- **Conflict handling:** If ANY of the selected documents already have a category assigned, show a warning before applying:
  > "⚠️ 3 of 30 selected documents already have a category (2 Correspondence, 1 Insurance). How would you like to proceed?"
  >
  > - **Apply to all** — overwrites existing categories for the entire selection
  > - **Apply to uncategorized only** — skips documents that already have a category, applies to the rest
  > - **Cancel** — no changes

  This ensures the user is never surprised by a silent overwrite during bulk operations.
- On confirm: `bulk_update_production_category()` for the applicable control numbers
- Progress bar for large batches (>100 docs)
- **Permission:** `# permission: assign_production_category` — Reviewer+

---

## Item 4 — Production Sort Mode

### 4A. New sort option in Production Setup

Replace the current binary checkbox with a 3-option radio or selectbox:

```python
st.subheader("Document Ordering")
sort_mode = st.radio(
    "Production sort order",
    options=["Sort by Production Category", "Sort by Ingestion Folder", "Sort by Family Only"],
    index=0,  # default to category sort
    help=(
        "**Production Category** — Groups documents by their assigned category "
        "(Correspondence, Contracts, etc.) in the order you defined. "
        "Produces contiguous Bates ranges per category — ideal for 26(a)(1) disclosures.\n\n"
        "**Ingestion Folder** — Groups by source folder structure, then family.\n\n"
        "**Family Only** — Sorts by document family group and control number only."
    ),
    key="prod_sort_mode"
)
```

### 4B. Category sort implementation

When `sort_mode == "Sort by Production Category"`:

```python
# Load category sort order
prod_cats = db_manager.get_production_categories(case_folder)
cat_order = {cat['name']: cat['sort_order'] for cat in prod_cats}
max_order = max(cat_order.values(), default=0) + 1  # uncategorized sorts last

# Map each document's category to its sort priority
# Use the FAMILY ROOT's category for the whole family (same pattern as folder sort)
df['_is_parent'] = df['parent_id'].isna() | (df['parent_id'].astype(str).str.strip() == '')
_root_cats = df[df['_is_parent']].set_index('control_number')['production_category']
df['_family_category'] = df['sort_group'].map(_root_cats).fillna(df['production_category'])
df['_cat_sort_order'] = df['_family_category'].map(cat_order).fillna(max_order)

df = df.sort_values(
    by=['_cat_sort_order', '_family_category', 'sort_group', '_is_parent', 'control_number'],
    ascending=[True, True, True, False, True]
)

# Cleanup temp columns
df = df.drop(columns=['_cat_sort_order', '_family_category', '_is_parent'], errors='ignore')
```

**Critical:** Family integrity must be maintained — all members of a family stay together. The family inherits the **root document's** category. If a parent email is "Correspondence" but an attachment was individually categorized as "Contracts," the family still sorts under "Correspondence." This matches the existing folder-sort pattern.

### 4C. Category summary display in Production Setup

Before the "Run Production" button, show a summary table:

```
Production Category Breakdown:
  Correspondence ........ 100 docs
  Contracts ............. 50 docs
  Development File ...... 150 docs
  Insurance ............. 40 docs
  Uncategorized ......... 160 docs  ⚠️
```

If uncategorized count > 0 and sort mode is "Production Category," show a warning:
> "⚠️ 160 documents have no production category assigned. They will be placed at the end of the production. Consider running Auto-Categorize in the Review page first."

### 4D. Post-production: Disclosure Summary

After production completes, generate a **Disclosure Category Summary** section in the production results:

```
📋 Disclosure Reference:
  1. Correspondence — ABC-000001 through ABC-000100
  2. Contracts — ABC-000101 through ABC-000150
  3. Development File — ABC-000151 through ABC-000300
  4. Insurance — ABC-000301 through ABC-000340
  5. Uncategorized — ABC-000341 through ABC-000500
```

This gives the user the exact Bates ranges they need for their 26(a)(1) disclosure certificate. Store this summary in `production_runs.settings_json` for later retrieval.

---

## Item 5 — Conflict-Handling Rules

Three assignment contexts, three levels of protection — matched to intentionality:

| Context | Overwrites existing? | User confirmation? | Rationale |
|---------|---------------------|--------------------|-----------|
| **Single-document dropdown** (detail pane) | Yes — direct replacement | None needed | User is looking at the document, making a deliberate choice. Lowest friction. |
| **Bulk assignment** (batch action bar) | Conditional | Warning + 3 options (apply all / uncategorized only / cancel) | User may not realize some selected docs already have categories. Warn, don't block. |
| **Auto-categorize tool** | Never | N/A — already-categorized docs are excluded from the query | Automation should never second-guess a human decision. Only touches `production_category IS NULL` rows. |

**Design principle:** The more automated the action, the more conservative the overwrite behavior. A human clicking a dropdown for one document needs no guardrails. A keyword engine scanning 2,500 documents needs maximum guardrails.

---

## Item 6 — Audit & Defensibility

All category operations must be audited:
- `PRODUCTION_CATEGORY_SET` — single document category change (old_value → new_value)
- `PRODUCTION_CATEGORY_BULK` — bulk assignment (count + category)
- `PRODUCTION_CATEGORY_AUTO` — auto-categorize run (count per category)
- `PRODUCTION_CATEGORIES_UPDATED` — category list/order changes

The production run's `settings_json` should record the sort mode used and category order, so the production is defensibly reproducible.

---

## Implementation Order

Recommended sprint sequence for Claude Code:

1. **Batch 1 — Schema + db_manager functions** (Item 1)
   - Migration, all 6 new functions, DEPENDENCY_MAP update
   - Test: verify migration runs clean, functions return expected shapes

2. **Batch 2 — Category Management UI** (Item 2)
   - Sidebar editor in Review, auto-categorize preview/apply flow
   - Test: create categories, run auto-categorize on test data

3. **Batch 3 — Review Integration** (Item 3)
   - Grid column, detail pane dropdown, bulk action bar button
   - Test: assign categories to documents individually and in bulk

4. **Batch 4 — Production Sort Mode** (Item 4)
   - Replace checkbox with 3-option radio, implement category sort logic
   - Test: run production with category sort, verify Bates ranges are contiguous per category
   - Test: verify family integrity (attachments follow parent's category)

5. **Batch 5 — Disclosure Summary + Audit** (Items 4D, 5, 6)
   - Post-production summary generation, conflict-handling logic, audit log entries
   - Test: verify summary matches actual Bates assignments
   - Test: verify bulk assignment conflict warning triggers correctly
   - Test: verify auto-categorize skips already-categorized documents

---

## Out of Scope (Future Enhancements)

- **AI-assisted categorization** using document text content (OpenSearch query-based classification) — would dramatically improve auto-categorize accuracy but adds complexity
- **Sub-categories** (e.g., Correspondence > Internal, Correspondence > External) — could be added later as a hierarchical extension
- **Cross-production category consistency** — enforcing that supplemental productions maintain the same category ordering as the original
- **Category-based privilege log grouping** — organize privilege log entries by production category
