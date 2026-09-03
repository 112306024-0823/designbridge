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

# ---------------------------------------------------------------------------
# SAM 2 cache
# ---------------------------------------------------------------------------

_sam2_predictor: Any = None

# checkpoint 與 config 路徑（相對於本專案 model/ 資料夾）
_SAM2_CHECKPOINT = Path(__file__).parent.parent / "model" / "sam2" / "checkpoints" / "sam2.1_hiera_tiny.pt"
_SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"


def _get_sam2_predictor():
    """Load SAM 2 predictor once and cache it."""
    global _sam2_predictor
    if _sam2_predictor is not None:
        return _sam2_predictor
    if not _SAM2_CHECKPOINT.is_file():
        print(f"[SAM2] checkpoint not found: {_SAM2_CHECKPOINT}")
        return None
    try:
        import torch
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = build_sam2(_SAM2_CONFIG, str(_SAM2_CHECKPOINT), device=device)
        _sam2_predictor = SAM2ImagePredictor(model)
        print(f"[SAM2] predictor loaded on {device}")
        return _sam2_predictor
    except Exception as e:
        print(f"[SAM2] failed to load: {e}")
        return None


def _resolve_inpaint_size(
    image_size: tuple[int, int],
    max_edge: int = 512,
) -> tuple[int, int]:
    """
    計算 inpainting 的目標尺寸：等比縮放至 max_edge，並對齊 64 的倍數。
    SD 1.5 建議 512×512，最大不超過 768。
    """
    w, h = image_size
    scale = min(max_edge / max(w, h), 1.0)
    new_w = max(64, round(w * scale / 64) * 64)
    new_h = max(64, round(h * scale / 64) * 64)
    return int(new_w), int(new_h)


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

    # meta 格式: {"present_labels": {"0": "wall", "3": "sofa", ...}}
    labels_dict = meta.get("present_labels") or meta.get("labels") or {}
    label_to_id = {v: int(k) for k, v in labels_dict.items()}

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
    mask = mask.filter(ImageFilter.MaxFilter(7))
    return mask


# 背景類別：不應該被當作修改目標
# 包含 UPerNet/ADE20K 的實際標籤名稱（windowpane ≠ window）
_BG_LABELS = {
    "wall", "floor", "ceiling", "sky", "earth", "ground",
    "window", "windowpane", "windowpane, window",
    "door", "door, double; double, door",
    "stairs", "stairway", "stairway, staircase", "escalator",
    "column", "column, pillar", "step", "path",
    "fence", "fencing", "fence, fencing",
    "railing", "rail", "bannister", "balustrade",
    "building", "house", "skyscraper",
}


def expand_mask_by_segmentation(
    manual_mask: Any,
    seg_path: str,
    seg_meta_path: str,
    image_size: tuple[int, int],
    top_k: int = 2,
) -> tuple[Any, list[str]]:
    """
    方式二：手繪遮罩 → 自動偵測被觸碰的物件 → 展開成完整物件遮罩。

    回傳 (mask, selected_labels)：
    - mask: 展開後的遮罩圖
    - selected_labels: 選中的 class 名稱列表（供 prompt 補全使用）

    步驟：
    1. 把手繪遮罩縮放到 segmentation 尺寸
    2. 排除背景類別（floor, wall, ceiling...）
    3. 只取重疊比例最高的 top_k 個 class
    4. 把這些 class 的完整像素塗白 → 輸出完整物件遮罩
    """
    import numpy as np
    from PIL import Image, ImageFilter

    seg_img = Image.open(seg_path)
    seg_array = np.array(seg_img)
    seg_h, seg_w = seg_array.shape

    # 手繪遮罩縮放到 segmentation 尺寸
    drawn = manual_mask.resize((seg_w, seg_h), Image.NEAREST).convert("L")
    drawn_array = np.array(drawn) > 128

    if not drawn_array.any():
        return fallback_center_mask(image_size), []

    with open(seg_meta_path) as f:
        meta = json.load(f)
    labels_dict = meta.get("present_labels") or meta.get("labels") or {}

    drawn_count = int(drawn_array.sum())
    touched_ids = set(seg_array[drawn_array].tolist())

    # 計算每個 class 的重疊比例，排除背景
    candidates = []
    for cid in touched_ids:
        label = labels_dict.get(str(cid), "").strip().lower()
        if label in _BG_LABELS:
            continue
        overlap = int(((seg_array == cid) & drawn_array).sum())
        ratio = overlap / drawn_count
        candidates.append((ratio, cid, label))

    if not candidates:
        return fallback_center_mask(image_size), []

    # 只取重疊比例最高的 top_k 個
    candidates.sort(reverse=True)
    selected = candidates[:top_k]
    for ratio, cid, label in selected:
        print(f"[adjuster] expand: class {cid} ({label})  overlap={ratio:.1%}")

    selected_labels = [label for _, _, label in selected]

    # 把選中 class 的完整像素塗白
    valid_ids = [cid for _, cid, _ in selected]
    mask_array = np.zeros(seg_array.shape, dtype=np.uint8)
    for cid in valid_ids:
        mask_array[seg_array == cid] = 255

    mask = Image.fromarray(mask_array).resize(image_size, Image.NEAREST)
    mask = mask.filter(ImageFilter.MaxFilter(7))
    return mask, selected_labels


