"""Prepare the fixed official Spark source and optionally its one main-env wheel.

No upstream installer is executed. --install-main is an explicit dependency
change: back up just comfy-kitchen, then pip --no-deps the matched local wheel.
Never update Torch, load models, change Core, start services or touch other jobs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ASSET_SHA = "88a2e15be0b6f61ffb62ff1236ffe24f12190e5adbd0058fec110423c4aea770"
WHEEL_SHA = "76f2bbeeeb111b70666ac841279a0a006d931f439e617b95bd9a3dbab5731620"
VERSION = "0.2.37+spark.h3.sm89.cu130.1"
PREFIX = "ComfyUI-Spark-H3/"
WHEEL = "comfy_kitchen-" + VERSION + "-cp312-abi3-win_amd64.whl"


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def record(path):
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": digest(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--install-main", action="store_true")
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    if digest(archive) != ASSET_SHA:
        raise ValueError("Official Spark release archive SHA mismatch")
    destination = args.destination.resolve()
    if destination.exists():
        raise FileExistsError("Preparation is create-only; use a fresh destination")
    source = destination / "source"
    destination.mkdir(parents=True)
    files = {}
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            if not entry.filename.startswith(PREFIX):
                raise ValueError("Unexpected official archive root")
            rel = entry.filename[len(PREFIX):]
            name = Path(rel)
            if name.is_absolute() or ".." in name.parts or ":" in rel or "\\" in rel:
                raise ValueError("Unsafe archive path")
            selected = rel in {"comfyui_backend.py", "comfyui_reblock_plan.py", "LICENSE"}
            selected |= rel.startswith("h3_sparse_attention/") and rel.endswith(".py")
            if not selected:
                continue  # no upstream nodes, installer, kernels builder or web auto-hooks
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            data = bundle.read(entry)
            with target.open("xb") as out:
                out.write(data)
            files[rel] = hashlib.sha256(data).hexdigest()
        wheel = destination / WHEEL
        with wheel.open("xb") as out:
            out.write(bundle.read(PREFIX + "wheelhouse/" + WHEEL))
    if digest(wheel) != WHEEL_SHA:
        raise ValueError("Matched official wheel SHA mismatch")
    distributions_before = {d.metadata["Name"].lower(): d.version for d in metadata.distributions()}
    before = metadata.distribution("comfy-kitchen")
    old_package = Path(before.locate_file("comfy_kitchen")).resolve(strict=True)
    old_info = Path(before._path).resolve(strict=True)
    site = Path(sys.prefix).resolve() / "Lib" / "site-packages"
    if args.install_main:
        if sys.version_info[:2] != (3, 12) or sys.platform != "win32":
            raise ValueError("This preparation pins the Windows CP312/SM89/CU130 wheel")
        if old_package.parent != site or old_info.parent != site:
            raise ValueError("Selected package is outside this interpreter's site-packages")
        if before.version != "0.2.37":
            raise ValueError("Main installation expects the inspected stock 0.2.37; re-audit changes")
        backup = destination / "before-comfy-kitchen"
        backup.mkdir()
        shutil.copytree(old_package, backup / old_package.name)
        shutil.copytree(old_info, backup / old_info.name)
        preimage = {p.relative_to(backup).as_posix(): digest(p)
                    for p in backup.rglob("*") if p.is_file()}
        with (backup / "receipt.json").open("x", encoding="utf-8") as out:
            json.dump({"python": sys.executable, "version": before.version,
                       "package": str(old_package), "dist_info": str(old_info),
                       "files": preimage}, out, indent=2)
        command = [sys.executable, "-m", "pip", "install", "--no-deps", "--no-index",
                   "--force-reinstall", str(wheel)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=120)
        with (destination / "pip-install.log").open("x", encoding="utf-8") as out:
            out.write(result.stdout + "\n" + result.stderr)
        if result.returncode:
            raise RuntimeError("Wheel installation failed; backup and full log retained")
        metadata.MetadataPathFinder.invalidate_caches()
        after = {d.metadata["Name"].lower(): d.version for d in metadata.distributions()}
        changed = {k for k in distributions_before.keys() | after.keys()
                   if distributions_before.get(k) != after.get(k)}
        if changed != {"comfy-kitchen"} or after.get("comfy-kitchen") != VERSION:
            raise RuntimeError("Unexpected distribution delta; inspect backup and environment")
    manifest = {"schema": "t8.h11.spark-runtime.v1",
                "upstream_commit": "1bb4cdb22648314901e4cbe82c3b414aa1f2e769",
                "upstream_tag": "comfyui-v0.1.2", "archive": record(archive),
                "source_root": str(source), "source_files": files,
                "wheel": record(wheel), "required_kitchen": VERSION,
                "python": sys.executable, "main_environment_install": args.install_main,
                "models_loaded": False, "kernel_executed": False,
                "upstream_installer_executed": False}
    with (destination / "runtime.json").open("x", encoding="utf-8") as out:
        json.dump(manifest, out, indent=2)
        out.write("\n")
    print(json.dumps({"config": str(destination / "runtime.json"),
                      "required_kitchen": VERSION, "source_files": len(files),
                      "installed_main": args.install_main,
                      "backup": str(destination / "before-comfy-kitchen") if args.install_main else None,
                      "models_loaded": False}))


if __name__ == "__main__":
    main()
