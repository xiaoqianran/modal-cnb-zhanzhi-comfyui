# ComfyUI源码修改

## 准备模型下载链接

为了实现自动下载模型，首先需要手工收集模型的下载链接，并保存到一个文件里。这里还需要指定模型的下载路径，建议使用json格式。

**注意**：

1. checkpoints、clip、clip_vision、controlnet、diffusion_models、loras、text_encoders、upscale_models、vae文件夹是由ComfyUI底层函数搜索的，可以通过hook源码实现自动下载。

2. 对于插件来说，得具体看插件是如何查找相关模型的，如果是调用ComfyUI底层函数，那该方法同样有效，否则无效。

示例：
```
{
    "checkpoints": {
        "hunyuan_dit_1.0.safetensors": "https://cnb.cool/ai-models/comfyanonymous/hunyuan_dit_comfyui/-/lfs/60ee5b765b40575c23a82cb4fec8e51e28157391e94397abf40d9546e81e1c58",
        "hunyuan_dit_1.1.safetensors": "https://cnb.cool/ai-models/comfyanonymous/hunyuan_dit_comfyui/-/lfs/26ab130e7bb515e976aa6d8fac8c3f11caef986c13140447ba102a4b1e675245",
        "hunyuan_dit_1.2.safetensors": "https://cnb.cool/ai-models/comfyanonymous/hunyuan_dit_comfyui/-/lfs/4fb84f84079cda457d171b3c6b15d1be95b5a3e5d9825703951a99ddf92d1787"
    },
    "clip_vision": {
        "clip_vision_g.safetensors": "https://cnb.cool/ai-models/comfyanonymous/clip_vision_g/-/lfs/9908329b3ead722a693ea400fab1d7c9ec91d6736fd194a94d20d793457f9c2e"
    }
}
```

## ComfyUI源码定位及修改

注意：这里主要是介绍修改思路/原理，本仓库中的实际代码可能有所不同，是针对实际情况优化修改的（如模型选项去重等，这里不再介绍）。

### folder_paths.py

#### 将预设模型添加到节点选项中

原始代码函数定位：

```
def recursive_search(directory: str, excluded_dir_names: list[str] | None=None) -> tuple[list[str], dict[str, float]]:
    if not os.path.isdir(directory):
        return [], {}

    if excluded_dir_names is None:
        excluded_dir_names = []

    result = []
    dirs = {}

    # Attempt to add the initial directory to dirs with error handling
    try:
        dirs[directory] = os.path.getmtime(directory)
    except FileNotFoundError:
        logging.warning(f"Warning: Unable to access {directory}. Skipping this path.")

    logging.debug("recursive file list on directory {}".format(directory))
    dirpath: str
    subdirs: list[str]
    filenames: list[str]

    for dirpath, subdirs, filenames in os.walk(directory, followlinks=True, topdown=True):
        subdirs[:] = [d for d in subdirs if d not in excluded_dir_names]
        for file_name in filenames:
            try:
                relative_path = os.path.relpath(os.path.join(dirpath, file_name), directory)
                result.append(relative_path)
            except:
                logging.warning(f"Warning: Unable to access {file_name}. Skipping this file.")
                continue

        for d in subdirs:
            path: str = os.path.join(dirpath, d)
            try:
                dirs[path] = os.path.getmtime(path)
            except FileNotFoundError:
                logging.warning(f"Warning: Unable to access {path}. Skipping this path.")
                continue

    logging.debug("found {} files".format(len(result)))
    return result, dirs
```

修改为：

