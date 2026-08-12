"""Build a Modal Secret payload from local HF / Civitai / GitHub tokens.

``.env`` may list the tokens directly. Other keys in that file (GPU, volumes,
repo URL, …) stay local and are never copied into the Secret.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

TOKEN_KEYS = (
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "CIVITAI_TOKEN",
    "CIVITAI_API_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
)

# Tools disagree on the canonical name; populate both when either is set.
TOKEN_ALIASES = (
    ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"),
    ("CIVITAI_TOKEN", "CIVITAI_API_TOKEN"),
    ("GITHUB_TOKEN", "GH_TOKEN"),
)

_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_dotenv(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY.match(key):
            continue
        result[key] = _unquote(value.strip())
    return result


def read_dotenv(path: str | Path) -> dict[str, str]:
    file = Path(path)
    if not file.is_file():
        return {}
    return parse_dotenv(file.read_text(encoding="utf-8"))


def _nonempty(mapping: Mapping[str, str], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    value = value.strip()
    return value or None


def token_secret_dict(
    environ: Mapping[str, str],
    dotenv: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Merge token keys from ``.env`` then ``environ`` (env wins). Fill aliases."""
    merged: dict[str, str] = {}
    for source in (dotenv or {}, environ):
        for key in TOKEN_KEYS:
            value = _nonempty(source, key)
            if value is not None:
                merged[key] = value
    for left, right in TOKEN_ALIASES:
        if left in merged and right not in merged:
            merged[right] = merged[left]
        elif right in merged and left not in merged:
            merged[left] = merged[right]
    return merged
