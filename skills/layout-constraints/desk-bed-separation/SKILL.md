---
name: desk-bed-separation
description: 書桌與床之間維持足夠間距，確保椅子可完整拉出
category: layout
order: 3
enforce: desk_bed_separation
parameters:
  min_gap: 0.10
  bed_types:
    - bed
    - bunk_bed
  iterations: 40
  pad: 0.02
---

# Desk-Bed Separation

僅移動書桌（床固定靠牆），迭代推開直到書桌與所有床的間距 ≥ `min_gap`（約 50 cm）。

## When to Apply

每次迭代皆執行（常態約束）。

## Rationale

書桌前方必須有足夠空間讓使用者坐下並拉開椅子，`min_gap = 0.10` 在 5 m 房間中約 50 cm，
恰好能放一張標準書椅。
