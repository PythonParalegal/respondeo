# Respondeo — User Guide

> **Platform Version:** Beta 2.15 (May 2026)
> **Audience:** Paralegals, Case Managers, and Attorneys
> **Classification:** Confidential — Firm Use Only
>
> **Recent Updates (Beta 2.15):** Inbound-production documents now correctly appear in Review text-search results (previously silently dropped from the visible grid even when matched in OpenSearch — Flag #28 fix in C7).

---

## Table of Contents

1. [Getting Started](#1-getting-started)
   - 1.1 [Logging In](#11-logging-in)
   - 1.2 [Selecting a Case](#12-selecting-a-case)
   - 1.3 [Understanding Your Role](#13-understanding-your-role)
   - 1.4 [Navigating the Sidebar](#14-navigating-the-sidebar)

2. [Ingesting Documents (Manager+)](#2-ingesting-documents-manager)
   - 2.1 [Preparing Files for Ingestion](#21-preparing-files-for-ingestion)
   - 2.2 [Running an Ingestion Scan](#22-running-an-ingestion-scan)
   - 2.3 [Assigning Custodians](#23-assigning-custodians)
   - 2.4 [Re-running Ingestion (Adding More Files)](#24-re-running-ingestion-adding-more-files)

3. [Processing Documents (Manager+)](#3-processing-documents-manager)
   - 3.1 [Understanding the Three Processing Phases](#31-understanding-the-three-processing-phases)
   - 3.2 [Running the Processor](#32-running-the-processor)
   - 3.3 [Handling Processing Errors](#33-handling-processing-errors)
   - 3.4 [Verifying Processing Results](#34-verifying-processing-results)
   - 3.5 [Processing Exception Report](#35-processing-exception-report)

4. [Running Analytics (Manager+)](#4-running-analytics-manager)
   - 4.1 [Email Threading](#41-email-threading)
   - 4.2 [Near-Duplicate Detection](#42-near-duplicate-detection)
   - 4.3 [When to Run Analytics](#43-when-to-run-analytics)
   - 4.4 [Understanding Suppressed Documents](#44-understanding-suppressed-documents)
   - 4.5 [Custodian Overlap Analysis](#45-custodian-overlap-analysis)
   - 4.6 [Concept Explorer](#46-concept-explorer)

5. [Reviewing Documents (All Roles)](#5-reviewing-documents-all-roles)
   - 5.1 [The Review Grid](#51-the-review-grid)
   - 5.2 [Searching Documents](#52-searching-documents)
   - 5.3 [Filtering the Grid](#53-filtering-the-grid)
   - 5.4 [Viewing a Document](#54-viewing-a-document)
   - 5.5 [Tagging Documents](#55-tagging-documents)
   - 5.6 [Adding Comments](#56-adding-comments)
   - 5.7 [Exporting the Review Grid to CSV (Manager+)](#57-exporting-the-review-grid-to-csv-manager)
   - 5.8 [Bates Batch Search](#58-bates-batch-search)
   - 5.9 [Micro-PDF Extraction (Extract Exact Pages)](#59-micro-pdf-extraction-extract-exact-pages)
   - 5.10 [Issue Coding / Custom Coding Fields](#510-issue-coding--custom-coding-fields)
   - 5.11 [Exhibit Designation (Mark as Exhibit)](#511-exhibit-designation-mark-as-exhibit)
   - 5.12 [Production History](#512-production-history)
   - 5.13 [Selective Re-Image (Manager+)](#513-selective-re-image-manager)
   - 5.14 [Reviewer Notes](#514-reviewer-notes)
   - 5.15 [Confidentiality Designation Override](#515-confidentiality-designation-override)
   - 5.16 [Date Range Filter](#516-date-range-filter)

6. [Redacting Documents (Manager+)](#6-redacting-documents-manager)
   - 6.1 [Opening a Document for Redaction](#61-opening-a-document-for-redaction)
   - 6.2 [Drawing Redaction Boxes](#62-drawing-redaction-boxes)
   - 6.3 [Assigning Privilege Reasons to Each Box](#63-assigning-privilege-reasons-to-each-box)
   - 6.4 [Saving Redaction Marks](#64-saving-redaction-marks)
   - 6.5 [Clearing Redaction Marks](#65-clearing-redaction-marks)
   - 6.6 [How Redaction Tags Stay in Sync](#66-how-redaction-tags-stay-in-sync)
   - 6.7 [Important: Redactions Are Non-Destructive Until Production](#67-important-redactions-are-non-destructive-until-production)

7. [Running Search Term Reports (Manager+)](#7-running-search-term-reports-manager)
   - 7.1 [Entering or Uploading Search Terms](#71-entering-or-uploading-search-terms)
   - 7.2 [Running the Report](#72-running-the-report)
   - 7.3 [Reviewing Hit Counts and Document Preview](#73-reviewing-hit-counts-and-document-preview)
   - 7.4 [Exporting the Report](#74-exporting-the-report)
   - 7.5 [STR Highlighting in the Review Module](#75-str-highlighting-in-the-review-module)

8. [Producing Documents (Manager+)](#8-producing-documents-manager)
   - 8.1 [Selecting Documents for Production](#81-selecting-documents-for-production)
   - 8.2 [Configuring Production Settings](#82-configuring-production-settings)
   - 8.3 [Running the Production](#83-running-the-production)
   - 8.4 [What Happens During Production](#84-what-happens-during-production)
   - 8.5 [Locating the Output Files](#85-locating-the-output-files)
   - 8.6 [Understanding Load Files (DAT, OPT, CSV)](#86-understanding-load-files-dat-opt-csv)
   - 8.7 [Multi-Production Tracking](#87-multi-production-tracking)

9. [Generating a Privilege Log (Manager+)](#9-generating-a-privilege-log-manager)
   - 9.1 [Running the Privilege Log](#91-running-the-privilege-log)
   - 9.2 [Abbreviation Normalization](#92-abbreviation-normalization)
   - 9.3 [Exporting to Excel or CSV](#93-exporting-to-excel-or-csv)

10. [Receiving Opposing Counsel Productions (Manager+)](#10-receiving-opposing-counsel-productions-manager)
    - 10.1 [Preparing the Inbound Production](#101-preparing-the-inbound-production)
    - 10.2 [Loading the Load File and Mapping Columns](#102-loading-the-load-file-and-mapping-columns)
    - 10.3 [Verifying the Import](#103-verifying-the-import)
    - 10.4 [Purging an Incorrect Import](#104-purging-an-incorrect-import)

11. [Filevine Sync (Manager+)](#11-filevine-sync-manager)
    - 11.1 [Pushing Documents to Filevine](#111-pushing-documents-to-filevine)
    - 11.2 [Pulling Back Reviewed Documents](#112-pulling-back-reviewed-documents)
    - 11.3 [Handling Sync Errors](#113-handling-sync-errors)

12. [Viewing Audit Logs (Admin Only)](#12-viewing-audit-logs-admin-only)
    - 12.1 [Accessing the Audit Log Viewer](#121-accessing-the-audit-log-viewer)
    - 12.2 [Filtering by User, Document, Module, or Date Range](#122-filtering-by-user-document-module-or-date-range)
    - 12.3 [Exporting Audit Logs to CSV](#123-exporting-audit-logs-to-csv)
    - 12.4 [Common Audit Queries](#124-common-audit-queries)

13. [User Management (Admin Only)](#13-user-management-admin-only)
    - 13.1 [Creating a New User](#131-creating-a-new-user)
    - 13.2 [Changing a User's Role](#132-changing-a-users-role)
    - 13.3 [Resetting a Password](#133-resetting-a-password)
    - 13.4 [Deleting a User](#134-deleting-a-user)
    - 13.5 [Managing Role Permissions](#135-managing-role-permissions-admin-only)

14. [Clawback / Inadvertent Disclosure (Manager+)](#14-clawback--inadvertent-disclosure-manager)
    - 14.1 [Marking a Clawback Demand](#141-marking-a-clawback-demand)
    - 14.2 [Monitoring Clawback Status](#142-monitoring-clawback-status)
    - 14.3 [Resolving a Clawback](#143-resolving-a-clawback)

15. [Deduplication Report (Manager+)](#15-deduplication-report-manager)
    - 15.1 [Running the Report](#151-running-the-report)
    - 15.2 [Understanding the Metrics](#152-understanding-the-metrics)
    - 15.3 [Exporting for Court Disclosure](#153-exporting-for-court-disclosure)

16. [Review Batching (Manager+)](#16-review-batching-manager)
    - 16.1 [Creating Batches](#161-creating-batches)
    - 16.2 [Assigning Batches to Reviewers](#162-assigning-batches-to-reviewers)
    - 16.3 [Working Through Your Batch (Reviewer)](#163-working-through-your-batch-reviewer)
    - 16.4 [Tracking Batch Progress](#164-tracking-batch-progress)
    - 16.5 [Manual Batch Editing](#165-manual-batch-editing)

17. [Managing Custodians (Manager+)](#17-managing-custodians-manager)
    - 17.1 [The Custodian Inventory](#171-the-custodian-inventory)
    - 17.2 [Editing Custodian Profiles](#172-editing-custodian-profiles)
    - 17.3 [Renaming a Custodian](#173-renaming-a-custodian)
    - 17.4 [Merging Custodians](#174-merging-custodians)
    - 17.5 [Reassigning Documents](#175-reassigning-documents)
    - 17.6 [Managing Collections](#176-managing-collections)
    - 17.7 [Collection Scope](#177-collection-scope)

18. [Legal Hold Tracking (Manager+)](#18-legal-hold-tracking-manager)
    - 18.1 [Setting a Legal Hold](#181-setting-a-legal-hold)
    - 18.2 [Uploading Hold Documents](#182-uploading-hold-documents)
    - 18.3 [Case Hold Summary and Timeline](#183-case-hold-summary-and-timeline)

19. [Generating Reports (Manager+)](#19-generating-reports-manager)
    - 19.1 [Defensibility Report](#191-defensibility-report)
    - 19.2 [Rebuilding the Search Index (Admin)](#192-rebuilding-the-search-index-admin)

20. [Case Maintenance (Manager+)](#20-case-maintenance-manager)
    - 20.1 [Matter Profile](#201-matter-profile)
    - 20.2 [Case Archive](#202-case-archive)
    - 20.3 [Issue Coding Fields Admin](#203-issue-coding-fields-admin)
    - 20.4 [De-NIST Filter Configuration](#204-de-nist-filter-configuration)
    - 20.5 [Hash Integrity Verification](#205-hash-integrity-verification)
    - 20.6 [Closed-Case Protections](#206-closed-case-protections)

21. [Exhibits (Manager+)](#21-exhibits-manager)
    - 21.1 [Creating Exhibit Sets](#211-creating-exhibit-sets)
    - 21.2 [Marking Exhibits During Review](#212-marking-exhibits-during-review)
    - 21.3 [Managing Exhibits](#213-managing-exhibits)
    - 21.4 [Exporting Binder PDFs](#214-exporting-binder-pdfs)

22. [Security](#22-security)
    - 22.1 [Session Timeout](#221-session-timeout)

- [Appendix A: Role Permissions Reference](#appendix-a-role-permissions-reference)
- [Appendix B: Tag Categories Reference](#appendix-b-tag-categories-reference)
- [Appendix C: Search Syntax Quick Reference](#appendix-c-search-syntax-quick-reference)
- [Appendix D: UI Tips](#appendix-d-ui-tips)
- [Appendix E: Troubleshooting](#appendix-e-troubleshooting)

---

## 1. Getting Started

### 1.1 Logging In

The platform runs in your web browser. No software installation is required on your workstation.

**Prerequisites:** Your administrator must have created your account before you can log in.

**Steps:**

1. Open your web browser (Chrome, Edge, or Firefox).
2. Navigate to the platform URL provided by your administrator (typically an internal firm network address).
3. On the login screen, enter your **Username** and **Password**.
4. Click **Login**.

**Result:** You are taken to the Home page, which shows the case selector and platform status dashboard.

> ⚠️ **Warning:** Passwords are case-sensitive. If you cannot log in, contact your administrator to reset your password — do not share passwords with other users, as every action you take is logged under your username.

[Screenshot: Login screen with Username and Password fields]

---

### 1.2 Selecting a Case

The platform is multi-case. Every piece of work (ingestion, review, production) happens inside a specific case. You must select a case before any module becomes functional.

**Prerequisites:** At least one case must exist. Administrators and Managers can create new cases from the Home page.

**Steps:**

1. On the Home page, locate the **Case Selector** panel near the top of the page.
2. If cases exist, they appear as a list of folders detected in the configured cases directory.
3. Click the case name you want to work on.
4. The platform loads the case database and activates the sidebar navigation.

**Result:** The selected case name appears in the sidebar header. All modules now operate on that case's data.

> ⚠️ **Warning:** If you do not see your case in the list, the case folder may not contain a `case.db` database file, or the case folder may not be under the configured cases root. Contact your administrator.

[Screenshot: Home page with case list and a case selected]

**Production History panel (after a case is selected):** below the dashboard charts, the Home page shows a **Production History** grid listing every outbound production run for the case — Volume, Date, Format, Mode, First Bates, Last Bates, Docs, Withheld, Redacted, By, and **Status** (`finalized`, `aborted`, `pass1_complete`, `in_progress`). Aborted runs render with `—` placeholders for the Bates fields and `0` under Docs. The grid is the paralegal-visible forensic record of every production attempt; aborted runs are intentionally excluded from the court-facing defensibility report's section 6.2 Production Run History but remain visible here for case-management traceability.

---

### 1.3 Understanding Your Role

Your role determines which modules you can access and which actions you can perform. The platform uses a **permission-based access system** built on top of named roles. Administrators can customize exactly which permissions each role has.

**Default roles:**

| Role | Badge | What You Can Do |
|------|-------|-----------------|
| **Admin** | 👑 Admin | Everything — including user management, audit log access, and permission configuration |
| **Manager** | 🏢 Manager | All case work — ingestion, processing, analytics, review, redaction, production, sync |
| **Reviewer** | 📋 Reviewer | Review module — search, tag, comment, redact, view documents, and save/share searches |
| **Expert** | 🔬 Expert | Limited review — search, tag, run STR, save personal searches, download produced documents only |

Administrators can also create **custom roles** with any combination of permissions (see Section 13.5). Your role badge appears in the sidebar below your username.

See [Appendix A](#appendix-a-role-permissions-reference) for the full permissions matrix.

---

### 1.4 Navigating the Sidebar

The sidebar on the left lists every module available to your role. Click any item to navigate to that module.

Modules appear in this order:

| Sidebar Entry | Purpose |
|---------------|---------|
| **Home** | Case selection, service status, user management (Admin) |
| **1 Ingestor** | Scan and register new files into the case |
| **2 Processor** | Extract text, deduplicate, and image documents |
| **3 Analytics** | Email threading, near-duplicate detection, and deduplication report |
| **4 Review** | Search, tag, review, redact, and run Search Term Reports |
| **5 Production** | Outbound production, inbound production loading, and privilege log |
| **6 Sync** | Push/pull documents to Filevine |
| **7 Exhibits** | Exhibit sets, exhibit marking, and binder PDF export |

> ⚠️ **Warning:** If a module does not appear in your sidebar, you do not have the required role to access it. Attempting to navigate directly to a restricted URL will show an "Access Denied" message.

---

## 2. Ingesting Documents (Manager+)

### 2.1 Preparing Files for Ingestion

Ingestion registers every file in a folder into the case database and records its MD5 fingerprint. Before ingesting, your source files must be in the right place.

**Prerequisites:** Manager or Admin role. A case must be selected.

**Steps:**

1. Locate the case folder on the file system (your administrator can provide the path, typically under the configured cases root directory).
2. Inside the case folder, create or identify the **`Ingest`** subfolder.
3. Copy or move your source files into `Ingest\`. You can organize them into subfolders — the ingestor scans recursively.
4. For PST files: copy the `.pst` file directly into `Ingest\`. The system will extract its contents automatically during processing.
5. For ZIP or RAR archives: copy the archive into `Ingest\`. The system will extract their contents during processing.

**Result:** Your source files are waiting in the `Ingest\` folder, ready to be registered.

> ⚠️ **Warning:** Never place files into `Processed\`, `Produced\`, `Inbound\`, or `Temp_Explode\`. The ingestor automatically excludes these system folders from scanning. Files placed there will not be ingested.

> ⚠️ **Warning:** Do not modify or move files in `Ingest\` after ingestion. The platform records each file's original path. Moving files post-ingestion breaks the path record.

---

### 2.2 Running an Ingestion Scan

Ingestion scans the `Ingest\` folder, computes MD5 hashes for every file, and registers each file in the case database with a unique control number.

**Prerequisites:** Files must be placed in the `Ingest\` folder. A custodian name must be decided (see Section 2.3).

**Steps:**

1. Navigate to **1 Ingestor** in the sidebar.
2. The page shows a case statistics header (total ingested, processed, and unprocessed documents).
3. In the **Scan Folder** field, verify the path points to the correct `Ingest\` subfolder. You can change this to any subfolder if you want to ingest a subset.
4. Enter the **Custodian Name** — the person or source whose documents these are (e.g., "John Smith", "Jane Doe's Laptop", "Opposing Counsel Initial Disclosures"). This field is required.
5. Set the **Thread Count** if desired (default is appropriate for most systems).
6. Review the interactive **Folder Preview** — it shows the file type and size breakdown for what will be scanned.
7. Click **Run Ingestion**.
8. Watch the step-by-step progress panel as files are scanned and registered.
9. When complete, review the **Post-Scan Results Card** showing how many files were registered, skipped (already registered), and any errors.

**Result:** Every file in the scan folder now has a record in the case database with status `New`, assigned a control number in the format `DOC-000001`.

> ⚠️ **Warning:** The Custodian field cannot be changed after ingestion without running a backfill. Enter it correctly — it is the key for organizing documents in the Review module's folder tree navigator.

> ⚠️ **Warning:** Ingestion does not extract text or create PDFs. Those steps happen in the Processor (Section 3).

[Screenshot: Ingestor page showing folder preview and scan settings]

---

### 2.3 Assigning Custodians

Every ingestion run assigns one custodian to all files registered in that run. To ingest documents from multiple custodians, run the ingestor separately for each custodian's folder, changing the Custodian Name each time.

**Steps:**

1. Create subfolders under `Ingest\` organized by custodian (e.g., `Ingest\John Smith\`, `Ingest\Jane Doe\`).
2. Copy each custodian's files into their respective subfolder.
3. In the Ingestor, set the **Scan Folder** to `Ingest\John Smith\` and set **Custodian Name** to "John Smith". Run the scan.
4. Repeat for each custodian, changing both the Scan Folder and Custodian Name each time.

**Result:** Documents from each custodian are tagged separately in the database and will appear under their own branch in the Review module's folder tree.

> ⚠️ **Warning:** If you ingest all documents in a single run with a single custodian name, they will all appear under that one custodian in the folder tree — even if they came from different people. Re-attribution requires a manual backfill.

---

### 2.4 Re-running Ingestion (Adding More Files)

The ingestor is idempotent: re-running it on a folder that has already been ingested will skip files that are already registered and only add new ones.

**Steps:**

1. Copy new files into the `Ingest\` folder (or the appropriate custodian subfolder).
2. Navigate to **1 Ingestor**.
3. Set the Custodian Name (use the same custodian name if adding to an existing collection; use a new name for new custodians).
4. Click **Run Ingestion**.

**Result:** Only new files are registered. Previously ingested files are skipped without creating duplicates. The post-scan results card shows the count of newly registered vs. skipped files.

---

## 3. Processing Documents (Manager+)

### 3.1 Understanding the Three Processing Phases

Processing transforms raw registered files into searchable, viewable documents. It runs in three sequential phases:

| Phase | What It Does |
|-------|-------------|
| **Phase 1: Container Explosion** | Extracts attachments from emails, ZIP files, PST archives. Registers each extracted file as a child document linked to its parent. Repeats recursively until no containers remain. PST extraction uses the headless `libpff` pure-Python engine as its primary path, with automatic fallback to Microsoft Outlook COM when `libpff` is unavailable. After extraction, MSG/EML containers are promoted for Phase 2 processing, while PST/ZIP shells are marked complete. |
| **Phase 2: Text Extraction & Indexing** | Sends each document to Apache Tika for text and metadata extraction. Indexes extracted text into OpenSearch for full-text search. Runs deduplication (MD5 exact-match). Runs OCR via Tesseract automatically on image-only PDFs that have no extractable text. Calculates content hash for near-duplicate detection in Analytics. A **Cancel** button is available during Phase 2 to safely stop a long-running extraction. |
| **Phase 3: Email Imaging** | Converts every `.msg` and `.eml` email to a standardized PDF using the platform's built-in imaging engine (no COM dependency). These PDFs are stored in the `Processed\` folder and are the files attorneys see in the Review module. |

Each phase can be run independently. If a phase fails partway through, you can re-run it — already-processed documents are skipped.

---

### 3.2 Running the Processor

**Prerequisites:** Documents must be ingested (status `New`) before processing. Manager or Admin role required.

**Steps:**

1. Navigate to **2 Processor** in the sidebar.
2. The page shows a **Queue Stats Dashboard** — total documents queued, file type breakdown, and any errors from prior runs.
3. Review the **Phase Cards** to understand what will run.
4. Click **Run Processor** (or the individual phase button if you need to run a specific phase only).
5. Monitor the colored status banners as each phase progresses. Phase 1 shows container explosion progress; Phase 2 shows text extraction with per-file status; Phase 3 shows email imaging progress.
6. When all phases complete, review the summary showing processed counts, errors, and skipped (already-processed) counts.

**Result:** Documents move to status `Processed` (or `Master` if they survive deduplication as the canonical copy). Their text is indexed in OpenSearch and their PDFs are in the `Processed\` folder.

> ⚠️ **Warning:** If OpenSearch is not running, text extraction will still complete but full-text indexing will fail. Check the service status on the Home page before running the Processor.

[Screenshot: Processor page showing phase cards and status banners during a run]

#### Background Processing & Job Monitor

Processing runs as a **background worker** — a separate system process that is completely independent of your browser session. This means:

- **You can close the browser tab.** Processing continues even if you navigate away, close the tab, or lose your internet connection.
- **You can log out and back in.** The worker process runs on the server — it does not depend on your Streamlit session being alive.
- **Automatic conflict prevention.** The platform prevents two processing jobs from running simultaneously on the same case. If a job is already running, the Processor page shows the live monitor instead of the Run button.

**Monitoring a running job:**

1. Navigate to **2 Processor** while a job is running.
2. The **Job Monitor** panel displays automatically, showing:
   - The current phase (color-coded: blue for Phase 1, green for Phase 2, purple for Phase 3).
   - A progress bar and document count (e.g., "1,234 / 5,678").
   - The current status message (e.g., "Phase 2: Extracting text — 1,234 of 5,678 documents").
   - An expandable **Recent Warnings** section showing the last 10 warnings from the worker (partial extractions, imaging failures, etc.).
3. The monitor auto-refreshes every 2 seconds.

**Cancelling a running job:**

1. In the Job Monitor panel, click **⛔ Cancel Processing**.
2. The worker finishes its current document, then stops cleanly. Already-processed documents are preserved — they do not need to be re-run.
3. The monitor updates to show the cancellation status and a summary of what was completed.

**After completion:**

When a background job finishes, the Processor page displays a completion banner with summary statistics (documents processed, emails imaged, suspicious files flagged). If a Processing Audit CSV was generated, a download button is available.

> ⚠️ **Warning:** If a background worker process is terminated unexpectedly (e.g., by a system restart), its job record may remain in "running" status. The platform detects this condition (zombie PID) and allows you to start a new run.

---

### 3.3 Handling Processing Errors

Documents that fail processing are recorded with status `Error` in the database. The Processor never stops for a single file error — it logs it and continues.

**Steps to review errors:**

1. After a Processor run, the summary card shows the error count.
2. In the **Retry / Backfill Controls** section, click **Show Errors** to see which documents failed and why.
3. Common causes: corrupted files, password-protected documents, very large files exceeding Tika's timeout.
4. For documents you need, troubleshoot the source file (e.g., remove password protection) and re-run the Processor — it will attempt only the errored documents.

> ⚠️ **Warning:** Password-protected files cannot be extracted by the platform. You must obtain the password, manually unlock the file, replace it in `Ingest\`, and re-run ingestion on that file before processing will succeed.

---

### 3.4 Verifying Processing Results

After processing, confirm the results before running Analytics.

**Steps:**

1. Navigate to the **Home** page. The case statistics dashboard shows counts for Ingested, Processed, and Unprocessed documents.
2. Navigate to **4 Review** and set the search to return all documents (leave the search bar empty and click Search).
3. Verify that the document count matches your expectations.
4. Check that PDFs are visible in the document preview panel for a sample of emails.
5. Check the **🔍 Dedup Report** tab in **3 Analytics** to confirm deduplication ran correctly (see Section 15).

> ⚠️ **Warning:** Do not run Analytics until all ingestion and processing is complete. Email threading and near-duplicate detection give incorrect results if run mid-ingestion.

---

### 3.5 Processing Exception Report

After processing, you can generate a detailed report of all processing failures for QC review and defensibility documentation.

**Prerequisites:** At least one Processor run must have completed. Manager or Admin role required.

**Steps:**

1. Navigate to **2 Processor** in the sidebar.
2. Locate the **Processing Exception Report** section.
3. The report header shows 4 key metrics: total documents attempted, total errors, error rate percentage, and unique error types encountered.
4. Click **Download Exception Report (.xlsx)** to export a 3-sheet Excel workbook:
   - **Sheet 1 — Summary:** The 4 key metrics and a breakdown of error counts by error type.
   - **Sheet 2 — Error Details:** Every failed document with its control number, filename, custodian, error message, and the processing phase where it failed.
   - **Sheet 3 — Error Type Analysis:** Grouped view showing each distinct error type, its frequency, and example documents.

**Result:** A downloadable Excel file documenting all processing failures. This report is useful for QC review (identifying systemic issues like password-protected files) and for defensibility documentation showing that failures were identified and addressed.

> ⚠️ **Warning:** The exception report reflects the current database state. If you re-run the Processor and previously errored documents succeed, they will no longer appear in the report. Export the report before re-running if you need a historical record.

---

## 4. Running Analytics (Manager+)

### 4.1 Email Threading

Email threading reconstructs conversation chains and identifies the minimum set of emails a reviewer must read to have complete context.

**One-sentence purpose:** Threading suppresses redundant earlier messages in email chains so reviewers only need to code the final, inclusive message that contains the full conversation.

**Prerequisites:** Processing must be complete. All internal email metadata (`message_id`, `in_reply_to`) must be populated by Tika. Manager or Admin role required.

**Steps:**

1. Navigate to **3 Analytics** in the sidebar.
2. Click the **Email Threading** tab.
3. Review the document count shown — this is the population that will be analyzed.
4. Click **Run Threading Analysis**. The system builds a conversation graph and shows you the results: how many threads were found, how many emails are Inclusive (must-read), and how many will be suppressed.
5. Review the metrics carefully. If the numbers look wrong (e.g., almost everything is suppressed), stop — do not execute.
6. If the analysis looks correct, click **Execute** to write the threading tags to the database.

**Result:** Emails tagged `Thread-Suppressed` will no longer appear in the Review grid by default (they are hidden when "Show Suppressed Items" is unchecked). Inclusive emails — the final message in each thread — remain visible and contain the full conversation context.

> ⚠️ **Warning:** Threading is a one-time operation per run. Re-running it clears and recalculates all thread tags. Use the re-run option (hidden behind a confirmation expander) only if you have ingested new emails since the last run.

> ⚠️ **Warning:** Threading only applies to internal documents (your client's documents). Opposing counsel productions are excluded from threading analysis.

> ⚠️ **Warning:** Attachments are never suppressed by threading. Only root-level emails participate in thread analysis.

[Screenshot: Analytics page showing threading results — inclusive/suppressed counts]

---

### 4.2 Near-Duplicate Detection

Near-duplicate detection identifies documents that are substantially similar (default threshold: 90% content overlap) — such as minor contract revisions, form letters, or boilerplate with trivial variations.

**One-sentence purpose:** Near-duplicate detection lets reviewers bulk-code entire families of nearly identical documents by coding only the Principal document in each cluster.

**Prerequisites:** Processing must be complete AND text must be indexed in OpenSearch. Near-duplicate detection cannot run without OpenSearch. Manager or Admin role required.

> 🆕 **Improved similarity accuracy (v2.16).** The similarity engine now compares documents using **k-gram shingling** — sliding windows of five consecutive words — instead of comparing individual words. This preserves phrase structure, so documents that share the same vocabulary but say different things (for example, two invoices on the same template with different line items) are no longer mistakenly clustered as near-duplicates. The practical effect is fewer false-positive suppressions on template-style documents.

> 🆕 **Suppression is now reviewer-confirmed, not automatic (v2.16).** Running near-duplicate analysis no longer applies the `NearDupe-Suppressed` tag directly. Instead it **identifies and saves the clusters** for a reviewer to confirm one at a time (see Section 4.7). Until a reviewer confirms a document as a duplicate, it stays in the active review population. This "fail-open" design means nothing is ever hidden from production on the algorithm's say-so alone — a human attests to every suppression.

**Steps:**

1. Navigate to **3 Analytics** and click the **Near-Duplicate Detection** tab.
2. Review the pre-run breakdown showing Total Duplicates, Preserved Attachments (which cannot be safely suppressed), and Actual Reduction (standalone documents that are candidates for suppression).
3. Adjust the Jaccard threshold if desired (default 0.90 is recommended for most cases).
4. Click **Run Near-Duplicate Analysis**.
5. Review the cluster preview showing which documents are elected as Principals and which become suppression candidates.
6. Click **Execute** to **save the clusters for review** (no tags are written yet).
7. Confirm the clusters in the Review module's **Near-Duplicate Clusters** surface (Section 4.7) — that is where the `NearDupe-Suppressed` tag is actually applied, per your decisions.

**Result:** The clusters are persisted and surfaced for reviewer confirmation. Each cluster's Principal document (the most metadata-rich copy, or the earliest control number in a tie) represents the cluster. Documents are not hidden from the review view until a reviewer confirms them as duplicates.

> ⚠️ **Warning:** Child documents (attachments) are never suppressed as near-duplicates, even if their content is identical to another document. This preserves the evidentiary value of each email family. A family-attached document remains visible (and producible) even when a reviewer confirms it is a duplicate.

> ⚠️ **Warning:** Near-duplicate detection requires OpenSearch to be running. If the service is down, this tab will show an error.

---

### 4.3 When to Run Analytics

Run analytics **once**, after all ingestion and processing is complete for the initial collection. If you add more documents later, you must re-run analytics to include them.

**Recommended sequence:**

1. Complete all ingestion for the matter
2. Complete all processing (all three phases)
3. Run Email Threading
4. Run Near-Duplicate Detection
5. Begin review

Do not run analytics on a partial collection — threading and near-dupe detection are calculated across the entire corpus, so partial runs will produce incorrect suppression decisions.

---

### 4.4 Understanding Suppressed Documents

"Suppressed" does not mean deleted. Suppressed documents remain in the database and can be viewed at any time by enabling the **Show Suppressed Items** checkbox in the Review grid.

There are three categories of suppression:

| Tag | How It's Assigned | What It Means |
|-----|-------------------|---------------|
| `Duplicate (MD5)` | Automatically during Phase 2 processing | An exact copy of another document (same MD5 hash). The duplicate was physically deleted from `Temp_Explode\` after deduplication. The canonical copy (Master) remains. |
| `Thread-Suppressed` | By Analytics — Email Threading | An earlier message in a thread whose content is fully quoted in a later inclusive email. |
| `NearDupe-Suppressed` | By a **reviewer confirming a near-duplicate cluster** (Section 4.7), after Analytics identifies the clusters | A document that is 90%+ content-similar to a Principal document in its cluster AND has been confirmed as a duplicate by a reviewer. Family-attached documents are never given this tag even when confirmed (family integrity wins). |

> ⚠️ **Warning:** `Thread-Suppressed` and `Junk Image` are generated exclusively by the Analytics/processing modules and cannot be hand-applied. As of v2.16, `NearDupe-Suppressed` is applied and removed through the reviewer-driven **Near-Duplicate Clusters** confirmation workflow (Section 4.7) — marking a member "Distinct" removes the tag, marking it "Same" applies it (unless the document is family-attached).

---

### 4.5 Custodian Overlap Analysis

Custodian Overlap Analysis shows which custodians share documents based on content hash. This is especially useful during deposition preparation — it identifies which custodians had access to the same documents.

**Prerequisites:** Processing must be complete (content hashes must be calculated). Reviewer or higher role required.

**Steps:**

1. Navigate to **3 Analytics** and click the **Custodian Overlap** tab.
2. The system builds a cross-custodian matrix comparing document content hashes across all custodians.
3. A Plotly heatmap displays the results: each cell shows the number of shared documents between two custodians. Darker cells indicate more overlap.
4. Hover over any cell to see the exact count and the custodian pair.
5. Click on a cell to drill down and see the specific shared documents.

**Result:** A visual matrix showing document overlap between every custodian pair. High overlap between custodians may indicate close working relationships, shared projects, or distribution lists — all useful context for deposition preparation and case strategy.

> ⚠️ **Warning:** Overlap analysis is based on content hash (identical content), not near-duplicate similarity. Two documents with minor formatting differences will not appear as overlapping even if the text is substantively the same.

---

### 4.6 Concept Explorer

The Concept Explorer helps attorneys discover related and associated terms they may not have considered. This is particularly valuable during search term negotiations with opposing counsel — it reveals terminology used in the actual document corpus rather than relying on assumptions.

**Prerequisites:** Documents must be processed and indexed in OpenSearch. Reviewer or higher role required.

**Steps:**

1. Navigate to **3 Analytics** and click the **Concept Explorer** tab.
2. Enter a seed search term in the input field (e.g., "merger").
3. Click **Explore**.
4. The system runs an OpenSearch `significant_text` aggregation, which identifies terms that appear disproportionately often in documents containing your seed term compared to the overall corpus.
5. Results appear as a list of associated terms ranked by significance score, showing each term and how strongly it correlates with your seed term.

**Result:** A list of related terms discovered from the actual document corpus. For example, searching "merger" might reveal associated terms like "acquisition," "due diligence," "closing," "shareholder," or company-specific jargon that would not appear in a generic legal dictionary.

> ⚠️ **Warning:** Concept Explorer requires OpenSearch to be running. The quality of results depends on the size and diversity of the document corpus — very small collections may not produce meaningful associations.

---

### 4.7 Reviewing Near-Duplicate Clusters (v2.16)

After Analytics identifies near-duplicate clusters (Section 4.2), a reviewer confirms them in the Review module's **Near-Duplicate Clusters** surface. This is where suppression actually happens — the algorithm proposes, a human disposes, and every suppression is attributable to a named reviewer for defensibility.

**One-sentence purpose:** Confirm or reject each algorithm-proposed near-duplicate so the suppression record reflects human judgment, not just a similarity score.

**Prerequisites:** Near-duplicate analysis has been run and clusters saved (Section 4.2, Step 6). Reviewer role or higher.

**Steps:**

1. Open the **Near-Duplicate Clusters** surface in the Review module. The left side lists every cluster with a progress badge (how many members still need a decision).
2. Select a cluster. The Principal document and each candidate member are shown, with a **side-by-side text difference** view so you can see exactly what differs between the Principal and each member.
3. For each member, choose **Same** (a true duplicate — suppress it) or **Distinct** (genuinely different — keep it in review). A member attached to an email family is shown but cannot be suppressed; it is retained for family integrity regardless of your decision.
4. When every member is decided, **attest** the cluster. Attestation records your username and the timestamp.
5. Move to the next cluster. The progress badge updates as you go.

**Result:** Confirmed members receive the `NearDupe-Suppressed` tag and drop out of the default review view; members marked Distinct stay in review; family-attached members are always retained. The attestation record (who confirmed each cluster, and when) flows into the Defensibility Report's near-duplicate section (Section 19.1).

> 💡 **A document can appear in more than one cluster.** If you decide a document is Same/Distinct in one cluster, that decision applies to the document everywhere it appears — you do not have to re-decide it in another cluster.

> ⚠️ **Re-running discards reviewer decisions.** If you re-run near-duplicate analysis after making decisions, the previous clusters and all confirmations are cleared. The Analytics tab requires you to type an explicit confirmation phrase before it will discard existing reviewer work.

---

## 5. Reviewing Documents (All Roles)

### 5.1 The Review Grid

The Review Grid is the primary interface for daily document review. It presents every processed document in a sortable, filterable data grid with integrated document preview, metadata inspection, and tagging.

**Prerequisites:** A case must be selected. Documents must be processed.

The grid displays documents in family-grouped order: parent emails appear first, with attachments indented beneath them using a `↳` visual indicator. This hierarchy is preserved at arbitrary depth — a grandchild attachment always appears directly beneath its parent, not pooled at the bottom of the family block.

**Default view behavior:**
- Suppressed documents (duplicates, thread-suppressed, near-dupe-suppressed) are hidden
- Junk images (files under 30KB) are hidden
- Documents are sorted by Family Group

**Family View (Manager+):** Toggle **👪 Family View** to switch from the flat grid to a grouped display where root documents appear as collapsible expanders containing their attachment sub-tables. This makes it easy to review entire email families at once.

[Screenshot: Review Grid showing family-grouped documents with attachment hierarchy]

---

### 5.2 Searching Documents

#### 5.2.1 Basic Search

Full-text search runs against the OpenSearch index, which contains the extracted text of every processed document.

**Steps:**

1. In the **Search** bar at the top of the Review page, type your search query.
2. Press **Enter** or click the search button.
3. The Review Grid updates to show only documents matching your query, ranked by relevance.
4. Each result shows a snippet preview with your search terms highlighted in yellow.

**Result:** The grid filters to documents containing your search terms. The search also scopes the document count shown in the folder tree navigator.

> ⚠️ **Warning:** Search requires OpenSearch to be running. If OpenSearch is unavailable, the search bar will show an error and return no results. You can still filter the grid using the column filters (Section 5.3.1) when OpenSearch is down.

> ⚠️ **Warning:** Leaving the search bar empty and pressing Enter returns all documents (subject to your active column filters and checkbox settings). This is the correct way to view the full collection.

#### 5.2.2 Boolean Operators and Advanced Syntax

The search engine supports full Boolean syntax. See [Appendix C](#appendix-c-search-syntax-quick-reference) for a complete one-page cheat sheet.

| Example | What It Finds |
|---------|---------------|
| `contract AND breach` | Documents containing both words |
| `"breach of contract"` | Documents with that exact phrase |
| `contract NOT amendment` | Documents with "contract" but not "amendment" |
| `negligen*` | "negligence," "negligent," "negligently," etc. |
| `recieve~` | Fuzzy match — also finds "receive" and common misspellings |
| `email_from:smith` | Documents where the From field contains "smith" |
| `(contract OR agreement) AND breach` | Grouped Boolean logic |

> ⚠️ **Warning:** Some characters have special meaning in the search syntax (e.g., `+`, `-`, `"`, `(`, `)`). If you need to search for these characters literally, enclose the term in quotes. Malformed queries are caught by the system's pre-validation before submission, and a helpful error message will appear.

#### 5.2.3 Saving and Loading Searches

You can save named searches for reuse and access a recent search history.

**To save a search:**

1. Run the search you want to save.
2. Click the **💾 Save** button next to the search bar.
3. Enter a name for the search.
4. Click **Save**.

**To load a saved search:**

1. Click **📌 Saved Searches** to expand the saved search panel.
2. Click the name of the search you want to load. The query is automatically applied.

**To view recent searches:**

1. Click **🕐 Recent** to expand the recent search panel.
2. The last 10 searches you ran are listed. Click any to reload it.
3. To clear recent history, click **🧹 Clear All** at the top of the Recent panel.

#### 5.2.4 Global (Shared) Searches

Managers and Admins can create searches that are available to all users on the case.

**Steps:**

1. Run a search and click **💾 Save**.
2. Before saving, check the **Share with all users** checkbox.
3. Click **Save**.

**Result:** The search appears in the Saved Searches panel for every user on this case, labeled as a global search.

[Screenshot: Saved Searches panel showing personal saves and global shared searches]

---

### 5.3 Filtering the Grid

#### 5.3.1 Column Filters

Each column in the Review Grid has a filter row directly below the column header. Type in any filter field to narrow the grid to documents matching that value.

**Steps:**

1. In the grid header row, locate the filter input below the column you want to filter.
2. Type your filter value (e.g., type "Smith" in the `custodian` filter to show only documents from that custodian).
3. The grid updates immediately with each keystroke.
4. To clear a filter, delete the text from the filter field.

Multiple column filters are applied simultaneously (AND logic). For example, filtering `custodian` to "Smith" and `file_extension` to "pdf" shows only PDFs from Smith.

#### 5.3.2 Show/Hide Suppressed Documents

Three checkboxes control which document populations are visible:

| Checkbox | Default | Effect |
|----------|---------|--------|
| **Show Suppressed Items (Duplicates & Threads)** | Off | When checked, shows exact duplicates and thread/near-dupe suppressed documents |
| **Hide Junk Images (<30KB)** | On | When unchecked, shows small image files (signature icons, tracking pixels, etc.) |
| **Hide Not Responsive** | Off | When checked, hides documents tagged "Not Responsive" |

**Steps:**

1. Locate the checkbox panel above the Review Grid.
2. Toggle the checkbox to change the visible population.
3. The grid count updates immediately.

> ⚠️ **Warning:** Even with suppressed documents hidden, they remain in the database and in any export. Hiding suppressed documents only affects the Review Grid display.

#### 5.3.3 Folder Tree Navigator

The sidebar in the Review module contains a hierarchical folder tree that organizes the entire document corpus by source.

**Structure:**

```
All Documents
├── Internal
│   ├── John Smith
│   ├── Jane Doe
│   └── Server Share
└── Opposing Counsel A
    ├── Initial Disclosures
    └── Supplemental Production 1
```

**Steps:**

1. Click any branch in the folder tree to scope the Review Grid to only documents from that source.
2. Click **All Documents** at the root to return to the full corpus.
3. Document counts appear at each level.

---

### 5.4 Viewing a Document

**Steps:**

1. Click on any row in the Review Grid to select a document.
2. The document preview panel opens on the right side of the screen (or below the grid, depending on your screen size).
3. The preview panel has three tabs:
   - **📄 Native / Image** — renders the PDF version of the document inline in the browser. For emails, this is the rendered PDF. For PDFs, this is the original file. For other formats, this is the imaged PDF.
   - **📝 Extracted Text** — shows the raw text extracted by Tika. If STR highlighting is active (Section 7.5), search terms appear highlighted in yellow.
   - **📦 Production (Bates)** — if the document has been produced, shows the Bates-stamped final image and final extracted text.
4. Use the page navigation controls within the Native / Image tab to move through multi-page documents.

**Family navigation:**

- The sidebar panel shows the document's family tree (parent email, sibling attachments, child documents).
- Click any family member to jump directly to that document. If the target is filtered out of the current search results, the viewer enters **Peek mode** — loading the document directly without changing your grid or search. A **← Back to queue** button returns you to exactly where you left off. You can peek from a peeked document (chained peeks) and still return to your original position.
- Click **Show Full Family in Grid** to replace the current grid with all members of the document's family group (parent + all attachments), regardless of search or filter settings. A **← Back to search results** banner restores your prior search query and column filters.

[Screenshot: Review page with document selected and preview panel showing Native/Image tab]

---

### 5.5 Tagging Documents

Tags categorize documents for privilege, responsiveness, and review status. Tagging is the core activity of document review.

#### 5.5.1 Applying a Single Tag

**Steps:**

1. In the Review Grid, click on a document row to select it.
2. Scroll down to the **Tags** panel below the document preview.
3. Locate the tag category you want (e.g., **Privilege**, **Responsiveness**, or **Review Status**).
4. Click the tag you want to apply (e.g., **Attorney-Client Privilege**).
5. The tag is saved immediately to the database.

**Result:** The tag appears in the document's `tags` column in the grid. A color-coded badge is visible on the row: red for Privilege tags, green for Responsiveness tags, blue for Review Status tags.

> ⚠️ **Warning:** System tags (`NearDupe-Suppressed`, `Thread-Suppressed`, `Junk Image`) cannot be manually applied or removed. These are read-only badges generated by the Analytics module.

[Screenshot: Tag panel with Privilege category expanded and Attorney-Client Privilege selected]

#### 5.5.2 Removing a Tag

**Steps:**

1. Select the document.
2. In the Tags panel, locate the tag you want to remove.
3. Click the tag again to deselect it (tags toggle on/off).

**Result:** The tag is removed from the document immediately.

> ⚠️ **Warning:** If a document has redaction marks saved in the Redaction module, its privilege tags are controlled by the redaction marks — not manually. Removing a privilege tag on a redacted document from the Review module may be overwritten the next time the Redaction module syncs. See Section 6.6 for details.

#### 5.5.3 Bulk Tagging Multiple Documents

The Bulk Action Bar appears automatically when you select two or more rows in the Review Grid.

**Steps:**

1. Check the checkboxes next to the documents you want to bulk-tag. You can also select all visible documents using the header checkbox.
2. The **Bulk Action Bar** slides into view at the top of the page.
3. In the Bulk Action Bar, choose the tags you want to apply or clear.
4. Click **Apply Tags** to add the selected tags to all checked documents, or **Clear Tags** to remove the selected tags.

**Result:** Tags are applied or removed across all selected documents in a single database operation.

> ⚠️ **Warning:** Bulk tag operations cannot be undone through the UI. Before executing a large bulk action, verify that your selection is correct.

> ⚠️ **Warning:** System tags are protected from bulk overwrites. Bulk clearing will never remove `NearDupe-Suppressed`, `Thread-Suppressed`, or `Junk Image` tags.

#### Tag Cascade to Attachments

When you apply, remove, or clear tags on a parent document (email), those tags automatically cascade to all of that document's children (attachments). This ensures that privilege and responsiveness coding stays consistent across email families — you do not need to individually tag each attachment.

System tags are never affected by cascade. Redaction marks on child documents are also unaffected.

[Screenshot: Bulk Action Bar visible with multiple rows selected]

#### 5.5.4 Understanding Tag Categories

Tags are organized into categories. The default categories are:

| Category | Color | Examples |
|----------|-------|---------|
| **Privilege** | Red | Attorney-Client Privilege, Work Product, Common Interest Privilege, Joint Defense Privilege, Trade Secret |
| **Responsiveness** | Green | Responsive, Not Responsive, Hot Document |
| **Review Status** | Blue | Needs Review, Suppressed |

Privilege categories directly integrate with the Privilege Log generator (Section 9) and the Redaction module (Section 6). When you redact a document and assign a privilege reason, that tag is automatically added to the document.

See [Appendix B](#appendix-b-tag-categories-reference) for the complete default tag list.

#### 5.5.5 System Tags (Read-Only)

System tags are applied automatically and cannot be modified by users:

| System Tag | Set By | Meaning |
|------------|--------|---------|
| `NearDupe-Suppressed` | Analytics — Near-Duplicate Detection | This document is 90%+ content-similar to a Principal document |
| `NearDupe-Principal` | Analytics — Near-Duplicate Detection | This is the canonical representative of a near-duplicate cluster |
| `Thread-Suppressed` | Analytics — Email Threading | This email's content is fully contained in a later inclusive email |
| `Junk Image` | Processor — Phase 2 | This image file is under 30KB or under 150×150 pixels |

---

### 5.6 Adding Comments

Comments are free-text notes on a document visible to all users on the case.

**Steps:**

1. Select a document in the Review Grid.
2. Locate the **Comment** panel below the Tags panel.
3. Type your note in the comment field.
4. Click **Save Comment**.

**Result:** The comment is saved to the database and associated with that document. Comments are visible to all users and are logged in the audit trail with your username and timestamp.

> ⚠️ **Warning:** Comments are not private. Every user with access to the case can read every comment. Do not use comments for privileged work product notes intended for attorneys only.

---

### 5.7 Exporting the Review Grid to CSV (Manager+)

You can export the current state of the Review Grid (filtered view) to a CSV file for reporting or offline analysis.

**Prerequisites:** Manager or Admin role required.

**Steps:**

1. Apply any search queries and column filters to narrow the grid to the population you want to export.
2. Scroll to the bottom of the Review Grid.
3. Click the **⬇️ Export to CSV** button.
4. The browser downloads a CSV file containing all visible columns for all visible rows.

**Result:** A CSV file with the current grid contents. This export respects your active filters — it only includes documents currently shown in the grid.

> ⚠️ **Warning:** The CSV export includes document metadata but not document content (extracted text) or PDFs. For a production export with images and load files, use the Production module (Section 8).

---

### 5.8 Bates Batch Search

When responding to or analyzing interrogatory responses, you often receive large, unformatted lists of Bates numbers (e.g., `ABC-001005, ABC 1009; XYZ 003-005`). The Bates Batch Search engine handles this automatically.

**Steps:**

1. In the Review sidebar or search area, click **📋 Bulk Bates** to open the Bates batch input popover.
2. Paste the raw Bates citations directly — dirty formatting, mixed delimiters, hyphenated ranges — exactly as received.
3. Click **Parse & Search**.
4. The system's mathematical intersection logic expands ranges, normalizes formatting, and filters the Review Grid to documents whose Bates ranges contain any of the specified page numbers.

**Result:** The Review Grid shows only the documents containing the cited pages.

> ⚠️ **Warning:** Bates batch search requires that production Bates numbers be assigned. If a document has not been produced (no Bates number), it will not appear in Bates batch results even if it would otherwise match.

---

### 5.9 Micro-PDF Extraction (Extract Exact Pages)

After a Bates Batch Search, you can extract only the specific cited pages as individual single-page PDFs packaged into a ZIP file.

**Steps:**

1. Run a Bates Batch Search (Section 5.8) to filter the grid to the relevant documents.
2. Select the documents from which you want to extract pages (or select all).
3. Click **📑 Extract Exact Pages & ZIP**.
4. The system uses PyMuPDF to isolate the specific pages from each multi-page source PDF.
5. A ZIP file is prepared and a download button appears.
6. Click the download button to save the ZIP to your computer.

**Result:** A ZIP file containing individual single-page PDFs named by control number and page number.

> ⚠️ **Warning:** This extraction creates a new ZIP file with copies of specific pages. It does not modify the source PDFs.

---

### 5.10 Issue Coding / Custom Coding Fields

Issue coding allows attorneys to classify documents using case-specific custom fields defined by the case administrator. These fields appear in the coding panel below the standard tags and provide structured data capture beyond simple tagging.

**Prerequisites:** Custom coding fields must be configured by an Admin (see Section 20.3). Reviewer or higher role required to fill in coding values.

**Steps:**

1. Select a document in the Review Grid.
2. Scroll to the **Coding** panel below the Tags panel.
3. Custom fields appear based on their configured type:
   - **Picklist fields** — Select a value from the dropdown (e.g., "Contract Type": Master Agreement, Amendment, SOW, NDA).
   - **Text fields** — Type free-form text (e.g., "Key Issue Summary").
   - **Boolean fields** — Check or uncheck a checkbox (e.g., "Contains PII").
4. Values are saved automatically when you change them.

**Result:** The document's coding values are stored in the database and are visible to all reviewers on the case.

> ⚠️ **Warning:** Issue coding values are attorney work product. They are intentionally excluded from production load files (DAT, CSV, OPT) to prevent inadvertent disclosure of case strategy. Issue coding data is available only within the platform and in CSV exports from the Review Grid.

---

### 5.11 Exhibit Designation (Mark as Exhibit)

For documents that have been produced (assigned Bates numbers), you can designate them as exhibits for depositions, motions, hearings, or trial.

**Prerequisites:** The document must have been produced (Bates number assigned). At least one exhibit set must exist (see Section 21). Reviewer or higher role required to mark exhibits; Manager or higher required to manage exhibit sets.

**Steps:**

1. Select a produced document in the Review Grid.
2. Scroll to the **Exhibits** section in the coding panel.
3. If the document is already in one or more exhibit sets, badges showing the set name and exhibit number are displayed.
4. Click **Mark as Exhibit**.
5. Select the target **Exhibit Set** from the dropdown (e.g., "Deposition of John Smith").
6. Enter the **Exhibit Number** — this is freeform text to accommodate any convention the presiding judge requires (e.g., "1", "A", "P-1", "Exhibit 14").
7. Optionally enter a **Description** (e.g., "Email from Smith to Jones re: contract terms, 3/15/2025").
8. Click **Save**.

**Result:** The document is added to the selected exhibit set. The exhibit badge appears on the document in the Review Grid. The same document can be marked as an exhibit in multiple sets.

> ⚠️ **Warning:** Only produced documents (those with Bates numbers) can be designated as exhibits. If you need to mark an unproduced document, produce it first.

---

### 5.12 Production History

For documents that have been produced in one or more production volumes, the Review module displays the complete production history.

**Prerequisites:** The document must have been produced at least once. Reviewer or higher role required.

**Steps:**

1. Select a produced document in the Review Grid.
2. In the document detail panel, locate the **Production History** expander.
3. Click to expand it. A table shows every production record for this document:

| Column | Description |
|--------|-------------|
| **Volume** | The production name (e.g., "VOL001") |
| **Bates Range** | The assigned Bates range (e.g., "ABC-000045 - ABC-000048") |
| **Type** | Original, Supplemental, or Replacement |
| **Date** | The date the production was run |

4. If the document's processed PDF has been modified since the most recent production (e.g., due to re-imaging), a warning banner appears: **"Stale Production — the processed PDF is newer than the most recent production."** This indicates the produced version may not reflect the current state of the document.

**Result:** A complete audit trail of every time the document was produced, with Bates ranges and production types.

> ⚠️ **Warning:** A "Stale Production" warning means the document was re-processed or re-imaged after its last production. Consider whether a supplemental or replacement production is needed to deliver the updated version.

> ℹ️ **Note:** The Production History section on the document detail panel, the Home page's "📦 Production History" widget, and the Defensibility Report's Section 6.2 all show only **outbound** productions — productions the firm performed. Inbound ingests from opposing counsel are tracked separately under the dedicated **9 Inbound Productions** module and in the audit log, but do not appear in production-history surfaces. This keeps the court-facing defensibility report free of material that could be misread as "productions we performed."

---

### 5.13 Selective Re-Image (Manager+)

For email documents (`.msg` and `.eml` files), Manager+ users can trigger a re-image directly from the Review module. This is useful when the original imaging had issues — for example, blank pages caused by dead external image URLs in HTML emails, or rendering artifacts.

**Prerequisites:** The document must be an email (`.msg` or `.eml`). Manager or Admin role required.

**Steps:**

1. Select the email document in the Review Grid.
2. In the document detail panel, locate the **Re-Image** button (visible only for email documents and only to Manager+ users).
3. Click **Re-Image**. A confirmation dialog appears explaining that re-imaging will reset the document's review state.
4. Click **Confirm Re-Image**.
5. The platform re-runs the email imaging pipeline for this document, generating a new PDF in `Processed\`.

**Result:** A fresh PDF is generated for the email. The document's review state is reset: `reviewed_by`, `privilege`, and `confidentiality` fields are cleared because the document content has changed and must be re-reviewed.

> ⚠️ **Warning:** Re-imaging resets the document's review state (reviewed_by, privilege, and confidentiality designations are cleared). This is intentional — since the imaged content has changed, prior review decisions may no longer be valid. The document must be re-reviewed after re-imaging.

> ⚠️ **Warning:** If the document has already been produced, re-imaging does not update the produced copy. A stale production warning will appear in the Production History (Section 5.12). Consider running a replacement production if the re-imaged version must be delivered.

---

### 5.14 Reviewer Notes

Reviewer Notes provide a per-document notepad visible to all reviewers on the case. Unlike comments (Section 5.6), notes are designed for review-workflow context — questions, flags, or observations that help other reviewers understand a document.

**Prerequisites:** Reviewer or higher role required.

**Steps:**

1. Select a document in the Review Grid.
2. Locate the **Reviewer Notes** panel in the coding area.
3. Type your note in the text field.
4. Click **Add Note**.

**Result:** The note is saved with your username and a timestamp. All notes for the document are displayed in chronological order, visible to every reviewer on the case.

> ⚠️ **Warning:** Reviewer notes are visible to all users with case access. Like comments, do not use notes for information that should be restricted to specific reviewers.

---

### 5.15 Confidentiality Designation Override

During production configuration (Section 8.2), you set a default confidentiality endorsement (e.g., "CONFIDENTIAL") that is stamped on every produced page. The Confidentiality Designation Override allows you to set a different designation for individual documents that require a higher or lower level of protection.

**Prerequisites:** Reviewer or higher role required.

**Steps:**

1. Select a document in the Review Grid.
2. In the coding panel, locate the **Confidentiality** dropdown.
3. Select the appropriate designation:
   - **(Default)** — Uses whatever confidentiality level is set at the production level.
   - **Confidential** — Standard confidentiality marking.
   - **Highly Confidential** — Restricted distribution.
   - **Attorney Eyes Only** — Viewable only by outside counsel.
4. The designation is saved immediately.

**Result:** When this document is produced, the per-document override replaces the production-level default on the Bates stamp. If no override is set, the production default applies.

> ⚠️ **Warning:** Confidentiality designations are typically governed by a protective order or stipulation. Ensure your designations comply with the applicable court order before production.

---

### 5.16 Date Range Filter

The Date Range Filter narrows the Review Grid to documents within a specific time period based on email dates.

**Prerequisites:** Documents must have date metadata populated (typically from email headers). All roles can use this filter.

**Steps:**

1. In the Review module, locate the **Date Range** filter above the grid (near the other filter controls).
2. Set the **From** date to the start of your desired range.
3. Set the **To** date to the end of your desired range.
4. The grid updates immediately to show only documents with a `date_sent` or `date_received` falling within the specified range.
5. To clear the date filter, remove the dates from both fields.

**Result:** The Review Grid shows only documents within the specified date range. This filter combines with any active search query and column filters (AND logic).

> ⚠️ **Warning:** Documents without date metadata (e.g., non-email files that lack a date_sent or date_received value) will be excluded from the filtered results when a date range is active. Clear the date filter to see all documents regardless of date.

---

## 6. Redacting Documents (All Roles)

### 6.1 Opening a Document for Redaction

The Redaction tab provides a full-screen canvas for drawing redaction marks on PDF pages. It is integrated into the Review module as the **✏️ Redact** tab.

**Prerequisites:** The document must be processed (a PDF must exist in `Processed\`). All authenticated users can draw and save redaction marks.

**Steps:**

1. Navigate to **4 Review** in the sidebar and click the **✏️ Redact** tab.
2. In the document selector at the top of the page, type the control number of the document you want to redact (e.g., `DOC-000045`), or select it from the list of documents with existing redaction status.
3. The document information header shows the filename and path.
4. The redaction canvas loads, showing the first page of the document's PDF.

**Result:** The document PDF is displayed on the canvas, ready for redaction marks.

> ⚠️ **Warning:** Only documents with a PDF in `Processed\` can be redacted. If a document shows an error loading, the PDF may not have been generated — run Phase 3 of the Processor for that document first.

[Screenshot: Redaction page showing document loaded in canvas with page navigation]

---

### 6.2 Drawing Redaction Boxes

**Steps:**

1. In the **Tool** panel on the right side of the page, select **Draw** mode (the default).
2. Click and drag on the canvas to draw a rectangular box over the text or image you want to redact.
3. The box appears as a solid black rectangle on the page.
4. To move or resize an existing box, switch to **Transform** mode in the Tool panel and drag the box.
5. To draw on a different page, use the page navigation controls to move to the next page. The canvas reloads for that page. Marks from previous pages are saved automatically when you navigate.

**Result:** Each box you draw is tracked as a redaction mark with its position in PDF coordinate space.

> ⚠️ **Warning:** Drawing boxes does not immediately modify the PDF on disk. Marks are saved only when you click **💾 Save Marks** (Section 6.4). If you navigate away from the page without saving, unsaved marks will be lost.

---

### 6.3 Assigning Privilege Reasons to Each Box

Each redaction box requires its own privilege reason. You cannot save marks without assigning a reason to every box on the page.

**Steps:**

1. After drawing a box, the **Mark Reasons** panel on the right side updates to show a reason selector for that box.
2. Each drawn box has its own dropdown. Click the dropdown and select the applicable privilege reason (e.g., **Attorney-Client Privilege**, **Work Product**).
3. If the appropriate reason is not in the list, select **[Custom Reason...]** from the bottom of the dropdown and type the custom reason in the text field that appears.
4. Repeat for every box on the page.

**Result:** Each box is individually labeled with its privilege basis.

> ⚠️ **Warning:** Every box must have a reason before you can save. The **💾 Save Marks** button will be disabled if any box on the current page lacks a reason.

---

### 6.4 Saving Redaction Marks

**Steps:**

1. After drawing all boxes on the current page and assigning reasons, click **💾 Save Marks**.
2. The platform writes two things simultaneously:
   - The mark coordinates and reasons are saved to the `redaction_marks` table in the database.
   - `add_redact_annot()` annotations are written to the PDF file on disk, making the black boxes visible in the Review module's document preview.
3. The document's `redaction_status` is updated to `Has Redactions` in the database.

**Result:** The redaction marks are saved. The document now shows solid black boxes in the Review module preview. The underlying text is still preserved (not yet destroyed — see Section 6.7).

> ⚠️ **Warning:** Due to Windows file locking, the Redaction module must fully close its PDF handle before saving. If you see an error about the file being locked, refresh the page and try again.

---

### 6.5 Clearing Redaction Marks

#### Clear marks on the current page only:

1. Click **🗑 Clear This Page**.
2. Confirm the action.
3. All marks on the current page are removed from the database and the annotations are removed from the PDF.

#### Clear all marks on all pages of this document:

1. Click **🗑🗑 Clear All Pages**.
2. Confirm the action.
3. All marks on every page are removed from the database and from the PDF annotations.

**Result:** The PDF is restored to its un-redacted state. The document's `redaction_status` is reset.

> ⚠️ **Warning:** Clearing marks also clears any privilege tags that were added to the document by the redaction workflow (see Section 6.6). Review the document's tags in the Review module after clearing to confirm the expected state.

---

### 6.6 How Redaction Tags Stay in Sync

When you save redaction marks, the platform automatically synchronizes the document's privilege tags to match the marks:

- Every unique privilege reason assigned to marks on that document is added as a tag on the document (e.g., if you have two boxes with "Attorney-Client Privilege" and one box with "Work Product," the document gets both tags).
- Any privilege tags previously on the document that no longer correspond to current marks are removed.

This synchronization runs on every Save and every Clear operation. The result is that the document's tags in the Review Grid always reflect what is actually redacted — no orphaned privilege tags can persist after marks are removed.

> ⚠️ **Warning:** Because of this sync behavior, manually removing a privilege tag in the Review module (Section 5.5.2) will not survive the next time the Redaction module saves that document. Privilege tags on redacted documents are authoritative in the Redaction module. If you need to change the privilege basis, change it in the Redaction module by updating the box's reason.

---

### 6.7 Important: Redactions Are Non-Destructive Until Production

The platform deliberately separates **marking** from **burning**:

- When you draw boxes and click **💾 Save Marks**, you create visible black boxes in the PDF, but the **underlying text content is preserved**. The original text can still be read programmatically from the file.
- The black boxes are PDF annotation objects (type `PDF_ANNOT_REDACT`), not content destruction.
- Content is permanently and irreversibly destroyed only when the document is run through Production (Section 8). At that point, `apply_redactions()` is called, which physically removes the text and image data beneath each box from the PDF binary.

**This means:**

- You can review redacted pages in the Review module and confirm the boxes are in the right places before running production.
- You can remove or adjust marks at any time before production without losing the underlying content.
- Once a document has gone through production with redactions burned, the original content is gone from the produced copy (though the original unredacted version in `Processed\` is untouched).

> ⚠️ **Warning:** Never distribute the pre-production PDF (from `Processed\`) to opposing counsel or third parties. The redaction marks are visible black boxes, but the underlying text is readable in the file. Only the production output (from `Produced\`) has the content permanently removed.

---

## 6.5 Splitting & Trimming Documents (Manager+)

The **Split** tab in the document viewer allows managers to break multi-page PDFs into independent documents or remove specific pages.

### Splitting a Document

Use split when a single PDF contains multiple logical documents (e.g., batch-scanned records).

1. Open a PDF document in the Review grid and click the **Split** tab.
2. Select **Split into ranges** mode.
3. Define page ranges for each resulting document (e.g., 1-50, 51-100). Use **Auto-Split** for one document per page.
4. The validation panel shows overlap/gap detection and a summary table.
5. Click **Execute Split** and confirm.

**Result:** Each range becomes a new document with its own control number, queued for processing in Module 2. The original document is hidden from the review grid (marked as `Split_Source`) but preserved in the database for audit purposes.

### Trimming a Document

Use trim to remove non-responsive pages (e.g., blank pages, cover sheets).

1. Open a PDF document and click the **Split** tab, then select **Trim pages** mode.
2. Enter page numbers to remove (e.g., `3-4, 8, 20-24`).
3. Review the validation summary showing how many pages will be kept vs. removed.
4. Click **Trim Document** and confirm.

**Result:** A single trimmed child document is created. The original is hidden but preserved.

### What Carries Over

Split and trim children inherit all legal metadata from the parent: privilege status, confidentiality designation, clawback status, tags, custodian, dates, and email metadata. Redaction marks are migrated with correct page renumbering. After split/trim, run **Module 2 (Processor)** on the new documents to extract text and index them for search.

> **Restriction:** Documents that have already been produced (Bates assigned) cannot be split or trimmed.

---

## 7. Running Search Term Reports (Manager+)

### 7.1 Entering or Uploading Search Terms

Search Term Reports (STR) run a list of keywords and phrases against the full OpenSearch index and report hit counts per term.

**Prerequisites:** Documents must be processed and indexed in OpenSearch. Manager or Admin role required.

**Steps:**

1. Navigate to **4 Review** in the sidebar, then select **📊 Search Term Reports** from the view selector at the top of the page.
2. You can enter search terms in two ways:
   - **Manual entry:** Type each term on a new line in the terms text area.
   - **CSV upload:** Click **Browse** and upload a CSV file. The first column of the CSV is used as the list of terms.
3. Toggle **Include Suppressed Documents** if you want hit counts to include documents normally hidden from review (exact duplicates, thread-suppressed, etc.).

---

### 7.2 Running the Report

**Steps:**

1. After entering or uploading your terms, click **Run STR**.
2. The system sends each term as a separate `query_string` query to OpenSearch.
3. A progress bar appears as each term is evaluated.

**Result:** A summary table appears showing each term and its hit count (the number of documents containing that term). Hit counts are exact, not sampled.

> ⚠️ **Warning:** Terms using wildcard syntax (`*`) or fuzzy syntax (`~`) may take longer to evaluate than exact terms. Very broad wildcards (e.g., `a*`) can be slow on large collections.

---

### 7.3 Reviewing Hit Counts and Document Preview

**Steps:**

1. In the summary table, click on any term row to expand it.
2. The expanded view shows the individual documents that hit on that term, with custodian, date, and a text snippet preview.
3. You can click a document's control number to jump to it in the Review module.

---

### 7.4 Exporting the Report

**Steps:**

1. After running the report, click **Export to Excel** to download a two-sheet Excel workbook:
   - **Sheet 1 — STR Summary:** Each term and its hit count.
   - **Sheet 2 — Hit Documents:** Each document that hit on at least one term, with term, control number, custodian, and date.
2. Alternatively, click **Export to CSV** for a summary-only CSV.

**Result:** A downloaded file ready for delivery to opposing counsel or for internal documentation.

---

### 7.5 STR Highlighting in the Review Module

After a report run, simple text terms (non-wildcard, non-Boolean) are automatically cached and carried into the Review module.

**Behavior:**

- When you navigate to **4 Review** and open the **📝 Extracted Text** tab for any document, every word matching a cached STR term is highlighted in yellow.
- A badge near the search bar shows which STR terms are currently active.
- To clear STR highlights, click **🧹 Clear STR Highlights** in the STR module results area.

**Result:** Attorneys reviewing documents can immediately see exactly where and how each search term appears in the document body — without running a new search.

[Screenshot: Review module Extracted Text tab showing yellow-highlighted STR terms]

---

## 8. Producing Documents (Manager+)

### 8.0 Stale File Warning (If Displayed)

When you open the Production module, the platform automatically checks for orphaned temporary files left behind by a prior production run that did not complete (for example, if the browser was closed mid-run or the server restarted).

If orphaned files are detected, a warning banner appears at the top of the page identifying the affected volume names. A **Clean Up Orphaned Files** button is available for Manager+ users. Click it to delete the orphaned files before starting a new production run. The cleanup is recorded in the audit log.

If no warning appears, no action is needed — there are no orphaned files.

---

### 8.1 Selecting Documents for Production

Production is the process of assigning Bates numbers and packaging documents for delivery to opposing counsel.

**Prerequisites:** Documents must be processed. Redaction marks should be finalized before production (see Section 6). Manager or Admin role required.

**Steps:**

1. Navigate to **5 Production** in the sidebar.
2. Under **1. Select Documents for Production**, the page shows a filtered grid of available documents.
3. Inbound productions (opposing counsel's deliveries) are **automatically excluded** from the grid and all outbound workflows — no checkbox, no opt-out. If you need to view them, use the Inbound Productions module.
4. Use the filter checkboxes to narrow the production set:
   - **Exclude Previously Produced** — prevents re-producing already-produced documents (default: on)
   - **Exclude Suppressed** — hides duplicates and junk from the grid (default: on)
   - **Exclude Non-Responsive** — hides documents tagged Non-Responsive (default: on)
   - **Exclude Clawback-Demanded** — hard-blocks documents with an active clawback demand (default: on)
5. To auto-select documents by tag, use the **Auto-Select by Tag** dropdown.
6. To manually select documents, check their checkboxes in the grid.
7. Use **☑️ Select All** to select all visible documents, or **🔲 Deselect All** to clear the selection.
8. When satisfied with the selection, click **✅ Confirm Selection (N documents)**.

**Result:** The selected documents are locked in for this production run. You proceed to configuration.

> ⚠️ **Warning:** Once you confirm the selection and run production, Bates numbers are permanently assigned. Review your selection carefully before confirming.

[Screenshot: Production page step 1 — document grid with filter checkboxes and selection controls]

---

### 8.2 Configuring Production Settings

**Steps:**

1. Under **2. Configure & Run**, scroll to the **Configure Production** section.
2. Set the **Production Name** (e.g., "VOL001" or "ABC Initial Disclosures").
3. Set the **Bates Prefix** (e.g., "ABC" to produce "ABC-000001").
4. Set the **Starting Number** and **Padding Length** (e.g., start at 1 with 6-digit padding yields "ABC-000001").
5. Select the **Production Format**: **PDF** (multi-page PDFs), **TIFF** (single-page TIFFs at 300 DPI, generates an Opticon OPT file), or **Native Only** (skips imaging; produces original files renamed to Bates numbers with slip-sheet placeholders).
6. Under **Bates Stamp Options**, configure:
   - **Stamp Bates on Pages** — check to burn the Bates number visually onto each page (default: on)
   - **Stamp Position** — bottom-right, bottom-left, or bottom-center
   - **Stamp Color** — black or red
7. Under **Confidentiality Endorsement**, select a designation (e.g., "CONFIDENTIAL") or choose Custom to type your own endorsement text. This text is stamped on each page alongside the Bates number.
8. Under **Date Range Culling**, optionally check **Filter by Date Range** to exclude documents outside a date range.

**Supplemental Productions (Volume II+):** If a prior production exists for this case, the **🔗 Continue from Last Production** toggle (on by default) automatically populates the Bates prefix and starting number from where the last production ended. This ensures Bates continuity across volumes. Toggle it off to enter arbitrary prefix/start values for an independent production.

**Parallel Imaging Workers:** The production page includes a slider for the number of parallel workers used during Pass 1 imaging. Its default value is controlled by the `IMAGING_WORKERS` setting in `config.py`. Set `IMAGING_WORKERS = 0` to let the platform auto-detect an appropriate count (`min(4, cpu_count - 1)`). Increase the value on machines with many cores to speed up imaging; lower it if the machine becomes unresponsive during production.

---

### 8.3 Running the Production

**Steps:**

1. After completing configuration, click **🚀 Run Production**.
2. A progress display shows each document as it is processed.
3. Do not close the browser tab while production is running.

**Result:** When complete, the production summary shows counts of produced documents, errors, and privileged documents withheld. Output files are placed in `Produced\{ProductionName}\`.

> ⚠️ **Warning:** If more than approximately 9,500 documents are selected, a warning banner appears before the run. OpenSearch has a default `max_result_window` of 10,000 results. Very large productions may need to be split into volumes.

> ⚠️ **Warning:** Production burns redaction marks. For any document with `redaction_status = Has Redactions`, `apply_redactions()` is called, which permanently removes the redacted text from the produced copy. This step is irreversible on the produced file (the original in `Processed\` is unaffected).

---

### 8.4 What Happens During Production

The production pipeline processes each document in this sequence:

| Step | Operation |
|------|-----------|
| 1 | Source routing: looks for the document in `Reviewed\` (Filevine pull-back), then `Processed\`, then the original path |
| 2 | Image: converts to PDF if not already a PDF (uses the universal imager) |
| 3 | Copy native to `NATIVES\` folder |
| 4 | Assign Bates numbers (family-aware — parent email and all attachments get contiguous numbers) |
| 5 | Burn redactions: calls `apply_redactions()` on documents with redaction marks (content permanently destroyed) |
| 6 | Extract post-redaction text (so load files reflect only the non-redacted text) |
| 7 | Stamp Bates number and confidentiality endorsement onto each page |
| 8 | Format: output as multi-page PDF or single-page TIFF at 300 DPI |
| 9 | Generate load files: `LOADFILE.csv`, `LOADFILE.DAT` (Concordance format), `IMAGES.OPT` (Opticon format) |
| 10 | Generate privilege log (`.csv`) listing all withheld documents with privilege basis |

---

### 8.5 Locating the Output Files

Production output is placed in:

```
{Case Folder}\Produced\{Production Name}\
├── IMAGES\          — PDF or TIFF files named by Bates number
├── NATIVES\         — Native file copies
├── TEXT\            — Extracted text files per document
├── LOADFILE.csv     — General-purpose CSV load file
├── LOADFILE.DAT     — Concordance DAT load file
├── IMAGES.OPT       — Opticon image load file (TIFF only)
└── PRIVILEGE_LOG.csv — Documents withheld for privilege
```

---

### 8.6 Understanding Load Files (DAT, OPT, CSV)

| File | Format | Use |
|------|--------|-----|
| **LOADFILE.csv** | Standard CSV | Import into any platform that accepts CSV |
| **LOADFILE.DAT** | Concordance DAT | Direct import into Relativity, Concordance, or similar platforms. Uses Concordance-standard `þ` delimiter and `°` quote characters |
| **IMAGES.OPT** | Opticon OPT | Image-level load file for TIFF productions. Maps each Bates number to its TIFF file path |

---

### 8.7 Multi-Production Tracking

Documents can be produced in multiple production volumes over the course of a matter. The platform tracks each production independently, supporting original, supplemental, and replacement production types.

**How it works:**

- When a document is produced for the first time, it receives a Bates range in the production volume (e.g., `ABC-000045 - ABC-000048` in `VOL001`). This is recorded as an **Original** production.
- If the same document needs to be produced again in a later volume (e.g., in response to a supplemental request), it receives a new Bates range in the new volume. This is recorded as a **Supplemental** production.
- If a previously produced document must be replaced (e.g., due to an incorrect redaction or a re-imaged email), it can be produced as a **Replacement** production with a new Bates range.
- Each production record is independent — the document retains all of its Bates numbers across all volumes.

**Viewing production history:**

In the Review module, select a multi-production document and expand the **Production History** panel (see Section 5.12) to see every production record with volume name, Bates range, production type, and date.

**Producing a previously produced document:**

1. In the Production module (Section 8.1), uncheck **Exclude Previously Produced** to make already-produced documents visible in the selection grid.
2. Select the documents you want to re-produce.
3. Configure the production settings as usual (Section 8.2). Use the **🔗 Continue from Last Production** toggle to maintain Bates continuity, or set an independent prefix/start for a new numbering series.
4. Run the production.

**Result:** The document receives a new Bates range in the new volume. Both the old and new production records are preserved in the production history.

> ⚠️ **Warning:** When re-producing a document, the new production uses the current state of the document's PDF (including any new redaction marks or re-imaging). If the document has changed since its prior production, verify that the new version is correct before delivering it to opposing counsel.

---

## 9. Privilege Log QC Editor (Manager+)

### 9.1 Generating and Filtering the Privilege Log

The Privilege Log QC Editor generates a filterable log of all documents tagged with privilege assertions — independent of the Production module, so you can review and QC privilege assertions at any time.

**Prerequisites:** Documents must have privilege tags applied. Manager or Admin role required.

**Steps:**

1. Navigate to **5 Production** in the sidebar and click the **Privilege Log** tab.
2. Select the **Privilege Basis** mode (Auto-detect from tags, or override with a specific basis).
3. Optionally toggle **Include 'Needs Review' documents** to include documents tagged "Needs Review."
4. Click **Generate Privilege Log**.

**Result:** A filterable data grid with all privileged documents. Above the grid, a **six-metric summary bar** shows:
- Privileged Documents (total)
- Withheld
- Redact & Produce
- Needs Disposition (highlighted if any exist)
- With Bates (already produced)
- Without Bates (not yet produced)

**Filters** (above the grid):
- **Disposition** — multiselect: Withhold, Redact, Needs Disposition
- **Privilege Basis** — multiselect from distinct values in the result set
- **Custodian** — multiselect from distinct custodians
- **Date range** — optional start/end date inputs
- **Show only Needs Disposition** — one-click convenience toggle to surface documents requiring attorney attention

---

### 9.2 Abbreviation Normalization

Reviewer shorthand is automatically normalized to the full canonical privilege description. This ensures the log uses consistent, court-ready language regardless of how individual reviewers tagged documents.

| Reviewer Entered | Normalized to |
|------------------|---------------|
| `AC`, `A-C`, `ACP`, `attorney client` | Attorney-Client Privilege |
| `WP`, `work prod`, `work product` | Work Product |
| `AC/WP` | Attorney-Client Privilege and Work Product |
| `CI`, `common interest` | Common Interest Privilege |
| `JD`, `joint defense` | Joint Defense Privilege |

You can also override the privilege basis using the **Privilege Basis Override** selector on the page for any individual entry before export.

---

### 9.3 Column Picker & Export

The Column Picker controls which columns appear in the exported CSV/Excel file. The QC grid always shows all available columns for review purposes.

**Available columns (19 total):**

| Column | Default | Notes |
|--------|---------|-------|
| Control Number, BegBates, EndBates | On | Document identifiers |
| Privilege Basis, Disposition, Description | On | Core privilege log fields |
| Date, From, To, CC, Subject/Title, Custodian | On | EDRM standard metadata |
| Record Type, File Name | Off | Extended identification |
| Confidentiality, Source Collection | Off | Case-specific metadata |
| Page Count, Redacted Pages | Off | Document metrics |
| Reviewer Notes | Off | Latest reviewer note from document notes |

**Saving column configuration:**
- Click **Save Config** to persist your column selection for this case (Manager+ with Production permission required).
- Click **Reset Defaults** to restore the EDRM standard column set.
- Column configuration is per-case and persists across sessions and users.

**Exporting:**
- Click **Download as CSV** or **Download as Excel (.xlsx)**.
- Only the columns selected in the column picker appear in the export, in the selected order.
- Excel export includes bold headers and auto-width columns.

> **Note:** The production-time privilege log (automatically generated during a production run) is a separate file — `PRIVILEGE_LOG.csv` in the production output folder. The QC Editor is for pre-production review and can be run at any time.

---

## 10. Receiving Opposing Counsel Productions (Manager+)

### 10.1 Preparing the Inbound Production

When opposing counsel produces documents, they typically deliver a structured package: a load file (`.dat` or `.csv`), image files (PDFs or TIFFs), native files, and extracted text files.

**Prerequisites:** You have received the production package and have access to it on the firm file system. Manager or Admin role required.

**Steps:**

1. Create a folder under `{Case Folder}\Inbound\{Party Name}\{Volume Name}\` (e.g., `Inbound\Opposing Corp\Vol001\`).
2. Copy the entire production package — load file, IMAGES folder, NATIVES folder, TEXT folder — into this folder.
3. Note the load file name and format (DAT or CSV).

> ℹ️ **Coming in beta-2.11:** a LAN-friendly folder picker will let you select the inbound production package from a network share or workstation directly — no manual copy-to-server step required. Until then, copy the files to the `Inbound/{Party}/{Volume}/` folder as described above. (See `docs/specs/Spec_Intake_Inbox_Pattern.md` for the design spec.)

---

### 10.2 Loading the Load File and Mapping Columns

**Steps:**

1. Navigate to **9 Inbound Productions** in the sidebar. (This was previously a tab under **5 Production**; it moved to its own dedicated module in beta-2.10 so inbound ingest is no longer affected by outbound workflow state.)
2. Click **Browse** and select the load file (`.dat` or `.csv`).
3. If the load file uses non-standard delimiters, configure the **Delimiter** and **Quote Character** fields (the default Concordance delimiter `\x14` / `þ` handles most vendor-produced DAT files).
4. Click **Parse Load File**. The first few rows of the file appear for inspection.
5. The **Column Mapping** interface shows each column from the load file alongside a dropdown to map it to a system field (e.g., map `BEGDOC` to `control_number`, `CUSTODIAN` to `custodian`, `DATERECEIVED` to `date_received`).
6. Leave any columns unmapped if you do not need them — they are automatically preserved as searchable JSON in the `dynamic_metadata` field.
7. Set the **Source Party** name (e.g., "Acme Corp") and **Production Volume** label (e.g., "Initial Disclosures").
8. Click **Run Import**.

**Result:** Documents from the load file are registered in the case database with `source_party` = your specified party name. They appear in the Review module under the Opposing Counsel branch of the folder tree.

> ⚠️ **Warning:** Date values in any format (MM/DD/YYYY, YYYY-MM-DD, natural language) are automatically normalized to ISO format. Inspect a few date fields after import to confirm they converted correctly.

> ⚠️ **Warning:** Inbound productions are isolated from internal analytics. Threading and near-duplicate detection will never run on opposing counsel documents and will not be contaminated by them.

---

### 10.3 Verifying the Import

**Steps:**

1. Navigate to **4 Review**.
2. In the folder tree navigator, find the newly imported party and volume.
3. Click it to scope the grid to those documents.
4. Spot-check several documents: verify the control numbers, custodians, and dates look correct.
5. Open a document preview to confirm PDFs or images are resolving correctly.

> ⚠️ **Warning:** If PDFs or images are not loading in the preview, the image paths in the load file may not match the actual file locations. The platform automatically scans the production folder for PDFs and TIFFs by filename — if the filenames do not match the load file's Bates numbers, images may not resolve.

---

### 10.4 Purging an Incorrect Import

If an import was incorrect (wrong volume, wrong party name, wrong column mapping), you can purge it cleanly.

**Steps:**

1. Navigate to **9 Inbound Productions** in the sidebar.
2. Locate the **Previous Productions** section at the bottom of the page.
3. Find the production you want to purge.
4. In the deletion confirmation field, type **DELETE** to confirm.
5. Click **Delete {Production Name}**.

**Result:** All documents from that production are removed from the database, their OpenSearch index entries are deleted, and their file records are cleaned up.

> ⚠️ **Warning:** Purging a production is irreversible. Any tags, comments, or review coding applied to documents in that production will also be permanently deleted. Confirm you have selected the correct production before typing DELETE.

---

## 11. Filevine Sync (Manager+)

### 11.1 Pushing Documents to Filevine

The Sync module pushes processed documents and their metadata to the firm's Filevine case management platform.

**Prerequisites:** The Filevine firm subdomain must be configured (by an administrator, in `config.py`). Manager or Admin role required.

**Steps:**

1. Navigate to **6 Sync** in the sidebar.
2. The page shows a list of processed documents that have not yet been pushed to Filevine (`sync_status = Pending`).
3. Select the documents you want to push, or use the **Select All** option.
4. Choose the target Filevine **Project** and **Collection**.
5. Click **Push to Filevine**.
6. A progress panel shows each document as it is uploaded (pre-signed URL generation → file transfer → finalization → metadata mapping).

**Result:** Selected documents are available in Filevine under the specified project and collection. Each document's `filevine_doc_id` is recorded in the database.

> ⚠️ **Warning:** The sync engine uses automatic retry with exponential backoff for API failures (rate limiting, server errors). If a document fails after all retries, it is flagged for re-sync rather than silently lost. Check the **Failed** count after a sync run.

---

### 11.2 Pulling Back Reviewed Documents

After attorneys annotate documents in Filevine (e.g., adding redaction marks using Filevine's built-in PDF viewer), you can pull those annotated versions back into the platform.

**Steps:**

1. Navigate to **6 Sync**.
2. Click **Pull Reviewed Documents**.
3. The platform queries Filevine for documents that have been modified since the last pull-back.
4. Modified documents are downloaded as PDFs into the `Reviewed\` folder in the case directory.
5. The platform scans each downloaded PDF for `PDF_ANNOT_REDACT` annotations and updates `redaction_status` accordingly.

**Result:** Filevine-annotated PDFs are now in `Reviewed\` and will be used in preference to the `Processed\` originals during production.

> ⚠️ **Warning:** Pull-back requires that documents were previously pushed to Filevine from this case. The platform cannot pull documents that were uploaded to Filevine through other means (e.g., manually uploaded through the Filevine web interface).

---

### 11.3 Handling Sync Errors

**Token expiration:** If the Filevine API token expires mid-sync, affected documents are flagged with `sync_status = Token_Expired`. Re-authenticate with Filevine and click **Re-sync Flagged** to resume.

**Rate limiting:** The sync engine automatically handles HTTP 429 responses with exponential backoff (2s → 4s → 8s). No user action is needed.

**Failed documents:** After any sync run, review the **Failed** count at the top of the Sync page. Click **Show Failed** to see which documents failed and their error messages. You can individually retry failed documents from this panel.

---

## 12. Viewing Audit Logs (Admin Only)

### 12.1 Accessing the Audit Log Viewer

The audit trail records every user action on every document across all modules. It is the platform's primary defensibility record — it allows you to answer "who did what to which document and when" for any document in any case.

**Prerequisites:** Admin role required. A case must be selected.

**Steps:**

1. Navigate to the **Home** page.
2. Scroll to the **🔍 Audit Log Viewer (Admin)** expander.
3. Click to expand it. The viewer is only visible to Admin users.

**Result:** The audit log viewer appears with filter controls and a data table.

[Screenshot: Home page showing Audit Log Viewer expander (Admin only, visible when case is selected)]

---

### 12.2 Filtering by User, Document, Module, or Date Range

The audit log viewer provides filters to isolate specific activity. Filters can be combined.

| Filter | What It Does |
|--------|-------------|
| **Username** | Show only actions by a specific user |
| **Control Number** | Show only actions on a specific document |
| **Module** | Show only actions from a specific module (e.g., "4_Review.py", "5_Production.py") |
| **Action** | Show only a specific action type (e.g., `TAG_APPLIED`, `REDACTION_SAVED`) |
| **Date Range** | Show only actions within a specific date range |

**Steps:**

1. In the audit log viewer, set your filter values.
2. The table updates as you type (or click Apply if a button is present).
3. The table returns up to 2,000 rows, ordered by timestamp descending (most recent first).

---

### 12.3 Exporting Audit Logs

Three export formats are available, all respecting your active filters:

**CSV** — Click **⬇️ CSV**. Downloads a plain comma-separated file suitable for spreadsheet import or programmatic analysis.

**Excel** — Click **⬇️ Excel**. Downloads an `.xlsx` file with two sheets:
- **Audit Log** — All filtered entries with frozen header row and auto-sized columns.
- **Export Metadata** — Documents the exact filter criteria applied (user, module, action, date range), so the export is self-describing.

**PDF** — Click **⬇️ PDF**, wait for the spinner, then click the download button that appears. Produces a court-ready landscape PDF with:
- Case name, generation date, and preparer name in the header.
- Applied filter criteria documented on every page.
- Page numbers in the footer (Page X of Y).
- "Privileged & Confidential" stamp.
- Table headers repeat on every page for multi-page audit trails.

> ⚠️ **Warning:** All three exports respect your active filters. To export the complete audit trail for the case, clear all filters before exporting.

---

### 12.4 Common Audit Queries

#### "Show me everything that happened to document ABC004817"

1. Set **Control Number** filter to `ABC004817`.
2. Clear all other filters.
3. Click Apply.

**Result:** Every action ever taken on that document appears — ingestion, processing, every tag applied or removed, every comment added, every redaction drawn or cleared, production Bates assignment.

#### "Show me all actions by reviewer Jane Doe last Tuesday"

1. Set **Username** filter to `jdoe` (or Jane's username).
2. Set the **Date Range** to start and end on last Tuesday.
3. Clear all other filters.

**Result:** Every action Jane took on any document in this case on that date — what documents she opened (if tracked), what tags she applied, what searches she ran.

#### "Show me all redaction activity across the entire case"

1. Set the **Action** filter. Select `REDACTION_SAVED`, then also include `REDACTION_CLEARED` and `REDACTION_BURNED` (you may need to run separate queries for each action type, or leave the action filter blank and scan the results).
2. Alternatively, set **Module** to `4_Review.py` and filter by `REDACTION_SAVED` or `REDACTION_CLEARED` action types.

**Result:** A complete record of every document that had redaction marks drawn, every page cleared, and every document where marks were burned during production.

#### "Show me when Bates numbers were assigned for Volume 2"

1. Set the **Action** filter to `BATES_ASSIGNED`.
2. If you know the production ran during a specific date range, set the **Date Range** accordingly.
3. Review the **Details** column — it contains the production name, allowing you to isolate entries for Volume 2.

**Result:** The exact timestamp when each document in Volume 2 received its Bates assignment, and which user ran the production.

#### "Export a complete audit trail for court submission"

1. Clear all filters in the audit log viewer.
2. Click **⬇️ Export Audit Log (CSV)**.
3. The export captures up to 2,000 rows. For very active cases with more than 2,000 audit entries, consider running multiple exports filtered by date range to capture the complete history.

#### "Show me when we ingested an inbound production from opposing counsel"

Inbound production events use a distinct event-type family from outbound `PRODUCTION_*` events:

1. Filter the audit log by **Event Type** `INBOUND_PRODUCTION_RECORDED` or `INBOUND_INGESTED`.
2. `INBOUND_INGESTED` is written once per document during ingest (high-volume — one row per document in the load file).
3. `INBOUND_PRODUCTION_RECORDED` is written once per successful volume, with the source party, production volume name, load file name, column mapping, and counts (total rows, error count, successful inserts) in the **Details** column.
4. Outbound production events (`PRODUCTION_STARTED`, `PRODUCTION_FINALIZED`, `BATES_ASSIGNED`, etc.) are **never mixed** with inbound events. Filtering by `PRODUCTION_*` will NOT return inbound history.

> ℹ️ **Why the separation?** Inbound ingests are deliveries from opposing counsel (documents we received), not productions we performed. Keeping the event-type families distinct prevents inbound ingests from being misread as outgoing productions — and keeps the court-facing defensibility report's production history free of material that does not belong there.

> ⚠️ **Warning:** The audit log is append-only and tamper-resistant within the platform. Entries are never modified or deleted by any user action. The log accurately reflects the complete sequence of platform activity.

---

## 13. User Management (Admin Only)

### 13.1 Creating a New User

**Prerequisites:** Admin role required. Navigate to the Home page.

**Steps:**

1. On the Home page, scroll to the **👥 User Management** section (visible only to Admins).
2. Under **➕ Add New User**, fill in:
   - **Username** — the login name (e.g., `jsmith`)
   - **Password** — temporary password (the user should change it at first login if your policy requires)
   - **Display Name** — the name shown in the sidebar and audit trail (e.g., "Jane Smith")
   - **Role** — select from available roles (`reviewer`, `manager`, `admin`, `expert`, or any custom role)
3. Click **Create User**.

**Result:** The user can immediately log in with the credentials you set.

> ⚠️ **Warning:** Usernames must be unique. The system will reject a creation attempt if the username already exists.

> ⚠️ **Warning:** There is no automated password reset email — password resets must be performed by an Admin (see Section 13.3). Communicate the initial password to the user via a secure channel.

---

### 13.2 Changing a User's Role

**Steps:**

1. On the Home page, scroll to **👥 User Management**.
2. Click the **🔑 Reset Password / Change Role / Delete User** expander.
3. In the **Select User** dropdown, select the user whose role you want to change.
4. Select the **Change Role** option.
5. In the **New Role** dropdown, select the new role (`reviewer`, `manager`, or `admin`).
6. Click **Apply Role Change**.

**Result:** The role change takes effect immediately. The user's next page load will reflect the new role and see the updated module visibility.

> ⚠️ **Warning:** Downgrading a user from Admin to Manager or Reviewer removes their access to User Management and the Audit Log Viewer immediately. If only one Admin exists and you downgrade them, there will be no admin user. Ensure at least one Admin always exists.

---

### 13.3 Resetting a Password

**Steps:**

1. On the Home page, scroll to **👥 User Management**.
2. Click the **🔑 Reset Password / Change Role / Delete User** expander.
3. Select the user in the **Select User** dropdown.
4. Select the **Reset Password** option.
5. Enter the **New Password** in the provided field.
6. Click **Apply Reset**.

**Result:** The user's password is immediately changed. Communicate the new password to the user.

> ⚠️ **Warning:** Admins cannot see existing passwords (they are hashed). A reset creates a new password — there is no "view current password" option.

---

### 13.4 Deleting a User

**Steps:**

1. On the Home page, scroll to **👥 User Management**.
2. Click the **🔑 Reset Password / Change Role / Delete User** expander.
3. Select the user in the **Select User** dropdown.
4. Select the **Delete User** option.
5. Click **🗑️ Confirm Delete**.

**Result:** The user account is deleted. The user cannot log in. Any audit log entries made by this user remain in the audit trail — they are not deleted.

> ⚠️ **Warning:** Deleting a user is irreversible. The deleted user's audit trail history is preserved but their account cannot be recovered. If you need to temporarily disable access, consider changing the password to a random string rather than deleting the account.

> ⚠️ **Warning:** You cannot delete your own Admin account while logged in. The system prevents this to avoid accidental lockout.

---

### 13.5 Managing Role Permissions (Admin Only)

The platform uses a **permission-based access system**. Each role (including custom roles) has a set of named permissions that control which features are accessible. Administrators can customize these permissions.

**Steps:**

1. On the Home page, scroll to **👥 User Management**.
2. Click the **🔑 Role Permissions** expander.
3. A checkbox grid shows every permission for every role. Check or uncheck permissions as needed.
4. To create a **custom role**, enter a role name in the **Add Custom Role** field and click **Create**. The new role starts with no permissions — check the ones it needs.
5. Click **Save Changes** when done.

**Result:** Permission changes take effect immediately for all users of that role on their next page load.

**Default permissions by role:**

| Permission | Admin | Manager | Reviewer | Expert |
|------------|-------|---------|----------|--------|
| `review` | ✅ | ✅ | ✅ | ✅ |
| `tag` | ✅ | ✅ | ✅ | ✅ |
| `comment` | ✅ | ✅ | ✅ | ✅ |
| `redact` | ✅ | ✅ | ✅ | ❌ |
| `saved_search_personal` | ✅ | ✅ | ✅ | ✅ |
| `saved_search_global` | ✅ | ✅ | ✅ | ❌ |
| `export_csv` | ✅ | ✅ | ❌ | ❌ |
| `export_pdf` | ✅ | ✅ | ❌ | ❌ |
| `download_produced` | ✅ | ✅ | ✅ | ✅ |
| `configure_columns` | ✅ | ✅ | ❌ | ❌ |
| `str_run` | ✅ | ✅ | ❌ | ✅ |
| `ingest` | ✅ | ✅ | ❌ | ❌ |
| `process` | ✅ | ✅ | ❌ | ❌ |
| `analytics` | ✅ | ✅ | ❌ | ❌ |
| `produce` | ✅ | ✅ | ❌ | ❌ |
| `sync` | ✅ | ✅ | ❌ | ❌ |
| `manage_users` | ✅ | ❌ | ❌ | ❌ |
| `view_audit` | ✅ | ❌ | ❌ | ❌ |

> ⚠️ **Warning:** Be cautious when modifying Admin permissions. If you remove `manage_users` from the Admin role, no one will be able to manage users or restore the permission.

---

## 14. Clawback / Inadvertent Disclosure (Manager+)

If a privileged document was inadvertently included in a production, the platform tracks the clawback demand and blocks the document from all future productions — implementing the protections contemplated by Federal Rule of Civil Procedure 26(b)(5)(B) and state equivalents.

**Prerequisites:** The document must have been previously produced (has a Bates number). Manager or Admin role required.

### 14.1 Marking a Clawback Demand

1. In **4 Review**, select the document that was inadvertently produced.
2. Click the **⚠️ Clawback** button in the document viewer action bar.
3. Enter the **Demand Date** (date the clawback letter was sent or will be sent).
4. Add any notes (e.g., the basis for privilege, the production volume it appeared in).
5. Click **Confirm**.

**Result:** The document is marked `Clawback_Demanded`. It will be **automatically excluded from all future production runs** (hard block). A `CLAWBACK_MARKED` audit entry is created with the demand date, notes, and the acting user.

### 14.2 Monitoring Clawback Status

The **3 Analytics** dashboard includes a Clawback summary card showing all clawback-demanded documents with their demand dates. Use this to track outstanding demands and verify that opposing counsel has complied.

### 14.3 Resolving a Clawback

Once opposing counsel confirms return or destruction of the inadvertently disclosed material:

1. In **4 Review**, select the clawback-demanded document.
2. Click the **⚠️ Clawback** button again in the action bar.
3. Change the status to **Clawback_Resolved**.

**Result:** The document's clawback status is updated. A `CLAWBACK_RESOLVED` audit entry is created. The document remains excluded from future productions unless you explicitly re-tag it for production.

> **Important:** The clawback hard block is a **safety net, not a substitute for the formal clawback letter.** Always send the written demand to opposing counsel pursuant to the applicable rules before or concurrently with marking the document in the platform.

---

## 15. Deduplication Report (Manager+)

### 15.1 Running the Report

The Deduplication Report is a defensibility report showing exactly how the platform reduced the review population and what safeguards were applied.

**Prerequisites:** Processing Phase 2 (deduplication) and Analytics must have run. Manager or Admin role required.

**Steps:**

1. Navigate to **3 Analytics** in the sidebar and click the **🔍 Dedup Report** tab.
2. The report generates automatically from the current database state — no configuration is needed.
3. The report takes a few seconds to calculate on large collections.

**Result:** The full report appears on screen.

---

### 15.2 Understanding the Metrics

The report is organized into five sections:

**Section 1 — Collection Overview:**

| Metric | Description |
|--------|-------------|
| Total Ingested | Every file registered during ingestion |
| Total Processed | Files that completed Phase 2 processing |
| Exact Duplicates | Files marked `Duplicate (MD5)` — identical hash match |
| Near-Dupe Suppressed | Files tagged `NearDupe-Suppressed` — 90%+ content similarity |
| Thread Suppressed | Emails tagged `Thread-Suppressed` — redundant within a thread |
| Net Reviewable | Total documents remaining after all suppression |

**Section 2 — Defensibility Summary:**

A generated prose paragraph describing the deduplication process and percentages, suitable for court disclosure or billing justification.

**Section 3 — Suppression Breakdown Table:**

A detailed breakdown of the exact counts and percentages for each suppression category.

**Section 4 — Exact Duplicate Clusters (top 200):**

Groups of documents with the same MD5 hash, showing the control numbers of the Master and its duplicates.

**Section 5 — Near-Duplicate Cluster Detail (top 200):**

Groups of near-duplicate documents, showing the Principal and each suppressed cluster member.

---

### 15.3 Exporting for Court Disclosure

**Steps:**

1. Click **Export to Excel (.xlsx)** to download a four-sheet workbook:
   - **Sheet 1** — Collection Overview metrics
   - **Sheet 2** — Defensibility Summary text
   - **Sheet 3** — Exact duplicate clusters
   - **Sheet 4** — Near-duplicate cluster families
2. Click **Export to CSV** for a summary-only CSV.

**Result:** A complete deduplication record ready for court submission or opposing counsel disclosure as part of your discovery-about-discovery obligations.

---

## 16. Review Batching (Manager+)

Review batching distributes the review workload among multiple attorneys. Each reviewer sees only their assigned queue, and progress is tracked per-batch.

### 16.1 Creating Batches

1. Open the **Review** module.
2. In the sidebar, expand **📦 Review Batches**.
3. You'll see the number of unbatched documents.
4. Choose **Split by** (Document count or Page count) — page count ensures each batch has roughly equal reading effort.
5. Set the **Number of batches** (e.g., 3 for three reviewers).
6. Optionally change the **Batch name prefix** (default: "Batch").
7. Click **Create N batches**.

The platform uses a family-aware algorithm — a parent email and its attachments will always land in the same batch. The algorithm balances batches evenly using the "Longest Processing Time" scheduling heuristic.

### 16.2 Assigning Batches to Reviewers

After creating batches, each batch appears in the sidebar with a document count and progress percentage. Use the dropdown next to each batch to assign it to a specific reviewer.

### 16.3 Working Through Your Batch (Reviewer)

When a reviewer logs in and opens the Review module, they'll see a **View** toggle above the search bar with their assigned batch(es). By default, Reviewers see only their batch; Managers see "All Documents."

For each document:
- Review the content in the document viewer.
- Apply tags as needed (Responsive, Not Responsive, Privileged, etc.).
- Click **"Reviewed — Next ▶"** to record your determination and advance to the next document.
- If you need to save work-in-progress without marking the document as reviewed, click **"Save"** instead — this preserves your tags but does not count the document as reviewed.

> **Important:** A document is only counted as "reviewed" when you click **Reviewed — Next ▶**. Clicking Save, browsing, or opening a document does NOT mark it as reviewed.

### 16.4 Tracking Batch Progress

- A **progress banner** appears above the grid when viewing a batch (e.g., "📦 Batch 1: 45 / 230 reviewed (20%)").
- In the sidebar, each batch shows its progress percentage and a status icon (⬜ Not Started, 🔄 In Progress, ✅ Complete).
- Batch status auto-updates after each "Reviewed — Next" click.

### 16.5 Manual Batch Editing

To move specific documents between batches:
1. In the sidebar, expand **📦 Review Batches** → **✏️ Manual Batch Editing**.
2. Select the target batch.
3. Paste control numbers (one per line or comma-separated).
4. Click **Move to '{batch name}'**.

To delete all batches and start over, click **🗑️ Delete All Batches** at the bottom of the batch expander.

---

## 17. Managing Custodians (Manager+)

The Custodians module (**👤 Custodians** in the sidebar) provides a centralized registry for custodian metadata, operational tools for renaming and merging custodians, and legal hold tracking.

### 17.1 The Custodian Inventory

The page opens with a horizontal bar chart showing every custodian and their document count. Bar colors indicate hold status:
- **Gray** — No hold
- **Green** — Active hold
- **Orange** — Released hold
- **Red** — Expired hold

### 17.2 Editing Custodian Profiles

1. Select a custodian from the dropdown.
2. Edit their **Title**, **Department**, **Email**, **Notes**, and **Data Sources**.
3. Click **💾 Save Custodian Profile**.

The right column shows computed collection statistics (document count, email count, date range).

### 17.3 Renaming a Custodian

In the **✏️ Rename** tab:
1. Select the current name.
2. Enter the new name.
3. The platform shows how many documents will be affected.
4. Click **Rename** to update all documents, the custodian registry, and any hold documents.

> After renaming, go to **Sync → Search Index Maintenance** to rebuild the search index.

### 17.4 Merging Custodians

In the **🔀 Merge** tab:
1. Select the custodian to **keep** (target).
2. Select the custodian to **merge** (source — will be deleted).
3. Type the source custodian's name to confirm.
4. Click **Merge Custodians**.

All documents from the source are reassigned to the target. The source custodian record and hold data are deleted.

> ⚠️ **Warning:** Merge is destructive. If the source custodian has an active legal hold, that hold data will be lost. Transfer hold information manually before merging.

### 17.5 Reassigning Documents

In the **📦 Reassign** tab, move a subset of documents from one custodian to another. Three selection methods:
- **Control number list** — paste specific control numbers.
- **Filter by file extension** — e.g., move all `.msg` files.
- **Filter by date range** — move documents within a date window.

### 17.6 Managing Collections

In the **📁 Collections** tab:
- View the source collection breakdown for a custodian.
- Rename a collection across all its documents.
- Assign a collection name to unorganized (no-collection) documents.

### 17.7 Collection Scope

The Collection Scope tab documents the collection status for each custodian's data sources. This information feeds directly into the Defensibility Report (Section 19.1) and provides a defensible record of what was collected, what was searched but yielded no responsive documents, and what was excluded from collection with justification.

**Prerequisites:** Manager or Admin role required.

**Steps:**

1. Navigate to the **Custodians** page and click the **Collection Scope** tab.
2. Select a custodian from the dropdown.
3. For each data source associated with the custodian, set the **Collection Status**:

| Status | Meaning |
|--------|---------|
| **Collected** | Data from this source was collected and ingested into the platform |
| **Searched-No-Hit** | This source was searched but contained no responsive documents |
| **Not-Reasonably-Accessible** | This source exists but is not reasonably accessible under Rule 26(b)(2)(B) (e.g., legacy backup tapes, decommissioned servers) |
| **Out-of-Scope** | This source is outside the scope of the discovery requests |

4. For each entry, fill in the **Justification** field explaining the basis for the collection decision (e.g., "Backup tapes from 2008 server; restoration cost estimated at $45,000; data predates relevant period by 3 years").
5. Click **Save** after updating each entry.

**Result:** A defensible record of collection decisions for each custodian and data source. This data appears in Section 2.2 of the Defensibility Report.

> ⚠️ **Warning:** The justification field is important for defensibility. Courts increasingly scrutinize collection scope decisions. A blank justification for a "Not-Reasonably-Accessible" or "Out-of-Scope" designation weakens your position in a discovery dispute.

---

## 18. Legal Hold Tracking (Manager+)

Legal hold tracking is part of the Custodians module, accessible below the operations tabs when a custodian is selected.

### 18.1 Setting a Legal Hold

1. Select a custodian on the **Custodians** page.
2. Scroll to **⚖️ Legal Hold Status**.
3. Set the **Hold Status** to Active.
4. Fill in the dates: **Hold Notice Issued**, **Custodian Acknowledged** (when they responded), and **Hold Released** (when applicable).
5. Select the **Notice Method** (Email, Letter, In-Person, Portal, Other).
6. Optionally enter the **Notice Recipient** (may differ from custodian if via counsel) and **Hold Notes**.
7. Click **💾 Save Hold Status**.

The hold card updates with a green "🟢 Active" badge.

### 18.2 Uploading Hold Documents

Below the hold form, you can upload preservation-related files (hold notices, signed acknowledgments, release letters, reminder emails).

1. Use the file uploader to select one or more files.
2. Choose the **Document type** (Hold Notice, Acknowledgment, Release Letter, etc.).
3. Optionally add notes.
4. Click **📤 Save file(s)**.

Uploaded files appear in a list with type badges (📋 Hold Notice, ✅ Acknowledgment, etc.), download buttons, and two-click delete.

> **Important:** Hold documents are stored as administrative records in a separate directory (`Hold_Documents/`). They are **never** added to the case document population, never get control numbers, never appear in Review or Production, and cannot be accidentally produced.

### 18.3 Case Hold Summary and Timeline

At the bottom of the Custodians page, the **📊 Case Hold Summary** shows:
- Metrics: Active Holds, Released, Unacknowledged, Total Custodians on Hold.
- A **Gantt-style timeline chart** showing each custodian's hold period (green = active, orange = released). Active holds with no release date extend to the present.

This summary spans all custodians — it's the case-wide hold posture at a glance.

---

## 19. Generating Reports (Manager+)

### 19.1 Defensibility Report

The Defensibility Report is a one-click, court-ready PDF that assembles existing platform data into a formal document suitable for Rule 26(g) certification, discovery response verification, or meet-and-confer letters.

**To generate:**
1. Go to the **Home** page with a case selected.
2. Scroll to **📋 Defensibility Report**.
3. Click **📄 Generate Defensibility Report**.
4. Wait for the spinner, then click **⬇️ Download Report**.

**The report includes 11 sections:**
1. **Executive Summary** — total documents, custodians, net reviewable, produced, dedup reduction.
2. **Collection & Ingestion** — custodian breakdown, file types, record types.
   - 2.2 **Collection Scope & Justification** — table showing collection decisions for each custodian/source combination (Collected, Searched-No-Hit, Not-Reasonably-Accessible, Out-of-Scope) with the justification text recorded in the Custodian module's Collection Scope tab (Section 17.7).
3. **Processing Protocol** — status breakdown, extraction methods, encrypted documents, OCR usage.
4. **Deduplication Methodology** — 4-layer narrative (MD5, SHA-256, MinHash, threading) with suppression breakdown.
   - 4.1 **Suppression Breakdown** — counts and percentages for each reduction layer. The near-duplicate row now reads "Near-Duplicate Confirmed-Suppressed (reviewer-attested)" to reflect that only reviewer-confirmed duplicates are counted (v2.16).
   - 4.2 **Near-Duplicate Cluster Review & Attestation** (v2.16) — documents the reviewer-gated suppression model for the court: how many near-duplicate clusters were identified, and the disposition of every non-principal document within them — how many were reviewer-confirmed as duplicates and suppressed, how many were retained for family integrity, how many were reviewed and determined distinct, and how many remain pending review. A per-cluster table lists each cluster's principal (by control number), member counts by disposition, similarity range, and the reviewer attestation (who confirmed it, and when). Suppressed documents bear no Bates number because they are excluded from production.
5. **Review Summary** — completion percentage, tag distribution, reviewer activity.
6. **Production Summary** — volumes, Bates ranges, certification, clawback section.
   - **Production Detail by Type** — breakdown of production volumes by type (Original, Supplemental, Replacement) with document counts, Bates ranges, and dates for each volume.
7. **Privilege Handling** — withheld/redacted metrics, no-disposition warnings.
8. **Audit Trail Summary** — event counts by type and user.
9. **Legal Hold Tracking** — hold metrics, unacknowledged warnings, custodian status table (appears only if holds exist).

The report includes a professional cover page with "Privileged & Confidential — Attorney Work Product" stamp, page numbers, and appendices for processing errors.

### 19.2 Rebuilding the Search Index (Admin)

If search filters return unexpected results (especially after custodian renames, merges, or schema changes), you can rebuild the OpenSearch index from the case database.

1. Go to **Sync** (Module 6).
2. The **🔄 Search Index Maintenance** section shows the SQLite document count vs OpenSearch count.
3. Click **🔄 Rebuild Search Index** → confirm.
4. Wait for the progress bar to complete.

This does not reprocess source files — it only reads metadata and text already stored in the database and re-uploads it to the search index with the current field mapping.

---

## 20. Case Maintenance (Manager+)

Case Maintenance provides administrative tools for managing case-level configuration, archival, and data integrity. These features are accessible from the **Home** page when a case is selected.

### 20.1 Matter Profile

The Matter Profile card on the Home dashboard displays and allows editing of key case metadata. This information appears in the Defensibility Report header and on exhibit binder cover sheets.

**Prerequisites:** All roles can view the Matter Profile. Manager or Admin role required to edit.

**Steps:**

1. Navigate to the **Home** page with a case selected.
2. Locate the **Matter Profile** card.
3. The card displays the following fields:

| Field | Description |
|-------|-------------|
| **Matter Number** | The firm's internal matter or file number |
| **Case Caption** | The formal case caption (e.g., "Smith v. Jones Corp.") |
| **Court** | The court where the case is filed (e.g., "U.S. District Court, Southern District of New York") |
| **Presiding Judge** | The assigned judge |
| **Date Filed** | The date the case was filed |
| **Date Opened** | The date the firm opened the matter |
| **Date Closed** | The date the matter was closed (if applicable) |
| **Opposing Counsel** | The name and firm of opposing counsel |
| **Notes** | Free-form notes about the matter |

4. To edit, click **Edit** on the Matter Profile card (Manager+ only).
5. Update the fields as needed.
6. Click **Save**.

**Result:** The case metadata is updated. These values flow into the Defensibility Report and exhibit binder cover sheets automatically.

---

### 20.2 Case Archive

The Case Archive creates a complete ZIP backup of the entire case folder for long-term preservation, transfer to another system, or offsite backup.

**Prerequisites:** Manager or Admin role required. The case must be selected.

**Steps:**

1. Navigate to the **Home** page with a case selected.
2. Locate the **Case Archive** section in Case Maintenance.
3. Click **Create Archive**.
4. The platform packages the entire case folder into a ZIP file, including:
   - The case database (`case.db`)
   - All files in `Ingest\`, `Processed\`, `Produced\`, `Reviewed\`, `Inbound\`, and `Hold_Documents\`
   - A `MANIFEST.json` file listing every file in the archive with its path, size, and MD5 hash
5. When complete, a download button appears.
6. Click **Download** to save the ZIP to your local machine or a network share.

**Result:** A self-contained ZIP archive of the entire case. The `MANIFEST.json` provides a verifiable inventory for chain-of-custody purposes.

> ⚠️ **Warning:** Case archives can be very large (tens of gigabytes for large cases). Ensure you have sufficient disk space for the archive file. The archive process may take several minutes depending on case size.

> ⚠️ **Warning:** The archive includes the case database with all review coding, tags, comments, and audit logs. Store archives securely — they contain attorney work product and potentially privileged information.

---

### 20.3 Issue Coding Fields Admin

This section allows Manager+ users to create, configure, and delete the custom coding fields that appear in the Review module's coding panel (see Section 5.10).

**Prerequisites:** Manager or Admin role required.

**Steps:**

1. Navigate to the **Home** page with a case selected.
2. Locate the **Issue Coding Fields** section in Case Maintenance.
3. To create a new field:
   - Enter a **Field Name** (e.g., "Contract Type", "Contains PII", "Key Issue").
   - Select the **Field Type**:
     - **Picklist** — A dropdown with predefined values. After selecting this type, enter the allowed values (one per line).
     - **Text** — A free-form text input.
     - **Boolean** — A checkbox (yes/no).
   - Click **Create Field**.
4. Existing fields are listed below with their type and configuration. You can:
   - Edit a picklist field's allowed values.
   - Delete a field (with confirmation). Deleting a field removes it from the coding panel and deletes all stored values for that field across all documents.

**Result:** The new field immediately appears in the coding panel for all reviewers in the Review module.

> ⚠️ **Warning:** Deleting a coding field permanently removes all values that reviewers have entered for that field across every document in the case. Export any needed data before deleting a field.

> ⚠️ **Warning:** Issue coding values are attorney work product and are intentionally excluded from production load files. They are accessible only within the platform and in Review Grid CSV exports.

---

### 20.4 De-NIST Filter Configuration

The De-NIST filter excludes system files, executables, and other non-relevant file types from processing based on the NIST National Software Reference Library standard. This prevents system artifacts from inflating the review population.

**Prerequisites:** Admin role required.

**Steps:**

1. Navigate to the **Home** page with a case selected.
2. Locate the **De-NIST Filter** section in Case Maintenance.
3. The current exclusion list shows all file extensions that will be filtered during processing (e.g., `.exe`, `.dll`, `.sys`, `.tmp`, `.log`).
4. To modify the list:
   - **Edit** — Add or remove individual extensions from the exclusion list.
   - **Save** — Save your changes.
   - **Reset to Defaults** — Restore the standard NIST-based exclusion list.
5. To generate a report of excluded files, click **Export Exclusion Report**. This produces a list of all files in the case that match the exclusion filter, useful for defensibility documentation.

**Result:** The exclusion list is updated. Future processing runs will skip files matching the excluded extensions.

> ⚠️ **Warning:** Modifying the De-NIST filter does not retroactively affect already-processed documents. Changes apply only to future processing runs. If you need to include previously excluded file types, add the files to the `Ingest\` folder and re-run ingestion and processing.

---

### 20.5 Hash Integrity Verification

Hash Integrity Verification re-computes the MD5 hash of every processed file and compares it to the hash recorded at ingestion time. This detects any accidental modification or corruption of case files — a critical check for chain-of-custody defensibility.

**Prerequisites:** Admin role required. Documents must have been ingested and processed.

**Steps:**

1. Navigate to the **Home** page with a case selected.
2. Locate the **Hash Integrity** section in Case Maintenance.
3. Click **Run Integrity Check**.
4. The platform re-hashes every file in the `Processed\` folder and compares the result to the original ingestion hash stored in the database.
5. When complete, the results show:
   - **Total files checked**
   - **Files verified (hash match)** — the file is identical to the ingested version.
   - **Mismatches flagged** — the current file hash differs from the ingestion hash, indicating the file was modified after ingestion.

**Result:** A verification report showing whether all processed files maintain their original integrity. Mismatched files are flagged for investigation.

> ⚠️ **Warning:** Hash mismatches do not necessarily indicate tampering — they can result from legitimate operations like re-imaging (Section 5.13) or redaction mark saves (Section 6.4). Investigate each mismatch to determine the cause before raising a chain-of-custody concern.

---

### 20.6 Closed-Case Protections

When a case is transitioned to **Archived** or **Closed** status, the platform automatically enforces read-only mode to preserve the evidentiary record.

**What changes when a case is closed:**

| Module | Behavior |
|--------|----------|
| **Ingestion, Processing, Production, Filevine Sync** | Completely blocked — a banner message explains the case is closed |
| **Review** | Full read access (search, view, filter, export CSV) — but tagging, comments, coding changes, and redaction edits are blocked |
| **Analytics** | All reports and visualizations remain accessible — no new analytics runs can be started |
| **Custodians** | Custodian records and hold information are viewable — edits, merges, and reassignments are blocked |
| **Exhibits** | Exhibit lists and binder PDFs can be viewed and exported — new exhibits cannot be added or reordered |
| **Audit Logs** | Always accessible — full search, filter, and export capabilities regardless of case status |

**How it works:** Each write operation checks the case status independently. This means a closed case never silently drops a write — the user always sees a clear message explaining why the action is unavailable.

**To reopen a case:** An Admin can change the case status back to **Active** from the Home page, which immediately restores full write access across all modules.

---

## 21. Exhibits (Manager+)

The Exhibits module provides a complete workflow for organizing produced documents into exhibit sets for depositions, motions, hearings, and trial. It supports creating named exhibit sets, marking documents as exhibits during review, managing exhibit order and numbering, and exporting printer-ready binder PDFs.

**Prerequisites:** Documents must have been produced (Bates numbers assigned) before they can be marked as exhibits. Navigate to the **Exhibits** module (Module 7) in the sidebar.

### 21.1 Creating Exhibit Sets

An exhibit set is a named collection of exhibits organized for a specific proceeding (e.g., "Deposition of John Smith" or "Motion for Summary Judgment").

**Prerequisites:** Manager or Admin role required to create and manage exhibit sets.

**Steps:**

1. Navigate to **7 Exhibits** in the sidebar.
2. Click **Create New Set**.
3. Fill in the set details:
   - **Set Name** — A descriptive name (e.g., "Deposition of John Smith — March 2026").
   - **Type** — Select the proceeding type: Deposition, Motion, Hearing, or Trial.
   - **Proceeding Date** — The scheduled date of the proceeding.
4. Click **Create**.

**Result:** The exhibit set is created and appears in the set selector. It is empty until you add exhibits.

---

### 21.2 Marking Exhibits During Review

Reviewers can mark produced documents as exhibits directly from the Review module's coding panel.

**Prerequisites:** The document must have been produced. At least one exhibit set must exist. Reviewer or higher role required.

**Steps:**

1. In the **Review** module, select a produced document.
2. In the coding panel, scroll to the **Exhibits** section.
3. If the document is already in any exhibit sets, badges display the set name and exhibit number.
4. Click **Mark as Exhibit**.
5. Select the target **Exhibit Set** from the dropdown.
6. Enter the **Exhibit Number** — this is freeform text to accommodate any numbering convention (e.g., "1", "A", "P-1", "Exhibit 14", "Defendant's Exhibit C").
7. Optionally enter a **Description** (e.g., "Email chain re: Q4 revenue projections").
8. Click **Save**.

**Result:** The document is added to the exhibit set. The same document can be an exhibit in multiple sets with different exhibit numbers.

---

### 21.3 Managing Exhibits

The Exhibits page provides tools for organizing and editing exhibit sets.

**Prerequisites:** Manager or Admin role required.

**Steps:**

1. Navigate to **7 Exhibits** in the sidebar.
2. Use the **Exhibit Set** dropdown to switch between sets.
3. The exhibit list shows all documents in the selected set, in order, with their exhibit number, description, Bates range, and document title.
4. Available management actions:
   - **Edit set details** — Click the edit icon next to the set name to change the name, type, proceeding date, or case caption.
   - **Reorder exhibits** — Use the up/down arrow buttons to change the order of exhibits in the set.
   - **Edit exhibit numbers and descriptions** — Click on any exhibit number or description to edit it inline.
   - **Remove exhibits** — Click the remove button next to an exhibit to remove it from the set (the document itself is not affected).
   - **Add documents** — Click **Add Document** to search for produced documents by control number, Bates number, or filename, and add them to the set.
   - **Delete the entire set** — Click **Delete Set** and confirm by typing the set name. This removes the set and all exhibit assignments within it (the underlying documents are not affected).

**Result:** The exhibit set is updated with your changes.

> ⚠️ **Warning:** Deleting an exhibit set removes all exhibit assignments within it. Documents that were in the set retain their production records but lose their exhibit designations for that set. This cannot be undone.

---

### 21.4 Exporting Binder PDFs

The binder export generates a complete, print-ready PDF containing all exhibits in a set, formatted for court use.

**Prerequisites:** Manager or Admin role required. The exhibit set must contain at least one exhibit.

**Steps:**

1. Navigate to **7 Exhibits** and select the exhibit set.
2. Click **Export Binder PDF**.
3. The platform assembles a PDF containing:
   - **Cover Sheet** — Case caption, exhibit set name, proceeding type, and proceeding date.
   - **Index of Exhibits** — A table listing each exhibit number, description, Bates range, and binder page number.
   - **Divider Pages** — A full-page divider before each exhibit showing the exhibit number and description.
   - **Exhibit Documents** — The actual Bates-stamped produced PDFs for each exhibit.
4. When assembly is complete, a download button appears.
5. Click **Download** to save the binder PDF.

**Result:** A single PDF file containing the complete exhibit binder, ready for printing or electronic filing.

**Formatting notes:**
- All pages are black and white, portrait orientation, and printer-friendly.
- If a document's produced PDF is missing (e.g., due to a file system issue), a placeholder page is inserted rather than failing the entire export. The placeholder identifies the missing document by control number and Bates range.
- Page numbers run continuously through the entire binder for easy reference.

> ⚠️ **Warning:** Binder PDFs can be large. A set with 50 exhibits averaging 10 pages each produces approximately a 500-page PDF. Ensure you have sufficient disk space and allow time for assembly.

---

## 22. Security

### 22.1 Session Timeout

The platform automatically logs out users after a configurable period of inactivity. This protects against unattended sessions with privileged access — for example, a reviewer who walks away from their desk without logging out.

**Default behavior:**

- After 30 minutes of inactivity (no clicks, no page navigation), the platform displays a session expiration warning.
- If the user does not interact within the warning period, the session ends and the user is returned to the login screen.
- Any unsaved work (e.g., an in-progress tag change or comment) is lost when the session expires.

**Configuration:**

The session timeout duration is configurable by the system administrator in the `auth_config.yaml` file. The default is 30 minutes. To change it:

1. Open `auth_config.yaml` in a text editor (system administrator access required).
2. Locate the `session_timeout_minutes` setting.
3. Change the value to the desired number of minutes.
4. Save the file and restart the platform.

> ⚠️ **Warning:** Setting the timeout too short (e.g., 5 minutes) will frustrate reviewers who pause to read documents. Setting it too long (e.g., 8 hours) defeats the purpose of the security control. The 30-minute default balances security with usability.

> ⚠️ **Warning:** The session timeout applies to all users regardless of role. There is no per-role timeout configuration.

---

## Appendix A: Role Permissions Reference

The platform uses named permissions. Administrators can customize which permissions each role has (see Section 13.5). The table below shows the **default** permission assignments.

| Action | Permission | Admin | Manager | Reviewer | Expert |
|--------|------------|-------|---------|----------|--------|
| Log in and select a case | *(always)* | ✅ | ✅ | ✅ | ✅ |
| View Review Grid | `review` | ✅ | ✅ | ✅ | ✅ |
| Search documents | `review` | ✅ | ✅ | ✅ | ✅ |
| Tag documents | `tag` | ✅ | ✅ | ✅ | ✅ |
| Add comments | `comment` | ✅ | ✅ | ✅ | ✅ |
| Save personal searches | `saved_search_personal` | ✅ | ✅ | ✅ | ✅ |
| Save global shared searches | `saved_search_global` | ✅ | ✅ | ✅ | ❌ |
| Download produced documents | `download_produced` | ✅ | ✅ | ✅ | ✅ |
| Redact documents | `redact` | ✅ | ✅ | ✅ | ❌ |
| Export CSV from Review Grid | `export_csv` | ✅ | ✅ | ❌ | ❌ |
| Export PDFs from Review Grid | `export_pdf` | ✅ | ✅ | ❌ | ❌ |
| Configure grid columns | `configure_columns` | ✅ | ✅ | ❌ | ❌ |
| Run Search Term Reports | `str_run` | ✅ | ✅ | ❌ | ✅ |
| Run Ingestor | `ingest` | ✅ | ✅ | ❌ | ❌ |
| Run Processor | `process` | ✅ | ✅ | ❌ | ❌ |
| Run Analytics | `analytics` | ✅ | ✅ | ❌ | ❌ |
| Run Production | `produce` | ✅ | ✅ | ❌ | ❌ |
| Push/Pull Filevine | `sync` | ✅ | ✅ | ❌ | ❌ |
| Manage Custodians / Holds | `custodian_management` | ✅ | ✅ | ❌ | ❌ |
| Generate Defensibility Report | `production` | ✅ | ✅ | ❌ | ❌ |
| Manage users / permissions | `manage_users` | ✅ | ❌ | ❌ | ❌ |
| View/export Audit Logs | `view_audit` | ✅ | ❌ | ❌ | ❌ |
| Rebuild Search Index | `user_admin` | ✅ | ❌ | ❌ | ❌ |
| Factory Reset Case | `user_admin` | ✅ | ❌ | ❌ | ❌ |

---

## Appendix B: Tag Categories Reference

### Default Privilege Tags (red badges)

These tags mark documents as withheld for privilege. Documents with any Privilege tag appear in the Privilege Log.

| Tag | When to Use |
|-----|-------------|
| Attorney-Client Privilege | Confidential communications between attorney and client seeking or providing legal advice |
| Work Product | Documents prepared in anticipation of litigation by or for an attorney |
| Attorney-Client Privilege and Work Product | Documents protected under both doctrines |
| Common Interest Privilege | Communications protected by a shared legal interest among co-parties or co-counsel |
| Joint Defense Privilege | Communications among parties with aligned interests in litigation (variant of Common Interest) |
| Trade Secret | Documents containing proprietary business information protected from disclosure |
| Marital Privilege | Spousal communications protected from compelled disclosure |
| Fifth Amendment | Documents whose production would constitute self-incrimination |
| Settlement Privilege (FRE 408) | Settlement communications protected under Federal Rule of Evidence 408 |
| Self-Critical Analysis Privilege | Internal self-evaluation documents protected in some jurisdictions |
| Executive / Deliberative Process Privilege | Government internal decision-making documents (applies in government cases) |
| Relevance Objection | Documents withheld as outside the scope of discovery (use with caution) |

### Default Responsiveness Tags (green badges)

| Tag | When to Use |
|-----|-------------|
| Responsive | Document is responsive to at least one discovery request |
| Not Responsive | Document is not responsive to any discovery request |
| Hot Document | Particularly significant or important document warranting immediate attorney attention |

### Default Review Status Tags (blue badges)

| Tag | When to Use |
|-----|-------------|
| Needs Review | Document has been seen but requires further review or supervisor sign-off |
| Suppressed | Manually suppressed from the active review set (distinct from system suppression) |

### System Tags (read-only — cannot be manually applied or removed)

| Tag | Set By | Meaning |
|-----|--------|---------|
| `NearDupe-Suppressed` | Analytics | 90%+ content-similar to a Principal document |
| `NearDupe-Principal` | Analytics | Canonical representative of a near-duplicate cluster |
| `Thread-Suppressed` | Analytics | Redundant earlier message in an email thread |
| `Junk Image` | Processor | Image file under 30KB or 150×150 pixels |

---

## Appendix C: Search Syntax Quick Reference

Print this page and keep it at your desk.

| Syntax | Example | What It Finds |
|--------|---------|---------------|
| Single word | `contract` | Documents containing "contract" |
| Exact phrase | `"breach of contract"` | Documents with that exact phrase (word order matters) |
| AND | `contract AND breach` | Documents containing both words |
| OR | `contract OR agreement` | Documents containing either word (or both) |
| NOT | `contract NOT amendment` | Documents with "contract" but not "amendment" |
| Required term | `+contract +breach` | Both terms required (same as AND) |
| Excluded term | `contract -amendment` | "contract" required, "amendment" excluded |
| Wildcard | `negligen*` | "negligence," "negligent," "negligently," etc. |
| Single-char wildcard | `te?t` | "test," "text," "tent," etc. |
| Fuzzy | `recieve~` | Matches "receive" and common misspellings (within 2 edits) |
| Fuzzy distance | `recieve~1` | Matches with 1 edit distance only |
| Field search | `email_from:smith` | Documents where the From field contains "smith" |
| Field phrase | `email_subject:"contract draft"` | Subject line contains exact phrase |
| Grouped | `(contract OR agreement) AND breach` | Boolean logic with grouping |
| Boost | `contract^2 agreement` | "contract" weighted higher in relevance ranking |

**Searchable fields for field-scoped queries:**

| Field | Content |
|-------|---------|
| `email_from` | Sender email address |
| `email_to` | Recipient email addresses |
| `email_cc` | CC'd recipients |
| `email_subject` | Email subject line |
| `custodian` | Document custodian |
| `file_name` | Original filename |
| `content` | Full extracted text (default field when no field is specified) |

> ⚠️ **Warning:** Wildcards (`*`, `?`) and fuzzy (`~`) queries can be slow on large collections because they require scanning the entire index. Use specific terms where possible, and avoid leading wildcards (e.g., `*contract`) which are especially expensive.

---

## Appendix D: UI Tips

**Suppress browser autocomplete:** The platform disables browser autocomplete across all input fields. If your browser still shows autocomplete suggestions, they are coming from your browser's own history (not the platform) and can be dismissed by pressing Escape.

**Tab navigation:** Use the Tab key to move between filter fields in the Review Grid without using the mouse.

**Sidebar collapse:** Click the `<` arrow at the top of the sidebar to collapse it and give the Review Grid more horizontal space on smaller screens.

**Column picker (Manager+):** In the Review Grid, expand the **🗂️ Configure Columns** expander to add, remove, or reorder the columns displayed in the grid. Your column configuration is saved for the current session.

**Sort the grid:** Click any column header in the Review Grid to sort by that column. Click again to reverse the sort direction.

**Document queue:** When you have a document selected in the Review Grid, the document queue panel (top of the right panel) shows `N of M` for your current position in the filtered result set. Use the **Select Document** dropdown to jump directly to any control number in the queue.

**Family navigation:** The **Family & Related Items** expander in the document queue panel shows the parent email and all sibling attachments. Click any control number to jump directly to that document — if the target is outside your current search results, the viewer enters **Peek mode** and a **← Back to queue** button returns you to your original position. Use **Show Full Family in Grid** to temporarily replace the grid with the complete family group.

**Keyboard shortcut — Save tags:** After applying a tag, press Tab to move focus to the next tag element without having to click.

---

## Appendix E: Troubleshooting

### OpenSearch is unavailable

**Symptom:** Search returns no results and shows a connection error. The Home page service status shows OpenSearch as offline. The Analytics near-duplicate tab shows an error.

**Resolution:**

1. Navigate to the Home page.
2. Expand the **🔐 System Backend Settings** panel.
3. Under **OpenSearch**, the connection status is displayed. If it shows disconnected, OpenSearch is not running.
4. OpenSearch must be started manually. Contact your system administrator to start the OpenSearch service, or if you are the administrator, run:
   ```
   {OPENSEARCH_HOME}\bin\opensearch.bat
   ```
   in a command prompt window.
5. Once OpenSearch shows as connected, reload the Review page.

> ⚠️ **Note:** Processing (text extraction) can run without OpenSearch, but documents will not be indexed and full-text search will not work. Run OpenSearch before beginning a Processor run.

---

### Tika is not running

**Symptom:** Processing fails for all documents during Phase 2 with extraction errors. The Processor status shows "Tika: Unavailable" or similar.

**Resolution:**

1. Navigate to the Home page.
2. Expand the **🔐 System Backend Settings** panel.
3. Under **Tika Server**, click **🚀 Launch Tika Server**.
4. Wait a few seconds for the Java server to start.
5. The status indicator should change to show Tika as available.
6. Return to the Processor and retry.

> ⚠️ **Note:** Tika requires Java to be installed on the server. If the Launch button does not work, verify Java is installed and the `TIKA_JAR` path in `config.py` is correct.

---

### Tesseract OCR is not detected

**Symptom:** The Processor status panel shows "Tesseract OCR: Not Available." Image-only PDFs (scanned documents with no extractable text) will have no indexed text and will not appear in full-text searches.

**Resolution:**

1. Verify Tesseract is installed on the server machine at the path configured in `config.py` (default: `C:\Tesseract-OCR\tesseract.exe`).
2. If installed at a different path, ask your administrator to update `TESSERACT_PATH` in `config.py`.
3. Restart the platform (refresh the browser — the Streamlit app will restart).
4. Re-run the Processor for the affected documents (they will have `has_text = 0` in the database).

---

### Processing errors on specific file types

**Symptom:** The Processor summary shows errors for a specific file extension (e.g., all `.rar` files errored, or a specific `.pptx` file failed).

**Common causes and resolutions:**

| Cause | Resolution |
|-------|-----------|
| Password-protected file | Obtain the password, unlock the file, re-register, re-process |
| Corrupted file | Flag the document as an error in your review log; if needed, obtain a replacement copy |
| Very large file exceeding Tika timeout | The 30-minute timeout is configurable in `config.py` (`TIKA_TIMEOUT`). For unusually large files, increase the timeout and re-run the Processor |
| RAR extraction failed | Ensure the `rarfile` library and unrar tool are installed on the server |
| Office document conversion timeout | The COM automation timeout is 90 seconds per document. Very complex Office files may exceed this. For individual documents, try generating the PDF manually outside the platform |

---

### "Database is locked" errors

**Symptom:** An error message appears saying "database is locked" or "SQLite database is locked."

**Cause:** SQLite is designed for a small number of concurrent writers. The platform uses WAL mode and 60-second connection timeouts to minimize this, but very heavy simultaneous writes (e.g., multiple processing runs triggered simultaneously) can still cause conflicts.

**Resolution:**

1. Do not run multiple Processor runs simultaneously.
2. If the error occurs during normal use, wait a few seconds and retry. The lock is typically brief.
3. If the lock is persistent (more than 30 seconds), check if a background thread from a previous session is still running. In rare cases, restarting the Streamlit application (via the server command line) resolves a stuck lock.

> ⚠️ **Warning:** Do not manually delete the `case.db` file or the `case.db-wal` / `case.db-shm` WAL files while the application is running. This will corrupt the database. Always shut down the platform before any manual database file operations.
