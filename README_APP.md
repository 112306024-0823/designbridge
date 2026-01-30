# DesignBridge 測試介面

## 快速啟動

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

或單獨安裝 Streamlit：

```bash
pip install streamlit
```

### 2. 啟動 Web 介面

```bash
streamlit run app.py
```

執行後會自動在瀏覽器開啟 `http://localhost:8501`

### 3. 使用介面

- 左側輸入欄位：
  - **文字需求**：描述設計需求（例如「客廳想要北歐風格，希望動線順暢」）
  - **改動幅度**：拉桿調整 edit_scope（0.0 = 最小改動，1.0 = 大幅改動）
  - **初始圖片路徑**：可選，留空表示從空布局開始

- 點擊「執行工作流」後，介面會顯示：
  - 路由決策（Layout / Style / Design Adjuster / Layout+Style）
  - 結構化需求（房間類型、目標風格）
  - 視覺前處理結果（stub）
  - 中間輸出
  - 完整 State JSON

### 4. 範例提示詞

點擊左側範例按鈕快速測試不同路由：

- **布局優化** → 預期路由到 `layout`
- **風格變更** → 預期路由到 `style`
- **局部微調** → 預期路由到 `design_adjuster`
- **布局+風格** → 預期路由到 `layout_and_style`

## 測試情境

### 情境一：Layout Agent

```
文字需求：客廳動線不順暢，希望重新規劃布局
edit_scope：0.7
預期路由：layout
```

### 情境二：Style Agent

```
文字需求：想要改成現代簡約風格
edit_scope：0.5
預期路由：style
```

### 情境三：Design Adjuster

```
文字需求：只想調整沙發位置和顏色
edit_scope：0.2
預期路由：design_adjuster
```

### 情境四：Layout + Style 協作

```
文字需求：北歐風格，開放式空間，動線順暢
edit_scope：0.8
預期路由：layout_and_style
```

## 介面截圖

介面包含：

1. **左側輸入欄**：文字需求、edit_scope 滑桿、初始圖片路徑
2. **範例提示詞按鈕**：快速載入測試案例
3. **執行按鈕**：觸發工作流
4. **結果顯示區**：
   - Task ID / Iteration / 路由決策（三欄卡片）
   - 結構化需求（展開式 JSON）
   - 視覺前處理結果
   - 中間輸出
   - 完整 State（折疊式）

## 後續擴充

當實作真實的 agent 後，可在介面加上：

- 圖片上傳與預覽（initial_image）
- 生成圖顯示（generated_image）
- 評估結果與 feedback
- 迭代控制（繼續 / 停止按鈕）
- 歷史紀錄（previous runs）
