# Example workflows

## `H3+selflift-avatar-fixed.json`

This workflow demonstrates `SelfLiftAvatarH3Sampler` with the full-sequence
global-context path:

```text
highres_tiling          = true
highres_tiling_mode     = global_stream
highres_token_chunk     = 4096
highres_weight_cache_gb = 4
```

It also includes `Model Attention Backend`, `MiniMax Low VRAM Attention`,
`MiniMax Chunk Feed Forward`, and `Block Sparse Attention` nodes used by the
maintainer's H3 setup.

### Before running

- Install the custom nodes required by the node types in the workflow.
- Download the model files listed in the workflow's Markdown notes. Model
  weights are not included in this repository.
- Replace the local reference image in the `LoadImage` node.
- Restart the ComfyUI backend and hard-refresh the browser after updating this
  plugin.

### Notes

- `global_stream` needs native SLA/sol-attn on every H3 block for the fastest
  memory-saving path. Without it, the sampler logs a fallback and uses the
  full-sequence global path.
- If TST or another attention override is active, the sampler preserves it and
  falls back to full-sequence dense attention with chunked MLP.
- A ComfyUI `Model Attention Backend` selector is removed only for the
  full-sequence fallback; the fallback uses default PyTorch attention to avoid
  long-sequence backend instability.
- `spatial` requires `video mask = 1` everywhere and `audio mask = 0`
  everywhere. Global modes support arbitrary full-sequence video/audio masks.
- The workflow uses a `global_stream` configuration, but the actual path is
  shown in the node status panel and the console. Do not judge the result from
  the first high-resolution preview alone; let all high-resolution steps finish.

## Credits

Special thanks to [Fish4AI](https://github.com/Fish4AI), author of
[comfyui-SelfLift-Fish](https://github.com/Fish4AI/comfyui-SelfLift-Fish).
The full-sequence global-context implementation used by this workflow is
adapted from that project and integrated with selflift-Avatar's masks and node
wiring. Thanks also to facok for the original comfyui-SelfLift project.
