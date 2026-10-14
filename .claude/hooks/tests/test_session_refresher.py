"""Tests for session_refresher hook script.

Pins the CONSUMER-side Claude Code hook contract: SessionStart context
injection is hookSpecificOutput.additionalContext, NOT systemMessage
(which renders in the terminal UI only and never reaches the model).
The original suite asserted systemMessage and passed while the model
received nothing — see the 2026-06-10 contract fix.

Content assertions target the refresher's stable header line, not slot
contents (slots churn at every sprint-close by design; the old suite's
'Check 1' assertion survived slot churn only as an accidental substring
of 'Check 12').
"""
import json
import os
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
HOOK = str(Path(__file__).resolve().parent.parent / "session_refresher.py")
REFRESHER = Path(__file__).resolve().parent.parent.parent / "refresher.md"


def test_session_start_injects_refresher_into_model_context():
    """SessionStart hook emits refresher.md verbatim as additionalContext."""
    proc = subprocess.run(
        [PYTHON, HOOK],
        input=json.dumps({"hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data.get("continue") is True
    hso = data.get("hookSpecificOutput", {})
    assert hso.get("hookEventName") == "SessionStart"
    ctx = hso.get("additionalContext", "")
    assert "Top recurring misses" in ctx
    # Verbatim injection: the model sees exactly what the file says.
    assert ctx == REFRESHER.read_text(encoding="utf-8")
    # systemMessage is a user-visible audit line, not the carrier.
    assert "injected" in data.get("systemMessage", "")


def test_missing_refresher_does_not_crash():
    """If refresher.md is missing, hook still exits 0 with continue:true."""
    env = os.environ.copy()
    env["REFRESHER_PATH_OVERRIDE"] = "/nonexistent/refresher.md"
    proc = subprocess.run(
        [PYTHON, HOOK],
        input=json.dumps({"hook_event_name": "SessionStart"}),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data.get("continue") is True
    assert "hookSpecificOutput" not in data
