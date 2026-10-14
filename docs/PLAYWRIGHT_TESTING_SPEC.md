# Playwright E2E Testing Framework — Implementation Spec

> **Purpose:** Give Claude CLI the ability to visually inspect and interact with the running Streamlit app after making changes, eliminating the manual "go poke at it" testing loop.
>
> **Author:** PM Claude (Cowork) — spec for Claude CLI implementation
>
> **Date:** 2026-04-15

---

## 1. Installation & Setup

### 1.1 Install Playwright (human must approve first — supply chain rule)

```bash
# Step 1: Dry-run to verify minimal transitive deps
pip install --dry-run playwright

# Step 2: Install and pin
pip install playwright==1.52.0 pytest-playwright==0.7.0 --break-system-packages
# (Use the venv: .venv/Scripts/pip.exe on this project)

# Step 3: Install ONLY Chromium (saves ~150MB vs all browsers)
playwright install chromium

# Step 4: Post-install .pth audit (MANDATORY per CLAUDE.md supply chain rules)
# Scan .venv/Lib/site-packages/ for .pth files
# Only distutils-precedence.pth should exist

# Step 5: Pin in requirements.txt under a new "Testing / E2E" section
# playwright==1.52.0
# pytest-playwright==0.7.0
```

### 1.2 Project Structure

```
tests/
├── conftest.py              ← existing (unit test fixtures)
├── e2e/
│   ├── conftest.py          ← E2E fixtures (browser, running app, auth)
│   ├── test_login.py        ← auth flow smoke test
│   ├── test_home.py         ← dashboard loads, case list visible
│   ├── test_ingestor.py     ← file upload + ingest workflow
│   ├── test_review.py       ← document viewer, redaction tools
│   └── screenshots/         ← auto-captured on failure (gitignored)
└── ... existing test files
```

---

## 2. E2E conftest.py — Core Fixtures

This is the heart of the framework. Create `tests/e2e/conftest.py`:

```python
"""
E2E test fixtures for Playwright + Streamlit.

Assumes Streamlit is already running at localhost:8501.
Claude CLI should start the app before running E2E tests.
"""
import os
import sys
import pytest
from playwright.sync_api import Page, expect

# Project root on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

BASE_URL = "http://localhost:8501"

# ── Screenshot on failure ────────────────────────────────────────────────────

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


@pytest.fixture(autouse=True)
def screenshot_on_failure(request, page: Page):
    """Capture a screenshot if the test fails — gives Claude CLI eyes."""
    yield
    if request.node.rep_call and request.node.rep_call.failed:
        name = request.node.name.replace("/", "_").replace("::", "_")
        path = os.path.join(SCREENSHOT_DIR, f"FAIL_{name}.png")
        page.screenshot(path=path, full_page=True)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach test outcome to the request node for screenshot_on_failure."""
    import pluggy
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


# ── Streamlit Helpers ────────────────────────────────────────────────────────

@pytest.fixture()
def app_page(page: Page):
    """
    Navigate to the Streamlit app and wait for it to load.
    Returns the Page object ready for interaction.
    """
    page.goto(BASE_URL)
    # Wait for Streamlit to finish initial render
    page.wait_for_load_state("networkidle")
    # Streamlit shows a "Running..." status while executing — wait for it to clear
    page.wait_for_selector('[data-testid="stStatusWidget"]', state="hidden", timeout=15000)
    return page


@pytest.fixture()
def logged_in_page(app_page: Page):
    """
    Navigate to the app and log in as admin.
    Adjust selectors based on your actual login UI.
    """
    # TODO: Implement based on Respondeo's auth UI
    # Example pattern:
    # app_page.get_by_label("Username").fill("admin")
    # app_page.get_by_label("Password").fill("admin_password")
    # app_page.get_by_role("button", name="Login").click()
    # app_page.wait_for_load_state("networkidle")
    return app_page


def streamlit_rerun_wait(page: Page, timeout: int = 10000):
    """
    After clicking a Streamlit widget, call this to wait for the
    re-run cycle to complete. Streamlit shows a status widget while
    the script is re-executing.
    """
    try:
        page.wait_for_selector(
            '[data-testid="stStatusWidget"]',
            state="visible",
            timeout=2000
        )
    except:
        pass  # Sometimes the rerun is instant
    page.wait_for_selector(
        '[data-testid="stStatusWidget"]',
        state="hidden",
        timeout=timeout
    )
```

---

## 3. Streamlit Selector Cheat Sheet

