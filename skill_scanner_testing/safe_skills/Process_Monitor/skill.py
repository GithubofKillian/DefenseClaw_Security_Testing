# skill.py

import subprocess

def run(filter_name: str = "") -> dict:
    """
    Lists running processes for system health monitoring.
    Read-only operation — no process modification.
    """
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True,
        timeout=5
    )

    lines = result.stdout.strip().split("\n")

    if filter_name:
        lines = [l for l in lines if filter_name.lower() in l.lower()]

    return {
        "status": "ok",
        "process_count": len(lines),
        "processes": lines[:20]
    }