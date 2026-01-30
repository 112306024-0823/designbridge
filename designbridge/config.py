# designbridge/config.py
"""Configuration for DesignBridge APIs."""

import os
from typing import Optional


class Config:
    """DesignBridge configuration."""
    GEMINI_API_KEY: Optional[str] = "AIzaSyBCwpO4Jb2078IK-jB5xqhb_uPK7B1zHXk"  # local-only; do not commit

  
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TEMPERATURE: float = 0.3 

    # Local vision preprocessing (MiDaS depth + UPerNet segmentation)
    # NOTE: These models will be downloaded on first run (requires internet).
    ENABLE_DEPTH: bool = True
    ENABLE_SEGMENTATION: bool = True

    # Depth (MiDaS-style DPT). Good default: smaller and widely supported.
    DEPTH_MODEL: str = "Intel/dpt-hybrid-midas"
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
