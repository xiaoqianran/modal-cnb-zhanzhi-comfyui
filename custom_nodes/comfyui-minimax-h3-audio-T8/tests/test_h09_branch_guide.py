"""Actual native guide encoder / native MLP calls; tiny CPU, not media proof."""
import asyncio
import json
from types import MethodType, SimpleNamespace

import pytest
import torch
import comfy.ops
from comfy.ldm.minimax.model import MLP
from comfy.model_patcher import ModelPatcher
from comfy.weight_adapter.lora import LoRAAdapter

import h3_audio_t8_pkg
from h3_audio_t8_pkg.nodes_branch_guide import (
    MiniMaxH3BranchGuideEXPT8, append_branch_guide,
)
from helpers import FakeAudioVAE, FakeVideoVAE, make_audio
from test_h05_timed_guide import setup


def branches():
    positive, latent = setup()
    metadata = positive[0][1]
    first = {"resolved_frame_index": 0, "latent": torch.full((1, 24, 1, 8, 8), .1)}
    second = {"resolved_frame_index": 40, "audio_latent": torch.full((1, 32, 2, 9), .7)}
    return [[positive[0][0], dict(metadata, minimax_keyframes=[first], start_percent=0.)],
            [positive[0][0] + 1, dict(metadata, minimax_keyframes=[second], start_percent=.5)]], latent


@pytest.mark.parametrize("kind", ["image", "audio", "both"])
def test_native_guide_encodes_once_preserves_each_branch_and_inputs(kind):
    positive, latent = branches()
    video, audio = latent["samples"].tensors
    before = video.clone(), audio.clone()
    vv, av = FakeVideoVAE(), FakeAudioVAE()
    kwargs = dict(vae=vv, image=torch.full((1, 128, 128, 3), .3)) if kind != "audio" else {}
    if kind != "image":
        kwargs.update(audio_vae=av, audio=make_audio(3.))
    output, report = append_branch_guide(positive, latent, 72, **kwargs)
    for old, new in zip(positive, output):
        assert new[0] is old[0]
        assert new[1] is not old[1]
        assert len(old[1]["minimax_keyframes"]) == 1
        assert len(new[1]["minimax_keyframes"]) == 2
        assert new[1]["minimax_keyframes"][0] is old[1]["minimax_keyframes"][0]
        assert new[1]["minimax_keyframes"][-1]["resolved_frame_index"] == 72
        for key, value in old[1].items():
            if key != "minimax_keyframes":
                assert new[1][key] is value
    assert output[0][1]["minimax_keyframes"][-1] is output[1][1]["minimax_keyframes"][-1]
    assert len(vv.encode_calls) == (kind != "audio")
    assert len(av.encode_calls) == (kind != "image")
    assert torch.equal(video, before[0]) and torch.equal(audio, before[1])
    assert json.loads(report)["original_anchor_counts"] == [1, 1]


def test_empty_and_tuple_histories_and_negative_endpoint():
    positive, latent = branches()
    positive[0][1].pop("minimax_keyframes")
    positive[1][1]["minimax_keyframes"] = tuple(positive[1][1]["minimax_keyframes"])
    output, report = append_branch_guide(positive, latent, -1, vae=FakeVideoVAE(),
                                       image=torch.zeros(1, 128, 128, 3))
    assert [len(entry[1]["minimax_keyframes"]) for entry in output] == [1, 2]
    assert json.loads(report)["resolved_frame_index"] == 123


def test_invalid_history_or_bounds_fails_without_encoding_or_mutation():
    positive, latent = branches()
    vae = FakeVideoVAE()
    with pytest.raises(ValueError, match="outside"):
        append_branch_guide(positive, latent, 124, vae=vae, image=torch.zeros(1, 128, 128, 3))
    positive[1][1]["minimax_keyframes"] = "not guides"
    with pytest.raises(ValueError, match="guide mappings"):
        append_branch_guide(positive, latent, 0, vae=vae, image=torch.zeros(1, 128, 128, 3))
    assert not vae.encode_calls
    assert len(positive[0][1]["minimax_keyframes"]) == 1


def test_current_native_mlp_invokes_actual_linear_forward_and_hooks():
    class CountLinear(torch.nn.Linear):
        def forward(self, value):
            self.calls = getattr(self, "calls", 0) + 1
            return super().forward(value)

    mlp = MLP(4, 6, operations=SimpleNamespace(Linear=CountLinear))
    seen = []
    handle = mlp.fc2.register_forward_hook(lambda *_: seen.append(True))
    value = torch.arange(12, dtype=torch.float32).reshape(3, 4) / 10
    output = mlp(value)
    up = mlp.fc1(value)
    # Core SwiGLU uses the first half as the gate.
    gate, hidden = up.chunk(2, dim=-1)
    expected = torch.nn.functional.linear(torch.nn.functional.silu(gate) * hidden, mlp.fc2.weight)
    handle.remove()
    assert seen == [True] and mlp.fc2.calls == 1
    torch.testing.assert_close(output, expected)


