# Feature Spec: Batch Remediation & Admin Module

**Date:** 2026-04-10
**Status:** Draft — Reviewed, decisions captured
**Target Version:** TBD (post beta-2.9)
**Author:** Claude (PM session) + the maintainer

---

## Problem Statement

When a paralegal or manager ingests documents into the wrong case, there is currently no mechanism to undo the mistake. The platform lacks any way to remove or quarantine wrongly-ingested documents. This creates real risk: documents from Case A sitting in Case B's database could be reviewed, tagged, or produced to the wrong opposing party — a potential privilege and confidentiality breach.

This spec defines **Batch Remediation** (quarantine and remove wrong documents from a case) and a new **Admin Module** to house it and other admin-only operations.

### Decision Log

| Decision | Outcome | Rationale |
|----------|---------|-----------|
| Cross-case transfer | **Dropped** | Complexity outweighs benefit. Quarantine + manual re-ingest into correct case is the standard paralegal workflow ("cut/paste to the right folder") and keeps each case's history self-contained. See Appendix A for the evaluated design. |
| Control number reuse | **No — numbers are retired permanently** | Reusing a DOCID creates ambiguity at deposition. Gaps with documented explanations are standard eDiscovery practice (same as privilege clawbacks). SQLite AUTOINCREMENT natively prevents reuse. |
| Access control level | **Admin only (role 3)** | Remediation is a high-impact, low-frequency operation. A paralegal who made the mistake should escalate to an admin who can verify scope. Permissions can be relaxed later; tightening after an incident feels punitive. Future enhancement: two-step approval (manager initiates, admin confirms). |
| Soft vs. hard delete | **Quarantine (soft delete + file move)** | Files moved to Quarantine folder, DB records flagged as Remediated. Permanent purge available later as a separate admin-only action. On-prem deployment means storage is not a constraint. |

---

## Design Principles

1. **Control numbers are permanent.** Once a `DOC-XXXXXX` is assigned, it is never reused — even after remediation. Gaps in numbering are documented and expected in litigation. Reusing a control number creates ambiguity that cannot be resolved at deposition.

2. **Audit everything.** Every remediation action is logged with who, what, when, and why. The audit trail is the defensibility story.

3. **Quarantine over delete.** Files are moved to a quarantine folder, not destroyed. The DB records are soft-deleted (flagged), not removed. This preserves the ability to prove what happened while keeping the working dataset clean.

4. **Fail safe.** If any step of remediation fails (DB update, OpenSearch cleanup, file move), the entire operation rolls back. No partial remediations.

---

## Part 1: Batch Remediation

### 1.1 Overview

An admin-level function that identifies a batch of wrongly-ingested documents and quarantines them from the case. Documents are removed from the active working set but remain recoverable and auditable.

### 1.2 Scope of Artifacts to Remediate

When documents are ingested and processed, they create artifacts across five systems. Remediation must address all five:

| Artifact | Location | Remediation Action |
|----------|----------|--------------------|
| **DB row** (`documents` table) | `case.db` | Set `processing_status = 'Remediated'`; populate `remediation_reason`, `remediated_by`, `remediated_at` |
| **Original file** | `{case}/Ingest/{path}` | Move to `{case}/Quarantine/{remediation_id}/{path}` |
| **Processed PDF** | `{case}/Processed/{control_number}.pdf` | Move to `{case}/Quarantine/{remediation_id}/Processed/` |
| **Split fragments** | `{case}/Split/{control_number}_*.pdf` | Move to `{case}/Quarantine/{remediation_id}/Split/` |
| **OpenSearch entry** | Case index | Delete by `_id = control_number` |
| **Review batch links** | `batch_documents` table | DELETE rows referencing remediated control numbers |
| **Filevine sync records** | `documents` table fields | Cleared as part of soft-delete update (fields: `filevine_doc_id`, `sync_status`, etc.) |

**Child documents** (attachments extracted from containers like PSTs and EMLs) must be remediated together with their parent. The system must walk `parent_id` relationships and include the full document family.

