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

    # Depth conditioning backend for re-planned layouts (uses the scene-graph projected depth):
    #   "kontext"    → Kontext depth-fusion LoRA (loose reference depth, current default)
    #   "controlnet" → true FLUX depth ControlNet via fal.ai (stronger geometric control; needs FAL_KEY)
    LAYOUT_DEPTH_CONTROL_BACKEND: str = os.getenv("DESIGNBRIDGE_LAYOUT_DEPTH_CONTROL_BACKEND", "kontext")
    DEPTH_CONTROLNET_MODEL: str = os.getenv(
        "DESIGNBRIDGE_DEPTH_CONTROLNET_MODEL", "Shakker-Labs/FLUX.1-dev-ControlNet-Depth"
    )

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
    # Project scene-graph furniture boxes into a perspective depth map for ControlNet.
    # When true and the user re-plans layout, this projected depth overrides the
    # input-photo depth so the precise coordinates actually control the render.
    ENABLE_LAYOUT_DEPTH_PROJECTION: bool = os.getenv(
        "DESIGNBRIDGE_ENABLE_LAYOUT_DEPTH_PROJECTION", "true"
    ).lower() in ("1", "true", "yes")
    # Calibrated against FLUX Kontext renders: pitch=-16 framed the room far better
    # than -6/-8 (more floor visible, furniture distribution matched the depth boxes).
    LAYOUT_PROJECTION_HFOV: float = float(os.getenv("DESIGNBRIDGE_LAYOUT_PROJECTION_HFOV", "65.0"))
    LAYOUT_PROJECTION_PITCH: float = float(os.getenv("DESIGNBRIDGE_LAYOUT_PROJECTION_PITCH", "-16.0"))
    LAYOUT_PROJECTION_SETBACK: float = float(os.getenv("DESIGNBRIDGE_LAYOUT_PROJECTION_SETBACK", "0.8"))

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
