# Python `email` / MIME API Reference — eDiscovery Platform Usage

**Last updated:** 2026-05-18  
**Applies to:** `container_exploder.py` (`_explode_eml`), `universal_imager.py` (EML imaging)  
**Python docs:** https://docs.python.org/3.11/library/email.html

---

## Parsing

We always parse with the modern `email.policy.default` policy, never the legacy (compat32) policy.

```python
import email
from email import policy

with open(path, 'rb') as f:
    msg = email.message_from_binary_file(f, policy=policy.default)
```

**Why `policy.default` matters:** The legacy policy returns raw header values (bytes/encoded strings). The modern policy returns decoded Unicode strings and supports `get_content()` instead of requiring manual charset handling.

---

## Walking MIME Structure

```python
for part in msg.walk():
    # walk() yields every MIME part in depth-first order
    # The first yielded part is the root message itself
```

### Key Methods on Each Part

| Method | Returns | Notes |
|--------|---------|-------|
| `part.get_content_type()` | `str` e.g. `'text/plain'` | Always lowercase. Never `None` — defaults to `'text/plain'` if missing. |
| `part.get_content_maintype()` | `str` e.g. `'text'` | The part before the `/`. |
| `part.get_content_disposition()` | `str` or `None` | `'inline'`, `'attachment'`, or `None` (no Content-Disposition header). |
| `part.get_filename()` | `str` or `None` | Checks Content-Disposition `filename=` param first, then Content-Type `name=` param. Returns `None` if neither exists. **Returns the string even if it's unhelpful** (e.g., `'attachment_0.bin'`). |
| `part.get_param('name')` | `str` or `None` | Reads the `name` parameter specifically from Content-Type. Rarely useful if `get_filename()` already checks it, but some malformed emails only populate one. |
| `part.get('Content-ID')` | `str` or `None` | RFC 2822 Content-ID header, usually wrapped in angle brackets: `<image001.png@01D...>`. Presence indicates an inline CID-referenced image. |
| `part.get_payload(decode=True)` | `bytes` or `None` | Returns decoded binary payload. `decode=True` handles base64/quoted-printable transfer encoding. **Idempotent** — safe to call multiple times. Returns `None` for multipart containers. |
| `part.get_content()` | `str` | Decodes text parts using the charset declared in Content-Type. Only use for `text/*` parts. Raises on binary parts. |

### Common MIME Structure Patterns

**Simple text email (no attachments):**
```
multipart/alternative
├── text/plain       (body)
└── text/html        (body, HTML version)
```

**Email with attachments:**
```
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
├── application/pdf (attachment — Content-Disposition: attachment; filename="doc.pdf")
└── image/png       (attachment)
```

**Email with inline images (CID-referenced):**
```
multipart/related
├── multipart/alternative
│   ├── text/plain
│   └── text/html        (contains <img src="cid:image001"> references)
├── image/png             (Content-ID: <image001>; Content-Disposition: inline)
└── image/jpeg            (Content-ID: <image002>; Content-Disposition: inline)
```

**Apple Mail signature blocks:**
```
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
├── text/html             (Content-Disposition: attachment; — this is a signature fragment!)
└── application/pdf       (real attachment)
```

---

## Known Gotchas — Things That Have Bitten Us

### 1. `get_content_disposition()` is `None` for body parts
Body text/html parts typically have **no** Content-Disposition header at all. Our skip logic relies on `disposition is None` to bypass body parts. If we only checked `disposition != 'attachment'`, we'd also skip `inline` parts (which include CID images).

**Our pattern:** `if part.get_content_disposition() is None: continue` — skips body parts.

### 2. CID images can have `Content-Disposition: attachment` — but presence of Content-ID alone is NOT sufficient
Some clients (notably iPhone Mail) mark inline CID images as `attachment`. Pre-beta-2.15-Commit-5 we treated any `Content-ID` header as the authoritative inline signal:
```python
if part.get('Content-ID'): continue  # OBSOLETE — broken by libpff stamping (see Gotcha #7)
```
This rule silently dropped every PST-extracted attachment because libpff stamps `Content-ID` on EVERY MAPI attachment. The correct test (Commit 5+) uses the shared `is_part_inline_image()` predicate in `container_exploder.py`, which checks BOTH (a) the part is an image and (b) the CID actually appears in the HTML body via `<img src="cid:...">` OR the filename appears via `<img src="...">`. Non-images are never inline regardless of Content-ID. See `docs/lessons/extraction-rendering-symmetry.md`.

### 3. `get_filename()` returns truthy but unhelpful strings
When an email client or converter assigns a name like `attachment_0.bin`, `get_filename()` returns that string — it doesn't know it's unhelpful. Our magic byte detection layer handles this case.

### 4. HTML attachment parts are usually NOT real attachments
`text/html` parts with `Content-Disposition: attachment` are almost always email signature blocks or body fragments (Apple Mail, some Outlook builds). Our exploder skips all `text/html` attachment parts. The imager appends them to the email body as visual content.

### 5. `list(set(attachment_names))` loses ordering
We use this in the imager to deduplicate attachment names for the PDF header. This is fine for display purposes but means the printed order may not match the MIME order. Not a defensibility concern.

### 6. Synthesized EMLs from libpff lose all type information
`_libpff_msg_to_eml_bytes()` historically hardcoded `application/octet-stream` for all attachments. This defeats every type-based filter. Fixed in beta-2.7 to use `mimetypes.guess_type()` from the resolved filename.

### 7. libpff stamps `Content-ID` on every PST-extracted attachment
The original purpose of `Content-ID` is to identify inline images referenced from the HTML body via `<img src="cid:...">`. libpff's stamping is non-RFC behavior driven by MAPI's internal attachment identifiers (every MAPI attachment gets a CID, inline or not). Code that uses `Content-ID` presence alone as an inline signal will silently drop every PST-extracted attachment — including Office docs, PDFs, and other non-image binaries. This was the case-wide test-case defect that motivated beta-2.15 Commit 5.

**The correct inline test:**
- (a) part is image type (`get_content_maintype() == 'image'`), AND
- (b) part's CID is actually referenced via `<img src="cid:...">` in the HTML body, OR its filename appears in `<img src="...">`.

The shared predicate `container_exploder.is_part_inline_image(part, html_cids, html_filenames)` is the single source of truth — both `_explode_eml` and `universal_imager.convert_eml_to_pdf` consume it (extraction-rendering symmetry). See `docs/lessons/extraction-rendering-symmetry.md`.

---

## Constructing Synthesized EMLs (libpff converter)

When we convert a libpff message to EML bytes, we build a MIME tree manually:

```python
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders as _enc

root = MIMEMultipart('mixed')
root['Subject'] = subject
root['From'] = from_header

# Body
root.attach(MIMEText(plain_body, 'plain', 'utf-8'))
root.attach(MIMEText(html_body, 'html', 'utf-8'))

# Attachment
part = MIMEBase('application', 'pdf')  # Use real MIME type, not octet-stream
part.set_payload(att_data)
_enc.encode_base64(part)
part.add_header('Content-Disposition', 'attachment', filename='real_name.pdf')
root.attach(part)

eml_bytes = root.as_bytes()
```

**Critical:** The `MIMEBase` main/sub type must reflect the actual content. Downstream consumers (`_explode_eml`, `universal_imager`) read `get_content_type()` from these parts and make filtering decisions based on it.
