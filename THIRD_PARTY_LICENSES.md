# THIRD_PARTY_LICENSES.md -- Respondeo eDiscovery Platform

> **Last Updated:** March 2026
> **Platform Version:** Beta 2.7

This document inventories every third-party component used by Respondeo
platform, including system-level services, Python packages, and transitive dependencies.
It is provided for transparency, compliance, and client due diligence.

Respondeo's application code is **proprietary**. It calls, imports, or
communicates with the components listed below at runtime but does not modify or
redistribute their source code (except as noted for streamlit-drawable-canvas patch).

---

## Summary of License Types

| License          | Count | Commercial Use | Redistribution | Copyleft |
|------------------|-------|----------------|----------------|----------|
| Apache 2.0       | 12    | Yes            | Yes            | No       |
| MIT              | 15    | Yes            | Yes            | No       |
| BSD (2/3-clause) | 10    | Yes            | Yes            | No       |
| PSF              | 1     | Yes            | Yes            | No       |
| MPL 2.0          | 1     | Yes            | Yes            | Weak     |
| LGPL v3          | 2     | Yes            | Yes            | Weak     |
| AGPL v3          | 1     | See note below | Yes            | **Strong** |
| GPL v2 + CPE     | 2     | Yes (use only) | N/A            | No (use) |

**ATTENTION: PyMuPDF (AGPL v3) -- see detailed note in the Python Packages section.**

---

## 1. System-Level Dependencies (Installed by Deploy-Platform.ps1)

These are standalone applications installed on the host machine. The platform
communicates with them via HTTP, CLI, or COM -- it does not embed or redistribute them.

### Python 3.11
- **License:** Python Software Foundation License (PSF)
- **URL:** https://python.org
- **Use:** Application runtime
- **Notes:** PSF license is permissive; no restrictions on commercial use

### Git
- **License:** GPL v2
- **URL:** https://git-scm.com
- **Use:** Version control (development/deployment tool only; not called at runtime)
- **Notes:** Using Git as a tool does not impose GPL obligations on your own code

### Java 21 (Eclipse Temurin)
- **License:** GPL v2 with Classpath Exception
- **URL:** https://adoptium.net
- **Use:** Runtime for Apache Tika Server and OpenSearch
- **Notes:** The Classpath Exception explicitly permits use without GPL obligations

### Apache Tika Server
- **License:** Apache License 2.0
- **URL:** https://tika.apache.org
- **Use:** Text extraction from documents (PDF, Office, email)
- **Notes:** Runs as a separate HTTP service on port 9998; permissive license

### OpenSearch
- **License:** Apache License 2.0
- **URL:** https://opensearch.org
- **Use:** Full-text search indexing and querying
- **Notes:** Runs as a separate HTTP service on port 9200; permissive license.
  OpenSearch is the open-source fork of Elasticsearch created after Elastic
  relicensed to SSPL.

### wkhtmltopdf
- **License:** LGPL v3
- **URL:** https://wkhtmltopdf.org
- **Use:** HTML-to-PDF conversion (called as external executable)
- **Notes:** LGPL permits use as an unmodified external tool without imposing
  license obligations. The platform calls it via CLI, does not link to it.

### Tesseract OCR
- **License:** Apache License 2.0
- **URL:** https://github.com/tesseract-ocr/tesseract
- **Use:** Optical character recognition for scanned documents
- **Notes:** Called as external executable via pytesseract wrapper; permissive

### LibreOffice (strongly recommended, not required)
- **License:** Mozilla Public License 2.0 (MPL)
- **URL:** https://www.libreoffice.org
- **Use:** High-fidelity Office-to-PDF conversion
- **Notes:** Called as external executable. MPL is a weak copyleft license that
  only requires sharing modifications to LibreOffice itself (not calling code).
  Platform falls back to mammoth if not installed.

### Microsoft Outlook (optional)
- **License:** Commercial (Microsoft 365 / Office license)
- **URL:** https://www.microsoft.com/microsoft-365
- **Use:** PST file extraction via COM automation (pywin32)
- **Notes:** Requires a licensed installation of Outlook on the host machine.
  Only needed for PST processing; all other features work without it.

