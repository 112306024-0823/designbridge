---
name: style-advisor
description: 透過 style_kb（Supabase 向量檢索 + top-1 命中 style_kb JSON）產生可控的風格參數（prompt / negative / 強度 / 材質 / 參考圖）
metadata:
  openclaw:
    envs:
      - STYLE_KB_DIR
---

# Style Advisor

依照目前 DesignBridge 的 stylekb 設計，Style Advisor 會優先走「Supabase 向量檢索」：

- 以文字需求（`user_input.text_prompt`）與可選的 `style_profile_id` 作為檢索條件
- 取 **top-1** 命中圖片（不做 top-k 融合加權）
- 回查該圖片在 `style_images.style_kb` 的 JSON，產生「可控、可解釋」的風格參數：
  - `style_prompt` / `negative_prompt`
  - `style_strength`（使用 `recommended_ip_adapter_weight`，clamp 到 0~1）
  - `style_summary`
  - `material_recommendations`
  - `reference_image_url` + 下載到本地的 `reference_image_path`（供 renderer 優先作為風格參考圖）

當 Supabase 不可用時，才會依序 fallback 到：
本地 Chroma 向量庫 → aggregated JSON（`style_kb/aggregated/<style_id>_aggregated.json`）。

## When to Use

`routing_decision` 為 `"style"` 或 `"layout_and_style"` 時呼叫。

## Inputs

```json
{
  "structured_requirement": { ... },
  "user_input": {
    "text_prompt": "optional-使用者文字需求（用於向量檢索）",
    "style_profile_id": "optional-指定 style_id（例如 nordic / modern...；auto 時視同未指定）",
    "no_style_reference": false
  }
}
```

## Rules

- 若 `user_input.no_style_reference = true`：直接回傳 `None`（完全不套用風格參考）。
- 風格 ID 決策：
  - 優先 `user_input.style_profile_id`（若合法且不是 `auto`）
  - 否則看 `structured_requirement.style_preferences.primary_style`（可為英文 style_id 或中文名稱映射）
- 檢索與參數來源優先序（runtime）：
  - **Priority 1：Supabase 向量檢索 → top-1 命中圖片 → 回查 `style_kb` JSON**
    - `style_prompt`：`style_kb.ai_params.prompts.positive`
    - `negative_prompt`：`style_kb.ai_params.prompts.negative`
    - `style_strength`：`style_kb.ai_params.recommended_ip_adapter_weight`（0~1）
    - `style_summary`：`style_kb.description`
    - `material_recommendations`：`style_kb.visual_elements.materials`（壓縮成短清單）
  - **Priority 2：`_STYLE_PROMPTS` fallback**
    - 若 `style_kb` 缺欄位或不存在，回退到 `style_id` 對應模板（未知 style_id 時回退到 `modern`）
- 若 Supabase 失敗：改用本地 Chroma → aggregated JSON；全部失敗回傳 `None`（renderer 用基礎 prompt）。

## Output Format

```json
{
  "style_params": {
    "style_profile_id": "nordic",
    "style_profile_name": "Nordic",
    "style_prompt": "Nordic Scandinavian interior, white walls, light wood, cozy minimalist...",
    "negative_prompt": "cluttered, dark, tropical, ornate",
    "style_strength": 0.8,
    "style_summary": "（來自 style_kb.description；若無則空字串）",
    "material_recommendations": ["wood matte floor", "linen fabric sofa", "white wall paint"],
    "color_guidance": {},
    "controlnet_type": "depth",
    "reference_image_url": "https://.../style_ref.jpg",
    "reference_image_path": "artifacts/style_ref/<hash>.jpg",
    "top_similarity": 0.8231,
    "source": "supabase_style_kb"
  }
}
```
