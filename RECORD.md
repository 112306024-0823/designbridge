# DesignBridge 待辦紀錄

> 本次對話（2026-08-29）整理，供之後接續處理。

## 進行中：Style Prompt 房間類型洩漏問題

**問題**：風格搜尋比對到的參考圖跟使用者實際要的房間類型不同時（例如使用者要臥室，比對到客廳圖），
`style_kb.ai_params.prompts.positive`（KB 生成的風格提示詞）裡常直接寫死房間類型/家具類別詞
（"living room", "sofa", "TV console", "dining table"...），被注入到最終生成 prompt 後跟 RA 的
`design_description`（已經正確描述臥室內容）互相矛盾，導致生成結果混雜錯誤房間的家具。

**根因鏈**：
- `designbridge/style/style_apply.py` → `build_style_params()` 只用 `text_query` + `style_id` 查詢，
  從未把 `req.meta.room_type` 傳入
- Supabase RPC `query_style_kb`（`style_kb_embedding` 向量查詢）本身也沒有 `space` 過濾參數
- `style_images.space` 欄位存在（CHECK 限定客廳/臥室/廚房/浴室/餐廳/書房/走道/玄關/陽台/辦公室/其他），
  但只有 641/3094（20.7%）填值，且從未被查詢邏輯使用過
- 更根本：`style_kb.ai_params.prompts.positive` 本身在**生成時**就沒被限制不能提房間/家具類別詞
  （`style_kb/extraction/prompts_style_kb.py` 的 `STYLE_KB_PROMPT`）
- `renderer.py`：Supabase KB 比對到的圖片實際上**沒有**被當作視覺 ControlNet/IP-Adapter 輸入
  （只有 `user_style_reference_local` 走 ipadapter/redux），所以洩漏管道確定是**純文字**，不是圖片視覺

**已決定的修法（方案 B：修源頭 + 全部重新生成，不留運行時黑名單）**：
1. ✅ 已改 `style_kb/extraction/prompts_style_kb.py` 的 `STYLE_KB_PROMPT`：
   明確要求 positive/negative prompt 不要提房間類型或具體家具類別名詞，只描述材質/造型/色調/光影/氛圍
2. ✅ 已改 `style_kb/extraction/fill_style_kb_from_supabase.py` 的 `fetch_null_rows()`：
   加 `force_rewrite` 參數，`True` 時連已有 `style_kb` 的行也重新查詢（目前只加了函式參數，
   **`main()` 的 CLI 還沒接上 `--force-rewrite` flag，也還沒實際串進 `fetch_null_rows` 呼叫處**）
3. ✅ 已完成，且改採更乾淨的路線——不是覆蓋舊的 `style_kb`，而是：
   - 新增 Supabase 欄位 `public.style_images.style_kb_2`（jsonb，migration: `add_style_kb_2_column`）
   - `fill_style_kb_from_supabase.py` 改成寫入 `style_kb_2`（`TARGET_COLUMN` 常數），
     舊的 `style_kb` 保持不動，方便新舊資料互相比對
   - `main()` 已加 `--force-rewrite` CLI 參數並串接到 `fetch_null_rows(force_rewrite=...)`
4. ✅ 已決定不留運行時黑名單，`designbridge/style/style_supabase.py` 裡的
   `_ROOM_FURNITURE_BLACKLIST` / `_strip_room_furniture_terms()` 已整段移除
   （改走「重新生成乾淨資料」，不需要 runtime 過濾）
