# Module Hardening Sprints 5-6 — Design Spec

**Date:** 2026-03-27
**Phase:** Module Hardening Sprints 5-6 (function decomposition + resource cleanup)
**Estimated complexity:** ~200 lines net reduction across universal_imager.py, container_exploder.py, pdf_exporter.py

---

## Problem

Four large functions (216-245 lines each) contain multiple logical sections with high coupling, making them hard to reason about, test, and maintain. Three resource cleanup issues risk file descriptor exhaustion and DB connection leaks.

## Principle

Extract helpers, don't rewrite. Public function signatures stay identical. Internal logic moves to private helpers. No behavior changes. Every refactored function must produce identical output for identical input.

---

## Sprint 5: Function Decomposition

### 1. Shared MSG OLE Pipeline (universal_imager.py)

`convert_msg_to_pdf()` (lines 676-891, 216 lines) and `extract_msg_text()` (lines 892-1091, 200 lines) share ~80% of their OLE parsing logic. Extract three shared helpers:

#### New helpers:

**`_parse_msg_headers(ole)` → dict**
- Extracts: from, to, cc, bcc, subject, date_sent, transport_headers_raw
- Uses existing OLE helper aliases (_ole_extract_string, _ole_extract_filetime, etc.)
- Returns a dict with all header fields

**`_parse_msg_body(ole)` → str**
- Priority: HTML stream → RTF decompression → plain text stream
- HTML cleanup (scrub RTF artifacts if present)
- Returns the best available body as a string (HTML preferred)

**`_parse_msg_attachments(ole, include_data=True)` → list[dict]**
- Each dict: filename, content_type, is_inline, cid, data_bytes (bytes or None)
- `include_data=False` for extract_msg_text (only needs names/counts, not binary data)
- Handles the 3-fallback filename resolution
- Handles inline image detection (CID matching)

#### Refactored callers:

**`convert_msg_to_pdf()`** shrinks to ~50 lines:
1. Open OLE
2. Call `_parse_msg_headers(ole)`
3. Call `_parse_msg_body(ole)`
4. Call `_parse_msg_attachments(ole, include_data=True)`
5. Build HTML via `_build_email_html()` (existing Sprint 2 helper)
6. Neutralize external images via `_neutralize_external_images()` (existing)
7. Substitute CID images via `_substitute_cid_images()` (existing)
8. Render PDF via 3-tier fallback (wkhtmltopdf → fitz.Story → textbox)
9. Strip blank pages, return

**`extract_msg_text()`** shrinks to ~40 lines:
1. Open OLE
2. Call `_parse_msg_headers(ole)`
3. Call `_parse_msg_body(ole)` — then strip HTML tags for plain text
4. Call `_parse_msg_attachments(ole, include_data=False)`
5. Compile metadata dict
6. Return (text, metadata)

### 2. flatten_pdf() Decomposition (universal_imager.py)

`flatten_pdf()` (lines 1410-1654, 245 lines) has three distinct paths. Extract:

**`_detect_pdf_interactivity(doc)` → (needs_flatten: bool, is_xfa: bool)**
- Checks: AcroForm presence, widget annotations, JavaScript, embedded files
- Returns early-exit signal for clean PDFs

**`_flatten_xfa_pdf(doc, dest_path)` → (bool, error_msg)**
- Page-by-page: check content stream size, rasterize XFA pages at 200 DPI, copy normal pages
- Strip residual widgets/annotations
- Atomic save via tempfile

**`_flatten_acroform_pdf(doc, dest_path)` → (bool, error_msg)**
- Strip widgets from all pages
- Remove doc-level interactivity (AcroForm, JavaScript, Names)
- Remove embedded files
- Garbage-collected save via tempfile

**Refactored `flatten_pdf()`** becomes ~30-line router:
1. Open doc
2. Call `_detect_pdf_interactivity(doc)`
3. If clean: copy and return
4. If XFA: call `_flatten_xfa_pdf()`
5. Else: call `_flatten_acroform_pdf()`

### 3. _libpff_message_to_eml() Decomposition (container_exploder.py)

`_libpff_message_to_eml()` (lines 763-980, 218 lines) builds RFC-compliant EML from pypff message. Extract:

**`_build_eml_headers(msg)` → MIMEMultipart**
- Parse transport headers
- Set From/To/Cc/Date/Subject/Message-ID
- Determine if multipart/mixed needed (has attachments) vs multipart/alternative
- Returns configured MIMEMultipart root

**`_attach_eml_bodies(root, msg)` → None**
- Attach plain-text body part (if present)
- Attach HTML body part (if present)
- Mutates root in place

**`_attach_eml_attachment(root, att, index, msg_id)` → None**
- Filename resolution (3 fallbacks)
- Content-Type detection
- CID/inline detection
- Branch: embedded message (recursive) vs regular binary
- For embedded: recursive call to `_libpff_message_to_eml()` with depth guard
- For binary: read data, base64 encode, create MIMEBase
- Appends to root

**Refactored `_libpff_message_to_eml()`** becomes ~25-line orchestrator:
1. Call `_build_eml_headers(msg)`
2. Call `_attach_eml_bodies(root, msg)`
3. Loop attachments: call `_attach_eml_attachment(root, att, i, msg_id)` for each
4. Return `root.as_bytes()`

---

## Sprint 6: Resource Cleanup

### 4. Inline Image Stream Leak (universal_imager.py, lines 510-546)

In `_append_inline_images_to_pdf()`, `fitz.open(stream=img_bytes)` and `fitz.open("pdf", pdfbytes)` inside the per-image loop are not wrapped in try/finally. If `convert_to_pdf()` or `insert_pdf()` raises, the stream handle leaks.

**Fix:** Nest try/finally around each `fitz.open()`:

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

### 5. DB Connection Cleanup (pdf_exporter.py, lines 237-243)

In `export_pdfs_to_zip()`, `db_manager.get_connection()` is called without try/finally. If the query raises, the connection leaks.

**Fix:**

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

### 6. COM Object Init Guard (container_exploder.py, ~line 420)

The existing try/finally pattern around COM `msg` is safe due to an `if msg:` guard, but `msg` is not initialized before the try block. If `OpenSharedItem()` raises before assignment, `msg` is undefined (though the guard catches it).

**Fix:** Add `msg = None` before the try block for defensive clarity.

---

## Files Changed

| File | Sprint | What |
|------|--------|------|
| `universal_imager.py` | 5 | Extract 3 shared MSG helpers, 3 flatten_pdf helpers; refactor 3 callers |
| `container_exploder.py` | 5 | Extract 3 EML helpers; refactor 1 caller |
| `universal_imager.py` | 6 | Fix inline image stream leak in _append_inline_images_to_pdf |
| `pdf_exporter.py` | 6 | Fix DB connection leak in export_pdfs_to_zip |
| `container_exploder.py` | 6 | Fix COM object init guard |

## Out of Scope

- Changing public API signatures
- Adding new features
- Restructuring file layout (helpers stay in same file as callers)
- Adding recursion depth limits to _libpff_message_to_eml (noted as future hardening)
