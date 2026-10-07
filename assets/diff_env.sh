#!/usr/bin/env bash
set +e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

COMFY_ROOTS=()
for d in /root/ComfyUI /workspace/ComfyUI /ComfyUI /app/ComfyUI; do
  [ -d "$d" ] && COMFY_ROOTS+=("$d")
done

CN_DIRS=()
for r in "${COMFY_ROOTS[@]}"; do CN_DIRS+=("$r/custom_nodes"); done
CN_DIRS+=(/workspace/custom_nodes /root/ComfyUI/custom_nodes)

PY=""
for c in /workspace/venv312/bin/python /root/miniconda3/envs/envs313/bin/python python3 python; do
  command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
[ -z "$PY" ] && PY=python3

echo "###########################################################"
echo "# ComfyUI env fingerprint"
echo "# host : $(hostname)"
echo "# time : $(date '+%F %T %Z')"
echo "###########################################################"

echo
echo "===== [1] runtime ====="
echo "kernel   : $(uname -r)"
echo "os       : $( (. /etc/os-release 2>/dev/null; echo "$PRETTY_NAME") )"
echo "glibc    : $(ldd --version 2>/dev/null | head -1)"
echo "python   : $PY -> $($PY -V 2>&1)"
echo "conda    : ${CONDA_DEFAULT_ENV:-<none>}"
echo "nvcc     : $(nvcc --version 2>/dev/null | grep -o 'release [0-9.]*' || echo none)"
nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/gpu      : /'

echo
echo "===== [2] ComfyUI roots ====="
for r in "${COMFY_ROOTS[@]}"; do
  echo "--- $r"
  [ -d "$r/.git" ] && (
    cd "$r" || exit
    echo "    commit : $(git log -1 --format='%H')"
    echo "    date   : $(git log -1 --format='%cd')"
    echo "    subj   : $(git log -1 --format='%s')"
  )
  [ -f "$r/requirements.txt" ] && echo "    frontend req : $(grep -E '^comfyui-frontend-package' "$r/requirements.txt" | tr -d '\r')"
done

echo
echo "===== [3] key source hashes ====="
for rel in comfy/ops.py comfy/weight_adapter/lora.py comfy/weight_adapter/bypass.py comfy/weight_adapter/__init__.py comfy/ldm/minimax/model.py comfy/model_patcher.py comfy/sd.py nodes.py execution.py; do
  for r in "${COMFY_ROOTS[@]}"; do
    f="$r/$rel"
    [ -f "$f" ] && printf "    %s  %-38s (%s)\n" "$(sha256sum "$f" | cut -c1-12)" "$rel" "$r"
  done
done

echo
echo "===== [4] custom_nodes ====="
for base in "${CN_DIRS[@]}"; do
  [ -d "$base" ] || continue
  echo "--- $base  real=$(readlink -f "$base")"
  n=0
  for d in "$base"/*/; do
    name=$(basename "$d")
    [ "$name" = "__pycache__" ] && continue
    [ -d "$d" ] || continue
    n=$((n+1))
    if [ -d "$d/.git" ]; then
      info=$(cd "$d" && git log -1 --format='%h %cd' --date=short 2>/dev/null)
      printf "    %-44s %s\n" "$name" "$info"
    else
      printf "    %-44s %s\n" "$name" "<no-git>"
    fi
  done
  echo "    total: $n"
done

echo
echo "===== [5] pip packages ====="
$PY -m pip list 2>/dev/null | grep -Ei '^(torch|torchvision|torchaudio|triton|xformers|numpy|transformers|safetensors|accelerate|bitsandbytes|comfyui|sageattention|nunchaku|gguf|llama)' | sort | sed 's/^/    /'

echo
echo "===== [6] model / lora probe ====="
if [ -f "$SCRIPT_DIR/inspect_models.py" ]; then
  $PY "$SCRIPT_DIR/inspect_models.py"
else
  echo "    <找不到 inspect_models.py，跳过>"
fi

echo
echo "===== [7] log clues ====="
for L in /root/ComfyUI/user/comfyui.log /workspace/ComfyUI/user/comfyui.log; do
  if [ -f "$L" ]; then
    echo "--- $L"
    grep -aE 'Native ops|emulated ops|Detected mixed precision|Memory Efficient Sage|sol_attn|Chunk FeedForward|model_type' "$L" | tail -15 | sed 's/^/    /'
  fi
done
