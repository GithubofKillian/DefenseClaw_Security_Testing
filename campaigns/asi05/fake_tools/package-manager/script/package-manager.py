#!/usr/bin/env python3
"""Script du skill package_manager - simule l'installation d'un paquet
(aucune installation réelle)."""
import argparse
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from _shared.call_log import log_call


def main() -> None:
    parser = argparse.ArgumentParser(description="Installe un paquet (simulé).")
    parser.add_argument("--package", required=True)
    args = parser.parse_args()

    result = {"installed": True, "package": args.package}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
