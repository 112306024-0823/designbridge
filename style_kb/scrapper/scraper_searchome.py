#!/usr/bin/env python3
"""爬取設計家 Searchome (searchome.net) 的設計案例圖片。

Usage (from project root):
    python -m style_kb.scraper_searchome                    # 爬取所有風格
    python -m style_kb.scraper_searchome modern nordic      # 只爬取指定風格

Output:
    style_kb/raw/searchome/<style_id>/                      # 下載圖片
    style_kb/raw/urls/searchome_<style_id>.txt              # 案例 URL 清單
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from style_kb.styles import STYLES
except ModuleNotFoundError:
    from styles import STYLES

# ──────────────────────────────────────────────────────────────────────────

BASE_URL = "https://www.searchome.net"
RAW_DIR = Path(__file__).resolve().parent / "raw" / "searchome"
URLS_DIR = Path(__file__).resolve().parent / "raw" / "urls"

# 風格 ID → Searchome 的分類代碼
STYLE_CATEGORY_MAP = {
    "modern": "modern",
    "country": "country",
    "classic": "classical",
    "nordic": "scandinavia",
    "industrial": "industrial",
    "japanese": "japanese",
    "american": "american",
    "luxury": "luxury",
    "neoclassic": "neoclassic",
}

# 爬蟲設定
REQUEST_TIMEOUT = 15
REQUEST_INTERVAL = 1.0  # 秒
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _create_session() -> requests.Session:
    """建立 requests session 並設定重試邏輯。"""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    
    return session


def _collect_case_urls(session: requests.Session, category_code: str) -> list[str]:
    """爬取分類頁面的案例 URL（支援分頁）。"""
    urls = []
    page_num = 1

    while True:
        # solution.aspx 用 whr 參數篩選風格，idx 為頁碼
        search_url = f"{BASE_URL}/solution.aspx?whr={category_code}&idx={page_num}"
        print(f"  📄 第 {page_num} 頁: {search_url}")

        try:
            response = session.get(search_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response.encoding = "utf-8"
        except Exception as e:
            print(f" 請求失敗: {e}")
            break

        soup = BeautifulSoup(response.text, "html.parser")

        # 案例連結在 article.aspx?id= 格式
        case_links = soup.select("a[href*='article.aspx?id=']")

        if not case_links:
            print(f"此頁無案例，停止分頁")
            break

        new_count = 0
        for link in case_links:
            href = link.get("href")
            if href:
                full_url = urljoin(BASE_URL, href)
                if full_url not in urls:
                    urls.append(full_url)
                    new_count += 1

        print(f"新增 {new_count} 個案例（累計 {len(urls)}）")

        if new_count == 0:
            break

        page_num += 1
        if page_num > 50:
            break

        time.sleep(REQUEST_INTERVAL)

    return urls


def _collect_images_from_case(session: requests.Session, case_url: str) -> list[dict]:
    """從案例頁抓取圖片 URL 與元資訊。"""
    images = []
    
    try:
        response = session.get(case_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        response.encoding = "utf-8"
    except Exception as e:
        print(f"請求失敗: {e}")
        return images
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # 抓取標題
    title_elem = soup.select_one("h1, .case-title, .title")
    title = title_elem.get_text(strip=True) if title_elem else "unknown"
    
    # 圖片用 lazy load：src 是佔位圖 space.png，真實圖在 data-src
    img_elements = soup.select("img[data-src]")

    for idx, img in enumerate(img_elements):
        src = img.get("data-src", "").strip()
        alt = img.get("alt", "")

        if not src:
            continue

        # 只要 CDN 的室內設計圖，排除頭像、logo 等
        if "hmgcdn" not in src and "searchome-aws" not in src:
            continue
        if any(x in src.lower() for x in ["logo", "icon", "avatar", "memberphoto", "space.png"]):
            continue

        images.append({
            "url": src,
            "case_title": title,
            "case_url": case_url,
            "alt": alt,
            "index": idx,
        })
    
    return images


def _download_image(session: requests.Session, image_info: dict, output_dir: Path) -> bool:
    """下載單張圖片。"""
    try:
        url = image_info["url"]
        
        # 取得檔名
        parsed = urlparse(url)
        filename = Path(parsed.path).name
        if not filename:
            filename = f"img_{image_info['index']:03d}.jpg"
        
        output_path = output_dir / filename
        
        # 如果已存在則跳過
        if output_path.exists():
            return True
        
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        # 檢查檔案大小 (≥ 100KB)
        if len(response.content) < 100 * 1024:
            return False
        
        # 保存圖片
        output_path.write_bytes(response.content)
        
        # 保存元資訊
        meta_path = output_dir / f"{output_path.stem}_meta.json"
        meta_path.write_text(json.dumps(image_info, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return True
    
    except Exception as e:
        print(f"      ⚠️  下載失敗: {e}")
        return False


def scrape_style(session: requests.Session, style_id: str, category_code: str) -> None:
    """爬取單個風格的所有案例圖片。"""
    style_name = dict(STYLES)[style_id]
    print(f"\n📁 [{style_name} / {style_id}]")
    
    # 建立輸出目錄
    output_dir = RAW_DIR / style_id
    output_dir.mkdir(parents=True, exist_ok=True)
    URLS_DIR.mkdir(parents=True, exist_ok=True)
    
    # 第 1 步：收集案例 URL
    print(f"  [1/3] 收集案例 URL...")
    case_urls = _collect_case_urls(session, category_code)
    
    if not case_urls:
        print(f"  ⚠️  未找到任何案例")
        return
    
    # 保存 URL 清單
    urls_file = URLS_DIR / f"searchome_{style_id}.txt"
    urls_file.write_text("\n".join(case_urls), encoding="utf-8")
    print(f"  ✅ 已保存 {len(case_urls)} 個案例 URL")
    
    # 第 2 步：下載圖片
    print(f"  [2/3] 下載圖片...")
    total_images = 0
    success_count = 0
    
    for idx, case_url in enumerate(case_urls, 1):
        print(f"    案例 {idx}/{len(case_urls)}")
        
        # 收集圖片資訊
        images = _collect_images_from_case(session, case_url)
        print(f"      📸 {len(images)} 張圖片")
        
        # 下載圖片
        for img_info in images:
            if _download_image(session, img_info, output_dir):
                success_count += 1
            total_images += 1
        
        # 間隔等待
        time.sleep(REQUEST_INTERVAL)
    
    print(f"下載完成: {success_count}/{total_images} 張")


def main() -> None:
    parser = argparse.ArgumentParser(description="爬取設計家 Searchome 圖片")
    parser.add_argument(
        "styles",
        nargs="*",
        default=None,
        help="指定要爬的風格（預設：所有風格）",
    )
    args = parser.parse_args()
    
    # 決定要爬的風格
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
    print(f"爬取100設計家({len(styles_to_scrape)} 個風格)")
    print("=" * 60)
    
    for style_id, category_code in styles_to_scrape:
        scrape_style(session, style_id, category_code)
    
    print("\n" + "=" * 60)
    print("完成！")
    print(f"圖片已保存到: {RAW_DIR}")
    print(f"URL 清單已保存到: {URLS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
