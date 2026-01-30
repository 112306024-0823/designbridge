# designbridge/schemas.py
"""Complete JSON schema definitions for DesignBridge agents per specification."""

from typing import Any, Literal
from typing_extensions import NotRequired, TypedDict


# ========== Requirement JSON ==========
class RequirementMeta(TypedDict):
    """Meta information about the design task."""

    room_type: str  # e.g. "living_room", "bedroom", "kitchen"
    design_goal: Literal["new_design", "renovation"]
    user_experience_level: NotRequired[str]  # "professional" | "general"


class SpaceInfo(TypedDict):
    """Spatial information from user or Vision."""

    estimated_size: NotRequired[dict[str, float]]  # {"width": ..., "height": ..., "depth": ...}
    windows: NotRequired[list[dict[str, Any]]]  # [{"position": ..., "size": ...}, ...]
    doors: NotRequired[list[dict[str, Any]]]


class StylePreferences(TypedDict):
    """Style-related preferences."""

    primary_style: str  # e.g. "北歐", "現代", "工業"
    secondary_style: NotRequired[str]  # For mixed styles
    color_palette: NotRequired[list[str]]  # ["#FFFFFF", "white", ...]
    material_preferences: NotRequired[list[str]]  # ["wood", "marble", ...]
    style_strength: float  # 0.0 (subtle) ~ 1.0 (strong)
    reference_images: NotRequired[list[str]]  # For IP-Adapter / CLIP


class LayoutConstraints(TypedDict):
    """Layout constraints from user."""

    must_keep: NotRequired[list[str]]  # Furniture to keep
    must_add: NotRequired[list[str]]  # Furniture to add
    must_remove: NotRequired[list[str]]  # Furniture to remove
    immutable_regions: NotRequired[list[dict[str, Any]]]  # No-change regions
    functional_zones: NotRequired[list[dict[str, Any]]]  # Work/rest zones


class EditScope(TypedDict):
    """Edit scope parameters."""

    scope_value: float  # 0.0 ~ 1.0
    allowed_operations: NotRequired[list[str]]  # ["inpaint", "layout", "style"]


class PriorityWeights(TypedDict):
    """Priority weights for evaluation."""

    layout_rationality: float
    style_consistency: float
    novelty: float


class RequirementJSON(TypedDict):
    """Complete requirement specification (output of Requirement Analyzer)."""

    meta: RequirementMeta
    space_info: NotRequired[SpaceInfo]
    style_preferences: StylePreferences
    layout_constraints: NotRequired[LayoutConstraints]
    edit_scope: EditScope
    priority_weights: PriorityWeights
    # Routing hints (for Design Director)
    hint_layout: NotRequired[bool]
    hint_style: NotRequired[bool]
    hint_adjuster: NotRequired[bool]


# ========== Vision JSON ==========
class VisionJSON(TypedDict):
    """Output of Visual Preprocessor."""

    segmentation: NotRequired[str | Any]  # path or tensor
    segmentation_meta: NotRequired[str | dict[str, Any]]  # class labels, present objects
    depth: NotRequired[str | Any]  # path or tensor
    geometry_constraints: NotRequired[dict[str, Any]]  # Immutable regions, spatial relations
    scene_objects: NotRequired[list[dict[str, Any]]]  # Detected objects for cross-validation


# ========== Task/Plan JSON ==========
class TaskPlanJSON(TypedDict):
    """Output of Design Director: task assignment and plan."""

    assigned_agents: list[str]  # ["layout", "style"] or ["adjuster"]
    generation_mode: Literal["layout_and_style", "style_only", "layout_only", "inpaint"]
    constraints_summary: dict[str, Any]
    priority_order: NotRequired[list[str]]


# ========== Style Params JSON ==========
class StyleParamsJSON(TypedDict):
    """Output of Style Designer: style control parameters for Renderer."""

    style_prompt: str
    negative_prompt: NotRequired[str]
    style_strength: float
    lora_weights: NotRequired[dict[str, float]]  # {"lora_name": weight}
    ip_adapter_images: NotRequired[list[str]]
    color_guidance: NotRequired[dict[str, Any]]


# ========== Scene Graph JSON ==========
class SceneGraphJSON(TypedDict):
    """Output of Space Planner: layout solution for Renderer."""

    furniture_placements: list[dict[str, Any]]  # [{"id": ..., "type": ..., "position": ..., "rotation": ...}]
    spatial_relations: NotRequired[list[dict[str, Any]]]
    layout_prompt: str  # Text description for ControlNet guidance
    layout_constraints_met: dict[str, bool]


# ========== Adjust Plan JSON ==========
class AdjustPlanJSON(TypedDict):
    """Output of Design Adjuster: inpainting plan."""

    inpaint_regions: list[dict[str, Any]]  # [{"mask": ..., "prompt": ..., "strength": ...}]
    protected_regions: NotRequired[list[dict[str, Any]]]
    consistency_guidance: str


# ========== Render Result JSON ==========
class RenderResultJSON(TypedDict):
    """Output of Renderer: generated image + metadata."""

    generated_image_path: str
    generation_params: dict[str, Any]  # Model, seed, steps, etc.
    controlnet_inputs: NotRequired[dict[str, str]]  # {"depth": ..., "segmentation": ...}
    timestamp: str


# ========== Eval/Feedback JSON ==========
class EvalFeedbackJSON(TypedDict):
    """Output of Evaluator: scores and decision."""

    scores: dict[str, float]  # {"layout_rationality": ..., "style_consistency": ..., "novelty": ...}
    weighted_score: float
    decision: Literal["continue", "stop"]
    feedback: str
    issues_found: NotRequired[list[str]]
    suggestions: NotRequired[list[str]]
