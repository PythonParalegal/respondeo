"""
pdf_exporter.py — Mass PDF Export Utility
==========================================
Packages selected documents from the Review module into a ZIP archive of PDFs.
Called from 4_Review.py's bulk action bar (Manager+ only).

File source options:
  "processed" — Processed/{control_number}.pdf  (imaged during processing)
  "native"    — Processed/{control_number}{ext}  (original native file)
  "produced"  — Productions/{volume}/IMAGES/{begdoc}.pdf  (Bates-stamped production copy)

Follows the same module pattern as universal_imager.py and container_exploder.py:
heavy lifting here, UI stays in the page file.
"""

# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        pdf_exporter.py
# version:       1.3.2
# project:       Respondeo eDiscovery Platform
# project_ver:   2.9.0
# last_modified: 2026-03-27 01:40
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────

import io
import json
import logging
import os
import zipfile

import fitz  # PyMuPDF

import re
import db_manager

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────
FILENAME_MAX_LENGTH = 200           # Truncation limit for sanitized ZIP entry names


# ---------------------------------------------------------------------------
# Bates number helpers
# ---------------------------------------------------------------------------

def _bates_number_sort_key(bates_str):
    """Extract numeric suffix from Bates number for correct ordering.
    Handles formats like 'PREFIX-000123', 'AB_001', etc."""
    if not bates_str:
        return ("", 0)
    m = re.search(r'(\d+)$', bates_str)
    if m:
        prefix = bates_str[:m.start()]
        return (prefix, int(m.group(1)))
    return (bates_str, 0)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_source_path(row, case_folder: str, file_source: str) -> tuple:
    """
    Return (path, reason) for the document file based on selected source.
    path   — filesystem path to use; may point to a non-existent file (caller checks).
    reason — human-readable error string when path is None (unresolvable); else None.

    Native path search order:
      1. Processed/{cn}{ext}  — natives are relocated here during processing
      2. Ingest/{file_name}   — fallback for files that were never processed
    """
    cn = row["control_number"]

    if file_source == "processed":
        return os.path.join(case_folder, "Processed", f"{cn}.pdf"), None

    elif file_source == "native":
        ext = row["file_extension"] or ""
        native_path = os.path.join(case_folder, "Processed", f"{cn}{ext}")
        if os.path.exists(native_path):
            return native_path, None
        ingest_path = os.path.join(case_folder, "Ingest", row["file_name"] or "")
        if os.path.exists(ingest_path):
            return ingest_path, None
        return None, "native file missing — not found in Processed/ or Ingest/"

    elif file_source == "produced":
        begdoc = row["begdoc"]
        if not begdoc:
            return None, "document has not been produced (no Bates number assigned)"

        # Check production_volume field first (populated for productions run after this fix)
        _row_keys = row.keys() if hasattr(row, 'keys') else []
        prod_vol = row["production_volume"] if "production_volume" in _row_keys else None
        if prod_vol:
            direct_path = os.path.join(case_folder, "Productions", prod_vol, "IMAGES", f"{begdoc}.pdf")
            if os.path.exists(direct_path):
                return direct_path, None

        # Fallback: scan all production volume folders (covers legacy data without production_volume)
        productions_dir = os.path.join(case_folder, "Productions")
        if os.path.isdir(productions_dir):
            for vol_name in os.listdir(productions_dir):
                candidate = os.path.join(productions_dir, vol_name, "IMAGES", f"{begdoc}.pdf")
                if os.path.exists(candidate):
                    return candidate, None

        return None, f"produced PDF not found ({begdoc}.pdf) — not in any Productions volume"

    return None, f"unknown file source: {file_source}"


def _file_not_found_msg(file_source: str, path: str) -> str:
    """Human-readable error when a resolved path does not exist on disk."""
    if file_source == "processed":
        return "processed PDF not found — document may not have been processed yet"
    if file_source == "produced":
        fname = os.path.basename(path)
        return f"produced PDF not found ({fname}) — not found in any Productions volume"
    return f"file not found: {path}"


# ---------------------------------------------------------------------------
# Filename construction
# ---------------------------------------------------------------------------

