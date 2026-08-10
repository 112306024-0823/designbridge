# designbridge/router.py
"""LLM-based Router: uses call_llm (Gemini) + SkillRegistry for routing."""

from __future__ import annotations

import json
from typing import Optional, TYPE_CHECKING

from designbridge.state import RoutingDecision

if TYPE_CHECKING:
    from designbridge.skill_registry import SkillRegistry


class RouterLLMError(Exception):
    """Raised when the LLM router fails to produce a valid routing decision."""


# Alias map for tolerant parsing — longest keys first to avoid partial matches
# (e.g. "layout_and_style" must be checked before "layout")
_DECISION_ALIASES: dict[str, RoutingDecision] = {
    "layout_and_style": "layout_and_style",
    "layout and style": "layout_and_style",
    "layout+style":     "layout_and_style",
    "both":             "layout_and_style",
    "layout_planner":   "layout",
    "layout planner":   "layout",
    "layout":           "layout",
    "style_advisor":    "style",
    "style advisor":    "style",
    "style":            "style",
    "design_adjuster":  "design_adjuster",
    "design adjuster":  "design_adjuster",
    "adjuster":         "design_adjuster",
    "inpaint":          "design_adjuster",
}


def _safe_parse_decision(llm_output: str) -> Optional[RoutingDecision]:
    """
    Parse LLM output into a RoutingDecision with three fallback tiers.

    Tier 1: JSON parse → "routing_decision" key → alias map
    Tier 2: Full-text lowercase scan against alias keys (longest-first)
    Tier 3: return None
    """
    # Tier 1: JSON
    text = llm_output.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = text.rstrip("`").strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            raw = str(data.get("routing_decision", "")).strip().lower()
            if raw in _DECISION_ALIASES:
                return _DECISION_ALIASES[raw]
    except (json.JSONDecodeError, ValueError):
        pass

    # Tier 2: scan full text
    lower = llm_output.lower()
    for alias, decision in _DECISION_ALIASES.items():
        if alias in lower:
            return decision

    # Tier 3
    return None


# Need re for fence stripping
import re


def build_router_prompt(structured_requirement: dict, skill_descriptions: str) -> str:
    """Fill DESIGN_DIRECTOR_ROUTER_PROMPT template."""
    from designbridge.prompts import DESIGN_DIRECTOR_ROUTER_PROMPT

    requirement_json = json.dumps(structured_requirement, ensure_ascii=False, indent=2)
    return (
        DESIGN_DIRECTOR_ROUTER_PROMPT.replace("{skill_descriptions}", skill_descriptions)
        .replace("{requirement_json}", requirement_json)
    )


def call_llm_router(
    structured_requirement: dict,
    vision_features: dict,
    temperature: float = 0.0,
    registry: Optional["SkillRegistry"] = None,
    # Deprecated: kept for backward compat, ignored (llm.py handles auth)
    api_key: str = "",
    gemini_model: str = "",
    gemini_temperature: float | None = None,
) -> RoutingDecision:
    """
    Call LLM (Gemini) to decide routing based on structured_requirement and skill descriptions.

    Raises RouterLLMError if the LLM output cannot be parsed into a RoutingDecision.
    """
    if registry is None:
        from designbridge.skill_registry import get_registry
        registry = get_registry()

    # gemini_temperature kept for backward compat; takes precedence if explicitly passed
    resolved_temperature = gemini_temperature if gemini_temperature is not None else temperature

    skill_descriptions = registry.format_for_prompt()
    prompt = build_router_prompt(structured_requirement, skill_descriptions)

    try:
        from designbridge.llm import call_llm
        llm_output = call_llm(prompt, temperature=resolved_temperature)
    except Exception as e:
        raise RouterLLMError(f"LLM call failed: {e}")

    decision = _safe_parse_decision(llm_output)
    if decision is None:
        raise RouterLLMError(
            f"LLM router returned unparseable output: {llm_output[:200]!r}"
        )
    return decision
