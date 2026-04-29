"""
Design Director skill script.
讀取 stdin JSON → 決定 routing → 輸出 routing_decision 到 stdout。

原始邏輯位於：designbridge/nodes.py::design_director / _route_decision
"""
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root))


def route(structured_requirement: dict) -> str:
    edit_scope_info = structured_requirement.get("edit_scope") or {}
    scope_value = float(edit_scope_info.get("scope_value", 0.5))

    hint_adjuster = structured_requirement.get("hint_adjuster") is True
    hint_layout = structured_requirement.get("hint_layout") is True
    hint_style = structured_requirement.get("hint_style") is True

    if hint_adjuster or scope_value < 0.3:
        return "design_adjuster"
    if hint_layout and hint_style:
        return "layout_and_style"
    if hint_layout:
        return "layout"
    if hint_style:
        return "style"
    return "layout_and_style"


def main():
    data = json.load(sys.stdin)
    structured_requirement = data.get("structured_requirement") or {}
    decision = route(structured_requirement)
    print(json.dumps({"routing_decision": decision}))


if __name__ == "__main__":
    main()
