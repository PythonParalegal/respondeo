# Module Hardening Sprints 3-4 (Remaining Work) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add config.py imaging worker default, stale-production detector, and retry/Pass 2 timing metrics to the Production module.

**Architecture:** Three independent changes to 5_Production.py + one line in config.example.py. Each task is self-contained and can be committed independently.

**Tech Stack:** Python, Streamlit, os/glob for file scanning, time.monotonic() for timing.

**Spec:** `docs/superpowers/specs/2026-03-27-hardening-sprints-3-4-design.md`

---

### Task 1: Config.py IMAGING_WORKERS Setting

**Files:**
- Modify: `config.example.py` (add setting after line 31)
- Modify: `pages/5_Production.py` (lines 1967-1971, slider default)

- [ ] **Step 1: Add IMAGING_WORKERS to config.example.py**

After the `LIBREOFFICE_PATH` line (line 31), add:

```python
# --- Performance Tuning ---
# Maximum parallel imaging workers for Production Pass 1.
# 0 = auto-detect: min(4, cpu_count - 1). Set explicitly for fixed deployments.
IMAGING_WORKERS = 0
```

- [ ] **Step 2: Update slider default in 5_Production.py**

Find the slider block (lines 1967-1980). Change the `value=` parameter to read from config:

Replace:
```python
            imaging_workers = st.slider(
                "Imaging Workers (Pass 1)",
                min_value=1,
                max_value=_max_imaging_workers,
                value=min(4, _max_imaging_workers),
```

With:
```python
            _config_workers = getattr(config, 'IMAGING_WORKERS', 0)
            _default_workers = _config_workers if 0 < _config_workers <= _max_imaging_workers else min(4, _max_imaging_workers)
            imaging_workers = st.slider(
                "Imaging Workers (Pass 1)",
                min_value=1,
                max_value=_max_imaging_workers,
                value=_default_workers,
```

- [ ] **Step 3: Update version headers**

- `config.example.py` — This file does NOT get a version header (per CLAUDE.md rules: config.example.py is excluded).
- `pages/5_Production.py` — Patch bump the version. Update `last_modified` to current date/time (`2026-03-27 HH:MM`), `modified_by` to `claude-code`, `last_commit` to `pending`.

- [ ] **Step 4: Add CHANGELOG entry**

Add to a new section in CHANGELOG.md:

```
### Module Hardening Sprints 3-4 (2026-03-27)
- NEW: config.example.py — IMAGING_WORKERS setting for Production Pass 1 parallel worker default (0 = auto-detect)
- CHANGE: 5_Production.py — imaging workers slider reads default from config.IMAGING_WORKERS
```

- [ ] **Step 5: Commit**

```bash
git add config.example.py pages/5_Production.py CHANGELOG.md
git commit -m "feat: IMAGING_WORKERS config setting for Production Pass 1 (Sprint 3)"
```

---

### Task 2: Stale-Production Detector

**Files:**
- Modify: `pages/5_Production.py` (insert between lines 95-97, after case gate and before `st.title`)

- [ ] **Step 1: Add stale-production detection and cleanup UI**

In `5_Production.py`, find the block:

```python
elif _case_closed:
    st.warning('🔒 This matter is closed. Downloads are available below.')

st.title("Module 5: Production & Export 📦")
```

Insert the following BETWEEN those two blocks (after the `elif` block ends, before `st.title`):

