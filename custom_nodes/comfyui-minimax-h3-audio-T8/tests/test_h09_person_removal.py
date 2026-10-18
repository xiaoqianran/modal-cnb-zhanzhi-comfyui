"""Tiny CPU executions of the actual native condition/pack interfaces; no media claim."""
import asyncio
from types import SimpleNamespace

import pytest
import torch
import comfy.model_base
import comfy.model_patcher
from comfy.ldm.minimax.model import PackedLayout, _video_t_spans

import h3_audio_t8_pkg
from h3_audio_t8_pkg import person_removal as p, source_conform as s
from h3_audio_t8_pkg.nodes_person_removal import NODES
from helpers import FakeClip, FakeVideoVAE, FakeAudioVAE


def rgb(count=120):
    return torch.arange(count).float().div(count + 22).reshape(-1, 1, 1, 1).expand(-1, 32, 64, 3).clone()


def plan(count=120):
    source = rgb(count)
    return p.make_plan(source, source.clone(), source[:1].clone())[0]


def pcm(frames, rate=32000, offset=0):
    return dict(waveform=torch.arange(offset, offset + p._sample(frames, rate)).float()
                .div(1e6)[None, None].expand(1, 2, -1).clone(), sample_rate=rate)


def native_model():
    # Actual MiniMaxH3.extra_conds and ModelPatcher with a tiny text identity in
    # place of Qwen refinement; no DiT weights, GPU, alternate layout or sampler.
    base = comfy.model_base.MiniMaxH3.__new__(comfy.model_base.MiniMaxH3)
    torch.nn.Module.__init__(base)
    base.concat_keys = ()
    base.manual_cast_dtype = None
    base.latent_shapes = None
    base.diffusion_model = SimpleNamespace(dtype=torch.float32, preprocess_text_embeds=lambda x: x)
    device = torch.device("cpu")
    return comfy.model_patcher.ModelPatcher(base, load_device=device, offload_device=device)


def test_external_mask_empty_frames_and_green_are_distinct_from_sampling_mask():
    frames = rgb(5)
    mask = torch.zeros(5, 32, 64)
    mask[2, 8:12, 10:14] = 1
    before = mask.clone(), frames.clone()
    processed, green, report = p.prepare_mask(frames, mask, grow=1, feather=1)
    assert not processed[:2].any() and not processed[3:].any()
    assert report["empty_frame_indices"] == [0, 1, 3, 4]
    assert 0 < report["area_fraction_by_frame"][2] < 1
    assert report["sampler_mask_attached"] is False
    assert report["external_origin_unverified"] is True
    assert torch.equal(green[processed > .5], torch.tensor([0., 1., 0.]).expand_as(green[processed > .5]))
    assert torch.equal(green[processed <= .5], frames[processed <= .5])
    assert torch.equal(mask, before[0]) and torch.equal(frames, before[1])


def test_original_manual_mask_reuses_actual_source_conform_map_and_rejects_staleness():
    frames = rgb(10)
    mask = torch.zeros(10, 32, 64)
    mask[2, 4:8, 10:15] = 1
    _, lineage = s.derive_control(frames, "manual_mask", mask)
    output, _, _, _, mapping, _ = s.conform(frames, 48., 64, 32, 5)
    processed, _, report = p.prepare_mask(output, mask, 0, 0, mapping, lineage)
    assert torch.equal(processed, mask[[0, 2, 4, 6, 8]])
    assert report["frame_map_report"]["lineage_status"] == "owned_preprocess_verified"
    assert report["annotation_semantics_verified"] is False
    with pytest.raises(ValueError, match="differs"):
        p.prepare_mask(output + .01, mask, frame_map=mapping)
    mask[2, 0, 0] = 1
    with pytest.raises(ValueError, match="modified"):
        p.prepare_mask(output, mask, frame_map=mapping, lineage=lineage)


@pytest.mark.parametrize("count,expected", [(1, (0,)), (22, (0,)), (23, (0, 21)),
    (38, (0, 21)), (43, (0, 21)), (120, (0, 21, 42, 63, 84, 98))])
def test_short_tail_schedule_and_full_recipe_cost(count, expected):
    value = plan(count)
    assert value.starts == expected
    _, report = p.make_plan(value.frames, value.green, value.clean)
    assert report["planned_total_sampler_steps"] == 12 * len(expected)
    assert report["delivered_frames"] == count and report["pixel_locked"] is False


@pytest.mark.parametrize("rate", [32000, 44100])
def test_six_windows_have_exact_full_frame_and_pcm_delivery_without_overlap_repeat(rate):
    value = plan()
    previous_frames, previous_audio = None, None
    for index, start in enumerate(value.starts):
        anchor, green, history, history_audio, _ = p.select_window(value, index, previous_frames, previous_audio)
        assert len(green) == 22
        if index:
            assert torch.equal(anchor, previous_frames[start:start + 1])
            assert torch.equal(history, previous_frames[start - 17:start + 1])
            assert history_audio["waveform"].shape[-1] == p._sample(start + 1, rate) - p._sample(start - 17, rate)
        window_rgb = torch.arange(start, start + 22).float().div(142).reshape(-1, 1, 1, 1).expand(-1, 32, 64, 3)
        window_audio = pcm(22, rate, p._sample(start, rate))
        # Native decoder may provide extra final samples; append crops by the
        # global boundary, not by rounded per-window length.
        tail_start = p._sample(start, rate) + window_audio["waveform"].shape[-1]
        tail = torch.arange(tail_start, tail_start + 2).float().div(1e6)[None, None].expand(1, 2, -1)
        window_audio["waveform"] = torch.cat((window_audio["waveform"], tail), -1)
        previous_frames, previous_audio, report = p.append_window(value, index,
            window_rgb, window_audio, previous_frames, previous_audio)
    assert report["complete"] and report["discarded_overlap_frames"] == 8
    torch.testing.assert_close(previous_frames, value.frames, rtol=0, atol=0)
    torch.testing.assert_close(previous_audio["waveform"], pcm(120, rate)["waveform"], rtol=0, atol=0)
    assert report["native_sampler_attested"] is False


