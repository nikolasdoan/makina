from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .bridge_ros2 import MockBridge, ZoneDefinition


def load_settings(base_dir: Path) -> Dict[str, Any]:
    settings_path = base_dir / "deployment" / "config" / "settings.yaml"
    if not settings_path.exists():
        raise FileNotFoundError(f"Missing settings.yaml at {settings_path}")
    with settings_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_settings(settings_path: Path, settings: Dict[str, Any]) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with settings_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(settings, f, sort_keys=False)


def canonicalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def resolve_zone_key(settings: Dict[str, Any], name: str) -> Optional[str]:
    zones = settings.get("zones", {})
    keys = list(zones.keys())
    m = re.fullmatch(r"\s*(?:zone\s*)?(\d+)\s*", name, flags=re.IGNORECASE)
    if m:
        idx = int(m.group(1))
        if 1 <= idx <= len(keys):
            return keys[idx - 1]
    target_canon = canonicalize_identifier(name)
    for key in keys:
        if canonicalize_identifier(key) == target_canon:
            return key
    return None


class ToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    ok: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PoseModel(BaseModel):
    x: float
    y: float
    z: float


class ObjectUpsert(BaseModel):
    id: str
    pose: PoseModel


class ZoneUpsert(BaseModel):
    id: str
    center_pose: PoseModel
    tolerance_m: float = 0.03


BASE_DIR = Path(__file__).resolve().parents[1]
SETTINGS_PATH = BASE_DIR / "deployment" / "config" / "settings.yaml"
SETTINGS = load_settings(BASE_DIR)


def build_bridge_from_settings(settings: Dict[str, Any]) -> MockBridge:
    zones_cfg = settings.get("zones", {})
    zones: Dict[str, ZoneDefinition] = {}
    for zone_id, zone_data in zones_cfg.items():
        center_pose = zone_data.get("center_pose", {})
        tolerance_m = float(zone_data.get("tolerance_m", 0.03))
        zones[zone_id] = ZoneDefinition(center_pose=center_pose, tolerance_m=tolerance_m)
    speed_scale = float(settings.get("safety", {}).get("speed_scale", 0.3))
    return MockBridge(zones=zones, speed_scale=speed_scale)


BRIDGE = build_bridge_from_settings(SETTINGS)


def reload_bridge_zones_from_settings() -> None:
    zones_cfg = SETTINGS.get("zones", {})
    zones: Dict[str, ZoneDefinition] = {}
    for zone_id, zone_data in zones_cfg.items():
        zones[zone_id] = ZoneDefinition(
            center_pose=zone_data.get("center_pose", {}),
            tolerance_m=float(zone_data.get("tolerance_m", 0.03)),
        )
    BRIDGE.zones = zones


app = FastAPI(title="Robot Agent Tool Server", version="0.1.0")

# Enable CORS for local dev
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

# Serve simple web UI
from pathlib import Path as _Path
_BASE_DIR = _Path(__file__).resolve().parents[1]
app.mount('/ui', StaticFiles(directory=str(_BASE_DIR / 'frontend'), html=True), name='static')

@app.get('/')
async def root_redirect():
    return RedirectResponse(url='/ui/')


@app.get("/status")
async def get_status() -> Dict[str, Any]:
    return {
        "ok": True,
        "bridge": BRIDGE.query_status(),
        "llm": {
            "provider": SETTINGS.get("llm", {}).get("provider", "openai"),
            "model": SETTINGS.get("llm", {}).get("model", "gpt-4o-mini"),
        },
    }


@app.get("/config")
async def get_config() -> Dict[str, Any]:
    return {
        "ok": True,
        "zones": SETTINGS.get("zones", {}),
        "objects": SETTINGS.get("objects", {}),
        "workspace": SETTINGS.get("workspace", {}),
    }


from tools.term_map import load_config as _load_cfg, render_map as _render_map

@app.get('/map')
async def get_map():
    cfg=_load_cfg(BASE_DIR)
    return { 'map': _render_map(cfg) }

