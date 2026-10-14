# Preflight — Family-Grouped Hybrid Native Export

**Anchor:** `beta-2.15` (drafted 2026-05-18).

**Purpose:** Add an export mode that emits family-grouped ZIPs containing
parent emails as imaged PDFs and attachments in their native format, with
filename prefixes that cause alphabetical sort to cluster families. Use case:
extracting reviewed/produced material out of the platform for upload into a
downstream case-management system (Filevine) where Bates stamping is not
wanted and family relationships must remain visible in the file list.

**Scope posture:** Strategic — adds a new product feature surface to a
production code module. PM proposes; the maintainer greenlights; CLI executes.

---

## §0 — Greenlight Gate

Standard N-Stage Gate per `docs/lessons/n-stage-gate-revision-handling.md`:

1. The maintainer's Stage 1 review of this preflight.
2. CLI pre-flight check, reports findings.
3. PM revises if needed (each revision triggers a fresh delta-scoped CLI
   re-check — patch and greenlight never ship in the same message).
4. The maintainer's Stage 2 greenlight in a separate message.
5. CLI executes, reports post-execution verification.

---

## §1 — Extraction Inventory

### 1.1 Files touched

| File | Action | LOC delta (estimate) | Summary |
|------|--------|----------------------|---------|
| `pdf_exporter.py` | MODIFY | +60 | Add `hybrid` file_source; add `family_prefix` naming mode; refactor `_resolve_source_path` to dispatch on `parent_id`; new `_build_family_prefix_filename` helper |
| `pages/4_Review.py` | MODIFY | +20 | Add "Hybrid (parents PDF, children native)" to source-map dropdown; add "Family prefix" checkbox in the bulk-export form |
| `tests/test_pdf_exporter.py` | CREATE or MODIFY | +30 | Smoke tests for hybrid path resolution and prefix generation |

Estimated total: ~110 LOC across three files. Falls into the "non-trivial
refactor with behavior change" tier — full 8-section template warranted.

### 1.2 Schema fields the change relies on

All already present in `documents`:

- `control_number` (TEXT, UNIQUE) — primary key
- `parent_id` (TEXT, nullable) — NULL = parent or standalone; NOT NULL = attachment child
- `group_id` (TEXT) — family/thread group; migration at `db_manager.py:380` guarantees `group_id = control_number` for parents/standalones
- `file_name` (TEXT) — original filename
- `file_extension` (TEXT) — original extension

No schema migration. No new columns. No new indexes (the existing covering
queries are adequate).

### 1.3 Existing functions touched

| Function | File | Change |
|----------|------|--------|
| `_resolve_source_path` | `pdf_exporter.py:63` | Add `hybrid` branch. For `parent_id IS NULL`, route to `processed` path; for `parent_id IS NOT NULL`, route to `native` path. |
| `_build_zip_filename` | `pdf_exporter.py:128` | Accept optional `family_prefix` kwarg. When provided, prepend `FAM-{NNNN}_{MM}_` (family member) or `SOLO-{NNNN}_` (standalone). |
| `export_pdfs_to_zip` | `pdf_exporter.py:205` | Accept new `family_prefix` parameter. Pre-compute family-numbering map from the input control_numbers (group_id → 4-digit ordinal). |
| Bulk export form | `pages/4_Review.py:3125-3169` | Add UI affordances. New entry in `source_map_grid`. New checkbox. |

### 1.4 New helper functions

| Function | Location | Purpose |
|----------|----------|---------|
| `_compute_family_numbering(rows)` | `pdf_exporter.py` (new) | Group rows by group_id; assign FAM-NNNN to multi-member families, SOLO-NNNN to singletons; return dict {control_number: (prefix_token, member_ordinal)} |
| `_build_family_prefix_filename` | `pdf_exporter.py` (new) | Variant of `_build_zip_filename` that prepends the family prefix and preserves the original extension instead of forcing `.pdf` |

### 1.5 Closure / external references

None new — `_resolve_source_path` already has access to `case_folder` and
`row`; the new hybrid branch composes existing logic.

### 1.6 Imports

No new top-level imports. `re` and `os` already present.

---

## §2 — Signature Proposal

