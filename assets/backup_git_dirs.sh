## 修改ComfyUI 插件目录下面的所有.git 为：git_backup
find /workspace/ComfyUI/custom_nodes/ -maxdepth 1 -mindepth 1 -type d \
  -exec bash -c '
    dir="$1"
    if [ -d "$dir/.git" ]; then
        echo "强制重命名: $dir/.git → $dir/git_backup" 
        rm -rf "$dir/git_backup" 2>/dev/null  # 先删除可能已存在的备份
        mv -f -- "$dir/.git" "$dir/git_backup"
    else 
        echo "跳过: $dir (无.git目录)"
    fi' bash {} \;

## 修改.gitignore 为 gitignore_backup
find /workspace/ComfyUI/custom_nodes/ -type f -name ".gitignore" \
  -exec bash -c '
    file="$1"
    dir=$(dirname "$file")
    target="$dir/gitignore_backup"
    echo "重命名: $file → $target"
    [ -f "$target" ] && rm -f "$target"  # 先删除可能已存在的备份
    mv -f -- "$file" "$target"' bash {} \;     