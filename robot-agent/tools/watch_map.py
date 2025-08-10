from __future__ import annotations

import os
import sys
import time
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SETTINGS = BASE_DIR / "deployment" / "config" / "settings.yaml"
TERM_MAP = BASE_DIR / "tools" / "term_map.py"


def clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def render_map_once() -> str:
    try:
        proc = subprocess.run(
            [sys.executable, str(TERM_MAP)],
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
            timeout=10,
        )
        if proc.returncode == 0:
            return proc.stdout
        return f"[map error] {proc.stderr.strip()}\n"
    except Exception as exc:  # noqa: BLE001
        return f"[map error] {exc}\n"


def main() -> None:
    last_mtime = 0.0
    clear_screen()
    print("Watching settings.yaml for changes... (Ctrl+C to exit)\n")
    # Always print initial map
    print(render_map_once())
    try:
        while True:
            try:
                mtime = SETTINGS.stat().st_mtime
            except FileNotFoundError:
                mtime = 0.0
            if mtime != last_mtime:
                last_mtime = mtime
                clear_screen()
                print("Watching settings.yaml for changes... (Ctrl+C to exit)\n")
                print(render_map_once())
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
