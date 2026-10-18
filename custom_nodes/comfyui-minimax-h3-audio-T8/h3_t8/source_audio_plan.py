"""Explicit global PCM cuts, phrase guards and voice-role assignment.

Does not infer words/speakers, resample, synthesize audio, touch Temporal Chunk,
or equate a reference voice with drive/final audio. Padding is visible silence;
the final track is a byte-preserving source slice, not the padded drive copy.
"""
from dataclasses import dataclass
from fractions import Fraction
import json

import torch

from .reference_package import canonical, tensor_record, IDENTIFIER

SCHEMA = "t8.h09.source-audio-plan.v1"
MAX_BYTES = 256*1024**2


def sample_at(frame, rate):
    # The SAME global endpoint is used on both sides of each cut, including
    # rates not divisible by 24. Never sum locally rounded segment lengths.
    return round(Fraction(frame * rate, 24))


def _audio(value):
    if not isinstance(value, dict) or type(value.get("sample_rate")) is not int:
        raise ValueError("Source master needs an explicit integer sample rate")
    pcm, rate = value.get("waveform"), value["sample_rate"]
    if (type(pcm) is not torch.Tensor or pcm.device.type != "cpu" or pcm.dtype != torch.float32
            or pcm.ndim != 3 or pcm.shape[0] != 1 or pcm.shape[1] not in (1, 2)
            or pcm.shape[-1] < 1 or pcm.numel()*pcm.element_size() > MAX_BYTES
            or not 8000 <= rate <= 192000):
        raise ValueError("Source master needs bounded CPU float32 mono/stereo PCM, 8–192kHz")
    tensor_record(pcm)
    return pcm, rate


@dataclass(frozen=True)
class SourceAudioPlan:
    json: str
    source_record: dict

    def validate(self, audio):
        pcm, rate = _audio(audio)
        value = json.loads(self.json)
        if (value.get("schema") != SCHEMA or value.get("source") != self.source_record
                or self.source_record != dict(sample_rate=rate, waveform=tensor_record(pcm))):
            raise ValueError("Source master changed; rebuild cuts and voice assignment")
        unsigned = {key: item for key, item in value.items() if key != "sha256"}
        from .director_project import sha
        if sha(unsigned) != value.get("sha256"):
            raise ValueError("Source-audio plan content changed")
        return value


