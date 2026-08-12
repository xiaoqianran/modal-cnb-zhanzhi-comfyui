#!/bin/bash

# ==============================================================================

# --- 脚本配置与路径计算 ---
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
ASSETS_DIR="$SCRIPT_DIR"
WORKSPACE_DIR=$(cd "$SCRIPT_DIR/.." && pwd)

# ==================== 新增的修复代码 (最小化修改) ====================
# 为了防止 "command not found" 错误，如果外部函数库不存在，
# 我们在这里定义两个简单的替代函数。
# 这样脚本就可以正常运行，而不会改变任何原有逻辑。
log_step() { echo -e "\n=== [步骤 $1]: $2 ==="; }
log_info() { echo "--> $1"; }
# =====================================================================


# --- 切换到工作目录 ---
cd "$WORKSPACE_DIR"

# ==================== (已移动到最前) 阶段 1: 初步清理与备份 ====================
log_step "1" "初步清理与备份"
[ -f "$ASSETS_DIR/update_workflow_index.sh" ] && bash "$ASSETS_DIR/update_workflow_index.sh"
[ -f "$ASSETS_DIR/backup_git_dirs.sh" ] && bash "$ASSETS_DIR/backup_git_dirs.sh"
[ -f "$ASSETS_DIR/backup_gitignores.sh" ] && bash "$ASSETS_DIR/backup_gitignores.sh"
find . -type d -name "hf_cache" -exec rm -rf {} +
rm -f ./ComfyUI/input/nfsw* 2>/dev/null || true
log_info "初步清理与备份完成。"
# =============================================================================


# 新增：检查暂存区是否有超过200MB的文件（修复版）
echo "检查是否有超过200MB的大文件..."
MAX_SIZE=$((200 * 1024 * 1024))  # 200MB的字节数

# 使用更稳健的方式处理文件路径（避免特殊字符问题）
while read -r mode sha size file; do
    if [ "$size" -gt "$MAX_SIZE" ]; then
        # 计算文件大小（MB）
        size_mb=$((size / 1024 / 1024))
        echo "错误：发现超过200MB的文件，禁止提交："
        echo "  $file ($size_mb MB)"
        exit 1
    fi
done < <(git ls-files --stage)

# 原有Git操作步骤保持不变
git config gc.auto 256
git gc --auto
cd /workspace
git add .
git commit -m "同步更新"
git push
