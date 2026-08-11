"""Stage-timing helper for diagnosing pipeline latency.

Usage:
    with log_stage("renderer.hf_inference", task_id=task_id):
        ...

Prints ``[timing][task_id] label: X.XXs`` to stdout when the block exits
(including on exception, so failed/skipped attempts still show how long
they took before failing).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TypeVar

T = TypeVar("T")


@contextmanager
def log_stage(label: str, task_id: str | None = None):
    prefix = f"[timing][{task_id}]" if task_id else "[timing]"
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"{prefix} {label}: {elapsed:.2f}s")


def timed_call(label: str, task_id: str | None, fn, *args, **kwargs) -> T:
    """Call ``fn(*args, **kwargs)`` wrapped in :func:`log_stage`; returns fn's result."""
    with log_stage(label, task_id=task_id):
        return fn(*args, **kwargs)
