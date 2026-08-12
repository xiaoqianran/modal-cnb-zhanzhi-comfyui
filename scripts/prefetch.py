#!/usr/bin/env python3
"""Eager model prefetch — Modal counterpart of CNB ``初始化下载``.

Reads the zhanzhi checkout's prefetch script in place. Does not vendor the
aria2c URL list into this repo.

Usage:
  python prefetch.py
  python prefetch.py --dry-run
  python prefetch.py --script /opt/zhanzhi/初始化下载 --root /models
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

_PATCHES = Path(__file__).resolve().parent.parent / "patches"
if _PATCHES.is_dir() and str(_PATCHES) not in sys.path:
    sys.path.insert(0, str(_PATCHES))

from catalog import (  # noqa: E402
    FetchItem,
    iter_missing,
    models_root,
    parse_aria2_file,
    zhanzhi_root,
)


def default_script() -> Path:
    override = os.environ.get("PREFETCH_SCRIPT")
    if override:
        return Path(override)
    root = zhanzhi_root()
    for candidate in (
        root / "初始化下载",
        Path("/workspace/初始化下载"),
        Path(__file__).resolve().parent.parent / "config" / "prefetch.extra.sh",
    ):
        if candidate.is_file():
            return candidate
    return root / "初始化下载"


def extra_script() -> Path | None:
    path = Path(os.environ.get("PREFETCH_EXTRA", "/opt/modal-cnb/config/prefetch.extra.sh"))
    return path if path.is_file() else None


def run_aria2(item: FetchItem, connections: int) -> None:
    os.makedirs(item.dest_dir, exist_ok=True)
    cmd = [
        "aria2c",
        "-x",
        str(connections),
        "-s",
        str(connections),
        "-c",
        "--auto-file-renaming=false",
        "-d",
        item.dest_dir,
        "-o",
        item.filename,
        item.url,
    ]
    print(f"[prefetch] {item.filename} -> {item.dest_dir}", flush=True)
    subprocess.run(cmd, check=True)


def collect_items(script: Path, extra: Path | None, root: str) -> list[FetchItem]:
    items = parse_aria2_file(script, root=root) if script.is_file() else []
    if extra:
        items.extend(parse_aria2_file(extra, root=root))
    # Last write wins on dest_path, first URL kept.
    by_path: dict[str, FetchItem] = {}
    for item in items:
        by_path.setdefault(item.dest_path, item)
    return list(by_path.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, default=None)
    parser.add_argument("--extra", type=Path, default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--connections", type=int, default=int(os.environ.get("ARIA2_CONNECTIONS", "8")))
    parser.add_argument("--sleep", type=float, default=0.0, help="Pause between downloads (politeness).")
    args = parser.parse_args(argv)

    script = args.script or default_script()
    extra = args.extra or extra_script()
    root = args.root or models_root()

    if not script.is_file():
        print(f"[prefetch] no prefetch script at {script}", file=sys.stderr)
        return 1

    items = collect_items(script, extra, root)
    missing = list(iter_missing(items))
    print(
        f"[prefetch] {len(items)} listed, {len(items) - len(missing)} present, "
        f"{len(missing)} to fetch (root={root})",
        flush=True,
    )
    if args.dry_run:
        for item in missing:
            print(f"  {item.dest_path}\n    {item.url}")
        return 0

    log_path = Path(os.environ.get("PREFETCH_LOG", "/tmp/prefetch.log"))
    failures = 0
    with log_path.open("a", encoding="utf-8") as log:
        for item in missing:
            try:
                run_aria2(item, args.connections)
                log.write(f"ok {item.dest_path}\n")
            except subprocess.CalledProcessError as exc:
                failures += 1
                log.write(f"fail {item.dest_path} {exc.returncode}\n")
                print(f"[prefetch] failed: {item.dest_path}", file=sys.stderr)
            if args.sleep:
                time.sleep(args.sleep)
    print(f"[prefetch] done, failures={failures}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
