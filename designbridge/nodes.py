# designbridge/nodes.py
"""DesignBridge graph nodes: Requirement Analyzer, Visual Preprocessing stub, Design Director, Renderer, agent stubs."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from designbridge.config import Config
from designbridge.prompts import REQUIREMENT_ANALYZER_PROMPT
from designbridge.style_apply import build_style_params, STYLE_NAME_TO_ID
from designbridge.state import DesignBridgeState, RoutingDecision
from designbridge.vision import run_visual_preprocessing
from designbridge.schemas import RequirementJSON, StyleParamsJSON
from designbridge.inpaint import (
    mask_from_segmentation,
    fallback_center_mask,
    build_inpaint_prompt,
    run_inpainting,
    run_hf_inpainting,
)

def requirement_analyzer(state: DesignBridgeState) -> dict[str, Any]:
    """
    Parse user_input into structured_requirement (JSON) using Gemini API.
    Falls back to rule-based if API key not set or API fails.
    """
    user = state.get("user_input") or {}
    text_prompt = (user.get("text_prompt") or "").strip()
    edit_scope = float(user.get("edit_scope", 0.5))
    initial_image = user.get("initial_image", "無")
    style_reference_image = user.get("style_reference_image", "")

    task_id = state.get("task_id") or str(uuid.uuid4())
    iteration = state.get("iteration", 0)

    # Try LLM (via LiteLLM) first, fall back to rule-based on failure
    try:
        structured_requirement = _call_llm_requirement_analyzer(
            text_prompt, edit_scope, initial_image, style_reference_image=style_reference_image
        )
    except Exception as e:
        print(f"⚠️  LLM call failed ({e}), falling back to rule-based")
        structured_requirement = _rule_based_requirement_analyzer(text_prompt, edit_scope, style_reference_image=style_reference_image)

    # If the user explicitly selected a style from the dropdown, override whatever
    # Gemini / rule-based inferred from the text so the whole pipeline stays consistent.
    explicit_style_id = (user.get("style_profile_id") or "").strip()
    if explicit_style_id and explicit_style_id != "auto":
        style_prefs = structured_requirement.setdefault("style_preferences", {})
        style_prefs["primary_style"] = explicit_style_id

    return {
        "task_id": task_id,
        "iteration": iteration,
        "structured_requirement": structured_requirement,
    }


def _is_valid_image_path(image_path: str) -> bool:
    """Return True if image_path is a non-empty, valid file path (not placeholder)."""
    if not image_path or not isinstance(image_path, str):
        return False
    s = image_path.strip()
    if s in ("", "無"):
        return False
    return Path(s).is_file()


def _call_llm_requirement_analyzer(
    text_prompt: str, edit_scope: float, initial_image: str, style_reference_image: str = ""
) -> dict[str, Any]:
    """Call LLM (via LiteLLM) to analyze requirements and return structured JSON.
    Sends images inline when valid file paths are provided (multimodal).
    """
    import json as _json
    from designbridge.llm import call_llm

    prompt = REQUIREMENT_ANALYZER_PROMPT.format(
        text_prompt=text_prompt,
        edit_scope=edit_scope,
        initial_image=initial_image,
    )

    images: list[str] = []
    if _is_valid_image_path(initial_image):
        images.append(initial_image)
    if style_reference_image and _is_valid_image_path(style_reference_image):
        images.append(style_reference_image)

    text = call_llm(prompt, images=images or None)
    text = text.strip()

    # Strip markdown code fences if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Tolerate leading/trailing noise around the JSON object
    if not text.startswith("{"):
        start = text.find("{")
        if start != -1:
            text = text[start:]
    if not text.endswith("}"):
        end = text.rfind("}")
        if end != -1:
            text = text[: end + 1]

    try:
        return _json.loads(text)
    except Exception:
        return _parse_nl_requirement(text, edit_scope, text_prompt)


def _parse_nl_requirement(nl_text: str, edit_scope: float, text_prompt: str = "") -> dict[str, Any]:
    """Parse natural language requirement report (labeled fields) into a compatible dict."""

    def extract_field(field: str) -> str:
        m = re.search(rf'^{re.escape(field)}:\s*(.+)$', nl_text, re.MULTILINE)
        return m.group(1).strip() if m else ""

    def extract_list(field: str) -> list[str]:
        val = extract_field(field)
        if not val or val.strip() in ("無", "none", ""):
            return []
        return [item.strip() for item in re.split(r'[,，]', val) if item.strip() not in ("", "無")]

    room_type = extract_field("空間類型") or "living_room"
    design_goal = extract_field("設計目標") or "renovation"
    primary_style = extract_field("主要風格") or "現代"
    secondary_style = extract_field("次要風格") or None
    if secondary_style in ("無", ""):
        secondary_style = None
    color_palette = extract_list("色彩偏好")
    material_preferences = extract_list("材質偏好")
    must_keep = extract_list("必須保留")
    must_add = extract_list("必須新增")
    must_remove = extract_list("必須移除")
    hint_layout = extract_field("涉及佈局") == "是"
    hint_style = extract_field("涉及風格") == "是"
    hint_adjuster = extract_field("僅局部微調") == "是" or edit_scope < 0.3
    design_description = extract_field("設計描述") or ""

    if edit_scope < 0.3:
        allowed_ops = ["inpaint"]
    elif edit_scope > 0.7:
        allowed_ops = ["layout", "style"]
    elif hint_layout and hint_style:
        allowed_ops = ["layout", "style"]
    elif hint_layout:
        allowed_ops = ["layout"]
    elif hint_style:
        allowed_ops = ["style"]
    else:
        allowed_ops = ["layout", "style"]

    return {
        "user_description_raw": text_prompt or nl_text,
        "design_description": design_description,
        "meta": {
            "room_type": room_type,
            "design_goal": design_goal,
            "user_experience_level": "general",
        },
        "space_info": {
            "estimated_size": {"width": 5.0, "height": 3.0, "depth": 4.0},
            "windows": [],
            "doors": [],
        },
        "style_preferences": {
            "primary_style": primary_style,
            "secondary_style": secondary_style,
            "color_palette": color_palette,
            "material_preferences": material_preferences,
            "style_strength": 0.7,
            "reference_images": [],
        },
        "layout_constraints": {
            "must_keep": must_keep,
            "must_add": must_add,
            "must_remove": must_remove,
            "immutable_regions": [],
            "functional_zones": [],
        },
        "edit_scope": {
            "scope_value": edit_scope,
            "allowed_operations": allowed_ops,
        },
        "priority_weights": {
            "layout_rationality": 0.4,
            "style_consistency": 0.4,
            "novelty": 0.2,
        },
        "hint_layout": hint_layout,
        "hint_style": hint_style,
        "hint_adjuster": hint_adjuster,
    }


def _rule_based_requirement_analyzer(text_prompt: str, edit_scope: float, style_reference_image: str = "") -> dict[str, Any]:
    """Fallback rule-based requirement analyzer: produce RequirementJSON structure."""
    text = text_prompt.lower()

    # Simple keyword extraction
    room_map = {
        "客廳": "living_room",
        "臥室": "bedroom",
        "書房": "study",
        "廚房": "kitchen",
    }
    for cn, en in room_map.items():
        if cn in text or en in text:
            room_type = en
            break
    else:
        room_type = "living_room"

    # Check specific styles first before generic "現代" to avoid false matches
    # e.g. "帶有現代感的日式設計" should resolve to "日式" not "現代"
    styles = ["北歐", "nordic", "scandinavian", "工業", "industrial", "日式", "japanese",
              "鄉村", "country", "古典", "classic", "美式", "american",
              "奢華", "luxury", "新古典", "neoclassic", "簡約", "minimal",
              "現代", "modern"]
    primary_style = next((s for s in styles if s in text), None)

    # Detect hints
    hint_layout = any(kw in text for kw in ["動線", "布局", "layout", "空間配置"])
    hint_style = any(kw in text for kw in ["風格", "style", "色彩", "材質"])
    hint_adjuster = any(kw in text for kw in ["局部", "微調", "單一"]) or edit_scope < 0.3

    # Determine allowed_operations
    if edit_scope < 0.3:
        allowed_ops = ["inpaint"]
    elif edit_scope > 0.7:
        allowed_ops = ["layout", "style"]
    elif hint_layout and hint_style:
        allowed_ops = ["layout", "style"]
    elif hint_layout:
        allowed_ops = ["layout"]
    elif hint_style:
        allowed_ops = ["style"]
    else:
        allowed_ops = ["layout", "style"]

    # Build RequirementJSON structure
    structured_requirement: dict[str, Any] = {
        "user_description_raw": text_prompt,
        "design_description": "",
        "meta": {
            "room_type": room_type,
            "design_goal": "renovation",  # default
            "user_experience_level": "general",
        },
        "space_info": {
            "estimated_size": {"width": 5.0, "height": 3.0, "depth": 4.0},
            "windows": [],
            "doors": [],
        },
        "style_preferences": {
            "primary_style": primary_style or "",
            "secondary_style": None,
            "color_palette": [],
            "material_preferences": [],
            "style_strength": 0.7,
            "reference_images": [style_reference_image] if style_reference_image else [],
        },
        "layout_constraints": {
            "must_keep": [],
            "must_add": [],
            "must_remove": [],
            "immutable_regions": [],
            "functional_zones": [],
        },
        "edit_scope": {
            "scope_value": edit_scope,
            "allowed_operations": allowed_ops,
        },
        "priority_weights": {
            "layout_rationality": 0.4,
            "style_consistency": 0.4,
            "novelty": 0.2,
        },
        "hint_layout": hint_layout,
        "hint_style": hint_style,
        "hint_adjuster": hint_adjuster,
    }

    return structured_requirement


def visual_preprocessing_local(state: DesignBridgeState) -> dict[str, Any]:
    """Local Visual Preprocessing: run depth + segmentation on the initial image (if provided)."""
    user = state.get("user_input") or {}
    image_path = user.get("initial_image")
    if not image_path:
        # Empty layout scenario: nothing to preprocess.
        return {"vision_features": {"geometry_constraints": {}}}

    task_id = state.get("task_id") or "no_task_id"
    try:
        artifacts = run_visual_preprocessing(
            image_path,
            task_id=task_id,
            enable_depth=Config.ENABLE_DEPTH,
            enable_segmentation=Config.ENABLE_SEGMENTATION,
            depth_model=Config.DEPTH_MODEL,
            segmentation_model=Config.SEGMENTATION_MODEL,
            artifacts_root=Path(Config.ARTIFACTS_DIR),
        )
    except Exception as e:
        # Keep the workflow usable even if vision dependencies/models aren't available yet.
        print(f"⚠️  Visual preprocessing failed ({e}), falling back to empty vision_features")
        return {"vision_features": {"geometry_constraints": {}}}

    vision_features: dict[str, Any] = {"geometry_constraints": {}}
    if artifacts.depth_path:
        vision_features["depth"] = artifacts.depth_path
    if artifacts.segmentation_path:
        vision_features["segmentation"] = artifacts.segmentation_path
    if artifacts.segmentation_meta_path:
        vision_features["segmentation_meta"] = artifacts.segmentation_meta_path

    return {"vision_features": vision_features}


def _route_decision(state: DesignBridgeState) -> RoutingDecision:
    """
    Design Director: decide routing from structured_requirement + vision_features.
    Uses edit_scope.scope_value and hint_* to choose layout / style / design_adjuster / layout_and_style.
    """
    req = state.get("structured_requirement") or {}
    edit_scope_info = req.get("edit_scope") or {}
    scope_value = float(edit_scope_info.get("scope_value", 0.5))

    hint_adjuster = req.get("hint_adjuster") is True
    hint_layout = req.get("hint_layout") is True
    hint_style = req.get("hint_style") is True

    if hint_adjuster or scope_value < 0.3:
        return "design_adjuster"
    if hint_layout and hint_style:
        return "layout_and_style"
    if hint_layout:
        return "layout"
    if hint_style:
        return "style"
    # Default: both layout and style
    return "layout_and_style"


def design_director(state: DesignBridgeState) -> dict[str, Any]:
    """
    動態調度：ENABLE_DYNAMIC_ROUTING=true 時由 Gemini 讀 SKILL.md 決策；
    否則使用原本的 rule-based routing。任何 LLM 失敗都自動 fallback。
    """
    if Config.get_dynamic_routing_enabled():
        try:
            from designbridge.router import call_llm_router, RouterLLMError
            api_key = Config.get_gemini_api_key()
            routing_decision = call_llm_router(
                structured_requirement=state.get("structured_requirement") or {},
                vision_features=state.get("vision_features") or {},
                api_key=api_key,
                gemini_model=Config.GEMINI_MODEL,
                gemini_temperature=Config.ROUTER_TEMPERATURE,
            )
            print(f"[design_director] LLM router: {routing_decision}")
        except Exception as e:
            print(f"[design_director] LLM routing failed ({e}), fallback to rule-based")
            routing_decision = _route_decision(state)
    else:
        routing_decision = _route_decision(state)

    return {"routing_decision": routing_decision}



def layout_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """Stub for Layout agent. Real impl: layout optimization + ControlNet, etc."""
    return {
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            "layout_agent": "stub_output",
        }
    }


def style_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """Quick style agent: load aggregated style profile and build prompt params."""
    req = state.get("structured_requirement") or {}
    user_input = state.get("user_input") or {}
    style_params = build_style_params(req, user_input)

    if not style_params:
        return {
            "intermediate_outputs": {
                **(state.get("intermediate_outputs") or {}),
                "style_agent": "no_aggregated_style_profile",
            }
        }

    return {
        "style_params": style_params,
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            "style_agent": {
                "status": "aggregated_style_loaded",
                "style_profile_id": style_params.get("style_profile_id"),
                "style_profile_name": style_params.get("style_profile_name"),
            },
        }
    }


def adjuster_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """
    Design Adjuster Agent：對初始圖片進行局部 inpainting。
    觸發條件：edit_scope < 0.3 或 hint_adjuster = True。
    """
    from PIL import Image

    task_id = state.get("task_id") or str(uuid.uuid4())
    user_input = state.get("user_input") or {}
    req = state.get("structured_requirement") or {}
    vision = state.get("vision_features") or {}
    style_params = state.get("style_params")

    image_path = user_input.get("initial_image", "")
    edit_scope = float(user_input.get("edit_scope", 0.2))

    # 沒有原圖就無法 inpaint，跳過
    if not image_path or not Path(image_path).is_file():
        return {
            "intermediate_outputs": {
                **(state.get("intermediate_outputs") or {}),
                "adjuster_agent": "no_initial_image_skipped",
            }
        }

    # 決定要修改哪些物件
    constraints = req.get("layout_constraints") or {}
    must_remove = constraints.get("must_remove") or []
    must_add = constraints.get("must_add") or []
    # 要移除的物件 = mask 目標；要新增的物件 = prompt 目標
    target_labels = must_remove if must_remove else ["furniture"]
    target_objects = must_add if must_add else target_labels

    # Mask 生成
    seg_path = vision.get("segmentation")
    seg_meta = vision.get("segmentation_meta")
    original_img = Image.open(image_path)
    img_size = original_img.size

    if seg_path and seg_meta and Path(str(seg_path)).is_file() and Path(str(seg_meta)).is_file():
        mask = mask_from_segmentation(str(seg_path), str(seg_meta), target_labels, img_size)
        mask_source = "segmentation"
    else:
        mask = fallback_center_mask(img_size)
        mask_source = "fallback_center"

    # Prompt 組裝
    prompt, negative_prompt = build_inpaint_prompt(req, style_params, target_objects)

    # strength：edit_scope 越小改動越保守（0.4~0.85）
    strength = max(0.4, min(0.85, edit_scope + 0.4))

    out_path = Path(Config.ARTIFACTS_DIR) / "render" / f"{task_id}.png"
    backend = "placeholder"

    # 1. HF Inference API（雲端，不需本地模型）
    if Config.HF_TOKEN:
        if run_hf_inpainting(image_path, mask, prompt, out_path):
            backend = "hf_inpainting"

    # 2. 本地 SD Inpainting
    if backend == "placeholder":
        if run_inpainting(image_path, mask, prompt, negative_prompt, strength, out_path):
            backend = "sd_inpainting"

    # 3. Fallback：複製原圖
    if backend == "placeholder":
        out_path.parent.mkdir(parents=True, exist_ok=True)
        original_img.save(str(out_path))

    adjust_plan = {
        "inpaint_regions": [{
            "target_labels": target_labels,
            "target_objects": target_objects,
            "prompt": prompt,
            "strength": strength,
            "mask_source": mask_source,
        }],
        "consistency_guidance": (req.get("style_preferences") or {}).get("primary_style", ""),
    }

    return {
        "generated_image": str(out_path),
        "render_result": {
            "generated_image_path": str(out_path),
            "generation_params": {
                "backend": backend,
                "model": "stable-diffusion-2-inpainting",
                "strength": strength,
                "mask_source": mask_source,
                "prompt_preview": prompt[:150],
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            "adjuster_agent": adjust_plan,
        },
    }


def layout_and_style_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """Quick layout+style agent: keep layout stub, but still attach style params."""
    req = state.get("structured_requirement") or {}
    user_input = state.get("user_input") or {}
    style_params = build_style_params(req, user_input)

    return {
        **({"style_params": style_params} if style_params else {}),
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            "layout_and_style_agent": {
                "layout": "stub_output",
                "style_profile_id": style_params.get("style_profile_id") if style_params else None,
            },
        }
    }


def _build_imagen_prompt_from_requirement(
    req: dict[str, Any],
    style_params: dict[str, Any] | None = None,
) -> str:
    """Build an English text prompt for image generation from structured_requirement and style params.
    Prefers the natural-language design_description from Gemini when available.
    """
    _STYLE_ID_TO_EN = {
        "modern": "modern contemporary",
        "country": "country rustic farmhouse",
        "classic": "classical traditional",
        "nordic": "Nordic Scandinavian minimalist",
        "industrial": "industrial loft",
        "japanese": "Japanese minimalist Japandi",
        "american": "American style",
        "luxury": "luxury high-end glamour",
        "neoclassic": "neoclassical",
    }
    design_description = (req.get("design_description") or "").strip()
    if design_description:
        base_prompt = design_description
    else:
        meta = req.get("meta") or {}
        style_prefs = req.get("style_preferences") or {}
        room_type = meta.get("room_type", "living_room").replace("_", " ")
        if style_params and style_params.get("style_profile_id"):
            style_id = style_params["style_profile_id"].lower()
        else:
            raw_style = style_prefs.get("primary_style") or ""
            style_id = STYLE_NAME_TO_ID.get(raw_style) or raw_style.lower()
        primary_style = _STYLE_ID_TO_EN.get(style_id, style_id) or "interior"
        color_palette = style_prefs.get("color_palette") or []
        colors = ", ".join(str(c) for c in color_palette[:3]) if color_palette else "neutral tones"
        base_prompt = (
            f"Interior design visualization: a {room_type} room, {primary_style} style, "
            f"colors {colors}. Photorealistic, well-lit, high quality."
        )

    if not style_params:
        return base_prompt

    color_guidance = style_params.get("color_guidance") or {}
    visual_essence = color_guidance.get("visual_essence") or []
    material_recommendations = style_params.get("material_recommendations") or []
    style_prompt = style_params.get("style_prompt") or ""
    summary = style_params.get("style_summary") or ""
    strength = style_params.get("style_strength", 0.7)

    extra_parts: list[str] = []
    style_name = style_params.get("style_profile_name", "")
    if style_name:
        extra_parts.append(f"Style profile: {style_name} (strength {strength}).")
    if summary:
        extra_parts.append(summary)
    if visual_essence:
        extra_parts.append("Visual essence: " + ", ".join(str(item) for item in visual_essence[:4]) + ".")
    if material_recommendations:
        extra_parts.append("Materials: " + ", ".join(str(item) for item in material_recommendations[:4]) + ".")
    if color_guidance.get("primary_color"):
        extra_parts.append(
            f"Palette: primary {color_guidance.get('primary_color')}, "
            f"secondary {color_guidance.get('secondary_color')}, "
            f"accent {color_guidance.get('accent_color')}."
        )
    if style_prompt:
        extra_parts.append(style_prompt)

    return (base_prompt + " " + " ".join(extra_parts)).strip()


def _renderer_placeholder_image(out_path: Path, task_id: str, prompt: str) -> None:
    """Save a placeholder image (PIL) when SDXL is unavailable."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (512, 512), color=(240, 240, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 200, 462, 312], fill=(255, 255, 255), outline=(180, 180, 190))
    text = "DesignBridge\n(placeholder)"
    try:
        draw.text((256, 256), text, fill=(100, 100, 110), anchor="mm")
    except Exception:
        draw.text((150, 240), "DesignBridge placeholder", fill=(100, 100, 110))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


