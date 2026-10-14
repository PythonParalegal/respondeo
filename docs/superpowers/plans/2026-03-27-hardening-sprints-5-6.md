# Module Hardening Sprints 5-6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose 4 large functions into focused helpers and fix 3 resource cleanup issues — no behavior changes, only internal refactoring.

**Architecture:** Extract private helper functions from oversized functions. Public signatures unchanged. Shared OLE parsing pipeline for MSG functions. Resource leaks fixed with try/finally wrappers.

**Tech Stack:** Python, olefile, PyMuPDF (fitz), pdfkit, email.mime, pypff

**Spec:** `docs/superpowers/specs/2026-03-27-hardening-sprints-5-6-design.md`

**Critical Rule:** These are pure refactoring tasks. NO behavior changes. Every refactored function must produce identical output for identical input. Read the full function before extracting anything.

---

### Task 1: Shared MSG OLE Helpers (universal_imager.py)

**Files:**
- Modify: `universal_imager.py` (add 3 new private helper functions)

**Context:** `convert_msg_to_pdf()` (lines 676-891) and `extract_msg_text()` (lines 892-1091) share ~80% of their OLE parsing code. Both open an OLE file, extract headers (from/to/cc/bcc/subject/date), extract body (HTML→RTF→plain text priority), and collect attachment info. This task extracts 3 shared helpers.

- [ ] **Step 1: Read both functions completely**

Read `convert_msg_to_pdf()` (lines 676-891) and `extract_msg_text()` (lines 892-1091) in full. Identify the shared OLE parsing patterns: header extraction, body extraction, attachment iteration.

Note the existing OLE helper aliases used by both:
- `_ole_extract_string` (module-level, extracts string from OLE property stream)
- `_ole_extract_binary` (module-level, extracts binary from OLE property stream)
- `_ole_extract_filetime` (module-level, extracts Windows FILETIME)
- `_ole_scrape_transport_headers_date` (module-level, parses date from transport headers)
- `_ole_decode_rtf_hex` (module-level, decodes RTF hex escape sequences)

- [ ] **Step 2: Extract `_parse_msg_headers(ole)` helper**

Create a new function BEFORE `convert_msg_to_pdf()`. This function extracts email header fields from an open OLE file object:

```python
def _parse_msg_headers(ole):
    """
    Extract email header fields from an open olefile OLE object.
    Returns dict with keys: subject, sender, to, cc, bcc, date_sent, date_iso,
    transport_headers_raw.
    """
```

Move the header extraction logic from `convert_msg_to_pdf()` lines ~696-740 into this function. This includes:
- Subject extraction (property 0037)
- Sender name + email assembly (properties 0C1A, 0C1F, 0065)
- To/CC/BCC extraction (properties 0E04, 0E03, 0E02)
- Date extraction from transport headers with FILETIME fallback (property 0039)
- Transport headers raw extraction (property 007D)

Return a dict with all fields. Use the module-level `_ole_extract_string`, `_ole_extract_filetime`, `_ole_scrape_transport_headers_date` helpers directly (no local aliases needed).

- [ ] **Step 3: Extract `_parse_msg_body(ole)` helper**

```python
def _parse_msg_body(ole):
    """
    Extract best available body text from an open olefile OLE object.
    Priority: HTML stream → RTF decompression → plain text stream.
    Returns (body_html_or_text: str, is_html: bool).
    """
```

Move body extraction logic from `convert_msg_to_pdf()` lines ~758-791 into this function. This includes:
- Check for HTML body stream (property 1013001F or 10130102)
- RTF body fallback with decompression via `compressed_rtf` module
- Plain text body fallback (property 1000)
- RTF hex decode cleanup
- HTML scrubbing via `_scrub_rtf_from_html()`

Return tuple: (body_string, is_html_boolean).

- [ ] **Step 4: Extract `_parse_msg_attachments(ole, include_data=True)` helper**

```python
def _parse_msg_attachments(ole, include_data=True):
    """
    Extract attachment information from an open olefile OLE object.

    Args:
        ole: Open OleFileIO object
        include_data: If True, read binary data for each attachment.
                     If False, only collect names/metadata (faster for text extraction).

    Returns list of dicts, each with keys:
        filename, content_type, is_inline, cid, data_bytes (bytes or None)
    """
```

Move attachment iteration logic from `convert_msg_to_pdf()` lines ~792-855 into this function. This includes:
- Enumerate `__attach_version1.0_#XXXXXXXX` directories
- Filename resolution: long filename (3703) → short filename (3704) → fallback "attachment_N"
- Content-Type detection from property 370E or mimetypes.guess_type
- CID / inline detection from property 3712
- Binary data extraction from property 3701 (only if include_data=True)
- MIME type fallback for extensionless attachments

