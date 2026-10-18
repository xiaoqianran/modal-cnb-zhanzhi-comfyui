"""Create a separate INT8 config; verify originals, reuse only matching dependencies.

--probe-only creates SOURCE-ONLY probe input, never a loadable model config.
No dependency installation, backend start, GPU operation or upstream launcher.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import os
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from h3_t8.freevideo_int8.contract import (  # noqa: E402
    REVISION, MODEL_REVISION, VDN_REVISION, RUNTIME, validate_config, validate_manifest,
)
from h3_t8.freevideo_exp.runtime import canonical, digest, verify_files, write_json_new  # noqa: E402
from h3_t8.freevideo_quality.profiles import PROFILES, TASKS  # noqa: E402
from h3_t8.freevideo_quality.assets import required, verify, table_path, REVISIONS  # noqa: E402


def select_tables(manifest, catalog, profiles, tasks):
    """Union exact identities, not a separate preparation per task alias."""
    selected = {}
    for task in tasks:
        if task not in TASKS:
            raise ValueError("Unsupported actual INT8 task")
        for quality in profiles:
            for table, location in required(manifest, catalog, quality,
                    "HIGH" if quality == "light" else "SINGLE", task, reference_audio_t=1.):
                key = table["directory"]
                previous = selected.get(key)
                if previous is not None and previous != (table, location):
                    raise ValueError("Conflicting table identities for the same physical directory")
                selected[key] = (table, location)
    return selected


def fetch_table(table, row, root):
    """New-only bounded resume; do not patch the frozen FP8 preparation helper."""
    from freevideo_engine.adaln_assets import check_table
    remote = table["download"]
    if (remote.get("repo") != "OpenVDN/vdn-minimax-h3-edge"
            or remote.get("prefix") not in REVISIONS
            or remote.get("revision") != REVISIONS[remote["prefix"]]):
        raise ValueError("Unpinned INT8 table download")
    path = table_path(root, row["file"])
    if path.exists():
        check_table(path, row, table["identity"])
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    if partial.is_symlink():
        raise ValueError("Table partial cannot be a symbolic link")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > row["bytes"]:
        raise ValueError("Oversized table partial retained for inspection")
    if offset < row["bytes"]:
        url = f"https://huggingface.co/{remote['repo']}/resolve/{remote['revision']}/{remote['prefix']}/{row['file']}"
        request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
        with urllib.request.urlopen(request, timeout=60) as response:
            if offset and (response.status != 206 or response.headers.get("Content-Range") !=
                           f"bytes {offset}-{row['bytes']-1}/{row['bytes']}"):
                raise ValueError("Table resume range mismatch; partial retained")
            with partial.open("r+b" if partial.exists() else "xb") as stream:
                if stream.seek(0, os.SEEK_END) != offset:
                    raise ValueError("Table partial changed during resume selection")
                size = offset
                for block in iter(lambda: response.read(1024**2), b""):
                    size += len(block)
                    if size > row["bytes"]:
                        raise ValueError("Oversized table response; partial retained")
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
    check_table(partial, row, table["identity"])
    partial.rename(path)  # Create-only on Windows; never replace existing evidence.
    print("Prepared " + row["file"], flush=True)


def record(path, kind="source"):
    path = Path(path).resolve(strict=True)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest(path), kind=kind)


def source_inventory(source, old):
    proof = json.loads((source / "t8-source-proof.json").read_text(encoding="utf8"))
    if proof.get("schema") != "t8.h09.freevideo-source.v1" or proof.get("commit") != REVISION:
        raise ValueError("Prepare the fixed independent H09 source first")
    rows = []
    for row in proof["files"]:
        path = (source / row["file"]).resolve(strict=True)
        if not path.is_relative_to(source) or path.is_symlink():
            raise ValueError("INT8 source escaped its verified root")
        value = path.read_bytes()
        if (len(value) != row["bytes"] or hashlib.sha256(value).hexdigest() != row["sha256"]
                or hashlib.sha1(f"blob {len(value)}\0".encode() + value).hexdigest() != row["git_blob"]):
            raise ValueError("INT8 source changed from its official Git blob")
        rows.append(dict(path=str(path), bytes=len(value), sha256=row["sha256"], kind="source"))
    dependencies = json.loads((source / "freevideo_engine/dependencies.json").read_text(encoding="utf8"))
    if dependencies["vdn"]["commit"] != VDN_REVISION or old.get("vdn_revision") != VDN_REVISION:
        raise ValueError("Borrowed VDN does not match the new author dependency")
    vdn = Path(old["vdn_root"]).resolve(strict=True)
    python = Path(old["python"]).resolve(strict=True)
    # Reuse the exact frozen VDN/interpreter; never borrow the old engine or body.
    borrowed = [row for row in old["files"] if row["kind"] == "source" and (
        Path(row["path"]).resolve().is_relative_to(vdn) or Path(row["path"]).resolve() == python)]
    if not any(Path(row["path"]).resolve() == python for row in borrowed):
        raise ValueError("Old configuration does not bind the actual isolated interpreter")
    verify_files(borrowed)
    rows += borrowed
    for folder in ("freevideo_int8", "freevideo_exp"):
        rows += [record(path) for path in sorted((ROOT / "h3_t8" / folder).glob("*.py"))]
    for name in ("profiles.py", "assets.py", "probe_worker.py"):
        rows.append(record(ROOT / "h3_t8/freevideo_quality" / name))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("legacy-config", "source-root", "home", "output-config"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--asset-receipt", type=Path)
    parser.add_argument("--sampling-root", type=Path)
    parser.add_argument("--profiles", nargs="+", choices=list(PROFILES), default=list(PROFILES))
    task_args = parser.add_mutually_exclusive_group()
    task_args.add_argument("--task", choices=TASKS)
    task_args.add_argument("--tasks", nargs="+", choices=TASKS)
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    tasks = list(dict.fromkeys(args.tasks or [args.task or "t2va"]))
    if args.output_config.exists():
        raise FileExistsError("Use a fresh INT8 config; no old runtime is overwritten")
    old = json.loads(args.legacy_config.read_text(encoding="utf8"))
    source, home = args.source_root.resolve(strict=True), args.home.resolve()
    rows = source_inventory(source, old)
    config = {key: old[key] for key in ("python", "vdn_root", "base", "checkpoint")}
    config.update(schema="t8-freevideo-int8-probe-config-v1" if args.probe_only else RUNTIME,
                  freevideo_revision=REVISION, model_revision=MODEL_REVISION, vdn_revision=VDN_REVISION,
                  source_root=str(source), home=str(home))
    if args.probe_only:
        config.update(files=rows, inventory_sha256=hashlib.sha256(canonical(rows).encode()).hexdigest(),
                      model_ready=False, native_sampler_runs=0)
        home.mkdir(parents=True, exist_ok=True)
        write_json_new(args.output_config, config)
        print(canonical(dict(config=str(args.output_config), model_ready=False, source_files=len(rows))))
        return
    if args.asset_receipt is None:
        raise ValueError("The completed original INT8 asset receipt is required")
    prepared = json.loads(args.asset_receipt.read_text(encoding="utf8"))
    catalog = json.loads((source / "freevideo_engine/prepared_models.json").read_text(encoding="utf8"))
    variant = catalog["variants"]["int8_convrot"]
    if (prepared.get("schema") != "t8.h09.int8-assets.v1" or prepared.get("model_revision") != MODEL_REVISION
            or prepared.get("source_revision") != REVISION or prepared.get("verified_files") != 278
            or prepared.get("files") != variant["files"] or variant["revision"] != MODEL_REVISION):
        raise ValueError("Need all 278 completed original INT8 assets, not partials or an FP8 receipt")
    asset_root = Path(prepared["asset_root"]).resolve(strict=True)
    cache = table_path(asset_root, variant["cache_prefix"])
    if Path(prepared["cache"]).resolve(strict=True) != cache:
        raise ValueError("INT8 receipt cache path differs from the fixed catalog")
    for row in variant["files"]:
        path = table_path(asset_root, row["file"])
        rows.append(dict(path=str(path), bytes=row["bytes"], sha256=row["sha256"], kind="weight"))
    verify_files(rows)
    # Import only explicit pinned table validators, not Engine/setup/launcher.
    sys.path.insert(0, str(source))
    from freevideo_engine.adaln_assets import validate_catalog, weight_identity
    manifest = validate_manifest(json.loads((cache / "manifest.json").read_text(encoding="utf8")))
    validate_catalog(manifest, 50)
    sampling = (args.sampling_root or Path(old["sampling_root"])).resolve()
    selected = select_tables(manifest, catalog, args.profiles, tasks)
    print(f"Preparing {len(selected)} distinct exact tables for {','.join(tasks)}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(fetch_table, table, row, sampling) for table, location in selected.values()
                if location == "sampling" for row in table["files"]]
        for job in jobs:
            job.result()
    for table, location in selected.values():
        folder = cache if location == "base" else sampling
        verify(table, folder)
        rows += [dict(path=str(table_path(folder, row["file"])), bytes=row["bytes"],
                      sha256=row["sha256"], kind="weight") for row in table["files"]]
    # Engine skeleton configs only, not old FP8 body weights.
    for name in ("base", "checkpoint"):
        parent = Path(old[name]).resolve(strict=True)
        configs = [row for row in old["files"] if Path(row["path"]).resolve().is_relative_to(parent)]
        verify_files(configs)
        rows += configs
    unique = {}
    for row in rows:
        path = str(Path(row["path"]).resolve())
        if path in unique and unique[path] != row:
            raise ValueError("Conflicting independent INT8 inventory rows")
        unique[path] = row
    rows = list(unique.values())
    config.update(cache=str(cache), sampling_root=str(sampling), files=rows,
                  inventory_sha256=hashlib.sha256(canonical(rows).encode()).hexdigest(),
                  prepared_profiles=args.profiles, prepared_task=tasks[0] if len(tasks) == 1 else "multiple",
                  prepared_tasks=tasks,
                  original_asset_receipt_sha256=digest(args.asset_receipt), model_ready=True,
                  boundary="Independent INT8 original assets, producer and Stage. Old FP8 configuration unchanged.")
    validate_config(config, full=True)
    home.mkdir(parents=True, exist_ok=True)
    write_json_new(args.output_config, config)
    print(canonical(dict(config=str(args.output_config), sha256=digest(args.output_config),
                         weight_identity=weight_identity(manifest), tables=len(selected), model_ready=True)))


if __name__ == "__main__":
    main()
