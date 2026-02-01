#!/usr/bin/env python3
# app.py
"""DesignBridge Streamlit web interface for testing."""

import json
import tempfile
import time
from pathlib import Path

import streamlit as st

from designbridge import get_compiled_graph

st.set_page_config(page_title="DesignBridge Test Interface", page_icon="🏠", layout="wide")

st.title("DesignBridge 測試介面")
st.markdown("輸入設計需求，查看 LangGraph 工作流的路由與執行結果")

# Sidebar for input
st.sidebar.header("輸入參數")

text_prompt = st.sidebar.text_area(
    "文字需求 (text_prompt)",
    value="客廳想要北歐風格，希望動線順暢",
    height=100,
    help="描述你的室內設計需求，例如風格、功能、布局等",
)

edit_scope = st.sidebar.slider(
    "改動幅度 (edit_scope)",
    min_value=0.0,
    max_value=1.0,
    value=0.6,
    step=0.1,
    help="0.0 = 最小改動（局部微調），1.0 = 大幅改動（完全重新設計）",
)

# 圖片上傳：上傳檔案或留空表示從空布局開始
st.sidebar.markdown("**初始空間圖片（可選）**")
uploaded_file = st.sidebar.file_uploader(
    "上傳現況照片或參考圖",
    type=["jpg", "jpeg", "png", "webp"],
    help="支援 JPG、PNG、WebP。留空表示從空布局開始。",
    label_visibility="collapsed",
)

# 上傳後顯示預覽與路徑
initial_image = ""
if uploaded_file is not None:
    # 暫存到 temp，取得路徑供工作流使用
    suffix = Path(uploaded_file.name).suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        initial_image = tmp.name
    st.sidebar.image(uploaded_file, caption="已上傳預覽", width="stretch")
    st.sidebar.caption(f"路徑：`{initial_image}`")
else:
    st.sidebar.caption("未上傳圖片：將從空布局開始")
    with st.sidebar.expander("進階：手動輸入圖片路徑"):
        manual_path = st.text_input(
            "圖片路徑",
            value="",
            help="若已有本機路徑可在此輸入",
            label_visibility="collapsed",
        )
        if manual_path and manual_path.strip():
            initial_image = manual_path.strip()

run_button = st.sidebar.button("▶️ 執行工作流", type="primary", width="stretch")

# Example prompts
st.sidebar.markdown("---")
st.sidebar.markdown("**💡 範例提示詞**")
example_prompts = {
    "布局優化": "客廳動線不順暢，希望重新規劃布局",
    "風格變更": "想要改成現代簡約風格",
    "局部微調": "只想調整沙發位置和顏色",
    "布局+風格": "北歐風格，開放式空間，動線順暢",
}
for name, prompt in example_prompts.items():
    if st.sidebar.button(f"📌 {name}", key=name, width="stretch"):
        st.session_state["example_prompt"] = prompt
        st.rerun()

if "example_prompt" in st.session_state:
    text_prompt = st.session_state["example_prompt"]
    del st.session_state["example_prompt"]

# Main content: 工作流圖示（Mermaid，可收合）
with st.expander("Workflow Diagram", expanded=True):
    try:
        _compiled = get_compiled_graph()
        _drawable = _compiled.get_graph()
        _mermaid_str = _drawable.draw_mermaid()
        try:
            _png_bytes = _drawable.draw_mermaid_png()
            st.image(_png_bytes, use_container_width=True)
        except Exception:
            st.caption("圖示以 Mermaid 原始碼顯示於下方。")
        with st.expander("🔍 檢視 / 複製 Mermaid 原始碼"):
            st.code(_mermaid_str, language="mermaid")
            st.caption("可複製到 [mermaid.live](https://mermaid.live) 編輯或匯出。")
    except Exception as e:
        st.warning(f"工作流圖無法載入：{e}")

st.markdown("---")

