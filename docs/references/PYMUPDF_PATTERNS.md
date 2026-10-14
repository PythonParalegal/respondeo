# PyMuPDF (fitz) API Reference — eDiscovery Platform Usage

**Last updated:** 2026-03-18  
**Applies to:** `2_Processor.py` (text extraction, OCR), `4_Review.py` (viewer rendering, redaction annotations), `5_Production.py` (redaction burn, Bates stamping), `pdf_exporter.py` (PDF merge/export), `universal_imager.py` (email-to-PDF, Story API)  
**License:** AGPL-3.0 (commercial Artifex license required for hosted/SaaS deployment)  
**Docs:** https://pymupdf.readthedocs.io/en/latest/

---

## Opening Documents

```python
import fitz

# Open from file path
doc = fitz.open("path/to/file.pdf")

# Open from bytes stream
doc = fitz.open(stream=byte_data, filetype="pdf")

# Create empty document (for building PDFs from scratch)
doc = fitz.open()

# Always close when done
doc.close()

# Preferred: use context manager
with fitz.open("file.pdf") as doc:
    ...
```

---

## Text Extraction (Processor — Phase 2)

```python
doc = fitz.open(filepath)
text = "\n".join(page.get_text() for page in doc)
doc.close()
```

**`page.get_text(option)`** — extraction modes:
| Option | Returns | Use |
|--------|---------|-----|
| `"text"` (default) | Plain text | Our primary extraction path. |
| `"html"` | HTML with formatting | Not used currently. |
| `"dict"` | Dict with blocks/lines/spans | Useful for position-aware extraction. |
| `"rawdict"` | Like "dict" but with character info | Not used. |
| `"words"` | List of `(x0, y0, x1, y1, word, block, line, word_num)` | Not used. |
| `"blocks"` | List of `(x0, y0, x1, y1, text, block, type)` | Not used. |

---

## OCR Fallback (Processor)

When PyMuPDF and Tika both return empty text, we render pages as images and run Tesseract:

```python
doc = fitz.open(filepath)
for page in doc:
    pix = page.get_pixmap(dpi=300)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    text = pytesseract.image_to_string(img)
```

**`page.get_pixmap()`** key parameters:
| Parameter | Default | Notes |
|-----------|---------|-------|
| `dpi` | 72 | We use 300 for OCR quality. Higher = more memory. |
| `colorspace` | `fitz.csRGB` | RGB is fine for OCR. |
| `alpha` | `False` | Transparency. Leave False for OCR. |

**`pix.tobytes(format)`** — `"png"`, `"ppm"`, `"pbm"`. We use `"png"`.

---

## Viewer Rendering (Review Module)

```python
doc = fitz.open(pdf_path)
page = doc[page_num]
mat = fitz.Matrix(zoom, zoom)  # e.g., zoom = dpi / 72
pix = page.get_pixmap(matrix=mat)
img_bytes = pix.tobytes("png")
```

**`fitz.Matrix(sx, sy)`** — scale transform. `fitz.Matrix(2, 2)` = 2x zoom = 144 DPI.

---

## Redaction Annotations (Review Module)

### Adding Redact Annotations
```python
doc = fitz.open(pdf_path)
page = doc[page_num]
rect = fitz.Rect(x0, y0, x1, y1)  # coordinates in PDF points (72 DPI)
annot = page.add_redact_annot(rect, fill=(0, 0, 0))  # black fill

# Store the privilege reason in the annotation's "content" field
annot.set_info(content="Attorney-Client Privilege")

doc.save(pdf_path)
doc.close()
```

### Reading Annotation Info
```python
annot.type       # (type_int, type_str) — 12 = PDF_ANNOT_REDACT
annot.info       # dict with 'content', 'title', etc.
annot.rect       # fitz.Rect of the annotation bounds
```

### Deleting Annotations
```python
for annot in list(page.annots()):  # Must convert to list before deleting
    if annot.type[0] == 12:        # Only delete redact annotations
        page.delete_annot(annot)
```

### Applying Redactions (Production — Burn In)
```python
page.apply_redactions()  # Permanently burns all redact annotations on this page
```

**Critical:** `apply_redactions()` is destructive and irreversible. After calling this, the redacted content is gone from the PDF. This is by design for production — we never want to ship a PDF where redactions can be "lifted."

### Post-Redaction Save: Garbage Collection is MANDATORY

`apply_redactions()` modifies the active content stream to remove text behind redaction marks. However, it does **NOT**:
- Delete the original (pre-redaction) content stream from the PDF object table
- Remove the redaction annotation objects (which contain privilege labels in their `Contents` field)
- Eliminate incremental update artifacts that preserve the pre-redaction page state

Without `garbage=4` on the save call, a forensic examiner can recover the full original text by reading orphaned PDF objects. This has led to sanctions and malpractice claims at other firms.

**Required save pattern after apply_redactions():**
```python
# 1. Apply redactions (burns marks, modifies active content stream)
page.apply_redactions()

# 2. Delete any remaining redaction annotation objects
for annot in list(page.annots() or []):
    if annot.type[0] == 12:  # PDF_ANNOT_REDACT
        page.delete_annot(annot)

# 3. Save with FULL garbage collection
doc.save(output_path, garbage=4, deflate=True, clean=True)
# garbage=4: removes ALL unreferenced objects (orphaned streams, consumed annotations)
# clean=True: rewrites content streams (eliminates incremental update structure)
# deflate=True: recompresses (smaller output)
```

