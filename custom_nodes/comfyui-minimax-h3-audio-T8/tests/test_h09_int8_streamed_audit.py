"""CPU-only empty-storage ownership contracts; not a CUDA/model qualification."""
import sys
from types import ModuleType, SimpleNamespace
import weakref

import pytest
import torch

from h3_audio_t8_pkg.freevideo_int8.audit import KernelAudit


@pytest.fixture
def streamed(monkeypatch):
    class Int8Linear(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer("weight_int8", torch.empty(0, dtype=torch.int8))
            self.register_buffer("weight_scale", torch.empty(0))

    projection = Int8Linear()
    owner = torch.nn.Module()
    owner.add_module("proj", projection)
    transformer = torch.nn.Module()
    transformer.add_module("block", owner)
    # Retain a concrete weak-referenceable source owner.
    class Source:
        prefixes = ["block."]
    source = Source()
    shapes = {"proj.weight_int8": (32 * 256, (32, 256)),
              "proj.weight_scale": (32, (1, 32))}
    tensors = list(owner.named_buffers())

    class Layout:
        index = 0
        def __init__(self):
            self.source = weakref.ref(source)
        def shapes(self, actual_source, index, weights):
            assert isinstance(weights, list)  # The author API requires len().
            if actual_source is not self.source() or index != self.index or len(weights) != len(tensors):
                raise ValueError("Original source/order required")
            for (name, value), (expected_name, expected) in zip(weights, tensors):
                if (name != expected_name or value is not expected or value.numel() != 0
                        or tuple(value.shape) != (0,)):
                    raise ValueError("Original tensor identities required")
            return shapes

    owner._freevideo_streamed_layout = Layout()
    offload = ModuleType("freevideo_engine.offload")
    offload.cpu_weights = lambda block: block.named_buffers()
    monkeypatch.setitem(sys.modules, "freevideo_engine.offload", offload)
    engine = SimpleNamespace(transformer=transformer, stream_weight_source=source)
    ops = SimpleNamespace(Int8Linear=Int8Linear, matmul=lambda x: x, rotate_quantize=lambda x: x)
    manifest = {"linears": {"block.proj": {"weight_shape": [32, 256], "scale_shape": [1, 32]}}}
    return engine, manifest, ops, owner, projection, shapes


def test_streamed_layout_owned_by_original_source_is_logically_installed_not_executed(streamed):
    engine, manifest, ops, owner, module, _ = streamed
    snapshot = KernelAudit(engine, manifest, ops).snapshot()
    assert snapshot["installed_targets"] == snapshot["initially_streamed_layout_targets"] == 1
    assert snapshot["initially_materialized_targets"] == 0
    assert snapshot["actual_calls"] == {"matmul": 0, "rotate_quantize": 0}
    assert module.weight_int8.numel() == module.weight_scale.numel() == 0


@pytest.mark.parametrize("change", ["source", "prefix", "index", "missing_layout", "tensor", "shape", "dtype"])
def test_empty_storage_is_not_trusted_from_manifest_or_replaced_layout(streamed, change):
    engine, manifest, ops, owner, module, shapes = streamed
    if change == "source":
        engine.stream_weight_source = object()
    elif change == "prefix":
        engine.stream_weight_source.prefixes = ["other."]
    elif change == "index":
        owner._freevideo_streamed_layout.index = 1
    elif change == "missing_layout":
        del owner._freevideo_streamed_layout
    elif change == "tensor":
        module.weight_int8 = torch.empty(0, dtype=torch.int8)
    elif change == "shape":
        shapes["proj.weight_int8"] = (32 * 256, (32, 512))
    else:
        module.weight_scale.data = torch.empty(0, dtype=torch.bfloat16)
    with pytest.raises(ValueError):
        KernelAudit(engine, manifest, ops)