```
# 导入json模块用来加载模型下载链接文件，导入subprocess模块用于后续调用aria2c下载模型
import json, subprocess

# 假设存放模型下载链接的文件是/workspace/source.json
source_file = "/workspace/source.json"
all_file_dict = {}
if os.path.exists(source_file):
    with open(source_file, "r", encoding="utf-8") as file:
        all_file_dict = json.load(file)

def recursive_search(directory: str, excluded_dir_names: list[str] | None=None) -> tuple[list[str], dict[str, float]]:
    if not os.path.isdir(directory):
        return [], {}

    if excluded_dir_names is None:
        excluded_dir_names = []

    result = []
    dirs = {}

    # Attempt to add the initial directory to dirs with error handling
    try:
        dirs[directory] = os.path.getmtime(directory)
    except FileNotFoundError:
        logging.warning(f"Warning: Unable to access {directory}. Skipping this path.")

    logging.debug("recursive file list on directory {}".format(directory))
    dirpath: str
    subdirs: list[str]
    filenames: list[str]

    for dirpath, subdirs, filenames in os.walk(directory, followlinks=True, topdown=True):
        subdirs[:] = [d for d in subdirs if d not in excluded_dir_names]
        for file_name in filenames:
            try:
                relative_path = os.path.relpath(os.path.join(dirpath, file_name), directory)
                result.append(relative_path)
            except:
                logging.warning(f"Warning: Unable to access {file_name}. Skipping this file.")
                continue

        for d in subdirs:
            path: str = os.path.join(dirpath, d)
            try:
                dirs[path] = os.path.getmtime(path)
            except FileNotFoundError:
                logging.warning(f"Warning: Unable to access {path}. Skipping this path.")
                continue

    # 将all_file_dict中的模型添加到节点选项中，这里注意models文件夹的实际绝对位置
    if "/workspace/ComfyUI/models/" in directory:
        folder = directory.split("/workspace/ComfyUI/models/")[-1]
        if folder in all_file_dict:
            for file in all_file_dict[folder]:
                # 跳过已经存在的文件选项
                if file not in result:
                    result.append(file)

    logging.debug("found {} files".format(len(result)))
    return result, dirs
```

#### 当文件不存在时自动下载

原始代码函数定位：

```
def get_full_path_or_raise(folder_name: str, filename: str) -> str:
    """
    Get the full path of a file in a folder, has to be a file
    """
    full_path = get_full_path(folder_name, filename)

    if full_path is None:
        raise FileNotFoundError(f"Model in folder '{folder_name}' with filename '{filename}' not found.")
    return full_path
```

修改为：

```
def get_full_path_or_raise(folder_name: str, filename: str) -> str:
    """
    Get the full path of a file in a folder, has to be a file
    """
    full_path = get_full_path(folder_name, filename)

    # 当没有找到模型时，尝试下载，注意models_path的位置，本仓库的.cnb.yml中将/models挂载在云节点缓存里
    if full_path is None:
        models_path = "/models"
        url = ""
        if folder_name in all_file_dict:
            file_dict = all_file_dict[folder_name]
            if filename in file_dict:
                url = file_dict[filename]
                file_path = os.path.join(models_path, folder_name, filename)
                folder_path = os.path.dirname(file_path)
                file_name = os.path.basename(file_path)
                os.makedirs(folder_path, exist_ok=True)
                subprocess.run(f'aria2c -x 4 -s 4 -c -d "{folder_path}" -o "{file_name}" "{url}"', shell=True)
                if os.path.isfile(file_path):
                    full_path = file_path

    if full_path is None:
        raise FileNotFoundError(f"Model in folder '{folder_name}' with filename '{filename}' not found.")
    return full_path
```

### app/model_manager.py

#### 将预设模型添加到UI界面选项中

将预设模型添加到UI界面选项中，主要是避免UI界面弹出模型缺失的提示

原始代码函数定位：

```
    def recursive_search_models_(self, directory: str, pathIndex: int) -> tuple[list[str], dict[str, float], float]:
        if not os.path.isdir(directory):
            return [], {}, time.perf_counter()

        excluded_dir_names = [".git"]
        # TODO use settings
        include_hidden_files = False

        result: list[str] = []
        dirs: dict[str, float] = {}

        for dirpath, subdirs, filenames in os.walk(directory, followlinks=True, topdown=True):
            subdirs[:] = [d for d in subdirs if d not in excluded_dir_names]
            if not include_hidden_files:
                subdirs[:] = [d for d in subdirs if not d.startswith(".")]
                filenames = [f for f in filenames if not f.startswith(".")]

            filenames = filter_files_extensions(filenames, folder_paths.supported_pt_extensions)

            for file_name in filenames:
                try:
                    full_path = os.path.join(dirpath, file_name)
                    relative_path = os.path.relpath(full_path, directory)

                    # Get file metadata
                    file_info = {
                        "name": relative_path,
                        "pathIndex": pathIndex,
                        "modified": os.path.getmtime(full_path),  # Add modification time
                        "created": os.path.getctime(full_path),   # Add creation time
                        "size": os.path.getsize(full_path)        # Add file size
                    }
                    result.append(file_info)

                except Exception as e:
                    logging.warning(f"Warning: Unable to access {file_name}. Error: {e}. Skipping this file.")
                    continue

            for d in subdirs:
                path: str = os.path.join(dirpath, d)
                try:
                    dirs[path] = os.path.getmtime(path)
                except FileNotFoundError:
                    logging.warning(f"Warning: Unable to access {path}. Skipping this path.")
                    continue

        return result, dirs, time.perf_counter()
```

