# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        os_manager.py
# version:       1.4.0
# project:       Respondeo eDiscovery Platform
# project_ver:   2.16.0
# last_modified: 2026-06-01 12:00
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import config
from opensearchpy import OpenSearch
from opensearchpy import helpers as os_helpers

_os_client = None

def get_os_client():
    """
    Returns a connected and verified OpenSearch client.
    Reuses existing client if already authenticated.
    No credentials needed — security plugin is disabled.
    """
    global _os_client
    
    if _os_client and _os_client.ping():
        return _os_client, "✅ Connected to OpenSearch (Cached)"

    try:
        client = OpenSearch(
            hosts=[config.OS_HOST],
            request_timeout=30,
            max_retries=10,
            retry_on_timeout=True
        )
        if client.ping():
            _os_client = client
            return client, "✅ Connected to OpenSearch"
        else:
            return None, "❌ Could not ping OpenSearch"
    except Exception as e:
        return None, f"Connection Failed: {e}"

def get_os_args():
    """
    Returns the raw connection dictionary for multiprocessing/threaded environments 
    where the client instance itself cannot be pickled/shared.
    """
    return {
        "hosts": [config.OS_HOST], 
        "request_timeout": 30, 
        "max_retries": 10, 
        "retry_on_timeout": True
    }

def get_index_name(folder_path_or_name: str) -> str:
    """
    Converts a case folder path or name into a valid OpenSearch index name.
    OpenSearch indices must be lowercase and cannot contain spaces or special chars [ , ", *, \, <, |, ,, >, /, ?].
    """
    import os
    import re
    # Extract just the folder name if a full path is provided
    name = os.path.basename(folder_path_or_name) or folder_path_or_name
    name = name.lower()
    # Replace spaces and special chars with underscores
    name = re.sub(r'[\s\*"\\<|,\>/?]+', '_', name)
    return name


def get_document_content(case_folder, control_number):
    """Fetch a single document's extracted text (`_source.content`) by
    control_number, for the near-dupe cluster-review diff pane (S-1b C8b).

    Returns the content string, or "" if the document is not found, OpenSearch is
    offline, or any error occurs (the diff pane degrades gracefully to an empty
    side). Uses an exact `term` match on `control_number.keyword` — mirrors the
    established precedent at pages/4_Review.py (the `.keyword` subfield is the
    exact-match field; a `term` on the analyzed `control_number` text field would
    not reliably match). Raw control_number is canonical in both the internal and
    inbound `_source` shapes (Flag #28 work)."""
    client, _status = get_os_client()
    if not client:
        return ""
    index_name = get_index_name(case_folder)
    try:
        resp = client.search(index=index_name, body={
            "size": 1,
            "query": {"term": {"control_number.keyword": control_number}},
            "_source": ["content"],
        })
        hits = resp.get("hits", {}).get("hits", [])
        return hits[0]["_source"].get("content", "") if hits else ""
    except Exception:
        return ""


def cn_from_hit(hit: dict) -> str:
    """
    Return the canonical control_number for an OS hit dict, handling
    both index shapes.

    Internal docs index with `_id == control_number` and `_source.control_number == cn`.
    Inbound docs index with `_id == f"{production_volume}-{control_number}"` (composite)
    and `_source.control_number == cn` (raw, not composite).

    The robust rule is: prefer `_source.control_number` (raw cn for both
    shapes); fall back to `_id` when `_source` is absent or the field is
    missing (defensive; OS hits from scan_all always include `_source`,
    but search hits may strip it under projection).

    Args:
        hit: An OS hit dict as returned by search() or scan_all().

    Returns:
        The control_number string. Never returns None — falls back to
        `hit["_id"]` if all other paths yield nothing.

    Raises:
        KeyError if the hit dict has neither `_source.control_number`
        nor `_id` (catastrophic OS response shape error; not expected in
        normal operation).
    """
    source = hit.get("_source") or {}
    cn = source.get("control_number")
    if cn:
        return cn
    return hit["_id"]


def compute_os_id(source_party: str, production_volume: str | None, control_number: str) -> str:
    """
    Compute the OpenSearch _id for a doc.

    Internal docs (source_party == "Internal"): _id == control_number.
    Inbound docs (any other source_party): _id == f"{production_volume}-{control_number}".

    Replaces the inline f-string pattern at pages/9_InboundProduction.py:453.
    Pairs with cn_from_hit() for the inverse direction.

    Args:
        source_party: "Internal" or any inbound-party string (e.g., opposing counsel name).
        production_volume: Required (non-None, non-empty) for inbound docs; ignored for internal.
        control_number: The doc's control number (raw, not composite).

    Returns:
        The OS _id string.

    Raises:
        ValueError: if source_party is non-"Internal" but production_volume is None or empty
            (cannot produce a meaningful composite _id).
    """
    if source_party == "Internal":
        return control_number
    if not production_volume:
        raise ValueError(
            f"compute_os_id: inbound doc (source_party={source_party!r}) requires "
            f"a non-empty production_volume; got {production_volume!r}."
        )
    return f"{production_volume}-{control_number}"


def ensure_highlight_limit(client, index_name: str, max_offset: int = 10_000_000):
    """
    Raises the index.highlight.max_analyzed_offset setting on an existing index.
    Default OpenSearch limit is 1,000,000 chars; this raises it to 10M.
    Safe to call multiple times (idempotent PUT settings call).
    """
    try:
        client.indices.put_settings(
            index=index_name,
            body={"index": {"highlight.max_analyzed_offset": max_offset}}
        )
    except Exception:
        # Non-fatal — search still works, just highlighting may fail on huge docs
        pass


