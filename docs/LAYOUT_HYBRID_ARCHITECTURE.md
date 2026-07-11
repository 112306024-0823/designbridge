# Layout 混合架構（Scene Graph → 投影深度圖 → FLUX ControlNet）

> 本文件說明 DesignBridge Layout Agent 目前採用的混合架構、完整資料流，以及相較於
> session 起始版本（commit `d97b3f90`）的逐檔改動。

---

## 1. 要解決的根本問題

精準布局控制需要 Scene Graph 輸出**座標**；但 Renderer（FLUX.1）只能吃自然語言或影像條件，
**無法直接解析座標數值**。結果是 Layout Agent 算出來的精確座標對最終生成沒有控制力——
座標和成圖之間缺一座橋。

更具體的斷點（在程式碼層面）：

- Renderer 其實**早就能吃深度圖**（`_render_hf_kontext` / `_render_flux_kontext_fal` 接受 depth PNG）。
- 但那張深度來自 Depth-Anything 對**輸入照片**的估計（`vision.get("depth")`）。
- Layout Agent 的座標只被畫成**俯視平面圖**（`_generate_floor_plan`），從未進到 Renderer。
- 一旦家具被重新擺放，輸入照片的深度就跟新佈局對不上 → 座標失去控制力。

## 2. 採用的混合架構（老師建議）

> **不做完整 3D。** 不用 Blender / TripoSR（風險高、家具生成品質不穩）。
> 每件家具用一個**長方體**代表，由 Scene Graph 座標直接在 3D 房間中擺位，
> 投影成 2D **透視深度圖**，當作 FLUX ControlNet 的精確空間條件。
> **純 NumPy** 即可，先只做深度圖，需要時再加 segmentation。

```
Scene Graph 座標 (俯視 bbox)
        │  每件家具 → 長方體（footprint + 高度）
        ▼
3D 房間立方體擺位（world coords）
        │  固定針孔相機 + z-buffer
        ▼
2D 透視深度圖（near=亮 / far=暗，對齊 Depth-Anything 慣例）
        │  ＋ 可選 segmentation mask（同一 pass 順手輸出）
        ▼
FLUX ControlNet / Kontext 風格化渲染
```

關鍵理念：座標**不再翻譯成自然語言讓 FLUX 猜**，而是直接在幾何上產生深度條件。

## 3. 完整資料流（接進 LangGraph 後）

```
requirement_analyzer
   └─ visual_preprocessing          Depth-Anything 跑輸入照片 → depth.png
   └─ design_director               路由
   └─ layout_and_style_agent        ★ 現在會真的規劃佈局（原本是 stub）
          run_layout_agent()
            ├─ LLM 產生家具座標 → 硬/軟約束迭代 → best_items
            ├─ _generate_floor_plan()        俯視平面圖（給人看）
            ├─ _generate_projected_depth()   ★ 投影成透視深度圖 + segmentation
            │      └─ scene_graph_to_depth.project_scene_graph_to_depth()  [純 NumPy]
            └─ scene_graph = {
                   furniture_placements,        精確座標
                   projected_depth_path,  ★     餵 ControlNet 的深度圖
                   projected_seg_path,    ★     segmentation mask
                   floor_plan_path, ...
               }
   └─ renderer
          ├─ depth_path = vision.get("depth")           預設：輸入照片深度
          ├─ if hint_layout: depth_path = projected_depth_path   ★ 覆蓋成投影深度
          └─ 依 LAYOUT_DEPTH_CONTROL_BACKEND 選後端：
                 "kontext"    → Kontext depth-fusion LoRA（鬆散參考，預設）
                 "controlnet" → 真正的 FLUX depth ControlNet（強約束，需 FAL_KEY）★
   └─ clip_evaluator
```

## 4. 新增元件詳解

### 4.1 `designbridge/scene_graph_to_depth.py`（新檔）

核心投影模組，純 NumPy。主要函式：

```python
project_scene_graph_to_depth(
    furniture_placements, space_info, out_path,
    image_size=(1024,1024), seg_out_path=None, camera_overrides=None,
) -> dict
```

實作步驟：

1. **長方體化** — `FURNITURE_HEIGHTS` 給每類家具一個高度（footprint 沿用 `layout_agent.FURNITURE_SIZES`）。
2. **擺進房間** — floor-plan 正規化座標映射到 world：
   - `x ∈ [0,1]` 左→右 → `X = (x-0.5) * room_w`
   - `y ∈ [0,1]` 上(遠牆)→下(近相機) → `Y = (1-y) * room_d`
   - `Z ∈ [0, height]` 地板→天花板
3. **針孔相機** — `_build_camera()`：站在近牆後方 `setback` 公尺、眼高 `eye_height`，朝 +Y 看，
   含俯角 `pitch`、水平視角 `hfov`。
4. **光柵化 + z-buffer** — `_raster_triangle` / `_raster_quad` 把房間外殼（地板/牆/天花板）
   與每個家具長方體的可見面投影、做 z-buffer。
5. **深度極性** — near=255（亮）、far=0（暗），對齊 `vision.run_depth_estimation` 的輸出慣例。
6. **segmentation** — 同一個 z-buffer pass 記錄每像素的物件 ID，上色輸出 mask。

