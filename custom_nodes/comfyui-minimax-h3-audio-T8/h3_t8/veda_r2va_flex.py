"""R2VA spans + independent budgets, with the existing T8 Flex kernel.

Not the upstream INT8 kernel; no inherited speed or INT8 numeric claim.
Shared vendored tiling/selection remain byte-unchanged.
"""
import torch

from . import veda_flex
from .veda_vendor.veda import mask, predictor as predictor_math, tiling


def tile_layout(spec, shape, reference_budget, device, cache):
    spans = []
    if not reference_budget.keeps_all:
        spans = [tiling.TiledSpan(s.start, s.grid, tiling.least_padding_shape(s.grid))
                 for s in spec.references]
    spans.append(tiling.TiledSpan(spec.target.start, spec.target.grid, shape))
    key = (tuple(spans), spec.sequence, torch.device(device))
    result = cache.get(key)
    if result is None:
        result = tiling.build_tile_layout(spans, spec.sequence, spec.sequence, device)
        cache[key] = result
    return result


@torch.no_grad()
def attend(q, k, v, *, layer_index, spec, choice, predictor, generated_budget,
           reference_budget, max_copy_mib, tile_cache, statistics):
    if q.ndim != 3 or q.shape != k.shape or q.shape != v.shape or q.shape[0] != spec.sequence:
        raise ValueError("R2VA Flex requires equal full-sequence [S,H,D] Q/K/V")
    sequence, heads, dim = q.shape
    p = choice.plan
    if (tuple(choice.actual_grid) != spec.target.grid or max_copy_mib < 1
            or not 0 <= layer_index < p.num_layers or len(p.head_shape[layer_index]) != heads):
        raise ValueError("R2VA Flex plan/actual grid/head count mismatch")
    out = q.new_empty(sequence + 1, heads, dim)
    layer = predictor.layers[layer_index]
    staged = next(layer.parameters()).device != q.device
    if staged:
        layer.to(q.device)
    try:
        for group in p.head_groups(layer_index, q.device):
            tiles = tile_layout(spec, group.shape, reference_budget, q.device, tile_cache)
            stats_key = (spec, group.shape, reference_budget)
            statistics[stats_key] = {
                "reference_tiles": tiles.n_ref_tiles, "target_tiles": tiles.n_video_tiles - tiles.n_ref_tiles,
                "global_tiles": tiles.n_global_tiles, "reference_tokens": tiles.ref_tokens,
                "target_tokens": tiles.target_tokens,
                "reference_dense_global": reference_budget.keeps_all,
                "tile_shape": str(group.shape)}
            blocks = mask.column_blocks(tiles, generated_budget, reference_budget)
            chunk_size = min(heads, veda_flex._head_chunks(tiles, q.dtype, dim, max_copy_mib))
            for chunk in group.heads.split(chunk_size):
                qt = tiling.gather_tiles(q, tiles, chunk)
                kt = tiling.gather_tiles(k, tiles, chunk)
                vt = tiling.gather_tiles(v, tiles, chunk)
                # Pool ONLY visual tiles: globals do not participate in top-k.
                fq = predictor_math.pool_tiles(qt, tiles)[:, :tiles.n_video_tiles]
                fk = predictor_math.pool_tiles(kt, tiles)[:, :tiles.n_video_tiles]
                scores = layer(fq, fk, chunk)
                selection = mask.select_video_blocks(scores, tiles, blocks)
                selected = mask.dense_block_mask(selection, tiles)
                real = len(chunk)
                missing = chunk_size - real
                if missing:
                    qt = torch.cat((qt, qt[:, -1:].expand(-1, missing, -1)), 1)
                    kt = torch.cat((kt, kt[:, -1:].expand(-1, missing, -1)), 1)
                    vt = torch.cat((vt, vt[:, -1:].expand(-1, missing, -1)), 1)
                    selected = torch.cat((selected, selected[-1:].expand(missing, -1, -1)), 0)
                result = veda_flex.compiled_flex()(
                    qt.transpose(0, 1)[None], kt.transpose(0, 1)[None], vt.transpose(0, 1)[None],
                    block_mask=veda_flex.flex_block_mask(selected, tiles.valid_count))
                tiling.scatter_tiles_(out, result[0].transpose(0, 1)[:, :real], tiles, chunk)
        return out[:sequence]
    finally:
        if staged:
            layer.to("cpu")
