"""Explicit native Wuli recipes. Core owns clocks, adapters and PDD head math.

No new checkpoint loader, Diffusers counter, attention selector or sampler loop.
Unknown user patches remain installed; observations never certify their quality.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import struct

import torch

ASSETS = {
    "trunk": "ee16350bd02f46627a15a64ebd37b31f8547dd507855141c9c446a13adead8a1",
    "widen": "eb643e48b5849523ffdbd365977926e6fa9b2e4c8a564f034f665560edb30805",
    "set": "36af67e8b334f89458234b29f80e1b23f7ffba44432c0450af03ee7780b60aa7",
}
def verified_asset(path, role):
    """Hash content on every call; filesystem timestamps are not identities.

    Windows ctime is generally creation time, and mtime can be restored after a
    same-length rewrite. A process-global stat cache can therefore certify stale
    bytes in a later task. Keep the before/after mutation check, but never reuse
    a previous call's digest. This does not certify a later loader's file handle.
    """
    path = Path(path).resolve(strict=True)
    before = path.stat()
    with path.open("rb") as file:
        sha = hashlib.file_digest(file, "sha256").hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("Selected Wuli asset changed while hashing")
    if sha != ASSETS[role]:
        raise ValueError(f"Wrong Wuli {role} content / SHA; ordinary manual loaders remain available")
    return {"role": role, "file": str(path), "bytes": before.st_size, "sha256": sha}


def bounded_header(path):
    path = Path(path)
    with path.open("rb") as file:
        prefix = file.read(8)
        if len(prefix) != 8:
            raise ValueError("Missing safetensors header")
        size = struct.unpack("<Q", prefix)[0]
        if not 2 <= size <= 16 * 1024**2 or size + 8 > path.stat().st_size:
            raise ValueError("Invalid safetensors header length")
        value = json.loads(file.read(size))
    if not isinstance(value, dict):
        raise ValueError("Invalid safetensors header object")
    return value


def bank_span(sigma, sigma_next, shift, heads):
    # Same base-time interval as native FinalLayer; no forward-count step clock.
    def base(s):
        return s / (shift + (1. - shift) * s)
    start, stop = (round((1. - base(s)) * heads) for s in (sigma, sigma_next))
    start = min(start, heads - 1)
    return start, max(stop, start + 1)


@dataclass
class RecipeAudit:
    recipe: str
    grid: tuple
    shift: float
    assets: list = field(default_factory=list)
    registration: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: set = field(default_factory=set)

    def reset(self, *args, **kwargs):
        self.calls.clear()
        self.errors.clear()

    def observe(self, executor, x, timestep, context, transformer_options=None, **kwargs):
        options = transformer_options or {}
        sigma = float(timestep.flatten()[0].detach().cpu()) / 1000.
        actual = options.get("sample_sigmas")
        actual = tuple(float(v) for v in actual.detach().cpu().flatten()) if torch.is_tensor(actual) else ()
        same_grid = len(actual) == len(self.grid) and all(abs(a-b) < 2e-6 for a, b in zip(actual, self.grid))
        index = min(range(len(self.grid)-1), key=lambda i: abs(self.grid[i]-sigma))
        exact = same_grid and abs(self.grid[index]-sigma) < 2e-6
        core = getattr(executor, "class_obj", None)
        head = getattr(core, "final_layer", None)
        shapes = {stream: list(getattr(head, stream + "_out").weight.shape)
                  for stream in ("video", "audio") if hasattr(head, stream + "_out")}
        native = (type(core).__module__ == "comfy.ldm.minimax.model"
                  and getattr(getattr(head, "forward", None), "__func__", None) is not None
                  and head.forward.__func__.__module__ == "comfy.ldm.minimax.model")
        if not exact:
            self.warnings.add("partial_or_changed_grid_NOT_author_native_full_trajectory")
        if not native:
            self.warnings.add("unknown_model_or_head_callable_preserved_NOT_native_head_certification")
        if options.get("minimax_h3_sigma_shift_video") != self.shift or options.get("minimax_h3_sigma_shift_audio") != 3.:
            self.warnings.add("clock_changed_after_recipe")
        record = {"sigma": sigma, "logical_step": index if exact else None,
                  "same_full_grid": same_grid, "head_shapes": shapes, "native_callable": native}
        if exact and self.recipe == "native4":
            record["native_expected_bank_span"] = bank_span(sigma, self.grid[index+1], self.shift, 4)
        try:
            result = executor(x, timestep, context, transformer_options, **kwargs)
        except BaseException as error:
            if len(self.errors) < 16:
                self.errors.append(type(error).__name__)
            raise
        if len(self.calls) < 4096:
            self.calls.append(record)  # only completed delegated calls, not scheduled NFE
        else:
            self.warnings.add("bounded_call_log_truncated")
        return result

    def report(self):
        steps = sorted({c["logical_step"] for c in self.calls if c["logical_step"] is not None})
        return {"schema": "t8.h11.wuli-native.v1", "recipe": self.recipe,
                "author_recipe": {"NFE": len(self.grid)-1, "shift_video": self.shift, "shift_audio": 3.,
                                  "scheduler": "simple", "sampler": "euler", "CFG": 1., "denoise": 1.},
                "sigma_grid": self.grid, "assets": self.assets, "patch_registration": self.registration,
                "completed_model_calls": len(self.calls), "observed_logical_steps": steps,
                "calls": self.calls, "errors": self.errors, "warnings": sorted(self.warnings),
                "full_trajectory_observed": steps == list(range(len(self.grid)-1)),
                "unknown_patches_portable": False, "automatic_quality_acceptance": False,
                "partial_HIGH_or_resume_qualified": False, "new_loader_or_head_math": False}


def native_clock(model, recipe, assets=None, registration=None):
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3SigmaShift
    from comfy_extras.nodes_custom_sampler import BasicScheduler, KSamplerSelect
    from comfy.patcher_extension import CallbacksMP, WrappersMP
    steps, shift = (8, 12.) if recipe == "native8" else (4, 6.)
    patched = MiniMaxH3SigmaShift.execute(model, shift, 3.).result[0]
    sigmas = BasicScheduler.execute(patched, "simple", steps, 1.).result[0]
    grid = tuple(float(v) for v in sigmas)
    # Native simple grid may be float32; compare to author equation, not rounded README.
    expected = tuple(shift * (1-i/steps) / (1+(shift-1)*(1-i/steps)) for i in range(steps+1))
    if len(grid) != len(expected) or any(abs(a-b) > 2e-6 for a, b in zip(grid, expected)):
        raise ValueError("Selected Core simple scheduler does not produce author's native full grid")
    state = RecipeAudit(recipe, grid, shift, assets or [], registration or [])
    if model.model_options.get("transformer_options", {}).get("wrappers") or getattr(model, "patches", {}):
        state.warnings.add("existing_user_patches_preserved_combination_quality_unverified")
    owner = "t8_wuli_audit_" + str(id(state))
    patched.add_wrapper_with_key(WrappersMP.DIFFUSION_MODEL, owner, state.observe)
    patched.add_callback_with_key(CallbacksMP.ON_PRE_RUN, owner, state.reset)
    sampler = KSamplerSelect.execute("euler").result[0]
    return patched, sigmas, sampler, state


def native8(model):
    core = model.get_model_object("diffusion_model")
    table = getattr(core, "adaln_t_table", None)
    if not torch.is_tensor(table) or tuple(table.shape) != (1025, 25):
        raise ValueError("Wuli native8 requires its 1025×25 AdaLN basis; an ordinary 8-column pruned model is not it")
    result = native_clock(model, "native8")
    result[3].warnings.add("basis_shape_does_NOT_prove_entire_checkpoint_SHA_use_matching_Wuli8_file")
    return result


def native4(model, paths):
    """Call native parser/add_patches in trunk -> widen -> absolute set order."""
    from comfy import lora as parser, lora_convert, utils
    from .h3_weight_diagnostics import lora_mapping_diagnostics
    core = model.get_model_object("diffusion_model")
    if torch.is_tensor(getattr(core, "adaln_t_table", None)):
        raise ValueError("Wuli native4 trunk targets original full FL2VA MLP, not a curve-pruned base")
    selected = [verified_asset(paths[role], role) for role in ("trunk", "widen", "set")]
    patched, registration = model, []
    for asset in selected:
        weights, metadata = utils.load_torch_file(asset["file"], safe_load=True, return_metadata=True)
        converted = lora_convert.convert_lora(weights)
        mapping = parser.model_lora_keys_unet(patched.model, {})
        patches = parser.load_lora(converted, mapping)
        candidate = patched.clone()
        applied = candidate.add_patches(patches, 1.)
        diagnostics = lora_mapping_diagnostics(converted, mapping, patches, applied)
        if (diagnostics["converted_unmapped_tensor_count"]
                or set(patches) != set(applied) or not patches):
            raise ValueError("Required Wuli native patch did not fully map: " + json.dumps(diagnostics))
        if metadata:
            candidate.set_attachments("lora_metadata", metadata)
        registration.append({"role": asset["role"], **diagnostics, "strength": 1.})
        patched = candidate
    return native_clock(patched, "native4", selected, registration)
