#!/bin/bash
# 文件名: gpu_mem_check.sh
# 功能: 检测NVIDIA显卡显存占用率，当空闲显存低于60%时给出红色提示，建议重启ComfyUI_Cloud
# 使用说明: 赋予执行权限(chmod +x gpu_mem_check.sh)后直接运行./gpu_mem_check.sh

# 定义ANSI颜色转义序列（兼容绝大多数Linux终端）
RED='\033[31m'          # 红色字体
YELLOW='\033[33m'       # 黄色字体（表格标题）
GREEN='\033[32m'        # 绿色字体（正常提示）
RESET='\033[0m'         # 重置为终端默认颜色

# ===================== 第一步：检查NVIDIA显卡环境 =====================
# 检查nvidia-smi命令是否可用
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}❌ 错误：未找到nvidia-smi命令，请确认已安装NVIDIA显卡驱动${RESET}"
    exit 1
fi

# 获取GPU数量（屏蔽错误输出）
GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader,nounits 2>/dev/null)

# 检查是否检测到GPU
if [ -z "$GPU_COUNT" ] || [ "$GPU_COUNT" -eq 0 ]; then
    echo -e "${RED}❌ 错误：未检测到NVIDIA显卡，请确认显卡驱动正常或显卡已正确识别${RESET}"
    exit 1
fi

# ===================== 第二步：输出显存信息表格 =====================
echo -e "\n${YELLOW}========== GPU显存占用情况 ==========${RESET}"
echo "+-----------------------------------------------+"
echo "| GPU ID | 显存总量(MiB) | 已用显存(MiB) | 占用率 |"
echo "+-----------------------------------------------+"

# 解析显存数据并标记是否需要提示（空闲显存<60% = 占用率>40%）
nvidia-smi --query-gpu=index,memory.total,memory.used --format=csv,noheader,nounits 2>/dev/null | awk -v red="$RED" -v green="$GREEN" -v reset="$RESET" '
BEGIN {
    need_alert = 0  # 初始化提示标记
}
{
    # 提取显存数据
    gpu_id = $1
    mem_total = $2
    mem_used = $3
    mem_percent = (mem_used / mem_total) * 100  # 占用率
    free_percent = 100 - mem_percent            # 空闲率（新增：便于理解）
    
    # 格式化输出每行数据
    printf "| %6s | %13s | %13s | %6.2f%% |\n", gpu_id, mem_total, mem_used, mem_percent
    
    # 判断条件：空闲显存低于60%（即占用率>40%）
    if (free_percent < 60) {
        need_alert = 1
    }
}
END {
    # 输出表格结束线
    print "+-----------------------------------------------+"
    
    # 输出提示信息
    if (need_alert == 1) {
        printf "\n%s⚠️  重要提示：检测到部分显卡空闲显存低于60%%！%s\n", red, reset
        printf "%s建议立即重新开启ComfyUI_Cloud，以获得更优质的运行体验%s\n\n", red, reset
    } else {
        printf "\n%s✅ 所有显卡空闲显存均在60%%以上，运行状态良好%s\n\n", green, reset
    }
}'

# 脚本正常结束
exit 0