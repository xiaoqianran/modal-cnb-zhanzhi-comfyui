"""R2VA execution-local audit only; never inherit T2VA portable eligibility.

Bind the actual configuration, implementation, visual clocks, plans and
derived cache contents. This is not a modular stage/cold-resume certificate.
"""
from dataclasses import asdict
import hashlib
from pathlib import Path

import torch

from . import veda_r2va_bundle as bundles
from .veda_vendor.veda import tiling, mask, predictor
from . import veda_r2va_flex as flex, veda_flex

_NATIVE_ATTEND = flex.attend
_NATIVE_FLEX = veda_flex.flex_attention
_FUNCTIONS = tuple((owner, name, getattr(owner, name)) for owner, names in (
    (flex, ("attend", "tile_layout")),
    (veda_flex, ("compiled_flex", "flex_block_mask", "_head_chunks")),
    (tiling, ("gather_tiles", "scatter_tiles_", "build_tile_layout", "least_padding_shape")),
    (mask, ("column_blocks", "select_video_blocks", "dense_block_mask")),
    (predictor, ("pool_tiles",)),
    (predictor.LayerPredictor, ("forward", "embed")),
    (predictor.TileScorePredictor, ("scores",)),
) for name in names)


def executable_issues(loaded, *, require_compiled=False):
    """Unknown executable modifications remain runnable, but not certified."""
    from . import veda_r2va_runtime
    issues = ["replaced_" + name for owner, name, original in _FUNCTIONS
              if getattr(owner, name, None) is not original]
    if veda_r2va_runtime.attend is not _NATIVE_ATTEND:
        issues.append("replaced_runtime_attend")
    compiled = veda_flex._COMPILED
    if ((compiled is None and require_compiled) or
            (compiled is not None and (not callable(compiled)
             or getattr(compiled, "_torchdynamo_orig_callable", None) is not _NATIVE_FLEX))):
        issues.append("unverified_compiled_Flex_owner")
    if loaded is not None:
        network = loaded.predictor
        if (type(network) is not predictor.TileScorePredictor
                or type(network.layers) is not torch.nn.ModuleList or len(network.layers) != 50):
            issues.append("unverified_predictor_architecture_owner")
        for child in network.modules():
            if (type(child) not in (predictor.TileScorePredictor, predictor.LayerPredictor, torch.nn.ModuleList)
                    or child.training or child._buffers or child._forward_hooks or child._forward_pre_hooks
                    or child._backward_hooks or child._backward_pre_hooks
                    or any(name in vars(child) for name in ("forward", "embed", "scores", "_call_impl", "_compiled_call_impl"))):
                issues.append("unverified_predictor_callable_or_hook")
    return sorted(set(issues))


def tensor_hash(value):
    data = value.detach().to("cpu").contiguous()
    return {"dtype": str(data.dtype), "shape": list(data.shape),
            "sha256": hashlib.sha256(data.view(torch.uint8).numpy().tobytes()).hexdigest()}


def parameter_hash(network):
    return bundles.digest({name: tensor_hash(value) for name, value in network.named_parameters()})


def implementation():
    root = Path(__file__).resolve().parent
    names = ("veda_r2va_bundle.py", "veda_r2va_layout.py", "veda_r2va_flex.py",
             "veda_r2va_runtime.py", "veda_r2va_identity.py", "veda_flex.py", "h3_core_compat.py",
             "veda_vendor/veda/tiling.py", "veda_vendor/veda/mask.py",
             "veda_vendor/veda/predictor.py", "veda_vendor/veda/plan.py")
    return {name: bundles.file_sha(root / name) for name in names}


def layout_record(native, spec):
    return {"layout": asdict(spec), "native_signature": list(native.signature),
            "native_segments": [list(row) for row in native.segments],
            "original_position_ids": tensor_hash(native.position_ids)}