---

## 2. Python Packages (Direct Dependencies)

These are installed via pip into the project's virtual environment.

### Streamlit
- **Version:** 1.55.0
- **License:** Apache License 2.0
- **URL:** https://streamlit.io
- **Use:** Web application framework (entire UI)

### streamlit-drawable-canvas
- **Version:** 0.9.3
- **License:** MIT
- **URL:** https://github.com/andfanilo/streamlit-drawable-canvas
- **Use:** In-browser redaction drawing tool
- **Notes:** A post-install JS patch is applied to fix a compatibility bug.
  The patch modifies one token in the bundled JS file. The MIT license
  permits this modification.

### streamlit-lottie
- **Version:** 0.0.5
- **License:** MIT
- **URL:** https://github.com/andfanilo/streamlit-lottie
- **Use:** Animated loading indicators

### bcrypt
- **Version:** 5.0.0
- **License:** Apache License 2.0
- **URL:** https://github.com/pyca/bcrypt
- **Use:** Password hashing for RBAC authentication

### opensearch-py
- **Version:** 3.1.0
- **License:** Apache License 2.0
- **URL:** https://github.com/opensearch-project/opensearch-py
- **Use:** Python client for OpenSearch API

### pandas
- **Version:** 2.3.3
- **License:** BSD 3-Clause
- **URL:** https://pandas.pydata.org
- **Use:** Tabular data manipulation throughout the pipeline

### datasketch
- **Version:** 1.9.0
- **License:** MIT
- **URL:** https://github.com/ekzhu/datasketch
- **Use:** MinHash LSH for near-duplicate document detection

### networkx
- **Version:** 3.6.1
- **License:** BSD 3-Clause
- **URL:** https://networkx.org
- **Use:** Graph algorithms for email threading (message-ID chain resolution)

### scipy
- **Version:** 1.17.1
- **License:** BSD 3-Clause
- **URL:** https://scipy.org
- **Use:** Statistical computations (dependency of datasketch/analytics)

### tika (Python client)
- **Version:** 3.1.0
- **License:** Apache License 2.0
- **URL:** https://github.com/chrismattmann/tika-python
- **Use:** Python wrapper for Apache Tika REST API

### PyMuPDF *** ATTENTION ***
- **Version:** 1.27.1
- **License:** GNU Affero General Public License v3 (AGPL-3.0)
- **URL:** https://github.com/pymupdf/PyMuPDF
- **Use:** PDF rendering, text extraction, page manipulation
- **LICENSING NOTE:**
  PyMuPDF is dual-licensed under AGPL-3.0 and a commercial license from Artifex.
  The AGPL is a strong copyleft license with a "network interaction" clause:
  if you make AGPL-covered software available to users over a network, those
  users must be able to receive the source code.

  **What this means for this platform:**
  The eDiscovery Hub serves its UI via Streamlit (HTTP on port 8501), and
  PyMuPDF is called within that server process. Under a strict reading of
  AGPL Section 13, users accessing the platform via browser could be
  considered "interacting with it remotely through a computer network,"
  which would trigger the source-availability obligation.

  **Current assessment (NOT legal advice):**
  - For internal firm use (employees only, on firm infrastructure), AGPL
    compliance is straightforward: keep the platform source available to
    the firm's own users. Since the platform is not offered to the public,
    the practical risk is minimal.
  - If the platform is ever offered as a hosted service to external clients,
    or if source availability is a concern, a commercial license from Artifex
    should be obtained. Contact: https://artifex.com/licensing
  - Alternative: Replace PyMuPDF with a permissively-licensed PDF library
    (e.g., pypdfium2 under Apache 2.0) if AGPL is unacceptable.

### Pillow
- **Version:** 12.1.1
- **License:** HPND (Historical Permission Notice and Disclaimer, MIT-like)
- **URL:** https://python-pillow.org
- **Use:** Image manipulation (thumbnails, PDF page rendering)

### pytesseract
- **Version:** 0.3.13
- **License:** Apache License 2.0
- **URL:** https://github.com/madmaze/pytesseract
- **Use:** Python wrapper for Tesseract OCR executable

