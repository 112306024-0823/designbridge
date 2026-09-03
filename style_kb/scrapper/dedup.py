"""Deduplication helpers for 100.com.tw image crawlers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "manifest" / "known_images.json"


def image_asset_key(url: str) -> str:
    """Stable filename key from a 100 CDN image URL."""
    clean = (url or "").split("!")[0].rstrip("/")
    name = Path(urlparse(clean).path).name
    return name or clean


def build_manifest_from_rows(rows: list[dict]) -> dict:
    """Build manifest dict from Supabase style_images rows."""
    image_keys: set[str] = set()
    image_ids: set[int] = set()
    work_ids: set[int] = set()
    case_urls: set[str] = set()

    for row in rows:
        meta = row.get("source_meta") or {}
        if not isinstance(meta, dict):
            continue

        if meta.get("case_url"):
            case_urls.add(str(meta["case_url"]))
        if meta.get("work_id") is not None:
            try:
                work_ids.add(int(meta["work_id"]))
            except (TypeError, ValueError):
                pass
        if meta.get("image_id") is not None:
            try:
                image_ids.add(int(meta["image_id"]))
            except (TypeError, ValueError):
                pass

        url = meta.get("url") or row.get("image_url") or ""
        key = image_asset_key(str(url))
        if key:
            image_keys.add(key)

        image_path = row.get("image_path") or ""
        if image_path:
            image_keys.add(Path(str(image_path)).name)

    return {
        "image_keys": sorted(image_keys),
        "image_ids": sorted(image_ids),
        "work_ids": sorted(work_ids),
        "case_urls": sorted(case_urls),
    }


def fetch_manifest_from_supabase() -> dict:
    """Load known images from Supabase style_images."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY")

    from supabase import create_client

    client = create_client(url, key)
    rows: list[dict] = []
    page_size = 1000
    offset = 0

    while True:
        res = (
            client.table("style_images")
            .select("image_path,image_url,source_meta")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = res.data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    return build_manifest_from_rows(rows)


def save_manifest(manifest: dict, path: Path = MANIFEST_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    if not path.is_file():
        return {"image_keys": [], "image_ids": [], "work_ids": [], "case_urls": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "image_keys": set(data.get("image_keys") or []),
        "image_ids": set(data.get("image_ids") or []),
        "work_ids": set(data.get("work_ids") or []),
        "case_urls": set(data.get("case_urls") or []),
    }


def is_duplicate(
    *,
    image_key: str,
    image_id: int | None,
    manifest: dict,
) -> bool:
    if image_key and image_key in manifest.get("image_keys", set()):
        return True
    if image_id is not None and image_id in manifest.get("image_ids", set()):
        return True
    return False
