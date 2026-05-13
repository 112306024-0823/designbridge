---
name: bed-not-near-window
description: 床鋪不緊貼窗戶開口，預留安全距離與採光空間
category: layout
order: 6
enforce: bed_not_near_window
parameters:
  window_clearance: 0.08
  pad: 0.02
  bed_types:
    - bed
    - bunk_bed
---

# Bed Not Near Window

偵測 `bed_types` 家具是否與任一牆面的窗戶重疊，若是則沿垂直牆方向推出至滿足
`window_clearance`（約 40 cm）。四面牆（上、下、左、右）均支援。

## When to Apply

每次迭代皆執行（常態約束）。

## Rationale

床緊貼窗戶會造成冷風直吹、結露受潮、以及緊急情況時難以開窗逃生；
`window_clearance = 0.08` 在 5 m 房間中約 40 cm。
