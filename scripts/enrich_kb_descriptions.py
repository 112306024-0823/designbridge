"""
一次性腳本：用 Gemini Vision 為 ikea_tw.json 每件商品生成中文視覺描述，
並寫回 json。已有 visual_description 的商品跳過（支援斷點續跑）。

執行方式：
    python scripts/enrich_kb_descriptions.py
"""
import json
import os
import time
from pathlib import Path

import google.generativeai as genai
import httpx

KB_PATH = Path(__file__).parent.parent / "designbridge" / "furniture_kb" / "ikea_tw.json"
PROMPT = (
    "請用15字以內的中文描述這件家具的外觀，"
    "包含形狀、顏色、材質特徵，不要提品牌或型號。"
    "只輸出描述文字，不要其他說明。"
)


def describe_item(model, image_url: str) -> str:
    img_bytes = httpx.get(image_url, timeout=10).content
    response = model.generate_content([
        PROMPT,
        {"mime_type": "image/jpeg", "data": img_bytes},
    ])
    return response.text.strip()


def main():
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")

    items = json.loads(KB_PATH.read_text(encoding="utf-8"))
    updated = 0

    for i, item in enumerate(items):
        if item.get("visual_description"):
            continue
        if not item.get("image_url"):
            item["visual_description"] = ""
            continue
        try:
            desc = describe_item(model, item["image_url"])
            item["visual_description"] = desc
            updated += 1
            print(f"[{i+1}/{len(items)}] {item['name'][:20]} → {desc}")
            if updated % 10 == 0:
                KB_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
            time.sleep(0.5)
        except Exception as e:
            print(f"  SKIP {item['name'][:20]}: {e}")
            item["visual_description"] = ""

    KB_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成，共更新 {updated} 件")


if __name__ == "__main__":
    main()
