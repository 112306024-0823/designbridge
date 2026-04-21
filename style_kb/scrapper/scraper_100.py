#!/usr/bin/env python3
"""爬取 100室內設計 (100.com.tw) 的設計案例圖片。

100.com.tw 是 Nuxt SPA，頁面由 JS 渲染，無法直接 requests 頁面。
改用官方 REST API：https://api.100.com.tw/v1/works?category_id={id}&page={page}

Usage (from project root):
    python -m style_kb.scraper_100                    # 爬取所有風格
    python -m style_kb.scraper_100 modern nordic      # 只爬取指定風格

Output:
    style_kb/raw/100interior/<style_id>/              # 下載圖片
    style_kb/raw/urls/100interior_<style_id>.txt      # 案例 URL 清單
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

try:
    from style_kb.styles import STYLES
except ModuleNotFoundError:
    from styles import STYLES

# ──────────────────────────────────────────────────────────────────────────

BASE_URL = "https://www.100.com.tw"
API_URL = "https://api.100.com.tw"
RAW_DIR = Path(__file__).resolve().parent / "raw" / "100interior"
URLS_DIR = Path(__file__).resolve().parent / "raw" / "urls"

# 風格 ID → 100.com.tw 的分類 ID 對應
STYLE_CATEGORY_MAP = {
    "modern": "1",
    "country": "6",
    "classic": "3",
    "nordic": "20",
    "industrial": "7",
    "japanese": "10",
    "american": "5",
    "luxury": "4",
    "neoclassic": "21",
}

REQUEST_TIMEOUT = 15
REQUEST_INTERVAL = 1.0
PER_PAGE = 30
MAX_PAGES = 100  # 最多爬 100 頁（3000 張）

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _create_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": BASE_URL,
    })
    return session


def _collect_works(session: requests.Session, category_id: str) -> list[dict]:
    """透過 REST API 分頁取得所有 works。"""
    works = []
    page = 1

    while page <= MAX_PAGES:
        url = f"{API_URL}/v1/works?category_id={category_id}&page={page}&per_page={PER_PAGE}"
        print(f"  📄 第 {page} 頁: {url}")

        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT, verify=False)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    ❌ 請求失敗: {e}")
            break

        items = data.get("data", [])
        if not items:
            break

        works.extend(items)
        print(f"    ✅ 取得 {len(items)} 筆（累計 {len(works)}）")

        meta = data.get("meta", {}).get("pagination", {})
        total_pages = meta.get("total_pages", 1)
        if page >= total_pages:
            break

        page += 1
        time.sleep(REQUEST_INTERVAL)

    return works


def _download_image(session: requests.Session, image_info: dict, output_dir: Path) -> bool:
    """下載單張圖片。"""
    try:
        url = image_info["url"]

        # 去掉縮圖後綴取原圖（如 !t1000.webp）
        clean_url = url.split("!")[0]

        parsed = urlparse(clean_url)
        filename = Path(parsed.path).name
        if not filename:
            filename = f"img_{image_info['work_id']}.jpg"

        output_path = output_dir / filename

        if output_path.exists():
            return True

        r = session.get(clean_url, timeout=REQUEST_TIMEOUT, verify=False)
        r.raise_for_status()

        # 檢查檔案大小 (≥ 50KB)
        if len(r.content) < 50 * 1024:
            return False

        output_path.write_bytes(r.content)

        meta_path = output_dir / f"{output_path.stem}_meta.json"
        meta_path.write_text(json.dumps(image_info, ensure_ascii=False, indent=2), encoding="utf-8")

        return True

    except Exception as e:
        print(f"      ❌ 下載失敗: {e}")
        return False


def scrape_style(session: requests.Session, style_id: str, category_id: str) -> None:
    """爬取單個風格的所有 works 封面圖。"""
    style_name = dict(STYLES)[style_id]
    print(f"\n📁 [{style_name} / {style_id}]")

    output_dir = RAW_DIR / style_id
    output_dir.mkdir(parents=True, exist_ok=True)
    URLS_DIR.mkdir(parents=True, exist_ok=True)

    # 第 1 步：從 API 取得所有 works
    print(f"  [1/2] 透過 API 取得 works...")
    works = _collect_works(session, category_id)

    if not works:
        print(f"  ⚠️  未找到任何 works")
        return

    # 保存 work 頁面 URL 清單
    case_urls = [f"{BASE_URL}/cases/{w['id']}/" for w in works]
    urls_file = URLS_DIR / f"100interior_{style_id}.txt"
    urls_file.write_text("\n".join(case_urls), encoding="utf-8")
    print(f"  ✅ 已保存 {len(works)} 個 work URL")

    # 第 2 步：下載封面圖
    print(f"  [2/2] 下載封面圖...")
    success_count = 0

    for work in works:
        cover = work.get("cover_img")
        if not cover or not cover.get("url"):
            continue

        image_info = {
            "url": cover["url"],
            "work_id": work["id"],
            "work_name": work.get("name", ""),
            "style": work.get("style_cn", ""),
            "size": work.get("size_cn", ""),
            "kind": work.get("kind_cn", ""),
            "region": work.get("region_cn", ""),
            "case_url": f"{BASE_URL}/cases/{work['id']}/",
        }

        if _download_image(session, image_info, output_dir):
            success_count += 1

    print(f"  ✅ 下載完成: {success_count}/{len(works)} 張")


def main() -> None:
    parser = argparse.ArgumentParser(description="爬取 100室內設計圖片")
    parser.add_argument(
        "styles",
        nargs="*",
        default=None,
        help="指定要爬的風格（預設：所有風格）",
    )
    args = parser.parse_args()

    styles_to_scrape = []
    if args.styles:
        for style_id in args.styles:
            if style_id in STYLE_CATEGORY_MAP:
                styles_to_scrape.append((style_id, STYLE_CATEGORY_MAP[style_id]))
            else:
                print(f"⚠️  未知風格: {style_id}")
    else:
        styles_to_scrape = list(STYLE_CATEGORY_MAP.items())

    if not styles_to_scrape:
        print("❌ 沒有有效的風格指定")
        return

    session = _create_session()

    print("=" * 60)
    print(f"🚀 開始爬取 100室內設計 ({len(styles_to_scrape)} 個風格)")
    print("=" * 60)

    for style_id, category_id in styles_to_scrape:
        scrape_style(session, style_id, category_id)

    print("\n" + "=" * 60)
    print("✅ 完成！")
    print(f"📁 圖片已保存到: {RAW_DIR}")
    print(f"📄 URL 清單已保存到: {URLS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
