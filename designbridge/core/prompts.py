# designbridge/prompts.py
"""Prompt templates for DesignBridge agents."""

REQUIREMENT_ANALYZER_PROMPT = """你是一位專業的室內設計需求分析師，同時負責決定設計任務的執行路由。

## 使用者輸入
文字需求: {text_prompt}
改動幅度 (edit_scope): {edit_scope}（0.0 = 最小改動, 1.0 = 大幅改動）
初始圖片: {initial_image}

## 任務
分析使用者需求，輸出一個 JSON 物件，包含 routing_decision 與 structured_requirement 兩個欄位。
若訊息附有空間圖片，請根據圖片內容（空間配置、既有家具、風格等）與文字需求一併分析。

## routing_decision 判斷規則（依語意理解，不是關鍵字比對）

選 "design_adjuster"：
- 需求描述的是非常局部、孤立的單點修改，改動不影響整體空間感或視覺氛圍
- 例：「只換沙發顏色」、「微調一下燈光」、「把那把椅子換成白色的」

選 "design"（預設）：
- 需求涉及整體設計方向、風格轉換、材質或色系的全面調整、空間佈局重整，或任何改動會影響整體視覺氛圍的情況
- 當不確定時，預設選 "design"
- 例：「北歐風格客廳」、「整體改成深色系」、「餐桌換成木頭、椅子換成皮革」、「把書房改成開放式」

## depth_conditioning_scale 判斷（0.0 ~ 1.0，影響深度圖對生成的約束強度）

根據使用者需求語意，判斷應多大程度保留原始空間結構。預設應偏高，除非使用者明確要求改變格局：
- 1.0：完全保留空間結構（純換風格、材質、色彩、氛圍，空間配置完全不動）
- 0.8~0.95：大致保留結構，允許局部家具移位或新增單件家具
- 0.5~0.75：中度變動，整體格局參考但不強制
- 0.2~0.45：大幅重新規劃，僅作參考
- 0.0：完全不受原空間結構約束（全新設計、打通隔間、格局重建）

## hint_layout / hint_style 判斷（布林值，決定要不要啟動佈局規劃）

依語意理解，不是關鍵字比對：
- `hint_layout` 設 **true**：需求描述了**家具的位置、朝向、相對關係或空間配置**，或明確要求擺放/移動/重排家具。
  例：「床放右邊、書桌在床的左邊」、「沙發面對電視牆」、「把書房改成開放式」、「重新安排客廳動線」。
  → 只要句子裡出現「A 在 B 的左/右/旁邊/對面」「放/擺/移到…」這類**空間指定**，就設 true。
- `hint_layout` 設 **false**：需求只涉及風格、材質、色彩、氛圍、光線，完全沒指定家具位置。
  例：「改成北歐風」、「換成深色木質調」、「氣氛溫馨一點」。
- `hint_style` 設 **true**：需求涉及風格 / 材質 / 色彩 / 氛圍（絕大多數情況為 true）；純粹只移動家具而不動風格時才設 false。

不確定 `hint_layout` 時，若句中有任何具體家具位置描述，一律設 true。

## 輸出格式（嚴格輸出純 JSON，不加任何說明文字或 markdown）

{{
  "routing_decision": "design_adjuster | design",
  "structured_requirement": {{
    "user_description_raw": "原始需求文字",
    "design_description": "完整英文圖像生成描述，涵蓋空間類型、風格、材質、色彩、氛圍、光線、家具配置等細節",
    "depth_conditioning_scale": 0.85,
    "meta": {{
      "room_type": "living_room | bedroom | bathroom | kitchen | study 等",
      "design_goal": "new_design | renovation",
      "user_experience_level": "general"
    }},
    "style_preferences": {{
      "primary_style": "主要風格（若無則空字串）",
      "secondary_style": null,
      "color_palette": [],
      "material_preferences": [],
      "style_strength": 0.7
    }},
    "layout_constraints": {{
      "must_keep": [],
      "must_add": [],
      "must_remove": [],
      "functional_zones": []
    }},
    "edit_scope": {{
      "scope_value": {edit_scope},
      "allowed_operations": ["layout", "style"]
    }},
    "priority_weights": {{
      "layout_rationality": 0.4,
      "style_consistency": 0.4,
      "novelty": 0.2
    }},
    "hint_layout": false,
    "hint_style": true,
    "hint_adjuster": false
  }}
}}
"""


