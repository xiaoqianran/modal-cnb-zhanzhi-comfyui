#!/bin/bash

echo "执行环境检查和修复..."

cd /workspace

# 1. 处理自定义节点目录
echo "处理自定义节点目录..."
for folder in "custom_nodes"; do
    mkdir -p /workspace/$folder
    rm -rf /workspace/ComfyUI/$folder 2>/dev/null
    ln -sf /workspace/$folder /workspace/ComfyUI/$folder
done

# 2. 处理 models 目录链接到 ComfyUI
echo "处理 models 目录链接..."
# 删除 ComfyUI 中已存在的 models 目录
rm -rf /workspace/ComfyUI/models 2>/dev/null
# 创建符号链接：/workspace/ComfyUI/models -> /models
ln -sf /models /workspace/ComfyUI/models

# 3. 只清理 models 相关的无效符号链接
echo "清理 models 相关的无效符号链接..."

# 清理 /workspace/models 目录下的无效链接（只清理外部无效链接）
if [ -d "/workspace/models" ]; then
    find /workspace/models -type l 2>/dev/null | while read file; do
        target=$(readlink "$file")
        # 只删除指向外部且无效的链接
        if [[ "$target" == /* ]] && ! [ -e "$target" ]; then
            echo "删除无效的外部链接: $file -> $target"
            rm "$file"
        fi
    done
fi

# 清理 /models 目录下的无效链接
if [ -d "/models" ]; then
    find /models -type l 2>/dev/null | while read file; do
        if ! [ -e "$(readlink "$file")" ]; then
            echo "删除 /models 中的无效链接: $file"
            rm "$file"
        fi
    done
fi

# 清理 /workspace/ComfyUI/models 链接（如果是无效链接）
if [ -L "/workspace/ComfyUI/models" ]; then
    if ! [ -e "$(readlink "/workspace/ComfyUI/models")" ]; then
        echo "删除无效的 ComfyUI models 链接"
        rm "/workspace/ComfyUI/models"
    fi
fi

echo "环境检查完成!"
