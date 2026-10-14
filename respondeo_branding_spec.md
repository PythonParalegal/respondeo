# Respondeo Branding Integration Spec

## Overview

Add the Respondeo Dominican Hound logo to the platform as favicon (browser tab) and sidebar branding. Two transparent PNG assets are ready in project root (120px_transparent.png and 32px_transparent.png).

## Assets

| File                                     | Description                           | Target Use   |
| ---------------------------------------- | ------------------------------------- | ------------ |
| Line-art full body (dog in arch, ~120px) | Medium detail, gold on transparent    | Sidebar logo |
| Minimal head (just head + torch, ~32px)  | Simplest version, gold on transparent | Favicon      |

**Step 0: Set up assets folder and copy images**

1. Create `assets/` directory in the ediscovery project root
2. Copy the two transparent PNGs into `assets/`
3. Name them: `sidebar_logo.png` (the full-body line art) and `favicon.png` (the minimal head)
4. Add `assets/` to git tracking (these are not sensitive files)

## Integration Points

### 1. Favicon — All Pages

Every `.py` file that calls `st.set_page_config()` needs the `page_icon` parameter added.

**Files to modify:**

- `home.py` (line 37)
- `pages/1_Ingestor.py` (line 36)
- `pages/2_Processor.py` (line 31)
- `pages/3_Analytics.py` (line 60)
- `pages/4_Review.py` (line 250)
- `pages/5_Production.py` (line 32)
- `pages/6_Sync.py` (line 22)
- `pages/7_Custodians.py` (line 46)
- `pages/8_Exhibits.py` (line 235)

**Pattern — add `page_icon` to each existing call:**

```python
# Before:
st.set_page_config(page_title="DIY Discovery Home", layout="wide")

# After:
st.set_page_config(page_title="Respondeo | Home", layout="wide", page_icon="assets/favicon.png")
```

**Note:** Also update `page_title` prefix from "DIY Discovery" / "Module N:" to "Respondeo |" for consistent branding across browser tabs. This is optional — discuss with the maintainer first.

### 2. Sidebar Logo — All Pages via ui_utils.py

Rather than adding `st.sidebar.image()` to every page file, add it to `ui_utils.py` since every page already calls `ui_utils.inject_custom_css()`. This is the DRY approach.

**In `ui_utils.py`, add a new function:**

```python
def inject_sidebar_branding():
    """Display Respondeo logo at top of sidebar."""
    import os
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "sidebar_logo.png")
    if os.path.exists(logo_path):
        st.sidebar.image(logo_path, width=120)
```

**Then call it from each page** right after `ui_utils.inject_custom_css()`:

```python
ui_utils.inject_custom_css()
ui_utils.inject_sidebar_branding()  # Add this line
```

**Alternative (cleaner):** Fold the branding into `inject_custom_css()` itself so no additional call is needed. Rename to `inject_custom_theme()` or similar if that feels clearer.

### 3. Home Page Title Update (home.py)

Replace the emoji-based title with the logo + text:

```python
# Before (line 74):
st.title("🕵️ DIY E-Discovery Hub")

# After:
col1, col2 = st.columns([1, 5])
with col1:
    st.image("assets/sidebar_logo.png", width=80)
with col2:
    st.title("Respondeo")
    st.caption("E-Discovery Platform")
```

## What NOT to change

- Do not modify any RBAC gates or case status checks
- Do not change sidebar functional content (case selection, dependencies, etc.)
- Do not modify the dark theme / CSS — the gold-on-transparent logos work on both light and dark backgrounds for the line-art versions
- The hero logo (detailed illustration) is NOT used in-app — reserved for future website

## Version Tracking

Follow standard version header rules in CLAUDE.md:

- Patch bump each modified file
- Update `last_modified` timestamp
- CHANGELOG entries for the branding additions
