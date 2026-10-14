"""
Smoke test: every file in pages/ must appear in auth_manager._NAV_PAGES.

Pins the registry-vs-filesystem contract. If a future sprint adds a page to
pages/ but forgets to register it in _NAV_PAGES, logged-in users cannot reach
it via the sidebar (the failure observed in beta-2.10 Commit 6, where Module 9
Inbound Productions was extracted but not registered).

Also asserts the reverse direction — a _NAV_PAGES entry pointing at a file
that no longer exists on disk would produce a dead sidebar link.

If a future sprint intentionally introduces an admin-only or hidden page that
should NOT appear in the post-login sidebar (e.g. per Spec_Batch_Remediation_
and_Admin_Module.md), update this test with an explicit allowlist rather than
deleting the assertion.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _discover_page_files() -> set[str]:
    """Return every pages/*.py file on disk as a forward-slash relative path."""
    pages_dir = REPO_ROOT / "pages"
    discovered = set()
    for p in pages_dir.glob("*.py"):
        if p.name == "__init__.py":
            continue
        discovered.add(p.relative_to(REPO_ROOT).as_posix())
    return discovered


def _registered_page_files() -> set[str]:
    """Return every path under pages/ that appears in auth_manager._NAV_PAGES."""
    from auth_manager import _NAV_PAGES
    return {
        path for path, _label, _perm in _NAV_PAGES
        if path.startswith("pages/")
    }


def test_every_pages_file_is_registered_in_nav():
    discovered = _discover_page_files()
    registered = _registered_page_files()

    unregistered = discovered - registered
    stale = registered - discovered

    problems = []
    if unregistered:
        problems.append(
            "Page files on disk but missing from auth_manager._NAV_PAGES "
            "(logged-in users cannot reach these via the sidebar):\n  "
            + "\n  ".join(sorted(unregistered))
        )
    if stale:
        problems.append(
            "_NAV_PAGES entries referencing nonexistent files "
            "(dead sidebar links):\n  "
            + "\n  ".join(sorted(stale))
        )

    assert not problems, "\n\n".join(problems)
