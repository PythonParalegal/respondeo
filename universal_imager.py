# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        universal_imager.py
# version:       1.13.4
# project:       Respondeo eDiscovery Platform
# project_ver:   2.15.0
# last_modified: 2026-05-21 15:33
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import os
import subprocess
import pythoncom
import win32com.client
from pathlib import Path
import logging
import config

logger = logging.getLogger(__name__)

# Squelch Streamlit thread context warnings caused by Windows multiprocessing re-importing UI scripts
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)
try:
    import fitz # PyMuPDF
except ImportError:
    fitz = None
try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import olefile
except ImportError:
    olefile = None

try:
    import compressed_rtf
except ImportError:
    compressed_rtf = None

import struct
from datetime import datetime, timedelta
import re

import html as _html
import email
from email import policy
from email.parser import BytesParser

# Shared inline-image predicate (extraction-rendering symmetry).
# Imported from container_exploder so _explode_eml and convert_eml_to_pdf
# classify each MIME part identically — they can't disagree about what's
# inline vs. attachment. See docs/lessons/extraction-rendering-symmetry.md.
from container_exploder import is_part_inline_image, _collect_html_inline_refs

# ── EDRM Imaging Policy ──────────────────────────────────────────────
# These sets define the *production policy*, not just technical capability.
#
# IMAGE_BY_POLICY: Converted to PDF/TIFF with Bates stamps.
#   These formats preserve all substantive content when imaged.
#
# NATIVE_BY_POLICY: Technically imageable via Office COM, but EDRM best
#   practice and most Case Management Orders require native production
#   because imaging destroys substantive content (formulas, hidden columns,
#   tab structure, cell comments, named ranges).
#   Produced as native files with a Bates slip sheet.
#
# Everything else: No imaging path exists. Produced as native + slip sheet.
#   Functionally identical to NATIVE_BY_POLICY in the production output.

IMAGE_BY_POLICY = frozenset([
    '.pdf',
    '.doc', '.docx', '.rtf',
    '.ppt', '.pptx',
    '.eml', '.msg',
    '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff',
    '.txt', '.log',
    '.htm', '.html',
])

NATIVE_BY_POLICY = frozenset([
    '.xls', '.xlsx', '.xlsm',
    '.csv', '.tsv',
])


def should_image(ext: str) -> bool:
    """Return True if EDRM policy says this extension should be imaged."""
    return ext.lower() in IMAGE_BY_POLICY


def is_native_by_policy(ext: str) -> bool:
    """Return True if this extension is technically imageable but should be produced natively per EDRM."""
    return ext.lower() in NATIVE_BY_POLICY


# ── Constants ─────────────────────────────────────────────────────────
FITZ_STORY_MAX_PAGES = 50           # Safety cap for fitz.Story page loop (email rendering)
XFA_EMPTY_THRESHOLD = 2000          # Byte threshold below which XFA page content stream is considered empty
PDF_EXPORT_FORMAT = 17              # Word ExportAsFixedFormat constant for PDF output
OL_DISCARD = 0                      # Outlook OlInspectorClose: discard changes on close
# PDF annotation type codes (PDF 1.7 spec Table 169) — interactive types stripped during flattening
ANNOT_TYPE_LINK = 1
ANNOT_TYPE_SOUND = 15
ANNOT_TYPE_MOVIE = 16
ANNOT_TYPE_SCREEN = 20
ANNOT_TYPE_RICHMEDIA = 24
ANNOT_TYPE_3D = 25
INTERACTIVE_ANNOT_TYPES = frozenset([
    ANNOT_TYPE_LINK, ANNOT_TYPE_SOUND, ANNOT_TYPE_MOVIE,
    ANNOT_TYPE_SCREEN, ANNOT_TYPE_RICHMEDIA, ANNOT_TYPE_3D,
])


# ── Shared OLE / MSG Parsing Helpers ──────────────────────────────────
def _ole_extract_string(ole, stream_id):
    """Safely extracts a UTF-16LE or CP1252 string stream from an OLE file."""
    for suff in ['001E', '001F']:
        target = f"__substg1.0_{stream_id}{suff}"
        if ole.exists(target):
            try:
                data = ole.openstream(target).read()
                if suff == '001F':
                    return data.decode('utf-16le', errors='ignore').strip('\x00')
                else:
                    return data.decode('cp1252', errors='ignore').strip('\x00')
            except Exception as e:
                logger.debug("Failed to read OLE string stream %s: %s", target, e)
    return None


def _ole_extract_binary(ole, stream_id):
    """Reads a binary (0102) property stream from an OLE file."""
    target = f"__substg1.0_{stream_id}0102"
    if ole.exists(target):
        try:
            return ole.openstream(target).read()
        except Exception as e:
            logger.debug("Failed to read OLE binary stream %s: %s", target, e)
    return None


def _ole_extract_int(ole, stream_id):
    """Read a MAPI PT_I4 (unsigned int32) property stream."""
    target = f"__substg1.0_{stream_id}0003"
    if ole.exists(target):
        try:
            data = ole.openstream(target).read()
            if len(data) >= 4:
                return struct.unpack('<I', data[:4])[0]
        except Exception as e:
            logger.debug("Failed to read OLE int stream %s: %s", target, e)
    return None


def _ole_extract_filetime(ole, stream_id):
    """Extracts and parses a FILETIME structure (100-ns intervals since 1601).
    Returns human-readable string (e.g., 'Monday, March 24, 2026 02:30 PM')."""
    target = f"__substg1.0_{stream_id}0040"
    if ole.exists(target):
        try:
            data = ole.openstream(target).read()
            if len(data) >= 8:
                val = struct.unpack('<Q', data[:8])[0]
                epoch = datetime(1601, 1, 1)
                dt = epoch + timedelta(microseconds=val / 10)
                return dt.strftime('%A, %B %d, %Y %I:%M %p')
        except Exception as e:
            logger.debug("Failed to parse FILETIME stream %s: %s", target, e)
    return None


def _ole_extract_filetime_iso(ole, stream_id):
    """Return FILETIME as ISO 8601 string for database storage."""
    target = f"__substg1.0_{stream_id}0040"
    if ole.exists(target):
        try:
            data = ole.openstream(target).read()
            if len(data) >= 8:
                val = struct.unpack('<Q', data[:8])[0]
                epoch = datetime(1601, 1, 1)
                dt = epoch + timedelta(microseconds=val / 10)
                return dt.isoformat()
        except Exception as e:
            logger.debug("Failed to parse FILETIME ISO stream %s: %s", target, e)
    return None


def _ole_scrape_transport_headers_field(ole, field_name):
    """Extract any named header value from the raw MIME transport headers stream."""
    target = '__substg1.0_007D001F'
    if ole.exists(target):
        try:
            data = ole.openstream(target).read()
            headers = data.decode('utf-16le', errors='ignore').replace('\x00', '')
            m = re.search(
                rf'^{re.escape(field_name)}:\s*(.*)$',
                headers, re.MULTILINE | re.IGNORECASE
            )
            if m:
                return m.group(1).strip()
        except Exception as e:
            logger.debug("Failed to scrape transport header '%s': %s", field_name, e)
    return None


def _ole_scrape_transport_headers_date(ole):
    """Convenience wrapper: scrape the Date header from transport headers."""
    return _ole_scrape_transport_headers_field(ole, 'Date')


def _ole_decode_rtf_hex(match):
    """Regex callback for \\'xx hex escapes in RTF streams."""
    try:
        return bytes.fromhex(match.group(1)).decode('cp1252')
    except Exception:
        return match.group(0)


def _to_iso_date(date_str):
    """Convert a human-readable date string to ISO 8601 for DB storage."""
    if not date_str or date_str in ('Unknown Date',):
        return None
    try:
        from dateutil import parser as _dateparser
        return _dateparser.parse(str(date_str)).isoformat()
    except Exception:
        return str(date_str)


def _strip_base64_images(html_str):
    """
    Remove base64-encoded inline images from HTML before passing to fitz.Story.
    Large data-URI images create atomic blocks that fitz cannot split across pages,
    causing story.place() to return more=1 forever (infinite loop / stretched pages).
    Stripping them here fixes the root cause without capping page counts.
    """
    placeholder = "<span>[Embedded Image - stripped for rendering]</span>"
    # Two passes: double-quoted and single-quoted src attributes
    result = re.sub(r'<img[^>]*\s+src="data:[^"]+"[^>]*>', placeholder, html_str, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r"<img[^>]*\s+src='data:[^']+'[^>]*>", placeholder, result, flags=re.IGNORECASE | re.DOTALL)
    return result


def _strip_blank_pages(pdf_path, min_text_chars=5):
    """
    Post-conversion safety net: removes blank pages from a rendered PDF.
    A page is considered blank if it contains fewer than `min_text_chars`
    characters of extractable text AND has no significant drawing commands.

    Always preserves at least one page (even if all pages are blank)
    so downstream page-count logic never sees a zero-page PDF.
    """
    if not fitz:
        return 0

    try:
        doc = fitz.open(pdf_path)
        total = len(doc)
        if total <= 1:
            doc.close()
            return 0

        blank_indices = []
        for i in range(total):
            page = doc[i]
            text = page.get_text().strip()
            has_drawings = bool(page.get_drawings())
            has_images = bool(page.get_images(full=True))

            if len(text) < min_text_chars and not has_drawings and not has_images:
                blank_indices.append(i)

        # Always keep at least page 0 — never produce an empty PDF
        if 0 in blank_indices and len(blank_indices) == total:
            blank_indices.remove(0)

        if not blank_indices:
            doc.close()
            return 0

        removed = len(blank_indices)
        for i in sorted(blank_indices, reverse=True):
            doc.delete_page(i)

        import tempfile
        _dir = os.path.dirname(pdf_path)
        _fd, _tmp = tempfile.mkstemp(suffix='.pdf', dir=_dir)
        os.close(_fd)
        try:
            doc.save(_tmp, garbage=4, deflate=True)
            doc.close()
            os.replace(_tmp, pdf_path)
        except Exception:
            doc.close()
            if os.path.exists(_tmp):
                try:
                    os.remove(_tmp)
                except OSError:
                    pass
            return 0

        if removed > 0:
            logger.info("Stripped %d blank pages from %s (was %d pages, now %d)",
                        removed, pdf_path, total, total - removed)
        return removed
    except Exception as e:
        logger.warning("_strip_blank_pages failed for %s: %s", pdf_path, e)
        return 0


