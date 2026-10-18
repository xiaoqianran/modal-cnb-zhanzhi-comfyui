"""Validated native reference spans and explicit non-exact plan selection.

Selection/layout semantics follow Veda-on-ComfyUI 8d7ac153 (MIT).
No resize, clock rewrite, or modification to legacy exact-plan selection.
"""
from dataclasses import dataclass
import math

import torch


@dataclass(frozen=True)
class Span:
    start: int
    grid: tuple


@dataclass(frozen=True)
class Layout:
    sequence: int
    target: Span
    references: tuple
    skipped: tuple


def segment_grid(positions):
    """Recover and verify a Cartesian row-major grid, retaining original time."""
    if positions.ndim != 2 or positions.shape[1] != 3 or not len(positions):
        raise ValueError("empty_or_invalid_position_grid")
    pos = positions.detach().cpu()
    if not bool(torch.isfinite(pos).all()):
        raise ValueError("nonfinite_position_grid")
    axes = [torch.unique(pos[:, i], sorted=True) for i in range(3)]
    grid = tuple(len(a) for a in axes)
    if math.prod(grid) != len(pos):
        raise ValueError("non_cartesian_position_grid")
    expected = torch.stack(torch.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)
    if not torch.equal(pos, expected):
        raise ValueError("non_row_major_position_grid")
    return grid


def describe(layout, sequence):
    if (getattr(layout, "seq_len", None) != sequence
            or len(getattr(layout, "signature", ())) != 5):
        raise RuntimeError("R2VA Veda requires the native H3 PackedLayout")
    positions = getattr(layout, "position_ids", None)
    segments = getattr(layout, "segments", None)
    if not isinstance(positions, torch.Tensor) or positions.shape != (sequence, 3) or not segments:
        raise RuntimeError("R2VA native layout lacks real position_ids/segments")
    cursor = 0
    video = []
    refs, skipped = [], []
    for start, stop, kind in segments:
        if (type(start) is not int or type(stop) is not int or start != cursor
                or not start <= stop <= sequence):
            raise RuntimeError("R2VA packed segments overlap or leave gaps")
        cursor = stop
        if kind == "video":
            video.append((start, stop))
        elif kind in ("cond", "ref_img"):
            try:
                refs.append(Span(start, segment_grid(positions[start:stop])))
            except ValueError as error:
                skipped.append((start, stop, kind, str(error)))
        # text, VLM and ALL audio remain global in both directions.
    _, frames, latent_h, latent_w, audio_t = layout.signature
    if (any(type(x) is not int or x < 1 for x in (frames, latent_h, latent_w, audio_t))
            or latent_h % 2 or latent_w % 2 or cursor != sequence or len(video) != 1
            or segments[-1][2] != "video"):
        raise RuntimeError("R2VA packed target geometry is invalid")
    start, stop = video[0]
    grid = (frames, latent_h // 2, latent_w // 2)
    if stop != sequence or stop - start != math.prod(grid) or segment_grid(positions[start:stop]) != grid:
        raise RuntimeError("R2VA target grid differs from its original position_ids")
    return Layout(sequence, Span(start, grid), tuple(refs), tuple(skipped))


@dataclass(frozen=True)
class PlanChoice:
    plan: object
    actual_grid: tuple
    exact: bool

    def report(self):
        return {"plan": self.plan.geometry, "plan_grid": list(self.plan.grid),
                "actual_grid": list(self.actual_grid), "exact": self.exact,
                "reason": "exact_embedded_plan" if self.exact else "nearest_plan_experimental_not_trained_size"}


def select_plan(table, grid, mode):
    if mode not in ("strict_exact", "nearest_exp"):
        raise ValueError("Choose strict_exact or explicit nearest_exp plan mode")
    candidates = list(table.plans.values())
    exact = [p for p in candidates if tuple(p.grid) == tuple(grid)]
    if len(exact) == 1:
        return PlanChoice(exact[0], tuple(grid), True)
    if mode == "strict_exact":
        raise ValueError(f"R2VA predictor has no unique exact plan for {grid}; choose nearest_exp explicitly or remove Apply")
    if not candidates or len(exact) > 1:
        raise ValueError("Empty or ambiguous R2VA tile plan table")
    candidates += [p.transposed() for p in candidates]
    aspect = math.log(grid[2] / grid[1])
    def cost(p):
        return (round(abs(math.log(p.grid[2] / p.grid[1]) - aspect), 3),
                abs(p.grid[0] - grid[0]), sum(s.num_tiles(grid) for s in p.shapes))
    return PlanChoice(min(candidates, key=cost), tuple(grid), False)
