"""Export eight reviewed saved canvases; no registration, model run or Queue.

Only listed machine-local resources and explanatory notes may change. Original
canvases, execution parameters, wiring and human evidence are retained separately.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

REVIEW_ID = "474d1311024ffa56ab50e404af7f7808f14ddc7e8e1d861b5766da35ef8a48eb"
RECIPES = {
    "H11_Spark_Dense": "A1", "H11_Spark_Sparse": "A1",
    "H11_Wuli8": "A2", "H11_Wuli4": "A3", "H11_AudioOnly": "A4",
    "H11_BridgeSidecar": "B1", "H11_PhaseCard": "B2", "H11_SceneTickets": "B3",
}
EDITS = {
    "H11_Spark_Dense": {7: {"runtime_config": ""}, 18: {"runtime_config": ""}},
    "H11_Spark_Sparse": {7: {"runtime_config": ""}, 18: {"runtime_config": ""}},
    "H11_BridgeSidecar": {1: {"sidecar_path": ""}, 2: {"sidecar_path": ""}},
    "H11_PhaseCard": {1: {"manifest_path": "", "manifest_sha256": ""},
                      3: {"manifest_path": "", "manifest_sha256": ""}},
}
GUIDANCE = {
    "H11_Spark_Dense": "Dense对照：两个runtime_config必须填写自己的显式Spark准备清单；空白不是自动安装。与Sparse同seed/模型/轨迹。",
    "H11_Spark_Sparse": "Spark：两个runtime_config必须填写自己的显式Spark准备清单；本例仅Windows CP312/Torch2.10/cu130/SM89官方轮子。未知owner/mask保留委托，实际Sparse调用请看Audit；不授提速百分比。",
    "H11_Wuli8": "选择准确完整Wuli原生8步模型，不是普通8列pruned；原生12/3、simple8/Euler/CFG1。25列shape不等于整模型SHA证明。",
    "H11_Wuli4": "准确full FL2VA底模→trunk→heads_widen→heads_set，三文件顺序与强度1保留；原生6/3、simple4/Euler/CFG1。trunk单独不是完整四步。",
    "H11_AudioOnly": "先把自己的正常5秒视频上传到LoadVideo；示例源文件不分发。A为paired-video、B为standalone声明，本次来自同一声音，不认证双人声纹。Qwen看图，DiT仅audio latent；DRIVE reference_only与FINAL试听分开，成片用生成声音而非FINAL替换。原Ref2VA40步保持。",
    "H11_BridgeSidecar": "先选择自己准确桥权重和对应inference_settings.json。sidecar_path留空只查所选权重同目录。本图并排false/true明确比较，true是该分支显式选择，不是节点默认值；没有Apply或采样。本次开发者Wushu说明fixture只验证传输与采用，不是新训练效果；完整SHA/内嵌契约优先。",
    "H11_PhaseCard": "两StageLoad分别填自己的完整FP8/INT8 Stage manifest与对应完整SHA；文件不分发，不能用MP4代替Stage。本图只读旧已完成回执，不加载DiT/VAE或重新采样。缺phase/compile/VAE/mux显示不可用，不是0；不是本次耗时或速度对比。",
    "H11_SceneTickets": "同一原稿两scene票据展示，不调用provider或采用提案。真正使用Ticket→Rewrite→Adopt，当前Ticket另接Adopt；默认保原稿。新提交改request_id，迟到提案只能归原镜头历史，跨scene/revision/request不得采用。",
}
PRIVATE = re.compile(r"(?:[A-Za-z]:[\\/]|(?:https?://)?(?:127\.0\.0\.1|localhost)(?=[:/]))")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_new(path, value):
    with Path(path).open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def set_widget(node, key, value):
    named = node["widgets_values_named"]
    positional = node["widgets_values"]
    if key not in named or not isinstance(positional, list) or positional != list(named.values()):
        raise ValueError("Actual saved widget contract changed")
    positional[list(named).index(key)] = value
    named[key] = value


def projection(graph, actual_api):
    """Check exact saved execution values against the real frontend export.

    Only Core's specific known UI controls/display serializer and LoadVideo's
    undeclared empty preview are excluded, never arbitrary extra inputs.
    """
    nodes = {str(n["id"]): n for n in graph["nodes"] if n["type"] not in ("Note", "MarkdownNote")}
    if set(nodes) != set(actual_api):
        raise ValueError("Saved/frontend node identities differ")
    edges = {e[0]: e for e in graph["links"]}
    if len(edges) != len(graph["links"]):
        raise ValueError("Duplicate link ID")
    result = {}
    for key, node in nodes.items():
        values = copy.deepcopy(node.get("widgets_values_named", {}))
        positional = node.get("widgets_values")
        if positional is not None and positional != list(values.values()):
            raise ValueError("Saved positional/named values differ")
        if values.get("control_after_generate") == "fixed" and node["type"] == "RandomNoise":
            del values["control_after_generate"]
        if values.get("upload") == "image" and node["type"] == "LoadVideo":
            del values["upload"]
        if node["type"] == "MiniMaxH3AudioOnlyConditioningEXPT8" and values.get("task_type") == "Ref2VA — 参考生音视频":
            values["task_type"] = "Ref2VA"
        for index, entry in enumerate(node.get("inputs", [])):
            if entry.get("link") is None:
                continue
            edge = edges[entry["link"]]
            source = nodes[str(edge[1])]
            output = source["outputs"][edge[2]]
            if (edge[3:5] != [node["id"], index] or edge[0] not in (output.get("links") or [])
                    or edge[5] != entry["type"]
                    or (output["type"] != entry["type"] and entry["type"] != "*")):
                raise ValueError("Actual link topology/type changed")
            values[entry["name"]] = [str(edge[1]), edge[2]]
        actual = actual_api[key]
        actual_values = copy.deepcopy(actual["inputs"])
        if node["type"] == "LoadVideo" and actual_values.get("video-preview") == "":
            del actual_values["video-preview"]
        if actual["class_type"] != node["type"] or actual_values != values or node.get("mode", 0) != 0:
            raise ValueError("Actual frontend execution differs: " + key + " " + repr(values) + " vs " + repr(actual_values))
        result[key] = {"class_type": node["type"], "inputs": values}
    return result


def portable(graph, api, name, feedback, parent_sha):
    if name not in RECIPES or feedback["answers"][RECIPES[name]]["status"] != "pass":
        raise ValueError("No specific human acceptance")
    result, expected = copy.deepcopy(graph), copy.deepcopy(api)
    nodes = {n["id"]: n for n in result["nodes"]}
    for identifier, values in EDITS.get(name, {}).items():
        for key, value in values.items():
            set_widget(nodes[identifier], key, value)
            expected[str(identifier)]["inputs"][key] = value
    note = ("# H11 · 人工审核通过的来源示例\n\n" + GUIDANCE[name]
            + "\n\n2026-10-12实际人审r7通过。仅本例媒体/接口范围，不保证所有模型、双采阶段、长窗或硬件；资源路径适配没有重新采样。"
            "原种子、尺寸、步数、时钟、音轨与全部边保持；旧工作流不迁移。详见本目录README。")
    for node in result["nodes"]:
        if node["type"] in ("Note", "MarkdownNote"):
            if node.get("widgets_values_named") is not None:
                set_widget(node, "text", note)
            else:
                node["widgets_values"] = [note]
    result["id"], result["revision"] = str(uuid.uuid4()), 0
    result.setdefault("extra", {})["workflow_title"] = name + " · reviewed source"
    result["extra"]["h11_reviewed_source"] = {
        "review_id": REVIEW_ID, "revision": feedback["revision"], "case": RECIPES[name],
        "original_saved_sha256": parent_sha,
        "accepted_media_sha256": [v["sha256"] for v in feedback["media"][RECIPES[name]]],
        "resource_adaptations_reexecuted": False, "automatic_adoption": False,
        "scope": "specific_accepted_media_or_interface_NOT_all_models_or_stages",
    }
    if any(PRIVATE.search(value) or value.startswith("\\\\") for value in strings(result)):
        raise ValueError("Undeclared private path; no broad redaction")
    # Cross-check every input and edge after the tiny declared resource edits.
    projection(result, expected)
    if result["links"] != graph["links"]:
        raise ValueError("Never reconnect approved graphs")
    return result, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seal", required=True, type=Path)
    parser.add_argument("--feedback", required=True, type=Path)
    parser.add_argument("--delivery", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    seal, feedback, delivery = read(args.seal), read(args.feedback), read(args.delivery)
    if (feedback["review_id"] != REVIEW_ID or feedback["review_id"] != delivery["review_id"]
            or feedback["qa"] is not False or feedback["automatic_accept"] is not False
            or feedback.get("unsaved_case_ids") or feedback["revision"] != 7
            or set(feedback["answers"]) != set(RECIPES.values())
            or any(row["status"] != "pass" for row in feedback["answers"].values())):
        raise ValueError("Require this exact complete human review, not QA or auto-acceptance")
    for group in delivery["groups"]:
        expected = [{"label": c["label"], "sha256": c["sha256"]} for c in group["clips"]]
        if feedback["media"][group["id"]] != expected:
            raise ValueError("Human review media identity differs")
        for clip in group["clips"]:
            if digest(args.media_root / clip["url"]) != clip["sha256"]:
                raise ValueError("Accepted media bytes changed")
    if args.destination.exists() or args.evidence.exists():
        raise FileExistsError("New templates/evidence only; never overwrite originals")
    planned = []
    for name in RECIPES:
        entry = seal["saved_workflows"][name]
        source, exported = Path(entry["path"]), Path(entry["UI_export"])
        if digest(source) != entry["sha256"] or digest(exported) != entry["UI_export_sha256"]:
            raise ValueError("Frozen saved canvas or actual frontend export changed")
        graph, api = read(source), read(exported)
        projected = projection(graph, api)
        child, expected = portable(graph, projected, name, feedback, entry["sha256"])
        planned.append((name, source, entry, child, expected))
    args.destination.mkdir(parents=True)
    args.evidence.mkdir(parents=True)
    shutil.copy2(args.feedback, args.evidence / "actual-human-feedback.json")
    records = []
    for name, source, entry, child, expected in planned:
        shutil.copy2(source, args.evidence / (name + "_Original.json"))
        target = args.destination / (name + ".json")
        write_new(target, child)
        write_new(args.evidence / (name + "_portable-api.json"), expected)
        if digest(source) != entry["sha256"]:
            raise ValueError("Original changed during export")
        records.append({"name": name, "case": RECIPES[name], "source_sha256": entry["sha256"],
                        "template_sha256": digest(target), "resource_edits": EDITS.get(name, {}),
                        "all_execution_parameters_and_edges_checked": True})
    write_new(args.evidence / "audit.json", {"review_id": REVIEW_ID, "revision": 7,
        "feedback_sha256": digest(args.feedback), "records": records, "new_GPU_runs": 0,
        "human_passes": 7, "saved_templates": 8, "original_canvases_unchanged": True,
        "resource_adaptations_reexecuted": False, "published": False})
    print(json.dumps({"saved_templates": 8, "human_passes": 7, "new_GPU_runs": 0}))


if __name__ == "__main__":
    main()
