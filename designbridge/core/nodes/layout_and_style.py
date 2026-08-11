"""Layout + Style graph node."""

from __future__ import annotations

import uuid
from typing import Any

from designbridge.core.state import DesignBridgeState
from designbridge.core.timing import timed_call
from designbridge.style.style_apply import build_style_params


def layout_and_style_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """Layout + style agent.

    Layout planning is only executed when the user explicitly requests spatial reorganization
    (hint_layout=True from LLM semantic analysis). Otherwise only style params are built,
    and spatial structure is left to the depth map (if available).
    """
    req = state.get("structured_requirement") or {}
    user_input = state.get("user_input") or {}
    hint_layout = bool(req.get("hint_layout", False))
    task_id = state.get("task_id") or str(uuid.uuid4())

    style_params = timed_call("layout_and_style.style_search", task_id, build_style_params, req, user_input)

    scene_graph: dict[str, Any] | None = None
    layout_intermediate: dict[str, Any] = {}
    if hint_layout:
        from designbridge.layout.layout_agent import run_layout_agent

        existing_layout = state.get("layout_from_depth")  # 照片萃取的現有家具位置（若有上傳圖）
        try:
            result = timed_call(
                "layout_and_style.layout_agent", task_id,
                run_layout_agent, req, task_id, existing_layout=existing_layout,
            )
            scene_graph = result.get("scene_graph")
            layout_intermediate = result.get("intermediate_outputs") or {}
            layout_status = "ok"
            _proj = (scene_graph or {}).get("projected_depth_path")
            print(
                f"[layout_and_style] hint_layout=True → layout planned "
                f"({len((scene_graph or {}).get('furniture_placements') or [])} items, "
                f"projected_depth={'yes' if _proj else 'no'})"
            )
        except Exception as e:
            layout_status = f"failed: {e}"
            print(f"⚠️ [layout_and_style] layout agent failed ({e}), continuing with style only")
    else:
        layout_status = "skipped: no layout replanning requested"
        print("[layout_and_style] hint_layout=False → skipping layout, spatial structure from depth map")

    return {
        **({"style_params": style_params} if style_params else {}),
        **({"scene_graph": scene_graph} if scene_graph else {}),
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            **layout_intermediate,
            "layout_and_style_agent": {
                "layout": layout_status,
                "hint_layout": hint_layout,
                "style_profile_id": style_params.get("style_profile_id") if style_params else None,
            },
        }
    }
