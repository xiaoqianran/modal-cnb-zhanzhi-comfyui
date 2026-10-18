"""New INT8 family contracts; tiny CPU values are not native sampler receipts."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
import h3_audio_t8_pkg
from h3_audio_t8_pkg.freevideo_int8 import contract as c, runtime as r
from h3_audio_t8_pkg.freevideo_int8.nodes import NODES, MODEL, STAGE
from h3_audio_t8_pkg.freevideo_quality import profiles as p, runtime as old
from h3_audio_t8_pkg.freevideo_quality.assets import evidence_sha
from h3_audio_t8_pkg.freevideo_exp.runtime import canonical, digest, tensor_record


def manifest():
    return dict(format="freevideo-int8-slim-v1", precision="int8", scale_granularity="rowwise",
                rotation=dict(kind="convrot", group=256),
                linears={"test": dict(storage="int8", convrot_group=256,
                                      weight_shape=[32, 256], scale_shape=[1, 32])})


def config(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    path = cache / "manifest.json"
    path.write_text(json.dumps(manifest()), encoding="utf8")
    files = [dict(path=str(path), bytes=path.stat().st_size, sha256=digest(path), kind="weight")]
    value = {name: str(tmp_path / name) for name in (
        "python", "source_root", "vdn_root", "base", "checkpoint", "home", "sampling_root")}
    value.update(cache=str(cache), schema=c.RUNTIME, freevideo_revision=c.REVISION,
                 model_revision=c.MODEL_REVISION, vdn_revision=c.VDN_REVISION,
                 files=files, inventory_sha256=hashlib.sha256(canonical(files).encode()).hexdigest())
    target = tmp_path / "int8.json"
    target.write_text(canonical(value), encoding="utf8")
    return target, value


def stage(role="LOW"):
    selected = p.plan("light", role)
    video, audio = torch.zeros(1, 24, 12, 16, 16), torch.ones(1, 32, 2, 65)
    roles = ["LOW", "HIGH"] if role == "HIGH" else [role]
    tables = [dict(identity=p.table_identity("3" * 64, "light", item, "t2va", reference_audio_t=1.),
                   index=i, bytes=100, sha256="4" * 64) for item in roles for i in range(50)]
    receipt = dict(schema=c.binding()["stage"], plan=selected, profile="light", role=role,
                   freevideo_revision=c.REVISION, model_revision=c.MODEL_REVISION, vdn_revision=c.VDN_REVISION,
                   model_precision="int8", engine=dict(linear_compute="int8"),
                   geometry=dict(width=256, height=256, frames=39), task="t2va",
                   clock=p.clock("light", role, "t2va", reference_audio_t=1.),
                   completed_nfe=selected["nfe"], sample=dict(step_seconds=[.1] * selected["nfe"]),
                   int8_kernels=dict(schema="t8-freevideo-int8-kernel-audit-v1", expected_targets=2,
                       installed_targets=2, actual_calls=dict(matmul=selected["nfe"]*2, rotate_quantize=selected["nfe"]),
                       nfe_calls=[dict(matmul=2, rotate_quantize=1) for _ in range(selected["nfe"])]),
                   request_sha256="0" * 64, output_sha256="1" * 64, source_inventory_sha256="2" * 64,
                   weight_identity="3" * 64, tables=tables, tables_sha256=evidence_sha(tables))
    if role == "HIGH":
        receipt.update(low_receipt_sha256="5" * 64, low_audio=tensor_record(audio))
    return r.make_stage(video, audio, receipt)


def test_config_family_and_actual_manifest_are_separate_and_content_bound(tmp_path):
    path, value = config(tmp_path)
    model = r.load_model(path)
    assert r.config_for(model, full=True) == value
    with pytest.raises(ValueError, match="Quality|quality|producer"):
        old.load_model(path)
    with pytest.raises(ValueError, match="INT8 Loader"):
        r.config_for(old.QualityModel(str(path), digest(path)))
    path.write_text(canonical(dict(value, model_revision=old.MODEL_REVISION)), encoding="utf8")
    with pytest.raises(ValueError, match="changed"):
        r.config_for(model)
    with pytest.raises(ValueError, match="pins"):
        r.load_model(path)


@pytest.mark.parametrize("change", [dict(precision="fp8"), dict(rotation=dict(kind="convrot", group=128)),
                                    dict(linears={"bad": dict(storage="int8", convrot_group=256,
                                         weight_shape=[32, 255], scale_shape=[1, 32])})])
def test_bad_precision_rotation_and_shapes_are_real_errors(change):
    with pytest.raises(ValueError, match="INT8"):
        c.validate_manifest(dict(manifest(), **change))


def test_inventory_manifest_and_duplicate_paths_do_not_bypass_integrity(tmp_path):
    path, value = config(tmp_path)
    broken = deepcopy(value)
    broken["files"] *= 2
    broken["inventory_sha256"] = hashlib.sha256(canonical(broken["files"]).encode()).hexdigest()
    with pytest.raises(ValueError, match="duplicate"):
        c.validate_config(broken)
    Path(value["cache"], "manifest.json").write_text("{}", encoding="utf8")
    with pytest.raises(ValueError, match="manifest"):
        r.load_model(path)


def test_exact_t1_tables_and_stages_do_not_inherit_fp8_or_dispatch_qualification():
    value = stage()
    assert r.validate_stage(value, "LOW")["completed_nfe"] == 8
    with pytest.raises(ValueError):
        old.validate_stage(value)
    with pytest.raises(ValueError):
        r.validate_stage(old.QualityStage(value.video, value.audio, value.receipt_json, value.receipt_sha256))
    receipt = json.loads(value.receipt_json)
    for change in (dict(engine=dict(linear_compute="native-fp8")), dict(model_precision="fp8"),
                   dict(schema=p.binding()["stage"]), dict(completed_nfe=4)):
        with pytest.raises(ValueError):
            r.make_stage(value.video, value.audio, dict(receipt, **change))
    broken = deepcopy(receipt)
    broken["tables"][0]["identity"] = p.table_identity("3" * 64, "light", "LOW", "ref2va_audio", reference_audio_t=0.)
    broken["tables_sha256"] = evidence_sha(broken["tables"])
    with pytest.raises(ValueError, match="table"):
        r.make_stage(value.video, value.audio, broken)


def test_new_cold_stage_roundtrip_preserves_exact_audio_and_rejects_tampering(tmp_path):
    value = stage("HIGH")
    path, sha = r.save_stage(value, tmp_path)
    restored = r.load_stage(path, sha)
    assert restored.receipt_json == value.receipt_json
    assert torch.equal(restored.video, value.video) and torch.equal(restored.audio, value.audio)
    restored.audio[0, 0, 0, 0] += 1
    with pytest.raises(ValueError, match="audio|content"):
        r.validate_stage(restored)
    with pytest.raises(ValueError, match="SHA"):
        r.load_stage(path, "a" * 64)


def test_planner_passes_precision_modality_schedule_lora_and_keeps_real_placement():
    calls = []
    engine = dict(linear_compute="int8", stream_weights=True, pin_host_gb=4.2, resident_blocks=7)
    policy = SimpleNamespace(engine=engine)
    def choose(hardware, **kwargs):
        calls.append((hardware, kwargs))
        return policy
    canvas = dict(width=864, height=480, frames=124)
    info = dict(task="ref2va_av", reference_video_tokens=405, reference_audio_tokens=84)
    hardware = object()
    result, admitted = c.policy_for(hardware, canvas, p.plan("max"), info,
        dict(max_block_bytes=123, root_bytes=456), choose=choose,
        geometry=lambda **kwargs: dict(kwargs, video_tokens=14850))
    assert result is policy and result.engine is engine
    assert calls[0][0] is hardware and calls[0][1]["precision"] == "int8"
    assert calls[0][1]["canvas"] is admitted and admitted["steps"] == 20 and admitted["task"] == "ref2va_av"
    assert admitted["reference_video_tokens"] == 405 and admitted["reference_audio_tokens"] == 84
    assert calls[0][1]["lora_max_block_bytes"] == 123 and calls[0][1]["lora_root_bytes"] == 456
    engine["linear_compute"] = "native-fp8"
    with pytest.raises(ValueError, match="arithmetic"):
        c.policy_for(hardware, canvas, p.plan("light"), info, {}, choose=choose, geometry=lambda **kw: kw)


def test_kernel_probe_admission_needs_actual_int8_not_legacy_finite_fp8():
    probes = dict(linear=dict(backend="linear-int8", policy="int8-convrot", status="complete", finite=True),
                  cudnn=dict(backend="cudnn"))
    c.validate_int8_probes(probes)
    for key, value in (("backend", "linear"), ("policy", "native-fp8-rowwise"), ("finite", False)):
        broken = deepcopy(probes)
        broken["linear"][key] = value
        with pytest.raises(ValueError, match="actual"):
            c.validate_int8_probes(broken)


def test_effect_descriptors_remain_external_and_legacy_types_stay_distinct():
    from h3_audio_t8_pkg.freevideo_exp.runtime import with_lora
    from h3_audio_t8_pkg.freevideo_exp.effects import with_eav
    model = r.Int8Model("not-opened", "0" * 64)
    facade = with_lora(r.facade(model), "disabled-and-missing", 0.)
    modified = r.from_facade(with_eav(facade, mode="report_only"))
    assert len(modified.loras) == 1 and json.loads(modified.eav)["mode"] == "report_only"
    assert model.loras == () and model.eav is None
    assert not isinstance(modified, old.QualityModel)
    with pytest.raises(ValueError, match="content"):
        r.validate_stage(replace(stage(), receipt_sha256="0" * 64))


def test_all_new_schemas_are_resolved_and_append_only_without_old_socket_types():
    nodes = asyncio.run(h3_audio_t8_pkg.comfy_entrypoint().get_node_list())
    start = nodes.index(NODES[0])
    assert nodes[start:start+len(NODES)] == NODES
    assert nodes[start-1].define_schema().node_id == "MiniMaxH3PersonAppendEXPT8"
    assert len(nodes) == len({cls.define_schema().node_id for cls in nodes})
    for cls in NODES:
        schema = cls.define_schema()
        assert schema.get_v1_info(cls).name == cls.__name__
    assert MODEL.io_type == "H3_T8_FREEVIDEO_INT8_MODEL" and STAGE.io_type == "H3_T8_FREEVIDEO_INT8_STAGE"


def test_actual_kernel_delegates_run_restore_and_do_not_erase_lora_forward():
    from h3_audio_t8_pkg.freevideo_int8.audit import KernelAudit, validate
    class Int8Linear:
        weight_int8 = torch.zeros(32, 256, dtype=torch.int8)
        weight_scale = torch.ones(1, 32)
        forward = object()  # A pre-existing callable/LoRA owner is not replaced.
    module = Int8Linear()
    original_forward = module.forward
    calls = []
    def gemm(value):
        calls.append(value)
        return value + 1
    def rotate(value):
        return value * 2
    ops = SimpleNamespace(Int8Linear=Int8Linear, matmul=gemm, rotate_quantize=rotate)
    engine = SimpleNamespace(transformer=SimpleNamespace(get_submodule=lambda name: module))
    audit = KernelAudit(engine, manifest(), ops)
    with audit.observe():
        assert ops.matmul(ops.rotate_quantize(3)) == 7
        audit.step()
    assert ops.matmul is gemm and ops.rotate_quantize is rotate and module.forward is original_forward
    assert calls == [6] and validate(audit.snapshot(), 1)["installed_targets"] == 1
    with pytest.raises(ValueError, match="no actual"):
        audit.step()
    broken = audit.snapshot()
    broken["nfe_calls"][0]["matmul"] = 0
    with pytest.raises(ValueError, match="kernel-call"):
        validate(broken, 1)


def test_actual_kernel_errors_propagate_and_foreign_replacement_is_preserved():
    from h3_audio_t8_pkg.freevideo_int8.audit import KernelAudit
    class Int8Linear:
        weight_int8 = torch.zeros(32, 256, dtype=torch.int8)
        weight_scale = torch.ones(1, 32)
    ops = SimpleNamespace(Int8Linear=Int8Linear, matmul=lambda x: 1/0, rotate_quantize=lambda x: x)
    audit = KernelAudit(SimpleNamespace(transformer=SimpleNamespace(get_submodule=lambda name: Int8Linear())), manifest(), ops)
    original = ops.matmul
    with pytest.raises(ZeroDivisionError), audit.observe():
        ops.matmul(1)
    assert ops.matmul is original and audit.counts["matmul"] == 0
    def foreign(x):
        return x
    with pytest.raises(ValueError, match="delegate changed"), audit.observe():
        ops.matmul = foreign
    assert ops.matmul is foreign
