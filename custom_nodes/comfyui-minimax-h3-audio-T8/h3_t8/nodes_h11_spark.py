"""Append-only Spark nodes; samplers, conditions and model selection stay external."""
import json
from comfy_api.latest import io
from .spark_runtime import apply_spark, preflight

STATE = io.Custom("H3_T8_SPARK_STATE")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class MiniMaxH3SparkPreflightEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Spark 后端预检（只读）",
            category="T8/MiniMax H3/Spark", is_experimental=True, is_output_node=True,
            description="核官方v0.1.2来源SHA和SM89/cu130轮子。不会安装、采样或自动选模型；不授画质/提速资格。",
            inputs=[io.String.Input("runtime_config", default="")],
            outputs=[io.String.Output("report_json")])

    @classmethod
    def execute(cls, runtime_config):
        report = canonical(preflight(runtime_config))
        return io.NodeOutput(report, ui={"text": [report]})

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("nan")


class MiniMaxH3SparkApplyEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Spark 注意力·独立阶段（SM89）",
            category="T8/MiniMax H3/Spark", is_experimental=True,
            description="MODEL→MODEL，LOW/HIGH各自接SIGMAS与阶段。保留已有block owner/未知hook/mask；无法组合处委托且报告未生效。真实kernel异常不回退。",
            inputs=[io.Model.Input("model"), io.Sigmas.Input("sigmas"),
                    io.String.Input("runtime_config", default=""), io.Boolean.Input("enabled", default=True),
                    io.String.Input("stage", default="SINGLE"),
                    io.Combo.Input("mode", options=["spark", "dense_control"], default="spark"),
                    io.Int.Input("warmup_steps", default=0, min=0, max=2048),
                    io.Int.Input("dense_layers", default=1, min=0, max=128),
                    io.Int.Input("min_tokens", default=1024, min=1, max=1000000),
                    io.Float.Input("topk_ratio", default=.2, min=.01, max=1.)],
            outputs=[io.Model.Output("model"), STATE.Output("spark_state"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, model, sigmas, runtime_config, **kwargs):
        result, state = apply_spark(model, sigmas, runtime_config, **kwargs)
        report = canonical(state.report() if state is not None else {"enabled": False, "model_unchanged": True})
        return io.NodeOutput(result, state, report)


class MiniMaxH3SparkAuditEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Spark 实际调用审计（采样后）",
            category="T8/MiniMax H3/Spark", is_experimental=True, is_output_node=True,
            description="after_sampling接实际采样latent保证执行顺序。Sparse=0不算Spark通过，保留委托范围和真实异常；不自动认证画质或速度。",
            inputs=[STATE.Input("spark_state"), io.Latent.Input("after_sampling")],
            outputs=[io.String.Output("report_json")])

    @classmethod
    def execute(cls, spark_state, after_sampling):
        report = canonical(spark_state.report() if spark_state is not None else {"enabled": False})
        return io.NodeOutput(report, ui={"text": [report]})

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float("nan")


NODES = [MiniMaxH3SparkPreflightEXPT8, MiniMaxH3SparkApplyEXPT8, MiniMaxH3SparkAuditEXPT8]
