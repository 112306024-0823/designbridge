# DesignBridge FastAPI 後端
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os
import time
import shutil
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 匯入設計引擎
from designbridge import get_compiled_graph
from designbridge.style_apply import list_available_style_profiles
from style_kb.styles import STYLES

app = FastAPI(title="DesignBridge API", description="室內設計 AI 工作流接口")

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
    style_profile_id: Optional[str] = None
    initial_image_path: Optional[str] = None
    style_reference_image_path: Optional[str] = None

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
        _embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
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

@app.get("/api/style-preview")
def get_style_preview(query: str = "", style_id: str = ""):
    """根據文字語意搜尋最符合的風格參考圖（Supabase pgvector），供前端即時預覽。"""
    sid = style_id.strip() or ""
    q = query.strip() or sid or "interior design"
    try:
        model = _get_embedding_model()
        embedding = model.encode(q, normalize_embeddings=True).tolist()
        client = _get_supabase()
        res = client.rpc("query_style_preview", {
            "query_embedding": embedding,
            "filter_style_id": sid,
        }).execute()
        if not res.data:
            return {"image_url": None}
        row = res.data[0]
        style_name = (row.get("source_meta") or {}).get("style", row["style_id"])
        return {
            "image_url": row["image_url"],
            "style_name": style_name,
            "similarity": round(row["similarity"], 4),
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
        }
        if request.style_profile_id and request.style_profile_id != "auto":
            user_input["style_profile_id"] = request.style_profile_id
        if request.initial_image_path:
            user_input["initial_image"] = request.initial_image_path
        if request.style_reference_image_path:
            user_input["style_reference_image"] = request.style_reference_image_path

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


        # 回傳結果（過濾掉不必要的內部狀態，只給前端需要的）
        return {
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
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))