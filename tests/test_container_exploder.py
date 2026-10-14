"""
test_container_exploder.py — regression tests for the EML inline-image
predicate added in beta-2.15 Commit 5.

Pinned-value tests for is_part_inline_image() and the revised _explode_eml()
classification rule:

  - Email containers (.eml/.msg) DEFINE families — their inline images
    (referenced from HTML body via CID or filename) are NOT extracted as
    children (they render inline in the parent email PDF).
  - Real attachments (everything else with Content-Disposition: attachment,
    including libpff-CID-stamped Office/PDF docs) ARE extracted as children.

The pre-Commit-5 over-skip rule (`if part.get('Content-ID'): continue`)
silently dropped every libpff-extracted PST attachment because libpff
stamps Content-ID on every attachment regardless of inline status.

See docs/lessons/extraction-rendering-symmetry.md for the full pattern.
"""
import pytest
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

import container_exploder
from container_exploder import is_part_inline_image, _explode_eml


# ---------------------------------------------------------------------------
# Helpers for building MIME parts in-memory
# ---------------------------------------------------------------------------

def _make_office_attachment(filename='report.docx', cid='<libpff-stamp@pst>'):
    """A .docx attachment with a libpff-stamped Content-ID (the bug case)."""
    part = MIMEApplication(
        b'fake docx bytes', _subtype='vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    if cid is not None:
        part.add_header('Content-ID', cid)
    part.add_header('Content-Disposition', 'attachment', filename=filename)
    return part


def _make_inline_image(filename='logo.png', cid='<logo@example>'):
    """An image part with a CID and disposition='inline'."""
    part = MIMEImage(b'\x89PNG\r\n\x1a\nfake-png', _subtype='png')
    if cid is not None:
        part.add_header('Content-ID', cid)
    part.add_header('Content-Disposition', 'inline', filename=filename)
    return part


def _build_eml(tmp_path, *, html_body, attachments, filename='test.eml'):
    """Build a multipart/mixed .eml on disk and return its path."""
    msg = MIMEMultipart('mixed')
    msg['Subject'] = 'pytest fixture'
    msg['From'] = 'sender@example.com'
    msg['To'] = 'recipient@example.com'
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    for att in attachments:
        msg.attach(att)
    eml_path = tmp_path / filename
    eml_path.write_bytes(msg.as_bytes())
    return eml_path


# ---------------------------------------------------------------------------
# Predicate unit tests (no .eml file required)
# ---------------------------------------------------------------------------

def test_is_part_inline_image_libpff_attachment_returns_false():
    """A non-image attachment (.docx) with a libpff-stamped Content-ID and
    no HTML body reference must be classified as real attachment (False).
    This is the headline regression-pin for the over-skip bug."""
    part = _make_office_attachment()
    assert is_part_inline_image(part, html_cids=set(), html_filenames=set()) is False


def test_is_part_inline_image_referenced_cid_returns_true():
    """An image part with Content-ID and a matching HTML <img src="cid:...">
    reference is truly inline → predicate returns True (skip extraction)."""
    part = _make_inline_image(cid='<logo@example>')
    assert is_part_inline_image(
        part, html_cids={'logo@example'}, html_filenames=set()
    ) is True


def test_is_part_inline_image_filename_referenced_returns_true():
    """An image part referenced by filename in <img src="signature.png"> is
    truly inline → predicate returns True (substituted into HTML body)."""
    part = _make_inline_image(filename='signature.png', cid=None)
    assert is_part_inline_image(
        part, html_cids=set(), html_filenames={'signature.png'}
    ) is True


def test_is_part_inline_image_unreferenced_image_returns_false():
    """An image part with a Content-ID that is NOT referenced from the HTML
    body (and whose filename is also not referenced) is a real attachment
    even though it has a Content-ID. Defends against libpff-style stamping
    that incorrectly attaches CIDs to non-inline images."""
    part = _make_inline_image(cid='<orphan@x>')
    assert is_part_inline_image(part, html_cids=set(), html_filenames=set()) is False


# ---------------------------------------------------------------------------
# End-to-end _explode_eml tests (require .eml on disk + output_dir)
# ---------------------------------------------------------------------------

def test_explode_eml_libpff_pst_produces_children(tmp_path):
    """A synthetic libpff-style .eml with 2 Office attachments (CID-stamped,
    no HTML CID refs) must yield 2 child tuples. Pre-Commit-5 this returned 0
    because the broad Content-ID skip dropped both. This is the case-wide
    regression the maintainer observed across ~1k .eml files in a test case."""
    output_dir = tmp_path / 'out'
    output_dir.mkdir()
    eml_path = _build_eml(
        tmp_path,
        html_body='<html><body>Email body with no inline images.</body></html>',
        attachments=[
            _make_office_attachment(filename='report.docx', cid='<libpff-doc-1@pst>'),
            _make_office_attachment(filename='data.xlsx', cid='<libpff-doc-2@pst>'),
        ],
    )

    result = _explode_eml(str(eml_path), str(output_dir))

    assert len(result) == 2, f"Expected 2 children, got {len(result)}: {result}"
    filenames = {tup[0] for tup in result}
    assert 'report.docx' in filenames
    assert 'data.xlsx' in filenames


def test_explode_eml_true_inline_image_skipped(tmp_path):
    """A .eml with one true inline image (CID + HTML CID ref) and one real
    attachment (.docx with libpff-stamp CID) must yield exactly 1 child:
    the .docx. The inline image stays inline (substituted by universal_imager
    via _substitute_cid_images, not extracted as a child)."""
    output_dir = tmp_path / 'out'
    output_dir.mkdir()
    eml_path = _build_eml(
        tmp_path,
        html_body=(
            '<html><body>'
            'Company logo: <img src="cid:logo@example">'
            '</body></html>'
        ),
        attachments=[
            _make_inline_image(filename='logo.png', cid='<logo@example>'),
            _make_office_attachment(filename='report.docx', cid='<libpff-doc@x>'),
        ],
    )

    result = _explode_eml(str(eml_path), str(output_dir))

    assert len(result) == 1, f"Expected 1 child (real attachment only), got {len(result)}: {result}"
    assert result[0][0] == 'report.docx', (
        f"Expected the .docx attachment to be the only child; "
        f"got {result[0][0]!r} instead"
    )
