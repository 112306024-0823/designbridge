"""Quotation graph node."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from designbridge.core.state import DesignBridgeState


def quotation_agent(state: DesignBridgeState) -> dict[str, Any]:
    """分析生成圖中的家具並對應 IKEA 商品給出報價。"""
    image_path = state.get("generated_image")
    req = state.get("structured_requirement") or {}

    if not image_path or not Path(image_path).is_file():
        return {"quotation_result": None}

    try:
        from designbridge.pricing.quotation import build_quotation
        result = build_quotation(image_path, req)
        total = len(result["furniture_list"])
        matched = result["kb_match_count"]
        print(f"[quotation] KB match: {matched}/{total} items")
        return {"quotation_result": result}
    except Exception as e:
        print(f"[quotation] failed: {e}")
        return {"quotation_result": None}
