---
name: sofa-not-back-to-door
description: 風水：沙發背面不朝門，背靠實牆面向入口
type: fengshui
trigger: sofa_not_back_to_door
order: 5
enforce:
  - sofa_not_back_to_door
prompt_addition: "feng shui compliant living room, sofa back against solid wall and facing the room entrance"
parameters:
  push_amount: 0.15
  door_threshold_high: 0.7
  door_threshold_low: 0.3
  sofa_threshold_high: 0.65
  sofa_threshold_low: 0.35
  pad: 0.02
---

# Sofa Not Back to Door

確保沙發背面（平面圖頂邊）不與門口同側，否則推移 `push_amount`。

## When to Apply

`special_constraints.sofa_not_back_to_door` 為 `true` 時觸發。

## Enforcement

- 門在底牆（`y > door_threshold_high`）且沙發背面也近底部（`y+h > sofa_threshold_high`）→ 沙發上移 `push_amount`
- 門在頂牆（`y < door_threshold_low`）且沙發背面也近頂部（`y < sofa_threshold_low`）→ 沙發下移 `push_amount`
