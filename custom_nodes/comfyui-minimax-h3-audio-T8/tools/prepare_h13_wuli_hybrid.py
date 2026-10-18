"""Verify/install one already-downloaded native Hybrid checkpoint, never convert it.

No network/auth, model load, GPU or dependency changes. Existing wrong files are
retained and rejected. A receipt is content evidence, not loaded-MODEL proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

REPO = "sandpies/Wuli-MiniMax-H3-Turbo-ComfyUI"
REVISION = "9df5eccfa095adcdbffba5ba8cbe4c0c66d15a7e"
FILENAME = "wuli_h3_turbo_8step_v1_flbase_refadaln_b25-49_flashgen050_int8_convrot_hq.safetensors"
SIZE = 25007719260
SHA = "a852255134e20112d63a23848be122bd0076e37b9ddac09e436d9d61abbba42b"


def verify(path):
    before = path.stat()
    if before.st_size != SIZE:
        raise ValueError("Selected ordinary Hybrid size mismatch; file retained")
    with path.open("rb") as file:
        actual = hashlib.file_digest(file, "sha256").hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("Hybrid changed while hashing")
    if actual != SHA:
        raise ValueError("Selected ordinary Hybrid SHA mismatch; file retained")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True, help="ComfyUI models root")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise FileExistsError("Keep previous receipt")
    source = args.source.resolve(strict=True)
    target = args.models.resolve(strict=True) / "diffusion_models" / FILENAME
    if target.is_symlink():
        raise ValueError("Hybrid target cannot redirect through a symlink")
    reused = target.exists()
    if reused:
        verify(target)
    else:
        verify(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="h13-hybrid-", suffix=".partial", dir=target.parent, delete=False) as temp:
            partial = Path(temp.name)
            with source.open("rb") as file:
                shutil.copyfileobj(file, temp, 8 * 1024**2)
            temp.flush()
            os.fsync(temp.fileno())
        verify(partial)
        # Atomic no-overwrite publication on the same filesystem. Failure retains
        # the verified partial for inspection, never overwrites another task's file.
        os.link(partial, target)
        partial.unlink()
    result = {"schema": "t8.h13.wuli-hybrid-assets.v1", "repo": REPO,
              "revision": REVISION, "variant": "ordinary_FLbase_RefAdaLN_b25-49_FlashGen050",
              "files": [{"file": str(target), "bytes": SIZE, "sha256": SHA}],
              "existing_verified_file_reused": reused, "native_ComfyUI": True,
              "loaded_MODEL_identity_proved": False, "quality_accepted": False,
              "weight_license": "MiniMax H3 Community License; upstream component terms also apply"}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