**Review batch cleanup:** If remediated documents were assigned to review batches (via the `batch_documents` junction table), those associations must be deleted. Leaving orphaned batch-document links could cause errors when loading review batches. The batch itself remains (other documents in the batch are unaffected).

### 1.3 Selection Interface

The remediation UI (proposed location: a new tab on the Ingestor page, or a dedicated admin page) should allow selecting documents by:

- **Ingestion date range** — using audit log timestamps for `DOCUMENT_INGESTED` events
- **Source collection / subcollection** — the `source_collection` and `source_subcollection` fields, which map to the folder structure under `Ingest/`
- **Custodian** — the `custodian` field
- **Control number range** — manual entry for surgical remediation
- **Parent container** — select a PST/EML/ZIP and automatically include all children

Before execution, the UI must display a preview showing: total document count, control number range, custodians affected, and any documents that have already been reviewed or tagged (these require extra confirmation since work product will be lost).

### 1.4 Database Schema Changes

#### New columns on `documents` table

```sql
ALTER TABLE documents ADD COLUMN remediation_id TEXT;
ALTER TABLE documents ADD COLUMN remediation_reason TEXT;
ALTER TABLE documents ADD COLUMN remediated_by TEXT;
ALTER TABLE documents ADD COLUMN remediated_at TEXT;
```

#### New `remediation_log` table

```sql
CREATE TABLE IF NOT EXISTS remediation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    remediation_id TEXT NOT NULL,       -- UUID grouping all docs in this batch
    action TEXT NOT NULL,               -- 'QUARANTINE', 'PERMANENT_DELETE', 'RESTORE'
    document_count INTEGER NOT NULL,
    control_number_range TEXT NOT NULL,  -- e.g. 'DOC-000400 through DOC-000899'
    reason TEXT NOT NULL,               -- free-text explanation (required)
    authorized_by TEXT NOT NULL,        -- username of manager/admin who approved
    executed_by TEXT NOT NULL,          -- username who ran the operation
    executed_at TEXT NOT NULL,          -- ISO8601 timestamp
    target_case TEXT,                   -- for TRANSFER actions: destination case name
    details_json TEXT                   -- full list of control numbers, file paths, etc.
);
```

#### New processing status value

- `Remediated` — document has been quarantined due to wrong-case ingestion or similar error. Excluded from all queries, review, analytics, and production, just like `Container_Scanned` and `Split_Source`.

### 1.5 Query Filtering

Every query that currently filters on `processing_status NOT IN ('Container_Scanned', 'Split_Source')` must also exclude `'Remediated'`. Based on current codebase analysis, these filters exist in `db_manager.py` at approximately lines 1184, 1704, 1720, and 2753, plus any page-level queries.

**Implementation note for Claude Code:** When implementing this, grep the entire codebase for `Container_Scanned` and `Split_Source` filter clauses. Every location that excludes those statuses must also exclude `Remediated`. This is the highest-risk area for regressions — a missed filter means remediated documents leak back into the working set.

### 1.6 Quarantine Folder Structure

```
{CaseFolder}/
└── Quarantine/
    └── {remediation_id}/
        ├── MANIFEST.json          -- machine-readable record of what's here and why
        ├── Ingest/                -- original files, preserving subfolder structure
        │   └── {original_path}/
        ├── Processed/             -- rendered PDFs
        └── Split/                 -- split fragments (if any)
```

**MANIFEST.json** contents:

```json
{
  "remediation_id": "uuid-here",
  "created_at": "2026-04-10T14:30:00",
  "reason": "Documents ingested into wrong case - should be in Smith v. Jones",
  "authorized_by": "jsmith",
  "executed_by": "tparalegal",
  "document_count": 47,
  "control_number_range": "DOC-000400 through DOC-000446",
  "control_numbers": ["DOC-000400", "DOC-000401", "..."],
  "source_case": "Wrong Case Name",
  "status": "quarantined"
}
```

### 1.7 Execution Flow

