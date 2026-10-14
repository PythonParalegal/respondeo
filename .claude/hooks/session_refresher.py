"""SessionStart hook: injects the contents of .claude/refresher.md as
session context, so top recurring misses are in active mind from turn 1.

Reads JSON event payload from stdin (mostly ignored — we just need to
fire on SessionStart).

Outputs JSON to stdout:
  {
    "continue": true,
    "systemMessage": "[session_refresher] refresher.md injected into model context",
    "hookSpecificOutput": {
      "hookEventName": "SessionStart",
      "additionalContext": "<contents of refresher.md>"
    }
  }

CONTRACT (2026-06-10 fix — see docs/specs/library_self_correction_design.md
§3.1 post-ship correction): `systemMessage` renders in the terminal UI for the
user and NEVER reaches the model. Model-side context injection requires
`hookSpecificOutput.additionalContext`. Pinned by
`.claude/hooks/tests/test_session_refresher.py`.

Failure mode: missing or unreadable refresher.md -> log to stderr, exit 0
with {"continue": true}. A broken hook MUST NOT brick the session.

See docs/specs/library_self_correction_design.md §3.2.
"""
import json
import os
import sys
import traceback
from pathlib import Path


def _resolve_refresher_path():
    """Allow REFRESHER_PATH_OVERRIDE for testing; default to project location."""
    override = os.environ.get("REFRESHER_PATH_OVERRIDE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "refresher.md"


def main():
    try:
        sys.stdin.read()
    except Exception:
        pass

    try:
        path = _resolve_refresher_path()
        if not path.exists():
            print(json.dumps({"continue": True}))
            return 0
        contents = path.read_text(encoding="utf-8")
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"continue": True}))
        return 0

    output = {
        "continue": True,
        # User-visible audit line only (terminal UI; never reaches the model).
        "systemMessage": "[session_refresher] refresher.md injected into model context",
        # What the model actually receives.
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": contents,
        },
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
