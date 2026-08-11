"""Optional startup preload for embedding / CLIP stacks.

Shifts cold-load cost from the first style search or first pipeline run to server boot.
Controlled by ``DESIGNBRIDGE_STARTUP_WARMUP``:

- ``off`` / ``0`` / ``false``: skip warmup
- otherwise: text-to-text style embedder, local Chroma + MiniLM if the vector
  store exists, and pipeline CLIP evaluator (transformers)

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

    def _warm_text_embedder() -> None:
        from designbridge.style_supabase import _get_text_embedding_model

        _get_text_embedding_model()

    def _warm_chroma() -> None:
        from designbridge.style_vector import warmup_vector_collection

        warmup_vector_collection()

    def _warm_clip_eval() -> None:
        from designbridge.clip_evaluator import _load_model

        _load_model()

    _step("Text-to-text style embedder (sentence-transformers)", _warm_text_embedder)
    _step("Local Chroma vector store (if ready)", _warm_chroma)
    _step("Pipeline CLIP evaluator (transformers)", _warm_clip_eval)

    print("DesignBridge startup warmup done.", flush=True)
