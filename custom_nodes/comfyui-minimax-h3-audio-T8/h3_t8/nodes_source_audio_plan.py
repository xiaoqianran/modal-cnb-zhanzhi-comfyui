"""Optional external PCM planning; no change to old samplers/audio nodes."""
import json
from comfy_api.latest import io
from . import source_audio_plan as r
from .reference_package import canonical

PLAN = io.Custom("T8_H3_SOURCE_AUDIO_PLAN")
CATEGORY = "T8/MiniMax H3/Audio/Source Plan Experimental"


class MiniMaxH3SourceAudioPlanEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Source Audio · 全局切口与声音归属 (EXP/T8)", category=CATEGORY,
            is_experimental=True, description="24fps全局PCM时钟，显式字词/呼吸保护、角色与实际声音参考编号。默认拒绝切断整句；不ASR/TTS、不替换Temporal Chunk或原音。",
            inputs=[io.Audio.Input("source_audio"), io.String.Input("cuts_json", default="[0,120,240]", multiline=True),
                io.String.Input("cues_json", default="[]", multiline=True),
                io.String.Input("voices_json", default='[{"role_id":"A","reference_ordinal":1},{"role_id":"B","reference_ordinal":2}]', multiline=True),
                io.Combo.Input("cut_policy", options=["strict", "shift_after_phrase"], default="strict"),
                io.Int.Input("max_shift_frames", default=12, min=0, max=240)],
            outputs=[PLAN.Output("plan"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, source_audio, cuts_json="[0,120,240]", cues_json="[]", voices_json='[{"role_id":"A","reference_ordinal":1}]', cut_policy="strict", max_shift_frames=12):
        plan, report = r.make_plan(source_audio, json.loads(cuts_json), json.loads(cues_json), json.loads(voices_json),
                                   cut_policy=cut_policy, max_shift_frames=max_shift_frames)
        return io.NodeOutput(plan, canonical(report))


class MiniMaxH3SourceAudioWindowEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Source Audio · 选窗 DRIVE / FINAL (EXP/T8)", category=CATEGORY,
            is_experimental=True, description="DRIVE显式右补静音至合法5+17k帧；FINAL保留原PCM精确切片，视频解码后按keep_frames裁回。两路不同用途，声音参考仍经Reference Route单独接入。",
            inputs=[PLAN.Input("plan"), io.Audio.Input("source_audio"), io.Int.Input("window_index", default=0, min=0, max=255)],
            outputs=[io.Audio.Output("drive_audio"), io.Audio.Output("final_audio"), io.Int.Output("native_frames"),
                     io.Int.Output("keep_frames"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, plan, source_audio, window_index=0):
        drive, final, report = r.window(plan, source_audio, window_index)
        return io.NodeOutput(drive, final, report["native_frames"], report["keep_frames"], canonical(report))


NODES = [MiniMaxH3SourceAudioPlanEXPT8, MiniMaxH3SourceAudioWindowEXPT8]
