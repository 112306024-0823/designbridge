"""
Style Advisor skill script.
讀取 stdin JSON → 從 style_kb 載入風格 profile → 輸出 style_params 到 stdout。

原始邏輯位於：designbridge/nodes.py::style_agent_stub
             designbridge/style_apply.py::build_style_params
"""
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root))

from designbridge.style_apply import build_style_params


def main():
    data = json.load(sys.stdin)
    structured_requirement = data.get("structured_requirement") or {}
    user_input = data.get("user_input") or {}

    style_params = build_style_params(structured_requirement, user_input)

    if not style_params:
        print(json.dumps({
            "intermediate_outputs": {
                "style_agent": "no_aggregated_style_profile"
            }
        }))
        return

    print(json.dumps({
        "style_params": style_params,
        "intermediate_outputs": {
            "style_agent": {
                "status": "aggregated_style_loaded",
                "style_profile_id": style_params.get("style_profile_id"),
                "style_profile_name": style_params.get("style_profile_name"),
            }
        }
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
