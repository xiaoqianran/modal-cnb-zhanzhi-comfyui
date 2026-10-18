"""Separated, opt-in person-removal ports; old workflows remain untouched."""
import uuid

from comfy_api.latest import io

from . import person_removal as runtime
from .nodes_source_conform import FRAME_MAP, LINEAGE
from .source_conform import canonical

PLAN = io.Custom("T8_H3_PERSON_REMOVAL_PLAN")
CATEGORY = "T8/MiniMax H3/Repair/Experimental/Person Removal"
PROMPT = ("Remove the green-masked person and reconstruct the background. "
          "Preserve the rest of the video, including its camera motion and frame timing.")


def schema(cls, title, inputs, outputs, description):
    return io.Schema(node_id=cls.__name__, display_name="H3 Person · " + title + " (EXP/T8)",
                     category=CATEGORY, inputs=inputs, outputs=outputs,
                     description=description, is_experimental=True)


class MiniMaxH3PersonMaskEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return schema(cls, "External MASK + Green Preview / 外置遮罩预览", [
            io.Image.Input("frames"), io.Mask.Input("mask"),
            io.Int.Input("grow", default=5, min=0, max=64),
            io.Int.Input("feather", default=0, min=0, max=32),
            FRAME_MAP.Input("frame_map", optional=True), LINEAGE.Input("lineage", optional=True)],
            [io.Mask.Output("processed_mask"), io.Image.Output("green_guide"),
             io.String.Output("report_json")],
            "One MASK per frame, no broadcast or invented tracking. Optional original MASK + "
            "actual Source Conform map reuses its frame selection. Green is an RGB visual guide, "
            "not a sampling mask. Empty frames remain empty. No segmentation model download.")

    @classmethod
    def execute(cls, frames, mask, grow=5, feather=0, frame_map=None, lineage=None):
        result, green, report = runtime.prepare_mask(frames, mask, grow, feather, frame_map, lineage)
        return io.NodeOutput(result, green, canonical(report))


class MiniMaxH3PersonPlanEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return schema(cls, "Window Plan / 移除窗口计划", [
            io.Image.Input("frames"), io.Image.Input("green_guide"), io.Image.Input("clean_first_frame"),
            io.Float.Input("source_fps", default=24., min=.1, max=240.)],
            [PLAN.Output("plan"), io.Int.Output("window_count"), io.String.Output("report_json")],
            "Source, externally prepared green guide and one clean first frame must share geometry. "
            "24fps, 22-frame native windows, 18-frame generated AV history. Author recipe is "
            "12 steps PER WINDOW (120 delivered frames need 6 windows / 72 sampler steps). "
            "Full-frame regeneration, not pixel locking; visual removal does not remove a voice.")

    @classmethod
    def execute(cls, frames, green_guide, clean_first_frame, source_fps=24.):
        plan, report = runtime.make_plan(frames, green_guide, clean_first_frame, source_fps)
        return io.NodeOutput(plan, len(plan.starts), canonical(report))


class MiniMaxH3PersonWindowEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return schema(cls, "Select Window / 选窗与历史", [
            PLAN.Input("plan"), io.Int.Input("window_index", default=0, min=0, max=4095),
            io.Image.Input("previous_frames", optional=True), io.Audio.Input("previous_audio", optional=True)],
            [io.Image.Output("anchor"), io.Image.Output("green_window"), io.Image.Output("history_frames"),
             io.Audio.Output("history_audio"), io.String.Output("report_json")],
            "First window uses the clean anchor; later windows use the previous generated boundary "
            "and 18 aligned generated AV frames. Connect cumulative Append outputs, not original "
            "source PCM. Short final tails pad guide frames only and are trimmed on Append.")

    @classmethod
    def execute(cls, plan, window_index=0, previous_frames=None, previous_audio=None):
        *values, report = runtime.select_window(plan, window_index, previous_frames, previous_audio)
        return io.NodeOutput(*values, canonical(report))


class MiniMaxH3PersonConditioningEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return schema(cls, "Native Conditioning / 原生移除条件", [
            io.Model.Input("model"), io.Clip.Input("clip"), io.Vae.Input("video_vae"),
            io.Vae.Input("audio_vae"), io.Image.Input("anchor"), io.Image.Input("green_window"),
            io.String.Input("prompt", default=PROMPT, multiline=True, dynamic_prompts=True),
            io.Image.Input("history_frames", optional=True), io.Audio.Input("history_audio", optional=True)],
            [io.Model.Output("model"), io.Conditioning.Output("positive"), io.Latent.Output("av_latent"),
             io.String.Output("report_json")],
            "External Ref2VA MODEL + Person Remover V1 LoRA strength1; no internal loading. "
            "Qwen sees Picture1/Video1; native VAE encodes green guide and generated history. "
            "MODEL-only history adapter preserves delegates and never patches global Core. "
            "Use output MODEL with stock CFG1 (same positive/negative), er_sde/simple12, "
            "shift video12/audio3. Separate sampler/decode/append. No Turbo or automatic double pass.")

    @classmethod
    def execute(cls, model, clip, video_vae, audio_vae, anchor, green_window, prompt=PROMPT,
                history_frames=None, history_audio=None):
        *values, report = runtime.condition_window(model, clip, video_vae, audio_vae,
            anchor, green_window, prompt, history_frames, history_audio)
        return io.NodeOutput(*values, canonical(report))


class MiniMaxH3PersonAppendEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return schema(cls, "Append AV / 窗口精确合并", [
            PLAN.Input("plan"), io.Int.Input("window_index", default=0, min=0, max=4095),
            io.Image.Input("frames"), io.Audio.Input("generated_audio"),
            io.Image.Input("previous_frames", optional=True), io.Audio.Input("previous_audio", optional=True)],
            [io.Image.Output("frames"), io.Audio.Output("generated_context_audio"),
             io.String.Output("report_json")],
            "Append full native 22-frame decoded windows on the global frame/PCM sample timeline. "
            "Discard overlap once; final frames exactly match source length. Generated audio is "
            "context for the NEXT window, not automatic final delivery. Save silent by default, "
            "or explicitly mux original source audio (including any removed person's voice). "
            "This is in-memory assembly, not persistent reroll/resume certification.")

    @classmethod
    def execute(cls, plan, window_index, frames, generated_audio, previous_frames=None, previous_audio=None):
        result, audio, report = runtime.append_window(plan, window_index, frames, generated_audio,
                                                       previous_frames, previous_audio)
        return io.NodeOutput(result, audio, canonical(report))


NODES = [MiniMaxH3PersonMaskEXPT8, MiniMaxH3PersonPlanEXPT8, MiniMaxH3PersonWindowEXPT8,
         MiniMaxH3PersonConditioningEXPT8, MiniMaxH3PersonAppendEXPT8]

for _node in NODES:
    _node.fingerprint_inputs = classmethod(lambda cls, **inputs: uuid.uuid4().hex)
