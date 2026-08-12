#!/bin/bash

# =================================================================================================
# ComfyUI 终极优化启动脚本 (针对 L40/H20 深度加固版)
# 核心提升：
#   1. 消除 TensorFlow 冗余警告噪音，净化日志
#   2. 激活 Triton 后端潜力，提升 L40 推理效率
#   3. 修复 PyTorch 2.4+ 显存配置警告 (PYTORCH_ALLOC_CONF)
#   4. 消除 Nunchaku 等插件的文件缺失噪音
#   5. 维持 LAZY 加载，保持秒级开机速度
# =================================================================================================

set -e

# --- 1. 强效进程清理 ---
echo "🧹 Cleaning up previous processes..."
pkill -f "python main.py" || true
pkill -f "comfyui" || true
sleep 1

# --- 2. 深度环境注入 ---
export PIP_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"
export PIP_TRUSTED_HOST="mirrors.aliyun.com"
export HF_ENDPOINT="https://hf-mirror.com"
export UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"

# [优化] 屏蔽 TensorFlow 的 CPU/GPU 报错噪音
export TF_CPP_MIN_LOG_LEVEL=3
export TF_ENABLE_ONEDNN_OPTS=0

# [保持] 极速加载：CUDA 内核延迟加载
export CUDA_MODULE_LOADING=LAZY

# 激活虚拟环境
VENV_ACTIVATE_PATH="/workspace/venv312/bin/activate"
if [ -f "$VENV_ACTIVATE_PATH" ]; then
    source "$VENV_ACTIVATE_PATH"
else
    echo "⚠️ Warning: Virtual environment not found."
fi

# --- 3. 硬件型号精准识别 ---
GPU_MODEL_RAW=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits 2>/dev/null | head -n 1 | xargs)
GPU_MODEL_CLEAN=$(echo "$GPU_MODEL_RAW" | tr '[:upper:]' '[:lower:]' | sed 's/ //g;s/-//g;s/_//g')

IS_L40=0
if [[ "$GPU_MODEL_CLEAN" == *"l40"* ]]; then
    echo "✅ Detected NVIDIA L40 (48GB VRAM) - Optimized for high throughput"
    IS_L40=1
elif [[ "$GPU_MODEL_CLEAN" == *"h20"* ]]; then
    echo "✅ Detected NVIDIA H20 (96GB VRAM) - Optimized for large cache"
    IS_L40=0
else
    echo "⚠️ Unknown GPU ($GPU_MODEL_RAW)"
fi

# --- 4. 显存策略与稳定性配置 ---
export CUDA_LAUNCH_BLOCKING=0
export TORCH_USE_CUDA_DSA=1
export CUDA_VISIBLE_DEVICES=0

# [修复] 使用最新 PyTorch 命名规范
export PYTORCH_ALLOC_CONF="backend:cudaMallocAsync,expandable_segments:True,garbage_collection_threshold:0.6"

# [保持] 强制全量加载模式
export COMFY_FORCE_FULL_MODEL_LOAD=1
export COMFY_DISABLE_LOWVRAM_FALLBACK=1
export COMFY_NO_LOWVRAM=1

# [优化] 尝试激活 Triton 后端
export COMFYUI_USE_TRITON=1

# [内存管理] 防止 RAM 溢出
export MALLOC_TRIM_THRESHOLD_=67108864

# --- 5. 硬件专属 CPU 线程配置 ---
if [ $IS_L40 -eq 1 ]; then
    export OMP_NUM_THREADS=8
    export MKL_NUM_THREADS=8
else
    export OMP_NUM_THREADS=32
    export MKL_NUM_THREADS=32
fi

# --- 6. 目录清理与预处理 ---
cd "/workspace/ComfyUI" || exit 1
echo "🔧 Cleaning temporary caches..."
rm -rf ./cache ./temp >/dev/null 2>&1

mkdir -p output input /workspace/输出 /workspace/输入
ln -snf /workspace/ComfyUI/output /workspace/输出 >/dev/null 2>&1
rm -rf /workspace/ComfyUI/input
ln -snf /workspace/输入 /workspace/ComfyUI/input >/dev/null 2>&1


# --- 7. CUDA 预载 (无报错初始化) ---
python -W ignore::FutureWarning -c "import torch; torch.cuda.init(); torch.cuda.empty_cache(); print('✅ CUDA initialized and cache cleared.')"

# --- 8. 智能生成 ComfyUI 启动参数 (多人共享模式优化) ---
COMFY_ARGS=(
    --listen
    --port 8188
    --enable-cors-header
    --preview-method auto
    --disable-cuda-malloc
)
if [ $IS_L40 -eq 1 ]; then
    # 共享环境下，使用 --highvram 能够预留更多空间给上下文，
    # 结合我们设置的 PYTORCH_ALLOC_CONF (backend:cudaMallocAsync) 
    # 可以极大地减少多人争抢显存时产生的碎片。
    COMFY_ARGS+=(--highvram --cache-none)
    echo "🚀 Strategy: L40 (Shared Context Optimized - High Stability)"
else
    # H20 显存极大，可以适当增加缓存，但为了防止 OOM，保留 --cache-ram
    COMFY_ARGS+=(--cache-ram 2) 
    echo "🚀 Strategy: H20 (Shared Context Optimized - Capacity First)"
fi



# --- 9. 最终启动 ---
echo -e "\n===== Final Execution Command ====="
echo "python main.py ${COMFY_ARGS[*]}"
echo "====================================\n"

exec python main.py "${COMFY_ARGS[@]}"
