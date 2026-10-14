"""Tests for trigger_injector hook script.

These tests pin the CONSUMER-side Claude Code hook contract, not just the
emitter's behavior — the 2026-06-10 fix exists because the original suite
asserted `systemMessage` (user-UI only, never reaches the model) and fed
the input under `user_prompt` (the documented field is `prompt`), so the
suite passed while the model never received a single reminder.

Contract pinned here:
  - UserPromptSubmit input text arrives under payload["prompt"].
  - Model-side injection is hookSpecificOutput.additionalContext with the
    correct hookEventName; systemMessage is an audit header only.
  - Per-session dedup: same trigger id is suppressed within the TTL window.
"""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

PYTHON = sys.executable
HOOK = str(Path(__file__).resolve().parent.parent / "trigger_injector.py")


def _run_hook(event, payload, env_extra=None):
    """Pipe JSON to the hook script, return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    env.update(env_extra or {})
    proc = subprocess.run(
        [PYTHON, HOOK, "--event", event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _fresh_session(tmp_path):
    """Unique session id + isolated dedup state dir per test."""
    return {
        "session_id": f"test-{uuid.uuid4().hex}",
        "env": {"TRIGGER_STATE_DIR_OVERRIDE": str(tmp_path)},
    }


def _context(data):
    return data.get("hookSpecificOutput", {}).get("additionalContext", "")


def test_no_match_emits_continue_only(tmp_path):
    """Prompt with no trigger keywords -> continue:true, no injection."""
    s = _fresh_session(tmp_path)
    rc, out, err = _run_hook(
        "UserPromptSubmit",
        {"prompt": "Hello, how are you today?", "session_id": s["session_id"]},
        env_extra=s["env"],
    )
    assert rc == 0, f"stderr: {err}"
    data = json.loads(out)
    assert data.get("continue") is True
    assert "hookSpecificOutput" not in data


def test_prompt_match_injects_additional_context():
    """Prompt containing 'preflight' under the DOCUMENTED 'prompt' key ->
    additionalContext carries the reminder; systemMessage is header-only."""
    rc, out, err = _run_hook(
        "UserPromptSubmit",
        {"prompt": "Let's start drafting a preflight for this commit.",
         "session_id": f"test-{uuid.uuid4().hex}"},
    )
    assert rc == 0, f"stderr: {err}"
    data = json.loads(out)
    hso = data.get("hookSpecificOutput", {})
    assert hso.get("hookEventName") == "UserPromptSubmit"
    assert "preflight-drafting" in hso.get("additionalContext", "")
    assert "preflight_drafting_checklist" in hso["additionalContext"]
    assert "[Triggers fired:" in hso["additionalContext"]
    # systemMessage exists for the user's audit trail but is NOT the carrier.
    assert "[Triggers fired:" in data.get("systemMessage", "")


def test_drift_correction_meta_trigger_fires():
    """Prompt with corrective language -> drift-correction-language fires."""
    rc, out, err = _run_hook(
        "UserPromptSubmit",
        {"prompt": "You missed Check 1 on this preflight.",
         "session_id": f"test-{uuid.uuid4().hex}"},
    )
    assert rc == 0, f"stderr: {err}"
    ctx = _context(json.loads(out))
    assert "drift-correction-language" in ctx
    assert "preflight-drafting" in ctx


def test_both_scope_fires_on_prompt_event():
    """A 'both' scope entry like file-archival-or-move fires on prompt that matches."""
    rc, out, err = _run_hook(
        "UserPromptSubmit",
        {"prompt": "I need to git mv this file.",
         "session_id": f"test-{uuid.uuid4().hex}"},
    )
    assert rc == 0, f"stderr: {err}"
    assert "file-archival-or-move" in _context(json.loads(out))


def test_pretooluse_scans_bash_command():
    """PreToolUse with a Bash command containing 'git mv' -> fires file-archival."""
    rc, out, err = _run_hook(
        "PreToolUse",
        {"tool_name": "Bash",
         "tool_input": {"command": "git mv docs/old.md docs/new.md"},
         "session_id": f"test-{uuid.uuid4().hex}"},
    )
    assert rc == 0, f"stderr: {err}"
    data = json.loads(out)
    hso = data.get("hookSpecificOutput", {})
    assert hso.get("hookEventName") == "PreToolUse"
    assert "file-archival-or-move" in hso.get("additionalContext", "")


def test_dedup_suppresses_repeat_fire_within_ttl(tmp_path):
    """Second fire of the same trigger id in the same session is suppressed."""
    s = _fresh_session(tmp_path)
    payload = {"tool_name": "Bash",
               "tool_input": {"command": "git mv docs/a.md docs/b.md"},
               "session_id": s["session_id"]}
    rc1, out1, err1 = _run_hook("PreToolUse", payload, env_extra=s["env"])
    assert rc1 == 0, f"stderr: {err1}"
    assert "file-archival-or-move" in _context(json.loads(out1))

    rc2, out2, err2 = _run_hook("PreToolUse", payload, env_extra=s["env"])
    assert rc2 == 0, f"stderr: {err2}"
    assert "hookSpecificOutput" not in json.loads(out2)


def test_dedup_is_per_session(tmp_path):
    """A different session id refires immediately — dedup state is per session."""
    s = _fresh_session(tmp_path)
    payload = {"tool_name": "Bash",
               "tool_input": {"command": "git mv docs/a.md docs/b.md"},
               "session_id": s["session_id"]}
    _run_hook("PreToolUse", payload, env_extra=s["env"])

    other = dict(payload, session_id=f"test-{uuid.uuid4().hex}")
    rc, out, err = _run_hook("PreToolUse", other, env_extra=s["env"])
    assert rc == 0, f"stderr: {err}"
    assert "file-archival-or-move" in _context(json.loads(out))


def test_dedup_ttl_zero_disables_suppression(tmp_path):
    """TTL override of 0 disables dedup entirely (test/diagnostic knob)."""
    s = _fresh_session(tmp_path)
    s["env"]["TRIGGER_DEDUP_TTL_OVERRIDE"] = "0"
    payload = {"tool_name": "Bash",
               "tool_input": {"command": "git mv docs/a.md docs/b.md"},
               "session_id": s["session_id"]}
    _run_hook("PreToolUse", payload, env_extra=s["env"])
    rc, out, err = _run_hook("PreToolUse", payload, env_extra=s["env"])
    assert rc == 0, f"stderr: {err}"
    assert "file-archival-or-move" in _context(json.loads(out))


def test_legacy_user_prompt_key_still_scanned():
    """Defensive fallback: payloads using the legacy 'user_prompt' key still match."""
    rc, out, err = _run_hook(
        "UserPromptSubmit",
        {"user_prompt": "drafting a preflight",
         "session_id": f"test-{uuid.uuid4().hex}"},
    )
    assert rc == 0, f"stderr: {err}"
    assert "preflight-drafting" in _context(json.loads(out))


def test_broken_input_does_not_crash_session():
    """Invalid JSON input -> hook still exits 0 with continue:true."""
    proc = subprocess.run(
        [PYTHON, HOOK, "--event", "UserPromptSubmit"],
        input="not valid json {{{",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data.get("continue") is True
