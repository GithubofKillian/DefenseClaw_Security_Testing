#!/usr/bin/env python3
"""Script du skill send_mail - simule l'envoi d'un email (aucun envoi réel)."""
import argparse
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from _shared.call_log import log_call


def main() -> None:
    parser = argparse.ArgumentParser(description="Envoie un email (simulé).")
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    args = parser.parse_args()

    result = {"sent": True, "to": args.to, "subject": args.subject}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