5. ✅ 已改用 Vertex AI（`fill_style_kb_from_supabase.py` 的 `get_gemini()`/`extract_style_kb()`
   改用 `google.genai.Client(vertexai=True, project=..., location=...)`，讀 `.env` 既有的
   `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION`，走 GCP 專案配額不受 AI Studio 免費 key
   15 req/min 限制，限速從 4s 降到 0.5s）。**⚠️ 尚未實際執行**——需要本機先跑過
   `gcloud auth application-default login`（或設定 `GOOGLE_APPLICATION_CREDENTIALS`），
   跑法：`python -m style_kb.extraction.fill_style_kb_from_supabase`（預設只處理
   `style_kb_2 IS NULL` 的行，也就是全部 3,094 筆，因為這是全新欄位）
   - ✅ 已執行完成：3087 筆全跑過，人工挑掉 13 筆品質不合格的直接從 Supabase 刪除，
     剩 3074 筆 `style_kb_2` 100% 覆蓋
   - ✅ 已決定：查詢邏輯（`style_supabase.py`）改讀 `style_kb_2`（`_pick_style_kb()` 現在直接讀
     `style_kb_2`，`_batch_load_style_kb` / 查詢 SELECT / fallback 排序三處都已切換）
   - ✅ 已執行完成：`embed_style_kb_supabase.py --reset` 跑完，`style_kb_embedding` 3074/3074
     全部補齊（改用 `style_kb_2` 的 `description.zh` + `tags.zh` 重算）。過程中發現腳本沒做
     `.range()` 分頁，PostgREST 單次查詢上限 1000 筆導致第一次只處理到 1000 筆，已修好分頁
     （跟 `fetch_null_rows()` 同一套模式）後補跑剩下的 1810 筆
   - ✅ **已刪除舊欄位** `style_kb`（migration: `drop_legacy_style_kb_column`）。刪除前清過
     所有還在引用它的程式碼：`api.py`（`/api/style-search`，順便修正 description 現在是
     `{"zh","en"}` 巢狀格式，不是純字串）、`style_supabase.py`（`_pick_style_kb` 拿掉
     fallback、兩處 SELECT 拿掉 `style_kb`）、`embed_style_kb_supabase.py`（SELECT 拿掉）、
     `upload_to_supabase.py`（insert 拿掉這個 key，新圖片改讓 `style_kb_2` 自然是 NULL）、
     `fill_style_kb_from_batch_json.py`（改寫 `style_kb_2`，這支是備用批次流程，跟主要的
     `fill_style_kb_from_supabase.py` 不同支，尚未補上這次對話新增的 space_info/quality_review/
     lora_caption 等欄位，之後若要用需要同步更新）
6. ⬜ （可選，加分項）Supabase RPC `query_style_kb` 加 `filter_space` 參數，
   依 `req.meta.room_type` 做軟性優先排序（非硬性過濾，因 `space` 欄位填充率僅 20.7%）——
   讓一開始就少比對到跨房間類型的參考圖，跟上面的文字清理互補
7. ✅ 已簡化 `style_supabase.py` 的 `_compose_style_kb_text()`（embedding 用文字組裝函式）
   —— 原本拼接 7 個來源（style_info.name+tags / description / materials / lighting /
   ai_params.positive / source_meta / style_id），中英文混雜在同一段拿去 embed。
   **改成只用 `description.zh` + `tags.zh`**：
   - 兩者都是純中文，不會有「中英文混雜稀釋 embedding 語意」的問題
   - `description` 本身已經是 Gemini 統整過的風格氛圍/配色/空間感受摘要，訊號夠濃縮
   - 大幅簡化程式碼，少掉很多 null-fallback 分支
   - 權衡：會失去材質細節關鍵字的搜尋召回力（例如使用者搜「大理石」，若 description
     剛好沒提到材質字眼，比現在的組合版稍微搜不到）

## 進行中：新增 space_info（room_type + 坪數級距），順便回填 space 欄位

- ✅ `STYLE_KB_PROMPT` 新增 `space_info: {room_type, estimated_size_tier}`：
  - `room_type` 對齊資料庫 `space` 欄位既有的 11 個 CHECK 值（客廳/臥室/廚房/浴室/餐廳/書房/
    走道/玄關/陽台/辦公室/其他），沒把握選「其他」
  - `estimated_size_tier`：小坪數/中坪數/大坪數三級距（不要求 Gemini 硬猜精確坪數，單張照片
    估不準，寧可用粗略級距）
  - `style_info.tags` 也順便改成雙語 `{"zh": [...], "en": [...]}`（呼應 description 的雙語化）
