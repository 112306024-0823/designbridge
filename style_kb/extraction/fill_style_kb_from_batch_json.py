#!/usr/bin/env python3
"""Fill/overwrite style_kb for a pre-downloaded batch JSON.

This is designed for the agent workflow:
- A batch JSON is created under `artifacts/style_kb_agent/<batch>/<batch>.json`
  with `id`, `style_id`, `small_path`.
- We feed the local (downscaled) image bytes into the vision model and write
  the resulting `style_kb` back to Supabase.

Usage (from project root):
    python -m style_kb.extraction.fill_style_kb_from_batch_json --batch artifacts/style_kb_agent/batch32/batch32.json
    python -m style_kb.extraction.fill_style_kb_from_batch_json --batch ... --limit 10 --sleep 4
    python -m style_kb.extraction.fill_style_kb_from_batch_json --batch ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(encoding="utf-8")

# project root + env
_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv

load_dotenv(_root / ".env")
load_dotenv()

from style_kb.extraction.fill_style_kb_from_supabase import (  # noqa: E402
    STYLE_NAME_MAP,
    extract_style_kb,
    get_supabase,
)


def _read_image_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if not data:
        raise RuntimeError(f"Empty image file: {path}")
    return data


def _load_batch(batch_json: Path) -> list[dict[str, Any]]:
    items = json.loads(batch_json.read_text(encoding="utf-8"))
    if not isinstance(items, list) or not items:
        raise RuntimeError("Batch JSON must be a non-empty list.")
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill style_kb from a batch JSON using vision model.")
    parser.add_argument("--batch", required=True, help="Path to batch json (e.g. artifacts/.../batch32.json)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=None, help="Seconds to sleep between requests.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-raw", action="store_true", help="Use raw_path instead of small_path.")
    args = parser.parse_args()

    batch_json = Path(args.batch)
    items = _load_batch(batch_json)

    offset = max(0, int(args.offset or 0))
    if args.limit is not None:
        items = items[offset : offset + int(args.limit)]
    else:
        items = items[offset:]

    sleep_sec = float(args.sleep) if args.sleep is not None else float(os.getenv("GEMINI_SLEEP_SEC", "4.0"))

    print("=" * 65)
    print("  DesignBridge — fill_style_kb_from_batch_json")
    print("=" * 65)
    print(f"  batch: {batch_json}")
    print(f"  items: {len(items)} (offset={offset})")
    print(f"  sleep: {sleep_sec}s")
    print(f"  mode : {'DRY' if args.dry_run else 'WRITE'}")
    print("=" * 65)

    client = get_supabase()
    ok = fail = 0
    total = len(items)

    for i, item in enumerate(items, 1):
        row_id = str(item["id"])
        style_id = str(item.get("style_id") or "")
        style_name = STYLE_NAME_MAP.get(style_id, style_id)

        img_path = Path(str(item["raw_path"] if args.use_raw else item["small_path"]))
        prefix = f"[{i:>3}/{total}] {style_id or '-'} | {row_id[:8]}"

        if args.dry_run:
            print(f"  [DRY] {prefix} → {img_path}")
            ok += 1
            continue

        try:
            image_bytes = _read_image_bytes(img_path)
            style_kb = extract_style_kb(
                image_bytes=image_bytes,
                mime_type="image/jpeg",
                style_id=style_id,
                style_name=style_name,
            )
            client.table("style_images").update({"style_kb": style_kb}).eq("id", row_id).execute()
            ok += 1
            tags = (style_kb.get("style_info") or {}).get("tags", [])
            print(f"  ✅ {prefix} → tags={tags}")
        except Exception as e:
            fail += 1
            print(f"  ❌ {prefix} → {e}")

        time.sleep(sleep_sec)

    print()
    print("=" * 65)
    print(f"  done: ok={ok} fail={fail}")
    print("=" * 65)


if __name__ == "__main__":
    main()

