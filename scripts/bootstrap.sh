#!/usr/bin/env bash
# Modal counterpart of CNB ``assets/welcome.sh``.
#
# Kept:
#   - link /models into ComfyUI
#   - install the on-demand download hook
#   - background prefetch (CNB 2026-07-11: start UI first, download slowly)
#   - start ComfyUI
# Dropped (CNB-only, redundant on Modal):
#   - code-server / vscode welcome
#   - Aliyun pip mirrors
#   - interactive VRAM prompt
#   - git_push / hydra.enc / rsync of workspace/models
#   - shared-GPU cache-none policy
set -euo pipefail

ZHANZHI_ROOT="${ZHANZHI_ROOT:-/opt/zhanzhi}"
COMFY_HOME="${COMFY_HOME:-$ZHANZHI_ROOT/ComfyUI}"
MODELS_ROOT="${MODELS_ROOT:-/models}"
DATA_ROOT="${DATA_ROOT:-/workspace/data}"
MODAL_CNB="${MODAL_CNB:-/opt/modal-cnb}"
PREFETCH="${PREFETCH:-1}"

mkdir -p \
  "$MODELS_ROOT" \
  "$DATA_ROOT/input" \
  "$DATA_ROOT/output" \
  "$DATA_ROOT/user/default/workflows"

if [[ ! -d "$COMFY_HOME" ]]; then
  echo "[bootstrap] ComfyUI missing at $COMFY_HOME — cloning"
  bash "$MODAL_CNB/scripts/clone_cnb.sh" "$ZHANZHI_ROOT"
fi

# Seed bundled workflows onto the persistent data volume once.
if [[ -d "$ZHANZHI_ROOT/工作流" ]] && [[ -z "$(ls -A "$DATA_ROOT/user/default/workflows" 2>/dev/null || true)" ]]; then
  echo "[bootstrap] seeding workflows"
  cp -a "$ZHANZHI_ROOT/工作流/." "$DATA_ROOT/user/default/workflows/"
fi

# One layout: ComfyUI sees models/input/output/user/custom_nodes via links.
# extra_model_paths.yaml is intentionally unused — CNB used both a symlink
# *and* extra_model_paths, which double-scanned the same tree.
rm -rf "$COMFY_HOME/models" "$COMFY_HOME/input" "$COMFY_HOME/output"
ln -sfn "$MODELS_ROOT" "$COMFY_HOME/models"
ln -sfn "$DATA_ROOT/input" "$COMFY_HOME/input"
ln -sfn "$DATA_ROOT/output" "$COMFY_HOME/output"

if [[ -d "$COMFY_HOME/user" && ! -L "$COMFY_HOME/user" ]]; then
  # First boot: keep any baked user files, then replace with the volume.
  cp -an "$COMFY_HOME/user/." "$DATA_ROOT/user/" 2>/dev/null || true
  rm -rf "$COMFY_HOME/user"
fi
ln -sfn "$DATA_ROOT/user" "$COMFY_HOME/user"

if [[ -d "$ZHANZHI_ROOT/custom_nodes" ]]; then
  rm -rf "$COMFY_HOME/custom_nodes"
  ln -sfn "$ZHANZHI_ROOT/custom_nodes" "$COMFY_HOME/custom_nodes"
fi

# CNB docs used these names; keep them as convenience links.
mkdir -p /workspace
ln -sfn "$DATA_ROOT/input" /workspace/输入
ln -sfn "$DATA_ROOT/output" /workspace/输出
ln -sfn "$DATA_ROOT/user/default/workflows" /workspace/工作流
ln -sfn "$COMFY_HOME" /workspace/ComfyUI

python3 "$MODAL_CNB/scripts/apply_hook.py" --comfy "$COMFY_HOME"

if [[ "$PREFETCH" == "1" ]]; then
  echo "[bootstrap] starting background prefetch -> /tmp/prefetch.log"
  nohup python3 "$MODAL_CNB/scripts/prefetch.py" > /tmp/prefetch.log 2>&1 &
  echo "[bootstrap] prefetch pid $!"
fi

exec bash "$MODAL_CNB/scripts/start_comfyui.sh"
