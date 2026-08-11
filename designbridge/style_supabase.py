"""Supabase-backed style vector search.

Embeds query text, calls pgvector RPC, downloads the matched image,
and passes it as the style reference image for generation.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_text_embedding_model = None
_supabase_client = None

STYLE_REF_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "style_ref"

_STYLE_PROMPTS: dict[str, dict[str, str]] = {
    "modern":     {"positive": "modern contemporary interior, clean lines, neutral tones, minimalist, photorealistic, high quality", "negative": "cluttered, dark, vintage, rustic"},
    "nordic":     {"positive": "Nordic Scandinavian interior, white walls, light wood, cozy minimalist, natural light, photorealistic, high quality", "negative": "cluttered, dark, tropical, ornate"},
    "japanese":   {"positive": "Japanese minimalist Japandi interior, tatami, shoji, natural wood, wabi-sabi, photorealistic, high quality", "negative": "cluttered, colorful, western, ornate"},
    "industrial": {"positive": "industrial loft interior, exposed brick, metal, raw concrete, Edison bulbs, photorealistic, high quality", "negative": "cozy, traditional, pastel, ornate"},
    "american":   {"positive": "American style interior, warm wood, comfortable furniture, traditional, welcoming, photorealistic, high quality", "negative": "minimalist, industrial, cold"},
    "classic":    {"positive": "classical traditional interior, symmetry, rich fabrics, crown molding, warm lighting, photorealistic, high quality", "negative": "minimalist, industrial, raw"},
    "country":    {"positive": "country rustic farmhouse interior, warm wood, linen, natural materials, cozy, photorealistic, high quality", "negative": "minimalist, industrial, cold, sterile"},
    "luxury":     {"positive": "luxury high-end interior, marble, gold accents, velvet, opulent, photorealistic, high quality", "negative": "minimalist, rustic, budget"},
    "neoclassic": {"positive": "neoclassical interior, elegant columns, symmetry, refined details, warm tones, photorealistic, high quality", "negative": "minimalist, industrial, rustic"},
}


def _get_text_embedding_model():
    global _text_embedding_model
    if _text_embedding_model is None:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("DESIGNBRIDGE_TEXT_EMBEDDING_MODEL", "BAAI/bge-m3")
        _text_embedding_model = SentenceTransformer(model_name)
    return _text_embedding_model


def _encode_query_text(text: str):
    """Encode retrieval query with model-specific prompt format."""
    model = _get_text_embedding_model()
    model_name = getattr(model, "model_card_data", None)
    name = ""
    if model_name and getattr(model_name, "model_id", None):
        name = str(model_name.model_id).lower()
    else:
        name = str(os.getenv("DESIGNBRIDGE_TEXT_EMBEDDING_MODEL", "BAAI/bge-m3")).lower()

    t = text.strip()
    if "e5" in name:
        t = f"query: {t}"
    elif "bge" in name:
        t = f"Represent this sentence for retrieving relevant interior design style references: {t}"

    return model.encode(t, normalize_embeddings=True)


def _encode_passage_texts(texts: list[str]):
    """Encode candidate passages with model-specific prompt format."""
    model = _get_text_embedding_model()
    model_name = getattr(model, "model_card_data", None)
    name = ""
    if model_name and getattr(model_name, "model_id", None):
        name = str(model_name.model_id).lower()
    else:
        name = str(os.getenv("DESIGNBRIDGE_TEXT_EMBEDDING_MODEL", "BAAI/bge-m3")).lower()

    prepared = texts
    if "e5" in name:
        prepared = [f"passage: {t}" for t in texts]

    return model.encode(prepared, normalize_embeddings=True)


def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _supabase_client


@dataclass
class SupabaseStyleResult:
    style_id: str
    image_url: str
    style_name: str
    similarity: float
    style_kb: dict[str, Any] | None = None


def _batch_load_style_kb(
    client,
    results: list["SupabaseStyleResult"],
) -> None:

    if not results:
        return
    image_urls = [r.image_url for r in results]
    try:
        rows = (
            client.table("style_images")
            .select("image_url,style_kb")
            .in_("image_url", image_urls)
            .execute()
            .data
            or []
        )
        kb_map: dict[str, dict[str, Any]] = {
            row["image_url"]: row["style_kb"]
            for row in rows
            if isinstance(row.get("style_kb"), dict)
        }
        for r in results:
            r.style_kb = kb_map.get(r.image_url)
    except Exception as e:
        print(f"⚠️ Batch style_kb 載入失敗：{e}")


def query_style_images_supabase(
    text_query: str,
    style_id: str | None = None,
    top_k: int = 3,
) -> list[SupabaseStyleResult]:
    """Search style images by text query (text-to-text: query text embedding vs
    style_kb text synthesized from JSON)."""
    q = text_query.strip() or style_id or "interior design"
    return _query_style_text_to_text(
        text_query=q,
        style_id=style_id,
        top_k=top_k,
    )


def _compose_style_kb_text(row: dict[str, Any]) -> str:
    """Build a compact searchable text from style_kb JSON."""
    style_kb = row.get("style_kb") or {}
    source_meta = row.get("source_meta") or {}
    parts: list[str] = []

    style_info = style_kb.get("style_info") if isinstance(style_kb, dict) else {}
    if isinstance(style_info, dict):
        name = style_info.get("name") or style_info.get("style")
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
                elif isinstance(m, str) and m.strip():
                    parts.append(m.strip())
        lighting = visual.get("lighting")
        if isinstance(lighting, dict):
            if lighting.get("type"):
                parts.append(str(lighting["type"]))
            if lighting.get("color_temp"):
                parts.append(f"{lighting['color_temp']}K")

    ai = style_kb.get("ai_params") if isinstance(style_kb, dict) else {}
    pos_from_kb, _ = _extract_kb_prompts(ai if isinstance(ai, dict) else None)
    if pos_from_kb:
        parts.append(pos_from_kb)

    # fallback metadata
    if source_meta.get("style"):
        parts.append(str(source_meta["style"]))
    if source_meta.get("kind"):
        parts.append(str(source_meta["kind"]))

    style_id_val = row.get("style_id")
    if style_id_val:
        parts.append(str(style_id_val))

    # normalize whitespace and keep deterministic order
    return " ".join(p.replace("\n", " ").strip() for p in parts if p and str(p).strip())


def _query_style_text_to_text(
    text_query: str,
    style_id: str | None,
    top_k: int,
) -> list[SupabaseStyleResult]:
    """Text-to-text retrieval using style_kb textual representation."""
    client = _get_supabase()
    query_emb = _encode_query_text(text_query)

    # Fast path: query precomputed style_kb_embedding via pgvector RPC (Supabase).
    # Falls back to in-Python ranking if RPC/column is not available yet.
    try:
        res = client.rpc(
            "query_style_kb",
            {
                "query_embedding": query_emb.tolist(),
                "filter_style_id": style_id or "",
                "top_k": int(top_k),
            },
        ).execute()
        if res.data:
            results: list[SupabaseStyleResult] = []
            for row in res.data:
                style_name = (row.get("source_meta") or {}).get("style", row["style_id"])
                results.append(
                    SupabaseStyleResult(
                        style_id=row["style_id"],
                        image_url=row["image_url"],
                        style_name=style_name,
                        similarity=round(float(row["similarity"]), 4),
                    )
                )
            _batch_load_style_kb(client, results)
            return results
    except Exception:
        # silent fallback (keeps current behavior for older DBs)
        pass

    q = client.table("style_images").select("style_id,image_url,source_meta,style_kb")
    q = q.not_.is_("style_kb", "null")
    if style_id:
        q = q.eq("style_id", style_id)
    rows = q.execute().data or []
    if not rows:
        return []

    docs: list[str] = []
    valid_rows: list[dict[str, Any]] = []
    for row in rows:
        text = _compose_style_kb_text(row)
        if text:
            docs.append(text)
            valid_rows.append(row)
    if not docs:
        return []

    doc_embs = _encode_passage_texts(docs)
    # dot product == cosine similarity because embeddings are normalized
    sims = (doc_embs @ query_emb).tolist()

    ranked = sorted(
        zip(valid_rows, sims),
        key=lambda x: float(x[1]),
        reverse=True,
    )[: max(1, top_k)]

    results: list[SupabaseStyleResult] = []
    for row, score in ranked:
        style_name = (row.get("source_meta") or {}).get("style", row["style_id"])
        kb = row.get("style_kb")
        results.append(
            SupabaseStyleResult(
                style_id=row["style_id"],
                image_url=row["image_url"],
                style_name=style_name,
                similarity=round(float(score), 4),
                style_kb=kb if isinstance(kb, dict) else None,
            )
        )
    return results


def download_style_image(image_url: str) -> Path | None:
    """Download image from Supabase Storage to local artifacts/style_ref/. Cached by URL hash."""
    STYLE_REF_DIR.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.md5(image_url.encode()).hexdigest()[:12]
    suffix = Path(image_url.split("?")[0]).suffix or ".jpg"
    local_path = STYLE_REF_DIR / f"{url_hash}{suffix}"
    if local_path.exists():
        return local_path
    try:
        import httpx
        resp = httpx.get(image_url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        local_path.write_bytes(resp.content)
        return local_path
    except Exception as e:
        print(f"下載風格參考圖失敗：{e}")
        return None



def _extract_material_recommendations(style_kb: dict[str, Any]) -> list[str]:
    """Extract compact material recommendation list from style_kb.

    Tolerates both the {type, finish, target} object schema and the flat
    string-list schema seen in older KB rows.
    """
    visual = style_kb.get("visual_elements")
    if not isinstance(visual, dict):
        return []
    materials = visual.get("materials")
    if not isinstance(materials, list):
        return []

    output: list[str] = []
    for item in materials:
        if isinstance(item, dict):
            material_type = str(item.get("type", "")).strip()
            finish = str(item.get("finish", "")).strip()
            target = str(item.get("target", "")).strip()
            label = " ".join(v for v in [material_type, finish, target] if v)
        elif isinstance(item, str):
            label = item.strip()
        else:
            continue
        if label:
            output.append(label)
    return output[:6]


def _extract_kb_prompts(ai_params: dict[str, Any] | None) -> tuple[str, str]:
    """Read (positive, negative) prompts from ai_params.

    Tolerates both the nested `prompts.{positive,negative}` schema (current
    extraction template) and the flat `positive_prompt`/`negative_prompt`
    schema found in older KB rows.
    """
    if not isinstance(ai_params, dict):
        return "", ""
    prompts = ai_params.get("prompts")
    if isinstance(prompts, dict):
        pos = str(prompts.get("positive", "")).strip()
        neg = str(prompts.get("negative", "")).strip()
        if pos or neg:
            return pos, neg
    pos = str(ai_params.get("positive_prompt", "")).strip()
    neg = str(ai_params.get("negative_prompt", "")).strip()
    return pos, neg


def _extract_kb_strength(ai_params: dict[str, Any] | None) -> float | None:
    """Read the IP-Adapter weight from ai_params, tolerating both the nested
    `adapter_config.ip_adapter_weight` schema and flat key variants."""
    if not isinstance(ai_params, dict):
        return None
    adapter_config = ai_params.get("adapter_config")
    if isinstance(adapter_config, dict):
        val = adapter_config.get("ip_adapter_weight")
        if isinstance(val, (int, float)):
            return float(val)
    for key in ("recommended_ip_adapter_weight", "ip_adapter_weight"):
        val = ai_params.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return None

def blend_style_params_supabase(results: list[SupabaseStyleResult]) -> dict[str, Any] | None:
    """
    Build style params from Supabase search results.
    - Downloads top-1 matched image as style reference
    - Uses style_id to select text prompt
    """
    if not results:
        return None

    top = results[0]
    style_id = top.style_id

    # Download the top matched image
    ref_path = download_style_image(top.image_url)

    style_kb = top.style_kb
    ai_params = style_kb.get("ai_params") if isinstance(style_kb, dict) else {}
    pos_from_kb, neg_from_kb = _extract_kb_prompts(ai_params)

    # Priority 2: fallback to style_id-based static prompts
    prompts = _STYLE_PROMPTS.get(style_id, _STYLE_PROMPTS["modern"])
    style_prompt = pos_from_kb or prompts["positive"]
    negative_prompt = neg_from_kb or prompts["negative"]

    summary = ""
    if isinstance(style_kb, dict):
        summary = str(style_kb.get("description", "")).strip()

    kb_strength = _extract_kb_strength(ai_params)
    style_strength = float(max(0.0, min(1.0, kb_strength))) if kb_strength is not None else 0.8

    from style_kb.styles import STYLES
    style_name_map = {sid: sname for sid, sname in STYLES}

    print(
        f"[OK] Supabase vector search -> {style_id} "
        f"(score={top.similarity:.3f}, ref_image={'OK' if ref_path else 'FAILED'})"
    )

    return {
        "style_profile_id": style_id,
        "style_profile_name": style_name_map.get(style_id, style_id),
        "style_prompt": style_prompt,
        "negative_prompt": negative_prompt,
        "style_strength": style_strength,
        "color_guidance": {},
        "controlnet_type": "depth",
        "style_summary": summary,
        "material_recommendations": _extract_material_recommendations(style_kb or {}),
        "reference_image_url": top.image_url,
        "reference_image_path": str(ref_path) if ref_path else None,
        "top_similarity": top.similarity,
        "source": "supabase_style_kb" if style_kb else "supabase_vector",
    }

