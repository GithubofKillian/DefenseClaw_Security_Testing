#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path.cwd()
    campaign_name = sys.argv[1] if len(sys.argv) > 1 else "asi01"
    runner = repo_root / "campaigns" / campaign_name / "run.py"

    if not runner.exists():
        print(f"Unknown campaign: {campaign_name}", file=sys.stderr)
        return 1

    result = subprocess.run([sys.executable, str(runner)], cwd=repo_root)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
