from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SANITIZE = ROOT / "scripts" / "sanitize_cnb_tree.sh"
PUBLISH = ROOT / "scripts" / "publish_cnb_mirror.sh"


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
        env=merged,
    )


def test_sanitize_drops_nested_git_and_oversized_files(tmp_path):
    dest = tmp_path / "tree"
    (dest / "ComfyUI").mkdir(parents=True)
    (dest / "ComfyUI" / "main.py").write_text("ok\n", encoding="utf-8")
    (dest / "custom_nodes" / "NodeA" / "git_backup" / "objects").mkdir(parents=True)
    (dest / "custom_nodes" / "NodeA" / "git_backup" / "objects" / "pack.bin").write_text("pack\n", encoding="utf-8")
    (dest / "custom_nodes" / "NodeA" / "__init__.py").write_text("a\n", encoding="utf-8")
    (dest / "venv312" / "lib").mkdir(parents=True)
    (dest / "venv312" / "lib" / "foo").write_text("venv\n", encoding="utf-8")
    big = dest / "custom_nodes" / "NodeA" / "weights.bin"
    big.write_bytes(b"\0")
    os.truncate(big, 91 * 1024 * 1024)
    subprocess.run(["bash", str(SANITIZE), str(dest)], check=True, capture_output=True)
    assert (dest / "ComfyUI" / "main.py").is_file()
    assert (dest / "custom_nodes" / "NodeA" / "__init__.py").is_file()
    assert not (dest / "custom_nodes" / "NodeA" / "git_backup").exists()
    assert not (dest / "venv312").exists()
    assert not big.exists()


def test_publish_commits_rsync_snapshot(tmp_path):
    src = tmp_path / "src"
    (src / "ComfyUI").mkdir(parents=True)
    (src / "ComfyUI" / "main.py").write_text("comfy\n", encoding="utf-8")
    (src / "custom_nodes" / "NodeA").mkdir(parents=True)
    (src / "custom_nodes" / "NodeA" / "__init__.py").write_text("a\n", encoding="utf-8")
    _git(src, "init", "--quiet")
    _git(src, "config", "user.email", "t@t")
    _git(src, "config", "user.name", "t")
    _git(src, "add", "-A")
    _git(src, "commit", "--quiet", "-m", "upstream")
    sha = _git(src, "rev-parse", "HEAD").stdout.strip()

    mirror = tmp_path / "mirror"
    result = subprocess.run(
        ["bash", str(PUBLISH), str(src), str(mirror)],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "MIRROR_PUSH": "0", "CNB_REPO_REF": "main"},
    )
    assert (mirror / "ComfyUI" / "main.py").is_file()
    assert (mirror / ".cnb-mirror-meta").read_text(encoding="utf-8").find(sha) >= 0
    assert "committed" in result.stdout
    log = _git(mirror, "log", "-1", "--oneline").stdout
    assert sha[:12] in log

    # Second publish with no file changes is a no-op.
    again = subprocess.run(
        ["bash", str(PUBLISH), str(src), str(mirror)],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "MIRROR_PUSH": "0"},
    )
    assert "no changes" in again.stdout