def _neutralize_external_images(html_str):
    """
    Replace external image src URLs with empty string to prevent wkhtmltopdf
    from attempting to fetch dead/slow remote resources that break email rendering.
    Preserves CID references (handled by inline image substitution) and data URIs.
    """
    result = re.sub(
        r'(<img[^>]*\s+src=")([^"]*?)(")',
        lambda m: m.group(1) + m.group(3) if m.group(2) and not m.group(2).startswith(('cid:', 'data:')) else m.group(0),
        html_str, flags=re.IGNORECASE | re.DOTALL
    )
    result = re.sub(
        r"(<img[^>]*\s+src=')([^']*?)(')",
        lambda m: m.group(1) + m.group(3) if m.group(2) and not m.group(2).startswith(('cid:', 'data:')) else m.group(0),
        result, flags=re.IGNORECASE | re.DOTALL
    )
    return result


def _scrub_rtf_from_html(text):
    """
    Strips residual RTF control words from de-encapsulated HTML.
    Called after hex decoding and htmltag unwrapping. HTML tags survive
    because RTF control words start with backslash, not angle brackets.
    Order matters: longer/compound words before their prefixes.
    """
    # 1. Unwrap any remaining {\*\htmltagNNN ...} wrappers
    text = re.sub(r'\{\\\*\\htmltag\d+\s*(.*?)\}', r'\1', text, flags=re.DOTALL)

    # 2. Strip explicit RTF control words (longest first to avoid prefix collisions)
    # --- htmlrtf toggle (must precede catch-all) ---
    text = re.sub(r'\\htmlrtf\d?\s?', '', text)
    # --- paragraph / line ---
    text = re.sub(r'\\pard\b\s?', '', text)      # \pard before \par
    text = re.sub(r'\\par\b\s?', '', text)
    text = re.sub(r'\\line\b\s?', '<br>', text)
    text = re.sub(r'\\pntext\b\s?', '', text)
    # --- character formatting ---
    for cw in ('plain', 'b0', 'b', 'i0', 'i', 'ulnone', 'ul0', 'ul',
               'strike0', 'strike', 'scaps0', 'scaps', 'super', 'sub', 'nosupersub'):
        text = re.sub(rf'\\{cw}\b\s?', '', text)
    # --- font / color (with numeric argument) ---
    for cw in ('fs', 'f', 'cf', 'highlight'):
        text = re.sub(rf'\\{cw}\d+\s?', '', text)
    # --- indent / spacing (with numeric argument) ---
    for cw in ('li', 'ri', 'fi', 'sa', 'sb', 'sl', 'slmult'):
        text = re.sub(rf'\\{cw}\d+\s?', '', text)
    # --- alignment ---
    for cw in ('ql', 'qr', 'qc', 'qj', 'qd'):
        text = re.sub(rf'\\{cw}\b\s?', '', text)
    # --- direction ---
    for cw in ('ltrch', 'rtlch', 'ltrpar', 'rtlpar'):
        text = re.sub(rf'\\{cw}\b\s?', '', text)
    # --- character type ---
    for cw in ('loch', 'hich', 'dbch'):
        text = re.sub(rf'\\{cw}\b\s?', '', text)
    # --- language / encoding ---
    for cw in ('lang', 'langfe', 'langnp'):
        text = re.sub(rf'\\{cw}\d+\s?', '', text)
    text = re.sub(r'\\noproof\b\s?', '', text)
    # --- misc with numeric arg ---
    for cw in ('kerning', 'expnd', 'expndtw'):
        text = re.sub(rf'\\{cw}\d+\s?', '', text)
    # --- special characters ---
    text = re.sub(r'\\~', '&nbsp;', text)         # non-breaking space
    text = re.sub(r'\\tab\b\s?', '&emsp;', text)

    # 3. Catch-all: any remaining \controlword patterns
    text = re.sub(r'\\[a-z]+\d*\s?', '', text)

    # 4. Remove orphaned RTF curly braces (outside of HTML tags)
    text = re.sub(r'(?<![<&])\{(?![^<]*>)', '', text)
    text = re.sub(r'(?<![<&])\}(?![^<]*>)', '', text)

    return text


# ── Shared Email-to-PDF Helpers ─────────────────────────────────────────────
# These helpers are used by both convert_eml_to_pdf() and convert_msg_to_pdf()
# to avoid duplicating rendering logic. Extracted in the 2.8.0 refactor sprint.

def _build_email_html(sender, date, to, cc, bcc, subject, attachments_html, html_body):
    """Build the standard HTML wrapper for email-to-PDF rendering."""
    return f'''
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; font-size: 11pt; margin: 40px; }}
            .header-block {{ border-bottom: 2px solid #ccc; padding-bottom: 20px; margin-bottom: 20px; }}
            .header-row {{ margin-bottom: 5px; }}
        </style>
    </head>
    <body>
        <div class="header-block">
            <div class="header-row"><b>From:</b> {sender}</div>
            <div class="header-row"><b>Sent:</b> {date}</div>
            <div class="header-row"><b>To:</b> {to}</div>
            {'<div class="header-row"><b>CC:</b> ' + cc + '</div>' if cc else ''}
            {'<div class="header-row"><b>BCC:</b> ' + bcc + '</div>' if bcc else ''}
            <div class="header-row"><b>Subject:</b> {subject}</div>
            {attachments_html}
        </div>
        <div class="body-block">
            {html_body}
        </div>
    </body>
    </html>
    '''


def _wrap_plain_text_as_html(plain_body):
    """Wrap plain text in styled <pre> tags for PDF rendering."""
    import html
    return f"<pre style='font-family: sans-serif; white-space: pre-wrap;'>{html.escape(plain_body)}</pre>"


def _substitute_cid_images(html_body, inline_images):
    """
    Replace cid: references in HTML with base64 data URIs.
    Returns (modified_html, unresolved_dict) where unresolved_dict contains
    images that had no matching <img src="cid:..."> tag in the HTML.
    """
    unresolved = {}
    if html_body and inline_images:
        for cid, b64_string in inline_images.items():
            pattern = r'src=["\']cid:' + re.escape(cid) + r'["\']'
            html_body, n = re.subn(pattern, f'src="{b64_string}"', html_body, flags=re.IGNORECASE)
            if n == 0:
                unresolved[cid] = b64_string
    elif inline_images:
        unresolved = dict(inline_images)
    return html_body, unresolved


