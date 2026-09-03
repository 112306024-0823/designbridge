#!/usr/bin/env python3
"""Export Supabase known image keys for crawler deduplication.

Usage (from project root):
    python -m style_kb.scrapper.export_manifest
    python -m style_kb.scrapper.export_manifest --output style_kb/manifest/known_images.json
"""

from __future__ import annotations

import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")

from style_kb.scrapper.dedup import MANIFEST_PATH, fetch_manifest_from_supabase, save_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Supabase image manifest")
    parser.add_argument("--output", type=str, default=str(MANIFEST_PATH))
    args = parser.parse_args()

    manifest = fetch_manifest_from_supabase()
    path = save_manifest(manifest, MANIFEST_PATH if not args.output else __import__("pathlib").Path(args.output))

    print(f"✅ manifest 已寫入：{path}")
    print(f"   image_keys: {len(manifest['image_keys'])}")
    print(f"   image_ids:  {len(manifest['image_ids'])}")
    print(f"   work_ids:   {len(manifest['work_ids'])}")
    print(f"   case_urls:  {len(manifest['case_urls'])}")


if __name__ == "__main__":
    main()
