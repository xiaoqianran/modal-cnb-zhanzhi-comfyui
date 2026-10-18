"""Three new contracts; no claim of voice fidelity or pretrained generation."""
import json
import pytest
import torch
from helpers import FakeAudioVAE, FakeClip, make_audio
from h3_audio_t8_pkg import audio_reference_only as audio
from h3_audio_t8_pkg.temporal_dialogue_encoding import validate_native_text_recipe


@pytest.fixture
def encoder(monkeypatch):
    value = FakeAudioVAE()
    monkeypatch.setattr(audio, "native_producer_identity", lambda obj, role: {
        "role": role, "sha256": str(getattr(obj, "revision", 0)), "portable_cache_reuse": True})
    return value


def test_qwen_grounding_stable_paired_roles_audio_only_blocks_and_raw_recipe(encoder):
    rgb = torch.full((5, 32, 32, 3), .5)
    pcm = make_audio(.1)
    original = pcm["waveform"].clone()
    a, report = audio.capture("A", "paired_video_soundtrack", "video", pcm, encoder, rgb)
    b, _ = audio.capture("B", "standalone_audio", "image", pcm, encoder, rgb[:1])
    clip = FakeClip()
    positive, latent, mux, prompt, media, text, recipe = audio.build(clip, encoder, [a, b],
        "<Video 1> hears <Audio 1>; <Picture 1> hears <Audio 2>.", 32, 32, 124)
    assert [r["kind"] for r in positive[0][1]["minimax_refs"]] == ["audio", "audio"]
    assert len(encoder.encode_calls) == 2 and len(clip.tokenize_calls) == 1
    assert torch.equal(pcm["waveform"], original) and mux is None
    items = clip.tokenize_calls[0][1]["minimax_ref_items"]
    assert [v["type"] for v in items] == ["audio", "video", "audio", "image"]
    mapping = json.loads(text)["mapping"]
    assert [(v["role_id"], v["audio_ordinal"], v["source_origin"]) for v in mapping] == [
        ("A", 1, "paired_video_soundtrack"), ("B", 2, "standalone_audio")]
    assert report["video_VAE_calls"] == 0 and latent["samples"].is_nested
    assert validate_native_text_recipe(recipe) is recipe
    assert json.loads(media)["audios"]["1"].endswith("paired_video_soundtrack")


def test_no_silent_media_drop_role_merge_reference_drive_substitution(encoder):
    rgb = torch.zeros(1, 32, 32, 3)
    with pytest.raises(ValueError, match="paired|Paired"):
        audio.capture("A", "paired_video_soundtrack", "image", make_audio(.1), encoder, rgb)
    with pytest.raises(ValueError, match="drop"):
        audio.capture("A", "standalone_audio", "none", make_audio(.1), encoder, rgb)
    a, _ = audio.capture("A", "standalone_audio", "none", make_audio(.1), encoder)
    with pytest.raises(ValueError, match="Duplicate"):
        audio.build(FakeClip(), encoder, [a, a], "test", 32, 32, 124)
    with pytest.raises(ValueError, match="drive_audio"):
        audio.build(FakeClip(), encoder, [a], "test", 32, 32, 124, audio_mode="lock_source")


def test_changed_pcm_latent_and_actual_encoder_refuse_stale_adoption(encoder):
    a, _ = audio.capture("A", "standalone_audio", "none", make_audio(.1), encoder)
    encoder.revision = 1
    with pytest.raises(ValueError, match="encoder changed"):
        a.verify(encoder)
    encoder.revision = 0
    a.audio_latent[..., 0] += 1
    with pytest.raises(ValueError, match="contents changed"):
        a.verify(encoder)
    assert not torch.cuda.is_initialized()
