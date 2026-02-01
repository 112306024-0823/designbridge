"""Local vision preprocessing for DesignBridge.

Implements:
- Depth estimation via HuggingFace Transformers:
  - Depth Anything V2 (Small/Base/Large) - recommended, finer details
  - Intel MiDaS DPT (legacy fallback)
- Semantic segmentation (UPerNet) via HuggingFace Transformers

Outputs are saved to disk and returned as file paths, so they can be stored in LangGraph state.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VisionArtifacts:
    """Paths to vision preprocessing outputs on disk."""

    depth_path: str | None = None
    segmentation_path: str | None = None
    segmentation_meta_path: str | None = None


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_device() -> tuple[str, int]:
    """Return (device_str, device_index_for_pipeline)."""
    try:
        import torch

        if torch.cuda.is_available():
            return ("cuda", 0)
    except Exception:
        # If torch isn't installed yet, default to CPU.
        pass
    return ("cpu", -1)


@lru_cache(maxsize=1)
def _load_depth_model(model_name: str) -> Any:
    """Load Depth Anything V2 model and processor once (cached)."""
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    processor = AutoImageProcessor.from_pretrained(model_name)
    model = AutoModelForDepthEstimation.from_pretrained(model_name)

    device, _ = _get_device()
    if device == "cuda":
        import torch

        model = model.to(torch.device("cuda"))
    model.eval()
    return processor, model


def run_depth_estimation(image_path: str, *, model_name: str, out_dir: Path) -> tuple[str, Path]:
    """Run depth estimation and save a PNG depth map."""
    import numpy as np
    import torch
    import torch.nn.functional as F
    from PIL import Image

    processor, model = _load_depth_model(model_name)

    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    device, _ = _get_device()
    if device == "cuda":
        inputs = {k: v.to("cuda") for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        predicted_depth = outputs.predicted_depth  # (B, H, W)

    # Upsample to original size
    depth = F.interpolate(
        predicted_depth.unsqueeze(1),
        size=image.size[::-1],
        mode="bicubic",
        align_corners=False,
    ).squeeze()

    depth_np = depth.cpu().numpy()
    # Normalize to 0..255 for visualization
    d_min, d_max = float(depth_np.min()), float(depth_np.max())
    if d_max - d_min < 1e-8:
        depth_norm = np.zeros_like(depth_np, dtype=np.uint8)
    else:
        depth_norm = ((depth_np - d_min) / (d_max - d_min) * 255.0).astype(np.uint8)

    ensure_dir(out_dir)
    depth_out = out_dir / "depth.png"
    Image.fromarray(depth_norm).save(depth_out)
    return str(depth_out), depth_out


@lru_cache(maxsize=1)
def _load_upernet(model_name: str) -> Any:
    """Load UPerNet segmentation model and processor once (cached)."""
    from transformers import AutoImageProcessor, UperNetForSemanticSegmentation

    processor = AutoImageProcessor.from_pretrained(model_name)
    model = UperNetForSemanticSegmentation.from_pretrained(model_name)

    device, _ = _get_device()
    if device == "cuda":
        import torch

        model = model.to(torch.device("cuda"))
    model.eval()
    return processor, model


def run_segmentation(
    image_path: str,
    *,
    model_name: str,
    out_dir: Path,
) -> tuple[str, str, Path]:
    """Run semantic segmentation and save label map PNG + a JSON metadata file."""
    import json

    import numpy as np
    import torch
    import torch.nn.functional as F
    from PIL import Image

    processor, model = _load_upernet(model_name)
    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")

    device, _ = _get_device()
    if device == "cuda":
        inputs = {k: v.to("cuda") for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits  # (B, C, h, w)

    # Upsample logits to original size
    up = F.interpolate(
        logits,
        size=image.size[::-1],
        mode="bilinear",
        align_corners=False,
    )
    seg = up.argmax(dim=1)[0].detach().cpu().numpy().astype(np.uint16)

    ensure_dir(out_dir)
    seg_out = out_dir / "segmentation.png"
    # Save as 16-bit PNG label map (class ids)
    Image.fromarray(seg, mode="I;16").save(seg_out)

    # Build simple metadata: id2label + present class ids
    id2label = getattr(model.config, "id2label", {}) or {}
    present_ids = sorted({int(x) for x in np.unique(seg).tolist()})
    present_labels = {str(i): id2label.get(i, "unknown") for i in present_ids}

    meta = {
        "model": model_name,
        "present_class_ids": present_ids,
        "present_labels": present_labels,
    }
    meta_out = out_dir / "segmentation_meta.json"
    meta_out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return str(seg_out), str(meta_out), meta_out


def run_visual_preprocessing(
    image_path: str,
    *,
    task_id: str,
    enable_depth: bool,
    enable_segmentation: bool,
    depth_model: str,
    segmentation_model: str,
    artifacts_root: Path,
) -> VisionArtifacts:
    """Run local visual preprocessing and save outputs."""
    out_dir = ensure_dir(artifacts_root / "vision" / task_id)

    depth_path: str | None = None
    seg_path: str | None = None
    seg_meta_path: str | None = None

    if enable_depth:
        depth_path, _ = run_depth_estimation(image_path, model_name=depth_model, out_dir=out_dir)

    if enable_segmentation:
        seg_path, seg_meta_path, _ = run_segmentation(
            image_path, model_name=segmentation_model, out_dir=out_dir
        )

    return VisionArtifacts(
        depth_path=depth_path,
        segmentation_path=seg_path,
        segmentation_meta_path=seg_meta_path,
    )

