"""Quick style-application helpers based on aggregated Style KB profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from style_kb.styles import STYLES


STYLE_NAME_TO_ID = {name: style_id for style_id, name in STYLES}
STYLE_ID_SET = {style_id for style_id, _ in STYLES}


def get_aggregated_style_dir() -> Path:
    """Return the directory containing aggregated style profiles."""
    return Path(__file__).resolve().parent.parent / "style_kb" / "aggregated"


def list_available_style_profiles() -> list[dict[str, str]]:
    """List aggregated style profiles that currently exist on disk."""
    aggregated_dir = get_aggregated_style_dir()
    available: list[dict[str, str]] = []
    for style_id, style_name in STYLES:
        profile_path = aggregated_dir / f"{style_id}_aggregated.json"
        if profile_path.exists():
            available.append(
                {
                    "style_id": style_id,
                    "style_name": style_name,
                    "path": str(profile_path),
                }
            )
    return available


def load_aggregated_style(style_id: str) -> dict[str, Any] | None:
    """Load an aggregated style profile by style_id."""
    profile_path = get_aggregated_style_dir() / f"{style_id}_aggregated.json"
    if not profile_path.exists():
        return None
    return json.loads(profile_path.read_text(encoding="utf-8"))


def resolve_style_profile_id(
    req: dict[str, Any],
    user_input: dict[str, Any] | None = None,
) -> str | None:
    """Resolve which aggregated style profile should be used for this request."""
    user_input = user_input or {}
    explicit_style_id = (user_input.get("style_profile_id") or "").strip()
    if explicit_style_id:
        return explicit_style_id if explicit_style_id in STYLE_ID_SET else None

    style_prefs = req.get("style_preferences") or {}
    primary_style = str(style_prefs.get("primary_style") or "").strip()
    if not primary_style:
        return None
    # Case-insensitive check for English style IDs (e.g. "Modern" → "modern")
    primary_style_lower = primary_style.lower()
    if primary_style_lower in STYLE_ID_SET:
        return primary_style_lower
    return STYLE_NAME_TO_ID.get(primary_style)


def build_style_params(
    req: dict[str, Any],
    user_input: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build renderer-ready style parameters from an aggregated style profile."""
    style_profile_id = resolve_style_profile_id(req, user_input)
    if not style_profile_id:
        return None

    profile = load_aggregated_style(style_profile_id)
    if not profile:
        return None

    style_prefs = req.get("style_preferences") or {}
    statistics = profile.get("statistics") or {}
    ai_config = profile.get("ai_config") or {}
    style_profile = profile.get("style_profile") or {}

    style_strength = float(style_prefs.get("style_strength", 0.7))
    recommended_weight = float(ai_config.get("recommended_ip_adapter_weight", 0.85))
    blended_strength = round((style_strength + recommended_weight) / 2, 2)

    color_guidance = {
        "primary_color": statistics.get("primary_color"),
        "secondary_color": statistics.get("secondary_color"),
        "accent_color": statistics.get("accent_color"),
        "avg_color_temp_k": statistics.get("avg_color_temp_k"),
        "top_materials": statistics.get("top_materials") or [],
        "visual_essence": style_profile.get("visual_essence") or [],
    }

    return {
        "style_profile_id": profile.get("style_id", style_profile_id),
        "style_profile_name": profile.get("style_name", style_profile_id),
        "style_prompt": ai_config.get("unified_positive_prompt", ""),
        "negative_prompt": ai_config.get("unified_negative_prompt", ""),
        "style_strength": blended_strength,
        "color_guidance": color_guidance,
        "material_recommendations": style_profile.get("material_recommendations") or [],
        "controlnet_type": ai_config.get("controlnet_type", "depth"),
        "style_summary": style_profile.get("summary", ""),
        "source_profile_path": str(get_aggregated_style_dir() / f"{style_profile_id}_aggregated.json"),
    }