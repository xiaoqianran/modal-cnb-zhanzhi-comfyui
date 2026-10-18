"""Six small contracts for new observational transport, not model execution."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from h3_audio_t8_pkg import freevideo_phase_live as live


def test_bounded_atomic_phase_reader_never_advances_nfe_or_exposes_extra_content(tmp_path):
    now, updates, packets = [10.], [], []
    observer = live.ObservedProgress(lambda n, total: updates.append((n, total)), 8, packets.append, clock=lambda: now[0])
    record = {"schema": "t8.h11.freevideo-phases.v1", "current_phase": "engine_load",
              "NFE_events": [{"completed": 8}], "prompt": "private text", "path": "private path"}
    (tmp_path/"phase.json").write_text(json.dumps(record), encoding="utf8")
    live.observe_phase(observer, tmp_path)
    assert packets[-1]["phase"] == "engine_load" and packets[-1]["completed_NFE"] == 0 and not updates
    assert "private" not in json.dumps(packets)
    for _ in range(30):
        observer.poll(tmp_path)
    assert len(packets) == 2  # bounded to one/sec for unchanged phase/count
    observer(1, 8)
    assert updates == [(1, 8)] and packets[-1]["completed_NFE"] == 1
    (tmp_path/"phase.json").write_text("x"*65537, encoding="utf8")
    observer.poll(tmp_path)
    assert packets[-1]["phase"] == "phase_unavailable" and updates == [(1, 8)]
    calls = []
    live.observe_phase(lambda *args: calls.append(args), tmp_path)
    assert calls == []  # no extra callback hooks on unknown third-party callables
    def original_failure(*args):
        raise RuntimeError("original callback failure")
    broken = live.ObservedProgress(original_failure, 8)
    with pytest.raises(RuntimeError, match="original callback failure"):
        broken(1, 8)


def test_actual_core_context_sender_preserves_original_bar_and_targets_original_client(monkeypatch):
    import torch
    import comfy.utils
    from comfy_execution.utils import CurrentNodeContext
    from server import PromptServer
    packets, bar_updates = [], []
    server = SimpleNamespace(client_id="original-client", send_sync=lambda *args: packets.append(args))
    monkeypatch.setattr(PromptServer, "instance", server, raising=False)
    bar = comfy.utils.ProgressBar(8)
    bar.hook = lambda n, total, preview, **kwargs: bar_updates.append((n, total, preview, kwargs))
    with CurrentNodeContext("original-prompt", "node_1"):
        progress = live.core_progress(bar, 8)
    server.client_id = "other-client"
    progress(1, 8)
    assert bar.current == 1 and len(bar_updates) == 1
    assert all(row[0] == live.EVENT and row[2] == "original-client" for row in packets)
    assert all(row[1]["prompt_id"] == "original-prompt" and row[1]["node_id"] == "node_1" for row in packets)
    with CurrentNodeContext("metadata-prompt", "node_2"):
        live.completed_card_notice({"completed_nfe": 3})
    assert packets[-1][1]["phase"] == "legacy_receipt" and packets[-1][1]["completed_NFE"] == 3
    assert bar.current == 1 and len(bar_updates) == 1 and not torch.cuda.is_initialized()


@pytest.mark.parametrize("family,part,original", [
    ("quality", "runtime", "3d68eca0a7e653be05bb2ba66f5f9e5bf9d2343753b173b9479c488b97c15920"),
    ("int8", "runtime", "53e392af52f06e048756042dec2edba98982b97c08d9011740e7f2700b92181c"),
    ("quality", "nodes", "50a889bbe8bd043b3ed0d51279f43a67bca0bdd57c69d43d1892ef667c6207e2"),
    ("int8", "nodes", "98252841a7a619181862e61f9efe960c7122c43812f0d67cf76489ee0ffa11ad"),
])
def test_original_math_request_sampler_schema_unchanged_except_observational_calls(family, part, original):
    root = Path(__file__).resolve().parents[1]
    class RemoveObserver(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None if node.module == "freevideo_phase_live" else node
        def visit_Expr(self, node):
            return None if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                            and node.value.func.id == "observe_phase") else node
        def visit_Return(self, node):
            if (isinstance(node.value, ast.Tuple) and len(node.value.elts) == 2
                    and isinstance(node.value.elts[1], ast.Call)
                    and isinstance(node.value.elts[1].func, ast.Name) and node.value.elts[1].func.id == "core_progress"):
                node.value.elts[1] = ast.parse("lambda n, count: bar.update_absolute(n, count)", mode="eval").body
            return node
    value = ast.parse((root/f"h3_t8/freevideo_{family}/{part}.py").read_text(encoding="utf8"))
    assert hashlib.sha256(ast.dump(RemoveObserver().visit(value), include_attributes=False).encode()).hexdigest() == original
