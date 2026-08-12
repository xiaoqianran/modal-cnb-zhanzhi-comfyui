#!/usr/bin/env bash
# Modal counterpart of CNB ``assets/start_ComfyUI.sh``.
#
# CNB's script is tuned for a *shared* L40 (``--cache-none``, release VRAM
# after each job). Modal gives you a dedicated GPU you are already paying for,
# so we keep models resident and only enable --highvram on large cards.
set -euo pipefail

ZHANZHI_ROOT="${ZHANZHI_ROOT:-/opt/zhanzhi}"
COMFY_HOME="${COMFY_HOME:-$ZHANZHI_ROOT/ComfyUI}"
PORT="${COMFY_PORT:-8188}"

cd "$COMFY_HOME"

export CUDA_MODULE_LOADING="${CUDA_MODULE_LOADING:-LAZY}"
export PYTORCH_ALLOC_CONF="${PYTORCH_ALLOC_CONF:-backend:cudaMallocAsync,garbage_collection_threshold:0.8}"
export TF_CPP_MIN_LOG_LEVEL=3
unset COMFY_FORCE_FULL_MODEL_LOAD || true

pkill -f "python.*main.py" >/dev/null 2>&1 || true

ARGS=(
  --listen 0.0.0.0
  --port "$PORT"
  --enable-cors-header
  --preview-method auto
)

MEM_MB="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -d ' ,' || true)"
if [[ "${COMFY_HIGHVRAM:-}" == "1" ]]; then
  ARGS+=(--highvram)
elif [[ "${COMFY_HIGHVRAM:-}" == "0" ]]; then
  :
elif [[ "$MEM_MB" =~ ^[0-9]+$ ]] && (( MEM_MB >= 60000 )); then
  ARGS+=(--highvram)
fi

if [[ -n "${COMFY_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  EXTRA=( $COMFY_EXTRA_ARGS )
  ARGS+=("${EXTRA[@]}")
fi

if python3 -c "import sageattention" >/dev/null 2>&1; then
  ARGS+=(--use-sage-attention)
fi

echo "[start] python main.py ${ARGS[*]}"
exec python3 main.py "${ARGS[@]}"