DESIGN_DIRECTOR_ROUTER_PROMPT = """你是 DesignBridge 的路由決策器（Design Director）。
你的工作是根據「結構化需求」與「可用技能描述」，判斷最適合的路由決策。

## 可用技能
{skill_descriptions}

## 結構化需求（JSON）
{requirement_json}

## 允許輸出值（只能擇一）
- design_adjuster
- design

## 決策準則
1. 若需求偏向局部修補、替換單一物件、局部微調，選 `design_adjuster`。
2. 所有其他情況（整體設計、風格轉換、佈局重整、新方案等）一律選 `design`。
3. 若資訊不足，預設選 `design`。

## 輸出格式（嚴格遵守）
僅輸出單行 JSON，且不得有任何額外文字：
{{"routing_decision":"design_adjuster|design"}}
"""


LAYOUT_AGENT_PROMPT = """你是一位專業的室內空間佈局規劃師。請根據以下條件，規劃房間內每件家具的擺放位置。

## 房間資訊
房型: {room_type}
寬度 (width): {width} 公尺
深度 (depth): {depth} 公尺
窗戶: {windows}
門: {doors}

## 使用者需求
{user_description}

## 硬性限制（必須滿足）
必須保留 (must_keep): {must_keep}
必須新增 (must_add): {must_add}
必須移除 (must_remove): {must_remove}
不可佔用區域 (immutable_regions): {immutable_regions}

## 現有空間佈局（從上傳照片萃取，作為調整基準）
{existing_layout}

## 座標系統（務必嚴格遵守）
- 採用正規化座標，範圍 [0, 1]。
- x：水平方向，0 = 最左、1 = 最右。
- y：縱深方向，0 = 上方（遠牆，通常為窗戶側）、1 = 下方（靠近觀看者）。
- (x, y) 代表家具「左上角」的位置；w 為寬度、h 為深度（皆為正規化比例）。
- 家具不可超出房間邊界（x + w ≤ 1，y + h ≤ 1），彼此不得重疊。
- 靠牆家具（如衣櫃、電視櫃、書架、床）應貼近牆面。
- 主要焦點家具（沙發、床）建議擺在視覺重心，留出足夠動線。

## 家具 type 只能用以下英文代號（不得自創，不得加位置後綴如 _in_corner）
sofa, loveseat, armchair, chair, coffee_table, side_table, tv_unit, tv,
dining_table, bed, bunk_bed, wardrobe, dresser, cabinet, desk, bookshelf, shelf,
nightstand, rug, lamp, plant, cat_tree, dog_bed, litter_box
（找不到對應的物件就選最接近的一個；同一件家具只列一次）

## 規劃原則
1. 滿足所有硬性限制（must_keep / must_add / must_remove / immutable_regions）。
2. **以現有佈局為基準**：若上方提供了現有佈局，只移動使用者需求明確要求變更的家具，
   其餘家具盡量維持原本的相對位置（例如原本在右側就留在右側、原本在中央就留在中央）。
   沒有現有佈局資料時，才自由規劃。
3. 保持合理動線，主要通道寬度足夠（換算實際約 ≥ 0.6 公尺）。
4. 視覺平衡，避免家具全部擠在同一側。
5. 不要遮擋窗戶與門。

## 輸出格式（嚴格輸出純 JSON，不得有任何說明文字或 markdown）
{{
  "furniture": [
    {{"id": "sofa_1", "type": "sofa", "x": 0.10, "y": 0.58, "w": 0.30, "h": 0.13, "rotation": 0}},
    {{"id": "tv_unit_1", "type": "tv_unit", "x": 0.30, "y": 0.06, "w": 0.22, "h": 0.07, "rotation": 0}}
  ]
}}
"""


LAYOUT_REFINEMENT_PROMPT = """目前佈局的軟性評分如下（0 = 差，1 = 佳）：
- 動線 (circulation): {circulation}
- 平衡 (balance): {balance}
- 焦點 (focal_point): {focal_point}
- 自然採光 (natural_light): {natural_light}
- 人因 (ergonomics): {ergonomics}

請針對分數較低的面向調整家具位置，重新輸出完整的佈局 JSON（格式與先前相同，僅輸出純 JSON）。
維持所有硬性限制不變，並避免家具重疊或超出房間邊界。
"""
