"""Four new CPU software contracts; not trained H3/Bridge video evidence."""
import json

import pytest
from safetensors.torch import save_file

from h3_audio_t8_pkg import bridge_sidecar as sidecar
from h3_audio_t8_pkg.semantic_bridge import BridgeConfig, file_sha
from h3_audio_t8_pkg.semantic_bridge_profiles import LEGACY_SETTINGS
from h3_audio_t8_pkg.semantic_bridge_trans import TransBridge, TransSpec


@pytest.fixture
def model_files(tmp_path):
    contract = {"schema": 1, "alpha_min": 1., "alpha_max": 1., "magnitude_match": "per_token",
                "token_span": "all", "tail_ratio": 1., "chunk_tokens": 0,
                "auto_alpha": False, "guard": False, "allow_dim_mismatch": False}
    model = TransBridge(TransSpec(64, 1, 2, 64, True, 1., None)).eval()
    state = {"net." + k: v for k, v in model.state_dict().items()}
    metadata = {"arch": "trans", "dim": "5120", "hidden": "64", "layers": "1", "heads": "2",
                "max_tokens": "64", "residual_skip": "True", "residual_scale": "1."}
    files = {}
    for name, extra in (("ordinary", {}), ("fixed", {"application_contract": contract})):
        weight = tmp_path / (name + ".safetensors")
        save_file(state, weight, metadata={**metadata, "extra_json": json.dumps(extra)})
        fixed = name == "fixed"
        record = {"schema": 1, "status": "fixed_contract" if fixed else "unvalidated_starting_point",
                  "model_file": "not-used-to-resolve-a-weight.safetensors", "model_sha256": file_sha(weight),
                  "settings": {"alpha": 1. if fixed else .12, "magnitude_match": "per_token" if fixed else "none",
                               "token_scope": "all_tokens", "chunk_tokens": 0,
                               "auto_alpha": False, "guard": False, "allow_dim_mismatch": False},
                  "training_alpha_range": [.05, .35], "trial_alphas": [1.] if fixed else [.05, .12, .2],
                  "video_calibrated_by_this_export": False}
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(record), encoding="utf-8")
        files[name] = (weight, path, record)
    return files


def test_proposal_default_inactive_explicit_adopt_and_legacy_unmodified(model_files):
    weight, path, _ = model_files["ordinary"]
    before = dict(LEGACY_SETTINGS)
    config, report = sidecar.sidecar_config(weight, path)
    assert not config.active and not report["adopted"]
    assert report["suggested_settings"]["alpha"] == .12
    assert report["label_used_as_path"] is False
    accepted, report = sidecar.sidecar_config(weight, path, confirm_adopt=True)
    assert accepted.active and accepted.magnitude_match == "none" and accepted.chunk_tokens == 0
    assert LEGACY_SETTINGS == before and not report["optimal_alpha_qualified"]


def test_bad_weight_sha_refuses_proposal_but_manual_path_still_works(model_files):
    weight, path, record = model_files["ordinary"]
    record["model_sha256"] = "0" * 64
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA|content|changed|hash"):
        sidecar.sidecar_config(weight, path, confirm_adopt=True)
    assert BridgeConfig(str(weight), file_sha(weight), alpha=.2).active


def test_fixed_embedded_contract_wins_and_wrong_sidecar_does_not_edit_weight(model_files):
    weight, path, record = model_files["fixed"]
    before = file_sha(weight)
    config, _ = sidecar.sidecar_config(weight, path, confirm_adopt=True)
    assert config.alpha == 1. and config.magnitude_match == "per_token"
    record["settings"]["alpha"] = .12
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="contract mismatch"):
        sidecar.sidecar_config(weight, path, confirm_adopt=True)
    assert file_sha(weight) == before


def test_duplicate_nonfinite_and_bypass_flags_are_rejected(model_files):
    weight, path, record = model_files["ordinary"]
    path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        sidecar.inspect_sidecar(weight, path)
    record["settings"]["alpha"] = float("nan")
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="Nonfinite"):
        sidecar.inspect_sidecar(weight, path)
    record["settings"]["alpha"] = .12
    record["settings"]["guard"] = True
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="bypass"):
        sidecar.inspect_sidecar(weight, path)
