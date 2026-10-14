# Respondeo Branding Integration Spec (v2)

> Revised after CLI Claude code review. Changes from v1: fixed relative path
> issue, removed contradictory alternative approaches, added 8_Exhibits.py gap,
> switched from st.sidebar.image() to st.logo(), separated title rename as
> out-of-scope decision.

## Overview

Add the Respondeo Dominican Hound logo to the platform as favicon (browser tab)
and sidebar branding. Two transparent PNG assets are ready in
project root.

## Assets

| File                             | Description                           | Target Use            |
| -------------------------------- | ------------------------------------- | --------------------- |
| Line-art full body (dog in arch) | Medium detail, gold on transparent    | Sidebar logo (~120px) |
| Minimal head (just head + torch) | Simplest version, gold on transparent | Favicon (~32px)       |

## Step 0: Set up assets folder and copy images

1. Create `assets/` directory in the ediscovery project root
2. Copy the two transparent PNGs into `assets/`
3. Name them: `sidebar_logo.png` (the full-body line art) and `favicon.png` (the minimal head)
4. Verify `assets/` is not excluded by `.gitignore` — check for blanket binary
   exclusion patterns. Add an explicit `!assets/` allow rule if needed.
5. Add `assets/` to git tracking (these are not sensitive files)

## Integration Points

### 1. Favicon — All Pages

Every `.py` file that calls `st.set_page_config()` needs the `page_icon`
parameter added. **Use `__file__`-relative paths** — do NOT use bare relative
paths like `"assets/favicon.png"` because Streamlit resolves them from CWD,
which may differ from the script location.

**Helper pattern** (add near top of each file, after imports):

```python
from pathlib import Path
_ASSETS = Path(__file__).resolve().parent / "assets"
# For pages/ subdir files, go up one level:
_ASSETS = Path(__file__).resolve().parent.parent / "assets"
```

**Files to modify (line numbers verified 2026-04-15):**

| File                    | Line | `_ASSETS` needs `parent.parent`? |
| ----------------------- | ---- | -------------------------------- |
| `home.py`               | 37   | No (project root)                |
| `pages/1_Ingestor.py`   | 36   | Yes (in pages/)                  |
| `pages/2_Processor.py`  | 31   | Yes                              |
| `pages/3_Analytics.py`  | 60   | Yes                              |
| `pages/4_Review.py`     | 250  | Yes                              |
| `pages/5_Production.py` | 32   | Yes                              |
| `pages/6_Sync.py`       | 22   | Yes                              |
| `pages/7_Custodians.py` | 46   | Yes                              |
| `pages/8_Exhibits.py`   | 235  | Yes                              |

**Pattern:**

```python
st.set_page_config(
    page_title="DIY Discovery Home",  # Keep existing titles — see "Out of Scope" below
    layout="wide",
    page_icon=str(_ASSETS / "favicon.png")
)
```

### 2. Sidebar Logo — All Pages via st.logo()

Use Streamlit's built-in `st.logo()` API (available since 1.31; we run 1.55).
This is the modern, purpose-built approach — it handles sidebar placement,
collapsed/expanded states, and does not re-read from disk on every rerun.

**In `ui_utils.py`, add a new function:**

```python
def inject_sidebar_branding():
    """Display Respondeo logo in sidebar using st.logo()."""
    from pathlib import Path
    logo_path = Path(__file__).resolve().parent / "assets" / "sidebar_logo.png"
    icon_path = Path(__file__).resolve().parent / "assets" / "favicon.png"
    if logo_path.exists():
        st.logo(
            str(logo_path),          # Shown when sidebar is expanded
            icon_image=str(icon_path) # Shown when sidebar is collapsed
        )
```

**Call it from every page** right after `inject_custom_css()`:

```python
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()
```

**IMPORTANT: `pages/8_Exhibits.py` does NOT currently call `inject_custom_css()`.**
Add both calls to that file explicitly:

```python
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()
```

### 3. Home Page Title Update (home.py)

Replace the emoji-based title with the logo alongside text:

```python
# Before (line 74):
st.title("🕵️ DIY E-Discovery Hub")

# After:
col1, col2 = st.columns([1, 5])
with col1:
    st.image(str(_ASSETS / "sidebar_logo.png"), width=80)
with col2:
    st.title("Respondeo")
    st.caption("E-Discovery Platform")
```

## Out of Scope (decide separately)

- **Renaming page_title values** from "DIY Discovery" / "Module N:" to
  "Respondeo | ..." — this is a branding decision separate from the logo
  integration. The maintainer should decide on naming convention before implementation.
- **Hero logo** (detailed illustration with dog on pedestal) — not used in-app,
  reserved for future marketing website.
- **Dark mode / light mode variants** — the gold line-art logos work on both
  backgrounds. No theme-conditional logic needed.

## What NOT to change

- Do not modify any RBAC gates or case status checks
- Do not change sidebar functional content (case selection, dependencies, etc.)
- Do not modify the dark theme / CSS

## Version Tracking

Follow standard version header rules in CLAUDE.md:

- Patch bump each modified file (minor bump for ui_utils.py since adding new function)
- Update `last_modified` timestamp
- CHANGELOG entries for the branding additions
