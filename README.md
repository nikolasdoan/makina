# Makina — Machine Control Intelligent Agent (UR5 + RealSense)

[![CI](https://github.com/nikolasdoan/makina/actions/workflows/ci.yml/badge.svg)](https://github.com/nikolasdoan/makina/actions/workflows/ci.yml)

Cloud-based, text-first agent to control a UR5 manipulator with a RealSense D435i. Runs a FastAPI tool server and a CLI chat on macOS for development, with ROS 2/MoveIt 2 on Ubuntu 22.04 later. ASCII maps visualize objects and zones.

- PRD: `PRD.MD`
- App code: `robot-agent/`

## Quick start (macOS, no ROS required)

Requirements:
- Python 3.10+
- Optional: `OPENAI_API_KEY` for OpenAI tool-calling (falls back to local parser if absent)

Setup:
```bash
cd robot-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Start services:
- Tool server (mock ROS bridge):
```bash
make server
```
- CLI chat (new terminal):
```bash
make cli
```

Example (CLI):
- Move using numeric zones: `move blue cube to 1`
- Status: `status`
- Config commands:
  - `:setobj yellow_cube 0.32 0.12 0.05`
  - `:setzone 3 0.45 0.00 0.10 0.04`
  - `:showcfg`
  - Map inline: `:map` or `:make map`

## ASCII map
- Single run:
```bash
make map
```
- Auto-refresh (separate terminal):
```bash
make watch-map
```

## Configuration
Edit `robot-agent/deployment/config/settings.yaml`:
- `llm`: provider/model (OpenAI now, Ollama later)
- `safety`: thresholds (confidence, speed scale, force)
- `zones`: numeric keys (`'1'`, `'2'`, `'3'`) with `center_pose` and `tolerance_m`
- `objects`: `object_id -> pose`
- `workspace`: bounds used for map projection

Changes persist to YAML and reflect in the watcher and the server in real time.

## Ubuntu (ROS 2/MoveIt 2) — later
- Replace `MockBridge` in `robot-agent/llm_tool_server/bridge_ros2.py` with an rclpy-based bridge (ROS 2 Humble on Ubuntu 22.04) and the UR driver + MoveIt 2.
- Keep `settings.yaml` in sync for zones/objects/safety.

## Project layout
```
robot-agent/
├── llm_tool_server/
│   ├── main.py           # FastAPI tool server
│   ├── schemas.py        # Tool schemas (pick/place/stop/query_status/set_speed/move_object,get_config)
│   └── bridge_ros2.py    # Mock ROS bridge; swap with ROS 2 bridge on Ubuntu later
├── tools/
│   ├── term_map.py       # ASCII map renderer
│   └── watch_map.py      # Auto-refresh map when settings.yaml changes
├── deployment/
│   └── config/
│       └── settings.yaml # Safety, zones (numeric), objects, workspace, llm
├── cli_chat.py           # CLI chat (OpenAI tool-calling or parser mode)
├── requirements.txt
└── Makefile              # server/cli/map/watch-map
```

## Notes
- Numeric zones are canonical. The server resolves targets like `1` or `zone 1` and persists object poses after successful placements.
- If the server isn’t running, CLI `:showcfg` and moves will fail; start the server first.
