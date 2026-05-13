---
name: pets
description: 寵物友善設計：窗台淨空讓貓咪通行、角落保留休息區、可攀爬家具靠牆
type: family_need
trigger: pets
order: 3
enforce:
  - pet_window_clearance
  - pet_corner_zone
  - pet_climbable_wall_anchor
prompt_addition: "scratch-resistant upholstery such as microfiber or full-grain leather, durable easy-to-clean surfaces, no delicate or fragile fabrics, stain-resistant flooring"
parameters:
  window_clearance: 0.10
  corner_size: 0.12
  pad: 0.02
  window_blockers:
    - wardrobe
    - bookshelf
    - shelf
    - cabinet
    - dresser
    - sofa
    - loveseat
    - armchair
  climbable_furniture:
    - bookshelf
    - shelf
    - wardrobe
    - cabinet
---

# Pet-Friendly Constraints

三步驟執行順序：

1. **窗台淨空** (`pet_window_clearance`)：`window_blockers` 清單中的家具不得佔用窗前 `window_clearance` 走道。
2. **角落保留** (`pet_corner_zone`)：距所有門最遠的角落保留 `corner_size` 方形區域作為寵物床 / 飼料站。
3. **可攀爬家具靠牆** (`pet_climbable_wall_anchor`)：`climbable_furniture` 清單中的家具必須貼緊最近牆面，消除後方縫隙。

## When to Apply

`special_constraints.pets` 為 `true` 時觸發。