@app.post("/config/object")
async def upsert_object(obj: ObjectUpsert) -> Dict[str, Any]:
    SETTINGS.setdefault("objects", {})[obj.id] = {"pose": obj.pose.model_dump()}
    save_settings(SETTINGS_PATH, SETTINGS)
    return {"ok": True, "object": SETTINGS["objects"][obj.id]}


@app.post("/config/zone")
async def upsert_zone(zone: ZoneUpsert) -> Dict[str, Any]:
    SETTINGS.setdefault("zones", {})[zone.id] = {
        "center_pose": zone.center_pose.model_dump(),
        "tolerance_m": zone.tolerance_m,
    }
    save_settings(SETTINGS_PATH, SETTINGS)
    reload_bridge_zones_from_settings()
    return {"ok": True, "zone": SETTINGS["zones"][zone.id]}


@app.post("/tool-call", response_model=ToolCallResponse)
async def tool_call(req: ToolCallRequest) -> ToolCallResponse:
    try:
        if req.name == "get_config":
            return ToolCallResponse(ok=True, result={
                "zones": SETTINGS.get("zones", {}),
                "objects": SETTINGS.get("objects", {}),
                "workspace": SETTINGS.get("workspace", {}),
            })
        if req.name == "set_speed":
            scale = float(req.arguments.get("scale"))
            res = BRIDGE.set_speed(scale)
            return ToolCallResponse(ok=res.get("ok", False), result=res, error=res.get("error"))
        if req.name == "stop":
            res = BRIDGE.stop()
            return ToolCallResponse(ok=res.get("ok", False), result=res, error=res.get("error"))
        if req.name == "pick":
            object_id = str(req.arguments.get("object_id"))
            grip_strength = float(req.arguments.get("grip_strength", 0.6))
            res = BRIDGE.pick(object_id=object_id, grip_strength=grip_strength)
            return ToolCallResponse(ok=res.get("ok", False), result=res, error=res.get("error"))
        if req.name == "place":
            target = req.arguments.get("target")
            pose = req.arguments.get("pose")
            zone_key: Optional[str] = None
            if target is not None:
                zone_key = resolve_zone_key(SETTINGS, str(target))
                if zone_key is None:
                    return ToolCallResponse(ok=False, error="unknown_zone")
            res = BRIDGE.place(target=zone_key, pose=pose)
            if res.get("ok"):
                placed_object = res.get("placed_object")
                if placed_object:
                    if zone_key is not None:
                        new_pose = SETTINGS.get("zones", {}).get(zone_key, {}).get("center_pose", {})
                    else:
                        new_pose = pose or {}
                    SETTINGS.setdefault("objects", {}).setdefault(placed_object, {})["pose"] = new_pose
                    save_settings(SETTINGS_PATH, SETTINGS)
            return ToolCallResponse(ok=res.get("ok", False), result=res, error=res.get("error"))
        if req.name == "move_object":
            object_id = str(req.arguments.get("object_id"))
            target = req.arguments.get("target")
            pose = req.arguments.get("pose")
            zone_key: Optional[str] = None
            if target is not None:
                zone_key = resolve_zone_key(SETTINGS, str(target))
                if zone_key is None:
                    return ToolCallResponse(ok=False, error="unknown_zone")
            p1 = BRIDGE.pick(object_id=object_id)
            if not p1.get("ok"):
                return ToolCallResponse(ok=False, error=p1.get("error"))
            p2 = BRIDGE.place(target=zone_key, pose=pose)
            if p2.get("ok"):
                if zone_key is not None:
                    new_pose = SETTINGS.get("zones", {}).get(zone_key, {}).get("center_pose", {})
                else:
                    new_pose = pose or {}
                SETTINGS.setdefault("objects", {}).setdefault(object_id, {})["pose"] = new_pose
                save_settings(SETTINGS_PATH, SETTINGS)
                p2["new_pose"] = new_pose
            return ToolCallResponse(ok=p2.get("ok", False), result=p2, error=p2.get("error"))
        if req.name == "query_status":
            res = BRIDGE.query_status()
            return ToolCallResponse(ok=True, result=res)
        return ToolCallResponse(ok=False, error="unknown_tool")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("llm_tool_server.main:app", host="0.0.0.0", port=8000, reload=True)
