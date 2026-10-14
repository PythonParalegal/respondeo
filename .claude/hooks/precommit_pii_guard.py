"""Pre-commit hook: secrets / PII guard.

Blocks a commit when a tracked text file contains something that should
never live in a public repository:

  * private keys and common API-token formats (AWS, GitHub, Slack,
    OpenAI/Anthropic-style ``sk-`` keys, PEM blocks)
  * email addresses outside reserved example domains
    (example.com/.org/.net, *.example, *.test, *.invalid, localhost)
  * North-American phone numbers outside the fictional 555 exchange
  * any regex in an optional, user-supplied local deny-list

The deny-list lets each developer add terms specific to their own
environment (client names, internal hostnames, personal paths) without
committing those terms. Sources, first match wins:

    1. --pattern PATTERN (repeatable)
    2. --denylist FILE
    3. $PII_GUARD_DENYLIST
    4. .claude/hooks/pii_denylist.local.txt (gitignored)

Deny-list format: one Python regex per line; blank lines and '#' comments
ignored; case-sensitive unless prefixed with "(?i)".

Usage:
    precommit_pii_guard.py [--pattern P ...] [--denylist F]
                           [--no-builtins] [--path PATH ... | --root DIR]

Without --path/--root, scans git-tracked files (minus EXCLUDE_PREFIXES).
--root walks a directory on disk (prunes .git/) and reports how many files
were scanned. Findings report file:line and rule name only; the matched
text is never echoed. A line containing the marker
"pii-guard: allow" (e.g. in an HTML or code comment) is skipped; use it
only for public business contacts.

Exit codes: 0 pass, 1 findings (or the file list could not be built).
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_DENYLIST = Path(".claude/hooks/pii_denylist.local.txt")
ENV_VAR = "PII_GUARD_DENYLIST"

ALLOW_MARKER = "pii-guard: allow"  # inline opt-out for public contacts

EXCLUDE_PREFIXES = (
    ".claude/hooks/tests/",  # fixtures intentionally contain bad samples
)

_ALLOWED_EMAIL_DOMAIN = re.compile(
    r"(^|\.)(example\.(com|org|net)|example|test|invalid|localhost)$", re.I)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b")
_PHONE = re.compile(r"(?<![\d-])\(?([2-9]\d{2})\)?[-. ]([2-9]\d{2})[-. ](\d{4})(?![\d-])")

BUILTIN_RULES = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("api-key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
]


def _email_hit(line):
    return any(not _ALLOWED_EMAIL_DOMAIN.search(m.group(1))
               for m in _EMAIL.finditer(line))


def _phone_hit(line):
    return any("555" not in (m.group(1), m.group(2))
               for m in _PHONE.finditer(line))


def load_denylist(path):
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def resolve_denylist(cli_patterns, denylist):
    if cli_patterns:
        return cli_patterns, "--pattern"
    for cand in (denylist, os.environ.get(ENV_VAR), DEFAULT_DENYLIST):
        if cand and Path(cand).is_file():
            return load_denylist(cand), str(cand)
    return [], None


def _tracked_files():
    res = subprocess.run(["git", "ls-files"], capture_output=True,
                         text=True, check=True)
    return [l.strip() for l in res.stdout.splitlines() if l.strip()]


def _walk_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        out.extend(str(Path(dirpath, n)) for n in filenames)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", action="append", default=None)
    ap.add_argument("--denylist", default=None)
    ap.add_argument("--no-builtins", action="store_true",
                    help="Only apply deny-list patterns")
    ap.add_argument("--path", action="append", default=None)
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    if args.path and args.root:
        print("pii-guard FAIL: --path and --root are mutually exclusive",
              file=sys.stderr)
        return 1

    deny, source = resolve_denylist(args.pattern, args.denylist)
    try:
        rules = [] if args.no_builtins else list(BUILTIN_RULES)
        rules += [(f"denylist#{i}", re.compile(p))
                  for i, p in enumerate(deny, start=1)]
    except re.error as e:
        print(f"pii-guard FAIL: bad deny-list pattern in {source}: {e}",
              file=sys.stderr)
        return 1
    checks = [(n, r.search) for n, r in rules]
    if not args.no_builtins:
        checks += [("email", _email_hit), ("phone", _phone_hit)]

    if args.root:
        files = _walk_files(args.root)
    elif args.path:
        files = list(args.path)
    else:
        try:
            files = [f for f in _tracked_files()
                     if not f.startswith(EXCLUDE_PREFIXES)]
        except subprocess.CalledProcessError as e:
            print(f"pii-guard FAIL: could not list tracked files: {e}",
                  file=sys.stderr)
            return 1

    findings, scanned = [], 0
    for rel in files:
        p = Path(rel)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")  # binaries are skipped
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for n, line in enumerate(text.splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            for name, check in checks:
                if check(line):
                    findings.append((rel, n, name))
                    break

    if args.root:
        print(f"pii-guard: scanned {scanned} files", file=sys.stderr)
    if findings:
        print("pii-guard FAIL:", file=sys.stderr)
        for rel, n, name in findings:
            print(f"  {rel}:{n} [{name}]", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
