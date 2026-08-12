#!/bin/bash

# 原有更新步骤保持不变
bash /workspace/assets/update_workflow_index.sh
bash /workspace/assets/update_models_index.sh

# 将ComfyUI的插件目录下面的 .git 目录重命名为：git_backup
echo "正在备份ComfyUI 插件 .git目录..."
bash /workspace/assets/backup_git_dirs.sh

# 删除所有hf_cache目录并严格检查残留
echo "正在删除hf_cache目录..."
find /workspace -type d -name "hf_cache" -exec rm -rf {} +
echo "正在检查hf_cache残留..."
if find /workspace -type d -name "hf_cache" | grep -q .; then
    echo "错误：存在未删除的hf_cache目录！"
    find /workspace -type d -name "hf_cache"
    exit 1
fi

# 提交前自动清理（新增删除nfsw文件操作）
echo "提交前执行Git自动优化..."
echo "正在删除/workspace/ComfyUI/input目录下所有nfsw开头的文件..."
# 强制删除所有以nfsw开头的文件（不提示、不中断）
rm -f /workspace/ComfyUI/input/nfsw* 2>/dev/null

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