Return list of attachment dicts.

- [ ] **Step 5: Refactor `convert_msg_to_pdf()` to use new helpers**

Replace the inline OLE parsing in `convert_msg_to_pdf()` with calls to the 3 new helpers:

```python
def convert_msg_to_pdf(msg_path, output_pdf_path):
    msg_path = str(Path(msg_path).resolve())
    output_pdf_path = str(Path(output_pdf_path).resolve())

    if not olefile:
        return False, "Failed to parse MSG natively: olefile module is missing"

    try:
        with olefile.OleFileIO(msg_path) as ole:
            headers = _parse_msg_headers(ole)
            body_str, is_html = _parse_msg_body(ole)
            attachments = _parse_msg_attachments(ole, include_data=True)

        # Build inline images dict and attachment names from parsed attachments
        inline_images = {}
        attachment_names = []
        for att in attachments:
            if att['is_inline'] and att['data_bytes']:
                # ... base64 encode for CID substitution (preserve existing logic)
            else:
                attachment_names.append(att['filename'])

        # Build HTML, neutralize, substitute CIDs (existing Sprint 2 helpers)
        html = _build_email_html(
            subject=headers['subject'], sender=headers['sender'],
            to=headers['to'], cc=headers['cc'],
            date_str=headers['date_sent'],
            body_html=body_str if is_html else None,
            body_plain=body_str if not is_html else None,
            attachment_names=attachment_names,
        )
        html = _neutralize_external_images(html)
        if inline_images:
            html = _substitute_cid_images(html, inline_images)

        # 3-tier PDF rendering fallback (preserve existing logic exactly)
        # ... wkhtmltopdf → fitz.Story → textbox fallback ...

        _strip_blank_pages(output_pdf_path)
        return True, None
    except Exception as e:
        return False, f"MSG→PDF conversion failed: {e}"
```

**CRITICAL:** Preserve all existing rendering logic (wkhtmltopdf → fitz.Story → textbox fallback chain) exactly as-is. Only the OLE parsing portion should use the new helpers. Read the original function carefully and keep all PDF generation code intact.

- [ ] **Step 6: Refactor `extract_msg_text()` to use new helpers**

Replace the inline OLE parsing in `extract_msg_text()` with calls to the same 3 helpers:

```python
def extract_msg_text(msg_path):
    if not olefile:
        return "", {}

    try:
        with olefile.OleFileIO(msg_path) as ole:
            headers = _parse_msg_headers(ole)
            body_str, is_html = _parse_msg_body(ole)
            attachments = _parse_msg_attachments(ole, include_data=False)

        # Strip HTML tags from body for plain text (preserve existing regex logic)
        if is_html:
            import re
            body_text = re.sub(r'<[^>]+>', ' ', body_str)
            body_text = re.sub(r'\s+', ' ', body_text).strip()
        else:
            body_text = body_str

        # Build compiled text and metadata dict (preserve existing structure exactly)
        attachment_names = [att['filename'] for att in attachments]
        # ... compile metadata dict with all 14 fields ...

        return compiled_text, metadata
    except Exception as e:
        logger.error("extract_msg_text failed for %s: %s", msg_path, e)
        return "", {}
```

**CRITICAL:** The metadata dict returned by `extract_msg_text()` has a specific structure consumed by the Processor module for OpenSearch indexing. Preserve every field name and format exactly.

- [ ] **Step 7: Update version header**

Minor bump (new helper functions). Update `last_modified`, `modified_by`, `last_commit`.

- [ ] **Step 8: Add CHANGELOG entries and commit**

```
### Module Hardening Sprint 5: Function Decomposition (2026-03-27)
- CHANGE: universal_imager.py — extracted _parse_msg_headers(), _parse_msg_body(), _parse_msg_attachments() shared helpers from convert_msg_to_pdf() and extract_msg_text(); net ~150 line reduction, no behavior changes
```

```bash
git add universal_imager.py CHANGELOG.md
git commit -m "refactor: shared MSG OLE pipeline — 3 helpers extracted (Sprint 5)"
```

---

### Task 2: flatten_pdf() Decomposition (universal_imager.py)

**Files:**
- Modify: `universal_imager.py` (decompose flatten_pdf at lines 1410-1654)

- [ ] **Step 1: Read flatten_pdf() completely**

