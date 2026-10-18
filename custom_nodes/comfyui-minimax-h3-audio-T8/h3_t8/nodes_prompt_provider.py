"""Optional external proposal provider; three explicit request/rewrite/adopt steps."""
import json
from comfy_api.latest import io
from . import prompt_provider as r
from .reference_package import canonical

REQUEST = io.Custom("T8_H3_PROMPT_REQUEST")
PROPOSAL = io.Custom("T8_H3_PROMPT_PROPOSAL")
CATEGORY = "T8/MiniMax H3/Prompt/FreeToken Experimental"


class MiniMaxH3FreeTokenRequestEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__,display_name="H3 FreeToken · 原稿与图片声明 (EXP/T8)",category=CATEGORY,
            is_experimental=True,description="保留原稿；可选<=8图片，逐张声明first/last/reference；不支持音视频混合输入。对白/歌词/文字需显式列入保护字串。",
            inputs=[io.String.Input("original_text",default="",multiline=True),io.Float.Input("seconds",default=5.,min=1.,max=60.),
                io.String.Input("image_roles_json",default="[]",multiline=True),io.String.Input("protected_literals_json",default="[]",multiline=True),
                io.Image.Input("images",optional=True)],
            outputs=[REQUEST.Output("request"),io.String.Output("original_text")])

    @classmethod
    def execute(cls,original_text,seconds=5.,image_roles_json="[]",protected_literals_json="[]",images=None):
        request = r.make_request(original_text,seconds,json.loads(image_roles_json),json.loads(protected_literals_json),images)
        return io.NodeOutput(request,original_text)


class MiniMaxH3FreeTokenRewriteEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__,display_name="H3 FreeToken · 单次待审提案 (EXP/T8)",category=CATEGORY,
            is_experimental=True,description="独立prepared配置／固定Qwen3-VL-4B／单次子进程。只提案、不自动换词、不采H3、不认证事实；失败不改原文。",
            inputs=[REQUEST.Input("request"),io.String.Input("runtime_config",default="")],
            outputs=[PROPOSAL.Output("proposal"),io.String.Output("candidate_text"),io.String.Output("report_json")])

    @classmethod
    def execute(cls,request,runtime_config):
        from comfy.model_management import throw_exception_if_processing_interrupted
        proposal,report = r.rewrite(request,runtime_config,interrupt=throw_exception_if_processing_interrupted)
        return io.NodeOutput(proposal,proposal.verify(request)["text"],canonical(report))


class MiniMaxH3FreeTokenAdoptEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__,display_name="H3 FreeToken · 显式采用／保原稿 (EXP/T8)",category=CATEGORY,
            is_experimental=True,description="默认输出原稿。显式采用前核实际原稿/图片与提案身份；不改导演台事实或素材接线，不证明语义正确。",
            inputs=[REQUEST.Input("request"),PROPOSAL.Input("proposal"),io.Boolean.Input("confirm_adopt",default=False)],
            outputs=[io.String.Output("text"),io.String.Output("report_json")])

    @classmethod
    def execute(cls,request,proposal,confirm_adopt=False):
        text,report = r.choose(request,proposal,confirm_adopt)
        return io.NodeOutput(text,canonical(report))


NODES = [MiniMaxH3FreeTokenRequestEXPT8,MiniMaxH3FreeTokenRewriteEXPT8,MiniMaxH3FreeTokenAdoptEXPT8]
