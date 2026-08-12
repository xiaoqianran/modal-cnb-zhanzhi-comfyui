import os
import re
import logging

# 目标文件路径
NODES_FILE = "/workspace/custom_nodes/ComfyUI-WanVideoWrapper/nodes_model_loading.py"
BACKUP_FILE = f"{NODES_FILE}.safe_backup"
# 精确匹配原始函数（不匹配已替换的函数）
REPLACE_PATTERN = r"\bfolder_paths\.get_full_path\b"  # \b 是单词边界，避免匹配已替换的函数
TARGET_FUNC = "folder_paths.get_full_path_or_raise"
# 唯一标记（确保幂等性）
PATCH_MARKER = "# 幂等补丁标记：get_full_path已安全替换"

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="[安全补丁] %(levelname)s: %(message)s"
)

def validate_file():
    if not os.path.exists(NODES_FILE):
        logging.error(f"文件不存在：{NODES_FILE}")
        return False
    return True

def create_backup():
    if os.path.exists(BACKUP_FILE):
        logging.warning(f"备份已存在：{BACKUP_FILE}")
        return True
    try:
        with open(NODES_FILE, "r", encoding="utf-8") as f_src, \
             open(BACKUP_FILE, "w", encoding="utf-8") as f_dst:
            f_dst.write(f_src.read())
        logging.info(f"已创建备份：{BACKUP_FILE}")
        return True
    except Exception as e:
        logging.error(f"备份失败：{e}")
        return False

def safe_replace():
    try:
        with open(NODES_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logging.error(f"读取文件失败：{e}")
        return False

    # 检查是否已打过补丁（通过标记）
    if PATCH_MARKER in content:
        logging.info("文件已处理，无需重复操作")
        return True

    # 仅替换原始函数（避免匹配已替换的结果）
    match_count = len(re.findall(REPLACE_PATTERN, content))
    if match_count == 0:
        logging.warning("未找到需要替换的原始函数，可能已处理")
        return True

    # 执行替换
    new_content = re.sub(REPLACE_PATTERN, TARGET_FUNC, content)
    # 添加防重复标记
    new_content += f"\n{PATCH_MARKER}\n"

    try:
        with open(NODES_FILE, "w", encoding="utf-8") as f:
            f.write(new_content)
        logging.info(f"成功替换 {match_count} 处原始函数")
        return True
    except Exception as e:
        logging.error(f"写入失败：{e}")
        return False

def main():
    logging.info("=" * 60)
    logging.info("启动幂等性补丁（支持重复运行）")
    logging.info("=" * 60)

    if not validate_file():
        return
    if not create_backup():
        return
    if safe_replace():
        logging.info("\n操作完成：函数替换已安全执行")
        logging.info(f"原始函数：folder_paths.get_full_path")
        logging.info(f"替换后：{TARGET_FUNC}")
    else:
        logging.error("\n操作失败，请检查日志")

if __name__ == "__main__":
    main()
