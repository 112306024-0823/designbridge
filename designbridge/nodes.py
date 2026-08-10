# designbridge/nodes.py
"""DesignBridge graph nodes: Requirement Analyzer, Visual Preprocessing, Design Director, Renderer, agent stubs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from designbridge.config import Config
from designbridge.prompts import REQUIREMENT_ANALYZER_PROMPT
from designbridge.style_apply import build_style_params, STYLE_NAME_TO_ID
from designbridge.state import DesignBridgeState, RoutingDecision
from designbridge.vision import run_visual_preprocessing
from designbridge.schemas import RequirementJSON, StyleParamsJSON
from designbridge.inpaint import (
    mask_from_segmentation,
    expand_mask_by_segmentation,
    fallback_center_mask,
    generate_mask_with_sam2,
    run_lama_inpainting,
    build_inpaint_prompt,
    run_inpainting,
    run_hf_inpainting,
    run_fal_inpainting,
    load_mask_from_path,
)
from designbridge.render_prompt import (
    _analyze_style_image_with_gemini,
    _build_imagen_prompt_from_requirement,
    _resolve_output_size,
)
from designbridge.render_backends import (
    _render_hf_inference,
    _render_hf_kontext,
    _render_flux_kontext_fal,
    _render_flux_controlnet_depth_fal,
    _render_flux_redux_fal,
    _render_flux_redux_local,
    _render_flux_ipadapter_fal,
    _render_flux,
)

_BASE_NEGATIVE_PROMPT = (
    "people, person, human, man, woman, child, hands, face, "
    "animal, pet, cat, dog, bird, "
    "text, watermark, signature, logo"
)

def requirement_analyzer(state: DesignBridgeState) -> dict[str, Any]:
    """
    Parse user_input into structured_requirement (JSON) using Gemini API.
    Falls back to rule-based if API key not set or API fails.
    """
    user = state.get("user_input") or {}
    text_prompt = (user.get("text_prompt") or "").strip()
    edit_scope = float(user.get("edit_scope", 0.5))
    initial_image = user.get("initial_image", "無")
    style_reference_image = user.get("style_reference_image", "")

    task_id = state.get("task_id") or str(uuid.uuid4())
    iteration = state.get("iteration", 0)

    # Try LLM (via LiteLLM) first, fall back to passing prompt directly on failure
    try:
        structured_requirement = _call_llm_requirement_analyzer(
            text_prompt, edit_scope, initial_image,
            style_reference_image=style_reference_image,
        )
    except Exception as e:
        print(f"⚠️  LLM call failed ({e}), passing prompt directly to renderer")
        structured_requirement = {
            "user_description_raw": text_prompt,
            "design_description": text_prompt,
            "meta": {"room_type": "living_room", "design_goal": "renovation", "user_experience_level": "general"},
            "space_info": {"estimated_size": {"width": 5.0, "height": 3.0, "depth": 4.0}, "windows": [], "doors": []},
            "style_preferences": {"primary_style": "", "secondary_style": None, "color_palette": [], "material_preferences": [], "style_strength": 0.7, "reference_images": []},
            "layout_constraints": {"must_keep": [], "must_add": [], "must_remove": [], "immutable_regions": [], "functional_zones": []},
            "edit_scope": {"scope_value": edit_scope, "allowed_operations": ["layout", "style"]},
            "priority_weights": {"layout_rationality": 0.4, "style_consistency": 0.4, "user_preference": 0.2},
        }

    # Merge family needs and feng shui rules into structured_requirement
    family_needs   = user.get("family_needs")   or []
    fengshui_rules = user.get("fengshui_rules") or []
    if family_needs or fengshui_rules:
        from designbridge.special_constraints import enrich_requirement
        structured_requirement = enrich_requirement(structured_requirement, family_needs, fengshui_rules)

    # If the user explicitly selected a style from the dropdown, override whatever
    # Gemini / rule-based inferred from the text so the whole pipeline stays consistent.
    explicit_style_id = (user.get("style_profile_id") or "").strip()
    if explicit_style_id and explicit_style_id != "auto":
        style_prefs = structured_requirement.setdefault("style_preferences", {})
        style_prefs["primary_style"] = explicit_style_id

    # Extract routing decision embedded by _call_llm_requirement_analyzer, then remove it
    # from the requirement so it doesn't pollute structured data.
    routing_decision = structured_requirement.pop("_routing_decision", None)

    result: dict[str, Any] = {
        "task_id": task_id,
        "iteration": iteration,
        "structured_requirement": structured_requirement,
    }
    if routing_decision:
        result["routing_decision"] = routing_decision
        print(f"[requirement_analyzer] routing_decision from LLM: {routing_decision}")

    return result


def _is_valid_image_path(image_path: str) -> bool:
    """Return True if image_path is a non-empty, valid file path (not placeholder)."""
    if not image_path or not isinstance(image_path, str):
        return False
    s = image_path.strip()
    if s in ("", "無"):
        return False
    return Path(s).is_file()


_VALID_ROUTING_DECISIONS = {"design_adjuster", "design"}


def _call_llm_requirement_analyzer(
    text_prompt: str, edit_scope: float, initial_image: str,
    style_reference_image: str = "",
) -> dict[str, Any]:
    """Call LLM to analyze requirements and return {structured_requirement, routing_decision}.
    The new prompt asks for a single JSON with both fields. Falls back to legacy NL parsing.
    """
    import json as _json
    from designbridge.llm import call_llm

    prompt = REQUIREMENT_ANALYZER_PROMPT.format(
        text_prompt=text_prompt,
        edit_scope=edit_scope,
        initial_image=initial_image,
    )

    images: list[str] = []
    if _is_valid_image_path(initial_image):
        images.append(initial_image)
    if style_reference_image and _is_valid_image_path(style_reference_image):
        images.append(style_reference_image)

    text = call_llm(prompt, images=images or None)
    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Tolerate leading/trailing noise around the JSON object
    if not text.startswith("{"):
        start = text.find("{")
        if start != -1:
            text = text[start:]
    if not text.endswith("}"):
        end = text.rfind("}")
        if end != -1:
            text = text[: end + 1]

    try:
        parsed = _json.loads(text)
    except Exception as exc:
        raise ValueError(f"Requirement analyzer LLM returned unparseable JSON: {text[:200]!r}") from exc

    # New format: {"routing_decision": "...", "structured_requirement": {...}}
    if "structured_requirement" in parsed and "routing_decision" in parsed:
        req = parsed["structured_requirement"]
        routing = parsed["routing_decision"]
        if routing not in _VALID_ROUTING_DECISIONS:
            routing = "design"
        req["_routing_decision"] = routing
        return req

    # Fallback: LLM returned the old flat structure directly
    return parsed





def visual_preprocessing_local(state: DesignBridgeState) -> dict[str, Any]:
    """Local Visual Preprocessing: run depth + segmentation on the initial image (if provided)."""
    user = state.get("user_input") or {}
    image_path = user.get("initial_image")
    task_id = state.get("task_id") or "no_task_id"

    vision_features: dict[str, Any] = {"geometry_constraints": {}}

    if image_path:
        try:
            artifacts = run_visual_preprocessing(
                image_path,
                task_id=task_id,
                enable_depth=Config.ENABLE_DEPTH,
                enable_segmentation=Config.ENABLE_SEGMENTATION,
                depth_model=Config.DEPTH_MODEL,
                segmentation_model=Config.SEGMENTATION_MODEL,
                artifacts_root=Path(Config.ARTIFACTS_DIR),
            )
            if artifacts.depth_path:
                vision_features["depth"] = artifacts.depth_path
            if artifacts.segmentation_path:
                vision_features["segmentation"] = artifacts.segmentation_path
            if artifacts.segmentation_meta_path:
                vision_features["segmentation_meta"] = artifacts.segmentation_meta_path
        except Exception as e:
            print(f"⚠️  Visual preprocessing failed ({e}), falling back to empty vision_features")
            return {"vision_features": vision_features}

        result: dict[str, Any] = {"vision_features": vision_features}
        if artifacts.layout_json:
            result["layout_from_depth"] = artifacts.layout_json
        return result

    return {"vision_features": vision_features}


def _route_decision(state: DesignBridgeState) -> RoutingDecision:
    """Fallback rule-based routing（LLM 失敗時）：預設走 design。"""
    return "design"


def design_director(state: DesignBridgeState) -> dict[str, Any]:
    """
    動態調度：ENABLE_DYNAMIC_ROUTING=true 時由 LLM（LiteLLM / xAI Grok / Gemini，依 llm.py 優先序）讀 SKILL.md 決策；
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
            from designbridge.router import call_llm_router, RouterLLMError
            # Auth is resolved inside designbridge.llm (LiteLLM / xAI / Gemini).
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



