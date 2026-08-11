"""
Design Adjuster skill script.
讀取 stdin JSON → 執行局部 inpainting → 輸出 generated_image 路徑到 stdout。

原始邏輯位於：designbridge/nodes.py::adjuster_agent_stub
"""
import json
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root))

from designbridge.core.config import Config
from designbridge.render.inpaint import (
    mask_from_segmentation,
    fallback_center_mask,
    build_inpaint_prompt,
    run_inpainting,
    run_hf_inpainting,
)


def main():
    data = json.load(sys.stdin)
    from PIL import Image

    task_id = data.get("task_id") or str(uuid.uuid4())
    user_input = data.get("user_input") or {}
    req = data.get("structured_requirement") or {}
    vision = data.get("vision_features") or {}
    style_params = data.get("style_params")

    image_path = user_input.get("initial_image", "")
    edit_scope = float(user_input.get("edit_scope", 0.2))

    if not image_path or not Path(image_path).is_file():
        print(json.dumps({
            "intermediate_outputs": {"adjuster_agent": "no_initial_image_skipped"}
        }))
        return

    constraints = req.get("layout_constraints") or {}
    must_remove = constraints.get("must_remove") or []
    must_add = constraints.get("must_add") or []
    target_labels = must_remove if must_remove else ["furniture"]
    target_objects = must_add if must_add else target_labels

    seg_path = vision.get("segmentation")
    seg_meta = vision.get("segmentation_meta")
    original_img = Image.open(image_path)
    img_size = original_img.size

    if seg_path and seg_meta and Path(str(seg_path)).is_file() and Path(str(seg_meta)).is_file():
        mask = mask_from_segmentation(str(seg_path), str(seg_meta), target_labels, img_size)
        mask_source = "segmentation"
    else:
        mask = fallback_center_mask(img_size)
        mask_source = "fallback_center"

    prompt, negative_prompt = build_inpaint_prompt(req, style_params, target_objects)
    strength = max(0.4, min(0.85, edit_scope + 0.4))

    out_path = Path(Config.ARTIFACTS_DIR) / "render" / f"{task_id}.png"
    backend = "placeholder"

    if Config.HF_TOKEN:
        if run_hf_inpainting(image_path, mask, prompt, out_path):
            backend = "hf_inpainting"

    if backend == "placeholder":
        if run_inpainting(image_path, mask, prompt, negative_prompt, strength, out_path):
            backend = "sd_inpainting"

    if backend == "placeholder":
        out_path.parent.mkdir(parents=True, exist_ok=True)
        original_img.save(str(out_path))

    result = {
        "generated_image": str(out_path),
        "render_result": {
            "generated_image_path": str(out_path),
            "generation_params": {
                "backend": backend,
                "model": "stable-diffusion-2-inpainting",
                "strength": strength,
                "mask_source": mask_source,
                "prompt_preview": prompt[:150],
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "intermediate_outputs": {
            "adjuster_agent": {
                "inpaint_regions": [{
                    "target_labels": target_labels,
                    "target_objects": target_objects,
                    "prompt": prompt,
                    "strength": strength,
                    "mask_source": mask_source,
                }]
            }
        }
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
