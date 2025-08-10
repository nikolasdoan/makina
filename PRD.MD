## PRD — Cloud‑based Conversational Agent for 6‑DOF Manipulator

Owner: TBD  •  Version: 0.1  •  Status: Draft

### 1) Goals and Non‑Goals

- **Primary goals**
  - **Natural‑language to safe robot actions** for a **UR5/UR5e** manipulator with **Intel RealSense** camera.
  - **Text chat first**, optional **voice** later.
  - **Sim and hardware parity**: develop in MoveIt 2 sim; swap to real robot with minimal change.
  - **Pick and place using perception**, with human confirmation for risky actions.
- **Secondary goals**
  - Extensible tool schema for new skills (e.g., scan, set speed, stop).
  - Lightweight UI (CLI now; simple web later).
- **Non‑goals (v1)**
  - Multi‑robot coordination, autonomous navigation, or mobile base.
  - Learning new policies on the robot; training pipelines.
  - Complex task planning beyond pick/place.

### 2) Personas and Use Cases

- **Lab Operator**: issues commands like “pick the red cube and place in bin A,” supervises safety.
- **Robotics Developer**: iterates on skills, vision, and ROS integration.
- **Demo Viewer**: runs scripted demos safely.

Core use cases:
- **Pick and place known objects** by name, color, or tag.
- **Query status**: current pose, gripper state, camera health.
- **Stop/abort**: immediate halt on request or anomaly.
- **Calibrate/update map**: add or adjust object poses (guard‑railed).

### 3) Requirements

- **Functional**
  - Chat interface to an LLM with tool‑calling to invoke robot skills.
  - Skills: `pick(object_id)`, `place(target|pose)`, `stop()`, `query_status()`, `set_speed(scale)`.
  - Perception: detect objects, estimate 3D pose, maintain `object_id → pose` registry.
  - Modes: simulation and hardware, selectable at runtime.
  - Safety: confirmation prompt for moves outside safe zone or unknown objects.
  - Feedback loop: stream execution state back to chat.
  - Demo task: **identify objects with YOLOv8 and execute “move object A to location B”** via pick+place.
- **Non‑functional (targets)**
  - **Latency**: text → tool call ≤ 1.5s p95; tool server → ROS action start ≤ 200ms.
  - **Perception**: ≥ 10 FPS; pose accuracy ≤ 10 mm at 0.5 m.
  - **Reliability**: pick success ≥ 90% on known objects; uptime 99% during demo sessions.
  - **Safety**: hard E‑Stop; software stop within 150ms; workspace and force/torque limits enforced.

### 4) Assumptions and Constraints

- Development on **macOS** (tool server + chat UI), with **ROS 2 Humble on Ubuntu 22.04** PC for simulation and hardware.
- Python 3.10+ for tool server; NVIDIA GPU optional on Ubuntu for YOLOv8.
- Manipulator: **UR5** via MoveIt 2 and **UR ROS 2 Driver (Humble)** in simulation; fixed table workspace; reachable bins.
- Camera: **Intel RealSense D435i**, wrist‑mounted, working distance **30–50 cm**; known calibration procedures.
- LLM: **OpenAI ChatGPT API first**; optional local LLM later (e.g., Ollama/vLLM) not required for v1.

### 5) System Architecture

```
[ Chat UI ] → [ LLM w/ Tool Calling ] → [ Tool Server (FastAPI) ]
                                           ↓
                                     [ ROS 2 Bridge ]
                                           ↓
                               [ Manipulator Skills (ROS 2 Action) ]
                                           ↓
                                 [ MoveIt 2 + Perception Nodes ]
                                           ↑
                        [ Camera → Object Detection → Pose Estimation ]
```

### 6) Tech Stack

| Layer                   | Tool / Framework                                          |
| ----------------------- | --------------------------------------------------------- |
| **LLM**                 | OpenAI ChatGPT API first; optional local LLM later (Ollama/vLLM) |
| **Tool server**         | Python + FastAPI (receives LLM tool calls)                |
| **Bridge to robot**     | ROS 2 Humble (with `rclpy`)                               |
| **Manipulator control** | MoveIt 2 + UR ROS 2 driver + ROS 2 Action interface       |
| **Perception**          | Intel RealSense + YOLOv8 + pose estimation                |
| **Object interface**    | AprilTags or QR markers (optional)                        |
| **Skill orchestration** | BehaviorTree.CPP or `py_trees` (simple first)             |
| **Chat UI**             | CLI for MVP; optional React + WebSocket                   |

### 7) Interfaces and APIs

- **Chat/LLM**: provider SDK; tool‑call JSON schemas below.
- **Tool Server (FastAPI)**
  - `POST /tool-call`: receives tool invocations from LLM, dispatches to ROS.
  - `GET /status`: returns robot/perception/system health.
  - WebSocket stream for execution updates (optional).
