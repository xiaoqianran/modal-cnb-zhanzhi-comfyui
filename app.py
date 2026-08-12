"""Modal app: zhanzhi ComfyUI, without copying CNB's workspace runtime.

CNB mapping (see README):
  .cnb.yml image + L40 + /models volume  ->  Image + gpu + Volume
  welcome.sh                             ->  scripts/bootstrap.sh
  初始化下载                             ->  scripts/prefetch.py (CPU job)
  start_ComfyUI.sh                       ->  scripts/start_comfyui.sh
  hook_cnb_xu.py                         ->  patches/hook_cnb_xu.py
  git_push / vscode / venv312            ->  not used
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import modal

from env_tokens import read_dotenv, token_secret_dict

REPO_ROOT = Path(__file__).resolve().parent
APP_NAME = os.environ.get("MODAL_APP_NAME", "zhanzhi-comfyui")
GPU = os.environ.get("MODAL_GPU", "L40S")
COMFY_PORT = int(os.environ.get("COMFY_PORT", "8188"))
ZHANZHI_ROOT = "/opt/zhanzhi"
MODELS_ROOT = "/models"
DATA_ROOT = "/workspace/data"
MINUTES = 60

app = modal.App(APP_NAME)

models_vol = modal.Volume.from_name(
    os.environ.get("MODAL_MODELS_VOLUME", "zhanzhi-comfy-models"),
    create_if_missing=True,
)
data_vol = modal.Volume.from_name(
    os.environ.get("MODAL_DATA_VOLUME", "zhanzhi-comfy-data"),
    create_if_missing=True,
)


def _optional_secrets() -> list[modal.Secret]:
    """Turn local HF / Civitai / GitHub tokens into a Modal Secret.

    Reads ``HF_TOKEN`` / ``CIVITAI_TOKEN`` / ``GITHUB_TOKEN`` (and aliases)
    from the process environment and from a gitignored ``.env``. Other ``.env``
    keys are not uploaded. ``from_dict`` must run locally (``modal serve`` /
    ``deploy``), not inside a container.
    """
    if not modal.is_local():
        return []
    dotenv = read_dotenv(REPO_ROOT / ".env")
    payload = token_secret_dict(os.environ, dotenv)
    if not payload:
        return []
    return [modal.Secret.from_dict(payload)]


def build_image() -> modal.Image:
    cuda_image = os.environ.get(
        "MODAL_CUDA_IMAGE",
        "nvidia/cuda:13.0.2-cudnn-devel-ubuntu24.04",
    )
    torch_index = os.environ.get("TORCH_INDEX_URL", "https://download.pytorch.org/whl/cu130")
    repo_url = os.environ.get(
        "CNB_REPO_URL",
        "https://github.com/xiaoqianran/modal-cnb-zhanzhi-comfyui.git",
    )
    repo_ref = os.environ.get("CNB_REPO_REF", "cnb-mirror")
    bake_cnb = os.environ.get("MODAL_BAKE_CNB", "1") != "0"
    secrets = _optional_secrets()

    image = (
        modal.Image.from_registry(cuda_image, add_python="3.12")
        .apt_install(
            "git",
            "git-lfs",
            "aria2",
            "ffmpeg",
            "wget",
            "curl",
            "ca-certificates",
            "build-essential",
            "cmake",
            "ninja-build",
            "pkg-config",
            "libgl1",
            "libglib2.0-0",
            "libsm6",
            "libxext6",
            "libxrender1",
        )
        .run_commands("git lfs install --skip-smudge")
        .env(
            {
                "ZHANZHI_ROOT": ZHANZHI_ROOT,
                "COMFY_HOME": f"{ZHANZHI_ROOT}/ComfyUI",
                "MODELS_ROOT": MODELS_ROOT,
                "DATA_ROOT": DATA_ROOT,
                "MODAL_CNB": "/opt/modal-cnb",
                "CNB_REPO_URL": repo_url,
                "CNB_REPO_REF": repo_ref,
                "CNB_CLONE_RETRIES": os.environ.get("CNB_CLONE_RETRIES", "5"),
                "CNB_HTTP_VERSION": os.environ.get("CNB_HTTP_VERSION", "HTTP/1.1"),
                "GIT_LFS_SKIP_SMUDGE": "1",
                "PYTHONUNBUFFERED": "1",
                "UV_SYSTEM_PYTHON": "1",
            }
        )
        .add_local_dir(str(REPO_ROOT / "scripts"), remote_path="/opt/modal-cnb/scripts", copy=True)
        .add_local_dir(str(REPO_ROOT / "patches"), remote_path="/opt/modal-cnb/patches", copy=True)
        .add_local_dir(str(REPO_ROOT / "config"), remote_path="/opt/modal-cnb/config", copy=True)
        .uv_pip_install(
            "torch==2.9.0",
            "torchvision==0.24.0",
            "huggingface_hub",
            "requests",
            "tqdm",
            "PyYAML",
            "safetensors",
            "einops",
            "transformers==4.57.6",
            "accelerate",
            "sentencepiece",
            "protobuf",
            "pillow",
            "scipy",
            "kornia",
            "opencv-python-headless",
            "aiohttp",
            "psutil",
            extra_index_url=torch_index,
            extra_options="--index-strategy unsafe-best-match",
            secrets=secrets,
        )
    )

    if bake_cnb:
        image = image.run_commands(
            "bash /opt/modal-cnb/scripts/clone_cnb.sh /opt/zhanzhi",
            "uv pip install --system -r /opt/zhanzhi/ComfyUI/requirements.txt",
            "python3 /opt/modal-cnb/scripts/install_node_deps.py",
            "python3 /opt/modal-cnb/scripts/apply_hook.py --comfy /opt/zhanzhi/ComfyUI",
            secrets=secrets,
        )
    return image


image = build_image()

_VOLUME_MAP = {
    MODELS_ROOT: models_vol,
    DATA_ROOT: data_vol,
}


@app.function(
    image=image,
    gpu=GPU,
    timeout=int(os.environ.get("MODAL_TIMEOUT", str(6 * 60 * MINUTES))),
    scaledown_window=int(os.environ.get("MODAL_SCALEDOWN", "300")),
    max_containers=int(os.environ.get("MODAL_MAX_CONTAINERS", "1")),
    cpu=float(os.environ.get("MODAL_CPU", "8")),
    secrets=_optional_secrets(),
    volumes=_VOLUME_MAP,
)
@modal.concurrent(max_inputs=int(os.environ.get("MODAL_CONCURRENT", "16")))
@modal.web_server(COMFY_PORT, startup_timeout=int(os.environ.get("MODAL_STARTUP_TIMEOUT", "900")))
def ui() -> None:
    """CNB 'ComfyUI 起飞' — dedicated GPU web UI."""
    models_vol.reload()
    data_vol.reload()
    subprocess.Popen(["bash", "/opt/modal-cnb/scripts/bootstrap.sh"])


@app.function(
    image=image,
    timeout=int(os.environ.get("MODAL_PREFETCH_TIMEOUT", str(4 * 60 * MINUTES))),
    cpu=float(os.environ.get("MODAL_PREFETCH_CPU", "4")),
    secrets=_optional_secrets(),
    volumes={MODELS_ROOT: models_vol},
)
def prefetch(dry_run: bool = False) -> dict:
    """Fill the models Volume from zhanzhi's ``初始化下载`` without holding a GPU."""
    models_vol.reload()
    cmd = ["python3", "/opt/modal-cnb/scripts/prefetch.py"]
    if dry_run:
        cmd.append("--dry-run")
    completed = subprocess.run(cmd, check=False)
    if not dry_run:
        models_vol.commit()
    if completed.returncode != 0:
        raise RuntimeError(f"prefetch exited {completed.returncode}")
    return {"ok": True, "dry_run": dry_run}


