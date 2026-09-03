# designbridge/config.py
"""Configuration for DesignBridge APIs."""

import os
from pathlib import Path

import dotenv

# Load .env from project root (parent of designbridge package) so it works from any cwd
_root = Path(__file__).resolve().parent.parent
dotenv.load_dotenv(_root / ".env")
dotenv.load_dotenv()  # Allow override from current working directory


class Config:
    """DesignBridge configuration."""

    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    GEMINI_TEMPERATURE: float = 0.3


    # xAI Grok — independent OpenAI-compatible client, key: GROK_API_KEY or XAI_API_KEY.
    XAI_MODEL: str = os.getenv("DESIGNBRIDGE_XAI_MODEL", "grok-3")
    XAI_BASE_URL: str = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
    XAI_API_KEY: str = os.getenv("GROK_API_KEY")

    # Style retrieval mode for Supabase reference search: "text-to-image" | "text-to-text"
    STYLE_RETRIEVAL_MODE: str = os.getenv("DESIGNBRIDGE_STYLE_RETRIEVAL_MODE", "text-to-image")
    # Text-only embedding model for text-to-text style retrieval.
    TEXT_EMBEDDING_MODEL: str = os.getenv("DESIGNBRIDGE_TEXT_EMBEDDING_MODEL", "BAAI/bge-m3")

    @classmethod
    def get_dynamic_routing_enabled(cls) -> bool:
        return os.getenv("DESIGNBRIDGE_ENABLE_DYNAMIC_ROUTING", "false").lower() in ("1", "true", "yes")

    ROUTER_TEMPERATURE: float = float(os.getenv("DESIGNBRIDGE_ROUTER_TEMPERATURE", "0.0"))

    LITELLM_MODEL: str = os.getenv("LITELLM_MODEL", "gemini/gemini-2.5-flash-lite")
    LITELLM_FALLBACK_MODEL: str = os.getenv("LITELLM_FALLBACK_MODEL", "gemini/gemini-2.5-flash-lite")

    # Image generation (Imagen) - same API key as Gemini; requires billing
    IMAGEN_MODEL: str = os.getenv("DESIGNBRIDGE_IMAGEN_MODEL", "imagen-4.0-generate-001")
    # Local image generation backend: always Flux
    @classmethod
    def get_local_model_type(cls) -> str:
        return "flux"

    # Model ID for Flux
    FLUX_MODEL: str = os.getenv("DESIGNBRIDGE_FLUX_MODEL", "black-forest-labs/FLUX.1-schnell")

    # Inpainting model (SD 1.5-based; runwayml/stable-diffusion-inpainting is publicly available)
    INPAINT_MODEL: str = os.getenv("DESIGNBRIDGE_INPAINT_MODEL", "runwayml/stable-diffusion-inpainting")

    FLUX_STEPS: int = int(os.getenv("DESIGNBRIDGE_FLUX_STEPS", "4"))
    ENABLE_FLUX_FALLBACK: bool = os.getenv("DESIGNBRIDGE_ENABLE_FLUX_FALLBACK", "true").lower() in ("1", "true", "yes")

    # fal.ai Inference API (cloud inpainting via FLUX.1-Fill)
    FAL_KEY: str | None = os.getenv("FAL_KEY")
    FAL_INPAINT_MODEL: str = os.getenv("DESIGNBRIDGE_FAL_INPAINT_MODEL", "fal-ai/flux-pro/v1/fill")

    # Hugging Face Inference API (cloud Flux; no local download). Tried first when HF_TOKEN set.
    ENABLE_HF_INFERENCE: bool = os.getenv("DESIGNBRIDGE_ENABLE_HF_INFERENCE", "true").lower() in ("1", "true", "yes")
    HF_TOKEN: str | None = os.getenv("HF_TOKEN")
    HF_INFERENCE_PROVIDER: str = os.getenv("DESIGNBRIDGE_HF_INFERENCE_PROVIDER", "hf-inference")
    FAL_REDUX_STEPS: int = int(os.getenv("FAL_REDUX_STEPS", "28"))
    FAL_REDUX_GUIDANCE: float = float(os.getenv("FAL_REDUX_GUIDANCE", "3.5"))
    ENABLE_FLUX_REDUX: bool = os.getenv("DESIGNBRIDGE_ENABLE_FLUX_REDUX", "false").lower() in ("1", "true", "yes")
    FAL_IP_ADAPTER_STEPS: int = int(os.getenv("FAL_IP_ADAPTER_STEPS", "28"))
    FAL_IP_ADAPTER_GUIDANCE: float = float(os.getenv("FAL_IP_ADAPTER_GUIDANCE", "3.5"))
    FAL_IP_ADAPTER_SCALE: float = float(os.getenv("FAL_IP_ADAPTER_SCALE", "0.6"))
    FAL_IP_ADAPTER_SIZE: int = int(os.getenv("FAL_IP_ADAPTER_SIZE", "512"))

    # Kontext LoRA (reference + depth fusion) via Replicate
    KONTEXT_LORA_MODEL: str = "thedeoxen/FLUX.1-Kontext-dev-reference-depth-fusion-LORA"
    KONTEXT_PROVIDER: str = os.getenv("DESIGNBRIDGE_KONTEXT_PROVIDER", "fal-ai")

    # Layout → 3D depth ControlNet: project the 2D floor plan into an eye-level depth
    # map and drive a FLUX depth ControlNet so the render honors furniture positions.
    # Requires FAL_KEY. Used in the layout-driven (text→design, no uploaded photo) flow.
    ENABLE_LAYOUT_CONTROLNET: bool = os.getenv(
        "DESIGNBRIDGE_ENABLE_LAYOUT_CONTROLNET", "true"
    ).lower() in ("1", "true", "yes")
    FAL_DEPTH_CONTROLNET_MODEL: str = os.getenv(
        "DESIGNBRIDGE_FAL_DEPTH_CONTROLNET_MODEL",
        "Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro",
    )
    # control_mode for the FLUX Union ControlNet on fal (string enum):
    # canny | tile | depth | blur | pose | gray | low-quality
    FAL_DEPTH_CONTROL_MODE: str = os.getenv("DESIGNBRIDGE_FAL_DEPTH_CONTROL_MODE", "depth")

    # The layout control uses TWO stacked controls on the Union model:
    #   • Canny of the furniture floor-FOOTPRINTS — the PRIMARY, faithful placement
    #     signal (distance-independent; footprints not cuboids, so the model still
    #     renders real furniture not boxes). This carries position AND size, so it is
    #     weighted strongly — under-weighting it is what let furniture drift off-plan.
    #   • Depth of the room shell — SECONDARY, mostly walls/window structure. From the
    #     elevated near-top-down camera, low furniture blends into the floor in depth,
    #     so depth is a weak furniture signal and is kept low on purpose.
    FAL_EDGE_CONDITIONING_SCALE: float = float(
        os.getenv("DESIGNBRIDGE_FAL_EDGE_CONDITIONING_SCALE", "0.35")
    )
    FAL_DEPTH_CONDITIONING_SCALE: float = float(
        os.getenv("DESIGNBRIDGE_FAL_DEPTH_CONDITIONING_SCALE", "0.30")
    )
    FAL_DEPTH_STEPS: int = int(os.getenv("DESIGNBRIDGE_FAL_DEPTH_STEPS", "42"))
    FAL_DEPTH_GUIDANCE: float = float(os.getenv("DESIGNBRIDGE_FAL_DEPTH_GUIDANCE", "4.2"))

    # Restrict the layout controls to the EARLY denoising steps only. Structure locks
    # in during the first steps; ending control early (e.g. 0.7 = first 70% of steps)
    # then lets the model freely resolve materials, lighting and realistic furniture
    # detail — directly easing the "full-strength control hurts plausibility" problem.
    # 1.0 = control the whole run (old behaviour).
    FAL_DEPTH_CONTROL_END: float = float(os.getenv("DESIGNBRIDGE_FAL_DEPTH_CONTROL_END", "0.4"))
    # Edges carry placement (not shape). Long enough to lock furniture onto the plan,
    # but ended before the final steps so the footprint canny fades instead of surviving
    # as visible floor wireframes in the render.
    FAL_EDGE_CONTROL_END: float = float(os.getenv("DESIGNBRIDGE_FAL_EDGE_CONTROL_END", "0.55"))

    # Draw furniture in the layout depth map as rough semantic silhouettes
    # (bed = low platform + headboard, sofa = seat + backrest + armrests,
    # table/desk = tabletop on legs) instead of plain cuboids, so the model can infer
    # the furniture category from the shape. Falls back to cuboids when false.
    # Keep ON: the semantic silhouette in the depth map is what lets the model render
    # furniture as recognisable furniture. With it OFF, low furniture reads as flat
    # floor mats / grey boxes. The "white clay blob" failure was NOT caused by this —
    # it was an empty/meta prompt starving the render of material content (now fixed by
    # the empty-prompt fallback in render_prompt.py). Requires a real prompt to look good.
    ENABLE_SEMANTIC_SHAPES: bool = os.getenv(
        "DESIGNBRIDGE_ENABLE_SEMANTIC_SHAPES", "true"
    ).lower() in ("1", "true", "yes")

    # Elevated three-quarter "look-at room centre" camera for the layout control
    # images — spreads the floor layout out legibly (an eye-level view crushes it).
    # Footroom-tuned: a lower/further eye aimed slightly deeper lifts the FRONT wall
    # off the bottom edge, so front-of-room furniture (e.g. an accent armchair) stays
    # fully framed instead of being clipped into the bottom dead zone and dropped.
    LAYOUT_CAM_EYE_H: float = float(os.getenv("DESIGNBRIDGE_LAYOUT_CAM_EYE_H", "2.2"))
    LAYOUT_CAM_SETBACK: float = float(os.getenv("DESIGNBRIDGE_LAYOUT_CAM_SETBACK", "2.6"))
    LAYOUT_CAM_TARGET_H: float = float(os.getenv("DESIGNBRIDGE_LAYOUT_CAM_TARGET_H", "0.5"))
    LAYOUT_CAM_TARGET_DEPTH_FRAC: float = float(
        os.getenv("DESIGNBRIDGE_LAYOUT_CAM_TARGET_DEPTH_FRAC", "0.58")
    )
    LAYOUT_CAM_FOV: float = float(os.getenv("DESIGNBRIDGE_LAYOUT_CAM_FOV", "58"))

    # Local vision preprocessing (Depth + UPerNet segmentation)
    # NOTE: These models will be downloaded on first run (requires internet).
    ENABLE_DEPTH: bool = True
    ENABLE_SEGMENTATION: bool = True

    # Depth estimation: Depth Anything V2 (via HuggingFace Transformers).
    # Options: Small (24.8M) | Base (97.5M) | Large (335M, default)
    DEPTH_MODEL: str = "depth-anything/Depth-Anything-V2-Large-hf"
    # Semantic segmentation (UPerNet). Example checkpoint on HuggingFace.
    SEGMENTATION_MODEL: str = "openmmlab/upernet-convnext-small"

    # Where to write artifacts (depth/segmentation outputs)
    ARTIFACTS_DIR: str = os.getenv("DESIGNBRIDGE_ARTIFACTS_DIR", "artifacts")

    # Layout agent
    LAYOUT_MAX_ITER: int = int(os.getenv("DESIGNBRIDGE_LAYOUT_MAX_ITER", "3"))

    @classmethod
    def get_gemini_api_key(cls) -> str:
        """Get Gemini API key from config or environment."""
        if cls.GEMINI_API_KEY:
            return cls.GEMINI_API_KEY
        raise ValueError(
            "GEMINI_API_KEY not set. Please set it in config.py or as environment variable."
        )

    @classmethod
    def get_xai_api_key(cls) -> str | None:
        """xAI API key for Grok. Prefer GROK_API_KEY, accept XAI_API_KEY alias."""
        return os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")
