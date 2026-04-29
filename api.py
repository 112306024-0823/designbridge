# DesignBridge FastAPI 後端
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import os
import time
import shutil
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import json
import threading

_history_lock = threading.Lock()
_history_file = Path(__file__).parent / "artifacts" / "history.json"

def _save_history(record: dict) -> None:
    """Append a generation record to artifacts/history.json (thread-safe)."""
    with _history_lock:
        if _history_file.exists():
            try:
                history = json.loads(_history_file.read_text(encoding="utf-8"))
            except Exception:
                history = []
        else:
            history = []
        history.append(record)
        _history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

# 匯入設計引擎
from designbridge import get_compiled_graph
from designbridge.style_apply import list_available_style_profiles
from style_kb.styles import STYLES

app = FastAPI(title="DesignBridge API", description="室內設計 AI 工作流接口")

artifacts_dir = Path("artifacts")
artifacts_dir.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(artifacts_dir)), name="artifacts")

artifacts_dir = Path("artifacts")
artifacts_dir.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(artifacts_dir)), name="artifacts")

style_images_dir = Path("style_kb/images")
if style_images_dir.exists():
    app.mount("/style-images", StaticFiles(directory=str(style_images_dir)), name="style-images")

# 解決前後端跨域問題 (具備彈性與擴充性的解法)
cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,             # 讀取 .env 中的自訂網域 (適合正式上線環境)
    allow_origin_regex=r"^https?://localhost:\d+$", # 允許所有 localhost 的開發埠號 (適合開發環境，不用再一直加 5174, 5175...)
    allow_methods=["*"],
    allow_headers=["*"],
)


# 1. 定義請求資料格式 (Pydantic Model)
class DesignRequest(BaseModel):
    text_prompt: str = ""
    edit_scope: float = 0.6
    model_type: str = "sdxl"
    output_aspect: str = "auto"
    style_profile_id: Optional[str] = None
    style_retrieval_mode: Optional[str] = None 
    initial_image_path: Optional[str] = None
    style_reference_image_path: Optional[str] = None
    no_style_reference: bool = False

# 2. 快取 Graph 實例
graph = get_compiled_graph()


@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """接收前端上傳的圖片，儲存到 artifacts/uploads/ 並回傳本機路徑。"""
    upload_dir = Path("artifacts/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix if file.filename else ".png"
    dest = upload_dir / f"{uuid.uuid4()}{suffix}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"path": str(dest)}

_embedding_model = None
_supabase_client = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("clip-ViT-B-32")
    return _embedding_model

def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _supabase_client

@app.get("/api/style-search")
def search_styles(
    query: str = "",
    style_id: str = "",
    top_k: int = 3,
    retrieval_mode: str = "text-to-image",
):
    """向量搜尋最相似的風格參考圖，回傳多筆候選供使用者選擇。"""
    from designbridge.style_supabase import _STYLE_PROMPTS
    from style_kb.styles import STYLES
    style_name_map = {sid: sname for sid, sname in STYLES}

    sid = style_id.strip() or ""
    q = query.strip() or sid or "interior design"
    try:
        from designbridge.style_supabase import query_style_images_supabase

        client = _get_supabase()
        results = query_style_images_supabase(
            text_query=q,
            style_id=sid or None,
            top_k=min(top_k, 6),
            retrieval_mode=retrieval_mode,
        )
        if not results:
            return []

        # 批次取 style_kb（兩筆查詢，不用 N+1）
        image_urls = [r.image_url for r in results]
        kb_res = client.table("style_images").select("image_url,style_kb").in_("image_url", image_urls).execute()
        kb_map = {r["image_url"]: r.get("style_kb") for r in (kb_res.data or [])}

        candidates = []
        for row in results:
            url = row.image_url
            s_id = row.style_id
            style_kb = kb_map.get(url)
            fallback = _STYLE_PROMPTS.get(s_id, _STYLE_PROMPTS.get("modern", {}))

            description = None
            positive_prompt = fallback.get("positive", "")
            negative_prompt = fallback.get("negative", "")

            if style_kb and isinstance(style_kb, dict):
                description = style_kb.get("description")
                ai = style_kb.get("ai_params") or {}
                prompts = ai.get("prompts") or {}
                positive_prompt = prompts.get("positive") or positive_prompt
                negative_prompt = prompts.get("negative") or negative_prompt

            source_meta = {}
            candidates.append({
                "style_id": s_id,
                "style_name": style_name_map.get(s_id, source_meta.get("style", s_id)),
                "image_url": url,
                "similarity": round(float(row.similarity), 4),
                "description": description,
                "positive_prompt": positive_prompt,
                "negative_prompt": negative_prompt,
            })
        return candidates
    except Exception as e:
        print(f"⚠️ style-search error: {e}")
        return []


@app.get("/api/style-preview")
def get_style_preview(
    query: str = "",
    style_id: str = "",
    retrieval_mode: str = "text-to-image",
):
    """根據文字語意搜尋最符合的風格參考圖（Supabase pgvector），供前端即時預覽。"""
    sid = style_id.strip() or ""
    q = query.strip() or sid or "interior design"
    try:
        from designbridge.style_supabase import query_style_images_supabase

        results = query_style_images_supabase(
            text_query=q,
            style_id=sid or None,
            top_k=1,
            retrieval_mode=retrieval_mode,
        )
        if not results:
            return {"image_url": None}
        row = results[0]
        style_name = row.style_name or row.style_id
        return {
            "image_url": row.image_url,
            "style_name": style_name,
            "similarity": round(row.similarity, 4),
        }
    except Exception as e:
        print(f"⚠️ style-preview error: {e}")
        return {"image_url": None}


@app.get("/")
def read_root():
    return {"message": "DesignBridge API is running"}



@app.get("/api/style-profiles")
def get_style_profiles():
    # 優先回傳磁碟上已有聚合檔的風格
    available = list_available_style_profiles()
    if available:
        return [{"style_id": s["style_id"], "style_name": s["style_name"]} for s in available]
    # fallback：回傳 STYLES 定義的完整清單
    return [{"style_id": sid, "style_name": sname} for sid, sname in STYLES]

# ── Chat (LiteLLM) ───────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str          # "user" | "assistant" | "system"
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None        # 留空則用 Config.LITELLM_MODEL
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """通用 LLM chat endpoint，透過 LiteLLM 支援任意模型。

    - stream=false（預設）：回傳 { "content": "..." }
    - stream=true：Server-Sent Events，每個 chunk 為 data: <text>\\n\\n
    """
    from designbridge.llm import call_llm, call_llm_stream
    from designbridge.config import Config

    history = [{"role": m.role, "content": m.content} for m in request.messages[:-1]]
    last = request.messages[-1]

    kwargs = dict(
        model=request.model or Config.LITELLM_MODEL,
        history=history or None,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )

    if request.stream:
        def _sse_generator():
            for chunk in call_llm_stream(last.content, **kwargs):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_sse_generator(), media_type="text/event-stream")

    try:
        content = call_llm(last.content, **kwargs)
        return {"content": content, "model": request.model or Config.LITELLM_MODEL}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 3. 建立 POST 路由