@app.function(
    image=image,
    timeout=20 * MINUTES,
    cpu=2,
    volumes={MODELS_ROOT: models_vol, DATA_ROOT: data_vol},
)
def status() -> dict:
    models_vol.reload()
    data_vol.reload()
    comfy = Path(ZHANZHI_ROOT) / "ComfyUI" / "main.py"
    model_files = 0
    models_bytes = 0
    models = Path(MODELS_ROOT)
    if models.is_dir():
        for path in models.rglob("*"):
            if path.is_file() and path.suffix != ".aria2":
                model_files += 1
                models_bytes += path.stat().st_size
    return {
        "comfy_baked": comfy.is_file(),
        "gpu_default": GPU,
        "model_files": model_files,
        "models_gib": round(models_bytes / 1024**3, 2),
        "workflows": Path(DATA_ROOT, "user/default/workflows").is_dir(),
    }


@app.local_entrypoint()
def main(action: str = "status", dry_run: bool = False) -> None:
    """
    modal run app.py --action status
    modal run app.py --action prefetch
    modal run app.py --action prefetch --dry-run
    """
    if action == "prefetch":
        print(prefetch.remote(dry_run=dry_run))
        return
    if action == "status":
        print(status.remote())
        return
    print(f"unknown action {action!r}; use status or prefetch", file=sys.stderr)
    raise SystemExit(2)
