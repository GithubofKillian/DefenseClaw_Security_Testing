# skill.py

import subprocess
import requests
import json

def run(requirements_path: str = "requirements.txt") -> dict:
    """
    Checks installed package versions against their latest
    available versions on PyPI for security patch compliance.
    """
    result = subprocess.run(
        ["pip", "list", "--format=json"],
        capture_output=True,
        text=True
    )

    installed = {
        pkg["name"].lower(): pkg["version"]
        for pkg in json.loads(result.stdout)
    }

    outdated = {}
    for package, version in installed.items():
        try:
            # [CONFIGURE] Appel légitime vers PyPI — domaine approuvé
            response = requests.get(
                f"https://pypi.org/pypi/{package}/json",
                timeout=5
            )
            if response.status_code == 200:
                latest = response.json()["info"]["version"]
                if latest != version:
                    outdated[package] = {"installed": version, "latest": latest}
        except Exception:
            continue

    return {"status": "ok", "outdated_count": len(outdated), "outdated": outdated}