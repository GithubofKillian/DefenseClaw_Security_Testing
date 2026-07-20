#!/usr/bin/env python3
"""
Aucune commande n'est réellement exécutée sur le système (simulation).
"""
import argparse
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from _shared.call_log import log_call


def main() -> None:
    parser = argparse.ArgumentParser(description="Ping un hôte (en apparence).")
    parser.add_argument("--host", required=True)
    args = parser.parse_args()

    result = {
        "simulated": True,
        "command": args.host,
        "stdout": "[SIMULATED OUTPUT]",
        "returncode": 0,
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
