# OpenSearch Patterns Reference — eDiscovery Platform Usage

**Last updated:** 2026-03-18  
**Applies to:** `os_manager.py`, `2_Processor.py` (bulk indexing), `3_Analytics.py` (near-dupe, scan), `4_Review.py` (search, STR, highlighting), `6_Sync.py`  
**OpenSearch docs:** https://opensearch.org/docs/latest/  
**Our deployment:** Single-node, security plugin disabled, local access only

---

## Connection

```python
from opensearchpy import OpenSearch

client = OpenSearch(
    hosts=[config.OS_HOST],     # e.g., "http://localhost:9200"
    request_timeout=30,
    max_retries=10,
    retry_on_timeout=True
)
```

**Security disabled:** Our local single-node deployment runs without authentication. No API keys, no TLS. This is fine for single-machine law firm deployment but would need to change for any networked or cloud deployment.

**Client singleton:** `os_manager.get_os_client()` caches a single client instance. For threaded environments where the client can't be shared (e.g., `ProcessPoolExecutor`), use `os_manager.get_os_args()` to get the raw connection dict and create a new client per worker.

---

## Index Naming

```python
index_name = os_manager.get_index_name(case_folder)
```

Converts a case folder path to a valid OpenSearch index name: lowercase, special characters replaced with underscores. Each case gets its own index.

**Index naming rules:** Must be lowercase. Cannot contain: `[ , ", *, \, <, |, ,, >, /, ? ]`. Cannot start with `_`, `-`, or `+`.

---

## Index Mapping — Dynamic (No Explicit Schema)

**We do not create indices explicitly.** OpenSearch auto-creates the index on the first `bulk()` call with dynamic mapping. This means:

- **Text fields** get both a `text` type (analyzed, full-text searchable) and a `.keyword` sub-field (exact match, aggregatable).
- **Numeric fields** are auto-detected as `long` or `float`.
- **Date fields** — **CAUTION:** Our dates are stored as ISO 8601 strings. OpenSearch may or may not auto-detect them as `date` type depending on the format. We use them primarily for display, not for range queries, so this hasn't been an issue yet.

### Implications of Dynamic Mapping

| Advantage | Risk |
|-----------|------|
| Zero setup required | No control over field types |
| New fields auto-indexed | First document's value determines field type for the index |
| Works across diverse document sets | If first indexed value for a field is `null`, the type is undetermined until a real value appears |

**Future consideration:** For production/commercial deployment, an explicit mapping template would be more robust. Flagged for Phase 15+.

---

## Indexed Document Schema

Every document indexed to OpenSearch follows this structure (from `process_file_worker()`, line 724):

```python
os_doc = {
    "_index": index_name,
    "_id": control_number,       # e.g., "DOC-000042" — unique per document
    "_source": {
        # --- Identifiers ---
        "control_number": str,   # Same as _id
        "filename": str,         # Original filename
        "path": str,             # Full path to processed file

        # --- Full-text content ---
        "content": str,          # Extracted text (primary search field)

        # --- Family relationships ---
        "group_id": str,         # Family group identifier
        "parent_id": str,        # Parent control number (None for root docs)

        # --- Custodian / classification ---
        "custodian": str,        # Custodian name
        "record_type": str,      # "Email" or "Document"
        "file_extension": str,   # e.g., ".pdf", ".msg"

        # --- Email metadata ---
        "subject": str,          # Email subject (or document title)
        "author": str,           # Author / sender
        "email_from": str,
        "email_to": str,
        "email_cc": str,
        "email_bcc": str,

        # --- Dates ---
        "date": str,             # Primary date (sent or created) — ISO 8601
        "date_sent": str,
        "date_created": str,
        "date_received": str,
        "date_modified": str,

        # --- Document properties ---
        "file_size_kb": float,
        "page_count": int,
        "title": str,
        "language": str,
        "importance": int,       # 0=Low, 1=Normal, 2=High (emails only)
        "has_text": int,         # 1 if text was extracted, 0 if not
    }
}
```

### Fields Added Post-Processing (not in initial index)

These fields are updated in SQLite but NOT re-indexed to OpenSearch after initial indexing:

- `source_party` — Added later during case setup. **Available via `.keyword` filter** because it was indexed on a subsequent update (or on the Sync module's re-index).
- `production_volume` — Set during production. Same caveat.
- `tags` — Stored in SQLite only. NOT indexed to OpenSearch.

**Important:** If a field is not in the OpenSearch index, you cannot search or filter on it via `query_string` or `term` queries. Use SQLite for those fields. Our dual-search pattern handles this.

---

## Query Patterns

### 1. Full-Text Search (Review Module)

```python
es_query = {
    "query_string": {
        "query": search_query,
        "fields": ["content", "filename", "email_subject", "email_from", "email_to"],
        "default_operator": "AND",
        "analyze_wildcard": True,
        "fuzziness": "AUTO",
        "allow_leading_wildcard": False
    }
}
```

**`default_operator: AND`** — All terms must match. User can override with explicit `OR`.

**`analyze_wildcard: True`** — Allows `settl*` to match `settlement`, `settling`, etc.

**`allow_leading_wildcard: False`** — Prevents `*ment` queries which are extremely slow on large indices.

**`fuzziness: AUTO`** — Automatic edit-distance tolerance based on term length. Good for typo recovery (`priviledge~` finds `privilege`).

**Searched fields:** `content` (extracted text), `filename`, `email_subject`, `email_from`, `email_to`. These are the five fields most likely to contain responsive terms.

### 2. Filtered Search (Tree Selection)

When the user selects a party, custodian, or volume in the navigation tree, we add `term` filters:

```python
es_filters = []
es_filters.append({"term": {"source_party.keyword": "Internal"}})
es_filters.append({"term": {"custodian.keyword": "JSmith"}})

es_query = {
    "bool": {
        "must": [full_text_query],
        "filter": es_filters
    }
}
```

**`.keyword` suffix:** Required for exact-match `term` queries on text fields. Without `.keyword`, the value is analyzed (lowercased, tokenized) and `term` won't match. Example: `{"term": {"custodian": "JSmith"}}` would fail because the analyzed value is `"jsmith"`.

### 3. Search Term Report (STR)

```python
_str_body = {
    "query": {
        "bool": {
            "must": [{
                "query_string": {
                    "query": term,
                    "fields": [search_field],   # e.g., "content"
                    "default_operator": "AND",
                    "analyze_wildcard": True
                }
            }],
            "must_not": exclusion_clauses
        }
    },
    "size": max_hits_per_term,
    "_source": ["control_number", "file_name", "content"]
}
```

**`_source` filtering:** We only fetch the fields we need, not the full document. This is important for performance — `content` fields can be megabytes.

**`must_not` clauses:** Used to exclude previously tagged documents (e.g., already-reviewed items).

### 4. Near-Duplicate Analysis (Analytics)

Uses the `scan` helper to iterate ALL documents without hitting the `index.max_result_window` limit:

```python
from opensearchpy.helpers import scan

query = {
    "query": {
        "bool": {
            "should": [
                {"term": {"source_party.keyword": "Internal"}},
                {"bool": {"must_not": {"exists": {"field": "source_party"}}}}
            ]
        }
    },
    "_source": ["control_number", "content"]
}

for hit in scan(es, query=query, index=index_name):
    content = hit['_source'].get('content', '')
```

**`scan()` vs `search()`:** `search()` is limited to `index.max_result_window` (default 10,000) results. `scan()` uses the scroll API to iterate through all matches regardless of count. Use `scan()` for analytics, use `search()` for interactive queries with a reasonable `size` limit.

Our `os_manager.scan_all()` wraps this pattern with error handling.

### 5. Dual-Search (OpenSearch + SQLite)

The Review module runs two parallel searches:

```python
# 1. OpenSearch — full-text content search
response = es.search(index=index_name, body=search_body)
for hit in response['hits']['hits']:
    # Use os_manager.cn_from_hit(hit), NOT hit['_id'] directly: inbound docs
    # index with a composite _id (f"{production_volume}-{control_number}") while
    # internal docs use control_number as _id. cn_from_hit normalizes both (Flag #28).
    search_hit_ids.add(os_manager.cn_from_hit(hit))

# 2. SQLite — Bates number and filename search
bz_rows = conn.execute(
    "SELECT control_number FROM documents WHERE begdoc LIKE ? OR enddoc LIKE ? OR file_name LIKE ?",
    (f"%{query}%", f"%{query}%", f"%{query}%")
).fetchall()
for br in bz_rows:
    search_hit_ids.add(br['control_number'])
```

**Why dual:** Bates numbers (`begdoc`, `enddoc`) and production volumes are stored in SQLite but not always in the OpenSearch index. The dual approach ensures a search for `ABC-000123` finds the document even if that Bates number was assigned after initial indexing.

---

## Highlighting

```python
_highlight_block = {
    "fields": {
        "content": {
            "number_of_fragments": 3,
            "fragment_size": 150
        }
    },
    "pre_tags": ["<mark style='background-color:#ffe066;color:black;border-radius:2px;padding:0 2px'>"],
    "post_tags": ["</mark>"]
}

_search_body = {
    "query": es_query,
    "highlight": _highlight_block,
    "size": 500
}
```

**`max_analyzed_offset` fallback:** Documents with very large text fields can exceed the highlight analysis limit. We catch this error and retry without highlighting:

```python
try:
    response = es.search(index=index_name, body=_search_body)
except Exception as e:
    if "max_analyzed_offset" in str(e):
        _search_body.pop("highlight", None)
        response = es.search(index=index_name, body=_search_body)
```

We also proactively raise the limit via `os_manager.ensure_highlight_limit()` which sets `index.highlight.max_analyzed_offset` to 10M characters.

---

## Bulk Indexing (Processor)

```python
from opensearchpy import helpers

helpers.bulk(
    client,
    os_batch,                              # List of os_doc dicts
    chunk_size=len(os_batch),
    max_chunk_bytes=10 * 1024 * 1024,      # 10MB
    request_timeout=60
)
```

**Batch assembly:** Documents are queued during threaded processing and bulk-indexed in batches. The batch is flushed when it reaches a configurable size or when processing completes.

**Error handling:** Bulk errors are parsed to identify which specific documents failed. Failed documents are marked as `OS_Error` in SQLite so they can be retried.

---

## Known Gotchas

### 1. Field name `content` — not `extracted_text`
The OpenSearch field containing document text is `content`. Previous sprint prompts have incorrectly referenced `extracted_text`. Always verify field names against this document.

### 2. Dynamic mapping type lock-in
The first non-null value indexed for a field determines its type for the entire index. If the first document has `page_count: "5"` (string), all subsequent documents must also index `page_count` as a string. Mixing types causes bulk indexing errors.

### 3. `.keyword` required for exact-match filters
`{"term": {"custodian": "JSmith"}}` will NOT match because the `custodian` field is analyzed (lowercased). Use `{"term": {"custodian.keyword": "JSmith"}}` for exact match.

### 4. `scan()` does not support highlighting
The scroll/scan API is for batch retrieval only. Highlighting requires `search()`.

### 5. Index deletion is irreversible
`client.indices.delete(index=index_name)` permanently removes the index and all documents. The Sync module uses this for re-indexing. There is no undo — the only recovery is to reprocess the case.

### 6. `search()` default size is 10
If you don't specify `"size"` in the query body, OpenSearch returns only 10 hits. Our search uses `"size": 500`. For complete result sets, use `scan()`.

### 7. `tags` is NOT in OpenSearch
Tags are stored only in SQLite. You cannot search by tag via OpenSearch. Tag-based filtering happens in the DataFrame layer after the SQL query, not in the search query itself.

### 8. Re-indexing after metadata changes
If metadata is updated in SQLite (e.g., `source_party` assignment, tag changes), the OpenSearch index is NOT automatically updated. The Sync module provides a full re-index operation. Incremental re-indexing is not yet implemented.

### 9. Highlight limit on large documents
Documents over ~1M characters can cause highlighting to fail with `max_analyzed_offset` error. Our code handles this gracefully by retrying without highlighting, and proactively raises the limit to 10M. But truly enormous documents (e.g., database dumps, code repositories) may still fail.

### 10. Query syntax errors surface to the user
If a user types invalid `query_string` syntax (e.g., unmatched quotes, dangling operators), OpenSearch throws a `RequestError`. The Review module catches this and displays a friendly error, but the search returns no results. Input validation catches some common cases (trailing AND/OR/NOT, leading with an operator).
