# Style KB — 資料蒐集規劃

## 目標

為 9 個室內設計風格各蒐集 **50 張以上**高品質參考圖片，
以台灣本地設計平台為主，確保圖片風格符合台灣市場審美。

風格清單：現代、鄉村、古典、北歐、工業、日式、美式、奢華、新古典

---

## 資料來源

### 主要：100室內設計（100.com.tw）

| 項目 | 說明 |
|------|------|
| 技術架構 | Nuxt SSR，初始 HTML 有內容 |
| 分類導航 | JS 驅動（需 Playwright 點擊篩選） |
| 圖片 CDN | `s1.100.com.tw` |
| robots.txt | 只擋 `/search`、`/api/kit/captcha/` |
| 爬取難度 | 中（需 Playwright） |
| 優點 | 台灣最大設計平台、風格標籤清晰、圖片量大 |

**建議爬取欄位：**
- 案例標題、設計師名稱
- 案例封面圖 + 內頁圖片
- 空間類型（客廳、臥室...）
- 風格標籤（用於輔助分類驗證）
- 來源 URL

---

### 次要：設計家 Searchome（searchome.net）

| 項目 | 說明 |
|------|------|
| 技術架構 | Hybrid SSR + JS 輪播 |
| 分類 URL | `/search.aspx?whr=[類別]&idx=[頁碼]` |
| 圖片 CDN | `searchome-aws.hmgcdn.com` |
| robots.txt | 非常開放（Allow: /），僅擋帳號/管理頁面 |
| 爬取難度 | 中（部分圖片需等 JS 觸發） |
| 優點 | 案例數量多、設計師資訊豐富 |

---

### 可考慮的其他來源

| 來源 | 特性 | 備註 |
|------|------|------|
| **幸福空間**（housedesign.tv） | 台灣，含影片截圖 | 可補充特定風格 |
| **iDesign 愛設計** | 台灣設計社群 | 用戶上傳為主，品質不一 |
| **La Vie 行動家** | 設計雜誌，品質高 | 圖片數量較少 |
| **Houzz** | 國際，台灣案例有限 | 做補充用 |
| **Unsplash API** | 免費授權、API 直接取用 | 非台灣本地，風格偏西方 |

> **建議：** 先從 100室內設計跑完，缺口風格再補設計家，其他來源視需求追加。

---

## 爬取策略

### 工具選擇

```
requests + BeautifulSoup  → 靜態頁面（設計家案例列表）
Playwright                → 需要 JS 互動的頁面（100室內設計風格篩選）
```

### 執行流程

```
[Step 1] 蒐集案例 URL 清單
Playwright 開啟風格篩選頁
→ 依序點選 9 個風格標籤
→ 滾動到底觸發 lazy load
→ 蒐集所有案例頁連結
→ 存到 raw_urls/<style_id>.txt

[Step 2] 下載圖片
逐一進入案例頁
→ 抓取所有設計圖片 URL（過濾 logo、廣告）
→ 下載到 style_kb/raw/<來源>/<style_id>/<圖檔>
→ 記錄 metadata JSON（來源、標題、原始標籤）

[Step 3] 品質過濾
→ 過濾解析度 < 800x600 的圖片
→ 過濾檔案大小 < 100KB
→ 去除重複（圖片 MD5 hash）

[Step 4] 分類確認（Gemini）
→ 執行 classify_image.py（待建）
→ Gemini 判斷主風格 + 信心分數
→ 信心分數 < 0.7 → 移至待人工複審資料夾
→ 通過 → 移至 style_kb/images/<style_id>/

[Step 5] 特徵萃取
→ 執行 extract_style_kb.py（已有）
→ 生成 style_kb/outputs/<style_id>/<圖檔>.json

[Step 6] 建向量索引
→ 執行 build_vector_store.py（已有）
→ 新圖片增量更新向量庫
```

---

## 目錄結構

```
style_kb/
├── raw/                        ← 爬蟲原始下載（不清洗）
│   ├── 100interior/
│   │   ├── nordic/
│   │   │   ├── img_001.jpg
│   │   │   └── img_001_meta.json   ← 來源 URL、標題、原始標籤
│   │   └── modern/
│   └── searchome/
│       └── nordic/
│
├── images/                     ← 通過品質過濾 + 分類確認的圖片
│   └── <style_id>/
│
├── review/                     ← 信心分數不足，待人工複審
│   └── <style_id>/
│
└── outputs/                    ← Gemini 特徵萃取結果（現有）
    └── <style_id>/
```

---

## 數量目標

| 風格 | 目標張數 | 目前 |
|------|----------|------|
| 現代 modern | 50 | 20 |
| 鄉村 country | 50 | 20 |
| 古典 classic | 50 | 0 |
| 北歐 nordic | 50 | 0 |
| 工業 industrial | 50 | 0 |
| 日式 japanese | 50 | 0 |
| 美式 american | 50 | 5 |
| 奢華 luxury | 50 | 20 |
| 新古典 neoclassic | 50 | 0 |
| **合計** | **450** | **65** |

---

## 圖片品質標準

- 解析度：**≥ 1024 x 768**（確保 Stable Diffusion 生成品質）
- 檔案大小：**≥ 150KB**
- 內容：**室內空間全景為主**，避免局部特寫（燈具、裝飾品）
- 去除：浮水印明顯、平面圖、施工照

---

## 分類策略討論

### 問題：不直接信任網站標籤

各平台標籤不統一：
```
100室內設計：「北歐風」「輕北歐」「北歐簡約」
設計家：     「北歐」「斯堪地那維亞」「Scandinavian」
```

### 做法：Gemini 二次分類

用 `classify_image.py`（待建）讓 Gemini 看圖判斷：

```json
{
  "primary_style": "nordic",
  "confidence": 0.89,
  "secondary_style": "japanese",
  "reason": "大量留白、淺木色、簡潔線條，符合北歐風核心特徵"
}
```

- confidence ≥ 0.80 → 自動歸入對應風格
- confidence 0.60~0.79 → 放入 `review/` 人工確認
- confidence < 0.60 → 丟棄或重新爬取

---

## 注意事項

1. **爬取速度**：每次請求間隔 1.5~2 秒，避免被封 IP
2. **User-Agent**：設定為正常瀏覽器 UA
3. **版權**：圖片僅用於本地模型訓練與參考，不對外展示
4. **增量執行**：每次執行只下載新案例，已存在的跳過

---

## 待建腳本

| 腳本 | 功能 | 狀態 |
|------|------|------|
| `scraper_100.py` | 爬取 100室內設計 | 待建 |
| `scraper_searchome.py` | 爬取設計家 | 待建 |
| `classify_image.py` | Gemini 自動風格分類 | 待建 |
| `quality_filter.py` | 解析度/大小/去重過濾 | 待建 |
| `extract_style_kb.py` | Gemini 特徵萃取 | ✅ 已有 |
| `build_vector_store.py` | 建 ChromaDB 索引 | ✅ 已有 |
