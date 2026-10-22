"""Human-readable ordinary-workflow names; never truncate or number a recipe."""
from __future__ import annotations

from pathlib import PurePosixPath
import re

try:
    from .check_windows_paths import validate_paths
except ImportError:  # Executed by a standalone tools/*.py entry point.
    from check_windows_paths import validate_paths


ORDINARY_SUFFIX = "_普通提示词"
LEGACY_NAME = re.compile(r"Plain_\d{3,}\.json", re.IGNORECASE)


def ordinary_target(source) -> PurePosixPath:
    """Retain functional words, stages, model variants and sampling recipe.

    Dates, the common H3 namespace, and replaced Prompt/Relay wording are not
    useful discriminators. All other source words, including EXP, stay intact.
    A genuinely new over-budget or ambiguous name must be reviewed explicitly.
    """
    path = PurePosixPath(str(source).replace("\\", "/"))
    if (path.is_absolute() or ".." in path.parts or path.parts[:2] != ("examples", "workflows")
            or path.suffix != ".json" or len(path.parts) < 4):
        raise ValueError(f"Unsafe workflow source: {source}")
    stem = re.sub(r"(^|_)\d{4}-\d{2}-\d{2}(?=_|$)", "_", path.stem)
    stem = re.sub(r"(^|_)Prompt_Relay(?=_|$)", "_", stem, flags=re.IGNORECASE)
    stem = re.sub(r"(^|_)(Advanced|H3|Relay)(?=_|$)", "_", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_+", "_", stem).strip("_")
    if not stem or LEGACY_NAME.fullmatch(stem + ".json"):
        raise ValueError(f"Source has no functional workflow name: {source}")
    target = path.with_name(stem + ORDINARY_SUFFIX + ".json")
    errors = validate_paths([target.as_posix()])
    if errors:
        raise ValueError("; ".join(errors))
    return target


def render_plain_index(rows) -> str:
    lines = [
        "# 普通提示词工作流", "",
        "普通版与对应原工作流放在同一分类／子目录，文件名保留功能、采样方案、阶段和 Full／Cold 等区别，",
        "以 `_普通提示词.json` 明确区分；不再使用无法辨识用途的 `Plain_001` 编号。原图保留。", "",
        "在完整提示词框一次输入画面、动作和对白；两采／各阶段文字仍可分别编辑。", "",
        "采样器、步数、sigma、模型、LoRA、放大器、音频、保存／恢复步骤沿用原图。",
        "原全局与局部文字合并为普通描述，时间路由被移除；画面不会因此获得强制的时间控制。", "",
        "恢复图请先运行对应普通版 Full 并保存新的阶段文件。Prepared LTX 普通文字仍由准备包的 prompt／缓存输入。",
        "仅完成结构、接口与保留参数校验，原版样片的人审结论不作为这些新文字副本的画质证明。", "",
        f"共 {len(rows)} 份对应关系；机器可读清单：[plain-prompt-index.json](plain-prompt-index.json)。",
        "旧编号和历史长名可查 [旧名→当前文件名与 SHA256](filename-map.tsv)。", "",
    ]
    last = None
    for row in rows:
        source, ordinary = PurePosixPath(row["source"]), PurePosixPath(row["ordinary"])
        category = source.parent.relative_to("examples/workflows").as_posix()
        if category != last:
            lines.extend(["", "## " + category, "", "| 原工作流 | 普通提示词副本 |", "|---|---|"])
            last = category
        src = source.relative_to("examples/workflows").as_posix()
        dst = ordinary.relative_to("examples/workflows").as_posix()
        lines.append(f"| [{source.name}](<{src}>) | [{ordinary.name}](<{dst}>) |")
    return "\n".join(lines) + "\n"