- **ROS 2 Actions/Topics**
  - Actions: `/skills/pick`, `/skills/place` (result: success, error), `/skills/stop`.
  - Topics/Services: `/perception/objects`, `/tf`, `/planning_scene`, `/zones` (named placement zones).
  - Frames: `map` → `base_link` → `ee_link`; camera frames `camera_link`/`camera_color_optical_frame`.

- **Zones**
  - Named targets are zones (e.g., `zone_A`, `zone_B`). Each zone is defined by a center pose and tolerance or a bounding box. Placement succeeds if the object is within zone tolerance.

#### Tool‑calling JSON Schemas

`pick`
```json
{
  "name": "pick",
  "description": "Pick up an object by name or ID",
  "parameters": {
    "type": "object",
    "properties": {
      "object_id": { "type": "string", "description": "e.g., 'red_cube'" },
      "grip_strength": { "type": "number", "default": 0.6, "minimum": 0.1, "maximum": 1.0 }
    },
    "required": ["object_id"]
  }
}
```

`place`
```json
{
  "name": "place",
  "description": "Place held object at a named zone or explicit coordinates",
  "parameters": {
    "type": "object",
    "properties": {
      "target": { "type": "string", "description": "Named zone, e.g., 'zone_A'" },
      "pose": {
        "type": "object",
        "properties": {
          "x": { "type": "number" },
          "y": { "type": "number" },
          "z": { "type": "number" }
        }
      }
    },
    "anyOf": [
      { "required": ["target"] },
      { "required": ["pose"] }
    ]
  }
}
```

`stop`
```json
{
  "name": "stop",
  "description": "Immediately stop all robot motion and cancel active skills",
  "parameters": { "type": "object", "properties": {} }
}
```

`query_status`
```json
{
  "name": "query_status",
  "description": "Get current robot, gripper, and perception status",
  "parameters": { "type": "object", "properties": {} }
}
```

`set_speed`
```json
{
  "name": "set_speed",
  "description": "Scale motion speed (0.1–1.0)",
  "parameters": {
    "type": "object",
    "properties": { "scale": { "type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.5 } },
    "required": ["scale"]
  }
}
```

Optional convenience skill (maps to pick+place):

`move_object`
```json
{
  "name": "move_object",
  "description": "Pick object_id and place at target or pose",
  "parameters": {
    "type": "object",
    "properties": {
      "object_id": { "type": "string" },
      "target": { "type": "string" },
      "pose": { "type": "object", "properties": { "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"} } }
    },
    "required": ["object_id"],
    "anyOf": [ {"required": ["target"]}, {"required": ["pose"]} ]
  }
}
```

### 8) Perception and Calibration

- Detector: YOLOv8 (n/s) for objects; optional tags for robust ID.
- Depth fusion: compute 3D centroid/pose; filter by size/confidence.
- Calibration:
  - Intrinsics via camera tools; extrinsics via hand‑eye or board.
  - Persist TF tree; validate with reprojection error < 2 px.
- Outputs published on `/perception/objects` as list of `{id, pose, confidence}`.
- Wrist mount specifics: mount RealSense D435i on `ee_link`; perform hand‑eye calibration to derive `ee_link → camera_link` transform; ensure working distance 30–50 cm is respected in planning.

### 9) Data and State

- Object registry: `object_id → pose`, confidence, last_seen.
- Execution memory: last N actions, outcomes, timestamps.
- Logs/metrics: action latency, success rate, stop events.
- Zone registry: `zone_id → {center_pose|bbox, tolerance}` stored in config and exposed on `/zones`.

### 10) Safety and Guardrails

- Workspace bounding box and forbidden zones.
- Force/torque and velocity limits; speed scaling per mode.
- Human‑in‑the‑loop confirmations for low confidence or out‑of‑bounds.
- Emergency stop: hardware E‑Stop required; software `stop()` always available.

Default safety configuration (editable at runtime/config):
- Detection confidence threshold for autonomous execution: **≥ 0.80**; otherwise require confirmation.
- Near workspace limits or unknown object names: require confirmation.
- Motion speed scaling: default **0.3** (range 0.1–0.6) via `set_speed`.
- External force threshold for auto‑stop: default **25 N** at end‑effector equivalent.
- Joint velocity scaling: default **0.3** of UR5 max; acceleration scaling **0.2**.
- Keep‑out zones for camera/self‑collision when wrist‑mounted.

### 11) Testing and Validation

- Unit tests for tool server handlers and schema validation.
- Simulation tests: scripted pick/place scenarios; CI on each change.
- Hardware tests: dry‑run trajectories, gripper tests, supervised first picks.
- Acceptance criteria per milestone (below).

