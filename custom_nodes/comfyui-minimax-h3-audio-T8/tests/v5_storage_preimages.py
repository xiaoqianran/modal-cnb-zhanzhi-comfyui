"""Reconstruct and hash-pin the two actual reviewed historical reader sources."""
import hashlib
import importlib.util
from pathlib import Path

from h3_audio_t8_pkg.modular_sampling import chunked_v5_storage as current
from h3_audio_t8_pkg.modular_sampling import chunked_v5_storage_compat as compat


def _replace_once(source, before, after):
    assert source.count(before) == 1, f"Reviewed source fragment changed: {before[:90]}"
    return source.replace(before, after, 1)


def reviewed_preimage_bytes(profile):
    source = Path(current.__file__).read_text(encoding="utf8")
    # Historical source hashes include the old size caps. Reconstruct those
    # exact old readers for replay tests, never weaken the pinned SHA or put
    # their admission limits back into current execution.
    size_changes = (
        ('from .storage import _digest,', 'from .storage import MAX_FILE, MAX_JSON, _digest,'),
        ('        snapshot = _decode_metadata_value(encoded, tensors, set(), path="chunked_v5.window")',
         '        if len(payload.encode("utf-8")) > MAX_JSON or sum(\n'
         '                item.numel() * item.element_size() for item in tensors.values()) > MAX_FILE - MAX_JSON:\n'
         '            raise ValueError("v5 frozen window exceeds metadata or tensor size limit")\n'
         '        snapshot = _decode_metadata_value(encoded, tensors, set(), path="chunked_v5.window")'),
        ('0 < header_bytes <= os.fstat(handle.fileno()).st_size - 8:', '0 < header_bytes <= MAX_JSON:'),
        ('0 < manifest_path.stat().st_size or', '0 < manifest_path.stat().st_size <= MAX_JSON or'),
        ('8 < manifest["state_bytes"] or', '8 < manifest["state_bytes"] <= MAX_FILE or'),
        ('0 < header_bytes or header_bytes >', '0 < header_bytes <= MAX_JSON or header_bytes >'),
    )
    for before, after in size_changes:
        source = _replace_once(source, before, after)
    changes = (
        ('from . import chunked_v5_storage_compat as compat\n', ''),
        ('modules = (parity, legacy, chunked_v5, chunked_v5_effects, chunked_v5_relay, compat)',
         'modules = (parity, legacy, chunked_v5, chunked_v5_effects, chunked_v5_relay)'),
        ('                manifest["schema"] != SCHEMA or manifest["state_file"] != "state.safetensors" or\n',
         '                manifest["schema"] != SCHEMA or manifest["state_file"] != "state.safetensors" or\n'
         '                manifest["implementation"] != _implementation_identity() or\n'),
        ('        profile = compat.implementation_profile(manifest["implementation"], _implementation_identity())\n', ''),
        ('"prepared_sha256": compat.prepared_sha(prepared, profile, _prepared_sha(prepared))}',
         '"prepared_sha256": _prepared_sha(prepared)}'),
        ('        current_binding = {**binding, "prepared_sha256": _prepared_sha(prepared)}\n'
         '        if verify_window(result, source, lifted, prepared, plan) != current_binding:',
         '        if verify_window(result, source, lifted, prepared, plan) != binding:'),
        ('              "implementation_profile": profile,\n'
         '              "source_storage_sha256": manifest["implementation"][compat.STORAGE_SOURCE],\n'
         '              "historical_literal_format": profile != compat.CURRENT_PROFILE,\n', ''),
    )
    for before, after in changes:
        source = _replace_once(source, before, after)
    if profile == compat.FULL_REPORT_PROFILE:
        start = source.index('def _stable_upscale_report(')
        end = source.index('def _prepared_sha(', start)
        source = source[:start] + source[end:]
        source = _replace_once(source,
            '_input_identity(_stable_upscale_report(prepared.lift.upscale_report))',
            '_input_identity(prepared.lift.upscale_report)')
        expected = compat.LEGACY_FULL_REPORT_SHA
    else:
        assert profile == compat.STABLE_PROFILE
        expected = compat.HISTORICAL_STABLE_SHA
    raw = source.encode('utf8')
    assert hashlib.sha256(raw).hexdigest() == expected
    return raw


def historical_module(tmp_path, profile):
    directory = tmp_path / profile
    directory.mkdir(exist_ok=True)
    path = directory / 'chunked_v5_storage.py'
    path.write_bytes(reviewed_preimage_bytes(profile))
    name = 'h3_audio_t8_pkg.modular_sampling._review_' + profile
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._implementation_identity()[compat.STORAGE_SOURCE] == hashlib.sha256(path.read_bytes()).hexdigest()
    return module
