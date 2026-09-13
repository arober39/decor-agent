from pathlib import Path

from app.catalog import PRODUCTS, catalog_image_url, cheaper_in_room, get_product, search_products

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


def test_paint_for_dark_oak() -> None:
    hits = search_products(query="white dove dark oak", category="paint")
    assert any(item.sku == "BM-PAINT-WD" for item in hits)


def test_brass_lamp_is_arca_already_on_sample_board() -> None:
    hits = search_products(query="brass lamp", category="lighting", room_type="living", limit=12)
    assert any(item.sku == "ART-LAMP-ARC" for item in hits)
    assert get_product("ART-LAMP-ARC").color == "brass"
    brass = [item for item in hits if "brass" in item.color]
    assert [item.sku for item in brass] == ["ART-LAMP-ARC"]


def test_living_rug_has_no_cheaper_bathroom_mat() -> None:
    options = cheaper_in_room("RUG-8X10-RST", "living")
    assert all(item.sku != "RUG-BATH-TER" for item in options)
    assert any(item.sku == "RUG-5X7-JUT" for item in options)
    assert get_product("RUG-BATH-TER").room_types == ("bathroom",)
    assert get_product("RUG-8X10-IVO").color == "ivory"
    assert "white" in get_product("RUG-8X10-IVO").tags


def test_sven_has_cheaper_living_sofa() -> None:
    options = cheaper_in_room("ART-SOFA-721", "living")
    assert any(item.sku == "IKE-SOFA-KL1" for item in options)


def test_midcentury_matches_hyphenated_style() -> None:
    hits = search_products(query="12x14 living room midcentury $2000", limit=12)
    assert any(item.sku == "ART-SOFA-721" for item in hits)


if __name__ == "__main__":
    test_unknown_sku_does_not_exist()
    test_every_sku_has_local_jpeg()
    test_every_room_has_usable_coverage()
    test_search_returns_real_skus()
    test_paint_for_dark_oak()
    print("PASS test_catalog")
