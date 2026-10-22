"""Render an installed-only companion index without modifying saved workflows.

The repository catalogue includes unpublished/uninstalled examples. It must not
be mirrored wholesale into a user's partial installation or used as its oracle.
This tool prints the proposed index; --check checks an explicitly supplied file.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

INDEX_NAME = "T8_INSTALLED_INDEX.md"
ROW = re.compile(r"^\|\s*(?:`([^`]+)`|\[([^\]]+)\]\([^)]*\))\s*\|\s*(.*?)\s*\|$")


def catalogue_rows(source: str) -> dict[str, str]:
    rows = {}
    for line in source.splitlines():
        match = ROW.fullmatch(line)
        if not match:
            continue
        name = match[1] or match[2]
        if not re.fullmatch(r"[0-9]{2,3}-[A-Za-z0-9_-]+", name):
            continue
        descriptions = rows.setdefault(name, [])
        if match[3] not in descriptions:
            descriptions.append(match[3])
    # The catalogue has both highlighted releases and the older category table.
    # Merge their descriptions rather than duplicating installed categories.
    return {name: "；".join(descriptions) for name, descriptions in rows.items()}


def render_installed_index(source: str, installed_root: Path) -> str:
    descriptions = catalogue_rows(source)
    lines = ["# MiniMax H3 T8 · 本机已安装工作流", "",
             "按本机实际含 JSON 的分类生成；仓库目录不等于本机安装清单。",
             "仅更新此独立索引，不覆盖原 README、JSON、素材或用户修改。", "",
             "| 目录 | JSON 数量 | 说明 |", "|---|---:|---|"]
    for directory in sorted(installed_root.iterdir(), key=lambda path: path.name):
        # Only T8 category directories; never follow outside-directory symlinks.
        if (not re.fullmatch(r"[0-9]{2,3}-[A-Za-z0-9_-]+", directory.name)
                or not directory.is_dir() or directory.is_symlink()):
            continue
        root = installed_root.resolve()
        if not directory.resolve().is_relative_to(root):
            continue
        count = sum(1 for path in directory.rglob("*.json")
                    if path.is_file() and path.resolve().is_relative_to(root))
        if not count:
            continue
        target = f"{directory.name}/"
        if (directory / "README.md").is_file():
            target += "README.md"
        description = descriptions.get(directory.name, "本机自有分类；仓库未列出，保留用户文件")
        lines.append(f"| [{directory.name}]({target}) | {count} | {description} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "examples/workflows/README.md"
    rendered = render_installed_index(source.read_text(encoding="utf-8"), args.installed_root)
    if args.check:
        if args.check.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Installed workflow index is stale; regenerate the companion index only")
        print("Installed workflow index matches actual JSON categories")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