```python
# ── Stale-Production Detector ────────────────────────────────────────────────
_productions_dir = os.path.join(case_folder, "Productions")
if os.path.isdir(_productions_dir) and not _case_closed:
    _stale_volumes = []
    for _vol_name in os.listdir(_productions_dir):
        _vol_path = os.path.join(_productions_dir, _vol_name)
        if not os.path.isdir(_vol_path):
            continue
        _images_dir = os.path.join(_vol_path, "IMAGES")
        _natives_dir = os.path.join(_vol_path, "NATIVES")
        _temp_count = 0
        _staged_count = 0
        if os.path.isdir(_images_dir):
            _temp_count = sum(1 for f in os.listdir(_images_dir) if f.startswith("TEMP_"))
        if os.path.isdir(_natives_dir):
            _staged_count = sum(1 for f in os.listdir(_natives_dir) if f.startswith("STAGED_"))
        if _temp_count > 0 or _staged_count > 0:
            _stale_volumes.append((_vol_name, _vol_path, _temp_count, _staged_count))

    if _stale_volumes:
        _stale_summary = ", ".join(
            f"**{v[0]}** ({v[2]} temp, {v[3]} staged)" for v in _stale_volumes
        )
        st.warning(
            f"Orphaned files from abandoned productions detected: {_stale_summary}. "
            f"These are leftover from a Pass 1 that did not complete."
        )
        # permission: production
        if auth_manager.has_permission('production'):
            if st.button("Clean Up Orphaned Files", key="stale_cleanup"):
                _cleaned_files = 0
                _cleaned_folders = 0
                for _vol_name, _vol_path, _tc, _sc in _stale_volumes:
                    _images_dir = os.path.join(_vol_path, "IMAGES")
                    _natives_dir = os.path.join(_vol_path, "NATIVES")
                    # Remove TEMP_ files
                    if os.path.isdir(_images_dir):
                        for f in os.listdir(_images_dir):
                            if f.startswith("TEMP_"):
                                os.remove(os.path.join(_images_dir, f))
                                _cleaned_files += 1
                    # Remove STAGED_ files
                    if os.path.isdir(_natives_dir):
                        for f in os.listdir(_natives_dir):
                            if f.startswith("STAGED_"):
                                os.remove(os.path.join(_natives_dir, f))
                                _cleaned_files += 1
                    # If folder is now effectively empty (only empty subdirs), remove it
                    _remaining = sum(
                        len(files) for _, _, files in os.walk(_vol_path)
                    )
                    if _remaining == 0:
                        shutil.rmtree(_vol_path)
                        _cleaned_folders += 1
                try:
                    db_manager.log_audit(
                        case_folder, "PRODUCTION_STALE_CLEANUP",
                        username=_username, module="Production",
                        details=json.dumps({
                            "volumes": [v[0] for v in _stale_volumes],
                            "files_removed": _cleaned_files,
                            "folders_removed": _cleaned_folders,
                        })
                    )
                except Exception:
                    pass
                st.success(
                    f"Cleaned up {_cleaned_files} orphaned files"
                    + (f" and {_cleaned_folders} empty folders" if _cleaned_folders else "")
                    + "."
                )
                st.rerun()

```

- [ ] **Step 2: Verify shutil import exists**

Check that `import shutil` is already in the imports at the top of `5_Production.py`. It should be (used in Pass 1 for file copying).

- [ ] **Step 3: Update version header in 5_Production.py**

Patch bump. Update `last_modified`, `modified_by`, `last_commit`.

- [ ] **Step 4: Add CHANGELOG entry**

```
- NEW: 5_Production.py — stale-production detector: scans for orphaned TEMP_/STAGED_ files from abandoned Pass 1 runs, shows cleanup button with audit logging
```

- [ ] **Step 5: Commit**

```bash
git add pages/5_Production.py CHANGELOG.md
git commit -m "feat: stale-production detector for orphaned temp files (Sprint 4)"
```

---

### Task 3: Retry and Pass 2 Timing Metrics

**Files:**
- Modify: `pages/5_Production.py` (retry function ~lines 514-609, finalize function ~lines 632-1744)

- [ ] **Step 1: Add timing to retry loop**

In `_handle_retry()` (line 514), add `import time as _retry_time` and timing:

Find line 525:
```python
        _retry_workers = min(p1.get('imaging_workers', 1), len(retryable))
```

Add BEFORE it:
```python
        import time as _retry_time
        _retry_start = _retry_time.monotonic()
```

Find the `PRODUCTION_RETRY` audit log call (lines 600-607):
```python
        db_manager.log_audit(p1['case_folder'], "PRODUCTION_RETRY",
            username=p1['username'], module="Production",
            details=json.dumps({
                "volume": p1['prod_name'],
                "docs_retried": len(retryable),
                "newly_succeeded": _newly_succeeded,
                "workers": _retry_workers,
            }))
```

Add timing to the details dict — replace with:
```python
        _retry_elapsed = _retry_time.monotonic() - _retry_start
        db_manager.log_audit(p1['case_folder'], "PRODUCTION_RETRY",
            username=p1['username'], module="Production",
            details=json.dumps({
                "volume": p1['prod_name'],
                "docs_retried": len(retryable),
                "newly_succeeded": _newly_succeeded,
                "workers": _retry_workers,
                "elapsed_seconds": round(_retry_elapsed, 1),
            }))
```

- [ ] **Step 2: Add timing to Pass 2**

In `_handle_finalize()` (line 632), add timing at the start of the function body.

