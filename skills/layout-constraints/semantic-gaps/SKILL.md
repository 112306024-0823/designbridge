---
name: semantic-gaps
description: 語義不相容的家具對之間維持最小間距，避免功能衝突
category: layout
order: 2
enforce: semantic_gaps
parameters:
  pairs:
    - types: [desk, bed]
      gap: 0.06
    - types: [desk, bunk_bed]
      gap: 0.06
    - types: [dining_table, bed]
      gap: 0.08
    - types: [sofa, bed]
      gap: 0.08
    - types: [wardrobe, dining_table]
      gap: 0.04
  iterations: 30
---

# Semantic Gaps

對 `pairs` 中每組語義不相容的家具對，迭代推開至滿足 `gap` 間距。

## When to Apply

每次迭代皆執行（常態約束）。

## Rationale

- `desk/dining_table` 靠近床：私人與公共空間混用，動線互干擾
- `sofa` 靠近床：客廳與臥室語義混淆
- `wardrobe` 緊貼 `dining_table`：開門空間不足
