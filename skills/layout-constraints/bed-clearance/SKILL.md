---
name: bed-clearance
description: 每張床至少一側（左或右）保留通道，確保可進出上床
category: layout
order: 4
enforce: bed_clearance
parameters:
  side_clearance: 0.06
---

# Bed Side Clearance

檢查每張床的左側與右側是否至少有一側淨空 ≥ `side_clearance`（約 30 cm）。
若兩側均被阻擋，則將右側阻擋物推出床邊緣 + `side_clearance`。

## When to Apply

每次迭代皆執行（常態約束）。

## Rationale

進出床鋪需要最低通道寬度；`side_clearance = 0.06` 在 5 m 房間中約 30 cm，
是人側身通過的最低標準。