- ✅ `fill_style_kb_from_supabase.py`：
  - `fetch_null_rows` 多 select 現有 `space` 欄位值
  - `update_style_kb` 加 `space_value` 參數，寫入時**只在該行 `space` 目前是 NULL 才回填**，
    不覆蓋既有值（保守處理，尊重已存在的資料）
  - `process_rows` 從 `style_kb.space_info.room_type` 取值，用 `_VALID_SPACE_VALUES` 驗證合法
    才回填，log 會印出 `space→客廳` 這種提示
- 這件事直接呼應前面發現的「`space` 欄位只有 20.7% 填值、且從未被查詢邏輯使用」的問題——
  跑完這次 style_kb_2 全批次後，`space` 欄位覆蓋率應該會大幅提升，讓 RECORD.md 上面那條
  「Supabase RPC `query_style_kb` 加 `filter_space` 軟性排序」的加分項變得更值得做
  （之前資料太稀疏，做了效果有限；現在資料補齊後才是真的划算的時機）。

## 進行中：description 加英文版（為未來英文版 UI 準備）

- ✅ 已改 `STYLE_KB_PROMPT`：`description` 欄位從純字串改成 `{"zh": "...", "en": "..."}`，
  兩版語意一致但各自道地表達，不是逐字翻譯。`en` 純粹給未來英文 UI 顯示用，跟步驟 3 的
  `ai_params.prompts.positive/negative`（生圖用英文 prompt）是不同用途、不要混用。
- ✅ 已補充：`description`（zh/en 都）明確要求可以、也應該提到空間類型/房間類型（例如
  「這是一間客廳」）——因為這欄位純粹給使用者閱讀、不會被注入生圖 prompt，跟步驟 3
  的 positive/negative 不同，沒有洩漏風險，反而應該讓使用者知道這筆資料原本是哪個空間。
- ✅ 已切換：`designbridge/style/style_supabase.py` 改讀 `style_kb_2`，`_compose_style_kb_text()`
  和 `blend_style_params_supabase()` 裡 `description` 都改成取 `.get("zh")`（沿用中文版，
  embedding 跟現有 UI 顯示邏輯不變，`en` 版先存著，等真的做英文 UI 再接他)。

## 進行中：429 自動重試

- 實測 workers=6 跟更高的值都持續遇到大量 429（14/30、14/30 兩次），workers=3 大幅改善（1/30）
  但仍有殘留失敗，代表配額會浮動，光調 workers 數字不夠穩定
- ✅ `extract_style_kb()` 加指數退避重試（1/2/4/8/16s + 隨機抖動，最多 5 次），429 視為暫時性、
  不計費（沒真的跑到推論），失敗就等一下重試，不再直接判定整行失敗
- 有了重試機制後 workers 可以放心調高（例如 8~10），429 只會拖慢那幾行、不會讓它們真的失敗

## 進行中：AI 建議正確風格分類（suggested_styles）

- ✅ `STYLE_KB_PROMPT` 的 `quality_review` 加 `suggested_styles`：不論信心分數高低，都從固定
  9 種風格（跟審核頁 `STYLE_OPT` 下拉選單一致，排除沒有實際資料的 `neoclassic`）排序推薦最多 3 個
- ✅ `fill_style_kb_from_supabase.py`：合法性過濾（只保留在 `_VALID_STYLE_IDS` 裡的），
  存進 `quality_flags.suggested_styles`
- ✅ 審核頁（`generate_review.py`）：展開卡片後「AI 風格」下拉選單下面多一排「AI 建議」小按鈕，
  點一下直接套用到下拉選單（不用手動找），目前選中的那個會反白標示

## 進行中：合併 LoRA caption 生成進同一次 Gemini 呼叫

- 一開始建議分開跑（避免同一次呼叫裡兩組相反指令互相污染），後來重新考慮：這份 prompt裡本來就已經有
  「同一次呼叫兩個欄位要求相反」的先例（步驟 3 不准提房間類型 vs 步驟 5 一定要提房間類型），架構上
  不是新風險，加上省下重複下載圖片+重複付一次圖片 input token 的成本，決定合併。
