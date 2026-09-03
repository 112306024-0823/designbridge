#!/usr/bin/env python3
"""品質過濾與去重。

從 style_kb/raw/<source>/<style_id>/ 讀取原始圖片，進行：
  1. 解析度檢查 (≥ 1024x768)
  2. 檔案大小檢查 (≥ 150KB)
  3. 圖片去重 (MD5 hash)

Usage (from project root):
    python -m style_kb.quality_filter                       # 過濾所有圖片
    python -m style_kb.quality_filter modern               # 只過濾指定風格
"""

from __future__ import annotations

import argparse
import hashlib
import sys; sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

from PIL import Image

from style_kb.styles import STYLES

_STYLE_KB_ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = _STYLE_KB_ROOT / "images"

# 最低品質要求
MIN_WIDTH = 1024
MIN_HEIGHT = 768
MIN_FILE_SIZE = 150 * 1024  # 150KB


def _compute_image_hash(image_path: Path) -> str:
    """計算圖片 MD5 hash。"""
    return hashlib.md5(image_path.read_bytes()).hexdigest()


def _filter_image(image_path: Path) -> tuple[bool, str | None]:
    # 檢查單張圖片是否符合品質標準。
    # 檢查檔案大小
    file_size = image_path.stat().st_size
    if file_size < MIN_FILE_SIZE:
        return False, f"檔案太小 ({file_size / 1024:.0f}KB < {MIN_FILE_SIZE / 1024:.0f}KB)"
    
    # 檢查解析度
    try:
        img = Image.open(image_path)
        width, height = img.size
        
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            return False, f"解析度不足 ({width}x{height} < {MIN_WIDTH}x{MIN_HEIGHT})"
        
        # 檢查是否已損壞的圖片
        img.verify()
        
    except Exception as e:
        return False, f"圖片讀取失敗: {e}"
    
    return True, None


def filter_style(style_id: str) -> None:
    """過濾單個風格的圖片（images/<style_id>/）。"""
    style_name = dict(STYLES).get(style_id, style_id)
    style_dir = IMAGES_DIR / style_id

    if not style_dir.exists():
        print(f"\n[{style_name}] 資料夾不存在，略過")
        return

    print(f"\n[{style_name} / {style_id}]")

    seen_hashes: set[str] = set()
    passed = failed = duplicates = 0

    image_files = sorted([
        f for f in style_dir.iterdir()
        if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    ])

    for image_path in image_files:
        is_valid, reason = _filter_image(image_path)

        if not is_valid:
            print(f"  skip {image_path.name} ({reason})")
            image_path.unlink()
            meta = image_path.with_name(image_path.stem + "_meta.json")
            if meta.exists():
                meta.unlink()
            failed += 1
            continue

        img_hash = _compute_image_hash(image_path)
        if img_hash in seen_hashes:
            print(f"  dup  {image_path.name}")
            image_path.unlink()
            meta = image_path.with_name(image_path.stem + "_meta.json")
            if meta.exists():
                meta.unlink()
            duplicates += 1
            continue

        seen_hashes.add(img_hash)
        passed += 1

    print(f"  pass:{passed}  fail:{failed}  dup:{duplicates}")


def main() -> None:
    parser = argparse.ArgumentParser(description="圖片品質過濾與去重")
    parser.add_argument(
        "styles",
        nargs="*",
        default=None,
        help="指定要過濾的風格（預設：所有風格）",
    )
    args = parser.parse_args()
    
    # 決定要過濾的風格
    styles_to_filter = []
    if args.styles:
        for style_id in args.styles:
            if style_id in dict(STYLES):
                styles_to_filter.append(style_id)
            else:
                print(f"未知風格: {style_id}")
    else:
        styles_to_filter = [sid for sid, _ in STYLES]
    
    if not styles_to_filter:
        print("無效的風格指定")
        return
    
    print("=" * 60)
    print(f"開始品質過濾 ({len(styles_to_filter)} 個風格)")
    print(f"標準: ≥ {MIN_WIDTH}x{MIN_HEIGHT}, ≥ {MIN_FILE_SIZE / 1024:.0f}KB")
    print("=" * 60)
    
    for style_id in styles_to_filter:
        filter_style(style_id)
    
    print("\n" + "=" * 60)
    print("品質過濾完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
