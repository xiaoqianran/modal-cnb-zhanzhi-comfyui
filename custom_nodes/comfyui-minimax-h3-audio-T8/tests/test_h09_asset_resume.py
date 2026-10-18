import hashlib
import io

import pytest
from tools import prepare_h09_freevideo_int8 as p


@pytest.mark.parametrize("prefix", [b"", b"ori"])
def test_actual_resume_accepts_our_empty_or_nonempty_partial_without_truncation(tmp_path, monkeypatch, prefix):
    data = b"original fixed asset"
    row = dict(file="int8-convrot/cache/blocks/00.safetensors", bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    target = p.target(tmp_path, row["file"])
    target.parent.mkdir(parents=True)
    partial = target.with_suffix(target.suffix+".partial")
    partial.write_bytes(prefix)
    class Response(io.BytesIO):
        status = 206 if prefix else 200
        headers = {"Content-Range": f"bytes {len(prefix)}-{len(data)-1}/{len(data)}"}
    calls = []
    def request(url, headers=None):
        calls.append((url,headers))
        return Response(data[len(prefix):])
    monkeypatch.setattr(p,"request",request)
    assert p.fetch_asset(tmp_path,row) == len(data)
    assert target.read_bytes() == data and not partial.exists() and len(calls) == 1
    assert p.fetch_asset(tmp_path,row) == len(data) and len(calls) == 1


def test_resume_keeps_bad_range_and_bad_sha_partials_for_inspection(tmp_path, monkeypatch):
    data = b"original fixed asset"
    row = dict(file="int8-convrot/cache/root.safetensors", bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    target = p.target(tmp_path,row["file"])
    target.parent.mkdir(parents=True)
    partial = target.with_suffix(target.suffix+".partial")
    partial.write_bytes(b"ori")
    class Bad(io.BytesIO):
        status = 200
        headers = {}
    monkeypatch.setattr(p,"request",lambda *args: Bad(data[3:]))
    with pytest.raises(ValueError,match="exact fixed byte range"):
        p.fetch_asset(tmp_path,row)
    assert partial.read_bytes() == b"ori" and not target.exists()
    class Corrupt(io.BytesIO):
        status = 206
        headers = {"Content-Range": f"bytes 3-{len(data)-1}/{len(data)}"}
    monkeypatch.setattr(p,"request",lambda *args: Corrupt(b"x"*(len(data)-3)))
    with pytest.raises(ValueError,match="SHA verification"):
        p.fetch_asset(tmp_path,row)
    assert partial.read_bytes() == b"ori"+b"x"*(len(data)-3) and not target.exists()
