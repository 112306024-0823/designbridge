#!/usr/bin/env python3
"""對 Supabase 中的圖片進行三層品質評估，結果寫回 DB。

Layer 1 — 規則法：解析度、檔案大小、長寬比
Layer 2 — OpenCV：模糊偵測（Laplacian variance）
Layer 3 — YOLO：人物 / 動物偵測

寫回欄位：width, height, file_size_kb, quality_score, quality_flags
quality_flags JSON 包含：
  orientation, very_low_res, low_res, too_small_kb, bad_ratio,
  severe_blur, blur, laplacian, person_detected, animal_detected

扣分規則（從 1.0 開始）：
  very_low_res      -0.5   最短邊 < 512px
  person_detected   -0.5   YOLO 偵測到人
  animal_detected   -0.4   YOLO 偵測到動物
  severe_blur       -0.4   Laplacian < 30
  blur              -0.2   Laplacian 30–100
  low_res           -0.2   最短邊 512–768px
  bad_ratio         -0.15  長寬比 > 2.5
  too_small_kb      -0.1   < 100 KB

Usage (from project root):
    python -m style_kb.collection.quality_filter_supabase --sample 20  # 取樣測試
    python -m style_kb.collection.quality_filter_supabase --run         # 執行全部
    python -m style_kb.collection.quality_filter_supabase --run --style modern
    python -m style_kb.collection.quality_filter_supabase --run --reset # 重新跑已處理的
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")
load_dotenv()

# ── 閾值 ──────────────────────────────────────────────────────────────────────
MIN_SHORT_HARD  = 512     # 最短邊硬性下限
MIN_SHORT_SOFT  = 768     # 最短邊軟性下限
MIN_FILE_KB     = 100.0   # 檔案大小下限 (KB)
MAX_RATIO       = 2.5     # 長寬比上限
BLUR_SEVERE     = 30.0    # Laplacian 極度模糊
BLUR_SOFT       = 100.0   # Laplacian 輕度模糊
YOLO_CONF       = 0.4     # YOLO 信心度門檻
DOWNLOAD_TIMEOUT = 20

# YOLO COCO class IDs
PERSON_CLS  = {0}
ANIMAL_CLS  = {14, 15, 16, 17, 18, 19, 20, 21, 22, 23}  # bird ~ giraffe

# 扣分權重
DEDUCTIONS = {
    "very_low_res":     0.5,
    "person_detected":  0.5,
    "animal_detected":  0.4,
    "severe_blur":      0.4,
    "blur":             0.2,
    "low_res":          0.2,
    "bad_ratio":        0.15,
    "too_small_kb":     0.1,
}


# ── Supabase ──────────────────────────────────────────────────────────────────

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


# ── YOLO ──────────────────────────────────────────────────────────────────────

_yolo = None

def get_yolo():
    global _yolo
    if _yolo is None:
        try:
            from ultralytics import YOLO
            _yolo = YOLO("yolov8n.pt")
            _yolo.overrides["verbose"] = False
            print("✅ YOLO 模型載入完成（yolov8n）")
        except ImportError:
            print("⚠️  ultralytics 未安裝，略過人物/動物偵測")
            print("   pip install ultralytics")
    return _yolo


# ── 品質計算 ──────────────────────────────────────────────────────────────────

def check_rules(img, file_bytes: bytes) -> dict:
    w, h = img.size
    short = min(w, h)
    ratio = max(w, h) / short if short > 0 else 99
    size_kb = len(file_bytes) / 1024
    orientation = "landscape" if w > h else "portrait" if h > w else "square"
    return {
        "orientation":  orientation,
        "very_low_res": short < MIN_SHORT_HARD,
        "low_res":      MIN_SHORT_HARD <= short < MIN_SHORT_SOFT,
        "too_small_kb": size_kb < MIN_FILE_KB,
        "bad_ratio":    ratio > MAX_RATIO,
    }


def check_blur(img) -> dict:
    import cv2
    import numpy as np
    gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return {
        "laplacian":   round(lap, 1),
        "severe_blur": lap < BLUR_SEVERE,
        "blur":        BLUR_SEVERE <= lap < BLUR_SOFT,
    }


def check_yolo(img) -> dict:
    import numpy as np
    model = get_yolo()
    if model is None:
        return {"person_detected": False, "animal_detected": False}
    results = model(np.array(img.convert("RGB")), conf=YOLO_CONF, verbose=False)[0]
    detected = {int(c) for c in results.boxes.cls.tolist()} if results.boxes else set()
    return {
        "person_detected": bool(detected & PERSON_CLS),
        "animal_detected": bool(detected & ANIMAL_CLS),
    }


def compute_score(flags: dict) -> float:
    score = 1.0
    for key, penalty in DEDUCTIONS.items():
        if flags.get(key):
            score -= penalty
    return round(max(0.0, score), 3)


def analyze(image_bytes: bytes) -> dict | None:
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as e:
        return {"quality_score": 0.0, "quality_flags": {"corrupt": True, "error": str(e)},
                "width": None, "height": None, "file_size_kb": round(len(image_bytes)/1024, 1)}

    flags = {
        **check_rules(img, image_bytes),
        **check_blur(img),
        **check_yolo(img),
    }
    return {
        "width":         img.width,
        "height":        img.height,
        "file_size_kb":  round(len(image_bytes) / 1024, 1),
        "quality_score": compute_score(flags),
        "quality_flags": flags,
    }


# ── DB 操作 ───────────────────────────────────────────────────────────────────

def fetch_rows(style: str | None, reset: bool, limit: int | None) -> list[dict]:
    client = get_supabase()
    if limit:
        q = client.table("style_images").select("id, image_url, style_id")
        if not reset:
            q = q.is_("quality_score", "null")
        if style:
            q = q.eq("style_id", style)
        return (q.limit(limit).execute()).data or []

    # 無 limit 時分頁抓取全部（Supabase 預設上限 1000）
    PAGE = 1000
    all_rows: list[dict] = []
    offset = 0
    while True:
        q = client.table("style_images").select("id, image_url, style_id")
        if not reset:
            q = q.is_("quality_score", "null")
        if style:
            q = q.eq("style_id", style)
        batch = (q.range(offset, offset + PAGE - 1).execute()).data or []
        all_rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return all_rows


def update_row(row_id: str, metrics: dict) -> None:
    get_supabase().table("style_images").update({
        "width":         metrics["width"],
        "height":        metrics["height"],
        "file_size_kb":  metrics["file_size_kb"],
        "quality_score": metrics["quality_score"],
        "quality_flags": metrics["quality_flags"],
    }).eq("id", row_id).execute()


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Supabase 三層圖片品質篩選")
    parser.add_argument("--run",    action="store_true", help="實際執行並寫入 DB（預設 dry run）")
    parser.add_argument("--style",  type=str, default=None, help="只處理指定風格")
    parser.add_argument("--sample", type=int, default=None, help="只取樣 N 張（測試用）")
    parser.add_argument("--reset",  action="store_true", help="重新處理已有 quality_score 的圖")
    args = parser.parse_args()

    dry_run = not args.run

    print("=" * 60)
    print("  quality_filter_supabase  （三層品質篩選）")
    print("=" * 60)
    print(f"  模式：{'DRY RUN' if dry_run else '實際執行'}")
    if args.style:  print(f"  風格篩選：{args.style}")
    if args.sample: print(f"  取樣數量：{args.sample}")
    print("=" * 60 + "\n")

    if not dry_run:
        get_yolo()  # 預先載入，避免第一筆慢

    rows = fetch_rows(args.style, args.reset, args.sample)
    print(f"共 {len(rows)} 筆待處理\n")

    if not rows:
        print("沒有需要處理的圖片。")
        return

    passed = failed = skipped = 0
    t0 = time.perf_counter()

    for i, row in enumerate(rows, 1):
        row_id    = row["id"]
        image_url = row["image_url"]
        style_id  = row["style_id"]
        prefix    = f"[{i:04d}/{len(rows)}] {style_id:12s}"

        if not image_url:
            print(f"  ⚠  {prefix} image_url 為空，略過")
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY] {prefix} {image_url.split('/')[-1]}")
            passed += 1
            continue

        # 下載
        try:
            import httpx
            resp = httpx.get(image_url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)
            resp.raise_for_status()
            img_bytes = resp.content
        except Exception as e:
            print(f"  ❌ {prefix} 下載失敗：{e}")
            failed += 1
            continue

        # 分析
        metrics = analyze(img_bytes)

        # 列印摘要
        score  = metrics["quality_score"]
        flags  = metrics["quality_flags"]
        issues = [k for k, v in flags.items() if v is True and k != "orientation"]
        orient = flags.get("orientation", "?")
        lap    = flags.get("laplacian", "?")
        icon   = "✅" if score >= 0.6 else ("⚠️ " if score >= 0.3 else "❌")
        print(f"  {icon} {prefix} score={score:.2f}  "
              f"{metrics.get('width','?')}x{metrics.get('height','?')}  "
              f"{orient}  blur={lap}"
              + (f"  [{', '.join(issues)}]" if issues else ""))

        if score >= 0.6:
            passed += 1
        else:
            failed += 1

        # 寫回 DB
        try:
            update_row(row_id, metrics)
        except Exception as e:
            print(f"      ⚠️  DB 寫入失敗：{e}")

        time.sleep(0.05)

    elapsed = time.perf_counter() - t0
    print()
    print("=" * 60)
    print(f"  {'[DRY RUN] ' if dry_run else ''}完成  ⏱ {elapsed:.0f}s")
    print(f"  ✅ 通過（≥0.6）：{passed}")
    print(f"  ❌ 不通過（<0.6）：{failed}")
    print(f"  ⏭  跳過：{skipped}")
    if not dry_run and (passed + failed) > 0:
        print(f"  通過率：{passed/(passed+failed)*100:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
