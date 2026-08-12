#!/usr/bin/env python3
"""
ComfyUI-RMBG SAM2 修复脚本
自动禁用 SAM2 模块以避免启动冲突
"""
 
import re
import os
import sys
from pathlib import Path
 
def apply_sam2_patch(file_path):
    """应用 SAM2 禁用补丁"""
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"❌ 错误: 文件不存在 {file_path}")
        return False
    
    # 读取原文件内容
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return False
    
    # 检查是否已经修复过
    disable_pattern = r'# \[SAM2_FIX\] 暂时禁用此模块'
    if re.search(disable_pattern, original_content, re.MULTILINE):
        print("✅ 文件已经修复过，无需重复修改")
        return True
    
    # 修复补丁内容
    patch_content = '''# [SAM2_FIX] 暂时禁用此模块以避免启动冲突
print("[ComfyUI-RMBG] SAM2Segment module temporarily disabled due to startup conflicts")
return  # 立即退出，避免执行可能造成冲突的代码
 
'''
    
    # 在文件开头插入修复补丁
    # 处理可能的编码声明
    lines = original_content.split('\n')
    
    # 找到第一行非注释、非空行
    insert_index = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            insert_index = i + 1
        else:
            break
    
    # 插入修复补丁
    lines.insert(insert_index, patch_content)
    
    # 添加标记到文件末尾，便于识别
    if not original_content.endswith('\n'):
        lines.append('')
    lines.append('# [SAM2_FIX_END] 文件已被 SAM2 修复脚本处理')
    
    # 写入修复后的内容
    fixed_content = '\n'.join(lines)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        
        print(f"✅ 成功应用 SAM2 修复补丁到: {file_path}")
        print("🔧 SAM2 模块已被禁用，ComfyUI 应该能正常启动")
        return True
        
    except Exception as e:
        print(f"❌ 写入文件失败: {e}")
        return False
 
def revert_sam2_patch(file_path):
    """恢复 SAM2 补丁"""
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"❌ 错误: 文件不存在 {file_path}")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return False
    
    # 检查是否有修复标记
    if '# [SAM2_FIX] 暂时禁用此模块' not in content:
        print("ℹ️ 文件未找到修复标记，可能未被修复过")
        return True
    
    # 移除修复补丁
    # 使用正则表达式移除从 [SAM2_FIX] 到 return 的部分
    pattern = r'# \[SAM2_FIX\] 暂时禁用此模块.*?return\s*# 立即退出，避免执行可能造成冲突的代码\s*\n?'
    content = re.sub(pattern, '', content, flags=re.DOTALL | re.MULTILINE)
    
    # 移除末尾的修复标记
    content = re.sub(r'# \[SAM2_FIX_END\] 文件已被 SAM2 修复脚本处理\s*$', '', content, flags=re.MULTILINE)
    
    # 清理多余的空行
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    content = content.rstrip() + '\n'
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 成功恢复 SAM2 补丁: {file_path}")
        print("🔄 SAM2 模块已恢复，可以重新使用")
        return True
        
    except Exception as e:
        print(f"❌ 写入文件失败: {e}")
        return False
 
def main():
    """主函数"""
    file_path = "/workspace/custom_nodes/comfyui-rmbg/AILab_SAM2Segment.py"
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "revert":
            print("🔄 恢复 SAM2 补丁...")
            revert_sam2_patch(file_path)
        elif sys.argv[1] == "help":
            print("用法:")
            print("  python fix_sam2.py          # 应用修复补丁")
            print("  python fix_sam2.py revert  # 恢复原始文件")
            print("  python fix_sam2.py help    # 显示帮助")
        else:
            print("❌ 未知参数，使用 'help' 查看用法")
    else:
        print("🔧 应用 SAM2 修复补丁...")
        apply_sam2_patch(file_path)
 
if __name__ == "__main__":
    main()