"""Requirement Analyzer graph node."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from designbridge.core.prompts import REQUIREMENT_ANALYZER_PROMPT
from designbridge.core.state import DesignBridgeState


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

    # Try LLM (Gemini) first, fall back to passing prompt directly on failure
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
        from designbridge.layout.special_constraints import enrich_requirement
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
    from designbridge.render.llm import call_llm

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
    except Exception as exc:
        raise ValueError(f"Requirement analyzer LLM returned unparseable JSON: {text[:200]!r}") from exc

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
