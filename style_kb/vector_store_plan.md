# Style KB — 向量資料庫規劃

## 為什麼棄用聚合方案

現有聚合流程把每個風格的 N 張圖統計平均後輸出一份代表性 JSON，
造成以下問題：

- **均值回歸**：50 張鄉村風格圖平均後，失去個別圖片的視覺特色
- **無法區分子類型**：同一風格內「溫暖木質鄉村」和「藍白地中海鄉村」被混為一談
- **無法回應使用者文字描述**：使用者說「帶點溫暖感」，聚合方案只能給固定結果
- **擴充性差**：新增圖片需重新聚合，索引增量更新困難

---

## 新架構：Per-image 向量索引

### 核心概念

```
每張圖 = 一個獨立的向量資料點

50 張鄉村圖 → 50 個向量
10 個風格   → 500 個向量（規模擴充後）

查詢時：
使用者需求 → embedding → 在 500 個點中找最近的 top-k
→ 返回最相關的 3~5 張圖片路徑
→ 這些圖直接作為 IP-Adapter 的 style reference 送進生成模型
```

### 資料流

```
[離線建索引]

style_kb/images/<style_id>/<image>.jpg
           +
style_kb/outputs/<style_id>/<image>.json
           ↓
    CLIP Vision Encoder
           ↓
    768-dim 圖像向量
           ↓
    ChromaDB 儲存
    metadata: { style_id, image_path, json_path,
                tags, primary_color, color_temp }


[線上查詢]

使用者輸入：選單「鄉村」+ 文字「溫暖廚房，白色木質感」
           ↓
    CLIP Text Encoder
           ↓
    query 向量
           ↓
    ChromaDB 搜尋
    filter: { style_id: "country" }
    top_k: 3
           ↓
    返回最相似的 3 張圖片路徑 + 對應 JSON
           ↓
    取出 prompt / 顏色 / 材質（從各自 JSON）
    依相似度分數加權組合
           ↓
    StyleParamsJSON → Renderer
    圖片路徑        → IP-Adapter
```

---

## Embedding 策略：CLIP

### 為什麼用 CLIP

- 圖片和文字在**同一個向量空間**：使用者輸入的文字可直接和圖像向量比對
- 無需 Gemini API 呼叫（查詢時完全本地）
- 對視覺特徵（顏色、材質、光線）的捕捉優於純文字 embedding

### 模型選擇

| 模型 | 向量維度 | 大小 | 說明 |
|------|----------|------|------|
| `openai/clip-vit-base-patch32` | 512 | ~600MB | 輕量，建議起步 |
| `openai/clip-vit-large-patch14` | 768 | ~1.7GB | 精度更高 |

建議先用 `clip-vit-base-patch32` 驗證效果。

### 備用方案：Text Embedding（快速起步）

若暫時不想下載 CLIP，可先用 Gemini `text-embedding-004`
把 JSON 欄位組合成文字再 embed，後續再切換 CLIP。

```
"鄉村風格。標籤：溫馨、木質、明亮。
地板：淺色木霧面。牆面：油漆霧面。
色調：主色#F5F5F5 輔色#E0D4C5 色溫3000K。
Cozy country style living room, warm white walls..."
```

---

## 向量庫：ChromaDB

### 選擇理由

- 完全本地、無需額外 server
- Python 原生，一行安裝：`pip install chromadb`
- 支援 metadata 過濾（按 style_id 縮小搜尋範圍）
- 持久化儲存於本地資料夾

### Collection 結構

```python
collection: "style_images"

每筆記錄：
  id:        "country_01"
  embedding: [0.23, -0.11, ...]   # CLIP 圖像向量
  document:  "鄉村風格，溫馨木質..."  # 供文字搜尋備用
  metadata: {
    "style_id":    "country",
    "style_name":  "鄉村",
    "image_path":  "style_kb/images/country/country_01.jpg",
    "json_path":   "style_kb/outputs/country/country_01.json",
    "tags":        "溫馨,木質,明亮",
    "primary_color": "#F5F5F5",
    "color_temp":  3000
  }
```

---

## 檔案規劃

```
style_kb/
├── images/                     # 原始圖片（不動）
├── outputs/                    # 每張圖的 Gemini 萃取 JSON（不動，source of truth）
├── vector_store/               # ChromaDB 持久化資料夾（自動產生）
├── build_vector_store.py       # 建索引腳本（離線執行）
├── styles.py                   # 不動
├── extract_style_kb.py         # 不動
├── aggregated/                 # 棄用（保留備查，不再讀取）
└── aggregate_style_kb.py       # 棄用

designbridge/
├── style_vector.py             # 新增：ChromaDB 查詢封裝
└── style_apply.py              # 修改：build_style_params() 改走向量查詢
```

---

## 建索引腳本規劃（build_vector_store.py）

```
執行方式：
  python -m style_kb.build_vector_store           # 建立全部
  python -m style_kb.build_vector_store country   # 只建 country
  python -m style_kb.build_vector_store --reset   # 清空重建

流程：
1. 掃描 style_kb/outputs/<style_id>/*.json
2. 對應找到 style_kb/images/<style_id>/<stem>.jpg
3. CLIP encode 圖片 → 向量
4. 從 JSON 讀取 metadata（tags、顏色、色溫、prompt）
5. 寫入 ChromaDB（支援增量：已存在的 id 跳過）

輸出：
  style_kb/vector_store/   ← ChromaDB 持久化目錄
```

---

## 查詢封裝規劃（style_vector.py）

```python
# 主要介面

def query_style_images(
    text_query: str,
    style_id: str | None = None,   # None = 不限風格
    top_k: int = 3,
) -> list[StyleImageResult]:
    """
    返回最相似的 top_k 張圖片資訊。
    StyleImageResult 包含：
      - image_path: 圖片路徑（給 IP-Adapter）
      - json_path:  對應 JSON 路徑（讀 prompt / 顏色）
      - style_id / style_name
      - similarity_score: 0~1
    """
```

---

## Style Agent 整合後的運作

```
[原本]
使用者選「鄉村」
  → resolve_style_profile_id() → "country"
  → load_aggregated_style("country") → 讀 aggregated JSON
  → 固定的 prompt / 固定顏色

[新]
使用者選「鄉村」+ 輸入「溫暖廚房，白色木質」
  → query_style_images("溫暖廚房 白色木質", style_id="country", top_k=3)
  → [country_01 (0.94), country_07 (0.88), country_15 (0.81)]
  → 依分數加權取各自 JSON 的 prompt / 顏色 / 材質
  → 3 張圖片路徑送 IP-Adapter
  → 動態組合 StyleParamsJSON
```

---

## 實作順序

1. `pip install chromadb transformers`
2. 撰寫並執行 `build_vector_store.py` → 建立本地向量索引
3. 撰寫 `style_vector.py` → 查詢介面
4. 修改 `designbridge/style_apply.py` → 接向量查詢
5. 修改 `designbridge/nodes.py` → 把 top-k 圖片路徑傳給 Renderer / IP-Adapter
6. 驗證：同一風格不同文字描述，確認返回不同圖片

---

## 擴充性

| 情境 | 做法 |
|------|------|
| 新增圖片 | 執行 `build_vector_store.py` 增量更新（已存在 id 跳過） |
| 新增風格 | 在 `styles.py` 加入，放入圖片和 outputs JSON，重新執行建索引 |
| 不限風格搜尋 | `query_style_images(text, style_id=None)` |
| 跨風格混合 | top_k 結果中包含多個 style_id → IP-Adapter 混用多張參考圖 |
