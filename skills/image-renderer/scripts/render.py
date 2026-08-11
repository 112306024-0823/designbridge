"""
Image Renderer skill script.
讀取 stdin JSON → 生成室內設計圖 → 輸出 generated_image 路徑到 stdout。

原始邏輯位於：designbridge/core/nodes/renderer.py::renderer
"""
import json
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root))

from designbridge.core.config import Config
from designbridge.render.render_prompt import (
    _build_imagen_prompt_from_requirement,
    _renderer_placeholder_image,
)
from designbridge.render.render_backends import (
    _render_hf_inference,
    _render_flux,
)


def main():
    data = json.load(sys.stdin)

    # Adjuster 已生成圖片時，renderer 跳過
    if data.get("routing_decision") == "design_adjuster" and data.get("generated_image"):
        print(json.dumps({}))
        return

    task_id = data.get("task_id") or str(uuid.uuid4())
    req = data.get("structured_requirement") or {}
    style_params = data.get("style_params") or {}

    out_path = Path(Config.ARTIFACTS_DIR) / "render" / f"{task_id}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = _build_imagen_prompt_from_requirement(req, style_params=style_params)
    negative_prompt = style_params.get("negative_prompt") or None

    hf_model_id = Config.FLUX_MODEL

    backend = "placeholder"
    generation_params = {
        "prompt_preview": prompt[:200],
        "negative_prompt_preview": (negative_prompt or "")[:200],
    }
    if style_params:
        generation_params["style_profile_id"] = style_params.get("style_profile_id")
        generation_params["style_profile_name"] = style_params.get("style_profile_name")
        generation_params["style_strength"] = style_params.get("style_strength")

    if Config.ENABLE_HF_INFERENCE and Config.HF_TOKEN:
        if _render_hf_inference(prompt, out_path, model=hf_model_id):
            backend = "hf_inference"
            generation_params["model"] = hf_model_id
            generation_params["provider"] = Config.HF_INFERENCE_PROVIDER

    if backend == "placeholder" and Config.ENABLE_FLUX_FALLBACK:
        if _render_flux(prompt, out_path):
            backend = "flux"
            generation_params["model"] = hf_model_id

    if backend == "placeholder":
        _renderer_placeholder_image(out_path, task_id, prompt)
        generation_params["fallback"] = "placeholder"

    generation_params["backend"] = backend

    result = {
        "generated_image": str(out_path),
        "render_result": {
            "generated_image_path": str(out_path),
            "generation_params": generation_params,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