Streamlit generates predictable `data-testid` attributes. Use these:

| Streamlit Widget | Playwright Selector |
|---|---|
| Button | `page.get_by_role("button", name="Button Text")` |
| Text input | `page.get_by_label("Label Text")` |
| Selectbox | `page.get_by_label("Label Text")` then `.select_option("value")` |
| Sidebar | `page.locator('[data-testid="stSidebar"]')` |
| Tab | `page.get_by_role("tab", name="Tab Name")` |
| File uploader | `page.locator('[data-testid="stFileUploader"] input[type="file"]')` |
| Dataframe | `page.locator('[data-testid="stDataFrame"]')` |
| Metric | `page.locator('[data-testid="stMetric"]')` |
| Success msg | `page.locator('[data-testid="stAlert"]')` |
| Spinner/running | `page.locator('[data-testid="stStatusWidget"]')` |
| Page nav (MPA) | `page.goto(f"{BASE_URL}/Page_Name")` |

**Important:** Streamlit multipage apps use URL paths like `/Ingestor`, `/Review`, etc. Navigate directly rather than clicking sidebar nav.

---

## 4. Example Test — Smoke Test

Create `tests/e2e/test_home.py`:

```python
"""Smoke test: app loads and dashboard renders."""
from playwright.sync_api import Page, expect


def test_app_loads(app_page: Page):
    """Streamlit app loads without crashing."""
    expect(app_page).to_have_title("Respondeo | Home")


def test_dashboard_has_metrics(app_page: Page):
    """Dashboard shows at least one metric card."""
    metrics = app_page.locator('[data-testid="stMetric"]')
    expect(metrics.first).to_be_visible(timeout=10000)


def test_sidebar_navigation(app_page: Page):
    """Sidebar is present and contains expected navigation."""
    sidebar = app_page.locator('[data-testid="stSidebar"]')
    expect(sidebar).to_be_visible()
```

---

## 5. Running Tests — Claude CLI Workflow

### Quick smoke test after a change:
```bash
# From project root, with Streamlit running in another terminal
.venv/Scripts/python.exe -m pytest tests/e2e/test_home.py -v --headed
```

### Run all E2E tests headless (CI-style):
```bash
.venv/Scripts/python.exe -m pytest tests/e2e/ -v
```

### Take a screenshot of current app state (ad-hoc debugging):
```python
# Quick script Claude CLI can run to "look at" the app
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("http://localhost:8501")
    page.wait_for_load_state("networkidle")
    page.screenshot(path="tests/e2e/screenshots/current_state.png", full_page=True)
    browser.close()
    print("Screenshot saved to tests/e2e/screenshots/current_state.png")
```

### Screenshot a specific page:
```python
# Navigate to Review page and capture state
page.goto("http://localhost:8501/Review")
page.wait_for_load_state("networkidle")
page.screenshot(path="tests/e2e/screenshots/review_page.png", full_page=True)
```

---

## 6. Claude CLI Integration Pattern

The intended workflow for Claude CLI after implementing this framework:

1. **Make code changes** to a Streamlit page
2. **Run the relevant E2E test** to verify the change didn't break anything
3. **If a test fails**, read the auto-captured screenshot from `tests/e2e/screenshots/`
4. **For ad-hoc investigation**, use the quick screenshot script to visually inspect the current app state
5. **Add new test cases** for new features as they're built

### Pytest markers for selective running:
```python
# In tests/e2e/conftest.py, register markers:
# pytest.ini or pyproject.toml:
# [tool.pytest.ini_options]
# markers = [
#     "smoke: quick sanity checks",
#     "review: Review page tests",
#     "production: Production page tests",
#     "slow: tests that take >10s",
# ]
```

---

## 7. .gitignore Addition

```
# E2E test artifacts
tests/e2e/screenshots/
```

---

## 8. Prerequisites Before Running

- Streamlit must be running (`streamlit run home.py`)
- A test case must exist in the database (or the login/case-selection flow must be handled in fixtures)
- For tests that need a logged-in session, the `logged_in_page` fixture needs to be implemented based on Respondeo's actual auth flow

---

## 9. Future Enhancements

- **Video recording**: Playwright can record test runs as video — useful for debugging complex multi-step failures
- **Visual regression**: Compare screenshots against baselines to catch CSS/layout regressions
- **Parallel execution**: `pytest-xdist` can run E2E tests in parallel with separate browser contexts
- **CI integration**: Run E2E tests as part of a pre-commit or pre-merge check
