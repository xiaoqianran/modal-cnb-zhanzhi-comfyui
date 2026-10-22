"""Regression checks for editor-visible text and preservation of real model choices."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest
import h3_audio_t8_pkg

from tools.build_plain_prompt_workflows import companion_targets, transform, validate_graph

ROOT = Path(__file__).resolve().parents[1]


def test_refresh_keeps_old_names_when_a_new_source_sorts_first(tmp_path):
    category = Path("examples/workflows/test")
    original = tmp_path / category / "B.json"
    added = tmp_path / category / "A.json"
    previous = {"rows": [{"source": (category / "B.json").as_posix(),
                          "ordinary": (category / "B_普通提示词.json").as_posix()}]}
    targets = companion_targets(tmp_path, [added, original], previous)
    assert targets[original].name == "B_普通提示词.json"
    assert targets[added].name == "A_普通提示词.json"


def test_legacy_numbered_manifest_requires_explicit_byte_preserving_migration(tmp_path):
    category = Path("examples/workflows/test")
    previous = {"rows": [{"source": (category / "B.json").as_posix(),
                          "ordinary": (category / "Plain_001.json").as_posix()}]}
    with pytest.raises(AssertionError, match="Migrate numbered examples"):
        companion_targets(tmp_path, [tmp_path / category / "B.json"], previous)


def test_descriptive_name_collision_is_not_hidden_with_a_number_or_hash(tmp_path):
    category = tmp_path / "examples/workflows/test"
    with pytest.raises(AssertionError, match="Ambiguous descriptive"):
        companion_targets(tmp_path, [category / "H3_Dual_Relay_EXP.json", category / "Dual_Prompt_Relay_EXP.json"], {"rows": []})


@pytest.fixture(scope="module")
def info():
    classes = asyncio.run(h3_audio_t8_pkg.comfy_entrypoint().get_node_list())
    result = {cls.define_schema().node_id: cls.GET_NODE_INFO_V1() for cls in classes}
    return json.loads(json.dumps(result))


@pytest.fixture
def marker(info):
    path = "examples/workflows/84-visual-marker/VM01_Marked_4plus4.json"
    source = json.loads((ROOT / path).read_text(encoding="utf-8"))
    untouched = deepcopy(source)
    converted = transform(source, info, path)
    assert source == untouched
    return source, converted


def test_marker_each_stage_uses_its_own_editable_full_prompt(marker, info):
    source, result = marker
    validate_graph(source, result, info)
    nodes = {node["id"]: node for node in result["nodes"]}
    edges = {edge[0]: edge for edge in result["links"]}
    providers = []
    for node in nodes.values():
        if node["type"] != "MiniMaxH3VisualMarkerConditioningEXPT8":
            continue
        recipe_pin = next(pin for pin in node["inputs"] if pin["name"] == "prompt_recipe")
        recipe = nodes[edges[recipe_pin["link"]][1]]
        text_pin = next(pin for pin in recipe["inputs"] if pin["name"] == "base_prompt")
        provider = nodes[edges[text_pin["link"]][1]]
        assert provider["type"] == "MiniMaxH3PlainPromptRecipeEXPT8"
        providers.append(provider["id"])
    assert len(providers) == len(set(providers)) == 2


def test_model_selection_corruption_is_detected_without_needing_model_files(marker, info):
    source, result = marker
    loader = next(node for node in result["nodes"] if node["type"] == "UNETLoader")
    loader["widgets_values"][0] = "different-model.safetensors"
    with pytest.raises(AssertionError, match="sampler/loader controls"):
        validate_graph(source, result, info)


def test_ordinary_origin_graph_keeps_real_window_projector_and_no_query_router(info):
    path = "examples/workflows/34-fasth3-v2/FastH3_V2_Split_01_First_LOW_HIGH_Relay_EAV_EXP.json"
    source = json.loads((ROOT / path).read_text(encoding="utf-8"))
    result = transform(source, info, path)
    validate_graph(source, result, info)
    types = {node["type"] for node in result["nodes"]}
    assert "MiniMaxH3PromptRelayLongVideoPlanT8Advanced" in types
    assert "MiniMaxH3PromptRelayQueryRouteT8Advanced" not in types
    assert "MiniMaxH3PlainPromptRecipeEXPT8" in types
