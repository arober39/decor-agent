from app.board import resolve_sample_board, sample_pin_labels
from app.catalog import get_product


def test_sample_board_uses_real_skus_or_skip() -> None:
    rows = resolve_sample_board()
    labels = sample_pin_labels()
    assert [row["label"] for row in rows] == labels
    for row in rows:
        if row["lane"] == "skip":
            assert row["sku"] is None
            assert row["product"] is None
            assert row["image_url"]
            continue
        assert row["lane"] in {"must", "close"}
        product = get_product(row["sku"])
        assert product is not None
        assert product.sku == row["sku"]
        assert row["image_url"]


def test_sample_board_maps_inventory_pins() -> None:
    rows = resolve_sample_board()
    by_label = {row["label"]: row for row in rows}
    assert by_label["Linen sofa, oak legs"]["sku"] == "ART-SOFA-721"
    assert by_label["Linen sofa, oak legs"]["lane"] == "must"
    assert by_label["Rust 8x10 rug"]["sku"] == "RUG-8X10-RST"
    assert by_label["Rust 8x10 rug"]["lane"] == "must"
    assert by_label["Marble coffee table"]["sku"] == "ART-COF-MRB"
    assert by_label["Ceramic table lamp"]["sku"] == "ART-LAMP-CER"
    assert by_label["Mohair lounge chair"]["sku"] == "ART-CHAIR-MOH"
    assert by_label["Linen drapery"]["sku"] == "WSM-DRAPE-LN"
    assert all(row["lane"] != "skip" for row in rows)
    assert by_label["Linen sofa, oak legs"]["image_url"]
    assert by_label["Mohair lounge chair"]["image_url"]


if __name__ == "__main__":
    test_sample_board_uses_real_skus_or_skip()
    test_sample_board_maps_inventory_pins()
    print("PASS test_board")
