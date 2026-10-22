"""Add ordinary-prompt companions to the published Relay example catalogue.

Existing workflows are read-only. The source-to-companion manifest is explicit;
short numbered filenames avoid truncating legacy Windows-hostile names.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import uuid
import re

try:
    from .plain_prompt_names import ORDINARY_SUFFIX, ordinary_target, render_plain_index
    from .check_windows_paths import validate_paths
except ImportError:
    from plain_prompt_names import ORDINARY_SUFFIX, ordinary_target, render_plain_index
    from check_windows_paths import validate_paths

ROOT = Path(__file__).resolve().parents[1]
ABSENT = object()
NOTES = {"Note", "MarkdownNote"}
TRANSPARENT_PLANS = {"MiniMaxH3PromptRelayQueryRouteT8Advanced", "MiniMaxH3PromptRelayPreviewT8Advanced",
    "MiniMaxH3PromptRelayResourceEstimateT8Advanced", "MiniMaxH3ContinuationRelayProjectEXPT8",
    "MiniMaxH3HyperFlowP7RelayProjectEXPT8", "MiniMaxH3ExternalRelayWindowEXPT8"}


@dataclass(frozen=True)
class Ref:
    node: int
    slot: int
    final: bool = False


def widget_specs(info):
    result = []
    for section in ("required", "optional"):
        for name, spec in info.get("input", {}).get(section, {}).items():
            options = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if not options.get("forceInput") and (isinstance(spec[0], list)
                    or spec[0] in {"INT", "FLOAT", "BOOLEAN", "STRING", "COMBO"}):
                result.append((name, spec, options))
    return result


def ordinary_text(global_prompt, local_prompts):
    """Keep all original words as ordinary prose, without a Relay scheduler."""
    values = [str(value).strip() for value in (global_prompt, local_prompts)
              if value is not None and str(value).strip()]
    return "\n\n".join(values)


class Graph:
    def __init__(self, source, info):
        self.source = deepcopy(source)
        self.nodes = {n["id"]: deepcopy(n) for n in source["nodes"]}
        self.original = deepcopy(self.nodes)
        self.info = info
        self.edges = {}
        for edge in source.get("links", []):
            target = self.nodes[edge[3]]
            self.edges[edge[3], target["inputs"][edge[4]]["name"]] = Ref(edge[1], edge[2])
        self.aliases = {}
        self.deleted = set()
        self.rebuilt = {}
        self.edited_widgets = set()
        self.plans = {}

    def params(self, node_id):
        if node_id in self.rebuilt:
            return dict(self.rebuilt[node_id])
        node = self.nodes[node_id]
        values = node.get("widgets_values") or []
        if isinstance(values, dict):
            result = dict(values)
        else:
            specs = widget_specs(self.info.get(node["type"], {}))
            def slots(items):
                return sum(1 + bool(opts.get("control_after_generate", name in {"seed", "noise_seed"}))
                           for name, _spec, opts in items)
            if slots(specs) != len(values):
                unlinked = [item for item in specs if (node_id, item[0]) not in self.edges]
                if slots(unlinked) == len(values):
                    specs = unlinked
            result, pos = {}, 0
            for name, _spec, opts in specs:
                if pos >= len(values):
                    break
                result[name] = values[pos]
                pos += 1 + bool(opts.get("control_after_generate", name in {"seed", "noise_seed"}))
        result.update({name: ref for (target, name), ref in self.edges.items() if target == node_id})
        return result

    def get(self, node_id, name, default=ABSENT):
        value = self.params(node_id).get(name, default)
        if value is ABSENT:
            raise ValueError(f"Missing input {node_id}:{self.nodes[node_id]['type']}.{name}")
        return value

    def output(self, node_id, name):
        for slot, output in enumerate(self.nodes[node_id].get("outputs", [])):
            if output["name"] == name:
                return Ref(node_id, slot, node_id in self.rebuilt)
        raise ValueError(f"Missing output {node_id}:{self.nodes[node_id]['type']}.{name}")

    def alias(self, node_id, outputs):
        for slot, output in enumerate(self.original[node_id].get("outputs", [])):
            self.aliases[Ref(node_id, slot)] = outputs.get(output["name"], ABSENT)
        self.deleted.add(node_id)

    def resolve(self, value, seen=None):
        if not isinstance(value, Ref):
            return value
        if value.final:
            return value
        seen = set() if seen is None else set(seen)
        if value in seen:
            raise ValueError(f"Alias cycle {value}")
        target = self.aliases.get(value, value)
        if target == value:
            return value
        seen.add(value)
        return self.resolve(target, seen)

    def change(self, node_id, kind, params, passthrough=None, rename=None):
        old = self.original[node_id]
        info = self.info[kind]
        names = info.get("output_name", info["output"])
        outputs = [{"name": name, "type": value, "links": None}
                   for name, value in zip(names, info["output"])]
        self.nodes[node_id].update(type=kind, title=info.get("display_name", kind),
            outputs=outputs, properties={"Node name for S&R": kind})
        self.rebuilt[node_id] = dict(params)
        passthrough, rename = passthrough or {}, rename or {}
        for slot, output in enumerate(old.get("outputs", [])):
            name = output["name"]
            new_name = rename.get(name, name)
            if name in passthrough:
                self.aliases[Ref(node_id, slot)] = passthrough[name]
            elif new_name in names:
                target = Ref(node_id, names.index(new_name), True)
                self.aliases[Ref(node_id, slot)] = target
            else:
                self.aliases[Ref(node_id, slot)] = ABSENT

    def set(self, node_id, name, value):
        if node_id in self.rebuilt:
            self.rebuilt[node_id][name] = value
            return
        if isinstance(value, Ref):
            self.edges[node_id, name] = value
            node = self.nodes[node_id]
            if not any(pin["name"] == name for pin in node.get("inputs", [])):
                spec = next((fields[name] for fields in self.info.get(node["type"], {}).get("input", {}).values()
                             if isinstance(fields, dict) and name in fields), None)
                if spec is None:
                    raise ValueError(f"Missing linked widget schema {node_id}.{name}")
                kind = "COMBO" if isinstance(spec[0], list) else spec[0]
                pin = {"name": name, "type": kind, "link": None}
                if kind in {"STRING", "INT", "FLOAT", "BOOLEAN", "COMBO"}:
                    pin["widget"] = {"name": name}
                node.setdefault("inputs", []).append(pin)
            return
        self.edges.pop((node_id, name), None)
        node = self.nodes[node_id]
        values = node.get("widgets_values", [])
        if isinstance(values, dict) and name in values:
            values[name] = value
            self.edited_widgets.add((node_id, name))
            return
        specs = widget_specs(self.info.get(node["type"], {}))
        pos = 0
        for field, _spec, opts in specs:
            if field == name:
                if isinstance(values, dict):
                    values[field] = value
                elif pos < len(values):
                    values[pos] = value
                else:
                    raise ValueError(f"Cannot set saved widget {node_id}.{name}")
                self.edited_widgets.add((node_id, name))
                return
            pos += 1 + bool(opts.get("control_after_generate", field in {"seed", "noise_seed"}))
        raise ValueError(f"Cannot locate widget {node_id}:{node['type']}.{name}")

    def drop(self, node_id, name):
        if node_id in self.rebuilt:
            self.rebuilt[node_id].pop(name, None)
        self.edges.pop((node_id, name), None)

    def clone(self, node_id):
        key = max(self.nodes) + 1
        self.nodes[key] = deepcopy(self.nodes[node_id])
        self.nodes[key]["id"] = key
        self.original[key] = deepcopy(self.nodes[key])
        self.nodes[key]["pos"] = [self.nodes[key].get("pos", [0, 0])[0],
                                   self.nodes[key].get("pos", [0, 0])[1] + 450]
        for (target, name), value in list(self.edges.items()):
            if target == node_id:
                self.edges[key, name] = value
        return key

    def text(self, value):
        if not isinstance(value, Ref):
            return str(value or "")
        node = self.original[value.node]
        kind = node["type"]
        if "Relay" in kind and kind != "MiniMaxH3MotionRelayLengthEXPT8":
            return self.plan(value)["prompt"]
        values = self.params(value.node)
        for name in ("text", "value", "prompt", "global_prompt", "base_prompt"):
            if name in values and not isinstance(values[name], Ref):
                return str(values[name])
        widgets = node.get("widgets_values", [])
        if isinstance(widgets, list):
            return "\n".join(str(v) for v in widgets if isinstance(v, str) and v.strip())
        raise ValueError(f"Cannot resolve prompt text from {kind}")

    def plan(self, value):
        if not isinstance(value, Ref):
            raise ValueError("Plan needs an upstream node")
        key = value.node
        if key in self.plans:
            return self.plans[key]
        kind, params = self.original[key]["type"], self.params(key)
        if kind in {"MiniMaxH3PromptRelayPlanT8Advanced", "MiniMaxH3LTXPromptRelayPlanEXPT8"}:
            local = self.text(params.get("local_prompts", ""))
            if isinstance(params.get("prompt_relay_events"), Ref):
                local = self.events(params["prompt_relay_events"])
            result = {"prompt": ordinary_text(self.text(params.get("global_prompt", "")), local),
                      "length": params.get("length", params.get("frame_count", 124))}
        elif kind == "MiniMaxH3PromptPacketRelayPlanT8Advanced":
            packet = self.text(params["prompt_packet"])
            events = params.get("events_json", params.get("local_events_json", ""))
            if isinstance(events, str):
                try:
                    events = "\n".join(row["prompt"] for row in json.loads(events))
                except (ValueError, TypeError, KeyError):
                    pass
            result = {"prompt": ordinary_text(packet, events), "length": params.get("length", 124)}
        else:
            upstream = next((params[name] for name in ("prompt_relay_plan", "global_plan", "projected_relay")
                             if isinstance(params.get(name), Ref)), None)
            if upstream is None:
                raise ValueError(f"Unmapped plan producer {kind}")
            result = dict(self.plan(upstream))
            if "length" in params:
                result["length"] = params["length"]
        self.plans[key] = result
        return result

    def prompt_source(self, value):
        while self.original[value.node]["type"] in TRANSPARENT_PLANS:
            params = self.params(value.node)
            value = next(params[name] for name in ("prompt_relay_plan", "global_plan")
                         if isinstance(params.get(name), Ref))
        return value

    def events(self, value):
        params = self.params(value.node)
        previous = self.events(params["previous_events"]) if isinstance(params.get("previous_events"), Ref) else ""
        current = self.text(params.get("prompt", params.get("local_prompt", ""))) if params.get("enabled", True) else ""
        return ordinary_text(previous, current)

    def build_node(self, node_id):
        node = self.nodes[node_id]
        params = self.rebuilt[node_id]
        info = self.info[node["type"]]
        specs = {name: spec for section in ("required", "optional")
                 for name, spec in info.get("input", {}).get(section, {}).items()}
        inputs, values = [], []
        for name, spec in specs.items():
            value = self.resolve(params.get(name, ABSENT))
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            is_widget = not opts.get("forceInput") and (isinstance(spec[0], list)
                or spec[0] in {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"})
            if isinstance(value, Ref):
                pin = {"name": name, "type": "COMBO" if isinstance(spec[0], list) else spec[0], "link": None}
                if is_widget:
                    pin["widget"] = {"name": name}
                inputs.append(pin)
                if is_widget:
                    values.append(opts.get("default", spec[0][0] if isinstance(spec[0], list) and spec[0] else
                        {"STRING": "", "BOOLEAN": False, "INT": 0, "FLOAT": 0., "COMBO": ""}.get(spec[0], "")))
                continue
            if is_widget:
                default = opts.get("default", spec[0][0] if isinstance(spec[0], list) and spec[0] else
                                   {"STRING": "", "BOOLEAN": False, "INT": 0, "FLOAT": 0.}.get(spec[0], ""))
                values.append(default if value is ABSENT else value)
                if opts.get("control_after_generate", name in {"seed", "noise_seed"}):
                    values.append("fixed")
            elif value is not ABSENT:
                inputs.append({"name": name, "type": spec[0], "link": None})
        # Autogrow names are concrete sockets, not ordinary literal widgets.
        for name, value in params.items():
            if name not in specs and isinstance(self.resolve(value), Ref):
                old = next((pin for pin in self.original[node_id].get("inputs", []) if pin["name"] == name), None)
                if old is None:
                    raise ValueError(f"Unknown dynamic input {node_id}.{name}")
                inputs.append({**old, "link": None})
        node["inputs"], node["widgets_values"] = inputs, values
        size = node.get("size", [400, 300])
        node["size"] = [max(size[0], 480), max(size[1], 400)] if isinstance(size, list) else [480, 400]

    def finish(self, source_name):
        for node_id in self.rebuilt:
            if node_id not in self.deleted:
                self.build_node(node_id)
        nodes = {key: node for key, node in self.nodes.items() if key not in self.deleted}
        # Debug-only consumers of removed Relay audit reports are no longer
        # executable; keep the sampling/delivery graph, not empty preview boxes.
        for key, node in list(nodes.items()):
            if node["type"] in {"PreviewAny", "ShowText|pysssss"}:
                incoming = [value for (target, _), value in self.edges.items() if target == key]
                if incoming and all(self.resolve(value) is ABSENT for value in incoming):
                    nodes.pop(key)
        for node in nodes.values():
            for pin in node.get("inputs", []):
                pin["link"] = None
            for output in node.get("outputs", []):
                output["links"] = None
        edges = []
        for node_id, node in nodes.items():
            for slot, pin in enumerate(node.get("inputs", [])):
                value = (self.rebuilt[node_id].get(pin["name"], ABSENT) if node_id in self.rebuilt
                         else self.edges.get((node_id, pin["name"]), ABSENT))
                value = self.resolve(value)
                if not isinstance(value, Ref):
                    continue
                if value.node not in nodes:
                    raise ValueError(f"Dangling output {value} to {node_id}.{pin['name']}")
                outputs = nodes[value.node].get("outputs", [])
                if value.slot >= len(outputs):
                    raise ValueError(f"Invalid slot {value}")
                edge_id = len(edges) + 1
                edges.append([edge_id, value.node, value.slot, node_id, slot, outputs[value.slot]["type"]])
                pin["link"] = edge_id
                outputs[value.slot]["links"] = (outputs[value.slot].get("links") or []) + [edge_id]
        result = deepcopy(self.source)
        result["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "t8/plain/" + source_name))
        result["nodes"], result["links"] = list(nodes.values()), edges
        result["last_link_id"] = len(edges)
        result["last_node_id"] = max(nodes)
        result["extra"] = {**result.get("extra", {}), "t8_plain_source": source_name}
        # Recompute execution order; keep every original sampler, loader and value.
        visited, active = set(), set()
        def visit(key):
            if key in active:
                raise ValueError(f"Workflow cycle at {key}")
            if key in visited:
                return
            active.add(key)
            for edge in edges:
                if edge[3] == key:
                    visit(edge[1])
            active.remove(key)
            nodes[key]["order"] = len(visited)
            visited.add(key)
        for key in nodes:
            visit(key)
        guide_id = max(nodes) + 1
        top = min((node.get("pos", [0, 0])[1] for node in nodes.values()), default=0)
        result["nodes"].append({"id": guide_id, "type": "MarkdownNote", "title": "普通提示词 · 从这里开始",
            "pos": [-900, top - 500], "size": [800, 400], "flags": {}, "order": len(nodes), "mode": 0,
            "inputs": [], "outputs": [], "properties": {}, "widgets_values": [
                "普通提示词副本\n\n来源：" + source_name + "\n\n"
                "在“完整提示词”框一次填写整段画面、动作与对白。两采／各阶段的文字框可分别编辑；"
                "原图的全局与局部文字已合并，不再按事件时间段路由。\n"
                "原采样次数、LoRA、底模、放大、音频和阶段接线保留。\n"
                "恢复版请先使用对应普通版 Full 保存新缓存，再填入新的文件路径和 SHA。"
                "Prepared LTX 的普通文字仍由准备包的 prompt／文本缓存提供。\n"
                "旧 NOTE 中的 Relay 操作属于原版；本副本按上述普通入口编辑。"]})
        result["last_node_id"] = guide_id
        return result


def transform(source, info, source_name):
    graph = Graph(source, info)
    original = list(graph.original.items())
    plan_types = {"MiniMaxH3PromptRelayPlanT8Advanced", "MiniMaxH3PromptRelayLongVideoPlanT8Advanced",
        "MiniMaxH3PromptRelayQueryRouteT8Advanced", "MiniMaxH3PromptRelayPreviewT8Advanced",
        "MiniMaxH3PromptRelayResourceEstimateT8Advanced", "MiniMaxH3PromptPacketRelayPlanT8Advanced",
        "MiniMaxH3ContinuationRelayProjectEXPT8", "MiniMaxH3HyperFlowP7RelayProjectEXPT8",
        "MiniMaxH3FastH3V2AcceptedRelayProjectEXPT8", "MiniMaxH3ExternalRelayWindowEXPT8"}
    # Resolve plans before their widgets and outputs are replaced.
    retained_projection_types = {"MiniMaxH3FastH3V2AcceptedRelayProjectEXPT8", "MiniMaxH3PromptRelayLongVideoPlanT8Advanced"}
    for node_id, node in original:
        if node["type"] in plan_types:
            graph.plan(Ref(node_id, 0))
    for node_id, node in original:
        kind = node["type"]
        p = graph.params(node_id)
        if kind in plan_types:
            plan = graph.plans[node_id]
            if kind in retained_projection_types:
                graph.nodes[node_id]["title"] = "普通提示词 · 本段帧数对齐"
                continue
            if kind in TRANSPARENT_PLANS:
                parent = graph.prompt_source(Ref(node_id, 0))
                graph.alias(node_id, {"prompt_relay_plan": parent,
                    "projected_relay": parent, "compiled_prompt": Ref(parent.node, 1, True),
                    "report_json": Ref(parent.node, 4, True) if graph.original[parent.node]["type"] not in retained_projection_types else ABSENT})
                continue
            graph.change(node_id, "MiniMaxH3PlainPromptRecipeEXPT8", {"prompt": plan["prompt"], "length": plan["length"]},
                         rename={"prompt_relay_plan": "prompt_recipe", "projected_relay": "prompt_recipe"})
            graph.nodes[node_id]["title"] = "完整提示词 · 普通文本"
        elif kind == "MiniMaxH3PromptRelayEventT8Advanced":
            graph.alias(node_id, {})
        elif kind in {"MiniMaxH3PromptRelayConditioningT8Advanced", "MiniMaxH3FreeVideoPromptRelayEXPT8",
                "MiniMaxH3FreeVideoQualityPromptRelayEXPT8", "MiniMaxH3FreeVideoINT8PromptRelayEXPT8",
                "MiniMaxH3ReferenceRelayConditioningEXPT8", "MiniMaxH3PromptRelayLongVideoConditioningT8Advanced",
                "MiniMaxH3ExternalRelayConditioningEXPT8", "MiniMaxH3VisualMarkerRelayConditioningEXPT8"}:
            plan = graph.plan(p.get("prompt_relay_plan", p.get("projected_relay")))
            target = {"MiniMaxH3ReferenceRelayConditioningEXPT8": "MiniMaxH3ReferenceConditioningEXPT8",
                "MiniMaxH3PromptRelayLongVideoConditioningT8Advanced": "MiniMaxH3LongVideoConditioningT8",
                "MiniMaxH3ExternalRelayConditioningEXPT8": "MiniMaxH3ExternalContinuationConditioningEXPT8",
                "MiniMaxH3VisualMarkerRelayConditioningEXPT8": "MiniMaxH3VisualMarkerConditioningEXPT8"}.get(kind, "MiniMaxH3AudioConditioningT8")
            selected = {name for section in ("required", "optional") for name in info[target]["input"].get(section, {})}
            options = {name: value for name, value in p.items() if name in selected or "." in name}
            plan_ref = graph.prompt_source(p.get("prompt_relay_plan", p.get("projected_relay")))
            frame_source = plan["length"]
            if (graph.original[plan_ref.node]["type"] not in retained_projection_types
                    and graph.plan(plan_ref)["length"] == plan["length"]):
                frame_source = Ref(plan_ref.node, 2, True)
            options.update(prompt=Ref(plan_ref.node, 1, True),
                           length=p.get("length", frame_source))
            if kind == "MiniMaxH3VisualMarkerRelayConditioningEXPT8":
                options.pop("prompt", None)
                options["length"] = p.get("length", frame_source)
                recipe = graph.clone(p["prompt_recipe"].node)
                graph.set(recipe, "base_prompt", Ref(plan_ref.node, 1, True))
                options["prompt_recipe"] = Ref(recipe, p["prompt_recipe"].slot)
            passthrough = {"model": p.get("model", ABSENT), "freevideo_model": p.get("freevideo_model", ABSENT)}
            if "model" in info[target]["input"].get("required", {}):
                passthrough.pop("model", None)
            graph.change(node_id, target, options, passthrough=passthrough)
        elif kind == "MiniMaxH3ProgressiveRelayStageApplyEXPT8":
            graph.alias(node_id, {name: p[name] for name in ("model", "positive", "negative")})
        elif kind in {"MiniMaxH3ContinuationRelayApplyEXPT8", "MiniMaxH3HyperFlowP7RelayApplyEXPT8"}:
            phase = p["prepared_phase"].node
            graph.alias(node_id, {"model": p["model"], "positive": graph.output(phase, "positive"),
                                  "negative": graph.output(phase, "negative")})
        elif kind in {"MiniMaxH3ChunkedV1RelayProjectEXPT8", "MiniMaxH3ChunkedV5RelayProjectEXPT8",
                      "MiniMaxH3H16RelayProjectEXPT8", "MiniMaxH3ChunkedPass2RelayBindEXPT8"}:
            graph.alias(node_id, {"model": p.get("raw_high_model", p.get("raw_model", p["relay_model"])),
                                  "positive": p["relay_positive"]})
        elif kind in {"MiniMaxH3FaceRelayBindEXPT8", "MiniMaxH3FaceLocalRelayBindEXPT8", "MiniMaxH3MotionRelayBindEXPT8"}:
            graph.alias(node_id, {"model": p["model"], "positive": p["relay_positive"]})
        elif kind in {"MiniMaxH3VDNRelayApplyEXPT8", "MiniMaxH3LTXPromptRelayApplyEXPT8"}:
            graph.alias(node_id, {"model": p["model"], "positive": p.get("positive", ABSENT)})
        elif kind in {"MiniMaxH3VDNRelayAuditEXPT8", "MiniMaxH3LTXPromptRelayAuditEXPT8"}:
            name = "av_latent" if "av_latent" in p else "candidate_latent"
            graph.alias(node_id, {name: p[name]})
        elif kind in {"MiniMaxH3ChunkedV1RelayAuditEXPT8", "MiniMaxH3ChunkedV5RelayAuditEXPT8",
                      "MiniMaxH3H16RelayAuditEXPT8", "MiniMaxH3ChunkedPass2RelayAuditEXPT8"}:
            origin = p.get("segment_result", p.get("window_result")).node
            graph.alias(node_id, {"cumulative_av_latent": graph.output(origin, "cumulative_av_latent")})
        elif kind == "MiniMaxH3EnhanceAVideoPromptRelayComposerT8Advanced":
            graph.change(node_id, "MiniMaxH3EnhanceAVideoT8Advanced", p)
        elif kind == "MiniMaxH3MotionRelayLengthEXPT8":
            graph.nodes[node_id]["title"] = "整段帧数 · 读取动作计划"
        elif kind == "MiniMaxH3SPEEDRelayApplyEXPT8":
            spec = p["stage_spec"].node
            source_id = graph.clone(p["speed_source"].node)
            plan = graph.plan(p["prompt_relay_plan"])
            graph.set(source_id, "prompt", Ref(graph.prompt_source(p["prompt_relay_plan"]).node, 1, True))
            graph.set(spec, "speed_source", Ref(source_id, 0))
            graph.set(spec, "reuse_t2va_text", False)
            graph.alias(node_id, {"model": p["model"], **{name: graph.output(spec, name) for name in
                ("positive", "av_latent", "mux_audio", "conditioned_prompt", "media_map_json", "report_json")}})
        elif kind == "MiniMaxH3LTXPromptRelayPlanEXPT8":
            plan = graph.plan(Ref(node_id, 0))
            graph.change(node_id, "PrimitiveStringMultiline", {"value": plan["prompt"]},
                         rename={"compiled_prompt": "STRING"})
        elif kind == "MiniMaxH3LTXPromptRelayEncodeEXPT8":
            plan_ref = p["ltx_relay_plan"]
            graph.change(node_id, "CLIPTextEncode", {"clip": p["clip"], "text": Ref(plan_ref.node, 0, True)},
                         rename={"positive": "CONDITIONING"})
        elif kind in {"MiniMaxH3PreparedLTXRelayPlanEXPT8", "MiniMaxH3PreparedLTXRelayEncodeEXPT8",
                      "MiniMaxH3TemporalRelayConfigEXPT8"}:
            graph.alias(node_id, {})
        elif kind == "MiniMaxH3TemporalV5RelayApplyEXPT8":
            graph.change(node_id, "MiniMaxH3TemporalWindowConditioningEXPT8", {
                "bank": p["bank"], "source_av_latent": p["partial4_denoised_output"],
                "plan": p["plan"], "window_index": p["window_index"]}, passthrough={"model": p["model"]})
        elif kind == "MiniMaxH3TemporalV5RelayAuditEXPT8":
            graph.alias(node_id, {"cumulative_av_latent": graph.output(p["scoped_window_result"].node, "cumulative_av_latent")})
    # Ordinary internal loop prompts; disconnect the plan and select disabled mode.
    for node_id, node in original:
        if node_id in graph.deleted:
            continue
        p = graph.params(node_id)
        if ("prompt_relay_plan" in p and "Relay" not in node["type"]
                and node["type"] != "MiniMaxH3FastH3V2ConditionProvenanceEXPT8"):
            plan = graph.plan(p["prompt_relay_plan"])
            graph.drop(node_id, "prompt_relay_plan")
            if "global_prompt" in p:
                graph.set(node_id, "global_prompt", plan["prompt"])
                if "local_prompts" in p:
                    graph.set(node_id, "local_prompts", "")
                if "segment_prompts_json" in p:
                    graph.set(node_id, "segment_prompts_json", "[]")
            elif "prompt" in p:
                graph.set(node_id, "prompt", plan["prompt"])
            for name in ("prompt_relay_mode", "relay_mode"):
                if name in p:
                    graph.set(node_id, name, "disabled")
        if node["type"] in {"MiniMaxH3ChunkedV5EAVApplyEXPT8", "MiniMaxH3H16EAVApplyEXPT8"}:
            graph.drop(node_id, "relay_positive")
        if node["type"] == "MiniMaxH3FastH3V2ConditionProvenanceEXPT8":
            # apply_exp with zero events installs only the native long-video
            # payload owner. report_only would skip that required motion patch.
            graph.set(node_id, "execution_mode", "apply_exp")
            graph.nodes[node_id]["title"] = "普通长视频条件 · 来源校验（零分段）"
        if node["type"] == "MiniMaxH3TemporalH16EffectsApplyEXPT8":
            graph.drop(node_id, "relay_config")
        if node["type"] == "MiniMaxH3PreparedLTXEffectsBindEXPT8":
            graph.drop(node_id, "ltx_relay_plan")
            graph.set(node_id, "relay_cache_manifest_path", "")
            graph.set(node_id, "relay_mode", "disabled")
        # New examples own new task/output names, so editing ordinary prose
        # does not accidentally resume or overwrite the original Relay task.
        for name in ("chain_id", "cache_id", "filename_prefix", "prefix"):
            value = graph.params(node_id).get(name)
            if isinstance(value, str) and value and not value.endswith("_plain"):
                graph.set(node_id, name, value + "_plain")
    return graph.finish(source_name)


def relay_graph(graph):
    return any("relay" in node.get("type", "").lower() for node in graph.get("nodes", []))


def validate_graph(source, result, info):
    """Independent wiring checks plus unchanged sampling/loader controls."""
    nodes = {node["id"]: node for node in result["nodes"]}
    original = {node["id"]: node for node in source["nodes"]}
    incoming = {}
    for edge in result["links"]:
        _edge_id, origin, slot, target, pin, kind = edge
        assert origin in nodes and target in nodes, "Dangling node"
        output, input_pin = nodes[origin]["outputs"][slot], nodes[target]["inputs"][pin]
        assert output["type"] == kind, "Wrong output type"
        expected = input_pin["type"]
        assert (kind == expected or "*" in (kind, expected)
                or {kind, expected} <= {"INT", "FLOAT"}), f"Type mismatch: {origin}:{kind} -> {target}.{input_pin['name']}:{expected}"
        assert input_pin["link"] == _edge_id, "Broken input ownership"
        assert _edge_id in output["links"], "Broken output ownership"
        incoming[target, input_pin["name"]] = (origin, slot)
    decoded = Graph(result, info)
    for node_id, node in nodes.items():
        if node["type"] not in info:
            continue
        values = decoded.params(node_id)
        for name, spec in info[node["type"]].get("input", {}).get("required", {}).items():
            if spec[0] == "COMFY_AUTOGROW_V3":
                continue
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            primitive = not opts.get("forceInput") and (isinstance(spec[0], list)
                or spec[0] in {"STRING", "INT", "FLOAT", "BOOLEAN", "COMBO"})
            if (node_id, name) in incoming or (primitive and name in values):
                continue
            # Only pre-existing untouched dormant nodes may retain an old gap.
            old = original.get(node_id)
            if old and old["type"] == node["type"]:
                old_values = Graph(source, info).params(node_id)
                if name not in old_values:
                    continue
            raise ValueError(f"Missing required input {node_id}:{node['type']}.{name}")
    critical = re.compile(r"Sampler|Sample|StageSetup|Schedule|Sigmas|Learned|GlobalLift|Upscale|Pass2|SourceSegment|Restart|UNETLoader|LoRA|Lora|VAELoader|CLIPLoader|Noise|CFG|Window|DualModel")
    checked = 0
    for node_id, old in original.items():
        kind = old["type"]
        if "Relay" in kind or not critical.search(kind):
            continue
        assert node_id in nodes, f"Removed sampler/loader: {node_id}:{kind}"
        new = nodes[node_id]
        assert new["type"] == kind, f"Changed sampler/loader: {node_id}:{kind}"
        if old.get("widgets_values") != new.get("widgets_values"):
            assert kind in info, f"Changed unknown sampler/loader controls: {node_id}:{kind}"
            old_g, new_g = Graph(source, info), Graph(result, info)
            before, after = old_g.params(node_id), new_g.params(node_id)
            mutable = {"prompt", "global_prompt", "local_prompts", "relay_mode", "prompt_relay_mode", "reuse_t2va_text",
                       "chain_id", "cache_id", "filename_prefix", "prefix", "segment_prompts_json"}
            for field in set(before) | set(after):
                if field in mutable or isinstance(before.get(field), Ref) or isinstance(after.get(field), Ref):
                    continue
                assert before.get(field) == after.get(field), f"Changed sampling control {node_id}.{field}"
        checked += 1
    return {"critical_nodes_preserved": checked, "nodes": len(nodes), "links": len(result["links"])}


def scan(root):
    for path in sorted((root / "examples/workflows").rglob("*.json")):
        graph = json.loads(path.read_text(encoding="utf-8-sig"))
        if (isinstance(graph, dict) and isinstance(graph.get("nodes"), list)
                and not graph.get("extra", {}).get("t8_plain_source") and relay_graph(graph)):
            yield path, graph


def companion_targets(root, sources, previous):
    """Keep published mappings stable when a new source sorts before old ones."""
    by_source = {}
    destinations = set()
    for row in previous["rows"]:
        source, target = row["source"], row["ordinary"]
        assert source not in by_source and target.casefold() not in destinations, "Duplicate prior mapping"
        relative = Path(target)
        assert not relative.is_absolute() and ".." not in relative.parts, "Unsafe prior target"
        assert relative.parent == Path(source).parent, "Companion moved outside source category"
        assert relative.stem.endswith(ORDINARY_SUFFIX), "Migrate numbered examples with rename_plain_prompt_workflows.py first"
        assert not validate_paths([relative.as_posix()]), "Windows-invalid companion target"
        by_source[source] = root / target
        destinations.add(target.casefold())
    result = {}
    for source in sources:
        relative = source.relative_to(root)
        if relative.as_posix() in by_source:
            result[source] = by_source[relative.as_posix()]
        else:
            target = ordinary_target(relative)
            assert target.as_posix().casefold() not in destinations, "Ambiguous descriptive companion name"
            destinations.add(target.as_posix().casefold())
            result[source] = root / target
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Refresh only manifest-owned, unchanged generated files")
    options = parser.parse_args()
    capture = json.loads(options.schema.read_text(encoding="utf-8"))
    info = {item["id"]: item["info"] for item in capture["nodes"]}
    info["PrimitiveStringMultiline"] = {"input": {"required": {"value": ["STRING", {"multiline": True, "default": ""}]}},
        "output": ["STRING"], "output_name": ["STRING"], "display_name": "完整提示词 · 普通文本"}
    info["MiniMaxH3PlainPromptRecipeEXPT8"] = {"input": {"required": {
        "prompt": ["STRING", {"multiline": True}], "length": ["INT", {"default": 124}]}},
        "output": ["H3_T8_PROMPT_RELAY_PLAN", "STRING", "INT", "STRING", "STRING"],
        "output_name": ["prompt_recipe", "compiled_prompt", "length", "timeline_json", "report_json"]}
    info["CLIPTextEncode"] = {"input": {"required": {"text": ["STRING", {"multiline": True}], "clip": ["CLIP", {}]}},
        "output": ["CONDITIONING"], "output_name": ["CONDITIONING"]}
    failures, success, candidates = [], [], []
    originals = list(scan(options.root))
    old_manifest = options.root / "examples/workflows/plain-prompt-index.json"
    previous = json.loads(old_manifest.read_text(encoding="utf-8")) if options.refresh else {"rows": []}
    owned = {row["ordinary"]: row for row in previous["rows"]}
    frozen = {path.relative_to(options.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (options.root / "examples/workflows").rglob("*.json")
              if path.relative_to(options.root).as_posix() not in owned
              and path.name != "plain-prompt-index.json"}
    targets = companion_targets(options.root, (path for path, _graph in originals), previous)
    for path, graph in originals:
        try:
            result = transform(graph, info, path.relative_to(options.root).as_posix())
            remaining = sorted({n["type"] for n in result["nodes"] if "Relay" in n["type"]
                                and n["type"] not in {"MiniMaxH3MotionRelayLengthEXPT8", "MiniMaxH3FastH3V2AcceptedRelayProjectEXPT8", "MiniMaxH3PromptRelayLongVideoPlanT8Advanced"}})
            if remaining:
                raise ValueError("Unconverted nodes: " + ", ".join(remaining))
            audit = validate_graph(graph, result, info)
            relative = path.relative_to(options.root).as_posix()
            target = targets[path]
            if target.exists():
                row_before = owned.get(target.relative_to(options.root).as_posix())
                assert row_before and row_before["source"] == relative, f"Unowned output {target}"
                assert hashlib.sha256(target.read_bytes()).hexdigest() == row_before["ordinary_sha256"], f"User-edited output {target}"
            payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            row = {"source": relative, "ordinary": target.relative_to(options.root).as_posix(),
                   "source_sha256": frozen[relative], "ordinary_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                   "source_title": graph.get("extra", {}).get("workflow_title", path.stem), **audit}
            success.append(row)
            candidates.append((target, payload))
        except Exception as error:
            failures.append({"path": path.relative_to(options.root).as_posix(), "error": str(error)})
    counts = Counter(item["error"] for item in failures)
    if options.write:
        if failures:
            raise ValueError("Complete catalogue conversion required before writing: " + str(failures[:3]))
        manifest_path = options.root / "examples/workflows/plain-prompt-index.json"
        index_path = options.root / "examples/workflows/PLAIN_PROMPTS.md"
        assert options.refresh or (not manifest_path.exists() and not index_path.exists()), "Companion index already exists"
        for target, payload in candidates:
            target.write_text(payload, encoding="utf-8", newline="\n")
        manifest_path.write_text(json.dumps({"schema": "t8.ordinary-prompt-examples.v1", "source_count": len(originals),
            "rows": success, "scope": "source/schema/wiring preservation; not new GPU quality acceptance"},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        index_path.write_text(render_plain_index(success), encoding="utf-8", newline="\n")
        for relative, digest in frozen.items():
            assert hashlib.sha256((options.root / relative).read_bytes()).hexdigest() == digest, "Original JSON changed"
    print(json.dumps({"converted": len(success), "failures": len(failures), "written": options.write,
                      "errors": counts, "examples": failures[:12]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
