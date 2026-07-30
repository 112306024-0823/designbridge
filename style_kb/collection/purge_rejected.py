#!/usr/bin/env python3
"""批次刪除圖片：先刪 Storage，再刪 Table row。

ID 清單從 generate_review.py 的 HTML 頁面複製而來。

Usage (from project root):
    python -m style_kb.collection.purge_rejected --ids id1,id2,id3
    python -m style_kb.collection.purge_rejected --ids id1,id2,id3 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")
load_dotenv()

BUCKET = "style-images"


def get_supabase():
    from supabase import create_client
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="批次刪除 Storage + Table")
    parser.add_argument("--ids",     required=True, help="逗號分隔的 UUID 清單")
    parser.add_argument("--dry-run", action="store_true", help="只列出要刪的，不實際刪除")
    args = parser.parse_args()

    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    if not ids:
        print("❌ 沒有有效的 ID")
        sys.exit(1)

    dry = args.dry_run
    client = get_supabase()

    # 查詢要刪除的 row（取得 image_path）
    rows = (client.table("style_images")
            .select("id, image_path, style_id, quality_score, quality_flags")
            .in_("id", ids)
            .execute()).data or []

    if not rows:
        print("❌ 找不到任何符合的 row")
        sys.exit(1)

    print(f"{'[DRY RUN] ' if dry else ''}共 {len(rows)} 筆待刪除\n")

    success = failed = 0

    for row in rows:
        row_id     = row["id"]
        image_path = row["image_path"]
        style_id   = row["style_id"]
        score      = row.get("quality_score", "?")
        flags      = row.get("quality_flags") or {}
        issues     = [k for k, v in flags.items() if v is True and k != "orientation"]

        print(f"  {style_id:12s} score={score}  [{', '.join(issues) or 'ok'}]")
        print(f"             path: {image_path}")

        if dry:
            print(f"             → [dry run] 跳過")
            success += 1
            continue

        # 1. 刪 Storage
        try:
            client.storage.from_(BUCKET).remove([image_path])
            print(f"             ✅ Storage 刪除")
        except Exception as e:
            print(f"             ⚠️  Storage 刪除失敗：{e}（繼續刪 Table）")

        # 2. 刪 Table
        try:
            client.table("style_images").delete().eq("id", row_id).execute()
            print(f"             ✅ Table 刪除")
            success += 1
        except Exception as e:
            print(f"             ❌ Table 刪除失敗：{e}")
            failed += 1

        print()

    print("=" * 50)
    if dry:
        print(f"[DRY RUN] 共 {success} 筆，加上 --dry-run 移除後實際執行")
    else:
        print(f"完成：成功 {success} / 失敗 {failed}")


if __name__ == "__main__":
    main()
