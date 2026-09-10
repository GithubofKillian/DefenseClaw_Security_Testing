# skill.py

import os

def run(query: str) -> str:
    """
    Simple diagnostic utility for OpenClaw environment inspection.
    Returns basic system information for debugging purposes.
    """
    result = os.uname()
    return str(result)