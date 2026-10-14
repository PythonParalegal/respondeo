# Phase 24a: EDRM Defensibility Gaps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 4 highest-priority defensibility gaps: collection scope documentation, hash integrity verification, session timeout, and De-NIST configurability.

**Architecture:** All 4 items are independent. Items 1 and 4 add new DB helpers + UI. Item 2 adds a verification tool to the dashboard. Item 3 modifies the auth gate. Each task produces a self-contained, committable change.

**Tech Stack:** Python, Streamlit, SQLite (via db_manager.py), PyYAML (auth_config.yaml)

**Spec:** `docs/superpowers/specs/2026-03-26-edrm-defensibility-design.md`

**Version tracking:** Every `.py` file edit must update the metadata header (`version`, `last_modified`, `modified_by`). Add CHANGELOG.md entries per functional change. See `CLAUDE.md` for full rules.

---

## File Map

| File | Tasks | Changes |
|------|-------|---------|
| `db_manager.py` | 1, 2, 5 | New `collection_scope` table in `init_db()`, 4 scope functions, 2 NIST extension functions |
| `pages/7_Custodians.py` | 2 | New "Collection Scope" tab in Operations section |
| `defensibility_report.py` | 3 | New Section 2.2 with collection scope table |
| `auth_manager.py` | 4 | Session timeout logic in `check_login()` |
| `auth_config.yaml` | 4 | New `session_timeout_minutes` key |
| `home.py` | 5, 6 | Hash verification section + De-NIST config section in Case Maintenance |
| `pages/2_Processor.py` | 6 | Load NIST extensions from DB instead of hardcoded set |

---

## Task 1: Collection Scope — Database Layer

**Files:**
- Modify: `db_manager.py:493-497` (add CREATE TABLE before `conn.commit()` in `init_db()`)
- Modify: `db_manager.py` (add new functions after the custodians section, ~line 470)

- [ ] **Step 1: Add `collection_scope` table to `init_db()`**

