# Third-Party Licenses

> **Last audited:** October 2026, against `requirements.txt`,
> `vendor/wheels/`, and `components/redaction_viewer/frontend/`.

Respondeo is licensed under the **GNU Affero General Public License v3.0**
(see `LICENSE`). This file lists the third-party components it uses, their
licenses, and how each relates to distributing Respondeo under AGPL-3.0.

License data for Python packages comes from installed package metadata
(`pip-licenses`) and the PyPI JSON API. Transitive versions are those
resolved in October 2026 and may differ in your environment. This is an
engineering inventory, not legal advice.

---

## Compatibility summary

**No license incompatible with AGPL-3.0 distribution was found.**

| License | Compatible with AGPL-3.0? | Notes |
|---|---|---|
| MIT, BSD-2/3-Clause, 0BSD, ISC, HPND/MIT-CMU, Zlib, CC0, PSF-2.0 | Yes | Permissive; keep copyright and license notices. |
| Apache-2.0 | Yes (GPLv3-family only) | Keep the license and any NOTICE file; note modifications. |
| MPL-2.0 | Yes | File-level copyleft; modified MPL files stay MPL. |
| LGPL-3.0-or-later | Yes | Users must be able to replace the library (dynamically linked / separate wheel). |
| AGPL-3.0 (PyMuPDF) | Yes | Same license as Respondeo. |
| GPL-2.0-or-later (option of text-unidecode) | Yes | Choose the "or later" option. Dev-only dependency. |
| GPL-2.0 with Classpath Exception (Java runtime) | Not linked | Separate program; not distributed with Respondeo. |
| Commercial (Microsoft Outlook/Office, optional) | Not distributed | Called through COM at runtime only. |

### Points that need attention

1. **PyMuPDF (AGPL-3.0 or Artifex commercial).** PyMuPDF 1.27.1 is
   dual-licensed: GNU AGPL-3.0, or a commercial license from Artifex.
   Respondeo uses it under the AGPL, which matches its own license. If
   Respondeo is ever offered under a separate commercial license, PyMuPDF
   (and MuPDF underneath it) will need an Artifex commercial license or
   must be replaced, because the AGPL terms would otherwise apply to the
   combined work.
2. **Dual licensing generally.** Offering Respondeo commercially in
   addition to the AGPL requires that the copyright holder own or have
   relicensing rights to all contributed code. Accept outside
   contributions only under terms (for example a contributor license
   agreement) that preserve that option.
3. **Network use (AGPL section 13).** Anyone who modifies Respondeo and
   lets users interact with it over a network must offer those users the
   corresponding source.
4. **libpff-python (LGPL-3.0-or-later).** Shipped as a prebuilt wheel in
   `vendor/wheels/`. The wheel itself contains no license file, so the LGPL
   and GPL texts and a source pointer (libyal/libpff, release 20231205) are
   provided alongside it in `vendor/wheels/`. The wheel is installed as a
   separate package, so users can replace it.
5. **wkhtmltopdf (LGPL-3.0).** Invoked as an external executable; not
   distributed. The upstream project is archived and unmaintained.
6. **Attribution.** Apache-2.0, BSD, MIT and MPL components require their
   copyright and license notices to be preserved when redistributed. The
   Python packages are installed from PyPI by the user and carry their own
   notices. The **compiled redaction-viewer bundle**
   (`components/redaction_viewer/frontend/build/`) *is* distributed in this
   repository and contains code from React, React DOM, scheduler
   (MIT, Meta Platforms), streamlit-component-lib (Apache-2.0, Snowflake),
   apache-arrow and flatbuffers (Apache-2.0), hoist-non-react-statics
   (BSD-3-Clause), tslib (0BSD) and several small MIT packages. Their
   notices are reproduced by reference in section 4 below.

---

## 1. External programs (installed separately, not distributed)

| Component | License | How Respondeo uses it |
|---|---|---|
| Python 3.11 | PSF-2.0 | Runtime |
| Java 21 (Eclipse Temurin) | GPL-2.0 with Classpath Exception | Runtime for Tika and OpenSearch |
| Apache Tika Server | Apache-2.0 | Text and metadata extraction over HTTP |
| OpenSearch | Apache-2.0 | Full-text index over HTTP |
| Tesseract OCR | Apache-2.0 | OCR via command line (`pytesseract`) |
| LibreOffice | MPL-2.0 | Office-to-PDF conversion via command line |
| wkhtmltopdf | LGPL-3.0 | HTML-to-PDF via command line (`pdfkit`) |
| Git | GPL-2.0 | Development and deployment tool only |
| Microsoft Outlook / Office | Commercial | Optional COM automation (PST/Office fallback) |

## 2. Python packages (direct, from `requirements.txt`)

