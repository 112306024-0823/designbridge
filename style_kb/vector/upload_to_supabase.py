#!/usr/bin/env python3
"""Upload style images + meta to Supabase Storage & style_images table.

Usage (from project root):
    python -m style_kb.upload_to_supabase              # dry run
    python -m style_kb.upload_to_supabase --upload     # actually upload
    python -m style_kb.upload_to_supabase --upload --limit 100  # default 100/style
"""

from __future__ import annotations

import argparse
import json
import os
import sys; sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = "style-images"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

IMAGES_DIR = Path(__file__).resolve().parent / "images"
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


def get_client():
    try:
        from supabase import create_client
    except ImportError:
        print("請先安裝: pip install supabase")
        sys.exit(1)
    return create_client(SUPABASE_URL, SERVICE_ROLE_KEY)


def ensure_bucket(client) -> None:
    buckets = [b.name for b in client.storage.list_buckets()]
    if BUCKET not in buckets:
        client.storage.create_bucket(BUCKET, options={"public": True})
        print(f"✅ 建立 bucket: {BUCKET}")
    else:
        print(f"   Bucket 已存在: {BUCKET}")


def already_uploaded(client, style_id: str) -> set[str]:
    res = client.table("style_images").select("image_path").eq("style_id", style_id).execute()
    return {row["image_path"] for row in res.data}


def upload_style(client, style_id: str, limit: int, dry_run: bool) -> int:
    style_dir = IMAGES_DIR / style_id
    out_dir = OUTPUTS_DIR / style_id

    images = sorted([
        p for p in style_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTS
    ])[:limit]

    uploaded_paths = set() if dry_run else already_uploaded(client, style_id)
    count = 0

    for img_path in images:
        storage_path = f"{style_id}/{img_path.name}"
        if storage_path in uploaded_paths:
            continue

        meta_path = style_dir / (img_path.stem + "_meta.json")
        source_meta = None
        if meta_path.exists():
            source_meta = json.load(open(meta_path, encoding="utf-8"))

        kb_path = out_dir / (img_path.stem + ".json") if out_dir.exists() else None
        style_kb = None
        if kb_path and kb_path.exists():
            style_kb = json.load(open(kb_path, encoding="utf-8"))

        image_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"

        if dry_run:
            print(f"  [dry] {storage_path}")
            count += 1
            continue

        # Upload image
        with open(img_path, "rb") as f:
            mime = "image/jpeg" if img_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            client.storage.from_(BUCKET).upload(
                path=storage_path,
                file=f,
                file_options={"content-type": mime, "upsert": "false"},
            )

        # Insert row
        client.table("style_images").insert({
            "style_id": style_id,
            "image_path": storage_path,
            "image_url": image_url,
            "source_meta": source_meta,
            "style_kb": style_kb,
        }).execute()

        count += 1
        if count % 10 == 0:
            print(f"  [{style_id}] {count}/{min(limit, len(images))}...")

    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true", help="Actually upload (default: dry run)")
    parser.add_argument("--limit", type=int, default=100, help="Max images per style")
    args = parser.parse_args()

    dry_run = not args.upload

    if not dry_run and (not SUPABASE_URL or not SERVICE_ROLE_KEY):
        print("❌ 缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY")
        sys.exit(1)

    client = None if dry_run else get_client()

    if not dry_run:
        ensure_bucket(client)

    styles = [d.name for d in sorted(IMAGES_DIR.iterdir()) if d.is_dir()]
    total = 0

    for style_id in styles:
        style_dir = IMAGES_DIR / style_id
        available = len([p for p in style_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS])
        will_upload = min(args.limit, available)
        print(f"\n📁 {style_id} ({available} 張，上傳 {will_upload} 張)")
        n = upload_style(client, style_id, args.limit, dry_run)
        print(f"   {'會上傳' if dry_run else '已上傳'} {n} 張")
        total += n

    mode = "Dry run" if dry_run else "完成"
    print(f"\n{'='*40}")
    print(f"{mode}：共 {total} 筆")
    if dry_run:
        print("加上 --upload 開始實際上傳")


if __name__ == "__main__":
    main()
