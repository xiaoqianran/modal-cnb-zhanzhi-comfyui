#!/usr/bin/env python3
"""
自动修复 ComfyUI-nunchaku 插件启动时自动下载模型的问题
使用正则表达式修改 /workspace/custom_nodes/ComfyUI-nunchaku/nodes/models/flux.py
"""
 
import re
import sys
from pathlib import Path
 
def apply_patch(file_path):
    """
    应用补丁到指定文件
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"错误: 文件不存在: {file_path}")
        return False
    
    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    print("正在应用补丁...")
    
    # === 修改 1: 在 INPUT_TYPES() 方法中移除 get_full_path_or_raise 调用 ===
    
    # 匹配 INPUT_TYPES() 方法中的文件检查逻辑
    pattern1 = r'(\s+# exclude the safetensors in the legacy svdquant folders\s+new_safetensor_files = \[\]\s+for safetensor_file in safetensor_files:\s+)safetensor_path = folder_paths\.get_full_path_or_raise\("diffusion_models", safetensor_file\)\s+safetensor_path = Path\(safetensor_path\)\s+if not \(safetensor_path\.parent / "config\.json"\)\.exists\(\):\s+new_safetensor_files\.append\(safetensor_file\)'
    
    replacement1 = r'\1# Note: File existence check moved to load_model() method to prevent auto-download on startup\n            new_safetensor_files.append(safetensor_file)'
    
    content = re.sub(pattern1, replacement1, content, flags=re.MULTILINE | re.DOTALL)
    
    # === 修改 2: 在 load_model() 方法中添加 legacy svdquant 检查逻辑 ===
    
    # 匹配 load_model() 方法中的文件路径获取部分
    pattern2 = r'(\s+if model_path\.endswith\(\("\.sft", "\.safetensors"\)\):\s+)model_path = Path\(folder_paths\.get_full_path_or_raise\("diffusion_models", model_path\)\)'
    
    replacement2 = r'\1model_path = Path(folder_paths.get_full_path_or_raise("diffusion_models", model_path))\n        \n        # Check if this is a legacy svdquant folder (moved from INPUT_TYPES method)\n        if not (model_path.parent / "config.json").exists():\n            raise FileNotFoundError(\n                f"Model file \'{model_path.name}\' appears to be in a legacy svdquant folder "\n                f"but config.json is missing. Please ensure the model is properly installed."\n            )'
    
    content = re.sub(pattern2, replacement2, content, flags=re.MULTILINE | re.DOTALL)
    
    # 检查是否有修改
    if content != original_content:
        # 创建备份
        backup_path = file_path.with_suffix('.py.backup')
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"已创建备份文件: {backup_path}")
        
        # 写入修改后的内容
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ 补丁应用成功！")
        print("修改内容:")
        print("1. 移除了 INPUT_TYPES() 方法中的 folder_paths.get_full_path_or_raise() 调用")
        print("2. 将 legacy svdquant 文件夹检查逻辑移动到 load_model() 方法中")
        print("3. 现在插件启动时不会自动下载模型，只有在实际加载模型时才会检查")
        return True
    else:
        print("⚠️  文件内容未发生变化，可能补丁已经应用过或文件结构已改变")
        return False
 
if __name__ == "__main__":
    target_file = "/workspace/custom_nodes/ComfyUI-nunchaku/nodes/models/flux.py"
    
    print("ComfyUI-nunchaku 自动下载模型修复补丁")
    print("=" * 50)
    print(f"目标文件: {target_file}")
    print()
    
    success = apply_patch(target_file)
    
    if success:
        print()
        print("使用说明:")
        print("- 重启 ComfyUI 后，启动时不会再自动下载模型")
        print("- 当你实际使用节点加载模型时，如果文件不存在会触发自动下载")
        print("- 如果需要恢复原文件，可以使用 .backup 备份文件")
    else:
        print()
        print("补丁应用失败，请检查文件是否存在或是否已被修改")
    
    sys.exit(0 if success else 1)