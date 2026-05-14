#!/usr/bin/env python3
# download_flux_models.py

import os
from pathlib import Path
import dotenv
import torch
from diffusers import FluxPriorReduxPipeline, FluxPipeline

dotenv.load_dotenv(Path(__file__).parent / ".env")
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    print("❌ 找不到 HF_TOKEN，請確認 .env 內有設定")
    raise SystemExit(1)

MODEL_REDUX = "black-forest-labs/FLUX.1-Redux-dev"
MODEL_DEV = "black-forest-labs/FLUX.1-dev"

def main():
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    print(f"裝置：{'cuda' if torch.cuda.is_available() else 'cpu'}，dtype：{dtype}\n")

    print(f"⏳ 下載 {MODEL_REDUX} ...")
    redux = FluxPriorReduxPipeline.from_pretrained(
        MODEL_REDUX,
        torch_dtype=dtype,
        token=HF_TOKEN,
    )
    del redux
    print(f"✅ {MODEL_REDUX} 下載完成\n")

    print(f"⏳ 下載 {MODEL_DEV} ...")
    dev = FluxPipeline.from_pretrained(
        MODEL_DEV,
        torch_dtype=dtype,
        token=HF_TOKEN,
    )
    del dev
    print(f"✅ {MODEL_DEV} 下載完成\n")

    print("=" * 50)
    print("✅ 所有模型已下載到本機快取。")
    print("   接下來把 .env 的 DESIGNBRIDGE_ENABLE_FLUX_REDUX 改為 true 即可使用 Redux 模式。")

if __name__ == "__main__":
    main()