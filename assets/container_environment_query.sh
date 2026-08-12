#!/usr/bin/env bash
set -euo pipefail

# 定义输出文件路径
OUTPUT_HTML="/workspace/assets/environment_report.html"

# 创建HTML文件头部
echo "<!DOCTYPE html>
<html>
<head>
<title>环境检查报告</title>
<meta charset=\"UTF-8\">
<style>
  body {
    background-color: #1e1e1e;
    color: #dcdcdc;
    font-family: 'Courier New', monospace;
    font-size: 14px;
    line-height: 1.5;
    margin: 0;
    padding: 20px;
  }
  pre {
    white-space: pre-wrap;
    margin: 0;
    padding: 0;
  }
  .title {
    color: #4ec9b0;
    font-weight: bold;
    margin: 20px 0 10px;
  }
  .label {
    color: #dcdc79;
  }
  .green {
    color: #4ec9b0;
  }
  .red {
    color: #f44747;
  }
  .yellow {
    color: #dcdc79;
  }
</style>
</head>
<body>
<pre>" > "$OUTPUT_HTML"

# ========== 辅助函数 ==========
# 输出到终端和HTML文件
output() {
  echo -e "$@"
  
  # 转换ANSI颜色为HTML span标签
  local html_output=$(echo -e "$@" | sed \
    -e 's/\\033\[1;36m/<span class="title">/g' \
    -e 's/\\033\[1;33m/<span class="label">/g' \
    -e 's/\\033\[1;32m/<span class="green">/g' \
    -e 's/\\033\[1;31m/<span class="red">/g' \
    -e 's/\\033\[0m/<\/span>/g' \
    -e 's/✅/<span class="green">✅<\/span>/g' \
    -e 's/❌/<span class="red">❌<\/span>/g' \
    -e 's/🧠/<span class="yellow">🧠<\/span>/g' \
    -e 's/🔧/<span class="yellow">🔧<\/span>/g' \
    -e 's/📦/<span class="yellow">📦<\/span>/g')
  
  echo "$html_output" >> "$OUTPUT_HTML"
}

# ========== 配色 ==========
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  CLR_TITLE='\033[1;36m'
  CLR_LABEL='\033[1;33m'
  CLR_GREEN='\033[1;32m'
  CLR_RED='\033[1;31m'
  CLR_RESET='\033[0m'
else
  CLR_TITLE='' CLR_LABEL='' CLR_GREEN='' CLR_RED='' CLR_RESET=''
fi

