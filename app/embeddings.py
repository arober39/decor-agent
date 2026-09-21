"""Shared embedding text and model id for ingest and search."""

from __future__ import annotations

from app.catalog import Product

COLLECTION = "decor_catalog"
MODEL_NAME = "all-MiniLM-L6-v2"


def product_to_text(product: Product) -> str:
    rooms = ", ".join(product.room_types)
    tags = ", ".join(product.tags)
    parts = [
        product.name,
        f"{product.brand} {product.category} for {rooms}.",
        f"Style: {product.style}.",
        f"Material: {product.material}." if product.material else "",
        f"Color: {product.color}.",
        f"Tags: {tags}." if tags else "",
        f"Dimensions: {product.dimensions}." if product.dimensions else "",
    ]
    return " ".join(part.strip() for part in parts if part.strip())


def avoid_tokens(avoid: str) -> list[str]:
    tokens: list[str] = []
    for chunk in avoid.replace(",", " ").split():
        token = chunk.strip().lower()
        if token:
            tokens.append(token)
    return tokens


def excluded_by_avoid(product: Product, avoid: str) -> bool:
    tokens = avoid_tokens(avoid)
    if not tokens:
        return False
    haystack = " ".join(
        [
            product.sku,
            product.name,
            product.brand,
            product.category,
            *product.tags,
        ]
    ).lower()
    return any(token in haystack for token in tokens)
