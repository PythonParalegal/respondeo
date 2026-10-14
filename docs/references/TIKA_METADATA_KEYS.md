# Apache Tika Metadata Keys Reference — eDiscovery Platform Usage

**Last updated:** 2026-03-18  
**Applies to:** `2_Processor.py` (`get_tika_data()`, `process_file_worker()`)  
**Tika docs:** https://tika.apache.org/  
**Our endpoint:** Configured in `config.py` as `TIKA_ENDPOINT` (default `http://localhost:9998`)

---

## How We Call Tika

```python
from tika import parser

parsed = parser.from_file(
    filepath,
    serverEndpoint=TIKA_ENDPOINT,
    headers={'X-Tika-Skip-Embedded': 'true'},  # Don't recurse into embedded files
    requestOptions={'timeout': TIKA_TIMEOUT}
)

content = parsed.get("content", "")       # Extracted text
metadata = parsed.get("metadata", {})     # Dict of metadata key-value pairs
```

**`X-Tika-Skip-Embedded: true`** — Prevents Tika from recursively extracting text from embedded attachments within container files. We handle container explosion separately in Phase 1.

**Retry logic:** 3 attempts with 1-second delay between failures.

**Text extraction priority:** PyMuPDF → Tika → Tesseract OCR. Tika is the second choice for PDFs (PyMuPDF is faster) but the primary extractor for Office formats, emails, and other document types.

---

## Metadata Key Mapping

Tika returns different key names depending on the file format and the parser that handled it. Our code uses a fallback chain — it tries multiple possible keys for each field and takes the first non-empty value.

### Helper Function

```python
def get_meta_str(keys):
    """Try each key in order; return first non-empty value as a string."""
    for k in keys:
        val = tika_meta.get(k)
        if val:
            if isinstance(val, list):
                return "; ".join(str(item).strip() for item in val)
            return str(val).strip()
    return None
```

**Important:** Tika returns some values as lists (especially multi-valued headers). Always handle `list` type before converting to string.

---

### Field → Tika Key Mapping

Each row shows our internal field name, the Tika keys we check (in fallback order), and which file formats typically populate each key.

#### Email Fields

