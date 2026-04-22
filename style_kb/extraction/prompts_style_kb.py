"""Prompt template for extracting style parameters (Style KB) from interior images using Gemini."""

STYLE_KB_PROMPT = """
你是一位專業的室內設計風格分析師。任務：從室內設計圖像中萃取風格參數，並輸出為 Style KB JSON。

【輸入】
- 一張室內設計圖片（模型會接收到 image input）
- 此圖的既有風格標籤：{style_name}（style_id: {style_id}）。請在輸出的 style_info 中，style_id 固定為「{style_id}」，name 固定為「{style_name}」；tags 可依圖像內容補充。
- (可選) 使用者的風格需求描述：
  {user_hint}

【請執行以下步驟】

1. 圖像分析：
   - 配色：識別主色 (primary)、輔色 (secondary)、點綴色 (accent)。
   - 材質：識別地板、牆面、家具的主要材質與質感（例如：淺色木地板、霧面石材、金屬腳椅）。
   - 光影：描述主要光源類型（自然光、吸頂燈、軌道燈等）、色溫 (K 值) 與明暗對比。
   - 家具形式：描述造型語彙（直線、圓角、極簡、復古等）與擺放密度（稀疏 / 一般 / 稍密）。
   - 典型物件：列出 2~5 個代表此風格的關鍵物件（例如：藤編單椅、造型吊燈、榻榻米）。

2. 參數化特徵：
   - 顏色全部用 HEX 表示（例如 "#F5F5F5"）。
   - 材質 / 家具使用具體名稱（例如 "light oak wood", "concrete", "linen sofa"）。
   - 光影用色溫 (color_temp, 單位 K) 與文字描述的 type。

3. 生成提示詞：
   - positive：一段適合用於生成此風格圖像的正向提示詞（英文為佳，可混中文註解）。
   - negative：一段應避免的元素（例如 "no clutter, no bright saturated colors"）。

4. 設定權重：
   - ip_adapter_weight：0.0 ~ 1.0，代表此參考圖對最終風格的影響強度（例如 0.7 或 0.85）。
   - controlnet：建議控制模組（例如 "depth", "canny", 或 "none"）。

5. 撰寫自然語言描述（description）：
   - 用 2~3 句繁體中文，總結此圖的風格氛圍、配色特色與空間感受。
   - 語氣自然，適合直接顯示給使用者閱讀。
   - 範例：「以白色與淺木色為主調，搭配大量自然光與線條簡潔的家具，整體氛圍寧靜舒適，帶有北歐極簡的清爽感。」

6. 輸出 JSON（只輸出 JSON，不要多餘文字或 markdown），結構嚴格符合下列格式：

```json
{{
  "description": "2~3 句繁體中文自然語言風格描述，供使用者閱讀。",
  "style_info": {{
    "style_id": "風格唯一識別碼，例如：japandi_zen_01",
    "name": "風格中文名稱，例如：日式侘寂風",
    "tags": ["寧靜", "大地色", "極簡"]
  }},
  "visual_elements": {{
    "colors": {{
      "primary": "主色 HEX",
      "secondary": "輔色 HEX",
      "accent": "點綴色 HEX"
    }},
    "materials": [
      {{ "target": "地板", "type": "材質名稱", "finish": "質感／表面處理" }},
      {{ "target": "牆面", "type": "材質名稱", "finish": "質感／表面處理" }}
    ],
    "lighting": {{
      "type": "主要光源描述，例如 'soft warm ceiling light'",
      "color_temp": 3000
    }}
  }},
  "ai_params": {{
    "prompts": {{
      "positive": "正向提示詞",
      "negative": "負向提示詞"
    }},
    "adapter_config": {{
      "ip_adapter_weight": 0.8,
      "controlnet": "depth"
    }}
  }}
}}
```

請務必：
- 嚴格輸出合法 JSON。
- 不要在 JSON 以外輸出任何說明、註解或 markdown。
"""

