from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ZoneDefinition:
    center_pose: Dict[str, float]
    tolerance_m: float


class MockBridge:
    """
    Mock ROS bridge used on macOS for development without ROS 2.
    Simulates stateful pick/place/stop interactions with simple validation.
    """

    def __init__(self, zones: Dict[str, ZoneDefinition], speed_scale: float = 0.3) -> None:
        self.held_object: Optional[str] = None
        self.speed_scale: float = speed_scale
        self.zones: Dict[str, ZoneDefinition] = zones
        self.last_action: str = "idle"
        self.stopped: bool = False

    def set_speed(self, scale: float) -> Dict[str, Any]:
        if not 0.1 <= scale <= 1.0:
            return {"ok": False, "error": "scale_out_of_range"}
        self.speed_scale = scale
        self.last_action = f"set_speed:{scale:.2f}"
        return {"ok": True}

    def stop(self) -> Dict[str, Any]:
        self.stopped = True
        self.last_action = "stop"
        self.held_object = None
        return {"ok": True}

    def pick(self, object_id: str, grip_strength: float = 0.6) -> Dict[str, Any]:
        if self.stopped:
            return {"ok": False, "error": "stopped"}
        # Simulate travel + grasp
        time.sleep(max(0.05, 0.25 * (1.0 - self.speed_scale)))
        self.held_object = object_id
        self.last_action = f"pick:{object_id}"
        return {"ok": True}

    def place(self, target: Optional[str] = None, pose: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        if self.stopped:
            return {"ok": False, "error": "stopped"}
        if self.held_object is None:
            return {"ok": False, "error": "no_object_held"}
        if target is None and pose is None:
            return {"ok": False, "error": "target_or_pose_required"}
        if target is not None:
            if target not in self.zones:
                return {"ok": False, "error": "unknown_zone"}
        # Simulate travel + release
        time.sleep(max(0.05, 0.25 * (1.0 - self.speed_scale)))
        placed_object = self.held_object
        self.held_object = None
        self.last_action = f"place:{target or 'pose'}"
        return {"ok": True, "placed_object": placed_object, "target": target, "pose": pose}

    def query_status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "held_object": self.held_object,
            "speed_scale": self.speed_scale,
            "stopped": self.stopped,
            "last_action": self.last_action,
        }
