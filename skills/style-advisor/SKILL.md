---
name: style-advisor
description: 從風格知識庫載入配對的風格 profile，產生色彩配置、材質建議與 image generation prompt
version: 1.0.0
metadata:
  openclaw:
    envs:
      - STYLE_KB_DIR
---

# Style Advisor

根據 `structured_requirement.style_preferences.primary_style`，從本地風格知識庫（style_kb）載入對應的聚合風格 profile，產生：
- 色彩指引（primary / secondary / accent color）
- 材質建議
- Image generation 用的 style prompt

## When to Use

`routing_decision` 為 `"style"` 或 `"layout_and_style"` 時呼叫。

## Inputs

```json
{
  "structured_requirement": { ... },
  "user_input": {
    "style_profile_id": "optional-直接指定 profile",
    "style_reference_image": "optional-風格參考圖路徑"
  }
}
```

## Rules

- 優先使用 `user_input.style_profile_id` 直接載入指定 profile
- 無指定時，依 `primary_style` 關鍵字搜尋 `style_kb/` 目錄
- 找不到符合 profile 時回傳 `"no_aggregated_style_profile"` 並讓 renderer 用基本 prompt

## Output Format

```json
{
  "style_params": {
    "style_profile_id": "nordic_001",
    "style_profile_name": "Nordic Minimal",
    "style_strength": 0.7,
    "style_prompt": "clean lines, natural wood, white walls...",
    "style_summary": "Scandinavian minimalism with warm accents",
    "color_guidance": {
      "primary_color": "#F5F0EB",
      "secondary_color": "#8B7355",
      "accent_color": "#2C5F2E",
      "visual_essence": ["airy", "warm", "natural"]
    },
    "material_recommendations": ["oak wood", "linen fabric", "matte white"],
    "negative_prompt": "cluttered, dark, ornate, baroque"
  }
}
```
