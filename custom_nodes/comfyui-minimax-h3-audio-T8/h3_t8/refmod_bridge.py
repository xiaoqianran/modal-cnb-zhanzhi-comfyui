"""Thin external-format assessment and explicit native-package join.

Existing v4/v5 RGB/PCM re-encoding importers remain the only normalization
converters. MultiRefMod MODEL hooks/blur-strength are not latent multipliers.
"""
from copy import deepcopy
import math
from pathlib import Path
import struct

from .reference_package import (ReferencePackage, MAX_MEMBERS, MAX_HEADER, IDENTIFIER,
    _unlinked, capture_package, file_sha)
from .tools.inspect_h3_external_reference import inspect_header, plain_json


def assess_external(path, expected_sha256, strength=1.):
    if type(strength) not in (int,float) or not math.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("RefMod slot strength must be a finite explicit number in 0..1")
    path = Path(path)
    _unlinked(path)
    before = file_sha(path)
    if before != expected_sha256:
        raise ValueError("Selected external reference file differs from its pinned SHA")
    header = inspect_header(path)
    with path.open("rb") as stream:
        length = struct.unpack("<Q",stream.read(8))[0]
        if not 2 <= length <= MAX_HEADER:
            raise ValueError("External header changed")
        metadata = plain_json(stream.read(length))["__metadata__"]
    bundle = plain_json(metadata["refmod_meta"])
    members = [bundle] if header["format_version"] == 4 else bundle["members"]
    modes = [row.get("mode", "unknown") for row in members]
    _unlinked(path)
    if file_sha(path) != before:
        raise ValueError("External reference changed during assessment")
    status = ("slot_skipped_explicitly" if strength == 0 else
              "delegate_original_MODEL_hook_semantics" if strength != 1 or any(mode != "encode" for mode in modes) else
              "candidate_for_existing_exact_RGB_PCM_importers")
    return dict(schema="t8.h09.refmod-bridge-assessment.v1", external_sha256=before,
        header=header, declared_modes=modes, slot_strength=strength, status=status,
        tensor_loads=0, imported=False, foreign_config_executed=False, MODEL_changed=False,
        strength_semantics="original_refmod_detail_blur_not_lora_strength_not_native_latent_scale",
        original_hook_delegate_preserved=True, automatic_accept=False)


def join_packages(packages, *, merge_roles=()):
    """An explicit join of ALREADY qualified native/imported packages.

    Stable roles spanning separately imported C-video/C-voice can be grouped
    only with explicit merge_roles=['C']; no guessing, sorting or pixel math.
    """
    if (not isinstance(packages,list) or not 1 <= len(packages) <= MAX_MEMBERS
            or not isinstance(merge_roles,(list,tuple)) or len(set(merge_roles)) != len(merge_roles)
            or any(not isinstance(role,str) or not IDENTIFIER.fullmatch(role) for role in merge_roles)):
        raise ValueError("Use a bounded ordered native package list and explicit unique merge-role IDs")
    members, tensors, mapping, identities, seen_roles, sources, producers = [], {}, [], [], set(), set(), {}
    for pi, package in enumerate(packages):
        if type(package) is not ReferencePackage:
            raise ValueError("Join needs qualified native packages, not unknown external payloads")
        manifest = package.verify()
        roles = {row["role_id"] for row in manifest["members"]}
        if (roles & seen_roles)-set(merge_roles):
            raise ValueError("Duplicate role across packages needs an explicit merge_roles declaration")
        seen_roles |= roles
        identities.append(manifest["sha256"])
        for mi, member in enumerate(manifest["members"]):
            key = (member["role_id"],member["kind"],member["source"]["sha256"])
            if key in sources:
                raise ValueError("Duplicate actual reference source is not a hidden strength increase")
            sources.add(key)
            producer = member["producer"]
            if producer["role"] in producers and producers[producer["role"]] != producer:
                raise ValueError("Actual reference producers differ; rebuild with the selected VAE before joining")
            producers[producer["role"]] = producer
            out = deepcopy(member)
            out["id"] = f"p{pi+1}_m{mi+1}"
            for field in ("latent","grounding"):
                if member[field] is not None:
                    name = out["id"] + ("_z" if field == "latent" else "_rgb")
                    tensors[name] = package.tensors[member[field]]
                    out[field] = name
            mapping.append(dict(package_index=pi, member_index=mi, original_member_id=member["id"],
                                joined_member_id=out["id"], role_id=out["role_id"], kind=out["kind"]))
            members.append(out)
    if len(members) > MAX_MEMBERS or set(merge_roles)-seen_roles:
        raise ValueError("Joined members exceed native capacity or requested merge role does not exist")
    result = capture_package(members,tensors)
    report = dict(schema="t8.h09.reference-join.v1", parent_manifest_sha256=identities,
        joined_manifest_sha256=result.verify()["sha256"], mapping=mapping, merge_roles=list(merge_roles),
        order="input_package_then_member_preserved", tensor_bytes_changed=False,
        strength_applied=False, MODEL_hooks_changed=False, automatic_accept=False)
    return result, report
