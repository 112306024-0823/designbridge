"""
測試 Gemini 多 key 輪替邏輯（純邏輯，不呼叫真實 API）。

執行方式：
    python test/test_gemini_key_rotation.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 蓋掉可能存在的 .env 值，確保測試結果穩定
os.environ["GEMINI_API_KEY"] = "key-a"
os.environ["GEMINI_API_KEYS"] = "key-a,key-b,key-c"

from designbridge.config import Config
import designbridge.llm as llm


def test_keys_merged_and_deduped():
    assert Config.get_gemini_api_keys() == ["key-a", "key-b", "key-c"]


def test_rotation_skips_quota_errors():
    llm._gemini_key_idx = 0
    calls = []

    def fake(api_key: str) -> str:
        calls.append(api_key)
        if api_key != "key-c":
            raise RuntimeError("429 quota exceeded")
        return "ok"

    assert llm.call_with_gemini_key_rotation(fake) == "ok"
    assert calls == ["key-a", "key-b", "key-c"]


def test_rotation_raises_after_all_keys_exhausted():
    llm._gemini_key_idx = 0

    def always_quota(api_key: str) -> str:
        raise RuntimeError("429 quota exceeded")

    try:
        llm.call_with_gemini_key_rotation(always_quota)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "quota" in str(e)


def test_non_quota_error_does_not_rotate():
    llm._gemini_key_idx = 0
    calls = []

    def fake(api_key: str) -> str:
        calls.append(api_key)
        raise ValueError("bad prompt")

    try:
        llm.call_with_gemini_key_rotation(fake)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert calls == ["key-a"]


if __name__ == "__main__":
    test_keys_merged_and_deduped()
    test_rotation_skips_quota_errors()
    test_rotation_raises_after_all_keys_exhausted()
    test_non_quota_error_does_not_rotate()
    print("OK")