def layout_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    from designbridge.layout_agent import run_layout_agent

    task_id = state.get("task_id") or str(uuid.uuid4())
    req = state.get("structured_requirement") or {}

    try:
        result = run_layout_agent(req, task_id)
    except Exception as e:
        print(f"⚠️ Layout agent failed ({e}), skipping layout")
        return {
            "intermediate_outputs": {
                **(state.get("intermediate_outputs") or {}),
                "layout_agent": f"failed: {e}",
            }
        }

    return {
        "scene_graph": result.get("scene_graph"),
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            **(result.get("intermediate_outputs") or {}),
        },
    }


def style_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """Quick style agent: load aggregated style profile and build prompt params."""
    req = state.get("structured_requirement") or {}
    user_input = state.get("user_input") or {}
    style_params = build_style_params(req, user_input)

    if not style_params:
        return {
            "intermediate_outputs": {
                **(state.get("intermediate_outputs") or {}),
                "style_agent": "no_aggregated_style_profile",
            }
        }

    return {
        "style_params": style_params,
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            "style_agent": {
                "status": "aggregated_style_loaded",
                "style_profile_id": style_params.get("style_profile_id"),
                "style_profile_name": style_params.get("style_profile_name"),
            },
        }
    }


_ZH_TO_SEG_LABELS: dict[str, list[str]] = {
    "沙發": ["sofa", "couch"],
    "椅子": ["chair"],
    "桌子": ["table", "desk"],
    "茶几": ["table"],
    "窗簾": ["curtain"],
    "地毯": ["carpet", "rug", "floor mat"],
    "燈": ["lamp", "light"],
    "床": ["bed"],
    "牆": ["wall"],
    "地板": ["floor"],
    "天花板": ["ceiling"],
    "植物": ["plant", "potted plant"],
    "電視": ["tv", "monitor"],
    "書櫃": ["bookcase", "shelf"],
}


