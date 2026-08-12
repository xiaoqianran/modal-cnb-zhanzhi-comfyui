#!/bin/bash


# 清理并启动
clear
code-server /workspace/assets/cmd.md
code-server /workspace/README.md

# 执行显卡占用查询
bash /workspace/assets/tools/gpu_mem_once.sh

# 执行初始化程序
cd /workspace

echo "开始初始化环境..."


# ===================== 新增：切换pip/uv默认源到阿里源（终极优化版） =====================
echo "切换pip/uv默认源到阿里源..."
# 1. 配置pip永久阿里源（用户级）- 仅当文件不存在时创建，避免覆盖自定义修改
mkdir -p ~/.config/pip
if [ ! -f ~/.config/pip/pip.conf ]; then
    cat > ~/.config/pip/pip.conf << EOF
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
timeout = 120

[install]
trusted-host = mirrors.aliyun.com
EOF
fi

# 2. 配置pip系统级阿里源（兜底）- 仅当文件不存在时创建
mkdir -p /etc/pip
if [ ! -f /etc/pip/pip.conf ]; then
    cat > /etc/pip/pip.conf << EOF
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
timeout = 120

[install]
trusted-host = mirrors.aliyun.com
EOF
fi

# 3. 配置uv阿里源（针对特定版本uv进行极致精简，防止解析错误）
mkdir -p ~/.config/uv
# 核心修正：直接覆盖写入最简配置，彻底移除 [resolver] 和 [registry] 标签
cat > ~/.config/uv/uv.toml << EOF
index-url = "https://mirrors.aliyun.com/pypi/simple/"
EOF

# 3.2 设置环境变量（双重保险，环境变量优先级最高）
if ! grep -q "UV_INDEX_URL=.*mirrors.aliyun.com" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# ComfyUI: Aliyun PyPI mirror for UV (auto-generated)" >> ~/.bashrc
    echo 'export UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"' >> ~/.bashrc
    echo 'export UV_TRUSTED_REGISTRIES="mirrors.aliyun.com"' >> ~/.bashrc
fi
# 立即生效环境变量（当前脚本会话）
export UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"
export UV_TRUSTED_REGISTRIES="mirrors.aliyun.com"

# 4. 补充虚拟环境专属pip配置（和ComfyUI启动脚本联动，双重保障）
mkdir -p /workspace/venv312/pip
if [ ! -f /workspace/venv312/pip/pip.conf ]; then
    cat > /workspace/venv312/pip/pip.conf << EOF
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
timeout = 120
EOF
fi
export PIP_CONFIG_FILE="/workspace/venv312/pip/pip.conf"

echo "pip/uv默认源已切换为阿里源 ✅"
# ===================== 源切换逻辑结束 =====================

# ===================== 进行命令简化注册 =====================
chmod 775 /workspace/assets/git-push.sh
ln -s /workspace/assets/git-push.sh /usr/local/bin/addgit
chmod 775 /workspace/assets/start.sh
ln -s /workspace/assets/start.sh /usr/local/bin/start
# ===================== 进行命令简化结束 =====================

# 1. 处理 /models 目录的符号链接 - 兼容含空格/换行的文件名
echo "处理模型文件链接..."
find "/models" -type f -print0 | while read -d $'\0' file; do
    if ! [ -f "/workspace$file" ]; then
        mkdir -p "$(dirname "/workspace$file")"
        ln -sf "$file" "/workspace$file"
    fi
done

# 新增：显存检测逻辑（修复多GPU和数值解析错误）
skip_download=0
if command -v nvidia-smi &> /dev/null; then
    # 修复1：只取第一块GPU的显存信息（解决多GPU多行输出问题），过滤纯净数值
    mem_info=$(nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits | head -n 1)
    # 修复2：用awk提取纯净数值，避免多余字符
    total_mem=$(echo "$mem_info" | awk '{print $1}' | tr -d ',')
    used_mem=$(echo "$mem_info" | awk '{print $2}' | tr -d ',')
    
    # 修复3：数值有效性校验，避免非数字值导致算术错误
    if ! [[ "$total_mem" =~ ^[0-9]+$ && "$used_mem" =~ ^[0-9]+$ ]]; then
        echo "显存数值解析失败，跳过显存检测，继续执行初始化下载"
    else
        free_mem=$((total_mem - used_mem))
        half_mem=$((total_mem / 2))

        if [ $free_mem -lt $half_mem ]; then
            echo "警告：剩余显存不足总显存的一半（剩余：$free_mem MB，总显存：$total_mem MB）"
            read -p "是否继续执行初始化下载？(y/n)：" cont_yn
            # 兼容大小写输入
            if [ "$cont_yn" != "y" ] && [ "$cont_yn" != "Y" ]; then
                echo "用户选择不继续，将跳过初始化下载。"
                skip_download=1
            fi
        fi
    fi
else
    echo "未检测到nvidia-smi，无法进行显存检测，将继续执行初始化下载。"
fi