def _build_zip_filename(row, naming_field: str, append_extension: bool,
                        seq_num: int, prefix_sequential: bool) -> str:
    """
    Construct the filename that will appear inside the ZIP archive.
    Falls back to control_number if the chosen naming field is empty.
    Always ends with .pdf.

    Special naming_field values:
      "begdoc_range" — "{begdoc} - {enddoc}" when enddoc differs; else just begdoc.
      "meta:<KEY>"   — parsed from the document's dynamic_metadata JSON.
    """
    if naming_field == "begdoc_range":
        begdoc = row["begdoc"] or ""
        enddoc = row["enddoc"] or ""
        if enddoc and enddoc != begdoc:
            raw_value = f"{begdoc} - {enddoc}"
        else:
            raw_value = begdoc
        if not raw_value:
            raw_value = row["control_number"]
    elif naming_field.startswith("meta:"):
        meta_key = naming_field[5:]
        try:
            meta_dict = json.loads(row["dynamic_metadata"] or "{}")
            raw_value = meta_dict.get(meta_key) or row["control_number"]
        except (json.JSONDecodeError, TypeError):
            raw_value = row["control_number"]
    else:
        raw_value = row[naming_field] if row[naming_field] else row["control_number"]
    safe_name = "".join(
        c if c.isalnum() or c in (' ', '-', '_', '.') else '_'
        for c in str(raw_value)
    ).strip()[:FILENAME_MAX_LENGTH]

    if not safe_name:
        safe_name = row["control_number"]

    if prefix_sequential:
        safe_name = f"{seq_num:04d}_{safe_name}"

    if append_extension and row["file_extension"]:
        safe_name = f"{safe_name}{row['file_extension']}"

    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"

    return safe_name


# ---------------------------------------------------------------------------
# Family merge
# ---------------------------------------------------------------------------

