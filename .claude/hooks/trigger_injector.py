"""UserPromptSubmit + PreToolUse hook: scans for trigger keywords and
injects reminder context into the model's context.

Reads JSON event payload from stdin per Claude Code hook contract:
  - UserPromptSubmit: {"prompt": "...", "session_id": "...", ...}
  - PreToolUse:       {"tool_name": "...", "tool_input": {...}, "session_id": "...", ...}

Outputs JSON to stdout:
  {
    "continue": true,
    "systemMessage": "[Triggers fired: id1, id2]",
    "hookSpecificOutput": {
      "hookEventName": "<UserPromptSubmit|PreToolUse>",
      "additionalContext": "[Triggers fired: ...]\n\n--- id1 ---\n<reminder1>..."
    }
  }

CONTRACT (2026-06-10 fix — see docs/specs/library_self_correction_design.md
§3.1 post-ship correction): `systemMessage` renders in the terminal UI for the
user and NEVER reaches the model. Model-side context injection requires
`hookSpecificOutput.additionalContext`. Likewise the UserPromptSubmit input
field is `prompt` (the original implementation read `user_prompt`, which
made prompt-scope triggers scan an empty string). Both halves of the
contract are pinned by `.claude/hooks/tests/test_trigger_injector.py`.

Noise control: a trigger id that already fired for this session within the
last DEDUP_TTL_SECONDS is suppressed, so a themed work session (e.g. an
afternoon of Review-page edits) injects each reminder once per TTL window
instead of on every tool call. State lives in a per-session temp file.
Test overrides: TRIGGER_STATE_DIR_OVERRIDE (state dir),
TRIGGER_DEDUP_TTL_OVERRIDE (TTL seconds; 0 disables dedup).

Failure mode: any exception -> log to stderr, exit 0 with {"continue": true}.
A broken hook MUST NOT brick the session.

See docs/specs/library_self_correction_design.md §3.1 and §11.
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
import traceback
from importlib import util
from pathlib import Path

DEDUP_TTL_SECONDS = 1800  # same trigger id refires after 30 min


def _load_triggers():
    """Load .claude/triggers.py from the project root (cwd or hook dir parent)."""
    triggers_path = Path(__file__).resolve().parent.parent / "triggers.py"
    spec = util.spec_from_file_location("_triggers", triggers_path)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TRIGGERS


def _extract_scan_text(event, payload):
    """Return the string to scan for keyword matches based on event type."""
    if event == "UserPromptSubmit":
        # Documented field is "prompt"; "user_prompt" kept as a defensive
        # fallback in case of older payload shapes.
        return payload.get("prompt") or payload.get("user_prompt") or ""
    if event == "PreToolUse":
        tool_input = payload.get("tool_input", {})
        if isinstance(tool_input, dict):
            return " ".join(str(v) for v in tool_input.values())
        return str(tool_input)
    return ""


def _scope_matches_event(scope, event):
    """A trigger's scope determines which events it fires on."""
    if scope == "both":
        return True
    if scope == "prompt":
        return event == "UserPromptSubmit"
    if scope == "tool":
        return event == "PreToolUse"
    return False


def _match_triggers(text, event, triggers):
    """Return list of (id, reminder) tuples for triggers that matched."""
    matches = []
    for entry in triggers:
        if not _scope_matches_event(entry.get("scope", "both"), event):
            continue
        for pattern in entry.get("patterns", []):
            if re.search(pattern, text, re.IGNORECASE):
                matches.append((entry["id"], entry["reminder"]))
                break
    return matches


def _state_path(session_id):
    """Per-session dedup state file in the temp dir (or test override dir)."""
    base = os.environ.get("TRIGGER_STATE_DIR_OVERRIDE") or tempfile.gettempdir()
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id))[:64] or "default"
    return Path(base) / f"claude_trigger_state_{safe}.json"


def _filter_recently_fired(matches, session_id):
    """Drop trigger ids that fired within the TTL window for this session;
    record the survivors as fired-now. Never raises — on any state error,
    fall back to firing everything (a duplicate reminder beats a lost one)."""
    try:
        ttl = float(os.environ.get("TRIGGER_DEDUP_TTL_OVERRIDE", DEDUP_TTL_SECONDS))
        if ttl <= 0:
            return matches
        path = _state_path(session_id)
        now = time.time()
        state = {}
        if path.exists():
            state = json.loads(path.read_text(encoding="utf-8"))
        fresh = [m for m in matches if now - state.get(m[0], 0) >= ttl]
        if fresh:
            for m in fresh:
                state[m[0]] = now
            path.write_text(json.dumps(state), encoding="utf-8")
        return fresh
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return matches


def _format_context(matches):
    """Build the additionalContext string injected into the model's context."""
    ids = ", ".join(m[0] for m in matches)
    blocks = "\n\n".join(f"--- {m[0]} ---\n{m[1]}" for m in matches)
    return f"[Triggers fired: {ids}]\n\n{blocks}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True,
                        choices=["UserPromptSubmit", "PreToolUse"])
    args = parser.parse_args()

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"continue": True}))
        return 0

    try:
        triggers = _load_triggers()
        text = _extract_scan_text(args.event, payload)
        matches = _match_triggers(text, args.event, triggers)
        matches = _filter_recently_fired(matches, payload.get("session_id", "default"))
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"continue": True}))
        return 0

    if not matches:
        print(json.dumps({"continue": True}))
        return 0

    ids = ", ".join(m[0] for m in matches)
    output = {
        "continue": True,
        # User-visible audit header only (terminal UI; never reaches the model).
        "systemMessage": f"[Triggers fired: {ids}]",
        # What the model actually receives.
        "hookSpecificOutput": {
            "hookEventName": args.event,
            "additionalContext": _format_context(matches),
        },
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
