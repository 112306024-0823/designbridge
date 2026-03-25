#!/usr/bin/env python3
"""Extract Layout JSON from interior images using depth estimation + depth_to_layout.

Usage (from project root `DesignBridge`):

    python -m layout_kb.extract_layout_kb

Input images 讀取自 style_kb/images/<style_id>/（與 extract_style_kb.py 共用圖片）

Results 會寫到：
    layout_kb/outputs/<style_id>/<image_stem>_layout.json
    layout_kb/outputs/<style_id>/<image_stem>_depth.png
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from designbridge.config import Config
from style_kb.styles import STYLES

# 專案根目錄（layout_kb/ 的上層）
_ROOT = Path(__file__).resolve().parent.parent

# 圖片來源：共用 style_kb/images/
IMAGES_DIR = _ROOT / "style_kb" / "images"

# 輸出目錄：layout_kb/outputs/
OUTPUTS_DIR = _ROOT / "layout_kb" / "outputs"


def _image_to_layout(
    image_path: Path,
    depth_out_path: Path,
) -> dict:
    """
    完整流程：原始室內照片 → depth.png → layout JSON
    1. 用 vision.py 的 run_depth_estimation 產深度圖
    2. 用 depth_to_layout 萃取佈局 JSON
    """
    from designbridge.depth_to_layout import (
        build_layout_json,
        compute_spatial_metrics,
        detect_furniture_blobs,
        load_depth,
        slice_zones,
    )
    from designbridge.vision import run_depth_estimation

    depth_out_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 1：用暫存目錄產 depth.png，再複製到目標路徑
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_depth_path, _ = run_depth_estimation(
            str(image_path),
            model_name=Config.DEPTH_MODEL,
            out_dir=Path(tmp_dir),
        )
        shutil.copy(tmp_depth_path, str(depth_out_path))

    # Step 2：萃取佈局 JSON
    depth = load_depth(str(depth_out_path))
    zones = slice_zones(depth)
    blobs = detect_furniture_blobs(depth, zones)
    metrics = compute_spatial_metrics(depth, zones)
    layout = build_layout_json(str(depth_out_path), depth, zones, blobs, metrics)

    # 記錄原始圖路徑
    layout["source"]["original_image"] = str(image_path)

    return layout


def main() -> None:
    import json

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # 建立各風格子資料夾
    for style_id, _ in STYLES:
        (OUTPUTS_DIR / style_id).mkdir(parents=True, exist_ok=True)

    print(f"📂 圖片來源：{IMAGES_DIR}")
    print(f"📂 輸出目錄：{OUTPUTS_DIR}")
    print(f"   使用深度模型：{Config.DEPTH_MODEL}")

    total_ok = 0
    total_fail = 0

    for style_id, style_name in STYLES:
        style_images_dir = IMAGES_DIR / style_id
        if not style_images_dir.is_dir():
            print(f"⏭️  略過 {style_id}（{style_name}）：無資料夾")
            continue

        image_files = sorted(
            p for p in style_images_dir.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )
        if not image_files:
            print(f"⏭️  略過 {style_id}（{style_name}）：資料夾內無圖片")
            continue

        style_out_dir = OUTPUTS_DIR / style_id
        print(f"\n📁 風格 [{style_name} / {style_id}]  共 {len(image_files)} 張")

        for img_path in image_files:
            stem = img_path.stem
            json_out = style_out_dir / f"{stem}_layout.json"
            depth_out = style_out_dir / f"{stem}_depth.png"

            # 已存在就跳過
            if json_out.exists():
                print(f"  ⏭️  {img_path.name}（已有 {json_out.name}，略過）")
                total_ok += 1
                continue

            print(f"  🔍 {img_path.name}  →  深度估計中...")
            try:
                layout = _image_to_layout(img_path, depth_out)
            except Exception as exc:
                print(f"  ❌ 失敗：{exc}")
                total_fail += 1
                continue

            json_out.write_text(
                json.dumps(layout, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            total_ok += 1

            sa = layout["space_analysis"]
            rec = layout["layout_recommendation"]
            cands = layout["furniture_candidates"]
            print(f"  ✅ {json_out.name}")
            print(f"     空間類型：{sa['space_type']}  "
                  f"開放度：{sa['spatial_metrics']['openness_score']:.0%}  "
                  f"路由建議：{rec['routing_hint']}")
            if cands:
                top = cands[0]
                print(f"     最大家具候選：{top['type']} @ {top['position']} "
                      f"({top['size_ratio']:.1%})")

    print(f"\n🎯 完成，成功 {total_ok} 張，失敗 {total_fail} 張。")
    print(f"   輸出位置：{OUTPUTS_DIR}")


if __name__ == "__main__":
    main()