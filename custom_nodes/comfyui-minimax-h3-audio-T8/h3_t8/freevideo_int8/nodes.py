"""Independent prepared INT8 nodes; legacy classes, schemas and configs stay intact."""
from pathlib import Path
import os

import folder_paths
from comfy_api.latest import io
from ..freevideo_exp.nodes import (offload_supplied_clip, MiniMaxH3FreeVideoEAVEXPT8,
    MiniMaxH3FreeVideoLoRAEXPT8, MiniMaxH3FreeVideoPromptRelayEXPT8)
from ..freevideo_exp.runtime import canonical, with_lora
from ..freevideo_exp.effects import with_eav, build_relay_conditioning
from . import runtime as fv
from ..freevideo_quality.profiles import LABELS, plan
from ..freevideo_phase_live import core_progress

MODEL = io.Custom("H3_T8_FREEVIDEO_INT8_MODEL")
STAGE = io.Custom("H3_T8_FREEVIDEO_INT8_STAGE")
CATEGORY = "T8/MiniMax H3/FreeVideo/INT8 v1"


def callbacks(total):
    import comfy.model_management
    import comfy.utils
    bar = comfy.utils.ProgressBar(total)
    return comfy.model_management.throw_exception_if_processing_interrupted, core_progress(bar, total)


