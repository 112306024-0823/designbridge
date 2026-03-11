#!/usr/bin/env python3
# run_designbridge.py
"""Run DesignBridge workflow with sample user input."""

from designbridge import get_compiled_graph

# Sample input: user_input only (Requirement Analyzer + Design Director will fill the rest)
initial_state = {
    "user_input": {
        "text_prompt": "客廳想要北歐風格，希望動線順暢",
        "edit_scope": 0.6,
    }
}

compiled = get_compiled_graph()
result = compiled.invoke(initial_state)

print("=== DesignBridge run result ===")
print("task_id:", result.get("task_id"))
print("iteration:", result.get("iteration"))
print("routing_decision:", result.get("routing_decision"))
print("structured_requirement (room_type, target_style):", end=" ")
req = result.get("structured_requirement") or {}
print(req.get("room_type"), req.get("target_style"))
print("intermediate_outputs:", result.get("intermediate_outputs"))
print("vision_features:", result.get("vision_features"))
