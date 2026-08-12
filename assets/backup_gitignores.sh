#!/bin/bash

# 目标目录列表
directories=(
 
    "/workspace/venv312"
  
)

# 遍历所有目标目录
for dir in "${directories[@]}"; do
    echo "处理目录: $dir"
    # 查找并重命名.gitignore文件
    find "$dir" -type f -name ".gitignore" -print -exec bash -c '
        file="$1"
        target="${file%/*}/gitignore_backup"
        echo "重命名: $file → $target"
        [ -f "$target" ] && rm -f "$target"  # 删除已存在的备份文件
        mv -f -- "$file" "$target"
    ' bash {} \;
done

echo "操作完成：所有.gitignore已重命名为gitignore_backup"