```
1. Admin selects documents and provides reason (free text, required)
2. System resolves full document families (parents + all children)
3. Preview displayed: count, CN range, custodians, review status warnings
4. Admin types "REMEDIATE" to confirm (same pattern as production purge)
5. BEGIN TRANSACTION
   a. Update all selected documents: processing_status = 'Remediated',
      set remediation_id, reason, by, at
   b. Insert remediation_log record
   c. Insert audit_log entries (one per document: action = 'DOCUMENT_REMEDIATED')
6. COMMIT (if any DB step fails, ROLLBACK and stop)
7. Move files to Quarantine folder (with MANIFEST.json)
8. Delete from OpenSearch index (bulk operation, log failures)
9. If OpenSearch delete partially fails: log warning but don't rollback
   (reindex_from_sqlite will clean up on next reindex since the DB
   records are already marked Remediated and won't be re-indexed)
10. Display summary: "47 documents quarantined. Control numbers DOC-000400
    through DOC-000446 are retired."
```

### 1.8 Access Control

```python
# permission: remediate_documents
auth_manager.require_role(3)  # Admin only
```

Closed cases block remediation (same as all other write operations).

**Future enhancement — two-step approval workflow:** A manager (role 2) can *initiate and preview* a remediation request, which enters a "pending approval" state. An admin (role 3) reviews the scope and confirms execution. This pattern gives case-knowledgeable managers the ability to flag the problem without giving them the keys to execute the fix unsupervised. Implement this when the user base grows beyond single-admin firms.

### 1.9 Permanent Purge (Optional, Admin-Only)

A secondary function that permanently deletes quarantined files from disk. This is for storage reclamation after the remediation has been verified and sufficient time has passed.

```python
# permission: purge_quarantine
auth_manager.require_role(3)  # Admin only
```

- Only operates on documents already in `Remediated` status
- Deletes physical files from the `Quarantine/` folder
- Does NOT delete DB records — those remain permanently as the audit trail
- Updates `MANIFEST.json` status from `"quarantined"` to `"purged"`
- Requires typing "PURGE" to confirm

### 1.10 Restore (Undo the Undo)

If a remediation was performed in error (wrong documents quarantined), a restore function reverses it:

- Moves files back from `Quarantine/` to their original locations
- Sets `processing_status` back to the value it had before remediation (stored in `details_json`)
- Clears remediation fields
- Re-indexes into OpenSearch
- Logs `DOCUMENT_RESTORED` audit entries
- Inserts `RESTORE` action into `remediation_log`

**This is only available if the quarantine has not been permanently purged.**

---

## Part 2: Admin Module

### 2.1 Motivation

The home page currently contains a mix of admin tools and general-purpose navigation. As the platform grows, admin-only operations (user management, case configuration, remediation, audit log review) should live in a dedicated space that non-admin users never see. This reduces clutter for reviewers and paralegals while giving admins a clear command center.

### 2.2 Proposed Structure

A new Streamlit page (e.g., `pages/7_Admin.py`) gated at role 3, containing tabs for distinct admin functions:

| Tab | Contents | Status |
|-----|----------|--------|
| **Remediation** | Batch remediation UI (this spec, Section 1.3) | New — build with this spec |
| **Quarantine Manager** | View quarantined batches, restore, permanent purge | New — Phase 2 |
| **Retired CNs** | Gap report showing retired control number ranges with reasons | New — Phase 1 |
| **User Management** | Existing user/role management (currently on home page?) | Migrate when ready |
| **Audit Log Viewer** | Searchable/filterable view of audit_log table | Future |
| **Case Configuration** | Case-level settings, status management | Future |

### 2.3 Access Control

```python
# permission: access_admin_module
auth_manager.require_role(3)  # Admin only — entire page gated
```

The page should not appear in the Streamlit sidebar for non-admin users. Streamlit's native page visibility can be controlled via `st.set_page_config` or conditional sidebar rendering.

### 2.4 Implementation Notes for Claude Code

- Follow the existing page pattern: role check at top, closed-case check where applicable, audit logging for all write operations.
- The Remediation tab is the priority — other tabs can be stubbed with "Coming Soon" placeholders.
- Home page cleanup (migrating existing admin tools) is a separate effort. Don't move things in the remediation sprint — just add the new page.

---

## Part 3: Retired Control Number Documentation

### 3.1 The Problem With Reuse

