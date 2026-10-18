"""Explicit native H3 Spark adapter. No installer or global attention mutation.

Kernel/reblock mathematics: zechengtang/Spark-H3, Apache-2.0, fixed v0.1.2.
We load only verified backend source, not its nodes or upstream installer.
Unsupported user hooks/conditions remain on their original path. Actual kernel
errors propagate; delegated calls are never counted as Spark execution.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import importlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys
import types
import zipfile

import torch

ASSET_SHA = "88a2e15be0b6f61ffb62ff1236ffe24f12190e5adbd0058fec110423c4aea770"
WHEEL_SHA = "76f2bbeeeb111b70666ac841279a0a006d931f439e617b95bd9a3dbab5731620"
COMMIT = "1bb4cdb22648314901e4cbe82c3b414aa1f2e769"
KITCHEN = "0.2.37+spark.h3.sm89.cu130.1"
PREFIX = "ComfyUI-Spark-H3/"


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def runtime_manifest(path):
    config = Path(path).resolve(strict=True)
    if config.stat().st_size > 64_000:
        raise ValueError("Spark runtime manifest exceeds 64KB")
    data = json.loads(config.read_text(encoding="utf-8"))
    if (data.get("schema") != "t8.h11.spark-runtime.v1"
            or data.get("upstream_commit") != COMMIT
            or data.get("required_kitchen") != KITCHEN):
        raise ValueError("Unrecognized Spark producer identity")
    archive = Path(data["archive"]["path"]).resolve(strict=True)
    if data["archive"]["sha256"] != ASSET_SHA or digest(archive) != ASSET_SHA:
        raise ValueError("Spark official archive SHA mismatch")
    source = Path(data["source_root"]).resolve(strict=True)
    expected = {}
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            rel = item.filename.removeprefix(PREFIX)
            selected = rel in {"comfyui_backend.py", "comfyui_reblock_plan.py", "LICENSE"}
            selected |= rel.startswith("h3_sparse_attention/") and rel.endswith(".py")
            if selected:
                expected[rel] = hashlib.sha256(bundle.read(item)).hexdigest()
    if data.get("source_files") != expected:
        raise ValueError("Spark source inventory differs from the fixed official archive")
    for rel, sha in expected.items():
        target = (source / rel).resolve(strict=True)
        if not target.is_relative_to(source) or target.is_symlink() or digest(target) != sha:
            raise ValueError("Spark source content changed: " + rel)
    if (data["wheel"]["sha256"] != WHEEL_SHA
            or digest(Path(data["wheel"]["path"]).resolve(strict=True)) != WHEEL_SHA):
        raise ValueError("Spark wheel SHA mismatch")
    return data


def preflight(path):
    data = runtime_manifest(path)
    try:
        version = importlib.metadata.version("comfy-kitchen")
    except importlib.metadata.PackageNotFoundError:
        version = None
    wheel_files = installed_wheel_files(data) if version == KITCHEN else {"matched": False, "files": 0}
    return {"schema": "t8.h11.spark-preflight.v1", "upstream_commit": COMMIT,
            "official_archive_sha256": ASSET_SHA, "installed_kitchen": version,
            "required_kitchen": KITCHEN, "wheel_identity_matches": version == KITCHEN,
            "installed_wheel_bytes": wheel_files,
            "target": "Windows SM89 / CUDA13.0 / CP312+abi3",
            "source_files_verified": len(data["source_files"]), "kernel_executed": False,
            "models_loaded_by_preflight": False, "automatic_install": False,
            "new_Spark_weights_required": False, "quality_or_speed_qualified": False}


def installed_wheel_files(data):
    distribution = importlib.metadata.distribution("comfy-kitchen")
    checked, differences = 0, []
    with zipfile.ZipFile(data["wheel"]["path"]) as wheel:
        for item in wheel.infolist():
            if item.is_dir() or item.filename.endswith("/RECORD"):
                continue  # pip rewrites RECORD with its generated installation metadata
            file = Path(distribution.locate_file(item.filename))
            if not file.is_file() or digest(file) != hashlib.sha256(wheel.read(item)).hexdigest():
                differences.append(item.filename)
            checked += 1
    return {"matched": not differences, "files": checked, "differences": differences}


def backend(path):
    data = runtime_manifest(path)
    if importlib.metadata.version("comfy-kitchen") != KITCHEN:
        raise RuntimeError("Install the explicit matched Spark wheel first; no automatic dependency changes")
    if not installed_wheel_files(data)["matched"]:
        raise ValueError("Installed Spark wheel code/native bytes differ from the approved wheel")
    namespace = "_t8_spark_v012_" + hashlib.sha256(data["source_root"].encode()).hexdigest()[:16]
    if namespace not in sys.modules:
        package = types.ModuleType(namespace)
        package.__path__ = [data["source_root"]]
        sys.modules[namespace] = package  # do not execute upstream __init__/node registration
    return importlib.import_module(namespace + ".comfyui_backend")


def sigma_grid(value):
    if not torch.is_tensor(value) or value.ndim != 1 or not 2 <= value.numel() <= 2049:
        raise ValueError("Spark needs an explicit 1D sampler SIGMAS grid (2..2049 values)")
    rows = tuple(float(x) for x in value.detach().cpu().tolist())
    if any(not math.isfinite(x) or x < 0 for x in rows) or any(a <= b for a, b in zip(rows, rows[1:])):
        raise ValueError("Spark sampler grid must be finite, nonnegative and strictly descending")
    return rows


@dataclass
class SparkState:
    grid: tuple
    stage: str
    mode: str
    warmup_steps: int
    dense_layers: int
    min_tokens: int
    upstream: object = field(repr=False)
    controller: object = field(repr=False)
    installed: list = field(default_factory=list)
    preserved: list = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)
    steps_seen: set = field(default_factory=set)
    errors: list = field(default_factory=list)
    run: int = 0
    _options_key: tuple | None = None
    _step: int | None = None
    _layout: tuple | None = None

    def pre_run(self, *_):
        self.run += 1
        self.counts.clear()
        self.reasons.clear()
        self.steps_seen.clear()
        self.errors.clear()
        self.controller.reset()
        self._options_key = self._step = self._layout = None

    def cleanup(self, *_):
        # Release device caches, but retain truthful counters for downstream Audit.
        self.controller.reset()
        self._options_key = self._step = self._layout = None

    def logical_step(self, options):
        sigmas, actual = options.get("sigmas"), options.get("sample_sigmas")
        if not torch.is_tensor(sigmas) or not torch.is_tensor(actual):
            return None, "sampler_grid_not_published"
        # Re-read tensor values: schedulers/hooks may reuse or mutate a tensor;
        # its Python id is not an immutable logical-step identity.
        rows = sigma_grid(actual)
        current = sigmas.detach().flatten().cpu().tolist()
        matches = len(rows) == len(self.grid) and all(
            math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-7) for a, b in zip(rows, self.grid))
        step = None
        if matches and current and all(math.isclose(current[0], x, rel_tol=1e-6, abs_tol=1e-7) for x in current):
            indices = [i for i, x in enumerate(self.grid[:-1])
                       if math.isclose(current[0], x, rel_tol=1e-6, abs_tol=1e-7)]
            if len(indices) == 1:
                step = indices[0]
        self._step = step
        if step is None:
            return None, "off_grid_or_changed_grid"
        if self.controller.evaluation_index != step:
            self.controller.last_reblock = None
        self.controller.evaluation_index = step
        self.steps_seen.add(step)  # repeated EAV calls do not advance logical warmup
        return step, None

    def report(self):
        return {"schema": "t8.h11.spark-audit.v1", "stage": self.stage, "mode": self.mode,
                "upstream_commit": COMMIT, "kernel_identity": KITCHEN, "run": self.run,
                "planned_sigmas": self.grid, "steps_observed": sorted(self.steps_seen),
                "installed_layers": self.installed, "preserved_layers": self.preserved,
                "actual_sparse_calls": self.counts["sparse"], "dense_control_calls": self.counts["dense"],
                "delegated_calls": self.counts["delegate"], "delegate_reasons": dict(self.reasons),
                "errors": list(self.errors), "Spark_executed": self.counts["sparse"] > 0,
                "all_user_effects_qualified": False, "quality_or_speed_qualified": False,
                "unknown_patch_cache_portable": False, "automatic_sampler_changes": False}


def packed_layout(state, layout, sequence, device):
    key = (layout, sequence, device)
    if state._layout is not None and state._layout[0][0] is layout and state._layout[0][1:] == key[1:]:
        return state._layout[1]
    spans = [(int(a), int(b)) for a, b, kind in getattr(layout, "segments", ()) if kind == "video"]
    if len(spans) != 1:
        raise ValueError("Spark layout requires one target video segment")
    start, stop = spans[0]
    positions = getattr(layout, "position_ids", None)
    if not 0 <= start < stop <= sequence or not torch.is_tensor(positions) or positions.shape != (sequence, 3):
        raise ValueError("Invalid published H3 packed layout")
    video = positions[start:stop].to(device=device)
    grid = tuple(int(video[:, axis].unique().numel()) for axis in range(3))
    if math.prod(grid) != stop - start or video.unique(dim=0).shape[0] != stop - start:
        raise ValueError("Target video rows do not form a complete unique dense grid")
    permutation = torch.cat((torch.arange(start, stop, device=device), torch.arange(start, device=device),
                             torch.arange(stop, sequence, device=device)))
    inverse = torch.empty_like(permutation)
    inverse[permutation] = torch.arange(sequence, device=device)
    result = state.upstream.ComfyPackedLayout(permutation, inverse, grid, stop - start,
                                             sequence, video, start)
    state._layout = (key, result)
    return result


def kernel_attention(state, attn, x, rope, options, layer):
    """Native chunked projections + original upstream Spark/reblock backend.

    All projection callables stay on the supplied MODEL. No BSA materializer,
    environment-triggered experimental producer or global attention selector.
    """
    import comfy.model_management
    import comfy.model_prefetch
    from comfy_kitchen.backends import cuda as ck

    comfy.model_management.throw_exception_if_processing_interrupted()
    layout = packed_layout(state, options["minimax_h3_layout"], x.shape[0], x.device)
    heads, dim = int(attn.heads), int(attn.head_dim)
    q = torch.empty((1, x.shape[0], heads, dim), device=x.device, dtype=x.dtype)
    k, v = torch.empty_like(q), torch.empty_like(q)
    qw = comfy.model_management.cast_to(attn.q_norm.weight, device=x.device)
    kw = comfy.model_management.cast_to(attn.k_norm.weight, device=x.device)
    stream = torch.cuda.current_stream(x.device).cuda_stream
    with comfy.model_prefetch.pause_malloc_graph():
        for start in range(0, x.shape[0], 16384):
            comfy.model_management.throw_exception_if_processing_interrupted()
            stop = min(start + 16384, x.shape[0])
            indices = layout.permutation[start:stop]
            projected = attn.qkv_proj(x.index_select(0, indices))
            freqs = rope.index_select(1, indices)
            qc, kc, vc = projected.split(heads * dim, dim=-1)
            qc, kc = (t.view(1, stop - start, heads, dim) for t in (qc, kc))
            ck._C.rms_rope(*(ck._wrap_for_dlpack(t) for t in
                            (qc, kc, freqs, qw, kw, q[:, start:stop], k[:, start:stop])),
                           attn.q_norm.eps, stream, True, freqs.shape[-3] * 2)
            v[:, start:stop].copy_(vc.view(1, stop - start, heads, dim))
    output = state.upstream.comfy_kitchen_spark_attention(state.controller, q, k, v, layout, layer)
    if not state.controller.output_in_original_layout:
        output = output.index_select(1, layout.inverse_permutation)
    state.counts["sparse"] += 1
    return attn.out_proj(output.reshape(x.shape[0], heads * dim))


def delegation_reason(state, block, layer, args):
    x, options = args["img"], args["transformer_options"]
    step, reason = state.logical_step(options)
    if reason:
        return reason
    if state.mode == "dense_control":
        return "explicit_dense_control"
    if step < state.warmup_steps or layer < state.dense_layers or x.shape[0] < state.min_tokens:
        return "explicit_dense_budget"
    if args.get("attention") is not None:
        return "existing_attention_callable"
    if options.get("patches") or any(options.get(k) is not None for k in
            ("attn_mask", "attention_mask", "attention_bias", "attn_bias", "optimized_attention_override")):
        return "existing_attention_patch_mask_or_bias"
    # A monkeypatched attention/DiT forward must not be bypassed by replacing attention.
    for owner in (block, block.attn):
        method = getattr(owner.forward, "__func__", None)
        if getattr(method, "__module__", None) != "comfy.ldm.minimax.model":
            return "non_native_forward_preserved"
    if args.get("rope_freqs") is None or options.get("minimax_h3_layout") is None:
        return "missing_native_rope_or_layout"
    spans = [(a, b) for a, b, kind in options["minimax_h3_layout"].segments if kind == "video"]
    if len(spans) != 1 or spans[0][1] - spans[0][0] < 1024:
        # The pinned fused root projection expects 16 children / 15 root scores.
        # Tiny packed sequences may contain lots of text but fewer video leaves.
        return "video_reblock_below_16_complete_leaves"
    if x.ndim != 2 or x.dtype != torch.bfloat16 or x.device.type != "cuda" or int(block.attn.head_dim) != 128:
        return "unsupported_activation_dtype_device_or_shape"
    if tuple(torch.cuda.get_device_capability(x.device)) != (8, 9):
        return "different_gpu_architecture"
    return None


def block_patch(state, block, layer):
    def patch(args, extra):
        reason = delegation_reason(state, block, layer, args)
        if reason:
            state.counts["dense" if reason == "explicit_dense_control" else "delegate"] += 1
            state.reasons[reason] += 1
            return extra["original_block"](args)

        def attention(x, rope_freqs=None, transformer_options=None):
            return kernel_attention(state, block.attn, x, rope_freqs, transformer_options or {}, layer)

        try:
            return extra["original_block"]({**args, "attention": attention})
        except BaseException as error:
            if len(state.errors) < 16:
                state.errors.append(type(error).__name__)
            raise  # never turn actual kernel/NaN/cancellation failures into dense success
    return patch


def apply_spark(model, sigmas, runtime_config, *, enabled=True, stage="SINGLE", mode="spark",
                warmup_steps=0, dense_layers=1, min_tokens=1024, topk_ratio=.2):
    if not enabled:
        return model, None
    if (not isinstance(stage, str) or not 1 <= len(stage) <= 128 or mode not in {"spark", "dense_control"}
            or type(warmup_steps) is not int or warmup_steps < 0
            or type(dense_layers) is not int or dense_layers < 0
            or type(min_tokens) is not int or min_tokens < 1
            or type(topk_ratio) not in (float, int) or not math.isfinite(topk_ratio) or not 0 < topk_ratio <= 1):
        raise ValueError("Invalid explicit Spark stage/budget settings")
    grid = sigma_grid(sigmas)
    upstream = backend(runtime_config)
    controller = upstream.ComfySparkController(upstream.ComfySparkConfig(
        topk_mode="topk_ratio", topk_ratio=float(topk_ratio)))
    controller.direct_output = True
    diffusion = model.get_model_object("diffusion_model")
    if type(diffusion).__name__ != "MiniMaxH3Model" or not hasattr(diffusion, "blocks"):
        raise TypeError("Spark requires the supplied native ComfyUI MiniMaxH3Model")
    state = SparkState(grid, stage, mode, warmup_steps, dense_layers, min_tokens, upstream, controller)
    patched = model.clone()
    replacements = patched.model_options.get("transformer_options", {}).get("patches_replace", {}).get("dit", {})
    for layer, block in enumerate(diffusion.blocks):
        key = ("double_block", layer)
        if key in replacements:
            state.preserved.append(layer)  # original owner remains installed and actually executes
            continue
        patched.set_model_patch_replace(block_patch(state, block, layer), "dit", "double_block", layer)
        state.installed.append(layer)
    from comfy.patcher_extension import CallbacksMP
    owner = "t8_spark_" + str(id(state))
    patched.add_callback_with_key(CallbacksMP.ON_PRE_RUN, owner, state.pre_run)
    patched.add_callback_with_key(CallbacksMP.ON_CLEANUP, owner, state.cleanup)
    return patched, state
