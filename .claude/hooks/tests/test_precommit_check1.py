"""Tests for precommit_check1: verify cited preflight files are git-tracked."""
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable
HOOK = str(Path(__file__).resolve().parent.parent / "precommit_check1.py")
REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_hook(preflight_path):
    proc = subprocess.run(
        [PYTHON, HOOK, "--preflight", str(preflight_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_passes_when_no_preflight_argument():
    """No preflight cited -> no check needed -> exit 0."""
    proc = subprocess.run(
        [PYTHON, HOOK],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0


def test_passes_when_preflight_cites_only_tracked_files(tmp_path):
    """Preflight cites files that exist and are git-tracked -> exit 0."""
    preflight = tmp_path / "test_preflight.md"
    preflight.write_text("Cites: `CLAUDE.md` and `db_manager.py`\n")
    rc, out, err = _run_hook(preflight)
    assert rc == 0, f"stderr: {err}"


def test_fails_when_preflight_cites_untracked_file(tmp_path):
    """Preflight cites a file that exists on disk but is not git-tracked
    -> exit 1 with clear error to stderr."""
    untracked = tmp_path / "untracked.md"
    untracked.write_text("not in git")
    preflight = tmp_path / "test_preflight.md"
    preflight.write_text(f"Cites: `{untracked}` (this is untracked)\n")
    rc, out, err = _run_hook(preflight)
    assert rc == 1
    assert "untracked" in err.lower() or "not tracked" in err.lower()
    assert str(untracked) in err or "untracked.md" in err


def test_passes_when_preflight_cites_gitignored_file(tmp_path):
    """A preflight that backtick-cites a gitignored-by-design file (config.py —
    it exists but is intentionally untracked, with config.example.py as the
    template) must NOT be flagged. Regression pin for the beta-2.16 C8a
    false-positive where Check 1 conflated gitignored-by-design with the
    in-session-draft failure mode it targets."""
    if not (REPO_ROOT / "config.py").exists():
        pytest.skip("config.py not present in this environment")
    ignored = subprocess.run(
        ["git", "check-ignore", "config.py"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    ).returncode == 0
    if not ignored:
        pytest.skip("config.py is not gitignored in this environment")
    preflight = tmp_path / "test_preflight.md"
    preflight.write_text("Cites the gitignored `config.py` by name (e.g. 'no `config.py` touch').\n")
    proc = subprocess.run(
        [PYTHON, HOOK, "--preflight", str(preflight)],
        capture_output=True, text=True, timeout=10, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
