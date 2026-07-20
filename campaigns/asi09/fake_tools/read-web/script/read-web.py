#!/usr/bin/env python3
"""Script du skill read_web - lit une page HTML locale dans malicious_pages/."""
import argparse
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from _shared.call_log import log_call

_PAGES_DIR = pathlib.Path(__file__).resolve().parents[3] / "malicious_pages"


def main() -> None:
    parser = argparse.ArgumentParser(description="Lit une page (simulé).")
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    filename = args.url.rstrip("/").split("/")[-1]
    page_path = _PAGES_DIR / filename
    if not page_path.exists():
        result = {"url": args.url, "content": "", "error": "page not found (mock)"}
    else:
        result = {"url": args.url, "content": page_path.read_text(encoding="utf-8")}

    log_call(exposed_as="read_web", real_function="read_web", args={"url": args.url})
    print(json.dumps(result))


if __name__ == "__main__":
    main()
