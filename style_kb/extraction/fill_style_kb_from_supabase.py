#!/usr/bin/env python3
"""從 Supabase Storage 的圖片 URL 批次補齊 style_kb 欄位（Vertex AI 版）。

寫入 style_kb（TARGET_COLUMN 常數；原名 style_kb_2，已改名回 style_kb）。
改用 Vertex AI 呼叫 Gemini（不是 AI Studio API key），走 GCP 專案配額，
免受 AI Studio 免費 key 15 req/min 的限制——執行前需要：
  1. .env 已有 GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION（已確認存在）
  2. 本機已跑過 `gcloud auth application-default login`，或設定
     GOOGLE_APPLICATION_CREDENTIALS 指向 service account json

流程：
  1. 查詢 Supabase style_images 表中 style_kb IS NULL 的行
  2. 用 httpx 將圖片下載到記憶體（不存磁碟；優先 source_meta.url，R2 image_url 當備援）
  3. 以 inline bytes 餵給 Gemini（Vertex AI），一次呼叫同時萃取：風格參數、space_info（room_type
     ／坪數）、quality_review（近景/風格不符判斷）、LoRA 訓練用 caption
  4. UPDATE style_kb，並視情況一併回填 space / estimated_ping_min / estimated_ping_max /
     ai_style_confidence / quality_flags / caption_en2（都只在原本是 NULL 時才回填，不覆蓋既有資料）

Usage (from project root):
    python -m style_kb.extraction.fill_style_kb_from_supabase                # 處理全部（序列）
    python -m style_kb.extraction.fill_style_kb_from_supabase --workers 8    # 平行處理，8 個 worker
    python -m style_kb.extraction.fill_style_kb_from_supabase --limit 10 # 先試跑 10 張
    python -m style_kb.extraction.fill_style_kb_from_supabase --style-id nordic
    python -m style_kb.extraction.fill_style_kb_from_supabase --dry-run  # 只顯示，不寫入
    python -m style_kb.extraction.fill_style_kb_from_supabase --force-rewrite  # 連已有 style_kb 的也重跑
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

from designbridge.core.config import Config
from style_kb.extraction.prompts_style_kb import STYLE_KB_PROMPT
from style_kb.styles import STYLES

STYLE_NAME_MAP = {sid: sname for sid, sname in STYLES}

TARGET_COLUMN = "style_kb"  # style_kb_2 已改名回 style_kb
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


# ── Gemini（Vertex AI）────────────────────────────────────────────────────────

_vertex_client = None

def get_gemini():
    """回傳 Vertex AI 模式的 genai.Client（走 GCP 專案配額，用 ADC 認證，不需要 API key）。"""
    global _vertex_client
    if _vertex_client is None:
        from google import genai
        _vertex_client = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        )
    return _vertex_client


def extract_style_kb(
    image_bytes: bytes, mime_type: str, style_id: str, style_name: str, max_retries: int = 5
) -> dict:
    """呼叫 Gemini（Vertex AI），以 inline bytes 萃取風格參數，回傳 dict。

    429 (RESOURCE_EXHAUSTED) 用指數退避 + 隨機抖動自動重試——429 是配額暫時打滿被擋下，
    沒有真的跑到模型推論，不計費，重試不會多花錢，只是多等一下。這樣就不用去猜「剛好」
    的 workers 數字，配額會浮動，重試機制比固定數字更穩。
    """
    import random
    import time as _time
    from google.genai import errors, types

    client = get_gemini()
    prompt = STYLE_KB_PROMPT.format(
        style_id=style_id,
        style_name=style_name,
        user_hint="（無額外提示）",
    )

    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(temperature=Config.GEMINI_TEMPERATURE),
            )
            break
        except errors.APIError as e:
            if e.code == 429 and attempt < max_retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"  ⏳ 429 rate limit，等待 {wait:.1f}s 後重試（第 {attempt + 1}/{max_retries} 次）")
                _time.sleep(wait)
                continue
            raise

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

def fetch_null_rows(style_id_filter: str | None, limit: int | None, force_rewrite: bool = False) -> list[dict]:
    """查詢待處理的行。預設只抓 TARGET_COLUMN（style_kb）IS NULL；force_rewrite=True 時
    連已有 style_kb 的行也重跑（例如 prompt 又再調整過，要整批重新產生）。

    PostgREST 單次查詢預設上限 1000 筆，用 .range() 分頁抓到全部（跟 generate_review.py
    的 fetch_rows() 同一套模式），不然全量執行永遠只會處理到前 1000 筆。"""
    client = get_supabase()
    PAGE = 1000
    all_rows: list[dict] = []
    offset = 0
    while True:
        q = (
            client.table("style_images")
            .select(
                "id, style_id, image_url, source_meta, space, "
                "estimated_ping_min, estimated_ping_max, quality_flags, caption_en2"
            )
            .order("style_id")
        )
        if not force_rewrite:
            q = q.is_(TARGET_COLUMN, "null")
        if style_id_filter:
            q = q.eq("style_id", style_id_filter)

        batch = (q.range(offset, offset + PAGE - 1).execute()).data or []
        all_rows.extend(batch)
        if limit and len(all_rows) >= limit:
            return all_rows[:limit]
        if len(batch) < PAGE:
            break
        offset += PAGE
    return all_rows


_VALID_SPACE_VALUES = {
    "客廳", "臥室", "廚房", "浴室", "餐廳", "書房", "走道", "玄關", "陽台", "辦公室", "其他",
}

# 跟審核頁前端的 STYLE_OPT 下拉選單一致（neoclassic 沒有實際資料、下拉選單也沒有這個選項，
# 排除掉避免建議一個使用者根本選不到的風格）
_VALID_STYLE_IDS = {
    "modern", "nordic", "japanese", "industrial", "american", "classic", "luxury", "country", "other",
}


def update_style_kb(
    row_id: str,
    style_kb: dict,
    space_value: str | None = None,
    ping_range: tuple[int, int] | None = None,
    ai_style_confidence: float | None = None,
    quality_flags_merged: dict | None = None,
    caption_value: str | None = None,
) -> None:
    """寫回 style_kb；space_value / ping_range / ai_style_confidence / caption_value 有值時
    一併回填對應欄位（呼叫端只在原本是 NULL 時才傳入，不覆蓋既有資料）。quality_flags_merged
    是「舊值 + 新的 is_closeup 鍵」合併後的完整 dict（技術性偵測欄位如 blur/laplacian 保留不動）。"""
    client = get_supabase()
    payload: dict = {TARGET_COLUMN: style_kb}
    if space_value:
        payload["space"] = space_value
    if ping_range:
        payload["estimated_ping_min"], payload["estimated_ping_max"] = ping_range
    if caption_value:
        payload["caption_en2"] = caption_value
    if ai_style_confidence is not None:
        payload["ai_style_confidence"] = ai_style_confidence
    if quality_flags_merged is not None:
        payload["quality_flags"] = quality_flags_merged
    client.table("style_images").update(payload).eq("id", row_id).execute()


def _process_one_row(i: int, total: int, row: dict, dry_run: bool) -> bool:
    """處理單一行，回傳是否成功。平行時每個 row 各自跑這個函式，互不共用可變狀態。"""
    row_id = row["id"]
    style_id = row["style_id"]
    style_name = STYLE_NAME_MAP.get(style_id, style_id)
    image_url = row["image_url"]
    work_name = (row.get("source_meta") or {}).get("work_name", "")

    prefix = f"[{i:>3}/{total}] {style_id} | {work_name or row_id[:8]}"

    if dry_run:
        print(f"  [DRY] {prefix} → {image_url[:60]}...")
        return True

    # 下載圖片：優先用 source_meta.url（原始來源，實測比 R2 鏡像可靠），R2 當備援
    # （R2 抽測 20 筆有 4 筆 404，範圍不只 american；source_meta.url 20/20 都通）
    source_url = (row.get("source_meta") or {}).get("url", "")
    try:
        if not source_url:
            raise ValueError("source_meta.url 為空")
        image_bytes, mime_type = download_image(source_url)
    except Exception as e:
        try:
            image_bytes, mime_type = download_image(image_url)
            print(f"  ⚠️  {prefix} → source_meta.url 失效，改用 R2 成功")
        except Exception as e2:
            print(f"  ❌ {prefix} → source_meta.url 與 R2 都下載失敗：{e2}")
            return False

    # Gemini 萃取（Vertex AI，走 GCP 專案配額，平行呼叫沒有 AI Studio 免費 key 那種單一 QPM 上限）
    try:
        style_kb = extract_style_kb(image_bytes, mime_type, style_id, style_name)
    except Exception as e:
        print(f"  ❌ {prefix} → Gemini 失敗：{e}")
        return False

    # 寫回 Supabase：space / 坪數區間都只在目前是 NULL 才回填，不覆蓋既有值
    space_info = style_kb.get("space_info") or {}
    room_type = space_info.get("room_type", "")
    space_value = room_type if (not row.get("space")) and room_type in _VALID_SPACE_VALUES else None

    ping_min, ping_max = space_info.get("estimated_ping_min"), space_info.get("estimated_ping_max")
    has_ping = row.get("estimated_ping_min") is None and row.get("estimated_ping_max") is None
    ping_range = (
        (int(ping_min), int(ping_max))
        if has_ping and isinstance(ping_min, (int, float)) and isinstance(ping_max, (int, float))
        else None
    )

    # ai_style_confidence 只在目前是 NULL 才回填；quality_flags 合併 is_closeup（保留既有技術性欄位）
    quality_review = style_kb.get("quality_review") or {}
    ai_confidence = quality_review.get("style_match_confidence")
    ai_confidence = float(ai_confidence) if isinstance(ai_confidence, (int, float)) and row.get("ai_style_confidence") is None else None

    quality_flags_merged = dict(row.get("quality_flags") or {})
    quality_flags_merged["is_closeup"] = bool(quality_review.get("is_closeup", False))
    if quality_review.get("style_mismatch_reason"):
        quality_flags_merged["style_mismatch_reason"] = quality_review["style_mismatch_reason"]
    suggested = quality_review.get("suggested_styles")
    if isinstance(suggested, list) and suggested:
        quality_flags_merged["suggested_styles"] = [s for s in suggested if s in _VALID_STYLE_IDS][:3]

    # caption_en2（LoRA 訓練用）只在目前是 NULL 才回填，不覆蓋既有資料
    lora_caption = style_kb.get("lora_caption") or ""
    caption_value = lora_caption if lora_caption and not row.get("caption_en2") else None

    try:
        update_style_kb(
            row_id, style_kb,
            space_value=space_value, ping_range=ping_range,
            ai_style_confidence=ai_confidence, quality_flags_merged=quality_flags_merged,
            caption_value=caption_value,
        )
    except Exception as e:
        print(f"  ❌ {prefix} → Supabase 更新失敗：{e}")
        return False

    tags = (style_kb.get("style_info") or {}).get("tags", {})
    tags_zh = tags.get("zh", tags) if isinstance(tags, dict) else tags
    space_note = f" space→{space_value}" if space_value else ""
    ping_note = f" ping→{ping_range[0]}~{ping_range[1]}" if ping_range else ""
    caption_note = " caption✓" if caption_value else ""

    # 「不適合當參考圖」綜合判斷：這次新加的 Gemini 語意判斷（is_closeup/style_match_confidence）
    # + quality_filter_supabase.py 早就算好、存在 quality_flags 裡的 person_detected/animal_detected
    # （不是重複偵測，兩者互補，這裡只是合併顯示成同一行警告）
    unsuitable_reasons = []
    if quality_review.get("is_closeup"):
        unsuitable_reasons.append("近景特寫")
    if (quality_review.get("style_match_confidence") or 1.0) < 0.5:
        unsuitable_reasons.append(f"風格不符({quality_review.get('style_mismatch_reason', '')})")
    if quality_flags_merged.get("person_detected"):
        unsuitable_reasons.append("含人物")
    if quality_flags_merged.get("animal_detected"):
        unsuitable_reasons.append("含動物")
    if unsuitable_reasons:
        print(f"  ⚠️  {prefix} → 疑似不適合當參考圖：{', '.join(unsuitable_reasons)}")
    print(f"  ✅ {prefix} → tags={tags_zh}{space_note}{ping_note}{caption_note}")
    return True


def process_rows(rows: list[dict], dry_run: bool, workers: int = 1) -> tuple[int, int]:
    """處理所有行，回傳 (成功數, 失敗數)。workers > 1 時用 ThreadPoolExecutor 平行處理
    （下載圖片 + Gemini 呼叫都是 I/O bound，用 thread 就夠，不需要 async/多行程）。
    每完成 10 筆印一次「進度／已耗時／預估剩餘」，不用等到全部跑完才知道還要多久。"""
    total = len(rows)
    if dry_run:
        results = [_process_one_row(i, total, row, dry_run) for i, row in enumerate(rows, 1)]
        return sum(results), len(results) - sum(results)

    import threading
    start = time.perf_counter()
    done = 0
    lock = threading.Lock()

    def _report_progress() -> None:
        nonlocal done
        with lock:
            done += 1
            n = done
        if n % 10 != 0 and n != total:
            return
        elapsed = time.perf_counter() - start
        eta = (elapsed / n) * (total - n)
        print(f"     …進度 {n}/{total}（{n/total:.0%}）已耗時 {elapsed/60:.1f} 分，預估剩餘 {eta/60:.1f} 分")

    results: list[bool] = []
    if workers <= 1:
        for i, row in enumerate(rows, 1):
            results.append(_process_one_row(i, total, row, dry_run))
            _report_progress()
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_process_one_row, i, total, row, dry_run) for i, row in enumerate(rows, 1)]
            for future in as_completed(futures):
                results.append(future.result())
                _report_progress()

    return sum(results), len(results) - sum(results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="從 Supabase Storage 批次補齊 style_kb（用 Gemini 分析圖片）"
    )
    parser.add_argument("--style-id", default=None, help="只處理指定風格，例如 nordic")
    parser.add_argument("--limit", type=int, default=None, help="最多處理幾筆（預設：全部）")
    parser.add_argument("--dry-run", action="store_true", help="只顯示要處理的行，不呼叫 Gemini 也不寫入")
    parser.add_argument("--workers", type=int, default=1,
                         help="平行 worker 數（預設 1 = 序列處理）。Vertex AI 走 GCP 專案配額，"
                              "沒有 AI Studio 免費 key 那種 15 req/min 上限，可以放心調高，"
                              "建議先從 5~8 試起，觀察有沒有 429 再往上調")
    parser.add_argument("--force-rewrite", action="store_true", help=f"連已有 {TARGET_COLUMN} 的行也重跑（覆蓋）")
    args = parser.parse_args()

    print("=" * 55)
    print(f"  DesignBridge — fill_style_kb_from_supabase (Vertex AI → {TARGET_COLUMN})")
    print("=" * 55)
    if args.dry_run:
        print("  模式：DRY RUN（不會寫入任何資料）")
    if args.force_rewrite:
        print(f"  模式：FORCE REWRITE（連已有 {TARGET_COLUMN} 的行也重跑）")
    print(f"  風格篩選：{args.style_id or '全部'}")
    print(f"  最多處理：{args.limit or '全部'}")
    print(f"  平行 workers：{args.workers}")
    print("=" * 55)

    print(f"\n🔍 查詢 {TARGET_COLUMN} 待處理的行...")
    rows = fetch_null_rows(args.style_id, args.limit, force_rewrite=args.force_rewrite)
    print(f"   找到 {len(rows)} 筆待處理\n")

    if not rows:
        print(f"✅ 沒有需要補齊的行，全部已有 {TARGET_COLUMN}。")
        return

    # 印出各風格數量摘要
    from collections import Counter
    counts = Counter(r["style_id"] for r in rows)
    for sid, cnt in sorted(counts.items()):
        print(f"{sid:<15} {cnt:>4} 張")
    print()

    t0 = time.perf_counter()
    ok, fail = process_rows(rows, dry_run=args.dry_run, workers=args.workers)
    elapsed = time.perf_counter() - t0

    print()
    print("=" * 55)
    print(f"  完成：✅ {ok} 成功  ❌ {fail} 失敗  ⏱ {elapsed:.0f}s")
    print("=" * 55)


if __name__ == "__main__":
    main()
