"""Doc-architecture index-drift pytest suite.

Pins the four-tier docs/ architecture by verifying bijection between
tier directory contents and each tier's README.md index. Also
verifies CLAUDE.md Dependency API References table entries point at
existing files.

Installed in beta-2.11 Commit 9 to prevent silent drift between
directory state and index state — a failure mode that went undetected
through Commits 6b–8 and required manual audit.

Run with: pytest tests/test_docs_index_consistency.py -v

Scope: read-only; asserts only.
"""

import os
import re
from pathlib import Path

import pytest

# Repo root anchored via this test file's location.
REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def _list_tier_files(tier: str, excluded: tuple[str, ...] = ("README.md",)) -> set[str]:
    """Return filenames in a tier directory, excluding named files."""
    tier_dir = DOCS_DIR / tier
    if not tier_dir.is_dir():
        return set()
    return {
        p.name
        for p in tier_dir.iterdir()
        if p.is_file() and p.suffix == ".md" and p.name not in excluded
    }


def _read_readme(tier: str) -> str:
    readme = DOCS_DIR / tier / "README.md"
    if not readme.is_file():
        return ""
    return readme.read_text(encoding="utf-8")


def _extract_md_links(markdown_text: str) -> set[str]:
    """Extract all markdown link targets that look like .md filenames."""
    pattern = re.compile(r"\]\(([^)]+\.md)\)")
    return {os.path.basename(match) for match in pattern.findall(markdown_text)}


# ---------------------------------------------------------------------------
# Tier parity tests
# ---------------------------------------------------------------------------


def test_lessons_tier_parity():
    """Every lesson file is indexed; every index entry points at a lesson file."""
    files = _list_tier_files("lessons")
    readme = _read_readme("lessons")
    linked = _extract_md_links(readme)
    unindexed = files - linked
    orphaned = linked - files
    assert not unindexed, (
        f"Lesson files without README entries: {sorted(unindexed)}"
    )
    assert not orphaned, (
        f"README entries pointing at non-existent files: {sorted(orphaned)}"
    )


def test_templates_tier_parity():
    files = _list_tier_files("templates")
    readme = _read_readme("templates")
    linked = _extract_md_links(readme)
    unindexed = files - linked
    orphaned = linked - files
    assert not unindexed, (
        f"Template files without README entries: {sorted(unindexed)}"
    )
    assert not orphaned, (
        f"README entries pointing at non-existent files: {sorted(orphaned)}"
    )


def test_references_tier_parity():
    files = _list_tier_files("references")
    readme = _read_readme("references")
    linked = _extract_md_links(readme)
    unindexed = files - linked
    orphaned = linked - files
    assert not unindexed, (
        f"Reference files without README entries: {sorted(unindexed)}"
    )
    assert not orphaned, (
        f"README entries pointing at non-existent files: {sorted(orphaned)}"
    )


def test_retrospectives_tier_parity():
    """Retrospectives tier exists after beta-2.11 Commit 9. Template excluded
    from the 'needs index entry' set since it's the scaffold not a real retro."""
    tier_dir = DOCS_DIR / "retrospectives"
    if not tier_dir.is_dir():
        pytest.skip("retrospectives tier not yet installed")
    files = _list_tier_files("retrospectives", excluded=("README.md", "template.md"))
    readme = _read_readme("retrospectives")
    linked = _extract_md_links(readme)
    # Template is explicitly listed in README so include it in the linked set
    # check; remove template.md from both sides since it's the scaffold.
    linked.discard("template.md")
    unindexed = files - linked
    orphaned = linked - files
    assert not unindexed, (
        f"Retrospective files without README entries: {sorted(unindexed)}"
    )
    assert not orphaned, (
        f"README entries pointing at non-existent files: {sorted(orphaned)}"
    )


# ---------------------------------------------------------------------------
# CLAUDE.md cross-reference tests
# ---------------------------------------------------------------------------


def test_claude_md_references_table_targets_exist():
    """Every docs/references/*.md pointer in CLAUDE.md points at a real file."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    # Capture paths of form `docs/references/<something>.md` in backticks or links.
    pattern = re.compile(r"docs/references/([A-Z_]+\.md)")
    referenced = set(pattern.findall(claude_md))
    references_dir = DOCS_DIR / "references"
    existing = {p.name for p in references_dir.iterdir() if p.suffix == ".md"}
    missing = referenced - existing
    assert not missing, (
        f"CLAUDE.md references docs/references/ files that don't exist: "
        f"{sorted(missing)}"
    )


def test_claude_md_tier_readmes_exist():
    """Every tier README referenced in CLAUDE.md actually exists on disk."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    pattern = re.compile(r"docs/(lessons|templates|references|retrospectives)/README\.md")
    referenced_tiers = set(pattern.findall(claude_md))
    for tier in referenced_tiers:
        readme_path = DOCS_DIR / tier / "README.md"
        assert readme_path.is_file(), (
            f"CLAUDE.md references docs/{tier}/README.md but the file doesn't exist"
        )