- ✅ `STYLE_KB_PROMPT` 新增步驟「LoRA 訓練用 caption（lora_caption）」，規則完全比照
  `generate_captions_supabase.py` 的 `CAPTION_PROMPT`（只能講房間類型/家具/位置/鏡位，
  絕對不能提材質/色調/氛圍/風格名稱）
- ✅ `fill_style_kb_from_supabase.py`：`lora_caption` 只在該行 `caption_en2` 目前是 NULL 才回填
  （沿用同一套保守回填模式），log 會標記 `caption✓`
- ⚠️ **未驗證的風險**：caption 要求「完全不提材質/色調」，但同一次輸出的 `ai_params.prompts.positive`
  就在旁邊大量描述材質色調，位置接近，理論上比房間類型那組更容易被「帶偏」污染，目前沒有實測資料
  支持或反駁這個猜測。
- ⬜ **待做**：先跑小批次（例如 `--limit 10`），人工檢查 `lora_caption` 有沒有意外混入材質/色調/
  風格詞，確認品質可接受後才擴大到全部 3,094 筆。

## 進行中：AI 順便判斷圖片是否適合當參考圖（近景 / 風格不符）

- **找到既有的審核前端，還在**：[style_kb/collection/review_server.py](style_kb/collection/review_server.py) +
  [generate_review.py](style_kb/collection/generate_review.py) —— 本地 HTTP server，從 Supabase 拉
  `quality_score`/`quality_flags`/`ai_style_confidence`/`space` 等欄位生成審核網頁，人工勾選要刪除的圖，
  複製 ID 給 `purge_rejected.py` 執行刪除。目前 `ai_style_confidence` 100% 是 null，`quality_flags`
  現有內容是純技術性 CV 檢測（blur/laplacian/解析度/長寬比，跟語意判斷是分開的兩件事）。
- ✅ `STYLE_KB_PROMPT` 新增 `quality_review: {is_closeup, style_match_confidence, style_mismatch_reason}`：
  判斷是否為近景特寫、是否真的符合指定風格分類，不符合就給低分+一句話原因
- ✅ `fill_style_kb_from_supabase.py`：
  - `ai_style_confidence` 只在目前是 NULL 才回填（來自 `style_match_confidence`）
  - `quality_flags` 用合併方式寫入新的 `is_closeup`（+ 可選的 `style_mismatch_reason`），
    保留既有的 blur/laplacian 等技術性欄位不被覆蓋
  - log 會標記疑似不適合的圖（`⚠️ 疑似不適合當參考圖`），方便事後篩選
- ✅ 已查完並修好 `generate_review.py` 的顯示邏輯：
  - `ai_style_confidence` 本來就有畫面（展開卡片「AI 風格」列的百分比），但原本 `hasAI` 只認
    `caption_model`（另一支舊 caption 腳本寫的欄位），跟我們新腳本無關——**已改成
    `caption_model` 或 `ai_style_confidence` 任一有值都顯示 AI 面板**
  - `is_closeup` 原本不在 `FLAG_LABELS` 會被後端濾掉——**已加入**，會自動顯示成黃色
    「近景特寫」篩選按鈕/卡片徽章
  - `style_mismatch_reason` 原本沒有顯示位置——**已接成滑鼠移到信心分數上的 tooltip**
  - 順便修掉一個既有小落差：JS `SPACE_OPT` 只有 9 個空間選項，補上遺漏的「玄關」「辦公室」
    （資料庫 CHECK 限制共 11 個）

## 其他待辦（本次對話發現，尚未動工）

- **R2 鏡像圖片網址故障範圍比預期廣**：`american/` 整個資料夾 15/15 全 404，20 筆隨機抽樣另外
  抓到 `japanese/` 也有 2 筆 404（R2 整體抽樣 16/20 成功 = 80%）。已確認 `source_meta.url`
  （原始來源網站 100.com.tw）20/20 全部成功，比 R2 更可靠。
  ✅ **已處理**：`fill_style_kb_from_supabase.py` 下載順序已對調，優先用 `source_meta.url`，
  R2 (`image_url`) 當備援（兩者都有值，3094/3094 筆都有 `source_meta.url`）。
  ⬜ 待查（非阻塞）：R2 bucket 實際故障範圍多大（只測了 american 全部 + 20 筆隨機抽樣，
  沒有逐一測過全部 3,094 筆），要不要之後修復 R2 本身（不影響現在能不能跑 style_kb_2 萃取，
  因為已經有 source_meta.url 這個更可靠的來源）。
