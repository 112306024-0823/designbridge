#!/usr/bin/env python3
"""
Quick test script to verify whether the Gemini API is reachable
with the current DesignBridge configuration (.env / Config).

Usage (from project root):

    python test_gemini.py

It will:
- Load GEMINI_API_KEY via designbridge.config.Config
- Send a minimal text-only prompt to Gemini
- Print a clear SUCCESS / FAILURE message
"""

from __future__ import annotations

import sys
from typing import Any

from designbridge.config import Config


def main() -> None:
    print("=== DesignBridge Gemini Connectivity Test ===")

    # 1) Check API key
    try:
        api_key = Config.get_gemini_api_key()
        print(f"[OK] GEMINI_API_KEY loaded from env/config (length={len(api_key)})")
    except Exception as e:  # noqa: BLE001
        print("[ERROR] GEMINI_API_KEY not configured correctly.")
        print(f"Details: {e}")
        sys.exit(1)

    # 2) Try a minimal Gemini call
    try:
        import google.generativeai as genai  # type: ignore[import]
    except ImportError:
        print("[ERROR] google-generativeai is not installed.")
        print("Run: pip install google-generativeai")
        sys.exit(1)

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(Config.GEMINI_MODEL)

        prompt = "你是一個測試用 API，請只回覆：\"OK\"。"
        print(f"[INFO] Calling Gemini model: {Config.GEMINI_MODEL!r} ...")
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=Config.GEMINI_TEMPERATURE,
            ),
        )

        text: str = (response.text or "").strip()
        print("\n=== Gemini Response ===")
        print(text)
        print("=======================")

        if text:
            print("\n[SUCCESS] Gemini API call succeeded.")
        else:
            print("\n[WARN] Gemini API call returned empty text, but no exception occurred.")

    except Exception as e:  # noqa: BLE001
        print("\n[ERROR] Gemini API call failed.")
        print(f"Details: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

