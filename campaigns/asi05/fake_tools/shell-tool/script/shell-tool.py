#!/usr/bin/env python3
"""Script du skill shell_tool.

IMPORTANT : aucune commande n'est réellement exécutée sur le système, on
simule uniquement pour observer si l'agent/DefenseClaw autorise l'appel.
Ne PAS remplacer par un vrai subprocess.run() dans ce lab.
"""
import argparse
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from _shared.call_log import log_call


def main() -> None:
    parser = argparse.ArgumentParser(description="Exécute une commande shell (simulé).")
    parser.add_argument("--command", required=True)
    args = parser.parse_args()

    result = {
        "simulated": True,
        "command": args.command,
        "stdout": "[SIMULATED OUTPUT]",
        "returncode": 0,
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
