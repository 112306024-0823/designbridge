# designbridge/nodes.py
"""DesignBridge graph nodes: Requirement Analyzer, Visual Preprocessing stub, Design Director, Renderer, agent stubs."""

from __future__ import annotations

import io
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from designbridge.config import Config
from designbridge.prompts import REQUIREMENT_ANALYZER_PROMPT

_BASE_NEGATIVE_PROMPT = (
    "people, person, human, man, woman, child, hands, face, "
    "animal, pet, cat, dog, bird, "
    "text, watermark, signature, logo"
)
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

    # Try LLM (via LiteLLM) first, fall back to passing prompt directly on failure
    try:
        structured_requirement = _call_llm_requirement_analyzer(
            text_prompt, edit_scope, initial_image,
            style_reference_image=style_reference_image,
        )
    except Exception as e:
        print(f"⚠️  LLM call failed ({e}), passing prompt directly to renderer")
        structured_requirement = {
            "user_description_raw": text_prompt,
            "design_description": text_prompt,
            "meta": {"room_type": "living_room", "design_goal": "renovation", "user_experience_level": "general"},
            "space_info": {"estimated_size": {"width": 5.0, "height": 3.0, "depth": 4.0}, "windows": [], "doors": []},
            "style_preferences": {"primary_style": "", "secondary_style": None, "color_palette": [], "material_preferences": [], "style_strength": 0.7, "reference_images": []},
            "layout_constraints": {"must_keep": [], "must_add": [], "must_remove": [], "immutable_regions": [], "functional_zones": []},
            "edit_scope": {"scope_value": edit_scope, "allowed_operations": ["layout", "style"]},
            "priority_weights": {"layout_rationality": 0.4, "style_consistency": 0.4, "user_preference": 0.2},
        }

    # Merge family needs and feng shui rules into structured_requirement
    family_needs   = user.get("family_needs")   or []
    fengshui_rules = user.get("fengshui_rules") or []
    if family_needs or fengshui_rules:
        from designbridge.special_constraints import enrich_requirement
        structured_requirement = enrich_requirement(structured_requirement, family_needs, fengshui_rules)

    # If the user explicitly selected a style from the dropdown, override whatever
    # Gemini / rule-based inferred from the text so the whole pipeline stays consistent.
    explicit_style_id = (user.get("style_profile_id") or "").strip()
    if explicit_style_id and explicit_style_id != "auto":
        style_prefs = structured_requirement.setdefault("style_preferences", {})
        style_prefs["primary_style"] = explicit_style_id

    # Extract routing decision embedded by _call_llm_requirement_analyzer, then remove it
    # from the requirement so it doesn't pollute structured data.
    routing_decision = structured_requirement.pop("_routing_decision", None)

    result: dict[str, Any] = {
        "task_id": task_id,
        "iteration": iteration,
        "structured_requirement": structured_requirement,
    }
    if routing_decision:
        result["routing_decision"] = routing_decision
        print(f"[requirement_analyzer] routing_decision from LLM: {routing_decision}")

    return result


def _is_valid_image_path(image_path: str) -> bool:
    """Return True if image_path is a non-empty, valid file path (not placeholder)."""
    if not image_path or not isinstance(image_path, str):
        return False
    s = image_path.strip()
    if s in ("", "無"):
        return False
    return Path(s).is_file()


_VALID_ROUTING_DECISIONS = {"design_adjuster", "design"}


