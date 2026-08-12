import os

os.chdir("/workspace")

def replace_str(path, old_str, new_str):
    if os.path.exists(path):
        with open(path, "r") as file:
            content = file.read()
        
        # 重复检测：如果新内容已存在，则跳过修改
        if new_str in content:
            print(f"已检测到 {path} 已包含目标修改，跳过替换")
            return
        
        # 检查旧内容是否存在，不存在则无需修改
        if old_str not in content:
            return
        
        # 执行替换并写入文件
        content = content.replace(old_str, new_str)
        with open(path, "w") as file:
            file.write(content)
        print(f"成功修改 {path}")

def patch_comfyui(root_path="ComfyUI"):  # 路径已改为 ComfyUI
    path = os.path.join(root_path, "folder_paths.py")
    if os.path.exists(path):
        source_code = r"""import os
import time"""
        patch_code = r"""import os
import hook_cnb_xu
import time"""
        replace_str(path, source_code, patch_code)
        
        source_code = r"""continue
    logging.debug("found {} files".format(len(result)))"""
        patch_code = r"""continue
    result = hook_cnb_xu.import_models(directory, result)
    logging.debug("found {} files".format(len(result)))"""
        replace_str(path, source_code, patch_code)
        
        source_code = r"""logging.warning("WARNING path {} exists but doesn't link anywhere, skipping.".format(full_path))

    return None"""
        patch_code = r"""logging.warning("WARNING path {} exists but doesn't link anywhere, skipping.".format(full_path))
    full_path = hook_cnb_xu.download_models(folder_name, filename)
    return full_path
    return None"""
        replace_str(path, source_code, patch_code)
        
        source_code = r"""full_path = get_full_path(folder_name, filename)
    if full_path is None:
        raise FileNotFoundError("""
        patch_code = r"""full_path = get_full_path(folder_name, filename)
    if full_path is None:
        full_path = hook_cnb_xu.download_models2(folder_name, filename)
    if full_path is None:
        raise FileNotFoundError("""
        replace_str(path, source_code, patch_code)
    
    path = os.path.join(root_path, "app/model_manager.py")
    if os.path.exists(path):
        source_code = r"""continue

        return result, dirs"""
        patch_code = r"""continue
        import hook_cnb_xu
        result = hook_cnb_xu.import_models2(directory, result)
        return result, dirs"""
        replace_str(path, source_code, patch_code)

patch_comfyui()