"""Four narrow CPU contracts; no CLIP/model download or quality simulation."""
import json

import pytest
import torch
from comfy.nested_tensor import NestedTensor

from h3_audio_t8_pkg.audio_first import audit, project
from h3_audio_t8_pkg.core import empty_av_latent, nested_av_parts
from h3_audio_t8_pkg.source_av import prepare_source_av_latent


def full():
    return empty_av_latent(64, 32, 124)[0]


class VAE:
    def __init__(self):
        self.images = []

    def encode(self, image):
        self.images.append(image)
        return torch.full((1, 24, 1, 2, 2), 0.25)


def test_projection_reuses_embeddings_and_encodes_only_raw_single_first_image():
    latent, embedding, hook = full(), torch.randn(1, 4, 8), object()
    vae = VAE()
    original = [[embedding, {"hooks": hook, "strength": 0.7, "minimax_token_tags": [0, 1],
                             "user_extension": hook, "minimax_frame_count": 124}]]
    condition, tiny, text = project(original, latent, video_vae=vae)
    report = json.loads(text)
    assert report["CLIP_encodes"] == report["VAE_encodes"] == 0 and not vae.images
    assert condition[0][0] is embedding and condition[0][1]["hooks"] is hook
    assert condition[0][1] is not original[0][1] and "user_extension" in report["unknown_metadata_preserved_unqualified"]
    tv, ta = nested_av_parts(tiny)
    assert tv.shape == (1, 24, 37, 2, 2) and ta.shape == (1, 32, 2, 207)
    keyframe = {"resolved_frame_index": 0, "latent": torch.zeros(1, 24, 1, 2, 4)}
    with_first = [[embedding, {**original[0][1], "minimax_keyframes": [keyframe]}]] * 2
    image = torch.rand(1, 20, 40, 3)
    projected, _, text = project(with_first, latent, image, vae)
    assert len(vae.images) == 1 and vae.images[0].shape == (1, 32, 32, 3)
    assert projected[0][0] is embedding and projected[0][1]["minimax_keyframes"][0]["latent"].shape == (1, 24, 1, 2, 2)
    assert projected[0][1]["minimax_keyframes"][0]["latent"] is projected[1][1]["minimax_keyframes"][0]["latent"]
    assert with_first[0][1]["minimax_keyframes"][0] is keyframe and not bool(keyframe["latent"].any())
    assert json.loads(text)["VAE_encodes"] == 1 and "noise_mask" not in latent
    assert not torch.cuda.is_initialized()


def test_projection_rejects_clock_spatial_multiguide_and_invalid_raw_vae():
    latent, embedding, vae = full(), torch.zeros(1, 4, 8), VAE()
    for metadata in ({"minimax_frame_count": 141}, {"minimax_refs": [{"kind": "image"}]},
                     {"area": (1, 2, 3, 4)}, {"control": object()}, {"t8_visual_marker_binding": {"id": 1}},
                     {"minimax_keyframes": [{"resolved_frame_index": 0}, {"resolved_frame_index": 123}]}):
        with pytest.raises(ValueError):
            project([[embedding, metadata]], latent, video_vae=vae)
    assert not vae.images
    v, a = nested_av_parts(latent)
    with pytest.raises(ValueError, match="clock"):
        project([[embedding, {}]], {"samples": NestedTensor((v, a[..., :-1]))})
    nan = a.clone()
    nan[..., 0] = float("nan")
    with pytest.raises(ValueError, match="NaN"):
        project([[embedding, {}]], {"samples": NestedTensor((v, nan))})
    original_kf = {"resolved_frame_index": 0, "latent": torch.zeros(1, 24, 1, 2, 4)}
    cond = [[embedding, {"minimax_keyframes": [original_kf]}]]
    with pytest.raises(ValueError, match="VAE"):
        project(cond, latent, torch.zeros(1, 20, 30, 3))
    class WrongVAE:
        def encode(self, image):
            return torch.zeros(1, 32, 1, 2, 2)
    with pytest.raises(ValueError, match="24"):
        project(cond, latent, torch.zeros(1, 20, 30, 3), WrongVAE())


def test_actual_source_av_strict_lock_preserves_full_video_and_tiny_audio():
    target = full()
    tiny = empty_av_latent(32, 32, 124)[0]
    v, _ = nested_av_parts(target)
    tv, ta = nested_av_parts(tiny)
    ta.copy_(torch.randn_like(ta))
    locked, _, _, text = prepare_source_av_latent(target, tiny, "regenerate", 1., "lock", 0., "strict", "strict")
    lv, la = nested_av_parts(locked)
    assert lv is v and la is ta and lv.shape[-1] != tv.shape[-1]
    vm, am = locked["noise_mask"].unbind()
    assert bool((vm == 1).all()) and not bool(am.any()) and "noise_mask" not in target
    assert "strict" in text
    with pytest.raises(ValueError, match="strict"):
        prepare_source_av_latent(target, {"samples": ta.double()}, "regenerate", 1., "lock", 0., "strict", "strict")
    with pytest.raises(ValueError, match="shorter"):
        prepare_source_av_latent(target, {"samples": ta[..., :-1]}, "regenerate", 1., "lock", 0., "strict", "strict")


def test_audit_binds_source_masks_clock_finite_and_actual_final_object():
    source = empty_av_latent(32, 32, 124)[0]
    locked = prepare_source_av_latent(full(), source, "regenerate", 1., "lock", 0., "strict", "strict")[0]
    lv, la = nested_av_parts(locked)
    final = {"samples": NestedTensor((lv + 1., la.clone())), "user_metadata": object()}
    result, text = audit(source, locked, final)
    assert result is final and json.loads(text)["audio_exact"] and not json.loads(text)["sampler_completion_proof"]
    near = {"samples": NestedTensor((lv, la + 1e-5))}
    assert not json.loads(audit(source, locked, near)[1])["audio_exact"]
    for changed in (la + 2.1e-5, la[..., :-1], la.double(), la + float("nan")):
        video = lv.double() if changed.dtype == torch.float64 else lv
        with pytest.raises(ValueError):
            audit(source, locked, {"samples": NestedTensor((video, changed))})
    sv, sa = nested_av_parts(source)
    with pytest.raises(ValueError, match="exact copy"):
        audit({"samples": NestedTensor((sv, sa + 0.1))}, locked, final)
    with pytest.raises(ValueError, match="NaN"):
        audit({"samples": NestedTensor((sv, sa + float("nan")))}, locked, final)
    with pytest.raises(ValueError, match="masks"):
        audit(source, {**locked, "noise_mask": NestedTensor((torch.ones_like(lv), torch.ones_like(la)))}, final)
    with pytest.raises(ValueError, match="explicit"):
        audit(source, {"samples": locked["samples"]}, final)
