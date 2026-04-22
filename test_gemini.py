#!/usr/bin/env python3
"""
Quick test script to verify whether Gemini API and Hugging Face token
are reachable with the current DesignBridge configuration (.env / Config).

Usage (from project root):

    python test_gemini.py

It will:
- Load GEMINI_API_KEY via designbridge.config.Config
- Send a minimal text-only prompt to Gemini
- Validate HF_TOKEN by calling Hugging Face whoami endpoint
- Print clear SUCCESS / FAILURE messages
"""

from __future__ import annotations

import sys
from typing import Any

import requests

from designbridge.config import Config


def main() -> None:
    print("=== DesignBridge Token Connectivity Test ===")
    gemini_ok = False
    hf_ok = False

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
        from google import genai  # type: ignore[import]
    except ImportError:
        print("[ERROR] google-genai is not installed.")
        print("Run: pip install google-genai")
        sys.exit(1)

    try:
        client = genai.Client(api_key=api_key)
        model_name = "gemini-2.0-flash"
        prompt = "你是一個測試用 API，請只回覆：\"OK\"。"
        print(f"[INFO] Calling Gemini model: {model_name!r} ...")
        response = client.models.generate_content(model=model_name, contents=prompt)

        text: str = (response.text or "").strip()
        print("\n=== Gemini Response ===")
        print(text)
        print("=======================")

        if text:
            print("\n[SUCCESS] Gemini API call succeeded.")
            gemini_ok = True
        else:
            print("\n[WARN] Gemini API call returned empty text, but no exception occurred.")
            gemini_ok = True

    except Exception as e:  # noqa: BLE001
        print("\n[ERROR] Gemini API call failed.")
        print(f"Details: {e}")

    # 3) Validate HF token (for HF Inference API usage)
    print("\n=== Hugging Face Token Test ===")
    import os
    hf_token = (os.getenv("HF_TOKEN") or Config.HF_TOKEN or "").strip()
    if not hf_token:
        print("[WARN] HF_TOKEN is not set. Skipping HF verification.")
    else:
        print(f"[OK] HF_TOKEN loaded from env/config (length={len(hf_token)})")
        try:
            resp = requests.get(
                "https://huggingface.co/api/whoami-v2",
                headers={"Authorization": f"Bearer {hf_token}"},
                timeout=20,
            )
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("name") or data.get("fullname") or "unknown"
                print(f"[SUCCESS] HF token verified. Account: {name}")
                hf_ok = True
            elif resp.status_code in (401, 403):
                print("[ERROR] HF token is invalid or lacks required permission.")
                print(f"Status: {resp.status_code}")
            else:
                print("[ERROR] Unexpected HF API response.")
                print(f"Status: {resp.status_code}")
                print(f"Body: {resp.text[:300]}")
        except requests.RequestException as e:
            print("[ERROR] Failed to connect to Hugging Face API.")
            print(f"Details: {e}")

    # 4) Final summary
    print("\n=== Summary ===")
    print(f"Gemini: {'OK' if gemini_ok else 'FAILED'}")
    print(f"HF Token: {'OK' if hf_ok else 'SKIPPED/FAILED'}")

    if not gemini_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

