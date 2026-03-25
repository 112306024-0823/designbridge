## 萃取方式

總共有十個 style（From 100 室內設計網站）。

每個 style 目前以多張參考圖進行單張萃取（例如 20 張圖 -> 20 份 style JSON），
再透過聚合流程合併成 1 份可直接用於風格套用的檔案。

## 聚合參數方式

聚合流程採用「統計聚合 + Gemini 語義聚合」兩階段：

1. 統計聚合（結構化欄位）
- 顏色：收集各檔案 `visual_elements.colors` 的 `primary/secondary/accent`，以 RGB 平均後輸出代表色。
- 材質：統計 `visual_elements.materials` 中 `type` 出現頻率，取前幾名作為 `top_materials`。
- 標籤：統計 `style_info.tags` 出現頻率，輸出 `top_tags`。
- 光線：統計 `visual_elements.lighting.color_temp`，輸出平均色溫 `avg_color_temp_k`。
- 生成權重：統計 `ai_params.adapter_config.ip_adapter_weight`，輸出平均值。

2. Gemini 智能聚合（語義欄位）
- 將統計摘要與風格資訊送入 Gemini。
- 生成可直接套用的風格語義參數：
	- `unified_positive_prompt`
	- `unified_negative_prompt`
	- `visual_essence`
	- `recommended_ip_adapter_weight`
	- `style_summary`
	- `material_recommendations`
	- `controlnet_type`

3. 最終輸出（每個 style 1 份）
- 輸出檔案位置：`style_kb/aggregated/<style_id>_aggregated.json`
- 主要欄位：
	- `statistics`：偏客觀統計值（顏色、材質、標籤、色溫）
	- `ai_config`：偏生成模型可直接使用參數（prompt、negative、ip-adapter 權重、controlnet 類型）
	- `style_profile`：偏產品與敘述層特徵（視覺精髓、摘要、材質建議）

## 為什麼這樣設計

- 純統計法雖穩定，但難以得到可直接用於生成的高品質 prompt。
- 純 LLM 法語義強，但可控性較差。
- 混合方案可同時保留可解釋性（統計）與可用性（生成語義），較適合後續「風格套用」流程。
