#!/usr/bin/env python3
"""Build ChromaDB vector store from per-image Style KB JSONs.

Usage (from project root):
    python -m style_kb.build_vector_store           # 建立全部風格
    python -m style_kb.build_vector_store country   # 只建 country
    python -m style_kb.build_vector_store --reset   # 清空重建

索引資料來源：style_kb/outputs/<style_id>/<image_stem>.json
向量庫輸出：  style_kb/vector_store/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from style_kb.styles import STYLES

# ── 設定 ─────────────────────────────────────────────────────────────────────

VECTOR_STORE_DIR = Path(__file__).resolve().parent / "vector_store"
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
IMAGES_DIR = Path(__file__).resolve().parent / "images"

COLLECTION_NAME = "style_images"

# 多語言 sentence-transformers 模型（支援中文+英文，約 120MB）
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

VALID_STYLE_IDS = {style_id for style_id, _ in STYLES}


# ── 文字組合 ──────────────────────────────────────────────────────────────────

def _build_document(data: dict, style_name: str) -> str:
    """把 per-image JSON 的關鍵欄位組合成可 embed 的文字段落。"""
    style_info = data.get("style_info", {})
    visual = data.get("visual_elements", {})
    ai_params = data.get("ai_params", {})

    tags = "、".join(style_info.get("tags", []))

    materials = visual.get("materials", [])
    material_text = "、".join(
        f"{m.get('target', '')}:{m.get('type', '')}" for m in materials
    )

    colors = visual.get("colors", {})
    color_text = (
        f"主色{colors.get('primary', '')} "
        f"輔色{colors.get('secondary', '')} "
        f"點綴{colors.get('accent', '')}"
    )

    lighting = visual.get("lighting", {})
    light_text = f"{lighting.get('type', '')} {lighting.get('color_temp', '')}K"

    positive_prompt = ai_params.get("prompts", {}).get("positive", "")

    return (
        f"{style_name}風格。"
        f"標籤：{tags}。"
        f"材質：{material_text}。"
        f"色調：{color_text}。"
        f"光線：{light_text}。"
        f"{positive_prompt}"
    )


def _build_metadata(data: dict, style_id: str, style_name: str,
                    image_path: Path, json_path: Path) -> dict:
    """從 JSON 抽取 ChromaDB metadata（只能是 str / int / float）。"""
    style_info = data.get("style_info", {})
    visual = data.get("visual_elements", {})
    ai_params = data.get("ai_params", {})

    colors = visual.get("colors", {})
    lighting = visual.get("lighting", {})
    adapter = ai_params.get("adapter_config", {})

    return {
        "style_id": style_id,
        "style_name": style_name,
        "image_path": str(image_path),
        "json_path": str(json_path),
        "tags": ",".join(style_info.get("tags", [])),
        "primary_color": colors.get("primary", ""),
        "secondary_color": colors.get("secondary", ""),
        "accent_color": colors.get("accent", ""),
        "color_temp": int(lighting.get("color_temp", 0)),
        "ip_adapter_weight": float(adapter.get("ip_adapter_weight", 0.85)),
        "controlnet": adapter.get("controlnet", "depth"),
        "positive_prompt": ai_params.get("prompts", {}).get("positive", ""),
        "negative_prompt": ai_params.get("prompts", {}).get("negative", ""),
    }


# ── 建索引 ────────────────────────────────────────────────────────────────────

def build(style_filter: str | None = None, reset: bool = False) -> None:
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

    client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            print("🗑️  已清空舊向量庫")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    styles_to_process = [
        (sid, sname) for sid, sname in STYLES
        if style_filter is None or sid == style_filter
    ]

    total_added = 0
    total_skipped = 0

    for style_id, style_name in styles_to_process:
        style_out_dir = OUTPUTS_DIR / style_id
        style_img_dir = IMAGES_DIR / style_id

        if not style_out_dir.is_dir():
            print(f"⏭️  略過 {style_id}：無 outputs 資料夾")
            continue

        json_files = sorted(style_out_dir.glob("*.json"))
        if not json_files:
            print(f"⏭️  略過 {style_id}：無 JSON 檔案")
            continue

        print(f"\n📁 [{style_name} / {style_id}] 共 {len(json_files)} 筆")

        for json_path in json_files:
            doc_id = f"{style_id}_{json_path.stem}"

            # 已存在則跳過（增量更新）
            existing = collection.get(ids=[doc_id])
            if existing["ids"]:
                print(f"  ⏭️  {json_path.name} (已存在)")
                total_skipped += 1
                continue

            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  ❌ 讀取失敗 {json_path.name}: {e}")
                continue

            # 找對應圖片（jpg / png / webp）
            image_path = Path("N/A")
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                candidate = style_img_dir / (json_path.stem + ext)
                if candidate.exists():
                    image_path = candidate
                    break

            document = _build_document(data, style_name)
            metadata = _build_metadata(
                data, style_id, style_name, image_path, json_path
            )

            collection.add(
                ids=[doc_id],
                documents=[document],
                metadatas=[metadata],
            )
            print(f"  ✅ {json_path.name}")
            total_added += 1

    print(f"\n🎯 完成：新增 {total_added} 筆，跳過 {total_skipped} 筆")
    print(f"   向量庫位置：{VECTOR_STORE_DIR}")
    print(f"   目前總筆數：{collection.count()}")


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build ChromaDB vector store for Style KB")
    parser.add_argument(
        "style_filter",
        nargs="?",
        default=None,
        help="只處理指定風格（例如 country）",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="清空向量庫後重建",
    )
    args = parser.parse_args()

    if args.style_filter and args.style_filter not in VALID_STYLE_IDS:
        print(f"❌ 風格 '{args.style_filter}' 不存在。")
        print(f"有效風格：{', '.join(sid for sid, _ in STYLES)}")
        return

    build(style_filter=args.style_filter, reset=args.reset)


if __name__ == "__main__":
    main()
