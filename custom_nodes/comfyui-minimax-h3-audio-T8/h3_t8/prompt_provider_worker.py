"""Owned offline prompt proposal; no ComfyUI import or persistent model."""
import contextlib
import io
import json
from pathlib import Path
import sys
import time


def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    started = time.monotonic()
    while not (root/"launch-gate").is_file():
        if time.monotonic()-started>30:
            raise RuntimeError("Proposal worker was not assigned to its supervisor")
        time.sleep(.05)
    sys.path.insert(0,str(Path(__file__).parents[1]))
    from h3_t8.prompt_provider import load_config, content_sha, protect_literals, PACKAGES
    from h3_t8.freevideo_exp.runtime import digest, write_json_new
    from importlib.metadata import version
    job = json.loads((root/"request.json").read_text(encoding="utf8"))
    config,_ = load_config(job["config_path"],job["config_sha256"])
    if {name:version(name) for name in PACKAGES}!=config["package_versions"]:
        raise ValueError("Isolated prompt dependencies changed; prepare a new configuration")
    original = job["request"]
    if content_sha(original)!=job["request_sha256"]:
        raise ValueError("Prompt request content changed")
    media = []
    for row in job["media"]:
        path = Path(row["path"])
        if path.is_symlink() or path.resolve(strict=True).parent!=root or digest(path)!=row["sha256"]:
            raise ValueError("Prompt source media changed")
        media.append(dict(file=str(path),role=row["role"]))
    sys.path.insert(0,config["source_root"])
    from freevideo_engine.prompt_vlm.rules import request, validate_output
    from freevideo_engine.prompt_vlm.worker import run
    value = request(dict(text=original["text"],seconds=original["seconds"],media=media))
    value["media"] = [dict(path=row["file"],role=row["role"]) for row in value["media"]]
    # Upstream output includes private prompts; keep it ONLY in this local run.
    captured = io.StringIO()
    class PrivateTee:
        def write(self,text):
            captured.write(text)
            return sys.__stdout__.write(text)
        def flush(self):
            sys.__stdout__.flush()
    with contextlib.redirect_stdout(PrivateTee()):
        run(Path(config["model_root"]),value)
    output = captured.getvalue()
    rows = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    complete = [row for row in rows if row.get("phase")=="complete"]
    if len(complete)!=1:
        raise ValueError("Proposal needs exactly one completed author result")
    text = protect_literals(validate_output(complete[0]["text"],value),original)
    load_config(job["config_path"],job["config_sha256"])
    write_json_new(root/"proposal.json",dict(schema="t8.h09.prompt-proposal.v1",text=text,
        request_sha256=job["request_sha256"],config_sha256=job["config_sha256"],
        source_revision=config["source_revision"],model_revision=config["model_revision"],
        diagnostics=complete[0]["diagnostics"]))


if __name__=="__main__":
    main()