def _call_llm_requirement_analyzer(
    text_prompt: str, edit_scope: float, initial_image: str,
    style_reference_image: str = "",
) -> dict[str, Any]:
    """Call LLM to analyze requirements and return {structured_requirement, routing_decision}.
    The new prompt asks for a single JSON with both fields. Falls back to legacy NL parsing.
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

    # Strip markdown code fences
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
        parsed = _json.loads(text)
    except Exception:
        return _parse_nl_requirement(text, edit_scope, text_prompt)

    # New format: {"routing_decision": "...", "structured_requirement": {...}}
    if "structured_requirement" in parsed and "routing_decision" in parsed:
        req = parsed["structured_requirement"]
        routing = parsed["routing_decision"]
        if routing not in _VALID_ROUTING_DECISIONS:
            routing = "design"
        req["_routing_decision"] = routing
        return req

    # Fallback: LLM returned the old flat structure directly
    return parsed


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
            "style_consistency": 0.6,
            "novelty": 0.2,
        },
        "hint_layout": hint_layout,
        "hint_style": hint_style,
        "hint_adjuster": hint_adjuster,
    }



def visual_preprocessing_local(state: DesignBridgeState) -> dict[str, Any]:
    """Local Visual Preprocessing: run depth + segmentation on the initial image (if provided)."""
    user = state.get("user_input") or {}
    image_path = user.get("initial_image")
    task_id = state.get("task_id") or "no_task_id"

    vision_features: dict[str, Any] = {"geometry_constraints": {}}

    if image_path:
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
            if artifacts.depth_path:
                vision_features["depth"] = artifacts.depth_path
            if artifacts.segmentation_path:
                vision_features["segmentation"] = artifacts.segmentation_path
            if artifacts.segmentation_meta_path:
                vision_features["segmentation_meta"] = artifacts.segmentation_meta_path
        except Exception as e:
            print(f"⚠️  Visual preprocessing failed ({e}), falling back to empty vision_features")

    return {"vision_features": vision_features}


def _route_decision(state: DesignBridgeState) -> RoutingDecision:
    """Fallback rule-based routing（LLM 失敗時）：預設走 design。"""
    return "design"


def design_director(state: DesignBridgeState) -> dict[str, Any]:
    """
    路由決策節點。
    優先使用 requirement_analyzer 已由 LLM 決定的 routing_decision（語意理解）。
    若尚未設定（LLM 失敗 fallback），才執行 rule-based routing。
    """
    if state.get("routing_decision"):
        print(f"[design_director] routing_decision already set: {state['routing_decision']}, skipping")
        return {}

    routing_decision = _route_decision(state)
    print(f"[design_director] fallback rule-based routing: {routing_decision}")
    return {"routing_decision": routing_decision}



def layout_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    from designbridge.layout_agent import run_layout_agent

    task_id = state.get("task_id") or str(uuid.uuid4())
    req = state.get("structured_requirement") or {}

    try:
        result = run_layout_agent(req, task_id)
    except Exception as e:
        print(f"⚠️ Layout agent failed ({e}), skipping layout")
        return {
            "intermediate_outputs": {
                **(state.get("intermediate_outputs") or {}),
                "layout_agent": f"failed: {e}",
            }
        }

    return {
        "scene_graph": result.get("scene_graph"),
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            **(result.get("intermediate_outputs") or {}),
        },
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


def _analyze_style_image_with_gemini(image_path: str) -> str:
    """Use Gemini vision to extract a concise style description from a reference image.
    Returns an English string ready to append to a generation prompt.
    """
    try:
        from designbridge.llm import call_llm

        analysis_prompt = (
            "Analyze this interior design style reference image. "
            "Describe concisely in English: color palette, materials and textures, "
            "furniture style, lighting mood, and overall atmosphere. "
            "Output only the description (no headers, no bullet points), "
            "suitable for appending to an image generation prompt. Under 60 words."
        )
        desc = call_llm(analysis_prompt, images=[image_path])
        return desc.strip()
    except Exception as e:
        print(f"⚠️  Gemini style image analysis failed: {e}")
        return ""


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


def _layout_json_to_prompt_text(layout_json: dict[str, Any]) -> str:
    """Convert depth_to_layout JSON into a concise English layout directive for the prompt."""
    analysis = layout_json.get("space_analysis") or {}
    space_type = analysis.get("space_type", "standard_room").replace("_", " ")
    perspective = analysis.get("camera_perspective", "eye_level").replace("_", " ")
    circulation = analysis.get("circulation_score", 0.5)

    parts: list[str] = [
        f"Spatial layout reference: {space_type} with {perspective} camera angle.",
    ]

    if circulation > 0.7:
        parts.append("Keep clear open floor space in the foreground for circulation.")
    elif circulation < 0.3:
        parts.append("Foreground area may include furniture pieces.")

    candidates = layout_json.get("furniture_candidates") or []
    if candidates:
        furniture_hints = [
            f"{c['type'].replace('_', ' ')} at {c['position']}"
            for c in candidates[:4]
            if c.get("confidence") == "high" or c.get("size_ratio", 0) > 0.04
        ]
        if furniture_hints:
            parts.append("Maintain similar furniture arrangement: " + ", ".join(furniture_hints) + ".")

    rec = layout_json.get("layout_recommendation") or {}
    anchor = rec.get("anchor_furniture") or []
    if anchor:
        keeps = [f"{a['furniture'].replace('_', ' ')} at {a['position']}" for a in anchor[:2]]
        if keeps:
            parts.append("Anchor pieces to preserve: " + ", ".join(keeps) + ".")

    metrics = (analysis.get("spatial_metrics") or {})
    symmetry = metrics.get("left_right_symmetry", 1.0)
    if symmetry > 0.9:
        parts.append("Preserve left-right spatial symmetry.")

    return " ".join(parts)


OutputAspect = Literal["auto", "1:1", "4:3", "3:4", "16:9", "9:16"]
_ASPECT_RATIO_MAP: dict[OutputAspect, float] = {
    "auto": 1.0,
    "1:1": 1.0,
    "4:3": 4.0 / 3.0,
    "3:4": 3.0 / 4.0,
    "16:9": 16.0 / 9.0,
    "9:16": 9.0 / 16.0,
}


def _round_to_multiple(value: int, multiple: int, min_value: int, max_value: int) -> int:
    rounded = max(min_value, min(max_value, int(round(value / multiple) * multiple)))
    return rounded


def _resolve_output_size(
    output_aspect: str,
    initial_image_path: str | None,
    long_edge: int = 1024,
    min_edge: int = 512,
    max_edge: int = 1344,
) -> tuple[int, int]:
    aspect_key: OutputAspect = output_aspect if output_aspect in _ASPECT_RATIO_MAP else "auto"
    ratio = _ASPECT_RATIO_MAP[aspect_key]

    if aspect_key == "auto" and initial_image_path and Path(initial_image_path).is_file():
        try:
            from PIL import Image

            with Image.open(initial_image_path) as img:
                w, h = img.size
            if w > 0 and h > 0:
                ratio = w / h
        except Exception:
            ratio = 1.0

    if ratio >= 1.0:
        width = long_edge
        height = int(round(long_edge / ratio))
    else:
        height = long_edge
        width = int(round(long_edge * ratio))

    width = _round_to_multiple(width, multiple=64, min_value=min_edge, max_value=max_edge)
    height = _round_to_multiple(height, multiple=64, min_value=min_edge, max_value=max_edge)
    return width, height


def _renderer_placeholder_image(
    out_path: Path,
    task_id: str,
    prompt: str,
    output_size: tuple[int, int],
) -> None:
    """Save a placeholder image (PIL) when SDXL is unavailable."""
    from PIL import Image, ImageDraw

    width, height = output_size
    img = Image.new("RGB", (width, height), color=(240, 240, 245))
    draw = ImageDraw.Draw(img)
    margin_x = max(30, int(width * 0.1))
    margin_y = max(30, int(height * 0.1))
    draw.rectangle(
        [margin_x, margin_y, width - margin_x, height - margin_y],
        fill=(255, 255, 255),
        outline=(180, 180, 190),
    )
    text = "DesignBridge\n(placeholder)"
    try:
        draw.text((width // 2, height // 2), text, fill=(100, 100, 110), anchor="mm")
    except Exception:
        draw.text((margin_x + 10, height // 2), "DesignBridge placeholder", fill=(100, 100, 110))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


# 快取模型，不用每次都載入
_sdxl_pipeline: Any = None
_controlnet_pipeline: Any = None
_flux_redux_prior: Any = None
_flux_redux_pipe: Any = None


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


def _render_hf_inference(
    prompt: str,
    out_path: Path,
    model: str = "",
    output_size: tuple[int, int] = (1024, 1024),
) -> bool:
    """
    Generate image via Hugging Face Inference API.
    No local model download. Returns True on success.
    """
    import secrets

    api_key = Config.HF_TOKEN
    if not api_key:
        return False
    try:
        from huggingface_hub import InferenceClient

        client = InferenceClient(
            provider=Config.HF_INFERENCE_PROVIDER,
            api_key=api_key,
        )
        # secrets.randbelow 使用 OS 真隨機源（/dev/urandom），
        # 避免 random 在多 worker / fork 下重複相同序列
        seed = secrets.randbelow(2**31)
        print(f"🎲 HF Inference seed: {seed}")
        width, height = output_size
        image = client.text_to_image(
            prompt,
            model=model,
            seed=seed,
            width=width,
            height=height,
        )
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


def _render_hf_inference_redux(
    prompt: str,
    style_image_path: str,
    out_path: Path,
    output_size: tuple[int, int] = (1024, 1024),
) -> bool:
    """
    Generate image via FLUX.1-Redux-dev using a style reference image + text prompt.
    Tries JSON payload (image base64 + prompt) first; falls back to raw image bytes.
    Returns True on success.
    """
    api_key = Config.HF_TOKEN
    if not api_key:
        return False
    try:
        import base64
        import io
        import requests
        from PIL import Image

        style_img = Image.open(style_image_path).convert("RGB")
        buf = io.BytesIO()
        style_img.save(buf, format="JPEG", quality=90)
        image_bytes = buf.getvalue()
        width, height = output_size

        url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-Redux-dev"
        auth_header = {"Authorization": f"Bearer {api_key}"}

        print(f"🎨 FLUX.1-Redux 風格參考生圖：{Path(style_image_path).name}")

        # 優先：JSON payload 帶入 prompt，讓文字需求也影響生成
        payload: dict = {
            "inputs": base64.b64encode(image_bytes).decode(),
            "parameters": {"width": width, "height": height},
        }
        if prompt.strip():
            payload["parameters"]["prompt"] = prompt.strip()

        response = requests.post(
            url,
            headers={**auth_header, "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )

        # 若 API 不支援 JSON 格式，退回純圖片 bytes
        if response.status_code in (400, 422):
            print(f"⚠️  FLUX.1-Redux JSON payload 不支援，改用 raw image bytes")
            response = requests.post(
                url,
                headers={**auth_header, "Content-Type": "image/jpeg"},
                data=image_bytes,
                timeout=120,
            )

        if response.status_code != 200:
            print(f"⚠️  FLUX.1-Redux HTTP {response.status_code}: {response.text[:200]}")
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        result_img = Image.open(io.BytesIO(response.content))
        result_img.save(str(out_path))
        return True
    except Exception as e:
        import traceback
        print(f"⚠️  FLUX.1-Redux render failed ({type(e).__name__}: {e})")
        traceback.print_exc()
        return False


def _render_hf_kontext(
    prompt: str,
    depth_path: str,
    out_path: Path,
    strength: float = 0.70,
) -> bool:
    """Generate image via Kontext LoRA using depth map as spatial reference through Replicate."""
    api_key = Config.HF_TOKEN
    if not api_key:
        return False
    try:
        from huggingface_hub import InferenceClient

        with open(depth_path, "rb") as f:
            input_image = f.read()

        client = InferenceClient(
            provider=Config.KONTEXT_PROVIDER,
            api_key=api_key,
        )
        image = client.image_to_image(
            input_image,
            prompt=f"redepthkontext {prompt}, same camera angle and perspective as reference",
            model=Config.KONTEXT_LORA_MODEL,
            strength=strength,
        )
        if image is None:
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(out_path))
        print(f"[kontext] Generated via {Config.KONTEXT_PROVIDER}")
        return True
    except Exception as e:
        import traceback
        print(f"⚠️  Kontext render failed ({type(e).__name__}: {e})")
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


def _get_flux_redux_pipelines():
    """Load FLUX.1-Redux prior + FLUX.1-dev backbone once and cache them.
    CPU 推理非常慢（30 分鐘以上 / 張），建議有 GPU 再用。
    需要 HF_TOKEN 且已接受 black-forest-labs/FLUX.1-dev 授權。
    """
    global _flux_redux_prior, _flux_redux_pipe
    if _flux_redux_prior is not None and _flux_redux_pipe is not None:
        return _flux_redux_prior, _flux_redux_pipe

    from diffusers import FluxPriorReduxPipeline, FluxPipeline
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32

    # CPU 模式明確指定 device_map=None，避免 accelerate 用 meta tensor 初始化
    # 造成後續 .to() / enable_sequential_cpu_offload() 失敗
    load_kwargs: dict = {"torch_dtype": dtype}
    if device == "cpu":
        load_kwargs["device_map"] = None

    print("⏳ 載入 FLUX.1-Redux prior（首次約需數分鐘下載）...")
    _flux_redux_prior = FluxPriorReduxPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-Redux-dev",
        **load_kwargs,
    )

    print("⏳ 載入 FLUX.1-dev backbone（含文字編碼器，支援 prompt + 風格圖）...")
    _flux_redux_pipe = FluxPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-dev",
        **load_kwargs,
    )

    if device == "cuda":
        # GPU 模式：model cpu offload 讓各層推理完即釋放 VRAM，峰值從 ~50GB 降到約 8-12GB
        _flux_redux_prior.enable_model_cpu_offload()
        _flux_redux_pipe.enable_model_cpu_offload()
    else:
        # CPU 模式：模型已直接載入 CPU RAM，無需額外 offload
        print("⚠️  CPU 模式：推理速度極慢，每張可能需要 30 分鐘以上")

    print("✅ FLUX.1-Redux 載入完成")
    return _flux_redux_prior, _flux_redux_pipe


def _render_flux_redux_local(
    style_image_path: str,
    out_path: Path,
    prompt: str = "",
    num_steps: int = 4,
    guidance_scale: float = 3.5,
    output_size: tuple[int, int] = (512, 512),
    text_weight: float = 0.35,
) -> bool:
    """Generate image via local FLUX.1-Redux pipeline using a style reference image + text prompt.

    text_weight controls how much the text prompt steers the global semantic direction
    via CLIP pooled_prompt_embeds (0.0 = pure image style, 1.0 = pure text direction).
    prompt_embeds (T5-equivalent spatial path) always comes from the Redux image encoder.
    """
    try:
        from PIL import Image
        import torch

        pipe_prior, pipe = _get_flux_redux_pipelines()
        style_img = Image.open(style_image_path).convert("RGB")
        width, height = output_size
        print(f"🎨 FLUX.1-Redux 本地推理中（{width}×{height}，steps={num_steps}）...")

        prior_out = pipe_prior(style_img)

        pipe_kwargs: dict = {
            "guidance_scale": guidance_scale,
            "num_inference_steps": num_steps,
            "height": height,
            "width": width,
            **prior_out,  # prompt_embeds + pooled_prompt_embeds，均來自圖像
        }

        if prompt.strip() and text_weight > 0.0 and pipe.text_encoder is not None:
            # CLIP 路（pooled_prompt_embeds）：用文字的全局語意向量取代/混合圖像的
            # T5 路（prompt_embeds）保持 Redux 圖像版本不動，維持視覺風格細節
            clip_inputs = pipe.tokenizer(
                [prompt.strip()],
                padding="max_length",
                max_length=77,
                truncation=True,
                return_tensors="pt",
            )
            with torch.no_grad():
                text_pooled = pipe.text_encoder(
                    clip_inputs.input_ids.to(pipe.text_encoder.device),
                    output_hidden_states=False,
                ).pooler_output  # [1, 768]

            image_pooled = prior_out.get("pooled_prompt_embeds")
            if image_pooled is not None and text_weight < 1.0:
                # 在圖像 pooled 和文字 pooled 之間插值，保留圖像風格的全局感
                pipe_kwargs["pooled_prompt_embeds"] = (
                    (1.0 - text_weight) * image_pooled + text_weight * text_pooled
                )
            else:
                pipe_kwargs["pooled_prompt_embeds"] = text_pooled

            print(f"   文字語意注入 text_weight={text_weight}：{prompt[:60]}...")

        result = pipe(**pipe_kwargs).images[0]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(str(out_path))
        return True
    except Exception as e:
        err = str(e)
        if "GatedRepo" in err or "local cache" in err or "connection" in err.lower():
            print(f"⚠️  FLUX.1-Redux 無法載入（模型未下載或授權未接受）：{err[:120]}")
            print("    → 請至 https://huggingface.co/black-forest-labs/FLUX.1-Redux-dev 接受授權後重試")
        else:
            import traceback
            print(f"⚠️  FLUX.1-Redux 本地推理失敗：{e}")
            traceback.print_exc()
        return False


def _render_flux_redux_fal(
    style_image_path: str,
    out_path: Path,
    prompt: str = "",
    num_steps: int = 28,
    guidance_scale: float = 3.5,
    output_size: tuple[int, int] = (1024, 1024),
) -> bool:
    """Generate image via fal.ai FLUX.1-Redux API (cloud, fast)."""
    fal_key = Config.FAL_KEY
    if not fal_key:
        return False
    try:
        import fal_client
        import requests
        import os

        os.environ["FAL_KEY"] = fal_key

        print("☁️  fal.ai FLUX.1-Redux 推理中...")

        # 上傳本地風格圖到 fal.ai storage
        with open(style_image_path, "rb") as f:
            image_url = fal_client.upload(f.read(), content_type="image/jpeg")

        width, height = output_size
        size_map = {
            (1024, 1024): "square_hd",
            (512, 512): "square",
            (1024, 768): "landscape_4_3",
            (768, 1024): "portrait_4_3",
            (1280, 720): "landscape_16_9",
            (720, 1280): "portrait_16_9",
        }
        image_size = size_map.get((width, height), {"width": width, "height": height})

        arguments: dict = {
            "image_url": image_url,
            "num_inference_steps": num_steps,
            "guidance_scale": guidance_scale,
            "image_size": image_size,
        }
        if prompt.strip():
            arguments["prompt"] = prompt.strip()

        result = fal_client.subscribe(
            "fal-ai/flux-1/dev/redux",
            arguments=arguments,
            with_logs=False,
        )

        img_url = result["images"][0]["url"]
        resp = requests.get(img_url, timeout=60)
        resp.raise_for_status()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
        print(f"✅ fal.ai FLUX.1-Redux 完成：{out_path.name}")
        return True

    except ImportError:
        print("⚠️  fal_client 未安裝，請執行：pip install fal-client")
        return False
    except Exception as e:
        print(f"⚠️  fal.ai FLUX.1-Redux 失敗：{e}")
        return False


def _render_flux_ipadapter_fal(
    style_image_path: str,
    out_path: Path,
    prompt: str,
    ip_adapter_scale: float = 0.6,
    num_steps: int = 28,
    guidance_scale: float = 3.5,
    output_size: tuple[int, int] = (1024, 1024),
) -> bool:
    """Generate image via fal.ai FLUX-general + XLabs IP-Adapter.

    Text prompt (T5 full sequence) controls room type and content.
    Style reference image controls visual style via IP-Adapter cross-attention.
    ip_adapter_scale: 0.0 = ignore image, 1.0 = full style transfer.
    """
    fal_key = Config.FAL_KEY
    if not fal_key:
        return False
    if not prompt.strip():
        print("⚠️  fal.ai IP-Adapter 需要文字 prompt 描述目標空間")
        return False
    try:
        import fal_client
        import requests
        import os

        os.environ["FAL_KEY"] = fal_key

        print("☁️  fal.ai FLUX-general + IP-Adapter 推理中...")

        with open(style_image_path, "rb") as f:
            image_url = fal_client.upload(f.read(), content_type="image/jpeg")

        width, height = output_size
        size_map = {
            (1024, 1024): "square_hd",
            (512, 512): "square",
            (1024, 768): "landscape_4_3",
            (768, 1024): "portrait_4_3",
            (1280, 720): "landscape_16_9",
            (720, 1280): "portrait_16_9",
        }
        image_size = size_map.get((width, height), {"width": width, "height": height})

        arguments: dict = {
            "prompt": prompt.strip(),
            "num_inference_steps": num_steps,
            "guidance_scale": guidance_scale,
            "image_size": image_size,
            "ip_adapters": [
                {
                    "path": "XLabs-AI/flux-ip-adapter",
                    "weight_name": "ip_adapter.safetensors",
                    "image_encoder_path": "openai/clip-vit-large-patch14",
                    "image_url": image_url,
                    "scale": ip_adapter_scale,
                }
            ],
        }

        result = fal_client.subscribe(
            "fal-ai/flux-general",
            arguments=arguments,
            with_logs=False,
        )

        img_url = result["images"][0]["url"]
        resp = requests.get(img_url, timeout=60)
        resp.raise_for_status()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
        print(f"✅ fal.ai FLUX IP-Adapter 完成：{out_path.name}")
        return True

    except ImportError:
        print("⚠️  fal_client 未安裝，請執行：pip install fal-client")
        return False
    except Exception as e:
        print(f"⚠️  fal.ai FLUX IP-Adapter 失敗：{e}")
        return False


def _render_sdxl(
    prompt: str,
    out_path: Path,
    control_image: str | Path | None = None,
    negative_prompt: str | None = None,
    output_size: tuple[int, int] = (1024, 1024),
) -> bool:
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
        width, height = output_size

        if model_type == "flux":
            pipe = _get_flux_pipeline()
            generator = torch.Generator(device=device).manual_seed(torch.randint(0, 2**32, (1,)).item())
            image = pipe(
                prompt=prompt,
                num_inference_steps=steps,
                guidance_scale=0.0,
                generator=generator,
                width=width,
                height=height,
            ).images[0]

        elif model_type == "sd":
            pipe = _get_sd_pipeline()
            image = pipe(prompt=prompt, num_inference_steps=steps, width=width, height=height).images[0]

        else:  # sdxl (default)
            if Config.ENABLE_CONTROLNET and control_image and Path(control_image).exists():
                pipe = _get_controlnet_pipeline()
                control_img = Image.open(control_image).convert("RGB")
                control_img = control_img.resize((width, height), Image.Resampling.LANCZOS)
                image = pipe(
                    prompt=prompt,
                    image=control_img,
                    num_inference_steps=steps,
                    controlnet_conditioning_scale=Config.CONTROLNET_CONDITIONING_SCALE,
                ).images[0]
            else:
                pipe = _get_sdxl_pipeline()
                kwargs = {
                    "prompt": prompt,
                    "num_inference_steps": steps,
                    "width": width,
                    "height": height,
                }
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
    # 加入隨機短碼，確保每次生成都是獨立新檔案（避免 task_id 相同時回傳舊圖）
    render_suffix = uuid.uuid4().hex[:8]
    out_path = render_dir / f"{task_id}_{render_suffix}.png"

    prompt = _build_imagen_prompt_from_requirement(req, style_params=style_params)
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
        "prompt_preview": prompt[:200],
        "negative_prompt_preview": (negative_prompt or "")[:200],
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
    style_method = user_input.get("style_method", "ai_analysis")
    style_reference_image = user_input.get("style_reference_image")
    user_style_reference_local: str | None = None
    if isinstance(style_reference_image, str) and style_reference_image.strip():
        style_reference_candidate = style_reference_image.strip()
        if Path(style_reference_candidate).exists():
            user_style_reference_local = style_reference_candidate
        elif style_reference_candidate.startswith(("http://", "https://")):
            try:
                from designbridge.style_supabase import download_style_image

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
                prompt = f"{prompt} Style reference: {_kb_text}"
                print(f"📚 Supabase KB 描述已注入 prompt（跳過 Gemini 分析）：{_kb_text[:80]}…")
            else:
                style_vision_desc = _analyze_style_image_with_gemini(user_style_reference_local)
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
        elif _render_flux_ipadapter_fal(
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
        elif Config.FAL_KEY and _render_flux_redux_fal(user_style_reference_local, out_path, prompt=prompt, output_size=output_size, num_steps=Config.FAL_REDUX_STEPS, guidance_scale=Config.FAL_REDUX_GUIDANCE):
            backend = "flux_redux_fal"
            generation_params["model"] = "fal-ai/flux-1/dev/redux"
            generation_params["style_reference"] = user_style_reference_local
        elif _render_flux_redux_local(user_style_reference_local, out_path, prompt=prompt, output_size=output_size):
            backend = "flux_redux_local"
            generation_params["model"] = "black-forest-labs/FLUX.1-Redux-dev (local)"
            generation_params["style_reference"] = user_style_reference_local

    # Kontext LoRA via Replicate：有 depth map 時優先，保留空間結構
    _SPATIAL_STRENGTH = {"none": 0.55, "minor": 0.60, "major": 0.75}
    spatial_level = (req.get("spatial_change_level") or "minor").lower()
    kontext_strength = _SPATIAL_STRENGTH.get(spatial_level, 0.70)

    if backend == "placeholder" and Config.HF_TOKEN:
        if depth_path and Path(str(depth_path)).is_file():
            if _render_hf_kontext(prompt, str(depth_path), out_path, strength=kontext_strength):
                backend = "hf_kontext"
                generation_params["model"] = Config.KONTEXT_LORA_MODEL
                generation_params["provider"] = Config.KONTEXT_PROVIDER
                generation_params["kontext_strength"] = kontext_strength

    # AI 分析模式 fallback：HF Inference API
    if backend == "placeholder" and Config.ENABLE_HF_INFERENCE and Config.HF_TOKEN:
        if _render_hf_inference(prompt, out_path, model=hf_model_id, output_size=output_size):
            backend = "hf_inference"
            generation_params["model"] = hf_model_id
            generation_params["provider"] = Config.HF_INFERENCE_PROVIDER

    # API 都失敗 → 回報錯誤，不走本地 fallback
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


def clip_evaluator_node(state: DesignBridgeState) -> dict[str, Any]:
    """Run CLIP evaluation on the generated image against the user's original input.

    Translates the raw user text_prompt to English before scoring so that the
    English-trained CLIP model can compare faithfully against what the user asked for.
    """
    image_path = state.get("generated_image")
    user = state.get("user_input") or {}
    raw_prompt = (user.get("text_prompt") or "").strip()

    if not image_path or not Path(image_path).is_file():
        return {"evaluation_result": {"scores": {}, "weighted_score": 0.0, "decision": "skip", "feedback": "no generated image", "issues_found": [], "suggestions": []}}

    if not raw_prompt:
        return {"evaluation_result": {"scores": {}, "weighted_score": 0.0, "decision": "skip", "feedback": "no text prompt", "issues_found": [], "suggestions": []}}

    try:
        from designbridge.clip_evaluator import evaluate, _translate_to_english
        text_prompt = _translate_to_english(raw_prompt)
        result = evaluate(image_path, text_prompt)
    except Exception as e:
        result = {"scores": {}, "weighted_score": 0.0, "decision": "skip", "feedback": f"CLIP evaluation failed: {e}", "issues_found": [], "suggestions": []}

    return {"evaluation_result": result}
