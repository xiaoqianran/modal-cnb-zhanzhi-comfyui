"""Scene-aware additive entrances; original Request/Rewrite/Adopt unchanged."""
import json
from comfy_api.latest import io
from . import prompt_scene_ticket as ticket
from .nodes_prompt_provider import REQUEST

TICKET = io.Custom("T8_H3_SCENE_PROMPT_TICKET")
PROPOSAL = io.Custom("T8_H3_SCENE_PROMPT_PROPOSAL")
CATEGORY = "T8/MiniMax H3/Prompt/FreeToken Experimental"


class MiniMaxH3ScenePromptTicketEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 FreeToken·镜头请求票据",
            category=CATEGORY, is_experimental=True,
            description="复用旧Request，绑定scene_id+revision+request_id+原稿/素材SHA。每个新异步请求明确更换request_id；不改旧请求格式或prepared配置。",
            inputs=[REQUEST.Input("request"), io.String.Input("scene_id", default="scene_1"),
                    io.Int.Input("scene_revision", default=0, min=0, max=2**31-1),
                    io.String.Input("request_id", default="request_1")],
            outputs=[TICKET.Output("scene_ticket"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, request, scene_id="scene_1", scene_revision=0, request_id="request_1"):
        value = ticket.bind(request, scene_id, scene_revision, request_id)
        return io.NodeOutput(value, json.dumps(value.verify(), ensure_ascii=False))


class MiniMaxH3ScenePromptRewriteEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 FreeToken·镜头绑定提案",
            category=CATEGORY, is_experimental=True,
            description="实际原H09 provider，发出前绑定票据，返回后仍归原镜头；不采H3、不自动采用、无新下载/云服务。",
            inputs=[TICKET.Input("scene_ticket"), io.String.Input("runtime_config", default="")],
            outputs=[PROPOSAL.Output("scene_proposal"), io.String.Output("candidate_text"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, scene_ticket, runtime_config):
        from comfy.model_management import throw_exception_if_processing_interrupted
        value, report = ticket.rewrite(scene_ticket, runtime_config, interrupt=throw_exception_if_processing_interrupted)
        return io.NodeOutput(value, value.verify()["text"], json.dumps(report, ensure_ascii=False))


class MiniMaxH3ScenePromptAdoptEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 FreeToken·核当前镜头后采用",
            category=CATEGORY, is_experimental=True, is_output_node=True,
            description="默认保当前原稿，迟到提案可看原镜头历史但不可跨scene/revision/request采用；事实与质量仍需真人判断。",
            inputs=[TICKET.Input("current_scene_ticket"), PROPOSAL.Input("scene_proposal"),
                    io.Boolean.Input("confirm_adopt", default=False)],
            outputs=[io.String.Output("text"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, current_scene_ticket, scene_proposal, confirm_adopt=False):
        text, report = ticket.choose(current_scene_ticket, scene_proposal, confirm_adopt)
        raw = json.dumps(report, ensure_ascii=False)
        return io.NodeOutput(text, raw, ui={"text": [raw]})


NODES = [MiniMaxH3ScenePromptTicketEXPT8, MiniMaxH3ScenePromptRewriteEXPT8, MiniMaxH3ScenePromptAdoptEXPT8]
