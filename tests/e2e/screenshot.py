"""
Ad-hoc screenshot utility for Claude CLI.

Usage:
  # Screenshot the home/login page:
  .venv/Scripts/python.exe tests/e2e/screenshot.py

  # Screenshot a specific page (logged in):
  .venv/Scripts/python.exe tests/e2e/screenshot.py --page Review

  # Screenshot without logging in (e.g., to see the login screen):
  .venv/Scripts/python.exe tests/e2e/screenshot.py --no-login

  # Custom output path:
  .venv/Scripts/python.exe tests/e2e/screenshot.py --out /tmp/shot.png
"""
import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"
E2E_USER = "e2e_admin"
E2E_PASS = "E2E_Test_Pass_42!"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


def _wait_for_streamlit(page, timeout=15000):
    try:
        page.wait_for_selector('[data-testid="stStatusWidget"]', state="visible", timeout=2000)
    except Exception:
        pass
    page.wait_for_selector('[data-testid="stStatusWidget"]', state="hidden", timeout=timeout)


def _login(page):
    page.get_by_label("Username").fill(E2E_USER)
    page.get_by_role("textbox", name="Password").fill(E2E_PASS)
    page.get_by_role("button", name="Login").click()
    page.wait_for_load_state("networkidle")
    _wait_for_streamlit(page)


def take_screenshot(page_name=None, login=True, output_path=None):
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # Navigate to target page (or root)
        target = f"{BASE_URL}/{page_name}" if page_name else BASE_URL
        page.goto(target)
        page.wait_for_load_state("networkidle")
        _wait_for_streamlit(page)

        # Login if requested (each page.goto gets its own Streamlit session)
        if login:
            _login(page)

        # Determine output path
        if not output_path:
            label = page_name or ("login" if not login else "home")
            output_path = os.path.join(SCREENSHOT_DIR, f"{label}.png")

        page.screenshot(path=output_path, full_page=True)
        browser.close()

    print(f"Screenshot saved: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Take a screenshot of the Streamlit app")
    parser.add_argument("--page", default=None, help="Page name (e.g., Review, Ingestor, Production)")
    parser.add_argument("--no-login", action="store_true", help="Skip login (see login screen)")
    parser.add_argument("--out", default=None, help="Output file path")
    args = parser.parse_args()

    take_screenshot(
        page_name=args.page,
        login=not args.no_login,
        output_path=args.out,
    )