# 快取模型，不用每次都載入
_sdxl_pipeline: Any = None
_controlnet_pipeline: Any = None
_sd_pipeline: Any = None
_flux_pipeline: Any = None


def _get_sdxl_pipeline():
    """Load SDXL pipeline once and cache it. GPU if available (~15–30s/image), else CPU (slower)."""
    global _sdxl_pipeline
    if _sdxl_pipeline is not None:
        return _sdxl_pipeline
    from diffusers import StableDiffusionXLPipeline
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _sdxl_pipeline = StableDiffusionXLPipeline.from_pretrained(
        Config.SDXL_MODEL,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        use_safetensors=True,
    )
    _sdxl_pipeline = _sdxl_pipeline.to(device)
    return _sdxl_pipeline


def _get_controlnet_pipeline():
    """Load SDXL + ControlNet pipeline once and cache it. Uses depth ControlNet for layout guidance."""
    global _controlnet_pipeline
    if _controlnet_pipeline is not None:
        return _controlnet_pipeline
    from diffusers import StableDiffusionXLControlNetPipeline, ControlNetModel
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Load ControlNet model (depth)
    controlnet = ControlNetModel.from_pretrained(
        Config.CONTROLNET_DEPTH_MODEL,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    )

    # Load SDXL pipeline with ControlNet
    _controlnet_pipeline = StableDiffusionXLControlNetPipeline.from_pretrained(
        Config.SDXL_MODEL,
        controlnet=controlnet,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        use_safetensors=True,
    )
    _controlnet_pipeline = _controlnet_pipeline.to(device)
    return _controlnet_pipeline


