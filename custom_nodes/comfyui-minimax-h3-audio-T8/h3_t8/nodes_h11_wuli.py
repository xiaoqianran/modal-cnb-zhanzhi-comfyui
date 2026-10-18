"""Append-only native Wuli recipe entrances; conditioning and sampling external."""
import json
import folder_paths
from comfy_api.latest import io
from .wuli_native import native4, native8

STATE = io.Custom("H3_T8_WULI_STATE")


def outputs():
    return [io.Model.Output("model"), io.Sigmas.Output("sigmas"), io.Sampler.Output("sampler"),
            STATE.Output("recipe_state"), io.String.Output("report_json")]


def result(values):
    model, sigmas, sampler, state = values
    return io.NodeOutput(model, sigmas, sampler, state, json.dumps(state.report(), ensure_ascii=False))


class MiniMaxH3Wuli8RecipeEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Wuli·原生8步配方",
            category="T8/MiniMax H3/Wuli", is_experimental=True,
            description="外置原生UNETLoader选择Wuli8完整模型。明确12/3、simple8、Euler，Guider使用CFG1；不证明任意HIGH或所有LoRA组合。",
            inputs=[io.Model.Input("model")], outputs=outputs())

    @classmethod
    def execute(cls, model):
        return result(native8(model))


class MiniMaxH3Wuli4ComposeEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        names = folder_paths.get_filename_list("loras")
        return io.Schema(node_id=cls.__name__, display_name="H3 Wuli·原生4步三文件组合",
            category="T8/MiniMax H3/Wuli", is_experimental=True,
            description="原始full FL2VA MODEL→trunk→widen→head set，三原件SHA核验、强度1。只用Core现有LoRA/reshape/set/headbank；外置条件和Sampler，不改旧图。",
            inputs=[io.Model.Input("model"), io.Combo.Input("trunk", options=names),
                    io.Combo.Input("widen", options=names), io.Combo.Input("set", options=names)],
            outputs=outputs())

    @classmethod
    def execute(cls, model, trunk, widen, set):
        paths = {role: folder_paths.get_full_path_or_raise("loras", name)
                 for role, name in (("trunk", trunk), ("widen", widen), ("set", set))}
        return result(native4(model, paths))


class MiniMaxH3WuliAuditEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Wuli·实际轨迹审计",
            category="T8/MiniMax H3/Wuli", is_experimental=True, is_output_node=True,
            inputs=[STATE.Input("recipe_state"), io.Latent.Input("after_sampling")],
            outputs=[io.String.Output("report_json")])

    @classmethod
    def execute(cls, recipe_state, after_sampling):
        report = json.dumps(recipe_state.report(), ensure_ascii=False, allow_nan=False)
        return io.NodeOutput(report, ui={"text": [report]})

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("nan")


NODES = [MiniMaxH3Wuli8RecipeEXPT8, MiniMaxH3Wuli4ComposeEXPT8, MiniMaxH3WuliAuditEXPT8]
