"""Real CPU Prepare pixel parity, not a GPU/semantic generation claim."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest
import torch

from h3_audio_t8_pkg.visual_marker import DEFAULT_MARKERS, prepare_markers


@pytest.mark.parametrize("mode", ["render_rectangles", "provided_marked"])
@pytest.mark.parametrize("line_width", [1, 3, 32])
def test_browser_actual_preview_matches_cpu_prepare(mode, line_width):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for browser-pixel parity")
    root = Path(__file__).resolve().parents[1]
    width, height = 73, 41
    pixels = torch.arange(width * height * 3).remainder(256).to(torch.uint8).reshape(1, height, width, 3)
    source = pixels.float() / 255
    marked, _, _ = prepare_markers(source, DEFAULT_MARKERS, mode=mode, line_width=line_width)
    rgba = torch.cat([pixels[0], torch.full((height, width, 1), 255, dtype=torch.uint8)], dim=-1)
    payload = {"source": {"width": width, "height": height, "data": rgba.flatten().tolist()},
               "spec": json.loads(DEFAULT_MARKERS), "mode": mode, "line_width": line_width}
    script = """
import {renderMarkedRGBA} from './web/visual_marker_authoring.mjs';
let input='';for await(const part of process.stdin)input+=part;
const p=JSON.parse(input),out=renderMarkedRGBA(p.source,p.spec,p.mode,p.line_width);
process.stdout.write(JSON.stringify([...out.data]));
"""
    result = subprocess.run([node, "--input-type=module", "-e", script], cwd=root,
                            input=json.dumps(payload), text=True, capture_output=True, check=True)
    actual = torch.tensor(json.loads(result.stdout), dtype=torch.uint8).reshape(height, width, 4)[..., :3]
    expected = (marked[0] * 255).round().to(torch.uint8)
    assert torch.equal(actual, expected)
    assert torch.equal((source * 255).round().to(torch.uint8), pixels)
