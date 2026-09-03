"""
Visual Preprocessor skill script.
讀取 stdin JSON → 執行深度估測 + 語意分割 → 輸出 vision_features JSON 到 stdout。

原始邏輯位於：designbridge/nodes.py::visual_preprocessing_local
"""
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root))

from designbridge.core.config import Config
from designbridge.layout.vision import run_visual_preprocessing


def main():
    data = json.load(sys.stdin)
    image_path = data.get("image_path", "")
    task_id = data.get("task_id", "no_task_id")

    if not image_path:
        print(json.dumps({"vision_features": {"geometry_constraints": {}}}))
        return

    try:
        artifacts = run_visual_preprocessing(
            image_path,
            task_id=task_id,
            enable_depth=Config.ENABLE_DEPTH,
            enable_segmentation=Config.ENABLE_SEGMENTATION,
            depth_model=Config.DEPTH_MODEL,
            segmentation_model=Config.SEGMENTATION_MODEL,
            artifacts_root=Path(Config.ARTIFACTS_DIR),
        )
    except Exception as e:
        print(f"[visual-preprocessor] Failed: {e}", file=sys.stderr)
        print(json.dumps({"vision_features": {"geometry_constraints": {}}}))
        return

    vision_features = {"geometry_constraints": {}}
    if artifacts.depth_path:
        vision_features["depth"] = str(artifacts.depth_path)
    if artifacts.segmentation_path:
        vision_features["segmentation"] = str(artifacts.segmentation_path)
    if artifacts.segmentation_meta_path:
        vision_features["segmentation_meta"] = str(artifacts.segmentation_meta_path)

    print(json.dumps({"vision_features": vision_features}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
