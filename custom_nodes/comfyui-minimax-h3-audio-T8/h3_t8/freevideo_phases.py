"""Bounded host-phase observation, independent of numeric producer/NFE clocks.

No torch import, CUDA synchronization, compiler invocation, download or updater.
Existing compiler timers are nested host counters; missing is unavailable, NOT0.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import sys
import time

COMPILER_TIMERS = {"frame_compile": "_compile.compile_inner", "backend_compile": "compile_fx_inner",
                   "code_generation": "GraphLowering.codegen", "async_wait": "async_compile.wait"}


def compiler_snapshot():
    module = sys.modules.get("torch._dynamo.utils")
    metrics = getattr(module, "compilation_time_metrics", None)
    if not isinstance(metrics, dict):
        return {"available": False}
    values = {}
    for name, key in COMPILER_TIMERS.items():
        items = metrics.get(key)
        if isinstance(items, list) and all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in items):
            values[name] = sum(items)
    return {"available": True, "nested_host_seconds": values}


class PhaseTimeline:
    def __init__(self, root=None, *, clock=time.monotonic, limit=128):
        self.clock, self.limit = clock, limit
        self.root = Path(root) if root is not None else None
        self.start = self.tick = clock()
        self.phase = "startup"
        self.spans, self.nfe, self.dropped = [], [], 0
        self.compiler_before = compiler_snapshot()

    def write(self):
        if self.root is not None:
            target = self.root / "phase.json"
            temporary = self.root / "phase.partial"
            temporary.write_text(json.dumps(self.snapshot(), allow_nan=False), encoding="utf8")
            os.replace(temporary, target)

    def begin(self, phase):
        if phase not in {"source_preflight", "imports_conditioning", "tables_policy_lora", "engine_load",
                         "sampling", "latent_validation_transport", "release", "receipt_integrity", "complete"}:
            raise ValueError("Unknown bounded worker phase")
        now = self.clock()
        if len(self.spans) < self.limit:
            self.spans.append({"phase": self.phase, "start_seconds": self.tick-self.start,
                               "host_wall_seconds": now-self.tick})
        else:
            self.dropped += 1
        self.phase, self.tick = phase, now
        self.write()

    def step(self, completed, total, seconds):
        if (type(completed) is not int or type(total) is not int or not 1 <= completed <= total <= 2048
                or type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0):
            raise ValueError("Invalid actual completed NFE observation")
        if len(self.nfe) < self.limit:
            self.nfe.append({"completed": completed, "total": total,
                             "author_existing_step_seconds": seconds, "at_host_seconds": self.clock()-self.start})
        else:
            self.dropped += 1
        self.write()

    def snapshot(self):
        after = compiler_snapshot()
        previous = self.compiler_before.get("nested_host_seconds", {})
        delta = {key: value-previous.get(key, 0.) for key, value in after.get("nested_host_seconds", {}).items()
                 if value >= previous.get(key, 0.)}
        return {"schema": "t8.h11.freevideo-phases.v1", "current_phase": self.phase,
                "spans": list(self.spans), "NFE_events": list(self.nfe), "dropped_events": self.dropped,
                "compiler": {"available": after["available"], "nested_host_seconds_delta": delta,
                             "additive_with_sampling_or_each_other": False},
                "current_phase_is_completed_NFE": False, "automatic_restart": False,
                "automatic_compile_or_download": False, "scope": "host wall phase, NOT CUDA completion"}


def phase_report(receipt, decode=None, mux=None):
    """Actual existing receipts only. Do not infer load/compile/transfer from NFE0."""
    decode, mux = decode or {}, mux or {}
    def measured(source, key, scope):
        value = source.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            return {"available": False, "scope": scope}
        return {"available": True, "seconds": value, "scope": scope}
    sampled = receipt.get("sample", {})
    return {"schema": "t8.h11.freevideo-phase-card.v1",
            "timeline": receipt.get("phase_timeline", {"available": False, "reason": "legacy receipt uninstrumented"}),
            "load": measured(receipt, "load_seconds", "author existing engine-load host time"),
            "sampling": measured(sampled, "sample_seconds", "author synchronized sampling total, includes first-step compile"),
            "completed_NFE": receipt.get("completed_nfe"), "actual_step_seconds": sampled.get("step_seconds", []),
            "transfer": measured(sampled.get("offload", {}), "h2d_seconds", "author existing CUDA transfer events; may overlap sampling"),
            "VAE_load": measured(decode, "vae_load_seconds", "explicit connected decode receipt"),
            "VAE_decode": measured(decode, "video_decode_seconds", "explicit connected decode receipt"),
            "mux": measured(mux, "mux_seconds", "explicit connected mux receipt"),
            "times_must_not_be_added": True, "missing_is_zero": False,
            "scheduled_grid_is_completed_NFE": False, "quality_or_speed_claim": False}
