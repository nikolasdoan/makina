# Robot Agent Scaffold

Cloud-based conversational agent controlling a UR5 with RealSense D435i. Text-first via ChatGPT API, with a mock ROS layer for macOS development and ROS 2/MoveIt 2 on Ubuntu 22.04 later.

## Quick start (macOS, no ROS required)

- Python 3.10+
- Optional: `OPENAI_API_KEY` for LLM tool-calling. Without it, CLI runs in a simple parser mode.

```bash
cd robot-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Start tool server (mock ROS bridge)
make server
# In another terminal, run the CLI chat
make cli
```

## Endpoints
- `POST /tool-call` — invoke a tool by name with arguments
- `GET /status` — basic health/status

## Configuration
Settings live in `deployment/config/settings.yaml` and can be overridden by env vars.

Key settings:
- safety thresholds (`confidence_threshold`, `speed_scale`, `force_threshold_newton`)
- named zones and tolerances
- LLM provider/model (`openai` now, `ollama` later)

## Directory
```
robot-agent/
├── llm_tool_server/
│   ├── main.py           # FastAPI server
│   ├── schemas.py        # Tool schemas (pick/place/stop/query_status/set_speed/move_object)
│   └── bridge_ros2.py    # Mock ROS bridge; swap to ROS 2 on Ubuntu later
├── deployment/
│   └── config/
│       └── settings.yaml # Safety, zones, LLM, perception
├── cli_chat.py           # CLI chat client (uses OpenAI if available; parser fallback)
├── requirements.txt
└── Makefile
```

## Ubuntu (ROS 2/MoveIt 2)
- Use UR5 MoveIt 2 sim and RealSense on Ubuntu 22.04. Bridge this server to ROS actions later by replacing `MockBridge` with a ROS 2 implementation in `bridge_ros2.py`.

## Notes
- This scaffold aims for immediate local testing without hardware.
- The PRD is in the project root at `../PRD.MD`.
