  ## 恢复ComfyUI 插件目录下面的所有 git_backup目录为.git
find /workspace/ComfyUI/custom_nodes/ -maxdepth 1 -mindepth 1 -type d \
  -exec sh -c '
    # 恢复 .git 目录
    dir="$1"
    if [ -d "$dir/git_backup" ]; then
        echo "强制恢复: $dir/git_backup → $dir/.git"
        rm -rf "$dir/.git" 2>/dev/null
        mv -- "$dir/git_backup" "$dir/.git"
    else
        echo "跳过 .git 恢复: $dir (无 git_backup 目录)"
    fi' sh {} \;

## 修改gitignore_backup 为 .gitignore
find /workspace/ComfyUI/custom_nodes/ -type f -name "gitignore_backup" \
  -exec bash -c '
    file="$1"
    dir="$(dirname "$file")"
    echo "重命名: $file → $dir/.gitignore"
    mv -f -- "$file" "$dir/.gitignore"' bash {} \;