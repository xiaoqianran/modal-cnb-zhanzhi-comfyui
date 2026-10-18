"""A timestamp is not a content identity, including Windows creation-time stamps."""
import hashlib
from pathlib import Path

import pytest

from h3_audio_t8_pkg import wuli_native as wuli


def test_same_size_restored_stat_requires_new_content_hash(tmp_path, monkeypatch):
    path = tmp_path / "heads.safetensors"
    path.write_bytes(b"correct")
    expected_stat = path.stat()
    original_stat = Path.stat
    monkeypatch.setitem(wuli.ASSETS, "widen", hashlib.sha256(b"correct").hexdigest())

    # Model a Windows creation time + restored mtime with unchanged length.
    # File reads are real; only the identity signal being disproved is frozen.
    def stable_stat(self, *args, **kwargs):
        if self == path:
            return expected_stat
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stable_stat)
    assert wuli.verified_asset(path, "widen")["sha256"] == wuli.ASSETS["widen"]
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA"):
        wuli.verified_asset(path, "widen")
