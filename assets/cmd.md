## 🔧 常用命令

### ComfyUI 一键启动命令
-   bash /workspace/assets/start_ComfyUI.sh

### 数据提交上传（推送）到自己的仓库
-   bash /workspace/assets/git_push.sh

### ComfyUI 更新
-   bash /workspace/assets/update_ComfyUI.sh

### 查看显卡占用

-   bash /workspace/assets/tools/gpu_mem_once.sh

### 云端模型编辑器：

-   python3 /workspace/assets/tools/web_editor.py

### 初始化模型编辑器：

-   python3 /workspace/assets/tools/Ini_edit_down.py

### ComfyUI 插件更新：
-   bash /workspace/assets/update_nodes.sh

### 恢复ComfyUI 插件.git目录（更新ComfyUI 插件前运行，将git_backup目录改名为.git）
-   bash /workspace/assets/restore_git_dirs.sh

### 备份ComfyUI 插件.git目录（更新ComfyUI 插件后运行，将.git目录改名为git_backup）
-   bash /workspace/assets/backup_git_dirs.sh

### 安装依赖
-   pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
  
-   pip install xformers==0.0.32.post2 -i https://mirrors.aliyun.com/pypi/simple/
    
-   pip install -r requirements.txt -i https://mirrors.hit.edu.cn/pypi/web/simple （哈工大源）
    
-   pip install -r req
uirements.txt -i https://pypi.org/simple（官方源）
### 快速切换显卡命令：
-   bash /workspace/assets/switch_cnb_yaml.sh H20
-   bash /workspace/assets/switch_cnb_yaml.sh L40

### 关闭开发环境
-   kill 1

### 激活ComfyUI虚拟空间
-   source /workspace/venv312/bin/activate

-   deactivate
-   pip install --upgrade numpy==1.26.4
-   pip install "numpy<2.4" --force-reinstall
                2.3.5
-   pip uninstall Torchao
-   pip uninstall pynvml
-   pip install nvidia-ml-py
    
### 软链接命令
-   ln -s /workspace/ComfyUI/models/prompt_generator/Qwen3-VL-8B-Instruct /workspace/ComfyUI/models/LLM/Qwen-VL
-   ln -s /workspace/输入 /workspace/ComfyUI/input
-   ln -s /workspace/ComfyUI/output /workspace/输出 
-   ln -s /workspace/工作流 /workspace/ComfyUI/user/default/workflows
-   ln -s /workspace/custom_nodes /workspace/ComfyUI/custom_nodes

### 下载命令
-   wget -O /models/vae/wan_2.1_vae.safetensors "https://cnb.cool/ai-models/Comfy-Org/Wan_2.1_ComfyUI_repackaged/-/lfs/2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b"

### 系统环境查看 （感谢sam大佬分享，代码由sam提供）
-   bash /workspace/assets/container_environment_query.sh

### 彻底清理本地仓库
-   git gc --prune=now --aggressive

### 查看子目录大小
-   du -h --max-depth=1

### 生成文件的SHA256哈希值
-   sha256sum 文件名
-   md5sum 

### 查看显卡占用
-   watch -n 1 nvidia-smi

### 查看系统性能
-   htop ； top

### 查找 /workspace 目录下的：.gitignore 文件
-   find /workspace -type f -name ".gitignore"

### 修复插件分支
-   bash /workspace/assets/Repair.sh

### ComfyUI-audio-separation-nodes 插件修改
-   修改了：/workspace/ComfyUI/custom_nodes/ComfyUI-audio-separation-nodes/src/separation.py  文件，让此插件使用的模型：/workspace/ComfyUI/models/audio_encoders/hdemucs_high_trained.pt 从本地加载，而不是每次下载到临时缓存目录。

###
-  修改了：/workspace/custom_nodes/ComfyUI-Whisper/apply_whisper.py 将模型（large-v3.pt）自动从H站下载修改为从CNB平台内部下载，