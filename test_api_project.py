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
