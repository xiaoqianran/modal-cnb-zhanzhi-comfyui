"""Ordinary text must not install Relay, including native long-video receipts."""
from copy import deepcopy
import json

import pytest

from h3_audio_t8_pkg.nodes_plain_prompt import MiniMaxH3PlainPromptRecipeEXPT8
from h3_audio_t8_pkg.prompt_relay_advanced import PROMPT_RELAY_BINDING_KEY
from h3_audio_t8_pkg.prompt_relay_long_video_advanced import (
    build_prompt_relay_long_video_conditioning,
    project_prompt_relay_plan_to_long_video_window,
    PROMPT_RELAY_LONG_VIDEO_ATTACHMENT_KEY,
)
from h3_audio_t8_pkg.long_video import LONG_VIDEO_SCHEMA
from h3_audio_t8_pkg.modular_sampling.fast_h3_v2_stage_attest import _verify_prompt_route
from test_prompt_relay_long_video_advanced import (
    _allow_fixture_core_contract, _model_patcher, NativeLikeFakeClip,
    FakeVideoVAE, FakeAudioVAE,
)


def plain():
    return MiniMaxH3PlainPromptRecipeEXPT8.execute("A woman walks, turns and says hello.", 193).result[0]


def projected():
    source = plain()
    window = project_prompt_relay_plan_to_long_video_window(source, 0, 124, 0, 0., 124 / 24)[0]
    return source, window


def test_plain_schema_exposes_only_full_prompt_and_length_and_zero_events():
    schema = MiniMaxH3PlainPromptRecipeEXPT8.define_schema()
    assert [item.id for item in schema.inputs] == ["prompt", "length"]
    result = MiniMaxH3PlainPromptRecipeEXPT8.execute("First she walks. Then she stops.", 124).result
    assert result[0]["events"] == []
    assert result[0]["frame_count"] == result[2] == 124
    assert "First she walks. Then she stops." in result[1]
    assert json.loads(result[3])["events"] == []


def test_plain_long_video_keeps_motion_payload_without_attention_route(monkeypatch):
    _allow_fixture_core_contract(monkeypatch)
    _, plan = projected()
    result = build_prompt_relay_long_video_conditioning(
        model=_model_patcher(), clip=NativeLikeFakeClip(), video_vae=FakeVideoVAE(), audio_vae=FakeAudioVAE(),
        context={"schema": LONG_VIDEO_SCHEMA, "empty": True, "chain_id": "ordinary", "target_segment_index": 0},
        prompt_relay_plan=plan, segment_index=0, context_frames=0, context_audio="video_and_audio",
        width=128, height=128, length=124, task_type="T2VA", audio_mode="native",
        audio_denoise_strength=.35, add_source_as_reference=False, prompt_primary_audio_ordinal=0,
        strict_prompt_tags=True, ref_image_size="match", reference_video_policy="official_2_to_15s",
        execution_mode="apply_exp", query_chunk_rows=64)
    model, positive = result[:2]
    assert getattr(model.get_model_object("extra_conds"), "_t8_long_video_patch_version") == 1
    assert model.get_attachment(PROMPT_RELAY_LONG_VIDEO_ATTACHMENT_KEY) is None
    assert PROMPT_RELAY_BINDING_KEY not in positive[0][1]
    report = json.loads(result[6])
    assert report["event_count"] == 0
    assert report["attention_patch_installed"] is False


def test_plain_receipt_route_keeps_hash_and_segment_checks():
    source, window = projected()
    _verify_prompt_route(source, window, source["plan_hash"], None, None, 0)
    for damaged in (dict(window, global_plan_hash="f" * 64),
                    dict(window, long_video_projection={"segment_index": 1})):
        with pytest.raises(ValueError):
            _verify_prompt_route(source, damaged, source["plan_hash"], None, None, 0)
    with pytest.raises(ValueError, match="current recipe"):
        _verify_prompt_route(source, window, "f" * 64, None, None, 0)
    for owner, effect in (({}, None), (None, {})):
        with pytest.raises(ValueError, match="unexpectedly contains"):
            _verify_prompt_route(source, window, source["plan_hash"], owner, effect, 0)


def test_segmented_route_does_not_use_ordinary_receipt_exception():
    source, window = projected()
    altered = deepcopy(window)
    altered["events"] = [{"local_prompt": "A segmented event"}]
    with pytest.raises(ValueError, match="Relay owner"):
        _verify_prompt_route(source, altered, source["plan_hash"], None, None, 0)
