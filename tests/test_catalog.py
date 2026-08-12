from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "patches"))

from catalog import (  # noqa: E402
    FetchItem,
    existing_catalog_paths,
    flatten_source_json,
    folder_from_directory,
    iter_missing,
    load_catalogs,
    load_flat_source,
    lookup_url,
    merge_folder_maps,
    parse_aria2_file,
    rewrite_models_dir,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_aria2_skips_comments_and_rewrites_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELS_ROOT", str(tmp_path / "models"))
    items = parse_aria2_file(FIXTURES / "init_download.sh", root=str(tmp_path / "models"))
    names = {item.filename: item for item in items}
    assert set(names) == {
        "SeC-4B-fp8.safetensors",
        "wan_2.1_vae.safetensors",
        "lightning.safetensors",
    }
    assert names["lightning.safetensors"].dest_dir.endswith("/loras")
    assert "nope.pt" not in names
    assert names["SeC-4B-fp8.safetensors"].url.endswith("aaa111")


def test_rewrite_models_dir():
    assert rewrite_models_dir("/models/vae", "/mnt/m") == "/mnt/m/vae"
    assert rewrite_models_dir("/workspace/ComfyUI/models/clip", "/mnt/m") == "/mnt/m/clip"
    assert rewrite_models_dir("/other/path", "/mnt/m") == "/other/path"


def test_flatten_source_json():
    data = json.loads((FIXTURES / "source.json").read_text(encoding="utf-8"))
    flat = flatten_source_json(data)
    assert flat["vae"]["wan_2.1_vae.safetensors"].endswith("wanvae")
    assert flat["text_encoders"]["umt5.safetensors"].endswith("umt5")
    assert flat["checkpoints"]["flux1-dev.safetensors"].endswith("fluxdev")


def test_overlay_wins_and_keeps_http_without_lfs():
    bundled = flatten_source_json(json.loads((FIXTURES / "source.json").read_text(encoding="utf-8")))
    overlay = load_flat_source(FIXTURES / "source_2.json")
    merged = merge_folder_maps(overlay, bundled)
    assert merged["checkpoints"]["mine.safetensors"].startswith("https://huggingface.co/")
    # overlay listed first: same relative path keeps overlay URL
    assert merged["vae"]["wan_2.1_vae.safetensors"].startswith("https://huggingface.co/")
    assert "flux1-dev.safetensors" in merged["checkpoints"]


def test_folder_from_directory(tmp_path):
    root = tmp_path / "models"
    (root / "checkpoints").mkdir(parents=True)
    assert folder_from_directory(str(root / "checkpoints"), roots=[str(root)]) == "checkpoints"
    assert folder_from_directory(str(root), roots=[str(root)]) is None


def test_lookup_url_aliases():
    catalog = {"diffusion_models": {"a.safetensors": "https://example.invalid/a"}}
    assert lookup_url(catalog, "unet", "a.safetensors") == "https://example.invalid/a"
    assert lookup_url(catalog, "vae", "a.safetensors") is None


def test_iter_missing(tmp_path):
    present = tmp_path / "vae" / "ok.safetensors"
    present.parent.mkdir(parents=True)
    present.write_bytes(b"x")
    items = [
        FetchItem(str(present.parent), "ok.safetensors", "https://example.invalid/ok"),
        FetchItem(str(present.parent), "missing.safetensors", "https://example.invalid/miss"),
    ]
    missing = list(iter_missing(items))
    assert [m.filename for m in missing] == ["missing.safetensors"]


def test_load_catalogs_from_explicit_paths():
    catalog = load_catalogs([FIXTURES / "source_2.json", FIXTURES / "source.json"])
    assert "mine.safetensors" in catalog["checkpoints"]
    assert "flux1-dev.safetensors" in catalog["checkpoints"]


def test_existing_catalog_paths_skips_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("ZHANZHI_ROOT", str(tmp_path))
    monkeypatch.setenv("MODAL_CNB_OVERLAY", str(tmp_path / "overlay"))
    (tmp_path / "overlay").mkdir()
    (tmp_path / "overlay" / "source_2.json").write_text("{}", encoding="utf-8")
    paths = existing_catalog_paths(tmp_path)
    assert paths[0].name == "source_2.json"