def test_actual_native_condition_and_model_only_history_layout_no_global_patch():
    original_layout_init = PackedLayout.__init__
    model, vv, av, clip = native_model(), FakeVideoVAE(), FakeAudioVAE(), FakeClip()
    green = rgb(22)
    first_model, first, latent, report = p.condition_window(model, clip, vv, av, green[:1], green, "remove")
    assert first_model is model and report["continuation"] is False
    assert len(vv.encode_calls) == 1 and not av.encode_calls
    assert "minimax_refs" not in first[0][1]  # Qwen-only ref, as author graph
    assert len(first[0][1]["minimax_keyframes"]) == 1
    assert [tuple(v.shape) for v in latent["samples"].tensors] == [(1, 24, 7, 2, 4), (1, 32, 2, 37)]
    history = rgb(18)
    patched, positive, latent, report = p.condition_window(model, clip, vv, av,
        history[-1:], green, "remove", history, pcm(18))
    assert patched is not model and model.object_patches == {}
    assert len(vv.encode_calls) == 4 and len(av.encode_calls) == 1
    assert PackedLayout.__init__ is original_layout_init
    metadata = positive[0][1]
    kwargs = dict(metadata, cross_attn=positive[0][0],
                  latent_shapes=[v.shape for v in latent["samples"].tensors], device="cpu")
    baseline = model.get_model_object("extra_conds")(**kwargs)
    old_layout = baseline["minimax_payload"].cond["layout"]
    old_positions = old_layout.position_ids.clone()
    revised = patched.get_model_object("extra_conds")(**kwargs)
    layout = revised["minimax_payload"].cond["layout"]
    span = sum(_video_t_spans(5))
    for (lo, hi, kind) in layout.segments:
        expected = old_positions[lo:hi].clone()
        if kind in ("audio", "video"):
            expected[:, 0] += span
        torch.testing.assert_close(layout.position_ids[lo:hi, 1:], old_positions[lo:hi, 1:])
        if kind in ("audio", "video", "text"):
            torch.testing.assert_close(layout.position_ids[lo:hi], expected)
    guides = [row for row in layout.segments if row[2] in ("cond", "cond_audio")]
    origin = float(old_positions[layout.segments[-1][0], 0])
    assert [round(float(layout.position_ids[row[0], 0]) - origin, 9) for row in guides] == [
        0., round(span, 9), 0., round(span, 9), round(span, 9)]
    assert torch.equal(old_layout.position_ids, old_positions)
    for name in ("img_pos", "img_update", "audio_pos", "audio_update"):
        assert torch.equal(getattr(layout, name), getattr(old_layout, name))


def test_history_wrapper_calls_existing_delegate_preserves_other_conditions_and_exceptions():
    model = native_model()
    original = model.get_model_object("extra_conds")
    calls, sentinel = [], object()
    def delegate(**kwargs):
        calls.append(True)
        if kwargs.pop("test_error", False):
            raise RuntimeError("real delegate error")
        return dict(original(**kwargs), external_condition=sentinel)
    model.add_object_patch("extra_conds", delegate)
    patched = p.patch_history_model(model)
    out = patched.get_model_object("extra_conds")(device="cpu")
    assert out["external_condition"] is sentinel and calls == [True]
    with pytest.raises(RuntimeError, match="real delegate"):
        patched.get_model_object("extra_conds")(test_error=True)
    assert len(calls) == 2 and model.object_patches["extra_conds"] is delegate


def test_bad_shapes_stale_owned_plan_and_invalid_history_fail_before_encoding():
    value = plan(23)
    with pytest.raises(ValueError, match="no broadcast"):
        p.prepare_mask(value.frames, torch.zeros(1, 32, 64))
    with pytest.raises(ValueError, match="24fps"):
        p.make_plan(value.frames, value.green, value.clean, 30.)
    with pytest.raises(ValueError, match="actual"):
        p.validate_plan({}, 0)
    value.green[0, 0, 0, 0] = .9
    with pytest.raises(ValueError, match="changed"):
        p.select_window(value, 0)
    vv = FakeVideoVAE()
    with pytest.raises(ValueError, match="exact generated boundary"):
        p.condition_window(native_model(), FakeClip(), vv, FakeAudioVAE(), rgb(1),
                           rgb(22), "remove", rgb(18), pcm(18))
    assert not vv.encode_calls


def test_registration_is_additive_and_all_actual_schemas_resolve():
    nodes = asyncio.run(h3_audio_t8_pkg.comfy_entrypoint().get_node_list())
    position = nodes.index(NODES[0])
    assert nodes[position:position + len(NODES)] == NODES
    assert nodes[position - 1].define_schema().node_id == "MiniMaxH3BranchGuideEXPT8"
    for cls in NODES:
        schema = cls.define_schema()
        assert schema.get_v1_info(cls).name == cls.__name__
    assert len(set(cls.define_schema().node_id for cls in nodes)) == len(nodes)
