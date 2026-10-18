"""One new additive-bias cuDNN probe bound to the independent INT8 producer.

Uses the exact shared effect math, but a fresh owned result and current INT8
compute identity. Never accepts/copies FP8 result files or queues a model job.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from h3_t8.freevideo_int8.runtime import load_model, config_for  # noqa: E402
from h3_t8.freevideo_exp.runtime import verify_files  # noqa: E402
from h3_t8.freevideo_exp.supervision import owned_process  # noqa: E402
from h3_t8.freevideo_exp.masked_probe import validate  # noqa: E402
from bind_freevideo_quality_probes import identify  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    path = args.config.resolve(strict=True)
    config = config_for(load_model(path))
    source = [r for r in config["files"] if r["kind"] != "weight"]
    verify_files(source)
    identity = identify(config, path)
    root = Path(config["home"]) / "masked-probe-v1"
    root.mkdir(exist_ok=False)
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "FREEVIDEO_RUNTIME_LOCK_FD", "FREEVIDEO_RUNTIME_LOCK_HANDLE"):
        env.pop(key, None)
    env.update(FREEVIDEO_HOME=config["home"], FREEVIDEO_VDN_ROOT=config["vdn_root"],
               TRITON_CACHE_DIR=str(Path(config["home"]) / "triton"),
               TORCHINDUCTOR_CACHE_DIR=str(Path(config["home"]) / "inductor"))
    code = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('freevideo_exp.masked_probe',run_name='__main__')"
    command = [config["python"], "-I", "-B", "-X", "utf8", "-c", code,
               str(ROOT / "h3_t8"), str(path), str(root)]
    with (root / "log.txt").open("x", encoding="utf8") as log:
        with owned_process(command, env, root, log) as process:
            if process.wait(timeout=120):
                raise RuntimeError("New INT8 masked probe failed; preserved " + str(root))
    verify_files(source)
    if identify(config, path) != identity:
        raise ValueError("INT8 compute identity changed during masked probe")
    result = validate(config, identity)
    print(json.dumps(dict(status="pass", producer=config["schema"], actual_GPU_probe_executions=1,
        native_sampler_runs=0, human_quality_accepted=False, result=result), ensure_ascii=False))


if __name__ == "__main__":
    main()
