import asyncio
from copy import deepcopy
from dataclasses import replace
import json

import pytest
import torch
import h3_audio_t8_pkg
from h3_audio_t8_pkg import source_audio_plan as r
from h3_audio_t8_pkg.nodes_source_audio_plan import NODES


def master(rate=44100, frames=240):
    return dict(waveform=torch.arange(r.sample_at(frames, rate)).float().div(rate*100).view(1, 1, -1).repeat(1, 2, 1), sample_rate=rate)


def voices():
    return [dict(role_id="A", reference_ordinal=1), dict(role_id="B", reference_ordinal=2)]


def cue(start=216000, stop=225600):
    return dict(id="line-A", role_id="A", start_sample=start, end_sample=stop,
                guard_before_samples=1200, guard_after_samples=1200, text="今天真不错。")


@pytest.mark.parametrize("rate", [32000, 44100, 48000])
def test_global_endpoints_exact_reassembly_and_visible_legal_padding(rate):
    audio = master(rate)
    before = audio["waveform"].clone()
    plan, report = r.make_plan(audio, [0, 101, 197, 240], [], voices())
    outputs = []
    for index in range(3):
        drive, final, row = r.window(plan, audio, index)
        outputs.append(final["waveform"])
        assert (row["native_frames"]-5) % 17 == 0 and row["native_frames"] >= row["keep_frames"]
        assert torch.equal(drive["waveform"][..., :row["keep_samples"]], final["waveform"])
        assert not drive["waveform"][..., row["keep_samples"]:].any()
        assert not row["resampled"] and row["final_not_generated"]
    assert torch.equal(torch.cat(outputs, -1), before) and torch.equal(audio["waveform"], before)
    assert report["audio_semantics"]["voice"] == "reference_only_not_drive_or_final"
    assert report["ignored_source_tail_samples"] == 0


def test_phrase_and_breath_guard_reject_or_explicitly_shift_only_one_cut():
    audio = master()
    with pytest.raises(ValueError, match="phrase/breath"):
        r.make_plan(audio, [0, 120, 240], [cue()], voices())
    plan, report = r.make_plan(audio, [0, 120, 240], [cue()], voices(), cut_policy="shift_after_phrase", max_shift_frames=8)
    assert report["actual_cuts"] == [0, 124, 240] and len(report["adjustments"]) == 1
    assert len(report["windows"][0]["cues"]) == 1 and not report["windows"][1]["cues"]
    finals = [r.window(plan, audio, index)[1]["waveform"] for index in range(2)]
    assert torch.equal(torch.cat(finals, -1), audio["waveform"])
    with pytest.raises(ValueError, match="allowed shift"):
        r.make_plan(audio, [0, 120, 240], [cue()], voices(), cut_policy="shift_after_phrase", max_shift_frames=1)


@pytest.mark.parametrize("bad", ["voice", "speaker", "guard", "cuts", "nonfinite", "mutated"])
def test_real_audio_contract_errors_not_silently_fixed(bad):
    audio, assigned, cuts, cues = master(), voices(), [0,120,240], [cue(100000,110000)]
    if bad == "voice":
        assigned[1]["reference_ordinal"] = 1
    elif bad == "speaker":
        cues[0]["role_id"] = "C"
    elif bad == "guard":
        cues[0]["guard_before_samples"] = 100001
    elif bad == "cuts":
        cuts = [0,120,120,240]
    elif bad == "nonfinite":
        audio["waveform"][0,0,0] = float("nan")
    else:
        plan, _ = r.make_plan(audio,cuts,cues,assigned)
        audio["waveform"][0,0,0] += 1
        with pytest.raises(ValueError, match="master changed"):
            r.window(plan,audio,0)
        return
    with pytest.raises(ValueError):
        r.make_plan(audio,cuts,cues,assigned)


def test_plan_content_tamper_and_all_nodes_actual_schemas():
    audio = master()
    plan, report = r.make_plan(audio,[0,120,240],[],voices())
    changed = deepcopy(report)
    changed["windows"][0]["source_end_sample"] += 1
    with pytest.raises(ValueError, match="content changed"):
        r.window(replace(plan,json=json.dumps(changed)),audio,0)
    registered = asyncio.run(h3_audio_t8_pkg.comfy_entrypoint().get_node_list())
    start = registered.index(NODES[0])
    assert registered[start:start+2] == NODES
    assert len(registered) == len({node.define_schema().node_id for node in registered})
    for cls in NODES:
        assert cls.define_schema().get_v1_info(cls).name == cls.__name__
