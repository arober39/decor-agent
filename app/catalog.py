"""Seeded product catalog. No LLM. This is the world, not the agent.

A design agent that names furniture from model weights is guessing.
Search returns these rows only. Unknown SKUs do not exist.
"""

from __future__ import annotations

from dataclasses import dataclass


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
        }


PRODUCTS: tuple[Product, ...] = (
    Product("ART-SOFA-721", "Sven 72-inch sofa", "Article", "sofa", ("living",), "mid-century", 129900, "charcoal", ("linen", "walnut")),
    Product("ART-SOFA-84V", "Sven 84-inch velvet sofa", "Article", "sofa", ("living",), "mid-century", 159900, "olive velvet", ("velvet",)),
    Product("IKE-SOFA-KL1", "KIVIK 3-seat sofa", "IKEA", "sofa", ("living",), "modern", 79900, "gray", ("family",)),
    Product("ART-CHAIR-LEO", "Leonie accent chair", "Article", "chair", ("living", "bedroom"), "mid-century", 39900, "oatmeal boucle", ("boucle",)),
    Product("ART-COF-48R", "Seno 48-inch round coffee table", "Article", "table", ("living",), "mid-century", 44900, "walnut", ("walnut", "round")),
    Product("RUG-8X10-JUT", "Handwoven jute rug 8x10", "Lulu and Georgia", "rug", ("living", "dining", "bedroom"), "natural", 39900, "natural jute", ("jute", "dark oak", "walnut")),
    Product("BM-PAINT-WD", "Benjamin Moore White Dove", "Benjamin Moore", "paint", ("living", "bedroom", "kitchen", "bathroom"), "classic", 8500, "warm white", ("dark oak", "walnut", "warm")),
    Product("BM-PAINT-SW", "Benjamin Moore Simply White", "Benjamin Moore", "paint", ("living", "bedroom", "kitchen"), "classic", 8500, "clean white", ("oak",)),
    Product("IKE-BED-MAL", "MALM queen bed", "IKEA", "bed", ("bedroom",), "modern", 29900, "white oak", ("queen",)),
    Product("ART-BED-CEN", "Ceni queen bed", "Article", "bed", ("bedroom",), "mid-century", 99900, "walnut", ("queen", "walnut")),
    Product("IKE-DESK-BEK", "BEKANT desk 63-inch", "IKEA", "desk", ("office", "bedroom"), "modern", 22900, "white / black", ("wfh",)),
    Product("ART-DESK-ODN", "Odette desk", "Article", "desk", ("office", "bedroom"), "mid-century", 59900, "walnut", ("wfh", "walnut")),
    Product("ART-LAMP-ARC", "Arca floor lamp", "Article", "lighting", ("living", "office"), "mid-century", 22900, "brass", ("brass",)),
    Product("IKE-VAN-GOD", "GODMORGON 24-inch vanity", "IKEA", "storage", ("bathroom",), "modern", 24900, "white", ("small-space",)),
    Product("WSM-MIRR-RND", "Round brass mirror 30-inch", "West Elm", "decor", ("bathroom", "living"), "classic", 19900, "brass", ("small-space",)),
    Product("RUG-BATH-TER", "Terrazzo bath mat", "Slowdown Studio", "rug", ("bathroom",), "playful", 4900, "speckled", ("terrazzo",)),
    Product("WSM-DIN-OAK", "Anton oak dining table 72-inch", "West Elm", "table", ("dining",), "organic modern", 89900, "white oak", ("oak",)),
    Product("ART-STOR-CRD", "Seno credenza", "Article", "storage", ("living", "dining"), "mid-century", 89900, "walnut", ("walnut", "media")),
    Product("IKE-KITCH-EN", "ENHET wall cabinet", "IKEA", "storage", ("kitchen",), "modern", 8900, "white", ("kitchen",)),
    Product("WSM-HW-BRS", "Unlacquered brass cabinet pull", "Schoolhouse", "hardware", ("kitchen", "bathroom"), "classic", 1800, "brass", ("farmhouse",)),
)


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
    tokens = [tok for tok in query.lower().split() if tok]
    scored: list[tuple[int, Product]] = []
    for product in PRODUCTS:
        if category and product.category != category.lower():
            continue
        if room_type and room_type.lower() not in product.room_types:
            continue
        if max_price_cents is not None and product.price_cents > max_price_cents:
            continue
        haystack = " ".join(
            [
                product.sku.lower(),
                product.name.lower(),
                product.brand.lower(),
                product.category,
                product.style,
                product.color.lower(),
                *product.room_types,
                *product.tags,
            ]
        )
        score = 1
        for token in tokens:
            if token in haystack:
                score += 3
        if tokens and score == 1:
            continue
        scored.append((score, product))
    scored.sort(key=lambda pair: (-pair[0], pair[1].price_cents))
    return [product for _, product in scored[: max(1, min(limit, 12))]]
