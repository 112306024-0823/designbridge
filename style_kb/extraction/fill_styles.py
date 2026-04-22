#!/usr/bin/env python3
"""補齊各風格圖片至目標數量，只下載目標風格的圖。

流程（每個風格獨立執行）：
  1. 計算還需要幾張
  2. 從 API 取 works，只下載 style_cn 符合目標風格的封面圖
  3. 達到需求數量立即停止，不多爬
  4. 執行 quality_filter 過濾低品質圖

Usage (from project root):
    python -m style_kb.fill_styles              # 補到 100 張
    python -m style_kb.fill_styles --target 200
    python -m style_kb.fill_styles classic      # 只補指定風格
"""

from __future__ import annotations

import argparse
import sys; sys.stdout.reconfigure(encoding="utf-8")
import time
from pathlib import Path

from style_kb.collection.quality_filter import filter_style
from style_kb.scrapper.scraper_100 import (
    STYLE_CATEGORY_MAP, _create_session, _download_image,
    REQUEST_INTERVAL, PER_PAGE, MAX_PAGES, API_URL, REQUEST_TIMEOUT
)
from style_kb.collection.sort_raw_images import STYLE_MAP, IMAGE_EXTS
from style_kb.styles import STYLES

IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"
RAW_STAGE = Path(__file__).resolve().parent.parent / "raw" / "_fill_stage"

# API style_cn → style_id 反查
ZH_TO_ID = {zh: sid for zh, sid in STYLE_MAP.items()}


def count_images(style_id: str) -> int:
    d = IMAGES_DIR / style_id
    if not d.exists():
        return 0
    return len([p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTS])


def fill_one_style(session, style_id: str, target: int) -> None:
    current = count_images(style_id)
    needed = target - current
    if needed <= 0:
        print(f"  {style_id}: 已有 {current} 張，跳過")
        return

    print(f"\n  {style_id}: 現有 {current} 張，需再補 {needed} 張")

    category_id = STYLE_CATEGORY_MAP.get(style_id)
    if not category_id:
        print(f"  無對應 category，跳過")
        return

    dest_dir = IMAGES_DIR / style_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    page = 1

    while downloaded < needed and page <= MAX_PAGES:
        url = f"{API_URL}/v1/works?category_id={category_id}&page={page}&per_page={PER_PAGE}"
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT, verify=False)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    API 失敗: {e}")
            break

        works = data.get("data", [])
        if not works:
            break

        for work in works:
            if downloaded >= needed:
                break

            # 只下載 style_cn 對應目標風格的 work
            style_cn = work.get("style_cn", "").strip()
            if ZH_TO_ID.get(style_cn) != style_id:
                continue

            cover = work.get("cover_img")
            if not cover or not cover.get("url"):
                continue

            image_info = {
                "url": cover["url"],
                "work_id": work["id"],
                "work_name": work.get("name", ""),
                "style": style_cn,
                "size": work.get("size_cn", ""),
                "kind": work.get("kind_cn", ""),
                "region": work.get("region_cn", ""),
                "case_url": f"https://www.100.com.tw/cases/{work['id']}/",
            }

            if _download_image(session, image_info, dest_dir):
                downloaded += 1

        pagination = data.get("meta", {}).get("pagination", {})
        total_pages = pagination.get("total_pages", 1)
        print(f"    第 {page}/{total_pages} 頁，本風格已下載 {downloaded}/{needed}")

        if page >= total_pages:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL)

    print(f"  下載完成：+{downloaded} 張")

    # 品質過濾
    filter_style(style_id)
    final = count_images(style_id)
    print(f"  過濾後：{final} 張")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=100)
    parser.add_argument("styles", nargs="*", help="指定風格（預設：全部）")
    args = parser.parse_args()

    style_ids = [s[0] for s in STYLES] if not args.styles else args.styles

    print(f"目標：每個風格 >= {args.target} 張\n")
    print(f"{'風格':<15} {'現有':>6}  狀態")
    print("-" * 35)
    needs = []
    for sid in style_ids:
        n = count_images(sid)
        short = max(0, args.target - n)
        print(f"{sid:<15} {n:>6}  {'OK' if short == 0 else f'缺 {short}'}")
        if short > 0:
            needs.append(sid)

    if not needs:
        print("\n所有風格已達標。")
        return

    print(f"\n開始補圖：{', '.join(needs)}\n")
    session = _create_session()
    for sid in needs:
        fill_one_style(session, sid, args.target)

    print("\n最終數量：")
    for sid in style_ids:
        n = count_images(sid)
        print(f"  {sid:<15} {n:>6}  {'OK' if n >= args.target else f'仍不足 ({n})'}")


if __name__ == "__main__":
    main()
