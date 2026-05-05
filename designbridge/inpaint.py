# designbridge/inpaint.py
"""Inpainting utilities for the Design Adjuster Agent.

Responsibilities:
- Pipeline loading & caching
- Mask generation from segmentation or fallback
- Prompt construction
- Inpainting execution
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from designbridge.config import Config

# ---------------------------------------------------------------------------
# Pipeline cache
# ---------------------------------------------------------------------------

_inpaint_pipeline: Any = None


def _is_inpaint_model_cached() -> bool:
    """檢查 inpainting 模型主要權重是否已在本機完整快取，不觸發下載。"""
    try:
        from huggingface_hub import try_to_load_from_cache, _CACHED_NO_EXIST
        # 檢查 unet 權重檔（最大、最後下載完的檔案）
        for filename in (
            "unet/diffusion_pytorch_model.safetensors",
            "unet/diffusion_pytorch_model.bin",
        ):
            result = try_to_load_from_cache(Config.INPAINT_MODEL, filename)
            if result is not None and result is not _CACHED_NO_EXIST:
                return True
        return False
    except Exception:
        return False


def _get_inpaint_pipeline():
    """Load SD Inpainting pipeline once and cache it."""
    global _inpaint_pipeline
    if _inpaint_pipeline is not None:
        return _inpaint_pipeline
    from diffusers import StableDiffusionInpaintPipeline
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    _inpaint_pipeline = StableDiffusionInpaintPipeline.from_pretrained(
        Config.INPAINT_MODEL,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    ).to(device)
    return _inpaint_pipeline


# ---------------------------------------------------------------------------
# Mask generation
# ---------------------------------------------------------------------------

def mask_from_segmentation(
    seg_path: str,
    seg_meta_path: str,
    target_labels: list[str],
    image_size: tuple[int, int],
) -> Any:
    """
    從語義分割圖產生 inpainting mask。
    白色（255）= 要修改的區域，黑色（0）= 保留。

    Args:
        seg_path: 分割圖路徑（16-bit label map PNG）
        seg_meta_path: 分割 metadata JSON 路徑（含 label → class_id 對應）
        target_labels: 要修改的物件名稱，例如 ["sofa", "chair"]
        image_size: 原始圖片尺寸 (width, height)

    Returns:
        PIL.Image mask（灰階）
    """
    import numpy as np
    from PIL import Image, ImageFilter

    seg_img = Image.open(seg_path)
    seg_array = np.array(seg_img)

    with open(seg_meta_path) as f:
        meta = json.load(f)

    # meta 格式: {"labels": {"0": "wall", "3": "sofa", ...}}
    label_to_id = {v: int(k) for k, v in meta.get("labels", {}).items()}

    mask_array = np.zeros(seg_array.shape, dtype=np.uint8)
    matched = []
    for label in target_labels:
        # 支援部分比對，例如 "sofa" 可以對到 "sofa_chair"
        for seg_label, class_id in label_to_id.items():
            if label.lower() in seg_label.lower() or seg_label.lower() in label.lower():
                mask_array[seg_array == class_id] = 255
                matched.append(seg_label)

    if not matched:
        # 找不到對應物件時，回傳中央區域 fallback
        return fallback_center_mask(image_size)

    mask = Image.fromarray(mask_array).resize(image_size)
    # 膨脹邊緣讓 inpainting 邊界更自然
    mask = mask.filter(ImageFilter.MaxFilter(15))
    return mask


def fallback_center_mask(image_size: tuple[int, int]) -> Any:
    """
    沒有 segmentation 時的 fallback：中央 50% 矩形區域。

    Args:
        image_size: (width, height)

    Returns:
        PIL.Image mask（灰階）
    """
    from PIL import Image, ImageDraw

    w, h = image_size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle([w // 4, h // 4, w * 3 // 4, h * 3 // 4], fill=255)
    return mask


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_inpaint_prompt(
    req: dict[str, Any],
    style_params: dict[str, Any] | None,
    target_objects: list[str],
) -> tuple[str, str]:
    """
    組 inpainting 的 positive / negative prompt。

    Args:
        req: structured_requirement（RequirementJSON）
        style_params: StyleParamsJSON（可為 None）
        target_objects: 要填入的物件，例如 ["blue sofa", "wooden chair"]

    Returns:
        (positive_prompt, negative_prompt)
    """
    style_prefs = req.get("style_preferences") or {}
    primary_style = style_prefs.get("primary_style", "modern")
    color_palette = style_prefs.get("color_palette") or []
    colors = ", ".join(str(c) for c in color_palette[:2]) if color_palette else ""

    base_prompt = ""
    negative_prompt = (
        "blurry, low quality, distorted, deformed, watermark, "
        "inconsistent lighting, unrealistic"
    )

    if style_params:
        base_prompt = style_params.get("style_prompt", "")
        neg = style_params.get("negative_prompt", "")
        if neg:
            negative_prompt = neg

    obj_desc = ", ".join(target_objects) if target_objects else "furniture"
    color_hint = f", {colors}" if colors else ""

    positive_prompt = (
        f"{obj_desc}{color_hint}, {primary_style} interior design style, "
        f"photorealistic, high quality, well-lit, seamless integration. "
        f"{base_prompt}"
    ).strip()

    return positive_prompt, negative_prompt


# ---------------------------------------------------------------------------
# Inpainting execution
# ---------------------------------------------------------------------------

def run_inpainting(
    image_path: str,
    mask: Any,
    prompt: str,
    negative_prompt: str,
    strength: float,
    out_path: Path,
) -> bool:
    """
    執行 SD inpainting，輸出修改後圖片。

    Args:
        image_path: 原始圖片路徑
        mask: PIL.Image 灰階 mask（白=修改，黑=保留）
        prompt: inpainting positive prompt
        negative_prompt: inpainting negative prompt
        strength: 修改幅度 0.4~0.9（越高改動越大）
        out_path: 輸出圖片路徑

    Returns:
        True = 成功，False = 失敗
    """
    if not _is_inpaint_model_cached():
        print(f"[SKIP] Inpainting model not cached yet: {Config.INPAINT_MODEL}")
        return False
    try:
        from PIL import Image

        pipe = _get_inpaint_pipeline()

        original = Image.open(image_path).convert("RGB")
        orig_w, orig_h = original.size

        # SD inpainting 要求 512x512
        target_size = (512, 512)
        image_resized = original.resize(target_size)
        mask_resized = mask.resize(target_size).convert("L")

        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image_resized,
            mask_image=mask_resized,
            strength=strength,
            num_inference_steps=30,
            guidance_scale=7.5,
        ).images[0]

        # 將結果貼回原始解析度（只更新 mask 區域）
        result_full = original.copy()
        result_back = result.resize((orig_w, orig_h))
        mask_full = mask.resize((orig_w, orig_h)).convert("L")
        result_full.paste(result_back, mask=mask_full)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        result_full.save(str(out_path))
        return True

    except Exception as e:
        import traceback
        print(f"⚠️  Inpainting failed ({type(e).__name__}: {e})")
        traceback.print_exc()
        return False


def run_hf_inpainting(
    image_path: str,
    mask: Any,
    prompt: str,
    out_path: Path,
) -> bool:
    """
    使用 Hugging Face Inference API 執行 inpainting（雲端，不需本地模型）。

    Args:
        image_path: 原始圖片路徑
        mask: PIL.Image 灰階 mask
        prompt: inpainting prompt
        out_path: 輸出路徑

    Returns:
        True = 成功，False = 失敗
    """
    if not Config.HF_TOKEN:
        return False
    try:
        from huggingface_hub import InferenceClient
        from PIL import Image
        import io

        client = InferenceClient(api_key=Config.HF_TOKEN)

        original = Image.open(image_path).convert("RGB").resize((512, 512))
        mask_resized = mask.resize((512, 512)).convert("L")

        # 轉 bytes
        img_bytes = io.BytesIO()
        original.save(img_bytes, format="PNG")
        mask_bytes = io.BytesIO()
        mask_resized.save(mask_bytes, format="PNG")

        result = client.image_to_image(
            image=img_bytes.getvalue(),
            prompt=prompt,
            model=Config.INPAINT_MODEL,
        )

        if result is None:
            return False

        out_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(str(out_path))
        return True

    except Exception as e:
        import traceback
        print(f"⚠️  HF Inpainting failed ({type(e).__name__}: {e})")
        traceback.print_exc()
        return False
