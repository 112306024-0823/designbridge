#!/usr/bin/env python3
"""Backfill `style_kb_embedding` for Supabase `public.style_images`.

This script precomputes a text embedding from each row's `style_kb` JSON and stores
it in `style_kb_embedding` (pgvector). After this, text-to-text retrieval can use
the Postgres RPC `public.query_style_kb` for fast top-k search.

Usage (from project root):
    python -m style_kb.vector.embed_style_kb_supabase
    python -m style_kb.vector.embed_style_kb_supabase --reset
    python -m style_kb.vector.embed_style_kb_supabase --style modern

Env:
  - SUPABASE_URL
  - SUPABASE_SERVICE_ROLE_KEY
  - DESIGNBRIDGE_TEXT_EMBEDDING_MODEL (default: BAAI/bge-m3)

Notes:
  - The DB column is created as `vector(1024)` by migration.
  - If you change embedding model dimension, you must also migrate the column.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _compose_style_kb_text(row: dict[str, Any]) -> str:
    """Mirror backend composition logic for style_kb search text."""
    style_kb = row.get("style_kb") or {}
    source_meta = row.get("source_meta") or {}
    parts: list[str] = []

    style_info = style_kb.get("style_info") if isinstance(style_kb, dict) else {}
    if isinstance(style_info, dict):
        name = style_info.get("name")
        if name:
            parts.append(str(name))
        tags = style_info.get("tags")
        if isinstance(tags, list):
            parts.append(" ".join(str(t) for t in tags if t))

    desc = style_kb.get("description") if isinstance(style_kb, dict) else None
    if desc:
        parts.append(str(desc))

    visual = style_kb.get("visual_elements") if isinstance(style_kb, dict) else {}
    if isinstance(visual, dict):
        mats = visual.get("materials")
        if isinstance(mats, list):
            for m in mats:
                if isinstance(m, dict):
                    parts.append(
                        " ".join(
                            str(m.get(k, "")).strip()
                            for k in ("type", "finish", "target")
                            if m.get(k)
                        )
                    )
        lighting = visual.get("lighting")
        if isinstance(lighting, dict):
            if lighting.get("type"):
                parts.append(str(lighting["type"]))
            if lighting.get("color_temp"):
                parts.append(f"{lighting['color_temp']}K")

    ai = style_kb.get("ai_params") if isinstance(style_kb, dict) else {}
    if isinstance(ai, dict):
        prompts = ai.get("prompts")
        if isinstance(prompts, dict) and prompts.get("positive"):
            parts.append(str(prompts["positive"]))

    if source_meta.get("style"):
        parts.append(str(source_meta["style"]))
    if source_meta.get("kind"):
        parts.append(str(source_meta["kind"]))
    if row.get("style_id"):
        parts.append(str(row["style_id"]))

    return " ".join(p.replace("\n", " ").strip() for p in parts if p and str(p).strip())


def _encode_query_text(text: str, model_name: str) -> str:
    """Apply model-specific instruction prefix (same as backend)."""
    t = text.strip()
    name = model_name.lower()
    if "e5" in name:
        return f"query: {t}"
    if "bge" in name:
        return f"Represent this sentence for retrieving relevant interior design style references: {t}"
    return t


def _encode_passage_texts(texts: list[str], model_name: str) -> list[str]:
    """Apply model-specific passage prefix (same as backend)."""
    name = model_name.lower()
    if "e5" in name:
        return [f"passage: {t}" for t in texts]
    return texts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", help="Only backfill a specific style_id")
    parser.add_argument("--reset", action="store_true", help="Recompute even if embedding exists")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    supabase_url = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    model_name = os.getenv("DESIGNBRIDGE_TEXT_EMBEDDING_MODEL", "BAAI/bge-m3")

    from supabase import create_client
    from sentence_transformers import SentenceTransformer

    client = create_client(supabase_url, service_role_key)
    model = SentenceTransformer(model_name)

    q = client.table("style_images").select("id,style_id,image_url,source_meta,style_kb,style_kb_embedding")
    q = q.not_.is_("style_kb", "null")
    if not args.reset:
        q = q.is_("style_kb_embedding", "null")
    if args.style:
        q = q.eq("style_id", args.style)

    rows = q.execute().data or []
    print(f"待處理：{len(rows)} 筆")
    if not rows:
        return

    # Build docs
    docs: list[str] = []
    ids: list[str] = []
    for r in rows:
        text = _compose_style_kb_text(r)
        if not text:
            continue
        docs.append(text)
        ids.append(r["id"])

    if not docs:
        print("沒有可用的 style_kb 文本可嵌入。")
        return

    # Encode in batches
    prepared_docs = _encode_passage_texts(docs, model_name=model_name)
    done = 0
    for i in range(0, len(prepared_docs), args.batch_size):
        chunk_texts = prepared_docs[i : i + args.batch_size]
        chunk_ids = ids[i : i + args.batch_size]

        embs = model.encode(chunk_texts, normalize_embeddings=True)
        if len(embs.shape) != 2:
            raise RuntimeError(f"Unexpected embedding shape: {embs.shape}")
        dim = int(embs.shape[1])
        if dim != 1024:
            raise RuntimeError(
                f"Embedding dim={dim} does not match DB column vector(1024). "
                "Please migrate style_kb_embedding dimension or change model."
            )

        for row_id, emb in zip(chunk_ids, embs.tolist(), strict=False):
            client.table("style_images").update({"style_kb_embedding": emb}).eq("id", row_id).execute()
            done += 1

        print(f"  {done}/{len(ids)} 完成...")

    print(f"完成：{done} 筆 style_kb_embedding 已寫入")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

