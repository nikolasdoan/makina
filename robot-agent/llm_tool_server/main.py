from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from openai import OpenAI

from .bridge_ros2 import MockBridge, ZoneDefinition
from .schemas import get_tool_schemas


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
# Load local .env for OPENAI_API_KEY if present
load_dotenv(dotenv_path=str(BASE_DIR / '.env'))
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
import os
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
            "active": bool(os.getenv("OPENAI_API_KEY")),
            "active": bool(os.getenv("OPENAI_API_KEY")),
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




@app.post("/llm/activate")
async def llm_activate(payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = str(payload.get('api_key', '')).strip()
    model = str(payload.get('model', '')).strip() or SETTINGS.get('llm', {}).get('model', 'gpt-4o-mini')
    if not api_key:
        return { 'ok': False, 'error': 'missing_api_key' }
    # Write to .env and set env for this process
    env_path = BASE_DIR / '.env'
    env_path.write_text('OPENAI_API_KEY=' + api_key + '\n', encoding='utf-8')
    os.environ['OPENAI_API_KEY'] = api_key
    SETTINGS.setdefault('llm', {})['provider'] = 'openai'
    SETTINGS['llm']['model'] = model
    save_settings(SETTINGS_PATH, SETTINGS)
    return { 'ok': True, 'llm': { 'provider': 'openai', 'model': model, 'active': True } }


@app.post("/llm/deactivate")
async def llm_deactivate() -> Dict[str, Any]:
    # Remove key from env and blank .env
    os.environ.pop('OPENAI_API_KEY', None)
    env_path = BASE_DIR / '.env'
    try:
        env_path.write_text('', encoding='utf-8')
    except Exception:
        pass
    return { 'ok': True, 'llm': { 'provider': SETTINGS.get('llm', {}).get('provider', 'openai'), 'model': SETTINGS.get('llm', {}).get('model', 'gpt-4o-mini'), 'active': False } }


@app.post("/chat")
async def chat(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = str(payload.get('text', '')).strip()
    if not text:
        return { 'ok': False, 'error': 'empty_text' }

    # If LLM active, use tool-calling; otherwise naive fallback
    use_llm = bool(os.getenv('OPENAI_API_KEY'))
    if use_llm:
        try:
            client = OpenAI()
            tools = [{ 'type': 'function', 'function': schema } for schema in get_tool_schemas()]
            system_prompt = (
                'You are a robotics assistant for a UR5 arm. Use tools to act. '                 'Resolve ambiguity by asking for clarification. Accept numeric zones (1,2,3). '                 'Confirm risky actions. Keep answers concise.'
            )
            messages = [
                { 'role': 'system', 'content': system_prompt },
                { 'role': 'user', 'content': text },
            ]
            first = client.chat.completions.create(
                model=SETTINGS.get('llm', {}).get('model', 'gpt-4o-mini'),
                messages=messages,
                tools=tools,
                tool_choice='auto',
            )
            msg = first.choices[0].message
            tool_results = []
            if msg.tool_calls:
                # append assistant message with tool_calls
                messages.append({
                    'role': 'assistant',
                    'content': msg.content or '',
                    'tool_calls': [
                        {
                            'id': tc.id,
                            'type': 'function',
                            'function': { 'name': tc.function.name, 'arguments': tc.function.arguments or '{}' },
                        } for tc in msg.tool_calls
                    ],
                })
                for tc in msg.tool_calls:
                    name = tc.function.name
                    import json as _json
                    args = _json.loads(tc.function.arguments or '{}')
                    # Execute via internal logic (same as /tool-call)
                    if name == 'set_speed':
                        res = BRIDGE.set_speed(float(args.get('scale')))
                    elif name == 'stop':
                        res = BRIDGE.stop()
                    elif name == 'pick':
                        res = BRIDGE.pick(object_id=str(args.get('object_id')), grip_strength=float(args.get('grip_strength', 0.6)))
                    elif name == 'place':
                        target=args.get('target'); pose=args.get('pose')
                        zone_key = resolve_zone_key(SETTINGS, str(target)) if target is not None else None
                        if target is not None and zone_key is None:
                            res = { 'ok': False, 'error': 'unknown_zone' }
                        else:
                            res = BRIDGE.place(target=zone_key, pose=pose)
                            if res.get('ok'):
                                placed_object = res.get('placed_object')
                                if placed_object:
                                    new_pose = SETTINGS.get('zones', {}).get(zone_key, {}).get('center_pose', {}) if zone_key is not None else (pose or {})
                                    SETTINGS.setdefault('objects', {}).setdefault(placed_object, {})['pose'] = new_pose
                                    save_settings(SETTINGS_PATH, SETTINGS)
                    elif name == 'move_object':
                        object_id=str(args.get('object_id'))
                        target=args.get('target'); pose=args.get('pose')
                        zone_key = resolve_zone_key(SETTINGS, str(target)) if target is not None else None
                        if target is not None and zone_key is None:
                            res = { 'ok': False, 'error': 'unknown_zone' }
                        else:
                            p1 = BRIDGE.pick(object_id=object_id)
                            if not p1.get('ok'):
                                res = p1
                            else:
                                p2 = BRIDGE.place(target=zone_key, pose=pose)
                                if p2.get('ok'):
                                    new_pose = SETTINGS.get('zones', {}).get(zone_key, {}).get('center_pose', {}) if zone_key is not None else (pose or {})
                                    SETTINGS.setdefault('objects', {}).setdefault(object_id, {})['pose'] = new_pose
                                    save_settings(SETTINGS_PATH, SETTINGS)
                                    p2['new_pose'] = new_pose
                                res = p2
                    elif name == 'query_status':
                        res = BRIDGE.query_status()
                    else:
                        res = { 'ok': False, 'error': 'unknown_tool' }
                    tool_results.append({ 'name': name, 'result': res })
                    # feed back
                    messages.append({ 'role': 'tool', 'tool_call_id': tc.id, 'name': name, 'content': _json.dumps(res) })
                # final follow-up
                follow = client.chat.completions.create(
                    model=SETTINGS.get('llm', {}).get('model', 'gpt-4o-mini'),
                    messages=messages,
                )
                assistant_text = follow.choices[0].message.content or 'ok'
                return { 'ok': True, 'assistant': assistant_text, 'tool_results': tool_results }
            else:
                # no tool calls -> just return text
                assistant_text = msg.content or ''
                return { 'ok': True, 'assistant': assistant_text, 'tool_results': [] }
        except Exception as e:
            return { 'ok': False, 'error': 'llm_error', 'detail': str(e) }

    # naive fallback
    import re as _re
    m = _re.match(r'^move\s+([a-z0-9_\- ]+)\s+to\s+([a-z0-9_\-]+)$', text.lower())
    if m:
        object_id = m.group(1).replace(' ', '_')
        target = m.group(2)
        zone_key = resolve_zone_key(SETTINGS, target)
        if target is not None and zone_key is None:
            return { 'ok': False, 'error': 'unknown_zone' }
        p1 = BRIDGE.pick(object_id=object_id)
        if not p1.get('ok'):
            return { 'ok': False, 'error': p1.get('error', 'pick_failed') }
        p2 = BRIDGE.place(target=zone_key, pose=None)
        return { 'ok': p2.get('ok', False), 'assistant': 'ok' if p2.get('ok') else 'failed', 'tool_results': [ { 'name': 'pick', 'result': p1 }, { 'name': 'place', 'result': p2 } ] }
    if text.lower() == 'status':
        return { 'ok': True, 'assistant': 'status', 'tool_results': [ { 'name': 'query_status', 'result': BRIDGE.query_status() } ] }
    return { 'ok': False, 'assistant': 'Try: "move blue cube to 1" or "status"', 'tool_results': [] }

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
