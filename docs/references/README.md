# docs/references — Dependency API References

Curated API references for third-party libraries where this project has been
bitten by incorrect attribute names, masked types, or undocumented behaviors.
Each file covers one dependency and is consulted **before** writing or
modifying code that touches that system.

## What belongs here

- Curated API summaries for a dependency (PyMuPDF, libpff, Outlook COM,
  Apache Tika, OpenSearch, Python `email` MIME).
- "Known Gotchas" sections distilled from real defects in this codebase.
- Method/attribute tables with the exact names that work vs. the ones that
  look correct but silently fail.
- Short code recipes for the canonical safe pattern.

## What does NOT belong here

- Durable project-level lessons that are not library-specific — those live
  in `docs/lessons/`.
- Reusable workflow templates (preflight structure, defect-triage format) —
  those live in `docs/templates/`.
- Sprint-specific preflight/audit documents — those live in `docs/audits/`.
- Completed specs or sprint docs — those live in `docs/archive/`.

## How to add a reference

1. One file per dependency, named `<NAME>_REFERENCE.md` or `<NAME>_PATTERNS.md`.
2. Lead with a one-line purpose statement and a table of contents.
3. Include a "Known Gotchas" section that names the failure mode, not just
   the fix.
4. Add a row to the Dependency API References table in `CLAUDE.md` so the
   reference is discoverable on every turn.
5. Update the file index below.

## Current references

- [EMAIL_MIME_REFERENCE.md](EMAIL_MIME_REFERENCE.md) — Python `email`
  module, MIME parsing, `get_filename()` behaviors, synthesized EML
  construction.
- [LIBPFF_API_REFERENCE.md](LIBPFF_API_REFERENCE.md) — `pypff` objects:
  file, folder, message, attachment attributes and methods.
- [OPENSEARCH_PATTERNS.md](OPENSEARCH_PATTERNS.md) — Index schema,
  `_source` field names, query DSL patterns, `.keyword` suffix rules.
- [OUTLOOK_COM_REFERENCE.md](OUTLOOK_COM_REFERENCE.md) — `win32com` /
  Outlook MAPI COM, attachment types, property tags, threading rules.
- [PYMUPDF_PATTERNS.md](PYMUPDF_PATTERNS.md) — PyMuPDF (`fitz`): text
  extraction, redaction annotations, Story API, pixmap rendering.
- [TIKA_METADATA_KEYS.md](TIKA_METADATA_KEYS.md) — Apache Tika
  metadata key names and fallback chains by file format.

## See also

- `CLAUDE.md` — Dependency API References table (pointer entrypoint).
- `docs/lessons/` — durable project-level patterns (not library-specific).
- `docs/templates/` — reusable workflow templates.
