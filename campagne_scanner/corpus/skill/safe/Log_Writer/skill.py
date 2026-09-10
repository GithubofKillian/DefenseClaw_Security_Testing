import os
from datetime import datetime

def run(message: str, level: str = "INFO", log_dir: str = "/var/log/openclaw") -> dict:
    ALLOWED_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]
    if level not in ALLOWED_LEVELS:
        return {"status": "error", "reason": "invalid log level"}

    BASE_DIR = os.path.abspath("/var/log/openclaw")

    requested_path = os.path.abspath(os.path.join(BASE_DIR, log_dir))

    if not requested_path.startswith(BASE_DIR + os.path.sep) and requested_path != BASE_DIR:
        return {"status": "error", "reason": "Access Denied: Path Traversal Detected"}

    log_path = os.path.join(requested_path, "agent.log")
    timestamp = datetime.utcnow().isoformat()
    entry = f"[{timestamp}] [{level}] {message}\n"

    with open(log_path, "a") as f:
        f.write(entry)

    return {"status": "ok", "entry": entry}