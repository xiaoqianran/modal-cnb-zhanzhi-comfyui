"""Explicit new Director draft from a JSON production recipe; never queues or adopts."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from h3_t8.production_recipe import prepare_project  # noqa: E402
from h3_t8.freevideo_exp.runtime import write_json_new  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Use a new output directory; original projects are never overwritten")
    project, report = prepare_project(json.loads(args.project.read_text(encoding="utf8")),
                                     json.loads(args.recipe.read_text(encoding="utf8")))
    args.output_dir.mkdir(parents=True)
    write_json_new(args.output_dir / "project.json", project)
    write_json_new(args.output_dir / "report.json", report)
    print(json.dumps(dict(project=str(args.output_dir / "project.json"), automatic_accept=False)))


if __name__ == "__main__":
    main()