# ========== 辅助函数 ==========
title() {
  local title="$1"
  local total_width=60

  # 尝试使用 python3 计算显示宽度，失败则使用字符长度
  local disp_w
  if command -v python3 >/dev/null 2>&1; then
    disp_w=$(python3 -c "
try:
    from wcwidth import wcswidth
    import sys
    w = wcswidth(sys.argv[1])
    print(w if w is not None and w >= 0 else len(sys.argv[1]))
except ImportError:
    print(len(sys.argv[1]))
" "$title" 2>/dev/null) || disp_w=${#title}
  else
  disp_w=${#title}
  fi

  local padding=$(( total_width - disp_w ))
  (( padding < 0 )) && padding=0

  local border_line
  border_line=$(printf '═%.0s' $(seq 1 $total_width))

  output "\n${CLR_TITLE}${border_line}${CLR_RESET}"
  printf "%s%*s\n" "$title" "$padding" "" | tee -a "$OUTPUT_HTML"
  output "${CLR_TITLE}${border_line}${CLR_RESET}"
}

label_value() {
  output "$(printf "%b%-20s%b %s" "$CLR_LABEL" "┃ $1" "$CLR_RESET" "$2")"
}

run() {
  local output_str=$("$@" 2>&1 | sed 's/^/  /')
  output "$output_str"
}

# 检查命令是否存在
check_command() {
  command -v "$1" >/dev/null 2>&1
}

# ========== 主脚本 ==========
{
# ========== 1️⃣ 系统信息 ==========
title "🖥️  系统信息"

# 解析 uname -a 的输出
UNAME_OUTPUT=$(uname -a)
read -r KERNEL_NAME HOSTNAME KERNEL_RELEASE KERNEL_VERSION MACHINE PROCESSOR HARDWARE_PLATFORM OS <<< "$UNAME_OUTPUT"

# 提取关键信息
DISTRO_INFO=""
if [[ -f /etc/os-release ]]; then
  DISTRO_INFO=$(grep "PRETTY_NAME" /etc/os-release | cut -d'"' -f2)
elif [[ -f /etc/redhat-release ]]; then
  DISTRO_INFO=$(cat /etc/redhat-release)
elif [[ -f /etc/debian_version ]]; then
  DISTRO_INFO="Debian $(cat /etc/debian_version)"
fi

# 解析内核版本信息
KERNEL_BASE=$(echo "$KERNEL_RELEASE" | cut -d'-' -f1)
KERNEL_BUILD=$(echo "$KERNEL_RELEASE" | cut -d'-' -f2-)

# 格式化显示
label_value "系统类型" "$KERNEL_NAME ($OS)"
label_value "主机名" "$HOSTNAME"
label_value "系统架构" "$MACHINE"
[[ -n "$DISTRO_INFO" ]] && label_value "发行版本" "$DISTRO_INFO"
label_value "内核版本" "$KERNEL_BASE"
label_value "内核构建" "$KERNEL_BUILD"

# 显示系统运行时间
if command -v uptime >/dev/null 2>&1; then
  UPTIME_INFO=$(uptime -p 2>/dev/null || uptime | awk '{print $3,$4}' | sed 's/,//')
  label_value "运行时间" "$UPTIME_INFO"
fi

# ========== 2️⃣ CPU / 内存 / 磁盘 ==========
title "🧠 CPU / 内存 / 磁盘"

# CPU 信息获取更鲁棒
if check_command lscpu; then
  CPU_MODEL=$(lscpu | awk -F: '/Model name/ {gsub(/^[ \t]+/, "", $2); print $2}' | head -1)
elif [[ -f /proc/cpuinfo ]]; then
  CPU_MODEL=$(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2 | sed 's/^[ \t]*//')
else
  CPU_MODEL="未知"
fi

# 内存信息获取
if check_command free; then
  MEM_USAGE=$(free -h | awk '/Mem:/ {print $3 " / " $2}')
else
  MEM_USAGE="未知"
fi

# 磁盘信息获取
if check_command df; then
  DISK_USAGE=$(df -h / 2>/dev/null | awk 'NR==2 {print $3 " / " $2 " (" $5 " 已用)"}')
else
  DISK_USAGE="未知"
fi

label_value "CPU" "$CPU_MODEL"
label_value "内存" "$MEM_USAGE"
label_value "根分区" "$DISK_USAGE"

# 激活 Python 虚拟环境
source /workspace/venv312/bin/activate

# ========== 3️⃣ Python & pip ==========
title "🐍 Python & pip"

if check_command python; then
  label_value "Python 路径" "$(which python)"
  label_value "Python 版本" "$极客python --version 2>&1)"
else
  label_value "Python 路径" "未安装"
  label_value "Python 版本" "未安装"
fi

if check_command pip; then
  label_value "pip 版本" "$(pip --version | cut -d' ' -f2)"
else
  label_value "pip 版本极客" "未安装"
fi

title "📂 Python 安装路径"
if check_command python; then
  run python - <<'PY'
import sys, platform, site

try:
    site_packages = next((p for p in site.getsitepackages() if 'site-packages' in p), "未找到")
except:
    site_packages = "未找到"

paths = [
    ("可执行文件", sys.executable),
    ("site‑packages", site_packages),
    ("Python Prefix", sys.prefix),
    ("Platform", platform.platform()),
]

# 计算最大标签宽度（考虑中文字符）
def display_width(text):
    """计算文本的显示宽度，中文字符算2个宽度"""
    width = 0
    for char in text:
        if ord(char) > 127:  # 非ASCII字符（包括中文）
            width += 2
        else:
            width += 1
    return width

max_width = max(display_width(k) for k, v in paths)
max_width = max(max_width, 15)  # 最小宽度15

for k, v in paths:
    label_width = display_width(k)
    padding = max_width - label_width + 3  # 额外3个空格
    spaces = " " * padding
    print(f"{k}{spaces}: {v}")
PY
else
  output "  Python 未安装"
fi

# ========== 4️⃣ PyTorch / torchvision / CUDA ==========
title "🔍 PyTorch / torchvision / CUDA"
if check_command python; then
  run python - <<'PY'
try:
    import torch
    print(f"torch        : {torch.__version__}")
    print(f"CUDA 支持     : {torch.cuda.is_available()}")
    print(f"CUDA Runtime : {torch.version.cuda}")
    if torch.c极客uda.is_available():
        try:
            device_props = torch.cuda.get_device_properties(0)
            print(f"GPU 设备      : {device_props.name}")
            print(f"GPU 内存      : {device_props.total_memory / 1024**3:.1f} GB")
        except:
            print("GPU 信息获取失败")
except ImportError:
    print("torch        : 未安装")

try:
    import torchvision
    print(f"torchvision  : {torchvision.__version__}")
except ImportError:
    print("torchvision  : 未安装")
PY
else
  output "  Python 未安装，无法检查 PyTorch"
fi

# ========== 5️⃣ Triton / xformers / flash‑attn / apex / sageattention ==========
title "🧪 Triton / xformers / flash‑attn / apex / sageattention"

if check_command python; then
  for pkg in triton xformers flash_attn apex sageattention; do
    run python - <<PYTHON
import os
import importlib
from importlib.util import find_spec
import importlib.metadata
import subprocess
import sys

pkg = "$pkg"
try:
    if pkg == "flash_attn":
        from flash_attn import __version__ as v
        loc = find_spec("flash_attn").origin
    elif pkg == "sageattention":
        try:
            v = importlib.metadata.version("sageattention")
        except:
            import sageattention
            v = getattr(sageattention, "__version__", "已安装")
        loc = find_spec("sageattention").origin
    elif pkg == "apex":
        # apex 特殊处理：尝试多种方法获取版本
        try:
            # 方法1: 尝试从 importlib.metadata 获取
            v = importlib.metadata.version("apex")
        except:
            try:
                # 方法2: 尝试从 pip show 获取
                result = subprocess.run([sys.executable, "-m", "pip", "show", "apex"], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.startswith('Version:'):
                            v = line.split(':', 1)[1].strip()
                            break
                    else:
                        v = "已安装"
                else:
                    v = "已安装"
            except:
                try:
                    # 方法3: 尝试从模块属性获取
                    import apex
                    v = getattr(apex, "__version__", None) or getattr(apex, "version", None) or "已安装"
                except:
                    v = "已安装"
        loc = find_spec("apex").origin
    else:
        m = importlib.import_module(pkg)
        v = getattr(m, "__version__", None) or getattr(m, "version", None) or "已安装"
        loc = getattr(m, "__file__", None)

    if loc:
        loc = os.path.dirname(loc)

    print(f"✅ {pkg:<13} 版本: {v:<10} 📁 {loc}")
except Exception as e:
    print(f"❌ {pkg:<13} 未安装")
PYTHON
  done
else
  output "  Python 未安装，无法检查扩展包"
fi

# ========== 6️⃣ CUDA 驱动 & 工具链 ==========
title "⚙️  CUDA 驱动 & 工具链"

if check_command nvidia-smi; then
  run nvidia-smi
else
  output "   ❌ ${CLR_RED}nvidia-smi 未找到，可能未安装 NVIDIA 驱动${CLR_RESET}"
fi

if check_command nvcc; then
  run nvcc --version
else
  output "   ❌ ${CLR_RED}nvcc 未安装，CUDA 工具链不可用${CLR_RESET}"
fi

# ========== 7️⃣ 当前路径 & 结构 ==========
title "📁 当前路径 & 结构"
label_value "当前目录" "$(pwd)"
run ls -lh --color=auto

# ========== 8️⃣ ComfyUI 插件列表 ==========
title "🧩 ComfyUI 插件列表（一级目录）"

CUSTOM_NODE_DIR="/workspace/ComfyUI/custom_nodes"

if [[ -d "$CUSTOM_NODE_DIR" ]]; then
  found_plugins=false
  for dir in "$CUSTOM_NODE_DIR"/*/; do
    if [[ -d "$dir" ]]; then
      found_plugins=true
      name=$(basename "$dir")
      fullpath=$(realpath "$dir")
      output "  🔧 $name   $fullpath"
    fi
  done
  
  if [[ "$found_plugins" == false ]]; then
    output "  ❌ ${CLR_RED}custom_nodes 目录为空${CLR_RESET}"
  fi
else
  output "  ❌ ${CLR_RED}custom_nodes 目录不存在${CLR_RESET}"
fi

# ========== 9️⃣ 模型文件（含 .gguf） ==========
title "🧠 模型 / LoRA 文件（含 .gguf）"

# 检查目录是否存在后再搜索
search_paths=()
for path in /works极客pace/ComfyUI/models /workspace/comfyui_data/input; do
  [[ -d "$path" ]] && search_paths+=("$path")
done

if [[ ${#search_paths[@]} -gt 0 ]]; then
  mapfile -t MODELS < <(find "${search_paths[@]}" -type f \
    $$ -iname '*.safetensors' -o -iname '*.ckpt' -o -iname '*.pth' -o -iname '*.gguf' $$ 2>/dev/null)
else
  MODELS=()
fi

if [[ ${#MODELS[@]} -eq 0 ]]; then
  output "     ❌ ${CLR_RED}未发现模型文件${CLR_RESET}"
else
  maxlen=0
  declare -A MODEL_PATHS
  for f in "${MODELS[@]}"; do
    name=$(basename "$f")
    dir=$(dirname "$f")
    [[ ${#name} -gt $maxlen ]] && maxlen=${#name}
    MODEL_PATHS["$name"]="$dir"
  done
  for name in "${!MODEL_PATHS[@]}"; do
    output "     🧠 $(printf "%-*s → %s" "$maxlen" "$name" "${MODEL_PATHS[$name]}")"
  done
fi

# ==========  🔟 已安装 pip 包列表 ==========
title "📦 所有已安装 Python 包（pip list）"

if check_command pip; then
  # 使用更简单可靠的方法，避免管道阻塞
  pip_output=$(pip list 2>/dev/null)
  
  # 计算总包数
  total_packages=$(echo "$pip_output" | wc -l)
  total_packages=$((total_packages - 2))  # 减去头部行
  
  # 显示所有包
  echo "$pip_output" | awk 'NR>2 { printf "  📦 %-30s %s\n", $1, $2 }' | while IFS= read -r line; do
    output "$line"
  done
  
  output "\n  📊 总计: $total_packages 个包"
else
  output "   ❌ ${CLR_RED}pip 未安装${CLR_RESET}"
fi

# ========== 1️⃣1️⃣ 网络连通性检查 ==========
title "🌐 网络连通性检查（PyPI / HuggingFace / Civitai）"

# 使用超时和更鲁棒的检查方法
check_network() {
  local url="$1"
  local name="$2"
  
  if timeout 5 ping -c1 -w2 "$url" &>/dev/null; then
    output "  ✅ $name 连通"
  else
    output "   ❌ $name 无法连接"
  fi
}

check_http() {
  local url="$1"
  local name="$2"
  
  if timeout 10 curl -s --head "$url" 2>/dev/null | head -n1 | grep -q "200 OK"; then
    output "  ✅ $name 可访问"
  else
    output "  ❌ $name 访问失败"
  fi
}

# 检查网络连通性
if check_command ping; then
  check_network "pypi.org" "PyPI        "
else
  output "   ❌ ping 命令不可用"
fi

if check_command curl; then
  check_http "https://huggingface.co" "HuggingFace "
  check_http "https://civitai.com" "Civitai     "
else
  output "   ❌ curl 命令不可用"
fi

# ✅ 结束标志
output "\n${CLR_GREEN}✅   全面环境检查完毕！${CLR_RESET}"

# 添加HTML文件尾部
echo "</pre>
</body>
</html>" >> "$OUTPUT_HTML"
} 