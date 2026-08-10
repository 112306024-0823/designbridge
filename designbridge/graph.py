# designbridge/graph.py
"""DesignBridge LangGraph: build and compile the workflow."""

from __future__ import annotations

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from designbridge.nodes import (
    adjuster_agent_stub,
    clip_evaluator_node,
    design_director,
    layout_and_style_agent_stub,
    quotation_agent,
    requirement_analyzer,
    renderer,
    visual_preprocessing_local,
)
from designbridge.state import DesignBridgeState, RoutingDecision


def _route_after_director(state: DesignBridgeState) -> str:
    """Map routing_decision to agent node name."""
    decision: RoutingDecision | None = state.get("routing_decision")
    if not decision:
        return "layout_and_style_agent"
    return {
        "design_adjuster": "adjuster_agent",
        "design": "layout_and_style_agent",
    }.get(decision, "layout_and_style_agent")


def build_graph() -> StateGraph:
    """
    Build DesignBridge workflow:
    START -> requirement_analyzer -> visual_preprocessing -> design_director
      -> (adjuster_agent | layout_and_style_agent) -> renderer -> END
    """
    graph: StateGraph[DesignBridgeState] = StateGraph(DesignBridgeState)

    graph.add_node("requirement_analyzer", requirement_analyzer)
    graph.add_node("visual_preprocessing", visual_preprocessing_local)
    graph.add_node("design_director", design_director)
    graph.add_node("adjuster_agent", adjuster_agent_stub)
    graph.add_node("layout_and_style_agent", layout_and_style_agent_stub)
    graph.add_node("renderer", renderer)
    graph.add_node("clip_evaluator", clip_evaluator_node)
    graph.add_node("quotation_agent", quotation_agent)

    graph.add_edge(START, "requirement_analyzer")
    graph.add_edge("requirement_analyzer", "visual_preprocessing")
    graph.add_edge("visual_preprocessing", "design_director")
    graph.add_conditional_edges(
        "design_director",
        _route_after_director,
        path_map={
            "adjuster_agent": "adjuster_agent",
            "layout_and_style_agent": "layout_and_style_agent",
        },
    )
    graph.add_edge("adjuster_agent", "renderer")
    graph.add_edge("layout_and_style_agent", "renderer")
    graph.add_edge("renderer", "clip_evaluator")
    graph.add_edge("clip_evaluator", "quotation_agent")
    graph.add_edge("quotation_agent", END)

    return graph


def get_compiled_graph():
    """Return compiled graph ready for invoke/stream."""
    return build_graph().compile()
