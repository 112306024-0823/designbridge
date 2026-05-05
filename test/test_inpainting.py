"""
Inpainting 獨立測試腳本
用法：
    python test_inpainting.py <圖片路徑> "<調整指令>"

範例：
    python test_inpainting.py photo.jpg "blue sofa, modern style"
    python test_inpainting.py photo.jpg "wooden floor, warm lighting"
"""

import sys
import time
from pathlib import Path

# 自動找到含有 designbridge package 的 project root
# 支援從 test/ 或 project root 任何位置執行
_here = Path(__file__).resolve().parent
_root = _here if (_here / 'designbridge').is_dir() else _here.parent
sys.path.insert(0, str(_root))


def main():
    # --- 參數解析 ---
    if len(sys.argv) < 3:
        print("用法：python test_inpainting.py <圖片路徑> \"<調整指令>\"")
        print("範例：python test_inpainting.py photo.jpg \"blue sofa, modern style\"")
        sys.exit(1)

    image_path = sys.argv[1]
    prompt = sys.argv[2]
    negative_prompt = "blurry, low quality, distorted, deformed, watermark, inconsistent lighting"

    if not Path(image_path).exists():
        print(f"[ERROR] 找不到圖片：{image_path}")
        sys.exit(1)

    print(f"圖片：{image_path}")
    print(f"指令：{prompt}")
    print()

    # --- 檢查模型快取 ---
    print("[1/4] 檢查模型快取...")
    from designbridge.config import Config
    from designbridge.inpaint import _is_inpaint_model_cached, _get_inpaint_pipeline, fallback_center_mask, run_inpainting

    if not _is_inpaint_model_cached():
        print(f"[WARN] 模型尚未完整快取：{Config.INPAINT_MODEL}")
        print("       請先執行：python -c \"from huggingface_hub import snapshot_download; snapshot_download('runwayml/stable-diffusion-inpainting')\"")
        print("       強制繼續載入（會觸發下載）...")
    else:
        print(f"[OK]  模型已快取：{Config.INPAINT_MODEL}")

    # --- 載入圖片，產生 mask ---
    print("[2/4] 載入圖片，產生 mask...")
    from PIL import Image

    original = Image.open(image_path).convert("RGB")
    w, h = original.size
    print(f"      圖片尺寸：{w} x {h}")

    mask = fallback_center_mask((w, h))

    # 儲存 mask 預覽
    out_dir = Path("artifacts/inpaint_test")
    out_dir.mkdir(parents=True, exist_ok=True)
    mask.save(str(out_dir / "mask_preview.png"))
    print(f"      mask 已儲存：{out_dir / 'mask_preview.png'}")

    # --- 載入 pipeline ---
    print("[3/4] 載入 inpainting pipeline（首次載入需要時間）...")
    t0 = time.perf_counter()
    try:
        pipe = _get_inpaint_pipeline()
        print(f"      載入完成，耗時 {time.perf_counter() - t0:.1f}s")
    except Exception as e:
        print(f"[ERROR] 載入失敗：{e}")
        sys.exit(1)

    # --- 執行 inpainting ---
    print("[4/4] 執行 inpainting...")
    out_path = out_dir / "result.png"
    t1 = time.perf_counter()

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"      使用裝置：{device}")

    target_size = (512, 512)
    image_resized = original.resize(target_size)
    mask_resized = mask.resize(target_size).convert("L")

    try:
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image_resized,
            mask_image=mask_resized,
            strength=0.75,
            num_inference_steps=30,
            guidance_scale=7.5,
        ).images[0]

        # 貼回原始解析度
        result_full = original.copy()
        result_back = result.resize((w, h))
        mask_full = mask.resize((w, h)).convert("L")
        result_full.paste(result_back, mask=mask_full)

        result_full.save(str(out_path))
        elapsed = time.perf_counter() - t1
        print(f"      完成，耗時 {elapsed:.1f}s")
        print()
        print(f"輸出路徑：{out_path.resolve()}")

    except Exception as e:
        import traceback
        print(f"[ERROR] inpainting 失敗：{e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