def _run_wkhtmltopdf(rendered_html, output_pdf_path):
    """
    Attempt PDF generation via wkhtmltopdf. Returns True if successful.
    Silently returns False if wkhtmltopdf is not installed.
    """
    path_wkhtmltopdf = getattr(config, 'WKHTMLTOPDF_PATH',
                               r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
    if not os.path.exists(path_wkhtmltopdf):
        return False
    try:
        cmd = [
            path_wkhtmltopdf,
            '--quiet',
            '--encoding', 'utf-8',
            '--load-error-handling', 'ignore',
            '--load-media-error-handling', 'ignore',
            '--no-stop-slow-scripts',
            '--disable-javascript',
            '-', output_pdf_path
        ]
        res = subprocess.run(cmd, input=rendered_html.encode('utf-8'),
                             capture_output=True, timeout=30)
        if res.returncode == 0 and os.path.exists(output_pdf_path):
            return True
        logger.error("wkhtmltopdf execution failed: %s",
                     res.stderr.decode('utf-8', errors='ignore'))
        return False
    except Exception as e:
        logger.error("wkhtmltopdf missing or failed: %s", e)
        return False


def _render_fitz_story(html, output_pdf_path):
    """
    Render HTML to PDF using fitz.Story with page-count safety cap.
    Base64 images are stripped before rendering (they cause infinite loops).
    Returns True if successful.
    """
    if not fitz:
        return False
    try:
        story = fitz.Story(html=_strip_base64_images(html))
        writer = fitz.DocumentWriter(output_pdf_path)
        rect = fitz.Rect(36, 36, 576, 756)

        more = 1
        page_count = 0
        while more and page_count < FITZ_STORY_MAX_PAGES:
            device = writer.begin_page(fitz.Rect(0, 0, 612, 792))
            more, _ = story.place(rect)
            story.draw(device)
            writer.end_page()
            page_count += 1
        if more:
            logger.warning("fitz.Story hit %d-page safety cap for %s — HTML may contain layout pathology",
                           FITZ_STORY_MAX_PAGES, output_pdf_path)

        writer.close()
        return True
    except Exception as e:
        logger.warning("fitz.Story rendering failed for %s: %s", output_pdf_path, e)
        return False


def _append_inline_images_to_pdf(output_pdf_path, images_dict):
    """
    Append base64-encoded inline images as full-resolution continuation pages.
    Skips decorative icons/tracking pixels (shortest side < 150px).
    Modifies the PDF at output_pdf_path in place via temp file.
    """
    if not fitz or not images_dict:
        return
    import tempfile, shutil
    try:
        main_doc = fitz.open(output_pdf_path)
        import base64
        for cid, data_uri in images_dict.items():
            try:
                if ';base64,' not in data_uri:
                    continue
                mime_type = data_uri.split(';base64,')[0].split('data:')[1]
                b64_data = data_uri.split(';base64,', 1)[1]
                img_bytes = base64.b64decode(b64_data)
                ext_map = {'image/jpeg': 'jpeg', 'image/png': 'png',
                           'image/gif': 'gif', 'image/bmp': 'bmp'}
                filetype = ext_map.get(mime_type, 'png')
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
            except Exception as img_e:
                logger.warning("Could not append inline image %s: %s", cid, img_e)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.pdf')
        os.close(tmp_fd)
        main_doc.save(tmp_path)
        main_doc.close()
        shutil.move(tmp_path, output_pdf_path)
    except Exception as append_e:
        logger.warning("Could not append inline images to PDF %s: %s",
                       output_pdf_path, append_e)


def convert_eml_to_pdf(eml_path, output_pdf_path):
    """
    Extracts EML contents natively using Python's built-in email module and renders to PDF.
    """
    eml_path = str(Path(eml_path).resolve())
    output_pdf_path = str(Path(output_pdf_path).resolve())
    
    try:
        with open(eml_path, 'rb') as f:
            msg = BytesParser(policy=policy.default).parse(f)
            
        subject = msg.get('subject', 'No Subject')
        sender = msg.get('from', 'Unknown Sender')
        to = msg.get('to', 'Unknown Recipient')
        date = msg.get('date', 'Unknown Date')
        cc = msg.get('cc', '')
        bcc = msg.get('bcc', '')

        # HTML-escape address fields — angle brackets around email addresses
        # (e.g. <user@example.com>) are interpreted as HTML tags by the PDF
        # renderer and silently dropped, leaving only the display name.
        subject = _html.escape(str(subject))
        sender = _html.escape(str(sender))
        to = _html.escape(str(to))
        date = _html.escape(str(date))
        cc = _html.escape(str(cc))
        bcc = _html.escape(str(bcc))

        html_body = None
        plain_body = None
        attachment_names = []
        html_appendages = []
        import base64
        inline_images = {}
        # Filename-referenced inline images deferred for substitution into
        # html_body after the body text is finalized. CID-referenced inlines
        # go straight to inline_images for _substitute_cid_images.
        _deferred_image_parts = []

        # Pre-scan HTML body for inline references (CIDs + filenames). Both
        # sets feed the shared is_part_inline_image() predicate so this
        # function and container_exploder._explode_eml classify each MIME
        # part identically (extraction-rendering symmetry).
        refs = _collect_html_inline_refs(msg)

        # Traverse EML payload
        for part in msg.walk():
            cid = part.get('Content-ID')
            disposition = part.get_content_disposition()
            content_type = part.get_content_type()

            # Classify the part: CID-inline → inline_images dict; filename-inline
            # → defer for html_body substitution; real attachment → header list
            # or html appendage. Pre-Commit-5 the CID-inline branch used `if cid:`
            # alone, which over-collected libpff-stamped CIDs on real attachments.
            # See docs/lessons/extraction-rendering-symmetry.md.
            if cid and cid.strip('<>') in refs.cids:
                # CID-referenced inline → CID substitution path.
                payload = part.get_payload(decode=True)
                if payload:
                    mime_type = content_type
                    b64_img = base64.b64encode(payload).decode('utf-8')
                    inline_images[cid.strip('<>')] = f"data:{mime_type};base64,{b64_img}"
            elif is_part_inline_image(part, refs.cids, refs.filenames):
                # Filename-referenced inline (no CID match) → defer substitution.
                _deferred_image_parts.append(part)
            elif disposition == 'attachment':
                # Real attachment (predicate False) — includes libpff-CID-stamped
                # Office/PDF docs that pre-Commit-5 were silently dropped.
                if content_type == 'text/html':
                    html_appendages.append(part.get_content())
                else:
                    fname = part.get_filename()
                    if fname:
                        attachment_names.append(fname)

            # Extract body — only grab inline (non-attachment) text parts for the primary slot
            if content_type == 'text/html' and not html_body and disposition != 'attachment':
                html_body = part.get_content()
            elif content_type == 'text/plain' and not plain_body:
                plain_body = part.get_content()

        # Append any HTML body fragments (e.g. Apple Mail signature blocks sent as text/html
        # attachments) directly to the end of the primary body so they render as part of
        # the email image rather than appearing as separate child documents.
        if html_appendages:
            separator = '<hr style="border: none; border-top: 1px solid #ccc; margin: 20px 0;">'
            if html_body:
                html_body += separator + separator.join(html_appendages)
            else:
                html_body = separator.join(html_appendages)

        # Resolve deferred filename-referenced inline images: substitute their
        # bytes as base64 data URIs into html_body where the filename matches.
        # is_part_inline_image already verified the filename is in refs.filenames,
        # so substitution should always find a match (modulo regex-escape edges).
        for _img_part in _deferred_image_parts:
            _img_fname = _img_part.get_filename() or ''
            if not (html_body and _img_fname):
                continue
            _payload = _img_part.get_payload(decode=True)
            if not _payload:
                continue
            _mime = _img_part.get_content_type()
            _b64 = base64.b64encode(_payload).decode('utf-8')
            _data_uri = f"data:{_mime};base64,{_b64}"
            _escaped_fname = re.escape(_img_fname)
            html_body = re.sub(
                r'(<img[^>]+src=["\'])[^"\']*' + _escaped_fname + r'(["\'])',
                r'\1' + _data_uri + r'\2',
                html_body,
                flags=re.IGNORECASE
            )
            logger.debug("Substituted inline image by filename: %s", _img_fname)

        html_body, unresolved_inline = _substitute_cid_images(html_body, inline_images)

        plain_body_raw = plain_body if plain_body else "No body text available."
        plain_body_html = _wrap_plain_text_as_html(plain_body_raw)
        if not html_body:
            html_body = plain_body_html

        attachments_html = ""
        if attachment_names:
            attachment_names = list(set(attachment_names))
            attachments_html = f'<div class="header-row"><b>Attachments:</b> {"; ".join(attachment_names)}</div>'

        rendered_html = _build_email_html(sender, date, to, cc, bcc, subject, attachments_html, html_body)

        # Neutralize external image URLs before rendering to prevent dead-link layout cascade
        rendered_html = _neutralize_external_images(rendered_html)

        pdf_generated = _run_wkhtmltopdf(rendered_html, output_pdf_path)
        if pdf_generated and unresolved_inline:
            _append_inline_images_to_pdf(output_pdf_path, unresolved_inline)

        if not pdf_generated:
            pdf_generated = _render_fitz_story(rendered_html, output_pdf_path)
            if pdf_generated:
                _append_inline_images_to_pdf(output_pdf_path, inline_images)

            if not pdf_generated:
                fallback_html = rendered_html.replace(str(html_body), str(plain_body_html)) if str(html_body) != str(plain_body_html) else rendered_html
                pdf_generated = _render_fitz_story(fallback_html, output_pdf_path)

            if not pdf_generated and fitz:
                # Minimal textbox fallback
                doc = fitz.open()
                page = doc.new_page()
                rect = page.rect + (36, 36, -36, -36)
                plain_fallback = f"From: {sender}\nTo: {to}\nDate: {date}\nSubject: {subject}\n\n[HTML Body Could Not Be Rendered]"
                page.insert_textbox(rect, plain_fallback, fontsize=10, fontname="helv", align=0)
                doc.save(output_pdf_path)
                doc.close()
                pdf_generated = True

        if pdf_generated:
            _strip_blank_pages(output_pdf_path)
            return True, None
        else:
            return False, "All HTML to PDF rendering engines failed."

    except Exception as fallback_e:
        return False, f"Failed natively extracting EML. Fallback Error: {fallback_e}"

def _parse_msg_headers(ole):
    """Extract all header fields from an open OLE MSG file.

    Returns a dict with keys: subject, sender, to, cc, bcc, date,
    date_sent_iso, date_received_iso, conversation_topic, conversation_index,
    message_id, in_reply_to, references, importance, sensitivity.
    """
    subject = _ole_extract_string(ole, '0037') or "No Subject"

    # Build From with full email address: "Name <email>"
    _sender_name = _ole_extract_string(ole, '0C1A')   # PR_SENDER_NAME
    _sender_email = _ole_extract_string(ole, '0C1F')   # PR_SENDER_EMAIL_ADDRESS
    if _sender_name and _sender_email and '@' in _sender_email:
        sender = f'{_sender_name} <{_sender_email}>'
    elif _sender_email and '@' in _sender_email:
        sender = _sender_email
    elif _sender_name:
        sender = _sender_name
    else:
        sender = "Unknown Sender"

    # Try transport headers first for To/CC/BCC with full SMTP addresses.
    # Fall back to display-name-only properties if headers unavailable.
    to = "Unknown Recipient"
    cc = ''
    bcc = ''

    _th_stream = '007D'
    for _th_target in ['__substg1.0_' + _th_stream + '001F',
                       '__substg1.0_' + _th_stream + '001E']:
        if ole.exists(_th_target):
            try:
                _th_raw = ole.openstream(_th_target).read()
                if '001F' in _th_target:
                    _th_str = _th_raw.decode('utf-16le', errors='ignore').replace('\x00', '')
                else:
                    _th_str = _th_raw.decode('utf-8', errors='ignore')
                if _th_str.strip():
                    _th_parsed = email.message_from_string(_th_str, policy=policy.default)
                    _th_to = _th_parsed.get('To')
                    _th_cc = _th_parsed.get('Cc')
                    _th_bcc = _th_parsed.get('Bcc')
                    if _th_to and '@' in str(_th_to):
                        to = str(_th_to)
                    if _th_cc and '@' in str(_th_cc):
                        cc = str(_th_cc)
                    if _th_bcc and '@' in str(_th_bcc):
                        bcc = str(_th_bcc)
                break
            except Exception:
                pass

    # Fallback to display-name-only properties
    if to == "Unknown Recipient":
        to = _ole_extract_string(ole, '0E04') or "Unknown Recipient"
    if not cc:
        cc = _ole_extract_string(ole, '0E03') or ''
    if not bcc:
        bcc = _ole_extract_string(ole, '0E02') or ''

    date = (_ole_extract_filetime(ole, '0039')
            or _ole_extract_filetime(ole, '3007')
            or _ole_scrape_transport_headers_date(ole)
            or "Unknown Date")

    # Extended metadata (used by extract_msg_text for indexing)
    date_sent_iso = (_ole_extract_filetime_iso(ole, '0039')
                     or _ole_extract_filetime_iso(ole, '3007')
                     or _to_iso_date(_ole_scrape_transport_headers_date(ole)))
    date_received_iso = _ole_extract_filetime_iso(ole, '0E06')
    conversation_topic = _ole_extract_string(ole, '0070')
    conv_index_raw = _ole_extract_binary(ole, '0071')
    conversation_index = conv_index_raw.hex() if conv_index_raw else None
    message_id = _ole_scrape_transport_headers_field(ole, 'Message-ID')
    if message_id:
        message_id = message_id.strip('<>')
    in_reply_to = _ole_scrape_transport_headers_field(ole, 'In-Reply-To')
    if in_reply_to:
        in_reply_to = in_reply_to.strip('<>')
    references = _ole_scrape_transport_headers_field(ole, 'References')
    # Date fallback from transport headers if no dedicated stream
    if not date_sent_iso:
        _raw_transport_date = _ole_scrape_transport_headers_field(ole, 'Date')
        date_sent_iso = _to_iso_date(_raw_transport_date)
    # Importance: 0=Low, 1=Normal, 2=High
    _imp_val = _ole_extract_int(ole, '0017')
    importance = {0: 'Low', 1: 'Normal', 2: 'High'}.get(_imp_val)
    # Sensitivity: 0=Normal, 1=Personal, 2=Private, 3=Confidential
    _sens_val = _ole_extract_int(ole, '0036')
    sensitivity = {0: 'Normal', 1: 'Personal', 2: 'Private', 3: 'Confidential'}.get(_sens_val)

    return {
        'subject':            subject,
        'sender':             sender,
        'to':                 to,
        'cc':                 cc,
        'bcc':                bcc,
        'date':               date,
        'date_sent_iso':      date_sent_iso,
        'date_received_iso':  date_received_iso,
        'conversation_topic': conversation_topic,
        'conversation_index': conversation_index,
        'message_id':         message_id,
        'in_reply_to':        in_reply_to,
        'references':         references,
        'importance':         importance,
        'sensitivity':        sensitivity,
    }


def _parse_msg_body(ole, context_label="MSG"):
    """Extract the best available body from an open OLE MSG file.

    Priority chain: HTML (stream 1013) → Compressed RTF de-encapsulation
    (stream 1009) → plain text (stream 1000).

    Returns (html_body_or_None, plain_body_raw).
      - html_body_or_None: HTML string if HTML or RTF-HTML was found, else None.
      - plain_body_raw: raw plain-text string (always populated, used as fallback).
    """
    html_body = None

    # 1. Try HTML directly (Stream 1013)
    raw_html = _ole_extract_binary(ole, '1013')
    if raw_html:
        html_body = raw_html.decode('utf-8', errors='ignore').strip('\x00')

    # 2. Try Compressed RTF (Stream 1009)
    if not html_body:
        raw_rtf = _ole_extract_binary(ole, '1009')
        if raw_rtf and compressed_rtf:
            try:
                c_rtf = compressed_rtf.decompress(raw_rtf)
                rtf_str = c_rtf.decode('cp1252', errors='ignore')
                # Extract all encapsulated HTML blocks
                matches = re.findall(r'\\htmlrtf0 ?(.*?)\\htmlrtf', rtf_str, re.DOTALL | re.IGNORECASE)
                if matches:
                    raw_html_rtf = "".join(matches)
                    # Remove RTF new lines
                    raw_html_rtf = re.sub(r'\\[rn]', '', raw_html_rtf)
                    # Decode the hexadecimal RTF sequences (e.g., \'3c becomes <)
                    html_body = re.sub(r"\'([0-9a-fA-F]{2})", _ole_decode_rtf_hex, raw_html_rtf)

                    html_body = _scrub_rtf_from_html(html_body)
            except Exception as rtf_e:
                logger.warning(f"RTF De-encapsulation failed for {context_label}: {rtf_e}")

    plain_body_raw = _ole_extract_string(ole, '1000') or "No body text available (File may be corrupted)."

    return html_body, plain_body_raw


def _parse_msg_attachments(ole, include_data=True):
    """Extract attachment metadata (and optionally binary data) from an open OLE MSG file.

    Args:
        ole: An open olefile.OleFileIO instance.
        include_data: When True, reads binary data, CID, and MIME type for inline
            image embedding.  When False, only collects filenames (cheaper for
            text-extraction callers that don't need image data).

    Returns a list of dicts, each with keys:
        - name: filename (str or None)
        - content_type: MIME type string (only when include_data=True, else None)
        - is_inline: bool — True when the attachment has a CID and is an image
        - cid: Content-ID string (only when include_data=True and is_inline, else None)
        - data_bytes: raw bytes (only when include_data=True and is_inline, else None)
    """
    attachments = []
    unique_attach_dirs = set(
        d[0] for d in ole.listdir()
        if d and d[0].startswith('__attach_version1.0_#')
    )
    for attach_dir in unique_attach_dirs:
        long_name_stream = f"{attach_dir}/__substg1.0_3707001F"
        short_name_stream = f"{attach_dir}/__substg1.0_3704001F"

        name = None
        if ole.exists(long_name_stream):
            try:
                name_bytes = ole.openstream(long_name_stream).read()
                name = name_bytes.decode('utf-16le', errors='ignore').strip('\x00')
            except Exception as e:
                logger.debug("MSG OLE long-name stream read failed for %s: %s", attach_dir, e)
        if not name and ole.exists(short_name_stream):
            try:
                name_bytes = ole.openstream(short_name_stream).read()
                name = name_bytes.decode('utf-16le', errors='ignore').strip('\x00')
            except Exception as e:
                logger.debug("MSG OLE short-name stream read failed for %s: %s", attach_dir, e)

        if not include_data:
            # Lightweight mode: only filenames needed
            attachments.append({
                'name': name,
                'content_type': None,
                'is_inline': False,
                'cid': None,
                'data_bytes': None,
            })
            continue

        # Full mode: determine inline status, read CID and binary data
        cid_stream = f"{attach_dir}/__substg1.0_3712001F"
        data_stream = f"{attach_dir}/__substg1.0_37010102"
        mime_stream = f"{attach_dir}/__substg1.0_370E001F"

        is_image = name and name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))
        # Fallback: check MIME type stream when filename has no image extension
        if not is_image and ole.exists(mime_stream):
            try:
                mime_bytes = ole.openstream(mime_stream).read()
                mime_val = mime_bytes.decode('utf-16le', errors='ignore').strip('\x00').lower()
                is_image = mime_val.startswith('image/')
            except Exception:
                pass

        if ole.exists(cid_stream) and ole.exists(data_stream) and is_image:
            try:
                cid_bytes = ole.openstream(cid_stream).read()
                cid = cid_bytes.decode('utf-16le', errors='ignore').strip('\x00')

                img_data = ole.openstream(data_stream).read()

                mime_type = "image/png"
                if ole.exists(mime_stream):
                    mime_bytes = ole.openstream(mime_stream).read()
                    mime_type = mime_bytes.decode('utf-16le', errors='ignore').strip('\x00')

                attachments.append({
                    'name': name,
                    'content_type': mime_type,
                    'is_inline': True,
                    'cid': cid,
                    'data_bytes': img_data,
                })
            except Exception as e:
                logger.warning(f"Failed to process inline image {attach_dir}: {e}")
                attachments.append({
                    'name': name,
                    'content_type': None,
                    'is_inline': False,
                    'cid': None,
                    'data_bytes': None,
                })
        else:
            attachments.append({
                'name': name,
                'content_type': None,
                'is_inline': False,
                'cid': None,
                'data_bytes': None,
            })

    return attachments