if run_button:
    if not text_prompt.strip():
        st.error("❌ 請輸入文字需求")
    else:
        with st.spinner("🔄 執行 DesignBridge 工作流..."):
            # Build initial state
            user_input = {
                "text_prompt": text_prompt,
                "edit_scope": edit_scope,
            }
            if initial_image:
                user_input["initial_image"] = initial_image

            initial_state = {"user_input": user_input}

            # Invoke graph
            try:
                compiled = get_compiled_graph()
                t0 = time.perf_counter()
                result = compiled.invoke(initial_state)
                elapsed = time.perf_counter() - t0

                # Display results
                st.success(f"工作流執行完成！（耗時 {elapsed:.2f} 秒）")

                # Key results in columns
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Task ID", result.get("task_id", "N/A")[:8] + "...")
                with col2:
                    st.metric("Iteration", result.get("iteration", 0))
                with col3:
                    routing = result.get("routing_decision", "N/A")
                    emoji_map = {
                        "layout": "📐",
                        "style": "🎨",
                        "design_adjuster": "🔧",
                        "layout_and_style": "📐🎨",
                    }
                    st.metric("路由決策", f"{emoji_map.get(routing, '❓')} {routing}")
                with col4:
                    st.metric("執行秒數", f"{elapsed:.2f} s")

                # Generated image (Renderer output)
                st.subheader("🖼️ 生成圖")
                gen_path = result.get("generated_image")
                render_result = result.get("render_result") or {}
                if gen_path and Path(gen_path).exists():
                    st.image(gen_path, caption="Renderer 輸出", use_container_width=True)
                    st.caption(f"路徑：`{gen_path}`")
                    gp = render_result.get("generation_params") or {}
                    backend = gp.get("backend", "")
                    if backend == "sdxl":
                        st.success("使用本機 SDXL 生成（免費）")
                    elif backend == "imagen":
                        st.caption("使用 Imagen API 生成")
                    elif gp.get("fallback") == "placeholder":
                        st.info("⚠️ Imagen 未可用且 SDXL 未成功，已顯示佔位圖。可安裝 diffusers 啟用本機 SDXL。")
                elif gen_path:
                    st.warning(f"生成圖路徑不存在：`{gen_path}`")
                else:
                    st.info("無生成圖")

                # Structured requirement
                st.subheader("📋 結構化需求（Requirement JSON）")
                req = result.get("structured_requirement", {})
                if req:
                    # Display key fields
                    col1, col2, col3, col4 = st.columns(4)
                    meta = req.get("meta", {})
                    style_prefs = req.get("style_preferences", {})
                    edit_scope_info = req.get("edit_scope", {})

                    with col1:
                        st.write("**房間類型**")
                        st.code(meta.get("room_type", "N/A"))
                    with col2:
                        st.write("**設計目標**")
                        st.code(meta.get("design_goal", "N/A"))
                    with col3:
                        st.write("**主要風格**")
                        st.code(style_prefs.get("primary_style", "N/A"))
                    with col4:
                        st.write("**Edit Scope**")
                        st.code(f"{edit_scope_info.get('scope_value', 0):.1f}")

                    # Priority weights
                    weights = req.get("priority_weights", {})
                    if weights:
                        st.write("**評估權重**")
                        wcol1, wcol2, wcol3 = st.columns(3)
                        with wcol1:
                            st.metric("佈局合理性", f"{weights.get('layout_rationality', 0):.1f}")
                        with wcol2:
                            st.metric("風格一致性", f"{weights.get('style_consistency', 0):.1f}")
                        with wcol3:
                            st.metric("創新程度", f"{weights.get('novelty', 0):.1f}")

                    # Constraints summary
                    constraints = req.get("layout_constraints", {})
                    must_add = constraints.get("must_add", [])
                    must_keep = constraints.get("must_keep", [])
                    if must_add or must_keep:
                        st.write("**佈局約束**")
                        if must_keep:
                            st.write(f"必留家具：{', '.join(must_keep)}")
                        if must_add:
                            st.write(f"必加家具：{', '.join(must_add)}")

                    with st.expander("🔍 完整 Requirement JSON"):
                        st.json(req)
                else:
                    st.info("無結構化需求")

                # Vision features
                st.subheader("👁️ 視覺前處理結果")
                vision = result.get("vision_features", {})
                if vision:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Segmentation**")
                        seg_path = vision.get("segmentation", "N/A")
                        st.code(seg_path)
                        try:
                            if isinstance(seg_path, str) and Path(seg_path).exists():
                                st.image(seg_path, caption="Segmentation label map", width="stretch")
                        except Exception:
                            pass
                    with col2:
                        st.write("**Depth Map**")
                        depth_path = vision.get("depth", "N/A")
                        st.code(depth_path)
                        try:
                            if isinstance(depth_path, str) and Path(depth_path).exists():
                                st.image(depth_path, caption="Depth map", width="stretch")
                        except Exception:
                            pass
                    with st.expander("🔍 完整 vision_features JSON"):
                        st.json(vision)
                else:
                    st.info("無視覺特徵")

                # Intermediate outputs
                st.subheader("🔄 中間輸出")
                intermediate = result.get("intermediate_outputs", {})
                if intermediate:
                    st.json(intermediate)
                else:
                    st.info("無中間輸出")

                # Full state
                with st.expander("🗂️ 完整 State JSON"):
                    st.json(result)

            except Exception as e:
                st.error(f"❌ 執行失敗：{e}")
                st.exception(e)
else:
    # Show placeholder
    st.info("👈 請在左側輸入參數，然後點擊「執行工作流」按鈕")

    # Display workflow diagram
    st.subheader("📊 DesignBridge 工作流")
    st.markdown(
        """
```
START
  ↓
Requirement Analyzer (需求解析)
  ↓
Visual Preprocessing (視覺前處理, stub)
  ↓
Design Director (任務路由)
  ↓
  ├─→ Layout Agent (佈局代理人)
  ├─→ Style Agent (風格代理人)
  ├─→ Design Adjuster (微調代理人)
  └─→ Layout + Style Agent (協作)
  ↓
END
```
    """
    )

    st.markdown("---")
    st.markdown("**路由邏輯**")
    st.markdown(
        """
- **Design Adjuster**：`edit_scope < 0.3` 或關鍵字「局部」、「微調」
- **Layout**：關鍵字「動線」、「布局」、「layout」
- **Style**：關鍵字「風格」、「style」、「色彩」
- **Layout + Style**：同時包含布局與風格，或預設值
    """
    )

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("**DesignBridge v0.1**")
st.sidebar.markdown("使用 LangGraph 建構的多代理室內設計工作流")
