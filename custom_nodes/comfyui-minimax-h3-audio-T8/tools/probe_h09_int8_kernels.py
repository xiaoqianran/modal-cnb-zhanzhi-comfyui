"""Exactly two bounded owned probes: actual INT8 ConvRot and cuDNN attention.

Can run from SOURCE-ONLY input while model assets download. Such input never
becomes a loadable model config or a sampler/media/quality certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from h3_t8.freevideo_exp.runtime import canonical, digest, verify_files, write_json_new  # noqa: E402
from h3_t8.freevideo_exp.supervision import owned_process  # noqa: E402
from h3_t8.freevideo_exp.probe_identity import bind  # noqa: E402
from h3_t8.freevideo_int8.contract import REVISION, MODEL_REVISION, validate_int8_probes  # noqa: E402
from bind_freevideo_quality_probes import identify  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    path = args.config.resolve(strict=True)
    config = json.loads(path.read_text(encoding="utf8"))
    if (config.get("freevideo_revision") != REVISION or config.get("model_revision") != MODEL_REVISION
            or config.get("inventory_sha256") != hashlib.sha256(canonical(config["files"]).encode()).hexdigest()):
        raise ValueError("Need fixed original INT8 source and intact source inventory")
    source_rows = [row for row in config["files"] if row["kind"] != "weight"]
    verify_files(source_rows)
    home = Path(config["home"]).resolve(strict=True)
    for name in ("probe-linear.log", "probe-cudnn.log", "kernel-probes.json", "kernel-probe-binding.json",
                 "probe-linear-owner", "probe-cudnn-owner"):
        if (home / name).exists():
            raise FileExistsError("Inspect existing probe evidence; do not rerun or overwrite: " + str(home / name))
    current = identify(config, path)
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "FREEVIDEO_RUNTIME_LOCK_FD", "FREEVIDEO_RUNTIME_LOCK_HANDLE"):
        env.pop(key, None)
    env.update(FREEVIDEO_HOME=str(home), FREEVIDEO_VDN_ROOT=config["vdn_root"],
               TRITON_CACHE_DIR=str(home / "triton"), TORCHINDUCTOR_CACHE_DIR=str(home / "inductor"),
               TORCHINDUCTOR_COMPILE_THREADS="1")
    results = {}
    for name, backend in (("linear", "linear-int8"), ("cudnn", "cudnn")):
        run = home / ("probe-" + name + "-owner")
        run.mkdir(exist_ok=False)
        log_path = home / ("probe-" + name + ".log")
        command = [config["python"], "-I", "-B", "-X", "utf8",
                   str(ROOT / "h3_t8/freevideo_quality/probe_worker.py"), str(run), config["source_root"], backend]
        started = time.monotonic()
        with log_path.open("x", encoding="utf8") as log, owned_process(command, env, run, log) as process:
            while process.poll() is None:
                if time.monotonic() - started > 180:
                    raise TimeoutError("Bounded INT8 probe exceeded 180s; owned tree cleanup and failed evidence retained")
                time.sleep(.2)
            if process.returncode:
                raise RuntimeError("INT8 probe failed; inspect " + str(log_path))
        rows = []
        for line in log_path.read_text(encoding="utf8").splitlines():
            if line.startswith('{"backend":'):
                rows.append(json.loads(line))
        if not rows or rows[-1].get("backend") != backend:
            raise ValueError("Actual probe log has no matching terminal result")
        result = rows[-1]
        limit = 1e-4 if name == "linear" else .006
        if (result.get("status") != "complete" or result.get("finite") is not True
                or result.get("relative_rmse_limit") != limit
                or not 0 <= result.get("relative_rmse", float("inf")) <= limit):
            raise ValueError("Actual INT8 probe failed its independent numerical comparison")
        results[name] = dict(result, log_sha256=digest(log_path))
        print(canonical(dict(probe=name, backend=backend, result=results[name])), flush=True)
    verify_files(source_rows)
    if identify(config, path) != current:
        raise ValueError("Actual compute environment changed during INT8 probes")
    validate_int8_probes(results)
    write_json_new(home / "kernel-probes.json", results)
    bind(config, current, results, origin=dict(kind="two-new-bounded-INT8-probes", actual_GPU_probe_executions=2,
        config_sha256=digest(path), native_sampler_runs=0, human_quality_accepted=False))
    print(canonical(dict(status="pass", actual_GPU_probe_executions=2, native_sampler_runs=0,
                         human_quality_accepted=False, home=str(home))), flush=True)


if __name__ == "__main__":
    main()
