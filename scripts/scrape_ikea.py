#!/usr/bin/env python3
"""
IKEA 台灣家具爬蟲 (www.ikea.com.tw)
用法：python scripts/scrape_ikea.py

輸出：designbridge/furniture_kb/ikea_tw.json
每筆格式：
{
  "name": "BÅRSLÖV 三人座沙發床附躺椅，Tibbleby 米色/灰色",
  "category": "sofa",
  "price": 17990,
  "currency": "TWD",
  "url": "https://www.ikea.com.tw/zh/products/...",
  "image_url": "https://www.ikea.com.tw/...",
  "style_tags": ["北歐", "現代"]
}
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

BASE_URL = "https://www.ikea.com.tw"

# 每個類別可以有多個子類別 URL（都會爬取，結果合併）
CATEGORIES: dict[str, list[str]] = {
    "sofa": [
        f"{BASE_URL}/zh/products/sofas",
    ],
    "table": [
        f"{BASE_URL}/zh/products/dining-tables",
    ],
    "chair": [
        f"{BASE_URL}/zh/products/dining-seating/upholstered-chairs",
        f"{BASE_URL}/zh/products/dining-seating/non-upholstered-chairs",
    ],
    "lamp": [
        f"{BASE_URL}/zh/products/luminaires/floor-lamps",
        f"{BASE_URL}/zh/products/luminaires/table-lamps",
        f"{BASE_URL}/zh/products/luminaires/ceiling-lights",
    ],
    "rug": [
        f"{BASE_URL}/zh/products/home-furnishing-rugs/home-rugs",
    ],
    "storage": [
        f"{BASE_URL}/zh/products/shelving-units/open-storage",
        f"{BASE_URL}/zh/products/shelving-units/secondary-storage",
    ],
    "bed": [
        f"{BASE_URL}/zh/products/beds/double-beds",
        f"{BASE_URL}/zh/products/beds/single-beds",
    ],
}

OUTPUT_PATH = Path(__file__).parent.parent / "designbridge" / "furniture_kb" / "ikea_tw.json"

STYLE_KEYWORDS: dict[str, list[str]] = {
    "北歐": ["nordic", "scandinavian", "北歐", "斯堪地那維亞"],
    "現代": ["modern", "contemporary", "現代", "簡約"],
    "工業": ["industrial", "工業"],
    "日式": ["japanese", "日式", "和風"],
    "鄉村": ["rustic", "country", "vintage", "復古", "鄉村"],
    "奢華": ["luxury", "velvet", "金色", "大理石", "marble"],
}


def _extract_style_tags(text: str) -> list[str]:
    lower = text.lower()
    return [style for style, kws in STYLE_KEYWORDS.items() if any(k in lower for k in kws)]


def _parse_price(text: str) -> Optional[int]:
    nums = re.findall(r"\d[\d,]*", text.replace("NT$", "").replace("$", ""))
    for n in nums:
        try:
            val = int(n.replace(",", ""))
            if val >= 100:
                return val
        except ValueError:
            continue
    return None


# JavaScript 注入：在 Playwright 頁面中執行，提取所有商品資料
# 支援兩種結構：
#   1. Carousel 頁 (.card.itemBlock) - 沙發、桌子等
#   2. Grid 頁 (.card.product-event-tracker in .products_list) - 燈具、地毯等
_EXTRACT_JS = """
() => {
    var results = [];
    var seen = {};

    // ── 方法 A：Carousel 卡片 (.card.itemBlock) ──
    var carouselCards = document.querySelectorAll('.card.itemBlock');
    for (var i = 0; i < carouselCards.length; i++) {
        var card = carouselCards[i];
        try {
            var nameEl = card.querySelector('.itemName');
            var seriesName = nameEl ? nameEl.innerText.trim() : '';
            var description = '';
            var bodySpans = card.querySelectorAll('.card-body span, .card-body p, .card-body div');
            for (var j = 0; j < bodySpans.length; j++) {
                var el = bodySpans[j];
                var txt = el.childElementCount === 0 ? el.innerText.trim() : '';
                if (txt && txt.length > 3 && txt.indexOf('$') === -1 && txt.indexOf('價格') === -1 && txt !== seriesName && txt.indexOf('比較') === -1) {
                    description = txt; break;
                }
            }
            var fullName = seriesName ? (description ? seriesName + ' ' + description : seriesName) : description;

            var price = null;
            var priceEls = card.querySelectorAll('.card-body p, .card-body span');
            var skipNext = false;
            for (var k = 0; k < priceEls.length; k++) {
                var ptxt = priceEls[k].innerText.trim();
                if (ptxt.indexOf('之前價格') !== -1) { skipNext = true; continue; }
                if (skipNext) { skipNext = false; continue; }
                if (ptxt.indexOf('$') !== -1 && /\\d{3,}/.test(ptxt)) {
                    var numStr = ptxt.replace(/[^0-9]/g, '');
                    if (numStr.length >= 3) { price = parseInt(numStr); break; }
                }
            }

            var linkEl = card.querySelector('a[href]');
            var url = linkEl ? linkEl.href : '';
            var imgEl = card.querySelector('img');
            var imgUrl = imgEl ? (imgEl.src || imgEl.dataset.src || imgEl.getAttribute('data-lazy-src') || '') : '';

            if (fullName && price && !seen[url || fullName]) {
                seen[url || fullName] = true;
                results.push({ name: fullName, price: price, url: url, image_url: imgUrl });
            }
        } catch(e) {}
    }

    // ── 方法 B：Grid 卡片 (.card.product-event-tracker) ──
    var gridCards = document.querySelectorAll('.card.product-event-tracker, .products_list .col-6 .card');
    for (var i = 0; i < gridCards.length; i++) {
        var card = gridCards[i];
        try {
            // 從 data-product-price 取價格
            var price = parseInt(card.getAttribute('data-product-price') || '0');
            if (!price) continue;

            // 從 data-product-tracking 取商品名稱
            var trackingStr = card.getAttribute('data-product-tracking') || '';
            var fullName = '';
            if (trackingStr) {
                try {
                    var tracking = JSON.parse(trackingStr);
                    var ga4 = tracking.ga4 && tracking.ga4.web;
                    if (ga4) {
                        var brand = ga4.item_brand || '';
                        var itemName = ga4.item_name || '';
                        fullName = brand || itemName;
                    }
                } catch(je) {}
            }

            // 若 tracking 沒有中文名，從卡片內 .itemName 或 a 元素取名稱
            if (!fullName || fullName.length < 2) {
                var nameEl2 = card.querySelector('.itemName, h2, h3, .card-title');
                if (nameEl2) fullName = nameEl2.innerText.trim();
            }

            // 從 .card-body 的第一個顯著 span 取中文名稱
            if (!fullName || /^[A-Z0-9]/.test(fullName)) {
                var bodySpans2 = card.querySelectorAll('.card-body span, .card-body .itemName');
                for (var j2 = 0; j2 < bodySpans2.length; j2++) {
                    var sp = bodySpans2[j2];
                    var sptxt = sp.childElementCount === 0 ? sp.innerText.trim() : '';
                    if (sptxt && sptxt.length > 3 && sptxt.indexOf('$') === -1 && sptxt.indexOf('比較') === -1 && /[\\u4e00-\\u9fff]/.test(sptxt)) {
                        fullName = sptxt; break;
                    }
                }
            }

            if (!fullName) fullName = card.getAttribute('data-product-id') || '';

            // 圖片：從 data_variations hidden input 取 JSON
            var imgUrl2 = '';
            var varInput = card.querySelector('input[name=data_variations]');
            if (varInput) {
                try {
                    var varData = JSON.parse(varInput.value);
                    if (varData.images && varData.images.length > 0) imgUrl2 = varData.images[0].url || '';
                } catch(je2) {}
            }
            if (!imgUrl2) {
                var imgEl2 = card.querySelector('img');
                imgUrl2 = imgEl2 ? (imgEl2.src || imgEl2.dataset.src || '') : '';
            }

            // 連結
            var linkEl2 = card.querySelector('a[href]');
            var url2 = linkEl2 ? linkEl2.href : '';

            var key2 = url2 || fullName;
            if (fullName && price && !seen[key2]) {
                seen[key2] = true;
                results.push({ name: fullName, price: price, url: url2, image_url: imgUrl2 });
            }
        } catch(e) {}
    }

    return results;
}
"""


def scrape_category_playwright(category: str, url: str) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright 未安裝：pip install playwright && playwright install chromium")
        return []

    items: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = browser.new_context(
            locale="zh-TW",
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8"},
        )
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            print(f"  → 開啟：{url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 等商品卡片出現（先等 productList，再等個別卡片）
            try:
                page.wait_for_selector(".productList", timeout=15000)
            except Exception:
                pass
            try:
                page.wait_for_selector(".card.itemBlock, .card.product-event-tracker", timeout=8000)
            except Exception:
                pass

            time.sleep(3)

            # 捲動以載入更多商品
            for _ in range(4):
                page.keyboard.press("End")
                time.sleep(0.8)

            time.sleep(1)

            # 執行 JS 提取
            raw_items: list[dict] = page.evaluate(_EXTRACT_JS)
            print(f"  → 抓到 {len(raw_items)} 件商品")

            for item in raw_items:
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                price = item.get("price") or 0
                product_url = item.get("url") or ""
                image_url = item.get("image_url") or ""

                # 補全相對 URL
                if product_url.startswith("/"):
                    product_url = BASE_URL + product_url

                style_tags = _extract_style_tags(name)

                items.append({
                    "name": name,
                    "category": category,
                    "price": price,
                    "currency": "TWD",
                    "url": product_url,
                    "image_url": image_url,
                    "style_tags": style_tags,
                })

        except Exception as e:
            print(f"  [!] 爬取失敗：{e}")
        finally:
            browser.close()

    return items


def _make_product_id(item: dict) -> str:
    """從 URL 或 name+category 產生穩定的商品 ID。"""
    import hashlib
    key = item.get("url") or f"{item.get('name')}_{item.get('category')}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:16]


def _upsert_to_supabase(items: list[dict]) -> None:
    """將商品 upsert 到 Supabase ikea_products 表。需設定環境變數 SUPABASE_URL / SUPABASE_KEY。"""
    import os
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("  [supabase] 未設定 SUPABASE_URL / SUPABASE_KEY，跳過 Supabase upsert")
        return

    try:
        from supabase import create_client
        client = create_client(url, key)

        rows = [
            {
                "id": _make_product_id(i),
                "name": i["name"],
                "category": i["category"],
                "price": i["price"],
                "currency": i.get("currency", "TWD"),
                "url": i.get("url") or "",
                "image_url": i.get("image_url") or "",
                "style_tags": i.get("style_tags") or [],
            }
            for i in items
        ]

        # 分批 upsert（Supabase 單次最多 ~500 筆）
        batch_size = 100
        total_upserted = 0
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            client.table("ikea_products").upsert(batch).execute()
            total_upserted += len(batch)
            print(f"  [supabase] upserted {total_upserted}/{len(rows)} rows...")
            time.sleep(0.3)

        print(f"  [supabase] 完成：共 {total_upserted} 件商品 upserted")
    except Exception as e:
        print(f"  [supabase] upsert 失敗：{e}")


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_items: list[dict] = []
    for category, urls in CATEGORIES.items():
        cat_items: list[dict] = []
        for url in urls:
            print(f"\n[{category}] {url}")
            items = scrape_category_playwright(category, url)
            cat_items.extend(items)
            time.sleep(1.5)
        if cat_items:
            print(f"  [{category}] total: {len(cat_items)} items")
        all_items.extend(cat_items)

    # 去除重複（以 url 為 key，其次以 name+category）
    seen: set[str] = set()
    unique: list[dict] = []
    for item in all_items:
        key = item.get("url") or f"{item.get('name')}_{item.get('category')}"
        if key and key not in seen:
            seen.add(key)
            unique.append(item)

    # 過濾掉沒有價格或名稱的項目
    unique = [i for i in unique if i.get("name") and i.get("price", 0) > 0]

    # 1. 存到本地 JSON（fallback / 離線使用）
    OUTPUT_PATH.write_text(
        json.dumps(unique, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n完成！共 {len(unique)} 件商品，已存到：{OUTPUT_PATH}")

    from collections import Counter
    counts = Counter(i["category"] for i in unique)
    for cat, cnt in sorted(counts.items()):
        print(f"  {cat}: {cnt} 件")

    # 2. Upsert 到 Supabase（若有設定環境變數）
    print("\n[supabase] 開始 upsert...")
    _upsert_to_supabase(unique)


if __name__ == "__main__":
    main()
