import os
import re
import logging
import sys  # 用于处理命令行参数

# -------------------------- 配置 --------------------------
# 默认路径（如果未通过命令行指定则使用）
DEFAULT_NODES_FILE = "/workspace/ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper/nodes_model_loading.py"
BACKUP_SUFFIX = ".safe_backup"  # 备份文件后缀
REPLACE_PATTERN = r"\bfolder_paths\.get_full_path\b"  # 精确匹配原始函数
TARGET_FUNC = "folder_paths.get_full_path_or_raise"
PATCH_MARKER = "# 幂等补丁标记：get_full_path已安全替换"

# -------------------------- 日志配置 --------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[安全补丁] %(levelname)s: %(message)s"
)

# -------------------------- 核心功能 --------------------------
def get_target_file():
    """从命令行参数获取目标文件路径，若无则使用默认路径"""
    if len(sys.argv) > 1:
        # 取第一个命令行参数作为目标文件
        return sys.argv[1]
    else:
        logging.warning(f"未指定目标文件，将使用默认路径：{DEFAULT_NODES_FILE}")
        return DEFAULT_NODES_FILE

def validate_file(file_path):
    """验证目标文件是否有效"""
    if not os.path.exists(file_path):
        logging.error(f"错误：文件不存在 -> {file_path}")
        return False
    if not os.path.isfile(file_path):
        logging.error(f"错误：路径不是有效文件 -> {file_path}")
        return False
    if not file_path.endswith(".py"):
        logging.warning(f"警告：目标文件不是Python文件（.py），仍将尝试处理")
    return True

def create_backup(file_path):
    """为目标文件创建备份"""
    backup_path = f"{file_path}{BACKUP_SUFFIX}"
    if os.path.exists(backup_path):
        logging.warning(f"备份文件已存在，跳过备份 -> {backup_path}")
        return True
    try:
        with open(file_path, "r", encoding="utf-8") as f_src, \
             open(backup_path, "w", encoding="utf-8") as f_dst:
            f_dst.write(f_src.read())
        logging.info(f"已创建备份文件 -> {backup_path}")
        return True
    except Exception as e:
        logging.error(f"备份失败：{str(e)}")
        return False

def safe_replace(file_path):
    """安全替换目标文件中的函数"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logging.error(f"读取文件失败：{str(e)}")
        return False

    # 检查是否已打过补丁
    if PATCH_MARKER in content:
        logging.info("文件已处理，无需重复操作")
        return True

    # 统计需要替换的数量
    match_count = len(re.findall(REPLACE_PATTERN, content))
    if match_count == 0:
        logging.warning("未找到需要替换的原始函数，可能已处理或不适用")
        return True

    # 执行替换
    new_content = re.sub(REPLACE_PATTERN, TARGET_FUNC, content)
    new_content += f"\n{PATCH_MARKER}\n"

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        logging.info(f"成功替换 {match_count} 处函数调用")
        return True
    except Exception as e:
        logging.error(f"写入文件失败：{str(e)}")
        return False

# -------------------------- 执行入口 --------------------------
def main():
    logging.info("=" * 60)
    logging.info("启动支持命令行参数的幂等性补丁")
    logging.info("=" * 60)

    # 1. 获取目标文件路径
    target_file = get_target_file()
    logging.info(f"目标文件：{target_file}")

    # 2. 验证文件有效性
    if not validate_file(target_file):
        return

    # 3. 创建备份
    if not create_backup(target_file):
        return

    # 4. 执行替换
    if safe_replace(target_file):
        logging.info("\n" + "=" * 60)
        logging.info("操作完成：函数替换已安全执行")
        logging.info(f"原始函数：folder_paths.get_full_path")
        logging.info(f"替换后：{TARGET_FUNC}")
        logging.info("=" * 60)
    else:
        logging.error("\n" + "=" * 60)
        logging.error("操作失败，请检查日志")
        logging.error("=" * 60)

if __name__ == "__main__":
    main()
