"""One ordinary prompt; retain a zero-event descriptor for old receipt inputs."""
from comfy_api.latest import io

from .prompt_relay_advanced import build_prompt_relay_plan, PROMPT_RELAY_PLAN_TYPE


class MiniMaxH3PlainPromptRecipeEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 · 完整提示词 / Ordinary Prompt",
            category="T8/MiniMax H3/Conditioning",
            description="One complete ordinary prompt. No local events, time ranges, attention routing or "
                        "Relay gain. The zero-event descriptor supports existing frame-count/cache receipts; "
                        "compiled_prompt connects to ordinary conditioning nodes.",
            inputs=[io.String.Input("prompt", multiline=True, dynamic_prompts=True),
                    io.Int.Input("length", default=124, min=5, step=17)],
            outputs=[io.Custom(PROMPT_RELAY_PLAN_TYPE).Output("prompt_recipe"),
                     io.String.Output("compiled_prompt"), io.Int.Output("length"),
                     io.String.Output("timeline_json"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, prompt, length=124):
        return io.NodeOutput(*build_prompt_relay_plan(
            global_prompt=prompt, local_prompts="", length=length, timing_mode="auto_equal",
            time_ranges="", math_profile="paper_v1", epsilon=.1, allow_gaps=False, allow_overlaps=False))


NODES = [MiniMaxH3PlainPromptRecipeEXPT8]
