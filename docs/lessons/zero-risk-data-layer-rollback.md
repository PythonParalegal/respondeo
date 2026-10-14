# Zero-Risk Data-Layer Rollback

**One-sentence summary:** When refactoring a data layer, preserve the persisted format so old and new code can both read each other's writes — that interchangeability is what makes the refactor revertable with zero data loss.

## The pattern

A refactor that changes both the code and the data format it persists is a refactor that cannot be cleanly reverted. If the new code writes data in a new format, reverting the code strands the new-format data in a database the old code does not understand. The only recovery is a forward-only migration that rewrites the data, which is itself a risk surface and requires a second commit.

The zero-risk design splits the concerns. The refactor changes the UI, the logic, the layering, the names — whatever it wants — but the persisted format stays exactly the same. Old code and new code both read and write the same records. `git revert` on the refactor works cleanly because no data-shaped dependency was introduced. Any accumulated data written by the new code is still readable by the pre-revert code.

When the data format itself must change, that migration is a separate, forward-and-backward-compatible commit that ships before the refactor and stays revertable on its own terms. The rule is "never bundle a storage-format change with a logic/UI change in the same commit." If both must happen, the format migration is either reversible (both read paths tolerate both formats for a transition period) or shipped as its own commit with its own rollback plan.

Before accepting a refactor commit, ask: "Could I `git revert` this commit right now and have the system keep working with existing data?" If the answer is no, the refactor has ordering constraints the design must acknowledge, and those constraints belong in the commit message or the preflight doc.

## Concrete example

**Sprint:** beta-2.7 interactive redaction viewer (`docs/specs/SPEC_interactive_redaction_viewer.md`).

The sprint replaced `streamlit-drawable-canvas` with a custom Streamlit bidirectional React component (`RedactionViewer`). The UI layer changed substantially — new React component, new SVG-based rendering, new zoom/pan behavior, new coordinate conversion code inside the component. The spec's explicit stated goal (line 19):

> Replace `st_canvas` with a custom Streamlit bidirectional component (`RedactionViewer`) that provides an interactive, modern document review experience **while preserving the existing backend (database schema, coordinate system, imaging pipeline, production burn chain) exactly as-is.**

Specifically, the `redaction_marks` table continues to store coordinates as `pdf_x0, pdf_y0, pdf_x1, pdf_y1` floats in PDF points (72 DPI). The old code (`st_canvas`-based) wrote PDF points. The new code (custom component) writes PDF points. A case database with accumulated redaction marks survives reverting the UI refactor with no data loss — both code paths understand the stored format.

The spec also calls out that the new component keeps scale-conversion and pixel coordinates *internal* to the React layer and never lets them reach the database. That boundary discipline is what makes the refactor reversible: the data layer never sees the new representation, so the new representation has no durable footprint.

## How to apply

- Before starting a refactor, identify the data surfaces the code touches: SQLite tables, file paths, session-state keys, OpenSearch fields, network protocols. List each with its current persisted format.
- For each data surface, decide: stays same, changes, or extends. Any surface marked "changes" is a format migration that ships as its own commit or extends into a compat shim.
- When the refactor's design phase ends, the refactor should touch zero persisted formats. If it still does, re-split the work into a data-migration commit plus a logic/UI refactor commit.
- Tests that exercise the refactor should include a "legacy data" fixture: a small dataset saved before the refactor started, loaded into the new code, with assertions that the new code produces identical output.
- In code review, look for schema migrations bundled with behavior changes. Flag and request splitting.

## See also

- **Related lessons:** `docs/lessons/atomic-multi-table-writes.md`, `docs/lessons/batch-commit-discipline.md`
- **Source:** `docs/specs/SPEC_interactive_redaction_viewer.md` §1 (goal statement), §5.3 (coordinate system), §5.4 (data-layer preservation claim)
- **Relevant code:** `components/redaction_viewer/` (the custom component), `redaction_marks` table in `db_manager.py`
