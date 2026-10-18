# H14 sources and boundaries

Thank you to baslack / Scriptorium for the token-row LoRA idea and prototype:
https://github.com/baslack/scripts_nodes/pull/2 (revision `18dc9a4`).
The upstream license is retained in `H14-Scriptorium-LICENSE.txt`.

T8's separate adapter uses native ComfyUI PackedLayout and plain-LoRA mapping,
checks whole-file coverage, separates generated from reference/conditioning rows,
and observes the native MLP boundary without replacing Core's fused operator.
It adds transactional cleanup, owner delegation and actual-call reporting.
No endorsement, complete modality isolation, universal compatibility or speedup
is implied. Native ComfyUI parsing, sampling, quantization and clocks remain its
own implementation and license.

The local test uses an existing five-view adapter, not a new voice model.
Weights and their license are separate from this extension; no checkpoint,
reference image, video, audio, binary runtime or private review data is bundled.
Wuli-art / sandpies provide the existing Wuli8 native base conversion. Follow
their terms and the MiniMax H3 Community License when acquiring those assets.

Flow target-band is research-only: no Flow numerical implementation or new
continuation default is included. Existing accepted continuation is preserved.
