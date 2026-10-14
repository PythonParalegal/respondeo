# Lesson — Container Family Model

**Canonized:** beta-2.15 Commit 4 (2026-05-15)
**Trigger:** the maintainer discovered a ~500-doc PST exported as a single ~500-page PDF via Review's "Combine families" toggle. Investigation revealed every document extracted from the PST shared the PST's `group_id`, collapsing the whole archive into one family.

## The Principle

**Containers don't make families; emails do.**

A family in eDiscovery is a parent email and its direct attachments. Archive containers (`.pst`, `.zip`, etc.) are file-system-like collections, not families — they hold documents that may have no relationship to each other beyond co-residence in the same archive. Treating a container as a family root produces nonsense groupings: a PST with 500 unrelated emails becomes one 500-document "family."

## The Pattern That Caused the Bug

Prior to Commit 4, `processing_engine.add_children_to_db` propagated `group_id` from any container to its children:

```python
group_id = parent_row['group_id'] or parent_id_str
# ... child gets parent's group_id ...
```

Combined with the multi-pass extraction in `processing_engine.scan_for_containers`, this meant:

1. PST is the top-level parent: `group_id = PST's DOC-id form`.
2. Each extracted email becomes a child of the PST: inherits PST's `group_id`.
3. Each email's attachments become children of the email: inherits email's `group_id` (which is still the PST's).
4. Cascades all the way down — every descendant of the PST shares one group_id.

Three downstream surfaces cascaded the same conflation:

- **PDF export** (`pdf_exporter.export_pdfs_to_zip` with `combine_families=True`) groups by `group_id` and merges each group into one PDF. With a single PST-rooted family, every doc merged into one PDF.
- **Production family-sort** (`pages/5_Production.py` `_walk_family_root`) walked `parent_id` to the topmost ancestor — for PST extractions, always the PST itself.
- **Review family-expansion** (`pages/4_Review.py` `_expand_to_families`) read `group_id` and unioned in every row sharing it — for PST extractions, the whole PST.

## The Fix (Commit 4)

Two-part change in `processing_engine.add_children_to_db`:

1. **Classification.** Two container kinds:
   - **Email containers** (`.eml`, `.msg`) — define families. Their direct children inherit the email's `group_id`.
   - **Archive containers** (`.pst`, `.zip`) — do not define families on their own. When at top-of-family, their direct children each start a new family rooted at themselves.

2. **Top-of-family detection.** A container is "at top of its family" iff its `group_id` is NULL/empty OR equals its own `DOC-{id:06d}` form. The NULL-handling matters because at extraction time, `Ingestor` has not yet assigned a `control_number` and the `db_manager.py` group_id migration is a no-op for unprocessed rows.

The detection rule cleanly handles three corner cases:
- **PST nested in ZIP:** PST gets its own `DOC-id` form from the ZIP-as-top-level-archive path. When PST's children are extracted, PST's `group_id == its parent_id_str` → detected as "top-of-its-family" → emails each start a new family. Correct.
- **ZIP attached to email:** ZIP inherits email's `group_id` (because email is not an archive). When ZIP's contents are extracted, ZIP's `group_id != ZIP's parent_id_str` → detected as "nested in email family" → contents inherit email's `group_id`. Correct.
- **Loose ZIP in PST:** ZIP gets its own `DOC-id` form (PST is top-level archive). When ZIP's contents are extracted, ZIP's `group_id == ZIP's parent_id_str` → contents each start a new family. Correct.

Consumer fix in `pages/5_Production.py`: `_walk_family_root` is deleted; all four call sites read `group_id` directly. The function was walking `parent_id` to find a family root — under the new model, `group_id` already encodes the answer.

## Migration of Existing Cases

`group_id` is persisted at extraction time. Re-running processing on an existing case does NOT recompute `group_id` — the processing-stage UPDATE only fills NULL values. To get email-level families on a case ingested before Commit 4:

- **(a, recommended):** Full delete + re-ingest from raw container source. Loses any manual coding (tags, redactions, privilege calls) on the case.
- **(b, deferred):** One-off SQL migration script that walks the documents table top-down and recomputes `group_id` per the new rule. ~50-80 LOC + edge-case handling. Not authored as of Commit 4 — defer until an existing case requires it.

## Known Coverage Gap

`ARCHIVE_EXTS = frozenset({'.pst', '.zip'})` covers only the archive types `container_exploder` currently supports. If `.rar`, `.7z`, `.tar`, `.gz`, or `.mbox` is ever added to the container pipeline, the set must be extended in the same commit — otherwise the new type re-introduces the mega-family bug for itself. Tracked as Flag #26 in `docs/FLAG_REGISTRY.md`.

## Related Lessons

- `docs/lessons/family-integrity-over-dedup.md` — the broader family-integrity principle this fix reinforces (families must be preserved across dedup and threading; this lesson is its cousin at the ingestion layer).
