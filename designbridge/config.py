# designbridge/config.py
"""Configuration for DesignBridge APIs."""

import os
from typing import Optional
import dotenv
dotenv.load_dotenv()


class Config:
    """DesignBridge configuration."""

    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    GEMINI_TEMPERATURE: float = 0.3

    # Image generation (Imagen) - same API key as Gemini; requires billing
    IMAGEN_MODEL: str = os.getenv("DESIGNBRIDGE_IMAGEN_MODEL", "imagen-4.0-generate-001")
    # Local SDXL fallback (free); set DESIGNBRIDGE_SDXL_MODEL to use another model
    SDXL_MODEL: str = os.getenv("DESIGNBRIDGE_SDXL_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
    SDXL_STEPS: int = int(os.getenv("DESIGNBRIDGE_SDXL_STEPS", "25"))
    ENABLE_SDXL_FALLBACK: bool = os.getenv("DESIGNBRIDGE_ENABLE_SDXL_FALLBACK", "true").lower() in ("1", "true", "yes")

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
