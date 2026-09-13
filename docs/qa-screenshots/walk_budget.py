import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
KEY = f"nav-budget-{int(time.time())}"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.add_init_script(f"localStorage.setItem('decora-context-key', {KEY!r});")
        page.goto("http://127.0.0.1:8765/studio", wait_until="networkidle")
        page.locator("#board-btn").click()
        page.wait_for_function(
            "() => document.querySelectorAll('.spec-row').length >= 4"
        )
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "nav-07-over-budget.png"), full_page=True)
        over = page.locator("#project-over-copy").inner_text()
        fit_hidden = page.locator("#project-over").evaluate(
            "el => el.classList.contains('hidden')"
        )
        cheaper = page.locator("[data-swap-sku]").count()
        drops = page.locator("[data-drop-sku]").count()
        page.locator("#chat-expand").click()
        expanded = page.locator(".ask-dock").evaluate(
            "el => el.classList.contains('expanded')"
        )
        page.locator('[data-job="fit"]').first.click()
        page.wait_for_function(
            """() => !document.querySelector('#project-over')
              || document.querySelector('#project-over').classList.contains('hidden')"""
        )
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "nav-08-fit-cap.png"), full_page=True)
        rugs = page.locator(".spec-meta").all_inner_texts()
        print(
            json.dumps(
                {
                    "over": over,
                    "fitHiddenBefore": fit_hidden,
                    "cheaperButtons": cheaper,
                    "dropButtons": drops,
                    "expanded": expanded,
                    "afterFitMetas": rugs,
                    "overHiddenAfter": page.locator("#project-over").evaluate(
                        "el => el.classList.contains('hidden')"
                    ),
                }
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
