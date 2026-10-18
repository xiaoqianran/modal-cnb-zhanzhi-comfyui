"""Save the two specifically accepted H13 canvases without sampling or rewiring."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import uuid

from save_h11_reviewed_workflows import PRIVATE, projection, read, set_widget, strings, write_new

REVIEW_ID = "c21678fded3be91ec0e4a2195b29439e8d93f49ef02ced4fa208fa24a02243d2"
CASES = {"AudioFirst": "A1", "Hybrid": "A2"}
MEDIA = {
    "A1": "f03dcf207024b586e42ba01e3ab1e0c8216d39a312878b89441a27f93bf524ec",
    "A2": "18769fcc475e6422162c78fc76e8f38524a9e6d491bda375c892bd7116ff2e7f",
}
GUIDANCE = {
    "AudioFirst": "T2VA同条件Tiny32×32完整8步→Source AV strict regenerate/lock→完整画幅8步。"
                  "Save接实际最终AV的锁音审计；Tiny FLAC仅独立试听，不能替换成片声音。"
                  "使用原完整Wuli8模型，不是另一张图的Hybrid模型。"
                  "单首帧另有真实VAE32编码合同，但本片不授予单首帧完整视频质量资格。",
    "Hybrid": "普通FLbase/RefAdaLN b25–49 Hybrid，原生Ref2VA、simple8/Euler/shift12:3/CFG1。"
              "模型已烘焙FlashGen0.5，不需要再叠同LoRA；不是Realism变体或Wuli4三件套。"
              "LoadImage的H13_reference.png是实际已审来源占位名，请选择自己有权使用的参考图；图片不随仓库分发。",
}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def exact_projection(graph, api):
    """Normalize two known frontend-only controls; compare all execution fields."""
    canonical = copy.deepcopy(graph)
    for node in canonical["nodes"]:
        values = node.get("widgets_values_named", {})
        if (node["type"] == "MiniMaxH3AudioConditioningT8"
                and values.get("task_type") == "Ref2VA — 参考生音视频"):
            if node["widgets_values"] != list(values.values()):
                raise ValueError("Saved positional/named widgets differ")
            node["widgets_values"][list(values).index("task_type")] = "Ref2VA"
            values["task_type"] = "Ref2VA"
        # Core LoadImage declares only image; image_upload creates a UI button.
        if node["type"] == "LoadImage" and values.get("upload") == "image":
            if node["widgets_values"] != list(values.values()):
                raise ValueError("Saved positional/named upload control differs")
            node["widgets_values"].pop(list(values).index("upload"))
            del values["upload"]
    return projection(canonical, api)


def export(evidence_root, feedback_path, destination, evidence):
    feedback = read(feedback_path)
    delivery = read(evidence_root / "human-review-v1/delivery.json")
    seal = read(evidence_root / "gpu-handoff-final-v2.json")
    drafts = read(evidence_root / "saved-UI-drafts-v1.json")
    if (feedback.get("schema") != "t8.v188.human-review.v1"
            or feedback.get("review_id") != REVIEW_ID or delivery["review_id"] != REVIEW_ID
            or feedback.get("revision") != 2 or feedback.get("qa") is not False
            or feedback.get("automatic_accept") is not False or feedback.get("unsaved_case_ids")
            or set(feedback["answers"]) != set(CASES.values())
            or set(feedback["media"]) != set(CASES.values())
            or any(row["status"] != "pass" for row in feedback["answers"].values())):
        raise ValueError("Require this actual complete two-case human feedback")
    groups = {group["id"]: group for group in delivery["groups"]}
    if set(groups) != set(CASES.values()):
        raise ValueError("Unexpected delivery cases")
    for case, group in groups.items():
        clip, = group["clips"]
        if (feedback["media"][case] != [{"label": clip["label"], "sha256": MEDIA[case]}]
                or clip["sha256"] != MEDIA[case]
                or sha(evidence_root / "human-review-v1/public" / clip["url"]) != MEDIA[case]):
            raise ValueError("Accepted media bytes/identity differ")
    if (evidence.exists() or (destination.exists()
            and (not destination.is_dir() or {p.name for p in destination.iterdir()} != {"README.md"}))):
        raise FileExistsError("New destination/evidence only; never overwrite saved originals")
    for name, digest in seal["source_sha256"].items():
        if name not in {"meta.json", "features.json", "docs/H13_AUDIO_FIRST_HYBRID.md"}:
            if sha(evidence_root.parents[2] / name) != digest:
                raise ValueError("Actual GPU-qualified runtime changed: " + name)
    planned = []
    for name, case in CASES.items():
        source = Path(drafts[name]["actual_saved_canvas"])
        history_path = evidence_root / (name.lower() + "-actual-v1/history.json")
        audit = read(evidence_root / (name.lower() + "-actual-v1/audit.json"))
        history = read(history_path)
        if (sha(source) != drafts[name]["saved_sha256"]
                or not history["status"]["completed"] or history["status"]["status_str"] != "success"
                or audit["media"]["sha256"] != MEDIA[case]
                or sha(Path(audit["media"]["path"])) != MEDIA[case]
                or not audit["actual_UI_graph_exact"]):
            raise ValueError("Frozen saved source, history or actual media changed")
        graph = read(source)
        api = exact_projection(graph, history["prompt"][2])
        child = copy.deepcopy(graph)
        note = ("# H13 · 人工审核通过的来源工作流\n\n" + GUIDANCE[name]
                + "\n\n2026-10-15实际人审r2通过，仅本例完整5秒/864×480/120帧/24fps。"
                  "原生124帧明确裁0–5秒；正常对白：你好，今天天气不错。"
                  "原seed、模型、步数、条件、全部接线与裁片参数保持，只有本NOTE和展示来源信息改变，未重新采样。"
                  "不授提速、长窗、多参考或任意外置EAV/Relay组合质量资格；旧工作流不迁移。"
                  "详见本目录README与docs/H13_AUDIO_FIRST_HYBRID.md。"
                  "感谢sepiablue-ai AudioFirst、Wuli-art/sandpies、FlashGen/Kijai及smhfacct。")
        notes = [node for node in child["nodes"] if node["type"] in ("Note", "MarkdownNote")]
        if len(notes) != 1 or set(notes[0].get("widgets_values_named", {})) != {"text"}:
            raise ValueError("Unexpected saved note contract")
        set_widget(notes[0], "text", note)
        child["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "t8:h13:" + name + ":reviewed:r2"))
        child["revision"] = 0
        child.setdefault("extra", {})["workflow_title"] = "H13 " + name + " · reviewed source"
        child["extra"]["h13_reviewed_source"] = {
            "review_id": REVIEW_ID, "revision": 2, "case": case,
            "original_saved_sha256": sha(source), "accepted_media_sha256": [MEDIA[case]],
            "execution_history_sha256": sha(history_path), "resource_adaptations": {},
            "resampled_during_export": False, "automatic_adoption": False,
            "scope": "specific_accepted_media_NOT_all_models_stages_or_hardware",
        }
        if any(PRIVATE.search(value) or value.startswith("\\\\") for value in strings(child)):
            raise ValueError("Undeclared private path; no broad redaction")
        if exact_projection(child, api) != api or child["links"] != graph["links"]:
            raise ValueError("Never change approved execution parameters or edges")
        planned.append((name, case, source, history_path, child, api))
    destination.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True)
    shutil.copy2(feedback_path, evidence / "actual-human-feedback.json")
    records = []
    for name, case, source, history_path, graph, api in planned:
        target = destination / ("H13_" + name + ".json")
        write_new(target, graph)
        shutil.copy2(source, evidence / (name + "_Original.json"))
        write_new(evidence / (name + "_exact-api.json"), api)
        records.append({"relative_path": target.as_posix(), "case": case,
                        "source_sha256": sha(source), "template_sha256": sha(target),
                        "history_sha256": sha(history_path), "accepted_media_sha256": [MEDIA[case]],
                        "links_sha256": hashlib.sha256(json.dumps(graph["links"], sort_keys=True).encode()).hexdigest(),
                        "execution_nodes": len(api), "all_execution_parameters_and_edges_exact": True})
    receipt = {"schema": "t8.h13.reviewed-export.v1", "review_id": REVIEW_ID, "revision": 2,
               "feedback_sha256": sha(feedback_path), "automatic_accept": False,
               "records": records, "saved_templates": 2, "human_passes": 2,
               "new_GPU_runs_during_export": 0, "old_workflow_changes": 0,
               "runtime_source_sha256": {name: sha(evidence_root.parents[2] / name)
                                         for name in seal["source_sha256"]
                                         if name not in {"meta.json", "features.json", "docs/H13_AUDIO_FIRST_HYBRID.md"}},
               "published": False}
    write_new(evidence / "audit.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--feedback", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    receipt = export(args.evidence_root, args.feedback, args.destination, args.evidence)
    print(json.dumps({key: receipt[key] for key in ("human_passes", "saved_templates", "new_GPU_runs_during_export", "published")}))


if __name__ == "__main__":
    main()
