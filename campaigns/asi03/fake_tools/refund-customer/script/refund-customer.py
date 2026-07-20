#!/usr/bin/env python3
"""Script du skill refund_customer - simule un remboursement (aucune transaction réelle).
Action réservée aux rôles manager/admin (cf. policies/privilege.rego)."""
import argparse
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from _shared.call_log import log_call


def main() -> None:
    parser = argparse.ArgumentParser(description="Rembourse un client (simulé).")
    parser.add_argument("--customer-id", required=True, dest="customer_id")
    parser.add_argument("--amount", required=True, type=float)
    args = parser.parse_args()

    result = {"refunded": True, "customer_id": args.customer_id, "amount": args.amount}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
