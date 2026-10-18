"""Explicit SHA-bound trainer guidance. Never auto-apply or rewrite old presets.

Schema source: T8mars/MinimaxH3_Semantic_Bridge_Trainer-T8 v0.2.2,
c9844b46e0e202c6ec15754983286038c020043b (MIT). Model license is independent.
Training bounds/recommendations are not video calibration or an optimum.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .semantic_bridge import BridgeConfig
from .semantic_bridge_profiles import inspect_bridge_profile, validate_profile_settings


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Bridge sidecar field: " + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Nonfinite JSON value: " + value)


def inspect_sidecar(weight, sidecar):
    path = Path(sidecar).resolve(strict=True)
    if path.stat().st_size > 64_000:
        raise ValueError("Bridge sidecar exceeds 64KB")
    raw = path.read_bytes()
    data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if type(data) is not dict or type(data.get("schema")) is not int or data["schema"] != 1:
        raise ValueError("Unsupported Bridge sidecar schema")
    if data.get("status") not in {"fixed_contract", "unvalidated_starting_point"}:
        raise ValueError("Unsupported Bridge guidance status")
    sha = data.get("model_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
        raise ValueError("Bridge sidecar requires the complete weight SHA256")
    profile = inspect_bridge_profile(weight, expected_sha=sha.lower())
    label = data.get("model_file")
    if not isinstance(label, str) or not 1 <= len(label) <= 512:
        raise ValueError("Bridge model_file must be a bounded display label")
    settings = data.get("settings")
    expected = {"alpha", "magnitude_match", "token_scope", "chunk_tokens",
                "auto_alpha", "guard", "allow_dim_mismatch"}
    if type(settings) is not dict or set(settings) != expected:
        raise ValueError("Bridge sidecar settings must follow the fixed schema1 formula")
    alpha = settings["alpha"]
    if type(alpha) not in (float, int) or not math.isfinite(alpha) or not 0 < alpha <= 1:
        raise ValueError("Bridge sidecar alpha must be finite and within (0,1]")
    if settings["magnitude_match"] not in {"none", "per_token"} or settings["token_scope"] != "all_tokens":
        raise ValueError("Unsupported exported magnitude/token formula")
    if type(settings["chunk_tokens"]) is not int or settings["chunk_tokens"] != 0:
        raise ValueError("Schema1 trainer guidance requires whole-sequence chunk_tokens=0")
    if any(settings[key] is not False for key in ("auto_alpha", "guard", "allow_dim_mismatch")):
        raise ValueError("Exported guidance must not enable auto-alpha/guard/dimension bypass")
    bounds = data.get("training_alpha_range")
    if bounds is not None and (type(bounds) is not list or len(bounds) != 2
            or any(type(a) not in (float, int) or not math.isfinite(a) for a in bounds)
            or not 0 < bounds[0] <= bounds[1] <= 1):
        raise ValueError("Invalid recorded training alpha bounds")
    trials = data.get("trial_alphas")
    if type(trials) is not list or not 1 <= len(trials) <= 16 or any(
            type(a) not in (float, int) or not math.isfinite(a) or not 0 < a <= 1 for a in trials):
        raise ValueError("Invalid bounded trial alpha list")
    if data.get("video_calibrated_by_this_export") is not False:
        raise ValueError("This schema does not export video-quality calibration")
    fixed = profile["fixed_contract"] is not None
    if (data["status"] == "fixed_contract") != fixed:
        raise ValueError("Sidecar fixed-contract claim disagrees with embedded weight metadata")
    chosen = {k: settings[k] for k in ("alpha", "magnitude_match", "token_scope", "chunk_tokens")}
    warnings = validate_profile_settings(profile, **chosen)  # fixed embedded contract wins
    if not fixed and bounds is not None and not bounds[0] <= alpha <= bounds[1]:
        raise ValueError("Suggested starting alpha is outside the recorded training formula")
    return {"schema": "t8.h11.bridge-sidecar.v1", "weight_sha256": profile["sha256"],
            "sidecar_sha256": hashlib.sha256(raw).hexdigest(), "model_file_label": label,
            "label_used_as_path": False, "architecture": profile["architecture"],
            "embedded_fixed_contract": profile["fixed_contract"], "status": data["status"],
            "suggested_settings": dict(settings), "training_alpha_range": bounds,
            "trial_alphas": trials, "existing_preset": profile["settings"],
            "existing_preset_source": profile["settings_source"], "warnings": warnings,
            "source": "explicit_external_unsigned_sidecar_bound_to_weight_content",
            "video_quality_qualified": False, "optimal_alpha_qualified": False,
            "adopted": False, "conditioning_modified": False, "weight_modified": False}


def sidecar_config(weight, sidecar, *, confirm_adopt=False, device="auto"):
    if type(confirm_adopt) is not bool:
        raise ValueError("Explicit adoption must be a boolean")
    report = inspect_sidecar(weight, sidecar)
    if device not in {"auto", "cpu", "cuda"}:
        raise ValueError("Invalid explicit Bridge compute device")
    s = report["suggested_settings"]
    # Even a valid proposal stays inactive unless the user explicitly adopts it.
    config = BridgeConfig(str(Path(weight).resolve()), report["weight_sha256"], float(s["alpha"]),
                          s["magnitude_match"], s["token_scope"], device, s["chunk_tokens"], confirm_adopt)
    report["adopted"] = confirm_adopt
    report["config_active"] = config.active
    return config, report
