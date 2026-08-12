#!/bin/bash

# =================================================================================================
#  ComfyUI 自定义节点批量更新脚本
#  版本: 2.0
#  功能:
#    - 自动遍历指定目录下的所有子目录。
#    - 识别出通过 `git clone` 安装的节点 (检查是否存在 .git 目录)。
#    - 对 Git 仓库执行 `git pull` 命令以拉取最新更新。
#    - 提供清晰、带颜色的状态输出 (成功, 已是最新, 跳过, 失败)。
#    - 在脚本结束时提供一个汇总报告。
# =================================================================================================

set -o pipefail

# --- 配置 ---
# ComfyUI 自定义节点的主目录
CUSTOM_NODES_DIR="/workspace/ComfyUI/custom_nodes"

# --- 样式定义 (颜色) ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- 初始化计数器 ---
updated_count=0
uptodate_count=0
skipped_count=0
failed_count=0
total_count=0

# --- 主逻辑 ---
echo -e "${BLUE}🚀 开始批量更新 ComfyUI 自定义节点...${NC}"
echo "目标目录: ${CUSTOM_NODES_DIR}"
echo "======================================================================="

# 检查目标目录是否存在
if [ ! -d "$CUSTOM_NODES_DIR" ]; then
    echo -e "${RED}错误: 目录不存在: ${CUSTOM_NODES_DIR}${NC}"
    exit 1
fi

# 遍历 custom_nodes 目录下的所有子目录
for node_dir in "$CUSTOM_NODES_DIR"/*/; do
    # 移除路径末尾的斜杠
    node_dir=${node_dir%/}
    # 提取节点名称 (目录名)
    node_name=$(basename "$node_dir")
    total_count=$((total_count + 1))

    # 检查是否存在 .git 目录，以确认是否为 Git 仓库
    if [ -d "$node_dir/.git" ]; then
        echo -e "-> 正在检查 ${YELLOW}${node_name}${NC}..."
        
        # 使用子 shell (小括号) 来执行 git 命令，这样不会改变当前脚本的工作目录，更安全
        # 捕获 git pull 的输出和错误信息
        if output=$( (cd "$node_dir" && git pull) 2>&1 ); then
            # git pull 命令成功执行
            if [[ "$output" == *"Already up to date."* ]]; then
                echo -e "   ${GREEN}✓ 已是最新版本。${NC}"
                uptodate_count=$((uptodate_count + 1))
            else
                echo -e "   ${GREEN}✓ 更新成功！${NC}"
                # (可选) 如果想看更新详情，可以取消下面这行的注释
                # echo -e "$output"
                updated_count=$((updated_count + 1))
            fi
        else
            # git pull 命令执行失败
            echo -e "   ${RED}✗ 更新失败。${NC} Git 输出:"
            # 将错误输出缩进，便于阅读
            echo "$output" | sed 's/^/     /'
            failed_count=$((failed_count + 1))
        fi
    else
        echo -e "-> 跳过 ${BLUE}${node_name}${NC} (非 Git 仓库，可能是手动安装或解压的)。"
        skipped_count=$((skipped_count + 1))
    fi
    echo # 添加一个空行以分隔每个节点的输出
done

# --- 汇总报告 ---
echo "======================================================================="
echo -e "${BLUE}✨ 更新完成！汇总报告:${NC}"
echo "-----------------------------------------------------------------------"
echo -e "总计检查插件数: ${total_count}"
echo -e "${GREEN}成功更新: ${updated_count}${NC}"
echo -e "${GREEN}已是最新: ${uptodate_count}${NC}"
echo -e "${BLUE}跳过 (非Git): ${skipped_count}${NC}"
echo -e "${RED}更新失败: ${failed_count}${NC}"
echo "======================================================================="

# 如果有失败的，给出提示
if [ "$failed_count" -gt 0 ]; then
    echo -e "${YELLOW}注意: 有 ${failed_count} 个插件更新失败。请检查上面的错误日志，可能需要手动进入目录解决冲突或处理其他问题。${NC}"
fi

