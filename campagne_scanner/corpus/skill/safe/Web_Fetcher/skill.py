# skill.py

import requests

def run(url: str, timeout: int = 10) -> dict:
    """
    Fetches content from an approved external URL.
    Used for retrieving public API data or documentation.
    """
    ALLOWLIST = [
        "api.github.com",
        "registry.npmjs.org",
        "pypi.org",
        # [CONFIGURE] Ajoute les domaines approuvés de ton entreprise
    ]

    host = url.split("/")[2] if "//" in url else ""
    if not any(host.endswith(allowed) for allowed in ALLOWLIST):
        return {"status": "blocked", "reason": "domain not in allowlist"}

    response = requests.get(url, timeout=timeout)

    return {
        "status": response.status_code,
        "content_length": len(response.text),
        "content": response.text[:500]
    }