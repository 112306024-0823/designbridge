---
name: design-adjuster
description: 對現有室內設計圖進行局部 inpainting，移除/替換指定家具，適合 edit_scope < 0.3 的微調需求
version: 1.0.0
metadata:
  openclaw:
    envs:
      - HF_TOKEN
      - ARTIFACTS_DIR
---

# Design Adjuster

對使用者上傳的原始室內圖片進行局部修改（inpainting）。
適用於：只想換一張沙發、移除某件家具、微調局部陳設，不需要全面重設計的情境。

## When to Use

`routing_decision` 為 `"design_adjuster"` 時呼叫，即：
- `edit_scope < 0.3`（幾乎不動大局）
- `hint_adjuster = true`（使用者明確說「局部」「微調」「單一物件」）

## Inpainting 流程

1. **Mask 生成**：從 segmentation 結果找出目標物件區域
   - 有 segmentation → 精確 mask（依 `must_remove` 標籤）
   - 無 segmentation → 退回中央區域 fallback mask
2. **Prompt 組裝**：結合 `must_add`、風格偏好、style_params 建構 inpainting prompt
3. **執行 inpainting**（按優先序）：
   - HF Inference API（有 `HF_TOKEN` 時，雲端執行）
   - 本地 SD Inpainting pipeline
   - Fallback：複製原圖（不修改）

## Inputs

```json
{
  "task_id": "uuid",
  "user_input": {
    "initial_image": "/path/to/original.jpg",
    "edit_scope": 0.2
  },
  "structured_requirement": { ... },
  "vision_features": {
    "segmentation": "/artifacts/seg.png",
    "segmentation_meta": "/artifacts/seg_meta.json"
  },
  "style_params": { ... }
}
```

## Rules

- `strength`（inpainting 強度）由 `edit_scope` 決定：`strength = clamp(edit_scope + 0.4, 0.4, 0.85)`
- 沒有原始圖片時直接跳過，回傳 `"no_initial_image_skipped"`
- 輸出圖片存於 `ARTIFACTS_DIR/render/{task_id}.png`
- design-adjuster 輸出後，image-renderer 不應再覆蓋產生的圖片

## Output Format

```json
{
  "generated_image": "/artifacts/render/task_id.png",
  "render_result": {
    "generated_image_path": "...",
    "generation_params": {
      "backend": "hf_inpainting",
      "model": "stable-diffusion-2-inpainting",
      "strength": 0.6,
      "mask_source": "segmentation",
      "prompt_preview": "..."
    },
    "timestamp": "2026-04-08T12:00:00Z"
  }
}
```
