#!/usr/bin/env python3
"""將 formerly-neoclassic 的 24 張圖從 100interior.com 重新下載，
上傳到 Supabase Storage 的 classic/ 路徑，修復 404 問題。

背景：storage.objects.name 已改為 classic/，但 S3 實際檔案未移動，
      所以需要重新上傳到正確位置。

Usage (from project root):
    python -m style_kb.migration.migrate_neoclassic_storage          # dry run
    python -m style_kb.migration.migrate_neoclassic_storage --upload # 實際執行
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = "style-images"


def get_client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SERVICE_ROLE_KEY)


def fetch_neoclassic_files(client) -> list[dict]:
    """取得 24 張 formerly-neoclassic 圖的 DB 記錄。"""
    res = (
        client.table("style_images")
        .select("id, image_path, image_url, source_meta")
        .eq("style_id", "classic")
        .like("source_meta->>style", "%新古典%")
        .execute()
    )
    return res.data


def download_image(source_url: str, timeout: int = 20) -> bytes:
    """從 100interior.com 下載圖片 bytes。"""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DesignBridge/1.0)"}
    resp = httpx.get(source_url, headers=headers, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def upload_to_storage(client, storage_path: str, image_bytes: bytes) -> str:
    """上傳到 Supabase Storage，upsert=True 覆蓋已存在的 metadata 記錄。"""
    client.storage.from_(BUCKET).upload(
        path=storage_path,
        file=image_bytes,
        file_options={"content-type": "image/jpeg", "upsert": "true"},
    )
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"


def verify_url(url: str) -> bool:
    """確認 URL 可存取（HTTP 200）。"""
    try:
        resp = httpx.head(url, timeout=10, follow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="修復 neoclassic→classic storage 搬移")
    parser.add_argument("--upload", action="store_true", help="實際執行（預設：dry run）")
    args = parser.parse_args()
    dry_run = not args.upload

    if not dry_run and (not SUPABASE_URL or not SERVICE_ROLE_KEY):
        print("❌ 缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY")
        sys.exit(1)

    client = get_client()
    files = fetch_neoclassic_files(client)

    print(f"{'DRY RUN — ' if dry_run else ''}找到 {len(files)} 筆 formerly-neoclassic 圖片\n")

    success = failed = 0

    for i, row in enumerate(files, 1):
        storage_path = row["image_path"]          # classic/filename.jpg
        source_url = row["source_meta"]["url"]    # 100interior.com URL
        target_url = row["image_url"]             # 驗證用

        print(f"[{i:02d}/{len(files)}] {storage_path}")
        print(f"         source: {source_url}")

        if dry_run:
            print(f"         → [dry run] 會下載並上傳到 {storage_path}")
            success += 1
            continue

        try:
            img_bytes = download_image(source_url)
            print(f"         下載完成：{len(img_bytes) / 1024:.0f} KB")

            upload_to_storage(client, storage_path, img_bytes)
            print(f"         上傳完成")

            # 驗證
            time.sleep(0.5)
            if verify_url(target_url):
                print(f"         ✅ URL 可存取")
                success += 1
            else:
                print(f"         ⚠️  URL 仍 404，請手動確認")
                failed += 1

        except Exception as e:
            print(f"         ❌ 失敗：{e}")
            failed += 1

        time.sleep(0.3)  # 避免 rate limit

    print(f"\n{'='*50}")
    if dry_run:
        print(f"Dry run 完成，共 {success} 筆，加上 --upload 開始實際執行")
    else:
        print(f"完成：成功 {success} / 失敗 {failed}")


if __name__ == "__main__":
    main()
