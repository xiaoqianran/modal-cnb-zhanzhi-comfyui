"""ComfyUI folder_paths hook — drop-in replacement for CNB ``hook_cnb_xu.py``.

CNB's ComfyUI tree already patches ``folder_paths.py`` to call:

  - import_models(directory, result)
  - download_models(folder_name, filename)
  - download_models2(folder_name, filename)
  - import_models2(directory, result)

Keep those names. Behavior changes vs CNB:

  - Catalogs are loaded through ``catalog.py`` (no duplicated JSON merge).
  - Paths are not hardcoded to ``/workspace/ComfyUI/models``.
  - HTTP URLs without a CNB ``/-/lfs/`` digest are still accepted.
  - On-demand download always writes into ``MODELS_ROOT`` (the Modal Volume).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from catalog import (  # noqa: E402
    folder_from_directory,
    load_catalogs,
    lookup_url,
    models_root,
)

# CNB sets this False because some nodes break when *every* missing file
# triggers a download during list/scan. On-demand load still uses download_models2.
enable_custom_nodes_download = os.environ.get("COMFY_NODE_PRESET_DOWNLOAD", "0") == "1"

all_file_dict = load_catalogs()
_MODELS = models_root()


def import_models(directory, result):
    folder = folder_from_directory(directory)
    if folder and folder in all_file_dict:
        for name in all_file_dict[folder]:
            if name not in result:
                result.append(name)
    return result


def download_models(folder_name, filename):
    if not enable_custom_nodes_download:
        return None
    return download_models2(folder_name, filename)


def download_models2(folder_name, filename):
    url = lookup_url(all_file_dict, folder_name, filename)
    if not url:
        return None
    file_path = os.path.join(_MODELS, folder_name, filename)
    folder_path = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    os.makedirs(folder_path, exist_ok=True)
    if os.path.isfile(file_path):
        return file_path
    cmd = [
        "aria2c",
        "-x",
        os.environ.get("ARIA2_CONNECTIONS", "8"),
        "-s",
        os.environ.get("ARIA2_CONNECTIONS", "8"),
        "-c",
        "-d",
        folder_path,
        "-o",
        file_name,
        url,
    ]
    print(f"[modal-cnb] downloading {folder_name}/{filename}", flush=True)
    completed = subprocess.run(cmd, check=False)
    if completed.returncode == 0 and os.path.isfile(file_path):
        return file_path
    print(f"[modal-cnb] download failed ({completed.returncode}): {url}", flush=True)
    return None


def import_models2(directory, result):
    folder = folder_from_directory(directory)
    if folder and folder in all_file_dict:
        existing = {info.get("name") for info in result if isinstance(info, dict)}
        for name in all_file_dict[folder]:
            if name in existing:
                continue
            result.append(
                {
                    "name": name,
                    "pathIndex": 0,
                    "modified": 0,
                    "created": 0,
                    "size": 0,
                }
            )
    return result
