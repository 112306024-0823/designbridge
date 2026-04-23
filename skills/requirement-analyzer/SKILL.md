---
name: requirement-analyzer
description: 解析使用者的室內設計需求文字（與可選的參考圖片），輸出結構化 JSON 供後續 agent 使用
version: 1.0.0
metadata:
  openclaw:
    envs:
      - GEMINI_API_KEY
---

# Requirement Analyzer

解析使用者的室內設計需求，將自然語言描述轉換成結構化 JSON（RequirementJSON）。

## When to Use

使用者描述了想要的室內設計結果，例如：
- 「幫我把客廳改成北歐風」
- 「微調沙發區的擺設」
- 「整個臥室重新規劃，加入更多收納空間」

## Inputs

從 stdin 接收 JSON：
```json
{
  "text_prompt": "使用者的設計描述",
  "edit_scope": 0.5,
  "initial_image": "/path/to/image.jpg"
}
```

- `text_prompt`：使用者輸入的設計需求（必填）
- `edit_scope`：修改幅度，0.0（微調）到 1.0（全面重設計）（必填）
- `initial_image`：參考圖片路徑（選填，有圖時啟用 Gemini Vision）

## Rules

- 優先使用 Gemini API 解析；API 失敗時自動切換 rule-based fallback
- 有圖片時一定要傳給 Gemini Vision 做多模態分析
- 輸出必須是合法 JSON，欄位依 RequirementJSON schema
- `edit_scope < 0.3` 時，`hint_adjuster` 設為 true
- 不要在輸出中加入任何說明文字，只輸出 JSON

## Output Format

輸出到 stdout 的純 JSON：
```json
{
  "user_description_raw": "...",
  "meta": { "room_type": "living_room", "design_goal": "renovation", "user_experience_level": "general" },
  "space_info": { ... },
  "style_preferences": { "primary_style": "北歐", "color_palette": [], ... },
  "layout_constraints": { "must_keep": [], "must_add": [], "must_remove": [] },
  "edit_scope": { "scope_value": 0.5, "allowed_operations": ["layout", "style"] },
  "priority_weights": { "layout_rationality": 0.4, "style_consistency": 0.4, "novelty": 0.2 },
  "hint_layout": false,
  "hint_style": true,
  "hint_adjuster": false
}
```