def convert_msg_to_pdf(msg_path, output_pdf_path):
    """
    Extracts MSG contents natively using olefile and renders to PDF using wkhtmltopdf.
    Limits execution strictly to OLE processing with PyMuPDF as a fallback rendering engine.
    """
    msg_path = str(Path(msg_path).resolve())
    output_pdf_path = str(Path(output_pdf_path).resolve())

    if not olefile:
        return False, "Failed to parse MSG natively: olefile module is missing"

    try:
        import base64

        with olefile.OleFileIO(msg_path) as ole:
            hdrs = _parse_msg_headers(ole)
            html_body, plain_body_raw = _parse_msg_body(ole, context_label=msg_path)
            attach_list = _parse_msg_attachments(ole, include_data=True)

        subject = _html.escape(str(hdrs['subject']))
        sender  = _html.escape(str(hdrs['sender']))
        to      = _html.escape(str(hdrs['to']))
        date    = _html.escape(str(hdrs['date']))
        cc      = _html.escape(str(hdrs['cc']))
        bcc     = _html.escape(str(hdrs['bcc']))

        plain_body_html = _wrap_plain_text_as_html(plain_body_raw)

        # 3. Plain Text Fallback (Stream 1000)
        if not html_body:
            html_body = plain_body_html

        # --- RECONSTRUCT INLINE IMAGES AND ATTACHMENT NAMES FROM PARSED LIST ---
        inline_images = {}
        attachment_names = []
        for att in attach_list:
            if att['is_inline'] and att['data_bytes']:
                b64_img = base64.b64encode(att['data_bytes']).decode('utf-8')
                inline_images[att['cid']] = f"data:{att['content_type']};base64,{b64_img}"
            else:
                if att['name']:
                    attachment_names.append(att['name'])

        if html_body:
            html_body, _ = _substitute_cid_images(html_body, inline_images)

        attachments_html = ""
        if attachment_names:
            attachment_names = list(set(attachment_names))
            attachments_html = f'<div class="header-row"><b>Attachments:</b> {"; ".join(attachment_names)}</div>'

        rendered_html = _build_email_html(sender, date, to, cc, bcc, subject, attachments_html, html_body)

        # Neutralize external image URLs before rendering to prevent dead-link layout cascade
        rendered_html = _neutralize_external_images(rendered_html)

        pdf_generated = _run_wkhtmltopdf(rendered_html, output_pdf_path)

        if not pdf_generated:
            pdf_generated = _render_fitz_story(rendered_html, output_pdf_path)
            if pdf_generated:
                _append_inline_images_to_pdf(output_pdf_path, inline_images)

            if not pdf_generated:
                fallback_html = rendered_html.replace(str(html_body), str(plain_body_html)) if str(html_body) != str(plain_body_html) else rendered_html
                pdf_generated = _render_fitz_story(fallback_html, output_pdf_path)

            if not pdf_generated and fitz:
                doc = fitz.open()
                page = doc.new_page()
                rect = page.rect + (36, 36, -36, -36)
                plain_fallback = f"From: {sender}\nTo: {to}\nDate: {date}\nSubject: {subject}\n\n[HTML Body Could Not Be Rendered]"
                page.insert_textbox(rect, plain_fallback, fontsize=10, fontname="helv", align=0)
                doc.save(output_pdf_path)
                doc.close()
                pdf_generated = True

        if pdf_generated:
            _strip_blank_pages(output_pdf_path)
            return True, None
        else:
            return False, "All HTML to PDF rendering engines failed."

    except Exception as fallback_e:
        return False, f"Failed natively extracting MSG. Fallback Error: {fallback_e}"

