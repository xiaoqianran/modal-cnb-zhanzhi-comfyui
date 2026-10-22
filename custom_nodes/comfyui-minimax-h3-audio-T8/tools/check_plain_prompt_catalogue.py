"""Read-only completeness and preserved-source checks for ordinary examples."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

try:
    from .plain_prompt_names import ordinary_target
except ImportError:
    from plain_prompt_names import ordinary_target

ROOT = Path(__file__).resolve().parents[1]
PURE_LEGACY_HELPERS = {"MiniMaxH3MotionRelayLengthEXPT8", "MiniMaxH3FastH3V2AcceptedRelayProjectEXPT8",
                       "MiniMaxH3PromptRelayLongVideoPlanT8Advanced"}


def check(root=ROOT):
    directory = root / "examples/workflows"
    manifest = json.loads((directory / "plain-prompt-index.json").read_text(encoding="utf-8"))
    expected = set()
    for path in directory.rglob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict) or not isinstance(value.get("nodes"), list):
            continue
        if value.get("extra", {}).get("t8_plain_source"):
            continue
        if any("relay" in node.get("type", "").lower() for node in value["nodes"]):
            expected.add(path.relative_to(root).as_posix())
    rows = manifest["rows"]
    assert len(rows) == manifest["source_count"] == len(expected)
    assert {row["source"] for row in rows} == expected, "Missing or extra source coverage"
    assert len({row["ordinary"] for row in rows}) == len(rows), "Duplicate companion target"
    totals = Counter()
    for row in rows:
        assert row["ordinary"] == ordinary_target(row["source"]).as_posix(), "Non-descriptive or misplaced ordinary workflow"
        for name, field in (("source", "source_sha256"), ("ordinary", "ordinary_sha256")):
            path = root / row[name]
            assert path.resolve().is_relative_to(root.resolve()), "Out-of-project path"
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row[field], f"Changed bytes: {row[name]}"
        old = json.loads((root / row["source"]).read_text(encoding="utf-8"))
        new = json.loads((root / row["ordinary"]).read_text(encoding="utf-8"))
        assert new["extra"]["t8_plain_source"] == row["source"]
        nodes = {node["id"]: node for node in new["nodes"]}
        assert len(nodes) == len(new["nodes"]), "Duplicate node ID"
        for node in nodes.values():
            assert "Relay" not in node["type"] or node["type"] in PURE_LEGACY_HELPERS, f"Active Relay node in {row['ordinary']}"
        by_input = {}
        adjacency = {key: set() for key in nodes}
        for edge in new["links"]:
            edge_id, origin, slot, target, pin, kind = edge
            output, input_pin = nodes[origin]["outputs"][slot], nodes[target]["inputs"][pin]
            assert output["type"] == kind
            assert input_pin["link"] == edge_id
            assert edge_id in output["links"]
            assert output["type"] == input_pin["type"] or "*" in (output["type"], input_pin["type"]) or {
                output["type"], input_pin["type"]} <= {"INT", "FLOAT"}
            by_input[target, input_pin["name"]] = (origin, slot)
            adjacency[target].add(origin)
        for node in old["nodes"]:
            kind = node["type"]
            if "Relay" in kind:
                continue
            if any(term in kind for term in ("Sampler", "Sample", "UNETLoader", "LoraLoader", "LoRA", "VAELoader", "LearnedLatent", "GlobalLift")):
                assert node["id"] in nodes and nodes[node["id"]]["type"] == kind, "Sampler/loader/lift removed"
                before, after = node.get("widgets_values"), nodes[node["id"]].get("widgets_values")
                if any(term in kind for term in ("UNETLoader", "LoraLoader", "LoRA", "VAELoader", "CLIPLoader", "LearnedLatent")):
                    assert before == after, "Model/LoRA/upscaler selection changed"
                if isinstance(before, list) and isinstance(after, list):
                    assert len(before) == len(after), "Sampling controls changed shape"
                    for a, b in zip(before, after):
                        if isinstance(a, (int, float, bool)):
                            assert type(a) is type(b) and a == b, "Numerical sampler/LoRA control changed"
                totals["preserved_sampler_loader_nodes"] += 1
        # Every legacy descriptor consumer must descend from an ordinary recipe,
        # never from a segmented Plan hidden elsewhere on the canvas.
        for node in nodes.values():
            if node["type"] == "MiniMaxH3FastH3V2ConditionProvenanceEXPT8":
                start, _ = by_input[node["id"], "prompt_relay_plan"]
                seen, pending = set(), [start]
                while pending:
                    key = pending.pop()
                    if key in seen:
                        continue
                    seen.add(key)
                    pending.extend(adjacency[key])
                assert any(nodes[key]["type"] == "MiniMaxH3PlainPromptRecipeEXPT8" for key in seen)
                assert nodes[start]["type"] in {"MiniMaxH3FastH3V2AcceptedRelayProjectEXPT8", "MiniMaxH3PromptRelayLongVideoPlanT8Advanced"}, "Receipt lost its actual window projection"
            if node["type"] == "MiniMaxH3VisualMarkerConditioningEXPT8":
                recipe_id, _ = by_input[node["id"], "prompt_recipe"]
                prompt_id, prompt_slot = by_input[recipe_id, "base_prompt"]
                assert nodes[prompt_id]["type"] == "MiniMaxH3PlainPromptRecipeEXPT8" and prompt_slot == 1
                totals["editable_marker_prompts"] += 1
        old_edges = {edge[0]: edge for edge in old["links"]}
        for node in old["nodes"]:
            if node["type"] == "MiniMaxH3SPEEDRelayApplyEXPT8":
                pins = {pin["name"]: old_edges[pin["link"]] for pin in node["inputs"] if pin.get("link") in old_edges}
                setup_id, prompt_id = pins["stage_spec"][1], pins["prompt_relay_plan"][1]
                while next(n for n in old["nodes"] if n["id"] == prompt_id)["type"] == "MiniMaxH3PromptRelayQueryRouteT8Advanced":
                    parent = next(n for n in old["nodes"] if n["id"] == prompt_id)
                    pin = next(p for p in parent["inputs"] if p["name"] == "prompt_relay_plan")
                    prompt_id = old_edges[pin["link"]][1]
                source_id, _ = by_input[setup_id, "speed_source"]
                actual_prompt_id, slot = by_input[source_id, "prompt"]
                assert actual_prompt_id == prompt_id and slot == 1, "Stage-specific SPEED text disconnected or shared"
                assert nodes[prompt_id]["type"] == "MiniMaxH3PlainPromptRecipeEXPT8"
                totals["independent_speed_prompts"] += 1
        totals["ordinary_workflows"] += 1
        totals["wire_edges"] += len(new["links"])
    return dict(status="pass", **totals)


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False))
