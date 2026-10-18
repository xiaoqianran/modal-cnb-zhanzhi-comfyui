"""Explicit Qwen-grounded, audio-VAE-only reference projection.

Separate from legacy video-required conditioning. No video encoding, no change
to paired source identity, source PCM timeline, drive/final slots or old defaults.
Transient execution-local objects, not a new persistent reference asset format.
"""
from dataclasses import dataclass
import json
import re

import torch
import node_helpers

from .core import (encode_audio_once, empty_av_latent, fit_audio_latent, nested_av_parts,
                   replace_audio_latent, validate_audio)
from .prompt_tags import media_map_json, prepare_prompt
from .reference_package import MAX_BYTES, tensor_record
from .progressive_producers import native_producer_identity


def producer_record(audio_vae):
    value = native_producer_identity(audio_vae, "audio_vae")
    if value.get("portable_cache_reuse") is False:
        return {"execution_local_object": id(audio_vae), "portable_cache_reuse": False,
                "opaque_internal_state_certified": False}
    return value


@dataclass(frozen=True)
class AudioReference:
    role: str
    origin: str
    grounding_kind: str
    grounding: object
    audio_latent: object
    source_pcm: object
    source_rate: int
    records_json: str
    producer: object
    producer_json: str

    def verify(self, audio_vae):
        if audio_vae is not self.producer:
            raise ValueError("Audio-only reference must use its actual selected audio VAE object; rebuild explicitly")
        if producer_record(audio_vae) != json.loads(self.producer_json):
            raise ValueError("Actual audio reference encoder changed; rebuild explicitly")
        actual = {"pcm": tensor_record(self.source_pcm), "latent": tensor_record(self.audio_latent),
                  "grounding": tensor_record(self.grounding) if self.grounding is not None else None}
        if actual != json.loads(self.records_json):
            raise ValueError("Audio-only reference contents changed after preparation")
        return actual


