---
name: wall-anchor
description: 靠牆家具若浮在空間中央則吸附至最近牆面
category: layout
order: 1
enforce: wall_anchor
parameters:
  wall_anchored:
    - wardrobe
    - bookshelf
    - shelf
    - tv_unit
    - tv
    - dresser
    - cabinet
    - bed
  snap_threshold: 0.12
  pad: 0.02
---

# Wall Anchor

`wall_anchored` 清單中的家具若距任一牆面均超過 `snap_threshold`，則吸附至最近牆邊（留 `pad` 間距）。

## When to Apply

每次迭代皆執行（常態約束）。

## Rationale

靠牆家具（衣櫃、書架、電視櫃等）浮在房間中央在物理上不合理，且會阻礙動線。
