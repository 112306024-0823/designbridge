# designbridge/nodes.py
"""DesignBridge graph nodes: Requirement Analyzer, Visual Preprocessing stub, Design Director, agent stubs."""

from __future__ import annotations

import json
import uuid
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


def _call_gemini_requirement_analyzer(
    text_prompt: str, edit_scope: float, initial_image: str, api_key: str
) -> dict[str, Any]:
    """Call Gemini API to analyze requirements and return structured JSON."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(Config.GEMINI_MODEL)

        prompt = REQUIREMENT_ANALYZER_PROMPT.format(
            text_prompt=text_prompt,
            edit_scope=edit_scope,
            initial_image=initial_image,
        )

        response = model.generate_content(
            prompt,
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
