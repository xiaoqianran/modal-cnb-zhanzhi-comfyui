"""Same-condition tiny AV projection and read-only lock verification.

Inspired by sepiablue-ai/ComfyUI-H3-AudioFirst-X2-Stream (GPL-3.0-only).
Not a new sampler or audio engine: SourceAVPrepare owns stream assembly.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

import torch

from .core import empty_av_latent, nested_av_parts, resize_image, split_noise_masks
from .source_av import frame_count_from_video_latent_t

TOLERANCE = 2e-5
CHUNK = 65536
SPATIAL_KEYS = {
    "area", "mask", "control", "control_apply_to_uncond", "concat_latent_image",
    "concat_mask", "noise_concat", "minimax_refs", "t8_visual_marker_binding",
    "t8_qwen_reference_view", "t8_temporal_dialogue_scope",
}
SAFE_KEYS = {
    "pooled_output", "strength", "start_percent", "end_percent", "hooks",
    "model_conds", "minimax_token_tags", "minimax_keyframes", "minimax_frame_count",
}


def _active(value):
    if value is None or value is False:
        return False
    if isinstance(value, (Mapping, list, tuple, str)):
        return len(value) != 0
    if torch.is_tensor(value):
        return value.numel() != 0
    return True


def _finite(tensor, name):
    if not torch.is_tensor(tensor) or not tensor.is_floating_point():
        raise ValueError(f"{name} must be a floating tensor")
    # No whole-video CPU/float clone and no global cache/allocator changes.
    for chunk in tensor.flatten().split(CHUNK):
        if not bool(torch.isfinite(chunk).all()):
            raise ValueError(f"{name} contains NaN/Inf")


def _av(latent, name):
    video, audio = nested_av_parts(latent)
    if video.shape[1] != 24 or min(video.shape[2:]) <= 0 or any(s % 2 for s in video.shape[-2:]):
        raise ValueError(f"{name}: expected 24-channel H3 video on a 32-pixel grid")
    frames = frame_count_from_video_latent_t(video.shape[2])
    if tuple(audio.shape[:3]) != (1, 32, 2) or audio.shape[-1] != round(frames * 40 / 24):
        raise ValueError(f"{name}: audio/video clock mismatch (24fps / 40 latent fps)")
    if video.dtype != audio.dtype or video.device != audio.device:
        raise ValueError(f"{name}: strict dtype/device mismatch")
    _finite(video, name + " video")
    _finite(audio, name + " audio")
    return video, audio, frames


def project(positive, video_latent, first_frame=None, video_vae=None):
    """Keep embeddings by reference; only explicitly re-encode a raw first image."""
    video, audio, frames = _av(video_latent, "full clock input")
    if not isinstance(positive, (list, tuple)) or not positive:
        raise ValueError("positive must be nonempty CONDITIONING")
    has_image = first_frame is not None
    unknown = set()
    for entry in positive:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2 or not isinstance(entry[1], Mapping):
            raise ValueError("Expected CONDITIONING [embedding, metadata] entries")
        _finite(entry[0], "conditioning embedding")
        metadata = entry[1]
        bad = sorted(key for key in SPATIAL_KEYS if _active(metadata.get(key)))
        if bad:
            raise ValueError("Tiny projection does not transform spatial/reference/scoped metadata: "
                             + ", ".join(bad) + "; keep the original full-resolution route")
        if "minimax_frame_count" in metadata and metadata["minimax_frame_count"] != frames:
            raise ValueError("Conditioning frame_count differs from full AV clock")
        keyframes = metadata.get("minimax_keyframes", [])
        if not isinstance(keyframes, (list, tuple)):
            raise ValueError("Expected native keyframe list")
        if len(keyframes) != int(has_image):
            raise ValueError("First batch supports T2VA or exactly one first-frame guide; connect its raw IMAGE")
        if keyframes:
            kf = keyframes[0]
            if not isinstance(kf, Mapping) or kf.get("resolved_frame_index") != 0 or _active(kf.get("audio_latent")):
                raise ValueError("Only a video first-frame guide at frame 0 is supported by tiny projection")
            old = kf.get("latent")
            if not torch.is_tensor(old) or tuple(old.shape) != (1, 24, 1, *video.shape[-2:]):
                raise ValueError("First-frame guide must match the full video canvas")
            _finite(old, "original first-frame latent")
        unknown.update(set(metadata) - SAFE_KEYS - SPATIAL_KEYS)
    encoded = None
    if has_image:
        if not torch.is_tensor(first_frame) or first_frame.ndim != 4 or first_frame.shape[0] != 1 or first_frame.shape[-1] < 3:
            raise ValueError("first_frame must be one raw IMAGE [1,H,W,C]")
        _finite(first_frame, "first_frame")
        if video_vae is None or not callable(getattr(video_vae, "encode", None)):
            raise ValueError("A video VAE is required to encode the raw first_frame at 32x32")
        encoded = video_vae.encode(resize_image(first_frame, 32, 32, "disabled"))
        _finite(encoded, "tiny first-frame VAE output")
        if tuple(encoded.shape) != (1, 24, 1, 2, 2):
            raise ValueError("Video VAE must produce H3 [1,24,1,2,2] for the 32x32 first frame")
    result = []
    for embedding, metadata in positive:
        copied = dict(metadata)  # Do not deepcopy opaque user hooks or tensor embeddings.
        if encoded is not None:
            keyframe = dict(metadata["minimax_keyframes"][0])
            keyframe["latent"] = encoded
            copied["minimax_keyframes"] = [keyframe]
        result.append([embedding, copied])
    tiny, _ = empty_av_latent(32, 32, frames)
    # Match the full template's explicit dtype/device, never silently alter its clock.
    from comfy.nested_tensor import NestedTensor
    tv, ta = nested_av_parts(tiny)
    tiny["samples"] = NestedTensor((tv.to(video), ta.to(audio)))
    report = {"schema": "t8.h13.audio-first-projection.v1", "frame_count": frames,
              "audio_latent_steps": audio.shape[-1], "tiny_canvas": [32, 32],
              "CLIP_encodes": 0, "VAE_encodes": int(has_image),
              "embedding_objects_reused": True, "full_inputs_mutated": False,
              "unknown_metadata_preserved_unqualified": sorted(unknown),
              "quality_accepted": False,
              "effects": "Compile branch-specific external EAV/Relay after projection; no inherited receipt qualification",
              "first_image_same_as_original_is_graph_responsibility": has_image}
    return result, tiny, json.dumps(report, ensure_ascii=False)


def _audio_digest(audio):
    digest = hashlib.sha256(str((tuple(audio.shape), str(audio.dtype))).encode("ascii"))
    for chunk in audio.flatten().split(CHUNK):
        digest.update(chunk.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def audit(audio_source, locked_input, samples):
    """Verify source→prepared input→actual final audio; return final unchanged."""
    sv, source, frames = _av(audio_source, "audio_source")
    lv, locked, locked_frames = _av(locked_input, "locked_input")
    fv, final, final_frames = _av(samples, "samples actual final")
    if frames != locked_frames or frames != final_frames or tuple(lv.shape) != tuple(fv.shape):
        raise ValueError("Source/prepared/final frame clock or full video shape differs")
    if any(a.shape != source.shape or a.dtype != source.dtype or a.device != source.device for a in (locked, final)):
        raise ValueError("Source/prepared/final audio shape or strict dtype/device mismatch")
    vm, am = split_noise_masks(locked_input, lv, locked)
    for mask, tensor, expected, name in ((vm, lv, 1, "video"), (am, locked, 0, "audio")):
        if not torch.is_tensor(mask) or mask.shape != tensor.shape:
            raise ValueError("Prepared " + name + " mask must be explicit and full-shaped")
        _finite(mask, "prepared " + name + " mask")
        if not bool((mask == expected).all()):
            raise ValueError("Prepared masks must be video=1 and audio=0")
    maximum = 0.0
    exact = True
    for src, pre, out in zip(source.flatten().split(CHUNK), locked.flatten().split(CHUNK), final.flatten().split(CHUNK), strict=True):
        if not torch.equal(src, pre):
            raise ValueError("locked_input is not an exact copy of this audio_source")
        exact = exact and torch.equal(src, out)
        difference = float((src.detach().cpu().double() - out.detach().cpu().double()).abs().max())
        maximum = max(maximum, difference)
    if maximum > TOLERANCE:
        raise ValueError(f"Actual final audio changed beyond fixed {TOLERANCE}: max_abs={maximum}")
    report = {"schema": "t8.h13.audio-first-lock-audit.v1", "frame_count": frames,
              "source_tiny_canvas": [sv.shape[-1] * 16, sv.shape[-2] * 16],
              "final_canvas": [fv.shape[-1] * 16, fv.shape[-2] * 16],
              "fixed_tolerance": TOLERANCE, "max_abs_difference": maximum,
              "audio_exact": exact, "source_sha256": _audio_digest(source),
              "actual_final_sha256": _audio_digest(final), "samples_returned_unchanged": True,
              "sampler_completion_proof": False, "perceptual_quality_accepted": False}
    return samples, json.dumps(report, ensure_ascii=False)
