from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from h3_audio_t8_pkg import production_recipe as r
from h3_audio_t8_pkg.director_project import new_project, compile_project, ProjectStore
from h3_audio_t8_pkg.director_radar import apply_operation, candidate_status


def fixture():
    project = new_project()
    first = project["doc"]["shots"][0]
    first["simplePrompt"] = 'A把白杯放到桌上，原对白：“杯子给你。”'
    for number in (2, 3):
        shot = deepcopy(first)
        shot.update(id=str(uuid.uuid4()), name=f"镜头{number}", simplePrompt='B接杯后点头。对白：“好，谢谢。”')
        project["doc"]["shots"].append(shot)
    def state(holder):
        return {"cup": dict(holder=holder, state="同一个白杯，完整")}
    rows = []
    for shot, start, end in zip(project["doc"]["shots"], ("A", "scene", "B"), ("scene", "B", "B")):
        rows.append(dict(shot_id=shot["id"], start_state=state(start), end_state=state(end),
                         changes=[] if start == end else ["cup"], dialogue=[dict(role_id="A", text="原对白${literal}")]))
    packet = dict(schema=r.SCHEMA, project_id=project["id"], revision=project["revision"],
        roles=[dict(role_id="A", description="A，红衣", asset_ids=[]), dict(role_id="B", description="B，蓝衣", asset_ids=[])],
        props=[dict(prop_id="cup", description="唯一白杯")], shots=rows)
    return project, packet


def test_actual_three_shot_compiler_pending_adoption_reopen_and_source_preserved(tmp_path):
    original, packet = fixture()
    before = deepcopy(original), deepcopy(packet)
    result, report = r.prepare_project(original, packet)
    assert (original, packet) == before
    assert report["automatic_accept"] is False and not report["queue_submitted"]
    assert all(row["candidate_status"] == "pending" for row in report["shots"])
    assert [row["prompt"] for row in compile_project(result)["shots"]] == [row["prompt"] for row in compile_project(original)["shots"]]
    for shot in result["doc"]["shots"]:
        sid = shot["id"]
        assert "${literal}" in shot["promptCandidate"]["text"]
        result = apply_operation(result, sid, "candidate_accept", dict(confirm=True, text_sha256=shot["promptCandidate"]["text_sha256"]))
    prompts = [row["prompt"] for row in compile_project(result)["shots"]]
    assert len(prompts) == 3 and all('"prop_id":"cup"' in text and '"role_id":"A"' in text for text in prompts)
    store = ProjectStore(tmp_path / "user", tmp_path / "input")
    saved = store.save(result, 0)
    reopened = store.load(saved["id"])
    assert [row["prompt"] for row in compile_project(reopened)["shots"]] == prompts
    assert reopened["doc"]["global"] == original["doc"]["global"] and reopened["assets"] == original["assets"]
    assert all("sourceEvidence" not in shot for shot in reopened["doc"]["shots"])


@pytest.mark.parametrize("damage", ["handoff", "undeclared-change", "role", "revision", "order"])
def test_concrete_ledger_errors_reject_without_mutating_project(damage):
    project, packet = fixture()
    before = deepcopy(project)
    if damage == "handoff":
        packet["shots"][1]["start_state"]["cup"]["holder"] = "A"
    elif damage == "undeclared-change":
        packet["shots"][0]["changes"] = []
    elif damage == "role":
        packet["shots"][0]["dialogue"][0]["role_id"] = "unknown-speaker"
    elif damage == "revision":
        packet["revision"] += 1
    else:
        packet["shots"].reverse()
    with pytest.raises(ValueError):
        r.prepare_project(project, packet)
    assert project == before


def test_existing_adoption_is_not_overwritten_and_draft_change_stales_imported_candidate():
    project, packet = fixture()
    result, _ = r.prepare_project(project, packet)
    shot = result["doc"]["shots"][0]
    result = apply_operation(result, shot["id"], "candidate_accept", dict(confirm=True, text_sha256=shot["promptCandidate"]["text_sha256"]))
    with pytest.raises(ValueError, match="already adopted"):
        r.prepare_project(result, packet)
    result["doc"]["shots"][0]["simplePrompt"] += "改了对白"
    assert candidate_status(result, result["doc"]["shots"][0]) == "stale"


def test_actual_bound_asset_content_stales_candidate_and_import_does_not_rewire_refs():
    project, packet = fixture()
    aid = str(uuid.uuid4())
    project["assets"] = [dict(id=aid, kind="image", name="A.png", sha256="a"*64)]
    packet["roles"][0]["asset_ids"] = [aid]
    with pytest.raises(ValueError, match="Bind declared"):
        r.prepare_project(project, packet)
    project["doc"]["sharedRefs"] = [aid]
    result, _ = r.prepare_project(project, packet)
    assert result["doc"]["sharedRefs"] == [aid]
    result["assets"][0]["sha256"] = "b"*64
    assert candidate_status(result, result["doc"]["shots"][0]) == "stale"


def test_malformed_shot_and_existing_skill_budget_fail_clearly():
    project, packet = fixture()
    packet["shots"][0] = None
    with pytest.raises(ValueError, match="shot declaration"):
        r.prepare_project(project, packet)
    project, packet = fixture()
    packet["roles"][0]["description"] = "甲"*4096
    with pytest.raises(ValueError, match="Skill budget"):
        r.prepare_project(project, packet)


def test_actual_cli_create_only_output_and_selected_installed_lora_card(tmp_path):
    project, packet = fixture()
    project_path, recipe_path = tmp_path/"source.json", tmp_path/"recipe.json"
    project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf8")
    recipe_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf8")
    original = project_path.read_bytes(), recipe_path.read_bytes()
    command = [sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve().parents[1]/"tools/import_h09_recipe.py"),
               "--project", str(project_path), "--recipe", str(recipe_path), "--output-dir", str(tmp_path/"new")]
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf8", timeout=60)
    assert process.returncode == 0, process.stderr
    report = json.loads((tmp_path/"new/report.json").read_text(encoding="utf8"))
    assert len(report["shots"]) == 3 and not report["automatic_accept"]
    assert (project_path.read_bytes(), recipe_path.read_bytes()) == original
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf8", timeout=60)
    assert process.returncode != 0 and "never overwritten" in process.stderr
    card = r.selected_lora_card("loras", "H3-Person-Remover-V1.safetensors", 1.)
    assert card["selected_runtime_strength"] == 1 and not card["bridge_alpha_selected"]
    assert not card["strength_applied"] and not card["quality_accepted"]
