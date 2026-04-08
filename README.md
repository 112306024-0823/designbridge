# DesignBridge

使用 **LangGraph** 編排的多代理室內設計工作流。現在建議使用 **FastAPI + Vue**。系統規格請見 `docs/DesignBridge.md`，Agent/JSON 規格請見 `docs/SCHEMAS.md`。

## 快速啟動（Vue + FastAPI）

### 1) 安裝依賴

在專案根目錄執行：

```bash
pip install -r requirements.txt
cd frontend
npm install
cd ..
```

### 2) 啟動後端（FastAPI）

在專案根目錄執行：

```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

後端啟動後可用：
- `http://localhost:8000`
- `http://localhost:8000/docs`（Swagger）

### 3) 啟動前端（Vue）

另開一個終端機，在專案根目錄執行：

```bash
cd frontend
npm run dev
```

前端啟動後瀏覽器開 Vite 顯示的網址（通常是 `http://localhost:5173`）。

### 4) 一鍵啟動（Windows）

可直接執行：

```bat
start_app.bat
```

它會自動開兩個視窗，分別啟動 FastAPI 與 Vue。

## 舊版啟動（Streamlit）

若仍需使用舊測試介面，可在專案根目錄執行：

```bash
streamlit run app.py
```

若指令無效，可改用：

```bash
python -m streamlit run app.py
```

啟動後瀏覽器開 `http://localhost:8501`。

## API 設定（Gemini）

Requirement Analyzer 會優先用 **Google Gemini API** 解析需求；若未設定或失敗，會自動 fallback 到規則式解析。

### 1) 安裝依賴

```bash
pip install -r requirements.txt

pip install google-generativeai
```

### 2) 取得 API Key

- 到 `https://makersuite.google.com/app/apikey` 建立並複製 API key

### 3) 設定 `GEMINI_API_KEY`

**方式 A：寫入 `.env`（推薦）**

在專案根目錄新增/編輯 `.env`：

```env
GEMINI_API_KEY=YOUR_API_KEY_HERE
```

**方式 B：臨時環境變數**

PowerShell：

```powershell
$env:GEMINI_API_KEY="YOUR_API_KEY_HERE"
```

CMD：

```cmd
set GEMINI_API_KEY=YOUR_API_KEY_HERE
```

## 雲端圖生（Hugging Face Inference API，預設優先）

**預設會先用雲端**生成圖片（Hugging Face Inference API，例如 nscale），無需下載 5GB 本機 SDXL；失敗再 fallback 本機 SDXL 或佔位圖。

1. 在 [Hugging Face](https://huggingface.co/settings/tokens) 建立 Access Token（Read 權限即可）。
2. 在 `.env` 加上：
   ```env
   HF_TOKEN=hf_你的token
   ```
3. 重啟 app 後即會優先使用雲端 SDXL。若想改回本機優先，可設 `DESIGNBRIDGE_ENABLE_HF_INFERENCE=false`。

## 測試工作流（CLI）

```bash
python scripts/run_designbridge.py
```

若 console 出現：
- ✅ 正常輸出結構化 JSON：Gemini 解析成功
- ⚠️ `falling back to rule-based`：API key 未設或呼叫失敗，已退回規則解析

## 專案結構

```
DesignBridge/
├── app.py                  # Streamlit UI
├── designbridge/           # LangGraph graph/nodes/config
├── scripts/
│   └── run_designbridge.py # CLI 測試入口
├── docs/                   # 規格與文件
└── artifacts/              # 產出（depth/seg/render）
```

## 參考文件

- `docs/DesignBridge.md`：工作流與 State 定義
- `docs/SCHEMAS.md`：各 Agent 的輸入/輸出 JSON 規格

## 根目錄需創建env, env格式
GEMINI_API_KEY=************
HF_TOKEN=************

自行更換Token，如果爆掉可以再用其他google帳號申請免費Token