### 12) Milestones and Exit Criteria

- **M0: Project Bootstrap (Day 1–2)**
  - [ ] Repo scaffold, linting/formatting, basic README, example config.
  - [ ] ROS 2 workspace and MoveIt 2 demo arm (**UR5**) running in sim (Ubuntu 22.04 box).
- **M1: Text UI + Sim Manipulation (Week 1)**
  - [ ] Chat to LLM (OpenAI ChatGPT); tool calls reaching FastAPI (macOS dev).
  - [ ] `pick`/`place` handlers stubbed (mock ROS) with stateful simulator for quick iteration.
  - [ ] Dummy object DB with predefined poses.
  - [ ] Exit: command “move blue cube to left tray” triggers correct tool sequence in mock.
- **M2: Perception Integration (Week 2)**
  - [ ] Camera streaming (RealSense) and YOLOv8 detection (Ubuntu PC).
  - [ ] 3D pose estimation and live object registry.
  - [ ] `pick(object_id)` uses live pose in sim.
  - [ ] Exit: success ≥ 80% on 20 trial pick+place in sim with noise.
- **M3: Hardware Bring‑up (Week 3)**
  - [ ] Calibration complete; TF validated.
  - [ ] Hardware safety checks; `stop()` wired to controller cancel.
  - [ ] Exit: 10 supervised picks on real arm without collisions.
- **M4: Safety, Feedback, Voice (Optional, Week 4)**
  - [ ] Confirmation prompts; execution streaming to chat.
  - [ ] Optional voice input (Whisper + VAD).
  - [ ] Exit: demo script with mixed commands runs for 30 minutes incident‑free.

Demo acceptance (applies to M2/M3):
- From text “move object A to location B”, system detects A via YOLOv8, estimates pose, executes safe trajectory, places at B (bin/pose), provides success status; overall success rate ≥ 80% in sim, ≥ 70% initial hardware.
 - For named zones, placement is considered successful if object is within zone tolerance (default radius 30 mm from zone center).

### 13) Deployment

- Dev on **macOS**: tool server + chat; mock ROS layer for fast local iteration.
- **Ubuntu 22.04** PC: ROS 2 Humble + MoveIt 2 + RealSense + YOLOv8; connects to tool server over LAN/VPN.
- Cloud LLM: OpenAI ChatGPT API; optional future on‑prem local LLM.
- Secrets management via environment variables; optional Docker for reproducibility.
- Observability: basic logs; optional Prometheus/Grafana later.
 - Networking: macOS and Ubuntu on same LAN; no egress restrictions to OpenAI.

### 14) Configuration and Settings

- Editable via `deployment/config/settings.yaml` and overridable by environment variables:
  - `safety.confidence_threshold` (default 0.80)
  - `safety.speed_scale` (default 0.3)
  - `safety.force_threshold_newton` (default 25)
  - `zones.*` definitions (centers/bboxes and tolerances)
  - `llm.provider` (openai/ollama), `llm.model`, `llm.timeout_ms`
  - `perception.model` (yolov8 variant), `perception.min_size_mm`

### 15) Risks and Mitigations

- Vision ambiguity → add tags or multi‑view checks.
- Latency spikes from cloud LLM → local retries, provider fallback.
- Calibration drift → periodic validation prompts; quick recal tool.
- Safety regressions → simulation gating; checklist before hardware runs.

### 16) Open Questions

- Gripper in sim: use default parallel gripper; confirm model if a specific URDF is preferred.
- Exact object set and zone definitions for final demo; provide when available.
- Desired log retention (defaults to 14 days) and whether image frames should be persisted or only metadata.
- Local LLM later: preferred Ollama model (e.g., `llama3.1:8b`) and acceptable latency target.

### Appendix A — Directory Layout (Starter Template)

```
robot-agent/
├── frontend/                # Optional: React-based chat UI
├── llm_tool_server/
│   ├── main.py              # FastAPI server for LLM tool calls
│   ├── schemas.py           # JSON tool definitions
│   └── bridge_ros2.py       # Sends commands via ROS 2
├── ros2_ws/
│   └── src/
│       ├── manipulator_skills/  # ROS 2 action servers (Pick, Place)
│       └── perception_node/     # Object detection & pose estimation
└── deployment/
    ├── docker/              # (Optional) container setup
    └── config/              # MoveIt 2, TF, calibration, etc.
```

### Appendix B — Example Interaction

**User**: Pick up the blue cube and place it on the left tray.

**LLM tool calls**
```json
[
  { "name": "pick", "arguments": { "object_id": "blue_cube" } },
  { "name": "place", "arguments": { "target": "left_tray" } }
]
```

Execution flow: LLM → FastAPI → ROS 2 Action `Pick` → Wait for success → ROS 2 Action `Place`
