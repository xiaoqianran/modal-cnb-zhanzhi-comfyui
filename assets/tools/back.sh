find /workspace/ComfyUI/custom_nodes/ -maxdepth 1 -mindepth 1 -type d \
  -exec bash -c 'if [ -d "$1/.git" ]; then 
        echo "强制重命名: $1/.git → $1/.git_backup" 
        mv -f -- "$1/.git" "$1/.git_backup"
     else 
        echo "跳过: $1 (无.git目录)"
     fi' bash {} \;

cd /workspace
git add .
git commit -m "同步更新"
git push