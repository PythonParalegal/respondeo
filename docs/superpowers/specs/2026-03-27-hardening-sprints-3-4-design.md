# Module Hardening Sprints 3-4 (Remaining Work) — Design Spec

**Date:** 2026-03-27
**Phase:** Module Hardening Sprints 3-4
**Estimated complexity:** ~100 lines changed across config.example.py, 5_Production.py

---

## Problem

Sprint 3's parallelization is already implemented (ProcessPoolExecutor + as_completed + UI slider). Three items remain:

1. The imaging worker count has no config.py default — it's only a per-session UI slider.
2. Orphaned temp files from abandoned productions are never cleaned up.
3. Retry and Pass 2 timing metrics are not logged (Pass 1 timing is).

## Scope

Three small, independent changes to the Production module.

---

## 1. Config.py IMAGING_WORKERS Setting

### config.example.py

Add after the existing tool paths:

```python
# Maximum parallel imaging workers for Production Pass 1.
# 0 = auto-detect: min(4, cpu_count - 1). Set explicitly for fixed deployments.
IMAGING_WORKERS = 0
```

### 5_Production.py

Change the slider's `value=` to read from config:

```python
_config_workers = getattr(config, 'IMAGING_WORKERS', 0)
_default_workers = _config_workers if _config_workers > 0 else min(4, _max_imaging_workers)
```

The slider still appears (useful during development). The config just sets the default. If `IMAGING_WORKERS` is 0 or missing, auto-detection kicks in.

**Future consideration:** The slider was a development tool. In full production deployment, evaluate whether to remove the slider and use config.py exclusively. Not in scope for this sprint.

---

## 2. Stale-Production Detector

### Detection (on page load)

At the top of the Production module (after auth/case gates, before the main UI), scan for orphaned files:

- `TEMP_*.pdf` in `{case_folder}/Productions/*/IMAGES/`
- `STAGED_*.pdf` in `{case_folder}/Productions/*/NATIVES/`

Only flag volumes where Pass 2 has NOT been completed (i.e., no finalized load file exists, or the production_runs record shows no `completed_at`). This avoids false positives on in-progress productions.

**Simplest approach:** Check if any `TEMP_*` or `STAGED_*` files exist in production folders. These should only exist during an active Pass 1 — if Pass 1 completed normally, temps are renamed to final Bates names in Pass 2. If they persist, it means the production was abandoned.

### UI

Show an `st.warning()` banner listing affected volumes and orphan file counts. Include a "Clean Up" button (Manager+) that deletes the orphaned files.

If a production folder contains ONLY temp/staged files and no finalized output, offer to delete the entire folder.

### Audit

Log `PRODUCTION_STALE_CLEANUP` with: volume name, temp file count, staged file count, folders deleted.

---

## 3. Remaining Timing Metrics

### Retry Duration

Wrap the existing retry loop (~lines 537-590) with `time.monotonic()` start/end. Add `elapsed_seconds` to the existing `PRODUCTION_RETRY` audit log details dict.

### Pass 2 Duration

Wrap the Pass 2 block (Bates stamping + load file generation + finalization) with `time.monotonic()` start/end. Log a new `PRODUCTION_PASS2_COMPLETE` audit event with:

```json
{
  "volume": "prod_name",
  "documents": count,
  "elapsed_seconds": 12.3
}
```

This complements the existing `PRODUCTION_PASS1_COMPLETE` event.

---

## Files Changed

- `config.example.py` — add `IMAGING_WORKERS` setting
- `pages/5_Production.py` — slider default from config, stale detector on page load, retry/Pass 2 timing

## Out of Scope

- Removing the slider (future deployment decision)
- Production-scale load testing (manual validation)
- Deployment guide changes (already updated in the recent docs sweep)