Read lines 1410-1654. Understand the three paths: clean (no interactivity), XFA forms (rasterize), standard AcroForm (strip widgets).

- [ ] **Step 2: Extract `_detect_pdf_interactivity(doc)` helper**

```python
def _detect_pdf_interactivity(doc):
    """
    Check a PyMuPDF document for interactive elements.
    Returns (needs_flatten: bool, is_xfa: bool).
    """
```

Move the 4-check detection logic from flatten_pdf() lines ~1437-1474 into this function:
- AcroForm presence check (xref_get_key on trailer/Root → AcroForms)
- Widget annotation check (page.widgets iterator)
- JavaScript check (xref_get_key on Names/JavaScript)
- Embedded files check (doc.embfile_count())

Also check for XFA (lines ~1483-1500): navigate Root→AcroForm→XFA via xref_get_key.

Return (needs_flatten, is_xfa).

- [ ] **Step 3: Extract `_flatten_xfa_pdf(doc, dest_path)` helper**

```python
def _flatten_xfa_pdf(doc, dest_path):
    """
    Flatten XFA form by rasterizing XFA pages at 200 DPI and copying normal pages.
    Returns (success: bool, error_msg: str or None).
    """
```

Move XFA path logic from flatten_pdf() lines ~1502-1576 into this function. This includes:
- Page-by-page iteration with content stream size check
- Rasterization of XFA pages via `page.get_pixmap(dpi=200)`
- Copy of normal pages via `new_doc.insert_pdf(doc, from_page=i, to_page=i)`
- Residual widget/annotation stripping
- Atomic save via tempfile + shutil.move

- [ ] **Step 4: Extract `_flatten_acroform_pdf(doc, dest_path)` helper**

```python
def _flatten_acroform_pdf(doc, dest_path):
    """
    Flatten standard AcroForm PDF by stripping widgets, JavaScript, and embedded files.
    Returns (success: bool, error_msg: str or None).
    """
```

Move standard path logic from flatten_pdf() lines ~1578-1646 into this function. This includes:
- Strip widgets from all pages via page.delete_widget()
- Strip non-widget annotations that are interactive
- Remove doc-level AcroForm, JavaScript, Names via xref_set_key
- Remove embedded files via embfile_del()
- Garbage-collected save via tempfile + shutil.move

- [ ] **Step 5: Refactor `flatten_pdf()` to router**

```python
def flatten_pdf(source_path, dest_path):
    """
    Creates a litigation-safe copy of a source PDF by stripping all
    interactive elements while preserving text selectability and visual fidelity.
    """
    if not fitz:
        return False, "PyMuPDF (fitz) is not available"

    try:
        doc = fitz.open(source_path)
        try:
            needs_flatten, is_xfa = _detect_pdf_interactivity(doc)

            if not needs_flatten:
                doc.close()
                import shutil
                shutil.copy2(source_path, dest_path)
                return True, None

            if is_xfa:
                return _flatten_xfa_pdf(doc, dest_path)
            else:
                return _flatten_acroform_pdf(doc, dest_path)
        finally:
            if not doc.is_closed:
                doc.close()
    except Exception as e:
        return False, f"PDF flatten failed: {e}"
```

- [ ] **Step 6: Update version header, CHANGELOG, commit**

Patch bump. Add CHANGELOG entry:

```
- CHANGE: universal_imager.py — decomposed flatten_pdf() into _detect_pdf_interactivity(), _flatten_xfa_pdf(), _flatten_acroform_pdf() router pattern; net ~40 line reduction
```

```bash
git add universal_imager.py CHANGELOG.md
git commit -m "refactor: flatten_pdf() decomposed into 3 helpers (Sprint 5)"
```

---

### Task 3: _libpff_message_to_eml() Decomposition (container_exploder.py)

**Files:**
- Modify: `container_exploder.py` (decompose _libpff_message_to_eml at lines 763-980)

- [ ] **Step 1: Read _libpff_message_to_eml() completely**

Read lines 763-980. Understand: transport header parsing, MIME root construction, body attachment, per-attachment processing (regular vs embedded message).

- [ ] **Step 2: Extract `_build_eml_headers(msg)` helper**

```python
def _build_eml_headers(msg):
    """
    Parse transport headers and construct a MIMEMultipart root with email headers set.
    Returns (root: MIMEMultipart, msg_id: str).
    """
```