def _merge_family_pdfs(file_paths: list) -> bytes:
    """
    Merge multiple PDFs into a single PDF using PyMuPDF insert_pdf().
    Parent must be first in file_paths; attachments follow in control_number order.
    Returns the merged PDF as bytes.
    """
    merged = fitz.open()
    try:
        for path in file_paths:
            if path and os.path.exists(path):
                src = fitz.open(path)
                try:
                    merged.insert_pdf(src)
                finally:
                    src.close()
        return merged.tobytes()
    finally:
        merged.close()


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def export_pdfs_to_zip(
    case_folder: str,
    control_numbers: list,
    file_source: str,
    naming_field: str,
    append_extension: bool,
    prefix_sequential: bool,
    combine_families: bool,
) -> tuple:
    """
    Build a ZIP archive of PDFs for the given control numbers.

    Args:
        case_folder:       Absolute path to the case folder.
        control_numbers:   List of control number strings from bulk_cns.
        file_source:       "processed" | "native" | "produced"
        naming_field:      Column name from the documents table to use as filename.
        append_extension:  If True, appends the original file extension before .pdf.
        prefix_sequential: If True, prefixes each file with a 4-digit sequence number.
        combine_families:  If True, merges selected members of the same family group
                           into a single PDF per group (parent first, then attachments
                           in control_number order). Only the selected documents are
                           combined — missing family members are not auto-included.

    Returns:
        (zip_bytes, errors_list)
        zip_bytes:   bytes object of the completed ZIP, or b"" if nothing exported.
        errors_list: list of {"control_number": str, "error": str} dicts.
    """
    if not control_numbers:
        return b"", []

    conn = db_manager.get_connection(case_folder)
    try:
        placeholders = ",".join("?" for _ in control_numbers)
        rows = conn.execute(
            f"SELECT * FROM documents WHERE control_number IN ({placeholders})",
            control_numbers,
        ).fetchall()
    finally:
        conn.close()

    # Build a dict for fast lookup
    row_map = {r["control_number"]: r for r in rows}
    # Preserve the caller's selection order
    ordered_rows = [row_map[cn] for cn in control_numbers if cn in row_map]

    errors = []
    zip_buffer = io.BytesIO()
    seen_names = {}  # deconflict duplicate filenames inside the ZIP

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:

        if combine_families:
            # Group selected rows by group_id; singletons (no group_id) are
            # treated as their own group keyed by control_number.
            groups = {}
            for row in ordered_rows:
                gid = row["group_id"] or row["control_number"]
                groups.setdefault(gid, []).append(row)

            seq_num = 1
            for gid, group_rows in groups.items():
                # Sort: parent (parent_id IS NULL) first, then by control_number
                group_rows.sort(
                    key=lambda r: (0 if not r["parent_id"] else 1, r["control_number"])
                )
                representative = group_rows[0]  # parent or first selected

                # For Bates range naming, compute the family-wide span
                # so the filename reflects all pages in the merged PDF.
                if naming_field == "begdoc_range" and len(group_rows) > 1:
                    family_begdoc = representative["begdoc"] or ""
                    family_enddoc = representative["enddoc"] or ""
                    for _gr in group_rows[1:]:
                        _gr_end = _gr["enddoc"] or _gr["begdoc"] or ""
                        if _bates_number_sort_key(_gr_end) > _bates_number_sort_key(family_enddoc):
                            family_enddoc = _gr_end
                    # Build a shallow copy so we don't mutate the original row
                    representative = dict(representative)
                    representative["enddoc"] = family_enddoc

                paths = []
                group_errors = []
                for row in group_rows:
                    p, reason = _resolve_source_path(row, case_folder, file_source)
                    if not p:
                        group_errors.append({
                            "control_number": row["control_number"],
                            "error": reason,
                        })
                    elif not os.path.exists(p):
                        group_errors.append({
                            "control_number": row["control_number"],
                            "error": _file_not_found_msg(file_source, p),
                        })
                    else:
                        paths.append(p)

                errors.extend(group_errors)

                if not paths:
                    continue

                try:
                    if len(paths) == 1:
                        # Single document — write directly (no merge overhead)
                        zip_name = _build_zip_filename(
                            representative, naming_field,
                            append_extension, seq_num, prefix_sequential
                        )
                        zip_name = _deconflict(zip_name, seen_names)
                        zf.write(paths[0], zip_name)
                    else:
                        merged_bytes = _merge_family_pdfs(paths)
                        zip_name = _build_zip_filename(
                            representative, naming_field,
                            append_extension, seq_num, prefix_sequential
                        )
                        zip_name = _deconflict(zip_name, seen_names)
                        zf.writestr(zip_name, merged_bytes)

                    seq_num += 1

                except Exception as exc:
                    errors.append({
                        "control_number": representative["control_number"],
                        "error": str(exc),
                    })

        else:
            # Flat export — one file per selected document
            for seq_num, row in enumerate(ordered_rows, start=1):
                try:
                    source_path, reason = _resolve_source_path(row, case_folder, file_source)
                    if not source_path:
                        errors.append({
                            "control_number": row["control_number"],
                            "error": reason,
                        })
                        continue
                    if not os.path.exists(source_path):
                        errors.append({
                            "control_number": row["control_number"],
                            "error": _file_not_found_msg(file_source, source_path),
                        })
                        continue

                    zip_name = _build_zip_filename(
                        row, naming_field, append_extension, seq_num, prefix_sequential
                    )
                    zip_name = _deconflict(zip_name, seen_names)

                    # For native source: non-PDF files need conversion or fallback
                    if file_source == "native" and not source_path.lower().endswith('.pdf'):
                        pdf_bytes = _convert_native_to_pdf(source_path, row, case_folder)
                        if pdf_bytes:
                            zf.writestr(zip_name, pdf_bytes)
                        else:
                            # Cannot convert — include with real extension instead
                            real_ext = os.path.splitext(source_path)[1]
                            zip_name_native = zip_name.rsplit('.pdf', 1)[0] + real_ext
                            zip_name_native = _deconflict(zip_name_native, seen_names)
                            zf.write(source_path, zip_name_native)
                            errors.append({
                                "control_number": row["control_number"],
                                "error": f"included as {real_ext} (no PDF conversion available)",
                            })
                    else:
                        zf.write(source_path, zip_name)

                except Exception as exc:
                    errors.append({
                        "control_number": row["control_number"],
                        "error": str(exc),
                    })

    zip_buffer.seek(0)
    result_bytes = zip_buffer.getvalue()
    return (result_bytes if result_bytes else b""), errors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _convert_native_to_pdf(source_path: str, row, case_folder: str) -> bytes | None:
    """
    Attempt to convert a non-PDF native file to PDF bytes.
    Strategy:
      1. If a processed PDF exists (Processed/{cn}.pdf), use it as the conversion.
      2. If the file is an image PyMuPDF can handle, convert in-memory.
      3. Otherwise return None — caller should include as native with real extension.
    """
    cn = row["control_number"]
    # 1. Fall back to processed PDF if it exists
    processed_pdf = os.path.join(case_folder, "Processed", f"{cn}.pdf")
    if os.path.exists(processed_pdf):
        with open(processed_pdf, "rb") as f:
            return f.read()

    # 2. Image conversion via PyMuPDF
    ext = os.path.splitext(source_path)[1].lower()
    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif'}
    if ext in IMAGE_EXTS:
        img_doc = None
        try:
            img_doc = fitz.open(source_path)
            pdf_bytes = img_doc.convert_to_pdf()
            return pdf_bytes
        except Exception:
            pass
        finally:
            if img_doc:
                try: img_doc.close()
                except Exception as e:
                    logger.debug("fitz close error in _image_to_pdf_bytes: %s", e)

    return None


def _deconflict(name: str, seen: dict) -> str:
    """
    Append _1, _2, … to name if it already exists in seen.
    Updates seen in-place.
    """
    if name not in seen:
        seen[name] = 0
        return name
    seen[name] += 1
    base, ext = os.path.splitext(name)
    new_name = f"{base}_{seen[name]}{ext}"
    # Recurse in the unlikely event the suffixed name is also taken
    return _deconflict(new_name, seen)
