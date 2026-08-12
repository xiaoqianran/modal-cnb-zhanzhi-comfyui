from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLONE = ROOT / "scripts" / "clone_cnb.sh"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote"
    remote.mkdir()
    _git(remote, "init", "--quiet")
    _git(remote, "config", "user.email", "t@t")
    _git(remote, "config", "user.name", "t")
    (remote / "ComfyUI" / ".git_backup").mkdir(parents=True)
    (remote / "ComfyUI" / "main.py").write_text("print('comfy')\n", encoding="utf-8")
    (remote / "ComfyUI" / ".git_backup" / "x").write_text("backup\n", encoding="utf-8")
    (remote / "custom_nodes" / "NodeA").mkdir(parents=True)
    (remote / "custom_nodes" / "NodeB").mkdir(parents=True)
    (remote / "custom_nodes" / "NodeA" / "__init__.py").write_text("a\n", encoding="utf-8")
    (remote / "custom_nodes" / "NodeB" / "__init__.py").write_text("b\n", encoding="utf-8")
    (remote / "工作流").mkdir()
    (remote / "工作流" / "a.json").write_text("{}\n", encoding="utf-8")
    (remote / "assets" / "tools" / "cache").mkdir(parents=True)
    (remote / "assets" / "x.txt").write_text("asset\n", encoding="utf-8")
    (remote / "assets" / "tools" / "cache" / "big").write_text("cache\n", encoding="utf-8")
    (remote / "venv312" / "lib").mkdir(parents=True)
    (remote / "venv312" / "lib" / "foo").write_text("venv\n", encoding="utf-8")
    (remote / "models").mkdir()
    (remote / "models" / "ckpt.safetensors").write_text("ckpt\n", encoding="utf-8")
    (remote / "输入").mkdir()
    (remote / "输入" / "a.png").write_text("in\n", encoding="utf-8")
    (remote / "初始化下载").write_text("#!/bin/bash\n", encoding="utf-8")
    (remote / "README.md").write_text("readme\n", encoding="utf-8")
    (remote / ".cnb.yml").write_text("cnb\n", encoding="utf-8")
    _git(remote, "add", "-A")
    _git(remote, "commit", "--quiet", "-m", "init")
    _git(remote, "branch", "-M", "main")
    return remote


def run_clone(remote: Path, dest: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(
        {
            "CNB_REPO_URL": str(remote),
            "CNB_REPO_REF": "main",
            "CNB_CLONE_RETRIES": "2",
            "CNB_CLONE_RETRY_WAIT": "1",
        }
    )
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(CLONE), str(dest)],
        check=True,
        text=True,
        capture_output=True,
        env=merged,
    )


def test_shallow_clone_skips_heavy_trees_and_keeps_nodes(tmp_path):
    remote = make_remote(tmp_path)
    dest = tmp_path / "dest"
    result = run_clone(remote, dest)
    assert "sparse-add custom_nodes/NodeA" in result.stdout
    assert "sparse-add 工作流" in result.stdout
    assert (dest / "ComfyUI" / "main.py").is_file()
    assert (dest / "custom_nodes" / "NodeA" / "__init__.py").is_file()
    assert (dest / "custom_nodes" / "NodeB" / "__init__.py").is_file()
    assert (dest / "工作流" / "a.json").is_file()
    assert (dest / "初始化下载").is_file()
    assert (dest / "assets" / "x.txt").is_file()
    assert not (dest / "venv312").exists()
    assert not (dest / "models").exists()
    assert not (dest / "输入").exists()
    assert not (dest / "ComfyUI" / ".git_backup").exists()
    assert not (dest / "assets" / "tools" / "cache").exists()


def test_clone_update_is_idempotent(tmp_path):
    remote = make_remote(tmp_path)
    dest = tmp_path / "dest"
    run_clone(remote, dest)
    (remote / "custom_nodes" / "NodeC").mkdir()
    (remote / "custom_nodes" / "NodeC" / "__init__.py").write_text("c\n", encoding="utf-8")
    _git(remote, "add", "-A")
    _git(remote, "commit", "--quiet", "-m", "add-node")
    result = run_clone(remote, dest)
    assert "updating existing checkout" in result.stdout
    assert (dest / "custom_nodes" / "NodeC" / "__init__.py").is_file()
    assert (dest / "ComfyUI" / "main.py").is_file()