def make_plan(audio, cuts, cues, voices, *, cut_policy="strict", max_shift_frames=12):
    pcm, rate = _audio(audio)
    if (not isinstance(cuts, list) or not 2 <= len(cuts) <= 257
            or any(type(n) is not int or n < 0 for n in cuts) or cuts[0] != 0
            or any(b <= a for a, b in zip(cuts, cuts[1:]))
            or sample_at(cuts[-1], rate) > pcm.shape[-1]):
        raise ValueError("Cuts must be increasing global 24fps frame endpoints within the actual master")
    if (cut_policy not in ("strict", "shift_after_phrase") or type(max_shift_frames) is not int
            or not 0 <= max_shift_frames <= 240):
        raise ValueError("Select an explicit phrase-cut policy and bounded shift")
    if not isinstance(voices, list) or not 1 <= len(voices) <= 3:
        raise ValueError("Declare 1–3 ordered voice-role bindings, not inferred speaker identity")
    roles, ordinals = set(), set()
    for row in voices:
        if (type(row) is not dict or set(row) != {"role_id", "reference_ordinal"}
                or not isinstance(row["role_id"], str) or not IDENTIFIER.fullmatch(row["role_id"])
                or type(row["reference_ordinal"]) is not int or not 1 <= row["reference_ordinal"] <= 3
                or row["role_id"] in roles or row["reference_ordinal"] in ordinals):
            raise ValueError("Voice roles and actual reference ordinals must be distinct and explicit")
        roles.add(row["role_id"])
        ordinals.add(row["reference_ordinal"])
    if not isinstance(cues, list) or len(cues) > 1024:
        raise ValueError("Use a bounded explicit PCM cue list")
    seen, guarded = set(), []
    for row in cues:
        if (type(row) is not dict or set(row) != {"id", "role_id", "start_sample", "end_sample", "guard_before_samples", "guard_after_samples", "text"}
                or not isinstance(row["id"], str) or not IDENTIFIER.fullmatch(row["id"])
                or row["id"] in seen or row["role_id"] not in roles
                or not isinstance(row["text"], str) or not row["text"].strip() or len(row["text"]) > 4096
                or any(type(row[key]) is not int for key in ("start_sample", "end_sample", "guard_before_samples", "guard_after_samples"))
                or not 0 <= row["start_sample"] < row["end_sample"] <= sample_at(cuts[-1], rate)
                or min(row["guard_before_samples"], row["guard_after_samples"]) < 0
                or max(row["guard_before_samples"], row["guard_after_samples"]) > rate*10
                or row["start_sample"]-row["guard_before_samples"] < 0
                or row["end_sample"]+row["guard_after_samples"] > sample_at(cuts[-1], rate)):
            raise ValueError("Cue must declare actual global samples, literal dialogue, role and explicit breath guards")
        seen.add(row["id"])
        guarded.append((row["start_sample"]-row["guard_before_samples"],
                        row["end_sample"]+row["guard_after_samples"], row["id"]))
    actual = list(cuts)
    adjustments = []
    for index in range(1, len(cuts)-1):
        desired = cuts[index]
        while True:
            sample = sample_at(actual[index], rate)
            crossed = [row for row in guarded if row[0] < sample < row[1]]
            if not crossed:
                break
            if cut_policy == "strict":
                raise ValueError("Cut splits an explicitly guarded phrase/breath: " + ", ".join(row[2] for row in crossed))
            target_sample = max(row[1] for row in crossed)
            # Smallest whole frame endpoint not earlier than the guard's end.
            target = (target_sample*24 + rate-1)//rate
            actual[index] = max(actual[index]+1, target)
            if actual[index]-desired > max_shift_frames or actual[index] >= cuts[index+1]:
                raise ValueError("No phrase-safe cut within the explicitly allowed shift")
        if actual[index] != desired:
            adjustments.append(dict(index=index, requested_frame=desired, actual_frame=actual[index]))
    if any(b <= a for a, b in zip(actual, actual[1:])):
        raise ValueError("Adjusted cuts are not increasing")
    rows = []
    for index, (start, stop) in enumerate(zip(actual, actual[1:])):
        kept = stop-start
        frames = max(5, ((max(5, kept)-5+16)//17)*17+5)
        if frames > 362:
            raise ValueError("One native source-audio window exceeds 362 frames; choose explicit shorter cuts")
        begin, end = sample_at(start, rate), sample_at(stop, rate)
        padded_end = sample_at(start+frames, rate)
        selected = [dict(cue, local_start_sample=cue["start_sample"]-begin,
                         local_end_sample=cue["end_sample"]-begin) for cue in cues
                    if cue["start_sample"] >= begin and cue["end_sample"] <= end]
        rows.append(dict(index=index, global_start_frame=start, global_end_frame=stop,
            source_start_sample=begin, source_end_sample=end, native_frames=frames,
            keep_frames=kept, trim_right_frames=frames-kept, keep_samples=end-begin,
            pad_right_samples=padded_end-end, drive_samples=padded_end-begin, cues=selected))
    source = dict(sample_rate=rate, waveform=tensor_record(pcm))
    value = dict(schema=SCHEMA, fps=24, source=source, requested_cuts=cuts, actual_cuts=actual,
                 adjustments=adjustments, windows=rows, voice_bindings=voices, cut_policy=cut_policy,
                 audio_semantics=dict(drive="source_plus_explicit_right_silence", final="original_source_no_padding",
                     voice="reference_only_not_drive_or_final", inferred_speaker=False, tts=False),
                 ignored_source_tail_samples=pcm.shape[-1]-sample_at(cuts[-1], rate), automatic_accept=False)
    from .director_project import sha
    value["sha256"] = sha(value)
    plan = SourceAudioPlan(canonical(value), source)
    plan.validate(audio)
    return plan, value


def window(plan, audio, index):
    if not isinstance(plan, SourceAudioPlan) or type(index) is not int:
        raise ValueError("Use an actual source-audio plan and explicit window index")
    value = plan.validate(audio)
    if not 0 <= index < len(value["windows"]):
        raise ValueError("Source-audio window index is outside the plan")
    row = value["windows"][index]
    pcm, rate = _audio(audio)
    final = pcm[..., row["source_start_sample"]:row["source_end_sample"]].clone()
    drive = torch.nn.functional.pad(final, (0, row["pad_right_samples"]))
    report = dict(row, plan_sha256=value["sha256"], final_record=tensor_record(final),
                  drive_record=tensor_record(drive), resampled=False, inferred_dialogue=False,
                  voice_bindings=value["voice_bindings"], final_not_generated=True)
    return dict(waveform=drive, sample_rate=rate), dict(waveform=final, sample_rate=rate), report
