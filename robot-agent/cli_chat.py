from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import httpx
from dotenv import load_dotenv


@dataclass
class ClientConfig:
    server_url: str


def run_ascii_map() -> str:
    base_dir = Path(__file__).resolve().parents[0]
    try:
        proc = subprocess.run(
            [sys.executable, str(base_dir / "tools" / "term_map.py")],
            capture_output=True,
            text=True,
            cwd=base_dir,
            timeout=10,
        )
        if proc.returncode == 0:
            return proc.stdout
        return f"[map error] {proc.stderr.strip()}"
    except Exception as exc:  # noqa: BLE001
        return f"[map error] {exc}"


def naive_parse_and_call(text: str, cfg: ClientConfig) -> Dict[str, Any]:
    text = text.strip().lower()
    if text.startswith(":showcfg"):
        return http_get("/config", cfg)
    if text.startswith(":make map") or text.startswith(":map"):
        # Returned as structured object; caller may print raw map separately
        return {"ok": True, "map": run_ascii_map()}
    m = re.match(r":setobj\s+(\w+)\s+([\-0-9\.]+)\s+([\-0-9\.]+)\s+([\-0-9\.]+)", text)
    if m:
        oid, x, y, z = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))
        return http_post(
            "/config/object",
            {"id": oid, "pose": {"x": x, "y": y, "z": z}},
            cfg,
        )
    m = re.match(r":setzone\s+(\w+)\s+([\-0-9\.]+)\s+([\-0-9\.]+)\s+([\-0-9\.]+)(?:\s+([\-0-9\.]+))?", text)
    if m:
        zid, x, y, z = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))
        tol = float(m.group(5)) if m.group(5) else 0.03
        return http_post(
            "/config/zone",
            {"id": zid, "center_pose": {"x": x, "y": y, "z": z}, "tolerance_m": tol},
            cfg,
        )
    m = re.match(r"move\s+([a-z0-9_\- ]+)\s+to\s+([a-z0-9_\-]+)", text)
    if m:
        object_id = m.group(1).replace(" ", "_")
        target = m.group(2)
        return call_tool("move_object", {"object_id": object_id, "target": target}, cfg)
    if text.startswith("status"):
        return call_tool("query_status", {}, cfg)
    return {"ok": False, "error": "unrecognized_command"}


def http_post(path: str, payload: Dict[str, Any], cfg: ClientConfig) -> Dict[str, Any]:
    with httpx.Client(timeout=20.0) as client:
        r = client.post(f"{cfg.server_url}{path}", json=payload)
        r.raise_for_status()
        return r.json()


def http_get(path: str, cfg: ClientConfig) -> Dict[str, Any]:
    with httpx.Client(timeout=20.0) as client:
        r = client.get(f"{cfg.server_url}{path}")
        r.raise_for_status()
        return r.json()


def call_tool(name: str, arguments: Dict[str, Any], cfg: ClientConfig) -> Dict[str, Any]:
    with httpx.Client(timeout=20.0) as client:
        r = client.post(
            f"{cfg.server_url}/tool-call",
            json={"name": name, "arguments": arguments},
        )
        r.raise_for_status()
        return r.json()


def chat_loop(cfg: ClientConfig) -> None:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    use_openai = bool(api_key)

    print("Robot Agent CLI — type 'exit' to quit.")
    print("Using OpenAI:" if use_openai else "Using naive parser mode (no OPENAI_API_KEY)")
    print("Commands: :setobj ID X Y Z | :setzone ID X Y Z [tol] | :showcfg | :map | :make map | move OBJECT to ZONE | status")

    if use_openai:
        from openai import OpenAI
        from llm_tool_server.schemas import get_tool_schemas

        client = OpenAI(api_key=api_key)
        tools = [
            {"type": "function", "function": schema} for schema in get_tool_schemas()
        ]
        system_prompt = (
            "You are a robotics assistant. Use tools to execute user commands."
            " Ask for confirmation if confidence is low or targets are ambiguous."
        )

        history = [
            {"role": "system", "content": system_prompt},
        ]

        while True:
            try:
                user_input = input("» ").strip()
            except KeyboardInterrupt:
                print()
                break
            if user_input.lower() in {"exit", "quit"}:
                break
            # Colon-prefixed commands are handled locally
            if user_input.startswith(":"):
                # Render map directly to terminal for :map / :make map
                if user_input.startswith(":map") or user_input.startswith(":make map"):
                    print(run_ascii_map())
                    continue
                print(json.dumps(naive_parse_and_call(user_input, cfg), indent=2))
                continue

            history.append({"role": "user", "content": user_input})

            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=history,
                tools=tools,
                tool_choice="auto",
            )
            choice = response.choices[0]
            msg = choice.message

            if msg.tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "{}",
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                history.append(assistant_msg)

                for tc in msg.tool_calls:
                    fn = tc.function
                    name = fn.name
                    arguments = json.loads(fn.arguments or "{}")
                    result = call_tool(name, arguments, cfg)
                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": name,
                            "content": json.dumps(result),
                        }
                    )
                response = client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=history,
                    tools=tools,
                )
                final_text = response.choices[0].message.content or "(no content)"
                print(final_text)
                history.append({"role": "assistant", "content": final_text})
            else:
                final_text = msg.content or "(no content)"
                print(final_text)
                history.append({"role": "assistant", "content": final_text})
    else:
        while True:
            try:
                user_input = input("» ").strip()
            except KeyboardInterrupt:
                print()
                break
            if user_input.lower() in {"exit", "quit"}:
                break
            if user_input.startswith(":map") or user_input.startswith(":make map"):
                print(run_ascii_map())
                continue
            print(json.dumps(naive_parse_and_call(user_input, cfg), indent=2))


if __name__ == "__main__":
    cfg = ClientConfig(server_url=os.getenv("TOOL_SERVER_URL", "http://127.0.0.1:8000"))
    chat_loop(cfg)
