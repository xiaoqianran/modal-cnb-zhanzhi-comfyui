#!/bin/bash

# 目标目录列表
directories=(
    "/workspace/Wan2GP"
    "/workspace/venv312"
    "/workspace/venv2gp"
)

# 遍历所有目标目录
for dir in "${directories[@]}"; do
    echo "处理目录: $dir"
    # 查找并重命名gitignore_backup文件
    find "$dir" -type f -name "gitignore_backup" -print -exec bash -c '
        file="$1"
        target="${file%/*}/.gitignore"
        echo "恢复: $file → $target"
        [ -f "$target" ] && rm -f "$target"  # 删除已存在的.gitignore
        mv -f -- "$file" "$target"
    ' bash {} \;
done

echo "操作完成：所有gitignore_backup已恢复为.gitignore"