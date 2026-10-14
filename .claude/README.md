# .claude/

Project configuration for Claude Code sessions.

## Enabling the hooks

`.claude/settings.json` is gitignored (it is per-machine). To register the
hooks in a fresh clone, copy the example and adjust the `python` command if
your interpreter lives elsewhere (e.g. `.venv/Scripts/python.exe` on Windows):

```bash
cp .claude/settings.example.json .claude/settings.json
```

This registers:

- `hooks/session_refresher.py` (SessionStart): injects `refresher.md`.
- `hooks/trigger_injector.py` (UserPromptSubmit, PreToolUse): keyword
  reminders from `triggers.py`.

The git pre-commit checks (`hooks/precommit_check1.py`,
`hooks/precommit_pii_guard.py`) are installed separately:

```bash
bash .claude/hooks/install_precommit.sh
```

Optional: put extra project-specific deny-list regexes in
`.claude/hooks/pii_denylist.local.txt` (gitignored; see
`pii_denylist.example.txt`).