def _render_hf_inference(prompt: str, out_path: Path, model: str = "") -> bool:
    """
    Generate image via Hugging Face Inference API.
    No local model download. Returns True on success.
    """
    api_key = Config.HF_TOKEN
    if not api_key:
        return False
    try:
        from huggingface_hub import InferenceClient

        client = InferenceClient(
            provider=Config.HF_INFERENCE_PROVIDER,
            api_key=api_key,
        )
        image = client.text_to_image(prompt, model=model)
        if image is None:
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(out_path))
        return True
    except Exception as e:
        import traceback
        print(f"⚠️  HF Inference render failed ({type(e).__name__}: {e})")
        traceback.print_exc()
        return False


def _get_sd_pipeline():
    """Load SD 3.5 pipeline once and cache it."""
    global _sd_pipeline
    if _sd_pipeline is not None:
        return _sd_pipeline
    from diffusers import DiffusionPipeline
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    kwargs: dict[str, Any] = {
        "torch_dtype": torch.bfloat16 if device == "cuda" else torch.float32,
    }
    if Config.HF_TOKEN:
        kwargs["token"] = Config.HF_TOKEN
    _sd_pipeline = DiffusionPipeline.from_pretrained(Config.SD_MODEL, **kwargs).to(device)
    return _sd_pipeline


