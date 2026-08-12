from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from apply_hook import install_hook_files, replace_once  # noqa: E402


def test_replace_once_is_idempotent(tmp_path):
    path = tmp_path / "folder_paths.py"
    path.write_text("import os\nimport time\n", encoding="utf-8")
    assert replace_once(path, "import os\nimport time", "import os\nimport hook_cnb_xu\nimport time") == "patched"
    assert "hook_cnb_xu" in path.read_text(encoding="utf-8")
    assert replace_once(path, "import os\nimport time", "import os\nimport hook_cnb_xu\nimport time") == "present"


def test_install_hook_files(tmp_path):
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    install_hook_files(comfy)
    assert (comfy / "hook_cnb_xu.py").is_file()
    assert (comfy / "catalog.py").is_file()
