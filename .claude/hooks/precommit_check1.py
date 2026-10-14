"""Pre-commit hook: verify every file path cited in the most recent
preflight is git-tracked.

Catches the Check 1 failure pattern (5 recurrences across beta-2.11,
beta-2.13, beta-2.15): treating an in-session-drafted file as if it's
already tracked because `ls` showed it exists.

Usage:
    precommit_check1.py [--preflight PATH]

If --preflight is omitted, scans `docs/audits/commit_*_preflight.md`
for the latest by mtime. If none found, exits 0 (no preflight to check).

Exit codes:
    0 — pass (no preflight, or all cited files tracked)
    1 — fail (one or more cited files exist on disk but are not tracked)
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path


_PATH_PATTERN = re.compile(r"`([^`\s][^`]*\.(py|md|json|yaml|yml|toml|txt|cfg))`")


def _find_latest_preflight():
    audits = Path("docs/audits")
    if not audits.exists():
        return None
    candidates = list(audits.glob("commit_*_preflight.md"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _extract_cited_paths(preflight_path):
    """Pull out backtick-quoted file paths from the preflight."""
    text = preflight_path.read_text(encoding="utf-8")
    paths = set()
    for match in _PATH_PATTERN.finditer(text):
        candidate = match.group(1)
        if "://" in candidate or candidate.startswith("http"):
            continue
        paths.add(candidate)
    return paths


def _is_tracked(path):
    """Return True if path is tracked in git."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _is_gitignored(path):
    """Return True if path is gitignored by design (e.g. config.py — machine-
    specific, with config.example.py as the tracked template). Such files are
    intentionally untracked and are NOT the in-session-draft failure mode Check 1
    targets. This implements the three-state distinction (tracked / gitignored /
    untracked-but-existing) drawn in
    docs/lessons/not-in-git-tracked-not-existent.md."""
    result = subprocess.run(
        ["git", "check-ignore", path],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path, default=None)
    args = parser.parse_args()

    preflight = args.preflight or _find_latest_preflight()
    if preflight is None or not preflight.exists():
        return 0

    cited = _extract_cited_paths(preflight)
    untracked = []
    for path_str in cited:
        path = Path(path_str)
        if path.exists() and not _is_tracked(path_str) and not _is_gitignored(path_str):
            untracked.append(path_str)

    if untracked:
        print(
            "Check 1 FAIL: preflight cites file(s) that exist on disk "
            "but are NOT git-tracked:\n  - "
            + "\n  - ".join(untracked)
            + "\n\nVerify via `git ls-files <path>`. If the file is "
            "intentionally in-session-drafted, `git add` it before "
            "committing. See docs/lessons/not-in-git-tracked-not-existent.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
