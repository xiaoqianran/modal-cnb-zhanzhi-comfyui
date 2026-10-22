"""User-selected patches and large valid stage metadata are not admission gates."""
import ast
import json
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest
import torch

from h3_audio_t8_pkg.modular_sampling.results import execution_identity, sample_stage
from h3_audio_t8_pkg.modular_sampling.storage import save_stage, load_stage
from h3_audio_t8_pkg.patch_stack_policy import model_identity_matches
from test_modular_stage_native_dispatch import prepared
from test_modular_results import inputs


@pytest.mark.parametrize("alias", [False, True])
@pytest.mark.parametrize("hook_kind", ["hook", "pre_hook"])
def test_native_memory_forward_with_existing_hook_survives_core_load(alias, hook_kind):
    args, _ = prepared()
    selected = args[1].model_patcher
    block = selected.model.diffusion_model.blocks[0]
    if alias:
        block.forward = MethodType(type(block).forward, block)
    if hook_kind == "hook":
        block.register_forward_hook(lambda module, values, output: output)
    else:
        block.register_forward_pre_hook(lambda module, values: values)
    initial = selected.model.model_sampling
    before = execution_identity(selected, initial)
    selected.patch_model(torch.device("cpu"), load_weights=False)
    after = execution_identity(selected, initial)
    assert model_identity_matches(before, after)


def test_existing_foreign_forward_is_preserved_as_unverified_not_rejected():
    args, _ = prepared()
    selected = args[1].model_patcher
    selected.patch_model(torch.device("cpu"), load_weights=False)
    block = selected.model.diffusion_model.blocks[0]
    original = block.forward
    foreign = MethodType(lambda self, *v, **kw: original(*v, **kw), block)
    block.forward = foreign
    observed = execution_identity(selected, selected.model.model_sampling)
    assert block.forward is foreign
    assert "diffusion_model.blocks.0" in observed["execution_selection"]["network_execution"]
    assert observed["unverified_memory_forwards"]


def test_valid_metadata_above_four_mib_roundtrips(tmp_path):
    args = list(inputs())
    args[4]["user_notes"] = "x" * (4 * 1024 * 1024 + 128)
    result = sample_stage(*args)[2]
    path, digest, _ = save_stage(result, tmp_path)
    output, denoised, _, restored, _ = load_stage(tmp_path, path, digest, "low_0_4")
    assert output["user_notes"] == denoised["user_notes"] == args[4]["user_notes"]
    assert restored.verify() == result.verify()
    assert not torch.cuda.is_initialized()


def test_non_native_model_preflight_is_advisory_not_error():
    from h3_audio_t8_pkg.preflight import run_preflight
    selected = SimpleNamespace(model=SimpleNamespace(diffusion_model=object()))
    report = json.loads(run_preflight(512, 288, 124, "native", model=selected)[2])
    assert not report["errors"]
    assert any("unverified" in text for text in report["warnings"])


def test_unknown_clip_kept_without_inventing_cache_identity(monkeypatch):
    from h3_audio_t8_pkg import qwen_prefix_cache_advanced as cache
    monkeypatch.setattr(cache, "core_contract", lambda: {"supported": True})
    selected = SimpleNamespace(cond_stage_model=object())
    clip, _, report = cache.build_prefix_cache_clip(selected, "memory_lru_exp", 2, 64, 0)
    assert clip is selected
    assert report["applied"] is False
    assert report["status"] == "cache_bypassed_user_clip_preserved"


def test_alternative_diffusion_class_can_use_memory_nodes(caplog):
    from h3_audio_t8_pkg.h3_memory_advanced import configure_chunk_feed_forward, configure_low_vram_attention
    from test_h3_memory_advanced import _small_model
    selected = _small_model()
    diffusion = selected.model.diffusion_model
    native_type = type(diffusion)
    # Same actual methods/parameters, independently named class, not a subclass
    # of the allowlisted class. The selected instance is never swapped out.
    members = {key: value for key, value in vars(native_type).items()
               if key not in {"__dict__", "__weakref__"}}
    diffusion.__class__ = type("UserSelectedH3", native_type.__bases__, members)
    prepared = configure_low_vram_attention(selected, 2)[0]
    prepared = configure_chunk_feed_forward(prepared, 2, 256)[0]
    assert prepared.model.diffusion_model is diffusion
    assert "advisory" in caplog.text


def test_alternative_diffusion_still_reports_actual_missing_blocks():
    from h3_audio_t8_pkg.h3_memory_advanced import configure_low_vram_attention
    from test_h3_memory_advanced import _small_model
    selected = _small_model()
    selected.model.diffusion_model.blocks = torch.nn.ModuleList()
    with pytest.raises(ValueError, match="does not expose any DiT blocks"):
        configure_low_vram_attention(selected, 2)


def test_existing_hook_is_called_by_actual_stage_sampler():
    args, _ = prepared()
    block = args[1].model_patcher.model.diffusion_model.blocks[0]
    calls = []
    handle = block.register_forward_hook(lambda module, values, output: calls.append(module))
    try:
        receipt = sample_stage(*args)[2].verify()
        assert calls and all(value is block for value in calls)
        assert receipt["verified_recipe_completion"] is True
    finally:
        handle.remove()
    assert not torch.cuda.is_initialized()


def test_legacy_storage_constants_are_never_current_admission_conditions():
    from h3_audio_t8_pkg.modular_sampling import storage
    for path in Path(storage.__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                names = {part.id for part in ast.walk(node.test) if isinstance(part, ast.Name)}
                assert not names & {"MAX_JSON", "MAX_FILE", "MAX_BUNDLE_JSON", "MAX_COMPRESSED"}, path


def test_foreign_timed_reference_tokenizer_delegates_instead_of_rejecting():
    from h3_audio_t8_pkg.timed_references_advanced import append_timed_reference
    calls = []
    class Tokenizer:
        def tokenize_with_weights(self, text, return_word_ids=False, **kwargs):
            calls.append((text, kwargs))
            return {"selected": [text]}
    tokenizer = Tokenizer()
    clip = SimpleNamespace(tokenizer=tokenizer, clone=lambda: SimpleNamespace(tokenizer=tokenizer))
    frames = torch.zeros(1, 8, 8, 3)
    selected = append_timed_reference(clip, {"prompt_tag": "motion", "frames": frames, "timestamps": [0.]})
    actual = selected.tokenizer.tokenize_with_weights("#motion", minimax_ref_items=[])
    assert actual == {"selected": ["<Video 1>"]}
    assert calls[0][1]["minimax_ref_items"][0]["data"] is frames
