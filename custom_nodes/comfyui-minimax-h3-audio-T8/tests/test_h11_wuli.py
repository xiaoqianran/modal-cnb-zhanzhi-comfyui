"""Five new narrow contracts; CPU observations are not Wuli video qualification."""
from copy import deepcopy
import hashlib
from types import SimpleNamespace

import pytest
import torch

from h3_audio_t8_pkg import wuli_native as wuli


class Model:
    def __init__(self):
        from comfy.model_sampling import ModelSamplingAV
        self.model = SimpleNamespace(model_config=SimpleNamespace(sampling_settings={}))
        self.sampling = ModelSamplingAV(self.model.model_config)
        self.core = SimpleNamespace(adaln_t_table=torch.zeros(1025, 25))
        self.model_options = {"transformer_options": {"wrappers": {"user": {"hook": [str]}}}}
        self.patches = {"user_LoRA": object()}
        self.wrappers, self.callbacks = [], []

    def get_model_object(self, name):
        return self.sampling if name == "model_sampling" else self.core

    def clone(self):
        value = Model()
        value.patches = self.patches.copy()
        value.model_options = deepcopy(self.model_options)
        return value

    def add_object_patch(self, name, obj):
        assert name == "model_sampling"
        self.sampling = obj

    def add_wrapper_with_key(self, *args):
        self.wrappers.append(args)

    def add_callback_with_key(self, *args):
        self.callbacks.append(args)


def test_actual_core_clocks_and_separate_stage_state_preserve_user_chain():
    model = Model()
    low, low_grid, _, a = wuli.native8(model)
    high, grid, _, b = wuli.native_clock(model, "native4")
    assert low is not model and high is not model and a is not b
    assert low.patches == high.patches == model.patches
    assert low.model_options["transformer_options"]["wrappers"] == model.model_options["transformer_options"]["wrappers"]
    assert len(low_grid) == 9 and len(grid) == 5
    assert low.sampling.audio_scale == 4 and high.sampling.audio_scale == 2
    assert [wuli.bank_span(float(grid[i]), float(grid[i+1]), 6., 4) for i in range(4)] == [(0, 1), (1, 2), (2, 3), (3, 4)]
    assert not a.report()["full_trajectory_observed"]
    assert not torch.cuda.is_initialized()


def test_basis_and_curve_full_base_errors_are_not_combination_bans():
    model = Model()
    model.core.adaln_t_table = torch.zeros(1025, 8)
    with pytest.raises(ValueError, match="25"):
        wuli.native8(model)
    with pytest.raises(ValueError, match="full FL2VA"):
        wuli.native4(model, {})
    assert model.patches and model.model_options["transformer_options"]["wrappers"]


def test_wrong_asset_role_and_mutated_file_cannot_reuse_hash(tmp_path, monkeypatch):
    path = tmp_path / "asset"
    path.write_bytes(b"correct")
    monkeypatch.setitem(wuli.ASSETS, "widen", hashlib.sha256(b"correct").hexdigest())
    assert wuli.verified_asset(path, "widen")["bytes"] == 7
    with pytest.raises(ValueError, match="SHA"):
        wuli.verified_asset(path, "set")
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA"):
        wuli.verified_asset(path, "widen")


def test_observer_eav_duplicate_sigma_partial_grid_and_exception_delegate():
    model, grid, _, state = wuli.native_clock(Model(), "native4")
    calls = []
    class Executor:
        class_obj = SimpleNamespace()
        def __call__(self, *args, **kwargs):
            calls.append(args)
            return "original"
    options = {"sample_sigmas": grid, "minimax_h3_sigma_shift_video": 6., "minimax_h3_sigma_shift_audio": 3.}
    for _ in range(2):
        assert state.observe(Executor(), None, grid[:1]*1000, None, options) == "original"
    assert state.report()["observed_logical_steps"] == [0] and len(calls) == 2
    state.observe(Executor(), None, grid[1:2]*1000, None, {**options, "sample_sigmas": grid[1:]})
    assert state.calls[-1]["logical_step"] is None
    assert state.report()["warnings"]
    class Broken(Executor):
        def __call__(self, *args, **kwargs):
            raise RuntimeError("actual error")
    with pytest.raises(RuntimeError, match="actual error"):
        state.observe(Broken(), None, grid[:1]*1000, None, options)
    assert state.errors == ["RuntimeError"] and len(state.calls) == 3
    state.reset()
    assert not state.calls and not state.errors


def test_native_core_reshape_then_absolute_set_cpu_algebra():
    from comfy import lora
    original = torch.randn(2, 3)
    widen = {"h.lora_up.weight": torch.zeros(8, 1), "h.lora_down.weight": torch.zeros(1, 3),
             "h.reshape_weight": torch.tensor([8, 3])}
    absolute = torch.arange(24, dtype=torch.float32).reshape(8, 3)
    first = lora.load_lora(widen, {"h": "h.weight"})["h.weight"]
    second = lora.load_lora({"h.set_weight": absolute}, {"h": "h.weight"})["h.weight"]
    result = lora.calculate_weight([(1., first, 1., None, None), (1., second, 1., None, None)], original, "h.weight")
    assert torch.equal(result, absolute) and result.shape == (8, 3)
    assert first.calculate_shape("h.weight") == (8, 3)