def scan_all(client, index: str, query: dict, batch_size: int = 500):
    """
    Generator that uses the OpenSearch scroll/scan API to retrieve ALL matching
    documents for a query, bypassing the index.max_result_window limit (default 10,000).

    Yields individual raw hit dicts (each with '_id', '_source', etc.).

    Usage:
        es, _ = os_manager.get_os_client()
        for hit in os_manager.scan_all(es, index_name, {"match_all": {}}):
            # cn_from_hit() normalizes both _id shapes: internal docs use
            # control_number as _id; inbound docs use a composite (Flag #28).
            cn = os_manager.cn_from_hit(hit)
            ...

    Args:
        client:     Active OpenSearch client instance.
        index:      Index name to scan.
        query:      OpenSearch query dict (the value of the "query" key, not the full body).
        batch_size: Number of documents to retrieve per scroll batch (default 500).
    """
    try:
        for hit in os_helpers.scan(
            client,
            index=index,
            query={"query": query},
            scroll="2m",
            size=batch_size,
            raise_on_error=True,
            preserve_order=False,
        ):
            yield hit
    except Exception as e:
        raise RuntimeError(f"scan_all failed on index '{index}': {e}") from e


def reindex_from_sqlite(case_folder: str, progress_callback=None):
    """
    Rebuild the OpenSearch index for a case by reading all processed
    documents from SQLite and bulk-upserting with the current field mapping.

    This does NOT reprocess source files — it only reads metadata and
    extracted text already stored in the database.

    Args:
        case_folder:      Full path to the case folder.
        progress_callback: Optional callable(current, total) for progress updates.

    Returns:
        tuple: (success_count: int, error_count: int, error_messages: list[str])
    """
    import logging
    import db_manager

    logger = logging.getLogger(__name__)

    client, msg = get_os_client()
    if not client:
        return 0, 0, [f"OpenSearch connection failed: {msg}"]

    index_name = get_index_name(case_folder)
    logger.info(f"Reindex started for case '{case_folder}' -> index '{index_name}'")

    # Read all processed documents from SQLite
    conn = db_manager.get_connection(case_folder)
    rows = conn.execute(
        "SELECT * FROM documents WHERE processing_status IN ('Processed', 'Master') AND control_number IS NOT NULL"
    ).fetchall()
    conn.close()

    total = len(rows)
    if total == 0:
        return 0, 0, ["No processed documents found in database"]

    # Bulk-scan existing index to preserve content text
    existing_content = {}
    try:
        for hit in scan_all(client, index_name, {"match_all": {}}):
            existing_content[cn_from_hit(hit)] = hit["_source"].get("content", "")
    except Exception:
        pass  # Index may not exist yet — content will be empty

    logger.info(f"Preserved content text for {len(existing_content)} existing documents")

    # Build OS docs and bulk-upsert
    BATCH_SIZE = 500
    batch = []
    success_count = 0
    error_count = 0
    error_messages = []

    for idx, row in enumerate(rows):
        cn = row["control_number"]
        extracted_text = existing_content.get(cn, "")

        os_doc = {
            "_index": index_name,
            "_id": cn,
            "_source": {
                "file_name":        row["file_name"] or "",
                "control_number":   cn,
                "path":             row["full_path"] or "",
                "content":          extracted_text,
                "group_id":         row["group_id"],
                "parent_id":        row["parent_id"],
                "custodian":        row["custodian"],
                "email_subject":    row["email_subject"],
                "author":           row["author"],
                "date":             row["date_sent"] or row["date_created"],
                "email_from":       row["email_from"],
                "email_to":         row["email_to"],
                "email_cc":         row["email_cc"],
                "email_bcc":        row["email_bcc"],
                "file_extension":   row["file_extension"],
                "record_type":      row["record_type"],
                "date_sent":        row["date_sent"],
                "date_created":     row["date_created"],
                "date_received":    row["date_received"],
                "date_modified":    row["date_modified"],
                "file_size_kb":     row["file_size_kb"],
                "page_count":       row["page_count"],
                "title":            row["title"],
                "language":         row["language"],
                "importance":       row["importance"],
                "has_text":         row["has_text"] or 0,
                "source_collection":    row["source_collection"] or "",
                "source_subcollection": row["source_subcollection"] or "",
                "source_party":     row["source_party"] if row["source_party"] is not None else "Internal",
                "production_volume": row["production_volume"] if row["production_volume"] is not None else "",
                "production_category": row["production_category"] if row["production_category"] is not None else "",
            }
        }
        batch.append(os_doc)

        if len(batch) >= BATCH_SIZE:
            _ok, _err = _flush_batch(client, batch, error_messages)
            success_count += _ok
            error_count += _err
            batch = []

        if progress_callback:
            progress_callback(idx + 1, total)

    # Flush remaining
    if batch:
        _ok, _err = _flush_batch(client, batch, error_messages)
        success_count += _ok
        error_count += _err

    logger.info(f"Reindex complete: {success_count} succeeded, {error_count} errors")
    return success_count, error_count, error_messages


def _flush_batch(client, batch, error_messages):
    """Bulk-upsert a batch of OS docs. Returns (success_count, error_count)."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        success, errors = os_helpers.bulk(
            client, batch, chunk_size=500,
            max_chunk_bytes=10 * 1024 * 1024,
            request_timeout=120,
            raise_on_error=False
        )
        err_count = len(errors) if isinstance(errors, list) else 0
        if err_count:
            for e in errors[:10]:
                msg = str(e)
                error_messages.append(msg)
                logger.error(f"Bulk index error: {msg}")
        return success, err_count
    except Exception as e:
        msg = f"Bulk upsert failed: {e}"
        error_messages.append(msg)
        logger.error(msg)
        return 0, len(batch)

