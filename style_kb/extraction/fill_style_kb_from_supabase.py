#!/usr/bin/env python3
"""從 Supabase Storage 的圖片 URL 批次補齊 style_kb 欄位。

流程：
  1. 查詢 Supabase style_images 表中 style_kb IS NULL 的行
  2. 用 httpx 將 image_url 下載到記憶體（不存磁碟）
  3. 以 inline bytes 餵給 Gemini，執行風格萃取
  4. UPDATE style_kb 欄位回 Supabase

Usage (from project root):
    python -m style_kb.extraction.fill_style_kb_from_supabase            # 處理全部
    python -m style_kb.extraction.fill_style_kb_from_supabase --limit 10 # 先試跑 10 張
    python -m style_kb.extraction.fill_style_kb_from_supabase --style-id nordic
    python -m style_kb.extraction.fill_style_kb_from_supabase --dry-run  # 只顯示，不寫入
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 讓 project root 的 .env 自動載入
_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")
load_dotenv()

from designbridge.config import Config
from style_kb.extraction.prompts_style_kb import STYLE_KB_PROMPT
from style_kb.styles import STYLES

STYLE_NAME_MAP = {sid: sname for sid, sname in STYLES}

# Gemini rate limit: 15 req/min (Flash free tier) → 4s interval
GEMINI_SLEEP = float(os.getenv("GEMINI_SLEEP_SEC", "4.0"))
DOWNLOAD_TIMEOUT = 20  # seconds


# ── Supabase client ──────────────────────────────────────────────────────────

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client
        _supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _supabase


# ── Gemini ───────────────────────────────────────────────────────────────────

_gemini_model = None

def get_gemini():
    global _gemini_model
    if _gemini_model is None:
        import google.generativeai as genai
        genai.configure(api_key=Config.get_gemini_api_key())
        _gemini_model = genai.GenerativeModel(Config.GEMINI_MODEL)
    return _gemini_model


def extract_style_kb(image_bytes: bytes, mime_type: str, style_id: str, style_name: str) -> dict:
    """呼叫 Gemini，以 inline bytes 萃取風格參數，回傳 dict。"""
    import google.generativeai as genai

    model = get_gemini()
    prompt = STYLE_KB_PROMPT.format(
        style_id=style_id,
        style_name=style_name,
        user_hint="（無額外提示）",
    )

    response = model.generate_content(
        [
            {"mime_type": mime_type, "data": image_bytes},
            prompt,
        ],
        generation_config=genai.GenerationConfig(temperature=Config.GEMINI_TEMPERATURE),
    )

    text = (getattr(response, "text", "") or "").strip()

    # 去除可能的 markdown code block
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Gemini 回傳非 dict：{type(data)}")

    # 強制鎖定 style_id / style_name，避免 Gemini 自行發揮
    data.setdefault("style_info", {})
    data["style_info"]["style_id"] = style_id
    data["style_info"]["name"] = style_name
    return data


# ── 下載圖片 ──────────────────────────────────────────────────────────────────

def download_image(url: str) -> tuple[bytes, str]:
    """下載圖片到記憶體，回傳 (bytes, mime_type)。"""
    import httpx

    resp = httpx.get(url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    # 保守 fallback
    if content_type not in ("image/jpeg", "image/png", "image/webp"):
        # 從 URL 猜
        lower_url = url.split("?")[0].lower()
        if lower_url.endswith(".png"):
            content_type = "image/png"
        elif lower_url.endswith(".webp"):
            content_type = "image/webp"
        else:
            content_type = "image/jpeg"

    return resp.content, content_type


# ── 主流程 ────────────────────────────────────────────────────────────────────

def fetch_null_rows(style_id_filter: str | None, limit: int | None) -> list[dict]:
    """查詢 style_kb IS NULL 的行。"""
    client = get_supabase()
    q = (
        client.table("style_images")
        .select("id, style_id, image_url, source_meta")
        .is_("style_kb", "null")
        .order("style_id")
    )
    if style_id_filter:
        q = q.eq("style_id", style_id_filter)
    if limit:
        q = q.limit(limit)

    res = q.execute()
    return res.data or []


def update_style_kb(row_id: str, style_kb: dict) -> None:
    client = get_supabase()
    client.table("style_images").update({"style_kb": style_kb}).eq("id", row_id).execute()


def process_rows(rows: list[dict], dry_run: bool) -> tuple[int, int]:
    """處理所有行，回傳 (成功數, 失敗數)。"""
    ok = fail = 0
    total = len(rows)

    for i, row in enumerate(rows, 1):
        row_id = row["id"]
        style_id = row["style_id"]
        style_name = STYLE_NAME_MAP.get(style_id, style_id)
        image_url = row["image_url"]
        work_name = (row.get("source_meta") or {}).get("work_name", "")

        prefix = f"[{i:>3}/{total}] {style_id} | {work_name or row_id[:8]}"

        if dry_run:
            print(f"  [DRY] {prefix} → {image_url[:60]}...")
            ok += 1
            continue

        # 下載圖片
        try:
            image_bytes, mime_type = download_image(image_url)
        except Exception as e:
            print(f"  ❌ {prefix} → 下載失敗：{e}")
            fail += 1
            continue

        # Gemini 萃取
        try:
            style_kb = extract_style_kb(image_bytes, mime_type, style_id, style_name)
        except Exception as e:
            print(f"  ❌ {prefix} → Gemini 失敗：{e}")
            fail += 1
            time.sleep(GEMINI_SLEEP)
            continue

        # 寫回 Supabase
        try:
            update_style_kb(row_id, style_kb)
        except Exception as e:
            print(f"  ❌ {prefix} → Supabase 更新失敗：{e}")
            fail += 1
            continue

        tags = (style_kb.get("style_info") or {}).get("tags", [])
        print(f"  ✅ {prefix} → tags={tags}")
        ok += 1

        # 避免打爆 Gemini rate limit
        time.sleep(GEMINI_SLEEP)

    return ok, fail


def main() -> None:
    parser = argparse.ArgumentParser(
        description="從 Supabase Storage 批次補齊 style_kb（用 Gemini 分析圖片）"
    )
    parser.add_argument("--style-id", default=None, help="只處理指定風格，例如 nordic")
    parser.add_argument("--limit", type=int, default=None, help="最多處理幾筆（預設：全部）")
    parser.add_argument("--dry-run", action="store_true", help="只顯示要處理的行，不呼叫 Gemini 也不寫入")
    parser.add_argument("--sleep", type=float, default=None, help="每次 Gemini 呼叫後等待秒數（預設 4.0）")
    args = parser.parse_args()

    if args.sleep is not None:
        global GEMINI_SLEEP
        GEMINI_SLEEP = args.sleep

    print("=" * 55)
    print("  DesignBridge — fill_style_kb_from_supabase")
    print("=" * 55)
    if args.dry_run:
        print("  模式：DRY RUN（不會寫入任何資料）")
    print(f"  風格篩選：{args.style_id or '全部'}")
    print(f"  最多處理：{args.limit or '全部'}")
    print(f"  Gemini 間隔：{GEMINI_SLEEP}s")
    print("=" * 55)

    print("\n🔍 查詢 style_kb IS NULL 的行...")
    rows = fetch_null_rows(args.style_id, args.limit)
    print(f"   找到 {len(rows)} 筆待處理\n")

    if not rows:
        print("✅ 沒有需要補齊的行，全部已有 style_kb。")
        return

    # 印出各風格數量摘要
    from collections import Counter
    counts = Counter(r["style_id"] for r in rows)
    for sid, cnt in sorted(counts.items()):
        print(f"   {sid:<15} {cnt:>4} 張")
    print()

    t0 = time.perf_counter()
    ok, fail = process_rows(rows, dry_run=args.dry_run)
    elapsed = time.perf_counter() - t0

    print()
    print("=" * 55)
    print(f"  完成：✅ {ok} 成功  ❌ {fail} 失敗  ⏱ {elapsed:.0f}s")
    print("=" * 55)


if __name__ == "__main__":
    main()
