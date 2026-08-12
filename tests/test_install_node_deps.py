from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from install_node_deps import pip_cmd  # noqa: E402


def test_pip_cmd_prefers_uv(monkeypatch):
    monkeypatch.setattr("install_node_deps.shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    assert pip_cmd() == ["uv", "pip", "install", "--system"]


def test_pip_cmd_falls_back_to_pip(monkeypatch):
    monkeypatch.setattr("install_node_deps.shutil.which", lambda name: None)
    cmd = pip_cmd()
    assert cmd[-1] == "install"
    assert "pip" in cmd
