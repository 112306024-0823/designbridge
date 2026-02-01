# DesignBridge API 設定指南

## Requirement Analyzer - Gemini API 設定

### 1. 安裝依賴

```bash
pip install google-generativeai
```

或使用 requirements.txt：

```bash
pip install -r requirements.txt
```

### 2. 取得 Gemini API Key

1. 前往 [Google AI Studio](https://makersuite.google.com/app/apikey)
2. 登入你的 Google 帳號
3. 點擊「Create API Key」建立 API key
4. 複製你的 API key

### 3. 設定 API Key

有兩種方式設定：

#### 方式一：環境變數（推薦）

**Windows PowerShell:**
```powershell
$env:GEMINI_API_KEY="YOUR_API_KEY_HERE"
```

**Windows CMD:**
```cmd
set GEMINI_API_KEY=YOUR_API_KEY_HERE
```

**Linux/Mac:**
```bash
export GEMINI_API_KEY="YOUR_API_KEY_HERE"
```

#### 方式二：直接寫在 config.py

編輯 `designbridge/config.py`：

```python
class Config:
    # TODO: Fill in your Gemini API key here
    GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"  # 👈 填入你的 API key
    
    GEMINI_MODEL = "gemini-1.5-pro"  # 或 "gemini-1.5-flash"
    GEMINI_TEMPERATURE = 0.3
```

### 4. 測試 API 串接

執行測試腳本：

```bash
python run_designbridge.py
```

或啟動 Streamlit 介面：

```bash
streamlit run app.py
```

輸入需求後，如果看到 console 出現：
- ✅ 正常輸出結構化 JSON → API 成功串接
- ⚠️ "Gemini API not available or failed, falling back to rule-based" → API key 未設定或錯誤，使用規則 fallback

### 5. Gemini 模型選擇

在 `config.py` 可調整模型：

| 模型 | 說明 | 適用情境 |
|------|------|----------|
| `gemini-1.5-pro` | 較強大，理解力更好 | 複雜需求、多語言、隱式需求推理 |
| `gemini-1.5-flash` | 較快速，成本較低 | 簡單需求、快速測試 |
| `gemini-2.0-flash-exp` | 實驗版，最新功能 | 嘗試最新特性 |

### 6. 調整 Temperature

`GEMINI_TEMPERATURE` 控制生成的隨機性：

- `0.0` - 最確定性，相同輸入產生相同輸出
- `0.3` - 推薦值，較穩定且有創意
- `1.0` - 最具創造性，但可能不穩定

### 7. Fallback 機制

如果 Gemini API 不可用或失敗，系統會自動退回到 **規則式分析**：

- 關鍵字匹配房間類型與風格
- 簡單的 hint 判斷（layout / style / adjuster）
- 不需要 API key，但分析精度較低

## Prompt 調整

需求分析的 prompt 定義在 `designbridge/prompts.py`：

```python
REQUIREMENT_ANALYZER_PROMPT = """你是一位專業的室內設計需求分析師...
```

可依需求調整：
- 加入更多房間類型或風格
- 修改隱式需求推理邏輯
- 調整輸出 JSON 格式

## 常見問題

### Q: API 呼叫失敗怎麼辦？

**A:** 檢查以下項目：
1. API key 是否正確設定
2. 是否已安裝 `google-generativeai`
3. 網路連線是否正常
4. API 配額是否用完（檢查 [Google AI Studio](https://makersuite.google.com/app/apikey)）

### Q: 如何看到 API 呼叫紀錄？

**A:** 在 console 會顯示：
- 成功：輸出 structured_requirement JSON
- 失敗：顯示 "⚠️ Gemini API not available or failed"

### Q: 可以用其他 LLM 嗎？

**A:** 可以！修改 `nodes.py` 的 `_call_gemini_requirement_analyzer` 改用：
- OpenAI GPT-4
- Claude (Anthropic)
- 本地 Ollama
- 其他支援 JSON mode 的 LLM

只需保持相同的輸入/輸出格式即可。

## 深度估計模型（Depth Anything V2）

預設使用 **Depth Anything V2**（vitl，335M params），透過 HuggingFace Transformers 載入。

在 `config.py` 可調整 `DEPTH_MODEL`：

| 模型 | 參數量 | 說明 |
|------|--------|------|
| `depth-anything/Depth-Anything-V2-Small-hf` | 24.8M | 最快，適合 CPU |
| `depth-anything/Depth-Anything-V2-Base-hf` | 97.5M | 平衡 |
| `depth-anything/Depth-Anything-V2-Large-hf` | 335M | **預設**，品質最佳 |

需 `transformers>=4.45.0` 與 `torch`。第一次執行會從 HuggingFace 下載模型。

## 下一步

串接完 Requirement Analyzer 後，可繼續串接：

1. **Visual Preprocessing**：Depth Anything V2 (depth) + UPerNet (segmentation)
2. **Layout/Style/Adjuster Agents**：Stable Diffusion + ControlNet
3. **Evaluation**：品質評估 + 決策迭代

每個階段都可參考 `README_API.md` 設定對應 API。
