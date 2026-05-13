---
name: children
description: 有幼兒家庭的安全布局，確保尖角家具緊靠牆面
type: family_need
trigger: children
order: 2
enforce:
  - child_safety
prompt_addition: "family-safe design, all furniture with rounded corners and soft padding on edges, no sharp protruding corners, non-toxic materials"
parameters:
  sharp_corner_furniture:
    - desk
    - dining_table
    - tv_unit
    - cabinet
    - dresser
    - bookshelf
    - shelf
  wall_threshold: 0.10
  pad: 0.02
---

# Children Safety

確保 `sharp_corner_furniture` 清單中的尖角家具緊靠最近牆面，避免尖角朝向開放空間傷及幼兒。

## When to Apply

`special_constraints.children` 為 `true` 時觸發。

## Enforcement

距牆超過 `wall_threshold` 的尖角家具會被推至最近牆邊（留 `pad` 間距）。
