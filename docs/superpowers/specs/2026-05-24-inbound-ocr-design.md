# Inbound Document Text Extraction — Design Spec

**Date:** 2026-05-24
**Status:** UNSHIPPED (ready for implementation plan)
**Sprint target:** beta-2.17+ (deferred from beta-2.16 per the maintainer's decision; out of S-2 scope)
**Related:** S-2 Flag #28 (`pages/4_Review.py` symptom patched beta-2.15 C7; cross-codebase audit + reindex bug fix scoped for beta-2.16 Phase 2). The `os_manager.compute_os_id()` helper introduced by this spec pairs with `os_manager.cn_from_hit()` introduced by the S-2 preflight — both helpers live in `os_manager.py`; either can ship first.

---

## 1. Problem statement

When opposing counsel sends inbound document productions, two formats arrive:

1. **Full eDiscovery format** — load file (`.dat`/`.csv`/`.txt`) + native files + companion extracted-text files (one `.txt` per doc, referenced by the `text_path` column). The existing inbound module at `pages/9_InboundProduction.py` consumes this happily: text content lands in OpenSearch's `content` field, docs are immediately searchable.

2. **Bare-minimum stamped-PDF format** — load file + native PDFs that have been printed, scanned (or printed-to-PDF), and Bates-stamped. No companion text files. This is by far the more common format in practice: most firms do not run eDiscovery on their disclosures unless the court has ordered it via a case management order; standard practice is convert-to-PDF → Bates-stamp → categorize in the disclosure certificate.

The current inbound ingest path **silently drops content for format 2**: with `text_path` empty or pointing at nothing, `_ib_extracted_text` stays `""`, `has_text=0` lands in SQLite (`pages/9_InboundProduction.py:475` passes `1 if _ib_extracted_text else 0` as the 20th tuple position consumed by `db_manager.upsert_inbound_documents_batch`), the OS `content` field is omitted, and the doc is searchable only on filename/metadata.

The substantive consequence: opposing's bare-minimum stamped PDFs are functionally invisible to text search inside the platform. The user can see them in the grid (filename, Bates range, custodian if present in the load file) but cannot find documents by phrase or keyword. Given that bare-minimum is the dominant format opposing counsel uses, this is a meaningful gap in the platform's value proposition for the receiving party.

**The feature.** A user-triggered "Run extraction" button in the Inbound module that runs Tika + Tesseract OCR on inbound natives where text is missing, writes the extracted content atomically to SQLite + OpenSearch, and reports a summary of what extracted cleanly, what failed, and why.

---

## 2. Goals + non-goals

**In scope:**

- Post-ingest user-triggered text extraction for inbound docs lacking text.
- Native-first extraction via `processing_engine.get_tika_data()` (which already chains Tika → `_ocr_fallback` internally for image-only PDFs), with image-path fallback if native yields no extractable text.
- Atomic per-doc SQLite + OpenSearch updates inside the extraction loop.
- Case-wide single button: processes all inbound docs where `has_text=0`, regardless of which production volume they came from. Handles backfill of legacy productions automatically.
- Continue-on-error per-doc with end-of-run summary; infrastructure failures (Tika down / Tesseract missing / OS unreachable) abort cleanly at a pre-flight gate before the loop starts.
- Failure classifications recorded to existing `extraction_notes` column for forensic inspection.
- Permission gate `extract_inbound_text` (manager+); audit events for run start / completion / abort.

**Out of scope (deferred; documented in §10):**

- Force-reextract of docs that already have text.
- Background worker model (continue across tab close).
- OCR of `.msg`/`.eml` inbound attachments (the existing internal pipeline handles via `container_exploder`; cross-pipeline rationalization is a separate feature).
- Per-doc cancel mid-run.
- OCR quality scoring, language detection, image preprocessing.
- Auto-detection of inbound vs internal at button-time (button is explicitly inbound-scoped by the SQL filter).

---

## 3. Design overview — Approach A: helpers in `processing_engine` + UI in `9_InboundProduction`

The feature lifts a small surface into existing modules rather than creating a new `inbound_extraction.py`. This matches the established pattern: compare `os_manager.reindex_from_sqlite()` (a function in `os_manager.py` called by the "Rebuild Search Index" button in `pages/6_Sync.py`). The shape is identical for this feature.

Two new functions in `processing_engine.py`, two new functions in `db_manager.py`, one new helper in `os_manager.py`, one new UI section in `pages/9_InboundProduction.py`. No new files.

---

## 4. Component surface

### `processing_engine.py`

```python
def extract_inbound_doc(doc_row: dict, client, index_name: str) -> tuple[bool, str | None, str | None]:
    """
    Extract text from one inbound doc and atomically write the result to
    SQLite + OpenSearch.

    Returns (success, method, notes) where:
      - success: True if extracted text is non-empty (above EXTRACTION_MIN_CHARS).
      - method: one of "tika", "tesseract_ocr" (existing taxonomy values
                from db_manager.py:169), or None on failure. The
                `extraction_notes` field carries the "which path was the
                source" distinction (e.g., "ocr_source: image_path") when
                that detail matters for forensic inspection; the method
                column itself uses only the established taxonomy to keep
                the per-extraction-method aggregation queries in
                defensibility_report.py:4703 working unchanged.
      - notes: failure classification string when success=False; None otherwise.

    Pure function on (doc_row, client, index_name). Does not consult the
    progress callback or print to UI. Side effects: one SQLite UPDATE,
    one OS partial-update (batched by caller).
    """

def extract_all_pending_inbound(
    case_folder: str,
    progress_callback=None,
) -> tuple[int, int, list[str]]:
    """
    Case-wide orchestrator. Queries SQLite for inbound docs where
    has_text=0, drives extract_inbound_doc per doc, batches OS
    bulk-update flushes every EXTRACTION_OS_BATCH_SIZE docs, returns the
    summary tuple (success_count, error_count, error_messages).

    Pre-flight checks (abort before loop if any fail):
      - Tika server reachable via GET on TIKA_URL with 2s timeout.
      - Tesseract binary exists at config.TESSERACT_PATH.
      - OpenSearch ping() succeeds.

    Failure of any pre-flight check raises InboundExtractionAborted with a
    classification field readable by the UI caller.

    Returns: (success_count, error_count, error_messages: list[str]).
    error_messages format: "DOC-00123: <classification>" for each failed doc.
    """
```

`extract_all_pending_inbound`'s signature mirrors `os_manager.reindex_from_sqlite(case_folder, progress_callback=None) -> tuple[int, int, list[str]]` deliberately. Code reviewers already understand the shape.

### `db_manager.py`

```python
def get_inbound_docs_pending_extraction(case_folder: str) -> list[dict]:
    """
    Return inbound docs needing text extraction:
      SELECT control_number, source_party, production_volume,
             full_path, native_path, image_path
      FROM documents
      WHERE source_party != 'Internal'
        AND has_text = 0
        AND (full_path IS NOT NULL OR native_path IS NOT NULL
             OR image_path IS NOT NULL)
      ORDER BY control_number
    Returns dicts (sqlite3.Row converted) for use by extract_inbound_doc.
    """

def update_inbound_extraction_state(
    case_folder: str,
    control_number: str,
    success: bool,
    method: str | None,
    notes: str | None,
    is_encrypted: bool = False,
) -> None:
    """
    Single-row UPDATE on the `documents` table for one inbound doc after
    an extraction attempt:
      - has_text = 1 if success else (unchanged; preserves prior value)
      - extraction_method = method (NULL on failure)
      - extraction_notes = notes (NULL on success)
      - is_encrypted = 1 if is_encrypted else (unchanged)

    The text content itself is NOT written to SQLite — there is no
    `content` column in the documents table. Content lives in OpenSearch
    only. The OS bulk-update is the caller's responsibility
    (extract_inbound_doc queues the OS partial-update into a batch
    buffer that extract_all_pending_inbound flushes via helpers.bulk).

    Wrapped in db_manager.get_connection context. Does NOT commit per
    row when called inside an active transaction; caller may batch via
    explicit transaction management if performance demands.
    """
```

### `os_manager.py`

```python
def compute_os_id(
    source_party: str,
    production_volume: str | None,
    control_number: str,
) -> str:
    """
    Compute the OpenSearch _id for a doc.

    Internal docs (source_party='Internal'): _id = control_number.
    Inbound docs (any other source_party): _id = f"{production_volume}-{control_number}".

    Replaces the inline pattern at pages/9_InboundProduction.py:453,
    lifting the composite-id convention into one place. Pairs with
    cn_from_hit() (introduced by the S-2 preflight) which handles the
    inverse direction (OS hit dict → control_number).

    Raises ValueError if source_party is non-Internal but production_volume
    is None — that combination cannot produce a meaningful _id.
    """
```

### `pages/9_InboundProduction.py`

New section "Text Extraction Backfill" rendered below the existing ingest UI:

```
[# permission: extract_inbound_text]
[Manager+ gate; closed-case posture: render disabled per CLAUDE.md rule]

### Text Extraction Backfill

[Count chip]  ⓘ  N inbound docs lack searchable text.

[Run extraction] button
  └─ on press:
      [st.progress(0)]  "Extracting: 0 / N"
      → calls processing_engine.extract_all_pending_inbound(
          case_folder, progress_callback=lambda current, total: ...)
      → during run, progress callback updates the bar + status text
      → on completion: replaces button with summary card (see §6)
      → on infrastructure-pre-flight abort: shows abort banner
        ("Apache Tika server not reachable at {url}. Start the service
        and re-click.") and does not enter the loop.
```

When the count is 0, the button is disabled and a calm "All inbound docs have text content" message replaces the count chip. No nag, no surprise empty-state run.

---

## 5. Per-doc lifecycle

Inside `extract_inbound_doc`:

1. **Source resolution.** Prefer `native_path` (the actual file). If empty, fall back to `image_path`. If both empty → record `extraction_notes="no_extractable_source"`, write SQLite update (notes only; has_text stays 0), return `(False, None, notes)`. The doc remains in the pending pool but is now diagnosed.
2. **Native-first extraction.** Call `processing_engine.get_tika_data(native_path)`. Returns `(text, meta_dict)`. `meta["extracted_with"]` reports the method Tika used internally: `tika` (text-layer extraction), `tesseract_ocr` (Tika's own OCR fallback fired for image-only PDF), or absent.
3. **Threshold gate.** If `len(text.strip()) > config.EXTRACTION_MIN_CHARS` (default 50), accept; method = `meta["extracted_with"]` (one of `"tika"` or `"tesseract_ocr"`).
4. **Image-path fallback** (only if native gate failed AND `image_path` populated AND `image_path` ≠ `native_path`). Call `processing_engine._ocr_fallback(image_path)`. If length passes threshold → accept; method = `"tesseract_ocr"` (existing taxonomy value); record `extraction_notes = "ocr_source: image_path"` to preserve the forensic distinction without polluting the method taxonomy.
5. **Both empty.** Record `extraction_notes="extraction_yielded_empty"`, write SQLite update (notes only; has_text stays 0). Doc stays in pending pool — visible to the user as a "stuck" doc on next run.
6. **Write phase (success).** `db_manager.update_inbound_extraction_state(case_folder, cn, success=True, method=method, notes=image_path_note_or_None, is_encrypted=False)` — sets `has_text=1`, `extraction_method`, `extraction_notes` (NULL unless image_path was used). Queue OS partial update into the caller's batch buffer:
   ```python
   {
     "_op_type": "update",
     "_index": index_name,
     "_id": os_manager.compute_os_id(source_party, production_volume, control_number),
     "doc": {"content": text, "extraction_method": method},
   }
   ```
7. **Write phase (failure).** `db_manager.update_inbound_extraction_state(case_folder, cn, success=False, method=None, notes=<classification>, is_encrypted=<bool>)` — records the notes and (for `password_protected` classification) sets `is_encrypted=1`. No OS write queued for failed docs.
8. **Exceptions during extraction.** Caught at the boundary; classified per §7. Doc is recorded as a failure; loop continues.

### Batch flush cadence

`extract_all_pending_inbound` accumulates OS update operations into a buffer. Flushes via `helpers.bulk(client, batch, raise_on_error=False, raise_on_exception=False)` (matching the existing inbound bulk-write pattern at `pages/9_InboundProduction.py:389`) every `config.EXTRACTION_OS_BATCH_SIZE` (default 50) docs, OR at end-of-loop, whichever fires first. Per-item failures returned by `helpers.bulk` are accumulated into the run's `error_messages` list and reported in the summary.

---

## 6. Error handling

### Pre-flight gate (infrastructure failures)

Run once at button-press, before the loop:

| Check | Trigger if | UI behavior |
|-------|------------|-------------|
| Tika reachable | `requests.get(config.TIKA_URL, timeout=2)` raises or returns non-2xx | Abort with banner: *"Apache Tika server not reachable at {url}. Start the service and re-click."* Audit: `INBOUND_TEXT_EXTRACTION_ABORTED` event with `failure_reason="tika_unreachable"`. |
| Tesseract binary | `not os.path.exists(config.TESSERACT_PATH)` | Abort with banner: *"Tesseract not found at {path}. Update config.py."* Audit event with `failure_reason="tesseract_missing"`. |
| OpenSearch reachable | `client.ping()` returns False or raises | Abort with banner: *"OpenSearch not reachable. Check the service."* Audit event with `failure_reason="opensearch_unreachable"`. |

These three checks intentionally do NOT enter the per-doc loop. The Q5 design choice ("continue-on-error during the loop") applies to per-doc failures; infrastructure problems are run-wide and warrant pre-flight detection so users get a clear, actionable error before wasting time.

### Per-doc classifications

Stored in `documents.extraction_notes` column (already present per CLAUDE.md §PST Extraction Architecture):

| Classification | Trigger |
|----------------|---------|
| `no_extractable_source` | Both `native_path` and `image_path` empty/missing. |
| `password_protected` | `fitz.open()` raises `PdfPasswordError`, OR Tika returns password-protection metadata. Also sets `is_encrypted=1` on the SQLite row. |
| `extraction_failed: <truncated message>` | Any other exception in extract chain; exception message truncated to 200 chars. |
| `extraction_yielded_empty` | Both Tika and OCR ran cleanly but combined output was < `EXTRACTION_MIN_CHARS`. |

`extraction_notes` for successful docs is cleared (set to NULL).

### Summary card content (end of run)

```
Extraction complete in 24 min 12 sec.
  ✓ 400 of 450 docs extracted successfully.
    • Tika text-layer (method=tika): 300
    • OCR via native render (method=tesseract_ocr, no notes): 80
    • OCR via image_path (method=tesseract_ocr, notes="ocr_source: image_path"): 20
  ⚠ 50 docs had issues:
    • Password-protected: 5
    • Empty after extraction: 40
    • Extraction error: 5  [Show details ▾]
  [Re-run extraction]   ← reprocesses only the still-empty docs
```

The "Re-run extraction" button is the same "Run extraction" trigger surfaced contextually — the case-wide-on-empty filter naturally picks up only the still-pending docs.

---

## 7. Testing strategy

Three tiers, matching existing project patterns.

### Unit (`tests/test_inbound_extraction.py`, new file)

- `test_extract_inbound_doc_tika_success` — mock `get_tika_data` returns text > threshold; assert SQLite + OS write called correctly; assert method = `"tika"`.
- `test_extract_inbound_doc_native_empty_image_fallback` — mock native returns empty, image_path populated; assert `_ocr_fallback(image_path)` called; assert method = `"tesseract_ocr"` AND `extraction_notes = "ocr_source: image_path"`.
- `test_extract_inbound_doc_both_empty` — both yield empty; assert `extraction_notes="extraction_yielded_empty"`, `has_text` stays 0, no OS write queued.
- `test_extract_inbound_doc_password_protected` — mock `get_tika_data` raises `PdfPasswordError`; assert `extraction_notes="password_protected"` AND `is_encrypted=1` on the row.
- `test_extract_inbound_doc_threshold_boundary` — returns 49 chars vs 51 chars; asserts threshold gate behavior at the boundary.
- `test_extract_inbound_doc_no_extractable_source` — both paths empty; assert `no_extractable_source` classification.
- `test_compute_os_id_internal` / `test_compute_os_id_inbound` / `test_compute_os_id_missing_volume_raises` — helper unit tests.
- `test_extract_all_pending_inbound_tika_unreachable_abort` — mock pre-flight Tika check fails; assert `InboundExtractionAborted` raised with classification; assert no docs touched.

### Integration (`tests/test_inbound_extraction_e2e.py`, new file)

Seed a case with 3 inbound docs (1 PDF with text layer, 1 image-only PDF, 1 deliberately corrupt PDF). Run `extract_all_pending_inbound`. Assert:

- Return tuple = `(2, 1, [<error msg for corrupt doc>])`.
- SQLite state: 2 docs have `has_text=1` and non-NULL `extraction_method`; 1 doc has `extraction_notes` populated and `has_text=0`.
- OS state: 2 docs have non-empty `content` field via direct OS query.
- OS `_id` shape: composite `{volume}-{cn}` for all 3 docs.

Uses real Tika + Tesseract if available; skip-on-unavailable via the existing `tests/conftest.py` infrastructure-skip pattern.

### Regression / contract pin

- `test_compute_os_id_matches_inbound_production_id_format` — pins the exact format produced today by `pages/9_InboundProduction.py:453` inline. This is the contract that S-2's `cn_from_hit` companion must honor for round-trips.

---

## 8. Configuration additions

In `config.py` and `config.example.py`:

```python
# Inbound text extraction tunables
EXTRACTION_MIN_CHARS = 50          # Below this, treat result as "noise" and try fallback path
EXTRACTION_OS_BATCH_SIZE = 50      # Docs per helpers.bulk flush
```

Both pinned to sensible defaults; tunable post-deployment if empirics surface a better number.

`TIKA_URL` and `TESSERACT_PATH` are already in `config.py` from the internal-side processing pipeline — reused, no new config.

---

## 9. Audit event taxonomy

Three events, all logged via `db_manager.log_audit()` (never-raise contract):

| Event | When | Payload |
|-------|------|---------|
| `INBOUND_TEXT_EXTRACTION_STARTED` | Button-press, after pre-flight gate passes | `{"pending_doc_count": N}` |
| `INBOUND_TEXT_EXTRACTION_COMPLETED` | Run-end, regardless of how many succeeded | `{"success_count": N, "error_count": M, "duration_sec": S, "method_breakdown": {"tika": X, "tesseract_ocr_native": Y, "tesseract_ocr_image_path": Z}}` (the audit JSON `method_breakdown` may use richer sub-keys than the SQLite `extraction_method` taxonomy — the SQLite column stays bounded to existing values for query compatibility; the audit JSON is free to carry forensic detail) |
| `INBOUND_TEXT_EXTRACTION_ABORTED` | Pre-flight gate fails | `{"failure_reason": "tika_unreachable" | "tesseract_missing" | "opensearch_unreachable"}` |

No per-doc audit events — would flood the log on large productions. Per-doc state lives in `documents.extraction_notes` for forensic inspection.

---

## 10. Cross-sprint dependencies and recovery contract

### Dependency on S-2 (Flag #28 fix)

- **Primary path** (extract → atomic per-doc OS update via partial-update bulk): **NOT dependent on S-2.** This feature ships independent of S-2.
- **Disaster-recovery path** (user clicks 6_Sync.py "Rebuild Search Index" after an interrupted extraction): **dependent on S-2.** Today's `os_manager.reindex_from_sqlite` silently drops extracted content for inbound docs (the `_id` lookup mismatch that S-2 fixes). Until S-2 ships, the recovery contract is:
  - Re-clicking "Run extraction" reprocesses any doc with `has_text=0` in SQLite — handles most interrupt scenarios.
  - The edge case of `has_text=1` in SQLite + missing content in OS (mid-batch interrupt) is not recoverable via re-click; user must wait for S-2 to ship, then click "Rebuild Search Index".

### OS helper coordination

`compute_os_id` (this spec, in `os_manager.py`) and `cn_from_hit` (S-2 spec, also in `os_manager.py`) are paired helpers for the two directions. Either can ship first; the second-shipping spec just imports the first.

---

## 11. Future enhancements (explicitly out of MVP scope)

| Enhancement | Defer rationale |
|-------------|-----------------|
| Force-reextract of docs that already have text | YAGNI — no current use case. Easy to add later as a checkbox before the "Run extraction" button. |
| Background-worker model | YAGNI — the maintainer chose user-trigger / defer-overnight model explicitly. Synchronous loop matches the 6_Sync.py rebuild pattern. |
| OCR of `.msg`/`.eml` inbound attachments | Out of scope — current spec scopes to flat doc extraction. Email parsing for inbound is its own complexity. |
| Per-doc cancel mid-run | YAGNI — case-wide button is atomic-per-doc; user can close the tab to abort and re-click later to resume. |
| OCR quality scoring / language detection / image preprocessing | YAGNI — Tesseract's defaults are the baseline; revisit if quality complaints surface empirically. |
| Auto-detection of inbound vs internal at button-time | N/A — button is explicitly inbound-scoped via the SQL filter (`source_party != 'Internal'`). |

---

## 12. Permission gate

`# permission: extract_inbound_text` — manager+. Matches the inbound ingest pattern (inbound ingest is itself manager-gated; extraction is the same hazard class).

Closed-case posture: per CLAUDE.md §Key Architecture Rules, render the UI section with the button disabled and a banner explaining the case is closed. Do NOT `st.stop()`.

---

## 13. Files touched (for plan-writing reference)

| File | Action |
|------|--------|
| `processing_engine.py` | +2 functions (`extract_inbound_doc`, `extract_all_pending_inbound`); add `InboundExtractionAborted` exception class. |
| `db_manager.py` | +2 functions (`get_inbound_docs_pending_extraction`, `update_inbound_extraction_state`). |
| `os_manager.py` | +1 helper (`compute_os_id`). |
| `pages/9_InboundProduction.py` | +1 UI section (~60-80 lines). Refactor L453 inline `_ib_opensearch_id` assignment to call `os_manager.compute_os_id(...)` (single-line replacement; preserves behavior). |
| `config.py` + `config.example.py` | +2 settings (`EXTRACTION_MIN_CHARS`, `EXTRACTION_OS_BATCH_SIZE`). |
| `tests/test_inbound_extraction.py` | NEW, ~8 unit tests. |
| `tests/test_inbound_extraction_e2e.py` | NEW, 1 integration test with seeded case. |
| `CHANGELOG.md` | NEW + CHANGE entries per Version Tracking rules. |
| `DEPENDENCY_MAP.md` | Add the new shared functions to §3 (shared function signatures) and update §4 (OpenSearch indexed fields — `extraction_method` field gets a row if not present). |

No new files outside `tests/`.

---

## 14. References

- `pages/9_InboundProduction.py` — existing inbound ingest module; L222-487 the load-file-driven ingest loop, L453 the inline `_ib_opensearch_id` pattern this spec lifts.
- `processing_engine.py:130-178` — `_ocr_fallback` (PyMuPDF + Tesseract).
- `processing_engine.py:179-235` — `get_tika_data` (Tika with internal OCR fallback chain).
- `os_manager.py:118-260` — `reindex_from_sqlite` (signature mirror reference).
- `pages/6_Sync.py` — "Rebuild Search Index" button (UX pattern mirror).
- `docs/lessons/extraction-rendering-symmetry.md` — shared-predicate pattern this spec follows for `compute_os_id`.
- `docs/lessons/atomic-multi-table-writes.md` — atomic per-doc write discipline.
- `docs/references/PYMUPDF_PATTERNS.md` — `fitz.open()` + rendering reference.
- `docs/references/TIKA_METADATA_KEYS.md` — Tika metadata fields including `extracted_with`.
- `docs/references/OPENSEARCH_PATTERNS.md` — bulk-update API and `_id` conventions.
- `docs/FLAG_REGISTRY.md` Flag #28 — the OS `_id` shape mismatch this spec assumes correct.
- CLAUDE.md §PST Extraction Architecture — confirms `extraction_notes` column existence; reuse rule.
- CLAUDE.md §Access Gate Convention — for the `extract_inbound_text` permission naming.

---

## 15. Implementation order recommendation (for writing-plans phase)

1. `os_manager.compute_os_id` + tests + refactor L453 callsite (1 commit; opens the door for both this spec and S-2).
2. `db_manager.get_inbound_docs_pending_extraction` + `db_manager.update_inbound_extraction_state` + tests (1 commit; pure data-layer additions).
3. `processing_engine.extract_inbound_doc` + unit tests (1 commit; pure function on doc_row).
4. `processing_engine.extract_all_pending_inbound` + integration test (1 commit; orchestrator wiring).
5. `pages/9_InboundProduction.py` UI section + permission gate + audit events + config additions + `DEPENDENCY_MAP.md` update + `CHANGELOG.md` entries (1 commit; the user-visible feature).

5 commits, each individually revertable. The full sequence ships as a feature arc in a sprint branch.