### pdfkit
- **Version:** 1.0.0
- **License:** MIT
- **URL:** https://github.com/JazzCore/python-pdfkit
- **Use:** Python wrapper for wkhtmltopdf (HTML-to-PDF)

### python-docx
- **Version:** 1.2.0
- **License:** MIT
- **URL:** https://github.com/python-openxml/python-docx
- **Use:** Reading/writing Microsoft Word (.docx) files

### mammoth
- **Version:** 1.11.0
- **License:** BSD 2-Clause
- **URL:** https://github.com/mwilliamson/python-mammoth
- **Use:** DOCX-to-HTML conversion (LibreOffice fallback for imaging)

### olefile
- **Version:** 0.47
- **License:** BSD 2-Clause
- **URL:** https://github.com/decalage2/olefile
- **Use:** Parsing OLE2 compound files (legacy .doc, .msg, .xls)

### compressed-rtf
- **Version:** 1.0.7
- **License:** MIT
- **URL:** https://github.com/delimitry/compressed_rtf
- **Use:** Decompressing RTF body content from MSG email files

### lxml
- **Version:** 6.0.2
- **License:** BSD 3-Clause
- **URL:** https://lxml.de
- **Use:** XML/HTML parsing (used by mammoth and document processing)

### libpff-python (pypff)
- **Version:** 20240825
- **License:** LGPL v3
- **URL:** https://github.com/libyal/libpff
- **Use:** PST file extraction without Outlook (fallback path)
- **Notes:** Pure-Python binding to the libpff C library. Used as a fallback when
  Outlook COM automation is unavailable. LGPL permits use as an unmodified
  library without imposing license obligations on the calling code, provided the
  library is dynamically linked (which pip-installed wheels satisfy).

### pywin32
- **Version:** 311
- **License:** PSF License
- **URL:** https://github.com/mhammond/pywin32
- **Use:** Windows COM automation (Outlook PST extraction, Office conversion)
- **Notes:** Windows-only; platform is designed for Windows deployment

### requests
- **Version:** 2.32.5
- **License:** Apache License 2.0
- **URL:** https://requests.readthedocs.io
- **Use:** HTTP client for Filevine API integration (6_Sync.py)

### python-dateutil
- **Version:** 2.9.0.post0
- **License:** Apache License 2.0 / BSD 3-Clause (dual)
- **URL:** https://github.com/dateutil/dateutil
- **Use:** Date parsing and manipulation

### PyYAML
- **Version:** 6.0.3
- **License:** MIT
- **URL:** https://pyyaml.org
- **Use:** Reading/writing auth_config.yaml (user credentials store)

### pytest (development only)
- **Version:** 9.0.2
- **License:** MIT
- **URL:** https://pytest.org
- **Use:** Test framework; not installed in production deployments
- **Notes:** Development dependency only; not required for platform operation

---

## 3. Transitive Dependencies (Automatically Installed)

These are pulled in by the direct dependencies above. They are not imported directly
by platform code but are present in the virtual environment.

