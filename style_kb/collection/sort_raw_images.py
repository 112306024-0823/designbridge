#!/usr/bin/env python3
"""Sort raw 100interior images into style_kb/images/<style_id>/ based on meta JSON.

Reads `style` from each `*_meta.json` (e.g. 現代風 → modern) and copies image + meta.

Usage (from project root):
    python -m style_kb.collection.sort_raw_images
    python -m style_kb.collection.sort_raw_images --copy
    python -m style_kb.collection.sort_raw_images --copy --limit 0   # all styles, no cap
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

STYLE_MAP = {
    "現代風": "modern",
    "現代": "modern",
    "北歐風": "nordic",
    "北歐": "nordic",
    "日式風": "japanese",
    "日式": "japanese",
    "美式風": "american",
    "美式": "american",
    "奢華風": "luxury",
    "奢華": "luxury",
    "工業風": "industrial",
    "工業": "industrial",
    "古典風": "classic",
    "古典": "classic",
    "新古典風": "neoclassic",
    "新古典": "neoclassic",
    "鄉村風": "country",
    "鄉村": "country",
    "其他": "other",
    "混搭風": "other",
    "中式風": "other",
}

FALLBACK_STYLE_ID = "other"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

_STYLE_KB_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = _STYLE_KB_ROOT / "raw" / "100interior_images"
IMAGES_DIR = _STYLE_KB_ROOT / "images"


def resolve_style_id(style_zh: str) -> str:
    """Map meta style label to style_id; unknown labels go to ``other``."""
    label = (style_zh or "").strip()
    if not label:
        return FALLBACK_STYLE_ID
    return STYLE_MAP.get(label, FALLBACK_STYLE_ID)


def move_and_sort(raw_dir: Path = RAW_DIR, limit: int = 0) -> None:
    """Move images from raw_dir to images/<style_id>/ based on meta JSON style field."""
    import sys; sys.stdout.reconfigure(encoding="utf-8")
    from collections import defaultdict

    existing_counts: dict[str, int] = {}
    for style_id in set(STYLE_MAP.values()) | {FALLBACK_STYLE_ID}:
        folder = IMAGES_DIR / style_id
        folder.mkdir(parents=True, exist_ok=True)
        existing_counts[style_id] = len([p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS])

    move_counts: dict[str, int] = defaultdict(int)
    skipped_styles: dict[str, int] = defaultdict(int)

    image_files = [p for p in raw_dir.rglob("*") if p.suffix.lower() in IMAGE_EXTS and "_meta" not in p.stem]
    print(f"Found {len(image_files)} images under {raw_dir}")

    for img_path in sorted(image_files):
        meta_path = img_path.with_name(img_path.stem + "_meta.json")
        if not meta_path.exists():
            continue

        meta = json.load(open(meta_path, encoding="utf-8"))
        style_zh = meta.get("style", "").strip()
        style_id = resolve_style_id(style_zh)
        if style_id == FALLBACK_STYLE_ID and style_zh and style_zh not in STYLE_MAP:
            skipped_styles[style_zh] += 1

        dest_folder = IMAGES_DIR / style_id
        dest_path = dest_folder / img_path.name

        if dest_path.exists():
            img_path.unlink()
            meta_path.unlink()
            continue

        if limit > 0 and (existing_counts[style_id] + move_counts[style_id]) >= limit:
            continue

        import shutil as _shutil
        _shutil.move(str(meta_path), str(dest_folder / meta_path.name))
        _shutil.move(str(img_path), str(dest_path))
        move_counts[style_id] += 1

    total = sum(move_counts.values())
    print(f"Moved {total} images. Skipped styles: {dict(skipped_styles)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sort raw images by meta JSON style")
    parser.add_argument("--copy", action="store_true", help="Actually copy files (default: dry run)")
    parser.add_argument("--limit", type=int, default=50, help="Max images per style (0 = unlimited)")
    parser.add_argument(
        "--raw-dir",
        default=str(RAW_DIR),
        help="Raw image directory (flat or nested)",
    )
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    images_dir = IMAGES_DIR

    # Count existing images per style
    existing_counts: dict[str, int] = {}
    for style_id in set(STYLE_MAP.values()) | {FALLBACK_STYLE_ID}:
        folder = images_dir / style_id
        folder.mkdir(parents=True, exist_ok=True)
        existing_counts[style_id] = len([
            p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS
        ]) if folder.exists() else 0

    copy_counts: dict[str, int] = defaultdict(int)
    skip_counts: dict[str, int] = defaultdict(int)
    other_sources: dict[str, int] = defaultdict(int)

    image_files = [
        p for p in raw_dir.rglob("*")
        if p.suffix.lower() in IMAGE_EXTS and "_meta" not in p.stem
    ]
    print(f"Found {len(image_files)} images under {raw_dir}")

    for img_path in sorted(image_files):
        meta_path = img_path.with_name(img_path.stem + "_meta.json")
        if not meta_path.exists():
            continue

        meta = json.load(open(meta_path, encoding="utf-8"))
        style_zh = meta.get("style", "").strip()
        style_id = resolve_style_id(style_zh)
        if style_id == FALLBACK_STYLE_ID and style_zh:
            other_sources[style_zh] += 1

        dest_folder = images_dir / style_id
        dest_path = dest_folder / img_path.name

        # Skip if already exists in dest
        if dest_path.exists():
            skip_counts[style_id] += 1
            continue

        # Enforce per-style limit
        total_so_far = existing_counts[style_id] + copy_counts[style_id]
        if args.limit > 0 and total_so_far >= args.limit:
            skip_counts[style_id] += 1
            continue

        if args.copy:
            shutil.copy2(img_path, dest_path)
            shutil.copy2(meta_path, dest_folder / meta_path.name)
        copy_counts[style_id] += 1

    mode = "Copied" if args.copy else "Would copy (dry run)"
    print(f"\n{'='*50}")
    print(f"{'Style':<15} {'Existing':>8} {'+ New':>6} {'Skipped':>8}")
    print(f"{'-'*50}")
    for style_id in sorted(set(list(copy_counts) + list(existing_counts))):
        ex = existing_counts.get(style_id, 0)
        cp = copy_counts.get(style_id, 0)
        sk = skip_counts.get(style_id, 0)
        if ex or cp:
            print(f"{style_id:<15} {ex:>8} {cp:>6} {sk:>8}")

    if other_sources:
        print(f"\nRouted to other ({FALLBACK_STYLE_ID}):")
        for s, n in sorted(other_sources.items(), key=lambda x: -x[1]):
            print(f"  {n:>5}  {s or '(empty)'}")

    total_new = sum(copy_counts.values())
    print(f"\n{mode}: {total_new} images total")
    if not args.copy:
        print("Run with --copy to actually copy files.")


if __name__ == "__main__":
    main()
