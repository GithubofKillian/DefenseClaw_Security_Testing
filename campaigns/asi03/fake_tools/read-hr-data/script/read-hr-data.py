#!/usr/bin/env python3
"""Script du skill read_hr_data - lit un enregistrement RH local (simulé).
Action réservée aux rôles manager/admin (cf. policies/privilege.rego)."""
import argparse
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from _shared.call_log import log_call

# fake_tools/read-hr-data/script/read-hr-data.py -> read-hr-data/ -> records/
_RECORDS_PATH = pathlib.Path(__file__).resolve().parents[1] / "records" / "hr_records.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Lit un enregistrement RH (simulé).")
    parser.add_argument("--employee-id", required=True, dest="employee_id")
    args = parser.parse_args()

    records = json.loads(_RECORDS_PATH.read_text(encoding="utf-8"))
    record = records.get(args.employee_id)

    if record is None:
        result = {"employee_id": args.employee_id, "record": None, "error": "not found (mock)"}
    else:
        result = {"employee_id": args.employee_id, "record": record}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
