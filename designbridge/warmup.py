"""Optional startup preload for embedding / CLIP stacks.

Shifts cold-load cost from the first style search or first pipeline run to server boot.
Controlled by ``DESIGNBRIDGE_STARTUP_WARMUP``:

- ``off`` / ``0`` / ``false``: skip warmup
- ``min`` (default): Supabase image-query embedder (CLIP via sentence-transformers),
  local Chroma + MiniLM if the vector store exists, and pipeline CLIP (transformers)
- ``full``: ``min`` plus the text-to-text embedding model (e.g. bge-m3)

Each step is isolated: a failure in one step does not block the others.
"""

from __future__ import annotations

import os


def run_startup_warmup() -> None:
    """Run configured preload steps (no-op when disabled)."""
    raw = (os.getenv("DESIGNBRIDGE_STARTUP_WARMUP", "min") or "min").strip().lower()
    if raw in ("0", "false", "off", "no", "none", "skip"):
        return

    mode = "full" if raw in ("full", "all", "1", "true", "yes") else "min"
    print(f"DesignBridge startup warmup (mode={mode})…", flush=True)

    def _step(name: str, fn) -> None:
        try:
            fn()
            print(f"  ✓ {name}", flush=True)
        except Exception as e:
            print(f"  ⚠ {name} skipped: {e}", flush=True)

    def _warm_supabase_clip() -> None:
        from designbridge.style_supabase import _get_embedding_model

        _get_embedding_model()

    def _warm_chroma() -> None:
        from designbridge.style_vector import warmup_vector_collection

        warmup_vector_collection()

    def _warm_clip_eval() -> None:
        from designbridge.clip_evaluator import _load_model

        _load_model()

    def _warm_text_embedder() -> None:
        from designbridge.style_supabase import _get_text_embedding_model

        _get_text_embedding_model()

    def _warm_vision() -> None:
        """Depth + segmentation checkpoints.

        By far the largest cold cost in the pipeline — constructing these two took ~155s
        on the CPU-only ARM box this was measured on, all of it charged to whoever
        uploaded the first photo. Loading them here moves it to boot, where nobody is
        waiting on a spinner.
        """
        from designbridge.config import Config
        from designbridge.vision import _load_depth_model, _load_upernet

        if Config.ENABLE_DEPTH:
            _load_depth_model(Config.DEPTH_MODEL)
        if Config.ENABLE_SEGMENTATION:
            _load_upernet(Config.SEGMENTATION_MODEL)

    _step("Supabase style CLIP embedder (sentence-transformers)", _warm_supabase_clip)
    _step("Local Chroma vector store (if ready)", _warm_chroma)
    _step("Pipeline CLIP evaluator (transformers)", _warm_clip_eval)
    _step("Depth + segmentation models (transformers)", _warm_vision)

    if mode == "full":
        _step("Text-to-text style embedder (sentence-transformers)", _warm_text_embedder)

    print("DesignBridge startup warmup done.", flush=True)