def sam2_mask_from_box(
    image_path: str,
    box_xyxy: tuple[int, int, int, int],
) -> Any:
    """以 bounding box 為 prompt 取得單一實例的精確遮罩（bool ndarray），失敗回傳 None。

    佈局路徑用這個把「語意類別的連通區域」精修成乾淨的實例輪廓：UPerNet 只給類別，
    連通區域只給粗略團塊，SAM 2 才切得出物件真正的邊界。
    """
    import numpy as np
    from PIL import Image

    predictor = _get_sam2_predictor()
    if predictor is None:
        return None
    try:
        import torch

        img_rgb = np.array(Image.open(image_path).convert("RGB"))
        with torch.inference_mode():
            predictor.set_image(img_rgb)
            masks, scores, _ = predictor.predict(
                box=np.asarray(box_xyxy), multimask_output=False
            )
        return masks[int(scores.argmax())].astype(bool)
    except Exception as e:
        print(f"[SAM2] box-prompt inference failed: {e}")
        return None


def generate_mask_with_sam2(
    image_path: str,
    drawn_mask: Any,
    image_size: tuple[int, int],
) -> tuple[Any, bool]:
    """
    使用 SAM 2 從手繪框生成精確的實例層級遮罩。

    步驟：
    1. 從手繪遮罩計算 bounding box
    2. 以 box 作為 SAM 2 的 prompt
    3. 回傳精確物件輪廓遮罩

    Args:
        image_path: 原始圖片路徑
        drawn_mask: 手繪遮罩 (PIL.Image)
        image_size: 原始圖片尺寸 (width, height)

    Returns:
        (mask, success): mask = PIL.Image L mode；success = 是否成功
    """
    import numpy as np
    from PIL import Image, ImageFilter

    predictor = _get_sam2_predictor()
    if predictor is None:
        return drawn_mask, False

    try:
        import torch

        # 從手繪遮罩計算 bounding box（xyxy 格式）
        drawn_arr = np.array(drawn_mask.convert("L")) > 128
        if not drawn_arr.any():
            return drawn_mask, False

        rows = np.any(drawn_arr, axis=1)
        cols = np.any(drawn_arr, axis=0)
        y_min, y_max = int(np.where(rows)[0][0]), int(np.where(rows)[0][-1])
        x_min, x_max = int(np.where(cols)[0][0]), int(np.where(cols)[0][-1])

        # 縮放 bounding box 到原圖座標（手繪遮罩可能是縮小版）
        dw, dh = drawn_mask.size
        w, h = image_size
        sx, sy = w / dw, h / dh
        pad = 8
        x_min = max(0, int(x_min * sx) - pad)
        y_min = max(0, int(y_min * sy) - pad)
        x_max = min(w - 1, int(x_max * sx) + pad)
        y_max = min(h - 1, int(y_max * sy) + pad)

        print(f"[SAM2] box prompt: ({x_min},{y_min}) -> ({x_max},{y_max})")

        img_rgb = np.array(Image.open(image_path).convert("RGB"))

        with torch.inference_mode():
            predictor.set_image(img_rgb)
            box = np.array([x_min, y_min, x_max, y_max])
            masks, scores, _ = predictor.predict(
                box=box,
                multimask_output=False,
            )

        best_idx = int(scores.argmax())
        sam_mask = masks[best_idx]  # bool H×W

        mask_img = Image.fromarray((sam_mask * 255).astype(np.uint8), mode="L")
        mask_img = mask_img.resize(image_size, Image.NEAREST)
        mask_img = mask_img.filter(ImageFilter.MaxFilter(7))

        print(f"[SAM2] instance mask generated, score={scores[best_idx]:.3f}")
        return mask_img, True

    except Exception as e:
        import traceback
        print(f"[SAM2] inference failed: {e}")
        traceback.print_exc()
        return drawn_mask, False


