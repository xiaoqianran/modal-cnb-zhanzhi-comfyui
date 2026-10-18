"""Append-only AudioFirst helpers. Existing Speech/SourceAV nodes stay intact."""
from comfy_api.latest import io

from .audio_first import audit, project

CATEGORY = "T8/MiniMax H3/AudioFirst Experimental"


class MiniMaxH3AudioFirstProjectionEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 AudioFirst · 同条件Tiny投影",
            category=CATEGORY, is_experimental=True,
            description="复用完整场景embedding，CLIP零次。T2VA或单首帧；有首帧时用原图/VAE重新编码32×32，不能缩放原latent冒充。帧数来自完整AV。多参考/空间/已编译窗条件保留旧路线，不静默丢弃。",
            inputs=[io.Conditioning.Input("positive"), io.Latent.Input("video_latent"),
                    io.Image.Input("first_frame", optional=True), io.Vae.Input("video_vae", optional=True)],
            outputs=[io.Conditioning.Output("tiny_positive"), io.Latent.Output("tiny_av_latent"),
                     io.String.Output("report_json")])

    @classmethod
    def execute(cls, positive, video_latent, first_frame=None, video_vae=None):
        result = project(positive, video_latent, first_frame, video_vae)
        return io.NodeOutput(*result, ui={"text": [result[-1]]})


class MiniMaxH3AudioFirstLockAuditEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 AudioFirst · 实际成片锁音审计",
            category=CATEGORY, is_experimental=True,
            description="Tiny完成denoised_output→SourceAVPrepare regenerate/lock strict→实际完整视频denoised_output。核三LATENT时钟、原音频绑定、mask1/0、finite及固定2e-5；原样返回实际最终输出，不替换音频，不代替完整成片人审。",
            inputs=[io.Latent.Input("audio_source"), io.Latent.Input("locked_input"),
                    io.Latent.Input("samples")],
            outputs=[io.Latent.Output("samples"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, audio_source, locked_input, samples):
        result = audit(audio_source, locked_input, samples)
        return io.NodeOutput(*result, ui={"text": [result[-1]]})


NODES = [MiniMaxH3AudioFirstProjectionEXPT8, MiniMaxH3AudioFirstLockAuditEXPT8]