def _get_flux_pipeline():
    """Load Flux.1 pipeline once and cache it."""
    global _flux_pipeline
    if _flux_pipeline is not None:
        return _flux_pipeline
    from diffusers import FluxPipeline
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    kwargs: dict[str, Any] = {
        "torch_dtype": torch.bfloat16 if device == "cuda" else torch.float32,
    }
    if Config.HF_TOKEN:
        kwargs["token"] = Config.HF_TOKEN
    _flux_pipeline = FluxPipeline.from_pretrained(Config.FLUX_MODEL, **kwargs).to(device)
    return _flux_pipeline


def _render_sdxl(prompt: str, out_path: Path, control_image: str | Path | None = None, negative_prompt: str | None = None) -> bool:
    """
    Generate image with local SD / SDXL / Flux based on Config.LOCAL_MODEL_TYPE.
    Returns True on success.
    """
    try:
        import torch
        from PIL import Image

        device = "cuda" if torch.cuda.is_available() else "cpu"
        steps = Config.SDXL_STEPS
        if device == "cpu":
            steps = min(steps, 20)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        model_type = Config.get_local_model_type()

        if model_type == "flux":
            pipe = _get_flux_pipeline()
            image = pipe(prompt=prompt, num_inference_steps=steps, guidance_scale=0.0).images[0]

        elif model_type == "sd":
            pipe = _get_sd_pipeline()
            image = pipe(prompt=prompt, num_inference_steps=steps).images[0]

        else:  # sdxl (default)
            if Config.ENABLE_CONTROLNET and control_image and Path(control_image).exists():
                pipe = _get_controlnet_pipeline()
                control_img = Image.open(control_image).convert("RGB")
                control_img = control_img.resize((1024, 1024), Image.Resampling.LANCZOS)
                image = pipe(
                    prompt=prompt,
                    image=control_img,
                    num_inference_steps=steps,
                    controlnet_conditioning_scale=Config.CONTROLNET_CONDITIONING_SCALE,
                ).images[0]
            else:
                pipe = _get_sdxl_pipeline()
                kwargs = {"prompt": prompt, "num_inference_steps": steps}
                if negative_prompt:
                    kwargs["negative_prompt"] = negative_prompt
                image = pipe(**kwargs).images[0]

        image.save(str(out_path))
        return True
    except Exception as e:
        import traceback
        print(f"⚠️ Render failed ({type(e).__name__}: {e})")
        traceback.print_exc()
        return False


