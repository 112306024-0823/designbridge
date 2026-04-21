---
name: layout-planner
description: 根據空間尺寸、動線需求與使用者限制，規劃室內家具布局方案
version: 1.0.0
metadata:
  openclaw: {}
---

# Layout Planner

依據 RequirementJSON 的 `layout_constraints` 和 `space_info`，產生家具擺放建議方案。

## When to Use

`routing_decision` 為 `"layout"` 或 `"layout_and_style"` 時呼叫。

## 目前狀態

> ⚠️ **Stub 實作**：Layout 規劃邏輯尚未完整實作（對應原 LangGraph 的 `layout_agent_stub`）。
> 目前僅回傳佔位輸出，後續可整合 ControlNet layout optimization。

## 完整實作時應包含

- 解讀 `must_keep` / `must_add` / `must_remove` 限制
- 根據 `space_info`（尺寸、門窗位置）規劃動線
- 輸出每件家具的位置座標與朝向
- 可選：使用深度圖（`vision_features.depth`）做空間感知

## Inputs

```json
{
  "structured_requirement": { ... },
  "vision_features": { ... }
}
```

## Output Format

```json
{
  "intermediate_outputs": {
    "layout_agent": "stub_output"
  }
}
```
