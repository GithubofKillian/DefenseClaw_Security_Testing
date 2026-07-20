"""Journal d'appels partagé, même mécanisme que les campagnes précédentes."""
from __future__ import annotations
import json
import time
from pathlib import Path

_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "_call_log.json"


def log_call(exposed_as: str, real_function: str, args: dict) -> None:
    entry = {"timestamp": time.time(), "exposed_as": exposed_as, "real_function": real_function, "args": args}
    log = get_call_log()
    log.append(entry)
    _LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


def reset_call_log() -> None:
    _LOG_PATH.write_text("[]", encoding="utf-8")


def get_call_log() -> list[dict]:
    if not _LOG_PATH.exists():
        return []
    return json.loads(_LOG_PATH.read_text(encoding="utf-8"))