def extract_msg_text(msg_path):
    """
    Standalone function to extract plain text from an MSG file for OpenSearch indexing.
    Returns a unified string containing the headers (From, To, Date, Subject) and the body.
    Bypasses GPL libraries by using pure OLE parsing.
    """
    if not olefile:
        return ""

    try:
        with olefile.OleFileIO(msg_path) as ole:
            hdrs = _parse_msg_headers(ole)
            html_body, plain_body_raw = _parse_msg_body(ole, context_label="extract_msg_text")
            attach_list = _parse_msg_attachments(ole, include_data=False)

        subject = hdrs['subject']
        sender  = hdrs['sender']
        to      = hdrs['to']
        cc      = hdrs['cc']
        bcc     = hdrs['bcc']
        date    = hdrs['date']

        body_text = ""
        if html_body:
            import html
            # Strip styling and scripts
            clean_html = re.sub(r'<style[^>]*>.*?</style>', '', html_body, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<script[^>]*>.*?</script>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
            # Convert common breaks to newlines
            clean_html = re.sub(r'<br\s*/?>', '\n', clean_html, flags=re.IGNORECASE)
            clean_html = re.sub(r'</p>', '\n\n', clean_html, flags=re.IGNORECASE)
            clean_html = re.sub(r'<tr[^>]*>', '\n', clean_html, flags=re.IGNORECASE)
            # Remove all other tags
            clean_html = re.sub(r'<[^>]+>', ' ', clean_html)
            body_text = html.unescape(clean_html).strip()
            # Clean up excessive newlines
            body_text = re.sub(r'\n\s*\n', '\n\n', body_text)

        # 3. Plain Text Fallback (Stream 1000) — plain_body_raw comes from _parse_msg_body
        if not body_text:
            # plain_body_raw may contain the sentinel from convert_msg_to_pdf's fallback;
            # treat it as empty if so, matching original extract_msg_text behavior.
            _plain = plain_body_raw.strip() if plain_body_raw else ""
            if _plain and _plain != "No body text available (File may be corrupted).":
                body_text = _plain

        if not body_text:
            body_text = "[No Body Text Available]"
        else:
            body_text = body_text.strip()

        # Extract basic attachment names from parsed list
        attachment_names = [att['name'] for att in attach_list if att['name']]

        attachments_str = ""
        if attachment_names:
            attachment_names = list(set(attachment_names))
            attachments_str = f"Attachments: {'; '.join(attachment_names)}\n"

        # Compile into a flat, searchable document string
        compiled_text = f"From: {sender}\nSent: {date}\nTo: {to}\nCC: {cc}\nSubject: {subject}\n{attachments_str}\n{body_text}"

        msg_meta = {
            'subject':            subject,
            'from':               sender,
            'to':                 to,
            'cc':                 cc or None,
            'bcc':                bcc or None,
            'date_sent':          hdrs['date_sent_iso'],
            'date_received':      hdrs['date_received_iso'],
            'message_id':         hdrs['message_id'],
            'in_reply_to':        hdrs['in_reply_to'],
            'references':         hdrs['references'],
            'conversation_index': hdrs['conversation_index'],
            'conversation_topic': hdrs['conversation_topic'],
            'importance':         hdrs['importance'],
            'sensitivity':        hdrs['sensitivity'],
            'attachment_count':   len(attachment_names),
        }
        return compiled_text, msg_meta

    except Exception as e:
        logger.error(f"Native MSG extraction error: {e}")
        return "", {}


def extract_eml_metadata(eml_path):
    """
    Extract structured metadata and plain text from an EML file using Python's email module.
    Returns (text, metadata_dict) matching the extract_msg_text() signature so the
    Processor can use a single branch for both formats.
    """
    try:
        with open(eml_path, 'rb') as f:
            msg = BytesParser(policy=policy.default).parse(f)

        subject = msg.get('subject', '') or ''
        sender = msg.get('from', '') or ''
        to = msg.get('to', '') or ''
        cc = msg.get('cc', '') or ''
        bcc = msg.get('bcc', '') or ''
        date_str = msg.get('date', '') or ''
        message_id = (msg.get('message-id', '') or '').strip('<>')
        in_reply_to = (msg.get('in-reply-to', '') or '').strip('<>')
        references = msg.get('references', '') or ''
        importance_raw = msg.get('importance') or msg.get('x-priority')
        sensitivity_raw = msg.get('sensitivity')

        # Sanitize date to ISO
        date_iso = None
        if date_str:
            try:
                from dateutil import parser as _dateparser
                date_iso = _dateparser.parse(str(date_str)).isoformat()
            except Exception:
                date_iso = str(date_str)

        # Extract body text and attachment names
        body_parts = []
        attachment_names = []
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            if disp == 'attachment':
                fname = part.get_filename()
                if fname:
                    attachment_names.append(fname)
                continue
            if ctype == 'text/plain' and not disp:
                body_parts.append(part.get_content())

        body_text = '\n'.join(body_parts).strip() or '[No Body Text Available]'
        attachment_names = list(set(attachment_names))
        attachments_str = f"Attachments: {'; '.join(attachment_names)}\n" if attachment_names else ""

        compiled_text = (
            f"From: {sender}\nSent: {date_str}\nTo: {to}"
            + (f"\nCC: {cc}" if cc else "")
            + f"\nSubject: {subject}\n{attachments_str}\n{body_text}"
        )

        eml_meta = {
            'subject':            subject or None,
            'from':               sender or None,
            'to':                 to or None,
            'cc':                 cc or None,
            'bcc':                bcc or None,
            'date_sent':          date_iso,
            'date_received':      None,  # EML doesn't reliably have a separate received timestamp
            'message_id':         message_id or None,
            'in_reply_to':        in_reply_to or None,
            'references':         references or None,
            'conversation_index': None,  # Microsoft-specific, not present in EML
            'conversation_topic': None,
            'importance':         str(importance_raw).strip() if importance_raw else None,
            'sensitivity':        str(sensitivity_raw).strip() if sensitivity_raw else None,
            'attachment_count':   len(attachment_names),
        }
        return compiled_text, eml_meta

    except Exception as e:
        logger.error(f"EML metadata extraction error: {e}")
        return "", {}


def convert_office_to_pdf(source_path, dest_pdf_path):
    """Uses local Office installations to print documents to PDF."""
    ext = os.path.splitext(source_path)[1].lower()
    source_path = os.path.abspath(source_path)
    dest_pdf_path = os.path.abspath(dest_pdf_path)

    try:
        pythoncom.CoInitialize()
        if ext in ['.doc', '.docx']:
            word = win32com.client.Dispatch("Word.Application")
            try:
                word.Visible = False
                doc = word.Documents.Open(source_path)
                doc.ExportAsFixedFormat(dest_pdf_path, 17) # PDF
                doc.Close()
            finally:
                word.Quit()
            return True, None
            
        elif ext in ['.xls', '.xlsx', '.csv']:
            excel = win32com.client.Dispatch("Excel.Application")
            try:
                excel.Visible = False
                wb = excel.Workbooks.Open(source_path)
                wb.ExportAsFixedFormat(0, dest_pdf_path) # PDF
                wb.Close()
            finally:
                excel.Quit()
            return True, None
            
        elif ext in ['.ppt', '.pptx']:
            ppt = win32com.client.Dispatch("PowerPoint.Application")
            try:
                pres = ppt.Presentations.Open(source_path, WithWindow=False)
                pres.ExportAsFixedFormat(dest_pdf_path, 32) # PDF
                pres.Close()
            finally:
                ppt.Quit()
            return True, None
    except Exception as e:
        return False, f"Office COM Exception: {str(e)}"
    finally:
        try: pythoncom.CoUninitialize()
        except Exception as e:
            logger.debug("CoUninitialize cleanup error: %s", e)
    return False, "Unsupported Office Extension"

def convert_image_to_pdf(source_path, dest_pdf_path):
    """Wraps supported image formats directly into a PDF payload."""
    if not fitz:
        return False, "PyMuPDF not installed"
    doc, img, imgPDF = None, None, None
    try:
        doc = fitz.open()
        img = fitz.open(source_path)
        rect = img[0].rect
        pdfbytes = img.convert_to_pdf()
        img.close(); img = None

        imgPDF = fitz.open("pdf", pdfbytes)
        page = doc.new_page(width=rect.width, height=rect.height)
        page.show_pdf_page(rect, imgPDF, 0)

        doc.save(dest_pdf_path)
        return True, None
    except Exception as e:
        return False, f"PyMuPDF Image Exception: {str(e)}"
    finally:
        for _d in (imgPDF, img, doc):
            if _d:
                try: _d.close()
                except Exception as e:
                    logger.debug("fitz close error in convert_image_to_pdf: %s", e)

def convert_text_to_pdf(source_path, dest_pdf_path):
    """Embeds raw text files onto a standard A4 sized PDF page."""
    if not fitz: return False, "PyMuPDF not installed"
    doc = None
    try:
        doc = fitz.open()
        page = doc.new_page()
        with open(source_path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()

        # Simple text insertion (handles basic wrapping)
        page.insert_textbox(page.rect + (36, 36, -36, -36), text, fontsize=11, fontname="helv")
        doc.save(dest_pdf_path)
        return True, None
    except Exception as e:
        return False, f"PyMuPDF Text Exception: {str(e)}"
    finally:
        if doc:
            try: doc.close()
            except Exception as e:
                logger.debug("fitz close error in convert_text_to_pdf: %s", e)

def convert_docx_to_pdf(source_path, dest_pdf_path):
    """
    Converts .docx files to PDF using LibreOffice Headless (Best Accuracy).
    Falls back to a lightweight Python-native parser (mammoth) if LibreOffice is unavailable.
    """
    ext = os.path.splitext(source_path)[1].lower()
    source_path = os.path.abspath(source_path)
    dest_pdf_path = os.path.abspath(dest_pdf_path)
    
    # Try LibreOffice Headless first
    libre_path = getattr(config, 'LIBREOFFICE_PATH', r"C:\Program Files\LibreOffice\program\soffice.exe")
    if os.path.exists(libre_path):
        import subprocess
        _libre_err = None  # Track failure reason
        try:
            cmd = [
                libre_path,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", os.path.dirname(dest_pdf_path),
                source_path
            ]
            # LibreOffice generates a PDF with the same basename but .pdf extension in outdir
            temp_pdf_name = os.path.splitext(os.path.basename(source_path))[0] + ".pdf"
            temp_pdf_path = os.path.join(os.path.dirname(dest_pdf_path), temp_pdf_name)

            # Remove any existing file with that name in the temp dir
            if os.path.exists(temp_pdf_path) and temp_pdf_path != dest_pdf_path:
                try: os.remove(temp_pdf_path)
                except Exception as e:
                    logger.debug("Could not remove temp PDF %s: %s", temp_pdf_path, e)

            res = subprocess.run(cmd, capture_output=True, timeout=60)

            if res.returncode == 0 and os.path.exists(temp_pdf_path):
                import shutil
                if temp_pdf_path != dest_pdf_path:
                    shutil.move(temp_pdf_path, dest_pdf_path)
                return True, None
            else:
                _libre_err = res.stderr.decode('utf-8', errors='ignore').strip() or f"exit code {res.returncode}, no output PDF"
                logger.warning(f"LibreOffice conversion failed for {source_path}: {_libre_err}")
        except subprocess.TimeoutExpired:
            _libre_err = "LibreOffice timed out (60s)"
            logger.warning(f"LibreOffice timeout for {source_path}")
        except Exception as e:
            _libre_err = str(e)
            logger.warning(f"LibreOffice exception for {source_path}: {_libre_err}")

        # LibreOffice was found but failed — for .doc files, no further fallback exists
        if ext != '.docx' and _libre_err:
            return False, f"LibreOffice conversion failed: {_libre_err}"
            
    # Fallback to pure Python 'mammoth' converter (lose some exact layout, but keeps text)
    if ext == '.docx':
        try:
            import mammoth
            with open(source_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html = result.value
            
            if not html.strip():
                html = "No text could be extracted from this Word document."
                
            import html as pyhtml
            safe_html = f"<div style='font-family: sans-serif; padding: 20px;'>{html}</div>"
            
            if not fitz:
                return False, "PyMuPDF not installed, cannot render mammoth HTML layout."
                
            story = fitz.Story(html=safe_html)
            writer = fitz.DocumentWriter(dest_pdf_path)
            rect = fitz.Rect(36, 36, 576, 756)
            
            more = 1
            page_count = 0
            while more and page_count < 200:
                device = writer.begin_page(fitz.Rect(0, 0, 612, 792))
                more, _ = story.place(rect)
                story.draw(device)
                writer.end_page()
                page_count += 1
                
            writer.close()
            return True, None
        except Exception as m_e:
            return False, f"Mammoth Fallback Exception: {str(m_e)}"
            
    return False, f"LibreOffice not found at configured path, and mammoth cannot parse {ext} (only .docx)"

def convert_html_to_pdf(source_path, dest_pdf_path):
    """
    Convert a standalone HTML file to PDF using wkhtmltopdf.
    Falls back to PyMuPDF text-based rendering (stripped HTML) if wkhtmltopdf is unavailable.
    """
    try:
        with open(source_path, 'r', encoding='utf-8', errors='replace') as f:
            html_content = f.read()
    except Exception as e:
        return False, f"Failed to read HTML file: {e}"

    path_wkhtmltopdf = getattr(config, 'WKHTMLTOPDF_PATH', r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
    if os.path.exists(path_wkhtmltopdf):
        try:
            cmd = [path_wkhtmltopdf, '--quiet', '--encoding', 'utf-8',
                   '--enable-local-file-access', source_path, dest_pdf_path]
            res = subprocess.run(cmd, capture_output=True, timeout=30)
            if res.returncode == 0 and os.path.exists(dest_pdf_path):
                return True, None
        except Exception:
            pass  # Fall through to PyMuPDF fallback

    # Fallback: strip tags and render as plain text via PyMuPDF
    try:
        import re as _re
        import tempfile
        text = _re.sub(r'<[^>]+>', ' ', html_content)
        text = ' '.join(text.split())  # collapse whitespace
        if not text.strip():
            text = "(Empty HTML document)"
        # Write stripped text to a temp file and reuse convert_text_to_pdf
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', encoding='utf-8',
                                         delete=False) as tmp:
            tmp.write(text)
            tmp_path = tmp.name
        try:
            return convert_text_to_pdf(tmp_path, dest_pdf_path)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception as fallback_err:
        return False, f"HTML conversion failed: {fallback_err}"


def _com_worker_wrapper(source_path, dest_pdf_path, q):
    """Module-level wrapper so Windows multiprocessing can pickle the target."""
    res = convert_office_to_pdf(source_path, dest_pdf_path)
    q.put(res)

def _detect_pdf_interactivity(doc):
    """
    Checks a PDF document for interactive elements and XFA forms.

    Runs four detection checks against the document catalog:
    1. AcroForm (fillable form fields)
    2. Widget annotations on any page
    3. JavaScript (Names tree, OpenAction, AA)
    4. Embedded file attachments

    Also detects XFA forms (content stored in XML, not page streams).

    Args:
        doc: An open fitz.Document object.

    Returns:
        (needs_flatten: bool, is_xfa: bool)
    """
    needs_flatten = False

    # --- Check 1: AcroForm (fillable form fields) ---
    # The AcroForm dict lives in the PDF catalog (trailer/Root).
    # Its presence means the PDF has or had form fields.
    catalog = doc.pdf_catalog()       # xref of the /Catalog object
    cat_dict = doc.xref_get_key(catalog, "AcroForm")
    if cat_dict[0] != 'null':         # 'null' means key absent
        needs_flatten = True

    # --- Check 2: Widget annotations on any page ---
    # Belt-and-suspenders: some PDFs have orphaned widgets
    # without an AcroForm entry.
    if not needs_flatten:
        for page in doc:
            if list(page.widgets()):
                needs_flatten = True
                break

    # --- Check 3: JavaScript in the document ---
    # JS can live in the Names tree (/JavaScript) or in
    # OpenAction/AA dictionaries. Check the catalog-level keys.
    if not needs_flatten:
        for js_key in ("JavaScript", "JS", "OpenAction", "AA"):
            val = doc.xref_get_key(catalog, js_key)
            if val[0] != 'null':
                needs_flatten = True
                break

    # --- Check 4: Embedded file attachments ---
    # /EmbeddedFiles in the Names dict = attached files.
    if not needs_flatten:
        names_val = doc.xref_get_key(catalog, "Names")
        if names_val[0] != 'null':
            # Resolve the Names dict and check for EmbeddedFiles
            if doc.embfile_count() > 0:
                needs_flatten = True

    # --- Detect XFA before modifying anything ---
    # XFA forms store content in XML, not in page content streams.
    # Stripping AcroForm on an XFA doc destroys the only renderable content.
    # We must rasterize XFA pages instead.
    is_xfa = False
    if cat_dict[0] != 'null':
        try:
            # AcroForm may be an indirect reference ("123 0 R") or inline dict
            acro_ref = cat_dict[1].strip()
            if acro_ref.endswith('R'):
                acro_xref = int(acro_ref.split()[0])
            else:
                acro_xref = catalog
            xfa_val = doc.xref_get_key(acro_xref, "XFA")
            if xfa_val[0] != 'null':
                is_xfa = True
        except Exception:
            pass  # If we can't determine, assume not XFA

    return needs_flatten, is_xfa


def _flatten_xfa_pdf(doc, dest_path):
    """
    Flattens an XFA-form PDF by rasterizing XFA pages and copying normal pages.

    XFA pages have near-empty content streams (~1KB of boilerplate setup
    commands) because the visual content lives in XML. These pages are
    rasterized at 200 DPI. Normal pages in hybrid XFA/standard documents
    are copied as-is to preserve text selectability.

    After building the new document, strips any residual interactive
    elements from copied normal pages and removes document-level
    interactivity entries.

    Uses atomic tempfile + rename pattern for crash safety.

    Args:
        doc: An open fitz.Document with XFA content.
        dest_path: Destination file path for the flattened PDF.

    Returns:
        (True, None) on success, (False, error_msg) on failure.
    """
    logger.info(f"XFA form detected in {os.path.basename(doc.name)}: "
                f"rasterizing XFA pages for litigation safety")

    # Threshold: XFA pages have near-empty content streams (~1KB of
    # boilerplate setup commands). Normal pages have substantially more.
    # 2000 bytes is a safe threshold — even a minimal real page with a
    # single line of text will exceed this.
    # Uses module-level XFA_EMPTY_THRESHOLD constant

    new_doc = fitz.open()  # Build a clean output PDF

    for page_idx in range(len(doc)):
        page = doc.load_page(page_idx)

        # Measure content stream size to determine if page is XFA-rendered
        contents = page.get_contents()
        content_bytes = sum(len(doc.xref_stream(x)) for x in contents)

        if content_bytes < XFA_EMPTY_THRESHOLD:
            # XFA page — rasterize: render to image, insert as new page
            # 200 DPI balances quality vs file size for legal review.
            # (300 DPI is only needed for OCR or TIFF production.)
            pix = page.get_pixmap(dpi=200)
            img_pdf = fitz.open("pdf", pix.pdfocr_tobytes(compress=True, language="eng") if hasattr(pix, 'pdfocr_tobytes') else pix.tobytes("pdf"))
            new_doc.insert_pdf(img_pdf)
            img_pdf.close()
            del pix
        else:
            # Normal page — copy as-is (preserves text selectability)
            new_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)

    # Strip any residual interactive elements from copied normal pages
    for page in new_doc:
        widgets = list(page.widgets())
        for widget in widgets:
            page.delete_widget(widget)
        annots = list(page.annots()) if page.annots() else []
        for annot in annots:
            if annot.type[0] in INTERACTIVE_ANNOT_TYPES:
                page.delete_annot(annot)
        page.clean_contents()

    # Remove document-level interactive entries
    if len(new_doc) > 0:
        new_catalog = new_doc.pdf_catalog()
        for key in ("AcroForm", "JavaScript", "JS", "OpenAction", "AA"):
            try:
                new_doc.xref_set_key(new_catalog, key, "null")
            except Exception:
                pass

    # Save the rebuilt document
    import tempfile
    _flat_fd, _flat_tmp = tempfile.mkstemp(suffix='.pdf',
                                            dir=os.path.dirname(dest_path))
    os.close(_flat_fd)
    try:
        new_doc.save(_flat_tmp, garbage=4, deflate=True, clean=True)
        new_doc.close()
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.replace(_flat_tmp, dest_path)
        return True, None
    except Exception as save_err:
        new_doc.close()
        if os.path.exists(_flat_tmp):
            try:
                os.remove(_flat_tmp)
            except OSError:
                pass
        return False, f"XFA flatten save failed: {save_err}"


def _flatten_acroform_pdf(doc, dest_path):
    """
    Flattens a standard AcroForm PDF by stripping interactive elements.

    Removes widget annotations (form fields), interactive annotation types
    (Link, Screen, RichMedia, 3D, Sound, Movie), document-level JavaScript
    and action entries, and embedded file attachments. Visual appearance of
    form fields is preserved (already baked into page content streams).

    Uses atomic tempfile + rename pattern for crash safety.

    Args:
        doc: An open fitz.Document with AcroForm content.
        dest_path: Destination file path for the flattened PDF.

    Returns:
        (True, None) on success, (False, error_msg) on failure.
    """
    logger.info(f"PDF flatten triggered for {os.path.basename(doc.name)}: "
                f"stripping interactive elements for litigation safety")

    # 1. Remove all widget annotations (form fields) from every page
    #    by baking their current appearance into the page content.
    for page in doc:
        widgets = list(page.widgets())
        for widget in widgets:
            # Widget's appearance stream is already painted into the page.
            # The widget annotation is the interactive overlay — deleting
            # it leaves the visual appearance baked into the page.
            page.delete_widget(widget)

        # Also remove interactive annotation types
        # (Link, Screen, RichMedia, 3D, Sound, Movie)
        annots = list(page.annots()) if page.annots() else []
        for annot in annots:
            atype = annot.type[0]
            # Keep visual-only annotations (text markup, stamps, ink, etc.)
            # but remove interactive ones.
            # Type codes: 1=Link, 15=Sound, 16=Movie, 20=Screen,
            # 24=RichMedia, 25=3D
            if atype in INTERACTIVE_ANNOT_TYPES:
                page.delete_annot(annot)

        page.clean_contents()

    # 2. Remove document-level interactive entries from the catalog
    catalog = doc.pdf_catalog()
    for key in ("AcroForm", "JavaScript", "JS", "OpenAction", "AA"):
        try:
            doc.xref_set_key(catalog, key, "null")
        except Exception:
            pass

    # 3. Remove embedded files
    while doc.embfile_count() > 0:
        try:
            doc.embfile_del(0)
        except Exception:
            break

    # 4. Save with full rewrite to eliminate orphaned objects
    import tempfile
    _flat_fd, _flat_tmp = tempfile.mkstemp(suffix='.pdf',
                                            dir=os.path.dirname(dest_path))
    os.close(_flat_fd)
    try:
        doc.save(
            _flat_tmp,
            garbage=4,      # Remove all unreferenced objects
            deflate=True,   # Recompress for smaller output
            clean=True,     # Rewrite content streams
            encryption=0,   # Strip encryption (already decrypted in memory)
        )
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.replace(_flat_tmp, dest_path)
        return True, None
    except Exception as save_err:
        if os.path.exists(_flat_tmp):
            try:
                os.remove(_flat_tmp)
            except OSError:
                pass
        return False, f"Flatten save failed: {save_err}"


def flatten_pdf(source_path, dest_path):
    """
    Creates a litigation-safe copy of a source PDF by stripping all
    interactive elements (form fields, JavaScript, embedded files,
    multimedia) while preserving text selectability and visual fidelity.

    Handles two types of interactive PDFs:
    - Standard AcroForm: strips widget annotations (visual appearance
      is already baked into page content streams).
    - XFA forms: rasterizes pages whose content lives in XML rather
      than page content streams (e.g., DocuSign, government fillable
      forms). Normal pages in hybrid XFA/standard documents are
      preserved with text selectability intact.

    If the source PDF has no interactive elements, performs a simple
    copy for performance (most litigation PDFs are clean).

    Called during processing (primary) and production (safety belt).

    Returns (True, None) on success, (False, error_msg) on failure.
    """
    if not fitz:
        return False, "PyMuPDF (fitz) is not installed"
    doc = None
    try:
        doc = fitz.open(source_path)

        needs_flatten, is_xfa = _detect_pdf_interactivity(doc)

        if not needs_flatten:
            # Clean PDF — simple copy is safe
            logger.debug(f"PDF clean-copy (no interactive elements): {os.path.basename(source_path)}")
            doc.close(); doc = None
            import shutil
            shutil.copy2(source_path, dest_path)
            return True, None

        if is_xfa:
            result = _flatten_xfa_pdf(doc, dest_path)
            doc.close(); doc = None
            return result
        else:
            result = _flatten_acroform_pdf(doc, dest_path)
            doc.close(); doc = None
            return result

    except Exception as e:
        return False, f"PDF flatten failed: {e}"
    finally:
        if doc:
            try: doc.close()
            except Exception as e:
                logger.debug("fitz close error in flatten_pdf: %s", e)


def image_document(source_path, dest_pdf_path):
    """
    Master router. Takes any supported source file and generates a PDF at dest_pdf_path.
    Returns (True, None) on success, (False, error_msg) on failure.
    """
    ext = os.path.splitext(source_path)[1].lower()

    # EDRM policy gate: refuse to image native-by-policy formats
    if is_native_by_policy(ext):
        return False, f"Native by EDRM policy: {ext} (spreadsheet/tabular data — imaging destroys formulas and structure)"

    # 1. Email COM Automation -> Now completely strictly native Python
    if ext == '.eml':
        return convert_eml_to_pdf(source_path, dest_pdf_path)
    elif ext == '.msg':
        return convert_msg_to_pdf(source_path, dest_pdf_path)
        
    # 2. LibreOffice Integration for Word
    elif ext in ['.doc', '.docx', '.rtf']:
        return convert_docx_to_pdf(source_path, dest_pdf_path)
        
    # 3. Office COM Automation
    elif ext in ['.xls', '.xlsx', '.csv', '.ppt', '.pptx']:
        # Run inside a subprocess to avoid COM Thread Leaks
        import multiprocessing
            
        q = multiprocessing.Queue()
        p = multiprocessing.Process(target=_com_worker_wrapper, args=(source_path, dest_pdf_path, q))
        p.start()
        p.join(timeout=90) # 90 second timeout for complex/large Excel files
        
        if p.is_alive():
            p.terminate()
            p.join()
            return False, "Office COM Timeout (Hung Process or Large File)"
            
        try:
            return q.get_nowait()
        except Exception as e:
            return False, f"Subprocess Error: {str(e)}"
            
    # 3. Native PyMuPDF Wrapping (Images)
    elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff']:
        return convert_image_to_pdf(source_path, dest_pdf_path)
        
    # 4. Native PyMuPDF Wrapping (Text)
    elif ext in ['.txt', '.log']:
        return convert_text_to_pdf(source_path, dest_pdf_path)

    # 4b. HTML files via wkhtmltopdf
    elif ext in ['.htm', '.html']:
        return convert_html_to_pdf(source_path, dest_pdf_path)

    # 5. Flatten and copy existing PDFs (strip form fields, JS, embedded files)
    elif ext == '.pdf':
        return flatten_pdf(source_path, dest_pdf_path)
        
    return False, f"No imaging path for extension: {ext}"

def convert_pdf_to_tiff(pdf_path, output_dir, prefix, start_num):
    """
    Explodes a multi-page PDF into single-page TIFF files for E-Discovery load files.
    Returns: (list_of_metadata_dicts, next_start_num)
    """
    if not fitz or not Image:
        raise Exception("PyMuPDF (fitz) or Pillow (PIL) is not installed.")

    Image.MAX_IMAGE_PIXELS = None  # Safe: trusted case documents, not untrusted web content
    generated = []
    current_num = start_num
    
    doc = None
    try:
        doc = fitz.open(pdf_path)
        # Handle zero-page PDFs safely
        if len(doc) == 0:
            return [], start_num

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=300) # High-res 300 DPI for E-Discovery

            # Ensure we are using direct memory mapping (zero-copy) to avoid FATAL OS Out-Of-Memory crashes
            # PyMuPDF 'pix.tobytes' creates a gargantuan un-garbage-collected PNG buffer in RAM per page.
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

            bates = f"{prefix}-{str(current_num).zfill(8)}"
            tif_filename = f"{bates}.tif"
            tif_path = os.path.join(output_dir, tif_filename)

            # LZW compression gives great quality/size ratio for TIFFs
            img.save(tif_path, format="TIFF", compression="tiff_lzw")
            img.close()

            generated.append({
                'path': tif_path,
                'bates': bates,
                'page': page_num + 1,
                'is_first_page': (page_num == 0),
                'file_ext': '.tif'
            })
            current_num += 1

            # Explicitly free memory to prevent PyMuPDF/PIL from crashing the OS
            del pix
            del img
            page = None
            import gc
            gc.collect()

        return generated, current_num
    except Exception as e:
        logger.error(f"Error exploding PDF to TIFFs {pdf_path}: {e}")
        return [], start_num
    finally:
        if doc:
            try: doc.close()
            except Exception as e:
                logger.debug("fitz close error in explode_pdf_to_tiffs: %s", e)

def generate_slipsheet(output_path, bates_number, filename, file_ext):
    """
    Generates a single-page PDF placeholder (slipsheet) for documents
    produced in native format that could not be imaged.
    """
    if not fitz:
        return False, "PyMuPDF (fitz) is not installed"
    doc = None
    try:
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)  # standard letter

        # Center content vertically
        center_y = 396

        # Title
        title = "DOCUMENT PRODUCED IN NATIVE FORMAT"
        title_width = fitz.get_text_length(title, fontname="helv", fontsize=14)
        page.insert_text(
            fitz.Point((612 - title_width) / 2, center_y - 60),
            title, fontname="helv", fontsize=14, color=(0, 0, 0)
        )

        # Bates number
        bates_label = f"Bates: {bates_number}"
        bates_width = fitz.get_text_length(bates_label, fontname="helv", fontsize=12)
        page.insert_text(
            fitz.Point((612 - bates_width) / 2, center_y),
            bates_label, fontname="helv", fontsize=12, color=(0, 0, 0)
        )

        # Filename
        file_label = f"Filename: {filename}"
        file_width = fitz.get_text_length(file_label, fontname="helv", fontsize=11)
        page.insert_text(
            fitz.Point((612 - file_width) / 2, center_y + 30),
            file_label, fontname="helv", fontsize=11, color=(0.3, 0.3, 0.3)
        )

        # File type
        type_label = f"File Type: {file_ext.upper()}"
        type_width = fitz.get_text_length(type_label, fontname="helv", fontsize=11)
        page.insert_text(
            fitz.Point((612 - type_width) / 2, center_y + 55),
            type_label, fontname="helv", fontsize=11, color=(0.3, 0.3, 0.3)
        )

        doc.save(output_path)
        return True, None
    except Exception as e:
        return False, f"Slipsheet Error: {str(e)}"
    finally:
        if doc:
            try: doc.close()
            except Exception as e:
                logger.debug("fitz close error in generate_slipsheet: %s", e)


