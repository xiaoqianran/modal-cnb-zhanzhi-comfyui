from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "patches"))

from prefetch import collect_items, main  # noqa: E402


def test_collect_items_dedupes_and_applies_extra(tmp_path):
    script = tmp_path / "init.sh"
    extra = tmp_path / "extra.sh"
    script.write_text(
        'aria2c -x 4 -s 4 -c -d "/models/vae" -o "a.safetensors" "https://example.invalid/a"\n',
        encoding="utf-8",
    )
    extra.write_text(
        'aria2c -x 4 -s 4 -c -d "/models/vae" -o "a.safetensors" "https://example.invalid/a-dup"\n'
        'aria2c -x 4 -s 4 -c -d "/models/loras" -o "b.safetensors" "https://example.invalid/b"\n',
        encoding="utf-8",
    )
    items = collect_items(script, extra, str(tmp_path / "models"))
    by_name = {i.filename: i for i in items}
    assert by_name["a.safetensors"].url.endswith("/a")
    assert "b.safetensors" in by_name


def test_prefetch_dry_run(tmp_path, capsys):
    script = tmp_path / "初始化下载"
    script.write_text(
        'aria2c -x 4 -s 4 -c -d "/models/vae" -o "a.safetensors" "https://example.invalid/a"\n',
        encoding="utf-8",
    )
    code = main(
        [
            "--script",
            str(script),
            "--root",
            str(tmp_path / "models"),
            "--dry-run",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "1 to fetch" in out
    assert "a.safetensors" in out
