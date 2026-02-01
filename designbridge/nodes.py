# designbridge/nodes.py
"""DesignBridge graph nodes: Requirement Analyzer, Visual Preprocessing stub, Design Director, Renderer, agent stubs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from designbridge.config import Config
from designbridge.prompts import REQUIREMENT_ANALYZER_PROMPT
from designbridge.state import DesignBridgeState, RoutingDecision
from designbridge.vision import run_visual_preprocessing


def requirement_analyzer(state: DesignBridgeState) -> dict[str, Any]:
    """
    Parse user_input into structured_requirement (JSON) using Gemini API.
    Falls back to rule-based if API key not set or API fails.
    """
    user = state.get("user_input") or {}
    text_prompt = (user.get("text_prompt") or "").strip()
    edit_scope = float(user.get("edit_scope", 0.5))
    initial_image = user.get("initial_image", "無")

    task_id = state.get("task_id") or str(uuid.uuid4())
    iteration = state.get("iteration", 0)

    # Try Gemini API first
    try:
        api_key = Config.get_gemini_api_key()
        structured_requirement = _call_gemini_requirement_analyzer(
            text_prompt, edit_scope, initial_image, api_key
        )
    except (ValueError, Exception) as e:
        print(f"⚠️  Gemini API not available or failed ({e}), falling back to rule-based")
        structured_requirement = _rule_based_requirement_analyzer(text_prompt, edit_scope)

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


def _call_gemini_requirement_analyzer(
    text_prompt: str, edit_scope: float, initial_image: str, api_key: str
) -> dict[str, Any]:
    """Call Gemini API to analyze requirements and return structured JSON.
    When initial_image is a valid file path, sends the image to Gemini Vision (multimodal).
    """
    try:
        import base64

        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(Config.GEMINI_MODEL)

        prompt = REQUIREMENT_ANALYZER_PROMPT.format(
            text_prompt=text_prompt,
            edit_scope=edit_scope,
            initial_image=initial_image,
        )

        # Build content: image + text when image path is valid (Gemini Vision)
        use_vision = _is_valid_image_path(initial_image)
        if use_vision:
            try:
                uploaded_file = genai.upload_file(path=initial_image)
                contents = [uploaded_file, prompt]
            except Exception:
                # Fallback: inline image data (e.g. if upload_file fails or is unavailable)
                path = Path(initial_image)
                suffix = path.suffix.lower()
                mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
                mime_type = mime_map.get(suffix, "image/jpeg")
                img_bytes = path.read_bytes()
                image_part = {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(img_bytes).decode("ascii")}}
                contents = [image_part, prompt]
        else:
            contents = prompt

        response = model.generate_content(
            contents,
            generation_config=genai.GenerationConfig(
                temperature=Config.GEMINI_TEMPERATURE,
            ),
        )

        # Extract JSON from response
        text = response.text.strip()
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        structured = json.loads(text)
        return structured

    except ImportError:
        raise ValueError(
            "google-generativeai not installed. Run: pip install google-generativeai"
        )
    except Exception as e:
        raise RuntimeError(f"Gemini API call failed: {e}")


def _rule_based_requirement_analyzer(text_prompt: str, edit_scope: float) -> dict[str, Any]:
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

    styles = ["北歐", "現代", "工業", "簡約", "minimal", "modern", "scandinavian"]
    primary_style = next((s for s in styles if s in text), "現代")

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
            "primary_style": primary_style,
            "secondary_style": None,
            "color_palette": [],
            "material_preferences": [],
            "style_strength": 0.7,
            "reference_images": [],
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
    Design Director: route task to Layout / Style / Adjuster / Layout+Style
    based on structured_requirement and vision_features.
    """
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
    """Stub for Style agent. Real impl: LoRA / IP-Adapter, etc."""
    return {
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            "style_agent": "stub_output",
        }
    }


def adjuster_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """Stub for Design Adjuster. Real impl: Inpainting, etc."""
    return {
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            "adjuster_agent": "stub_output",
        }
    }


def layout_and_style_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """Stub for Layout + Style collaboration. Real impl: both agents + rendering."""
    return {
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            "layout_and_style_agent": "stub_output",
        }
    }


def _build_imagen_prompt_from_requirement(req: dict[str, Any]) -> str:
    """Build an English text prompt for Imagen from structured_requirement."""
    meta = req.get("meta") or {}
    style_prefs = req.get("style_preferences") or {}
    room_type = meta.get("room_type", "living_room").replace("_", " ")
    primary_style = style_prefs.get("primary_style", "modern")
    color_palette = style_prefs.get("color_palette") or []
    colors = ", ".join(str(c) for c in color_palette[:3]) if color_palette else "neutral tones"
    return (
        f"Interior design visualization: a {room_type} room, {primary_style} style, "
        f"colors {colors}. Photorealistic, well-lit, high quality."
    )