**NEVER** save a redacted PDF without `garbage=4`. This is a data leak, not a cosmetic issue.

**Why `encryption=0`:** Some PDFs have encryption metadata even when not password-protected. `encryption=0` strips it, ensuring the produced PDF is cleanly readable.

---

## Highlight Annotations (Review Search Hits)

```python
annot = page.add_highlight_annot(rect)
annot.set_colors(stroke=(1, 0.9, 0))  # Yellow
annot.set_opacity(0.4)
annot.update()
```

---

## Story API (Email Imaging)

Used to render HTML content into paginated PDFs. This is how we convert email bodies to PDF.

```python
story = fitz.Story(html=html_content)
writer = fitz.DocumentWriter(output_path)
content_rect = fitz.Rect(36, 36, 576, 756)  # Margins within letter-size page

while True:
    device = writer.begin_page(fitz.Rect(0, 0, 612, 792))  # Letter size
    more, _ = story.place(content_rect)
    story.draw(device)
    writer.end_page()
    if not more:
        break

writer.close()
```

**Known issues with Story API:**
- **Base64 images cause infinite looping.** Story can enter an infinite loop trying to lay out very large inline images. We strip base64 images from the HTML before passing to Story, then append them as separate pages afterward.
- **Limited CSS support.** Story supports basic CSS but not all properties. Complex layouts may not render identically to a browser.
- **No JavaScript.** Story renders static HTML only.

---

## Document Manipulation

### Insert PDF Pages (Merging)
```python
merged = fitz.open()
src = fitz.open("source.pdf")
merged.insert_pdf(src)  # Appends all pages
merged.insert_pdf(src, from_page=0, to_page=2)  # Specific range
merged.save("merged.pdf")
```

### New Blank Page
```python
doc = fitz.open()
page = doc.new_page(width=612, height=792)  # Letter size
```

### Insert Text
```python
rect = page.rect + (36, 36, -36, -36)  # Inset margins
page.insert_textbox(rect, text, fontsize=10, fontname="helv", align=0)
```

### Converting Images to PDF Pages
```python
img_stream = fitz.open(stream=img_bytes, filetype="png")
pdfbytes = img_stream.convert_to_pdf()
img_pdf = fitz.open("pdf", pdfbytes)
main_doc.insert_pdf(img_pdf)
```

---

## Key Types

| Type | Description | Common Construction |
|------|-------------|---------------------|
| `fitz.Rect(x0, y0, x1, y1)` | Rectangle in PDF coordinate space (points, 72/inch) | `fitz.Rect(36, 36, 576, 756)` |
| `fitz.Matrix(sx, sy)` | 2D transform matrix | `fitz.Matrix(dpi/72, dpi/72)` |
| `fitz.Pixmap` | Rasterized page image | `page.get_pixmap(...)` |

**Coordinate system:** PDF origin is bottom-left, but PyMuPDF normalizes to top-left. `Rect(0, 0, 612, 792)` = US Letter, where 612pt = 8.5in and 792pt = 11in.

---

## Known Gotchas

### 1. Annotation iteration during deletion
`page.annots()` returns a generator. If you delete annotations while iterating, you'll skip items or crash. Always convert to a list first: `for annot in list(page.annots())`.

### 2. `apply_redactions()` is irreversible
Once called, the content under redaction annotations is permanently removed from the PDF. There is no undo. Our production pipeline copies to a temp file, burns redactions, then replaces — so the pre-redaction original is preserved in the Processed directory.

### 3. Story API infinite loop on large images
`fitz.Story` can enter an infinite layout loop when HTML contains large base64-encoded images. Our workaround: strip all base64 images with `_strip_base64_images()`, render the text body, then append images as separate pages.

### 4. `save()` vs `save(incremental=True)`
`doc.save(path)` does a full rewrite. `doc.save(path, incremental=True)` appends changes. After redaction burn, always use full rewrite (`incremental=False`, the default) to ensure redacted content is physically removed from the file, not just hidden by a newer revision.

### 5. Memory with large documents
PyMuPDF holds page data in memory. For very large PDFs (thousands of pages), process page-by-page and close/reopen if needed. We haven't hit this yet but it's a scaling concern.

### 6. AGPL-3.0 licensing
PyMuPDF is AGPL-licensed. Any hosted or SaaS deployment of our platform requires either open-sourcing the full codebase or purchasing a commercial license from Artifex. This is a known consideration documented in the project memory.

### 7. Windows file locking

`fitz.open()` holds an exclusive Windows file lock for the lifetime of the
document object. Every `fitz.open()` call must be wrapped in `try/finally`
or used as a context manager (`with fitz.open(...) as doc:`) to guarantee
`.close()` runs before any other code path tries to open the same file.
Production and Review modules both touch imaged PDFs from multiple code
paths — a missed close leaves the file locked until the Python process
exits, which on a long-lived Streamlit session means the user gets
`PermissionError: [WinError 32]` on the next operation until they restart.