| Package                    | Version       | License         | Pulled In By        |
|----------------------------|---------------|-----------------|---------------------|
| altair                     | 6.0.0         | BSD 3-Clause    | streamlit           |
| attrs                      | 25.4.0        | MIT             | jsonschema          |
| blinker                    | 1.9.0         | MIT             | streamlit           |
| cachetools                 | 7.0.2         | MIT             | streamlit           |
| certifi                    | 2026.2.25     | MPL 2.0         | requests            |
| charset-normalizer         | 3.4.4         | MIT             | requests            |
| click                      | 8.3.1         | BSD 3-Clause    | streamlit           |
| cobble                     | 0.1.4         | BSD 2-Clause    | mammoth             |
| colorama                   | 0.4.6         | BSD 3-Clause    | click (Windows)     |
| Events                     | 0.5           | BSD 3-Clause    | opensearch-py       |
| gitdb                      | 4.0.12        | BSD 3-Clause    | GitPython           |
| GitPython                  | 3.1.46        | BSD 3-Clause    | streamlit           |
| grpcio                     | 1.78.0        | Apache 2.0      | opensearch-py       |
| idna                       | 3.11          | BSD 3-Clause    | requests            |
| iniconfig                  | 2.3.0         | MIT             | pytest              |
| Jinja2                     | 3.1.6         | BSD 3-Clause    | streamlit           |
| jsonschema                 | 4.26.0        | MIT             | altair              |
| jsonschema-specifications  | 2025.9.1      | MIT             | jsonschema          |
| MarkupSafe                 | 3.0.3         | BSD 3-Clause    | Jinja2              |
| narwhals                   | 2.17.0        | MIT             | altair              |
| numpy                      | 2.4.2         | BSD 3-Clause    | pandas, scipy       |
| opensearch-protobufs       | 0.19.0        | Apache 2.0      | opensearch-py       |
| packaging                  | 26.0          | Apache 2.0      | streamlit, pytest   |
| pluggy                     | 1.6.0         | MIT             | pytest              |
| protobuf                   | 6.33.5        | BSD 3-Clause    | opensearch-protobufs|
| pyarrow                    | 23.0.1        | Apache 2.0      | streamlit           |
| pydeck                     | 0.9.1         | Apache 2.0      | streamlit           |
| Pygments                   | 2.19.2        | BSD 2-Clause    | streamlit           |
| pytz                       | 2026.1.post1  | MIT             | pandas              |
| referencing                | 0.37.0        | MIT             | jsonschema          |
| rpds-py                    | 0.30.0        | MIT             | referencing         |
| six                        | 1.17.0        | MIT             | python-dateutil     |
| smmap                      | 5.0.2         | BSD 3-Clause    | gitdb               |
| tenacity                   | 9.1.4         | Apache 2.0      | streamlit           |
| toml                       | 0.10.2        | MIT             | streamlit           |
| tornado                    | 6.5.4         | Apache 2.0      | streamlit           |
| typing_extensions          | 4.15.0        | PSF             | streamlit, pydantic |
| tzdata                     | 2025.3        | Apache 2.0      | pandas (Windows)    |
| urllib3                    | 2.6.3         | MIT             | requests            |
| watchdog                   | 6.0.0         | Apache 2.0      | streamlit           |

---

## 4. Data Formats and Protocols (No License Implications)

The platform reads and writes these standard formats. No licensing is involved
in processing open standards:

- **PDF** (ISO 32000) -- open standard
- **SQLite** (public domain) -- database engine is built into Python stdlib
- **EDRM/Concordance load files** (.DAT, .OPT) -- industry-standard delimited text
- **OpenSearch REST API** -- standard HTTP/JSON protocol
- **Tika REST API** -- standard HTTP protocol
- **Filevine REST API** -- commercial API (requires firm's own API credentials)
- **SMTP/MIME** (RFC 5322, RFC 2045) -- email parsing via Python stdlib
- **OLE2** (Microsoft Compound Binary Format) -- parsed via olefile
- **OOXML** (.docx, .xlsx, .pptx) -- ECMA-376 / ISO/IEC 29500 open standard

---

## 5. Recommendations

### For Internal Firm Deployments (Current Use Case)
All components are safe for internal commercial use. The AGPL coverage of PyMuPDF
is a minor concern for internal-only deployments where users are firm employees.
Ensure that firm personnel who access the platform can, upon request, receive the
platform source code. In practice, this is already satisfied if the firm maintains
the Git repository internally.

### If Offering as a Hosted Service to External Clients
Before deploying the platform as a service for external parties:
1. Obtain a commercial license for PyMuPDF from Artifex, OR
2. Replace PyMuPDF with a permissively-licensed alternative (pypdfium2, pikepdf, etc.)
3. Conduct a full license audit with legal counsel

### Ongoing Maintenance
When upgrading any dependency, verify the license has not changed. Notable risk:
packages sometimes switch from permissive to restrictive licenses between major
versions (as Elasticsearch did, prompting the creation of OpenSearch).

---

*This document is provided for informational purposes and does not constitute legal
advice. Consult qualified legal counsel for definitive licensing guidance.*
