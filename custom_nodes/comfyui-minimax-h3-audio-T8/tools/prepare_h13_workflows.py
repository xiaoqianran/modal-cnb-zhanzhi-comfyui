"""Create two private drafts using actual /object_info, never POST /prompt.

Drafts are not reviewed examples. Import/save/reopen in the real UI before Run.
"""
import argparse
import json
from pathlib import Path
import urllib.request
import uuid

from api_to_frontend_workflow import convert
from frontend_workflow_compat import normalize_native_widget_inputs
from prepare_h11_spark_workflows import graph, node, PROMPT
from prepare_h11_wuli_workflows import canonical_graph
from prepare_h13_wuli_hybrid import FILENAME, SHA


def base(model):
    value = graph("dense_control", "")
    del value["17"], value["18"]
    value["1"]["inputs"]["unet_name"] = model
    value["7"] = node("MiniMaxH3SigmaShift", model=["1", 0], shift_video=12., shift_audio=3.)
    value["6"]["inputs"]["model"] = ["7", 0]
    return value


def audio_first():
    value = base("wuli_h3_turbo_8step_v1_comfyui_int8_convrot.safetensors")
    value["19"] = node("MiniMaxH3AudioFirstProjectionEXPT8", positive=["5", 0], video_latent=["5", 1])
    value["20"] = node("BasicGuider", model=["7", 0], conditioning=["19", 0])
    value["21"] = node("RandomNoise", noise_seed=904513)
    value["22"] = node("SamplerCustomAdvanced", noise=["21", 0], guider=["20", 0], sampler=["10", 0],
                       sigmas=["6", 0], latent_image=["19", 1])
    value["23"] = node("MiniMaxH3SourceAVPrepareT8", video_latent=["5", 1], audio_latent=["22", 1],
        video_mode="regenerate", video_denoise_strength=1., audio_mode="lock", audio_denoise_strength=0.,
        audio_fit_policy="strict", dtype_device_policy="strict")
    value["11"]["inputs"]["latent_image"] = ["23", 0]
    value["24"] = node("MiniMaxH3AudioFirstLockAuditEXPT8", audio_source=["22", 1],
                       locked_input=["23", 0], samples=["11", 1])
    value["12"]["inputs"]["samples"] = ["24", 0]
    value["13"]["inputs"]["samples"] = ["24", 0]
    value["25"] = node("VAEDecodeAudio", samples=["22", 1], vae=["4", 0])
    value["26"] = node("TrimAudioDuration", audio=["25", 0], start_index=0., duration=5.)
    value["27"] = node("PreviewAudio", audio=["26", 0])
    value["16"]["inputs"]["filename_prefix"] = "H13/AudioFirst"
    return canonical_graph(value)


def hybrid(reference):
    value = base(FILENAME)
    value["19"] = node("LoadImage", image=reference)
    value["5"] = node("MiniMaxH3AudioConditioningT8", clip=["2", 0], video_vae=["3", 0], audio_vae=["4", 0],
        prompt="Use <Picture 1> as the same adult woman's appearance reference. " + PROMPT,
        width=864, height=480, length=124, task_type="Ref2VA", audio_mode="native", audio_denoise_strength=1.,
        add_source_as_reference=False, prompt_primary_audio_ordinal=0, strict_prompt_tags=True,
        ref_image_size="match", reference_video_policy="official_2_to_15s", allow_above_reference_area=True,
        **{"ref_images.ref_image_0": ["19", 0]})
    value["16"]["inputs"]["filename_prefix"] = "H13/Hybrid"
    return canonical_graph(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--reference-image", required=True, help="Owned reference filename already in this server's input")
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists():
        raise FileExistsError("Fresh draft directory required")
    with urllib.request.urlopen(args.server.rstrip("/") + "/object_info", timeout=20) as response:
        info = json.loads(response.read())
    drafts = []
    for name, api, note in (
        ("AudioFirst", audio_first(),
         "T2VA同完整场景embedding；Tiny32×32先8步，SourceAV strict regenerate/lock，再完整864×480 8步。"
         "最终Save接实际完整采样后Audit，不是Tiny声音替换；另有Tiny音频试听。"
         "首帧支持在CPU合同覆盖，本图T2VA不调用Tiny VAE。不是第二套音频采样算法。"),
        ("Hybrid", hybrid(args.reference_image),
         "普通FLbase/RefAdaLN b25–49 Hybrid，原生UNETLoader，Ref2VA参考图，不是原Wuli8或三件4。"
         "已烘焙FlashGen0.5，不再叠同权重；完整资源SHA与实际MODEL接线分列。SHA=" + SHA)):
        missing = {n["class_type"] for n in api.values()} - info.keys()
        if missing:
            raise ValueError("Actual backend missing " + repr(missing))
        workflow = convert(api, info, "H13 " + name + " · DRAFT · 5s")
        normalize_native_widget_inputs(workflow)
        workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "t8:h13:" + name + ":v1"))
        last = workflow["last_node_id"] + 1
        workflow["nodes"].append({"id": last, "type": "MarkdownNote", "pos": [0, -370],
            "size": [950, 320], "flags": {}, "order": last, "mode": 0, "inputs": [], "outputs": [],
            "properties": {}, "widgets_values": ["# H13 " + name + " · 草稿/尚待实际Run与人审\n\n" + note +
                "\n864×480≈0.4MP，24fps原生124帧→视频120帧/音频0..5秒，正常对白：你好，今天天气不错。"
                "外置MODEL/条件/SIGMAS/Sampler保持；EAV/Relay各分支显式准备，不继承错误空间receipt。"
                "不覆盖旧工作流，不宣称长窗/提速/通用画质。CPU服务禁止点Run，GPU资源释放后在GPU服务实际验收。"
                "感谢sepiablue-ai AudioFirst、Wuli-art/sandpies、FlashGen/Kijai、smhfacct。"]})
        workflow["last_node_id"] = last
        drafts.append((name, api, workflow))
    args.destination.mkdir(parents=True)
    for name, api, workflow in drafts:
        for suffix, data in (("api", api), ("canvas", workflow)):
            with (args.destination / (name + "_" + suffix + ".json")).open("x", encoding="utf8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        print(json.dumps({"name": name, "nodes": len(api), "draft_id": workflow["id"],
                          "actual_UI_run": False, "human_accepted": False}))


if __name__ == "__main__":
    main()
