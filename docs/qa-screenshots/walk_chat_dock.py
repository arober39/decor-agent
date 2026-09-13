import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
KEY = f"nav-dock-{int(time.time())}"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.add_init_script(f"localStorage.setItem('decora-context-key', {KEY!r});")
        page.goto("http://127.0.0.1:8765/studio", wait_until="networkidle")
        page.locator("#board-btn").click()
        page.wait_for_function("() => document.querySelectorAll('.spec-row').length >= 4")
        page.wait_for_timeout(400)
        metrics = page.evaluate(
            """() => {
              const board = document.querySelector('.board-panel');
              const list = document.querySelector('.list-panel');
              const scroll = document.querySelector('.list-scroll');
              const dock = document.querySelector('.ask-dock');
              return {
                boardH: Math.round(board.getBoundingClientRect().height),
                listH: Math.round(list.getBoundingClientRect().height),
                listScrolls: scroll.scrollHeight > scroll.clientHeight + 4,
                hasExpand: Boolean(document.getElementById('chat-expand')),
                hasResizer: Boolean(document.getElementById('chat-resizer')),
                dockH: Math.round(dock.getBoundingClientRect().height),
              };
            }"""
        )
        page.screenshot(path=str(OUT / "nav-09-scroll-list.png"), full_page=True)
        box = page.locator("#chat-resizer").bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] - 160)
        page.mouse.up()
        page.wait_for_timeout(200)
        after = page.evaluate(
            "() => Math.round(document.querySelector('.ask-dock').getBoundingClientRect().height)"
        )
        page.screenshot(path=str(OUT / "nav-10-chat-drag.png"), full_page=True)
        print(json.dumps({**metrics, "dockAfterDrag": after}))
        browser.close()


if __name__ == "__main__":
    main()
