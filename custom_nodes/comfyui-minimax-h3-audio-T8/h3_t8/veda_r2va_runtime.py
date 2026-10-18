"""Opt-in per-MODEL R2VA predictor route; preserve foreign owners/masks."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
import time
import warnings
import weakref

import torch

from .h3_core_compat import plain_attention_backend, set_h3_attention_backend
from .patch_stack_policy import warn_patch_stack
from .veda_flex import require_flex_runtime
from . import veda_r2va_bundle as bundles
from .veda_r2va_flex import attend
from .veda_r2va_layout import describe, select_plan
from .veda_vendor.veda.mask import Budget
from . import veda_r2va_identity as identity


def budget(text, metadata, prefix):
    text = str(text).strip().lower()
    if text == "trained":
        return bundles.trained_budget(metadata, prefix)
    if text in ("dense", "0%"):
        return Budget(ratio=1.)
    if not text.isdigit() or not 1 <= int(text) <= 4096:
        raise ValueError("Budget must be trained, dense/0%, or 1..4096 key tiles")
    return Budget(tiles=float(text))


@dataclass
class R2VARuntime:
    bundle: bundles.R2VABundleRef
    mode: str
    plan_mode: str
    generated: Budget
    reference: Budget
    max_copy_mib: int
    previous_backend: str | None
    loaded: object = None
    bypass_reason: str | None = None
    calls: int = 0
    sparse_calls: int = 0
    delegates: dict = field(default_factory=dict)
    choices: dict = field(default_factory=dict)
    tile_cache: dict = field(default_factory=dict)
    layout_cache: object = field(default_factory=weakref.WeakKeyDictionary)
    layout_bindings: object = field(default_factory=weakref.WeakKeyDictionary)
    statistics: dict = field(default_factory=dict)
    failure: str | None = None
    attention_host_dispatch_seconds: float = 0.
    unverified_executables: set = field(default_factory=set)
    bound_configuration: dict = field(default_factory=dict)
    bound_implementation: dict = field(default_factory=dict)
    observed_layouts: dict = field(default_factory=dict)

    def configuration(self):
        return {"schema": "t8.veda-r2va.configuration.v1", "bundle_sha256": self.bundle.sha256,
                "metadata_sha256": bundles.digest(self.bundle.metadata), "mode": self.mode,
                "plan_mode": self.plan_mode, "generated_budget": vars(self.generated),
                "reference_budget": vars(self.reference), "max_copy_mib": self.max_copy_mib,
                "previous_backend": self.previous_backend, "requested_sparse_kernel": "t8_pytorch_flex_not_upstream_int8"}

    def snapshot(self):
        config = self.configuration()
        try:
            execution = identity.execution_identity(self)
        except Exception as error:
            self.failure = f"{type(error).__name__}: {error}"
            raise
        verified = execution["verified_executable_owner"]
        return {**config, "schema": "t8.veda-r2va.audit.v1",
                "configuration_sha256": bundles.digest(config),
                "status": "failed" if self.failure else
                          "bypassed_owner_preserved" if self.bypass_reason else
                          "unverified_executable_preserved" if not verified and self.sparse_calls else
                          "observed_sparse_experimental" if self.sparse_calls else
                          "observed_dense_delegate" if self.calls else "not_executed",
                "bypass_reason": self.bypass_reason, "calls": self.calls,
                "sparse_calls": self.sparse_calls if verified else 0,
                "sparse_attempts": self.sparse_calls,
                "unverified_sparse_calls": self.sparse_calls if not verified else 0,
                "delegated_calls": sum(self.delegates.values()),
                "delegate_reasons": dict(self.delegates), "failure": self.failure,
                "plans": [c.report() for c in self.choices.values()],
                "tile_layouts": list(self.statistics.values()),
                "skipped_references": [list(row) for spec in self.layout_cache.values() for row in spec.skipped],
                "attention_host_dispatch_seconds": round(self.attention_host_dispatch_seconds, 6),
                "timing_boundary": "Host dispatch, no CUDA synchronization; not GPU latency or speedup",
                "executed_sparse_kernel": "t8_pytorch_flex_not_upstream_int8" if self.sparse_calls and verified else None,
                "execution_identity": execution,
                "quality_accepted": False, "end_to_end_speedup_verified": False,
                "stage_portability": "execution_local_only_no_legacy_T2VA_or_cold_resume_eligibility"}


def apply_r2va(model, bundle, *, mode="report_only", plan_mode="strict_exact",
               generated_budget="trained", reference_budget="trained", max_copy_mib=64):
    if type(bundle) is not bundles.R2VABundleRef or mode not in ("report_only", "apply_exp"):
        raise ValueError("Use the R2VA Bundle and an explicit supported mode")
    if plan_mode not in ("strict_exact", "nearest_exp") or not 1 <= max_copy_mib <= 256:
        raise ValueError("Invalid R2VA plan mode/copy budget")
    fresh = bundles.inspect_bundle(bundle.path)
    if fresh.sha256 != bundle.sha256 or fresh.metadata != bundle.metadata:
        raise ValueError("R2VA Bundle content/metadata changed")
    generated = budget(generated_budget, bundle.metadata, "target")
    reference = budget(reference_budget, bundle.metadata, "ref")
    core = model.get_model_object("diffusion_model")
    blocks = getattr(core, "blocks", None)
    if blocks is None or len(blocks) != 50 or any(
            getattr(b.attn, "heads", None) != 56 or getattr(b.attn, "head_dim", None) != 128 for b in blocks):
        raise ValueError("R2VA Veda requires native H3 50-layer 56x128 attention")
    options = model.model_options.get("transformer_options", {})
    patches = options.get("patches_replace", {})
    if not isinstance(patches, Mapping):
        raise TypeError("MODEL patches_replace must be a mapping")
    previous = options.get("optimized_attention_override")
    if previous is not None and not callable(previous):
        raise TypeError("Existing attention owner must be callable")
    backend = None if previous is None else plain_attention_backend(previous)
    bypass = []
    if any(bool(v) for v in patches.values()):
        bypass.append("existing_DiT_patch_owner")
    if previous is not None and backend is None:
        bypass.append("unverified_attention_owner")
    reason = ",".join(bypass) or None
    runtime = R2VARuntime(bundle, mode, plan_mode, generated, reference, int(max_copy_mib), backend,
                          bypass_reason=reason)
    runtime.bound_configuration = runtime.configuration()
    runtime.bound_implementation = identity.implementation()
    if bundle.sha256 != bundles.OFFICIAL_SHA256:
        warn_patch_stack("R2VA predictor is not the pinned official preview; content checked, quality unverified")
    if reason:
        warn_patch_stack("R2VA Veda preserves " + reason + "; no sparse coverage claim")
        return model.clone(), runtime
    if mode == "apply_exp":
        from comfy.cli_args import enables_dynamic_vram
        if os.name == "nt" and enables_dynamic_vram():
            raise RuntimeError("R2VA Flex requires --disable-dynamic-vram on this Windows stack; MODEL unchanged")
        require_flex_runtime(torch.device(model.load_device))
        runtime.loaded = bundles.load(bundle)
    table = bundles.read_plans(bundle.metadata)
    cloned = model.clone()

    def delegate(q, k, v, heads, **kwargs):
        from comfy.ldm.modules import attention as core_attention
        kwargs["_inside_attn_wrapper"] = True
        if previous is not None:
            return previous(core_attention.optimized_attention, q, k, v, heads, **kwargs)
        return core_attention.optimized_attention(q, k, v, heads, **kwargs)

    def route(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False,
              skip_output_reshape=False, transformer_options=None, **kwargs):
        opts = transformer_options or {}
        layout, layer_index = opts.get("minimax_h3_layout"), opts.get("block_index")
        call = dict(mask=mask, attn_precision=attn_precision, skip_reshape=skip_reshape,
                    skip_output_reshape=skip_output_reshape, transformer_options=transformer_options, **kwargs)
        if layout is None or layer_index is None:
            return delegate(q, k, v, heads, **call)
        runtime.calls += 1
        try:
            def dense(reason):
                runtime.delegates[reason] = runtime.delegates.get(reason, 0) + 1
                return delegate(q, k, v, heads, **call)
            sequence = getattr(layout, "seq_len", None)
            if q.ndim == 4 and q.shape[-2] != sequence:
                return dense("partial_query_preserved")
            if (not skip_reshape or skip_output_reshape or q.ndim != 4
                    or q.shape[:2] != (1, 56) or heads != 56 or q.shape[-1] != 128
                    or q.shape != k.shape or q.shape != v.shape
                    or type(layer_index) is not int or not 0 <= layer_index < 50):
                return dense("unsupported_attention_contract_preserved")
            # A mask/Relay bias must never be dropped to force sparse attention.
            if mask is not None:
                return dense("mask_preserved")
            try:
                spec = runtime.layout_cache.get(layout)
            except TypeError:
                spec = None
            if spec is None:
                spec = describe(layout, sequence)
                record = identity.layout_record(layout, spec)
                runtime.observed_layouts[bundles.digest(record)] = record
                try:
                    runtime.layout_cache[layout] = spec
                    runtime.layout_bindings[layout] = record
                except TypeError:
                    pass
            choice = runtime.choices.get(spec.target.grid)
            if choice is None:
                choice = select_plan(table, spec.target.grid, plan_mode)
                runtime.choices[spec.target.grid] = choice
                if not choice.exact:
                    warnings.warn("R2VA Veda uses nearest_exp: " + str(choice.report()), RuntimeWarning, stacklevel=2)
            if mode == "report_only":
                return dense("report_only")
            started = time.monotonic()
            runtime.unverified_executables.update(identity.executable_issues(runtime.loaded))
            output = attend(q[0].transpose(0, 1), k[0].transpose(0, 1), v[0].transpose(0, 1),
                            layer_index=layer_index, spec=spec, choice=choice,
                            predictor=runtime.loaded.predictor, generated_budget=generated,
                            reference_budget=reference, max_copy_mib=max_copy_mib,
                            tile_cache=runtime.tile_cache, statistics=runtime.statistics)
            runtime.attention_host_dispatch_seconds += time.monotonic() - started
            runtime.unverified_executables.update(identity.executable_issues(runtime.loaded, require_compiled=True))
            runtime.sparse_calls += 1
            return output.reshape(1, sequence, heads * 128)
        except Exception as error:
            runtime.failure = f"{type(error).__name__}: {error}"
            raise

    set_h3_attention_backend(cloned, route)
    return cloned, runtime
