---
name: design-director
description: 根據結構化需求與視覺特徵，決定要呼叫哪個設計 agent（layout / style / adjuster / layout_and_style）
version: 1.0.0
metadata:
  openclaw: {}
---

# Design Director

分析 RequirementJSON 中的 edit_scope 和 hint_* 旗標，決定最適合的下游 agent。

## When to Use

在 requirement-analyzer 和 visual-preprocessor 都完成後呼叫。
這是 routing 決策點，輸出決定接下來要用哪個 agent。

## Routing 邏輯

| 條件 | 指派 agent |
|---|---|
| `hint_adjuster = true` 或 `edit_scope < 0.3` | design-adjuster（局部微調） |
| `hint_layout = true` AND `hint_style = true` | layout-planner + style-advisor（合併） |
| 只有 `hint_layout = true` | layout-planner |
| 只有 `hint_style = true` | style-advisor |
| 預設 | layout-planner + style-advisor（合併） |

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
  "routing_decision": "layout_and_style"
}
```

`routing_decision` 的可能值：`"layout"`、`"style"`、`"design_adjuster"`、`"layout_and_style"`
