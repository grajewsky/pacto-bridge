import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        row = {"utc": datetime.now(timezone.utc).isoformat(), "level": record.levelname,
               "logger": record.name, "message": record.getMessage()}
        if hasattr(record, "event"):
            row["event"] = record.event
        if record.exc_info:
            row["exception"] = self.formatException(record.exc_info)
        return json.dumps(row)


def configure(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
