"""Observe real installed INT8 projections and delegated kernels, not config labels.

Only used in the owned isolated worker. No forward hooks, tensor replacement,
Core mutation, cached activation or inferred all-target execution coverage.
"""
from contextlib import contextmanager
import math


def _storage_shape(engine, name, module, field):
    value = getattr(module, field)
    if value.numel() != 0:
        return list(value.shape), False
    # Author Windows streaming deliberately replaces nonresident buffers with
    # zero-storage tensors. Its retained layout verifies the ORIGINAL source,
    # tensor identities, dtype and order before returning their real shapes.
    # An arbitrary empty buffer or a manifest label is not sufficient evidence.
    source = getattr(engine, "stream_weight_source", None)
    parts = name.split(".")
    for end in range(len(parts), 0, -1):
        owner_name = ".".join(parts[:end])
        owner = engine.transformer.get_submodule(owner_name)
        saved = getattr(owner, "_freevideo_streamed_layout", None)
        if saved is None:
            continue
        if (source is None or saved.source() is not source
                or not 0 <= saved.index < len(source.prefixes)
                or source.prefixes[saved.index] != owner_name + "."):
            raise ValueError("INT8 streamed source/order differs: " + name)
        from freevideo_engine.offload import cpu_weights
        shapes = saved.shapes(source, saved.index, list(cpu_weights(owner)))
        key = ".".join([*parts[end:], field])
        if key not in shapes:
            raise ValueError("INT8 streamed buffer is not bound to its original layout: " + name)
        count, shape = shapes[key]
        if count != math.prod(shape):
            raise ValueError("INT8 streamed layout size differs: " + name)
        return list(shape), True
    raise ValueError("INT8 empty buffer has no original streamed layout: " + name)


class KernelAudit:
    def __init__(self, engine, manifest, ops):
        self.ops = ops
        self.expected = len(manifest["linears"])
        self.installed = 0
        self.streamed = 0
        for name, spec in manifest["linears"].items():
            module = engine.transformer.get_submodule(name)
            if not isinstance(module, ops.Int8Linear):
                raise ValueError("Engine projection is not an installed Int8Linear: " + name)
            weight_shape, streamed = _storage_shape(engine, name, module, "weight_int8")
            scale_shape, scale_streamed = _storage_shape(engine, name, module, "weight_scale")
            if (weight_shape != spec["weight_shape"]
                    or str(module.weight_int8.dtype) != "torch.int8"
                    or scale_shape != spec["scale_shape"]
                    or str(module.weight_scale.dtype) != "torch.float32"
                    or streamed != scale_streamed):
                raise ValueError("Installed INT8 projection storage differs from manifest: " + name)
            self.installed += 1
            self.streamed += int(streamed)
        self.counts = dict(matmul=0, rotate_quantize=0)
        self.steps = []
        self.previous = dict(self.counts)

    @contextmanager
    def observe(self):
        originals, wrappers = {}, {}
        for name in self.counts:
            original = getattr(self.ops, name)
            originals[name] = original

            def delegated(*args, _name=name, _original=original, **kwargs):
                result = _original(*args, **kwargs)
                self.counts[_name] += 1  # Count successful actual calls only.
                return result

            wrappers[name] = delegated
            setattr(self.ops, name, delegated)
        try:
            yield self
        finally:
            changed = []
            for name, original in originals.items():
                if getattr(self.ops, name) is wrappers[name]:
                    setattr(self.ops, name, original)
                else:
                    changed.append(name)  # Never erase someone else's replacement.
            if changed:
                raise ValueError("INT8 audit delegate changed during execution: " + ", ".join(changed))

    def step(self):
        row = {key: self.counts[key] - self.previous[key] for key in self.counts}
        if row["matmul"] <= 0:
            raise ValueError("Completed NFE had no actual successful INT8 GEMM")
        self.steps.append(row)
        self.previous = dict(self.counts)

    def snapshot(self):
        return dict(schema="t8-freevideo-int8-kernel-audit-v1", expected_targets=self.expected,
                    installed_targets=self.installed, actual_calls=dict(self.counts),
                    initially_streamed_layout_targets=self.streamed,
                    initially_materialized_targets=self.installed - self.streamed,
                    nfe_calls=[dict(row) for row in self.steps],
                    scope="installed_targets_and_actual_kernel_counts_not_per_target_coverage")


def validate(value, nfe):
    if (not isinstance(value, dict) or value.get("schema") != "t8-freevideo-int8-kernel-audit-v1"
            or type(value.get("expected_targets")) is not int or value["expected_targets"] < 1
            or value.get("installed_targets") != value["expected_targets"]):
        raise ValueError("Completion needs actual installed INT8 projection evidence")
    total, steps = value.get("actual_calls", {}), value.get("nfe_calls")
    if not isinstance(steps, list) or len(steps) != nfe:
        raise ValueError("INT8 kernel evidence does not cover actual NFE")
    for key in ("matmul", "rotate_quantize"):
        if (type(total.get(key)) is not int or total[key] < 1
                or any(not isinstance(row, dict) or type(row.get(key)) is not int
                       or row[key] < (1 if key == "matmul" else 0) for row in steps)
                or sum(row[key] for row in steps) > total[key]):
            raise ValueError("Incomplete actual INT8 kernel-call evidence: " + key)
    return value
