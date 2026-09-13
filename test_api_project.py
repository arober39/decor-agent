from fastapi.testclient import TestClient

from app import store
from server import app


def setup_function() -> None:
    store.reset()


def test_studio_and_catalog_routes() -> None:
    client = TestClient(app)
    home = client.get("/")
    studio = client.get("/studio")
    catalog = client.get("/api/catalog", params={"limit": 4})
    assert home.status_code == 200
    assert b"Open studio" in home.content
    assert studio.status_code == 200
    assert b"Ask Decora" in studio.content
    assert catalog.status_code == 200
    products = catalog.json()["products"]
    assert len(products) == 4
    assert all(item["image_url"] for item in products)


def test_from_board_then_approve() -> None:
    client = TestClient(app)
    caps = client.get("/api/capabilities", params={"context_key": "http-board"})
    assert caps.status_code == 200
    assert caps.json()["board_intake"] is True

    mapped = client.post(
        "/api/project/from-board",
        json={"context_key": "http-board"},
    )
    assert mapped.status_code == 200
    body = mapped.json()
    assert body["pending_approval"] is True
    assert len(body["spec_list"]) == 6
    assert all(item["status"] == "draft" for item in body["spec_list"])

    approved = client.post(
        "/api/project/approve",
        json={"context_key": "http-board", "kind": "spec"},
    )
    assert approved.status_code == 200
    done = approved.json()
    assert done["pending_approval"] is False
    assert all(item["status"] == "committed" for item in done["spec_list"])
    assert done["status"] == "complete"
