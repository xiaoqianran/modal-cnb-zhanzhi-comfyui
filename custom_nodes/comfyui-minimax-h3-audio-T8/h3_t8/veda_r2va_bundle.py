"""Separate R2VA loader; never relax the legacy T2VA bundle contract.

Predictor format/FP8 convention: Veda-Sparse/Miowtion (MIT).
Weights are external, under the MiniMax H3 Community License.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

import torch
from safetensors import safe_open

from .veda_vendor.veda import mask, plan, predictor

OFFICIAL_REVISION = "1598b407905b7c0af85aa0c13acdfa6f01ff2982"
OFFICIAL_SHA256 = "23edace948693772be33d5cc945d302d2b037a29bd44bd57071bfbdd8b02517d"
OFFICIAL_FILENAME = "minimax_h3_r2va_veda_preview_fp8.safetensors"
FORMAT = "miowtion-veda-predictor-v1"
DTYPES = {"float8_e4m3fn": "F8_E4M3", "bfloat16": "BF16",
          "float16": "F16", "float32": "F32"}
SCALE_SUFFIX = ".__scale"


def file_sha(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode()).hexdigest()


def trained_budget(metadata, prefix):
    kind = metadata.get(prefix + "_budget_kind")
    value = float(metadata.get(prefix + "_budget_value", "nan"))
    if kind not in ("tiles", "ratio") or not math.isfinite(value) or value <= 0:
        raise ValueError("R2VA predictor needs positive target/ref budgets")
    if kind == "ratio" and value > 1:
        raise ValueError("R2VA predictor keep ratio must not exceed one")
    return mask.Budget(**{kind: value})


def read_plans(metadata):
    rows = json.loads(metadata["plans"])
    if not isinstance(rows, dict) or not rows:
        raise ValueError("R2VA predictor has no embedded plans")
    result = []
    for name, row in rows.items():
        p = plan.TilePlan.from_json(row)
        if (p.geometry != name or len(p.grid) != 3
                or any(type(x) is not int or x <= 0 for x in p.grid)
                or p.num_layers != 50 or not p.shapes
                or any(s.t <= 0 or s.h <= 0 or s.w <= 0 for s in p.shapes)
                or any(len(r) != 56 or any(type(i) is not int or not 0 <= i < len(p.shapes)
                                          for i in r) for r in p.head_shape)):
            raise ValueError("R2VA embedded plan geometry/heads are invalid")
        result.append(p)
    return plan.PlanTable(result)


@dataclass(frozen=True)
class R2VABundleRef:
    path: Path
    sha256: str
    metadata: dict

    def report(self):
        return {"schema": "t8.veda-r2va.bundle.v1", "file": self.path.name,
                "sha256": self.sha256, "official_preview": self.sha256 == OFFICIAL_SHA256,
                "trained_target_budget": vars(trained_budget(self.metadata, "target")),
                "trained_reference_budget": vars(trained_budget(self.metadata, "ref")),
                "plans": {name: list(p.grid) for name, p in read_plans(self.metadata).plans.items()},
                "status": "bundle_only_not_an_inference_result",
                "weights_license": "MiniMax H3 Community License"}


def inspect_bundle(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".safetensors":
        raise ValueError("Select an existing R2VA predictor safetensors, not a DiT/LoRA")
    with safe_open(path, framework="pt", device="cpu") as f:
        m = dict(f.metadata() or {})
        if (m.get("format") != FORMAT or
                tuple(m.get(k) for k in ("num_layers", "num_heads", "head_dim")) != ("50", "56", "128")
                or m.get("tile_conditions", "").lower() != "true"):
            raise ValueError("Use the R2VA Veda predictor with tiled visual conditions (50 x 56 x 128)")
        trained_budget(m, "target")
        trained_budget(m, "ref")
        read_plans(m)
        stored = m.get("dtype")
        if stored not in DTYPES:
            raise ValueError("Unsupported R2VA predictor storage dtype")
        shapes = {f"layers.{i}.proj_{side}": [56, 384, 128]
                  for i in range(50) for side in ("q", "k")}
        if stored == "float8_e4m3fn":
            shapes.update({k + SCALE_SUFFIX: [56] for k in list(shapes)})
        if set(f.keys()) != set(shapes):
            raise ValueError("R2VA predictor tensor/scale keys do not match its declared architecture")
        for key, shape in shapes.items():
            view = f.get_slice(key)
            expected = "F32" if key.endswith(SCALE_SUFFIX) else DTYPES[stored]
            if view.get_shape() != shape or view.get_dtype() != expected:
                raise ValueError("R2VA predictor has wrong tensor shape/dtype: " + key)
    return R2VABundleRef(path, file_sha(path), m)


@dataclass
class LoadedR2VA:
    predictor: object
    plans: object
    metadata: dict
    parameter_sha256: str


def load(reference):
    if type(reference) is not R2VABundleRef:
        raise TypeError("Use the separate R2VA Bundle output")
    fresh = inspect_bundle(reference.path)
    if fresh.sha256 != reference.sha256 or fresh.metadata != reference.metadata:
        raise ValueError("R2VA predictor changed since Bundle evaluation")
    state = {}
    with safe_open(reference.path, framework="pt", device="cpu") as f:
        for i in range(50):
            for side in ("q", "k"):
                key = f"layers.{i}.proj_{side}"
                values = f.get_tensor(key)
                if reference.metadata["dtype"] == "float8_e4m3fn":
                    scale = f.get_tensor(key + SCALE_SUFFIX)
                    if not bool(torch.isfinite(scale).all()) or not bool((scale > 0).all()):
                        raise ValueError("R2VA per-head scales must be finite and positive")
                    values = values.float() * scale[:, None, None]
                values = values.to(torch.bfloat16)
                if not bool(torch.isfinite(values).all()):
                    raise ValueError("R2VA predictor contains nonfinite projections")
                state[key] = values
    # No random CPU allocation/initialization and no change to caller RNG.
    with torch.device("meta"):
        network = predictor.TileScorePredictor(50, 56, 128)
    network.load_state_dict(state, strict=True, assign=True)
    network.requires_grad_(False).eval()
    if file_sha(reference.path) != reference.sha256:
        raise ValueError("R2VA predictor changed during load")
    from .veda_r2va_identity import parameter_hash
    return LoadedR2VA(network, read_plans(reference.metadata), dict(reference.metadata), parameter_hash(network))
