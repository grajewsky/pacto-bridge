#!/usr/bin/env python3
"""Compatibility entry point: passive FFF0 vendor notification capture."""
import asyncio
from pactobridge.app import capture
from pactobridge.cli import capture_path, show

if __name__ == "__main__":
    path = capture_path()
    print(f"Passive capture: {path}. Ctrl+C to stop. No treadmill control commands.")
    try:
        asyncio.run(capture(path, show))
    except KeyboardInterrupt:
        pass