Move header logic from _libpff_message_to_eml() lines ~769-848 into this function. This includes:
- Transport header parsing via `msg.transport_headers` or `email.message_from_string()`
- From/To/Cc extraction with fallbacks to pypff properties
- Date extraction and formatting
- Subject extraction
- Message-ID extraction or generation
- MIMEMultipart type selection (mixed vs alternative based on attachment count)
- Setting all headers on the root object

Return (root, msg_id).

- [ ] **Step 3: Extract `_attach_eml_bodies(root, msg)` helper**

```python
def _attach_eml_bodies(root, msg):
    """
    Attach plain-text and/or HTML body parts to the MIME root.
    Mutates root in place.
    """
```

Move body attachment logic from lines ~849-859. This includes:
- Plain text body attachment (msg.plain_text_body)
- HTML body attachment (msg.html_body)
- MIMEText part construction for each

- [ ] **Step 4: Extract `_attach_eml_attachment(root, att, index, msg_id)` helper**

```python
def _attach_eml_attachment(root, att, index, msg_id):
    """
    Process a single pypff attachment and append it to the MIME root.
    Handles both regular binary attachments and embedded MAPI messages.
    Mutates root in place.
    """
```

Move per-attachment logic from lines ~872-978. This includes:
- Filename resolution (3 fallbacks using _get_record_string)
- Content-Type detection
- CID / inline detection
- Branch: if MAPI_ATTACH_EMBEDDED_MSG → recursive `_libpff_message_to_eml()` call, wrap in MIMEMessage
- Else: read data, base64 encode, create MIMEBase, set Content-Disposition and Content-ID
- Append part to root

- [ ] **Step 5: Refactor `_libpff_message_to_eml()` to orchestrator**

```python
def _libpff_message_to_eml(msg):
    """
    Build a RFC-compliant .eml bytes object from a pypff message.
    Uses HTML body when available, plain text as fallback.
    Attaches any embedded files as MIME parts.
    """
    root, msg_id = _build_eml_headers(msg)
    _attach_eml_bodies(root, msg)

    num_att = msg.number_of_attachments
    for i in range(num_att):
        try:
            att = msg.get_attachment(i)
            _attach_eml_attachment(root, att, i, msg_id)
        except Exception as att_err:
            logger.warning("Attachment %d failed in libpff EML build: %s", i, att_err)

    return root.as_bytes()
```

- [ ] **Step 6: Update version header, CHANGELOG, commit**

Minor bump for container_exploder.py (new helper functions). Add CHANGELOG:

```
- CHANGE: container_exploder.py — decomposed _libpff_message_to_eml() into _build_eml_headers(), _attach_eml_bodies(), _attach_eml_attachment(); ~25-line orchestrator replaces 218-line monolith
```

```bash
git add container_exploder.py CHANGELOG.md
git commit -m "refactor: _libpff_message_to_eml() decomposed into 3 helpers (Sprint 5)"
```

---

### Task 4: Resource Cleanup — Inline Image Stream Leak (universal_imager.py)

**Files:**
- Modify: `universal_imager.py` (fix _append_inline_images_to_pdf at lines 510-546)

- [ ] **Step 1: Read _append_inline_images_to_pdf() completely**

Read lines 510-546. Note the `fitz.open(stream=...)` and `fitz.open("pdf", ...)` calls inside the per-image loop that are not in try/finally.

- [ ] **Step 2: Wrap fitz.open() calls in try/finally**

Find the inner loop (iterating over `images_dict.items()`). Replace the unprotected open/close pattern with try/finally:

Find this pattern (around lines 527-536):
```python
                img_stream = fitz.open(stream=img_bytes, filetype=filetype)
                img_rect = img_stream[0].rect
                if min(img_rect.width, img_rect.height) < 150:
                    img_stream.close()
                    continue
                pdfbytes = img_stream.convert_to_pdf()
                img_stream.close()

                img_pdf = fitz.open("pdf", pdfbytes)
                main_doc.insert_pdf(img_pdf)
                img_pdf.close()
```

Replace with:
```python
                img_stream = fitz.open(stream=img_bytes, filetype=filetype)
                try:
                    img_rect = img_stream[0].rect
                    if min(img_rect.width, img_rect.height) < 150:
                        continue
                    pdfbytes = img_stream.convert_to_pdf()
                finally:
                    img_stream.close()

                img_pdf = fitz.open("pdf", pdfbytes)
                try:
                    main_doc.insert_pdf(img_pdf)
                finally:
                    img_pdf.close()
```

- [ ] **Step 3: Update version header, CHANGELOG, commit**

Patch bump. Add CHANGELOG:

