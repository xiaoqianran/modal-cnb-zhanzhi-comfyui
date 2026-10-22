"""Rename only manifest-owned ordinary examples, retaining each JSON byte.

Read-only by default. --write requires a new private backup directory beneath
this repository's artifacts/development; no user/default/workflows is touched.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re

try:
    from .check_windows_paths import validate_paths
    from .plain_prompt_names import LEGACY_NAME, ordinary_target, render_plain_index
except ImportError:
    from check_windows_paths import validate_paths
    from plain_prompt_names import LEGACY_NAME, ordinary_target, render_plain_index

ROOT = Path(__file__).resolve().parents[1]
INDEX = Path("examples/workflows/plain-prompt-index.json")
NAME_MAP = Path("examples/workflows/filename-map.tsv")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def owned_path(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe repository path: {relative}")
    result = root / path
    if not result.resolve().is_relative_to(root.resolve()) or result.is_symlink():
        raise ValueError(f"Escaping or linked repository path: {relative}")
    return result


def plan_renames(root):
    root = root.resolve()
    original_index = (root / INDEX).read_bytes()
    manifest = json.loads(original_index.decode("utf-8"))
    rows = manifest["rows"]
    if len(rows) != manifest["source_count"]:
        raise ValueError("Incomplete ordinary-workflow manifest")
    moves, seen_sources, seen_targets, seen_old, updated_rows = [], set(), set(), set(), []
    for row in rows:
        source = owned_path(root, row["source"])
        old = owned_path(root, row["ordinary"])
        new_relative = ordinary_target(row["source"]).as_posix()
        new = owned_path(root, new_relative)
        if old.parent != source.parent or new.parent != source.parent:
            raise ValueError("Ordinary workflow must stay beside its source")
        source_key, target_key = row["source"].casefold(), new_relative.casefold()
        if source_key in seen_sources or target_key in seen_targets or row["ordinary"].casefold() in seen_old:
            raise ValueError("Ambiguous source or descriptive filename; review names explicitly")
        seen_sources.add(source_key)
        seen_targets.add(target_key)
        seen_old.add(row["ordinary"].casefold())
        for path, field in ((source, "source_sha256"), (old, "ordinary_sha256")):
            if sha256(path.read_bytes()) != row[field]:
                raise ValueError(f"User-edited or stale manifest file: {path.relative_to(root)}")
        graph = json.loads(old.read_text(encoding="utf-8-sig"))
        if graph.get("extra", {}).get("t8_plain_source") != row["source"]:
            raise ValueError(f"File is not the manifest-owned ordinary workflow: {row['ordinary']}")
        if old != new:
            if not LEGACY_NAME.fullmatch(old.name):
                raise ValueError(f"Refusing to silently rename a non-numbered workflow: {old.name}")
            if new.exists() or any(p.name.casefold() == new.name.casefold() for p in new.parent.iterdir()):
                raise ValueError(f"Destination already exists: {new_relative}")
            moves.append({"old_path": row["ordinary"], "new_path": new_relative,
                          "sha256": sha256(old.read_bytes().replace(b"\r\n", b"\n")),
                          "raw_sha256": row["ordinary_sha256"]})
        updated_rows.append({**row, "ordinary": new_relative})
    errors = validate_paths([row["ordinary"] for row in updated_rows])
    if errors:
        raise ValueError("\n".join(errors))
    manifest["rows"] = updated_rows
    updates = {
        INDEX: (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        Path("examples/workflows/PLAIN_PROMPTS.md"): render_plain_index(updated_rows).encode("utf-8"),
    }
    map_path = root / NAME_MAP
    map_rows = list(csv.DictReader(io.StringIO(map_path.read_text(encoding="utf-8")), delimiter="\t"))
    for move in moves:
        historical = {key: move[key] for key in ("old_path", "new_path", "sha256")}
        prior = next((row for row in map_rows if row["old_path"] == historical["old_path"]), None)
        if prior is not None and prior != historical:
            raise ValueError("Conflicting historical filename mapping")
        if prior is None:
            map_rows.append(historical)
    for field in ("old_path", "new_path"):
        if len({row[field].casefold() for row in map_rows}) != len(map_rows):
            raise ValueError(f"Duplicate historical filename {field}")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=("old_path", "new_path", "sha256"), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(map_rows)
    updates[NAME_MAP] = stream.getvalue().encode("utf-8")
    for directory in sorted({Path(row["source"]).parent for row in rows}):
        relative = directory / "README.md"
        path = owned_path(root, relative)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        new_content = re.sub(
            r"^(普通提示词副本：[^\r\n]*?对照\][^\r\n]*?\)。)[^\r\n]*",
            r"\1本目录 `*_普通提示词.json` 按原功能、采样和阶段命名，与原图同目录。完整描述一次填写，各阶段可分别编辑；原图保留。",
            content, count=1, flags=re.MULTILINE,
        )
        if new_content != content:
            updates[relative] = new_content.encode("utf-8")
    overview = Path("examples/workflows/README.md")
    content = (root / overview).read_text(encoding="utf-8")
    updates[overview] = content.replace("`Plain_*.json`", "`*_普通提示词.json`（按功能、采样和阶段命名，与原图同目录）").encode("utf-8")
    updates = {path: data for path, data in updates.items() if (root / path).read_bytes() != data}
    moved_old = {move["old_path"] for move in moves}
    protected = {path.relative_to(root).as_posix(): sha256(path.read_bytes())
                 for path in (root / "examples/workflows").rglob("*.json")
                 if path.relative_to(root).as_posix() not in moved_old and path.relative_to(root) != INDEX}
    before = {relative: (root / relative).read_bytes() for relative in updates}
    return {"moves": moves, "updates": updates, "before": before, "protected": protected, "rows": updated_rows}


def apply_renames(root, plan, backup):
    root, backup = root.resolve(), backup.resolve()
    allowed = (root / "artifacts/development").resolve()
    if not backup.is_relative_to(allowed) or backup == allowed or backup.exists():
        raise ValueError("Use a new, task-owned artifacts/development backup directory")
    # Check every source and destination again before the first filesystem move.
    for move in plan["moves"]:
        old, new = owned_path(root, move["old_path"]), owned_path(root, move["new_path"])
        if sha256(old.read_bytes()) != move["raw_sha256"] or new.exists():
            raise ValueError("Files changed after rename preflight; nothing was moved")
    for relative, digest in plan["protected"].items():
        if sha256(owned_path(root, relative).read_bytes()) != digest:
            raise ValueError("Protected workflow changed after preflight")
    before = plan["before"]
    if any((root / relative).read_bytes() != data for relative, data in before.items()):
        raise ValueError("Reference files changed after preflight; nothing was moved")
    backup.mkdir(parents=True)
    for relative, data in before.items():
        path = backup / "preimage" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (backup / "before.json").write_text(json.dumps({"moves": plan["moves"], "protected": plan["protected"]},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    moved = []
    try:
        for move in plan["moves"]:
            old, new = owned_path(root, move["old_path"]), owned_path(root, move["new_path"])
            old.rename(new)
            moved.append(move)
        for relative, data in plan["updates"].items():
            (root / relative).write_bytes(data)
        for move in moved:
            if sha256((root / move["new_path"]).read_bytes()) != move["raw_sha256"]:
                raise ValueError("Renamed JSON bytes changed")
        for relative, digest in plan["protected"].items():
            if sha256((root / relative).read_bytes()) != digest:
                raise ValueError(f"Protected workflow changed: {relative}")
    except Exception:
        for relative, data in before.items():
            (root / relative).write_bytes(data)
        for move in reversed(moved):
            old, new = owned_path(root, move["old_path"]), owned_path(root, move["new_path"])
            if old.exists() or sha256(new.read_bytes()) != move["raw_sha256"]:
                raise RuntimeError(f"Concurrent change prevents safe rollback; see {backup}")
            new.rename(old)
        raise
    result = {"status": "pass", "renamed": len(moved), "categories": len({Path(row['source']).parent for row in plan['rows']}),
              "updated_reference_files": len(plan["updates"]), "protected_jsons_unchanged": len(plan["protected"]),
              "all_renamed_json_bytes_unchanged": True, "user_workflows_touched": False,
              "sampling_or_model_changes": False, "gpu_or_generation_run": False}
    (backup / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup", type=Path)
    options = parser.parse_args()
    plan = plan_renames(options.root)
    if options.write:
        if options.backup is None:
            parser.error("--write requires --backup")
        if not plan["moves"] and not plan["updates"]:
            result = {"status": "already_current", "renamed": 0}
        else:
            result = apply_renames(options.root, plan, options.backup)
    else:
        result = {"status": "preflight_pass", "renames": len(plan["moves"]), "reference_files": len(plan["updates"]),
                  "examples": plan["moves"][:5]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
