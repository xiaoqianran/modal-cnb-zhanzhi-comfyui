"""Shared model catalog for Modal — one source of truth.

CNB splits the same information across:
  - ``初始化下载`` (eager aria2c prefetch)
  - ``assets/source.json`` (ComfyUI dropdown + on-demand download)
  - ``assets/source_2.json`` (user overlay)
  - ``自定义下载链接.json`` (another overlay)

This module reads those files in place from a zhanzhi checkout. It does not
copy their contents into this repo.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping
from urllib.parse import urlparse

ARIA2_RE = re.compile(
    r"aria2c\b.*?-d\s+(?P<quote1>['\"])(?P<dest>.*?)(?P=quote1)"
    r".*?-o\s+(?P<quote2>['\"])(?P<name>.*?)(?P=quote2)"
    r".*?(?P<quote3>['\"])(?P<url>https?://.*?)(?P=quote3)",
    re.IGNORECASE,
)

SKIP_SOURCE_KEYS = {"自定义下载链接说明：", "path_dict"}

# ComfyUI folder aliases used by both core and custom nodes.
FOLDER_ALIASES: tuple[tuple[str, ...], ...] = (
    ("unet", "diffusion_models"),
    ("clip", "text_encoders"),
)


@dataclass(frozen=True)
class FetchItem:
    dest_dir: str
    filename: str
    url: str

    @property
    def dest_path(self) -> str:
        return os.path.join(self.dest_dir, self.filename)


def models_root(default: str = "/models") -> str:
    return os.environ.get("MODELS_ROOT", default).rstrip("/")


def zhanzhi_root(default: str = "/opt/zhanzhi") -> Path:
    return Path(os.environ.get("ZHANZHI_ROOT", default))


def rewrite_models_dir(path: str, root: str | None = None) -> str:
    """Map CNB ``/models/...`` destinations onto the active models volume."""
    root = (root or models_root()).rstrip("/")
    normalized = path.replace("\\", "/").rstrip("/")
    if normalized == "/models" or normalized.startswith("/models/"):
        suffix = normalized[len("/models") :].lstrip("/")
        return f"{root}/{suffix}" if suffix else root
    if normalized.startswith("/workspace/models/"):
        suffix = normalized[len("/workspace/models/") :]
        return f"{root}/{suffix}" if suffix else root
    if normalized.startswith("/workspace/ComfyUI/models/"):
        suffix = normalized[len("/workspace/ComfyUI/models/") :]
        return f"{root}/{suffix}" if suffix else root
    return path


def parse_aria2_script(text: str, *, root: str | None = None) -> list[FetchItem]:
    """Parse uncommented ``aria2c ... -d DIR -o FILE URL`` lines."""
    items: list[FetchItem] = []
    seen: set[tuple[str, str]] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = ARIA2_RE.search(line)
        if not match:
            continue
        dest = rewrite_models_dir(match.group("dest"), root)
        name = match.group("name").strip()
        url = match.group("url").strip()
        if not name or not url:
            continue
        key = (os.path.join(dest, name), url)
        if key in seen:
            continue
        seen.add(key)
        items.append(FetchItem(dest_dir=dest, filename=name, url=url))
    return items


def parse_aria2_file(path: str | Path, *, root: str | None = None) -> list[FetchItem]:
    return parse_aria2_script(Path(path).read_text(encoding="utf-8"), root=root)


def lfs_digest(url: str) -> str:
    if "/-/lfs/" in url:
        return url.split("/-/lfs/", 1)[-1].split("?", 1)[0]
    return ""


def _dedup_key(url: str) -> str:
    digest = lfs_digest(url)
    if digest:
        return f"lfs:{digest}"
    parsed = urlparse(url)
    return f"url:{parsed.scheme}://{parsed.netloc}{parsed.path}"


def merge_folder_maps(
    *maps: Mapping[str, Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    """Merge ``{folder: {relative_path: url}}`` catalogs.

    Earlier maps win. Duplicate LFS digests / URLs in a later map are skipped
    even when the relative path differs.
    """
    merged: dict[str, dict[str, str]] = {}
    seen: dict[str, set[str]] = {}
    for mapping in maps:
        for folder, files in mapping.items():
            if folder in SKIP_SOURCE_KEYS or not isinstance(files, dict):
                continue
            bucket = merged.setdefault(folder, {})
            digests = seen.setdefault(folder, set())
            for relpath, url in files.items():
                if not isinstance(relpath, str) or not isinstance(url, str):
                    continue
                if not relpath or not url.startswith(("http://", "https://")):
                    continue
                key = _dedup_key(url)
                if key in digests:
                    continue
                if relpath in bucket:
                    continue
                digests.add(key)
                bucket[relpath] = url
    for folder, files in list(merged.items()):
        merged[folder] = {k: files[k] for k in sorted(files)}
    return {k: merged[k] for k in sorted(merged)}


def load_flat_source(path: str | Path) -> dict[str, dict[str, str]]:
    """Load source_2.json / 自定义下载链接.json (flat folder -> file -> url)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for folder, files in data.items():
        if folder in SKIP_SOURCE_KEYS or not isinstance(files, dict):
            continue
        cleaned: dict[str, str] = {}
        for relpath, url in files.items():
            if isinstance(relpath, str) and isinstance(url, str) and url.startswith("http"):
                cleaned[relpath] = url
        if cleaned:
            out[folder] = cleaned
    return out


