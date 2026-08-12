#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAM2 Import Fix Patch for ComfyUI-Impact-Pack
自动修复SAM2导入问题的补丁脚本
"""
 
import re
import os
import sys
from datetime import datetime
 
class SAM2ImportFixer:
    def __init__(self, file_path):
        self.file_path = file_path
        self.patch_marker = "# [SAMPL2_PATCH] - Modified by SAM2 fixer"
        self.backup_suffix = ".backup_sam2_fix"
        
    def is_already_patched(self, content):
        """检查文件是否已经被修改过"""
        return self.patch_marker in content
    
    def backup_file(self):
        """创建文件备份"""
        backup_path = self.file_path + self.backup_suffix
        try:
            with open(self.file_path, 'r', encoding='utf-8') as original:
                with open(backup_path, 'w', encoding='utf-8') as backup:
                    backup.write(original.read())
            print(f"✓ 备份文件已创建: {backup_path}")
            return True
        except Exception as e:
            print(f"✗ 备份文件失败: {e}")
            return False
    
    def fix_sam2_imports(self, content):
        """修复SAM2导入问题"""
        
        # 定义正则表达式模式
        patterns = {
            # 匹配SAM2可用性检查
            'sam2_check': re.compile(r'^(\s*)(is_sam2_available\s*=\s*importlib\.util\.find_spec\("sam2"\))', re.MULTILINE),
            
            # 匹配SAM2不可用消息
            'sam2_message': re.compile(r'^(\s*)(sam2_unavailable_message\s*=\s*f".*?")', re.MULTILINE | re.DOTALL),
            
            # 匹配整个if-else块
            'sam2_import_block': re.compile(
                r'^(\s*if is_sam2_available:.*?\n\s*from sam2\.sam2_image_predictor import SAM2ImagePredictor\n\s*from sam2\.build_sam import build_sam2, build_sam2_video_predictor\n\s*else:\n\s*logging\.warning\(sam2_unavailable_message\))',
                re.MULTILINE | re.DOTALL
            )
        }
        
        modified_content = content
        
        # 1. 注释掉SAM2可用性检查
        def replace_sam2_check(match):
            indent = match.group(1)
            line = match.group(2)
            return f"{indent}# [SAMPL2_PATCH] {line}\n{indent}# [SAMPL2_PATCH] Disabled SAM2 check to prevent import errors\n{indent}is_sam2_available = False"
        
        modified_content = patterns['sam2_check'].sub(replace_sam2_check, modified_content)
        
        # 2. 注释掉SAM2消息定义
        def replace_sam2_message(match):
            indent = match.group(1)
            line = match.group(2)
            return f"{indent}# [SAMPL2_PATCH] {line}\n{indent}# [SAMPL2_PATCH] SAM2 message disabled"
        
        modified_content = patterns['sam2_message'].sub(replace_sam2_message, modified_content)
        
        # 3. 注释掉整个导入块
        def replace_import_block(match):
            block = match.group(1)
            lines = block.split('\n')
            commented_lines = []
            
            for line in lines:
                if line.strip():
                    # 获取缩进
                    indent_match = re.match(r'^(\s*)', line)
                    indent = indent_match.group(1) if indent_match else ""
                    commented_lines.append(f"{indent}# [SAMPL2_PATCH] {line.strip()}")
                else:
                    commented_lines.append("")
            
            return '\n'.join(commented_lines)
        
        modified_content = patterns['sam2_import_block'].sub(replace_import_block, modified_content)
        
        # 4. 添加修复说明注释
        fix_comment = f"""
# [SAMPL2_PATCH] - SAM2 Import Fix Applied
# [SAMPL2_PATCH] Modified by automatic fixer on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# [SAMPL2_PATCH] Reason: SAM2 dependency not available, preventing ComfyUI startup
# [SAMPL2_PATCH] To restore SAM2 functionality, install: pip install git+https://github.com/facebookresearch/segment-anything-2.git
"""
        
        # 在文件开头添加修复说明
        modified_content = fix_comment + modified_content
        
        return modified_content
    
    def apply_fix(self):
        """应用修复"""
        print(f"🔧 开始修复文件: {self.file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(self.file_path):
            print(f"✗ 文件不存在: {self.file_path}")
            return False
        
        # 读取原文件
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"✗ 读取文件失败: {e}")
            return False
        
        # 检查是否已经修复过
        if self.is_already_patched(content):
            print("✓ 文件已经被修复过，跳过修改")
            return True
        
        # 创建备份
        if not self.backup_file():
            print("✗ 备份失败，中止修改")
            return False
        
        # 应用修复
        try:
            modified_content = self.fix_sam2_imports(content)
            
            # 写回文件
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            print("✓ SAM2导入修复完成")
            print("✓ 已重新启动ComfyUI应该能正常启动")
            return True
            
        except Exception as e:
            print(f"✗ 修复失败: {e}")
            # 尝试恢复备份
            try:
                backup_path = self.file_path + self.backup_suffix
                if os.path.exists(backup_path):
                    with open(backup_path, 'r', encoding='utf-8') as backup:
                        with open(self.file_path, 'w', encoding='utf-8') as original:
                            original.write(backup.read())
                    print("✓ 已恢复原文件")
            except:
                pass
            return False
 
def main():
    """主函数"""
    print("=== SAM2 Import Fixer for ComfyUI-Impact-Pack ===")
    
    # 目标文件路径
    target_file = "/workspace/ComfyUI/custom_nodes/comfyui-impact-pack/modules/impact/core.py"
    
    # 创建修复器实例
    fixer = SAM2ImportFixer(target_file)
    
    # 应用修复
    success = fixer.apply_fix()
    
    if success:
        print("\n✅ 修复成功完成！")
        print("\n📋 修复说明:")
        print("- 已注释掉SAM2相关导入")
        print("- 创建了备份文件")
        print("- 添加了防止重复修改的标记")
        print("\n💡 提示:")
        print("- 现在可以重启ComfyUI")
        print("- 如需恢复SAM2功能，请安装: pip install git+https://github.com/facebookresearch/segment-anything-2.git")
        print("- 备份文件位于: core.py.backup_sam2_fix")
    else:
        print("\n❌ 修复失败")
        print("请检查文件路径和权限")
        return 1
    
    return 0
 
if __name__ == "__main__":
    sys.exit(main())