"""Style-application helpers — vector store first, aggregated JSON fallback."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from style_kb.styles import STYLES

STYLE_NAME_TO_ID = {name: style_id for style_id, name in STYLES}
STYLE_ID_SET = {style_id for style_id, _ in STYLES}


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def resolve_style_profile_id(
    req: dict[str, Any],
    user_input: dict[str, Any] | None = None,
) -> str | None:
    """從使用者選單或 Gemini 解析結果，決定風格 ID。"""
    user_input = user_input or {}
    explicit_style_id = (user_input.get("style_profile_id") or "").strip()
    if explicit_style_id and explicit_style_id not in ("", "auto"):
        return explicit_style_id if explicit_style_id in STYLE_ID_SET else None

    style_prefs = req.get("style_preferences") or {}
    primary_style = str(style_prefs.get("primary_style") or "").strip()
    if not primary_style:
        return None
    primary_style_lower = primary_style.lower()
    if primary_style_lower in STYLE_ID_SET:
        return primary_style_lower
    return STYLE_NAME_TO_ID.get(primary_style)


def list_available_style_profiles() -> list[dict[str, str]]:
    """列出所有風格（固定清單，不再依賴 aggregated 資料夾）。"""
    return [
        {"style_id": style_id, "style_name": style_name}
        for style_id, style_name in STYLES
    ]


# ── 主要介面 ──────────────────────────────────────────────────────────────────

def build_style_params(
    req: dict[str, Any],
    user_input: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    建立 Renderer 可用的風格參數。

    優先順序：
    1. Supabase pgvector 語義搜尋
    2. 本地 ChromaDB（若 Supabase 不可用）
    3. Fallback：aggregated JSON
    """
    if (user_input or {}).get("no_style_reference"):
        return None

    style_profile_id = resolve_style_profile_id(req, user_input)
    text_query = (user_input or {}).get("text_prompt", "").strip()
    query = text_query or style_profile_id or "interior design"
    retrieval_mode = (
        (user_input or {}).get("style_retrieval_mode")
        or os.getenv("DESIGNBRIDGE_STYLE_RETRIEVAL_MODE", "text-to-image")
    )

    # ── 1. Supabase pgvector 搜尋 ─────────────────────────────────────────────
    try:
        from designbridge.style_supabase import (
            query_style_images_supabase,
            blend_style_params_supabase,
        )
        results = query_style_images_supabase(
            text_query=query,
            style_id=style_profile_id,
            top_k=3,
            retrieval_mode=str(retrieval_mode),
        )
        if results:
            return blend_style_params_supabase(results)
    except Exception as e:
        print(f"⚠️  Supabase 向量搜尋失敗，嘗試本地向量庫：{e}")

    # ── 2. 本地 ChromaDB 搜尋 ─────────────────────────────────────────────────
    try:
        from designbridge.style_vector import (
            is_vector_store_ready,
            query_style_images,
            blend_style_params,
        )
        if is_vector_store_ready():
            results_local = query_style_images(
                text_query=query,
                style_id=style_profile_id,
                top_k=3,
            )
            if results_local:
                params = blend_style_params(results_local)
                print(f"✅ 本地向量搜尋：top-1 [{results_local[0].doc_id}] score={results_local[0].similarity_score}")
                return params
    except Exception as e:
        print(f"⚠️  本地向量庫查詢失敗：{e}")

    # ── 3. Fallback：aggregated JSON ──────────────────────────────────────────
    if not style_profile_id:
        return None

    aggregated_dir = Path(__file__).resolve().parent.parent / "style_kb" / "aggregated"
    profile_path = aggregated_dir / f"{style_profile_id}_aggregated.json"
    if not profile_path.exists():
        return None

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    style_prefs = req.get("style_preferences") or {}
    statistics = profile.get("statistics") or {}
    ai_config = profile.get("ai_config") or {}
    style_profile_data = profile.get("style_profile") or {}

    style_strength = float(style_prefs.get("style_strength", 0.7))
    recommended_weight = float(ai_config.get("recommended_ip_adapter_weight", 0.85))

    print(f"⚠️  使用 aggregated fallback：{style_profile_id}")
    return {
        "style_profile_id": profile.get("style_id", style_profile_id),
        "style_profile_name": profile.get("style_name", style_profile_id),
        "style_prompt": ai_config.get("unified_positive_prompt", ""),
        "negative_prompt": ai_config.get("unified_negative_prompt", ""),
        "style_strength": round((style_strength + recommended_weight) / 2, 2),
        "color_guidance": {
            "primary_color": statistics.get("primary_color"),
            "secondary_color": statistics.get("secondary_color"),
            "accent_color": statistics.get("accent_color"),
            "avg_color_temp_k": statistics.get("avg_color_temp_k"),
        },
        "controlnet_type": ai_config.get("controlnet_type", "depth"),
        "style_summary": style_profile_data.get("summary", ""),
        "source": "aggregated_fallback",
    }