class MiniMaxH3FreeVideoINT8LoaderEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="FreeVideo INT8 · 新四档模型加载", category=CATEGORY,
            is_experimental=True, description="独立v0.3.20 prepared ConvRot INT8与参考音频t=1；旧FP8／四档／8+2／4+4配置不变。先显式准备原件、质量表及新INT8内核检查；不在Loader下载。",
            inputs=[io.String.Input("runtime_config", default="", tooltip="专用user/default/T8/freevideo-runtime-int8-v1.json；不读取旧默认环境变量")],
            outputs=[MODEL.Output("freevideo_model"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, runtime_config=""):
        path = runtime_config.strip() or os.environ.get("T8_FREEVIDEO_INT8_RUNTIME_CONFIG") or str(Path(folder_paths.get_user_directory()) / "default/T8/freevideo-runtime-int8-v1.json")
        model = fv.load_model(path)
        config = fv.config_for(model)
        return io.NodeOutput(model, canonical(dict(freevideo_revision=config["freevideo_revision"],
            model_revision=config["model_revision"], profiles=list(LABELS), validation="metadata_only_full_SHA_at_execution")))


class MiniMaxH3FreeVideoINT8SamplerEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="FreeVideo INT8 · 四档采样（Light仅LOW8）", category=CATEGORY,
            is_experimental=True, description="Light输出完整LOW8，还需外置放大＋独立HIGH3。其他三档12/16/20单采终态，可直接解码，不接HIGH。",
            inputs=[MODEL.Input("freevideo_model"), io.Conditioning.Input("conditioning"),
                io.Combo.Input("quality", options=list(LABELS), default=next(iter(LABELS))),
                io.Int.Input("width", default=864, min=256, max=4096, step=32),
                io.Int.Input("height", default=480, min=256, max=4096, step=32),
                io.Int.Input("frames", default=124, min=39, max=2000, step=17),
                io.Int.Input("seed", default=171, min=0, max=2**63-1, control_after_generate=True),
                io.Clip.Input("clip_to_offload", optional=True)],
            outputs=[io.Latent.Output("av_latent"), STAGE.Output("completed_stage"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, freevideo_model, conditioning, quality=next(iter(LABELS)), width=864, height=480, frames=124, seed=171, clip_to_offload=None):
        interrupt, progress = callbacks(plan(quality)["nfe"])
        offload_supplied_clip(clip_to_offload)
        stage = fv.sample(freevideo_model, conditioning, width, height, frames, seed,
                          quality=quality, interrupt=interrupt, progress=progress)
        return io.NodeOutput(fv.av_output(stage), stage, stage.receipt_json)


class MiniMaxH3FreeVideoINT8HIGH3EXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="FreeVideo INT8 · Light独立HIGH3", category=CATEGORY,
            is_experimental=True, description="新community3时间表，不是旧尾3步。接新Light LOW8＋外置放大，保留已完成LOW音轨；不能接MID或12/16/20单采。",
            inputs=[MODEL.Input("freevideo_model"), io.Conditioning.Input("conditioning"), STAGE.Input("completed_low"),
                io.Latent.Input("lifted_av_latent"), io.Int.Input("seed", default=172, min=0, max=2**63-1, control_after_generate=True),
                io.Clip.Input("clip_to_offload", optional=True)],
            outputs=[io.Latent.Output("av_latent"), STAGE.Output("completed_stage"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, freevideo_model, conditioning, completed_low, lifted_av_latent, seed=172, clip_to_offload=None):
        from ..core import nested_av_parts
        receipt = fv.validate_stage(completed_low, "LOW")
        video, _ = nested_av_parts(lifted_av_latent)
        interrupt, progress = callbacks(3)
        offload_supplied_clip(clip_to_offload)
        stage = fv.sample(freevideo_model, conditioning, video.shape[-1] * 16, video.shape[-2] * 16,
            receipt["geometry"]["frames"], seed, quality="light", low=completed_low, lifted=lifted_av_latent,
            interrupt=interrupt, progress=progress)
        return io.NodeOutput(fv.av_output(stage), stage, stage.receipt_json)


class MiniMaxH3FreeVideoINT8StageSaveEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="FreeVideo INT8 · 保存阶段", category=CATEGORY,
            is_experimental=True, is_output_node=True, inputs=[STAGE.Input("completed_stage")],
            outputs=[STAGE.Output("completed_stage"), io.String.Output("manifest_path"), io.String.Output("manifest_sha256")])

    @classmethod
    def execute(cls, completed_stage):
        path, sha = fv.save_stage(completed_stage, Path(folder_paths.get_output_directory()) / "T8-FreeVideo/int8-stages")
        return io.NodeOutput(completed_stage, path, sha, ui={"text": [path, sha]})


class MiniMaxH3FreeVideoINT8StageLoadEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="FreeVideo INT8 · 冷加载阶段", category=CATEGORY,
            is_experimental=True, description="填写真实INT8缓存path/SHA。LOW8可接独立HIGH3，单采或HIGH终态直接解码；旧Stage/MID不互换。",
            inputs=[io.String.Input("manifest_path", default=""), io.String.Input("manifest_sha256", default="")],
            outputs=[io.Latent.Output("av_latent"), STAGE.Output("completed_stage"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, manifest_path, manifest_sha256):
        stage = fv.load_stage(manifest_path, manifest_sha256)
        return io.NodeOutput(fv.av_output(stage), stage, stage.receipt_json)


def effect_schema(schema, node_id, display):
    schema.node_id, schema.category, schema.display_name = node_id, CATEGORY, display
    schema.inputs[0] = MODEL.Input("freevideo_model")
    schema.outputs[0] = MODEL.Output("freevideo_model")
    return schema


class MiniMaxH3FreeVideoINT8LoRAEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return effect_schema(MiniMaxH3FreeVideoLoRAEXPT8.define_schema(), cls.__name__, "FreeVideo INT8 · 串联LoRA")

    @classmethod
    def execute(cls, freevideo_model, lora_name, strength=1.0):
        path = lora_name if strength == 0 else folder_paths.get_full_path_or_raise("loras", lora_name)
        result = fv.from_facade(with_lora(fv.facade(freevideo_model), path, strength))
        return io.NodeOutput(result, canonical(dict(slots=len(result.loras), disabled=strength == 0)))


class MiniMaxH3FreeVideoINT8EAVEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return effect_schema(MiniMaxH3FreeVideoEAVEXPT8.define_schema(), cls.__name__, "FreeVideo INT8 · 外置EAV")

    @classmethod
    def execute(cls, freevideo_model, **kwargs):
        result = fv.from_facade(with_eav(fv.facade(freevideo_model), **kwargs))
        return io.NodeOutput(result, result.eav)


class MiniMaxH3FreeVideoINT8PromptRelayEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return effect_schema(MiniMaxH3FreeVideoPromptRelayEXPT8.define_schema(), cls.__name__, "FreeVideo INT8 · 外置Prompt Relay条件")

    @classmethod
    def execute(cls, **kwargs):
        kwargs["freevideo_model"] = fv.facade(kwargs["freevideo_model"])
        model, *outputs = build_relay_conditioning(**kwargs)
        return io.NodeOutput(fv.from_facade(model), *outputs)


NODES = [MiniMaxH3FreeVideoINT8LoaderEXPT8, MiniMaxH3FreeVideoINT8SamplerEXPT8,
         MiniMaxH3FreeVideoINT8HIGH3EXPT8, MiniMaxH3FreeVideoINT8StageSaveEXPT8,
         MiniMaxH3FreeVideoINT8StageLoadEXPT8, MiniMaxH3FreeVideoINT8LoRAEXPT8,
         MiniMaxH3FreeVideoINT8EAVEXPT8, MiniMaxH3FreeVideoINT8PromptRelayEXPT8]