修改为：

```
    def recursive_search_models_(self, directory: str, pathIndex: int) -> tuple[list[str], dict[str, float], float]:
        if not os.path.isdir(directory):
            return [], {}, time.perf_counter()

        excluded_dir_names = [".git"]
        # TODO use settings
        include_hidden_files = False

        result: list[str] = []
        dirs: dict[str, float] = {}

        for dirpath, subdirs, filenames in os.walk(directory, followlinks=True, topdown=True):
            subdirs[:] = [d for d in subdirs if d not in excluded_dir_names]
            if not include_hidden_files:
                subdirs[:] = [d for d in subdirs if not d.startswith(".")]
                filenames = [f for f in filenames if not f.startswith(".")]

            filenames = filter_files_extensions(filenames, folder_paths.supported_pt_extensions)

            for file_name in filenames:
                try:
                    full_path = os.path.join(dirpath, file_name)
                    relative_path = os.path.relpath(full_path, directory)

                    # Get file metadata
                    file_info = {
                        "name": relative_path,
                        "pathIndex": pathIndex,
                        "modified": os.path.getmtime(full_path),  # Add modification time
                        "created": os.path.getctime(full_path),   # Add creation time
                        "size": os.path.getsize(full_path)        # Add file size
                    }
                    result.append(file_info)

                except Exception as e:
                    logging.warning(f"Warning: Unable to access {file_name}. Error: {e}. Skipping this file.")
                    continue

            for d in subdirs:
                path: str = os.path.join(dirpath, d)
                try:
                    dirs[path] = os.path.getmtime(path)
                except FileNotFoundError:
                    logging.warning(f"Warning: Unable to access {path}. Skipping this path.")
                    continue


        # 添加预设模型，这里同样注意models文件夹的实际绝对路径
        if "/workspace/ComfyUI/models/" in directory:
            folder = directory.split("/workspace/ComfyUI/models/")[-1]

            # 从folder_paths.py中导入all_file_dict
            from folder_paths import all_file_dict

            if folder in all_file_dict:
                for file in all_file_dict[folder]:
                    found = False
                    for file_info in result:
                        if file == file_info["name"]:
                            found = True
                    if not found:
                        # 注意这里的file_info，实际上应包括pathIndex、modified、created、size四个参数，这里设置为0就可以避免弹出缺少模型的提示了
                        # 但都设置为0，在UI界面中，点击模型库模块里的模型，可能没有反应
                        file_info = {
                            "name": file,
                            "pathIndex": 0,
                            "modified": 0,
                            "created": 0,
                            "size": 0
                        }
                        result.append(file_info)
                        

        return result, dirs, time.perf_counter()
```

### extra_model_paths.yaml

该文件主要是添加额外的模型搜索路径，这里添加/models文件夹，是为了把自动下载的模型缓存在云节点上。需要搭配.cnb.yml文件设置。

```
comfyui:
     base_path: /models/

     checkpoints: checkpoints/
     clip: clip/
     clip_vision: clip_vision/
     configs: configs/
     controlnet: controlnet/
     diffusion_models: |
                  diffusion_models
                  unet
     embeddings: embeddings/
     loras: loras/
     upscale_models: upscale_models/
     vae: vae/
```

### .cnb.yml

通过volumes设置缓存文件夹/models

```
$:
  vscode:
    - docker:
        image: docker.cnb.cool/cnb-xu/docker/comfyui:latest
        volumes:
          - /models
```