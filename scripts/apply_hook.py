#!/usr/bin/env python3
"""Install the on-demand download hook into a ComfyUI checkout.

CNB's ComfyUI is already patched to ``import hook_cnb_xu``. For that tree we
only copy our hook next to ``folder_paths.py``.

If someone points ZHANZHI_ROOT at vanilla ComfyUI, this script applies the
same four patches CNB's ``assets/patch.py`` does — but idempotently, and
without depending on CNB's encrypted hydra fixer.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_PATCHES = Path(__file__).resolve().parent.parent / "patches"

PATCHES = (
    (
        "folder_paths.py",
        "import os\nimport time",
        "import os\nimport hook_cnb_xu\nimport time",
    ),
    (
        "folder_paths.py",
        'continue\n    logging.debug("found {} files".format(len(result)))',
        "continue\n    result = hook_cnb_xu.import_models(directory, result)\n"
        '    logging.debug("found {} files".format(len(result)))',
    ),
    (
        "folder_paths.py",
        'logging.warning("WARNING path {} exists but doesn\'t link anywhere, skipping.".format(full_path))\n\n    return None',
        'logging.warning("WARNING path {} exists but doesn\'t link anywhere, skipping.".format(full_path))\n'
        "    full_path = hook_cnb_xu.download_models(folder_name, filename)\n"
        "    return full_path\n"
        "    return None",
    ),
    (
        "folder_paths.py",
        "full_path = get_full_path(folder_name, filename)\n    if full_path is None:\n        raise FileNotFoundError(",
        "full_path = get_full_path(folder_name, filename)\n"
        "    if full_path is None:\n"
        "        full_path = hook_cnb_xu.download_models2(folder_name, filename)\n"
        "    if full_path is None:\n"
        "        raise FileNotFoundError(",
    ),
    (
        "app/model_manager.py",
        "continue\n\n        return result, dirs",
        "continue\n        import hook_cnb_xu\n        result = hook_cnb_xu.import_models2(directory, result)\n        return result, dirs",
    ),
)


def replace_once(path: Path, old: str, new: str) -> str:
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8")
    if new in text:
        return "present"
    if old not in text:
        return "skipped"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return "patched"


def install_hook_files(comfy: Path) -> None:
    comfy.mkdir(parents=True, exist_ok=True)
    for name in ("hook_cnb_xu.py", "catalog.py"):
        src = _PATCHES / name
        if not src.is_file():
            raise SystemExit(f"missing {src}")
        shutil.copy2(src, comfy / name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--comfy",
        type=Path,
        default=Path(os_env_comfy()),
    )
    parser.add_argument("--vanilla-patch", action="store_true")
    args = parser.parse_args(argv)

    comfy = args.comfy
    folder_paths = comfy / "folder_paths.py"
    if not folder_paths.is_file():
        print(f"[hook] ComfyUI not found at {comfy}", file=sys.stderr)
        return 1

    install_hook_files(comfy)
    already = "import hook_cnb_xu" in folder_paths.read_text(encoding="utf-8")
    if already and not args.vanilla_patch:
        print(f"[hook] CNB-patched ComfyUI detected, installed hook into {comfy}")
        return 0

    print(f"[hook] applying vanilla folder_paths patches in {comfy}")
    for rel, old, new in PATCHES:
        status = replace_once(comfy / rel, old, new)
        print(f"  {rel}: {status}")
    return 0


def os_env_comfy() -> str:
    import os

    return os.environ.get("COMFY_HOME", os.path.join(os.environ.get("ZHANZHI_ROOT", "/opt/zhanzhi"), "ComfyUI"))


if __name__ == "__main__":
    raise SystemExit(main())
