"""INT8 producer, immutable inputs and geometry-aware author resource policy.

No engine, Torch, CUDA, network or ComfyUI import at module import time.
Old FP8 descriptors and completion receipts cannot become INT8 by relabelling.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:  # Worker imports the sibling packages without importing ComfyUI.
    from ..freevideo_exp.runtime import canonical, digest, verify_files
except ImportError:
    from freevideo_exp.runtime import canonical, digest, verify_files

REVISION = "ebc94ecdeec3cbfe74040fe69a5116a62bf01dcd"
MODEL_REVISION = "da37681f5a1f7015fdb63482142b865111b687d3"
VDN_REVISION = "30b6b380c2482f3519469350810c2955d8847fd9"
RUNTIME = "t8-freevideo-runtime-int8-v1"


def binding(schema=RUNTIME):
    if schema != RUNTIME:
        raise ValueError("Use the independent prepared INT8 runtime; FP8 families stay separate")
    return dict(runtime=RUNTIME, revision=REVISION, model_revision=MODEL_REVISION,
                request="t8-freevideo-request-int8-v1", stage="t8-freevideo-stage-int8-v1",
                saved="t8-freevideo-saved-int8-v1", precision="int8", reference_audio_t=1.)


def receipt_binding(schema):
    value = binding()
    if schema != value["stage"]:
        raise ValueError("Expected completed INT8 Stage, not FP8 Stage, MID or arbitrary LATENT")
    return value


def validate_manifest(value):
    if (value.get("format") != "freevideo-int8-slim-v1" or value.get("precision") != "int8"
            or value.get("scale_granularity") != "rowwise"
            or value.get("rotation", {}).get("kind") != "convrot"
            or value.get("rotation", {}).get("group") != 256):
        raise ValueError("Prepared INT8 requires rowwise ConvRot group-256, not renamed FP8 weights")
    linears = value.get("linears")
    if not isinstance(linears, dict) or not linears:
        raise ValueError("INT8 manifest has no actual projection targets")
    for name, row in linears.items():
        shape = row.get("weight_shape")
        if (row.get("storage") != "int8" or row.get("convrot_group") != 256
                or not isinstance(shape, list) or len(shape) != 2
                or any(type(n) is not int or n <= 0 for n in shape) or shape[1] % 256
                or row.get("scale_shape") != [1, shape[0]]):
            raise ValueError("INT8 projection storage/rotation/shape mismatch: " + name)
    return value


def validate_config(value, full=False):
    binding(value.get("schema"))
    if tuple(value.get(k) for k in ("freevideo_revision", "vdn_revision", "model_revision")) != (
            REVISION, VDN_REVISION, MODEL_REVISION):
        raise ValueError("INT8 runtime/source pins differ from its independent producer")
    for name in ("python", "source_root", "vdn_root", "cache", "base", "checkpoint", "home", "sampling_root"):
        if not isinstance(value.get(name), str) or not Path(value[name]).is_absolute():
            raise ValueError("INT8 runtime requires an explicit absolute " + name)
    files = value.get("files")
    if (not isinstance(files, list) or not files or value.get("inventory_sha256") !=
            hashlib.sha256(canonical(files).encode()).hexdigest()):
        raise ValueError("INT8 runtime has no intact independent inventory")
    paths = []
    for row in files:
        if (not isinstance(row, dict) or row.get("kind") not in ("source", "weight", "metadata")
                or not isinstance(row.get("path"), str) or not Path(row["path"]).is_absolute()
                or type(row.get("bytes")) is not int or row["bytes"] < 0
                or not isinstance(row.get("sha256"), str) or len(row["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in row["sha256"])):
            raise ValueError("Invalid INT8 inventory row")
        paths.append(str(Path(row["path"]).resolve()))
    if len(paths) != len(set(paths)):
        raise ValueError("INT8 inventory has duplicate physical paths")
    manifest = Path(value["cache"]) / "manifest.json"
    bound = next((row for row in files if Path(row["path"]).resolve() == manifest.resolve()), None)
    if bound is None or digest(manifest) != bound["sha256"]:
        raise ValueError("INT8 manifest is not bound to its original asset inventory")
    validate_manifest(json.loads(manifest.read_text(encoding="utf8")))
    if full:
        verify_files(files)
    return value


def policy_for(hardware, canvas, selected, info, lora_report, *, choose, geometry):
    """Call the pinned author planner with the REAL precision, schedule and refs.

    Keep the returned streaming/pinning/residency decisions. No fixed forced
    placement, request downscale, shortened schedule or borrowed speed claim.
    The caller supplies the isolated, content-verified author implementations.
    """
    admitted = geometry(**canvas)
    if any(admitted[k] != canvas[k] for k in ("width", "height", "frames")):
        raise ValueError("INT8 resource policy cannot silently align or resize an admitted request")
    admitted.update(steps=selected["base_steps"], task=info["task"])
    for key in ("reference_video_tokens", "reference_audio_tokens"):
        count = info[key]
        if type(count) is not int or count < 0:
            raise ValueError("Actual INT8 reference rows must be nonnegative integers")
        admitted[key] = count
    policy = choose(hardware, attention="cudnn", available_backends={"cudnn"}, canvas=admitted,
                    precision="int8", lora_max_block_bytes=lora_report.get("max_block_bytes", 0),
                    lora_root_bytes=lora_report.get("root_bytes", 0))
    if policy.engine.get("linear_compute") != "int8":
        raise ValueError("INT8 resource planner selected different projection arithmetic")
    return policy, admitted


def validate_int8_probes(probes):
    """The legacy finite FP8 check is not evidence for INT8 rotation/GEMM."""
    linear = probes.get("linear", {})
    if (linear.get("backend") != "linear-int8" or linear.get("policy") != "int8-convrot"
            or linear.get("status") != "complete" or linear.get("finite") is not True):
        raise ValueError("INT8 requires an actual linear-int8 ConvRot probe, not an old FP8 probe")
    if probes.get("cudnn", {}).get("backend") != "cudnn":
        raise ValueError("INT8 execution needs its own actual cuDNN probe")