def _renderer_placeholder_image(out_path: Path, task_id: str, prompt: str) -> None:
    """Save a placeholder image (PIL) when Imagen is unavailable."""
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


# Cached SDXL pipeline (loaded once, reused for subsequent renders)
_sdxl_pipeline: Any = None
_controlnet_pipeline: Any = None


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


def _render_sdxl(prompt: str, out_path: Path, control_image: str | Path | None = None) -> bool:
    """
    Generate image with local SDXL. If control_image is provided and ControlNet is enabled,
    uses ControlNet pipeline with depth guidance. Returns True on success.
    """
    try:
        import torch
        from PIL import Image
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        steps = Config.SDXL_STEPS
        if device == "cpu":
            steps = min(steps, 20)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use ControlNet if enabled and control_image is provided
        if Config.ENABLE_CONTROLNET and control_image and Path(control_image).exists():
            pipe = _get_controlnet_pipeline()
            control_img = Image.open(control_image).convert("RGB")
            # Resize control image to match SDXL's expected resolution (1024x1024 or similar)
            control_img = control_img.resize((1024, 1024), Image.Resampling.LANCZOS)
            
            image = pipe(
                prompt=prompt,
                image=control_img,
                num_inference_steps=steps,
                controlnet_conditioning_scale=Config.CONTROLNET_CONDITIONING_SCALE,
            ).images[0]
        else:
            # Fallback to standard SDXL without ControlNet
            pipe = _get_sdxl_pipeline()
            image = pipe(prompt=prompt, num_inference_steps=steps).images[0]
        
        image.save(str(out_path))
        return True
    except Exception as e:
        print(f"⚠️  SDXL render failed ({e})")
        return False


def renderer(state: DesignBridgeState) -> dict[str, Any]:
    """
    Renderer: generate image from structured_requirement.
    Order: Imagen API (if billing) -> local SDXL (free) -> placeholder.
    """
    task_id = state.get("task_id") or str(uuid.uuid4())
    req = state.get("structured_requirement") or {}
    artifacts_root = Path(Config.ARTIFACTS_DIR)
    render_dir = artifacts_root / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    out_path = render_dir / f"{task_id}.png"

    prompt = _build_imagen_prompt_from_requirement(req)
    generation_params: dict[str, Any] = {"prompt_preview": prompt[:200]}
    backend = "placeholder"
    
    # Get vision features for ControlNet (if available)
    vision = state.get("vision_features") or {}
    depth_path = vision.get("depth")
    seg_path = vision.get("segmentation")
    controlnet_inputs: dict[str, str] = {}
    if depth_path:
        controlnet_inputs["depth"] = str(depth_path)
    if seg_path:
        controlnet_inputs["segmentation"] = str(seg_path)

    # 1. Try Imagen (requires billed account)
    try:
        api_key = Config.get_gemini_api_key()
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_images(
            model=Config.IMAGEN_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )
        if response.generated_images:
            gen_img = response.generated_images[0]
            if hasattr(gen_img, "image") and gen_img.image is not None and hasattr(gen_img.image, "image_bytes"):
                from io import BytesIO
                from PIL import Image
                img = Image.open(BytesIO(gen_img.image.image_bytes))
                img.save(str(out_path))
                backend = "imagen"
                generation_params["model"] = Config.IMAGEN_MODEL
            else:
                raise RuntimeError("Imagen response missing image_bytes")
        else:
            raise RuntimeError("Imagen returned no images")
    except Exception as e:
        print(f"⚠️  Imagen render failed ({e})")
        generation_params["imagen_error"] = str(e)

    # 2. If Imagen failed, try local SDXL (free, with ControlNet if depth available)
    if backend == "placeholder" and Config.ENABLE_SDXL_FALLBACK:
        # Use depth image for ControlNet guidance if available
        control_img = depth_path if depth_path and Path(depth_path).exists() else None
        if _render_sdxl(prompt, out_path, control_image=control_img):
            backend = "sdxl"
            generation_params["model"] = Config.SDXL_MODEL
            if control_img:
                generation_params["controlnet"] = "depth"
                generation_params["controlnet_scale"] = Config.CONTROLNET_CONDITIONING_SCALE
        else:
            generation_params["sdxl_error"] = "SDXL render failed"

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
