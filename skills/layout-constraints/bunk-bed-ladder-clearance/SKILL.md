---
name: bunk-bed-ladder-clearance
description: 上下舖四個方向至少一側保留梯子活動空間
category: layout
order: 5
enforce: bunk_bed_ladder_clearance
parameters:
  ladder_clearance: 0.08
---

# Bunk Bed Ladder Clearance

檢查上下舖上、下、左、右四側是否至少有一側淨空 ≥ `ladder_clearance`（約 40 cm）。
若四側均被阻擋，則將底側阻擋物推至 `bed.y + bed.h + ladder_clearance`。

## When to Apply

每次迭代皆執行（常態約束）。

## Rationale

上下舖梯子需要地面空間才能安全使用；底側（腳端）是最自然的梯子位置，
`ladder_clearance = 0.08` 在 5 m 房間中約 40 cm。