def cache_records(cache):
    """Rebuild from native spans on CPU; do not discard a mutated live cache."""
    records = []
    for (spans, sequence, device), actual in cache.items():
        expected = tiling.build_tile_layout(spans, sequence, sequence, "cpu")
        if type(actual) is not tiling.TileLayout or set(vars(actual)) != set(vars(expected)):
            raise ValueError("R2VA tile cache has unknown state")
        values = {}
        for name, wanted in vars(expected).items():
            value = getattr(actual, name)
            if isinstance(wanted, torch.Tensor):
                if (type(value) is not torch.Tensor or value.device != device or value.dtype != wanted.dtype
                        or value.shape != wanted.shape or not torch.equal(value.detach().cpu(), wanted)):
                    raise ValueError("R2VA tile cache changed: " + name)
                values[name] = tensor_hash(value)
            elif type(value) is not type(wanted) or value != wanted:
                raise ValueError("R2VA tile cache changed: " + name)
            else:
                values[name] = value
        records.append({"spans": [asdict(span) for span in spans], "sequence": sequence,
                        "content_sha256": bundles.digest(values)})
    return records


def execution_identity(runtime):
    if runtime.configuration() != runtime.bound_configuration or implementation() != runtime.bound_implementation:
        raise ValueError("R2VA configuration/implementation changed during execution")
    if (bundles.file_sha(runtime.bundle.path) != runtime.bundle.sha256
            or bundles.digest(runtime.bundle.metadata) != runtime.bound_configuration["metadata_sha256"]):
        raise ValueError("R2VA predictor file/metadata changed during execution")
    loaded_hash = None
    if runtime.loaded is not None:
        loaded_hash = parameter_hash(runtime.loaded.predictor)
        if loaded_hash != runtime.loaded.parameter_sha256:
            raise ValueError("R2VA loaded predictor parameters changed")
    table = bundles.read_plans(runtime.bundle.metadata)
    from .veda_r2va_layout import select_plan, describe
    for native, spec in runtime.layout_cache.items():
        current = layout_record(native, describe(native, native.seq_len))
        if current != runtime.layout_bindings.get(native) or current["layout"] != asdict(spec):
            raise ValueError("R2VA bound native layout/position_ids changed")
    issues = sorted(set(executable_issues(runtime.loaded, require_compiled=bool(runtime.sparse_calls)))
                    | runtime.unverified_executables)
    plans = []
    for grid, choice in runtime.choices.items():
        expected = select_plan(table, grid, runtime.plan_mode)
        # TilePlan contains a derived group cache; compare numerical data,
        # not allocation or cached Tensor equality.
        if (choice.actual_grid != expected.actual_grid or choice.exact != expected.exact
                or choice.plan.to_json() != expected.plan.to_json()):
            raise ValueError("R2VA selected plan changed")
        for (layer, device), groups in choice.plan._groups.items():
            wanted = expected.plan.head_groups(layer, "cpu")
            if len(groups) != len(wanted) or any(
                    a.shape != b.shape or a.heads.device != torch.device(device)
                    or a.heads.dtype != b.heads.dtype or not torch.equal(a.heads.detach().cpu(), b.heads)
                    for a, b in zip(groups, wanted, strict=True)):
                raise ValueError("R2VA cached head assignment changed")
        plans.append({**choice.report(), "content_sha256": bundles.digest(choice.plan.to_json())})
    result = {"schema": "t8.veda-r2va.execution-local-content.v1",
              "configuration": runtime.bound_configuration, "implementation": runtime.bound_implementation,
              "loaded_parameter_sha256": loaded_hash, "observed_layouts": list(runtime.observed_layouts.values()),
              "observed_plans": plans, "tile_caches": cache_records(runtime.tile_cache),
              "verified_executable_owner": not issues, "unverified_executable_reasons": issues,
              "torch_version": str(torch.__version__), "cuda_version": torch.version.cuda,
              "portable_cache_reuse": False, "inherits_T2VA_eligibility": False,
              "boundary": "Execution-local R2VA audit, not a portable Stage or cold-resume identity"}
    return {**result, "sha256": bundles.digest(result)}