| Our Field | Tika Keys (fallback order) | Populated By |
|-----------|---------------------------|--------------|
| `subject` | `dc:subject`, `subject`, `Message:Subject` | EML, MSG (via Tika's MBOX/RFC822 parser) |
| `from` | `Message-From`, `Message:From-Email`, `creator`, `Author`, `Sender` | EML, MSG. Note: `creator`/`Author` are non-email fallbacks for documents |
| `to` | `Message-To`, `Message:To-Email` | EML, MSG |
| `cc` | `Message-Cc`, `Message:CC-Email` | EML, MSG |
| `bcc` | `Message-Bcc` | EML, MSG (rarely populated — BCC stripped on receipt) |
| `msg_id` | `Message-ID`, `identifier`, `Message:Raw-Header:Message-ID` | EML |
| `in_reply_to` | `In-Reply-To`, `Message:Raw-Header:In-Reply-To` | EML |
| `references` | `references`, `Message:Raw-Header:References` | EML |

**Note:** For MSG and EML files, we prefer native metadata (from `extract_msg` / Python `email` module) over Tika. Tika values are fallback only. The override logic is at line 684–693 of `2_Processor.py`.

#### Date Fields

| Our Field | Tika Keys (fallback order) | Notes |
|-----------|---------------------------|-------|
| `created` | `Creation-Date`, `meta:creation-date`, `dcterms:created` | Document creation date. For emails, this is usually the send date. |
| `sent` | `dcterms:created` | **Known approximation:** Tika doesn't have a dedicated "sent" key for emails. We use `dcterms:created` as a proxy. Native email metadata overrides this when available. |
| `received` | `Message:Received-Date`, `dcterms:modified` | `dcterms:modified` is a weak fallback — it's the file modification date, not necessarily receive time. |
| `modified` | `Last-Modified`, `Last-Save-Date`, `dcterms:modified` | Last modification time of the file/document. |

**Date handling:** All date values are passed through `sanitize_date()` which uses `dateutil.parser.parse()` to normalize diverse date string formats to ISO 8601. Tika returns dates as strings in various formats (ISO, RFC 2822, etc.).

#### Document Metadata

| Our Field | Tika Keys (fallback order) | Notes |
|-----------|---------------------------|-------|
| `author` | `Author`, `creator` | Document author. For emails, overridden by sender address via native extractor. |
| `language` | `dc:language`, `Content-Language`, `language` | ISO language code (e.g., `en`, `de`). Not always populated. |
| `title` | `dc:title`, `title` | Document title from metadata (not filename). |
| `mime_type` | `Content-Type` | The detected MIME type. Tika is authoritative here. |
| `creating_app` | `Application-Name`, `Application-Version`, `producer`, `pdf:docinfo:producer` | The application that created the file (e.g., "Microsoft Word", "Adobe Acrobat"). |

#### Numeric / Boolean Fields

| Our Field | Tika Keys (fallback order) | Notes |
|-----------|---------------------------|-------|
| `is_encrypted` | `pdf:encrypted` | `"true"` (string) or `True` (bool) if PDF is password-protected. |
| `word_count` | `meta:word-count`, `Word-Count` | Integer. Can be a list — take first element. Common for Office documents. |
| `page_count` | `xmpTPg:NPages`, `meta:page-count`, `Page-Count`, `pdf:docinfo:custom:NPages` | Integer. Can also be a list. |

---

## Format-Specific Key Availability

Not every key is populated for every format. Here's what to expect:

### PDF
- **Reliably populated:** `Content-Type`, `Creation-Date`, `Last-Modified`, `pdf:encrypted`, `xmpTPg:NPages`, `pdf:docinfo:producer`
- **Sometimes populated:** `Author`, `dc:title`, `dc:language`
- **Never populated:** Email fields (Message-From, etc.)

### Office Documents (.docx, .xlsx, .pptx)
- **Reliably populated:** `Content-Type`, `Author`, `Creation-Date`, `Last-Modified`, `Application-Name`, `meta:word-count` (Word only), `meta:page-count` (Word only)
- **Sometimes populated:** `dc:title`, `dc:subject`, `dc:language`
- **Never populated:** Email fields, `pdf:encrypted`

### Legacy Office (.doc, .xls, .ppt)
- **Reliably populated:** Same as modern Office, but key names may differ slightly
- **Watch out:** `Author` may be an Exchange DN for internally-created documents

### EML
- **Reliably populated:** `Message-From`, `Message-To`, `Message:Subject`, `Content-Type`, `Message-ID`
- **Sometimes populated:** `Message-Cc`, `In-Reply-To`, `references`, `Message:Received-Date`
- **Rarely populated:** `dc:language`, `Author`

### MSG (via Tika)
- **Tika's MSG parser is less reliable than native OLE extraction.** We prefer `extract_msg` / `universal_imager.extract_msg_text()` for MSG files. Tika is fallback only.
- **Watch out:** Tika may extract embedded image base64 data into the content field, bloating text. We strip this with a regex.

### Images (.png, .jpg, .gif, .bmp, .tiff)
- **Reliably populated:** `Content-Type`, `Image Width`, `Image Height`
- **Sometimes populated:** `tiff:XResolution`, `tiff:YResolution`, EXIF data
- **Text content:** Always empty — images go through OCR fallback if needed.

### Plain Text (.txt, .csv)
- **Reliably populated:** `Content-Type`
- **Rarely populated:** Almost nothing else. Content is the file itself.

---

## Post-Extraction Processing

### Base64 stripping (emails only)
```python
tika_text = re.sub(r'(?:[A-Za-z0-9+/]{40,}\s*){50,}', 
                   '\n[Embedded Base64 Data Removed]\n', tika_text)
```
Emails with inline images produce massive base64 blocks in extracted text. We strip these to avoid bloating the OpenSearch index.

### Text truncation (emails only)
```python
if len(tika_text) > 1500000:
    tika_text = tika_text[:1500000] + "\n\n[TEXT TRUNCATED DUE TO EXCESSIVE LENGTH]"
```
Cap at 1.5MB. Only emails with enormous HTML bodies hit this.

### Extraction method tracking
We tag each document with how its text was obtained:
| Value | Meaning |
|-------|---------|
| `native_ole` | MSG/EML native parser (preferred for emails) |
| `pymupdf` | PyMuPDF direct extraction (preferred for PDFs) |
| `tesseract_ocr` | OCR fallback (image-only PDFs, scanned docs) |
| `tika` | Apache Tika (Office docs, fallback for everything else) |

### Raw metadata JSON
The full Tika metadata dict is stored as JSON in the `tika_metadata_json` column. This is a catch-all for fields we don't explicitly map — useful for debugging and future enrichment sprints.

---

## Known Gotchas

### 1. Tika returns lists for some single-value fields
Keys like `Word-Count`, `Page-Count`, and even `Author` can come back as `["42"]` instead of `"42"`. Always check for list type and extract the first element.

### 2. `dcterms:created` is NOT "date sent" for emails
This is the closest Tika gives us, but it's really "date created" in Dublin Core terms. For accurate send dates, always prefer native email metadata.

### 3. Tika server can be slow or unresponsive
We retry 3 times with 1-second delay. The `TIKA_TIMEOUT` config controls per-request timeout. For large files (100MB+ PSTs being parsed by Tika), timeouts are common — but we don't send PSTs to Tika, only their extracted children.

### 4. `X-Tika-Skip-Embedded: true` is critical
Without this header, Tika will recursively extract text from all embedded objects (attachments inside emails, OLE objects inside Word docs). This would double-process content that our Phase 1 container explosion already handles, and bloat the extracted text with duplicate attachment content.

### 5. Content-Type from Tika vs Content-Type from MIME headers
Tika's `Content-Type` metadata value is Tika's own detection of the file type (based on magic bytes + heuristics). This is different from the `Content-Type` MIME header inside an email. Don't confuse the two — they serve different purposes.

### 6. `creator` vs `Author` ambiguity
For PDF files, `creator` is the PDF creator tool (e.g., "Adobe InDesign") while `Author` is the document author. For Office files, both typically refer to the person. Our fallback chain checks `Author` first, then `creator`, which is correct for most formats but may pick up a tool name instead of a person name for some PDFs.
