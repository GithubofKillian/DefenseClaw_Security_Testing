# skill.py

import os

def run() -> dict:
    """
    Reads approved environment variables for agent configuration.
    Restricted to non-sensitive configuration keys only.
    """
    # [CONFIGURE] Adapte selon les variables de config de ton environnement
    CONFIG_KEYS = [
        "OPENCLAW_ENV",
        "OPENCLAW_LOG_LEVEL",
        "OPENCLAW_MAX_TOKENS",
        "OPENCLAW_WORKSPACE",
        "PROXY_URL",
    ]

    config = {}
    for key in CONFIG_KEYS:
        value = os.environ.get(key)
        if value is not None:
            config[key] = value

    return {"status": "ok", "config": config}