"""Versioned, line-flushed JSONL captures; replay never opens Bluetooth."""
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time


class Recorder:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Refuse to silently overwrite a previous hardware capture.
        self.file = path.open("x", encoding="utf-8")
        self.started = time.monotonic()

    def event(self, kind: str, **fields) -> dict:
        row = dict(fields, schema=1, kind=kind,
                   utc=datetime.now(timezone.utc).isoformat(),
                   elapsed_s=time.monotonic() - self.started)
        self.file.write(json.dumps(row, allow_nan=False) + "\n")
        self.file.flush()
        return row

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def read_events(path: Path):
    previous = 0.0
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
                elapsed = row["elapsed_s"]
                if (row["schema"] != 1 or not isinstance(row["kind"], str)
                        or isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
                        or not math.isfinite(elapsed) or elapsed < previous):
                    raise ValueError("invalid schema or timestamp")
                if row["kind"] == "notification":
                    bytes.fromhex(row["hex"])
                    if not isinstance(row["characteristic"], str):
                        raise ValueError("invalid characteristic")
                previous = elapsed
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"{path}:{line_no}: invalid capture: {exc}") from exc
            yield row


async def replay(path: Path, callback, rate: float = 1.0):
    if not math.isfinite(rate) or rate < 0:
        raise ValueError("Replay rate must be finite and >= 0 (0 means immediate)")
    first = None
    started = time.monotonic()
    for row in read_events(path):
        if first is None:
            first = row["elapsed_s"]
        if rate:
            delay = (row["elapsed_s"] - first) / rate - (time.monotonic() - started)
            if delay > 0:
                await asyncio.sleep(delay)
        callback(row)