| Package | Version | License | Notes |
|---|---|---|---|
| streamlit | 1.55.0 | Apache-2.0 | |
| streamlit-lottie | 0.0.5 | Apache-2.0 | PyPI metadata is blank; license from the upstream repository |
| bcrypt | 5.0.0 | Apache-2.0 | |
| opensearch-py | 3.1.0 | Apache-2.0 | |
| pandas | 2.3.3 | BSD-3-Clause | |
| datasketch | 1.9.0 | MIT | |
| networkx | 3.6.1 | BSD-3-Clause | |
| scipy | 1.17.1 | BSD-3-Clause | |
| plotly | >=5.24.0 (7.1.0 resolved) | MIT | |
| tika | 3.1.0 | Apache-2.0 | Python client for Tika Server |
| **PyMuPDF** | 1.27.1 | **AGPL-3.0 or Artifex commercial** | See point 1 above |
| Pillow | 12.1.1 | MIT-CMU (HPND) | Has published advisories; see README |
| pytesseract | 0.3.13 | Apache-2.0 | |
| pdfkit | 1.0.0 | MIT | Has a published advisory; see README |
| python-docx | 1.2.0 | MIT | |
| mammoth | 1.11.0 | BSD-2-Clause | |
| olefile | 0.47 | BSD-2-Clause | |
| compressed-rtf | 1.0.7 | MIT | |
| lxml | 6.0.2 | BSD-3-Clause | Bundles libxml2/libxslt (MIT) |
| pywin32 | 311 | PSF-2.0 | Windows only |
| requests | 2.32.5 | Apache-2.0 | |
| python-dateutil | 2.9.0.post0 | Apache-2.0 / BSD-3-Clause (dual) | |
| PyYAML | 6.0.3 | MIT | |
| openpyxl | 3.1.5 | MIT | |
| libpff-python | 20231205 (vendored wheel) | LGPL-3.0-or-later | See point 4 above |
| pytest | 9.0.2 | MIT | Development only |
| playwright | 1.52.0 | Apache-2.0 | Development only (E2E tests) |
| pytest-playwright | 0.7.2 | Apache-2.0 | Development only |

`streamlit-drawable-canvas` (MIT) is referenced by `setup_check.py` and
older documentation but is not in `requirements.txt`; the redaction
viewer is now a custom component.

## 3. Python packages (transitive)

| Package | Version | License |
|---|---|---|
| Events | 0.5 | BSD-3-Clause |
| GitPython | 3.2.0 | BSD-3-Clause |
| Jinja2 | 3.1.6 | BSD License |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| Pygments | 2.21.0 | BSD-2-Clause |
| altair | 6.3.0 | BSD License |
| attrs | 26.1.0 | MIT |
| blinker | 1.9.0 | MIT License |
| cachetools | 7.2.1 | MIT |
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| cobble | 0.1.4 | BSD License |
| et_xmlfile | 2.0.0 | MIT License |
| gitdb | 4.0.12 | BSD License |
| greenlet | 3.5.6 | MIT AND PSF-2.0 |
| grpcio | 1.84.0 | Apache-2.0 |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| narwhals | 2.27.1 | MIT |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| opensearch-protobufs | 0.19.0 | Apache Software License |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pluggy | 1.6.0 | MIT License |
| protobuf | 6.33.6 | 3-Clause BSD License |
| pyarrow | 26.0.0 | Apache-2.0 |
| pydeck | 0.9.3 | Apache License 2.0 |
| pyee | 13.0.1 | MIT License |
| pytest-base-url | 2.1.0 | MPL-2.0 |
| python-slugify | 8.0.4 | MIT License |
| pytz | 2026.5 | MIT License |
| referencing | 0.37.0 | MIT |
| rpds-py | 2026.9.1 | MIT |
| six | 1.17.0 | MIT License |
| smmap | 5.0.3 | BSD License |
| tenacity | 9.2.1 | Apache-2.0 |
| text-unidecode | 1.3 | Artistic-1.0 or GPL-2.0-or-later (dev only; via pytest-playwright → python-slugify) |
| toml | 0.10.2 | MIT |
| tornado | 6.5.10 | Apache Software License |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.5 | Apache-2.0 |
| urllib3 | 2.8.0 | MIT |
| watchdog | 6.0.0 | Apache Software License |

## 4. Bundled frontend (redaction viewer)

`components/redaction_viewer/frontend/build/` is a compiled Vite bundle.
Runtime packages included in it (from `package-lock.json`):

| Package | Version | License |
|---|---|---|
| react, react-dom | 18.3.1 (and 16.14.0 via streamlit-component-lib) | MIT |
| scheduler | 0.23.2 / 0.19.1 | MIT |
| prop-types, react-is, loose-envify, js-tokens, object-assign | various | MIT |
| streamlit-component-lib | 2.0.0 | Apache-2.0 |
| apache-arrow | 11.0.0 | Apache-2.0 |
| flatbuffers | 2.0.4 | Apache-2.0 |
| hoist-non-react-statics | 3.3.2 | BSD-3-Clause |
| tslib | 2.8.1 | 0BSD |
| json-bignum | 0.0.3 | MIT |
| command-line-args, command-line-usage, pad-left, and their helpers | various | MIT |

Build-time only (not shipped): TypeScript (Apache-2.0), Vite (MIT),
@vitejs/plugin-react (MIT), @types/* (MIT).

Full license texts for these packages are available in each package's
distribution (`node_modules/<package>/LICENSE` after `npm install`) and
at their upstream repositories.

## 5. Vendored code

| Path | Component | License |
|---|---|---|
| `vendor/wheels/libpff_python-20231205-cp311-cp311-win_amd64.whl` | libpff-python (libyal) | LGPL-3.0-or-later (texts and source pointer in `vendor/wheels/`) |

## 6. Data formats

DAT/OPT (Concordance/Opticon) load files, PDF, EML/MSG/PST, TIFF and
similar formats are file formats, not licensed software, and carry no
license obligations.
