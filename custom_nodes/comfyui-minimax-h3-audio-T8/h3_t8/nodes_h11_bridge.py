"""Append-only explicit Bridge guidance import. Existing auto/manual nodes unchanged."""
from pathlib import Path
from comfy_api.latest import io
from .nodes_semantic_bridge import BridgeIO, model_paths, resolve_model
from .semantic_bridge import canonical
from .bridge_sidecar import sidecar_config


class MiniMaxH3SemanticBridgeSidecarPresetEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 语义桥·模型专属参数说明（显式采用）",
            category="T8/MiniMax H3/Semantic Bridge", is_experimental=True, is_output_node=True,
            description="读取Trainer inference_settings.json并核实际完整权重SHA。固定内嵌契约优先；0.12只是未校准起点。默认不采用/不Apply，旧0.10和多桥顺序不改。",
            inputs=[io.Combo.Input("model_name", options=list(model_paths()) or ["No Semantic Bridge models installed"]),
                    io.String.Input("sidecar_path", default="", tooltip="留空只读所选权重同目录inference_settings.json；也可明确选择说明的本机绝对路径。model_file仅显示标签，不用于找权重。"),
                    io.Boolean.Input("confirm_adopt", default=False),
                    io.Combo.Input("device", options=["auto", "cpu", "cuda"], default="auto")],
            outputs=[BridgeIO.Output("semantic_bridge"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, model_name, sidecar_path="", confirm_adopt=False, device="auto"):
        weight = resolve_model(model_name)
        path = sidecar_path or str(Path(weight).parent / "inference_settings.json")
        config, data = sidecar_config(weight, path, confirm_adopt=confirm_adopt, device=device)
        report = canonical(data)
        return io.NodeOutput(config, report, ui={"text": [report]})

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("nan")  # recheck both files; no stale adoption from an old sidecar


NODES = [MiniMaxH3SemanticBridgeSidecarPresetEXPT8]