def flatten_source_json(data: Mapping[str, object]) -> dict[str, dict[str, str]]:
    """Turn CNB ``source.json`` (path_dict + per-repo file maps) into a flat catalog."""
    path_dict = data.get("path_dict")
    if not isinstance(path_dict, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    seen: dict[str, set[str]] = {}
    for _group, repos in path_dict.items():
        if not isinstance(repos, dict):
            continue
        for repo, root_path in repos.items():
            if not isinstance(root_path, str):
                continue
            repo_files = data.get(repo)
            if not isinstance(repo_files, dict):
                continue
            for relpath, url in repo_files.items():
                if not isinstance(relpath, str) or not isinstance(url, str):
                    continue
                if relpath.endswith(".yaml"):
                    continue
                file_path = f"{root_path.rstrip('/')}/{relpath.lstrip('/')}"
                rel_models = _models_relative(file_path)
                if rel_models is None or "/" not in rel_models:
                    continue
                folder, name = rel_models.split("/", 1)
                key = _dedup_key(url)
                digests = seen.setdefault(folder, set())
                if key in digests:
                    continue
                bucket = out.setdefault(folder, {})
                if name in bucket and bucket[name] != url:
                    # Same filename, different blob: keep both under a disambiguated key.
                    name = f"{repo}/{name}"
                    if name in bucket:
                        continue
                digests.add(key)
                bucket[name] = url
    return out


def _models_relative(file_path: str) -> str | None:
    path = file_path.replace("\\", "/")
    markers = (
        "/workspace/ComfyUI/models/",
        "workspace/ComfyUI/models/",
        "/workspace/models/",
        "workspace/models/",
        "/models/",
        "models/",
    )
    for marker in markers:
        if marker in path:
            return path.split(marker, 1)[-1]
    return None


def load_source_json(path: str | Path) -> dict[str, dict[str, str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return flatten_source_json(data)


def existing_catalog_paths(root: Path | None = None) -> list[Path]:
    """Catalog files in CNB overlay order: user overlay first, then bundled maps."""
    root = root or zhanzhi_root()
    overlay = Path(os.environ.get("MODAL_CNB_OVERLAY", "/opt/modal-cnb/config"))
    candidates = [
        overlay / "source_2.json",
        Path("/workspace/自定义下载链接.json"),
        root / "自定义下载链接.json",
        root / "assets" / "source_2.json",
        Path("/workspace/assets/source_2.json"),
        root / "assets" / "source.json",
        Path("/workspace/assets/source.json"),
    ]
    seen: set[Path] = set()
    out: list[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        out.append(path)
    return out


def load_catalogs(paths: Iterable[Path] | None = None) -> dict[str, dict[str, str]]:
    maps: list[dict[str, dict[str, str]]] = []
    for path in paths or existing_catalog_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if "path_dict" in data:
            maps.append(flatten_source_json(data))
        else:
            maps.append(load_flat_source(path))
    return merge_folder_maps(*maps)


def folder_from_directory(directory: str, roots: Iterable[str] | None = None) -> str | None:
    directory = os.path.abspath(directory).rstrip("/")
    search_roots = list(roots or (models_root(), "/opt/zhanzhi/ComfyUI/models", "/workspace/ComfyUI/models"))
    for raw_root in search_roots:
        root = os.path.abspath(raw_root).rstrip("/")
        if directory == root:
            return None
        prefix = root + os.sep
        if directory.startswith(prefix):
            return directory[len(prefix) :].replace("\\", "/")
    return None


def aliased_folders(folder_name: str) -> tuple[str, ...]:
    for group in FOLDER_ALIASES:
        if folder_name in group:
            return group
    return (folder_name,)


def lookup_url(catalog: Mapping[str, Mapping[str, str]], folder_name: str, filename: str) -> str | None:
    for folder in aliased_folders(folder_name):
        files = catalog.get(folder) or {}
        if filename in files:
            return files[filename]
    return None


def iter_missing(items: Iterable[FetchItem]) -> Iterator[FetchItem]:
    for item in items:
        if os.path.isfile(item.dest_path):
            continue
        yield item
