"""New Spark contracts only. CPU stubs do not qualify CUDA or video quality."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
import torch

from h3_audio_t8_pkg import spark_runtime as spark


class Controller:
    def __init__(self, config=None):
        self.config = config
        self.reset()

    def reset(self):
        self.evaluation_index = -1
        self.last_reblock = None


def state():
    return spark.SparkState((1., .7, .3, 0.), "HIGH", "spark", 1, 1, 64,
                           SimpleNamespace(ComfyPackedLayout=lambda *a: SimpleNamespace(
                               permutation=a[0], inverse_permutation=a[1], grid=a[2], video_tokens=a[3])),
                           Controller())


def options(sigma=1., grid=None):
    return {"sigmas": torch.tensor([sigma]), "sample_sigmas": torch.tensor(
        [1., .7, .3, 0.] if grid is None else grid)}


def test_logical_grid_same_sigma_eav_inplace_and_offgrid():
    s = state()
    opt = options()
    assert s.logical_step(opt) == (0, None)
    assert s.logical_step(options()) == (0, None)  # EAV extra evaluation is idempotent
    opt["sigmas"].fill_(.7)  # same tensor id is not stale step 0
    assert s.logical_step(opt) == (1, None)
    assert s.steps_seen == {0, 1}
    assert s.logical_step(options(.9))[0] is None
    assert s.logical_step(options(.7, [1., .7, .2, 0.]))[0] is None
    assert s.steps_seen == {0, 1}
    with pytest.raises(ValueError, match="descending"):
        spark.sigma_grid(torch.tensor([1., .7, .7, 0.]))


def test_state_cleanup_retains_audit_and_new_run_is_separate():
    low, high = state(), state()
    low.logical_step(options())
    low.counts["sparse"] = 4
    low.cleanup()
    assert low.report()["actual_sparse_calls"] == 4
    assert high.report()["actual_sparse_calls"] == 0
    low.pre_run()
    assert low.report()["actual_sparse_calls"] == 0 and low.run == 1
    assert not low.steps_seen


def test_packed_layout_exact_prefix_and_inverse_not_duplicate_grid():
    s = state()
    positions = torch.tensor([[9., 9., 9.], [0., 0., 0.], [0., 0., 1.],
                              [0., 1., 0.], [0., 1., 1.], [8., 8., 8.]])
    layout = SimpleNamespace(position_ids=positions, segments=[(0, 1, "audio"), (1, 5, "video"), (5, 6, "text")])
    packed = spark.packed_layout(s, layout, 6, torch.device("cpu"))
    assert packed.permutation.tolist() == [1, 2, 3, 4, 0, 5]
    seq = torch.arange(6)
    assert torch.equal(seq[packed.permutation][packed.inverse_permutation], seq)
    assert packed.grid == (1, 2, 2)
    bad = SimpleNamespace(position_ids=positions.clone(), segments=[(1, 5, "video")])
    bad.position_ids[2] = bad.position_ids[1]
    with pytest.raises(ValueError, match="dense grid"):
        spark.packed_layout(s, bad, 6, torch.device("cpu"))


def test_unsupported_bias_and_existing_callable_delegate_without_mutation():
    s = state()
    s.warmup_steps = s.dense_layers = 0
    args = {"img": torch.zeros(64, 128), "transformer_options": options(.7), "attention": lambda *_: 3}
    original = dict(args)
    calls = []
    patch = spark.block_patch(s, None, 2)
    assert patch(args, {"original_block": lambda a: calls.append(a) or "original"}) == "original"
    assert calls == [args] and args == original
    assert s.report()["actual_sparse_calls"] == 0
    assert s.reasons["existing_attention_callable"] == 1
    args.pop("attention")
    bias = torch.ones(2, 2)
    args["transformer_options"]["attn_bias"] = bias
    assert patch(args, {"original_block": lambda a: a["transformer_options"]["attn_bias"]}) is bias
    assert s.reasons["existing_attention_patch_mask_or_bias"] == 1


def test_kernel_failure_never_calls_dense_fallback(monkeypatch):
    s = state()
    monkeypatch.setattr(spark, "delegation_reason", lambda *_: None)
    monkeypatch.setattr(spark, "kernel_attention", lambda *_: (_ for _ in ()).throw(RuntimeError("kernel failed")))
    args = {"img": torch.zeros(1, 1), "transformer_options": {}}
    calls = []

    def original(a):
        calls.append(a)
        return a["attention"](a["img"])

    with pytest.raises(RuntimeError, match="kernel failed"):
        spark.block_patch(s, SimpleNamespace(attn=object()), 0)(args, {"original_block": original})
    assert len(calls) == 1 and s.errors == ["RuntimeError"]
    assert "attention" not in args


def test_apply_clone_preserves_original_owner_lora_and_disabled_no_runtime(monkeypatch):
    calls = []
    def original_owner(a, e):
        return calls.append(a) or "user"
    diffusion = type("MiniMaxH3Model", (), {"blocks": [object(), object()]})()

    class Model:
        def __init__(self):
            self.model_options = {"transformer_options": {"patches_replace": {"dit": {("double_block", 0): original_owner}}}}
            self.patches = {"user_lora": object()}
            self.callbacks = []

        def get_model_object(self, name):
            assert name == "diffusion_model"
            return diffusion

        def clone(self):
            cloned = Model()
            cloned.model_options = deepcopy(self.model_options)
            cloned.patches = self.patches.copy()
            return cloned

        def set_model_patch_replace(self, callback, section, kind, layer):
            self.model_options["transformer_options"]["patches_replace"][section][(kind, layer)] = callback

        def add_callback_with_key(self, *args):
            self.callbacks.append(args)

    upstream = SimpleNamespace(ComfySparkController=Controller, ComfySparkConfig=lambda **kw: kw)
    monkeypatch.setattr(spark, "backend", lambda _: upstream)
    model = Model()
    patched, s = spark.apply_spark(model, torch.tensor([1., .7, .3, 0.]), "fake")
    assert patched is not model and patched.patches == model.patches
    assert s.preserved == [0] and s.installed == [1]
    user = patched.model_options["transformer_options"]["patches_replace"]["dit"][("double_block", 0)]
    assert user is original_owner and user(123, {}) == "user" and calls == [123]
    assert set(model.model_options["transformer_options"]["patches_replace"]["dit"]) == {("double_block", 0)}
    monkeypatch.setattr(spark, "backend", lambda _: (_ for _ in ()).throw(AssertionError("must not load")))
    assert spark.apply_spark(model, None, "absent", enabled=False) == (model, None)
