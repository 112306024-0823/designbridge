"""Design Director graph node — routes to adjuster_agent vs layout_and_style_agent."""

from __future__ import annotations

from typing import Any

from designbridge.core.config import Config
from designbridge.core.state import DesignBridgeState, RoutingDecision


def _route_decision(state: DesignBridgeState) -> RoutingDecision:
    """Fallback rule-based routing（LLM 失敗時）：預設走 design。"""
    return "design"


def design_director(state: DesignBridgeState) -> dict[str, Any]:
    """
    動態調度：ENABLE_DYNAMIC_ROUTING=true 時由 LLM（Gemini）讀 SKILL.md 決策；
    否則使用原本的 rule-based routing。任何 LLM 失敗都自動 fallback。
    細部微調模式（refine_mode=True）直接強制 routing 到 design_adjuster。
    優先使用 requirement_analyzer 已由 LLM 決定的 routing_decision（語意理解）。
    """
    # 使用者明確選擇細部微調，跳過 LLM 判斷直接 route
    if (state.get("user_input") or {}).get("refine_mode"):
        print("[design_director] refine_mode=True → design_adjuster")
        return {"routing_decision": "design_adjuster"}

    # 若 routing_decision 已由上游節點設定，跳過重複判斷
    if state.get("routing_decision"):
        print(f"[design_director] routing_decision already set: {state['routing_decision']}, skipping")
        return {}

    if Config.get_dynamic_routing_enabled():
        try:
            from designbridge.core.router import call_llm_router, RouterLLMError
            # Auth is resolved inside designbridge.render.llm (Gemini).
            routing_decision = call_llm_router(
                structured_requirement=state.get("structured_requirement") or {},
                vision_features=state.get("vision_features") or {},
                api_key="",
                gemini_model=Config.GEMINI_MODEL,
                gemini_temperature=Config.ROUTER_TEMPERATURE,
            )
            print(f"[design_director] LLM router: {routing_decision}")
            return {"routing_decision": routing_decision}
        except Exception as e:
            print(f"[design_director] LLM routing failed ({e}), fallback to rule-based")

    routing_decision = _route_decision(state)
    print(f"[design_director] fallback rule-based routing: {routing_decision}")
    return {"routing_decision": routing_decision}
