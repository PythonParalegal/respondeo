"""
E2E test fixtures for Playwright + Streamlit.

Assumes:
  - Streamlit is running at localhost:8501
  - Test user 'e2e_admin' exists (run seed_test_user.py first)
"""
import os
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8501"

# Test credentials — must match seed_test_user.py
E2E_USER = "e2e_admin"
E2E_PASS = "E2E_Test_Pass_42!"

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


# ── Screenshot on failure ────────────────────────────────────────────────────

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach test outcome to the request node for screenshot_on_failure."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(autouse=True)
def screenshot_on_failure(request, page: Page):
    """Capture a full-page screenshot if the test fails."""
    yield
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        name = request.node.name.replace("/", "_").replace("::", "_")
        path = os.path.join(SCREENSHOT_DIR, f"FAIL_{name}.png")
        page.screenshot(path=path, full_page=True)


# ── Streamlit helpers ────────────────────────────────────────────────────────

def _wait_for_streamlit(page: Page, timeout: int = 15000):
    """Wait for Streamlit's 'Running...' spinner to clear."""
    try:
        page.wait_for_selector(
            '[data-testid="stStatusWidget"]', state="visible", timeout=2000
        )
    except Exception:
        pass  # Sometimes the rerun is instant
    page.wait_for_selector(
        '[data-testid="stStatusWidget"]', state="hidden", timeout=timeout
    )


# ── Page fixtures ────────────────────────────────────────────────────────────

@pytest.fixture()
def app_page(page: Page):
    """Navigate to the app root and wait for initial render."""
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    _wait_for_streamlit(page)
    return page


@pytest.fixture()
def logged_in_page(app_page: Page):
    """
    Log in as e2e_admin and return the page on the home dashboard.
    Assumes the app is showing the login form on first visit.
    """
    # Fill the login form (inside a st.form with key="login_form")
    app_page.get_by_label("Username").fill(E2E_USER)
    app_page.get_by_role("textbox", name="Password").fill(E2E_PASS)
    app_page.get_by_role("button", name="Login").click()

    # Wait for Streamlit rerun after login
    app_page.wait_for_load_state("networkidle")
    _wait_for_streamlit(app_page)

    # Verify we're past the login screen — sidebar should have the logout button
    expect(app_page.get_by_role("button", name="Logout")).to_be_visible(timeout=10000)

    return app_page


def streamlit_rerun_wait(page: Page, timeout: int = 10000):
    """
    Call after clicking a Streamlit widget to wait for the rerun cycle.
    Exported for use in test files.
    """
    _wait_for_streamlit(page, timeout)
