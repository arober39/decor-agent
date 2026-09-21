from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.catalog import PRODUCTS
from app.embeddings import COLLECTION, MODEL_NAME, product_to_text
from app.vector_env import resolve

DISTANCE = Distance.COSINE

"""Embed the PIM catalog into a named Qdrant environment.

Target is required: python scripts/ingest_catalog.py --environment local-test
"""

"""
Read it as a pipeline: which cluster -> turn furniture into sentences -> turn sentences into numbers ->
store numbers in that cluster.
"""

"""
Setup (imports and constants)
The script pulls in argparse (CLI flags), dotenv (.env keys), Qdrant, and sentence-transformers. 
It sticks the repo root on sys.path so from app.catalog import PRODUCTS works when you run 
python scripts/ingest_catalog.py instead of as a package.
COLLECTION and MODEL_NAME are named constants. 
Changing the model later changes vector size, which is the “wipe and rebuild” incident.
"""

"""
point_id
Qdrant will not take ART-SOFA-721 as an id. uuid5 turns that SKU into the same UUID every time, 
so a second ingest overwrites the same point instead of duplicating it.
"""
def point_id(sku: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, sku))

"""
parse_args
--environment is required=True with no default. If you forget it, argparse exits 
before anything talks to Qdrant. That is deliberate: the script must not “helpfully” hit 6333.
"""
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--environment",
        required=True,
        help="Name from environments.yaml (no default)",
    )
    return parser.parse_args(argv)

"""
ensure_collection
Ask Qdrant for decor_catalog.

Missing → create it with this model’s size (384) and Cosine distance.
Exists with size 384 → leave it.
Exists with a different size → print that you are dropping it, delete, recreate.
Wrong size means old vectors are garbage. You cannot mix 384 and 768 in one collection. 
This delete is the dangerous operation the later guardrails are about. 
Here it only runs on whatever --environment you passed.
"""
def ensure_collection(client: QdrantClient, size: int) -> None:
    try:
        info = client.get_collection(COLLECTION)
        existing = info.config.params.vectors.size
        if existing == size:
            return
        print(f"dropping {COLLECTION}: vector size {existing} != {size}")
        client.delete_collection(COLLECTION)
    except UnexpectedResponse:
        pass
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=size, distance=DISTANCE),
    )

"""
ingest — the actual sequence

1. resolve(environment) reads environments.yaml and gives you name, sensitivity, URL, API key. 
local-test → http://localhost:6333 + local key.
2. Print the target so you can see if you are about to write to the wrong place.
3. Load all-MiniLM-L6-v2. First time it downloads; later it uses the local cache.
4. get_sentence_embedding_dimension() → 384. Collection size must match this.
5. QdrantClient(url=..., api_key=...) opens that cluster only.
6. ensure_collection as above.
7. Build one string per PRODUCTS row, then model.encode(...) → a 384-float vector per row.
8. Wrap each as a PointStruct: id from SKU, vector, payload sku / price_cents / category 
(filters in step 3; not embedded).
9. upsert writes them. Print how many.
"""
def ingest(environment: str) -> int:
    env = resolve(environment)
    print(f"target={env.name} sensitivity={env.sensitivity} url={env.url}")
    model = SentenceTransformer(MODEL_NAME)
    size = model.get_sentence_embedding_dimension()
    client = QdrantClient(url=env.url, api_key=env.api_key())
    ensure_collection(client, size)
    texts = [product_to_text(product) for product in PRODUCTS]
    vectors = model.encode(texts, show_progress_bar=True)
    points = [
        PointStruct(
            id=point_id(product.sku),
            vector=vectors[i].tolist(),
            payload={
                "sku": product.sku,
                "price_cents": product.price_cents,
                "category": product.category,
            },
        )
        for i, product in enumerate(PRODUCTS)
    ]
    client.upsert(collection_name=COLLECTION, points=points)
    print(f"upserted {len(points)} points into {COLLECTION}")
    return 0

"""
Run only:

python scripts/ingest_catalog.py --environment local-test
"""
def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args(argv)
    return ingest(args.environment)


if __name__ == "__main__":
    raise SystemExit(main())