def capture(role, origin, grounding_kind, audio, audio_vae, frames=None):
    if not isinstance(role, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", role):
        raise ValueError("Explicit short role ID required")
    if origin not in ("standalone_audio", "paired_video_soundtrack") or grounding_kind not in ("none", "image", "video"):
        raise ValueError("Choose explicit source origin and Qwen-only grounding kind")
    if origin == "paired_video_soundtrack" and grounding_kind != "video":
        raise ValueError("Paired-video audio retains its explicit video source, not guessed standalone conversion")
    grounding = None
    if grounding_kind == "none":
        if frames is not None:
            raise ValueError("Qwen grounding none must not silently drop connected frames")
    else:
        if (type(frames) is not torch.Tensor or frames.ndim != 4 or frames.shape[-1] != 3
                or frames.dtype != torch.float32 or frames.numel()*4 > MAX_BYTES
                or not bool(torch.isfinite(frames).all()) or not bool(((frames >= 0) & (frames <= 1)).all())
                or (grounding_kind == "image" and frames.shape[0] != 1)
                or (grounding_kind == "video" and not 5 <= frames.shape[0] <= 360)):
            raise ValueError("Bounded finite RGB grounding required; image=1 frame, video=5..360 at24fps")
        grounding = frames.detach().cpu().contiguous().clone()
    pcm, rate = validate_audio(audio)
    if pcm.shape[1] not in (1, 2) or pcm.numel()*pcm.element_size() > MAX_BYTES:
        raise ValueError("Bounded mono/stereo source PCM required")
    pcm = pcm.detach().cpu().float().contiguous().clone()
    tensor_record(pcm)  # finite/bounded validation before VAE
    if rate <= 0:
        raise ValueError("Source sample rate must be positive")
    from .core import ensure_h3_audio_vae_non_aligned_crop_compat
    ensure_h3_audio_vae_non_aligned_crop_compat(audio_vae)
    producer = producer_record(audio_vae)
    encoded = encode_audio_once(audio_vae, {"waveform": pcm, "sample_rate": rate}).detach().cpu().contiguous().clone()
    if tuple(encoded.shape[:3]) != (1, 32, 2) or encoded.shape[-1] < 1:
        raise ValueError("Selected audio encoder did not produce native H3 audio latent")
    records = {"pcm": tensor_record(pcm), "latent": tensor_record(encoded),
               "grounding": tensor_record(grounding) if grounding is not None else None}
    source = AudioReference(role, origin, grounding_kind, grounding, encoded, pcm, rate,
                            json.dumps(records, sort_keys=True), audio_vae, json.dumps(producer, sort_keys=True))
    source.verify(audio_vae)
    return source, {"role": role, "origin": origin, "Qwen_grounding": grounding_kind,
                    "no_visual_latent": True, "video_VAE_calls": 0, "audio_VAE_calls": 1,
                    "source_sample_rate": rate, "source_samples": pcm.shape[-1],
                    "execution_local_only": True, "contents": records, "automatic_accept": False}


def build(clip, audio_vae, sources, prompt, width, height, length, *,
          audio_mode="native", drive_audio=None, final_audio=None, semantic_bridge=None):
    if type(sources) is not list or not 1 <= len(sources) <= 3 or any(type(s) is not AudioReference for s in sources):
        raise ValueError("Use 1..3 explicit prepared audio-only sources in declared slot order")
    roles = [s.role for s in sources]
    if len(set(roles)) != len(roles):
        raise ValueError("Duplicate stable role ID; no implicit role merge or renumbering")
    if width < 32 or height < 32 or width % 32 or height % 32:
        raise ValueError("Canvas uses positive 32-grid")
    if audio_mode not in ("native", "reference_only", "lock_source", "remix_source"):
        raise ValueError("Unknown explicit source audio mode")
    if audio_mode != "native" and drive_audio is None:
        raise ValueError("Selected audio mode requires explicit drive_audio, not a voice reference")
    latent, frames = empty_av_latent(width, height, length)
    _, audio_template = nested_av_parts(latent)
    items, refs, pictures, videos, audios, mapping = [], [], [], [], [], []
    before = []
    for slot, source in enumerate(sources, 1):
        before.append(source.verify(audio_vae))
        items.append({"type": "audio"})
        refs.append({"kind": "audio", "ref_audio_t": int(source.audio_latent.shape[-1]),
                     "audio_latent": source.audio_latent.clone()})
        audios.append(f"role:{source.role}/{source.origin}")
        visual_ordinal = None
        if source.grounding_kind == "image":
            items.append({"type": "image", "data": source.grounding.clone()})
            pictures.append("Qwen_only:" + source.role)
            visual_ordinal = len(pictures)
        elif source.grounding_kind == "video":
            indices = list(range(0, source.grounding.shape[0], 12))
            items.append({"type": "video", "data": source.grounding[indices].clone(),
                          "timestamps": [index/24 for index in indices]})
            videos.append("Qwen_only:" + source.role)
            visual_ordinal = len(videos)
        mapping.append({"role_id": source.role, "declared_slot": slot, "audio_ordinal": len(audios),
                        "source_origin": source.origin, "Qwen_visual_kind": source.grounding_kind,
                        "Qwen_visual_ordinal": visual_ordinal, "DiT_kind": "audio",
                        "no_visual_latent": True, "source_PCM_samples": source.source_pcm.shape[-1]})
    counts = {"pictures": len(pictures), "videos": len(videos), "audios": len(audios)}
    text, warnings = prepare_prompt(prompt, counts, source_audio_ordinal=0,
                                   prompt_primary_audio_ordinal=0, strict=True)
    tokenize_kwargs = {"minimax_ref_items": items}
    positive = clip.encode_from_tokens_scheduled(clip.tokenize(text, **tokenize_kwargs))
    values = {"minimax_refs": refs, "t8_audio_only_reference_projection": {
        "schema": "t8.h11.audio-reference-only.v1", "mapping": mapping,
        "video_VAE_calls": 0, "fresh_Qwen_encoding": True, "execution_local_only": True}}
    positive = node_helpers.conditioning_set_values(positive, values)
    if semantic_bridge is not None and semantic_bridge.active:
        from .semantic_bridge import apply_bridge
        positive, _ = apply_bridge(positive, semantic_bridge,
            encoding_source="native_h3:Ref2VA:audio_only_fresh_Qwen")
    if drive_audio is not None and audio_mode in ("lock_source", "remix_source"):
        encoded = fit_audio_latent(encode_audio_once(audio_vae, drive_audio), audio_template)
        # Explicit source control. No automatic voice-reference-as-drive substitution.
        latent = replace_audio_latent(latent, encoded, 0. if audio_mode == "lock_source" else .35)
    for source, expected in zip(sources, before):
        if source.verify(audio_vae) != expected:
            raise ValueError("Reference source changed during fresh encoding")
    from .temporal_dialogue_encoding import capture_native_text_recipe
    recipe = capture_native_text_recipe(clip, tokenize_kwargs, values, counts, 0, 0, True,
        semantic_bridge, "Ref2VA", frames, width, height)
    report = {"mapping": mapping, "media_counts": counts, "warnings": warnings,
              "video_VAE_calls": 0, "DiT_visual_reference_blocks": 0,
              "drive_audio_explicit": drive_audio is not None, "final_audio_explicit": final_audio is not None,
              "audio_mode": audio_mode, "automatic_accept": False}
    return (positive, latent, final_audio if final_audio is not None else drive_audio,
            text, media_map_json(pictures, videos, audios, 0), json.dumps(report, ensure_ascii=False), recipe)