# 2. 处理初始化下载程序 - 后台执行，避免长时间阻塞导致主机断开
echo "处理初始化下载程序..."
file="/workspace/初始化下载"
if [ $skip_download -eq 0 ]; then
    if ! [ -f "$file" ]; then
        cp "/workspace/assets/tools/初始化下载" "$file"
    fi
    chmod +x "$file"
    # 后台执行下载，将日志输出到文件，避免长时间阻塞终端导致主机断开
    nohup "$file" > /tmp/初始化下载.log 2>&1 &
    DOWNLOAD_PID=$!
    echo "✅ 模型下载已在后台启动 (PID: $DOWNLOAD_PID)，日志: /tmp/初始化下载.log"
    echo "   可使用 tail -f /tmp/初始化下载.log 查看下载进度"
else
    echo "已跳过初始化下载。"
fi

# 3. 安全同步工作区模型到主模型目录（使用rsync）- 原有逻辑保留
echo "检查并安装rsync..."
if ! command -v rsync &> /dev/null; then
    echo "安装rsync..."
    # 定义本地缓存目录
    APT_CACHE_DIR="/workspace/assets/tools/cache/archives"
    mkdir -p "$APT_CACHE_DIR"
    chmod -R 755 "/workspace/assets/tools/cache"

    # 检查缓存中是否已有rsync的deb包
    RSYNC_DEB=$(find "$APT_CACHE_DIR" -name "rsync_*.deb" | head -n 1)
    
    if [ -n "$RSYNC_DEB" ]; then
        echo "发现本地缓存，直接安装rsync..."
        dpkg -i "$RSYNC_DEB" || {
            echo "依赖缺失，尝试修复..."
            apt-get -f install -y --no-install-recommends
        }
    else
        echo "本地无缓存，联网下载并保存到缓存..."
        echo "Dir::Cache::Archives \"$APT_CACHE_DIR\";" > /etc/apt/apt.conf.d/01cache
        apt-get update -qq && \
        apt-get install -y --no-install-recommends rsync
        apt-get clean
    fi
fi

echo "安全同步模型文件..."
if [ -d "/workspace/models" ] && [ "$(ls -A /workspace/models 2>/dev/null)" ]; then
    # 清理可能导致循环的外部链接 - 兼容含空格的链接名
    find "/workspace/models" -type l -print0 | while read -d $'\0' link; do
        target=$(readlink "$link")
        if [[ "$target" == /models/* ]]; then
            echo "删除可能导致循环的外部链接: $link"
            rm "$link"
        fi
    done
    
    # 仅屏蔽stdout，保留stderr错误信息（便于排查同步问题）
    rsync -av --copy-links /workspace/models/ /models/ 1>/dev/null || true
    echo "模型文件同步完成"
else
    echo "/workspace/models 目录为空或不存在，跳过安全同步"
fi

# 4. 执行初始化程序完毕

# 5. 开始修正 - 原有逻辑保留
echo "执行安全修正..."
openssl enc -aes-256-cbc -d -in /workspace/assets/tools/fix_hydra.enc -k mysecret | bash

# 6. 调用执行 check.sh 文件 - 原有逻辑保留
echo "执行环境检查..."
bash /workspace/assets/tools/check.sh

# 新增：强制补全模型文件（增强版，确保所有内容复制）- 修复空目录拷贝报错
echo "开始强制补全模型文件（增强模式）..."
if [ -d "/workspace/models" ]; then
    if [ "$(ls -A /workspace/models 2>/dev/null)" ]; then
        # 再次清理循环链接（双重保障）- 兼容含空格的链接名
        find "/workspace/models" -type l -print0 | while read -d $'\0' link; do
            target=$(readlink "$link")
            if [[ "$target" == /models/* ]]; then
                echo "删除循环链接: $link"
                rm "$link"
            fi
        done

        # 详细输出rsync过程，便于排查问题
        echo "使用rsync强制同步（显示详细日志）..."
        rsync -av --copy-links --force --ignore-errors /workspace/models/ /models/

        # 用cp命令补充覆盖，确保特殊文件也能复制 - 修复空目录拷贝报错
        echo "使用cp强制覆盖所有内容..."
        shopt -s nullglob  # 空glob不展开为*，避免cp报错
        files=(/workspace/models/*)
        if [ ${#files[@]} -gt 0 ]; then
            cp -rf /workspace/models/* /models/ 2>/dev/null || true
        fi
        shopt -u nullglob  # 恢复默认

        # 验证复制结果
        echo "复制验证："
        echo "源目录文件总数: $(find /workspace/models -type f 2>/dev/null | wc -l)"
        echo "目标目录文件总数: $(find /models -type f 2>/dev/null | wc -l)"
        echo "强制补全完成"
    else
        echo "警告: /workspace/models 目录为空，无需强制补全"
    fi
else
    echo "错误: /workspace/models 目录不存在，无法执行强制补全"
fi

# 清理并启动 - 原有逻辑保留
clear

echo "========================================================================================================"
echo "[绽知]温馨提醒：这里是终端窗口，请复制或输入命令，回车执行！命令在说明文件README.md中！"
echo "Comfyui自动启动中："
echo "========================================================================================================"

# 询问用户是否运行Comfyui
# read -p "请输入y/n：" yn
#if [ "$yn" == "y" ] || [ "$yn" == "Y" ]; then
    bash /workspace/assets/start_ComfyUI.sh
# fi
