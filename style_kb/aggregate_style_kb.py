#!/usr/bin/env python3
"""Aggregate multiple Style KB JSONs into a unified style profile using Gemini.

Usage (from project root `DesignBridge`):

    python -m style_kb.aggregate_style_kb              # 聚合所有風格
    python -m style_kb.aggregate_style_kb country      # 只聚合 country 風格
    python -m style_kb.aggregate_style_kb luxury       # 只聚合 luxury 風格

Results will be written to:
    style_kb/aggregated/<style_id>_aggregated.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from designbridge.config import Config
from style_kb.styles import STYLES


def extract_color_hex(color_str: str) -> str | None:
    """Extract hex color from string."""
    if isinstance(color_str, str) and color_str.startswith("#"):
        return color_str
    return None


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert RGB to hex color."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def average_colors(colors: list[str]) -> str:
    """Calculate average of multiple hex colors."""
    rgbs = [hex_to_rgb(c) for c in colors if c and c.startswith("#")]
    if not rgbs:
        return "#808080"
    avg_r = int(mean(r[0] for r in rgbs))
    avg_g = int(mean(r[1] for r in rgbs))
    avg_b = int(mean(r[2] for r in rgbs))
    return rgb_to_hex((avg_r, avg_g, avg_b))


def aggregate_statistics(json_files: list[Path]) -> dict[str, Any]:
    """Extract statistics from multiple JSON files."""
    all_data = []
    colors_primary = []
    colors_secondary = []
    colors_accent = []
    materials_list = []
    tags_all = []
    color_temps = []
    ip_weights = []
    prompts_positive = []
    prompts_negative = []

    for json_path in json_files:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            all_data.append(data)

            # 顏色
            if "visual_elements" in data and "colors" in data["visual_elements"]:
                colors = data["visual_elements"]["colors"]
                if "primary" in colors:
                    colors_primary.append(colors["primary"])
                if "secondary" in colors:
                    colors_secondary.append(colors["secondary"])
                if "accent" in colors:
                    colors_accent.append(colors["accent"])

            # 材料
            if "visual_elements" in data and "materials" in data["visual_elements"]:
                materials_list.extend(data["visual_elements"]["materials"])

            # 標籤
            if "style_info" in data and "tags" in data["style_info"]:
                tags_all.extend(data["style_info"]["tags"])

            # 光線色溫
            if "visual_elements" in data and "lighting" in data["visual_elements"]:
                lighting = data["visual_elements"]["lighting"]
                if "color_temp" in lighting:
                    color_temps.append(lighting["color_temp"])

            # AI 參數
            if "ai_params" in data:
                ai_params = data["ai_params"]
                if "prompts" in ai_params:
                    if "positive" in ai_params["prompts"]:
                        prompts_positive.append(ai_params["prompts"]["positive"])
                    if "negative" in ai_params["prompts"]:
                        prompts_negative.append(ai_params["prompts"]["negative"])
                if "adapter_config" in ai_params:
                    if "ip_adapter_weight" in ai_params["adapter_config"]:
                        ip_weights.append(ai_params["adapter_config"]["ip_adapter_weight"])
        except Exception as e:
            print(f" 讀取 {json_path.name} 失敗: {e}")

    # 統計結果
    stats = {
        "file_count": len(json_files),
        "successfully_read": len(all_data),
        "colors": {
            "primary": average_colors(colors_primary),
            "primary_candidates": colors_primary[:5],
            "secondary": average_colors(colors_secondary),
            "accent": average_colors(colors_accent),
        },
        "materials_top": [
            {
                "target": m.get("target"),
                "type": m.get("type"),
                "frequency": sum(
                    1
                    for mm in materials_list
                    if mm.get("type") and mm.get("type") == m.get("type")
                ),
            }
            for m in materials_list
        ][:10],
        "tags_frequency": dict(Counter(tags_all).most_common(10)),
        "avg_color_temp": int(mean(color_temps)) if color_temps else 3800,
        "avg_ip_adapter_weight": round(mean(ip_weights), 2) if ip_weights else 0.85,
        "prompts_sample": {
            "positive": prompts_positive[0] if prompts_positive else "",
            "negative": prompts_negative[0] if prompts_negative else "",
        },
    }

    return stats


def call_gemini_aggregate(stats: dict[str, Any], style_id: str, style_name: str) -> dict[str, Any]:
    """Use Gemini to create intelligent aggregation from statistics."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError(
            "google-genai 未安裝。請先執行: pip install google-genai"
        ) from exc

    api_key = Config.get_gemini_api_key()
    client = genai.Client(api_key=api_key)

    prompt = f"""分析以下室內設計風格的統計數據，這些數據來自 {stats['successfully_read']} 個 {style_name}（{style_id}）風格的室內設計案例。

## 統計數據：
- 主要顏色：{stats['colors']['primary']}
- 次要顏色：{stats['colors']['secondary']}
- 強調色：{stats['colors']['accent']}
- 平均色溫：{stats['avg_color_temp']}K
- 常見材料：{[m['type'] for m in stats['materials_top'][:3] if m['type']]}
- 風格標籤：{list(stats['tags_frequency'].keys())}
- 平均 IP Adapter 權重：{stats['avg_ip_adapter_weight']}

## 任務：
請生成一個統一的 {style_name}（{style_id}）風格檔案，返回 JSON 格式，包含：

1. **unified_positive_prompt**：一個表達力強的正向提示詞（用於圖片生成），融合所有案例的特點，長度 150-200 字
2. **unified_negative_prompt**：統一的反向提示詞（應避免什麼）
3. **visual_essence**：風格的核心視覺特徵（3-5個最重要的描述）
4. **recommended_ip_adapter_weight**：建議的 IP Adapter 權重（0-1）
5. **style_summary**：該風格的一句核心描述（20-30 字）
6. **material_recommendations**：推薦使用的 3-5 個材料類型
7. **controlnet_type**：建議的 ControlNet 類型（depth、canny、normal、segmentation）

請確保輸出是有效的 JSON，可以直接被 Python json.loads() 解析。"""

    response = client.models.generate_content(
        model=Config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=Config.GEMINI_TEMPERATURE,
        ),
    )

    text = (getattr(response, "text", "") or "").strip()

    # 處理 ```json ... ``` 包裹
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Gemini 回傳的不是 JSON 物件。")

    return data


