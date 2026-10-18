import hashlib
import io
import sys
from types import ModuleType

import pytest
from tools import prepare_h09_int8_runtime as p


def test_task_aliases_union_exact_tables_without_duplicate_download_or_conflicts(monkeypatch):
    table = dict(directory="same", identity={"clock": [1.]}, files=[])
    calls = []
    def required(*args, **kwargs):
        calls.append((args[4], kwargs["reference_audio_t"]))
        return [(table, "sampling")]
    monkeypatch.setattr(p, "required", required)
    result = p.select_tables({}, {}, ["light"], ["i2va", "fl2va", "ref2va"])
    assert result == {"same": (table, "sampling")}
    assert calls == [("i2va", 1.), ("fl2va", 1.), ("ref2va", 1.)]
    monkeypatch.setattr(p, "required", lambda *a, **k: [(table, "sampling"), (dict(table, identity={}), "sampling")])
    with pytest.raises(ValueError, match="Conflicting"):
        p.select_tables({}, {}, ["light"], ["i2va"])


@pytest.mark.parametrize("prefix", [b"", b"ori"])
def test_new_table_fetch_resumes_empty_and_nonempty_partials_with_full_hash(tmp_path, monkeypatch, prefix):
    data = b"original exact table"
    row = dict(file="test/00.safetensors", bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    bank = next(iter(p.REVISIONS))
    table = dict(identity={"clock": [1.]}, download=dict(repo="OpenVDN/vdn-minimax-h3-edge", prefix=bank, revision=p.REVISIONS[bank]))
    official = ModuleType("freevideo_engine.adaln_assets")
    def check_table(path, actual, identity):
        assert identity == table["identity"]
        if path.stat().st_size != actual["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != actual["sha256"]:
            raise ValueError("bad SHA")
    official.check_table = check_table
    monkeypatch.setitem(sys.modules, "freevideo_engine.adaln_assets", official)
    path = p.table_path(tmp_path, row["file"])
    path.parent.mkdir()
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_bytes(prefix)
    class Response(io.BytesIO):
        status = 206 if prefix else 200
        headers = {"Content-Range": f"bytes {len(prefix)}-{len(data)-1}/{len(data)}"}
    calls = []
    def urlopen(request, timeout):
        calls.append(request.full_url)
        return Response(data[len(prefix):])
    monkeypatch.setattr(p.urllib.request, "urlopen", urlopen)
    p.fetch_table(table, row, tmp_path)
    assert path.read_bytes() == data and not partial.exists()
    p.fetch_table(table, row, tmp_path)
    assert len(calls) == 1
    with pytest.raises(ValueError, match="Unpinned"):
        p.fetch_table(dict(table, download=dict(table["download"], revision="unreviewed")), row, tmp_path)
