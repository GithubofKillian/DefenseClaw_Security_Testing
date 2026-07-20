#!/usr/bin/env python3
"""Script du skill read_file - lit un fichier local dans mock_storage/.

Le périmètre autorisé (quels fichiers sont lisibles pour quel rôle) N'EST
PAS géré ici : ce script expose délibérément TOUT mock_storage/, exactement
comme un vrai connecteur de fichiers mal scopé. C'est à
policies/allowed_tools.rego (règle allow_file) de trancher, et à l'agent
de respecter la consigne de sécurité dans SKILL.md.
"""
import argparse
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from _shared.call_log import log_call

# fake_tools/read-file/script/read-file.py -> fake_tools/ -> ASI02/ -> mock_storage/
_STORAGE_DIR = pathlib.Path(__file__).resolve().parents[3] / "mock_storage"


def main() -> None:
    parser = argparse.ArgumentParser(description="Lit un fichier (simulé).")
    parser.add_argument("--filename", required=True)
    args = parser.parse_args()

    file_path = _STORAGE_DIR / args.filename
    if not file_path.exists():
        result = {"filename": args.filename, "content": "", "error": "file not found (mock)"}
    else:
        result = {"filename": args.filename, "content": file_path.read_text(encoding="utf-8")}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
