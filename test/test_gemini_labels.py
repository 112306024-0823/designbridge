"""
測試 Gemini API 從中文 prompt 提取語義分割標籤。

執行方式：
    python test/test_gemini_labels.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from designbridge.llm import call_llm

TEST_CASES = [
    "把沙發換成藍色",
    "窗簾改成米白色",
    "把椅子和桌子都換掉",
    "更換布藝單人椅",        # 關鍵字字典 miss，需要 Gemini
    "把落地燈換成北歐風",    # 關鍵字字典 miss
    "整體換成現代風格",      # 模糊，預期回傳 furniture
]

def extract_labels(text: str) -> list[str]:
    result = call_llm(
        f"From this interior design modification request, extract the names of objects/furniture "
        f"that need to be modified. Return ONLY a comma-separated list of English nouns "
        f"(e.g. sofa, curtain, chair). If unclear, return: furniture\n\nRequest: {text}",
        max_tokens=40,
    )
    return [l.strip().lower() for l in result.split(",") if l.strip()]

def run():
    print("測試 Gemini label 提取\n" + "=" * 40)
    all_pass = True
    for prompt in TEST_CASES:
        try:
            labels = extract_labels(prompt)
            print(f"[PASS] \"{prompt}\"")
            print(f"       → {labels}\n")
        except Exception as e:
            all_pass = False
            print(f"[FAIL] \"{prompt}\"")
            print(f"       錯誤: {e}\n")

    if all_pass:
        print("Gemini API 正常運作。")
    else:
        print("有部分呼叫失敗，請檢查 API key 或網路連線。")

if __name__ == "__main__":
    run()
