#!/usr/bin/env python3
"""
scene_graph_to_depth.py
-----------------------
把 Layout Agent 的 scene graph 座標（俯視 bounding box）投影成「與算圖視角一致」的
透視深度圖（perspective depth map），作為 FLUX ControlNet / Kontext 的精確空間條件。

設計理念（老師建議）：
  不做完整 3D（不需 Blender / TripoSR）。每件家具用一個長方體代表，由 scene graph
  的正規化座標直接在 3D 房間中擺位，再用固定針孔相機投影 + z-buffer，得到透視深度圖。
  純 NumPy 即可。之後若需要再加 segmentation mask（同一個 pass 順手輸出）。

深度極性與 vision.run_depth_estimation 一致：近處亮（255）、遠處暗（0），
對齊 Depth-Anything V2 的視覺化慣例，方便沿用既有 Kontext / ControlNet 深度條件。

座標慣例：
  floor-plan x ∈ [0,1] 左→右；y ∈ [0,1] 上(遠牆)→下(近相機側)
  world: X 左右、Y 遠近(由近相機側往遠牆遞增)、Z 上下(地板 0、天花板 H)

用法：
  python -m designbridge.layout.scene_graph_to_depth placements.json --out depth.png --seg seg.png --vis
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


# ── 家具高度（公尺）─ footprint 已由 layout_agent.FURNITURE_SIZES 提供，這裡補垂直高度 ──
FURNITURE_HEIGHTS: dict[str, float] = {
    "sofa": 0.85,
    "loveseat": 0.80,
    "coffee_table": 0.45,
    "tv_unit": 0.50,
    "tv": 0.70,
    "dining_table": 0.75,
    "chair": 0.90,
    "armchair": 0.95,
    "bed": 0.55,
    "bunk_bed": 1.70,
    "bunk_ladder": 1.55,
    "wardrobe": 2.00,
    "desk": 0.75,
    "bookshelf": 1.80,
    "side_table": 0.55,
    "nightstand": 0.55,
    "lamp": 1.50,
    "rug": 0.02,
    "plant": 1.20,
    "cabinet": 0.90,
    "dresser": 0.85,
    "shelf": 1.60,
    "default": 0.80,
}

# 房間外殼（地板/牆/天花板）在 segmentation 中的中性顏色
_SHELL_COLORS: dict[str, tuple[int, int, int]] = {
    "floor": (190, 190, 190),
    "ceiling": (225, 225, 225),
    "wall": (210, 210, 210),
}


def _furniture_color(ftype: str) -> tuple[int, int, int]:
    from designbridge.layout.layout_agent import FURNITURE_COLORS
    return FURNITURE_COLORS.get(ftype, FURNITURE_COLORS["default"])


# ── 相機 ──────────────────────────────────────────────────────────────────────

def _build_camera(
    image_size: tuple[int, int],
    *,
    hfov_deg: float = 60.0,
    eye_height: float = 1.40,
    setback: float = 0.80,
    pitch_deg: float = -6.0,
) -> dict[str, float]:
    """固定針孔相機：站在近牆後方 `setback` 公尺、眼高 `eye_height`，朝 +Y（房間內）看。

    pitch_deg < 0 代表略微俯視（看到較多地板），符合一般室內算圖視角。
    """
    w, h = image_size
    f = 0.5 * w / np.tan(np.radians(hfov_deg) / 2.0)
    return {
        "x": 0.0,
        "y": -float(setback),
        "z": float(eye_height),
        "pitch": np.radians(pitch_deg),
        "f": float(f),
        "cx": w / 2.0,
        "cy": h / 2.0,
        "w": w,
        "h": h,
        "near": 0.05,
    }


def _project(points: np.ndarray, cam: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    """world points (N,3) → 像素座標 (N,2) 與前向深度 (N,)。"""
    rx = points[:, 0] - cam["x"]
    ry = points[:, 1] - cam["y"]
    rz = points[:, 2] - cam["z"]

    th = cam["pitch"]
    fwd = ry * np.cos(th) + rz * np.sin(th)   # 進入畫面方向
    up = -ry * np.sin(th) + rz * np.cos(th)   # 畫面上方

    depth = np.maximum(fwd, cam["near"])
    u = cam["cx"] + cam["f"] * rx / depth
    v = cam["cy"] - cam["f"] * up / depth
    return np.stack([u, v], axis=1), fwd


# ── 三角形光柵化 + z-buffer ────────────────────────────────────────────────────

def _raster_triangle(
    zbuf: np.ndarray,
    idbuf: np.ndarray,
    p0: np.ndarray, p1: np.ndarray, p2: np.ndarray,
    d0: float, d1: float, d2: float,
    obj_id: int,
) -> None:
    """把單一三角形以 z-buffer 寫入。p* 為像素座標 (2,)，d* 為各頂點前向深度。"""
    h, w = zbuf.shape
    minx = max(int(np.floor(min(p0[0], p1[0], p2[0]))), 0)
    maxx = min(int(np.ceil(max(p0[0], p1[0], p2[0]))), w - 1)
    miny = max(int(np.floor(min(p0[1], p1[1], p2[1]))), 0)
    maxy = min(int(np.ceil(max(p0[1], p1[1], p2[1]))), h - 1)
    if minx > maxx or miny > maxy:
        return

    denom = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
    if abs(denom) < 1e-9:
        return

    xs = np.arange(minx, maxx + 1)
    ys = np.arange(miny, maxy + 1)
    gx, gy = np.meshgrid(xs, ys)

    a = ((p1[1] - p2[1]) * (gx - p2[0]) + (p2[0] - p1[0]) * (gy - p2[1])) / denom
    b = ((p2[1] - p0[1]) * (gx - p2[0]) + (p0[0] - p2[0]) * (gy - p2[1])) / denom
    c = 1.0 - a - b
    inside = (a >= 0) & (b >= 0) & (c >= 0)
    if not inside.any():
        return

    depth = a * d0 + b * d1 + c * d2
    sub_z = zbuf[miny:maxy + 1, minx:maxx + 1]
    sub_id = idbuf[miny:maxy + 1, minx:maxx + 1]
    closer = inside & (depth < sub_z)
    sub_z[closer] = depth[closer]
    sub_id[closer] = obj_id


def _raster_quad(
    zbuf: np.ndarray, idbuf: np.ndarray,
    world_quad: np.ndarray, cam: dict[str, float], obj_id: int,
) -> None:
    """把世界座標四邊形（4,3，順序為環繞）拆成兩個三角形光柵化。"""
    pix, depth = _project(world_quad, cam)
    # 任一頂點在相機後方則略過（PoC：房間內物件皆在前方，足夠）
    if (depth <= cam["near"]).any():
        return
    _raster_triangle(zbuf, idbuf, pix[0], pix[1], pix[2], depth[0], depth[1], depth[2], obj_id)
    _raster_triangle(zbuf, idbuf, pix[0], pix[2], pix[3], depth[0], depth[2], depth[3], obj_id)


# ── 幾何組裝 ──────────────────────────────────────────────────────────────────

def _room_dims(space_info: dict) -> tuple[float, float, float]:
    size = (space_info or {}).get("estimated_size") or {}
    w = float(size.get("width", 5.0))
    d = float(size.get("depth", 4.0))
    h = float(size.get("height", 2.8))
    return w, d, h


def _fp_to_world_box(item: dict, room_w: float, room_d: float) -> tuple[float, float, float, float, float]:
    """floor-plan bbox → world (x0,x1,y0,y1,top_z)。"""
    fx = float(item.get("x", 0.0))
    fy = float(item.get("y", 0.0))
    fw = float(item.get("w", 0.1))
    fh = float(item.get("h", 0.1))
    ftype = str(item.get("type", "default"))

    x0 = (fx - 0.5) * room_w
    x1 = (fx + fw - 0.5) * room_w
    # floor-plan y=0 為遠牆、y=1 為近相機側 → world Y 由近(0)到遠(room_d)
    y_near = (1.0 - (fy + fh)) * room_d
    y_far = (1.0 - fy) * room_d
    top_z = FURNITURE_HEIGHTS.get(ftype, FURNITURE_HEIGHTS["default"])
    return x0, x1, y_near, y_far, top_z


def _add_room_shell(
    zbuf: np.ndarray, idbuf: np.ndarray, cam: dict[str, float],
    room_w: float, room_d: float, room_h: float,
    shell_ids: dict[str, int],
) -> None:
    hx = room_w / 2.0
    # 地板
    _raster_quad(zbuf, idbuf, np.array([
        [-hx, 0.0, 0.0], [hx, 0.0, 0.0], [hx, room_d, 0.0], [-hx, room_d, 0.0],
    ]), cam, shell_ids["floor"])
    # 天花板
    _raster_quad(zbuf, idbuf, np.array([
        [-hx, 0.0, room_h], [hx, 0.0, room_h], [hx, room_d, room_h], [-hx, room_d, room_h],
    ]), cam, shell_ids["ceiling"])
    # 遠牆
    _raster_quad(zbuf, idbuf, np.array([
        [-hx, room_d, 0.0], [hx, room_d, 0.0], [hx, room_d, room_h], [-hx, room_d, room_h],
    ]), cam, shell_ids["wall"])
    # 左牆
    _raster_quad(zbuf, idbuf, np.array([
        [-hx, 0.0, 0.0], [-hx, room_d, 0.0], [-hx, room_d, room_h], [-hx, 0.0, room_h],
    ]), cam, shell_ids["wall"])
    # 右牆
    _raster_quad(zbuf, idbuf, np.array([
        [hx, 0.0, 0.0], [hx, room_d, 0.0], [hx, room_d, room_h], [hx, 0.0, room_h],
    ]), cam, shell_ids["wall"])


def _add_box(
    zbuf: np.ndarray, idbuf: np.ndarray, cam: dict[str, float],
    x0: float, x1: float, y0: float, y1: float, z1: float, obj_id: int,
) -> None:
    """擺一個長方體（z0=0 在地板）。渲染頂面 + 四側面。"""
    z0 = 0.0
    # 頂面
    _raster_quad(zbuf, idbuf, np.array([
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]), cam, obj_id)
    # 近面 (y0)
    _raster_quad(zbuf, idbuf, np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]]), cam, obj_id)
    # 遠面 (y1)
    _raster_quad(zbuf, idbuf, np.array([
        [x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]]), cam, obj_id)
    # 左面 (x0)
    _raster_quad(zbuf, idbuf, np.array([
        [x0, y0, z0], [x0, y1, z0], [x0, y1, z1], [x0, y0, z1]]), cam, obj_id)
    # 右面 (x1)
    _raster_quad(zbuf, idbuf, np.array([
        [x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]]), cam, obj_id)


# ── 主函式 ────────────────────────────────────────────────────────────────────

def project_scene_graph_to_depth(
    furniture_placements: list[dict],
    space_info: dict | None = None,
    out_path: str | Path | None = None,
    *,
    image_size: tuple[int, int] = (1024, 1024),
    seg_out_path: str | Path | None = None,
    camera_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把 furniture_placements 投影成透視深度圖（近亮遠暗），可選輸出 segmentation。

    回傳 dict：depth_path / seg_path / depth_array / id_map / meta。
    """
    space_info = space_info or {}
    w_img, h_img = image_size
    cam = _build_camera(image_size, **(camera_overrides or {}))
    room_w, room_d, room_h = _room_dims(space_info)

    zbuf = np.full((h_img, w_img), np.inf, dtype=np.float32)
    idbuf = np.zeros((h_img, w_img), dtype=np.int32)  # 0 = 空 / 背景

    # id 配置：1..N_shell 給外殼，之後給家具
    shell_ids = {"floor": 1, "ceiling": 2, "wall": 3}
    _add_room_shell(zbuf, idbuf, cam, room_w, room_d, room_h, shell_ids)

    id_to_type: dict[int, str] = {
        1: "_floor", 2: "_ceiling", 3: "_wall",
    }
    next_id = 4
    for item in (furniture_placements or []):
        x0, x1, y0, y1, z1 = _fp_to_world_box(item, room_w, room_d)
        if x1 <= x0 or y1 <= y0:
            continue
        obj_id = next_id
        next_id += 1
        id_to_type[obj_id] = str(item.get("type", "default"))
        _add_box(zbuf, idbuf, cam, x0, x1, y0, y1, z1, obj_id)

    # 深度 → 8-bit 灰階（近亮遠暗，對齊 Depth-Anything 視覺化）
    finite = np.isfinite(zbuf)
    depth_img = np.zeros((h_img, w_img), dtype=np.uint8)
    if finite.any():
        dvals = zbuf[finite]
        dmin, dmax = float(dvals.min()), float(dvals.max())
        if dmax - dmin < 1e-6:
            depth_img[finite] = 255
        else:
            norm = (zbuf - dmin) / (dmax - dmin)        # 0=近,1=遠
            bright = ((1.0 - norm) * 255.0).clip(0, 255)
            depth_img[finite] = bright[finite].astype(np.uint8)

    result: dict[str, Any] = {
        "depth_array": depth_img,
        "id_map": idbuf,
        "id_to_type": id_to_type,
        "meta": {
            "room_dims": {"width": room_w, "depth": room_d, "height": room_h},
            "image_size": {"width": w_img, "height": h_img},
            "furniture_count": next_id - 4,
        },
    }

    from PIL import Image
    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(depth_img, mode="L").save(str(out_path))
        result["depth_path"] = str(out_path)

    if seg_out_path is not None:
        seg_rgb = np.zeros((h_img, w_img, 3), dtype=np.uint8)
        for oid, ftype in id_to_type.items():
            mask = idbuf == oid
            if not mask.any():
                continue
            if ftype.startswith("_"):
                color = _SHELL_COLORS.get(ftype[1:], _SHELL_COLORS["wall"])
            else:
                color = _furniture_color(ftype)
            seg_rgb[mask] = color
        seg_out_path = Path(seg_out_path)
        seg_out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(seg_rgb, mode="RGB").save(str(seg_out_path))
        result["seg_path"] = str(seg_out_path)

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def _load_placements(path: Path) -> tuple[list[dict], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data, {}
    placements = (
        data.get("furniture_placements")
        or data.get("furniture")
        or (data.get("scene_graph") or {}).get("furniture_placements")
        or []
    )
    space_info = data.get("space_info") or {}
    return placements, space_info


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把 scene graph 家具座標投影成透視深度圖（FLUX ControlNet 條件）"
    )
    parser.add_argument("placements", help="furniture_placements JSON（list 或含該欄位的物件）")
    parser.add_argument("--out", default=None, help="深度圖輸出路徑（預設同目錄 projected_depth.png）")
    parser.add_argument("--seg", default=None, help="可選 segmentation mask 輸出路徑")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--hfov", type=float, default=60.0)
    parser.add_argument("--pitch", type=float, default=-6.0, help="相機俯角（負=俯視，看更多地板）")
    parser.add_argument("--vis", action="store_true", help="另存深度+seg 並排視覺化圖")
    args = parser.parse_args()

    src = Path(args.placements)
    placements, space_info = _load_placements(src)
    out_path = Path(args.out) if args.out else src.parent / "projected_depth.png"
    seg_path = Path(args.seg) if args.seg else None

    res = project_scene_graph_to_depth(
        placements, space_info, out_path,
        image_size=(args.width, args.height),
        seg_out_path=seg_path,
        camera_overrides={"hfov_deg": args.hfov, "pitch_deg": args.pitch},
    )

    print(f"家具數：{res['meta']['furniture_count']}")
    print(f"房間尺寸：{res['meta']['room_dims']}")
    print(f"深度圖：{res.get('depth_path')}")
    if res.get("seg_path"):
        print(f"Segmentation：{res['seg_path']}")

    if args.vis:
        try:
            import matplotlib.pyplot as plt
            n = 2 if seg_path else 1
            fig, axes = plt.subplots(1, n, figsize=(7 * n, 6))
            axes = np.atleast_1d(axes)
            axes[0].imshow(res["depth_array"], cmap="gray", vmin=0, vmax=255)
            axes[0].set_title("Projected Depth (near=bright)")
            axes[0].axis("off")
            if seg_path:
                from PIL import Image
                axes[1].imshow(np.array(Image.open(seg_path)))
                axes[1].set_title("Segmentation")
                axes[1].axis("off")
            vis_out = out_path.parent / (out_path.stem + "_vis.png")
            plt.tight_layout()
            plt.savefig(vis_out, dpi=110, bbox_inches="tight")
            plt.close()
            print(f"視覺化：{vis_out}")
        except ImportError:
            print("matplotlib 未安裝，略過視覺化")


if __name__ == "__main__":
    main()
