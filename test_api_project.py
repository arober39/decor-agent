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
    assert b"starter brief" in studio.content
    assert b"sample board" in studio.content
    assert b"start-guide" in studio.content
    assert b"list-locked" in studio.content
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
    assert body["skipped"] == []
    assert all(item["sku"] for item in body["spec_list"])
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


def test_fit_budget_route_drops_the_close_rug() -> None:
    client = TestClient(app)
    client.post("/api/project/from-board", json={"context_key": "http-fit"})
    fitted = client.post("/api/project/fit-budget", json={"context_key": "http-fit"})
    assert fitted.status_code == 200
    body = fitted.json()
    skus = {item["sku"] for item in body["spec_list"]}
    assert "ART-SOFA-721" in skus
    assert "RUG-8X10-RST" in skus
    assert "RUG-BATH-TER" not in skus
    assert body["budget"]["over_budget"] is False


if __name__ == "__main__":
    setup_function()
    test_from_board_then_approve()
    print("PASS test_api_project")
