# Exhibit List / Trial Binder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let attorneys designate produced documents as exhibits during review, manage exhibit sets on a dedicated page, and export assembled binder PDFs with cover sheets, index, and divider pages.

**Architecture:** Two new DB tables (`exhibit_sets`, `exhibits`) with CRUD helpers in `db_manager.py`. Exhibit marking popover added to Review coding panel (outside the form). New `pages/8_Exhibits.py` for set management and binder export. Binder PDF assembled via pdfkit (cover/index/dividers) + PyMuPDF (merge produced PDFs).

**Tech Stack:** SQLite, Streamlit, pdfkit (wkhtmltopdf), PyMuPDF (fitz), existing db_manager/auth_manager patterns.

**Spec:** `docs/superpowers/specs/2026-03-26-exhibit-list-trial-binder-design.md`

---

### Task 1: Schema Migration + DB Helper Functions

**Files:**
- Modify: `db_manager.py` (add tables in migration block ~line 517-564, add CRUD functions after existing coding_fields functions ~line 1635)

- [ ] **Step 1: Add exhibit_sets and exhibits table creation to migration block**

In `db_manager.py`, find the `document_coding` CREATE TABLE block (around line 551-564). After the `idx_dc_field_id` index creation (line 564), add:

```python
        # ── Exhibit Sets & Exhibits ────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exhibit_sets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                case_folder TEXT    NOT NULL,
                set_name    TEXT    NOT NULL,
                set_type    TEXT    NOT NULL DEFAULT 'Deposition',
                proceeding_date TEXT,
                case_caption    TEXT,
                created_by  TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                UNIQUE(case_folder, set_name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exhibits (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                exhibit_set_id  INTEGER NOT NULL,
                control_number  TEXT    NOT NULL,
                exhibit_number  TEXT    NOT NULL,
                description     TEXT,
                sort_order      INTEGER NOT NULL DEFAULT 0,
                added_by        TEXT    NOT NULL,
                added_at        TEXT    NOT NULL,
                FOREIGN KEY (exhibit_set_id) REFERENCES exhibit_sets(id) ON DELETE CASCADE,
                FOREIGN KEY (control_number) REFERENCES documents(control_number),
                UNIQUE(exhibit_set_id, exhibit_number),
                UNIQUE(exhibit_set_id, control_number)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exhibits_set_id ON exhibits(exhibit_set_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exhibits_cn ON exhibits(control_number)")
```

- [ ] **Step 2: Verify PRAGMA foreign_keys is enabled for CASCADE**

In `get_connection()` (around line 16-37), after the `PRAGMA journal_mode=WAL` line, check if `PRAGMA foreign_keys = ON` is already set. If not, add it. CASCADE deletes on `exhibit_sets` → `exhibits` require this pragma. Add after the WAL pragma line:

```python
    conn.execute("PRAGMA foreign_keys = ON")
```

**Note:** Check if this pragma already exists in `get_connection()` first. If it does, skip this step.

- [ ] **Step 3: Add Exhibit Sets CRUD functions**

After the last coding_fields function in `db_manager.py` (around line 1635), add:

```python
# ── Exhibit Sets & Exhibits ──────────────────────────────────────────────


def create_exhibit_set(case_folder, set_name, set_type, proceeding_date,
                       case_caption, created_by):
    """Create a new exhibit set. Returns the new set id."""
    conn = get_connection(case_folder)
    try:
        cursor = conn.execute(
            "INSERT INTO exhibit_sets "
            "(case_folder, set_name, set_type, proceeding_date, case_caption, "
            " created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (case_folder, set_name, set_type, proceeding_date, case_caption,
             created_by, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_exhibit_sets(case_folder):
    """Return all exhibit sets for a case as list of dicts."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT * FROM exhibit_sets WHERE case_folder = ? ORDER BY created_at",
            (case_folder,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_exhibit_set(case_folder, set_id, **fields):
    """Update exhibit set fields (set_name, set_type, proceeding_date, case_caption)."""
    allowed = {'set_name', 'set_type', 'proceeding_date', 'case_caption'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [set_id]
    conn = get_connection(case_folder)
    try:
        conn.execute(f"UPDATE exhibit_sets SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def delete_exhibit_set(case_folder, set_id):
    """Delete an exhibit set and all its exhibits (CASCADE)."""
    conn = get_connection(case_folder)
    try:
        conn.execute("DELETE FROM exhibit_sets WHERE id = ?", (set_id,))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Add Exhibits CRUD functions**

Immediately after the exhibit set functions, add:

```python
def add_exhibit(case_folder, exhibit_set_id, control_number, exhibit_number,
                description, sort_order, added_by):
    """Add a document to an exhibit set. Returns the new exhibit id."""
    conn = get_connection(case_folder)
    try:
        cursor = conn.execute(
            "INSERT INTO exhibits "
            "(exhibit_set_id, control_number, exhibit_number, description, "
            " sort_order, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (exhibit_set_id, control_number, exhibit_number, description,
             sort_order, added_by, datetime.now().isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_exhibits(case_folder, exhibit_set_id):
    """
    Return all exhibits in a set, ordered by sort_order.
    JOINs to documents for file_name/custodian, and to document_productions
    for the most recent Bates range and page count.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT e.*,
                   d.file_name, d.custodian, d.record_type,
                   dp.begdoc, dp.enddoc, dp.page_count AS prod_page_count,
                   dp.production_volume
            FROM exhibits e
            JOIN documents d ON e.control_number = d.control_number
            LEFT JOIN document_productions dp ON e.control_number = dp.control_number
                AND dp.produced_at = (
                    SELECT MAX(dp2.produced_at)
                    FROM document_productions dp2
                    WHERE dp2.control_number = e.control_number
                )
            WHERE e.exhibit_set_id = ?
            ORDER BY e.sort_order, e.id
        """, (exhibit_set_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_exhibit(case_folder, exhibit_id, **fields):
    """Update exhibit fields (exhibit_number, description, sort_order)."""
    allowed = {'exhibit_number', 'description', 'sort_order'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [exhibit_id]
    conn = get_connection(case_folder)
    try:
        conn.execute(f"UPDATE exhibits SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def remove_exhibit(case_folder, exhibit_id):
    """Remove an exhibit from its set."""
    conn = get_connection(case_folder)
    try:
        conn.execute("DELETE FROM exhibits WHERE id = ?", (exhibit_id,))
        conn.commit()
    finally:
        conn.close()


def reorder_exhibits(case_folder, exhibit_set_id, ordered_exhibit_ids):
    """Bulk update sort_order for all exhibits in a set."""
    conn = get_connection(case_folder)
    try:
        for idx, eid in enumerate(ordered_exhibit_ids):
            conn.execute(
                "UPDATE exhibits SET sort_order = ? WHERE id = ? AND exhibit_set_id = ?",
                (idx, eid, exhibit_set_id)
            )
        conn.commit()
    finally:
        conn.close()


def get_document_exhibit_sets(case_folder, control_number):
    """
    Return which exhibit sets a document belongs to, with exhibit numbers.
    Used by the Review coding panel to show exhibit badges.
    """
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT e.exhibit_number, es.set_name, es.id AS set_id
            FROM exhibits e
            JOIN exhibit_sets es ON e.exhibit_set_id = es.id
            WHERE e.control_number = ?
            ORDER BY es.set_name, e.exhibit_number
        """, (control_number,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_next_sort_order(case_folder, exhibit_set_id):
    """Return the next available sort_order value for an exhibit set."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM exhibits WHERE exhibit_set_id = ?",
            (exhibit_set_id,)
        ).fetchone()
        return row[0]
    finally:
        conn.close()
```

- [ ] **Step 5: Verify datetime import exists in db_manager.py**

Check that `from datetime import datetime` is in the imports at the top of `db_manager.py`. If not, add it.

- [ ] **Step 6: Update version header in db_manager.py**

Bump the minor version (new functions added). Update `last_modified` to current date/time, `modified_by` to `claude-code`, `last_commit` to `pending`.

- [ ] **Step 7: Add CHANGELOG entries**

```
- NEW: db_manager.py — exhibit_sets and exhibits tables with CASCADE delete, indexes
- NEW: db_manager.py — 9 exhibit CRUD functions: create/get/update/delete exhibit sets, add/get/update/remove/reorder exhibits, get_document_exhibit_sets, get_next_sort_order
```

- [ ] **Step 8: Commit**

```bash
git add db_manager.py CHANGELOG.md
git commit -m "feat: exhibit_sets + exhibits tables and CRUD helpers (Phase 24c.7)"
```

---

### Task 2: Auth Permissions

**Files:**
- Modify: `auth_manager.py` (lines 48-61 for ALL_PERMISSIONS, lines 29-45 for _DEFAULT_PERMISSIONS)

- [ ] **Step 1: Add exhibit permissions to ALL_PERMISSIONS**

In `auth_manager.py`, find the `ALL_PERMISSIONS` list (line 48-61). Add to the `# Review` section:

```python
    # Review
    'review', 'tag', 'redact', 'export_csv', 'export_pdf',
    'str_run', 'str_export', 'column_picker',
    'saved_search_global', 'saved_search_personal', 'download_produced',
    'reimage',
    'mark_exhibit', 'view_exhibits',
```

Add to the `# Production / legal` section:

```python
    # Production / legal
    'production', 'inbound_production', 'privilege_log',
    'custodian_management',
    'manage_exhibit_sets', 'manage_exhibits', 'export_exhibit_binder',
```

- [ ] **Step 2: Add exhibit permissions to _DEFAULT_PERMISSIONS**

In `_DEFAULT_PERMISSIONS` (lines 29-45):

Add to the `'manager'` set:
```python
        'manage_exhibit_sets', 'manage_exhibits', 'export_exhibit_binder',
        'mark_exhibit', 'view_exhibits',
```

Add to the `'reviewer'` set:
```python
        'mark_exhibit', 'view_exhibits',
```

- [ ] **Step 3: Update version header in auth_manager.py**

Patch bump (adding new permission values to existing constants). Update `last_modified`, `modified_by`, `last_commit`.

- [ ] **Step 4: Add CHANGELOG entry**

```
- NEW: auth_manager.py — exhibit permissions: mark_exhibit, view_exhibits, manage_exhibit_sets, manage_exhibits, export_exhibit_binder added to ALL_PERMISSIONS and role defaults
```

- [ ] **Step 5: Commit**

```bash
git add auth_manager.py CHANGELOG.md
git commit -m "feat: exhibit permissions for reviewer and manager roles"
```

---

### Task 3: Review Module — Exhibit Badges + Mark as Exhibit

**Files:**
- Modify: `pages/4_Review.py` (insert after the form block ends, around line 4403, before the "Inline New Tag Creator" at line 4404)

**Context:** The coding panel (Pane 3) uses a `st.form()` for tag/coding saves. The exhibit marking UI must go **outside** the form because it uses its own button actions. Insert it between the form's end (line ~4403) and the "Inline New Tag Creator" expander (line 4404).

- [ ] **Step 1: Add exhibit section after form block**

Find line 4403 in `4_Review.py` (the last line of the form's `btn_next` handler). After that line, and before the `# ── Inline New Tag Creator` comment at line 4404, insert:

```python

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
                if not _case_closed and auth_manager.has_permission(_username, 'mark_exhibit'):
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
```

- [ ] **Step 2: Verify sqlite3 import exists at top of 4_Review.py**

Check that `import sqlite3` is in the imports (it should already be at line 4 based on the existing imports). If not, add it.

- [ ] **Step 3: Update version header in 4_Review.py**

Minor bump (new feature section added). Update `last_modified`, `modified_by`, `last_commit`.

- [ ] **Step 4: Add CHANGELOG entry**

```
- NEW: 4_Review.py — Exhibit designation section in coding panel: exhibit badges for produced docs + "Mark as Exhibit" expander with set/number/description fields
```

- [ ] **Step 5: Commit**

```bash
git add pages/4_Review.py CHANGELOG.md
git commit -m "feat: exhibit marking in Review coding panel (Phase 24c.7)"
```

---

### Task 4: Exhibits Management Page — Set Management + Exhibit List

**Files:**
- Create: `pages/8_Exhibits.py`

- [ ] **Step 1: Create 8_Exhibits.py with full page structure**

Create `pages/8_Exhibits.py` with the version header, access gates, exhibit set management, and exhibit list display:

```python
# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        8_Exhibits.py
# version:       1.0.0
# project:       DIY eDiscovery Hub
# project_ver:   2.9.0
# last_modified: <CURRENT_DATETIME>
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import os
import sqlite3
from datetime import datetime, date

import db_manager
import config
import auth_manager

st.set_page_config(page_title="Exhibits", layout="wide")
st.title("Module 7: Exhibits")

# ── Auth & Case Gate ─────────────────────────────────────────────────────────
# permission: view_exhibits
if not auth_manager.is_logged_in():
    st.warning("Please log in to access this module.")
    st.stop()

_username = st.session_state.get("username", "unknown")
auth_manager.require_role("reviewer")

case_folder = st.session_state.get("case_folder")
if not case_folder:
    st.info("Select a case from the Home page first.")
    st.stop()

_case_closed = st.session_state.get("case_status") == "Closed"
_is_manager = auth_manager.is_manager()

# ── Exhibit Set Selector ─────────────────────────────────────────────────────
exhibit_sets = db_manager.get_exhibit_sets(case_folder)
set_names = [es['set_name'] for es in exhibit_sets]

col_sel, col_new = st.columns([3, 1])

with col_sel:
    if set_names:
        selected_set_name = st.selectbox(
            "Exhibit Set",
            options=set_names,
            key="exhibits_set_selector",
        )
        selected_set = next(es for es in exhibit_sets if es['set_name'] == selected_set_name)
    else:
        st.info("No exhibit sets yet. Create one below to get started.")
        selected_set = None

# ── Create New Set (Manager+) ────────────────────────────────────────────────
# permission: manage_exhibit_sets
if _is_manager and not _case_closed:
    with col_new:
        st.write("")  # vertical spacer
        _show_create = st.button("New Set", use_container_width=True)

    if _show_create or not set_names:
        with st.expander("Create Exhibit Set", expanded=(not set_names)):
            _new_name = st.text_input("Set Name", placeholder="e.g., Deposition of John Smith")
            _type_col, _date_col = st.columns(2)
            with _type_col:
                _new_type = st.selectbox("Type", ["Deposition", "Motion", "Hearing", "Trial"])
            with _date_col:
                _new_date = st.date_input("Proceeding Date", value=None)
            _new_caption = st.text_input(
                "Case Caption Override (optional)",
                placeholder="Leave blank to use case-level caption",
            )
            if st.button("Create Set"):
                if not _new_name.strip():
                    st.error("Set name is required.")
                else:
                    try:
                        _new_id = db_manager.create_exhibit_set(
                            case_folder, _new_name.strip(), _new_type,
                            _new_date.isoformat() if _new_date else None,
                            _new_caption.strip() or None, _username
                        )
                        try:
                            db_manager.log_audit(
                                case_folder, "EXHIBIT_SET_CREATED",
                                username=_username, module="Exhibits",
                                details=f"Created set: {_new_name.strip()} ({_new_type})"
                            )
                        except Exception:
                            pass
                        st.success(f"Created exhibit set: {_new_name.strip()}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("An exhibit set with this name already exists.")

if not selected_set:
    st.stop()

# ── Set Details (Manager+ can edit) ──────────────────────────────────────────
# permission: manage_exhibit_sets
with st.expander("Set Details"):
    if _is_manager and not _case_closed:
        _edit_name = st.text_input("Set Name", value=selected_set['set_name'], key="edit_set_name")
        _e_col1, _e_col2 = st.columns(2)
        with _e_col1:
            _type_options = ["Deposition", "Motion", "Hearing", "Trial"]
            _type_idx = _type_options.index(selected_set['set_type']) if selected_set['set_type'] in _type_options else 0
            _edit_type = st.selectbox("Type", _type_options, index=_type_idx, key="edit_set_type")
        with _e_col2:
            _existing_date = None
            if selected_set.get('proceeding_date'):
                try:
                    _existing_date = date.fromisoformat(selected_set['proceeding_date'])
                except ValueError:
                    pass
            _edit_date = st.date_input("Proceeding Date", value=_existing_date, key="edit_set_date")
        _edit_caption = st.text_input(
            "Case Caption Override",
            value=selected_set.get('case_caption') or '',
            key="edit_set_caption",
        )

        _btn_col1, _btn_col2 = st.columns([1, 1])
        with _btn_col1:
            if st.button("Save Changes", key="save_set_details"):
                db_manager.update_exhibit_set(
                    case_folder, selected_set['id'],
                    set_name=_edit_name.strip(),
                    set_type=_edit_type,
                    proceeding_date=_edit_date.isoformat() if _edit_date else None,
                    case_caption=_edit_caption.strip() or None,
                )
                st.success("Set details updated.")
                st.rerun()
        with _btn_col2:
            if st.button("Delete Set", type="secondary", key="delete_set_btn"):
                st.session_state['_confirm_delete_set'] = True

            if st.session_state.get('_confirm_delete_set'):
                st.warning(f"Delete **{selected_set['set_name']}** and all its exhibits?")
                _dc1, _dc2 = st.columns(2)
                if _dc1.button("Yes, Delete", key="confirm_delete_yes"):
                    db_manager.delete_exhibit_set(case_folder, selected_set['id'])
                    try:
                        db_manager.log_audit(
                            case_folder, "EXHIBIT_SET_DELETED",
                            username=_username, module="Exhibits",
                            details=f"Deleted set: {selected_set['set_name']}"
                        )
                    except Exception:
                        pass
                    st.session_state.pop('_confirm_delete_set', None)
                    st.success("Exhibit set deleted.")
                    st.rerun()
                if _dc2.button("Cancel", key="confirm_delete_no"):
                    st.session_state.pop('_confirm_delete_set', None)
                    st.rerun()
    else:
        st.write(f"**Name:** {selected_set['set_name']}")
        st.write(f"**Type:** {selected_set['set_type']}")
        st.write(f"**Proceeding Date:** {selected_set.get('proceeding_date') or 'Not set'}")
        if selected_set.get('case_caption'):
            st.write(f"**Case Caption:** {selected_set['case_caption']}")

# ── Exhibit List ─────────────────────────────────────────────────────────────
st.subheader(f"Exhibits — {selected_set['set_name']}")

exhibits = db_manager.get_exhibits(case_folder, selected_set['id'])

if exhibits:
    for idx, ex in enumerate(exhibits):
        _bates = f"{ex.get('begdoc', '')} – {ex.get('enddoc', '')}" if ex.get('begdoc') else "N/A"
        _cols = st.columns([0.5, 1, 2.5, 2, 0.5, 1, 1])
        _cols[0].write(f"**{idx + 1}**")
        _cols[1].write(f"**{ex['exhibit_number']}**")
        _cols[2].write(ex.get('description') or '')
        _cols[3].code(_bates, language=None)
        _cols[4].write(str(ex.get('prod_page_count') or ex.get('page_count', '')))
        _cols[5].write(ex.get('custodian') or '')

        # Action buttons (Manager+)
        # permission: manage_exhibits
        if _is_manager and not _case_closed:
            with _cols[6]:
                _act_col1, _act_col2, _act_col3 = st.columns(3)
                if idx > 0:
                    if _act_col1.button("↑", key=f"up_{ex['id']}", help="Move up"):
                        _ordered = [e['id'] for e in exhibits]
                        _ordered[idx], _ordered[idx - 1] = _ordered[idx - 1], _ordered[idx]
                        db_manager.reorder_exhibits(case_folder, selected_set['id'], _ordered)
                        st.rerun()
                if idx < len(exhibits) - 1:
                    if _act_col2.button("↓", key=f"dn_{ex['id']}", help="Move down"):
                        _ordered = [e['id'] for e in exhibits]
                        _ordered[idx], _ordered[idx + 1] = _ordered[idx + 1], _ordered[idx]
                        db_manager.reorder_exhibits(case_folder, selected_set['id'], _ordered)
                        st.rerun()
                if _act_col3.button("✕", key=f"rm_{ex['id']}", help="Remove"):
                    db_manager.remove_exhibit(case_folder, ex['id'])
                    try:
                        db_manager.log_audit(
                            case_folder, "EXHIBIT_REMOVED",
                            username=_username, control_number=ex['control_number'],
                            module="Exhibits",
                            details=f"Removed Exhibit {ex['exhibit_number']} from {selected_set['set_name']}"
                        )
                    except Exception:
                        pass
                    st.rerun()

        st.markdown("<hr style='margin:2px 0; border:none; border-top:1px solid #e2e8f0;'>",
                    unsafe_allow_html=True)
else:
    st.info("No exhibits in this set yet. Add documents using the section below or mark them during Review.")

# ── Add Document to Set (Manager+) ───────────────────────────────────────────
# permission: manage_exhibits
if _is_manager and not _case_closed:
    with st.expander("Add Document to Set"):
        _search_q = st.text_input(
            "Search produced documents",
            placeholder="File name, custodian, or Bates number...",
            key="ex_doc_search",
        )
        if _search_q.strip():
            _existing_cns = {ex['control_number'] for ex in exhibits}
            conn = db_manager.get_connection(case_folder)
            try:
                _search_results = conn.execute("""
                    SELECT d.control_number, d.file_name, d.custodian,
                           dp.begdoc, dp.enddoc, dp.page_count
                    FROM documents d
                    JOIN document_productions dp ON d.control_number = dp.control_number
                        AND dp.produced_at = (
                            SELECT MAX(dp2.produced_at)
                            FROM document_productions dp2
                            WHERE dp2.control_number = d.control_number
                        )
                    WHERE d.control_number NOT IN ({','.join('?' * len(_existing_cns))})
                      AND (d.file_name LIKE ? OR d.custodian LIKE ?
                           OR dp.begdoc LIKE ? OR d.control_number LIKE ?)
                    LIMIT 25
                """, (
                    *_existing_cns,
                    f"%{_search_q}%", f"%{_search_q}%",
                    f"%{_search_q}%", f"%{_search_q}%",
                )).fetchall()
            finally:
                conn.close()

            if _search_results:
                for _sr in _search_results:
                    _sr_dict = dict(_sr)
                    _sr_bates = f"{_sr_dict.get('begdoc', '')} – {_sr_dict.get('enddoc', '')}"
                    _sr_cols = st.columns([2, 2, 2, 1.5, 1.5])
                    _sr_cols[0].write(_sr_dict['control_number'])
                    _sr_cols[1].write(_sr_dict.get('file_name', ''))
                    _sr_cols[2].code(_sr_bates, language=None)
                    _add_num = _sr_cols[3].text_input(
                        "Ex #", key=f"add_num_{_sr_dict['control_number']}",
                        label_visibility="collapsed", placeholder="Ex #",
                    )
                    if _sr_cols[4].button("Add", key=f"add_btn_{_sr_dict['control_number']}"):
                        if not _add_num.strip():
                            st.error("Exhibit number required.")
                        else:
                            _next_order = db_manager.get_next_sort_order(
                                case_folder, selected_set['id']
                            )
                            try:
                                db_manager.add_exhibit(
                                    case_folder, selected_set['id'],
                                    _sr_dict['control_number'], _add_num.strip(),
                                    '', _next_order, _username,
                                )
                                try:
                                    db_manager.log_audit(
                                        case_folder, "EXHIBIT_ADDED",
                                        username=_username,
                                        control_number=_sr_dict['control_number'],
                                        module="Exhibits",
                                        details=f"Exhibit {_add_num.strip()} in {selected_set['set_name']}"
                                    )
                                except Exception:
                                    pass
                                st.success(f"Added as Exhibit {_add_num.strip()}")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error(
                                    "Exhibit number already used in this set, "
                                    "or document already in this set."
                                )
            else:
                st.caption("No matching produced documents found.")
```

- [ ] **Step 2: Add CHANGELOG entry**

```
- NEW: 8_Exhibits.py — Exhibits management page: set CRUD (create/edit/delete), exhibit list with reorder/remove, add-document search for produced docs
```

- [ ] **Step 3: Commit**

```bash
git add pages/8_Exhibits.py CHANGELOG.md
git commit -m "feat: Exhibits management page — set CRUD and exhibit list (Phase 24c.7)"
```

---

### Task 5: Binder PDF Export

**Files:**
- Modify: `pages/8_Exhibits.py` (add export section at the bottom)

- [ ] **Step 1: Add binder generation function**

At the top of `8_Exhibits.py`, after the existing imports, add:

```python
import fitz  # PyMuPDF

try:
    import pdfkit
    PDFKIT_AVAILABLE = True
except ImportError:
    PDFKIT_AVAILABLE = False
```

Then, after the import block but before `st.set_page_config(...)`, add the binder generation function:

```python
def _generate_binder_pdf(case_folder, exhibit_set, exhibits_list):
    """
    Assemble a binder PDF: cover sheet → index → (divider + document) per exhibit.
    Returns (pdf_bytes, warnings_list).
    """
    wk_cfg = pdfkit.configuration(wkhtmltopdf=config.WKHTMLTOPDF_PATH)
    wk_opts = {
        'page-size': 'Letter',
        'orientation': 'Portrait',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': 'UTF-8',
        'no-outline': None,
        'enable-local-file-access': None,
    }
    warnings = []

    # ── Resolve produced PDF paths and page counts ────────────────────
    exhibit_pages = []  # list of (exhibit, pdf_path, page_count)
    for ex in exhibits_list:
        vol = ex.get('production_volume')
        begdoc = ex.get('begdoc')
        if not vol or not begdoc:
            warnings.append(f"Exhibit {ex['exhibit_number']}: no production record found")
            exhibit_pages.append((ex, None, 0))
            continue
        pdf_path = os.path.join(case_folder, "Productions", vol, "IMAGES", f"{begdoc}.pdf")
        if not os.path.exists(pdf_path):
            warnings.append(f"Exhibit {ex['exhibit_number']}: PDF not found at {pdf_path}")
            exhibit_pages.append((ex, None, 0))
            continue
        src = fitz.open(pdf_path)
        pc = src.page_count
        src.close()
        exhibit_pages.append((ex, pdf_path, pc))

    # ── Calculate page numbers for index ──────────────────────────────
    # Cover = 1 page. Index = 1 page (re-render if >25 exhibits later).
    # Each exhibit = 1 divider + N document pages.
    cover_pages = 1
    # First pass: estimate index at 1 page
    index_pages_est = max(1, (len(exhibits_list) + 24) // 25)
    binder_page = cover_pages + index_pages_est + 1  # +1 for first divider
    index_entries = []
    for ex, pdf_path, pc in exhibit_pages:
        bates = f"{ex.get('begdoc', '')} – {ex.get('enddoc', '')}" if ex.get('begdoc') else "N/A"
        index_entries.append({
            'exhibit_number': ex['exhibit_number'],
            'description': ex.get('description') or '',
            'bates': bates,
            'binder_page': binder_page,
        })
        binder_page += pc + 1  # document pages + next divider

    # ── Build case caption ────────────────────────────────────────────
    caption = exhibit_set.get('case_caption') or ''
    if not caption:
        conn = db_manager.get_connection(case_folder)
        try:
            row = conn.execute(
                "SELECT value FROM case_settings WHERE key = 'case_caption'"
            ).fetchone()
            caption = row[0] if row else os.path.basename(case_folder)
        except Exception:
            caption = os.path.basename(case_folder)
        finally:
            conn.close()

    proc_date = exhibit_set.get('proceeding_date') or ''

    # ── Render Cover HTML ─────────────────────────────────────────────
    cover_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  @page {{ size: letter portrait; margin: 1in; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #000;
         text-align: center; padding-top: 2.5in; margin: 0; }}
  .rule {{ width: 40%; height: 1px; background: #000; margin: 28px auto; }}
  .caption {{ font-size: 18pt; font-weight: bold; margin-bottom: 6px; }}
  .sub {{ font-size: 12pt; color: #333; margin-bottom: 28px; }}
  .set-name {{ font-size: 15pt; font-weight: bold; margin-bottom: 4px; }}
  .date {{ font-size: 12pt; color: #333; margin-bottom: 28px; }}
  .label {{ font-size: 12pt; letter-spacing: 2px; text-transform: uppercase; }}
  .conf {{ font-size: 9pt; color: #555; font-style: italic; margin-top: 120px; }}
</style></head><body>
  <div class="caption">{caption}</div>
  <div class="rule"></div>
  <div class="set-name">{exhibit_set['set_name']}</div>
  <div class="date">{proc_date}</div>
  <div class="rule"></div>
  <div class="label">Exhibit Binder</div>
  <div class="conf">Confidential — Subject to Protective Order</div>
</body></html>"""

    # ── Render Index HTML ─────────────────────────────────────────────
    index_rows = ""
    for ie in index_entries:
        index_rows += (
            f"<tr><td style='padding:5px 8px; font-weight:bold;'>{ie['exhibit_number']}</td>"
            f"<td style='padding:5px 8px;'>{ie['description']}</td>"
            f"<td style='padding:5px 8px; font-family:Courier New,monospace; font-size:9pt;'>{ie['bates']}</td>"
            f"<td style='padding:5px 8px; text-align:right;'>{ie['binder_page']}</td></tr>\n"
        )

    index_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  @page {{ size: letter portrait; margin: 0.75in; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #000; margin: 0; padding: 0; }}
  h2 {{ text-align: center; font-size: 14pt; margin-bottom: 4px; }}
  .sub {{ text-align: center; font-size: 10pt; color: #555; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10pt; }}
  th {{ text-align: left; padding: 5px 8px; border-bottom: 2px solid #000; }}
  th:last-child {{ text-align: right; }}
  td {{ border-bottom: 1px solid #ccc; }}
</style></head><body>
  <h2>INDEX OF EXHIBITS</h2>
  <div class="sub">{exhibit_set['set_name']} — {proc_date}</div>
  <table>
    <thead><tr>
      <th style="width:10%;">Exhibit</th>
      <th style="width:45%;">Description</th>
      <th style="width:25%;">Bates Range</th>
      <th style="width:20%;">Binder Page</th>
    </tr></thead>
    <tbody>{index_rows}</tbody>
  </table>
</body></html>"""

    # ── Render Divider HTMLs ──────────────────────────────────────────
    def _divider_html(ex, pc):
        bates = f"{ex.get('begdoc', '')} – {ex.get('enddoc', '')}" if ex.get('begdoc') else "N/A"
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  @page {{ size: letter portrait; margin: 1in; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #000;
         display: flex; flex-direction: column; justify-content: center;
         align-items: center; text-align: center; min-height: 8in;
         margin: 0; padding: 0; }}
  .set {{ font-size: 10pt; letter-spacing: 2px; text-transform: uppercase;
          color: #555; margin-bottom: 24px; }}
  .rule {{ width: 60px; height: 2px; background: #000; margin-bottom: 24px; }}
  .exnum {{ font-size: 28pt; font-weight: bold; margin-bottom: 12px; }}
  .rule2 {{ width: 60px; height: 1px; background: #555; margin: 14px auto; }}
  .desc {{ font-size: 12pt; color: #333; max-width: 400px; line-height: 1.5; }}
  .bates {{ font-size: 10pt; font-family: 'Courier New', monospace; color: #555; margin-top: 12px; }}
  .pages {{ font-size: 9pt; color: #555; margin-top: 4px; }}
</style></head><body>
  <div class="set">{exhibit_set['set_name']}</div>
  <div class="rule"></div>
  <div class="exnum">Exhibit {ex['exhibit_number']}</div>
  <div class="rule2"></div>
  <div class="desc">{ex.get('description') or ''}</div>
  <div class="bates">{bates}</div>
  <div class="pages">{pc} page{'s' if pc != 1 else ''}</div>
</body></html>"""

    # ── Placeholder for missing documents ─────────────────────────────
    def _placeholder_html(ex):
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  @page {{ size: letter portrait; margin: 1in; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #000;
         display: flex; flex-direction: column; justify-content: center;
         align-items: center; text-align: center; min-height: 8in; margin: 0; }}
</style></head><body>
  <div style="font-size:16pt; font-weight:bold; margin-bottom:16px;">
    Exhibit {ex['exhibit_number']}</div>
  <div style="font-size:12pt; color:#555;">Document Not Available</div>
  <div style="font-size:10pt; color:#888; margin-top:8px;">
    {ex['control_number']}</div>
</body></html>"""

    # ── Assemble PDF ──────────────────────────────────────────────────
    merged = fitz.open()
    try:
        # Cover
        cover_bytes = pdfkit.from_string(cover_html, False, options=wk_opts, configuration=wk_cfg)
        cover_doc = fitz.open(stream=cover_bytes, filetype="pdf")
        merged.insert_pdf(cover_doc)
        cover_doc.close()

        # Index
        index_bytes = pdfkit.from_string(index_html, False, options=wk_opts, configuration=wk_cfg)
        index_doc = fitz.open(stream=index_bytes, filetype="pdf")
        merged.insert_pdf(index_doc)
        index_doc.close()

        # Exhibits
        for ex, pdf_path, pc in exhibit_pages:
            # Divider
            div_bytes = pdfkit.from_string(
                _divider_html(ex, pc if pdf_path else 0),
                False, options=wk_opts, configuration=wk_cfg
            )
            div_doc = fitz.open(stream=div_bytes, filetype="pdf")
            merged.insert_pdf(div_doc)
            div_doc.close()

            # Document (or placeholder)
            if pdf_path:
                src = fitz.open(pdf_path)
                merged.insert_pdf(src)
                src.close()
            else:
                ph_bytes = pdfkit.from_string(
                    _placeholder_html(ex), False, options=wk_opts, configuration=wk_cfg
                )
                ph_doc = fitz.open(stream=ph_bytes, filetype="pdf")
                merged.insert_pdf(ph_doc)
                ph_doc.close()

        return merged.tobytes(), warnings
    finally:
        merged.close()
```

- [ ] **Step 2: Add export section to the page**

At the bottom of `8_Exhibits.py`, after the "Add Document to Set" expander block, add:

```python
# ── Export Binder PDF (Manager+) ─────────────────────────────────────────────
# permission: export_exhibit_binder
if _is_manager and not _case_closed and exhibits:
    st.markdown("---")
    st.subheader("Export")

    if not PDFKIT_AVAILABLE:
        st.error("pdfkit is not installed. Binder export requires pdfkit and wkhtmltopdf.")
    else:
        if st.button("Generate Binder PDF", type="primary"):
            with st.spinner("Assembling binder PDF..."):
                try:
                    pdf_bytes, warnings = _generate_binder_pdf(
                        case_folder, selected_set, exhibits
                    )
                    if warnings:
                        for w in warnings:
                            st.warning(w)
                    st.session_state['_binder_pdf'] = pdf_bytes
                    st.session_state['_binder_name'] = selected_set['set_name']
                    try:
                        db_manager.log_audit(
                            case_folder, "EXHIBIT_BINDER_EXPORTED",
                            username=_username, module="Exhibits",
                            details=f"Binder for {selected_set['set_name']} — {len(exhibits)} exhibits"
                        )
                    except Exception:
                        pass
                    st.success(
                        f"Binder ready — {len(exhibits)} exhibits, "
                        f"{len([w for w in warnings])} warnings."
                    )
                except Exception as e:
                    st.error(f"Binder generation failed: {e}")

        if st.session_state.get('_binder_pdf'):
            _safe_name = "".join(
                c if c.isalnum() or c in (' ', '-', '_') else '_'
                for c in st.session_state.get('_binder_name', 'Exhibit_Binder')
            ).strip().replace(' ', '_')
            st.download_button(
                "Download Binder PDF",
                data=st.session_state['_binder_pdf'],
                file_name=f"{_safe_name}_Exhibit_Binder.pdf",
                mime="application/pdf",
            )
```

- [ ] **Step 3: Update version header in 8_Exhibits.py**

The file was just created at 1.0.0 in Task 4 — bump to 1.1.0 (new function added). Update `last_modified`.

- [ ] **Step 4: Add CHANGELOG entry**

```
- NEW: 8_Exhibits.py — Binder PDF export: cover sheet, index with binder page numbers, per-exhibit divider pages, assembled via pdfkit + PyMuPDF
```

- [ ] **Step 5: Commit**

```bash
git add pages/8_Exhibits.py CHANGELOG.md
git commit -m "feat: exhibit binder PDF export with cover/index/dividers (Phase 24c.7)"
```

---

### Task 6: DEPENDENCY_MAP.md + CHANGELOG Finalization

**Files:**
- Modify: `DEPENDENCY_MAP.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update DEPENDENCY_MAP.md**

Add the new tables and cross-module references. Find section §1 (Database Schema) and add:

```markdown
### exhibit_sets
| Column | Consumers | Notes |
|--------|-----------|-------|
| `id` | `exhibits.exhibit_set_id` (FK), `8_Exhibits.py`, `4_Review.py` | PK, auto-increment |
| `case_folder` | `8_Exhibits.py` | Used for all queries |
| `set_name` | `8_Exhibits.py`, `4_Review.py` (badge display) | UNIQUE with case_folder |

### exhibits
| Column | Consumers | Notes |
|--------|-----------|-------|
| `exhibit_set_id` | `db_manager.get_exhibits()`, `8_Exhibits.py` | FK → exhibit_sets, CASCADE delete |
| `control_number` | `4_Review.py` (badge lookup), `8_Exhibits.py` (binder PDF path resolution) | FK → documents |
| `exhibit_number` | `4_Review.py` (badge), `8_Exhibits.py` (list + binder) | Freeform text, UNIQUE per set |
| `sort_order` | `8_Exhibits.py` (reorder), `db_manager.get_exhibits()` (ORDER BY) | Determines binder sequence |
```

Add to cross-module references section:

```markdown
### Exhibit cross-module dependencies
- `db_manager.get_document_exhibit_sets()` → consumed by `4_Review.py` coding panel
- `db_manager.get_exhibit_sets()` → consumed by `4_Review.py` (set dropdown) and `8_Exhibits.py`
- `document_productions.production_volume` + `begdoc` → consumed by `8_Exhibits.py` binder export for PDF path resolution
- `auth_manager.ALL_PERMISSIONS` → `mark_exhibit`, `view_exhibits`, `manage_exhibit_sets`, `manage_exhibits`, `export_exhibit_binder`
```

- [ ] **Step 2: Add CHANGELOG wrap-up entry**

Ensure the CHANGELOG has a phase header if not already present:

```
- DOCS: DEPENDENCY_MAP.md — added exhibit_sets and exhibits table cross-references
```

- [ ] **Step 3: Commit**

```bash
git add DEPENDENCY_MAP.md CHANGELOG.md
git commit -m "docs: DEPENDENCY_MAP.md — exhibit tables and cross-module references"
```

---

### Task 7: Context Maintenance

**Files:**
- Modify: `CLAUDE.md` (Current State table)
- Modify: memory files

- [ ] **Step 1: Update CLAUDE.md Current State table**

Update the fields:
- `Last completed sprint` → `Phase 24c.7: Exhibit List / Trial Binder (beta-2.9)`
- `What's next` → `See ROADMAP_TODO.md — Module Hardening Sprints 3-4, Holistic Audit Passes 3-9`

- [ ] **Step 2: Update ROADMAP_TODO.md**

Mark the exhibit list item as complete:
```
7. [x]   Exhibit List / Trial Binder — exhibits table with exhibit numbers, descriptions, deposition names; ordered PDF binder export with cover sheet and index
```

- [ ] **Step 3: Update memory/project_state.md**

Update to reflect completed work and what's next.

- [ ] **Step 4: Add CHANGELOG entry**

```
- DOCS: CLAUDE.md — context maintenance after Phase 24c.7
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md ROADMAP_TODO.md CHANGELOG.md
git commit -m "docs: context maintenance after Phase 24c.7 Exhibit List"
```
