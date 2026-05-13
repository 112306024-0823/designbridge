---
name: bed-not-facing-door
description: 風水：床腳不正對門口，避免衝煞
type: fengshui
trigger: bed_not_facing_door
order: 4
enforce:
  - bed_not_facing_door
prompt_addition: "feng shui compliant bedroom, bed positioned so feet do not point directly at the door"
parameters:
  offset: 0.12
  pad: 0.02
---

# Bed Not Facing Door

若床腳端（`y + h`）與門口中心線對齊，將床橫移 `offset` 以避開衝煞方向。

## When to Apply

`special_constraints.bed_not_facing_door` 為 `true` 時觸發。

## Enforcement

偵測床腳中心是否落在門口寬度範圍內，若是則依床心位置決定左移或右移 `offset`。