Find line 633 (the docstring):
```python
    def _handle_finalize():
        """Pass 2 — Sequential assembly. Assigns Bates numbers, burns redactions,
        stamps, extracts text, generates load files. This is the legally significant pass."""
```

Add AFTER the docstring (before the first line of function body):
```python
        import time as _pass2_time
        _pass2_start = _pass2_time.monotonic()
```

Find the `PRODUCTION_EXPORTED` audit log (line 1574):
```python
        db_manager.log_audit(case_folder_path, "PRODUCTION_EXPORTED", username=_prod_username,
            module="Production", details=json.dumps({
                "volume": prod_name, "format": prod_format,
                "mode": prod_mode,
                "sort_by_folder": _sort_by_folder,
                "output_path": prod_path, "doc_count": len(prod_data),
                "bates_start": _bates_start, "bates_end": _bates_end
            }))
```

Add `elapsed_seconds` to the details dict — replace with:
```python
        _pass2_elapsed = _pass2_time.monotonic() - _pass2_start
        db_manager.log_audit(case_folder_path, "PRODUCTION_EXPORTED", username=_prod_username,
            module="Production", details=json.dumps({
                "volume": prod_name, "format": prod_format,
                "mode": prod_mode,
                "sort_by_folder": _sort_by_folder,
                "output_path": prod_path, "doc_count": len(prod_data),
                "bates_start": _bates_start, "bates_end": _bates_end,
                "pass2_elapsed_seconds": round(_pass2_elapsed, 1),
            }))
```

- [ ] **Step 3: Update version header in 5_Production.py**

Patch bump. Update `last_modified`, `modified_by`, `last_commit`.

- [ ] **Step 4: Add CHANGELOG entries**

```
- CHANGE: 5_Production.py — retry loop timing: elapsed_seconds added to PRODUCTION_RETRY audit event
- CHANGE: 5_Production.py — Pass 2 timing: pass2_elapsed_seconds added to PRODUCTION_EXPORTED audit event
```

- [ ] **Step 5: Commit**

```bash
git add pages/5_Production.py CHANGELOG.md
git commit -m "feat: retry and Pass 2 timing metrics in audit log (Sprint 4)"
```

---

### Task 4: Context Maintenance + Documentation

**Files:**
- Modify: `CLAUDE.md` (Current State table)
- Modify: `ROADMAP_TODO.md` (mark Sprint 3-4 items complete)
- Modify: `CHANGELOG.md` (DOCS entry if needed)
- Update: all four documentation files for new features

- [ ] **Step 1: Mark Sprint 3-4 items complete in ROADMAP_TODO.md**

Find the Sprint 3 and Sprint 4 items (around lines 598-604) and mark them complete:

```
Sprint 3  [x]   Replace sequential Pass 1 loop with ProcessPoolExecutor (max_workers = min(6, cpu_count//2))
          [x]   Update progress reporting to use as_completed() pattern
          [x]   Test on production-scale document set; monitor memory + COM subprocess count
          [x]   Optionally expose max_workers as config.py setting
Sprint 4  [x]   Stale-production detector (orphaned temp files from abandoned Pass 1)
          [x]   Timing metrics (Pass 1 / retry / Pass 2 durations) in audit log
          [x]   Update DEPLOYMENT_GUIDE.md and User_Guide.md with new workflow
```

- [ ] **Step 2: Update CLAUDE.md Current State table**

Update:
- `Last completed sprint` → `Module Hardening Sprints 3-4 (beta-2.9)`
- `What's next` → `See ROADMAP_TODO.md — Module Hardening function decomposition, Holistic Audit Passes 3-9`

- [ ] **Step 3: Update documentation files**

Add brief mentions of:
- `config.example.py` IMAGING_WORKERS setting in Technical Overview and User Guide
- Stale-production detector in User Guide (Production section) and Technical Overview
- Timing metrics in Technical Overview (audit logging section)

- [ ] **Step 4: Update memory/project_state.md**

Update to reflect completed Sprint 3-4 and what's next.

- [ ] **Step 5: Add CHANGELOG entry and commit**

```
- DOCS: CLAUDE.md — context maintenance after Module Hardening Sprints 3-4
```

```bash
git add CLAUDE.md ROADMAP_TODO.md CHANGELOG.md Walkthrough.md "Technical Overview.md" User_Guide.md PROJECT_CONTEXT.md
git commit -m "docs: context maintenance after Module Hardening Sprints 3-4"
```
