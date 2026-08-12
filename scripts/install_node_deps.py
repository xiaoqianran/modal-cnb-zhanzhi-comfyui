#!/usr/bin/env python3
"""Best-effort install of each custom node's requirements.txt.

Uses ``uv pip`` when Modal's image has uv (Image.uv_pip_install), otherwise pip.
Conflicts must not fail the image build — that is the CNB workspace model
(broken nodes stay broken, the rest still boot).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def pip_cmd() -> list[str]:
    if shutil.which("uv"):
        return ["uv", "pip", "install", "--system"]
    return [sys.executable, "-m", "pip", "install"]


def configure_github_https() -> None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return
    subprocess.run(
        [
            "git",
            "config",
            "--global",
            f"url.https://x-access-token:{token}@github.com/.insteadOf",
            "https://github.com/",
        ],
        check=False,
    )


def main() -> int:
    configure_github_https()
    root = Path(os.environ.get("ZHANZHI_ROOT", "/opt/zhanzhi")) / "custom_nodes"
    if not root.is_dir():
        print(f"[deps] no custom_nodes at {root}")
        return 0
    cmd = pip_cmd()
    print(f"[deps] installer: {' '.join(cmd)}", flush=True)
    failed: list[str] = []
    for req in sorted(root.glob("*/requirements.txt")):
        name = req.parent.name
        print(f"[deps] {name}", flush=True)
        completed = subprocess.run([*cmd, "-r", str(req)], check=False)
        if completed.returncode != 0:
            failed.append(name)
    if failed:
        print("[deps] failed (ignored):", ", ".join(failed), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