def _bbox_mask_from_vision(image_path: str, target_object: str, img_size: tuple) -> Any:
    """
    當 segmentation 找不到目標物件（mask 過小）時，
    請 Gemini Vision 直接給出物件的 bounding box，用來生成 mask。
    """
    from PIL import Image, ImageDraw, ImageFilter

    prompt = f"""Look at this interior design image.
Find the "{target_object}" in the image.
Return ONLY valid JSON with the bounding box as fractions of image dimensions (0.0 to 1.0):
{{"x1": 0.3, "y1": 0.2, "x2": 0.6, "y2": 0.5}}
Where x1,y1 is top-left corner and x2,y2 is bottom-right corner.
If the object is not visible in the image, return: {{"not_found": true}}"""

    try:
        from designbridge.llm import call_llm
        raw = call_llm(prompt, images=[image_path], max_tokens=60, temperature=0.0)
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        bbox = json.loads(raw.strip())
        if bbox.get("not_found"):
            print(f"[adjuster] vision bbox: '{target_object}' not found in image")
            return None
        w, h = img_size
        x1 = int(bbox["x1"] * w)
        y1 = int(bbox["y1"] * h)
        x2 = int(bbox["x2"] * w)
        y2 = int(bbox["y2"] * h)
        mask = Image.new("L", img_size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle([x1, y1, x2, y2], fill=255)
        mask = mask.filter(ImageFilter.MaxFilter(21))
        print(f"[adjuster] vision bbox: '{target_object}' at ({x1},{y1})-({x2},{y2})")
        return mask
    except Exception as e:
        print(f"[adjuster] _bbox_mask_from_vision failed ({e})")
        return None


def analyze_edit_intent(
    text: str,
    image_path: str,
    seg_meta_path: str | None,
) -> dict:
    """
    用 Gemini Vision 同時判斷：
    - action: remove / replace / modify_style / add
    - seg_labels: 要操作的物件（從圖中已偵測到的 present_labels 中選）
    - replace_with: 若 action=replace，描述替換目標

    比起純字典比對，能正確處理位置語境（「床上電腦」→ target=laptop, not bed）
    和任意自然語言 prompt。
    """
    # 讀取圖中實際偵測到的物件清單，讓 LLM 從真實存在的 label 中選
    available_labels: list[str] = []
    if seg_meta_path and Path(seg_meta_path).is_file():
        with open(seg_meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        labels_dict = meta.get("present_labels") or meta.get("labels") or {}
        available_labels = list(labels_dict.values())

    labels_hint = f"Objects detected in the image: {available_labels}" if available_labels else ""

    prompt = f"""You are an interior design AI assistant.
Analyze this modification request and return JSON only (no markdown, no explanation).

User request: "{text}"
{labels_hint}

Return this exact JSON:
{{
  "action": "remove",
  "seg_labels": ["<label>"],
  "replace_with": null
}}

Where action must be one of: remove | replace | modify_style | add
- remove: 移除/刪除/去除/拿掉/清除/刪掉
- replace: 換掉/換成/改成/替換/換一個
- modify_style: 改顏色/改風格/換材質/換色
- add: 加入/添加/放一個/增加

seg_labels rules:
- Pick the TARGET OBJECT being modified, NOT its location.
  Example: "移除床上電腦" → ["laptop"] not ["bed"]
- If the object appears in the detected list, use that exact label name.
- If not in the list, use the best English noun (e.g. "laptop", "computer").

replace_with: describe the new object only if action=replace, else null."""

    try:
        from designbridge.llm import call_llm
        images = [image_path] if image_path and Path(image_path).is_file() else None
        raw = call_llm(prompt, images=images, max_tokens=150, temperature=0.0)
        raw = raw.strip()
        # 去掉 LLM 可能包的 markdown fence
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        action      = result.get("action", "modify_style")
        seg_labels  = [l.lower() for l in (result.get("seg_labels") or []) if l]
        replace_with = result.get("replace_with")
        print(f"[adjuster] vision intent → action={action}  seg_labels={seg_labels}")
        return {"action": action, "seg_labels": seg_labels, "replace_with": replace_with}
    except Exception as e:
        print(f"[adjuster] analyze_edit_intent failed ({e}), fallback to modify_style")
        return {"action": "modify_style", "seg_labels": [], "replace_with": None}


def adjuster_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """
    Design Adjuster Agent：對初始圖片進行局部 inpainting。
    觸發條件：edit_scope < 0.3 或 hint_adjuster = True。
    """
    from PIL import Image

    task_id = state.get("task_id") or str(uuid.uuid4())
    user_input = state.get("user_input") or {}
    req = state.get("structured_requirement") or {}
    vision = state.get("vision_features") or {}
    style_params = state.get("style_params")

    image_path = user_input.get("initial_image", "")
    edit_scope = float(user_input.get("edit_scope", 0.2))
    manual_mask_path = user_input.get("mask_image")   # 手繪遮罩路徑（選填）

    # 沒有原圖就無法 inpaint，跳過
    if not image_path or not Path(image_path).is_file():
        return {
            "intermediate_outputs": {
                **(state.get("intermediate_outputs") or {}),
                "adjuster_agent": "no_initial_image_skipped",
            }
        }

    # 決定要修改哪些物件
    constraints = req.get("layout_constraints") or {}
    must_remove = constraints.get("must_remove") or []
    must_add = constraints.get("must_add") or []
    target_labels = must_remove if must_remove else ["furniture"]
    target_objects = must_add if must_add else target_labels

    # Mask 生成優先序：
    #   有手繪 + 有 segmentation → 展開成完整物件遮罩（方式二）
    #   只有手繪                 → 直接用手繪遮罩
    #   只有 segmentation        → 從文字 prompt 解析物件標籤
    #   都沒有                   → 中央 fallback
    original_img = Image.open(image_path)
    img_size = original_img.size

    seg_path = vision.get("segmentation")
    seg_meta = vision.get("segmentation_meta")
    has_seg  = bool(seg_path and seg_meta
                    and Path(str(seg_path)).is_file()
                    and Path(str(seg_meta)).is_file())
    print(f"[adjuster] seg_path: {seg_path}  exists={has_seg}")

    edit_action      = None   # 由 analyze_edit_intent 填入（無手繪遮罩時）
    replace_with     = None
    effective_labels: list[str] = []

    if manual_mask_path and Path(str(manual_mask_path)).is_file():
        drawn_mask = load_mask_from_path(str(manual_mask_path), img_size)

        # 優先用 SAM 2 取得實例層級精確遮罩
        sam2_mask, sam2_ok = generate_mask_with_sam2(image_path, drawn_mask, img_size)
        if sam2_ok:
            mask = sam2_mask
            mask_source = "sam2_instance"
            seg_labels = []
            print("[adjuster] mask source: SAM 2 instance segmentation")
        elif has_seg:
            # SAM 2 失敗 → fallback：手繪 + UPerNet 展開
            mask, seg_labels = expand_mask_by_segmentation(
                drawn_mask, str(seg_path), str(seg_meta), img_size
            )
            mask_source = "manual_expanded_by_seg"
        else:
            mask = drawn_mask
            mask_source = "manual_drawing"
            seg_labels = []
    else:
        # Gemini Vision 判斷意圖：物件目標 + 動作類型
        text_prompt = user_input.get("text_prompt") or ""
        intent       = analyze_edit_intent(text_prompt, image_path, str(seg_meta) if seg_meta else None)
        edit_action  = intent["action"]
        seg_labels   = intent["seg_labels"]
        replace_with = intent["replace_with"]
        effective_labels = seg_labels or target_labels
        print(f"[adjuster] effective_labels: {effective_labels}")
        if has_seg:
            mask = mask_from_segmentation(str(seg_path), str(seg_meta), effective_labels, img_size)
            mask_source = f"segmentation({'+'.join(effective_labels[:3])})"
        else:
            mask = fallback_center_mask(img_size)
            mask_source = "fallback_center"

    # Prompt 組裝：使用者輸入 text_prompt 為主，風格資訊為輔
    user_text = (user_input.get("text_prompt") or "").strip()
    auto_prompt, negative_prompt = build_inpaint_prompt(req, style_params, target_objects)

    # 純移除動作詞集合
    _REMOVAL_ACTIONS = {"刪除", "移除", "去除", "清除", "刪掉", "拿掉"}

    # 動作詞對照表：中文 → 英文 inpainting 指令模板
    _ACTION_TEMPLATES = {
        "刪除":  "Remove the {obj} completely. {fill}",
        "移除":  "Remove the {obj} completely. {fill}",
        "去除":  "Remove the {obj} completely. {fill}",
        "清除":  "Remove the {obj} completely. {fill}",
        "刪掉":  "Remove the {obj} completely. {fill}",
        "拿掉":  "Remove the {obj} completely. {fill}",
        "換掉":  "Replace the {obj} with a suitable alternative that matches the room style",
        "換一個": "Replace the {obj} with a suitable alternative that matches the room style",
    }

    # 物件移除後的背景填補描述（依物件類型決定填什麼）
    _OBJ_FILL_CONTEXT: dict[str, str] = {
        "lamp":                "Fill with clean ceiling surface matching the surrounding texture and color",
        "light":               "Fill with clean ceiling surface matching the surrounding texture and color",
        "chandelier":          "Fill with clean ceiling surface matching the surrounding texture and color",
        "pendant":             "Fill with clean ceiling surface matching the surrounding texture and color",
        "sconce":              "Fill with clean wall surface matching the surrounding",
        "sofa":                "Fill with clean floor surface matching the surrounding floor material",
        "couch":               "Fill with clean floor surface matching the surrounding floor material",
        "chair":               "Fill with clean floor surface matching the surrounding floor material",
        "table":               "Fill with clean floor surface matching the surrounding floor material",
        "desk":                "Fill with clean floor surface matching the surrounding floor material",
        "coffee table":        "Fill with clean floor surface matching the surrounding floor material",
        "television receiver": "Fill with clean wall surface matching the surrounding wall color",
        "tv":                  "Fill with clean wall surface matching the surrounding wall color",
        "monitor":             "Fill with clean wall surface matching the surrounding wall color",
        "plant":               "Fill with clean floor area matching the surrounding",
        "potted plant":        "Fill with clean floor area matching the surrounding",
        "curtain":             "Fill with a clear window showing natural light",
        "rug":                 "Fill with clean floor surface matching the surrounding floor material",
        "carpet":              "Fill with clean floor surface matching the surrounding floor material",
        "shelf":               "Fill with clean wall surface matching the surrounding wall color",
        "bookcase":            "Fill with clean wall surface matching the surrounding wall color",
    }

    # 根據 seg_labels 取得最相關的填補描述
    def _get_fill_context(labels: list[str]) -> str:
        for lbl in labels:
            for key, ctx in _OBJ_FILL_CONTEXT.items():
                if key in lbl.lower() or lbl.lower() in key:
                    return ctx
        return "Fill with background that seamlessly blends with the surrounding environment"

    # 判斷是否為純移除任務
    # 無手繪遮罩：用 Vision 意圖分析結果；有手繪遮罩：fallback 到動作詞比對
    if edit_action is not None:
        is_removal = (edit_action == "remove")
    else:
        is_removal = any(a in user_text for a in _REMOVAL_ACTIONS)

    # 設定 fal.ai 推理參數
    # 移除任務：更多步數（細節更好）+ 較低 guidance（讓背景填補更自然）
    # 顏色/風格修改：標準步數 + 較高 guidance（prompt 跟隨更準）
    fal_num_steps     = 50  if is_removal else 28
    fal_guidance      = 3.0 if is_removal else 5.0

    if user_text:
        # 若 user_text 是純動作詞，補上 segmentation 偵測到的物件名稱 + 背景填補描述
        action_en = None
        for zh_action, template in _ACTION_TEMPLATES.items():
            if user_text.strip() == zh_action:
                obj_name = seg_labels[0] if seg_labels else "object"
                fill_ctx = _get_fill_context(seg_labels) if is_removal else ""
                action_en = template.format(obj=obj_name, fill=fill_ctx).strip()
                print(f"[adjuster] vague prompt '{user_text}' → auto-completed: {action_en}")
                break

        if action_en:
            en_text = action_en
        else:
            # 嘗試用 Gemini 翻譯成英文（FLUX 效果更好），失敗就直接用原文
            en_text = user_text
            try:
                from designbridge.llm import call_llm
                obj_hint = f" The selected object is: {seg_labels[0]}." if seg_labels else ""
                translated = call_llm(
                    f"Translate this interior design modification request to English in one sentence.{obj_hint} "
                    f"Return ONLY the translation, no extra words.\n\n{user_text}",
                    max_tokens=120,
                )
                t = translated.strip()
                # 至少 2 個英文字，且不以虛詞結尾（避免截斷的不完整翻譯）
                _incomplete_endings = {"a", "an", "the", "to", "of", "with", "and", "from", "in", "on", "at", "by", "for", "into", "onto"}
                last_word = t.rstrip(".").split()[-1].lower() if t else ""
                if t and len(t.split()) >= 2 and last_word not in _incomplete_endings:
                    en_text = t
                    print(f"[adjuster] translated prompt: {en_text}")
                else:
                    print(f"[adjuster] translation rejected ('{t}'), using original: {user_text}")
            except Exception:
                pass

        prompt = f"{en_text}. Photorealistic, high quality, seamless integration, well-lit interior."
    else:
        prompt = auto_prompt

    # Debug：印出送出的 prompt 與 mask 狀況
    mask_white = sum(1 for p in mask.getdata() if p > 128) if hasattr(mask, 'getdata') else -1
    mask_total = mask.width * mask.height if hasattr(mask, 'width') else -1
    print(f"[adjuster] prompt: {prompt[:120]}")
    print(f"[adjuster] mask: {mask_white}/{mask_total} white px ({mask_white/mask_total:.1%} edit area)" if mask_total > 0 else "[adjuster] mask: unknown")
    print(f"[adjuster] mask_source: {mask_source}")

    # mask 覆蓋率過低（< 2%）且無手繪遮罩：改用 Vision bbox 定位
    if (edit_action is not None and mask_total > 0
            and mask_white / mask_total < 0.02):
        target_name = (effective_labels or seg_labels or ["object"])[0]
        print(f"[adjuster] mask too small ({mask_white/mask_total:.1%}), trying vision bbox for '{target_name}'")
        bbox_mask = _bbox_mask_from_vision(image_path, target_name, img_size)
        if bbox_mask is not None:
            mask = bbox_mask
            mask_source = f"vision_bbox({target_name})"
            mask_white = sum(1 for p in mask.getdata() if p > 128)
            print(f"[adjuster] bbox mask: {mask_white}/{mask_total} white px ({mask_white/mask_total:.1%})")

    # DRY_RUN 模式：只存遮罩，不呼叫任何 inpainting API（測試用）
    import os
    if os.getenv("ADJUSTER_DRY_RUN"):
        dry_out = Path(Config.ARTIFACTS_DIR) / "render" / f"{task_id}_dry_mask.png"
        dry_out.parent.mkdir(parents=True, exist_ok=True)
        mask.save(str(dry_out))
        print(f"[adjuster] DRY_RUN: 遮罩已存到 {dry_out}，跳過 inpainting")
        return {
            "generated_image": image_path,   # 回傳原圖，讓 renderer 跳過
            "intermediate_outputs": {
                **(state.get("intermediate_outputs") or {}),
                "adjuster_agent": {"status": "dry_run", "mask_path": str(dry_out), "mask_source": mask_source},
            }
        }

    # strength：edit_scope 越小改動越保守（0.4~0.85）
    strength = max(0.4, min(0.85, edit_scope + 0.4))

    render_suffix = uuid.uuid4().hex[:8]
    out_path = Path(Config.ARTIFACTS_DIR) / "render" / f"{task_id}_{render_suffix}.png"
    backend = "placeholder"

    # 1. LaMa（純移除任務：背景重建最穩定）
    if is_removal:
        if run_lama_inpainting(image_path, mask, out_path):
            backend = "lama_inpainting"

    # 2. fal.ai FLUX.1-Fill（修改任務，或 LaMa 失敗時的 fallback）
    if backend == "placeholder" and Config.FAL_KEY:
        print(f"[adjuster] task={'removal' if is_removal else 'modification'}  steps={fal_num_steps}  guidance={fal_guidance}")
        if run_fal_inpainting(image_path, mask, prompt, out_path,
                              num_steps=fal_num_steps, guidance_scale=fal_guidance):
            backend = "fal_inpainting"

    # 4. HF Inference API
    if backend == "placeholder" and Config.HF_TOKEN:
        if run_hf_inpainting(image_path, mask, prompt, out_path):
            backend = "hf_inpainting"

    # 5. 本地 SD Inpainting
    if backend == "placeholder":
        if run_inpainting(image_path, mask, prompt, negative_prompt, strength, out_path,
                          mask_path=manual_mask_path):
            backend = "sd_inpainting"

    # 6. Fallback：複製原圖
    if backend == "placeholder":
        out_path.parent.mkdir(parents=True, exist_ok=True)
        original_img.save(str(out_path))

    adjust_plan = {
        "inpaint_regions": [{
            "target_labels": target_labels,
            "target_objects": target_objects,
            "prompt": prompt,
            "strength": strength,
            "mask_source": mask_source,
        }],
        "consistency_guidance": (req.get("style_preferences") or {}).get("primary_style", ""),
    }

    return {
        "generated_image": str(out_path),
        "render_result": {
            "generated_image_path": str(out_path),
            "generation_params": {
                "backend": backend,
                "model": "stable-diffusion-2-inpainting",
                "strength": strength,
                "mask_source": mask_source,
                "prompt_preview": prompt[:150],
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "intermediate_outputs": {
            **(state.get("intermediate_outputs") or {}),
            "adjuster_agent": adjust_plan,
        },
    }


def layout_and_style_agent_stub(state: DesignBridgeState) -> dict[str, Any]:
    """Layout + style agent.

    Layout planning is only executed when the user explicitly requests spatial reorganization
    (hint_layout=True from LLM semantic analysis). Otherwise only style params are built,
    and spatial structure is left to the depth map (if available).
    """
    req = state.get("structured_requirement") or {}
    user_input = state.get("user_input") or {}
    hint_layout = bool(req.get("hint_layout", False))

    style_params = build_style_params(req, user_input)

    scene_graph: dict[str, Any] | None = None
    layout_intermediate: dict[str, Any] = {}
    if hint_layout:
        from designbridge.layout_agent import run_layout_agent

        task_id = state.get("task_id") or str(uuid.uuid4())
        existing_layout = state.get("layout_from_depth")  # 照片萃取的現有家具位置（若有上傳圖）
        try:
            result = run_layout_agent(req, task_id, existing_layout=existing_layout)
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



def renderer(state: DesignBridgeState) -> dict[str, Any]:
    """
    Renderer: generate image from structured_requirement using Flux.
    Falls back to placeholder on failure.
    若 routing_decision 為 design_adjuster 且已有 generated_image，直接跳過不覆蓋。
    """
    # Adjuster 已產出 inpainted 圖片，renderer 不再重新生成
    if state.get("routing_decision") == "design_adjuster" and state.get("generated_image"):
        return {}

    task_id = state.get("task_id") or str(uuid.uuid4())
    req = state.get("structured_requirement") or {}
    style_params = state.get("style_params") or {}
    artifacts_root = Path(Config.ARTIFACTS_DIR)
    render_dir = artifacts_root / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    # 加入隨機短碼，確保每次生成都是獨立新檔案（避免 task_id 相同時回傳舊圖）
    render_suffix = uuid.uuid4().hex[:8]
    out_path = render_dir / f"{task_id}_{render_suffix}.png"

    prompt = _build_imagen_prompt_from_requirement(req, style_params=style_params)

    # 只有使用者明確要求重新規劃佈局時，才把 layout 結果注入 prompt
    if req.get("hint_layout"):
        scene_graph = state.get("scene_graph") or {}
        layout_prompt = (scene_graph.get("layout_prompt") or "").strip()

        if not layout_prompt:
            layout_from_depth = state.get("layout_from_depth") or {}
            if layout_from_depth:
                from designbridge.render_prompt import _layout_json_to_prompt_text
                layout_prompt = _layout_json_to_prompt_text(layout_from_depth)

        if layout_prompt:
            prompt = f"{prompt} {layout_prompt}"
            print(f"[renderer] layout_prompt injected: {layout_prompt[:80]}")

    _style_neg = (style_params.get("negative_prompt") or "").strip(", ")
    negative_prompt = f"{_BASE_NEGATIVE_PROMPT}, {_style_neg}" if _style_neg else _BASE_NEGATIVE_PROMPT
    _special = req.get("special_constraints") or {}
    if _special.get("wheelchair"):
        negative_prompt = f"{negative_prompt}, wheelchair, wheelchair user, mobility aid, disability equipment"
    if _special.get("children"):
        negative_prompt = f"{negative_prompt}, child, children, baby, toddler, kid"
    if _special.get("pets"):
        negative_prompt = f"{negative_prompt}, cat, dog, bird, rabbit, hamster, pet, animal"
    user_input = state.get("user_input") or {}

    vision = state.get("vision_features") or {}
    output_aspect = str(user_input.get("output_aspect") or "auto")
    output_size = _resolve_output_size(output_aspect, user_input.get("initial_image"))
    output_width, output_height = output_size
    generation_params: dict[str, Any] = {
        "prompt_preview": prompt[:200],
        "negative_prompt_preview": (negative_prompt or "")[:200],
        "output_aspect": output_aspect,
        "output_size": {"width": output_width, "height": output_height},
    }
    backend = "placeholder"

    if style_params:
        generation_params["style_profile_id"] = style_params.get("style_profile_id")
        generation_params["style_profile_name"] = style_params.get("style_profile_name")
        generation_params["style_strength"] = style_params.get("style_strength")

    # Get vision features for ControlNet (if available)
    depth_path = vision.get("depth")
    seg_path = vision.get("segmentation")

    # When the user re-plans layout, the input-photo depth no longer matches the new
    # furniture arrangement. Override it with the depth projected from the scene-graph
    # coordinates so the Layout Agent's precise placements actually control the render.
    if req.get("hint_layout") and Config.ENABLE_LAYOUT_DEPTH_PROJECTION:
        _sg = state.get("scene_graph") or {}
        _proj_depth = _sg.get("projected_depth_path")
        if _proj_depth and Path(_proj_depth).exists():
            depth_path = _proj_depth
            _proj_seg = _sg.get("projected_seg_path")
            if _proj_seg and Path(_proj_seg).exists():
                seg_path = _proj_seg
            print(f"[renderer] using scene-graph projected depth as ControlNet condition: {Path(_proj_depth).name}")

    controlnet_inputs: dict[str, str] = {}
    if depth_path:
        controlnet_inputs["depth"] = str(depth_path)
    if seg_path:
        controlnet_inputs["segmentation"] = str(seg_path)

    # 1. Hugging Face Inference API (cloud Flux; no local download)
    hf_model_id = Config.FLUX_MODEL

    # Use style_reference_image as control image:
    # priority: user upload > Supabase matched image > depth map
    style_method = user_input.get("style_method", "ai_analysis")
    style_reference_image = user_input.get("style_reference_image")
    user_style_reference_local: str | None = None
    if isinstance(style_reference_image, str) and style_reference_image.strip():
        style_reference_candidate = style_reference_image.strip()
        if Path(style_reference_candidate).exists():
            user_style_reference_local = style_reference_candidate
        elif style_reference_candidate.startswith(("http://", "https://")):
            try:
                from designbridge.style_supabase import download_style_image

                downloaded_ref = download_style_image(style_reference_candidate)
                if downloaded_ref and downloaded_ref.exists():
                    user_style_reference_local = str(downloaded_ref)
            except Exception as e:
                print(f"⚠️  下載使用者風格參考圖失敗：{e}")

    if user_style_reference_local:
        control_img = user_style_reference_local
        controlnet_inputs["style_reference_image"] = user_style_reference_local
        if style_method == "ai_analysis":
            _kb_url = (style_params or {}).get("reference_image_url", "")
            _kb_text = (style_params or {}).get("style_summary", "").strip()
            _is_kb_image = (
                _kb_url
                and _kb_text
                and isinstance(style_reference_image, str)
                and style_reference_image.strip() == _kb_url
            )
            if _is_kb_image:
                prompt = f"{prompt} Style reference: {_kb_text}"
                print(f"📚 Supabase KB 描述已注入 prompt（跳過 Gemini 分析）：{_kb_text[:80]}…")
            else:
                style_vision_desc = _analyze_style_image_with_gemini(user_style_reference_local)
                if style_vision_desc:
                    prompt = f"{prompt} Style reference: {style_vision_desc}"
                    generation_params["gemini_style_description"] = style_vision_desc
                    print(f"🎨 Gemini 風格描述已注入 prompt：{style_vision_desc[:80]}…")
    elif style_params and style_params.get("reference_image_path") and Path(style_params["reference_image_path"]).exists():
        control_img = style_params["reference_image_path"]
        controlnet_inputs["style_reference_image"] = control_img
        print(f"使用 Supabase 匹配圖作為風格參考：{Path(control_img).name}")
    else:
        control_img = depth_path if depth_path and Path(depth_path).exists() else None

    # IP-Adapter 模式：文字控制空間類型，圖像注入風格（fal.ai FLUX-general）
    if style_method == "ipadapter" and user_style_reference_local and backend == "placeholder":
        if not Config.FAL_KEY:
            print("⚠️  IP-Adapter 模式需要 FAL_KEY，改走 ai_analysis fallback")
        elif _render_flux_ipadapter_fal(
            user_style_reference_local, out_path, prompt=prompt,
            ip_adapter_scale=Config.FAL_IP_ADAPTER_SCALE,
            num_steps=Config.FAL_IP_ADAPTER_STEPS,
            guidance_scale=Config.FAL_IP_ADAPTER_GUIDANCE,
            output_size=(Config.FAL_IP_ADAPTER_SIZE, Config.FAL_IP_ADAPTER_SIZE),
        ):
            backend = "flux_ipadapter_fal"
            generation_params["model"] = "fal-ai/flux-general + XLabs IP-Adapter"
            generation_params["style_reference"] = user_style_reference_local
            generation_params["ip_adapter_scale"] = Config.FAL_IP_ADAPTER_SCALE

    # Redux 模式：本地 FLUX.1-Redux pipeline（需先在 HuggingFace 接受授權並下載模型）
    # DESIGNBRIDGE_ENABLE_FLUX_REDUX=true 才嘗試載入，避免未授權時每次報錯
    if style_method == "redux" and user_style_reference_local and backend == "placeholder":
        if not Config.ENABLE_FLUX_REDUX:
            print("⚠️  FLUX.1-Redux 未啟用（DESIGNBRIDGE_ENABLE_FLUX_REDUX=false），改走 ai_analysis fallback")
        elif Config.FAL_KEY and _render_flux_redux_fal(user_style_reference_local, out_path, prompt=prompt, output_size=output_size, num_steps=Config.FAL_REDUX_STEPS, guidance_scale=Config.FAL_REDUX_GUIDANCE):
            backend = "flux_redux_fal"
            generation_params["model"] = "fal-ai/flux-1/dev/redux"
            generation_params["style_reference"] = user_style_reference_local
        elif _render_flux_redux_local(user_style_reference_local, out_path, prompt=prompt, output_size=output_size):
            backend = "flux_redux_local"
            generation_params["model"] = "black-forest-labs/FLUX.1-Redux-dev (local)"
            generation_params["style_reference"] = user_style_reference_local

    # Kontext LoRA：有 depth map 時優先，保留空間結構
    # depth_conditioning_scale: 1.0=完全保留結構, 0.0=忽略深度圖
    # lora scale 直接對應 depth_conditioning_scale，不需轉換
    depth_conditioning_scale = float(req.get("depth_conditioning_scale") or 0.85)
    depth_conditioning_scale = max(0.0, min(1.0, depth_conditioning_scale))
    effective_depth_path = depth_path if depth_conditioning_scale >= 0.20 else None

    # 真正的 FLUX depth ControlNet（opt-in，需 FAL_KEY）：對深度幾何的約束遠強於 Kontext LoRA，
    # 讓 scene-graph 投影深度真正控制家具擺位。設 LAYOUT_DEPTH_CONTROL_BACKEND=controlnet 啟用。
    if (
        backend == "placeholder"
        and Config.LAYOUT_DEPTH_CONTROL_BACKEND == "controlnet"
        and Config.FAL_KEY
        and effective_depth_path and Path(str(effective_depth_path)).is_file()
    ):
        if _render_flux_controlnet_depth_fal(
            prompt, str(effective_depth_path), out_path,
            conditioning_scale=depth_conditioning_scale,
            output_size=output_size,
        ):
            backend = "flux_controlnet_depth_fal"
            generation_params["model"] = f"fal-ai/flux-general + {Config.DEPTH_CONTROLNET_MODEL}"
            generation_params["depth_conditioning_scale"] = depth_conditioning_scale

    if backend == "placeholder" and effective_depth_path and Path(str(effective_depth_path)).is_file():
        if Config.HF_TOKEN:
            if _render_hf_kontext(prompt, str(effective_depth_path), out_path,
                                  depth_conditioning_scale=depth_conditioning_scale):
                backend = "hf_kontext"
                generation_params["model"] = Config.KONTEXT_LORA_MODEL
                generation_params["provider"] = Config.KONTEXT_PROVIDER
                generation_params["depth_conditioning_scale"] = depth_conditioning_scale

    # AI 分析模式 fallback：HF Inference API
    if backend == "placeholder" and Config.ENABLE_HF_INFERENCE and Config.HF_TOKEN:
        if _render_hf_inference(prompt, out_path, model=hf_model_id, output_size=output_size):
            backend = "hf_inference"
            generation_params["model"] = hf_model_id
            generation_params["provider"] = Config.HF_INFERENCE_PROVIDER

    # 2. Local Flux model
    if backend == "placeholder" and Config.ENABLE_FLUX_FALLBACK:
        if _render_flux(prompt, out_path):
            backend = "flux"
            generation_params["model"] = hf_model_id
        else:
            generation_params["render_error"] = "local render failed"

    # 3. Fallback to placeholder
    if backend == "placeholder":
        generation_params["render_error"] = "API unavailable: both Kontext and HF Inference failed"
        print("⚠️  Renderer: all API backends failed, no image generated")

    generation_params["backend"] = backend
    path_str = str(out_path)
    render_result: dict[str, Any] = {
        "generated_image_path": path_str,
        "generation_params": generation_params,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Add controlnet_inputs if any were used
    if controlnet_inputs:
        render_result["controlnet_inputs"] = controlnet_inputs
    
    return {
        "generated_image": path_str,
        "render_result": render_result,
    }


def clip_evaluator_node(state: DesignBridgeState) -> dict[str, Any]:
    """Run CLIP evaluation on the generated image against the user's original input.

    Translates the raw user text_prompt to English before scoring so that the
    English-trained CLIP model can compare faithfully against what the user asked for.
    """
    image_path = state.get("generated_image")
    user = state.get("user_input") or {}
    raw_prompt = (user.get("text_prompt") or "").strip()

    if not image_path or not Path(image_path).is_file():
        return {"evaluation_result": {"scores": {}, "weighted_score": 0.0, "decision": "skip", "feedback": "no generated image", "issues_found": [], "suggestions": []}}

    if not raw_prompt:
        return {"evaluation_result": {"scores": {}, "weighted_score": 0.0, "decision": "skip", "feedback": "no text prompt", "issues_found": [], "suggestions": []}}

    try:
        from designbridge.clip_evaluator import evaluate, _translate_to_english
        text_prompt = _translate_to_english(raw_prompt)
        result = evaluate(image_path, text_prompt)
    except Exception as e:
        result = {"scores": {}, "weighted_score": 0.0, "decision": "skip", "feedback": f"CLIP evaluation failed: {e}", "issues_found": [], "suggestions": []}

    return {"evaluation_result": result}


def quotation_agent(state: DesignBridgeState) -> dict[str, Any]:
    """分析生成圖中的家具並對應 IKEA 商品給出報價。"""
    image_path = state.get("generated_image")
    req = state.get("structured_requirement") or {}

    if not image_path or not Path(image_path).is_file():
        return {"quotation_result": None}

    try:
        from designbridge.quotation import build_quotation
        result = build_quotation(image_path, req)
        total = len(result["furniture_list"])
        matched = result["kb_match_count"]
        print(f"[quotation] KB match: {matched}/{total} items")
        return {"quotation_result": result}
    except Exception as e:
        print(f"[quotation] failed: {e}")
        return {"quotation_result": None}