def generate_privilege_placeholder(output_path, bates_number, privilege_basis,
                                    control_number=None, endorsement=None):
    """
    Generates a single-page PDF placeholder for a document withheld
    on the basis of privilege. Inserted into the IMAGES folder of a
    production so there are no unexplained Bates gaps.

    Args:
        output_path:     Full path for the output PDF
        bates_number:    The Bates stamp for this placeholder (e.g. "ABC-000042")
        privilege_basis: The asserted basis (e.g. "Attorney-Client Privilege")
        control_number:  Optional internal control number for traceability
        endorsement:     Optional production endorsement text (e.g. "CONFIDENTIAL")

    Returns:
        (success: bool, error: str|None)
    """
    if not fitz:
        return False, "PyMuPDF (fitz) is not installed"
    doc = None
    try:
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)  # US Letter

        center_y = 350

        # Border frame (professional appearance)
        border_rect = fitz.Rect(72, 72, 540, 720)  # 1-inch margins
        page.draw_rect(border_rect, color=(0.6, 0.6, 0.6), width=1.5)

        # Title
        title = "DOCUMENT WITHHELD"
        title_width = fitz.get_text_length(title, fontname="helv", fontsize=16)
        page.insert_text(
            fitz.Point((612 - title_width) / 2, center_y - 80),
            title, fontname="helv", fontsize=16, color=(0.7, 0, 0)
        )

        # Privilege basis
        basis_label = f"Basis: {privilege_basis}"
        basis_width = fitz.get_text_length(basis_label, fontname="helv", fontsize=13)
        page.insert_text(
            fitz.Point((612 - basis_width) / 2, center_y - 30),
            basis_label, fontname="helv", fontsize=13, color=(0, 0, 0)
        )

        # Bates number
        bates_label = f"Bates: {bates_number}"
        bates_width = fitz.get_text_length(bates_label, fontname="helv", fontsize=12)
        page.insert_text(
            fitz.Point((612 - bates_width) / 2, center_y + 10),
            bates_label, fontname="helv", fontsize=12, color=(0, 0, 0)
        )

        # Control number (if provided)
        if control_number:
            cn_label = f"Control: {control_number}"
            cn_width = fitz.get_text_length(cn_label, fontname="helv", fontsize=10)
            page.insert_text(
                fitz.Point((612 - cn_width) / 2, center_y + 40),
                cn_label, fontname="helv", fontsize=10, color=(0.4, 0.4, 0.4)
            )

        # Endorsement (if provided, e.g. "CONFIDENTIAL")
        if endorsement:
            end_width = fitz.get_text_length(endorsement, fontname="helv", fontsize=10)
            page.insert_text(
                fitz.Point((612 - end_width) / 2, 700),
                endorsement, fontname="helv", fontsize=10, color=(0.5, 0.5, 0.5)
            )

        doc.save(output_path)
        return True, None
    except Exception as e:
        return False, f"Privilege Placeholder Error: {str(e)}"
    finally:
        if doc:
            try: doc.close()
            except Exception as e:
                logger.debug("fitz close error in generate_privilege_placeholder: %s", e)


