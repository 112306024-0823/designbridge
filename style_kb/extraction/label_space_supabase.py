#!/usr/bin/env python3
"""Backfill `space` labels for Supabase `public.style_images` using CLIP.

This script downloads each `image_url`, runs a lightweight zero-shot classifier
using CLIP, then updates `style_images.space` with one of:

Usage (from project root):
    python -m style_kb.extraction.label_space_supabase
    python -m style_kb.extraction.label_space_supabase --reset
    python -m style_kb.extraction.label_space_supabase --style modern
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from dotenv import load_dotenv

load_dotenv()

sys.stdout.reconfigure(encoding="utf-8")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

MODEL_ID = "openai/clip-vit-base-patch32"
IMAGE_BATCH_SIZE = 8


@dataclass(frozen=True)
class SpaceCandidate:
    label: str
    prompt: str


SPACE_CANDIDATES: tuple[SpaceCandidate, ...] = (
    SpaceCandidate("客廳", "a photo of a living room interior design"),
    SpaceCandidate("餐廳", "a photo of a dining room interior design"),
    SpaceCandidate("房間", "a photo of a bedroom interior design"),
    SpaceCandidate("廚房", "a photo of a kitchen interior design"),
    SpaceCandidate("書房", "a photo of a study room interior design"),
    SpaceCandidate("玄關", "a photo of a hallway interior design"),
    SpaceCandidate("廁所", "a photo of a toilet interior design"),
    SpaceCandidate("陽台", "a photo of a balcony interior design"),
    SpaceCandidate("辦公室", "a photo of a office interior design"),
    SpaceCandidate("其他", "a photo of an interior space"),
)


def _fetch_image(url: str):
    """Download image URL → PIL.Image. Returns None on failure."""
    try:
        import httpx
        from PIL import Image

        resp = httpx.get(url, timeout=25, follow_redirects=True)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        print(f"    ⚠️  下載失敗 {url[:60]}... → {e}")
        return None


def _chunked(items: list[dict], n: int) -> Iterable[list[dict]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def _predict_spaces(images) -> list[tuple[str, float]]:
    """Predict (label, confidence) for each image using CLIP."""
    import torch
    from transformers import CLIPModel, CLIPProcessor

    processor = CLIPProcessor.from_pretrained(MODEL_ID)
    model = CLIPModel.from_pretrained(MODEL_ID)
    model.eval()

    texts = [c.prompt for c in SPACE_CANDIDATES]

    inputs = processor(text=texts, images=images, return_tensors="pt", padding=True, truncation=True, max_length=77)
    with torch.no_grad():
        outputs = model(**inputs)
        image_emb = outputs.image_embeds  # (B, D)
        text_emb = outputs.text_embeds  # (T, D)

    image_emb = image_emb / image_emb.norm(dim=-1, keepdim=True)
    text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)

    # cosine similarities: (B, T)
    sims = (image_emb @ text_emb.T).cpu().numpy()

    preds: list[tuple[str, float]] = []
    for row in sims:
        best_idx = int(np.argmax(row))
        best_score = float(row[best_idx])

        # If the best match is weak, fall back to "其他"
        if best_score < 0.20:
            preds.append(("其他", best_score))
            continue

        preds.append((SPACE_CANDIDATES[best_idx].label, best_score))

    return preds


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", help="只處理指定風格（style_id）")
    parser.add_argument("--reset", action="store_true", help="重算所有行（含已有 space）")
    args = parser.parse_args()

    from supabase import create_client

    client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

    q = client.table("style_images").select("id,style_id,image_url,space")
    if not args.reset:
        q = q.is_("space", "null")
    if args.style:
        q = q.eq("style_id", args.style)
    rows = q.execute().data or []

    print(f"待處理：{len(rows)} 筆")
    if not rows:
        print("無需處理。")
        return

    done = 0
    skipped = 0

    for batch in _chunked(rows, IMAGE_BATCH_SIZE):
        images = []
        valid_rows = []

        for row in batch:
            img = _fetch_image(row["image_url"])
            if img is None:
                skipped += 1
                continue
            images.append(img)
            valid_rows.append(row)

        if not images:
            continue

        preds = _predict_spaces(images)
        for row, (label, score) in zip(valid_rows, preds):
            client.table("style_images").update({"space": label}).eq("id", row["id"]).execute()
            done += 1

        print(f"  {done}/{len(rows)} 完成，{skipped} 筆跳過...")

    print(f"\n完成：{done} 筆已寫入 space，{skipped} 筆跳過")


if __name__ == "__main__":
    main()

