import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
CONTEXT_KEY = f"nav-walk-{int(time.time())}"


def shot(page, name: str) -> None:
    path = OUT / f"nav-{name}.png"
    page.screenshot(path=str(path), full_page=True)
    payload = {"name": name, "url": page.url}
    if page.locator("#project-status").count():
        payload["status"] = page.locator("#project-status").inner_text()
        payload["approveHidden"] = page.locator("#approval-actions").evaluate(
            "el => el.classList.contains('hidden')"
        )
        payload["listActionsHidden"] = page.locator("#list-actions").evaluate(
            "el => el.classList.contains('hidden')"
        )
        payload["changePanelHidden"] = page.locator("#change-panel").evaluate(
            "el => el.classList.contains('hidden')"
        )
        payload["listNoteHidden"] = page.locator("#list-note").evaluate(
            "el => el.classList.contains('hidden')"
        )
        payload["listNote"] = page.locator("#list-note").inner_text().strip()
        payload["thread"] = " ".join(page.locator("#messages").inner_text().split())[:400]
    print(json.dumps(payload), flush=True)


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.add_init_script(
            f"localStorage.setItem('decora-context-key', {CONTEXT_KEY!r});"
        )

        page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        shot(page, "01-home")

        page.goto("http://127.0.0.1:8765/studio", wait_until="networkidle")
        page.wait_for_timeout(500)
        shot(page, "02-studio-empty")

        page.locator("#board-btn").click()
        page.wait_for_function(
            """() => {
              const list = document.querySelector('#project-specs');
              return list && list.querySelectorAll('.spec-row').length >= 4;
            }"""
        )
        page.wait_for_timeout(300)
        shot(page, "03-after-board")

        page.locator("#list-actions [data-job='change']").click()
        page.wait_for_function(
            """() => !document.querySelector('#change-panel')
              ?.classList.contains('hidden')"""
        )
        page.wait_for_timeout(200)
        shot(page, "04-change-panel")

        page.locator("#change-input").fill(
            "swap the lamp for the brass lamp they have in inventory"
        )
        page.locator("#change-form button[type='submit']").click()
        page.locator("#list-note").wait_for(state="visible", timeout=120_000)
        page.wait_for_function(
            """() => {
              const note = document.querySelector('#list-note');
              const thread = document.querySelector('#messages');
              const text = `${note?.innerText || ''} ${thread?.innerText || ''}`.toLowerCase();
              return text.includes('already') && text.includes('brass');
            }""",
            timeout=120_000,
        )
        page.wait_for_timeout(400)
        shot(page, "05-after-swap-ask")

        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(200)
        shot(page, "06-after-swap-mobile")

        print(json.dumps({"contextKey": CONTEXT_KEY}), flush=True)
        browser.close()


if __name__ == "__main__":
    main()