- **一筆資料 `style_id` 跟 R2 資料夾路徑不一致**：抽樣時發現一筆 `style_id='modern'` 但
  `image_url` 路徑是 `.../japanese/api_1859484_1682050149_...`，`style_id` 標籤跟實際存放
  資料夾對不上，待查是否為個案或系統性問題（例如某次重新分類時只改了 DB 欄位沒搬檔案）。

- **CLIP 評分自動重試迴圈沒接線**：`designbridge/core/graph.py` 的 `clip_evaluator` → `END` 是無條件邊，
  但 `EvalFeedbackJSON.decision`（`Literal["continue","stop"]`）已經算好分數卻沒人讀。
  要加 conditional edge：分數不夠（`"continue"`）繞回 `renderer` 重跑，`"stop"` 才放行到 END。
- **RA（Requirement Analyzer）微調**（`designbridge/core/nodes/requirement.py`）：
  - 手動剝字串解析 JSON 很脆弱，改用 Gemini `response_mime_type="application/json"` / `response_schema`
  - LLM 呼叫失敗時靜默套用寫死預設值，前端完全不知道，建議把失敗狀態塞進 `intermediate_outputs`
  - `REQUIREMENT_ANALYZER_PROMPT` 目前零 few-shot 範例，建議加 5~10 個邊界案例
    （尤其 `hint_layout` vs `hint_style` 判斷、`routing_decision` 邊界情況）
  - （RA 多輪澄清機制是更大的既定計畫，見 memory：`ra_clarification_planned.md`，尚未開始）
- **quotation_agent 跟 layout 的 scene_graph 脫鉤**：`quotation_agent` 不讀 layout 規劃出的
  `furniture_placements`，是拿生成完的圖重新用 `detect_furniture_gemini()` 偵測，兩邊清單可能對不上。
- **segmentation 死重**：`renderer.py` 裡組出的 `controlnet_inputs["segmentation"]` 從沒被任何
  render backend 讀取，是純 metadata；若走純生圖（非 `design_adjuster` 局部編輯）路徑，
  這段 UPerNet segmentation（~6.75s）是白算的，可考慮跳過。
- **legacy 死檔案**：`style_kb/extract_style_kb.py`（不在 `extraction/` 底下那支）是重構後遺留的舊版，
  引用已不存在的模組路徑，可直接刪除。
- **`caption_en` vs `caption_en2` 欄位命名疑似不一致**：`generate_captions_supabase.py` 的 docstring/
  註解都寫「生成 caption_en」，但實際 `update_caption()` 寫入的是 `caption_en2` 欄位；
  `caption_en`（393 筆）疑似是另一支本地腳本 `style_kb/collection/generate_captions.py` 產生的，
  兩者是否為同一用途要確認清楚，避免之後搞混。

## 已完成（本次對話）

- ✅ 修正投影深度圖跟生圖畫布長寬比不一致的問題（`layout_and_style.py` / `layout_agent.py` /
  `scene_graph_to_depth.py`：`_generate_projected_depth` 現在會接收並使用正確的 `output_size`）
- ✅ 投影深度圖邊緣加 `GaussianBlur(radius=3)` 軟化硬邊，緩解 ControlNet 疊影/半透明瑕疵
- ✅ 確認 Supabase `sufrsiwuieyspywvacpp`（DesignBridge 專案）連線與現況：
  `style_images`（3,094 筆）、`ikea_products`（380 筆）

## 系統擴充構想清單（非緊急，供之後排優先序）

帳號＋雲端設計紀錄（Supabase Auth）、對話式多輪修改、3D/AR 匯出、預算感知報價、
一次生成多版本讓使用者選、無障礙需求報告書、報價接真實電商購買連結、
`design_adjuster` 支援多點同時編輯、前後對比滑桿、一鍵匯出設計提案 PDF。
