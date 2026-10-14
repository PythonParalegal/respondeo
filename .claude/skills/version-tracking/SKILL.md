---
name: version-tracking
description: Maintain version headers in all .py source files and keep CHANGELOG.md current. Triggered on any file edit.
---

# Version Tracking Conventions

## File Header Format

Every .py file must have this block as the first content after any shebang, encoding declaration, or pyre-ignore directive:

```python
# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        <filename.py>
# version:       <major.minor.patch>
# project:       Respondeo eDiscovery Platform
# project_ver:   <matches __version__ in config.py>
# last_modified: <YYYY-MM-DD HH:MM>
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
```

## Rules for Editing Files

When you modify any .py file:
1. Update `last_modified` to today's date AND time in `YYYY-MM-DD HH:MM` format (24-hour)
2. Set `modified_by` to `claude-code`
3. If the change modifies behavior (not just formatting/comments):
   - Bump the patch number (e.g., 1.0.3 → 1.0.4)
   - Add a one-line CHANGELOG.md entry under the current sprint heading
4. If the change adds a new function, class, or feature:
   - Bump the minor number (e.g., 1.1.4 → 1.2.0), reset patch to 0
5. Always leave `last_commit` as `pending`

When you create a new .py file:
1. Add the full header block with version 1.0.0
2. Set project_ver to match current `__version__` in config.py
3. Add CHANGELOG.md entry: "NEW: <filename> — <purpose>"

## Project Version
- `__version__` in config.py is the project-level version
- NEVER change this unless the human explicitly tells you to
- File-level versions track individual file change history independently

## CHANGELOG.md Format
```
## [sprint-name] — In Progress

### YYYY-MM-DD
- FIX: filename.py — description of fix
- NEW: filename.py — what was added
- CHANGE: filename.py — what changed and why
```

## Files That Do NOT Get Version Headers
- `__init__.py` (empty or near-empty)
- `config.example.py` (template file)
- Anything in `_scratchpad/` (diagnostic/debug scripts)
- Anything in `tests/` (test files don't self-version)
- `.md`, `.yaml`, `.json`, `.txt`, and other non-Python files
