"""Opt-in native H3 guide encoding with per-branch anchor preservation.

Delegates geometry, frame bounds, VAE encoding and audio cropping to Core.
Does not monkeypatch Core or change existing workflows.
"""
from collections.abc import Mapping, Sequence
import json

from comfy_api.latest import io


def append_branch_guide(positive, latent, frame_idx, **inputs):
    # Core imports its own top-level nodes module; defer until Comfy is loaded.
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide

    if (not isinstance(positive, Sequence) or isinstance(positive, (str, bytes))
            or not positive):
        raise ValueError("positive must be non-empty CONDITIONING")
    histories = []
    for entry in positive:
        if (not isinstance(entry, Sequence) or len(entry) != 2
                or not isinstance(entry[1], Mapping)):
            raise ValueError("Each conditioning branch needs embedding and metadata")
        history = entry[1].get("minimax_keyframes", [])
        if (not isinstance(history, Sequence) or isinstance(history, (str, bytes))
                or not all(isinstance(row, Mapping) for row in history)):
            raise ValueError("minimax_keyframes must contain guide mappings")
        histories.append(list(history))

    # Empty only the *temporary* history so Core encodes exactly one new guide.
    # The original embedding, reference objects, audio and metadata are untouched.
    metadata = dict(positive[0][1])
    metadata["minimax_keyframes"] = []
    encoded = MiniMaxH3AddGuide.execute(
        [[positive[0][0], metadata]], latent, frame_idx, **inputs
    ).result[0]
    guides = encoded[0][1].get("minimax_keyframes", [])
    if len(guides) != 1 or not isinstance(guides[0], Mapping):
        raise RuntimeError("Native H3 AddGuide did not return one encoded guide")
    guide = guides[0]
    # Preserve newly introduced native metadata, without importing the first
    # branch's original references or schedule into any other branch.
    native_added = {key: value for key, value in encoded[0][1].items()
                    if key not in metadata and key != "minimax_keyframes"}
    result = []
    for entry, history in zip(positive, histories):
        branch = dict(entry[1])
        for key, value in native_added.items():
            branch.setdefault(key, value)
        branch["minimax_keyframes"] = [*history, guide]
        result.append([entry[0], branch])
    report = dict(schema="t8.branch-guide.v1", branches=len(result),
                  original_anchor_counts=[len(rows) for rows in histories],
                  appended_guides_per_branch=1,
                  resolved_frame_index=guide["resolved_frame_index"],
                  image_encoded="latent" in guide,
                  audio_encoded="audio_latent" in guide,
                  native_guide_calls=1, video_vae_calls=int("latent" in guide),
                  audio_vae_calls=int("audio_latent" in guide), core_monkeypatched=False,
                  native_added_metadata_keys=sorted(native_added),
                  existing_references_and_schedules_preserved=True,
                  quality_verified=False)
    return result, json.dumps(report, ensure_ascii=False, allow_nan=False)


class MiniMaxH3BranchGuideEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3BranchGuideEXPT8",
            display_name="H3 Branch-safe Guide / 分支安全追加引导 (EXP/T8)",
            category="T8/MiniMax H3/Conditioning/Experimental",
            description="Append one native image/audio guide to every branch, preserving "
                        "each branch's own anchors, references and sampling schedule. "
                        "Opt-in; does not replace Core Add Guide or alter old workflows.",
            inputs=[io.Conditioning.Input("positive"), io.Latent.Input("latent"),
                    io.Int.Input("frame_idx", default=0, min=-9999, max=9999),
                    io.Vae.Input("vae", optional=True),
                    io.Vae.Input("audio_vae", optional=True),
                    io.Image.Input("image", optional=True),
                    io.Audio.Input("audio", optional=True)],
            outputs=[io.Conditioning.Output("positive"), io.String.Output("report_json")],
            is_experimental=True)

    @classmethod
    def execute(cls, positive, latent, frame_idx, vae=None, audio_vae=None,
                image=None, audio=None):
        return io.NodeOutput(*append_branch_guide(
            positive, latent, frame_idx, vae=vae, audio_vae=audio_vae,
            image=image, audio=audio))


NODES = [MiniMaxH3BranchGuideEXPT8]
