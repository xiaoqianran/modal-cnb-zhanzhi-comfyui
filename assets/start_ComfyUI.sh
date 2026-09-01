#!/bin/bash

# =================================================================================================
#  ComfyUI CNB 云原生容器通用生产启动脚本 (V20.1 - Fully Unified L40/H20 Edition)
#  优化重点: 消除 VNCCS 报错 | CPU 16核精准绑定 | mmap 内存映射与零锁页防爆
# =================================================================================================

set -e

# --- 1. 强效清理旧残留进程 (保持端口与显存干净) ---
LISTEN_PORT=8188
echo "🧹 Cleaning up previous ComfyUI & Python processes on port ${LISTEN_PORT}..."
pkill -f "python main.py" 2>/dev/null || true
pkill -f "comfyui" 2>/dev/null || true

PIDS=$(ss -tulnp 2>/dev/null | grep ":$LISTEN_PORT" | grep -o 'pid=[0-9]*' | cut -d'=' -f2 | sort -u || true)
if [ -n "$PIDS" ]; then
    for pid in $PIDS; do kill -9 "$pid" 2>/dev/null || true; done
fi
sleep 1
echo "✅ Cleanup done."

# --- 2. 虚拟环境激活与国内镜像加速 ---
export PIP_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"
export PIP_TRUSTED_HOST="mirrors.aliyun.com"
export HF_ENDPOINT="https://hf-mirror.com"
export UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"

VENV_ACTIVATE_PATH="/workspace/venv312/bin/activate"
if [ -f "$VENV_ACTIVATE_PATH" ]; then
    source "$VENV_ACTIVATE_PATH"
else
    echo "⚠️ Warning: Virtual environment not found at $VENV_ACTIVATE_PATH."
fi

# --- 3. 容器 CPU 线程自适应对齐与 NUMA 避障 ---
RAW_CPU_COUNT=$(python -c 'import os; print(len(os.sched_getaffinity(0)))' 2>/dev/null || echo "16")
TARGET_CORES=$(python -c 'import os; print(",".join(map(str, sorted(list(os.sched_getaffinity(0))))))' 2>/dev/null || echo "")

# 限制上限为 16 线程，防止 96 核心 EPYC 处理器引发的线程调度争抢
CPU_COUNT=$(( RAW_CPU_COUNT > 16 ? 16 : RAW_CPU_COUNT ))

export OMP_NUM_THREADS=$CPU_COUNT
export MKL_NUM_THREADS=$CPU_COUNT
export NUMEXPR_MAX_THREADS=$CPU_COUNT
export NUMEXPR_NUM_THREADS=$CPU_COUNT

LAUNCHER=""
if command -v taskset &>/dev/null && [ -n "$TARGET_CORES" ]; then
    CORE_SPAN=$(python -c "cores = [$TARGET_CORES]; print(max(cores) - min(cores))" 2>/dev/null || echo "999")
    if [ "$CORE_SPAN" -lt 32 ]; then
        echo "🎯 [CPU Config] Single‑socket cores detected. Pinning to [$TARGET_CORES]"
        LAUNCHER="taskset -c $TARGET_CORES"
    else
        echo "ℹ️ [CPU Config] Multi‑socket span detected. Skip taskset pinning, Threads capped at $CPU_COUNT."
    fi
fi

# --- 4. 深度算力释放与即时内存回收配置 ---
export TF_CPP_MIN_LOG_LEVEL=3
export TF_ENABLE_ONEDNN_OPTS=0
export CUDA_MODULE_LOADING=LAZY

export CUDA_LAUNCH_BLOCKING=0
export TORCH_USE_CUDA_DSA=0
export CUDA_VISIBLE_DEVICES=0

# 激活 Triton 与 SageAttention 后端（全面释放 Hopper / Ada 算力）
export COMFYUI_USE_TRITON=1
export COMFY_KITCHEN_USE_TRITON=1
export COMFY_KITCHEN_BACKEND=triton

# 显存防碎与内存即时归还
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
export PYTORCH_ALLOC_CONF="backend:cudaMallocAsync,garbage_collection_threshold:0.6"
export MALLOC_TRIM_THRESHOLD_=0

# 移除历史干扰环境变量，由 ComfyUI 原生引擎完全接管显存分级
unset COMFY_FORCE_FULL_MODEL_LOAD
unset COMFY_DISABLE_LOWVRAM_FALLBACK
unset COMFY_NO_LOWVRAM

# --- 5. 目录清理、创建与软连接维护 (彻底消除 VNCCS 报错) ---
cd "/workspace/ComfyUI" || exit 1
echo "🔧 Cleaning temporary caches..."
rm -rf ./cache ./temp >/dev/null 2>&1

# 预先创建必要层级目录（杜绝 VNCCS 刷屏报错）
mkdir -p /workspace/ComfyUI/output/VNCCS/Characters
mkdir -p /workspace/ComfyUI/output /workspace/ComfyUI/input
mkdir -p /workspace/输出 /workspace/输入

ln -snf /workspace/ComfyUI/output /workspace/输出 >/dev/null 2>&1
rm -rf /workspace/ComfyUI/input
ln -snf /workspace/输入 /workspace/ComfyUI/input >/dev/null 2>&1

# --- 6. CUDA 预载与显存初始化 ---
python -W ignore::FutureWarning -c "import torch; torch.cuda.init(); torch.cuda.empty_cache(); print('✅ CUDA initialized & Memory cleared.')"

# --- 7. 统一的高效防爆启动参数 (全卡通用) ---
COMFY_ARGS=(
    --listen
    --port 8188
    --enable-cors-header
    --preview-method none        # 彻底关闭无用预览，消灭中间解码开销
    --cuda-malloc                # 开启 cudaMallocAsync 高效显存分配器
    --mmap-torch-files           # 🌟 内存映射加载：按需读取，消灭物理 RAM 常驻
    --disable-pinned-memory      # 🌟 禁用锁页强占：彻底解除 114GB 内存死锁
)

# --- 8. 启动汇总与执行 ---
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits 2>/dev/null | head -n 1 || echo "NVIDIA GPU")

echo "=========================================="
echo "🔧 统一生产环境配置摘要："
echo "   检测到 GPU：$GPU_NAME"
echo "   CPU 活动线程数：$OMP_NUM_THREADS（已限制并对齐）"
echo "   NUMA 启动器：${LAUNCHER:-已绕过（由操作系统管理）}"
echo "   内存引擎：mmap（已启用）| 固定内存（已禁用）"
echo "   启动参数：${COMFY_ARGS[*]}"
echo "=========================================="

exec $LAUNCHER python main.py "${COMFY_ARGS[@]}"