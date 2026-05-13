# designbridge/state.py
"""DesignBridge LangGraph state schema per DesignBridge.md."""

from typing import Any, Literal
from typing_extensions import NotRequired, TypedDict

from designbridge.schemas import (
    EvalFeedbackJSON,
    RequirementJSON,
    RenderResultJSON,
    SceneGraphJSON,
    StyleParamsJSON,
    TaskPlanJSON,
    VisionJSON,
)

# Routing decision: which agent(s) Design Director assigns
RoutingDecision = Literal["layout", "style", "design_adjuster", "layout_and_style"]


class UserInput(TypedDict):
    """User input: image (optional), text prompt, edit scope (0~1)."""

    initial_image: NotRequired[str]  # image_path_or_id, optional for empty layout
    text_prompt: str
    edit_scope: float  # 0~1
    output_aspect: NotRequired[Literal["auto", "1:1", "4:3", "3:4", "16:9", "9:16"]]
    style_profile_id: NotRequired[str]  # optional aggregated style profile to apply directly
    style_reference_image: NotRequired[str]  # optional style reference image path
    family_needs: NotRequired[list[str]]   # e.g. ["children", "wheelchair", "pets"]
    fengshui_rules: NotRequired[list[str]] # e.g. ["bed_not_facing_door", ...]


class DesignBridgeState(TypedDict):
    """Global state shared across all DesignBridge agents."""

    task_id: NotRequired[str]
    iteration: NotRequired[int]
    # User input
    user_input: NotRequired[UserInput]
    # Requirement Analyzer output (RequirementJSON)
    structured_requirement: NotRequired[RequirementJSON]
    # Vision Preprocessor output (VisionJSON)
    vision_features: NotRequired[VisionJSON]
    # Design Director output (TaskPlanJSON)
    task_plan: NotRequired[TaskPlanJSON]
    routing_decision: NotRequired[RoutingDecision]
    # Agent outputs
    style_params: NotRequired[StyleParamsJSON]
    scene_graph: NotRequired[SceneGraphJSON]
    # Renderer output
    render_result: NotRequired[RenderResultJSON]
    generated_image: NotRequired[str]
    # Depth layout extraction output
    layout_from_depth: NotRequired[dict[str, Any]]
    # Evaluator output
    evaluation_result: NotRequired[EvalFeedbackJSON]
    # Legacy / intermediate outputs (can be refactored later)
    intermediate_outputs: NotRequired[dict[str, Any]]