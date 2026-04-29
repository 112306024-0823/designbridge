---
name: visual-preprocessor
description: 對室內設計參考圖片進行深度估測（Depth Anything V2）與語意分割，輸出視覺特徵供 ControlNet 使用
version: 1.0.0
metadata:
  openclaw:
    envs:
      - ARTIFACTS_DIR
---

# Visual Preprocessor

對使用者上傳的室內圖片進行本地視覺前處理：
1. **深度估測**（Depth Anything V2）→ 產生 depth map，供 ControlNet 空間引導
2. **語意分割**（Segmentation）→ 識別家具、牆壁、地板等物件區域

## When to Use

在 requirement-analyzer 完成後，且使用者有提供參考圖片時呼叫。
沒有圖片時跳過此步驟，回傳空的 vision_features。

## Inputs

從 stdin 接收 JSON：
```json
{
  "image_path": "/path/to/room.jpg",
  "task_id": "uuid-string"
}
```

## Rules

- 模型載入需要時間，第一次執行較慢（~30s），後續呼叫使用快取
- 若 torch / transformers 未安裝或模型下載失敗，回傳空的 geometry_constraints
- depth_path 和 segmentation_path 都是本地暫存檔路徑

## Output Format

```json
{
  "vision_features": {
    "geometry_constraints": {},
    "depth": "/artifacts/task_id/depth.png",
    "segmentation": "/artifacts/task_id/seg.png",
    "segmentation_meta": "/artifacts/task_id/seg_meta.json"
  }
}
```
