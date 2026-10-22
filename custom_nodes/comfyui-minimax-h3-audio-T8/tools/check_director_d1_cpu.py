"""Explicit CPU-only scoped checks; does not start or submit to a ComfyUI server."""

import os
from pathlib import Path
import sys

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["OMP_NUM_THREADS"] = "1"
ROOT = Path(__file__).resolve().parents[1]
core_root = ROOT.parents[1] if len(ROOT.parents) > 1 else None
if core_root is not None and (core_root / "comfy").is_dir():
    sys.path.insert(0, str(core_root))
from comfy.cli_args import args  # noqa: E402 -- configure Core CPU before Torch imports

args.cpu = True
# Resolve Core's top-level nodes before tests add the extension's runtime path.
# Otherwise server.py imports h3_t8/nodes.py as an unqualified top-level module.
import nodes as core_nodes  # noqa: E402,F401

sys.path.insert(0, str(ROOT))
import pytest  # noqa: E402
import torch  # noqa: E402

if __name__ == "__main__":
    result = pytest.main(
        # Relocated workspaces may retain pytest-rewritten bytecode containing
        # the old absolute source path. Plain assertions use Python's normal
        # filename repair, keeping inspect/source-identity tests meaningful.
        ["--assert=plain", *(sys.argv[1:] or [str(ROOT / "tests" / "test_director_d1.py"), "-q"])]
    )
    assert not torch.cuda.is_initialized(), "CPU check initialized CUDA"
    raise SystemExit(result)
