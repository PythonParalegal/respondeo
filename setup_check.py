"""
setup_check.py
──────────────
Environment validation script for the eDiscovery Platform.

Verifies that all required external services and tools are reachable before
starting the Streamlit app.  Run this from the repo root after a fresh setup:

    python setup_check.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import sys
import os
import shutil
import socket

# ── Colour helpers (ANSI, disabled on non-TTY) ────────────────────────────────
_USE_COLOUR = sys.stdout.isatty()

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

def _ok(s: str) -> str:  return _c(s, "32")   # green
def _fail(s: str) -> str: return _c(s, "31")  # red
def _warn(s: str) -> str: return _c(s, "33")  # yellow
def _bold(s: str) -> str: return _c(s, "1")


# ── Individual checks ─────────────────────────────────────────────────────────

def check_python_version() -> tuple[bool, str]:
    v = sys.version_info
    ok = v >= (3, 9)
    return ok, f"Python {v.major}.{v.minor}.{v.micro}"


def check_http_endpoint(url: str, timeout: int = 5) -> tuple[bool, str]:
    """Returns (reachable, detail_string)."""
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except Exception as e:
        return False, str(e)[:80]


def check_executable(name: str, config_attr: str | None = None) -> tuple[bool, str]:
    """Check if an executable is on PATH or at the configured path."""
    # Try PATH first
    found = shutil.which(name)
    if found:
        return True, found
    # Try config override
    if config_attr:
        try:
            import config as _cfg
            path = getattr(_cfg, config_attr, None)
            if path and os.path.isfile(path):
                return True, path
        except ImportError:
            pass
    return False, f"'{name}' not found on PATH"


def check_outlook_com() -> tuple[bool, str]:
    if sys.platform != "win32":
        return True, "Skipped (non-Windows)"
    try:
        import win32com.client
        outlook = win32com.client.Dispatch("Outlook.Application")
        del outlook
        return True, "COM object created successfully"
    except ImportError:
        return False, "pywin32 not installed"
    except Exception as e:
        return False, str(e)[:80]


def check_cases_root() -> tuple[bool, str]:
    try:
        import config as _cfg
        root = getattr(_cfg, "CASES_ROOT", None)
        if not root:
            return False, "CASES_ROOT not set in config.py"
        if os.path.isdir(root):
            return True, root
        return False, f"Directory not found: {root}"
    except ImportError:
        return False, "config.py not found"


def check_canvas_patch() -> tuple[bool, str]:
    try:
        import importlib.util, glob
        spec = importlib.util.find_spec("streamlit_drawable_canvas")
        if spec is None:
            return False, "streamlit-drawable-canvas not installed"

        pkg_dir = (
            list(spec.submodule_search_locations)[0]
            if spec.submodule_search_locations
            else os.path.dirname(spec.origin or "")
        )
        bundles = glob.glob(
            os.path.join(pkg_dir, "frontend", "build", "static", "js", "main.*.js")
        )
        if not bundles:
            return False, "JS bundle not found — package layout may have changed"

        PATCHED_TOKEN = b",t.backgroundImage],[]"
        BUGGY_TOKEN   = b",t.backgroundImage],[A]"

        for js_path in bundles:
            with open(js_path, "rb") as f:
                content = f.read()
            if PATCHED_TOKEN in content:
                return True, "Patch applied ✓"
            if BUGGY_TOKEN in content:
                return False, "Patch NOT applied — run: python _scratchpad/post_install_patch.py"
        return True, "Token not found (newer package version — likely OK)"

    except Exception as e:
        return False, str(e)[:80]


# ── Runner ────────────────────────────────────────────────────────────────────

def _load_config_urls() -> tuple[str, str]:
    try:
        import config as _cfg
        tika = getattr(_cfg, "TIKA_ENDPOINT", "http://localhost:9998/tika")
        os_host = getattr(_cfg, "OS_HOST", "http://localhost:9200")
    except ImportError:
        tika = "http://localhost:9998/tika"
        os_host = "http://localhost:9200"
    return tika, os_host


def main() -> int:
    tika_url, os_url = _load_config_urls()

    checks = [
        ("Python ≥ 3.9",         check_python_version),
        ("Tika reachable",        lambda: check_http_endpoint(tika_url)),
        ("OpenSearch reachable",  lambda: check_http_endpoint(os_url)),
        ("wkhtmltopdf",           lambda: check_executable("wkhtmltopdf", "WKHTMLTOPDF_PATH")),
        ("Tesseract",             lambda: check_executable("tesseract", "TESSERACT_PATH")),
        ("Outlook COM",           check_outlook_com),
        ("Cases root accessible", check_cases_root),
        ("Canvas patch applied",  check_canvas_patch),
    ]

    print()
    print(_bold("=" * 62))
    print(_bold("  eDiscovery Platform — Environment Validation"))
    print(_bold("=" * 62))
    print(f"  {'Check':<30}  {'Status':<6}  Detail")
    print(f"  {'-'*30}  {'-'*6}  {'-'*40}")

    failures = 0
    for label, fn in checks:
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"Unexpected error: {exc}"

        status = _ok("  PASS") if ok else _fail("  FAIL")
        if not ok:
            failures += 1
        print(f"  {label:<30}  {status}   {detail}")

    print(_bold("=" * 62))
    if failures == 0:
        print(_ok("  ✅  All checks passed — platform is ready to run."))
    else:
        print(_fail(f"  ❌  {failures} check(s) failed — see details above."))
        print()
        print("  Quick fixes:")
        print("    Tika       →  java -jar C:\\Tools\\tika\\tika-server-*.jar")
        print("    OpenSearch →  C:\\Tools\\opensearch-*\\bin\\opensearch.bat")
        print("    wkhtmltopdf→  winget install wkhtmltopdf.wkhtmltopdf")
        print("    Tesseract  →  winget install UB-Mannheim.TesseractOCR")
        print("    Canvas     →  python _scratchpad/post_install_patch.py")
    print(_bold("=" * 62))
    print()

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
