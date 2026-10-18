"""Explicit, pinned Person Remover download; no packages, GPU or service changes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request

REPO = "akatz-ai/MiniMax-H3-Person-Remover-LoRA"
REVISION = "bbc23bf8d6ef833aef43afc0ae740b7cf937d763"
NAME = "H3-Person-Remover-V1.safetensors"
SIZE = 155110584
SHA = "b01dc9fe888c2f4e455a8eb3b4878dfd4038ee0e2320a7b186c7935e65c93ba5"


def request(url):
    return urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "T8-H09-Explicit-Assets"}), timeout=60)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.model_dir.resolve()
    receipt = args.receipt_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    receipt.mkdir(parents=True, exist_ok=True)
    target = root / NAME
    if target.is_symlink():
        raise ValueError("Original weights must have an unambiguous physical target")
    if not target.exists():
        if shutil.disk_usage(root).free < SIZE + 1024**3:
            raise ValueError("Insufficient disk space for weights plus margin")
        partial = root / (NAME + ".partial")
        total, sha, tick = 0, hashlib.sha256(), time.monotonic()
        with request(f"https://huggingface.co/{REPO}/resolve/{REVISION}/{NAME}") as response, partial.open("xb") as out:
            while chunk := response.read(4 * 1024**2):
                total += len(chunk)
                if total > SIZE:
                    raise ValueError("Download exceeds pinned size; partial retained")
                out.write(chunk)
                sha.update(chunk)
                if time.monotonic() - tick > 10:
                    print(json.dumps(dict(downloaded_bytes=total, total_bytes=SIZE)), flush=True)
                    tick = time.monotonic()
        if total != SIZE or sha.hexdigest() != SHA:
            raise ValueError("Weight identity mismatch; partial retained")
        partial.rename(target)  # Never overwrites another model.
    if target.stat().st_size != SIZE or digest(target) != SHA:
        raise ValueError("Existing weight does not match the pinned original")

    # Metadata / example are retained as source material, never executed.
    with request(f"https://huggingface.co/api/models/{REPO}/tree/{REVISION}?recursive=true&expand=true") as response:
        raw = response.read(4 * 1024**2 + 1)
    if len(raw) > 4 * 1024**2:
        raise ValueError("Unbounded model metadata")
    listing = json.loads(raw)
    selected = {"README.md", "LICENSE", "examples/README.md",
                "examples/Person-Remover-Window-Reroll-V1.json"}
    inventory = []
    for row in listing:
        name = row.get("path")
        if name not in selected:
            continue
        if row.get("type") != "file" or not 0 < row.get("size", 0) <= 2 * 1024**2:
            raise ValueError("Unexpected source metadata descriptor")
        with request(f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}") as response:
            data = response.read(2 * 1024**2 + 1)
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if len(data) != row["size"] or blob != row.get("oid"):
            raise ValueError("Source Git object identity mismatch")
        destination = receipt / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != data:
                raise ValueError("Existing source material changed")
        else:
            with destination.open("xb") as stream:
                stream.write(data)
        inventory.append(dict(path=name, sha256=hashlib.sha256(data).hexdigest(),
                              bytes=len(data), git_oid=blob))
    if {row["path"] for row in inventory} != selected:
        raise ValueError("Pinned source material is incomplete")
    proof = dict(schema="t8.h09.person-assets.v1", repository=REPO, revision=REVISION,
                 weight_path=str(target), bytes=SIZE, sha256=SHA, source=inventory,
                 original_weights=True, converted=False, installed_software=False,
                 sampler_runs=0, human_quality_accepted=False,
                 license="MiniMax H3 Community License; third-party Relay is separate")
    proof_path = receipt / "assets.json"
    with proof_path.open("x", encoding="utf8") as out:
        json.dump(proof, out, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(dict(status="assets_verified_not_media_qualified", proof=str(proof_path))), flush=True)


if __name__ == "__main__":
    main()
