"""Put a wrong-size decor_catalog on local-test only.

python scripts/seed_broken_local_test.py --environment local-test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, VectorParams

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.embeddings import COLLECTION
from app.vector_env import resolve

WRONG_SIZE = 768
ALLOWED = "local-test"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args(argv)
    if args.environment != ALLOWED:
        raise SystemExit(f"refusing {args.environment!r}; only {ALLOWED} is allowed")
    env = resolve(args.environment)
    print(f"target={env.name} url={env.url} size={WRONG_SIZE}")
    if "6333" not in env.hosts[0]:
        raise SystemExit(f"refusing url {env.url}; expected local-test on 6333")
    client = QdrantClient(url=env.url, api_key=env.api_key(), check_compatibility=False)
    try:
        client.delete_collection(COLLECTION)
        print(f"deleted {COLLECTION}")
    except UnexpectedResponse:
        print(f"{COLLECTION} was not present")
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=WRONG_SIZE, distance=Distance.COSINE),
    )
    print(f"created {COLLECTION} size={WRONG_SIZE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