When control numbers are retired via remediation or transfer, gaps appear in the numbering sequence. This is normal and expected in eDiscovery. The defensible approach is to document the gaps, not fill them.

**Why reuse is dangerous:** Imagine at deposition, opposing counsel references "DOC-000405." If that number was recycled, which document are they referring to — the quarantined one or its replacement? The audit log resolves it, but you've created needless ambiguity that a simple "those numbers are retired" avoids entirely.

### 3.2 Gap Documentation

The `remediation_log` table (Section 1.4) stores the control number ranges for each remediation event. A utility query can generate a gap report:

```sql
SELECT remediation_id, control_number_range, reason, executed_at
FROM remediation_log
WHERE action = 'QUARANTINE'
ORDER BY executed_at;
```

This should be surfaceable in the UI (perhaps on a Case Summary or Admin page) so that anyone reviewing the case can see: "Control numbers DOC-000400 through DOC-000446 were retired on 2026-04-10 — wrong-case ingestion, see remediation log entry [uuid]."

### 3.3 SQLite AUTOINCREMENT Behavior

Important technical note: SQLite's `AUTOINCREMENT` guarantees that IDs are never reused, even after deletion. From the SQLite docs: *"The AUTOINCREMENT keyword...prevents the reuse of ROWIDs over the lifetime of the database."* This means even if we hard-deleted DB rows (which we don't — we soft-delete), the `id` column that feeds `DOC-XXXXXX` would naturally skip the retired numbers. The design aligns with the database's native behavior.

---

## Part 4: Implementation Priority

### Phase 1 (Recommended: Next sprint after beta-2.9 stabilizes)

- Admin Module page (`7_Admin.py`) with role 3 gate
- Batch Remediation UI — Remediation tab (Sections 1.1–1.8)
- Query filtering updates (Section 1.5) — **highest regression risk, test thoroughly**
- Quarantine folder structure (Section 1.6)
- Retired CN report tab (Section 3.2)

### Phase 2 (When Phase 1 is proven stable)

- Quarantine Manager tab — view, restore, permanent purge (Sections 1.9–1.10)
- Two-step approval workflow for manager-initiated remediation requests

### Phase 3 (Future — as admin module matures)

- Migrate existing admin tools from home page to Admin Module
- Audit Log Viewer tab
- Case Configuration tab

---

## Open Questions for the maintainer

1. **Notification:** Should remediation trigger any notification (email, Streamlit toast, case log entry) to the case manager, or is the audit log sufficient?

2. **Review work product:** If remediated documents had already been reviewed, tagged, or had privilege designations applied, should the system warn and require extra confirmation? (Spec currently assumes yes — see Section 1.3 preview.)

3. **Admin page numbering:** The spec suggests `7_Admin.py`. Does this fit the current sidebar ordering, or should it be positioned differently?

---

## Appendix A: Cross-Case Transfer (Evaluated and Deferred)

This feature was evaluated during spec drafting and **deferred indefinitely**. The quarantine + manual re-ingest workflow is simpler, keeps each case's history self-contained, and matches the natural paralegal mental model ("move the files to the right folder"). The design is preserved here for reference if the need arises.

**What it would do:** Move documents directly from one case to another with chain-of-custody logging in both cases.

**Why it was deferred:**

- Cross-case references are inherently fragile — if Case B is deleted or renamed, Case A's audit trail has orphaned references
- Control number translation (old CN → new CN) across cases adds permanent mapping complexity
- SQLite doesn't support distributed transactions, so atomicity across two case databases requires a fragile two-phase commit
- Parent-child integrity across cases means a PST with 200 children must transfer all-or-nothing
- The alternative (quarantine + re-ingest) is fully defensible and avoids all of these problems at the cost of re-processing time

**If revisited in the future**, the design would involve: marking source documents as `Transferred`, inserting new rows with new CNs in the target case's DB, copying files, remapping parent-child and group relationships, and maintaining a CN mapping manifest in both cases' Quarantine folders.

---

*This spec was drafted in a Cowork PM session. Implementation prompts for Claude Code in VS Code should reference this document for requirements.*
