from pathlib import Path

from app.catalog import PRODUCTS, catalog_image_url, get_product, search_products

_IMAGES = Path(__file__).resolve().parent / "web" / "images"
_ROOMS = ("living", "bedroom", "dining", "kitchen", "bathroom", "office")


def test_unknown_sku_does_not_exist() -> None:
    assert get_product("FAKE-SOFA") is None


def test_every_sku_has_local_jpeg() -> None:
    assert len(PRODUCTS) >= 60
    for product in PRODUCTS:
        path = _IMAGES / f"{product.sku}.jpg"
        assert path.is_file(), f"missing photo {product.sku}"
        assert path.read_bytes()[:2] == b"\xff\xd8", f"not a jpeg {product.sku}"
        url = catalog_image_url(product.sku)
        assert url == f"/web/images/{product.sku}.jpg"
        assert not url.startswith("https://")
        assert product.as_dict()["image_url"] == url


def test_every_room_has_usable_coverage() -> None:
    for room in _ROOMS:
        rows = [item for item in PRODUCTS if room in item.room_types]
        assert len(rows) >= 6, room
        assert len({item.category for item in rows}) >= 3, room


def test_search_returns_real_skus() -> None:
    hits = search_products(query="walnut sofa")
    assert hits
    assert all(get_product(item.sku) is not None for item in hits)
