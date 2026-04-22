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

    @classmethod
    def get_dynamic_routing_enabled(cls) -> bool:
        return os.getenv("DESIGNBRIDGE_ENABLE_DYNAMIC_ROUTING", "false").lower() in ("1", "true", "yes")

    ROUTER_TEMPERATURE: float = float(os.getenv("DESIGNBRIDGE_ROUTER_TEMPERATURE", "0.0"))

    # Image generation (Imagen) - same API key as Gemini; requires billing
    IMAGEN_MODEL: str = os.getenv("DESIGNBRIDGE_IMAGEN_MODEL", "imagen-4.0-generate-001")
    # Local image generation backend: "sdxl" | "sd" | "flux" (read dynamically so runtime changes take effect)
    @classmethod
    def get_local_model_type(cls) -> str:
        return os.getenv("DESIGNBRIDGE_LOCAL_MODEL_TYPE", "sdxl").lower()

    # Model IDs for each backend
    SDXL_MODEL: str = os.getenv("DESIGNBRIDGE_SDXL_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
    SD_MODEL: str = os.getenv("DESIGNBRIDGE_SD_MODEL", "stabilityai/stable-diffusion-xl-base-1.0") #stabilityai/stable-diffusion-3.5-medium
    FLUX_MODEL: str = os.getenv("DESIGNBRIDGE_FLUX_MODEL", "black-forest-labs/FLUX.1-schnell")

    SDXL_STEPS: int = int(os.getenv("DESIGNBRIDGE_SDXL_STEPS", "25"))
    ENABLE_SDXL_FALLBACK: bool = os.getenv("DESIGNBRIDGE_ENABLE_SDXL_FALLBACK", "true").lower() in ("1", "true", "yes")

    # Hugging Face Inference API (cloud SDXL; no local download). Tried first when HF_TOKEN set. Uses HF_TOKEN.
    ENABLE_HF_INFERENCE: bool = os.getenv("DESIGNBRIDGE_ENABLE_HF_INFERENCE", "true").lower() in ("1", "true", "yes")
    HF_TOKEN: str | None = os.getenv("HF_TOKEN")
    HF_INFERENCE_PROVIDER: str = os.getenv("DESIGNBRIDGE_HF_INFERENCE_PROVIDER", "hf-inference")
    
    # ControlNet for SDXL (depth + segmentation guidance)
    ENABLE_CONTROLNET: bool = os.getenv("DESIGNBRIDGE_ENABLE_CONTROLNET", "true").lower() in ("1", "true", "yes")
    CONTROLNET_DEPTH_MODEL: str = "diffusers/controlnet-depth-sdxl-1.0"
    CONTROLNET_CONDITIONING_SCALE: float = 0.5  # Strength of ControlNet guidance (0.0-1.0)

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
