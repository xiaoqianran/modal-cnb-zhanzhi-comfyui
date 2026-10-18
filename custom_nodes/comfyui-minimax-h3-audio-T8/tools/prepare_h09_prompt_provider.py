"""Explicit pinned Qwen model preparation; no install, launcher or inference."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from h3_t8.prompt_provider import REVISION, MODEL_REVISION, SCHEMA, PACKAGES, content_sha  # noqa: E402
from h3_t8.freevideo_exp.runtime import digest, write_json_new  # noqa: E402
from prepare_h09_freevideo_int8 import source_tree, fetch_asset, target  # noqa: E402


def record(path):
    path = path.resolve(strict=True)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-root","model-root","python","home","output-config"):
        parser.add_argument("--"+name,type=Path,required=True)
    args = parser.parse_args()
    if args.output_config.exists():
        raise FileExistsError("Use a new prompt config; old runtimes are not overwritten")
    source,model = args.source_root.resolve(),args.model_root.resolve()
    proof = source_tree(source)
    catalog = json.loads((source/"freevideo_engine/prompt_vlm/model.json").read_text(encoding="utf8"))
    if catalog["repo"]!="Qwen/Qwen3-VL-4B-Instruct" or catalog["revision"]!=MODEL_REVISION or len(catalog["files"])!=12:
        raise ValueError("Fixed author prompt model catalog changed")
    model.mkdir(parents=True,exist_ok=True)
    missing = 0
    for row in catalog["files"]:
        path = target(model,row["file"])
        partial = path.with_suffix(path.suffix+".partial")
        present = path.stat().st_size if path.exists() else partial.stat().st_size if partial.exists() else 0
        missing += max(0,row["bytes"]-present)
    if shutil.disk_usage(model).free<missing+8*1024**3:
        raise ValueError("Keep 8GiB free after missing prompt assets; no cleanup performed")
    print(json.dumps(dict(model_revision=MODEL_REVISION,files=12,total_bytes=sum(r["bytes"] for r in catalog["files"]),
                          missing_bytes=missing,inference_started=False)),flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(fetch_asset,model,row,repo=catalog["repo"],revision=MODEL_REVISION) for row in catalog["files"]]
        for job in jobs:
            job.result()
    rows = [record(source/row["file"]) for row in proof["files"]]
    rows.append(record(source/"t8-source-proof.json"))
    rows += [record(target(model,row["file"])) for row in catalog["files"]]
    rows += [record(ROOT/"h3_t8"/name) for name in ("prompt_provider.py","prompt_provider_worker.py","reference_package.py","prepared_identity.py")]
    rows += [record(ROOT/"h3_t8/freevideo_exp"/name) for name in ("runtime.py","supervision.py")]
    rows += [record(args.python)]
    package_script = "from importlib.metadata import version; import json; print(json.dumps({n:version(n) for n in "+repr(PACKAGES)+"}))"
    found = subprocess.run([str(args.python.resolve()),"-I","-B","-c",package_script],capture_output=True,text=True,check=True,timeout=30)
    config = dict(schema=SCHEMA,source_root=str(source),source_revision=REVISION,model_root=str(model),
        model_revision=MODEL_REVISION,python=str(args.python.resolve()),home=str(args.home.resolve()),
        files=rows,inventory_sha256=content_sha(rows),package_versions=json.loads(found.stdout),model_ready=True,
        source="author_FreeToken_portable_ops_plus_transformers_not_full_FreeToken_platform",
        model_downloaded=True,inference_started=False,automatic_accept=False,
        environment_scope="source_and_model_SHA_interpreter_SHA_dependency_versions_not_all_site_packages_bytes")
    args.home.mkdir(parents=True,exist_ok=True)
    write_json_new(args.output_config,config)
    print(json.dumps(dict(config=str(args.output_config),sha256=digest(args.output_config),verified_files=12,
                          sampler_runs=0,proposal_runs=0)),flush=True)


if __name__=="__main__":
    main()
