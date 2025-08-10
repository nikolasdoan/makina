from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import yaml


@dataclass
class Pose:
    x: float
    y: float


COLOR_KEYS = [
    ("red", "R"),
    ("blue", "B"),
    ("green", "G"),
    ("yellow", "Y"),
    ("orange", "O"),
    ("purple", "P"),
    ("pink", "P"),
    ("black", "K"),  # K to avoid blue 'B' clash
    ("white", "W"),
    ("gray", "A"),   # A for grAy to avoid 'G'
]


def load_config(base: Path) -> Dict:
    with (base / "deployment" / "config" / "settings.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def project_to_grid(x: float, y: float, bounds: Dict[str, Tuple[float, float]], width: int, height: int) -> Tuple[int, int]:
    xmin, xmax = bounds["x"]
    ymin, ymax = bounds["y"]
    # Normalize to [0,1]
    nx = (x - xmin) / (xmax - xmin)
    ny = (y - ymin) / (ymax - ymin)
    # Grid coords (row, col). Row inverted so +y is up.
    col = max(0, min(width - 1, int(round(nx * (width - 1)))))
    row = max(0, min(height - 1, int(round((1.0 - ny) * (height - 1)))))
    return row, col


def label_for_object(obj_id: str) -> str:
    low = obj_id.lower()
    for key, letter in COLOR_KEYS:
        if key in low:
            return letter
    for ch in obj_id:
        if ch.isalpha():
            return ch.upper()
    return "O"


def render_map(cfg: Dict, width: int = 41, height: int = 21) -> str:
    bounds = cfg.get("workspace", {}).get("bounds_m", {"x": [0.0, 1.0], "y": [0.0, 1.0]})
    grid = [[" "] * width for _ in range(height)]

    # Borders
    for c in range(width):
        grid[0][c] = "-"; grid[height - 1][c] = "-"
    for r in range(height):
        grid[r][0] = "|"; grid[r][width - 1] = "|"
    grid[0][0] = "+"; grid[0][width - 1] = "+"; grid[height - 1][0] = "+"; grid[height - 1][width - 1] = "+"

    # Zones numbered 1..N (single cell shows last digit if >9)
    zones = cfg.get("zones", {})
    zone_labels: Dict[str, str] = {}
    for idx, zid in enumerate(zones.keys(), start=1):
        zone_labels[zid] = str(idx)[-1]

    for zid, zdef in zones.items():
        cp = zdef.get("center_pose", {})
        row, col = project_to_grid(cp.get("x", 0.0), cp.get("y", 0.0), bounds, width, height)
        ch = zone_labels.get(zid, "Z")
        if grid[row][col] in {"|", "-", "+"}:
            continue
        grid[row][col] = ch

    # Objects with single-letter tags
    objects = cfg.get("objects", {})
    object_labels: Dict[str, str] = {oid: label_for_object(oid) for oid in objects.keys()}
    for oid, odef in objects.items():
        p = odef.get("pose", {})
        row, col = project_to_grid(p.get("x", 0.0), p.get("y", 0.0), bounds, width, height)
        ch = object_labels.get(oid, "O")
        if grid[row][col] not in {" ",}|{"|","-","+"}:  # collision with zone/other -> mark '*'
            grid[row][col] = "*"
        else:
            grid[row][col] = ch

    lines = ["".join(row) for row in grid]

    # Legends
    obj_items = ", ".join(f"{object_labels[k]}={k}" for k in objects.keys())
    zone_items = ", ".join(f"{zone_labels[k]}={k}" for k in zones.keys())
    legend = [
        "Legend: Objects[letter=id] | Zones[number=id]",
        f"Objects: {obj_items}" if obj_items else "Objects: (none)",
        f"Zones: {zone_items}" if zone_items else "Zones: (none)",
        f"Bounds x={bounds['x']} y={bounds['y']}",
    ]
    return "\n".join(lines + [""] + legend)


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    cfg = load_config(base)
    print(render_map(cfg))


if __name__ == "__main__":
    main()