def stamp_bates_on_pdf(pdf_path, prefix, start_num, position="bottom-left", font_size=12, endorsement=None, color="black", padding=6):
    """
    Burns Bates numbers onto each page of a PDF in-place.
    Page 1 gets start_num, page 2 gets start_num+1, etc.
    Returns (True, None) on success, (False, error_msg) on failure.
    """
    if not fitz:
        return False, "PyMuPDF (fitz) is not installed"
    doc = None
    try:
        doc = fitz.open(pdf_path)
        # If fitz had to repair the PDF on open, the Document object may be
        # invalid for incremental operations. Force a full rewrite to normalize.
        if doc.is_repaired:
            import tempfile
            _norm_dir = os.path.dirname(pdf_path)
            _norm_fd, _norm_tmp = tempfile.mkstemp(suffix='.pdf', dir=_norm_dir)
            os.close(_norm_fd)
            try:
                doc.save(_norm_tmp, garbage=0, deflate=True)
                doc.close()
                os.replace(_norm_tmp, pdf_path)
                doc = fitz.open(pdf_path)  # re-open the clean copy
            except Exception:
                doc.close()
                if os.path.exists(_norm_tmp):
                    try:
                        os.remove(_norm_tmp)
                    except Exception:
                        pass
                # Fall through — attempt stamping on the original anyway
                doc = fitz.open(pdf_path)
        if len(doc) == 0:
            doc.close(); doc = None
            return True, None

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            bates_text = f"{prefix}-{str(start_num + page_num).zfill(padding)}"

            # Measure text width for precise positioning
            text_width = fitz.get_text_length(bates_text, fontname="helv", fontsize=font_size)
            text_height = font_size + 2
            margin = 36  # standard margin in points
            bg_padding = 4  # padding around text inside background rect

            page_rect = page.rect  # rotation-aware visual dimensions
            rot = page.rotation    # 0, 90, 180, or 270

            # ── Calculate desired position in VISUAL coordinate space ──
            if position == "bottom-left":
                vis_x = margin
            elif position == "bottom-right":
                vis_x = page_rect.width - margin - text_width
            else:  # bottom-center
                vis_x = (page_rect.width - text_width) / 2
            vis_y = page_rect.height - margin

            # ── Transform to raw content-stream coordinates if page is rotated ──
            if rot != 0:
                derot = page.derotation_matrix
                # Transform Bates stamp position
                raw_point = fitz.Point(vis_x, vis_y) * derot
                # Transform background rect corners
                raw_bg_tl = fitz.Point(
                    vis_x - bg_padding,
                    vis_y - text_height - bg_padding
                ) * derot
                raw_bg_br = fitz.Point(
                    vis_x + text_width + bg_padding,
                    vis_y + bg_padding
                ) * derot
                bg_rect = fitz.Rect(raw_bg_tl, raw_bg_br)
                bg_rect.normalize()  # ensure x0<x1, y0<y1 after rotation
                ins_point = raw_point
                text_rotate = rot
            else:
                ins_point = fitz.Point(vis_x, vis_y)
                bg_rect = fitz.Rect(
                    vis_x - bg_padding,
                    vis_y - text_height - bg_padding,
                    vis_x + text_width + bg_padding,
                    vis_y + bg_padding
                )
                text_rotate = 0

            # ── Draw semi-opaque white background rectangle ──
            shape = page.new_shape()
            shape.draw_rect(bg_rect)
            shape.finish(color=None, fill=(1, 1, 1), fill_opacity=0.85)
            shape.commit()

            # Determine RGB color
            rgb_color = (1, 0, 0) if color and color.lower() == "red" else (0, 0, 0)

            # ── Draw Bates number text ──
            page.insert_text(
                ins_point,
                bates_text,
                fontname="helv",
                fontsize=font_size,
                color=rgb_color,
                rotate=text_rotate,
            )

            # ── Confidentiality endorsement at top-center (if specified) ──
            if endorsement and endorsement.strip():
                endorse_text = endorsement.strip()
                endorse_size = font_size
                endorse_width = fitz.get_text_length(endorse_text, fontname="helv", fontsize=endorse_size)
                endorse_vis_x = (page_rect.width - endorse_width) / 2
                endorse_vis_y = margin  # near top of page in visual space

                if rot != 0:
                    raw_endorse_point = fitz.Point(endorse_vis_x, endorse_vis_y) * derot
                    raw_endorse_bg_tl = fitz.Point(
                        endorse_vis_x - bg_padding,
                        endorse_vis_y - endorse_size - bg_padding
                    ) * derot
                    raw_endorse_bg_br = fitz.Point(
                        endorse_vis_x + endorse_width + bg_padding,
                        endorse_vis_y + bg_padding
                    ) * derot
                    endorse_bg_rect = fitz.Rect(raw_endorse_bg_tl, raw_endorse_bg_br)
                    endorse_bg_rect.normalize()
                    endorse_ins_point = raw_endorse_point
                    endorse_rotate = rot
                else:
                    endorse_ins_point = fitz.Point(endorse_vis_x, endorse_vis_y)
                    endorse_bg_rect = fitz.Rect(
                        endorse_vis_x - bg_padding,
                        endorse_vis_y - endorse_size - bg_padding,
                        endorse_vis_x + endorse_width + bg_padding,
                        endorse_vis_y + bg_padding
                    )
                    endorse_rotate = 0

                endorse_shape = page.new_shape()
                endorse_shape.draw_rect(endorse_bg_rect)
                endorse_shape.finish(color=None, fill=(1, 1, 1), fill_opacity=0.85)
                endorse_shape.commit()

                page.insert_text(
                    endorse_ins_point,
                    endorse_text,
                    fontname="helv",
                    fontsize=endorse_size,
                    color=rgb_color,
                    rotate=endorse_rotate,
                )

        # Always use full rewrite for production PDFs.
        # Incremental saves preserve the original object tree, which can
        # retain interactive elements (form fields, JS) that should not
        # survive production. Full rewrite with garbage collection ensures
        # only referenced objects appear in the output.
        import tempfile
        _stamp_dir = os.path.dirname(pdf_path)
        _stamp_fd, _stamp_tmp = tempfile.mkstemp(suffix='.pdf', dir=_stamp_dir)
        os.close(_stamp_fd)
        try:
            doc.save(_stamp_tmp, garbage=4, deflate=True, clean=True)
            doc.close(); doc = None
            os.replace(_stamp_tmp, pdf_path)
        except Exception as _save_err:
            if doc: doc.close(); doc = None
            if os.path.exists(_stamp_tmp):
                try:
                    os.remove(_stamp_tmp)
                except OSError:
                    pass
            return False, f"Bates stamp save failed: {_save_err}"

        return True, None
    except Exception as e:
        return False, f"Bates Stamp Error: {str(e)}"
    finally:
        if doc:
            try: doc.close()
            except Exception as e:
                logger.debug("fitz close error in stamp_bates_on_pdf: %s", e)


def get_pdf_page_count(pdf_path):
    """Safely retrieves the number of pages in a PDF."""
    if not fitz: return 1
    try:
        with fitz.open(pdf_path) as doc:
            count = len(doc)
            return max(count, 1)
    except Exception as e:
        logger.debug("get_pdf_page_count failed for %s: %s", pdf_path, e)
        return 1


def image_document_safe(source_path, dest_pdf_path, control_number):
    """
    Standalone imaging wrapper for two-pass production.
    Returns a dict with imaging results — no SQLite, no OpenSearch, no Streamlit access.
    Designed to be picklable for future ProcessPoolExecutor use (Sprint 3).
    """
    try:
        success, error_msg = image_document(source_path, dest_pdf_path)
        page_count = get_pdf_page_count(dest_pdf_path) if success else 1
        return {
            'control_number': control_number,
            'success': success,
            'error_msg': error_msg or '',
            'page_count': page_count,
        }
    except Exception as e:
        return {
            'control_number': control_number,
            'success': False,
            'error_msg': f"Worker exception: {e}",
            'page_count': 1,
        }