def main() -> None:
    # 解析命令行參數
    parser = argparse.ArgumentParser(description="聚合風格知識庫")
    parser.add_argument(
        "style_filter",
        nargs="?",
        default=None,
        help="只聚合指定的風格。若不指定則聚合所有風格。",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    outputs_dir = base_dir / "outputs"
    aggregated_dir = base_dir / "aggregated"
    aggregated_dir.mkdir(parents=True, exist_ok=True)

    # 決定要處理的風格
    if args.style_filter:
        valid_styles = [s[0] for s in STYLES]
        if args.style_filter not in valid_styles:
            print(f"❌ 錯誤：風格 '{args.style_filter}' 不存在。")
            print(f"有效的風格包括：{', '.join(valid_styles)}")
            return
        styles_to_process = [(s[0], s[1]) for s in STYLES if s[0] == args.style_filter]
    else:
        styles_to_process = STYLES

    total = 0
    for style_id, style_name in styles_to_process:
        style_output_dir = outputs_dir / style_id
        if not style_output_dir.is_dir():
            print(f"⏭️ 略過 {style_id}（{style_name}）：無輸出資料夾")
            continue

        json_files = sorted(style_output_dir.glob("*.json"))
        if not json_files:
            print(f"⏭️ 略過 {style_id}（{style_name}）：資料夾內無 JSON 檔")
            continue

        print(f"\n📊 正在聚合 [{style_name} / {style_id}]，共 {len(json_files)} 個檔案...")

        # 步驟 1：統計聚合
        print(f"  📈 步驟 1/2：統計聚合...")
        stats = aggregate_statistics(json_files)
        print(f"  ✅ 成功讀取 {stats['successfully_read']} 個檔案")

        # 步驟 2：Gemini 智能聚合
        print(f"  🤖 步驟 2/2：調用 Gemini 進行智能聚合...")
        try:
            gemini_result = call_gemini_aggregate(stats, style_id, style_name)
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ Gemini 聚合失敗: {exc}")
            continue

        # 組合最終結果
        final_result = {
            "style_id": style_id,
            "style_name": style_name,
            "aggregated_from": stats["file_count"],
            "successfully_used": stats["successfully_read"],
            "statistics": {
                "primary_color": stats["colors"]["primary"],
                "secondary_color": stats["colors"]["secondary"],
                "accent_color": stats["colors"]["accent"],
                "avg_color_temp_k": stats["avg_color_temp"],
                "top_materials": [m["type"] for m in stats["materials_top"][:5] if m["type"]],
                "top_tags": list(stats["tags_frequency"].keys()),
            },
            "ai_config": {
                "unified_positive_prompt": gemini_result.get("unified_positive_prompt", ""),
                "unified_negative_prompt": gemini_result.get("unified_negative_prompt", ""),
                "recommended_ip_adapter_weight": gemini_result.get(
                    "recommended_ip_adapter_weight", stats["avg_ip_adapter_weight"]
                ),
                "controlnet_type": gemini_result.get("controlnet_type", "depth"),
            },
            "style_profile": {
                "visual_essence": gemini_result.get("visual_essence", []),
                "summary": gemini_result.get("style_summary", ""),
                "material_recommendations": gemini_result.get("material_recommendations", []),
            },
        }

        # 保存結果
        output_path = aggregated_dir / f"{style_id}_aggregated.json"
        output_path.write_text(
            json.dumps(final_result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        total += 1
        print(f"  ✅ {output_path.name}")

    print(f"\n🎯 完成，共聚合 {total} 個風格。")


if __name__ == "__main__":
    main()