@app.post("/api/generate")
async def generate_design(request: DesignRequest):
    try:
        # 設定環境變數（對應你原本的邏輯）
        os.environ["DESIGNBRIDGE_LOCAL_MODEL_TYPE"] = request.model_type
        
        # 準備 LangGraph 初始狀態
        user_input = {
            "text_prompt": request.text_prompt,
            "edit_scope": request.edit_scope,
            "output_aspect": request.output_aspect,
        }
        if request.style_profile_id and request.style_profile_id != "auto":
            user_input["style_profile_id"] = request.style_profile_id
        if request.style_retrieval_mode:
            user_input["style_retrieval_mode"] = request.style_retrieval_mode
        if request.initial_image_path:
            user_input["initial_image"] = request.initial_image_path
        if request.style_reference_image_path:
            user_input["style_reference_image"] = request.style_reference_image_path
        if request.no_style_reference:
            user_input["no_style_reference"] = True

        initial_state = {"user_input": user_input}

        # 執行工作流
        t0 = time.perf_counter()
        result = graph.invoke(initial_state)
        elapsed = time.perf_counter() - t0
        generated_image_path = result.get("generated_image")
        generated_image_url = None
        if isinstance(generated_image_path, str):
            normalized = generated_image_path.replace("\\", "/")
            if normalized.startswith("artifacts/"):
                generated_image_url = f"http://localhost:8000/{normalized}"


        response = {
            "status": "success",
            "elapsed_time": f"{elapsed:.2f}s",
            "routing_decision": result.get("routing_decision"),
            "generated_image_path": generated_image_path,
            "generated_image_url": generated_image_url,
            "structured_requirement": result.get("structured_requirement"),
            "task_id": result.get("task_id"),
            "iteration": result.get("iteration"),
            "render_result": result.get("render_result"),
            "vision_features": result.get("vision_features"),
            "intermediate_outputs": result.get("intermediate_outputs"),
            "style_params": result.get("style_params"),
            "evaluation_result": result.get("evaluation_result"),
        }

        # 儲存生成紀錄
        _save_history({
            "task_id": result.get("task_id"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "elapsed_seconds": round(elapsed, 2),
            "text_prompt": request.text_prompt,
            "model_type": request.model_type,
            "style_profile_id": request.style_profile_id,
            "style_reference_image_path": request.style_reference_image_path,
            "routing_decision": result.get("routing_decision"),
            "generated_image_path": generated_image_path,
            "generated_image_url": generated_image_url,
            "style_params": result.get("style_params"),
        })

        return response

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))