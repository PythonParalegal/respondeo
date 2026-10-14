# Respondeo

Respondeo is an on-premises eDiscovery platform. It runs on a single
Windows workstation or server inside your own network, so case data never
leaves your control.

The goal is to give smaller law firms an affordable, self-hosted
alternative to per-gigabyte SaaS review platforms, so they can run
discovery on infrastructure they own.

## Features

- **Ingestion.** Folder and file intake with custodian tracking. PST, ZIP,
  EML and MSG containers are exploded into documents with parent/child
  family relationships preserved (libpff, with Outlook COM as an optional
  fallback).
- **Processing.** Text and metadata extraction via Apache Tika, with
  Tesseract OCR as a fallback for image-only pages. Documents are imaged to
  PDF (native email rendering, LibreOffice for Office formats, wkhtmltopdf
  for HTML).
- **Analytics.** MD5 and content-hash deduplication, email threading
  (Message-ID with subject-line fallback), MinHash near-duplicate
  clustering with reviewer confirmation, and a search term report.
- **Review.** Full-text search (OpenSearch), tagging and coding, privilege
  designation, review batches, family navigation, and role-based access
  control.
- **Redaction.** In-browser redaction with reasons; redactions are burned
  into produced images.
- **Productions.** Bates-numbered productions with DAT and OPT load files,
  native and image exports, and production history.
- **Privilege logs.** Generated from privilege designations and redaction
  reasons.
- **Inbound productions.** Load opposing-party productions from DAT/OPT
  load files.
- **Defensibility report.** A PDF summarizing ingestion, processing,
  deduplication, review, production, privilege and the audit trail for a
  case.

## Requirements

- Windows 10 or 11 (64-bit), or Windows Server, with administrator access
- Python 3.11 (3.12 and 3.13 are untested; 3.14+ is not supported)
- Java 21+ (for Apache Tika and OpenSearch)
- Apache Tika Server, OpenSearch, Tesseract OCR, wkhtmltopdf, and
  LibreOffice (strongly recommended)
- 8 GB RAM minimum; 16 GB or more recommended
- Microsoft Outlook (optional, PST fallback only)

**Linux and macOS:** not supported as a deployment target. Several features
depend on Windows (Outlook/Office COM automation via `pywin32`, the
PowerShell installer, and `.bat` launchers). Most of the test suite runs on
Linux, but full processing and production workflows have only been
exercised on Windows.

## Quick start

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for the full procedure,
including manual and offline installs.

1. Open PowerShell as Administrator and run the bootstrap script, which
   installs Python, Java, the system tools, Tika and OpenSearch and creates
   the virtual environment:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\Deploy-Platform.ps1
   ```
   Or set up the Python environment manually:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copy `config.example.py` to `config.py` and set the tool paths and the
   case data root.
3. Validate the environment:
   ```powershell
   python setup_check.py
   ```
4. Start OpenSearch and Tika (`Start-Services.bat`), then the application:
   ```powershell
   streamlit run home.py --server.address 127.0.0.1 --server.port 8501
   ```
5. Open `http://localhost:8501`.

Before exposing the application or OpenSearch to a network, read the
security items under known limitations below.

## Status and known limitations

Respondeo is beta software. **It has not been certified, audited or
validated for production use in litigation.** Evaluate it on non-critical
data and verify its output independently before relying on it.

Known issues:

- **Review search returns at most 500 hits.** The Review search request is
  fixed at `"size": 500` (`pages/4_Review.py:2652`). Larger result sets are
  silently truncated in the grid.
- **Search term report counts may cap at 10,000.** The report reads
  `hits.total.value` without `track_total_hits`
  (`pages/4_Review.py:821-827`), so OpenSearch reports a lower bound of
  10,000 for terms with more hits.
- **Index items can be dropped on a bulk flush failure.** During reindex,
  if a bulk request raises (for example, a timeout), the whole batch is
  counted as errors and is not retried (`os_manager.py:330-352`). Those
  documents are missing from the search index until the next reindex.
- **OpenSearch is installed without authentication and listening on all
  interfaces.** The installer writes `plugins.security.disabled: true` and
  `network.host: 0.0.0.0` (`Deploy-Platform.ps1:525-527`). Bind OpenSearch
  to `127.0.0.1` or enable the security plugin, and firewall port 9200,
  before using real data.
- **Integration secrets are stored in plaintext.** Filevine client
  secret and access token are saved to the per-case `case_settings` table
  in `case.db` without encryption (`pages/6_Sync.py:562-571`,
  `db_manager.py:4912`). Protect case folders accordingly.
- **The Filevine connector is an untested prototype.** Do not rely on it.
- **Scale.** Testing has been done on small document sets only
  (roughly a thousand documents). Performance and correctness on large
  matters are unknown.
- **Pinned dependencies with published advisories.** As of October 2026,
  `pip-audit` reports advisories for Pillow 12.1.1 (fixed in 12.3.0),
  requests 2.32.5 (2.33.0), lxml 6.0.2 (6.1.0), pytest 9.0.2 (9.0.3) and
  pdfkit 1.0.0 (no fixed release). These pins have not yet been upgraded
  and re-tested.
- **Latent bugs:**
  - Case archive on the Home page references `io` without importing it
    (`home.py:989`), so "Generate Case Archive" raises `NameError`.
  - The Sync page's network pull calls `scan_for_redactions()`
    (`pages/6_Sync.py:849, 856`) before that function is defined
    (`pages/6_Sync.py:1038`), so the pull fails with `NameError` when it
    reaches that path.
  - The custom-role inheritance cycle guard calls an undefined `logger`
    (`auth_manager.py:115`), so a role cycle raises `NameError` instead of
    being logged and ignored.

## Disclaimer

Respondeo is provided **as is, without warranty of any kind**, as stated in
the license. Nothing in this software or its documentation is legal advice.
You are responsible for verifying that its output meets your discovery
obligations, court orders, and professional responsibility rules.

## License

Copyright (C) 2026 PythonParalegal

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, version 3 of the License. See
[LICENSE](LICENSE) for the full text.

Third-party components and their licenses are listed in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md). Note that PyMuPDF is
licensed under AGPL-3.0 (or a commercial license from Artifex), which is
one reason this project uses the AGPL.

## Contributing

Issues and pull requests are welcome. Please open an issue to discuss
significant changes before starting work. Run the test suite
(`python -m pytest tests .claude/hooks/tests`) before submitting, and do
not include real case data, client information or credentials in issues,
commits or test fixtures; use synthetic sample data. By contributing, you
agree that your contributions are licensed under the AGPL-3.0.

Development notes and conventions are in `CLAUDE.md`, `PROJECT_CONTEXT.md`
and `docs/`. Parts of the codebase were written with AI coding agents under
the maintainer's direction.
