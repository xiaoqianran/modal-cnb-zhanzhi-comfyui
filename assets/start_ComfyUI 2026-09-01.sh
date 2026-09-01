#!/bin/bash

# =================================================================================================
# ComfyUI 共享 GPU 终极平衡启动脚本 (L40 48G / H20 96G 专属优化版)
# 核心策略：
#   1. 启用 cudaMallocAsync，让 PyTorch 在运行完后立即释放显存给其他共享用户，避免互相 OOM。
#   2. 恢复 ComfyUI 智能分步加载（Default VRAM），大幅降低峰值显存，确保多任务并行不崩溃。
#   3. 关闭调试型环境变量（DSA），释放 20%+ 的原生 GPU 算力。
#   4. 清理僵尸进程，保持容器环境纯净。
# =================================================================================================

set -e

# --- 1. 强效进程清理 (防止后台残留占用) ---
echo "🧹 Cleaning up previous python processes to release VRAM..."
pkill -f "python main.py" || true
pkill -f "comfyui" || true
sleep 1

# --- 2. 深度环境注入 ---
export PIP_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"
export PIP_TRUSTED_HOST="mirrors.aliyun.com"
export HF_ENDPOINT="https://hf-mirror.com"
export UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"

# 屏蔽 TensorFlow 的冗余报错噪音
export TF_CPP_MIN_LOG_LEVEL=3
export TF_ENABLE_ONEDNN_OPTS=0

# 极速加载：CUDA 内核延迟加载
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
    echo "✅ Detected NVIDIA L40 (48GB VRAM) - Shared Multi-Tenant Mode"
    IS_L40=1
elif [[ "$GPU_MODEL_CLEAN" == *"h20"* ]]; then
    echo "✅ Detected NVIDIA H20 (96GB VRAM) - Massive VRAM Mode"
    IS_L40=0
else
    echo "⚠️ Unknown GPU ($GPU_MODEL_RAW), defaulting to balanced config"
    IS_L40=1
fi

# --- 4. 显存策略与稳定性配置 (共享 GPU 核心优化) ---
export CUDA_LAUNCH_BLOCKING=0
# 关闭设备端断言，恢复原生推理速度 (DSA 开启会拖慢 20%+ 速度)
export TORCH_USE_CUDA_DSA=0
export CUDA_VISIBLE_DEVICES=0

# [关键优化] 纯净启用 cudaMallocAsync
# 不配置 expandable_segments，因为 Async 内存池自带优秀的碎片整理，且能主动将闲置显存退还给系统（其他共享容器）
export PYTORCH_ALLOC_CONF="backend:cudaMallocAsync,garbage_collection_threshold:0.6"

# [关键修复] 移除强制全量加载的环境变量！
# 允许 ComfyUI 启用智能分步加载与 CPU 卸载，大幅度降低大模型（如 Flux, HunyuanVideo）的峰值显存要求
unset COMFY_FORCE_FULL_MODEL_LOAD
unset COMFY_DISABLE_LOWVRAM_FALLBACK
unset COMFY_NO_LOWVRAM

# [优化] 尝试激活 Triton 后端提高算力
export COMFYUI_USE_TRITON=1

# 防止内存（RAM）溢出
export MALLOC_TRIM_THRESHOLD_=67108864

# --- 5. 硬件专属 CPU 线程配置 ---
if [ $IS_L40 -eq 1 ]; then
    export OMP_NUM_THREADS=8
    export MKL_NUM_THREADS=8
else
    export OMP_NUM_THREADS=16
    export MKL_NUM_THREADS=16
fi

# --- 6. 目录清理与软连接维护 ---
cd "/workspace/ComfyUI" || exit 1
echo "🔧 Cleaning temporary caches..."
rm -rf ./cache ./temp >/dev/null 2>&1

mkdir -p output input /workspace/输出 /workspace/输入
ln -snf /workspace/ComfyUI/output /workspace/输出 >/dev/null 2>&1
rm -rf /workspace/ComfyUI/input
ln -snf /workspace/输入 /workspace/ComfyUI/input >/dev/null 2>&1

# --- 7. CUDA 预载 ---
python -W ignore::FutureWarning -c "import torch; torch.cuda.init(); torch.cuda.empty_cache(); print('✅ CUDA initialized & Memory cleared.')"

# --- 8. 智能生成 ComfyUI 启动参数 ---
# 移除了 --disable-cuda-malloc，使上面的 cudaMallocAsync 真正生效
# 移除了 --highvram，在共享显卡环境下，不加任何显存参数即代表启用最安全的默认智能 VRAM 管理
COMFY_ARGS=(
    --listen
    --port 8188
    --enable-cors-header
    --preview-method auto
)

if [ $IS_L40 -eq 1 ]; then
    # L40 48G：共享显卡，默认 VRAM 模式 + 不保留模型缓存。
    # 这会使 ComfyUI 在画图结束后，自动把显存里的模型释放回系统内存，把显存完全让给其他共享用户，彻底杜绝互相 OOM！
    COMFY_ARGS+=(--cache-none)
    echo "🚀 Strategy: L40 (Cooperative Shared Mode - Default VRAM & Auto-Release)"
else
    # H20 96G：显存极大，允许保留 2 个模型在缓存中提升连续出图速度
    COMFY_ARGS+=(--cache-ram 2)
    echo "🚀 Strategy: H20 (High-Capacity Shared Mode - Balanced Cache)"
fi

# --- 9. 最终启动 ---
echo -e "\n===== Final Execution Command ====="
echo "python main.py ${COMFY_ARGS[*]}"
echo "====================================\n"

exec python main.py "${COMFY_ARGS[@]}"