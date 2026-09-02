"""Renderer graph node."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from designbridge.core.config import Config
from designbridge.core.state import DesignBridgeState
from designbridge.core.timing import timed_call
from designbridge.render.render_prompt import (
    _analyze_style_image_with_gemini,
    _build_imagen_prompt_from_requirement,
    _resolve_output_size,
)
from designbridge.render.render_backends import (
    _render_hf_inference,
    _render_hf_kontext,
    _render_flux_kontext_fal,
    _render_flux_controlnet_depth_fal,
    _render_flux_redux_fal,
    _render_flux_redux_local,
    _render_flux_ipadapter_fal,
    _render_flux_fal,
    _render_flux,
)

_BASE_NEGATIVE_PROMPT = (
    "people, person, human, man, woman, child, hands, face, "
    "animal, pet, cat, dog, bird, "
    "text, watermark, signature, logo"
)


def renderer(state: DesignBridgeState) -> dict[str, Any]:
    """
    Renderer: generate image from structured_requirement using Flux.
    Falls back to placeholder on failure.
    若 routing_decision 為 design_adjuster 且已有 generated_image，直接跳過不覆蓋。
    """
    # Adjuster 已產出 inpainted 圖片，renderer 不再重新生成
    if state.get("routing_decision") == "design_adjuster" and state.get("generated_image"):
        return {}

    task_id = state.get("task_id") or str(uuid.uuid4())
    req = state.get("structured_requirement") or {}
    style_params = state.get("style_params") or {}
    artifacts_root = Path(Config.ARTIFACTS_DIR)
    render_dir = artifacts_root / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    # 加入隨機短碼，確保每次生成都是獨立新檔案（避免 task_id 相同時回傳舊圖）
    render_suffix = uuid.uuid4().hex[:8]
    out_path = render_dir / f"{task_id}_{render_suffix}.png"

    prompt = _build_imagen_prompt_from_requirement(req, style_params=style_params)

    # 只有使用者明確要求重新規劃佈局時，才把 layout 結果注入 prompt
    if req.get("hint_layout"):
        scene_graph = state.get("scene_graph") or {}
        layout_prompt = (scene_graph.get("layout_prompt") or "").strip()

        if not layout_prompt:
            layout_from_depth = state.get("layout_from_depth") or {}
            if layout_from_depth:
                from designbridge.render.render_prompt import _layout_json_to_prompt_text
                layout_prompt = _layout_json_to_prompt_text(layout_from_depth)

        if layout_prompt:
            prompt = f"{prompt} {layout_prompt}"
            print(f"[renderer] layout_prompt injected: {layout_prompt[:80]}")

    _style_neg = (style_params.get("negative_prompt") or "").strip(", ")
    negative_prompt = f"{_BASE_NEGATIVE_PROMPT}, {_style_neg}" if _style_neg else _BASE_NEGATIVE_PROMPT
    _special = req.get("special_constraints") or {}
    if _special.get("wheelchair"):
        negative_prompt = f"{negative_prompt}, wheelchair, wheelchair user, mobility aid, disability equipment"
    if _special.get("children"):
        negative_prompt = f"{negative_prompt}, child, children, baby, toddler, kid"
    if _special.get("pets"):
        negative_prompt = f"{negative_prompt}, cat, dog, bird, rabbit, hamster, pet, animal"
    user_input = state.get("user_input") or {}

    vision = state.get("vision_features") or {}
    output_aspect = str(user_input.get("output_aspect") or "auto")
    output_size = _resolve_output_size(output_aspect, user_input.get("initial_image"))
    output_width, output_height = output_size
    generation_params: dict[str, Any] = {
        # 完整 prompt（不截斷）：testing 用，前端結構化需求卡片會顯示這份
        "prompt_preview": prompt,
        "negative_prompt_preview": negative_prompt or "",
        "output_aspect": output_aspect,
        "output_size": {"width": output_width, "height": output_height},
    }
    backend = "placeholder"

    if style_params:
        generation_params["style_profile_id"] = style_params.get("style_profile_id")
        generation_params["style_profile_name"] = style_params.get("style_profile_name")
        generation_params["style_strength"] = style_params.get("style_strength")

    # Get vision features for ControlNet (if available)
    depth_path = vision.get("depth")
    seg_path = vision.get("segmentation")

    # When the user re-plans layout, the input-photo depth no longer matches the new
    # furniture arrangement. Override it with the depth projected from the scene-graph
    # coordinates so the Layout Agent's precise placements actually control the render.
    using_projected_depth = False
    if req.get("hint_layout") and Config.ENABLE_LAYOUT_DEPTH_PROJECTION:
        _sg = state.get("scene_graph") or {}
        _proj_depth = _sg.get("projected_depth_path")
        if _proj_depth and Path(_proj_depth).exists():
            depth_path = _proj_depth
            using_projected_depth = True
            _proj_seg = _sg.get("projected_seg_path")
            if _proj_seg and Path(_proj_seg).exists():
                seg_path = _proj_seg
            print(f"[renderer] using scene-graph projected depth as ControlNet condition: {Path(_proj_depth).name}")

    controlnet_inputs: dict[str, str] = {}
    if depth_path:
        controlnet_inputs["depth"] = str(depth_path)
    if seg_path:
        controlnet_inputs["segmentation"] = str(seg_path)

    # 1. Hugging Face Inference API (cloud Flux; no local download)
    hf_model_id = Config.FLUX_MODEL

    # Use style_reference_image as control image:
    # priority: user upload > Supabase matched image > depth map
    style_method = user_input.get("style_method", "ai_analysis")
    style_reference_image = user_input.get("style_reference_image")
    user_style_reference_local: str | None = None
    if isinstance(style_reference_image, str) and style_reference_image.strip():
        style_reference_candidate = style_reference_image.strip()
        if Path(style_reference_candidate).exists():
            user_style_reference_local = style_reference_candidate
        elif style_reference_candidate.startswith(("http://", "https://")):
            try:
                from designbridge.style.style_supabase import download_style_image

                downloaded_ref = download_style_image(style_reference_candidate)
                if downloaded_ref and downloaded_ref.exists():
                    user_style_reference_local = str(downloaded_ref)
            except Exception as e:
                print(f"⚠️  下載使用者風格參考圖失敗：{e}")

    if user_style_reference_local:
        control_img = user_style_reference_local
        controlnet_inputs["style_reference_image"] = user_style_reference_local
        if style_method == "ai_analysis":
            _kb_url = (style_params or {}).get("reference_image_url", "")
            _kb_text = (style_params or {}).get("style_summary", "").strip()
            _is_kb_image = (
                _kb_url
                and _kb_text
                and isinstance(style_reference_image, str)
                and style_reference_image.strip() == _kb_url
            )
            if _is_kb_image:
                # KB's English style_prompt is already folded into `prompt` by
                # _build_imagen_prompt_from_requirement; its Chinese description
                # (_kb_text) is UI-display-only, so skip re-injecting it here.
                print(f"📚 Supabase KB 圖片已作為風格參考（風格描述已由 style_prompt 注入，跳過 Gemini 分析）")
            else:
                style_vision_desc = timed_call(
                    "renderer.gemini_style_analysis", task_id,
                    _analyze_style_image_with_gemini, user_style_reference_local,
                )
                if style_vision_desc:
                    prompt = f"{prompt} Style reference: {style_vision_desc}"
                    generation_params["gemini_style_description"] = style_vision_desc
                    print(f"🎨 Gemini 風格描述已注入 prompt：{style_vision_desc[:80]}…")
    elif style_params and style_params.get("reference_image_path") and Path(style_params["reference_image_path"]).exists():
        control_img = style_params["reference_image_path"]
        controlnet_inputs["style_reference_image"] = control_img
        print(f"使用 Supabase 匹配圖作為風格參考：{Path(control_img).name}")
    else:
        control_img = depth_path if depth_path and Path(depth_path).exists() else None

    # IP-Adapter 模式：文字控制空間類型，圖像注入風格（fal.ai FLUX-general）
    if style_method == "ipadapter" and user_style_reference_local and backend == "placeholder":
        if not Config.FAL_KEY:
            print("⚠️  IP-Adapter 模式需要 FAL_KEY，改走 ai_analysis fallback")
        elif timed_call(
            "renderer.flux_ipadapter_fal", task_id,
            _render_flux_ipadapter_fal,
            user_style_reference_local, out_path, prompt=prompt,
            ip_adapter_scale=Config.FAL_IP_ADAPTER_SCALE,
            num_steps=Config.FAL_IP_ADAPTER_STEPS,
            guidance_scale=Config.FAL_IP_ADAPTER_GUIDANCE,
            output_size=(Config.FAL_IP_ADAPTER_SIZE, Config.FAL_IP_ADAPTER_SIZE),
        ):
            backend = "flux_ipadapter_fal"
            generation_params["model"] = "fal-ai/flux-general + XLabs IP-Adapter"
            generation_params["style_reference"] = user_style_reference_local
            generation_params["ip_adapter_scale"] = Config.FAL_IP_ADAPTER_SCALE

    # Redux 模式：本地 FLUX.1-Redux pipeline（需先在 HuggingFace 接受授權並下載模型）
    # DESIGNBRIDGE_ENABLE_FLUX_REDUX=true 才嘗試載入，避免未授權時每次報錯
    if style_method == "redux" and user_style_reference_local and backend == "placeholder":
        if not Config.ENABLE_FLUX_REDUX:
            print("⚠️  FLUX.1-Redux 未啟用（DESIGNBRIDGE_ENABLE_FLUX_REDUX=false），改走 ai_analysis fallback")
        elif Config.FAL_KEY and timed_call(
            "renderer.flux_redux_fal", task_id,
            _render_flux_redux_fal,
            user_style_reference_local, out_path, prompt=prompt, output_size=output_size,
            num_steps=Config.FAL_REDUX_STEPS, guidance_scale=Config.FAL_REDUX_GUIDANCE,
        ):
            backend = "flux_redux_fal"
            generation_params["model"] = "fal-ai/flux-1/dev/redux"
            generation_params["style_reference"] = user_style_reference_local
        elif timed_call(
            "renderer.flux_redux_local", task_id,
            _render_flux_redux_local,
            user_style_reference_local, out_path, prompt=prompt, output_size=output_size,
        ):
            backend = "flux_redux_local"
            generation_params["model"] = "black-forest-labs/FLUX.1-Redux-dev (local)"
            generation_params["style_reference"] = user_style_reference_local

    # Kontext LoRA：有 depth map 時優先，保留空間結構
    # depth_conditioning_scale: 1.0=完全保留結構, 0.0=忽略深度圖
    # lora scale 直接對應 depth_conditioning_scale，不需轉換
    depth_conditioning_scale = float(req.get("depth_conditioning_scale") or 0.85)
    depth_conditioning_scale = max(0.0, min(1.0, depth_conditioning_scale))
    # The LLM's depth_conditioning_scale is calibrated for real photo depth ("how much to
    # preserve an existing room's structure"). Projected/synthetic depth is geometrically
    # blockier (sharp axis-aligned furniture boxes, no natural surface variation) than what
    # ControlNet was trained on — conditioning that strongly on it renders furniture as
    # disconnected floating boxes instead of a coherent room, so cap it lower here.
    if using_projected_depth:
        depth_conditioning_scale = min(depth_conditioning_scale, Config.PROJECTED_DEPTH_MAX_CONDITIONING_SCALE)
    effective_depth_path = depth_path if depth_conditioning_scale >= 0.20 else None

    # 真正的 FLUX depth ControlNet（opt-in，需 FAL_KEY）：對深度幾何的約束遠強於 Kontext LoRA，
    # 讓 scene-graph 投影深度真正控制家具擺位。設 LAYOUT_DEPTH_CONTROL_BACKEND=controlnet 啟用。
    if (
        backend == "placeholder"
        and Config.LAYOUT_DEPTH_CONTROL_BACKEND == "controlnet"
        and Config.FAL_KEY
        and effective_depth_path and Path(str(effective_depth_path)).is_file()
    ):
        if timed_call(
            "renderer.flux_controlnet_depth_fal", task_id,
            _render_flux_controlnet_depth_fal,
            prompt, str(effective_depth_path), out_path,
            conditioning_scale=depth_conditioning_scale,
            num_steps=Config.FAL_CONTROLNET_STEPS,
            guidance_scale=Config.FAL_CONTROLNET_GUIDANCE,
            output_size=output_size,
        ):
            backend = "flux_controlnet_depth_fal"
            generation_params["model"] = f"fal-ai/flux-general + {Config.DEPTH_CONTROLNET_MODEL}"
            generation_params["depth_conditioning_scale"] = depth_conditioning_scale

    if backend == "placeholder" and effective_depth_path and Path(str(effective_depth_path)).is_file():
        if Config.HF_TOKEN:
            if timed_call(
                "renderer.hf_kontext", task_id,
                _render_hf_kontext,
                prompt, str(effective_depth_path), out_path,
                depth_conditioning_scale=depth_conditioning_scale,
            ):
                backend = "hf_kontext"
                generation_params["model"] = Config.KONTEXT_LORA_MODEL
                generation_params["provider"] = Config.KONTEXT_PROVIDER
                generation_params["depth_conditioning_scale"] = depth_conditioning_scale

    # AI 分析模式 fallback：HF Inference API
    if backend == "placeholder" and Config.ENABLE_HF_INFERENCE and Config.HF_TOKEN:
        if timed_call(
            "renderer.hf_inference", task_id,
            _render_hf_inference,
            prompt, out_path, model=hf_model_id, output_size=output_size,
        ):
            backend = "hf_inference"
            generation_params["model"] = hf_model_id
            generation_params["provider"] = Config.HF_INFERENCE_PROVIDER

    # 2. fal.ai FLUX 純文字生圖（雲端，不需 depth/style 參考圖；HF 兩條路都失敗時的快速備援）
    if backend == "placeholder" and Config.FAL_KEY:
        if timed_call(
            "renderer.flux_fal", task_id,
            _render_flux_fal,
            prompt, out_path, output_size=output_size,
        ):
            backend = "flux_fal"
            generation_params["model"] = "fal-ai/flux/schnell"

    # 3. Local Flux model（最後手段：CPU 推理慢，且首次會下載整包模型，僅在雲端全部失敗時使用）
    if backend == "placeholder" and Config.ENABLE_FLUX_FALLBACK:
        if timed_call("renderer.flux_local", task_id, _render_flux, prompt, out_path):
            backend = "flux"
            generation_params["model"] = hf_model_id
        else:
            generation_params["render_error"] = "local render failed"

    # 4. Fallback to placeholder
    if backend == "placeholder":
        generation_params["render_error"] = "API unavailable: both Kontext and HF Inference failed"
        print("⚠️  Renderer: all API backends failed, no image generated")

    generation_params["backend"] = backend
    path_str = str(out_path)
    render_result: dict[str, Any] = {
        "generated_image_path": path_str,
        "generation_params": generation_params,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Add controlnet_inputs if any were used
    if controlnet_inputs:
        render_result["controlnet_inputs"] = controlnet_inputs

    return {
        "generated_image": path_str,
        "render_result": render_result,
    }
