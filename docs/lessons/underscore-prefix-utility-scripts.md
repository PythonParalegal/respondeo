# Underscore-Prefix Utility Scripts

**One-sentence summary:** The `_name.py` filename convention marks utility and migration scripts that are excluded from version-header requirements and CHANGELOG entries.

## The pattern

Python projects accumulate one-shot scripts: recon probes, data-migration helpers, diagnostic crawlers, ad-hoc patches. These scripts are valuable — they record how a specific problem was investigated, and git history gives a forensic trail when a later question arises. But they are not platform code. Requiring them to carry the same version-header metadata, CHANGELOG entries, and review discipline as live application modules creates friction that discourages writing them at all, which makes future forensic trails poorer.

The convention: a leading underscore in the filename (`_name.py`) marks the file as a utility/migration script. These files are still tracked in git (they have forensic value), still Python-lint-clean (they'll be read by humans later), and still expected to function when run. What they don't carry:

- No module metadata header (the `# ─── MODULE METADATA ────` block).
- No per-file CHANGELOG entry when introduced or modified.
- No version bumping discipline.
- No MEMORY.md update.
- No CLAUDE.md cross-reference.

The distinction is about operational reachability. A file without underscore prefix is reached during normal app operation — a page, a worker, a module imported by live code. A file with underscore prefix is reached only when someone explicitly runs it (usually a CLI invocation or one-shot Python call). `_pst_worker.py` is an edge case: the underscore signals "worker helper" but it is called by live code during PST extraction, so it gets version headers despite the prefix. Most `_*.py` files are truly one-shot and get no headers.

Utility scripts still belong in git because they document methodology. A recon script that crawls PDFs for annotations, a migration script that rewrites one schema version to another, a diagnostic probe that dumps libpff internals — each one becomes evidence later when someone asks "how did we handle that case?" Keeping them in git (tracked, not gitignored) preserves the trail.

## Concrete example

**Sprint:** beta-2.10 annotation reconciliation.

A batch of annotated PDFs needed reconciling against the case database. A one-shot script was needed to crawl every annotation, extract the Bates number from each annotated page, cross-reference against the database, and produce a CSV report.

The task description explicitly scoped the script as non-platform code:

> **This is a one-time bridge tool — NOT a permanent platform module.** No module metadata header, no CHANGELOG entry, no CLAUDE.md/MEMORY.md updates. Save it as `_recon_annotation_scan.py` in the project root (underscore prefix = utility/migration script convention).

The script ran once, produced its report, and remained in git. It is not imported by any live code; it is not on any execution path the app hits. A future annotation reconciliation can look at this script to understand the methodology used for the previous one, without the script needing to be kept up-to-date with the live platform.

Contrast with `_pst_worker.py`: the underscore signals "subprocess worker helper," but the file is launched by `subprocess.Popen` from `container_exploder.py` during live PST extraction. Live code reachability makes it platform code, so it carries full module metadata despite the prefix.

## How to apply

- When creating a new `.py` file, ask: "Is this reached by normal app operation?" If no, prefix with underscore and skip the metadata-header / CHANGELOG / MEMORY dance. If yes, no underscore (or underscore but with full headers, like `_pst_worker.py`).
- Utility scripts still get tracked in git. Do not add to `.gitignore` unless the file contains secrets or is genuinely scratchpad-quality.
- Scripts at project root with underscore prefix: `_recon_*.py` (reconnaissance), `_migrate_*.py` (data migrations), `_diagnose_*.py` (diagnostic probes). Names should be self-explanatory; reviewers and future-me should be able to tell the purpose from the filename.
- When a utility script starts to be called by live code, either re-home it without the underscore prefix OR add full metadata headers. The prefix-without-headers-but-called-by-live-code state is the confusing one.

## See also

- **Related lessons:** `docs/lessons/batch-commit-discipline.md`
- **Relevant code:** `_pst_worker.py` (edge case with headers), `_recon_annotation_scan.py` (canonical utility script)
