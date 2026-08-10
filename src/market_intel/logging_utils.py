from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .config import get_settings


def configure_logging() -> None:
    root = get_settings().path("logs_root")
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler()],
        force=True,
    )


def to_json_safe(value: Any) -> Any:
    """Recursively convert runtime objects into JSON-safe values.

    This directly fixes Streamlit/json.dumps failures such as:
    TypeError: Object of type bytes is not JSON serializable.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "size": len(value),
            "base64": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return to_json_safe(value.model_dump())
    if is_dataclass(value):
        return to_json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


class RunLogger:
    def __init__(self, source_text: str, source_name: str, query: str) -> None:
        settings = get_settings()
        cfg = settings.section("logging")
        root = settings.path("logs_root")
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime(cfg["timestamp_format"])
        self.run_dir = root / f'{cfg["folder_prefix"]}{stamp}'
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.log_path = self.run_dir / "run.log"
        self._logger = logging.getLogger(f"market_intel.run.{stamp}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        handler = logging.FileHandler(self.log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        self._logger.handlers = [handler]

        source_hash = hashlib.sha256(source_text.encode("utf-8", errors="replace")).hexdigest()
        request_payload = {
            "timestamp": datetime.now().isoformat(),
            "source_name": source_name,
            "source_sha256": source_hash,
            "query": query,
        }
        if bool(cfg["store_source_text"]):
            request_payload["source_text"] = source_text
        else:
            request_payload["source_excerpt"] = source_text[: int(cfg["source_excerpt_characters"])]
        self.write_json("request.json", request_payload)
        self.info("Run started")

    def info(self, message: str) -> None:
        self._logger.info(message)

    def exception(self, message: str) -> None:
        self._logger.exception(message)

    def write_json(self, filename: str, payload: Any) -> None:
        path = self.run_dir / filename
        path.write_text(json.dumps(to_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    def finish(self, result: dict) -> None:
        self.write_json("response.json", result)
        if "evaluation" in result:
            self.write_json("evaluation.json", result["evaluation"])
        self.info("Run completed")
