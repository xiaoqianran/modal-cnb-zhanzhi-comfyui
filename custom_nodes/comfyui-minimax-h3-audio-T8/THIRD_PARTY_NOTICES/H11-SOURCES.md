# H11 source acknowledgements

- **Spark-H3**, zechengtang and contributors: https://github.com/zechengtang/Spark-H3,
  commit `1bb4cdb22648314901e4cbe82c3b414aa1f2e769`, ComfyUI v0.1.2, Apache-2.0.
  The explicit preparation tool retains the official LICENSE with separately prepared
  backend/reblock source. T8 does not vendor/register the whole upstream node pack.
  The forked comfy-kitchen wheel and its dependency notices remain separate.
- **Wuli MiniMax-H3 Turbo**, Wuli-art, and **native ComfyUI conversion**, sandpies:
  https://huggingface.co/Wuli-art/MiniMax-H3-Turbo and
  https://huggingface.co/sandpies/Wuli-MiniMax-H3-Turbo-ComfyUI.
  Native artifact revision `82f86823abcd6288370d73bc19a98e636282ad28`.
  T8 calls existing ComfyUI clocks/LoRA/head-bank APIs; no upstream conversion code is copied.
  Derived model weights carry the MiniMax H3 Community License, not the adapter code license.
- **FreeVideo / FreeToken**, FlashML-org: https://github.com/FlashML-org/FreeVideo.
  Existing producer-specific pins and notices remain intact. H11 adds bounded observation
  and scene-ticket metadata, not the updater, idle compiler or a replacement engine.
- **MiniMax H3 Semantic Bridge Trainer T8**, T8mars and contributors:
  https://github.com/T8mars/MinimaxH3_Semantic_Bridge_Trainer-T8,
  guidance schema from `c9844b46e0e202c6ec15754983286038c020043b`, MIT.
  Reading guidance does not confer training/video-quality calibration; weight licenses remain separate.
- **80s Horror LoRA**, Sam Wasserman / wassermanproductions:
  https://github.com/wassermanproductions/wasserman-80s-horror-lora/releases/tag/v1.0.0.
  Project code/docs Apache-2.0; the model derivative is distributed under the
  MiniMax H3 Community License. T8 supplies a resource recipe, no bundled weights.

Acknowledgement and metadata are not independent verification of every model,
hardware, adapter combination or licensing use case.
