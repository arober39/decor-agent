"""Nearest-neighbor catalog search via Qdrant. No LLM."""

from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from app.catalog import Product, get_product
from app.config import get_settings
from app.embeddings import COLLECTION, MODEL_NAME, excluded_by_avoid
from app.vector_env import resolve

load_dotenv()

_OVERFETCH = 20


@lru_cache(maxsize=1)
def _encoder() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=4)
def _client(url: str, api_key: str) -> QdrantClient:
    return QdrantClient(url=url, api_key=api_key, check_compatibility=False)


def _passes_filters(
    product: Product,
    category: str,
    room_type: str,
    max_price_cents: int | None,
    avoid: str,
) -> bool:
    if category and product.category != category.lower():
        return False
    if room_type and room_type.lower() not in product.room_types:
        return False
    if max_price_cents is not None and product.price_cents > max_price_cents:
        return False
    if excluded_by_avoid(product, avoid):
        return False
    return True


def search_semantic(
    query: str = "",
    category: str = "",
    room_type: str = "",
    max_price_cents: int | None = None,
    avoid: str = "",
    limit: int = 5,
    environment: str | None = None,
) -> list[Product]:
    if not (query or "").strip():
        return []
    try:
        name = (environment or get_settings().qdrant_environment).strip()
        env = resolve(name)
        vector = _encoder().encode(query.strip()).tolist()
        cap = max(limit * 4, _OVERFETCH)
        hits = _client(env.url, env.read_only_api_key()).query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=cap,
            with_payload=True,
        )
    except Exception:
        return []
    points = getattr(hits, "points", hits) or []
    matches: list[Product] = []
    seen: set[str] = set()
    for point in points:
        payload = getattr(point, "payload", None) or {}
        sku = str(payload.get("sku") or "").strip()
        if not sku or sku in seen:
            continue
        product = get_product(sku)
        if product is None:
            continue
        if not _passes_filters(product, category, room_type, max_price_cents, avoid):
            continue
        seen.add(sku)
        matches.append(product)
        if len(matches) >= max(1, min(limit, 12)):
            break
    return matches
