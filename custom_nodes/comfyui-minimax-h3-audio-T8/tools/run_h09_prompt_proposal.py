"""One local pending text proposal; never auto-adopts or queues H3."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from h3_t8.prompt_provider import make_request, rewrite  # noqa: E402
from h3_t8.freevideo_exp.runtime import write_json_new  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--request",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Use a new output directory; original prompt is never overwritten")
    value = json.loads(args.request.read_text(encoding="utf8"))
    if set(value)!={"text","seconds","protected_literals"}:
        raise ValueError("This minimal CLI takes an explicit text-only request; images use the optional canvas request node")
    request = make_request(value["text"],value["seconds"],[],value["protected_literals"])
    proposal,report = rewrite(request,args.config)
    args.output_dir.mkdir(parents=True,exist_ok=False)
    write_json_new(args.output_dir/"original.json",value)
    write_json_new(args.output_dir/"proposal.json",proposal.verify(request))
    write_json_new(args.output_dir/"report.json",report)
    print(json.dumps(dict(output_dir=str(args.output_dir),automatic_accept=False,native_sampler_runs=0)))


if __name__=="__main__":
    main()
