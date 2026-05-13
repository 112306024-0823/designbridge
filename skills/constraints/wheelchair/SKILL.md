---
name: wheelchair
description: 輪椅使用者無障礙動線，所有家具間距 ≥ 120 cm
type: family_need
trigger: wheelchair
order: 1
enforce:
  - wheelchair_clearance
prompt_addition: "barrier-free design, wide open corridors at least 120 cm, no obstacles in main pathways, accessible furniture arrangement"
parameters:
  min_gap: 0.15
  pad: 0.02
  iterations: 60
---

# Wheelchair Clearance

迭代式推開所有家具對，直到每對間距 ≥ `min_gap`（5 m 房間約 75 cm）。

## When to Apply

`special_constraints.wheelchair` 為 `true` 時觸發。

## Enforcement

重複掃描所有家具對，沿最短重疊軸方向各推半格，直至所有間距滿足 `min_gap` 或達到 `iterations` 次上限。
