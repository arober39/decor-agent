import json
import os
import subprocess
from pathlib import Path

os.environ["DECORA_PERSIST"] = "0"
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from fastapi.testclient import TestClient

from app.flags import SAVE_ROOM_PDF_FLAG
from server import app

ROOT = Path(__file__).resolve().parent


def test_save_room_pdf_flag_key_and_default_off() -> None:
    assert SAVE_ROOM_PDF_FLAG == "save-room-as-pdf"
    client = TestClient(app)
    caps = client.get("/api/capabilities").json()
    assert caps["save_room_as_pdf"] is False
    assert caps["board_intake"] is True
    assert caps["cart_hold"] is False
    assert caps["sample_board"] == "living-linen"

    studio = client.get("/studio").text
    assert (
        '<button id="save-room-pdf" class="btn btn-ghost hidden" type="button">Save room as PDF</button>'
        in studio
    )
    assert 'src="/web/room-pdf.js?v=room-pdf"' in studio


def test_save_room_pdf_capability_follows_flag(monkeypatch) -> None:
    import server

    def fake_flag(key, ctx, default=False):
        if key == SAVE_ROOM_PDF_FLAG:
            return True
        return default

    monkeypatch.setattr(server, "get_flag", fake_flag)
    client = TestClient(app)
    caps = client.get("/api/capabilities", params={"context_key": "pdf-room"}).json()
    assert caps["save_room_as_pdf"] is True
    assert caps["cart_hold"] is False
    assert caps["board_intake"] is True
    assert caps["sample_board"] == "living-linen"


def test_save_room_pdf_runs_only_from_the_button() -> None:
    script = (ROOT / "web" / "studio.js").read_text()
    builder = (ROOT / "web" / "room-pdf.js").read_text()
    click_at = script.index('getElementById("save-room-pdf")?.addEventListener("click"')
    handler = script[click_at : click_at + 320]
    assert 'button.classList.contains("hidden")' in handler
    assert "saveRoomAsPdf(currentProject)" in handler
    assert script.count("saveRoomAsPdf(") == 2
    assert "window.print()" not in script.split("function saveRoomAsPdf", 1)[0]
    for banned in ("fetch(", "window.print", "/api/chat", "search_catalog", "qdrant"):
        assert banned not in builder


def _render_plan(project: dict) -> str:
    renderer = r"""
const fs = require("fs");
const vm = require("vm");
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync("web/room-pdf.js", "utf8"), context);
process.stdout.write(context.roomPlanBody(JSON.parse(process.env.PLAN)));
"""
    env = os.environ.copy()
    env["PLAN"] = json.dumps(project)
    result = subprocess.run(
        ["node", "-e", renderer],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    return result.stdout


def test_room_plan_document_lists_the_plan_without_purchasing() -> None:
    html = _render_plan(
        {
            "status": "awaiting_approval",
            "brief": {
                "lifestyle": "reads at night",
                "style_preferences": "warm woods",
                "keep": ["oak dresser"],
                "avoid": ["pink"],
            },
            "rooms": {
                "living": {
                    "name": "Living room",
                    "room_type": "living",
                    "width_ft": 12,
                    "length_ft": 14,
                }
            },
            "spec_list": [
                {
                    "sku": "ART-SOFA-721",
                    "name": "Sven 72-inch sofa",
                    "lane": "must",
                    "status": "draft",
                    "price_cents": 129900,
                    "qty": 1,
                    "why": "Seats the room.",
                    "color": "charcoal",
                },
                {
                    "sku": "RUG-8X10-RST",
                    "name": "Rust rug",
                    "lane": "close",
                    "status": "draft",
                    "price_cents": 34900,
                    "qty": 1,
                    "why": "Optional color.",
                },
            ],
            "skipped": [{"label": "Linen drapery", "why": "Not in the catalog."}],
            "cart": [{"sku": "ART-LAMP-CER", "name": "Ceramic lamp", "price_cents": 12900, "qty": 2}],
            "budget": {
                "total_cents": 200000,
                "committed_cents": 0,
                "draft_cents": 164800,
                "planned_cents": 164800,
                "remaining_cents": 35200,
                "over_budget": False,
                "over_cents": 0,
            },
            "pending_approval": True,
            "rejected": ["Swap the lamp"],
        }
    )
    assert "Living room" in html
    assert "12 × 14 ft" in html
    assert "Ready to approve" in html
    assert "warm woods" in html
    assert "Avoid: pink" in html
    assert "Sven 72-inch sofa" in html
    assert "ART-SOFA-721" in html
    assert "Keep" in html
    assert "Optional" in html
    assert "$1299" in html
    assert "$1648 planned of $2000" in html
    assert "Remaining" not in html
    assert "Linen drapery" in html
    assert "Skip is not a spend line." in html
    assert "Ceramic lamp" in html
    assert "not in the budget" in html
    assert "Swap the lamp" in html
    assert "does not approve the list or purchase anything." in html
    assert "/api/chat" not in html

    over = _render_plan(
        {
            "pending_approval": True,
            "budget": {
                "total_cents": 200000,
                "committed_cents": 0,
                "draft_cents": 326400,
                "planned_cents": 326400,
                "remaining_cents": 200000,
                "over_budget": True,
                "over_cents": 126400,
            },
        }
    )
    assert "$3264 planned of $2000" in over
    assert "$1264 over the cap" in over
    assert "Remaining $2000" not in over

    empty = _render_plan({})
    assert "No room yet" in empty
    assert "Budget not set" in empty
    assert "No pieces on the list yet." in empty
    assert "Skipped" not in empty
    assert "Held in cart" not in empty

    hostile = _render_plan({"rooms": {"x": {"name": '<script>alert(1)</script>'}}})
    assert "<script>alert" not in hostile
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in hostile
