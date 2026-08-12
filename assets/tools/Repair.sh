#!/bin/bash
# 插件URL列表文件
URL_FILE="/workspace/assets/ComfyUI 插件.txt"
PLUGINS_DIR="/workspace/ComfyUI/custom_nodes"
EXCLUDE_PLUGIN="comfyui-impact-pack"  # 要排除的插件名

# 确保插件目录存在
mkdir -p "$PLUGINS_DIR"

# 解除父仓库绑定（排除指定插件）
find "$PLUGINS_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | while IFS= read -r -d '' plugin_dir; do
    plugin_name=$(basename "$plugin_dir")
    
    # 排除指定插件
    if [[ "$plugin_name" == "$EXCLUDE_PLUGIN" ]]; then
        echo "跳过排除插件: $plugin_name"
        continue
    fi
    
    echo "处理目录: $plugin_dir"
    rm -rf "${plugin_dir}/.git" "${plugin_dir}/.github" 2>/dev/null
    git -C "$plugin_dir" init --quiet
done

# 关联远程仓库（排除指定插件）
while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    plugin_name=$(awk '{print $1}' <<< "$line")
    repo_url=$(awk '{print $2}' <<< "$line")
    [[ -z "$plugin_name" || -z "$repo_url" ]] && continue
    
    # 排除指定插件
    if [[ "$plugin_name" == "$EXCLUDE_PLUGIN" ]]; then
        echo "跳过排除插件: $plugin_name"
        continue
    fi
    
    target_dir="$PLUGINS_DIR/$plugin_name"
    echo "处理插件: $plugin_name ($repo_url)"
    mkdir -p "$target_dir"

    # 初始化Git操作
    (
        cd "$target_dir" || exit 1
        echo "当前目录: $(pwd)"
        git init --quiet
        git remote remove origin 2>/dev/null
        git remote add origin "$repo_url"
        
        # 获取远程数据并识别默认分支
        git fetch --all --quiet
        default_branch=$(git remote show origin | grep 'HEAD branch' | cut -d':' -f2 | xargs)
        
        # 优先使用默认分支 > main > master
        if [[ -n "$default_branch" ]]; then
            echo "使用默认分支: $default_branch"
            # 确保本地分支存在并建立跟踪关系
            if ! git rev-parse --verify --quiet "$default_branch" >/dev/null; then
                git branch "$default_branch" --track "origin/$default_branch" >/dev/null
            fi
            git checkout -f "$default_branch"
            git reset --hard "origin/$default_branch"
        elif git show-ref --verify --quiet "refs/remotes/origin/main"; then
            echo "使用main分支"
            git checkout -f -B main --track origin/main
            git reset --hard origin/main
        elif git show-ref --verify --quiet "refs/remotes/origin/master"; then
            echo "使用master分支"
            git checkout -f -B master --track origin/master
            git reset --hard origin/master
        else
            echo "警告：未找到有效分支，尝试检出HEAD"
            git checkout -f HEAD
        fi
        
        git clean -fd
        
        echo "插件 $plugin_name 更新成功"
    ) || echo "插件 $plugin_name 更新失败"
done < "$URL_FILE"

# 更新子模块
echo "更新ComfyUI子模块..."
(cd /workspace/ComfyUI && git submodule update --init --recursive --quiet)

echo "批量修复完成！重启ComfyUI生效"