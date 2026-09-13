"""Product catalog loaded from the PIM. No LLM. This is the world, not the agent.

A design agent that names furniture from model weights is guessing.
Search returns these rows only. Unknown SKUs do not exist.
Every SKU has a pre-stored photo at /web/images/{sku}.jpg.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


_PIM_PATH = Path(__file__).resolve().parent / "pim" / "catalog.json"


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    brand: str
    category: str
    room_types: tuple[str, ...]
    style: str
    price_cents: int
    color: str
    tags: tuple[str, ...]
    material: str = ""
    dimensions: str = ""
    in_stock: bool = True
    qty_on_hand: int = 8

    def as_dict(self) -> dict:
        return {
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "room_types": list(self.room_types),
            "style": self.style,
            "price_cents": self.price_cents,
            "price_dollars": round(self.price_cents / 100, 2),
            "color": self.color,
            "tags": list(self.tags),
            "material": self.material,
            "dimensions": self.dimensions,
            "in_stock": self.in_stock,
            "qty_on_hand": self.qty_on_hand,
            "image_url": catalog_image_url(self.sku),
        }


def local_photo(filename: str) -> str:
    return f"/web/images/{filename}"


def catalog_image_url(sku: str) -> str:
    return local_photo(f"{sku.strip().upper()}.jpg")


def _product_from_row(row: dict) -> Product:
    qty = int(row.get("qty_on_hand", 8))
    return Product(
        sku=str(row["sku"]).strip().upper(),
        name=row["name"],
        brand=row["brand"],
        category=row["category"],
        room_types=tuple(row["room_types"]),
        style=row["style"],
        price_cents=int(row["price_cents"]),
        color=row["color"],
        tags=tuple(row.get("tags") or ()),
        material=str(row.get("material") or ""),
        dimensions=str(row.get("dimensions") or ""),
        in_stock=bool(row.get("in_stock", qty > 0)),
        qty_on_hand=qty,
    )


def _load_products() -> tuple[Product, ...]:
    rows = json.loads(_PIM_PATH.read_text())
    products = tuple(_product_from_row(row) for row in rows)
    skus = [product.sku for product in products]
    if len(skus) != len(set(skus)):
        raise ValueError("PIM catalog has duplicate SKUs")
    return products


PRODUCTS: tuple[Product, ...] = _load_products()


_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "for",
        "i",
        "my",
        "of",
        "plan",
        "room",
        "the",
        "to",
        "under",
        "want",
        "with",
        "budget",
    }
)


def _fold(text: str) -> str:
    """mid-century and midcentury should hit the same inventory row."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def get_product(sku: str) -> Product | None:
    needle = sku.strip().upper()
    for product in PRODUCTS:
        if product.sku == needle:
            return product
    return None


def search_products(
    query: str = "",
    category: str = "",
    room_type: str = "",
    max_price_cents: int | None = None,
    limit: int = 5,
) -> list[Product]:
    tokens = []
    for tok in query.lower().replace("-", " ").split():
        bare = tok.lstrip("$")
        if tok in _STOP or bare in _STOP:
            continue
        if re.fullmatch(r"\d+(x\d+)?", bare) or re.fullmatch(r"\d+(?:,\d{3})*(?:\.\d+)?", bare):
            continue
        folded = _fold(tok)
        if folded:
            tokens.append(folded)
    scored: list[tuple[int, Product]] = []
    for product in PRODUCTS:
        if category and product.category != category.lower():
            continue
        if room_type and room_type.lower() not in product.room_types:
            continue
        if max_price_cents is not None and product.price_cents > max_price_cents:
            continue
        exact = {
            _fold(product.sku),
            _fold(product.brand),
            _fold(product.category),
            _fold(product.style),
            _fold(product.color),
            _fold(product.material),
            _fold(product.dimensions),
            *(_fold(room) for room in product.room_types),
            *(_fold(tag) for tag in product.tags),
        }
        name_fold = _fold(product.name)
        score = 1
        for token in tokens:
            if token in exact or token in name_fold:
                score += 3
        if tokens and score == 1:
            continue
        scored.append((score, product))
    scored.sort(key=lambda pair: (-pair[0], pair[1].price_cents))
    return [product for _, product in scored[: max(1, min(limit, 12))]]
