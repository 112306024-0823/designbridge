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

    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
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
