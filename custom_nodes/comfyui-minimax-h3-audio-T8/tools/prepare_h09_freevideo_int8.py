"""Explicit pinned INT8 assets/source preparation; no setup, imports or GPU."""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import time
import urllib.request
import zipfile

REVISION = "ebc94ecdeec3cbfe74040fe69a5116a62bf01dcd"
MODEL_REVISION = "da37681f5a1f7015fdb63482142b865111b687d3"
REPO = "OpenVDN/vdn-minimax-h3-edge"


def request(url, headers=None):
    return urllib.request.urlopen(urllib.request.Request(url, headers={
        "User-Agent": "T8-H09-Pinned-INT8-Preparation", **(headers or {})}), timeout=60)


def small(url, limit=128 * 1024**2):
    with request(url) as response:
        value = response.read(limit + 1)
    if len(value) > limit:
        raise ValueError("Official source response exceeded its bounded size")
    return value


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def source_tree(root):
    marker = root / "t8-source-proof.json"
    if root.exists():
        proof = json.loads(marker.read_text(encoding="utf8"))
        if proof.get("commit") != REVISION:
            raise ValueError("Existing INT8 source is not the fixed new source family")
        for row in proof["files"]:
            path = root / row["file"]
            if path.is_symlink() or digest(path) != row["sha256"]:
                raise ValueError("Previously prepared INT8 source changed")
        return proof
    api = "https://api.github.com/repos/FlashML-org/FreeVideo/git/"
    commit = json.loads(small(api + "commits/" + REVISION))
    tree = json.loads(small(api + "trees/" + commit["tree"]["sha"] + "?recursive=1"))
    if commit.get("sha") != REVISION or tree.get("truncated") or tree.get("sha") != commit["tree"]["sha"]:
        raise ValueError("Incomplete fixed official source tree")
    archive = zipfile.ZipFile(io.BytesIO(small("https://codeload.github.com/FlashML-org/FreeVideo/zip/" + REVISION)))
    entries = [row for row in tree["tree"] if row["type"] == "blob" and
               (row["path"].startswith("freevideo_engine/") or row["path"].startswith(("LICENSE", "NOTICE", "THIRD_PARTY")))]
    checked = []
    for row in entries:
        name = row["path"]
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or row["mode"] not in ("100644", "100755"):
            raise ValueError("Unsafe official source member")
        value = archive.read("FreeVideo-" + REVISION + "/" + name)
        blob = hashlib.sha1(f"blob {len(value)}\0".encode() + value).hexdigest()
        if blob != row["sha"]:
            original = json.loads(small(api + "blobs/" + row["sha"]))
            if original.get("sha") != row["sha"] or original.get("encoding") != "base64":
                raise ValueError("Official Git blob lookup mismatch")
            value = base64.b64decode(original["content"])
            if hashlib.sha1(f"blob {len(value)}\0".encode() + value).hexdigest() != row["sha"]:
                raise ValueError("Official Git blob content mismatch")
        checked.append((row, value))
    root.mkdir(parents=True, exist_ok=False)
    records = []
    for row, value in checked:
        path = root / row["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(value)
        records.append(dict(file=row["path"], bytes=len(value), sha256=hashlib.sha256(value).hexdigest(), git_blob=row["sha"]))
    proof = dict(schema="t8.h09.freevideo-source.v1", commit=REVISION,
                 official_tree=tree["sha"], files=records, upstream_setup_executed=False)
    write_new(marker, proof)
    return proof


def target(root, name):
    member = PurePosixPath(name)
    if member.is_absolute() or ".." in member.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe INT8 asset member")
    result = root.joinpath(*member.parts)
    if result.is_symlink() or not result.resolve().is_relative_to(root):
        raise ValueError("INT8 asset path escaped physical root")
    return result


def fetch_asset(root, row, *, repo=REPO, revision=MODEL_REVISION):
    path = target(root, row["file"])
    if path.exists():
        if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
            raise ValueError("Existing INT8 asset changed: " + row["file"])
        return row["bytes"]
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    if partial.is_symlink():
        raise ValueError("Partial INT8 asset cannot be a symbolic link")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > row["bytes"]:
        raise ValueError("Oversized partial retained for inspection")
    if offset < row["bytes"]:
        url = f"https://huggingface.co/{repo}/resolve/{revision}/{row['file']}"
        with request(url, {"Range": f"bytes={offset}-"} if offset else None) as response:
            if offset and (response.status != 206 or response.headers.get("Content-Range") !=
                           f"bytes {offset}-{row['bytes'] - 1}/{row['bytes']}"):
                raise ValueError("Resume response did not match its exact fixed byte range")
            # A prior disconnected response may leave our zero-byte partial.
            # Reopen that exact file without truncation; xb is for a NEW path.
            with partial.open("r+b" if partial.exists() else "xb") as stream:
                if stream.seek(0, os.SEEK_END) != offset:
                    raise ValueError("INT8 partial changed after its resume range was selected")
                size = offset
                for block in iter(lambda: response.read(4 * 1024**2), b""):
                    size += len(block)
                    if size > row["bytes"]:
                        raise ValueError("Oversized download response; partial retained")
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
    if partial.stat().st_size != row["bytes"] or digest(partial) != row["sha256"]:
        raise ValueError("Downloaded INT8 asset failed full size/SHA verification; partial retained")
    # Create-only destination; a racing creator is never replaced.
    partial.rename(path)
    return row["bytes"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    source, root, receipt = args.source_root.resolve(), args.asset_root.resolve(), args.receipt.resolve()
    if receipt.exists():
        raise FileExistsError("Use a new create-only INT8 preparation receipt")
    started = time.monotonic()
    proof = source_tree(source)
    catalog = json.loads((source / "freevideo_engine/prepared_models.json").read_text(encoding="utf8"))
    variant = catalog["variants"]["int8_convrot"]
    if catalog["repo"] != REPO or variant["revision"] != MODEL_REVISION or len(variant["files"]) != 278:
        raise ValueError("Official INT8 catalog differs from H09 fixed identity")
    print(json.dumps(dict(source_root=str(source), source_revision=proof["commit"],
                         model_revision=MODEL_REVISION, asset_count=278,
                         total_bytes=sum(r["bytes"] for r in variant["files"]), upstream_executed=False)), flush=True)
    if args.source_only:
        write_new(receipt, dict(schema="t8.h09.int8-source-only.v1", source=proof,
                               assets_downloaded=False, sampler_runs=0))
        return
    root.mkdir(parents=True, exist_ok=True)
    missing = 0
    for row in variant["files"]:
        path = target(root, row["file"])
        partial = path.with_suffix(path.suffix + ".partial")
        present = path.stat().st_size if path.exists() else partial.stat().st_size if partial.exists() else 0
        missing += max(0, row["bytes"] - present)
    if shutil.disk_usage(root).free < missing + 8 * 1024**3:
        raise ValueError("INT8 download requires missing bytes plus 8GiB retained free space; no cleanup performed")
    completed, byte_count = 0, 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fetch_asset, root, row) for row in variant["files"]]
        for future in as_completed(futures):
            byte_count += future.result()
            completed += 1
            if completed % 10 == 0 or completed == 278:
                print(json.dumps(dict(verified_files=completed, total_files=278, verified_bytes=byte_count)), flush=True)
    result = dict(schema="t8.h09.int8-assets.v1", source_root=str(source), source_revision=REVISION,
                  asset_root=str(root), model_repository=REPO, model_revision=MODEL_REVISION,
                  cache=str(root / variant["cache_prefix"]), files=variant["files"],
                  verified_files=completed, verified_bytes=byte_count,
                  elapsed_seconds=time.monotonic() - started, original_prepared_weights=True,
                  converted=False, upstream_setup_executed=False, runtime_installed=False,
                  sampler_runs=0, human_quality_accepted=False)
    write_new(receipt, result)
    print(json.dumps({k: v for k, v in result.items() if k != "files"}), flush=True)


if __name__ == "__main__":
    main()
