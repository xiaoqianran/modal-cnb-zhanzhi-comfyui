# H13 sources and boundaries

- AudioFirst idea / original helper:
  https://github.com/sepiablue-ai/ComfyUI-H3-AudioFirst-X2-Stream
  reviewed revision `36c5385bf8e9b86161a75ae5c3d2440cf723552d`, GPL-3.0-only.
  Thank you to sepiablue-ai. T8 implements same-condition projection and a
  read-only three-input audit; its existing SourceAVPrepare performs the lock.
  The main project is GPL-3.0-or-later; this source's GPL-3.0 terms remain applicable.
  No third-party checkpoint or complete extension is bundled.
- Native Wuli conversion / ordinary Hybrid:
  https://huggingface.co/sandpies/Wuli-MiniMax-H3-Turbo-ComfyUI
  revision `9df5eccfa095adcdbffba5ba8cbe4c0c66d15a7e`, ordinary Hybrid asset SHA
  `a852255134e20112d63a23848be122bd0076e37b9ddac09e436d9d61abbba42b`.
  Wuli-art (8-step distillation), sandpies (native conversion/hybrid), MiniMax H3
  base/community weights; MiniMax H3 Community License applies separately from
  adapter GPL. FlashGen by Beidouqixing / Huawei Ascend (Apache-2.0), conversion
  by Kijai; FL-base Ref-AdaLN hybrid method by smhfacct. Respect all source terms.
  fal Realism-People is a separate optional variant, not included or downloaded
  by this recipe. No claim of upstream endorsement or universal quality/speed.
- ComfyUI owns native latent clocks, samplers, VAE and stream-mask math.
  No Torch/Core/CK update is required by these two helpers.

Human review is a separate gate. Resource SHA, schema registration and CPU tests
are not perceptual certification, trained weights, or loaded-MODEL identity.
