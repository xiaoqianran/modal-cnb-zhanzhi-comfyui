"""Qualify the actual complete INT8 config and unchanged tiny probe evidence.

No sampler, model weight materialization, new kernel execution or media claim.
Hardware identification uses one short isolated process, released on return.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from h3_t8.freevideo_int8.runtime import load_model, config_for  # noqa: E402
from h3_t8.freevideo_int8.contract import validate_int8_probes  # noqa: E402
from h3_t8.freevideo_exp.probe_identity import validate_probes  # noqa: E402
from h3_t8.freevideo_exp.runtime import digest, write_json_new  # noqa: E402
from bind_freevideo_quality_probes import identify  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config",type=Path)
    parser.add_argument("--receipt",type=Path,required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise FileExistsError("Use a new prepared audit receipt")
    model = load_model(args.config)
    config = config_for(model,full=True)
    current = identify(config,args.config)
    home = Path(config["home"])
    probes = json.loads((home/"kernel-probes.json").read_text(encoding="utf8"))
    validate_int8_probes(probes)
    validate_probes(config,probes,current)
    result = dict(schema="t8.h09.int8-prepared-audit.v1",config_path=model.config_path,
        config_sha256=model.config_sha256,source_inventory_sha256=config["inventory_sha256"],
        verified_inventory_files=len(config["files"]),prepared_profiles=config["prepared_profiles"],
        prepared_task=config["prepared_task"],
        prepared_tasks=config.get("prepared_tasks", [config["prepared_task"]]),
        probe_binding_sha256=digest(home/"kernel-probe-binding.json"),
        actual_compute_identity_unchanged=True,new_GPU_probe_executions=0,
        native_sampler_runs=0,human_quality_accepted=False,speed_verified=False)
    write_json_new(args.receipt,result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