def test_native_mlp_lora_and_explicit_callable_delegate_are_preserved(monkeypatch):
    """Actual Core LoRA/Linear; force-forward routing, not a CUDA fused-kernel test."""
    rng_before = torch.get_rng_state().clone()
    mlp = MLP(4, 6, dtype=torch.float32, device="cpu",
              operations=comfy.ops.disable_weight_init)
    # load_state_dict also supports Core's lazy weight initialization, without RNG.
    weights = {"fc1.weight": torch.arange(48, dtype=torch.float32).reshape(12, 4) / 50,
               "fc2.weight": torch.arange(24, dtype=torch.float32).reshape(4, 6) / 40}
    mlp.load_state_dict(weights, assign=True)
    original = mlp.fc2.weight.detach().clone()
    value = torch.arange(12, dtype=torch.float32).reshape(3, 4) / 10
    baseline = mlp(value).detach().clone()
    up = torch.arange(8, dtype=torch.float32).reshape(4, 2) / 20
    down = torch.arange(12, dtype=torch.float32).reshape(2, 6) / 30
    adapter = LoRAAdapter.load("fc2", {"fc2.lora_up.weight": up,
                                      "fc2.lora_down.weight": down},
                               alpha=2., dora_scale=None)
    assert adapter is not None
    patcher = ModelPatcher(mlp, torch.device("cpu"), torch.device("cpu"))
    assert patcher.add_patches({"fc2.weight": adapter}, strength_patch=.5) == ["fc2.weight"]
    assert patcher.patches["fc2.weight"][0][1] is adapter
    seen, delegated = [], []
    handle = mlp.fc2.register_forward_hook(lambda *_: seen.append(True))
    native_forward = mlp.fc2.forward

    def wrapped_forward(owner, inputs):
        delegated.append(owner)
        return native_forward(inputs) + .125

    def rejected_forward(owner, inputs):
        raise RuntimeError("actual delegate failure")

    def forbidden_fused_route(*args, **kwargs):
        raise AssertionError("explicit force-forward must not select fusion")

    try:
        patcher.patch_weight_to_device("fc2.weight", device_to=torch.device("cpu"))
        expected_weight = original + .5 * (up @ down)
        torch.testing.assert_close(mlp.fc2.weight, expected_weight)
        gate, hidden = torch.nn.functional.linear(value, weights["fc1.weight"]).chunk(2, -1)
        expected = torch.nn.functional.linear(torch.nn.functional.silu(gate) * hidden,
                                              expected_weight)
        torch.testing.assert_close(mlp(value), expected)
        wrapper = MethodType(wrapped_forward, mlp.fc2)
        mlp.fc2.forward = wrapper
        mlp.fc2.comfy_force_forward = True
        with monkeypatch.context() as guard:
            # Verify the actual routing guard without faking GPU/kernel execution.
            guard.setattr(comfy.ops, "_fp16_linear_wanted", forbidden_fused_route)
            guard.setattr(comfy.ops, "linear_input_act_", forbidden_fused_route)
            torch.testing.assert_close(mlp(value), expected + .125)
            assert mlp.fc2.forward is wrapper and delegated == [mlp.fc2]
            assert seen == [True, True]
            failing = MethodType(rejected_forward, mlp.fc2)
            mlp.fc2.forward = failing
            with pytest.raises(RuntimeError, match="actual delegate failure"):
                mlp(value)
            assert mlp.fc2.forward is failing
            assert patcher.patches["fc2.weight"][0][1] is adapter
    finally:
        mlp.fc2.forward = native_forward
        if hasattr(mlp.fc2, "comfy_force_forward"):
            del mlp.fc2.comfy_force_forward
        handle.remove()
        patcher.unpatch_model(device_to=torch.device("cpu"))
    assert torch.equal(mlp.fc2.weight, original)
    torch.testing.assert_close(mlp(value), baseline)
    assert torch.equal(torch.get_rng_state(), rng_before)
    assert not torch.cuda.is_initialized()


def test_schema_registration_is_additive_after_existing_veda_nodes():
    nodes = asyncio.run(h3_audio_t8_pkg.comfy_entrypoint().get_node_list())
    position = nodes.index(MiniMaxH3BranchGuideEXPT8)
    assert nodes[position - 1].define_schema().node_id == "MiniMaxH3VedaR2VAAuditEXPT8"
    schema = MiniMaxH3BranchGuideEXPT8.define_schema()
    assert schema.node_id == "MiniMaxH3BranchGuideEXPT8"
    assert [item.id for item in schema.outputs] == ["positive", "report_json"]