def run_lama_inpainting(
    image_path: str,
    mask: Any,
    out_path: Path,
) -> bool:
    """
    使用 LaMa 執行背景重建（純移除任務專用）。

    LaMa 專門針對大面積遮罩的背景重建最佳化，
    比 FLUX.1-Fill 更穩定於「移除後填空」場景。

    Args:
        image_path: 原始圖片路徑
        mask: PIL.Image L mode 遮罩（白=移除區域）
        out_path: 輸出圖片路徑

    Returns:
        True = 成功，False = 失敗
    """
    try:
        from simple_lama_inpainting import SimpleLama
        from PIL import Image

        lama = SimpleLama()
        original = Image.open(image_path).convert("RGB")
        orig_size = original.size

        mask_l = mask.convert("L")
        if mask_l.size != orig_size:
            mask_l = mask_l.resize(orig_size, Image.NEAREST)

        result = lama(original, mask_l)

        # 強制合成：mask 以外的像素還原為原圖，防止 LaMa 模糊化周圍區域
        # result 尺寸可能與 orig_size 不同（LaMa 內部縮放），先對齊
        import numpy as np
        if result.size != orig_size:
            result = result.resize(orig_size, Image.LANCZOS)
        orig_arr   = np.array(original)
        result_arr = np.array(result.convert("RGB"))
        mask_arr   = np.array(mask_l.resize(orig_size, Image.NEAREST))
        composite  = np.where(mask_arr[:, :, np.newaxis] > 128, result_arr, orig_arr)
        result = Image.fromarray(composite.astype(np.uint8))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(str(out_path))
        print(f"[LaMa] inpainting success -> {out_path.name}")
        return True

    except Exception as e:
        import traceback
        print(f"[LaMa] inpainting failed: {e}")
        traceback.print_exc()
        return False


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
        "people, person, human, man, woman, child, hands, face, "
        "animal, pet, cat, dog, bird, "
        "blurry, low quality, distorted, deformed, watermark, "
        "inconsistent lighting, unrealistic"
    )

    if style_params:
        base_prompt = style_params.get("style_prompt", "")
        neg = (style_params.get("negative_prompt") or "").strip(", ")
        if neg:
            negative_prompt = f"{negative_prompt}, {neg}"

    _special = req.get("special_constraints") or {}
    if _special.get("wheelchair"):
        negative_prompt = f"{negative_prompt}, wheelchair, wheelchair user, mobility aid, disability equipment"
    if _special.get("children"):
        negative_prompt = f"{negative_prompt}, child, children, baby, toddler, kid"
    if _special.get("pets"):
        negative_prompt = f"{negative_prompt}, cat, dog, bird, rabbit, hamster, pet, animal"

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

def load_mask_from_path(mask_path: str, image_size: tuple[int, int]) -> Any:
    """從路徑載入手繪遮罩並 resize 到 image_size。"""
    from PIL import Image
    mask = Image.open(mask_path).convert("L")
    return mask.resize(image_size)


