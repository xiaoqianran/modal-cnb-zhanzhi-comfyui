"""New explicit reference projection, old required video-VAE schema untouched."""
import json
from comfy_api.latest import io
from .audio_reference_only import capture, build
from .core import sorted_autogrow_values
from .nodes_reference_package import RECIPE
from .nodes_semantic_bridge import BridgeIO

SOURCE = io.Custom("H3_T8_AUDIO_ONLY_REFERENCE")


class MiniMaxH3AudioOnlyReferenceEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 参考·仅音频VAE准备",
            category="T8/MiniMax H3/References Experimental", is_experimental=True,
            description="明确原声来源，Qwen可看参考RGB，DiT只接音频latent。paired视频保留来源标记；不调用video VAE、不把声纹参考当DRIVE或FINAL。",
            inputs=[io.Audio.Input("audio"), io.Vae.Input("audio_vae"), io.String.Input("role_id", default="A"),
                io.Combo.Input("origin", options=["standalone_audio", "paired_video_soundtrack"], default="standalone_audio"),
                io.Combo.Input("grounding_kind", options=["none", "image", "video"], default="none"),
                io.Image.Input("frames", optional=True)],
            outputs=[SOURCE.Output("audio_reference"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, audio, audio_vae, role_id="A", origin="standalone_audio", grounding_kind="none", frames=None):
        source, report = capture(role_id, origin, grounding_kind, audio, audio_vae, frames)
        text = json.dumps(report, ensure_ascii=False)
        return io.NodeOutput(source, text, ui={"text": [text]})


class MiniMaxH3AudioOnlyConditioningEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 参考·no_visual_latent条件",
            category="T8/MiniMax H3/References Experimental", is_experimental=True,
            description="新独立入口，不改旧图。来源按输入slot顺序，原生positive/AV latent与raw text recipe供外置Sampler/Bridge/EAV/Relay。仅明确Ref2VA音频参考路径，画质/声纹待验。",
            inputs=[io.Clip.Input("clip"), io.Vae.Input("audio_vae"),
                io.Autogrow.Input("sources", template=io.Autogrow.TemplatePrefix(input=SOURCE.Input("source"), prefix="source_", min=1, max=3)),
                io.String.Input("prompt", multiline=True), io.Int.Input("width", default=864, min=32, step=32),
                io.Int.Input("height", default=480, min=32, step=32), io.Int.Input("length", default=124, min=5, step=17),
                io.Combo.Input("audio_mode", options=["native", "reference_only", "lock_source", "remix_source"], default="native"),
                io.Audio.Input("drive_audio", optional=True), io.Audio.Input("final_audio", optional=True),
                BridgeIO.Input("semantic_bridge", optional=True)],
            outputs=[io.Conditioning.Output("positive"), io.Latent.Output("av_latent"), io.Audio.Output("mux_audio"),
                     io.String.Output("conditioned_prompt"), io.String.Output("media_map_json"),
                     io.String.Output("report_json"), RECIPE.Output("native_text_recipe")])

    @classmethod
    def execute(cls, clip, audio_vae, sources, prompt, width=864, height=480, length=124, **kwargs):
        values = build(clip, audio_vae, sorted_autogrow_values(sources), prompt, width, height, length, **kwargs)
        return io.NodeOutput(*values, ui={"text": [values[5]]})


NODES = [MiniMaxH3AudioOnlyReferenceEXPT8, MiniMaxH3AudioOnlyConditioningEXPT8]
