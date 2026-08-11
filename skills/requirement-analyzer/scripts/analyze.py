"""
Requirement Analyzer skill script.
讀取 stdin JSON → 呼叫 designbridge 的 requirement_analyzer 邏輯 → 輸出 JSON 到 stdout。

原始邏輯位於：designbridge/nodes.py::requirement_analyzer
"""
import json
import sys
from pathlib import Path

# 確保可以 import designbridge（從 skills/requirement-analyzer/scripts/ 往上找專案根目錄）
_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root))

from designbridge.core.nodes import (
    _call_gemini_requirement_analyzer,
    _rule_based_requirement_analyzer,
)
from designbridge.core.config import Config


def main():
    data = json.load(sys.stdin)
    text_prompt = data.get("text_prompt", "").strip()
    edit_scope = float(data.get("edit_scope", 0.5))
    initial_image = data.get("initial_image", "無")

    try:
        api_key = Config.get_gemini_api_key()
        result = _call_gemini_requirement_analyzer(
            text_prompt, edit_scope, initial_image, api_key
        )
    except Exception as e:
        print(f"[requirement-analyzer] Gemini fallback: {e}", file=sys.stderr)
        result = _rule_based_requirement_analyzer(text_prompt, edit_scope)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
