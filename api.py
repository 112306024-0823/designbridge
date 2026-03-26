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

# 匯入設計引擎
from designbridge import get_compiled_graph
from designbridge.style_apply import list_available_style_profiles
from style_kb.styles import STYLES

app = FastAPI(title="DesignBridge API", description="室內設計 AI 工作流接口")

artifacts_dir = Path("artifacts")
artifacts_dir.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(artifacts_dir)), name="artifacts")

# 解決前後端跨域問題
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
        raise HTTPException(status_code=500, detail=str(e))