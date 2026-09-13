"""Sample mood board → catalog lanes. No vision model. No invented SKUs.

Pins that have no inventory become skip lines, not fake products.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.catalog import get_product, local_photo


@dataclass(frozen=True)
class BoardRule:
    label: str
    lane: str  # must | close | skip
    sku: str | None
    why: str
    image_url: str = ""


# Curated living-room board. Queries are implicit: each rule names a real SKU or none.
SAMPLE_LIVING_BOARD: tuple[BoardRule, ...] = (
    BoardRule(
        "Linen sofa, oak legs",
        "must",
        "ART-SOFA-721",
        "The board’s seating is the look. Sven 72-inch is the catalog linen sofa.",
        local_photo("pin-linen-sofa.jpg"),
    ),
    BoardRule(
        "Rust 8x10 rug",
        "must",
        "RUG-8X10-RST",
        "Rust 8x10 is in inventory. This is the ground.",
        local_photo("pin-rust-rug.jpg"),
    ),
    BoardRule(
        "Marble coffee table",
        "close",
        "ART-COF-MRB",
        "Hon marble 42-inch is the stone table in inventory.",
        local_photo("pin-marble-table.jpg"),
    ),
    BoardRule(
        "Ceramic table lamp",
        "close",
        "ART-LAMP-CER",
        "Glaze ceramic table lamp is the lighting row the pin asked for.",
        local_photo("pin-ceramic-lamp.jpg"),
    ),
    BoardRule(
        "Mohair lounge chair",
        "close",
        "ART-CHAIR-MOH",
        "Cline mohair lounge chair is in inventory.",
        local_photo("pin-mohair-chair.jpg"),
    ),
    BoardRule(
        "Linen drapery",
        "close",
        "WSM-DRAPE-LN",
        "Belgian linen 96-inch drapes are in inventory.",
        local_photo("pin-linen-drapery.jpg"),
    ),
)


def pin_image_url(label: str) -> str:
    for rule in SAMPLE_LIVING_BOARD:
        if rule.label == label:
            return rule.image_url
    return ""


def sample_pin_labels() -> list[str]:
    return [rule.label for rule in SAMPLE_LIVING_BOARD]


def resolve_sample_board() -> list[dict]:
    """Return lane decisions with catalog rows when they exist."""
    rows: list[dict] = []
    for rule in SAMPLE_LIVING_BOARD:
        product = get_product(rule.sku) if rule.sku else None
        if rule.lane != "skip" and product is None:
            rows.append(
                {
                    "label": rule.label,
                    "lane": "skip",
                    "sku": None,
                    "why": f"Mapped SKU {rule.sku} is missing from the catalog.",
                    "product": None,
                    "image_url": rule.image_url,
                }
            )
            continue
        rows.append(
            {
                "label": rule.label,
                "lane": rule.lane,
                "sku": product.sku if product else None,
                "why": rule.why,
                "product": product.as_dict() if product else None,
                "image_url": rule.image_url,
            }
        )
    return rows