### 2.1 New parameter on `export_pdfs_to_zip`

```python
def export_pdfs_to_zip(
    case_folder: str,
    control_numbers: list,
    file_source: str,                    # "processed" | "native" | "produced" | "hybrid"
    naming_field: str,
    append_extension: bool,
    prefix_sequential: bool,
    combine_families: bool,
    family_prefix: bool = False,         # NEW
) -> tuple:
```

Default `False` preserves existing call sites. New callers opt in.

### 2.2 `combine_families` × `family_prefix` interaction

These are mutually exclusive — `combine_families` merges into one PDF (no
filenames to prefix), `family_prefix` keeps families as separate files with
a shared prefix. The UI should disable one when the other is checked. The
function should raise `ValueError` if both are `True`.

### 2.3 `file_source="hybrid"` × `combine_families=True` interaction

Hybrid means mixed file types in a family (PDF parent + XLSX child). The
existing PyMuPDF-based `_merge_family_pdfs` cannot merge non-PDF. Three
options:

- **Option A (recommended):** Disallow the combination — raise
  `ValueError("combine_families is not supported with hybrid source")`.
  Forces the user to pick: merge everything to PDF (use `processed` source +
  combine_families) OR keep natives separate (use `hybrid` source +
  family_prefix).
- Option B: Silently fall back to `processed` for the merge.
- Option C: Image-convert natives before merging (expensive, lossy for
  spreadsheets, defeats the user's reason for choosing hybrid).

Recommend A. State explicitly in the docstring.

### 2.4 Family prefix format

```
FAM-{NNNN}_{MM}_<sanitized_filename>.<ext>     # member of a multi-doc family
SOLO-{NNNN}_<sanitized_filename>.<ext>         # standalone (no siblings)
```

- `NNNN`: 4-digit family ordinal (zero-padded), assigned by group_id
  encounter order in the input control_numbers list.
- `MM`: 2-digit member ordinal within family. `00` = parent
  (`parent_id IS NULL`); `01`, `02`, … = attachments sorted by control_number.
- `<sanitized_filename>`: existing `file_name` sanitization logic.
- `<ext>`: original extension when hybrid (parent → `.pdf`, child → native ext).

Sort behavior: alphabetical sort clusters `FAM-0001_*` together, then
`FAM-0002_*`, etc.; all `SOLO-*` rows sort after the family clusters (`F` <
`S` alphabetically). Within a family, parent (`_00_`) sorts first.

---

## §3 — Verdict Backing

### 3.1 Verdict 1 — Backward compatibility

No existing call site passes `family_prefix`; default `False` preserves
current ZIP output byte-for-byte for the three pre-existing source modes.

Grep evidence (run at draft time):
- `export_pdfs_to_zip(` — 1 call site, in `pages/4_Review.py:3152`. Unchanged
  except the new kwarg (which receives default at first).

### 3.2 Verdict 2 — Hybrid path resolution correctness

For hybrid source, `_resolve_source_path` returns:
- Parent (`parent_id IS NULL`): `Processed/{cn}.pdf` (the imaged email)
- Child (`parent_id IS NOT NULL`): `Processed/{cn}{ext}` first, then
  `Ingest/{file_name}` fallback (same as current `native` source)

Standalones (`parent_id IS NULL`, no children): treated as parent → imaged
PDF. This is correct for the email use case (a parentless email is still an
email, image it). It may be unexpected for a non-email standalone (e.g., a
PDF dropped directly into Ingest). Mitigation: standalone behavior is the
same as choosing `processed` source today, which is the safer default for
mixed inputs.

### 3.3 Verdict 3 — Family numbering determinism

`_compute_family_numbering` must assign the same FAM-NNNN on every run
given the same input. Implementation: iterate `control_numbers` in caller
order, record first-occurrence index per group_id, sort group_ids by first
occurrence, assign 0001, 0002, etc.

Test pin: build a fixture with 3 families (A, B, C) in a specific input
order, assert (FAM-0001 == A, FAM-0002 == B, FAM-0003 == C).

---

## §4 — Phase Plan

### Phase A — Core helpers (no UI)

- Add `_compute_family_numbering` and `_build_family_prefix_filename` in
  `pdf_exporter.py`.
- Add `hybrid` branch in `_resolve_source_path`.
- Add `family_prefix` parameter to `export_pdfs_to_zip` (default False,
  no UI consumer yet).
- Pin behavior with unit tests in `tests/test_pdf_exporter.py`.

Verification: `pytest tests/test_pdf_exporter.py` green; call from a Python
REPL to verify a tiny case works end-to-end.

### Phase B — UI wiring

- Add "Hybrid (parents PDF, children native)" to the source dropdown in
  `pages/4_Review.py`'s bulk export form.
- Add "Family prefix" checkbox (mutex with "Combine families").
- Wire the new parameters into the `export_pdfs_to_zip` call.

Verification: launch Streamlit, run the export on a small reviewed case,
inspect the resulting ZIP filenames.

### Phase total table

| Phase | LOC | Risk | Verification |
|-------|-----|------|--------------|
| A | ~75 | Low — pure additions | Pytest + REPL smoke |
| B | ~20 | Low — UI plumbing | Manual Streamlit walk-through |

---

## §5 — Version Bumps + Test Plan

### 5.1 Per-file version bumps

| File | Current version | Proposed | Justification |
|------|-----------------|----------|---------------|
| `pdf_exporter.py` | 1.3.2 | 1.4.0 | New public-facing modes (minor bump for added functionality) |
| `pages/4_Review.py` | (TBD by CLI at execution) | patch | Form wiring only |
| `tests/test_pdf_exporter.py` | (new or existing) | 1.0.0 / patch | Test additions |

`project_ver` stays at `2.14.0` until the maintainer greenlights a 2.15.0 bump on
sprint close.

### 5.2 Test plan

1. **Existing coverage:** verify `tests/test_pdf_exporter.py` (if present)
   still passes against the existing three source modes. Pin output for a
   3-doc fixture using `processed` source pre/post change.
2. **New tests:**
   - `test_compute_family_numbering_deterministic` — 3 families in a fixed
     order produce FAM-0001/0002/0003.
   - `test_hybrid_source_routes_parent_to_pdf` — fixture with parent (PDF
     exists at Processed/{cn}.pdf) and child (native at Processed/{cn}.xlsx);
     hybrid resolves correctly for each.
   - `test_family_prefix_combine_families_mutex` — calling with both
     `family_prefix=True` and `combine_families=True` raises.
   - `test_solo_prefix_for_singletons` — a doc with no siblings gets
     `SOLO-NNNN_` not `FAM-NNNN_`.
3. **Manual UI walkthrough:**
   - Open a reviewed case → Review → select a small
     set with 2-3 families and 1-2 standalones.
   - Export with hybrid source + family prefix.
   - Open the ZIP, sort by name, verify families cluster and parents come
     first within each family.

---

## §6 — Scope-Expansion Probe Responses

### Probe 6.1 — Existing `prefix_sequential` checkbox

Quote: `prefix_sequential` checkbox at `4_Review.py:3136` prepends a
4-digit per-document sequence (`0001_`, `0002_`, etc.).

Does it overlap with family_prefix? No — sequential is per-document, family
is per-group. They could in principle stack (`FAM-0001_00_0042_filename.pdf`),
but that's noisy. Recommendation: when family_prefix is on, disable
prefix_sequential (it's redundant — family prefix already encodes ordering).

### Probe 6.2 — Production module's own ZIP export

`pages/5_Production.py` builds production-volume ZIPs. Does it have an
analogous family grouping problem? Not directly — produced ZIPs are
Bates-stamped and DAT-linked; family relationships are tracked in the
load file (`PARENTID`/`ATTACHIDS` fields), not the ZIP filename. Out of
scope.

### Probe 6.3 — Failure mode if not bundled

The family_prefix feature without the hybrid source is half-useful — you
could prefix a flat native export and still get clustered families in
sort order, but every email comes out as `.eml`/`.msg`, which is what
the maintainer specifically wanted to avoid. Without family_prefix, the hybrid
source emits a flat mix with no family signal in the filename.

These two features are jointly load-bearing for the stated use case.
Three-criteria test: same root cause (Filevine upload UX), same fix
pattern (modify pdf_exporter), same hazard class (export-correctness).
**Bundle both into one preflight, ship in one commit.**

### Probe 6.4 — Adjacent unrelated work

The CHANGELOG lifecycle, version-tag protocol, and Standing Orders are
untouched. No version bump beyond file-level. No DEPENDENCY_MAP change
(no new shared schema/key/path).

### Probe 6.5 — Revised recommendation

Bundle Phase A + Phase B in one commit. Defer Production-module
adjustments (Probe 6.2) — out of scope.

---

## §7 — Line-Number Drift Re-Verification + Rollback

### 7.1 Drift posture

Plan is anchored on `beta-2.15`. Line numbers above were
captured from this snapshot. If execution lands more than one commit
later, CLI re-locates by grep stem:
- `_resolve_source_path` definition
- `_build_zip_filename` definition
- `export_pdfs_to_zip` definition + call site
- `source_map_grid` literal in `4_Review.py`

### 7.2 Rollback plan

`git revert <SHA>` is sufficient. No schema migration, no file-system
state outside git. Existing exports continue to work because all new
parameters default to backward-compatible values.

---

## §8 — Summary / Greenlight Posture

### §8.1 — PM Drafting-Checklist Ledger

| # | Check | Result | Evidence / note |
|---|-------|--------|-----------------|
| 1 | Not-in-git verification | PASS | `git ls-files docs/specs/` confirmed |
| 2 | Scope-expansion probe enumeration | PASS | §6 covers prefix_sequential overlap, Production parity, joint bundling |
| 3 | Line-number drift capture | PASS | Anchor recorded; grep stems listed in §7 |
| 4 | Prior-arc destination check | N/A | No prior arc — first preflight on this feature |
| 5 | Version-bump cascade identification | PASS | §5.1 lists per-file bumps; `project_ver` stays at 2.14.0 |
| 6 | Cross-module impact against DEPENDENCY_MAP | PASS | No shared schema/key/path change |
| 7 | Grep-by-behavior-stem discipline | PASS | §7.1 prescribes grep-stem re-location |
| 8 | Rollback plan | PASS | §7.2 — `git revert` sufficient |
| 9 | Test plan | PASS | §5.2 — unit + manual walkthrough |
| 10 | Permission-gate visibility (strategic touches) | PASS | §0 marks PM-proposes posture; new product feature in production module qualifies as strategic |
| 11 | Grep-count cross-verification | PASS | "1 call site in `4_Review.py:3152`" verified at draft time |

### §8.2 — Verdict matrix

| Audit Item | Verdict | Backing section |
|------------|---------|-----------------|
| Backward compatibility | ✅ | §3.1 |
| Hybrid path resolution | ✅ | §3.2 |
| Family numbering determinism | ✅ | §3.3 |

### §8.3 — Open questions for the maintainer

1. **Singleton non-email behavior:** A PDF or DOCX dropped directly into
   Ingest (not extracted from a PST) will be a singleton parent. Should
   hybrid source image it (current §3.2 recommendation) or keep it native?
   The "emails as PDF" intent argues for keeping non-emails native, but
   detecting "is this an email" reliably requires checking `file_extension`
   or `record_type`. Quick decision needed; default to "image everything
   parentless" is the simpler implementation.

2. **Filename collision when family members share a name:** If two
   attachments to the same email both have `file_name = "image001.png"`
   (common with inline-image extraction), they'll get
   `FAM-0001_01_image001.png` and `FAM-0001_02_image001.png` — the
   member-ordinal prefix already deconflicts them. Confirm this is the
   desired behavior (vs. appending `_1`, `_2` via the existing
   `_deconflict` path).

3. **Production scope:** Should hybrid source be allowed against produced
   documents (`file_source="produced"`)? The Bates-stamped copy is always
   PDF, so hybrid-with-produced collapses to the same as produced. Cleaner
   to forbid the combination than to silently coerce. Recommend disallow.

> Ready for CLI pre-flight check. Proceeding to execution only after CLI
> reports clean AND the maintainer issues Stage 2 greenlight in a separate message
> per N-Stage Gate Standing Order.
