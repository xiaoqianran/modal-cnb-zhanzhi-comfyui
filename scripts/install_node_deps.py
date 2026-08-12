#!/usr/bin/env python3
"""Best-effort pip install of each custom node's requirements.txt.

Conflicts must not fail the image build — that is the CNB workspace model
(broken nodes stay broken, the rest still boot).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(os.environ.get("ZHANZHI_ROOT", "/opt/zhanzhi")) / "custom_nodes"
    if not root.is_dir():
        print(f"[deps] no custom_nodes at {root}")
        return 0
    failed: list[str] = []
    for req in sorted(root.glob("*/requirements.txt")):
        name = req.parent.name
        print(f"[deps] {name}", flush=True)
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req)],
            check=False,
        )
        if completed.returncode != 0:
            failed.append(name)
    if failed:
        print("[deps] failed (ignored):", ", ".join(failed), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
