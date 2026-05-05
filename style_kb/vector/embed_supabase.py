#!/usr/bin/env python3
"""為 Supabase style_images 表產生 CLIP image embedding，存入 embedding 欄位（512 維）。

用 CLIP ViT-B-32 直接 encode 圖片，讓圖片和文字 query 落在同一向量空間。

Usage (from project root):
    python -m style_kb.vector.embed_supabase              # 處理所有 embedding IS NULL
    python -m style_kb.vector.embed_supabase --style modern
    python -m style_kb.vector.embed_supabase --reset      # 重算所有（含已有向量的）
"""

from __future__ import annotations

import argparse
import io
import os
import sys; sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
EMBEDDING_MODEL = "clip-ViT-B-32"
BATCH_SIZE = 16  # 圖片比文字重，縮小 batch


def fetch_image(url: str):
    """Download image URL → PIL.Image. Returns None on failure."""
    try:
        import httpx
        from PIL import Image
        resp = httpx.get(url, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        print(f"    ⚠️  下載失敗 {url[:60]}... → {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", help="只處理指定風格")
    parser.add_argument("--reset", action="store_true", help="重算所有行（含已有向量）")
    args = parser.parse_args()

    from supabase import create_client
    from sentence_transformers import SentenceTransformer

    client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"模型載入：{EMBEDDING_MODEL}")

    q = client.table("style_images").select("id,style_id,image_url")
    if not args.reset:
        q = q.is_("embedding", "null")
    if args.style:
        q = q.eq("style_id", args.style)
    rows = q.execute().data
    print(f"待處理：{len(rows)} 筆")

    if not rows:
        print("無需處理。")
        return

    done = 0
    skipped = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]

        images = []
        valid_rows = []
        for row in batch:
            img = fetch_image(row["image_url"])
            if img is not None:
                images.append(img)
                valid_rows.append(row)
            else:
                skipped += 1

        if not images:
            continue

        embeddings = model.encode(images, normalize_embeddings=True).tolist()

        for row, emb in zip(valid_rows, embeddings):
            client.table("style_images").update({"embedding": emb}).eq("id", row["id"]).execute()

        done += len(valid_rows)
        print(f"  {done}/{len(rows)} 完成，{skipped} 筆跳過...")

    print(f"\n完成：{done} 筆向量已寫入，{skipped} 筆跳過")


if __name__ == "__main__":
    main()
