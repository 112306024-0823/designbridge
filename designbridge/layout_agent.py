# designbridge/layout_agent.py
"""Layout Agent: furniture placement planning with hard and soft constraints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from designbridge.config import Config
from designbridge.layout_constraints import get_layout_constraint_registry


FURNITURE_SIZES: dict[str, tuple[float, float]] = {
    "sofa": (0.30, 0.13),
    "loveseat": (0.22, 0.12),
    "coffee_table": (0.15, 0.10),
    "tv_unit": (0.22, 0.07),
    "tv": (0.22, 0.06),
    "dining_table": (0.20, 0.13),
    "chair": (0.08, 0.08),
    "armchair": (0.11, 0.11),
    "bed": (0.22, 0.28),
    "bunk_bed": (0.22, 0.30),
    "bunk_ladder": (0.06, 0.08),
    "wardrobe": (0.18, 0.08),
    "desk": (0.16, 0.09),
    "bookshelf": (0.10, 0.05),
    "side_table": (0.07, 0.07),
    "nightstand": (0.07, 0.07),
    "lamp": (0.04, 0.04),
    "rug": (0.32, 0.22),
    "plant": (0.06, 0.06),
    "cabinet": (0.14, 0.07),
    "dresser": (0.14, 0.09),
    "shelf": (0.10, 0.05),
    "default": (0.12, 0.10),
}

FURNITURE_COLORS: dict[str, tuple[int, int, int]] = {
    "sofa": (100, 149, 237),
    "loveseat": (120, 160, 240),
    "bed": (147, 112, 219),
    "bunk_bed": (110, 80, 190),
    "bunk_ladder": (160, 120, 70),
    "dining_table": (205, 133, 63),
    "desk": (70, 130, 180),
    "coffee_table": (176, 196, 222),
    "tv_unit": (105, 105, 105),
    "tv": (80, 80, 80),
    "wardrobe": (139, 90, 43),
    "chair": (188, 143, 143),
    "armchair": (180, 130, 130),
    "rug": (210, 180, 140),
    "bookshelf": (160, 120, 80),
    "shelf": (160, 120, 80),
    "nightstand": (180, 160, 120),
    "side_table": (180, 160, 120),
    "dresser": (150, 110, 70),
    "cabinet": (130, 100, 70),
    "lamp": (255, 220, 100),
    "plant": (80, 160, 80),
    "default": (150, 200, 150),
}

SOFT_WEIGHTS = {
    "circulation": 0.35,
    "balance": 0.25,
    "focal_point": 0.20,
    "natural_light": 0.10,
    "ergonomics": 0.10,
}



@dataclass
class FurnitureItem:
    id: str
    type: str
    x: float   # normalized [0,1] — left edge
    y: float   # normalized [0,1] — top edge
    w: float
    h: float
    rotation: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "w": round(self.w, 4),
            "h": round(self.h, 4),
            "rotation": self.rotation,
        }


# ─────────────────────────── Geometry ───────────────────────────

def _overlaps(a: FurnitureItem, b: FurnitureItem, margin: float = 0.02) -> bool:
    return not (
        a.x + a.w + margin <= b.x
        or b.x + b.w + margin <= a.x
        or a.y + a.h + margin <= b.y
        or b.y + b.h + margin <= a.y
    )


def _push_apart(items: list[FurnitureItem], iterations: int = 60) -> list[FurnitureItem]:
    """AABB collision resolution: iteratively push overlapping pairs apart."""
    for _ in range(iterations):
        moved = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if not _overlaps(a, b):
                    continue
                acx, acy = a.x + a.w / 2, a.y + a.h / 2
                bcx, bcy = b.x + b.w / 2, b.y + b.h / 2
                dx, dy = acx - bcx, acy - bcy
                ox = (a.x + a.w + 0.02) - b.x if dx >= 0 else b.x + b.w + 0.02 - a.x
                oy = (a.y + a.h + 0.02) - b.y if dy >= 0 else b.y + b.h + 0.02 - a.y
                # Push along shorter overlap axis
                if abs(ox) <= abs(oy):
                    half = ox / 2
                    a.x += half * (1 if dx >= 0 else -1)
                    b.x -= half * (1 if dx >= 0 else -1)
                else:
                    half = oy / 2
                    a.y += half * (1 if dy >= 0 else -1)
                    b.y -= half * (1 if dy >= 0 else -1)
                moved = True
        if not moved:
            break
    return items


def _clip_to_room(items: list[FurnitureItem], pad: float = 0.02) -> list[FurnitureItem]:
    for item in items:
        item.x = max(pad, min(1.0 - item.w - pad, item.x))
        item.y = max(pad, min(1.0 - item.h - pad, item.y))
    return items


# ─────────────────────────── Soft Constraints ───────────────────────────

def _score_soft_constraints(
    items: list[FurnitureItem], space_info: dict
) -> dict[str, float]:
    n = len(items)
    if n == 0:
        return {k: 0.5 for k in SOFT_WEIGHTS}

    size = space_info.get("estimated_size") or {}
    room_w = float(size.get("width", 5.0))   # metres
    room_d = float(size.get("depth", 4.0))

    # Pairwise gaps in physical metres
    gaps_m: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = items[i], items[j]
            gx = max(b.x - (a.x + a.w), a.x - (b.x + b.w), 0.0) * room_w
            gy = max(b.y - (a.y + a.h), a.y - (b.y + b.h), 0.0) * room_d
            gaps_m.append(gx + gy)

    # Circulation (35%): fraction of pairs with physical clearance ≥ 0.60 m
    AISLE_MIN_M = 0.60
    circulation = (
        sum(1 for g in gaps_m if g >= AISLE_MIN_M) / len(gaps_m)
    ) if gaps_m else 0.5

    # Balance (25%): area-weighted CoM distance from room centre (0.5, 0.5)
    areas = [item.w * item.h for item in items]
    total_area = sum(areas) or 1.0
    cx = sum((item.x + item.w / 2) * a for item, a in zip(items, areas)) / total_area
    cy = sum((item.y + item.h / 2) * a for item, a in zip(items, areas)) / total_area
    balance = max(0.0, 1.0 - 2 * (abs(cx - 0.5) + abs(cy - 0.5)))

    # Focal point (20%): largest piece near focal wall (y≈0.72) and horizontally centred
    largest = max(items, key=lambda i: i.w * i.h)
    focal_dx = abs(largest.x + largest.w / 2 - 0.5)
    focal_dy = abs(largest.y + largest.h / 2 - 0.72)
    focal_point = max(0.0, 1.0 - (focal_dx + focal_dy) * 1.5)

    # Natural light (10%): penalise large items blocking top-wall windows (y < 0.15)
    windows = space_info.get("windows") or []
    blocking = sum(1 for item in items if item.y < 0.15 and item.h > 0.08)
    if windows:
        natural_light = max(0.0, 1.0 - blocking / max(len(windows), 1))
    else:
        natural_light = max(0.0, 0.75 - blocking * 0.15)

    # Ergonomics (10%): fraction of pairs with physical gap ≥ 0.40 m
    ERGO_MIN_M = 0.40
    ergonomics = (
        sum(1 for g in gaps_m if g >= ERGO_MIN_M) / len(gaps_m)
    ) if gaps_m else 1.0

    return {
        "circulation": round(circulation, 3),
        "balance": round(balance, 3),
        "focal_point": round(focal_point, 3),
        "natural_light": round(natural_light, 3),
        "ergonomics": round(ergonomics, 3),
    }


def _weighted_score(scores: dict[str, float]) -> float:
    return round(sum(scores.get(k, 0.0) * w for k, w in SOFT_WEIGHTS.items()), 4)


# ─────────────────────────── Hard Constraints ───────────────────────────

def _apply_hard_constraints(
    items: list[FurnitureItem], constraints: dict
) -> list[FurnitureItem]:
    must_remove = {
        s.lower().replace(" ", "_") for s in (constraints.get("must_remove") or [])
    }
    must_add = [
        s.lower().replace(" ", "_") for s in (constraints.get("must_add") or [])
    ]

    items = [item for item in items if item.type not in must_remove]

    existing = {item.type for item in items}
    for ftype in must_add:
        if ftype not in existing:
            w, h = FURNITURE_SIZES.get(ftype, FURNITURE_SIZES["default"])
            items.append(FurnitureItem(f"{ftype}_{len(items)+1}", ftype, 0.72, 0.72, w, h))
            existing.add(ftype)

    return items


def _enforce_immutable(
    items: list[FurnitureItem], regions: list[dict]
) -> list[FurnitureItem]:
    """Push items out of immutable regions (door/window clearance zones)."""
    for region in regions:
        rx = float(region.get("x", 0))
        ry = float(region.get("y", 0))
        rw = float(region.get("w", 0.1))
        rh = float(region.get("h", 0.1))
        for item in items:
            if (item.x + item.w > rx and item.x < rx + rw
                    and item.y + item.h > ry and item.y < ry + rh):
                candidate_x = rx - item.w - 0.03
                item.x = candidate_x if candidate_x >= 0 else rx + rw + 0.03
    return items


def _enforce_wall_anchor(
    items: list[FurnitureItem], space_info: dict, params: dict
) -> list[FurnitureItem]:
    """Snap wall-anchored furniture to the nearest wall if floating in the room."""
    wall_anchored = set(params.get("wall_anchored", []))
    snap_threshold = float(params.get("snap_threshold", 0.12))
    pad = float(params.get("pad", 0.02))
    for item in items:
        if item.type not in wall_anchored:
            continue
        d_t = item.y
        d_b = 1.0 - (item.y + item.h)
        d_l = item.x
        d_r = 1.0 - (item.x + item.w)
        if min(d_t, d_b, d_l, d_r) <= snap_threshold:
            continue
        if d_t <= d_b and d_t <= d_l and d_t <= d_r:
            item.y = pad
        elif d_b <= d_l and d_b <= d_r:
            item.y = 1.0 - item.h - pad
        elif d_l <= d_r:
            item.x = pad
        else:
            item.x = 1.0 - item.w - pad
    return items


def _build_semantic_gap_map(params: dict) -> dict[frozenset, float]:
    result: dict[frozenset, float] = {}
    for pair in params.get("pairs", []):
        types = pair.get("types", [])
        gap = float(pair.get("gap", 0.0))
        if len(types) == 2:
            result[frozenset(types)] = gap
    return result


def _enforce_semantic_gaps(
    items: list[FurnitureItem], space_info: dict, params: dict
) -> list[FurnitureItem]:
    """Push semantically incompatible furniture pairs apart to their required minimum gap."""
    gap_map = _build_semantic_gap_map(params)
    iterations = int(params.get("iterations", 30))
    for _ in range(iterations):
        moved = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                gap = gap_map.get(frozenset({a.type, b.type}))
                if gap is None or not _overlaps(a, b, margin=gap):
                    continue
                acx, acy = a.x + a.w / 2, a.y + a.h / 2
                bcx, bcy = b.x + b.w / 2, b.y + b.h / 2
                dx, dy = acx - bcx, acy - bcy
                ox = (a.x + a.w + gap) - b.x if dx >= 0 else b.x + b.w + gap - a.x
                oy = (a.y + a.h + gap) - b.y if dy >= 0 else b.y + b.h + gap - a.y
                if abs(ox) <= abs(oy):
                    half = ox / 2
                    a.x += half * (1 if dx >= 0 else -1)
                    b.x -= half * (1 if dx >= 0 else -1)
                else:
                    half = oy / 2
                    a.y += half * (1 if dy >= 0 else -1)
                    b.y -= half * (1 if dy >= 0 else -1)
                moved = True
        if not moved:
            break
    return items


def _enforce_bed_clearance(
    items: list[FurnitureItem], space_info: dict, params: dict
) -> list[FurnitureItem]:
    """Ensure each bed has at least one accessible side (left or right) free of obstruction."""
    side_clearance = float(params.get("side_clearance", 0.06))
    beds = [i for i in items if i.type == "bed"]
    others = [i for i in items if i.type != "bed"]

    for bed in beds:
        def _zone_clear(zx: float, zy: float, zw: float, zh: float) -> bool:
            return all(
                o.x + o.w <= zx or o.x >= zx + zw or
                o.y + o.h <= zy or o.y >= zy + zh
                for o in others
            )

        left_ok = bed.x >= side_clearance and _zone_clear(
            bed.x - side_clearance, bed.y, side_clearance, bed.h
        )
        right_ok = bed.x + bed.w + side_clearance <= 1.0 and _zone_clear(
            bed.x + bed.w, bed.y, side_clearance, bed.h
        )
        if left_ok or right_ok:
            continue
        for other in others:
            if (other.x < bed.x + bed.w + side_clearance and
                    other.x + other.w > bed.x + bed.w and
                    other.y < bed.y + bed.h and other.y + other.h > bed.y):
                other.x = bed.x + bed.w + side_clearance

    return items


def _enforce_desk_bed_separation(
    items: list[FurnitureItem], space_info: dict, params: dict
) -> list[FurnitureItem]:
    """Push desks away from beds and bunk beds so no part of the desk overlaps the bed area.
    Only the desk is moved — beds are wall-anchored and stay put.
    """
    M = float(params.get("min_gap", 0.10))
    bed_types = set(params.get("bed_types", ["bed", "bunk_bed"]))
    iterations = int(params.get("iterations", 40))
    pad = float(params.get("pad", 0.02))

    for _ in range(iterations):
        moved = False
        for desk in (i for i in items if i.type == "desk"):
            for bed in (i for i in items if i.type in bed_types):
                if not _overlaps(desk, bed, margin=M):
                    continue
                dcx = desk.x + desk.w / 2
                dcy = desk.y + desk.h / 2
                bcx = bed.x + bed.w / 2
                bcy = bed.y + bed.h / 2
                dx, dy = dcx - bcx, dcy - bcy
                ox = (desk.x + desk.w + M) - bed.x if dx >= 0 else bed.x + bed.w + M - desk.x
                oy = (desk.y + desk.h + M) - bed.y if dy >= 0 else bed.y + bed.h + M - desk.y
                if abs(ox) <= abs(oy):
                    desk.x += ox * (1 if dx >= 0 else -1)
                else:
                    desk.y += oy * (1 if dy >= 0 else -1)
                desk.x = max(pad, min(1.0 - desk.w - pad, desk.x))
                desk.y = max(pad, min(1.0 - desk.h - pad, desk.y))
                moved = True
        if not moved:
            break
    return items


def _enforce_bunk_bed_ladder_clearance(
    items: list[FurnitureItem], space_info: dict, params: dict
) -> list[FurnitureItem]:
    """Ensure each bunk bed has at least one side clear at floor level for ladder access.
    Checks all 4 sides; if none is clear, pushes obstructing items away from the bottom side
    (most natural ladder placement).
    """
    LC = float(params.get("ladder_clearance", 0.08))
    bunk_beds = [i for i in items if i.type == "bunk_bed"]
    others = [i for i in items if i.type != "bunk_bed"]

    for bed in bunk_beds:
        def _zone_clear(zx: float, zy: float, zw: float, zh: float) -> bool:
            return all(
                o.x + o.w <= zx or o.x >= zx + zw or
                o.y + o.h <= zy or o.y >= zy + zh
                for o in others
            )

        top_ok    = bed.y >= LC and _zone_clear(bed.x, bed.y - LC, bed.w, LC)
        bottom_ok = bed.y + bed.h + LC <= 1.0 and _zone_clear(bed.x, bed.y + bed.h, bed.w, LC)
        left_ok   = bed.x >= LC and _zone_clear(bed.x - LC, bed.y, LC, bed.h)
        right_ok  = bed.x + bed.w + LC <= 1.0 and _zone_clear(bed.x + bed.w, bed.y, LC, bed.h)

        if top_ok or bottom_ok or left_ok or right_ok:
            continue

        for other in others:
            if (other.x < bed.x + bed.w and other.x + other.w > bed.x
                    and other.y < bed.y + bed.h + LC
                    and other.y + other.h > bed.y + bed.h):
                other.y = bed.y + bed.h + LC

    return items


_LADDER_WALL_THRESHOLD = 0.05  # side is "against wall" if bed edge within this distance

def _inject_bunk_bed_ladder(items: list[FurnitureItem]) -> list[FurnitureItem]:
    """Place a bunk_ladder item next to each bunk_bed on its clearest floor-accessible side.

    Only non-wall sides are considered — the ladder must start from open floor space,
    not be sandwiched between the bed and a wall.
    Prefers foot-end (bottom) → right → left → head-end (top).
    Safe to call every iteration — skips beds that already have a ladder.
    """
    PAD = 0.02
    base_lw, base_lh = FURNITURE_SIZES["bunk_ladder"]

    others = [i for i in items if i.type not in ("bunk_bed", "bunk_ladder")]
    existing_ids = {i.id for i in items if i.type == "bunk_ladder"}
    new_ladders: list[FurnitureItem] = []

    for bed in (i for i in items if i.type == "bunk_bed"):
        ladder_id = f"bunk_ladder_{bed.id}"
        if ladder_id in existing_ids:
            continue

        def _zone_clear(zx: float, zy: float, zw: float, zh: float) -> bool:
            if zx < PAD or zy < PAD or zx + zw > 1.0 - PAD or zy + zh > 1.0 - PAD:
                return False
            return all(
                o.x + o.w <= zx or o.x >= zx + zw or
                o.y + o.h <= zy or o.y >= zy + zh
                for o in others
            )

        # Detect which sides are wall-adjacent — ladder cannot start from a wall
        wall_top    = bed.y <= _LADDER_WALL_THRESHOLD
        wall_bottom = 1.0 - (bed.y + bed.h) <= _LADDER_WALL_THRESHOLD
        wall_left   = bed.x <= _LADDER_WALL_THRESHOLD
        wall_right  = 1.0 - (bed.x + bed.w) <= _LADDER_WALL_THRESHOLD

        cx = bed.x + (bed.w - base_lw) / 2
        cy = bed.y + (bed.h - base_lw) / 2

        # (priority, lx, ly, lw, lh) — only non-wall sides eligible
        attempts: list[tuple[float, float, float, float, float]] = []

        if not wall_bottom:
            lx, ly = cx, bed.y + bed.h + PAD
            if _zone_clear(lx, ly, base_lw, base_lh):
                attempts.append((3.0, lx, ly, base_lw, base_lh))

        if not wall_right:
            lx, ly = bed.x + bed.w + PAD, cy
            if _zone_clear(lx, ly, base_lh, base_lw):
                attempts.append((2.0, lx, ly, base_lh, base_lw))

        if not wall_left:
            lx, ly = bed.x - base_lh - PAD, cy
            if _zone_clear(lx, ly, base_lh, base_lw):
                attempts.append((1.0, lx, ly, base_lh, base_lw))

        if not wall_top:
            lx, ly = cx, bed.y - base_lh - PAD
            if _zone_clear(lx, ly, base_lw, base_lh):
                attempts.append((0.0, lx, ly, base_lw, base_lh))

        if not attempts:
            continue

        _, lx, ly, lw, lh = max(attempts, key=lambda a: a[0])
        new_ladders.append(FurnitureItem(
            id=ladder_id, type="bunk_ladder",
            x=max(PAD, min(1.0 - lw - PAD, lx)),
            y=max(PAD, min(1.0 - lh - PAD, ly)),
            w=lw, h=lh,
        ))

    return items + new_ladders


def _enforce_bed_not_near_window(
    items: list[FurnitureItem], space_info: dict, params: dict
) -> list[FurnitureItem]:
    """Push beds and bunk beds away from window openings on any wall."""
    windows = space_info.get("windows") or []
    wc = float(params.get("window_clearance", 0.08))
    pad = float(params.get("pad", 0.02))
    bed_types = set(params.get("bed_types", ["bed", "bunk_bed"]))

    for item in items:
        if item.type not in bed_types:
            continue
        for window in windows:
            wx = float(window.get("x", 0.5))
            wy = float(window.get("y", 0.0))
            ww = float(window.get("w", 0.15))
            wh = float(window.get("h", ww))

            if wy <= 0.15:
                if item.y < wc and item.x + item.w > wx and item.x < wx + ww:
                    item.y = wc + pad
            elif wy >= 0.85:
                if (item.y + item.h > 1.0 - wc
                        and item.x + item.w > wx and item.x < wx + ww):
                    item.y = 1.0 - wc - item.h - pad
            elif wx <= 0.15:
                if item.x < wc and item.y + item.h > wy and item.y < wy + wh:
                    item.x = wc + pad
            elif wx >= 0.85:
                if (item.x + item.w > 1.0 - wc
                        and item.y + item.h > wy and item.y < wy + wh):
                    item.x = 1.0 - wc - item.w - pad
    return items


_LAYOUT_ENFORCERS: dict[str, Callable] = {
    "wall_anchor":               _enforce_wall_anchor,
    "semantic_gaps":             _enforce_semantic_gaps,
    "desk_bed_separation":       _enforce_desk_bed_separation,
    "bed_clearance":             _enforce_bed_clearance,
    "bunk_bed_ladder_clearance": _enforce_bunk_bed_ladder_clearance,
    "bed_not_near_window":       _enforce_bed_not_near_window,
}


# ─────────────────────────── LLM Interface ───────────────────────────

def _parse_llm_layout(text: str) -> list[dict] | None:
    text = text.strip()
    for prefix in ("```json", "```"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if not text.startswith("{"):
        start = text.find("{")
        if start != -1:
            text = text[start:]
    if not text.endswith("}"):
        end = text.rfind("}")
        if end != -1:
            text = text[: end + 1]
    try:
        data = json.loads(text)
        return data.get("furniture") or []
    except Exception:
        return None


def _call_llm_layout(prompt: str) -> list[FurnitureItem]:
    from designbridge.llm import call_llm

    text = call_llm(prompt)
    furniture_list = _parse_llm_layout(text)
    if not furniture_list:
        return []

    items: list[FurnitureItem] = []
    for f in furniture_list:
        ftype = str(f.get("type", "default")).lower().replace(" ", "_")
        dw, dh = FURNITURE_SIZES.get(ftype, FURNITURE_SIZES["default"])
        items.append(
            FurnitureItem(
                id=str(f.get("id", f"{ftype}_{len(items)+1}")),
                type=ftype,
                x=max(0.0, min(0.95, float(f.get("x", 0.1)))),
                y=max(0.0, min(0.95, float(f.get("y", 0.1)))),
                w=float(f.get("w", dw)),
                h=float(f.get("h", dh)),
                rotation=float(f.get("rotation", 0)),
            )
        )
    return items


# ───────────────────────── Default Fallback Layouts ───────────────────────────

def _default_layout(room_type: str) -> list[FurnitureItem]:
    presets: dict[str, list[FurnitureItem]] = {
        "living_room": [
            FurnitureItem("sofa_1", "sofa", 0.10, 0.58, 0.30, 0.13),
            FurnitureItem("coffee_table_1", "coffee_table", 0.18, 0.46, 0.15, 0.10),
            FurnitureItem("tv_unit_1", "tv_unit", 0.28, 0.08, 0.22, 0.07),
            FurnitureItem("armchair_1", "armchair", 0.52, 0.52, 0.11, 0.11),
            FurnitureItem("rug_1", "rug", 0.08, 0.42, 0.38, 0.24),
            FurnitureItem("plant_1", "plant", 0.76, 0.10, 0.06, 0.06),
        ],
        "bedroom": [
            FurnitureItem("bed_1", "bed", 0.30, 0.28, 0.22, 0.28),
            FurnitureItem("wardrobe_1", "wardrobe", 0.08, 0.08, 0.18, 0.08),
            FurnitureItem("nightstand_1", "nightstand", 0.24, 0.35, 0.07, 0.07),
            FurnitureItem("nightstand_2", "nightstand", 0.55, 0.35, 0.07, 0.07),
            FurnitureItem("dresser_1", "dresser", 0.68, 0.08, 0.14, 0.09),
        ],
        "kitchen": [
            FurnitureItem("dining_table_1", "dining_table", 0.30, 0.38, 0.20, 0.15),
            FurnitureItem("chair_1", "chair", 0.22, 0.40, 0.08, 0.08),
            FurnitureItem("chair_2", "chair", 0.52, 0.40, 0.08, 0.08),
            FurnitureItem("chair_3", "chair", 0.35, 0.30, 0.08, 0.08),
            FurnitureItem("chair_4", "chair", 0.35, 0.52, 0.08, 0.08),
        ],
        "study": [
            FurnitureItem("desk_1", "desk", 0.32, 0.08, 0.16, 0.09),
            FurnitureItem("chair_1", "chair", 0.37, 0.18, 0.08, 0.08),
            FurnitureItem("bookshelf_1", "bookshelf", 0.08, 0.08, 0.10, 0.05),
            FurnitureItem("bookshelf_2", "bookshelf", 0.08, 0.15, 0.10, 0.05),
            FurnitureItem("armchair_1", "armchair", 0.65, 0.55, 0.11, 0.11),
            FurnitureItem("side_table_1", "side_table", 0.62, 0.53, 0.07, 0.07),
        ],
    }
    return list(presets.get(room_type, presets["living_room"]))


# ─────────────────────────── Floor Plan Image ───────────────────────────

_FURNITURE_LABEL_MAP: dict[str, str] = {
    "sofa": "Sofa", "loveseat": "Loveseat", "coffee_table": "Coffee Table",
    "tv_unit": "TV Unit", "tv": "TV", "dining_table": "Dining Table",
    "chair": "Chair", "armchair": "Armchair", "bed": "Bed",
    "bunk_bed": "Bunk Bed", "bunk_ladder": "Ladder",
    "wardrobe": "Wardrobe", "desk": "Desk", "bookshelf": "Bookshelf",
    "side_table": "Side Table", "nightstand": "Nightstand",
    "lamp": "Lamp", "rug": "Rug", "plant": "Plant",
    "cabinet": "Cabinet", "dresser": "Dresser", "shelf": "Shelf",
}

_ROOM_LABEL_MAP: dict[str, str] = {
    "living_room": "LIVING ROOM", "bedroom": "BEDROOM",
    "kitchen": "KITCHEN / DINING", "study": "STUDY",
}


def _build_floor_plan_svg(items: list[FurnitureItem], room_type: str) -> str:
    W, H = 800, 800
    M = 80    # outer margin
    R = W - 2 * M   # room box size (640px)
    WT = 16   # wall thickness
    RI = R - 2 * WT  # interior room size (608px)

    def px(v: float) -> float: return M + WT + v * RI
    def py(v: float) -> float: return M + WT + v * RI
    def pw(v: float) -> float: return v * RI
    def ph(v: float) -> float: return v * RI

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        # White background
        f'<rect width="{W}" height="{H}" fill="white"/>',
        # Wall body (gray = solid concrete/masonry)
        f'<rect x="{M}" y="{M}" width="{R}" height="{R}" fill="#c8c8c8" stroke="#1a1a1a" stroke-width="2.5"/>',
        # Interior floor (off-white)
        f'<rect x="{M+WT}" y="{M+WT}" width="{RI}" height="{RI}" fill="#f8f6f0"/>',
    ]

    # Light grid lines
    for i in range(1, 5):
        gx = M + WT + i * RI // 5
        gy = M + WT + i * RI // 5
        lines.append(f'<line x1="{gx}" y1="{M+WT}" x2="{gx}" y2="{M+WT+RI}" stroke="#e0ddd6" stroke-width="1"/>')
        lines.append(f'<line x1="{M+WT}" y1="{gy}" x2="{M+WT+RI}" y2="{gy}" stroke="#e0ddd6" stroke-width="1"/>')

    # Door — bottom center (gap + swing arc)
    dcx = M + WT + RI // 2
    door_w = 48
    bot_wall_y = M + R - WT
    lines.append(f'<rect x="{dcx - door_w//2}" y="{bot_wall_y - 1}" width="{door_w}" height="{WT + 3}" fill="white"/>')
    lines.append(f'<line x1="{dcx - door_w//2}" y1="{bot_wall_y}" x2="{dcx - door_w//2}" y2="{bot_wall_y - door_w}" stroke="#555" stroke-width="1.5"/>')
    lines.append(f'<path d="M {dcx - door_w//2} {bot_wall_y - door_w} A {door_w} {door_w} 0 0 1 {dcx + door_w//2} {bot_wall_y}" stroke="#555" stroke-width="1.2" fill="none" stroke-dasharray="5,3"/>')

    # Window — top center (blue glazing)
    wcx = M + WT + RI // 2
    win_w = 70
    lines.append(f'<rect x="{wcx - win_w//2}" y="{M}" width="{win_w}" height="{WT}" fill="#c0daf8" stroke="#2e6ab5" stroke-width="1.5"/>')
    lines.append(f'<line x1="{wcx}" y1="{M}" x2="{wcx}" y2="{M + WT}" stroke="#2e6ab5" stroke-width="1.5"/>')

    # Furniture
    for item in items:
        fx1 = px(item.x)
        fy1 = py(item.y)
        fw  = pw(item.w)
        fh  = ph(item.h)
        fx2 = fx1 + fw
        fy2 = fy1 + fh
        fcx = fx1 + fw / 2
        fcy = fy1 + fh / 2

        r, g, b = FURNITURE_COLORS.get(item.type, FURNITURE_COLORS["default"])
        fill = f"rgb({r},{g},{b})"

        if item.type in ("chair", "armchair"):
            rad = max(5.0, min(fw, fh) / 2 - 1)
            lines.append(f'<circle cx="{fcx:.1f}" cy="{fcy:.1f}" r="{rad:.1f}" fill="{fill}" fill-opacity="0.55" stroke="#333" stroke-width="1.5"/>')
            if item.type == "armchair":
                br = rad + 4
                lines.append(f'<path d="M {fcx-br:.1f} {fcy:.1f} A {br} {br} 0 0 1 {fcx+br:.1f} {fcy:.1f}" stroke="#333" stroke-width="2.2" fill="none"/>')

        elif item.type == "plant":
            rad = max(5.0, min(fw, fh) / 2 - 1)
            lines.append(f'<circle cx="{fcx:.1f}" cy="{fcy:.1f}" r="{rad:.1f}" fill="{fill}" fill-opacity="0.65" stroke="#2a6a2a" stroke-width="1.5"/>')
            lines.append(f'<line x1="{fcx:.1f}" y1="{fy1+2:.1f}" x2="{fcx:.1f}" y2="{fy2-2:.1f}" stroke="#2a6a2a" stroke-width="1"/>')
            lines.append(f'<line x1="{fx1+2:.1f}" y1="{fcy:.1f}" x2="{fx2-2:.1f}" y2="{fcy:.1f}" stroke="#2a6a2a" stroke-width="1"/>')

        elif item.type == "lamp":
            rad = max(4.0, min(fw, fh) / 2)
            lines.append(f'<circle cx="{fcx:.1f}" cy="{fcy:.1f}" r="{rad:.1f}" fill="{fill}" fill-opacity="0.8" stroke="#b09000" stroke-width="1.5"/>')

        else:
            fw_r = max(4.0, fw)
            fh_r = max(4.0, fh)
            lines.append(f'<rect x="{fx1:.1f}" y="{fy1:.1f}" width="{fw_r:.1f}" height="{fh_r:.1f}" fill="{fill}" fill-opacity="0.45" stroke="#333" stroke-width="1.5" rx="2"/>')

            if item.type == "sofa" and fw > 40:
                n = max(2, int(fw / 30))
                for k in range(1, n):
                    lx = fx1 + k * fw / n
                    lines.append(f'<line x1="{lx:.1f}" y1="{fy1+3:.1f}" x2="{lx:.1f}" y2="{fy2-3:.1f}" stroke="#555" stroke-width="0.9"/>')
                bk_y = fy1 + fh * 0.32
                lines.append(f'<line x1="{fx1+2:.1f}" y1="{bk_y:.1f}" x2="{fx2-2:.1f}" y2="{bk_y:.1f}" stroke="#555" stroke-width="1.3"/>')

            elif item.type in ("bed", "bunk_bed") and fw > 32:
                hb_h = max(4.0, fh * 0.13)
                lines.append(f'<rect x="{fx1:.1f}" y="{fy1:.1f}" width="{fw_r:.1f}" height="{hb_h:.1f}" fill="#888" stroke="#444" stroke-width="1"/>')
                pl_w = fw * 0.37
                pl_h = max(4.0, fh * 0.22)
                pl_y = fy1 + hb_h + 3
                lines.append(f'<rect x="{fx1+3:.1f}" y="{pl_y:.1f}" width="{pl_w:.1f}" height="{pl_h:.1f}" fill="white" stroke="#666" stroke-width="0.9" rx="3"/>')
                if fw > 55:
                    lines.append(f'<rect x="{fx2-pl_w-3:.1f}" y="{pl_y:.1f}" width="{pl_w:.1f}" height="{pl_h:.1f}" fill="white" stroke="#666" stroke-width="0.9" rx="3"/>')

            elif item.type in ("desk", "dining_table", "coffee_table") and fw > 28:
                lines.append(f'<line x1="{fcx:.1f}" y1="{fy1+2:.1f}" x2="{fcx:.1f}" y2="{fy2-2:.1f}" stroke="#666" stroke-width="0.8"/>')
                lines.append(f'<line x1="{fx1+2:.1f}" y1="{fcy:.1f}" x2="{fx2-2:.1f}" y2="{fcy:.1f}" stroke="#666" stroke-width="0.8"/>')

            elif item.type == "wardrobe" and fw > 28:
                lines.append(f'<line x1="{fcx:.1f}" y1="{fy1:.1f}" x2="{fcx:.1f}" y2="{fy2:.1f}" stroke="#555" stroke-width="1.2"/>')
                lines.append(f'<circle cx="{fcx-4:.1f}" cy="{fcy:.1f}" r="2.5" fill="#555"/>')
                lines.append(f'<circle cx="{fcx+4:.1f}" cy="{fcy:.1f}" r="2.5" fill="#555"/>')

            elif item.type in ("bookshelf", "shelf") and fh > 14:
                n = max(2, int(fh / 12))
                for k in range(1, n):
                    sy = fy1 + k * fh / n
                    lines.append(f'<line x1="{fx1+1:.1f}" y1="{sy:.1f}" x2="{fx2-1:.1f}" y2="{sy:.1f}" stroke="#666" stroke-width="0.9"/>')

            elif item.type == "rug" and fw > 28:
                pad2 = min(7.0, fw * 0.09)
                lines.append(f'<rect x="{fx1+pad2:.1f}" y="{fy1+pad2:.1f}" width="{fw-pad2*2:.1f}" height="{fh-pad2*2:.1f}" fill="none" stroke="#999" stroke-width="0.9" stroke-dasharray="5,3"/>')

            elif item.type == "tv_unit" and fw > 28:
                lines.append(f'<rect x="{fx1+fw*0.15:.1f}" y="{fy1+fh*0.15:.1f}" width="{fw*0.7:.1f}" height="{fh*0.7:.1f}" fill="#555" stroke="#333" stroke-width="0.8" rx="1"/>')

        # Label
        label = _FURNITURE_LABEL_MAP.get(item.type, item.type.replace("_", " ").title())
        short = label if len(label) <= 9 else label[:8] + "."
        if fw >= 24 and fh >= 12:
            fs = int(max(8, min(11, fw / 5.5)))
            lines.append(f'<text x="{fcx:.1f}" y="{fcy+1:.1f}" font-family="Arial,Helvetica,sans-serif" font-size="{fs}" text-anchor="middle" dominant-baseline="middle" fill="#111">{short}</text>')

    # Room title — top-left inside wall
    room_label = _ROOM_LABEL_MAP.get(room_type, room_type.upper().replace("_", " "))
    lines.append(f'<text x="{M+WT+10}" y="{M+WT+22}" font-family="Arial,Helvetica,sans-serif" font-size="15" font-weight="bold" fill="#222">{room_label}</text>')

    # North arrow — top-right
    na_x, na_y = M + R - 24, M + 30
    lines.append(f'<polygon points="{na_x},{na_y-14} {na_x-8},{na_y+8} {na_x+8},{na_y+8}" fill="#333"/>')
    lines.append(f'<text x="{na_x}" y="{na_y+21}" font-family="Arial,Helvetica,sans-serif" font-size="12" text-anchor="middle" fill="#333">N</text>')

    # Scale bar — bottom-left inside wall
    sb_x = M + WT + 10
    sb_y = M + WT + RI - 18
    sb_w = RI // 5
    lines.append(f'<rect x="{sb_x}" y="{sb_y-2}" width="{sb_w}" height="4" fill="#444"/>')
    lines.append(f'<text x="{sb_x + sb_w//2}" y="{sb_y+13}" font-family="Arial,Helvetica,sans-serif" font-size="9" text-anchor="middle" fill="#444">1 m</text>')

    lines.append('</svg>')
    return '\n'.join(lines)


def _generate_floor_plan(
    items: list[FurnitureItem],
    task_id: str,
    room_type: str = "living_room",
    room_w: float = 4.0,
    room_d: float = 4.0,
) -> str | None:
    out = Path(Config.ARTIFACTS_DIR) / "layout" / f"{task_id}_floor_plan.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        import cairo
        import math

        W, H = 900, 980   # extra height for title + legend below
        M = 90            # outer margin
        R = 720           # room box size (square)
        WT = 20           # wall thickness
        RI = R - 2 * WT  # interior room span (680px)

        px_per_m_w = RI / room_w

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        ctx = cairo.Context(surface)
        ctx.set_antialias(cairo.ANTIALIAS_BEST)

        def text(s: str, x: float, y: float, size: float = 9, bold: bool = False, center: bool = False):
            ctx.select_font_face(
                "Arial",
                cairo.FONT_SLANT_NORMAL,
                cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
            )
            ctx.set_font_size(size)
            if center:
                ext = ctx.text_extents(s)
                x -= ext.width / 2
            ctx.move_to(x, y)
            ctx.show_text(s)

        # ── White background ──────────────────────────────────────────
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()

        # ── Outer border / title area ─────────────────────────────────
        ctx.set_source_rgb(0, 0, 0)
        ctx.set_line_width(1.5)
        ctx.rectangle(M - 10, M - 40, R + 20, R + 20 + 60)  # full drawing frame
        ctx.stroke()

        # Title bar at top of drawing frame
        ctx.set_source_rgb(0, 0, 0)
        ctx.rectangle(M - 10, M - 40, R + 20, 36)
        ctx.fill()
        ctx.set_source_rgb(1, 1, 1)
        room_label = _ROOM_LABEL_MAP.get(room_type, room_type.upper().replace("_", " "))
        text(f"FLOOR PLAN — {room_label}", M, M - 12, size=14, bold=True)
        size_label = f"{room_w:.1f}m × {room_d:.1f}m  ({room_w * room_d:.1f} m²)"
        ctx.set_source_rgb(0.85, 0.85, 0.85)
        text(size_label, M + R - 4, M - 12, size=10)

        # ── Solid black walls ─────────────────────────────────────────
        ctx.set_source_rgb(0.08, 0.08, 0.08)
        ctx.rectangle(M, M, R, R)
        ctx.fill()

        # ── Interior floor (white) ────────────────────────────────────
        ctx.set_source_rgb(1, 1, 1)
        ctx.rectangle(M + WT, M + WT, RI, RI)
        ctx.fill()

        # ── Fine grid (every meter) ───────────────────────────────────
        ctx.set_source_rgba(0.82, 0.82, 0.82, 1)
        ctx.set_line_width(0.6)
        grid_step_w = RI / room_w
        grid_step_d = RI / room_d
        for i in range(1, int(room_w)):
            gx = M + WT + i * grid_step_w
            ctx.move_to(gx, M + WT); ctx.line_to(gx, M + WT + RI); ctx.stroke()
        for j in range(1, int(room_d)):
            gy = M + WT + j * grid_step_d
            ctx.move_to(M + WT, gy); ctx.line_to(M + WT + RI, gy); ctx.stroke()

        # ── Door — bottom center (gap in wall + swing arc) ────────────
        dcx = M + WT + RI / 2
        door_px = min(80.0, px_per_m_w * 0.9)  # ~0.9m door
        bot_y = float(M + R - WT)
        # Erase gap
        ctx.set_source_rgb(1, 1, 1)
        ctx.rectangle(dcx - door_px / 2, bot_y, door_px, WT + 1)
        ctx.fill()
        # Swing
        hinge = dcx - door_px / 2
        ctx.set_source_rgb(0, 0, 0)
        ctx.set_line_width(1.2)
        ctx.move_to(hinge, bot_y); ctx.line_to(hinge, bot_y - door_px); ctx.stroke()
        ctx.set_dash([4, 3])
        ctx.arc(hinge, bot_y, door_px, -math.pi / 2, 0)
        ctx.stroke()
        ctx.set_dash([])
        # Label
        ctx.set_source_rgb(0.3, 0.3, 0.3)
        text("D", dcx - 3, bot_y + WT + 12, size=8)

        # ── Window — top center (three-line convention) ───────────────
        wcx = M + WT + RI / 2
        win_px = min(100.0, px_per_m_w * 1.2)
        # erase wall gap
        ctx.set_source_rgb(1, 1, 1)
        ctx.rectangle(wcx - win_px / 2, M, win_px, WT)
        ctx.fill()
        # three lines (standard window symbol)
        ctx.set_source_rgb(0, 0, 0)
        ctx.set_line_width(1.2)
        for offset in (-win_px / 2, 0.0, win_px / 2):
            ctx.move_to(wcx + offset, M); ctx.line_to(wcx + offset, M + WT); ctx.stroke()
        ctx.set_line_width(0.8)
        ctx.move_to(wcx - win_px / 2, M + WT / 2)
        ctx.line_to(wcx + win_px / 2, M + WT / 2)
        ctx.stroke()
        # Label
        ctx.set_source_rgb(0.3, 0.3, 0.3)
        text("W", wcx - 3, M - 4, size=8)

        # ── Room dimension ticks (outside walls) ─────────────────────
        ctx.set_source_rgb(0.2, 0.2, 0.2)
        ctx.set_line_width(0.8)
        tick = 6
        # Bottom: width
        dim_y = M + R + 16
        ctx.move_to(M, dim_y - tick); ctx.line_to(M, dim_y + tick); ctx.stroke()
        ctx.move_to(M + R, dim_y - tick); ctx.line_to(M + R, dim_y + tick); ctx.stroke()
        ctx.move_to(M, dim_y); ctx.line_to(M + R, dim_y); ctx.stroke()
        ctx.set_source_rgb(0, 0, 0)
        text(f"{room_w:.1f} m", M + R / 2, dim_y + 13, size=9, center=True)
        # Right: depth
        dim_x = M + R + 16
        ctx.set_source_rgb(0.2, 0.2, 0.2)
        ctx.move_to(dim_x - tick, M); ctx.line_to(dim_x + tick, M); ctx.stroke()
        ctx.move_to(dim_x - tick, M + R); ctx.line_to(dim_x + tick, M + R); ctx.stroke()
        ctx.move_to(dim_x, M); ctx.line_to(dim_x, M + R); ctx.stroke()
        ctx.save()
        ctx.translate(dim_x + 14, M + R / 2)
        ctx.rotate(-math.pi / 2)
        ctx.set_source_rgb(0, 0, 0)
        text(f"{room_d:.1f} m", 0, 0, size=9, center=True)
        ctx.restore()

        # ── Furniture (rugs drawn first as floor layer) ───────────────
        ordered = [i for i in items if i.type == "rug"] + [i for i in items if i.type != "rug"]
        for item in ordered:
            fx1 = M + WT + item.x * RI
            fy1 = M + WT + item.y * RI
            fw  = item.w * RI
            fh  = item.h * RI
            fcx = fx1 + fw / 2
            fcy = fy1 + fh / 2
            fx2 = fx1 + fw
            fy2 = fy1 + fh
            fw_r, fh_r = max(4.0, fw), max(4.0, fh)

            # Real-world size in meters
            rw = item.w * room_w
            rd = item.h * room_d

            if item.type in ("chair", "armchair"):
                rad = max(5.0, min(fw, fh) / 2 - 1)
                ctx.set_source_rgb(0.94, 0.94, 0.94)
                ctx.arc(fcx, fcy, rad, 0, 2 * math.pi); ctx.fill()
                ctx.set_source_rgb(0, 0, 0)
                ctx.set_line_width(1.2)
                ctx.arc(fcx, fcy, rad, 0, 2 * math.pi); ctx.stroke()
                if item.type == "armchair":
                    ctx.set_line_width(2.0)
                    ctx.arc(fcx, fcy, rad + 5, math.pi, 2 * math.pi); ctx.stroke()

            elif item.type == "plant":
                rad = max(5.0, min(fw, fh) / 2 - 1)
                ctx.set_source_rgb(0.9, 0.9, 0.9)
                ctx.arc(fcx, fcy, rad, 0, 2 * math.pi); ctx.fill()
                ctx.set_source_rgb(0, 0, 0)
                ctx.set_line_width(1.2)
                ctx.arc(fcx, fcy, rad, 0, 2 * math.pi); ctx.stroke()
                ctx.set_line_width(0.8)
                ctx.move_to(fcx, fy1 + 2); ctx.line_to(fcx, fy2 - 2); ctx.stroke()
                ctx.move_to(fx1 + 2, fcy); ctx.line_to(fx2 - 2, fcy); ctx.stroke()

            elif item.type == "lamp":
                rad = max(4.0, min(fw, fh) / 2)
                ctx.set_source_rgb(0.9, 0.9, 0.9)
                ctx.arc(fcx, fcy, rad, 0, 2 * math.pi); ctx.fill()
                ctx.set_source_rgb(0, 0, 0)
                ctx.set_line_width(1.2)
                ctx.arc(fcx, fcy, rad, 0, 2 * math.pi); ctx.stroke()

            elif item.type == "rug":
                ctx.set_source_rgb(0.92, 0.92, 0.92)
                ctx.rectangle(fx1, fy1, fw_r, fh_r); ctx.fill()
                ctx.set_source_rgb(0.5, 0.5, 0.5)
                ctx.set_line_width(0.8)
                ctx.set_dash([5, 3])
                ctx.rectangle(fx1, fy1, fw_r, fh_r); ctx.stroke()
                pad = min(6.0, fw * 0.08)
                ctx.rectangle(fx1 + pad, fy1 + pad, fw_r - pad * 2, fh_r - pad * 2); ctx.stroke()
                ctx.set_dash([])

            else:
                # Standard rectangular furniture — white fill, black outline
                ctx.set_source_rgb(0.96, 0.96, 0.96)
                ctx.rectangle(fx1, fy1, fw_r, fh_r); ctx.fill()
                ctx.set_source_rgb(0, 0, 0)
                ctx.set_line_width(1.5)
                ctx.rectangle(fx1, fy1, fw_r, fh_r); ctx.stroke()

                ctx.set_source_rgb(0, 0, 0)
                ctx.set_line_width(0.8)

                if item.type == "sofa" and fw > 35:
                    n = max(2, int(fw / 28))
                    for k in range(1, n):
                        lx = fx1 + k * fw / n
                        ctx.move_to(lx, fy1 + 3); ctx.line_to(lx, fy2 - 3); ctx.stroke()
                    bk_y = fy1 + fh * 0.30
                    ctx.set_line_width(1.5)
                    ctx.move_to(fx1 + 1, bk_y); ctx.line_to(fx2 - 1, bk_y); ctx.stroke()

                elif item.type in ("bed", "bunk_bed") and fw > 28:
                    hb_h = max(4.0, fh * 0.14)
                    ctx.set_source_rgb(0.2, 0.2, 0.2)
                    ctx.rectangle(fx1, fy1, fw_r, hb_h); ctx.fill()
                    pl_w = fw * 0.38
                    pl_h = max(4.0, fh * 0.22)
                    pl_y = fy1 + hb_h + 4
                    ctx.set_source_rgb(1, 1, 1)
                    ctx.rectangle(fx1 + 3, pl_y, pl_w, pl_h); ctx.fill()
                    ctx.set_source_rgb(0, 0, 0)
                    ctx.set_line_width(0.8)
                    ctx.rectangle(fx1 + 3, pl_y, pl_w, pl_h); ctx.stroke()
                    if fw > 50:
                        ctx.set_source_rgb(1, 1, 1)
                        ctx.rectangle(fx2 - pl_w - 3, pl_y, pl_w, pl_h); ctx.fill()
                        ctx.set_source_rgb(0, 0, 0)
                        ctx.rectangle(fx2 - pl_w - 3, pl_y, pl_w, pl_h); ctx.stroke()

                elif item.type in ("desk", "dining_table", "coffee_table") and fw > 24:
                    ctx.set_line_width(0.6)
                    ctx.move_to(fcx, fy1 + 2); ctx.line_to(fcx, fy2 - 2); ctx.stroke()
                    ctx.move_to(fx1 + 2, fcy); ctx.line_to(fx2 - 2, fcy); ctx.stroke()

                elif item.type == "wardrobe" and fw > 24:
                    ctx.set_line_width(1.2)
                    ctx.move_to(fcx, fy1); ctx.line_to(fcx, fy2); ctx.stroke()
                    ctx.set_source_rgb(0, 0, 0)
                    ctx.arc(fcx - 5, fcy, 2.5, 0, 2 * math.pi); ctx.fill()
                    ctx.arc(fcx + 5, fcy, 2.5, 0, 2 * math.pi); ctx.fill()

                elif item.type in ("bookshelf", "shelf", "cabinet") and fh > 12:
                    n = max(2, int(fh / 10))
                    for k in range(1, n):
                        sy = fy1 + k * fh / n
                        ctx.move_to(fx1 + 1, sy); ctx.line_to(fx2 - 1, sy); ctx.stroke()

                elif item.type == "tv_unit" and fw > 24:
                    ctx.set_source_rgb(0.15, 0.15, 0.15)
                    ctx.rectangle(fx1 + fw * 0.12, fy1 + fh * 0.12, fw * 0.76, fh * 0.76)
                    ctx.fill()

                elif item.type == "dresser" and fw > 20:
                    n = max(2, int(fw / 18))
                    for k in range(1, n):
                        lx = fx1 + k * fw / n
                        ctx.move_to(lx, fy1); ctx.line_to(lx, fy2); ctx.stroke()
                    ctx.arc(fcx, fcy, 2.5, 0, 2 * math.pi); ctx.fill()

            # ── Furniture label + real-world size ─────────────────────
            if fw >= 20 and fh >= 12:
                label = _FURNITURE_LABEL_MAP.get(item.type, item.type.replace("_", " ").title())
                fs_name = max(7.5, min(10.0, fw / 6.5))
                fs_dim  = max(6.5, min(8.5,  fw / 7.5))

                ctx.set_source_rgb(0.05, 0.05, 0.05)
                # If enough vertical space show name + dims on separate lines
                if fh >= 26:
                    text(label, fcx, fcy - 1, size=fs_name, center=True)
                    dim_str = f"{rw:.2f}×{rd:.2f}m"
                    ctx.set_source_rgb(0.35, 0.35, 0.35)
                    text(dim_str, fcx, fcy + fs_dim + 2, size=fs_dim, center=True)
                else:
                    short = label if len(label) <= 7 else label[:6] + "."
                    text(short, fcx, fcy + 3, size=fs_name, center=True)

        # ── North arrow (top-right, inside title) ─────────────────────
        na_x, na_y = M + R - 8, M - 24
        ctx.set_source_rgb(1, 1, 1)
        ctx.move_to(na_x, na_y - 10); ctx.line_to(na_x - 6, na_y + 6); ctx.line_to(na_x + 6, na_y + 6)
        ctx.close_path(); ctx.fill()
        ctx.set_source_rgb(0.9, 0.9, 0.9)
        text("N", na_x, na_y + 16, size=9, bold=True, center=True)

        # ── Scale bar (bottom, inside frame) ─────────────────────────
        sb_x = M
        sb_y = M + R + 38
        sb_w = int(px_per_m_w)  # 1 meter in pixels
        ctx.set_source_rgb(0, 0, 0)
        ctx.set_line_width(1.5)
        ctx.move_to(sb_x, sb_y); ctx.line_to(sb_x + sb_w, sb_y); ctx.stroke()
        ctx.set_line_width(1)
        for tick_x in (sb_x, sb_x + sb_w):
            ctx.move_to(tick_x, sb_y - 4); ctx.line_to(tick_x, sb_y + 4); ctx.stroke()
        text("0", sb_x - 3, sb_y + 13, size=8)
        text("1 m", sb_x + sb_w - 6, sb_y + 13, size=8)
        ctx.set_source_rgb(0.4, 0.4, 0.4)
        text("SCALE 1:?  (indicative)", sb_x + sb_w + 16, sb_y + 4, size=7)

        # ── Legend ────────────────────────────────────────────────────
        lx, ly = M + R - 200, M + R + 10
        ctx.set_source_rgb(0.3, 0.3, 0.3)
        text("D = Door  |  W = Window  |  Grid = 1 m", lx, ly + 30, size=7.5)

        surface.write_to_png(str(out))
        print(f"[layout_agent] Floor plan saved (pycairo B&W): {out}")
        return str(out)

    except Exception as e:
        print(f"⚠️ pycairo floor plan failed ({e}), falling back to PIL")

    # Fallback: PIL raster
    try:
        from PIL import Image, ImageDraw, ImageFont

        SIZE, MARGIN = 640, 52
        ROOM = SIZE - 2 * MARGIN
        WALL = 10
        img = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([MARGIN, MARGIN, SIZE - MARGIN, SIZE - MARGIN],
                       fill=(30, 30, 30), outline=(0, 0, 0), width=WALL)
        draw.rectangle([MARGIN + WALL, MARGIN + WALL,
                        SIZE - MARGIN - WALL, SIZE - MARGIN - WALL],
                       fill=(255, 255, 255))
        try:
            font_sm = font_md = None
            for fp in ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
                if Path(fp).exists():
                    font_sm = ImageFont.truetype(fp, 9)
                    font_md = ImageFont.truetype(fp, 13)
                    break
            if font_sm is None:
                font_sm = font_md = ImageFont.load_default()
        except Exception:
            font_sm = font_md = ImageFont.load_default()
        ROOM_I = ROOM - 2 * WALL
        for item in items:
            x1 = int(MARGIN + WALL + item.x * ROOM_I)
            y1 = int(MARGIN + WALL + item.y * ROOM_I)
            x2 = max(x1 + 6, int(MARGIN + WALL + (item.x + item.w) * ROOM_I))
            y2 = max(y1 + 6, int(MARGIN + WALL + (item.y + item.h) * ROOM_I))
            draw.rectangle([x1, y1, x2, y2], fill=(240, 240, 240), outline=(0, 0, 0), width=1)
            label = _FURNITURE_LABEL_MAP.get(item.type, item.type.replace("_", " ").title())
            short = label if len(label) <= 8 else label[:7] + "."
            if x2 - x1 >= 18 and y2 - y1 >= 10:
                draw.text(((x1 + x2) // 2, (y1 + y2) // 2), short,
                          fill=(0, 0, 0), anchor="mm", font=font_sm)
        room_label = _ROOM_LABEL_MAP.get(room_type, room_type.upper().replace("_", " "))
        draw.text((MARGIN + WALL + 6, MARGIN + WALL + 6), room_label, fill=(0, 0, 0), font=font_md)
        img.save(str(out))
        print(f"[layout_agent] Floor plan saved (PIL fallback): {out}")
        return str(out)
    except Exception as e:
        print(f"⚠️ Floor plan generation failed: {e}")
        return None


# ─────────────────────────── Main Entry Point ───────────────────────────

def run_layout_agent(
    structured_requirement: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    """
    Run layout planning. Returns a partial state dict (scene_graph, intermediate_outputs).
    NOTE: intermediate_outputs is NOT pre-merged — callers must merge with existing state.
    NOTE: layout_prompt is intentionally empty — spatial text degrades diffusion quality.
          Floor plan PNG is used for ControlNet only when ENABLE_LAYOUT_CONTROLNET=true.
    """
    from designbridge.prompts import LAYOUT_AGENT_PROMPT, LAYOUT_REFINEMENT_PROMPT

    layout_registry = get_layout_constraint_registry()
    meta = structured_requirement.get("meta") or {}
    space_info = structured_requirement.get("space_info") or {}
    constraints = structured_requirement.get("layout_constraints") or {}
    user_description = (
        structured_requirement.get("design_description")
        or structured_requirement.get("user_description_raw")
        or ""
    )
    room_type = meta.get("room_type", "living_room")
    max_iter = Config.LAYOUT_MAX_ITER

    def _build_prompt(extra: str = "") -> str:
        return LAYOUT_AGENT_PROMPT.format(
            room_type=room_type,
            width=space_info.get("estimated_size", {}).get("width", 5.0),
            depth=space_info.get("estimated_size", {}).get("depth", 4.0),
            windows=json.dumps(space_info.get("windows") or [], ensure_ascii=False),
            doors=json.dumps(space_info.get("doors") or [], ensure_ascii=False),
            must_keep=", ".join(constraints.get("must_keep") or []) or "無",
            must_add=", ".join(constraints.get("must_add") or []) or "無",
            must_remove=", ".join(constraints.get("must_remove") or []) or "無",
            immutable_regions=json.dumps(
                constraints.get("immutable_regions") or [], ensure_ascii=False
            ),
            user_description=user_description + ("\n" + extra if extra else ""),
        )

    # Initial layout from LLM
    try:
        items = _call_llm_layout(_build_prompt())
        if not items:
            raise ValueError("empty response")
    except Exception as e:
        print(f"⚠️ LLM layout failed ({e}), using default layout")
        items = _default_layout(room_type)

    best_items: list[FurnitureItem] = []
    best_score = -1.0
    scores: dict[str, float] = {}
    scores_history: list[float] = []
    SCORE_THRESHOLD = 0.65

    for iteration in range(max_iter):
        items = _apply_hard_constraints(items, constraints)
        immutable = constraints.get("immutable_regions") or []
        if immutable:
            items = _enforce_immutable(items, immutable)
        items = _clip_to_room(items)
        items = _inject_bunk_bed_ladder(items)
        items = _push_apart(items)
        for _card in layout_registry.load():
            _fn = _LAYOUT_ENFORCERS.get(_card.enforce)
            if _fn:
                items = _fn(items, space_info, _card.parameters)
        from designbridge.special_constraints import apply_special_layout_constraints
        items = apply_special_layout_constraints(items, structured_requirement)
        items = _clip_to_room(items)

        scores = _score_soft_constraints(items, space_info)
        total = _weighted_score(scores)
        scores_history.append(total)

        if total > best_score:
            best_score = total
            best_items = [FurnitureItem(**i.to_dict()) for i in items]

        print(
            f"[layout_agent] iter={iteration} score={total:.3f} "
            f"circ={scores['circulation']:.2f} bal={scores['balance']:.2f} "
            f"foc={scores['focal_point']:.2f} erg={scores['ergonomics']:.2f}"
        )

        if total >= SCORE_THRESHOLD or iteration >= max_iter - 1:
            break

        feedback = LAYOUT_REFINEMENT_PROMPT.format(**scores)
        try:
            refined = _call_llm_layout(_build_prompt(feedback))
            if refined:
                items = refined
        except Exception:
            break

    acceptance_rate = (
        sum(1 for s in scores_history if s >= SCORE_THRESHOLD) / len(scores_history)
        if scores_history else 0.0
    )
    print(
        f"[layout_agent] iterations={len(scores_history)} "
        f"best={best_score:.3f} acceptance_rate={acceptance_rate:.2%}"
    )

    from designbridge.special_constraints import verify_special_constraints
    special_satisfaction = verify_special_constraints(best_items, structured_requirement)
    infeasible_constraints = [k for k, v in special_satisfaction.items() if not v]
    feasible = not infeasible_constraints
    if infeasible_constraints:
        print(
            f"[layout_agent] ⚠️  infeasible after convergence: {infeasible_constraints}"
        )

    # Hard constraint satisfaction report
    must_keep_set = {s.lower().replace(" ", "_") for s in (constraints.get("must_keep") or [])}
    must_add_set = {s.lower().replace(" ", "_") for s in (constraints.get("must_add") or [])}
    must_remove_set = {s.lower().replace(" ", "_") for s in (constraints.get("must_remove") or [])}
    existing = {item.type for item in best_items}

    _lc_params = {c.enforce: c.parameters for c in layout_registry.load()}
    _wa_params = _lc_params.get("wall_anchor", {})
    _wall_anchored = set(_wa_params.get("wall_anchored", []))
    _snap_threshold = float(_wa_params.get("snap_threshold", 0.12))
    _gap_map = _build_semantic_gap_map(_lc_params.get("semantic_gaps", {}))

    constraint_check = {
        "must_keep_satisfied": all(t in existing for t in must_keep_set),
        "must_add_satisfied": all(t in existing for t in must_add_set),
        "must_remove_satisfied": all(t not in existing for t in must_remove_set),
        "collision_free": not any(
            _overlaps(best_items[i], best_items[j])
            for i in range(len(best_items))
            for j in range(i + 1, len(best_items))
        ),
        "wall_anchored": all(
            min(item.x, 1.0 - item.x - item.w, item.y, 1.0 - item.y - item.h) <= _snap_threshold
            for item in best_items if item.type in _wall_anchored
        ),
        "semantic_gaps_met": not any(
            _overlaps(best_items[i], best_items[j],
                      margin=_gap_map.get(frozenset({best_items[i].type, best_items[j].type}), 0.0))
            for i in range(len(best_items))
            for j in range(i + 1, len(best_items))
            if frozenset({best_items[i].type, best_items[j].type}) in _gap_map
        ),
    }

    size = space_info.get("estimated_size") or {}
    _fp_room_w = float(size.get("width", 4.0))
    _fp_room_d = float(size.get("depth", 4.0))
    floor_plan_path = _generate_floor_plan(best_items, task_id, room_type, _fp_room_w, _fp_room_d)

    scene_graph: dict[str, Any] = {
        "furniture_placements": [item.to_dict() for item in best_items],
        "layout_prompt": "",  # intentionally empty — not injected into diffusion prompt
        "layout_constraints_met": constraint_check,
        "soft_constraint_scores": scores,
        "weighted_score": best_score,
        "floor_plan_path": floor_plan_path,
        "feasible": feasible,
        "infeasible_constraints": infeasible_constraints,
    }

    return {
        "scene_graph": scene_graph,
        "intermediate_outputs": {
            "layout_agent": {
                "status": "ok" if feasible else "infeasible",
                "furniture_count": len(best_items),
                "weighted_score": best_score,
                "soft_scores": scores,
                "constraint_check": constraint_check,
                "floor_plan_path": floor_plan_path,
                "scores_history": scores_history,
                "acceptance_rate": round(acceptance_rate, 3),
                "iterations_run": len(scores_history),
                "feasible": feasible,
                "infeasible_constraints": infeasible_constraints,
            }
        },
    }
