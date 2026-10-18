"""Read-only phase card from verified completed native FreeVideo receipts."""
import json
from comfy_api.latest import io
from .freevideo_phases import phase_report
from .freevideo_phase_live import completed_card_notice


def bounded_report(raw):
    if not isinstance(raw, str) or len(raw.encode()) > 65536:
        raise ValueError("Phase receipt JSON must be bounded")
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError("Phase receipt must be an object")
    return value


class MiniMaxH3FreeVideoPhaseCardEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="FreeVideo·阶段耗时卡（只读）",
            category="T8/MiniMax H3/Diagnostics", is_experimental=True, is_output_node=True,
            description="连接完成Stage，区分load/compile/transfer/采样/VAE/mux。旧收据缺失字段=不可用而非0；nested/并行计时不相加，NFE0不等于挂起，不自动重启。",
            inputs=[io.Custom("H3_T8_FREEVIDEO_QUALITY_STAGE").Input("completed_quality_stage", optional=True),
                    io.Custom("H3_T8_FREEVIDEO_INT8_STAGE").Input("completed_int8_stage", optional=True),
                    io.String.Input("decode_report_json", default="{}", multiline=True),
                    io.String.Input("mux_report_json", default="{}", multiline=True)],
            outputs=[io.String.Output("report_json")])

    @classmethod
    def execute(cls, completed_quality_stage=None, completed_int8_stage=None,
                decode_report_json="{}", mux_report_json="{}"):
        if (completed_quality_stage is None) == (completed_int8_stage is None):
            raise ValueError("Connect exactly one actual completed Stage")
        if completed_quality_stage is not None:
            from .freevideo_quality.runtime import validate_stage
            receipt = validate_stage(completed_quality_stage)
        else:
            from .freevideo_int8.runtime import validate_stage
            receipt = validate_stage(completed_int8_stage)
        report = json.dumps(phase_report(receipt, bounded_report(decode_report_json), bounded_report(mux_report_json)),
                            ensure_ascii=False, allow_nan=False)
        completed_card_notice(receipt)
        return io.NodeOutput(report, ui={"text": [report]})

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        # This new diagnostic refreshes its execution-bound UI notice. Actual
        # Stage validation remains required; no sampler is invalidated/requeued.
        return float("nan")


NODES = [MiniMaxH3FreeVideoPhaseCardEXPT8]
