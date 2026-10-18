"""Download only four SHA-pinned native ComfyUI Wuli assets. No conversion/install.

Create-only final files; bounded partial resume; no auth bypass, implicit token,
HF cache duplicate, model loading, dependency changes or sampler execution.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

REPO = "sandpies/Wuli-MiniMax-H3-Turbo-ComfyUI"
REVISION = "82f86823abcd6288370d73bc19a98e636282ad28"
ASSETS = [
    ("8step/wuli_h3_turbo_8step_v1_comfyui_int8_convrot.safetensors", "diffusion_models",
     21387480044, "6d81c5d4975b47de69e6854cb2c9664ac875beed25ce2ebe0f65b7081d0c737b"),
    ("4step/wuli_h3_turbo_4step_v1_trunk_comfyui_bf16.safetensors", "loras",
     1956196560, "ee16350bd02f46627a15a64ebd37b31f8547dd507855141c9c446a13adead8a1"),
    ("4step/wuli_h3_turbo_4step_v1_heads_widen.safetensors", "loras",
     48968, "eb643e48b5849523ffdbd365977926e6fa9b2e4c8a564f034f665560edb30805"),
    ("4step/wuli_h3_turbo_4step_v1_heads_set.safetensors", "loras",
     11013072, "36af67e8b334f89458234b29f80e1b23f7ffba44432c0450af03ee7780b60aa7"),
]


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def fetch(asset, root):
    rel, folder, total, expected = asset
    target = root / folder / Path(rel).name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("New Wuli target must not redirect through a symlink")
    if target.exists():
        if target.stat().st_size != total or digest(target) != expected:
            raise ValueError("Existing selected asset has wrong content; retained: " + str(target))
        return {"file": str(target), "sha256": expected, "bytes": total, "reused": True}
    partial = target.with_suffix(target.suffix + ".h11.partial")
    if partial.is_symlink():
        raise ValueError("Partial cannot be a symbolic link")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > total:
        raise ValueError("Oversized partial retained for inspection")
    sha = hashlib.sha256()
    if offset:
        with partial.open("rb") as file:
            for block in iter(lambda: file.read(8 * 1024**2), b""):
                sha.update(block)
    if offset < total:
        url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{rel}?download=true"
        request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
        with urllib.request.urlopen(request, timeout=30) as response:
            if offset and (response.status != 206 or response.headers.get("Content-Range") !=
                           f"bytes {offset}-{total-1}/{total}"):
                raise ValueError("Unexpected resume response; partial retained")
            with partial.open("r+b" if partial.exists() else "xb") as out:
                if out.seek(0, os.SEEK_END) != offset:
                    raise ValueError("Partial concurrently changed")
                count, last = offset, time.monotonic()
                for block in iter(lambda: response.read(8 * 1024**2), b""):
                    count += len(block)
                    if count > total:
                        raise ValueError("Asset response exceeds expected size")
                    out.write(block)
                    sha.update(block)
                    if time.monotonic() - last > 20:
                        print(json.dumps({"download": target.name, "bytes": count, "total": total}), flush=True)
                        last = time.monotonic()
                out.flush()
                os.fsync(out.fileno())
    if partial.stat().st_size != total or sha.hexdigest() != expected:
        raise ValueError("Asset size/SHA mismatch; partial retained: " + target.name)
    partial.rename(target)  # new-only final publication on Windows
    print(json.dumps({"complete": target.name, "bytes": total, "sha256": expected}), flush=True)
    return {"file": str(target), "sha256": expected, "bytes": total, "reused": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise FileExistsError("Keep previous download evidence")
    with ThreadPoolExecutor(max_workers=2) as executor:
        files = list(executor.map(lambda row: fetch(row, args.models.resolve()), ASSETS))
    receipt = {"schema": "t8.h11.wuli-assets.v1", "repo": REPO, "revision": REVISION,
               "files": files, "model_loaded": False, "quality_qualified": False,
               "weight_license": "MiniMax H3 Community License (independent of adapter code)"}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as out:
        json.dump(receipt, out, indent=2)
        out.write("\n")
    print(json.dumps({"receipt": str(args.receipt), "files": len(files)}))


if __name__ == "__main__":
    main()
