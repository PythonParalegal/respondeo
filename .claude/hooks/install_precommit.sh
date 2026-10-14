#!/bin/sh
# Re-install the project's pre-commit hook.
# Run after fresh clone or after .git/hooks/ was wiped.

set -e

ROOT="$(git rev-parse --show-toplevel)"
DEST="$ROOT/.git/hooks/pre-commit"

cat > "$DEST" <<'SH'
#!/bin/sh
PY=".venv/Scripts/python.exe"
if [ ! -f "$PY" ]; then
    PY="python"
fi
"$PY" .claude/hooks/precommit_check1.py || exit $?
"$PY" .claude/hooks/precommit_pii_guard.py || exit $?
exit 0
SH

chmod +x "$DEST"
echo "Installed pre-commit hook at $DEST"
