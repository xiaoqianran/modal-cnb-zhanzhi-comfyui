import json, os, subprocess

models_path = "/workspace/ComfyUI/models"  # 修改为新的路径
enable_custom_nodes_download = False  # True/False 启用/禁用 插件自动下载预设模型
# 注意：
# 1. 即使启用，也只有部分插件支持
# 2. 已知不兼容的插件：comfyui-custom-scripts、rgthree-comfy
# 3. 检测到不兼容的插件会禁用所有插件自动下载预设模型
incompatible_nodes = [
    "comfyui-custom-scripts",
    "rgthree-comfy"
]

# -------------------------- 完全保留原始代码的enable判断逻辑，未做任何修改 --------------------------
if enable_custom_nodes_download:
    for node in os.listdir("/workspace/custom_nodes"):
        if node.lower() in incompatible_nodes:
            enable_custom_nodes_download = False
if not enable_custom_nodes_download:
    print("已禁用插件自动下载预设模型")

# -------------------------- 按你的思路：先合并source_2和自定义下载链接.json（同结构） --------------------------
all_file_dict = {}  # 最终给原代码用的"自定义下载链接合并后字典"
sha256_dict = {}    # 用于合并时去重（source_2优先级 > 自定义链接）

# 1. 先加载source_2.json，存入all_file_dict（优先级最高）
source_2_path = "/workspace/assets/source_2.json"
if os.path.exists(source_2_path):
    try:
        with open(source_2_path, "r", encoding="utf-8") as f:
            source_2_data = json.load(f)
        for file_type in source_2_data:
            # 跳过说明文字，只处理模型类型（如checkpoints、diffusion_models）
            if file_type == "自定义下载链接说明：":
                continue
            # 确保是字典结构（避免非模型类型的无效数据）
            if not isinstance(source_2_data[file_type], dict):
                continue
            # 遍历source_2的文件条目，记录SHA256去重
            for file_path, url in source_2_data[file_type].items():
                current_sha256 = url.split("/-/lfs/")[-1] if "/-/lfs/" in url else ""
                if not current_sha256:
                    continue  # 跳过无SHA256的无效URL
                # 去重：已存在的SHA256不重复添加
                if file_type not in sha256_dict:
                    sha256_dict[file_type] = []
                if current_sha256 in sha256_dict[file_type]:
                    continue
                sha256_dict[file_type].append(current_sha256)
                # 存入合并字典
                if file_type not in all_file_dict:
                    all_file_dict[file_type] = {}
                all_file_dict[file_type][file_path] = url
        print("source_2.json加载并合并完成")
    except Exception as e:
        print(f"source_2.json加载错误: {e}")

# 2. 加载自定义下载链接.json，合并到all_file_dict（优先级低于source_2）
custom_path = "/workspace/自定义下载链接.json"
if os.path.exists(custom_path):
    try:
        with open(custom_path, "r", encoding="utf-8") as f:
            custom_data = json.load(f)
        for file_type in custom_data:
            if file_type == "自定义下载链接说明：":
                continue
            if not isinstance(custom_data[file_type], dict):
                continue
            # 遍历自定义链接条目，用SHA256去重（不覆盖source_2的内容）
            for file_path, url in custom_data[file_type].items():
                current_sha256 = url.split("/-/lfs/")[-1] if "/-/lfs/" in url else ""
                if not current_sha256:
                    continue
                if file_type not in sha256_dict:
                    sha256_dict[file_type] = []
                if current_sha256 in sha256_dict[file_type]:
                    continue
                sha256_dict[file_type].append(current_sha256)
                # 存入合并字典
                if file_type not in all_file_dict:
                    all_file_dict[file_type] = {}
                all_file_dict[file_type][file_path] = url
        print("自定义下载链接.json加载并合并完成")
    except Exception as e:
        print(f"自定义下载链接.json格式错误，无法加载: {e}")

