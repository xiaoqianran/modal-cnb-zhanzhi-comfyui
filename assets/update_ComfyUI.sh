#!/bin/bash

echo "开始更新ComfyUI..."

# 进入ComfyUI目录
cd /workspace/ComfyUI

# 提前删除.gitignore，避免git pull冲突
rm -rf .gitignore

# 恢复.git目录
if [ -d ".git_backup" ]; then
    mv .git_backup .git
    echo "恢复ComfyUI的.git目录"
fi

# ================== 新增逻辑：恢复 server.py ==================
SERVER_PY="/workspace/ComfyUI/server.py"
SERVER_PY_BAK="/workspace/ComfyUI/server.py.bak"

if [ -f "$SERVER_PY_BAK" ]; then
    if [ -f "$SERVER_PY" ]; then
        echo "删除当前 server.py..."
        rm -f "$SERVER_PY"
    fi
    echo "恢复备份的 server.py..."
    mv "$SERVER_PY_BAK" "$SERVER_PY"
else
    echo "未找到 server.py.bak，跳过恢复步骤。"
fi
# ================== 新增逻辑结束 ==================

# 更新ComfyUI
echo "正在更新ComfyUI..."
git pull origin master

# 隐藏.git目录
mv .git .git_backup
echo "隐藏ComfyUI的.git目录"

# 激活虚拟环境
source /workspace/venv312/bin/activate
pip install -r /workspace/ComfyUI/requirements.txt
# uv pip install -U comfy-cli
# uv pip install -U comfyui-frontend-package
# uv pip install -U comfyui-workflow-templates
# uv pip install -U comfyui-embedded-docs

# 恢复自定义的.gitignore
rm -rf .gitignore
cp /workspace/assets/.gitignore /workspace/ComfyUI/.gitignore

# 返回主目录
cd ../..

bash /workspace/assets/tools/hook

echo "更新完成！"
