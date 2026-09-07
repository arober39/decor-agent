from app.catalog import get_product, search_products


def test_unknown_sku_does_not_exist() -> None:
    assert get_product("FAKE-SOFA") is None


def test_search_returns_real_skus() -> None:
    hits = search_products(query="walnut sofa")
    assert hits
    assert all(get_product(item.sku) is not None for item in hits)


def test_paint_for_dark_oak() -> None:
    hits = search_products(query="white dove dark oak", category="paint")
    assert any(item.sku == "BM-PAINT-WD" for item in hits)


def test_midcentury_matches_hyphenated_style() -> None:
    hits = search_products(query="12x14 living room midcentury $2000")
    assert any(item.sku == "ART-SOFA-721" for item in hits)


if __name__ == "__main__":
    test_unknown_sku_does_not_exist()
    test_search_returns_real_skus()
    test_paint_for_dark_oak()
    print("PASS test_catalog")
