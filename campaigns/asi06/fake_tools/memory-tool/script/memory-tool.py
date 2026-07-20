#!/usr/bin/env python3
"""Script du skill memory_tool - lit/écrit dans memory/memory.json (simulé,
fichier local réel dans ce lab, pas de vraie base de données)."""
import argparse
import json
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from _shared.call_log import log_call

# fake_tools/memory-tool/script/memory-tool.py -> fake_tools/ -> asi06/ -> memory/memory.json
_MEMORY_PATH = pathlib.Path(__file__).resolve().parents[3] / "memory" / "memory.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Lit/écrit la mémoire de l'agent (simulé).")
    parser.add_argument("--action", required=True, choices=["read", "write"])
    parser.add_argument("--content", help="Contenu à écrire (requis si --action write).")
    parser.add_argument("--source", default="conversation", help="Origine du fait mémorisé.")
    args = parser.parse_args()

    memory = json.loads(_MEMORY_PATH.read_text(encoding="utf-8")) if _MEMORY_PATH.exists() else {"facts": []}

    if args.action == "read":
        print(json.dumps(memory))
        return

    # --action write
    if not args.content:
        parser.error("--content est requis pour --action write")

    entry = {"content": args.content, "source": args.source, "timestamp": time.time()}
    memory.setdefault("facts", []).append(entry)
    _MEMORY_PATH.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"written": True, "content": args.content}))


if __name__ == "__main__":
    main()
