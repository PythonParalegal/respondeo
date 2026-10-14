"""
Smoke tests: app loads, login works, key pages render.

Run:  .venv/Scripts/python.exe -m pytest tests/e2e/test_smoke.py -v
Requires: Streamlit running at localhost:8501, e2e_admin user seeded.
"""
from playwright.sync_api import Page, expect


class TestAppLoads:
    """Basic app availability checks (no login required)."""

    def test_app_responds(self, app_page: Page):
        """Streamlit app loads without crashing."""
        # The page should have some content (not a connection error)
        expect(app_page.locator("body")).not_to_be_empty()

    def test_login_form_visible(self, app_page: Page):
        """Login form renders with username, password, and submit."""
        expect(app_page.get_by_label("Username")).to_be_visible()
        expect(app_page.get_by_role("textbox", name="Password")).to_be_visible()
        expect(app_page.get_by_role("button", name="Login")).to_be_visible()


class TestLogin:
    """Authentication flow tests."""

    def test_login_succeeds(self, logged_in_page: Page):
        """Can log in as e2e_admin and reach the dashboard."""
        # After login, the sidebar should be visible
        sidebar = logged_in_page.locator('[data-testid="stSidebar"]')
        expect(sidebar).to_be_visible()

    def test_login_shows_display_name(self, logged_in_page: Page):
        """After login, the user's display name appears in the sidebar."""
        # "Playwright Bot" is the display name from seed_test_user.py
        sidebar = logged_in_page.locator('[data-testid="stSidebar"]')
        expect(sidebar.get_by_text("Playwright Bot")).to_be_visible(timeout=5000)


class TestPageNavigation:
    """Verify key pages load without errors after login."""

    PAGES = [
        ("Ingestor", "Respondeo | Ingest"),
        ("Processor", "Respondeo | Processor"),
        ("Analytics", "Respondeo | Analytics"),
        ("Review", "Respondeo | Review"),
        ("Production", "Respondeo | Production"),
        ("Custodians", "Respondeo | Custodians"),
        ("Exhibits", "Respondeo | Exhibits"),
    ]

    def test_home_has_title(self, logged_in_page: Page):
        """Home page has the expected title."""
        expect(logged_in_page).to_have_title("Respondeo | Home", timeout=5000)

    def test_pages_load(self, page: Page):
        """Each page loads without Streamlit error banners after login."""
        from tests.e2e.conftest import _wait_for_streamlit, BASE_URL, E2E_USER, E2E_PASS

        for page_name, expected_title in self.PAGES:
            # Each goto creates a fresh Streamlit session, so login per page
            page.goto(f"{BASE_URL}/{page_name}")
            page.wait_for_load_state("networkidle")
            _wait_for_streamlit(page)

            # Login on this page
            page.get_by_label("Username").fill(E2E_USER)
            page.get_by_role("textbox", name="Password").fill(E2E_PASS)
            page.get_by_role("button", name="Login").click()
            page.wait_for_load_state("networkidle")
            _wait_for_streamlit(page)

            # No Streamlit error/exception banner should be visible
            error_banners = page.locator('[data-testid="stException"]')
            expect(error_banners).to_have_count(0)
