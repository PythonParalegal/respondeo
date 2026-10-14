# Spec: Case-Scoped Intake-Inbox Pattern for Modules 1 & 9

**Status:** Proposed — awaiting planning session
**Target sprint:** beta-2.11 (or later)
**Author context:** Drafted from PM-Claude / maintainer design conversation during beta-2.10 Commit 7.6 verification, 2026-04-17

---

## 1. Problem Statement

Respondeo's LAN-shared deployment model means paralegals sit at their own workstations while the Streamlit server runs on a shared office PC. Today, getting files into the system requires:

1. Paralegal downloads file (opposing production ZIP, custodial data folder, etc.) to their workstation
2. Paralegal manually transfers file to the server PC (via shared folder, USB drive, IT help, etc.)
3. Paralegal asks someone where exactly the file landed on the server
4. Paralegal types or pastes that absolute path into Module 1 (Ingestor) or Module 9 (Inbound Productions)

This UX is hostile to non-technical paralegals (the platform's core user — "the 45-year-old who started transcribing dictation on tape"). It also produces no chain-of-custody record — a file's arrival on the server is invisible, unhashed, untimestamped, and unattributed to a case until ingestion completes, after which the origin path is forgotten.

Additionally, the platform has no native folder-picker mechanism. Streamlit is a web framework; browsers cannot reach the filesystem by design. A `tkinter.filedialog.askdirectory()` workaround would only work for solo-practitioner deployments where server = workstation, not for the LAN-shared deployment that represents the platform's primary market.

## 2. Proposed Solution

Per-case, per-module **intake inboxes** — dedicated drop-zone folders inside each case's folder tree. Paralegals drop files into these folders via their normal network-share access. Modules 1 and 9 each render a dropdown of their inbox's current contents, turning file selection into a one-click operation with no path typing.

Post-ingest, ingested files automatically move to a parallel `archive/` subtree with timestamp prefix, producing a visible, auditable lifecycle and a defensibility-grade chain of custody record.

## 3. User Workflows

### 3.1 Paralegal (primary workflow)

1. Opposing counsel delivers production → paralegal downloads ZIP to their workstation's Downloads folder.
2. Paralegal opens Windows File Explorer. A desktop shortcut (provisioned during IT setup) opens the network-shared cases root directly.
3. Paralegal navigates to their active case folder (e.g., `\\Server\RespondeoCases\Smith_v_Jones\`) and into `inbox\inbound\`.
4. Paralegal drags the ZIP from Downloads into `inbox\inbound\`.
5. Paralegal opens Respondeo in their browser, selects the Smith case, clicks **Module 9: Inbound Productions**.
6. Step 1 of the module now shows **"Select from Inbox"** as the primary interaction — a dropdown listing everything currently in `inbox\inbound\`. The ZIP they just dropped appears in the list.
7. Paralegal clicks the ZIP, fills out Source Party Name and Production Volume Name (as today), and clicks Ingest.
8. Module 9 extracts the ZIP to a staging location, ingests the production, then moves the original ZIP to `inbox\archive\inbound\2026-04-17_14-23-01__OCA001.zip`.
9. The ZIP disappears from the inbox dropdown and appears in the archive folder — paralegal has visual confirmation the ingestion completed and the source file is preserved for audit.

Module 1 (Ingestor) follows the same pattern pointing at `inbox\ingest\` for custodial data.

### 3.2 IT Admin (one-time setup)

1. Identify the Respondeo cases root on the server PC (e.g., `C:\RespondeoCases\`).
2. Configure a Windows network share on that folder with the following permissions:
   - Paralegal user group: **Read/Write**
   - Streamlit service account (the user account running `streamlit run home.py`): **Full Control**
   - Everyone else: **No Access**
3. On each paralegal workstation, create a desktop shortcut pointing at `\\ServerPC\RespondeoCases` for easy access.
4. Confirm IT's firewall allows SMB traffic between paralegal workstations and the server PC.
5. Run a one-time backfill utility (see §9) that creates `inbox/` and `archive/` subfolders in every existing case folder.

Full IT setup instructions — including ACL commands, troubleshooting SMB issues, and how to add new paralegals to the share — live in a new `docs/IT_Setup_Guide.md` produced as part of this sprint.

## 4. Technical Architecture

### 4.1 Case folder structure changes

Every case folder gains an `inbox/` subtree:

```
{case_folder}/
  inbox/
    ingest/        ← Module 1 Ingestor drop zone
    inbound/       ← Module 9 Inbound Productions drop zone
    archive/
      ingest/      ← Module 1 post-ingest destination
      inbound/     ← Module 9 post-ingest destination
    failed/
      ingest/      ← Module 1 failed-ingestion destination
      inbound/     ← Module 9 failed-ingestion destination
  documents/
  processed/
  production_output/
  ...
```

Created automatically on:
- New case creation (in whichever function provisions the case folder — likely in `db_manager.py` or `home.py`).
- Case open if any subfolder is missing (self-healing backfill — see §9).

### 4.2 Config additions (`config.py`)

```python
# Intake inbox pattern
INTAKE_INBOX_ENABLED = True  # Master switch; False retains legacy paste-path-only UX
INTAKE_ARCHIVE_ON_SUCCESS = True  # Move source to archive/ on successful ingest
INTAKE_MOVE_ON_FAILURE = True  # Move source to failed/ on ingest failure (vs. leaving in inbox)
INTAKE_AUTO_EXTRACT_ZIP = True  # Auto-unzip .zip files before ingesting
INTAKE_INBOX_SUBFOLDERS = {
    'ingest': 'ingest',       # Module 1 drop zone name under {case}/inbox/
    'inbound': 'inbound',     # Module 9 drop zone name under {case}/inbox/
}
```

All new config keys mirrored in `config.example.py`.

### 4.3 New UI helper: `ui_utils.inbox_picker()`

```python
def inbox_picker(case_folder, intake_type, key_prefix, case_closed=False):
    """
    Render an intake-inbox picker for the specified intake type.

    Args:
        case_folder: path to the current case folder
        intake_type: 'ingest' | 'inbound' — determines which inbox subfolder
        key_prefix: Streamlit session-state key prefix (avoid widget key collisions)
        case_closed: if True, picker renders in disabled state

    Returns:
        selected_path: absolute path to the user-picked file/folder, or None
    """
```

Behavior:
- Lists contents of `{case_folder}/inbox/{intake_type}/` (excluding dotfiles and the `archive/`/`failed/` subfolders themselves).
- Renders as a `st.selectbox` with a "Refresh list" button adjacent.
- Shows file size and mtime for each entry (helps users identify what they just dropped).
- Empty inbox: shows info message "No files in inbox. Drop files into `{inbox_path}` using Windows Explorer, then click Refresh."
- Returns `None` until user makes a selection.
- Below the primary picker, renders a collapsed "Advanced: enter path manually" expander containing the legacy `st.text_input` as fallback for edge cases (external drives, shell-scripted workflows, debugging).

### 4.4 Module 1 Ingestor integration

Replace the current path `st.text_input` at ingest-root selection with `ui_utils.inbox_picker(case_folder, 'ingest', 'm1_intake')`. Preserve all downstream ingestion logic unchanged — the picker just returns a path.

### 4.5 Module 9 Inbound Productions integration

Same pattern: replace the Local Path input with `ui_utils.inbox_picker(case_folder, 'inbound', 'm9_intake')`.

### 4.6 Post-ingest archive move

After successful ingest, move the source file/folder via `shutil.move()`:

```
from:   {case}/inbox/{intake_type}/{filename}
to:     {case}/inbox/archive/{intake_type}/{YYYY-MM-DD_HH-MM-SS}__{filename}
```

Timestamp prefix prevents collisions when the same filename is re-ingested later. Use a filesystem-safe timestamp format (no colons).

On failure:
- If `INTAKE_MOVE_ON_FAILURE = True`: move to `{case}/inbox/failed/{intake_type}/{timestamp}__{filename}` with a sibling `{timestamp}__{filename}.error.txt` containing the exception traceback.
- If `False`: leave in inbox so user can retry.

### 4.7 Chain-of-custody audit log (recommended)

Add a new DB table `intake_events`:

```sql
CREATE TABLE IF NOT EXISTS intake_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_folder TEXT NOT NULL,
    intake_type TEXT NOT NULL,          -- 'ingest' | 'inbound'
    original_filename TEXT NOT NULL,
    file_size_bytes INTEGER,
    file_hash_sha256 TEXT,
    arrived_at TEXT,                    -- ISO-8601, from file mtime at detection
    detected_at TEXT NOT NULL,          -- when picker first saw the file
    ingested_at TEXT,                   -- NULL if not yet ingested
    ingested_by TEXT,                   -- username from auth_manager
    outcome TEXT,                       -- 'success' | 'failed' | 'pending'
    archive_path TEXT,                  -- absolute path to archived source, if moved
    production_run_id INTEGER,          -- FK to production_runs if direction='inbound'
    notes TEXT
);
```

New `db_manager` helpers: `record_intake_event()`, `update_intake_outcome()`, `get_intake_history(case_folder, intake_type=None)`. The defensibility report gains a new section rendering this table per case.

## 5. ZIP Auto-Extract Policy

Default behavior (`INTAKE_AUTO_EXTRACT_ZIP = True`):
- User picks `OCA001.zip` from the inbox.
- Module 9 extracts to `{case}/inbox/_staging/{timestamp}__OCA001/` before ingest.
- Ingestion proceeds against the extracted folder.
- Post-ingest: both the original ZIP (archived per §4.6) and the staging extraction (cleaned up or retained — see §11.3 open decision) are handled according to config.

Non-ZIP folders (a directory dropped directly into the inbox) skip staging and ingest in place.

Loose files (a single `.pdf` or `.eml` dropped into the inbox) — out of scope for this spec; policy is to reject with "please place files inside a named folder or ZIP for ingestion." Rationale: production-quality ingest workflows are structured around load files and manifests; loose-file handling requires different UX.

## 6. Error Handling

### 6.1 Failed ingest

- Source moved to `inbox/failed/{intake_type}/` per §4.6.
- Sibling `.error.txt` captures the exception.
- Intake event record updated with `outcome='failed'`.
- UI surfaces the failure at the next picker render: "1 file in `failed/` — view details" link.

### 6.2 Concurrent selection of the same file

- Streamlit's session isolation makes true concurrent selection unlikely (each user has their own browser session and selection state).
- Defense: attempt atomic `shutil.move()` before starting ingestion. If the move fails because the source disappeared (another session grabbed it), surface "This file was ingested by another user" error.

### 6.3 File deleted between picker render and ingest click

- Same atomic-move defense applies.
- UI refresh button lets users see current inbox state.

### 6.4 Disk-full / permissions errors

- Catch at archive-move step. If the archive move fails after successful ingest, log loudly and leave the source in inbox (don't roll back the ingestion; the data is already in the DB).
- Flag the intake_event with a notes field so admins can manually resolve.

## 7. Defensibility & Chain of Custody

This feature's defensibility value is first-class, not an accident. Each `intake_events` row is a provable record of:

- **Arrival:** when the file landed in the inbox (from OS mtime + our detection timestamp)
- **Integrity:** SHA-256 hash at the moment of pickup — if opposing counsel later alleges the file was altered, we can prove the hash matches what we received
- **Attribution:** which paralegal ingested it, into which case, at what time
- **Preservation:** archive path showing the unmodified source was retained

The defensibility report should render this table for each case as a new section **"6.3 Inbound File Intake Log"** (and optionally split outbound custodial intake into **"6.1 Custodial Data Intake Log"** if Module 1 is in scope).

Attorney-facing value (for Walkthrough.md update): "Respondeo records the arrival, hash, and preservation of every file entering the system, producing a court-admissible chain-of-custody record for each matter."

## 8. Supply Chain

**No new Python dependencies.** All functionality uses stdlib: `os`, `shutil`, `zipfile`, `hashlib`, `pathlib`, `datetime`.

## 9. Migration Path for Existing Cases

Cases that existed before this sprint won't have `inbox/` trees. On case open (inside `home.py`'s case-selection flow), run a lightweight self-heal:

```python
def _ensure_intake_tree(case_folder):
    """Create inbox/{ingest,inbound,archive/ingest,archive/inbound,failed/ingest,failed/inbound} if missing."""
    for sub in ['ingest', 'inbound',
                'archive/ingest', 'archive/inbound',
                'failed/ingest', 'failed/inbound']:
        os.makedirs(os.path.join(case_folder, 'inbox', sub), exist_ok=True)
```

`exist_ok=True` makes this a no-op for cases that already have the tree. No data migration required — only directory creation.

## 10. Testing Plan

### 10.1 Unit tests
- `inbox_picker()` with empty inbox renders the "no files" message.
- `inbox_picker()` with mixed file and folder contents renders both correctly with size/mtime.
- Archive-move timestamp format is filesystem-safe (no colons, no forbidden chars).
- `record_intake_event()` writes all required fields.

### 10.2 Integration tests
- Drop fixture file into temp inbox, invoke picker simulator, confirm file appears.
- Trigger ingest, confirm file moves to archive with correct timestamp.
- Trigger failed ingest, confirm file moves to failed with error sibling.

### 10.3 End-to-end (Playwright)
- Log in, select case, navigate to Module 9, confirm picker renders with seeded inbox contents.
- Select a fixture ZIP, confirm module proceeds to ingest flow.
- After ingest completes, confirm file no longer appears in picker.

### 10.4 Stress / edge-case tests
- Very large file in inbox (10GB+): confirm picker loads without hanging on size-calc.
- Inbox with 500+ files: confirm dropdown renders acceptably (may need pagination or search).
- Filename with non-ASCII characters: confirm archive-move handles correctly.
- Permission-denied on archive folder: confirm graceful error message.

## 11. Open Design Decisions for Planning Session

1. **Staging extraction cleanup.** After ZIP auto-extract and successful ingest, do we:
   - (a) Delete the staging folder to save disk
   - (b) Keep it indefinitely
   - (c) Move it to archive alongside the ZIP
   - Disk usage vs. defensibility trade-off.

2. **Loose-file policy.** This spec rejects loose files in the inbox. Should Module 1 accept loose custodial files as a valid case (e.g., a single attorney letter)? Or always require folder structure?

3. **`intake_events` table vs. existing `audit_log` table.** Should intake be tracked in a dedicated table (this spec's proposal) or as specialized rows in the existing audit log? Dedicated table is cleaner for querying, audit log is simpler. Trade-off for DB-schema review.

4. **Picker refresh strategy.** Manual "Refresh" button (this spec's default), periodic auto-refresh every N seconds, or filesystem watcher (via `watchdog` library — which would add a dependency)? Manual is simplest; filesystem watcher is best UX but adds supply-chain surface.

5. **Multi-user concurrency UI.** If two paralegals happen to select the same file at the same time, one will succeed and one will see "file gone" error. Is that acceptable, or do we need explicit locking (first-click-wins UI feedback)? Concurrency is rare in small-firm deployments, but worth a planning-session decision.

6. **Paste-path "Advanced" fallback.** Keep as collapsible expander, or remove entirely once the inbox pattern is proven? Removing forces users into the inbox pattern (cleaner UX discipline) but eliminates the escape hatch for edge cases. Recommendation: keep the expander.

7. **Module 7 Custodians hold-letter uploads and Module 4 Review STR-report uploads currently use `st.file_uploader` (browser upload).** Should those be migrated to the inbox pattern too, for consistency? They handle smaller files (KB-MB range) where browser upload is acceptable — probably leave as-is but confirm during planning.

## 12. Out of Scope

- **Cloud-deployment variant.** This spec assumes LAN-shared deployment. A future cloud-hosted variant would need a different intake mechanism (probably `st.file_uploader` with chunked upload support or S3 presigned URLs). Out of scope here.
- **Cross-case file movement.** If a paralegal drops a file in Case A's inbox but intended Case B, this spec provides no remediation — they need to move the file manually via Explorer. A "move file to another case" UI action is out of scope.
- **Network-share setup automation.** IT configures the SMB share manually per §3.2. Automated provisioning (Ansible, Chocolatey, etc.) is out of scope.
- **Retention/cleanup policies.** The `archive/` tree will grow over case lifetime. This spec provides no automatic retention policy. Out of scope — handle in a future "case lifecycle management" sprint.
- **Inbox quota enforcement.** No disk-quota mechanism in this spec. If an inbox fills the case's drive, Respondeo fails gracefully but doesn't proactively warn. Consider for future hardening sprint.

## 13. Estimated Effort

Full sprint item. Rough breakdown:

| Work area | Size |
|-----------|------|
| Config additions + case-folder bootstrap | Small |
| `ui_utils.inbox_picker()` helper | Medium |
| Module 1 Ingestor integration | Medium |
| Module 9 Inbound Productions integration | Medium |
| Archive/failed move logic | Small |
| `intake_events` DB table + helpers | Small-Medium |
| Defensibility report section | Small |
| Self-heal backfill for existing cases | Small |
| Unit + integration tests | Medium |
| Playwright E2E tests | Small |
| User_Guide.md update with screenshots | Medium |
| IT_Setup_Guide.md (new doc) | Medium |
| Walkthrough.md update (attorney-facing) | Small |
| DEPENDENCY_MAP.md update | Small |

Approximately one full sprint cycle (~2 weeks of focused work), plus planning overhead.

## 14. Dependencies on Other Roadmap Items

- **Permission system migration.** This spec uses the current `'ingest'` and `'production'` permissions. If beta-2.11 also advances the role-to-permission migration, the inbox picker should gate via permissions not roles.
- **Batch Remediation / Admin Module (Phase 27).** No conflict, but the admin module may want visibility into the inbox/archive state across all cases.
- **No blocking dependencies.**

## 15. Success Criteria

This feature is complete when:

1. A paralegal can complete an inbound-production ingest with zero path typing, using only the Module 9 UI and their Windows File Explorer.
2. Every ingested file produces an `intake_events` row with arrival time, hash, and archive path.
3. The defensibility report includes an Inbound File Intake Log section readable by an opposing-counsel audit.
4. Existing cases work without manual migration (self-heal on case open).
5. The legacy paste-path input remains available as an "Advanced" option for edge cases.
6. User_Guide.md contains a step-by-step workflow a non-technical paralegal can follow without IT assistance.
7. IT_Setup_Guide.md contains setup instructions that a competent IT admin can execute without code archaeology.

---

**End of spec.** Ready for beta-2.11 planning session.
