"""Optional pinned FreeToken-portable proposal, never an automatic prompt rewrite.

One owned subprocess, no engine imports or persistent weights in ComfyUI.
Explicit protected literals are a mechanical guard, not semantic fact checking.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid

from .reference_package import canonical, tensor_record
from .freevideo_exp.runtime import digest, verify_files, write_json_new

REVISION = "ebc94ecdeec3cbfe74040fe69a5116a62bf01dcd"
MODEL_REVISION = "ebb281ec70b05090aa6165b016eac8ec08e71b17"
SCHEMA = "t8.h09.prompt-provider.v1"
PACKAGES = ("torch", "transformers", "accelerate", "Pillow", "psutil")


def content_sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class PromptRequest:
    json: str
    sha256: str
    images: object

    def verify(self):
        value = json.loads(self.json)
        if content_sha(value) != self.sha256 or value.get("schema") != "t8.h09.prompt-request.v1":
            raise ValueError("Prompt request content changed")
        actual = tensor_record(self.images) if self.images is not None else None
        if actual != value["images_record"]:
            raise ValueError("Prompt reference pixels changed; prepare a fresh proposal")
        return value


def make_request(text, seconds, roles, protected, images=None):
    if (not isinstance(text,str) or not text.strip() or len(text)>12000
            or type(seconds) not in (int,float) or not math.isfinite(seconds) or not 1<=seconds<=60):
        raise ValueError("Use an explicit nonempty draft <=12000 characters and 1–60 seconds")
    if (not isinstance(roles,list) or len(roles)>8 or any(role not in ("first","last","reference") for role in roles)
            or roles.count("first")>1 or roles.count("last")>1
            or "reference" in roles and any(role in roles for role in ("first","last"))):
        raise ValueError("Use <=8 explicit image roles; reference images cannot mix with first/last anchors")
    if (not isinstance(protected,list) or len(protected)>64
            or any(not isinstance(line,str) or not line.strip() or len(line)>4096 or line not in text for line in protected)
            or len(set(protected))!=len(protected)):
        raise ValueError("Protected dialogue/lyrics/writing must be distinct literal substrings of the original draft")
    if images is None:
        if roles:
            raise ValueError("Declared image roles require actual IMAGE pixels")
        record = None
    else:
        import torch
        if (type(images) is not torch.Tensor or images.device.type!="cpu" or images.dtype!=torch.float32
                or images.ndim!=4 or images.shape[-1]!=3 or images.shape[0]!=len(roles)
                or not roles or min(images.shape[1:3])<1 or images.shape[1]*images.shape[2]>50_000_000
                or images.numel()*images.element_size()>256*1024**2
                or not torch.isfinite(images).all() or images.min()<0 or images.max()>1):
            raise ValueError("Use bounded CPU float32 RGB IMAGE batch in [0,1], one image per role")
        images = images.detach().clone()
        record = tensor_record(images)
    # The native writer numbers first before last; preserve reference order.
    order = sorted(range(len(roles)),key=lambda i: roles[i]!="first") if "reference" not in roles else list(range(len(roles)))
    value = dict(schema="t8.h09.prompt-request.v1",text=text,seconds=float(seconds),
                 roles=roles,media_order=order,protected_literals=protected,images_record=record)
    return PromptRequest(canonical(value),content_sha(value),images)


def protect_literals(text, value):
    import re
    if not isinstance(text,str) or not 100<=len(text)<=20000:
        raise ValueError("Proposal output must be a bounded complete prompt")
    for literal in value["protected_literals"]:
        if text.count(literal)!=value["text"].count(literal):
            raise ValueError("Proposal changed or repeated a protected literal; original remains selected")
    # Only explicitly declared speech is allowed. This does not detect every
    # invented visual fact or all possible untagged speech: those need review.
    speech = re.findall(r"<d>(.*?)</d>",text,flags=re.DOTALL)
    for line in speech:
        plain = re.sub(r"^\[[^\]\n]{1,64}\]\s*","",line).strip()
        if plain not in value["protected_literals"]:
            raise ValueError("Proposal introduced undeclared dialogue; declare exact speech or keep the original")
    return text


@dataclass(frozen=True)
class PromptProposal:
    json: str
    sha256: str

    def verify(self, request):
        value = json.loads(self.json)
        original = request.verify()
        if (value.get("schema")!="t8.h09.prompt-proposal.v1" or content_sha(value)!=self.sha256
                or value.get("request_sha256")!=request.sha256):
            raise ValueError("Proposal is modified or stale for the actual draft/media")
        protect_literals(value["text"],original)
        return value


def choose(request, proposal, confirmed=False):
    original = request.verify()
    if type(confirmed) is not bool:
        raise ValueError("Use an explicit adoption boolean")
    if not confirmed:
        return original["text"],dict(adopted=False,original_retained=True,automatic_accept=False)
    if type(proposal) is not PromptProposal:
        raise ValueError("Explicit adoption needs an actual proposal")
    value = proposal.verify(request)
    return value["text"],dict(adopted=True,original_retained=True,automatic_accept=False,
                               request_sha256=request.sha256,proposal_sha256=proposal.sha256)


def load_config(path, expected_sha=None):
    path = Path(path).resolve(strict=True)
    before = digest(path)
    if expected_sha is not None and before!=expected_sha:
        raise ValueError("Prompt provider configuration changed")
    value = json.loads(path.read_text(encoding="utf8"))
    if (value.get("schema")!=SCHEMA or value.get("source_revision")!=REVISION
            or value.get("model_revision")!=MODEL_REVISION or value.get("model_ready") is not True
            or content_sha(value.get("files"))!=value.get("inventory_sha256")):
        raise ValueError("Use the independently prepared, pinned prompt provider configuration")
    verify_files(value["files"])
    paths = {str(Path(row["path"]).resolve()):row for row in value["files"]}
    if len(paths)!=len(value["files"]):
        raise ValueError("Prompt provider inventory contains duplicate physical paths")
    for name in ("source_root","model_root","python","home"):
        if not isinstance(value.get(name),str) or not Path(value[name]).is_absolute():
            raise ValueError("Prompt provider requires an explicit absolute "+name)
    source = Path(value["source_root"])
    proof_path = source/"t8-source-proof.json"
    if str(proof_path.resolve()) not in paths:
        raise ValueError("Prompt source proof must be bound, not an unverified source label")
    proof = json.loads(proof_path.read_text(encoding="utf8"))
    if proof.get("schema")!="t8.h09.freevideo-source.v1" or proof.get("commit")!=REVISION:
        raise ValueError("Prompt source proof differs from its fixed author family")
    for row in proof["files"]:
        actual = paths.get(str((source/row["file"]).resolve()),{})
        if actual.get("bytes")!=row["bytes"] or actual.get("sha256")!=row["sha256"]:
            raise ValueError("Prompt inventory omits/changes an actual pinned source member")
    catalog = json.loads((source/"freevideo_engine/prompt_vlm/model.json").read_text(encoding="utf8"))
    if catalog.get("repo")!="Qwen/Qwen3-VL-4B-Instruct" or catalog.get("revision")!=MODEL_REVISION or len(catalog.get("files",[]))!=12:
        raise ValueError("Prompt model catalog differs from its fixed identity")
    for row in catalog["files"]:
        actual = paths.get(str((Path(value["model_root"])/row["file"]).resolve()),{})
        if actual.get("bytes")!=row["bytes"] or actual.get("sha256")!=row["sha256"]:
            raise ValueError("Prompt inventory must contain all 12 original model/tokenizer files")
    for bound_path in (Path(__file__),Path(__file__).with_name("prompt_provider_worker.py"),Path(value["python"])):
        if str(bound_path.resolve()) not in paths:
            raise ValueError("Prompt provider implementation/interpreter is missing from the inventory")
    if set(value.get("package_versions",{}))!=set(PACKAGES):
        raise ValueError("Prompt provider requires actual isolated dependency versions")
    if digest(path)!=before:
        raise ValueError("Prompt provider configuration changed during verification")
    return value, before


def rewrite(request, config_path, *, interrupt=None, timeout_seconds=1800):
    from .freevideo_exp.supervision import owned_process
    if type(request) is not PromptRequest:
        raise ValueError("Use an actual prompt request, not arbitrary JSON")
    original = request.verify()
    config, config_sha = load_config(config_path)
    run = Path(config["home"])/"proposals"/uuid.uuid4().hex
    run.mkdir(parents=True,exist_ok=False)
    media = []
    if request.images is not None:
        from PIL import Image
        import torch
        for number,index in enumerate(original["media_order"]):
            path = run/f"image-{number+1}.png"
            rgb = request.images[index].mul(255).round().to(dtype=torch.uint8).numpy()
            Image.fromarray(rgb).save(path,format="PNG")
            media.append(dict(path=str(path),role=original["roles"][index],sha256=digest(path)))
    job = dict(config_path=str(Path(config_path).resolve()),config_sha256=config_sha,
               request=json.loads(request.json),request_sha256=request.sha256,media=media)
    write_json_new(run/"request.json",job)
    env = dict(os.environ)
    for key in ("PYTHONPATH","PYTHONHOME","PYTHONSTARTUP","FREEVIDEO_RUNTIME_LOCK_FD","FREEVIDEO_RUNTIME_LOCK_HANDLE"):
        env.pop(key,None)
    env.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_HUB_DISABLE_TELEMETRY="1",
               FREEVIDEO_HOME=config["home"],TOKENIZERS_PARALLELISM="false")
    command = [config["python"],"-I","-B","-X","utf8",str(Path(__file__).with_name("prompt_provider_worker.py")),str(run)]
    started = time.monotonic()
    with (run/"worker.log").open("x",encoding="utf8") as log, owned_process(command,env,run,log) as process:
        while process.poll() is None:
            if interrupt:
                interrupt()
            if time.monotonic()-started>timeout_seconds:
                raise TimeoutError("Owned proposal timed out; only its process tree is released")
            time.sleep(.2)
        if process.returncode:
            raise RuntimeError(f"Prompt proposal failed; original retained. Local private diagnostics: {run/'worker.log'}")
    load_config(config_path,config_sha)
    request.verify()
    for row in media:
        if digest(row["path"])!=row["sha256"]:
            raise ValueError("Proposal source PNG changed during inference")
    result = json.loads((run/"proposal.json").read_text(encoding="utf8"))
    if result.get("request_sha256")!=request.sha256 or result.get("config_sha256")!=config_sha:
        raise ValueError("Worker proposal identity differs from its actual request")
    result.update(worker_log_sha256=digest(run/"worker.log"),worker_exited=True,persistent_model=False,
                  automatic_accept=False,semantic_facts_verified=False,run_dir=str(run))
    proposal = PromptProposal(canonical(result),content_sha(result))
    proposal.verify(request)
    return proposal,dict(request_sha256=request.sha256,proposal_sha256=proposal.sha256,
        run_dir=str(run),diagnostics=result["diagnostics"],automatic_accept=False,
        original_unchanged=True,semantic_facts_verified=False,native_sampler_runs=0)
