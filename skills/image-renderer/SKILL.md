---
name: image-renderer
description: 根據結構化需求與風格參數生成室內設計圖，支援 HF Inference API、本地 SDXL/SD/Flux，以及 ControlNet 深度引導
version: 1.0.0
metadata:
  openclaw:
    envs:
      - HF_TOKEN
      - ARTIFACTS_DIR
---

# Image Renderer

從 `structured_requirement` 和 `style_params` 組裝 text prompt，呼叫圖片生成模型輸出室內設計圖。

## When to Use

所有設計 agent（layout-planner、style-advisor）完成後呼叫。
**例外**：若 `routing_decision = "design_adjuster"` 且已有 `generated_image`，跳過此步驟（adjuster 已生成圖片）。

## Prompt 組裝邏輯

基本格式：
```
Interior design visualization: a {room_type} room, {primary_style} style,
colors {color_palette}. Photorealistic, well-lit, high quality.
```

有 `style_params` 時附加：
- style profile 名稱與強度
- `style_summary`、`visual_essence`
- 材質建議、色彩目標

## 生成後端（按優先序）

1. **HF Inference API**（`HF_TOKEN` 存在時）：雲端執行，無需本地 GPU
2. **本地模型**（`ENABLE_SDXL_FALLBACK = true`）：
   - `SDXL` + ControlNet（有 depth map 時）
   - `SDXL`（無 depth map）
   - `SD 3.5` 或 `Flux.1`（依 `LOCAL_MODEL_TYPE` 設定）
3. **Placeholder**：PIL 產生佔位圖，用於開發測試

## ControlNet 使用條件

- `ENABLE_CONTROLNET = true`
- `vision_features.depth` 存在且檔案有效
- 模型類型為 `sdxl`

## Inputs

```json
{
  "task_id": "uuid",
  "structured_requirement": { ... },
  "style_params": { ... },
  "vision_features": {
    "depth": "/artifacts/depth.png",
    "segmentation": "/artifacts/seg.png"
  },
  "routing_decision": "layout_and_style",
  "generated_image": null
}
```

## Output Format

```json
{
  "generated_image": "/artifacts/render/task_id.png",
  "render_result": {
    "generated_image_path": "...",
    "generation_params": {
      "backend": "hf_inference",
      "model": "stabilityai/stable-diffusion-xl-base-1.0",
      "provider": "hf-inference",
      "style_profile_id": "nordic_001",
      "style_strength": 0.7,
      "prompt_preview": "Interior design visualization: ...",
      "controlnet": "depth",
      "controlnet_scale": 0.5
    },
    "timestamp": "2026-04-08T12:00:00Z"
  }
}
```
