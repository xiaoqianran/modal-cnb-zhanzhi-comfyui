# v1.98.2 — Topaz decoder and multi-NVIDIA monitor fixes

- Resolve H.264/HEVC explicitly inside the owned worker: prefer listed software decoders, otherwise CUVID. Do not open an implicit QSV decoder on NVIDIA-only machines.
- Apply the chosen input decoder to video/audio probes, enhancement/interpolation, decoded PCM and final strict decode. Decoder crashes, corrupt media and timeouts are not fallback signals.
- Use complete decoded frame formats for CUVID Main10; retain pixel-format, CFR, packet/PCM, AV timing, cancellation and publication checks.
- Use Topaz-specific selected-index NVIDIA telemetry instead of the DLSS-only single-card reader. Preserve the DLSS restriction and all old nodes/defaults/workflows.
- 117 targeted CPU tests pass. The installed official Topaz binaries strictly decoded existing 72-frame H.264 (software and CUVID) and FFV1 fixtures; H.264 audio packets/PCM and timeline match. No new enhancement quality or actual two-card hardware qualification is claimed.
- Thanks to wonkwq for [#30's diagnosis and patch](https://github.com/T8mars/comfyui-minimax-h3-audio-T8/issues/30), cabenn for [#23](https://github.com/T8mars/comfyui-minimax-h3-audio-T8/issues/23), and the other reporters. See [usage and limits](TOPAZ_EXP.md).
- PR #29 is changes-requested, not merged: its duration-drift heuristic can rewrite genuine VFR. No implicit source-timing repair is introduced by this release.

GitHub publication is distinct from Comfy Registry activation. Pending moderation does not mean this version is installable through Manager.