# -------------------------- 修改后的source.json处理逻辑 --------------------------
source_file = "/workspace/assets/source.json"
if os.path.exists(source_file):
    with open(source_file, "r", encoding="utf-8") as file:
        source = json.load(file)
    for class_1st in source["path_dict"]:
        class_2nd_dict = source["path_dict"][class_1st]
        for class_2nd in class_2nd_dict:
            root_path = class_2nd_dict[class_2nd]
            if class_2nd not in source:
                continue
            class_2nd_file_dict = source[class_2nd]
            for file in class_2nd_file_dict:
                file_path = root_path + "/" + file
                # 修改这里：检测新的模型路径（修正版）
                if "/models/" in file_path and "/workspace/ComfyUI/models/" not in file_path:
                    file_path = file_path.split("/models/", 1)[-1]
                # 如果是新的路径格式
                elif "/workspace/ComfyUI/models/" in file_path:
                    file_path = file_path.split("/workspace/ComfyUI/models/", 1)[-1]
                else:
                    continue
                if "/" not in file_path:
                    continue
                file_type = file_path.split("/")[0]
                file_path = file_path.split("/")[-1]
                if file_path.endswith(".yaml"):
                    continue
                current_url = class_2nd_file_dict[file]
                current_sha256 = current_url.split("/-/lfs/")[-1]
                # 去重：跳过合并字典中已有的SHA256
                if file_type not in sha256_dict:
                    sha256_dict[file_type] = []
                if current_sha256 in sha256_dict[file_type]:
                    continue
                sha256_dict[file_type].append(current_sha256)
                # 合并到all_file_dict（原逻辑：路径冲突时重命名）
                if file_type not in all_file_dict:
                    all_file_dict[file_type] = {}
                if file_path in all_file_dict[file_type]:
                    record_url = all_file_dict[file_type][file_path]
                    record_sha256 = record_url.split("/-/lfs/")[-1]
                    if current_sha256 == record_sha256:
                        continue
                    else:
                        if "/-/lfs/" in current_url:
                            parts = current_url.split("/-/lfs/")[0].split("/")
                            file_path = parts[-2] + "/" + parts[-1] + "/" + file_path
                        else:
                            file_path = class_1st + "/" + class_2nd + "/" + file_path
                all_file_dict[file_type][file_path] = class_2nd_file_dict[file]
    # 原代码的排序逻辑
    for i in all_file_dict:
        sub_dict = all_file_dict[i]
        if isinstance(sub_dict, dict):
            all_file_dict[i] = {key: sub_dict[key] for key in sorted(sub_dict)}
    all_file_dict = {key: all_file_dict[key] for key in sorted(all_file_dict)}
    print("source.json处理完成")

# -------------------------- 修改后的函数部分 --------------------------
def import_models(directory, result):
    if "/workspace/ComfyUI/models/" in directory:  # 修改路径检测
        folder = directory.split("/workspace/ComfyUI/models/", 1)[-1]
        if folder in all_file_dict:
            for file in all_file_dict[folder]:
                if file not in result:
                    result.append(file)
    return result

def download_models(folder_name, filename):
    if not enable_custom_nodes_download:
        return None
    full_path = download_models2(folder_name, filename)
    return full_path

def download_models2(folder_name, filename):
    folder_list = [folder_name]
    folder_map_list = [
        ["unet", "diffusion_models"],
        ["clip", "text_encoders"]
    ]
    for folder_map in folder_map_list:
        if folder_name in folder_map:
            folder_list = folder_map
    for folder_name in folder_list:
        if folder_name in all_file_dict:
            file_dict = all_file_dict[folder_name]
            if filename in file_dict:
                url = file_dict[filename]
                file_path = os.path.join(models_path, folder_name, filename)  # 使用新的models_path
                folder_path = os.path.dirname(file_path)
                file_name = os.path.basename(file_path)
                os.makedirs(folder_path, exist_ok=True)
                subprocess.run(f'aria2c -x 4 -s 4 -c -d "{folder_path}" -o "{file_name}" "{url}"', shell=True)
                if os.path.isfile(file_path):
                    return file_path
    return None

def import_models2(directory, result):
    if "/workspace/ComfyUI/models/" in directory:  # 修改路径检测
        folder = directory.split("/workspace/ComfyUI/models/", 1)[-1]
        if folder in all_file_dict:
            for file in all_file_dict[folder]:
                found = False
                for file_info in result:
                    if file == file_info["name"]:
                        found = True
                        break
                if not found:
                    file_info = {
                        "name": file,
                        "pathIndex": 0,
                        "modified": 0,
                        "created": 0,
                        "size": 0
                    }
                    result.append(file_info)
    return result
