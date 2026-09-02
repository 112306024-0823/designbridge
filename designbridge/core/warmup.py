"""Optional startup preload for embedding / CLIP stacks.

Shifts cold-load cost from the first style search or first pipeline run to server boot.
Controlled by ``DESIGNBRIDGE_STARTUP_WARMUP``:

- ``off`` / ``0`` / ``false``: skip warmup
- ``min`` (default): local Chroma + MiniLM if the vector store exists,
  pipeline CLIP (transformers), and the text-to-text style embedder (e.g. bge-m3)

Each step is isolated: a failure in one step does not block the others.
"""

from __future__ import annotations

import os


def run_startup_warmup() -> None:
    """Run configured preload steps (no-op when disabled)."""
    raw = (os.getenv("DESIGNBRIDGE_STARTUP_WARMUP", "min") or "min").strip().lower()
    if raw in ("0", "false", "off", "no", "none", "skip"):
        return

    print("DesignBridge startup warmup…", flush=True)

    def _step(name: str, fn) -> None:
        try:
            fn()
            print(f"  ✓ {name}", flush=True)
        except Exception as e:
            print(f"  ⚠ {name} skipped: {e}", flush=True)

    def _warm_chroma() -> None:
        from designbridge.style.style_vector import warmup_vector_collection

        warmup_vector_collection()

    def _warm_clip_eval() -> None:
        from designbridge.render.clip_evaluator import _load_model

        _load_model()

    def _warm_text_embedder() -> None:
        from designbridge.style.style_supabase import _get_text_embedding_model

        _get_text_embedding_model()

    def _warm_sam2() -> None:
        from designbridge.render.inpaint import _get_sam2_predictor

        _get_sam2_predictor()

    _step("Local Chroma vector store (if ready)", _warm_chroma)
    _step("Pipeline CLIP evaluator (transformers)", _warm_clip_eval)
    _step("Text-to-text style embedder (sentence-transformers)", _warm_text_embedder)
    _step("SAM 2 instance segmentation predictor", _warm_sam2)

    print("DesignBridge startup warmup done.", flush=True)