def run_inpainting(
    image_path: str,
    mask: Any,
    prompt: str,
    negative_prompt: str,
    strength: float,
    out_path: Path,
    mask_path: str | None = None,
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

        # 優先使用手繪遮罩，否則用自動生成的 mask
        if mask_path:
            mask = load_mask_from_path(mask_path, (orig_w, orig_h))

        # Keep original aspect ratio instead of forcing square output.
        target_size = _resolve_inpaint_size((orig_w, orig_h))
        image_resized = original.resize(target_size)
        mask_resized = mask.resize(target_size).convert("L")

        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image_resized,
            mask_image=mask_resized,
            strength=strength,
            num_inference_steps=30,
            guidance_scale=2.5,
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


def run_fal_inpainting(
    image_path: str,
    mask: Any,
    prompt: str,
    out_path: Path,
    mask_path: str | None = None,
    num_steps: int = 28,
    guidance_scale: float = 3.5,
) -> bool:
    """
    使用 fal.ai FLUX.1-Fill 執行 inpainting（雲端，免下載模型）。

    Args:
        image_path: 原始圖片路徑
        mask: PIL.Image 灰階 mask（白=修改，黑=保留）
        prompt: inpainting prompt
        out_path: 輸出路徑
        mask_path: 若有手繪遮罩路徑，優先使用
        num_steps: 推理步數，移除任務建議 50，修改任務建議 28
        guidance_scale: prompt 跟隨強度，顏色修改建議調高至 5.0

    Returns:
        True = 成功，False = 失敗
    """
    if not Config.FAL_KEY:
        return False
    try:
        import base64
        import io
        import os
        import urllib.request
        import fal_client
        from PIL import Image

        os.environ.setdefault("FAL_KEY", Config.FAL_KEY)

        # 載入原圖
        original = Image.open(image_path).convert("RGB")
        orig_size = original.size  # (width, height)

        # 決定遮罩來源：手繪路徑 > 傳入的 PIL mask
        if mask_path and Path(mask_path).is_file():
            mask_img = Image.open(mask_path).convert("L")
        else:
            mask_img = mask.convert("L") if hasattr(mask, "convert") else mask

        # 確保 mask 與原圖尺寸一致（畫布是縮放版本，必須 resize 回原圖大小）
        if mask_img.size != orig_size:
            mask_img = mask_img.resize(orig_size, Image.NEAREST)

        # Debug：把實際傳給 fal.ai 的圖片和遮罩存到本地
        _debug_dir = out_path.parent / "fal_debug"
        _debug_dir.mkdir(parents=True, exist_ok=True)
        original.save(str(_debug_dir / "input_image.png"))
        mask_img.save(str(_debug_dir / "input_mask.png"))
        white_px = sum(1 for p in mask_img.getdata() if p > 128)
        total_px = mask_img.width * mask_img.height
        print(f"[fal] prompt: {prompt[:100]}")
        print(f"[fal] image size: {orig_size}")
        print(f"[fal] mask white px: {white_px}/{total_px} ({white_px/total_px:.1%})")
        print(f"[fal] debug files → {_debug_dir}")

        def _to_data_url(img: Any) -> str:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            return f"data:image/png;base64,{b64}"

        print(f"[fal] num_steps={num_steps}  guidance_scale={guidance_scale}")
        result = fal_client.subscribe(
            Config.FAL_INPAINT_MODEL,
            arguments={
                "prompt": prompt,
                "image_url": _to_data_url(original),
                "mask_url": _to_data_url(mask_img),
                "num_images": 1,
                "num_inference_steps": num_steps,
                "guidance_scale": guidance_scale,
                "output_format": "png",
                "safety_tolerance": "2",
            },
        )

        images = result.get("images") or []
        if not images:
            print("⚠️  fal.ai returned no images")
            return False

        result_url = images[0]["url"]
        print(f"✅  fal.ai inpainting success → {result_url[:60]}...")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(result_url, str(out_path))
        return True

    except Exception as e:
        import traceback
        print(f"⚠️  fal.ai inpainting failed ({type(e).__name__}: {e})")
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

        original_full = Image.open(image_path).convert("RGB")
        target_size = _resolve_inpaint_size(original_full.size)
        original = original_full.resize(target_size)
        mask_resized = mask.resize(target_size).convert("L")

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
