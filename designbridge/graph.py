# designbridge/graph.py
"""DesignBridge LangGraph: build and compile the workflow."""

from __future__ import annotations

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from designbridge.nodes import (
    adjuster_agent_stub,
    design_director,
    layout_agent_stub,
    layout_and_style_agent_stub,
    requirement_analyzer,
    style_agent_stub,
    visual_preprocessing_local,
)
from designbridge.state import DesignBridgeState, RoutingDecision


def _route_after_director(state: DesignBridgeState) -> str:
    """Map routing_decision to agent node name."""
    decision: RoutingDecision | None = state.get("routing_decision")
    if not decision:
        return "layout_and_style_agent"
    return {
        "layout": "layout_agent",
        "style": "style_agent",
        "design_adjuster": "adjuster_agent",
        "layout_and_style": "layout_and_style_agent",
    }.get(decision, "layout_and_style_agent")


def build_graph() -> StateGraph:
    """
    Build DesignBridge workflow:
    START -> requirement_analyzer -> visual_preprocessing_stub -> design_director
      -> (layout_agent | style_agent | adjuster_agent | layout_and_style_agent) -> END
    """
    graph: StateGraph[DesignBridgeState] = StateGraph(DesignBridgeState)

    graph.add_node("requirement_analyzer", requirement_analyzer)
    graph.add_node("visual_preprocessing", visual_preprocessing_local)
    graph.add_node("design_director", design_director)
    graph.add_node("layout_agent", layout_agent_stub)
    graph.add_node("style_agent", style_agent_stub)
    graph.add_node("adjuster_agent", adjuster_agent_stub)
    graph.add_node("layout_and_style_agent", layout_and_style_agent_stub)

    graph.add_edge(START, "requirement_analyzer")
    graph.add_edge("requirement_analyzer", "visual_preprocessing")
    graph.add_edge("visual_preprocessing", "design_director")
    graph.add_conditional_edges(
        "design_director",
        _route_after_director,
        path_map={
            "layout_agent": "layout_agent",
            "style_agent": "style_agent",
            "adjuster_agent": "adjuster_agent",
            "layout_and_style_agent": "layout_and_style_agent",
        },
    )
    graph.add_edge("layout_agent", END)
    graph.add_edge("style_agent", END)
    graph.add_edge("adjuster_agent", END)
    graph.add_edge("layout_and_style_agent", END)

    return graph


def get_compiled_graph():
    """Return compiled graph ready for invoke/stream."""
    return build_graph().compile()