In `db_manager.py`, find the line `conn.commit()` near line 497 inside `init_db()`. Insert before it:

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collection_scope (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                custodian_id INTEGER NOT NULL,
                source_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending','Collected','Searched-No-Hit',
                                      'Not-Reasonably-Accessible','Out-of-Scope')),
                justification TEXT,
                reviewed_by TEXT,
                reviewed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (custodian_id) REFERENCES custodians(id) ON DELETE CASCADE,
                UNIQUE(custodian_id, source_name)
            )
        """)
```

- [ ] **Step 2: Add `get_collection_scope()` function**

Add after the custodians section (after the last custodian function, around line 470):

```python
# ---------------------------------------------------------------------------
# COLLECTION SCOPE
# ---------------------------------------------------------------------------

def get_collection_scope(case_folder, custodian_id):
    """Return all collection scope rows for a given custodian."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute(
            "SELECT * FROM collection_scope WHERE custodian_id = ? ORDER BY source_name",
            (custodian_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
```

- [ ] **Step 3: Add `upsert_collection_scope()` function**

```python
def upsert_collection_scope(case_folder, custodian_id, source_name, status,
                            justification, reviewed_by):
    """Insert or update a collection scope entry."""
    conn = get_connection(case_folder)
    try:
        conn.execute("""
            INSERT INTO collection_scope
                (custodian_id, source_name, status, justification, reviewed_by, reviewed_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(custodian_id, source_name) DO UPDATE SET
                status = excluded.status,
                justification = excluded.justification,
                reviewed_by = excluded.reviewed_by,
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
        """, (custodian_id, source_name, status, justification, reviewed_by))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Add `get_all_collection_scope()` function**

```python
def get_all_collection_scope(case_folder):
    """Return all collection scope rows joined with custodian names (for reports)."""
    conn = get_connection(case_folder)
    try:
        rows = conn.execute("""
            SELECT c.name AS custodian, cs.source_name, cs.status,
                   cs.justification, cs.reviewed_by, cs.reviewed_at
            FROM collection_scope cs
            JOIN custodians c ON c.id = cs.custodian_id
            ORDER BY c.name, cs.source_name
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
```

- [ ] **Step 5: Add `seed_collection_scope()` function**

```python
def seed_collection_scope(case_folder, custodian_id, source_names):
    """Bulk-insert Pending scope entries for sources not yet tracked."""
    conn = get_connection(case_folder)
    try:
        for src in source_names:
            conn.execute("""
                INSERT OR IGNORE INTO collection_scope (custodian_id, source_name, status)
                VALUES (?, ?, 'Pending')
            """, (custodian_id, src))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 6: Update version header and CHANGELOG**

Bump `db_manager.py` version (minor bump — new functions added). Add CHANGELOG entry:
`- NEW: db_manager.py — collection_scope table + 4 CRUD functions (get, upsert, get_all, seed)`

---

## Task 2: Collection Scope — Custodians UI

**Files:**
- Modify: `pages/7_Custodians.py:198` (add tab to tabs definition)
- Modify: `pages/7_Custodians.py:450` (add new tab content after collections_tab)

- [ ] **Step 1: Add "Collection Scope" tab to the tabs definition**

At line 198, change the tabs definition from 4 tabs to 5:

```python
    rename_tab, merge_tab, reassign_tab, collections_tab, scope_tab = st.tabs(
        ["✏️ Rename", "🔀 Merge", "📦 Reassign", "📁 Collections", "📋 Collection Scope"]
    )
```

- [ ] **Step 2: Add scope_tab content after collections_tab block**

After the end of `with collections_tab:` (around line 450), add:

```python
        with scope_tab:
            if not selected_custodian:
                st.info("Select a custodian above to manage collection scope.")
            else:
                # Get custodian ID
                _cust_row = conn_cust.execute(
                    "SELECT id, data_sources FROM custodians WHERE name = ?",
                    (selected_custodian,)
                ).fetchone()
                if not _cust_row:
                    st.warning("Custodian not found in database.")
                else:
                    _cust_id = _cust_row['id']
                    _data_sources = json.loads(_cust_row['data_sources'] or '[]')

                    # Auto-seed any data_sources not yet in collection_scope
                    if _data_sources:
                        db_manager.seed_collection_scope(case_folder, _cust_id, _data_sources)

                    # Load current scope entries
                    _scope_rows = db_manager.get_collection_scope(case_folder, _cust_id)

                    if not _scope_rows:
                        st.info(
                            "No collection sources configured. Add data sources in the "
                            "custodian detail panel above, or enter sources manually below."
                        )
                        # Manual add form
                        with st.form("add_scope_source", clear_on_submit=True):
                            _new_src = st.text_input("Source Name (e.g., 'Exchange Mailbox')")
                            if st.form_submit_button("Add Source", width='stretch'):
                                if _new_src.strip():
                                    db_manager.upsert_collection_scope(
                                        case_folder, _cust_id, _new_src.strip(),
                                        'Pending', '', st.session_state.get('username', '')
                                    )
                                    st.rerun()
                    else:
                        _status_options = [
                            'Pending', 'Collected', 'Searched-No-Hit',
                            'Not-Reasonably-Accessible', 'Out-of-Scope'
                        ]

                        # Completeness indicator
                        _documented = sum(1 for r in _scope_rows if r['status'] != 'Pending')
                        _total_src = len(_scope_rows)
                        if _documented == _total_src:
                            st.success(f"All {_total_src} sources documented.")
                        else:
                            st.warning(f"{_documented} of {_total_src} sources documented. "
                                       f"{_total_src - _documented} still pending.")

                        # Editable form for each source
                        with st.form("scope_form"):
                            _updates = []
                            for row in _scope_rows:
                                st.markdown(f"**{row['source_name']}**")
                                _col_s, _col_j = st.columns([1, 2])
                                with _col_s:
                                    _new_status = st.selectbox(
                                        "Status",
                                        _status_options,
                                        index=_status_options.index(row['status']),
                                        key=f"scope_status_{row['id']}",
                                        label_visibility="collapsed",
                                    )
                                with _col_j:
                                    _new_just = st.text_area(
                                        "Justification",
                                        value=row['justification'] or '',
                                        key=f"scope_just_{row['id']}",
                                        height=68,
                                        label_visibility="collapsed",
                                        placeholder="Justification / notes…",
                                    )
                                _updates.append((row['source_name'], _new_status, _new_just))
                                if row['reviewed_by']:
                                    st.caption(
                                        f"Last reviewed by {row['reviewed_by']} "
                                        f"on {row['reviewed_at'] or '—'}"
                                    )
                                st.markdown("---")

                            _save_col, _add_col = st.columns(2)
                            with _save_col:
                                _save = st.form_submit_button(
                                    "💾 Save All", width='stretch'
                                )
                            with _add_col:
                                _new_manual = st.text_input(
                                    "Add source:",
                                    placeholder="New source name…",
                                    label_visibility="collapsed",
                                )

                        if _save:
                            _username = st.session_state.get('username', '')
                            for src_name, status, justification in _updates:
                                db_manager.upsert_collection_scope(
                                    case_folder, _cust_id, src_name,
                                    status, justification, _username
                                )
                            if _new_manual and _new_manual.strip():
                                db_manager.upsert_collection_scope(
                                    case_folder, _cust_id, _new_manual.strip(),
                                    'Pending', '', _username
                                )
                            try:
                                db_manager.log_audit(
                                    case_folder,
                                    action="COLLECTION_SCOPE_UPDATED",
                                    user=_username,
                                    module="Custodians",
                                    details=json.dumps({
                                        "custodian": selected_custodian,
                                        "sources_updated": len(_updates),
                                    })
                                )
                            except Exception:
                                pass
                            st.success("Collection scope saved.")
                            st.rerun()
```

- [ ] **Step 3: Ensure `json` is imported at top of file**

Check if `import json` is already present. If not, add it to the imports section.

- [ ] **Step 4: Update version header and CHANGELOG**

Bump `7_Custodians.py` version (minor bump — new tab added). Add CHANGELOG entry:
`- NEW: 7_Custodians.py — Collection Scope tab with per-custodian per-source status tracking and justification`

---

## Task 3: Collection Scope — Defensibility Report

**Files:**
- Modify: `defensibility_report.py:808` (add Section 2.2 after Section 2.1)

- [ ] **Step 1: Add `_collect_collection_scope()` helper**

Add a new helper function near the other `_collect_*` functions (around line 160):

```python
def _collect_collection_scope(case_folder):
    """Collect all collection scope data for the defensibility report."""
    try:
        return db_manager.get_all_collection_scope(case_folder)
    except Exception:
        return []
```

- [ ] **Step 2: Call the helper in the main report generation**

Find where `ingestion = _collect_ingestion_stats(case_folder)` is called (in the main report generation function). Add after it:

```python
    collection_scope = _collect_collection_scope(case_folder)
```

- [ ] **Step 3: Add Section 2.2 HTML after Section 2.1**

Find the closing `</table>` after the custodian breakdown (around line 808). Insert after it:

```python
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
```

- [ ] **Step 4: Update version header and CHANGELOG**

Bump `defensibility_report.py` version (minor bump). Add CHANGELOG entry:
`- NEW: defensibility_report.py — Section 2.2 Collection Scope & Justification in defensibility report`

---

## Task 4: Session Timeout / Auto-Logout

**Files:**
- Modify: `auth_manager.py:156-202` (add timeout logic to `check_login()`)
- Modify: `auth_config.yaml` (add `session_timeout_minutes` key)

- [ ] **Step 1: Add `session_timeout_minutes` to auth_config.yaml**

Add at the top of the file (before `custom_roles`):

```yaml
# Session timeout in minutes (0 = disabled). Forces re-login after inactivity.
session_timeout_minutes: 30
```

- [ ] **Step 2: Add `import time` to auth_manager.py if not present**

Check the imports section. If `import time` is not present, add it alongside the other imports.

- [ ] **Step 3: Add timeout check in `check_login()` after authentication gate**

In `check_login()`, find the block starting at `if st.session_state.get('authenticated'):` (around line 162). Replace the entire authenticated block with:

```python
    if st.session_state.get('authenticated'):
        # ── Session timeout check ────────────────────────────────────
        _timeout_minutes = _load_config().get('session_timeout_minutes', 30)
        if _timeout_minutes and _timeout_minutes > 0:
            _last_activity = st.session_state.get('last_activity_time', 0)
            if _last_activity and (time.time() - _last_activity) > (_timeout_minutes * 60):
                # Session expired — force re-login
                for _key in ('authenticated', 'username', 'user_role', 'display_name',
                             'last_activity_time'):
                    st.session_state.pop(_key, None)
                st.warning("⏱️ Session expired due to inactivity. Please log in again.")
                return False
        # Update activity timestamp
        st.session_state['last_activity_time'] = time.time()

        # Enforce case-access restriction on every page load.
        _cf = st.session_state.get('current_case_folder')
        if _cf:
            _uname = st.session_state.get('username', '')
            _allowed = get_allowed_cases(_uname)
            if _allowed is not None and _cf not in _allowed:
                st.session_state.pop('current_case_folder', None)
        return True
```

- [ ] **Step 4: Set initial activity timestamp on login**

Find the line `st.session_state['authenticated'] = True` inside the successful login block (around line 191). Add immediately after the existing session state assignments (after `st.session_state['display_name'] = ...`):

```python
                st.session_state['last_activity_time'] = time.time()
```

- [ ] **Step 5: Update version header and CHANGELOG**

Bump `auth_manager.py` version (minor bump — new feature). Add CHANGELOG entry:
`- NEW: auth_manager.py — session timeout / auto-logout after configurable inactivity period (default 30 min)`

---

## Task 5: Hash Integrity Verification

**Files:**
- Modify: `home.py:592-654` (add section inside Case Maintenance expander)

- [ ] **Step 1: Add "Verify Document Integrity" section in Case Maintenance expander**

Find the end of the Factory Reset section inside the Case Maintenance expander (around line 654). Add after it:

```python
            # ── Hash Integrity Verification ──────────────────────────────
            st.divider()
            st.subheader("🔍 Verify Document Integrity")
            st.caption(
                "Re-compute MD5 hashes for all ingested files and compare against "
                "stored values. Detects accidental modification, corruption, or "
                "missing files."
            )
            # permission: verify_integrity
            if st.button("Run Integrity Check", key="btn_verify_integrity",
                         width='stretch'):
                import hashlib
                _conn_v = db_manager.get_connection(case_folder)
                try:
                    _docs = _conn_v.execute(
                        "SELECT control_number, file_name, full_path, md5_hash "
                        "FROM documents WHERE full_path IS NOT NULL AND md5_hash IS NOT NULL"
                    ).fetchall()
                finally:
                    _conn_v.close()

                if not _docs:
                    st.info("No documents with stored hashes found.")
                else:
                    _total = len(_docs)
                    _matches = 0
                    _mismatches = []
                    _missing = []
                    _progress = st.progress(0, text="Verifying…")

                    for idx, doc in enumerate(_docs):
                        _progress.progress(
                            (idx + 1) / _total,
                            text=f"Verifying {idx + 1} / {_total}…"
                        )
                        fpath = doc['full_path']
                        if not os.path.isfile(fpath):
                            _missing.append({
                                'Control Number': doc['control_number'],
                                'File Name': doc['file_name'],
                                'Expected Path': fpath,
                            })
                            continue
                        # Compute MD5
                        _h = hashlib.md5()
                        try:
                            with open(fpath, 'rb') as _f:
                                for _chunk in iter(lambda: _f.read(8192), b''):
                                    _h.update(_chunk)
                            _actual = _h.hexdigest()
                        except Exception:
                            _actual = None

                        if _actual == doc['md5_hash']:
                            _matches += 1
                        else:
                            _mismatches.append({
                                'Control Number': doc['control_number'],
                                'File Name': doc['file_name'],
                                'Expected Hash': doc['md5_hash'],
                                'Actual Hash': _actual or 'ERROR',
                            })

                    _progress.empty()

                    # Display results
                    rc1, rc2, rc3, rc4 = st.columns(4)
                    rc1.metric("Total Verified", _total)
                    rc2.metric("Matches ✅", _matches)
                    rc3.metric("Mismatches ⚠️", len(_mismatches))
                    rc4.metric("Missing Files ❌", len(_missing))

                    if _mismatches:
                        st.error(f"{len(_mismatches)} file(s) have been modified since ingestion!")
                        st.dataframe(pd.DataFrame(_mismatches), width='stretch',
                                     hide_index=True)

                    if _missing:
                        st.warning(f"{len(_missing)} file(s) are missing from disk!")
                        st.dataframe(pd.DataFrame(_missing), width='stretch',
                                     hide_index=True)

                    if not _mismatches and not _missing:
                        st.success("All files verified — no integrity issues detected.")

                    # Audit log
                    try:
                        db_manager.log_audit(
                            case_folder,
                            action="INTEGRITY_VERIFICATION",
                            user=st.session_state.get('username', ''),
                            module="Home",
                            details=json.dumps({
                                'total': _total, 'matches': _matches,
                                'mismatches': len(_mismatches),
                                'missing': len(_missing),
                            })
                        )
                    except Exception:
                        pass
```

- [ ] **Step 2: Ensure `import hashlib` is available**

The `import hashlib` is inline (inside the button click block) to avoid loading it on every page render. No top-level import needed.

- [ ] **Step 3: Update version header and CHANGELOG**

Bump `home.py` version (minor bump — new feature). Add CHANGELOG entry:
`- NEW: home.py — Hash Integrity Verification in Case Maintenance (re-hashes all files, flags mismatches/missing)`

---

## Task 6: De-NIST Configurability

**Files:**
- Modify: `db_manager.py` (add 2 NIST extension functions)
- Modify: `home.py:654+` (add De-NIST config UI in Case Maintenance)
- Modify: `pages/2_Processor.py:511-518` (load from DB instead of hardcoded)

- [ ] **Step 1: Add NIST extension functions to db_manager.py**

Add after the collection scope functions:

```python
# ---------------------------------------------------------------------------
# DE-NIST CONFIGURATION
# ---------------------------------------------------------------------------

# Default NIST extensions — used as fallback when no case-level config exists
DEFAULT_NIST_EXTENSIONS = [
    '.exe', '.dll', '.sys', '.drv', '.ocx', '.cpl', '.scr',
    '.msi', '.msp', '.mst', '.cab', '.cat', '.inf',
    '.tmp', '.temp', '.log', '.dmp', '.etl',
    '.lnk', '.url', '.ini', '.dat', '.db-journal',
    '.thumbs.db', '.ds_store',
    '.pf', '.mui', '.nls', '.tlb',
]


def get_nist_extensions(case_folder):
    """Return the NIST exclusion extension list for a case. Falls back to default."""
    conn = get_connection(case_folder)
    try:
        row = conn.execute(
            "SELECT setting_value FROM case_settings WHERE setting_key='nist_extensions'"
        ).fetchone()
        if row and row['setting_value']:
            import json as _json
            return _json.loads(row['setting_value'])
        return list(DEFAULT_NIST_EXTENSIONS)
    finally:
        conn.close()


def set_nist_extensions(case_folder, extensions):
    """Save the NIST exclusion extension list for a case."""
    import json as _json
    conn = get_connection(case_folder)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO case_settings (setting_key, setting_value) VALUES ('nist_extensions', ?)",
            (_json.dumps(extensions),)
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 2: Add De-NIST config UI in home.py Case Maintenance**

After the Hash Integrity Verification section (added in Task 5), add:

```python
            # ── De-NIST Filter Configuration ─────────────────────────────
            st.divider()
            st.subheader("🚫 De-NIST Filter Configuration")
            st.caption(
                "File extensions excluded during processing (system/application files). "
                "One extension per line, including the leading dot."
            )

            _current_nist = db_manager.get_nist_extensions(case_folder)
            _nist_text = st.text_area(
                "NIST Extensions",
                value='\n'.join(sorted(_current_nist)),
                height=200,
                key="nist_ext_editor",
                label_visibility="collapsed",
            )
            st.caption(f"{len(_current_nist)} extensions currently configured.")

            _nist_c1, _nist_c2 = st.columns(2)
            with _nist_c1:
                # permission: configure_nist
                if st.button("💾 Save Extensions", key="btn_save_nist",
                             width='stretch'):
                    _parsed = [
                        line.strip().lower()
                        for line in _nist_text.strip().splitlines()
                        if line.strip()
                    ]
                    # Ensure all start with '.'
                    _parsed = [ext if ext.startswith('.') else f'.{ext}' for ext in _parsed]
                    db_manager.set_nist_extensions(case_folder, _parsed)
                    try:
                        db_manager.log_audit(
                            case_folder,
                            action="NIST_CONFIG_UPDATED",
                            user=st.session_state.get('username', ''),
                            module="Home",
                            details=json.dumps({'extension_count': len(_parsed)})
                        )
                    except Exception:
                        pass
                    st.success(f"Saved {len(_parsed)} extensions.")
                    st.rerun()

            with _nist_c2:
                if st.button("🔄 Reset to Default", key="btn_reset_nist",
                             width='stretch'):
                    db_manager.set_nist_extensions(
                        case_folder, list(db_manager.DEFAULT_NIST_EXTENSIONS)
                    )
                    st.success("Reset to default extensions.")
                    st.rerun()

            # Export exclusion report
            _conn_nist = db_manager.get_connection(case_folder)
            try:
                _excluded = _conn_nist.execute("""
                    SELECT control_number, file_name, file_extension, custodian
                    FROM documents WHERE processing_status = 'NIST_Excluded'
                    ORDER BY file_extension, file_name
                """).fetchall()
            finally:
                _conn_nist.close()

            if _excluded:
                _excl_df = pd.DataFrame([dict(r) for r in _excluded])
                st.download_button(
                    f"⬇️ Export Exclusion Report ({len(_excluded)} files)",
                    data=_excl_df.to_csv(index=False).encode('utf-8'),
                    file_name="NIST_Exclusion_Report.csv",
                    mime="text/csv",
                    key="dl_nist_report",
                    width='stretch',
                )
```

- [ ] **Step 3: Modify 2_Processor.py to load NIST extensions from DB**

Replace the hardcoded `NIST_EXTENSIONS` set (lines 511-518) with:

```python
        # 0. De-NIST: Exclude system/application files by extension
        NIST_EXTENSIONS = set(db_manager.get_nist_extensions(case_folder))
```

Keep everything else in the NIST filtering block (lines 519-530) unchanged — it already uses `NIST_EXTENSIONS` as a set.

Note: `case_folder` must be available at this point. Check what variable name is used — it's likely `case_folder` from the page-level `st.session_state.get('current_case_folder')`. Verify the variable name used in the surrounding code.

- [ ] **Step 4: Update version headers and CHANGELOG**

Bump versions:
- `db_manager.py` — already bumped in Task 1; add to same minor version
- `home.py` — already bumped in Task 5; add to same minor version
- `2_Processor.py` — patch bump (behavior change, loading from DB instead of hardcoded)

CHANGELOG entries:
- `- NEW: db_manager.py — De-NIST extension config functions (get/set) with case_settings storage`
- `- NEW: home.py — De-NIST filter configuration UI with export exclusion report`
- `- CHANGE: 2_Processor.py — NIST extensions loaded from case_settings (configurable per case) with hardcoded fallback`

---

## Task 7: Cross-Module Impact Audit + Context Maintenance

**Files:**
- `CLAUDE.md` (update Current State table)
- `CHANGELOG.md` (verify all entries present)
- `DEPENDENCY_MAP.md` (add new cross-module dependencies)

- [ ] **Step 1: Update DEPENDENCY_MAP.md**

Add new cross-module dependencies:
- `collection_scope` table: read by `7_Custodians.py`, `defensibility_report.py`; written by `7_Custodians.py`
- `nist_extensions` case_setting: read by `2_Processor.py`, `home.py`; written by `home.py`
- `last_activity_time` session state key: read/written by `auth_manager.py`
- `session_timeout_minutes` config key: read by `auth_manager.py`; stored in `auth_config.yaml`

- [ ] **Step 2: Update CLAUDE.md Current State table**

- `Last CHANGELOG date` → `2026-03-26`
- `Last completed sprint` → `Phase 24a: EDRM Defensibility Gaps (beta-2.8)`
- `What's next` → `Phase 24b: EDRM Workflow + Differentiators, Module Hardening Sprints 2-4`

- [ ] **Step 3: Update memory files**

Update `project_state.md` with current sprint status.

---

## Verification

After all tasks complete:

1. **Syntax check:** `python -c "import py_compile; py_compile.compile('file.py', doraise=True)"` for all modified files
2. **Collection Scope:** Navigate to Custodians > select a custodian with data_sources > verify Collection Scope tab shows sources > save status/justification > verify defensibility report Section 2.2
3. **Hash Verification:** Navigate to Home > Case Maintenance > click Verify Integrity > verify progress bar and results
4. **Session Timeout:** Log in > wait 31 minutes (or temporarily set timeout to 1 minute in auth_config.yaml) > navigate to any page > verify re-login prompt
5. **De-NIST Config:** Navigate to Home > Case Maintenance > verify extensions editor > save > verify 2_Processor.py uses saved extensions (check by processing a test file)
6. **Grep for `use_container_width`** — should still be 0 (no regressions from Phase 23)
