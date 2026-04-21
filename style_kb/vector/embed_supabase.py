#!/usr/bin/env python3
"""為 Supabase style_images 表產生 text embedding，存入 embedding 欄位。

文字來源優先順序：
  1. style_kb JSON（Gemini 萃取，資訊最豐富）
  2. source_meta JSON（style / size / kind / region）

Usage (from project root):
    python -m style_kb.embed_supabase              # 處理所有 embedding IS NULL
    python -m style_kb.embed_supabase --style modern
    python -m style_kb.embed_supabase --reset      # 重算所有（含已有向量的）
"""

from __future__ import annotations

import argparse
import os
import sys; sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
BATCH_SIZE = 64


def build_document(row: dict) -> str:
    style_id = row.get("style_id", "")
    kb = row.get("style_kb") or {}
    meta = row.get("source_meta") or {}

    if kb:
        style_info = kb.get("style_info", {})
        visual = kb.get("visual_elements", {})
        ai_params = kb.get("ai_params", {})
        tags = "、".join(style_info.get("tags", []))
        materials = "、".join(
            f"{m.get('target','')}:{m.get('type','')}"
            for m in visual.get("materials", [])
        )
        colors = visual.get("colors", {})
        color_text = f"主色{colors.get('primary','')} 輔色{colors.get('secondary','')} 點綴{colors.get('accent','')}"
        lighting = visual.get("lighting", {})
        light_text = f"{lighting.get('type','')} {lighting.get('color_temp','')}K"
        positive = ai_params.get("prompts", {}).get("positive", "")
        return f"{style_id}風格。標籤：{tags}。材質：{materials}。色調：{color_text}。光線：{light_text}。{positive}"

    style_zh = meta.get("style", style_id)
    size = meta.get("size", "")
    kind = meta.get("kind", "")
    region = meta.get("region", "")
    return f"{style_zh}風格。{size} {kind} {region}".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", help="只處理指定風格")
    parser.add_argument("--reset", action="store_true", help="重算所有行（含已有向量）")
    args = parser.parse_args()

    from supabase import create_client
    from sentence_transformers import SentenceTransformer

    client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"模型載入：{EMBEDDING_MODEL}")

    # 讀取目標行
    q = client.table("style_images").select("id,style_id,style_kb,source_meta")
    if not args.reset:
        q = q.is_("embedding", "null")
    if args.style:
        q = q.eq("style_id", args.style)
    rows = q.execute().data
    print(f"待處理：{len(rows)} 筆")

    if not rows:
        print("無需處理。")
        return

    # 批次 embed
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        docs = [build_document(r) for r in batch]
        embeddings = model.encode(docs, normalize_embeddings=True).tolist()

        for row, emb in zip(batch, embeddings):
            client.table("style_images").update({"embedding": emb}).eq("id", row["id"]).execute()

        done = min(i + BATCH_SIZE, len(rows))
        print(f"  {done}/{len(rows)}...")

    print(f"完成：{len(rows)} 筆向量已寫入")


if __name__ == "__main__":
    main()