另含 CLI：`python -m designbridge.scene_graph_to_depth placements.json --vis`

### 4.2 `scripts/calibrate_layout_depth.py`（新檔）

相機校準工具：固定佈局、掃描相機參數（HFOV / pitch / setback），可選 `--render` 實際呼叫
FLUX，輸出「深度圖 vs 成圖」並排 montage，肉眼挑出最貼合 FLUX 視角的相機設定。純 PIL 拼圖。

```bash
# 只看框景（不花 API）
python -m scripts.calibrate_layout_depth --hfov=55,65,75 --pitch=-6,-12
# 連 FLUX 算圖一起比
python -m scripts.calibrate_layout_depth --render --hfov=65,80 --pitch=-16
```

> 注意：argparse 對負數要用 `=`，例如 `--pitch=-16`。

## 5. 相較起始版本（`d97b3f90`）的逐檔改動

| 檔案 | 類型 | 改動 |
|---|---|---|
| `designbridge/scene_graph_to_depth.py` | **新檔** | 投影模組（座標→透視深度圖+seg），純 NumPy |
| `scripts/calibrate_layout_depth.py` | **新檔** | 相機校準工具 |
| `designbridge/layout_agent.py` | 修改 | 新增 `_generate_projected_depth()`，並在 `run_layout_agent` 的 `scene_graph` 加入 `projected_depth_path` / `projected_seg_path` |
| `designbridge/prompts.py` | 修改 | **補上 `LAYOUT_AGENT_PROMPT` 與 `LAYOUT_REFINEMENT_PROMPT`**（原本 `run_layout_agent` import 這兩個根本不存在的名稱 → 證明它從未在 production 跑過） |
| `designbridge/nodes.py` | 修改 | (a) `layout_and_style_agent_stub` 由純 stub 改為 `hint_layout=True` 時真的呼叫 `run_layout_agent`、回傳 `scene_graph`；(b) renderer 在 `hint_layout` 時用投影深度覆蓋輸入照片深度；(c) 接入新的 ControlNet 後端 |
| `designbridge/render_backends.py` | 修改 | 新增 `_render_flux_controlnet_depth_fal()`（fal.ai flux-general + 真正 depth ControlNet） |
| `designbridge/config.py` | 修改 | 新增投影/ControlNet 相關設定（見下） |

### 重點：被修掉的潛藏 bug

`run_layout_agent` 一直 `from designbridge.prompts import LAYOUT_AGENT_PROMPT, LAYOUT_REFINEMENT_PROMPT`，
但這兩個名稱在 `prompts.py` 從未定義。同時 graph 接的是**不呼叫 `run_layout_agent` 的 stub**，
所以這個 broken import 一直沒被觸發。這次把佈局接進 live graph 才讓它浮現，並補上 prompt 修好。

## 6. 新增設定（`config.py`）

```python
# 投影開關與相機（校準後預設）
ENABLE_LAYOUT_DEPTH_PROJECTION  = true     # DESIGNBRIDGE_ENABLE_LAYOUT_DEPTH_PROJECTION
LAYOUT_PROJECTION_HFOV          = 65.0      # DESIGNBRIDGE_LAYOUT_PROJECTION_HFOV
LAYOUT_PROJECTION_PITCH         = -16.0     # DESIGNBRIDGE_LAYOUT_PROJECTION_PITCH（校準結果）
LAYOUT_PROJECTION_SETBACK       = 0.8       # DESIGNBRIDGE_LAYOUT_PROJECTION_SETBACK

# 深度條件後端
LAYOUT_DEPTH_CONTROL_BACKEND    = "kontext" # 或 "controlnet"（需 FAL_KEY）
DEPTH_CONTROLNET_MODEL          = "Shakker-Labs/FLUX.1-dev-ControlNet-Depth"
```

`pitch=-16` 是用 `calibrate_layout_depth.py --render` 校準出來的：俯角大、看到較多地板，
成圖構圖最完整、家具分佈最貼合深度圖（對照 `pitch=-8` 偏平視、家具貼牆）。

## 7. 現況與後續

| 元件 | 狀態 |
|---|---|
| 投影模組 + 校準工具 | ✅ 完成、單元測試過 |
| `run_layout_agent` → 投影深度 | ✅ 已接、真實 LLM 與離線 fallback 皆驗證通過 |
| live graph 端到端 | ✅ 佈局節點已非 stub，完整流程會產生並使用投影深度 |
| Kontext depth LoRA 後端 | ✅ 既有；校準確認可用（但屬「鬆散參考深度」，非逐格對齊） |
| 真正 FLUX depth ControlNet 後端 | ⚠️ 程式碼已備、預設關閉；尚未端到端實測（需 `FAL_KEY`，HF 額度已用罄） |

**建議下一步：**

1. 設 `FAL_KEY` + `LAYOUT_DEPTH_CONTROL_BACKEND=controlnet`，實測真正 ControlNet 後端，
   微調 `conditioning_scale`（通常 0.5〜0.8）與 fal `controlnets` 參數名。
2. 若需更高家具辨識度，再把 segmentation mask 也接成第二條 ControlNet 條件（目前已產出、尚未餵入）。
3. 補跑 HFOV 上限的校準（65 vs 80 因額度用罄未比完）。
