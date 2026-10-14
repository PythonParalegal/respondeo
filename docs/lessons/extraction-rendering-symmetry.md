# Lesson — Extraction-Rendering Symmetry

**Canonized:** beta-2.15 Commit 5 (2026-05-18)
**Trigger:** the maintainer re-ingested a test case after Commit 4's family-model fix and observed that DOC-000123 (an .eml with 2 visible attachments) had NO family members in the Review grid. Direct test confirmed `_explode_eml` returned 0 children for the file. Case-wide impact: ~1k .eml files, all with `attachment_count > 0`, all with zero child rows.

## The Principle

**When two code paths classify the same thing, they must use the same predicate.**

In an eDiscovery pipeline, every MIME part inside an email is either:
- An **attachment** — extracted as a separate child document, listed in the rendered email's "Attachments" header, indexed independently for search, separately Bates-stamped during production.
- **Inline content** — rendered AS PART OF the parent email's PDF body, NOT extracted as a child.

These are mutually exclusive. A part cannot be both. If the extraction side and the rendering side disagree about which a given part is, the result is silent data loss (extraction-side says "inline" + rendering-side says "attachment" → vanishes from both) or duplication (extraction-side says "attachment" + rendering-side says "inline" → present as both a child doc AND embedded in the parent PDF).

## The Pattern That Caused the Bug

Pre-Commit-5, the extraction path (`_explode_eml`) and the rendering path (`universal_imager.convert_eml_to_pdf`) each independently used `part.get('Content-ID') is not None` as the "is this inline?" test. The comment in `_explode_eml` justified this as defending against iPhone Mail clients that set `Content-Disposition: attachment` on inline images.

But libpff (the PST extraction library) stamps a `Content-ID` header on EVERY attachment it extracts from a PST, because MAPI internally assigns identifiers to all attachments. Under the original rule, every libpff-extracted attachment looked "inline" — Office documents, PDFs, even non-image binaries — and was silently dropped by both code paths. The rendering side's `_append_inline_images_to_pdf` fallback then tried to render the `.docx` bytes via PyMuPDF's image API, silently failed, and the attachment vanished entirely from the system.

The defect was invisible until Commit 4 made families email-rooted: under the pre-Commit-4 PST-as-family model, every email-and-its-attachments was lumped into "one PST family," so the absence of child rows was masked. After Commit 4, the missing children stood out — the maintainer's first PST re-ingest exposed both the family-model correctness AND the upstream extraction defect.

## The Fix (Commit 5)

Single shared predicate in `container_exploder.py`:

```python
def is_part_inline_image(part, html_cids, html_filenames):
    if part.get_content_maintype() != 'image':
        return False  # non-images are never inline
    cid = part.get('Content-ID')
    if cid and cid.strip('<>') in html_cids:
        return True  # CID referenced from <img src="cid:..."> in HTML body
    fname = part.get_filename() or ''
    if fname and fname.lower() in html_filenames:
        return True  # filename referenced from <img src="..."> in HTML body
    return False  # everything else is an attachment
```

Both `_explode_eml` (extraction) and `universal_imager.convert_eml_to_pdf` (rendering) call this single function. They cannot disagree, because they share the same logic literally.

The HTML body pre-scan in `_collect_html_inline_refs` (renamed from `_collect_html_referenced_images` in Commit 5) returns BOTH filename-referenced inlines AND CID-referenced inlines as a NamedTuple. Both code paths consume the same NamedTuple.

## The Broader Principle: Pinned-Value Pattern

This is an instance of the **pinned-value pattern** (see also `feedback_pinned_value_pattern.md` in auto-memory): "when two places must agree on a rule (SQL fragment, predicate, format), use single helper + pinned-value test with `is` identity check."

The fix's tests assert via the predicate function itself, not by duplicating the logic. Future changes to the inline-classification rule update one function; the symmetry is automatic.

## Diagnostic Signal

If you observe an email document with `attachment_count > 0` and zero child rows in the documents table, this is the signature. Check:

```sql
SELECT d.control_number, d.file_name, d.attachment_count,
       (SELECT COUNT(*) FROM documents c
        WHERE c.parent_id = 'DOC-' || printf('%06d', d.id)) AS actual_children
FROM documents d
WHERE d.attachment_count > 0
  AND d.file_extension = '.eml'
LIMIT 20;
```

`actual_children = 0` while `attachment_count > 0` indicates extraction silently dropped the attachments. Pre-Commit-5 this was case-wide for any libpff-extracted PST. Post-Commit-5, this should be effectively zero.

## Related Lessons

- `docs/lessons/container-family-model.md` (Commit 4) — the family-rooting fix that exposed this defect.
- `feedback_pinned_value_pattern.md` (auto-memory) — the broader pattern.
- `docs/references/EMAIL_MIME_REFERENCE.md` — Known Gotchas section now lists libpff's CID-stamping behavior.

## Known Coverage Gap

The `.msg` path (Outlook COM) uses MAPI properties (`PR_ATTACH_FLAGS`, `PR_ATTACHMENT_HIDDEN`) rather than Content-ID for inline detection. It does NOT share this defect. If `.msg` extraction is ever rewritten to go through Python's `email` module, the shared predicate must apply there too. Tracked in `docs/FLAG_REGISTRY.md` Flag #27 as a coverage note.
