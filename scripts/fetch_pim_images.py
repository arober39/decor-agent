"""Download or copy one JPEG per catalog SKU into web/images/{sku}.jpg.

Photos are stored on disk so the app never fabricates or hotlinks images
at request time. Sources live in scripts/pim_photos.json only.
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "app" / "pim" / "catalog.json"
PHOTOS = ROOT / "scripts" / "pim_photos.json"
IMAGES = ROOT / "web" / "images"
UA = "decora-pim/1.0 (local catalog photo fetch)"


def is_jpeg(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 32:
        return False
    return path.read_bytes()[:2] == b"\xff\xd8"


def unsplash_url(photo_id: str) -> str:
    return f"https://images.unsplash.com/{photo_id}?auto=format&fit=crop&w=800&q=70"


def fetch_url(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=45) as response:
        dest.write_bytes(response.read())


def main() -> int:
    products = json.loads(CATALOG.read_text())
    sources = json.loads(PHOTOS.read_text())
    skus = [row["sku"] for row in products]
    missing_source = [sku for sku in skus if sku not in sources]
    extra_source = sorted(set(sources) - set(skus))
    if missing_source:
        print("No photo source for:", ", ".join(missing_source), file=sys.stderr)
        return 1
    if extra_source:
        print("Photo sources not in PIM:", ", ".join(extra_source), file=sys.stderr)
        return 1

    IMAGES.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    wrote = 0
    skipped = 0
    for sku in skus:
        dest = IMAGES / f"{sku}.jpg"
        spec = sources[sku]
        if is_jpeg(dest):
            skipped += 1
            continue
        try:
            if "copy" in spec:
                src = ROOT / spec["copy"]
                if src.resolve() == dest.resolve() and is_jpeg(dest):
                    skipped += 1
                    continue
                shutil.copyfile(src, dest)
            elif "unsplash" in spec:
                fetch_url(unsplash_url(spec["unsplash"]), dest)
            else:
                raise ValueError(f"{sku} has no copy or unsplash source")
            if not is_jpeg(dest):
                dest.unlink(missing_ok=True)
                raise ValueError("not a jpeg")
            wrote += 1
            print(f"ok {sku}")
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
            failed.append(f"{sku}: {exc}")
            print(f"fail {sku}: {exc}", file=sys.stderr)

    print(f"wrote {wrote}, already present {skipped}, failed {len(failed)}")
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