```
### Module Hardening Sprint 6: Resource Cleanup (2026-03-27)
- FIX: universal_imager.py — inline image stream leak: wrapped fitz.open(stream=...) in try/finally inside _append_inline_images_to_pdf() loop
```

```bash
git add universal_imager.py CHANGELOG.md
git commit -m "fix: inline image stream leak in _append_inline_images_to_pdf (Sprint 6)"
```

---

### Task 5: Resource Cleanup — DB Connection + COM Object (pdf_exporter.py, container_exploder.py)

**Files:**
- Modify: `pdf_exporter.py` (fix export_pdfs_to_zip at lines 237-243)
- Modify: `container_exploder.py` (fix COM object init guard)

- [ ] **Step 1: Fix DB connection leak in pdf_exporter.py**

Read lines 230-250 of `pdf_exporter.py`. Find the unprotected connection pattern:

```python
    conn = db_manager.get_connection(case_folder)
    placeholders = ",".join("?" for _ in control_numbers)
    rows = conn.execute(
        f"SELECT * FROM documents WHERE control_number IN ({placeholders})",
        control_numbers,
    ).fetchall()
    conn.close()
```

Replace with:
```python
    conn = db_manager.get_connection(case_folder)
    try:
        placeholders = ",".join("?" for _ in control_numbers)
        rows = conn.execute(
            f"SELECT * FROM documents WHERE control_number IN ({placeholders})",
            control_numbers,
        ).fetchall()
    finally:
        conn.close()
```

- [ ] **Step 2: Fix COM object init guard in container_exploder.py**

Find the COM processing function (around line 420) where `msg = outlook.OpenSharedItem(...)` is called inside a try block without initializing `msg = None` before the try. The existing finally block has `if msg:` guard which is correct, but `msg` may be undefined if `OpenSharedItem` raises.

Add `msg = None` before the try block:

```python
    msg = None
    try:
        msg = outlook.OpenSharedItem(target_open_path)
        # ... rest of processing ...
```

- [ ] **Step 3: Update version headers for both files**

Patch bump for both `pdf_exporter.py` and `container_exploder.py`. Update `last_modified`, `modified_by`, `last_commit`.

- [ ] **Step 4: Add CHANGELOG entries and commit**

```
- FIX: pdf_exporter.py — DB connection leak: wrapped get_connection() in try/finally in export_pdfs_to_zip()
- FIX: container_exploder.py — COM object init guard: added msg=None before try block for safe finally cleanup
```

```bash
git add pdf_exporter.py container_exploder.py CHANGELOG.md
git commit -m "fix: DB connection leak + COM object init guard (Sprint 6)"
```

---

### Task 6: Context Maintenance + Documentation

**Files:**
- Modify: `CLAUDE.md`, `ROADMAP_TODO.md`, `CHANGELOG.md`
- Modify: `Walkthrough.md`, `Technical Overview.md`, `User_Guide.md`, `PROJECT_CONTEXT.md`

- [ ] **Step 1: Mark Sprint 5-6 items complete in ROADMAP_TODO.md**

Find the function decomposition items (around lines 694-704) and mark them complete:
```
7. [x]   universal_imager.py — Decompose convert_msg_to_pdf()...
8. [x]   universal_imager.py — Decompose extract_msg_text()...
9. [x]   universal_imager.py — Decompose flatten_pdf()...
10. [x]  container_exploder.py — Decompose _libpff_message_to_eml()...
```

And resource cleanup items (around lines 702-704):
```
11. [x]  container_exploder.py — COM object cleanup...
12. [x]  universal_imager.py — Inline image stream leak...
13. [x]  pdf_exporter.py — DB connection cleanup...
```

- [ ] **Step 2: Update CLAUDE.md Current State table**

- `Last completed sprint` → `Module Hardening Sprints 5-6: Function Decomposition + Resource Cleanup`
- `What's next` → `See ROADMAP_TODO.md — Holistic Audit Passes 3-9`

- [ ] **Step 3: Update documentation files**

Add brief mentions of the refactoring to Technical Overview.md and PROJECT_CONTEXT.md:
- Shared MSG OLE pipeline (3 helpers)
- flatten_pdf() router pattern
- _libpff_message_to_eml() orchestrator pattern
- Resource leak fixes

- [ ] **Step 4: Update memory/project_state.md and commit**

```bash
git add CLAUDE.md ROADMAP_TODO.md CHANGELOG.md Walkthrough.md "Technical Overview.md" User_Guide.md PROJECT_CONTEXT.md
git commit -m "docs: context maintenance after Module Hardening Sprints 5-6"
```
