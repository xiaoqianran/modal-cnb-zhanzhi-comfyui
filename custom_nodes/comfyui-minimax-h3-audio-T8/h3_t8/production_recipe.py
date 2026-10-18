"""H09 structured continuity ledger -> existing Director Skill/candidate compiler.

User declarations are NOT observed evidence. Never selects LoRAs, edits source
drafts, adopts candidates, downloads assets or changes shared compilation.
"""
from copy import deepcopy
import math
import re

from .director_project import canonical, identity, sha, validate_project, compile_project
from .director_radar import apply_operation, candidate_status

SCHEMA = "t8.h09.production-recipe.v1"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}")


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Production role/prop requires an explicit stable ASCII ID")
    return value


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError("Production declaration must contain 1–4096 characters")
    return value


def validate_packet(project, packet):
    project = validate_project(project)
    if (type(packet) is not dict or set(packet) != {"schema", "project_id", "revision", "roles", "props", "shots"}
            or packet["schema"] != SCHEMA or packet["project_id"] != project["id"]
            or type(packet["revision"]) is not int or packet["revision"] != project["revision"]
            or len(canonical(packet).encode()) > 512*1024):
        raise ValueError("Production recipe must match the actual project/revision and bounded schema")
    assets = {row["id"] for row in project["assets"]}
    roles, props = {}, {}
    for field, target in (("roles", roles), ("props", props)):
        rows = packet[field]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
            raise ValueError("Production recipe needs 1–32 explicit " + field)
        for row in rows:
            key = "role_id" if field == "roles" else "prop_id"
            expected = {key, "description", "asset_ids"} if field == "roles" else {key, "description"}
            if type(row) is not dict or set(row) != expected:
                raise ValueError("Production role/prop fields differ from schema")
            name = _id(row[key])
            if name in target or name in {"scene", "unknown"}:
                raise ValueError("Duplicate/reserved production ID")
            target[name] = _text(row["description"])
            if field == "roles":
                refs = row["asset_ids"]
                if (not isinstance(refs, list) or len(refs) > 15 or len(set(refs)) != len(refs)
                        or any(identity(aid) not in assets for aid in refs)):
                    raise ValueError("Production role references must match actual project assets")
    rows = packet["shots"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise ValueError("Production recipe needs 1–32 ordered shots")
    shot_fields = {"shot_id", "start_state", "end_state", "changes", "dialogue"}
    if any(type(row) is not dict or set(row) != shot_fields for row in rows):
        raise ValueError("Production shot declaration has missing/unknown fields")
    shot_ids = [identity(row["shot_id"]) for row in rows]
    actual = [row["id"] for row in project["doc"]["shots"]]
    if len(set(shot_ids)) != len(shot_ids) or any(sid not in actual for sid in shot_ids):
        raise ValueError("Production shot IDs must be distinct actual shots")
    if [actual.index(sid) for sid in shot_ids] != sorted(actual.index(sid) for sid in shot_ids):
        raise ValueError("Production shots must follow actual project order")
    declared_assets = {aid for role in packet["roles"] for aid in role["asset_ids"]}
    for sid in shot_ids:
        shot = next(item for item in project["doc"]["shots"] if item["id"] == sid)
        bound = set(project["doc"]["sharedRefs"] + shot["refs"] + shot["tray"])
        bound.update(shot[key] for key in ("first", "last", "audio") if shot.get(key))
        if not declared_assets <= bound:
            raise ValueError("Bind declared role assets in the existing Director references/tray before compiling; no implicit rewiring")
    previous = None
    for row in rows:
        for name in ("start_state", "end_state"):
            state = row[name]
            if type(state) is not dict or set(state) != set(props):
                raise ValueError("Declare every prop's state, including explicitly unknown states")
            for value in state.values():
                if (type(value) is not dict or set(value) != {"holder", "state"}
                        or value["holder"] not in set(roles) | {"scene", "unknown"}):
                    raise ValueError("Prop holder must be an explicit role, scene or unknown")
                _text(value["state"])
        changed = row["changes"]
        if (not isinstance(changed, list) or len(set(changed)) != len(changed)
                or any(name not in props for name in changed)):
            raise ValueError("Production changes must name distinct declared props")
        if any(row["start_state"][name] != row["end_state"][name] and name not in changed for name in props):
            raise ValueError("Prop changes require an explicit per-shot change declaration")
        if previous is not None and row["start_state"] != previous:
            raise ValueError("Prop continuity differs across declared shot boundaries")
        previous = row["end_state"]
        dialogue = row["dialogue"]
        if not isinstance(dialogue, list) or len(dialogue) > 32:
            raise ValueError("Production dialogue must be a bounded explicit list")
        for event in dialogue:
            if type(event) is not dict or set(event) != {"role_id", "text"} or event["role_id"] not in roles:
                raise ValueError("Dialogue needs a declared role and literal text")
            _text(event["text"])
    return deepcopy(packet)


def prepare_project(project, packet):
    """Return new pending candidates, never edit/adopt/save the input project."""
    original = validate_project(project)
    packet = validate_packet(original, packet)
    result = deepcopy(original)
    for row in packet["shots"]:
        sid = row["shot_id"]
        shot = next(item for item in result["doc"]["shots"] if item["id"] == sid)
        if shot.get("promptCandidate", {}).get("active"):
            raise ValueError("Preserve/revert an already adopted candidate before importing this recipe")
        declarations = {key: deepcopy(packet[key]) for key in ("roles", "props")}
        declarations.update({key: deepcopy(value) for key, value in row.items() if key != "shot_id"})
        ledger = canonical(declarations)
        if len(ledger) > 4096:
            raise ValueError("One shot's production ledger exceeds the existing Director's 4096-character Skill budget; shorten declarations, not truncate them")
        # Single-pass parameter replacement keeps ${...} in user text literal.
        result = apply_operation(result, sid, "skill_create", dict(
            name="H09 · 稳定角色与道具交接", scope="shot",
            text="[用户制作声明，不是已确认画面事实]\n${ledger}\n保留原稿和字面对白；仅本镜执行允许变化。未观察状态不补造，画面因果与实际持物仍待人审。",
            parameter_schema={"ledger": dict(type="string", max_length=4096)},
            parameters={"ledger": ledger}))
        result = apply_operation(result, sid, "candidate_create", dict(facts=False, intent=True))
    compiled = compile_project(result)
    report = dict(schema="t8.h09.production-import.v1", source_project_sha256=sha(original),
        recipe_sha256=sha(packet), project_sha256=sha(result), shots=[dict(shot_id=row["shot_id"],
            candidate_status=candidate_status(result, next(s for s in result["doc"]["shots"] if s["id"] == row["shot_id"])))
            for row in packet["shots"]], compiled=compiled,
        source_drafts_unchanged=True, evidence_unchanged=True, automatic_accept=False,
        queue_submitted=False, loras_changed=False, claims_are="user_declarations_not_observed_facts")
    return result, report


def selected_lora_card(folder, filename, strength):
    """Read the existing actual installed card; never guess alpha or auto-load."""
    if type(strength) not in (int, float) or not math.isfinite(strength):
        raise ValueError("Select a finite explicit runtime LoRA strength")
    from .model_recipe_cards import inspect_installed_recipe
    card = inspect_installed_recipe(folder, filename)
    return dict(schema="t8.h09.selected-lora-recipe.v1", installed=card,
                selected_runtime_strength=strength, bridge_alpha_selected=False,
                strength_applied=False, model_downloaded=False, quality_accepted=False)