def renderer(state: DesignBridgeState) -> dict[str, Any]:
    """
    Renderer: generate image from structured_requirement.
    Uses Stable Diffusion XL only (with ControlNet if depth available), then placeholder on failure.
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
    out_path = render_dir / f"{task_id}.png"

    prompt = _build_imagen_prompt_from_requirement(req, style_params=style_params)
    negative_prompt = style_params.get("negative_prompt") or None
    generation_params: dict[str, Any] = {
        "prompt_preview": prompt[:200],
        "negative_prompt_preview": (negative_prompt or "")[:200],
    }
    backend = "placeholder"

    if style_params:
        generation_params["style_profile_id"] = style_params.get("style_profile_id")
        generation_params["style_profile_name"] = style_params.get("style_profile_name")
        generation_params["style_strength"] = style_params.get("style_strength")

    # Get vision features for ControlNet (if available)
    vision = state.get("vision_features") or {}
    depth_path = vision.get("depth")
    seg_path = vision.get("segmentation")
    controlnet_inputs: dict[str, str] = {}
    if depth_path:
        controlnet_inputs["depth"] = str(depth_path)
    if seg_path:
        controlnet_inputs["segmentation"] = str(seg_path)

    # 1. Hugging Face Inference API (cloud SDXL; no local download)
    model_type = Config.get_local_model_type()
    if model_type == "flux":
        hf_model_id = Config.FLUX_MODEL
    elif model_type == "sd":
        hf_model_id = Config.SD_MODEL
    else:
        hf_model_id = Config.SDXL_MODEL

    # Use style_reference_image as control image:
    # priority: user upload > Supabase matched image > depth map
    user_input = state.get("user_input") or {}
    style_reference_image = user_input.get("style_reference_image")
    if style_reference_image and Path(style_reference_image).exists():
        control_img = style_reference_image
        controlnet_inputs["style_reference_image"] = str(style_reference_image)
    elif style_params and style_params.get("reference_image_path") and Path(style_params["reference_image_path"]).exists():
        control_img = style_params["reference_image_path"]
        controlnet_inputs["style_reference_image"] = control_img
        print(f"使用 Supabase 匹配圖作為風格參考：{Path(control_img).name}")
    else:
        control_img = depth_path if depth_path and Path(depth_path).exists() else None

    if backend == "placeholder" and Config.ENABLE_HF_INFERENCE and Config.HF_TOKEN:
        if _render_hf_inference(prompt, out_path, model=hf_model_id):
            backend = "hf_inference"
            generation_params["model"] = hf_model_id
            generation_params["provider"] = Config.HF_INFERENCE_PROVIDER

    # 2. Local model (SD / SDXL / Flux)
    if backend == "placeholder" and Config.ENABLE_SDXL_FALLBACK:
        if _render_sdxl(prompt, out_path, control_image=control_img):
            backend = model_type
            generation_params["model"] = hf_model_id
            if control_img:
                if style_reference_image and Path(style_reference_image).exists() and control_img == style_reference_image:
                    generation_params["controlnet"] = "style_reference_image"
                elif model_type == "sdxl":
                    generation_params["controlnet"] = style_params.get("controlnet_type", "depth")
                generation_params["controlnet_scale"] = Config.CONTROLNET_CONDITIONING_SCALE
        else:
            generation_params["render_error"] = "local render failed"

    # 3. Fallback to placeholder
    if backend == "placeholder":
        _renderer_placeholder_image(out_path, task_id, prompt)
        generation_params["fallback"] = "placeholder"

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


def clip_evaluator_node(state: DesignBridgeState) -> dict[str, Any]:
    """Run CLIP evaluation on the generated image against the user's text prompt."""
    image_path = state.get("generated_image")
    user = state.get("user_input") or {}
    text_prompt = (user.get("text_prompt") or "").strip()

    if not image_path or not Path(image_path).is_file():
        return {"evaluation_result": {"scores": {}, "weighted_score": 0.0, "decision": "skip", "feedback": "no generated image", "issues_found": [], "suggestions": []}}

    if not text_prompt:
        return {"evaluation_result": {"scores": {}, "weighted_score": 0.0, "decision": "skip", "feedback": "no text prompt", "issues_found": [], "suggestions": []}}

    try:
        from designbridge.clip_evaluator import evaluate
        result = evaluate(image_path, text_prompt)
    except Exception as e:
        result = {"scores": {}, "weighted_score": 0.0, "decision": "skip", "feedback": f"CLIP evaluation failed: {e}", "issues_found": [], "suggestions": []}

    return {"evaluation_result": result}
