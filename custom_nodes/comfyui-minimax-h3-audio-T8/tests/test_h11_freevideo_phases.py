"""Bounded observation and unchanged producer AST, not fresh model runs."""
import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
from h3_audio_t8_pkg import freevideo_phases as phases


def test_phase_never_fakes_completed_nfe_zero_compile_or_additive_cuda_time(tmp_path, monkeypatch):
    now = [10.]
    module = SimpleNamespace(compilation_time_metrics={"compile_fx_inner": [2.]})
    monkeypatch.setitem(sys.modules, "torch._dynamo.utils", module)
    log = phases.PhaseTimeline(tmp_path, clock=lambda: now[0], limit=3)
    now[0] += 7
    log.begin("engine_load")
    assert not log.snapshot()["NFE_events"]
    now[0] += 4
    log.begin("sampling")
    module.compilation_time_metrics["compile_fx_inner"].append(3.)
    log.step(1, 8, 11.)
    assert log.snapshot()["compiler"]["nested_host_seconds_delta"] == {"backend_compile": 3.}
    assert not log.snapshot()["compiler"]["additive_with_sampling_or_each_other"]
    for _ in range(7):
        log.begin("release")
    assert len(log.spans) == 3 and log.dropped == 6
    report = phases.phase_report({"completed_nfe": 8, "sample": {"step_seconds": [11.]*8}})
    assert not report["load"]["available"] and not report["transfer"]["available"]
    assert not report["VAE_decode"]["available"] and report["completed_NFE"] == 8
    with pytest.raises(ValueError, match="NFE"):
        log.step(0, 8, 1.)


@pytest.mark.parametrize("family", ["quality", "int8"])
def test_worker_numeric_producer_request_and_sampler_ast_unchanged(family):
    root = Path(__file__).resolve().parents[1]
    original_AST_sha = {
        "quality": "7b1cf1646ac057b3c14b7cbe58560e1fabb65865537ca31cf433899544d257b3",
        "int8": "d0aa1fff7370344fab4edf006728492c2556b979cc12e3b60ae0827bbf047ec5",
    }
    class RemoveTelemetry(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None if node.module == "freevideo_phases" else node
        def visit_Expr(self, node):
            return None if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "timeline") else node
        def visit_Assign(self, node):
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "timeline":
                return None
            if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                    and target.value.id == "report" and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "phase_timeline"):
                return None
            return node
    current = ast.parse((root / f"h3_t8/freevideo_{family}/worker.py").read_text(encoding="utf8"))
    stripped = ast.dump(RemoveTelemetry().visit(current), include_attributes=False).encode()
    assert hashlib.sha256(stripped).hexdigest() == original_AST_sha[family]
