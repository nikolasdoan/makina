from typing import Dict, Any, List


def get_tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "name": "pick",
            "description": "Pick up an object by name or ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_id": {
                        "type": "string",
                        "description": "e.g., 'red_cube'",
                    },
                    "grip_strength": {
                        "type": "number",
                        "default": 0.6,
                        "minimum": 0.1,
                        "maximum": 1.0,
                    },
                },
                "required": ["object_id"],
            },
        },
        {
            "name": "place",
            "description": "Place held object at a zone (numeric ID or name) or explicit coordinates",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Zone reference, e.g., '1' or 'zone_1'",
                    },
                    "pose": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "z": {"type": "number"},
                        },
                    },
                },
            },
        },
        {
            "name": "stop",
            "description": "Immediately stop all robot motion and cancel active skills",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "query_status",
            "description": "Get current robot, gripper, and perception status",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "set_speed",
            "description": "Scale motion speed (0.1–1.0)",
            "parameters": {
                "type": "object",
                "properties": {
                    "scale": {
                        "type": "number",
                        "minimum": 0.1,
                        "maximum": 1.0,
                        "default": 0.5,
                    }
                },
                "required": ["scale"],
            },
        },
        {
            "name": "move_object",
            "description": "Pick object_id and place at target or pose",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_id": {"type": "string"},
                    "target": {"type": "string", "description": "Zone reference like '1' or '2'"},
                    "pose": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "z": {"type": "number"},
                        },
                    },
                },
                "required": ["object_id"],
            },
        },
        {
            "name": "get_config",
            "description": "Get zones (numeric IDs), objects, and workspace bounds",
            "parameters": {"type": "object", "properties": {}},
        },
    ]
