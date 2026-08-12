# -*- coding: utf-8 -*-
"""
📝 脚本名称：ComfyUI 汉化工作流全家桶 (班长版 V41 - 终极地址适配版)
📅 更新日期：2025年
👨‍🏫 作者：班长
💻 适用环境：Windows 11 / Mac / Linux + ComfyUI
🛠️ V41 修复日志：
    1. 【地址适配】针对 Custom 模式，自动识别并补全 `/v1/chat/completions`。
       - 完美支持如 `https://ai.t8star.cn` 这类仅填写域名的中转站地址。
    2. 【防拦截】增加了 User-Agent 伪装，防止被服务端 WAF 拦截返回 HTML 验证页。
    3. 【调试日志】在控制台明确打印最终拼接的 API URL，所见即所得。
"""

import os
import json
import inspect
import nodes
import folder_paths
import urllib.request
import urllib.error
import ssl
import torch
import numpy as np
from PIL import Image
import io
import base64
import random
import ast
import time
import re
import sys
import hashlib
import gc
import platform
import psutil
import threading 
import traceback 
from enum import Enum
from pathlib import Path

# 尝试导入 Transformers (本地推理核心)
try:
    from transformers import AutoModelForImageTextToText, AutoProcessor, AutoTokenizer, AutoConfig, BitsAndBytesConfig, TextIteratorStreamer, StoppingCriteria, StoppingCriteriaList
    from huggingface_hub import snapshot_download as hf_snapshot_download
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("👨‍🏫 班长提示：未检测到 transformers 库，本地模型功能将不可用 (API 模式不受影响)。")

# 尝试导入 ModelScope
try:
    from modelscope.hub.snapshot_download import snapshot_download as ms_snapshot_download
    MODELSCOPE_AVAILABLE = True
except ImportError:
    MODELSCOPE_AVAILABLE = False

print("👨‍🏫 班长提示：正在加载汉化全家桶 (V41 终极地址适配版)...")

# ================= 🛠️ 全局缓存与工具 =================

MODEL_CACHE = {}
PROCESSOR_CACHE = {}
TOKENIZER_CACHE = {}
INTERRUPT_EVENT = threading.Event()

def clear_global_cache():
    global MODEL_CACHE, PROCESSOR_CACHE, TOKENIZER_CACHE
    MODEL_CACHE.clear()
    PROCESSOR_CACHE.clear()
    TOKENIZER_CACHE.clear()
    gc.collect()
    if torch.cuda.is_available(): torch.cuda.empty_cache()

def get_vram_info():
    """获取当前显存使用情况"""
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        return f"{allocated:.2f}GB (已用) / {reserved:.2f}GB (预留)"
    return "N/A"

class AnyType(str):
    def __ne__(self, __value: object) -> bool: return False

class AnyObject:
    def __init__(self): 
        self.shape = (1, 512, 512, 3)
        self.device = "cpu"
        self.dtype = torch.float32
    def __getattr__(self, name): return self
    def __getitem__(self, key): return self
    def __call__(self, *args, **kwargs): return self
    def __str__(self): return "Universal_Mock_String"
    def __eq__(self, other): return True
    def __ne__(self, other): return False

class StreamStoppingCriteria(StoppingCriteria):
    def __init__(self): pass
    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        return INTERRUPT_EVENT.is_set()

# ================= 1. 万能空对象节点 =================

class BanzhangAnyOutputNode:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {}}
    RETURN_TYPES = (AnyType("*"),) 
    RETURN_NAMES = ("🧩 万能输入源",)
    FUNCTION = "do_nothing"
    CATEGORY = "👨‍🏫班长/辅助工具"
    def do_nothing(self): return (AnyObject(),)

# ================= 📦 Qwen 本地推理组件 =================

class Quantization(str, Enum):
    Q4_BIT = "4-bit (节省显存)"
    Q8_BIT = "8-bit (平衡)"
    NONE = "None (FP16)"
    @classmethod
    def get_values(cls): return [item.value for item in cls]

# 班长 V19: 纯净 Qwen3 版
DEFAULT_MODEL_CONFIGS = {
    # --- Qwen3-VL Series ---
    "Qwen3-VL-2B-Instruct": { "repo_id": "Qwen/Qwen3-VL-2B-Instruct", "default": True, "quantized": False, "vram_requirement": { "full": 4.0, "8bit": 2.5, "4bit": 1.5 } },
    "Qwen3-VL-2B-Thinking": { "repo_id": "Qwen/Qwen3-VL-2B-Thinking", "default": False, "quantized": False, "vram_requirement": { "full": 4.0, "8bit": 2.5, "4bit": 1.5 } },
    "Qwen3-VL-2B-Instruct-FP8": { "repo_id": "Qwen/Qwen3-VL-2B-Instruct-FP8", "default": False, "quantized": True, "vram_requirement": { "full": 2.5 } },
    "Qwen3-VL-2B-Thinking-FP8": { "repo_id": "Qwen/Qwen3-VL-2B-Thinking-FP8", "default": False, "quantized": True, "vram_requirement": { "full": 2.5 } },
    
    "Qwen3-VL-4B-Instruct": { "repo_id": "Qwen/Qwen3-VL-4B-Instruct", "default": True, "quantized": False, "vram_requirement": { "full": 6.0, "8bit": 3.5, "4bit": 2.0 } },
    "Qwen3-VL-4B-Thinking": { "repo_id": "Qwen/Qwen3-VL-4B-Thinking", "default": False, "quantized": False, "vram_requirement": { "full": 6.0, "8bit": 3.5, "4bit": 2.0 } },
    "Qwen3-VL-4B-Instruct-FP8": { "repo_id": "Qwen/Qwen3-VL-4B-Instruct-FP8", "default": False, "quantized": True, "vram_requirement": { "full": 2.5 } },
    "Qwen3-VL-4B-Thinking-FP8": { "repo_id": "Qwen/Qwen3-VL-4B-Thinking-FP8", "default": False, "quantized": True, "vram_requirement": { "full": 2.5 } },
    
    "Qwen3-VL-8B-Instruct": { "repo_id": "Qwen/Qwen3-VL-8B-Instruct", "default": False, "quantized": False, "vram_requirement": { "full": 12.0, "8bit": 7.0, "4bit": 4.5 } },
    "Qwen3-VL-8B-Thinking": { "repo_id": "Qwen/Qwen3-VL-8B-Thinking", "default": False, "quantized": False, "vram_requirement": { "full": 12.0, "8bit": 7.0, "4bit": 4.5 } },
    "Qwen3-VL-8B-Instruct-FP8": { "repo_id": "Qwen/Qwen3-VL-8B-Instruct-FP8", "default": False, "quantized": True, "vram_requirement": { "full": 7.5 } },
    "Qwen3-VL-8B-Thinking-FP8": { "repo_id": "Qwen/Qwen3-VL-8B-Thinking-FP8", "default": False, "quantized": True, "vram_requirement": { "full": 7.5 } },
    
    "Qwen3-VL-32B-Instruct": { "repo_id": "Qwen/Qwen3-VL-32B-Instruct", "default": False, "quantized": False, "vram_requirement": { "full": 28.0, "8bit": 14.0, "4bit": 8.5 } },
    "Qwen3-VL-32B-Thinking": { "repo_id": "Qwen/Qwen3-VL-32B-Thinking", "default": False, "quantized": False, "vram_requirement": { "full": 28.0, "8bit": 14.0, "4bit": 8.5 } },
    "Qwen3-VL-32B-Instruct-FP8": { "repo_id": "Qwen/Qwen3-VL-32B-Instruct-FP8", "default": False, "quantized": True, "vram_requirement": { "full": 24.0 } },
    "Qwen3-VL-32B-Thinking-FP8": { "repo_id": "Qwen/Qwen3-VL-32B-Thinking-FP8", "default": False, "quantized": True, "vram_requirement": { "full": 24.0 } },
    
    # --- Others ---
    "Huihui-Qwen3-VL-4B-Instruct-Abliterated": { "repo_id": "fireicewolf/Huihui-Qwen3-VL-4B-Instruct-abliterated", "source": "modelscope", "default": False, "quantized": False, "abliterated": True, "warning": "此模型已移除安全过滤，可能生成敏感内容。仅用于研究和测试环境。" },
    "Huihui-Qwen3-VL-8B-Instruct-Abliterated": { "repo_id": "huihui-ai/Huihui-Qwen3-VL-8B-Instruct-abliterated", "default": False, "quantized": False, "abliterated": True, "warning": "此模型已移除安全过滤，可能生成敏感内容。仅用于研究和测试环境。" }
}

MODEL_CONFIGS = DEFAULT_MODEL_CONFIGS.copy()

# 尝试加载外部配置文件
try:
    current_dir = Path(__file__).parent
    config_path = current_dir / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            external_configs = json.load(f)
            models_only = {k: v for k, v in external_configs.items() if not k.startswith('_')}
            MODEL_CONFIGS.update(models_only)
            print("👨‍🏫 班长：已加载外部 config.json 配置。")
except Exception as e:
    print(f"👨‍🏫 班长：使用内置全套模型库。")

class ImageProcessor:
    _cache = {}
    def to_pil(self, image_tensor: torch.Tensor, max_side: int = 0) -> Image.Image:
        """转换并可选缩放图像"""
        tensor_id = id(image_tensor)
        
        if image_tensor.dim() == 4: image_tensor = image_tensor[0]
        image_np = (image_tensor.cpu().numpy() * 255).astype(np.uint8)
        pil_image = Image.fromarray(image_np)
        
        # V25: 图像缩放逻辑
        if max_side > 0:
            w, h = pil_image.size
            if max(w, h) > max_side:
                ratio = max_side / max(w, h)
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)
        
        return pil_image

class ModelDownloader:
    def __init__(self):
        base_models_dir = None
        try:
            if hasattr(folder_paths, "models_dir"):
                base_models_dir = Path(folder_paths.models_dir)
        except: pass
            
        if base_models_dir is None or not base_models_dir.exists():
            try:
                comfy_root = Path(__file__).parent.parent.parent
                base_models_dir = comfy_root / "models"
            except: pass
        
        if base_models_dir:
            self.models_dir = base_models_dir / "prompt_generator"
        else:
            self.models_dir = Path(__file__).parent / "models" / "prompt_generator"
            
        self.models_dir.mkdir(parents=True, exist_ok=True)
        print(f"👨‍🏫 班长：本地模型存储路径已锁定 -> {self.models_dir.absolute()}")

    def ensure_model_available(self, model_name):
        model_info = MODEL_CONFIGS.get(model_name)
        if not model_info: raise ValueError(f"未知模型: {model_name}")
        
        repo_id = model_info['repo_id']
        source = model_info.get('source', 'huggingface')
        model_folder_name = repo_id.split('/')[-1]
        model_path = self.models_dir / model_folder_name
        
        if model_path.exists() and (model_path / "config.json").exists():
            return str(model_path)
            
        print(f"📥 正在从 {source} 下载模型 '{model_name}'...")
        print(f"📂 目标路径: {model_path}")
        
        if source == 'modelscope':
            if not MODELSCOPE_AVAILABLE: raise RuntimeError("请先安装 modelscope: pip install modelscope")
            ms_snapshot_download(model_id=repo_id, cache_dir=str(model_path.parent), local_dir=str(model_path))
        else:
            hf_snapshot_download(repo_id=repo_id, local_dir=str(model_path), resume_download=True)
            
        return str(model_path)

def get_device_info():
    info = {"device_type": "cpu", "recommended_device": "cpu"}
    if torch.cuda.is_available():
        info["recommended_device"] = "cuda"
        info["gpu_mem"] = torch.cuda.get_device_properties(0).total_memory / 1024**3
    return info

# ================= 2. Qwen 配置节点 =================

class Qwen3VL_ModelConfig:
    @classmethod
    def INPUT_TYPES(cls):
        model_names = [name for name in MODEL_CONFIGS.keys() if not name.startswith('_')]
        default = "Qwen3-VL-4B-Instruct" if "Qwen3-VL-4B-Instruct" in model_names else (model_names[0] if model_names else "None")
        return {
            "required": {
                "🤖 模型选择": (model_names, {"default": default}),
                "⚙️ 量化级别": (list(Quantization.get_values()), {"default": Quantization.NONE}),
                "🔄 保持模型加载": ("BOOLEAN", {"default": True}),
            }
        }
    RETURN_TYPES = ("QWEN3VL_MODEL_CONFIG",)
    RETURN_NAMES = ("🔧 本地Qwen配置",)
    FUNCTION = "get_config"
    CATEGORY = "👨‍🏫班长/Qwen3VL"
    
    def get_config(self, **kwargs):
        return ({
            "model_name": kwargs.get("🤖 模型选择"),
            "quantization": kwargs.get("⚙️ 量化级别"),
            "keep_loaded": kwargs.get("🔄 保持模型加载", False)
        },)

# ================= 3. 抓取神器节点 =================

class BanzhangNodeTranslator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "⚡ 执行开关": ("BOOLEAN", {"default": True, "label_on": "🚀 启动", "label_off": "😴 暂停"}),
                "🔍 插件搜索": ("STRING", {"default": "", "multiline": False, "placeholder": "输入 菜单名(Category) 或 文件夹名(如 layerstyle)"}),
                "📂 保存目录": ("STRING", {"default": "output", "multiline": False}),
            },
            "optional": {
                "🔗 识别用节点": (AnyType("*"), {"tooltip": "连线识别来源 (可选)"}),
            },
            "hidden": {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"}
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("📄 运行状态报告", "📂 JSON文件路径")
    FUNCTION = "execute_task"
    CATEGORY = "👨‍🏫班长/辅助工具"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        m = hashlib.sha256()
        for k in ["🔍 插件搜索", "⚡ 执行开关", "📂 保存目录"]:
            v = kwargs.get(k, "")
            m.update(str(v).encode())
        prompt = kwargs.get("prompt", {})
        unique_id = kwargs.get("unique_id", None)
        if unique_id and prompt:
            node_data = prompt.get(str(unique_id), {})
            inputs_config = node_data.get("inputs", {})
            m.update(str(inputs_config).encode())
        return m.hexdigest()

    def execute_task(self, **kwargs):
        enable_switch = kwargs.get("⚡ 执行开关", True)
        raw_search_query = kwargs.get("🔍 插件搜索", "").strip()
        save_dir_input = kwargs.get("📂 保存目录", "output")
        reference_data = kwargs.get("🔗 识别用节点", None)
        prompt_data = kwargs.get("prompt", None)
        my_node_id = kwargs.get("unique_id", None)

        if not enable_switch: return ("😴 暂停中...", "")

        target_class_type = None 
        if reference_data is not None and prompt_data and my_node_id:
            try:
                my_node_data = prompt_data.get(str(my_node_id))
                if my_node_data and "inputs" in my_node_data:
                    link_info = my_node_data["inputs"].get("🔗 识别用节点")
                    if isinstance(link_info, list) and len(link_info) > 0:
                        upstream_node_id = str(link_info[0])
                        upstream_node_data = prompt_data.get(upstream_node_id)
                        if upstream_node_data and "class_type" in upstream_node_data:
                            target_class_type = upstream_node_data["class_type"]
                            print(f"👨‍🏫 班长：顺藤摸瓜成功！检测到上游节点类名 -> 【{target_class_type}】")
            except Exception as e:
                print(f"👨‍🏫 班长：连线分析失败 ({e})，回退到搜索框模式。")

        if target_class_type:
            search_query = "" 
            print(f"👨‍🏫 班长：启用【精准识别模式】，忽略搜索框内容。")
        else:
            search_query = raw_search_query
            if not search_query:
                return ("❌ 请输入搜索关键词 (如 layerstyle) 或连接一个有效的节点。", "")

        search_lower = search_query.lower() if search_query else ""
        target_node_ids = set() 
        matched_roots = set()   
        
        for node_id, node_class in nodes.NODE_CLASS_MAPPINGS.items():
            is_hit = False
            node_cat = ""
            if hasattr(node_class, "CATEGORY"): node_cat = str(node_class.CATEGORY).strip()
            node_file_path = ""
            try: node_file_path = inspect.getfile(node_class).replace("\\", "/").lower()
            except: pass

            if target_class_type:
                if node_id == target_class_type: is_hit = True
            else:
                if node_cat and search_lower and search_lower in node_cat.lower(): is_hit = True
                elif search_lower and len(search_lower) > 2 and search_lower in node_file_path: is_hit = True

            if is_hit:
                target_node_ids.add(node_id)
                if node_cat:
                    parts = node_cat.split('/')
                    root = parts[0].strip()
                    if root and root.lower() not in ["image", "latent", "mask", "sampling", "utils", "advanced", "api", "_for_testing"]:
                        matched_roots.add(root)
                if target_class_type and node_file_path:
                     parts = node_file_path.split("/")
                     if "custom_nodes" in parts:
                         idx = parts.index("custom_nodes")
                         if idx + 1 < len(parts): matched_roots.add(parts[idx+1])

        if not target_node_ids:
            err_msg = f"❌ 未找到目标插件。"
            if target_class_type: err_msg += f"\n已识别到上游节点类名：{target_class_type}，但在系统映射中未找到。"
            else: err_msg += f"\n搜索词：'{search_query}' 无匹配。"
            return (err_msg, "")

        final_target_roots = set(matched_roots) 
        final_node_ids = set(target_node_ids)
        
        if target_class_type and final_target_roots:
             print(f"👨‍🏫 班长：根据连线节点，锁定所属插件根目录 -> {final_target_roots}，正在抓取全家桶...")
             for node_id, node_class in nodes.NODE_CLASS_MAPPINGS.items():
                 if hasattr(node_class, "CATEGORY"):
                     cat = str(node_class.CATEGORY).strip()
                     for root in final_target_roots:
                         if cat.startswith(root): final_node_ids.add(node_id)

        extraction_result = {}
        count = 0
        detected_plugin_path_name = None 
        KNOWN_SOCKET_TYPES = ["IMAGE", "MASK", "LATENT", "MODEL", "CLIP", "VAE", "CONDITIONING", "STYLE_MODEL", "CLIP_VISION", "WEBCAM", "AUDIO", "VIDEO", "GLIGEN", "CONTROL_NET"]
        sorted_node_ids = sorted(list(final_node_ids))

        for node_id in sorted_node_ids:
            try:
                node_class = nodes.NODE_CLASS_MAPPINGS[node_id]
                if detected_plugin_path_name is None:
                    try:
                        class_file = inspect.getfile(node_class)
                        abs_path = os.path.abspath(class_file)
                        parts = abs_path.split(os.sep)
                        if "custom_nodes" in parts:
                            idx = parts.index("custom_nodes")
                            if idx + 1 < len(parts): detected_plugin_path_name = parts[idx+1]
                    except: pass

                display_name = nodes.NODE_DISPLAY_NAME_MAPPINGS.get(node_id, node_id)
                inputs_dict = {}
                widgets_dict = {}
                
                if hasattr(node_class, "INPUT_TYPES"):
                    try:
                        inp = node_class.INPUT_TYPES()
                        all_params = {}
                        if isinstance(inp, dict):
                            all_params.update(inp.get("required", {}))
                            all_params.update(inp.get("optional", {}))
                        
                        for k, v in all_params.items():
                            raw_type = v[0]
                            opts = v[1] if len(v) > 1 and isinstance(v[1], dict) else {}
                            is_socket = False
                            if isinstance(raw_type, list): is_socket = False 
                            elif isinstance(opts, dict) and opts.get("forceInput", False): is_socket = True
                            elif isinstance(raw_type, str):
                                if raw_type in KNOWN_SOCKET_TYPES: is_socket = True
                            if is_socket: inputs_dict[k] = k
                            else: widgets_dict[k] = k
                    except: pass

                outputs_dict = {}
                if hasattr(node_class, "RETURN_NAMES"):
                    for n in node_class.RETURN_NAMES: outputs_dict[n] = n
                elif hasattr(node_class, "RETURN_TYPES"):
                     for i in range(len(node_class.RETURN_TYPES)): outputs_dict[f"output_{i}"] = f"output_{i}"

                count += 1
                extraction_result[node_id] = {
                    "title": str(display_name),
                    "inputs": inputs_dict,
                    "widgets": widgets_dict,
                    "outputs": outputs_dict
                }
            except: pass

        if save_dir_input == "output": target_dir = folder_paths.get_output_directory()
        else:
            if not os.path.isabs(save_dir_input): target_dir = os.path.join(os.getcwd(), save_dir_input)
            else: target_dir = save_dir_input

        if not os.path.exists(target_dir):
            try: os.makedirs(target_dir)
            except: return (f"❌ 目录创建失败: {target_dir}", "")

        if detected_plugin_path_name: final_name = detected_plugin_path_name
        elif matched_roots: final_name = list(matched_roots)[0]
        elif search_query: final_name = search_query
        else: final_name = "Detected_Plugin"
            
        final_name = re.sub(r'[\\/*?:"<>|]', "", final_name) 
        json_file = f"{final_name}.json"
        full_path = os.path.join(target_dir, json_file)

        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(extraction_result, f, indent=4, ensure_ascii=False, sort_keys=True)
        return (f"✅ 抓取成功！\n🎯 目标名称：{final_name}\n📊 节点数量：{count} 个\n📂 JSON路径：{full_path}", full_path)

# ================= 4. AI 全能生成 (V41 终极地址适配版) =================

class BanzhangAITranslator:
    def __init__(self):
        self.image_processor = ImageProcessor()
        self.downloader = ModelDownloader() if TRANSFORMERS_AVAILABLE else None
        
    # V30: 定义预设数据
    PRESET_KEYS = [
        "无 (使用自定义)",
        "汉化节点 - 指令", 
        "提示词风格 - 标签",
        "提示词风格 - 简单",
        "提示词风格 - 详细",
        "提示词风格 - 极致详细",
        "提示词风格 - 电影感"
    ]
    
    SYSTEM_PROMPTS = {
        "汉化节点 - 指令": """你负责ComfyUI插件汉化。
核心规则：
1. 绝对不要修改Key。
2. 必须翻译Value：即使Value是英文缩写(如"cfg_scale")，也要意译为中文(如"引导系数")。
3. 即使Key=Value也要翻译Value。
4. 保留Emoji。
5. 只输出纯JSON。
6. 【关键】翻译 Title 时，必须智能保留插件特征（前缀/后缀/括号标识）：
   - 🚫 严禁翻译括号内的插件简称：'Remove Background (RMBG)' -> '移除背景 (RMBG)'。
   - 🚫 严禁翻译作者专属前缀：'CR Select Model' -> 'CR 选择模型'。""",
        "提示词风格 - 标签": "你的任务是为文生图AI生成一个简洁的逗号分隔标签列表，仅基于图像中的视觉信息。限制输出最多50个唯一标签。严格描述视觉元素，如主体、服装、环境、颜色、光照和构图。不要包含抽象概念、解释、营销术语或技术术语。目标是一个简洁的视觉描述符列表。避免重复标签。",
        "提示词风格 - 简单": "分析图像并生成一个简单的单句文生图提示词。简洁地描述主要主体和场景。",
        "提示词风格 - 详细": "基于图像生成一个详细的艺术性文生图提示词。将主体、动作、环境、光照和整体氛围组合成一个连贯的段落，约2-3句话。关注关键视觉细节。",
        "提示词风格 - 极致详细": "从图像生成一个极其详细和描述性的文生图提示词。创建一个丰富的段落，详细阐述主体的外观、服装纹理、具体背景元素、光线的质量和颜色、阴影以及整体氛围。追求高度描述性和沉浸式的提示词。",
        "提示词风格 - 电影感": "作为一个大师级提示词工程师。为图像生成AI创建一个高度详细和富有感染力的提示词。描述主体、姿势、环境、光照、情绪和艺术风格（如照片写实、电影感、绘画风格）。将所有元素编织成一个自然语言段落，专注于视觉冲击力。"
    }

    @classmethod
    def INPUT_TYPES(cls):
        api_providers = [
            "Doubao (豆包/火山)", 
            "Aliyun (通义千问)", 
            "DeepSeek (深度求索)", 
            "Ollama (本地)",
            "Baidu Qianfan (百度千帆)", 
            "Moonshot (Kimi)", 
            "Zhipu (智谱GLM)", 
            "SiliconFlow (硅基流动)", 
            "OpenAI (官方/中转)",
            "Custom (自定义)"
        ]
        
        return {
            "required": {
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "🔑 API_KEY": ("STRING", {"default": "sk-xxxx", "multiline": False}),
                "🌐 API服务商": (api_providers, {"default": "Doubao (豆包/火山)"}), 
                "🔗 自定义地址": ("STRING", {"default": ""}),
                "🤖 模型名称": ("STRING", {"default": "default"}),
                
                # V30: 新增预设选项
                "🎨 提示词预设": (cls.PRESET_KEYS, {"default": "无 (使用自定义)"}),
                
                # V31: 更新输入框名称和提示
                "🧠 系统指令 (指令)": ("STRING", {"default": "", "multiline": True, "placeholder": "[指令区] System Prompt。若选预设，此处可留空。"}),
                "🗣️ 用户提示 (正文)": ("STRING", {"default": "", "multiline": True, "placeholder": "[内容区] User Prompt。输入需要处理的文字、JSON数据或图片描述请求。"}),
                
                # V25: 参数优化
                "🔢 最大token数": ("INT", {"default": 2048, "min": 64, "max": 8192, "step": 16, "tooltip": "生成文本的最大长度"}),
                "🌡️ 采样温度": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.1, "tooltip": "值越高越随机，值越低越确定"}),
                "🎬 视频帧率": ("INT", {"default": 16, "min": 1, "max": 60, "step": 1, "tooltip": "本地模型处理视频时的帧率设定"}),
                # V25.1: 参数确认
                "📉 媒体限制(边长)": ("INT", {"default": 512, "min": 0, "max": 1920, "step": 64, "tooltip": "强制缩小图片/视频尺寸（长边）以防爆显存，推荐512"}),
                # V36.1: 批处理大小 (默认 10)
                "🔢 批处理大小": ("INT", {"default": 10, "min": 1, "max": 100, "step": 1, "tooltip": "汉化时的批处理大小，显存小请调小（如3-5）"}),
            },
            "optional": {
                "🔧 本地Qwen配置": ("QWEN3VL_MODEL_CONFIG", {"forceInput": False, "tooltip": "连接此处启用本地显卡模式"}),
                "📂 JSON路径": ("STRING", {"forceInput": True}),
                "🖼️ 图像1": ("IMAGE", {}),
                "🖼️ 图像2": ("IMAGE", {}),
                "🖼️ 图像3": ("IMAGE", {}),
                # V20: 视频输入
                "🎥 视频": ("IMAGE", {"tooltip": "输入的视频帧序列"}),
                "💾 覆盖原文件": ("BOOLEAN", {"default": True}),
                "🔄 质检次数": ("INT", {"default": 5}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("📄 运行报告", "📝 生成内容")
    FUNCTION = "generate_content"
    CATEGORY = "👨‍🏫班长/辅助工具"

    # --- 辅助方法 ---
    def _get_api_config(self, kwargs):
        """提取并构建 API 配置 (V41: 智能地址适配版)"""
        api_key = kwargs.get("🔑 API_KEY", "").strip()
        provider_full = kwargs.get("🌐 API服务商", "Doubao (豆包/火山)")
        provider_key = provider_full.split(" ")[0]
        custom_url = kwargs.get("🔗 自定义地址", "").strip().rstrip('/')
        model_input = kwargs.get("🤖 模型名称", "default").strip()

        url_map = {
            "Doubao": "https://ark.cn-beijing.volces.com/api/v3",
            "Aliyun": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "DeepSeek": "https://api.deepseek.com",
            "Ollama": "http://localhost:11434/v1",
            "Zhipu": "https://open.bigmodel.cn/api/paas/v4", 
            "OpenAI": "https://api.openai.com/v1"
        }
        
        # V41: 智能地址补全逻辑
        if provider_key == "Custom":
            if custom_url.endswith("/chat/completions"):
                url = custom_url
            elif custom_url.endswith("/v1"):
                url = f"{custom_url}/chat/completions"
            else:
                # 默认补全 /v1/chat/completions (绝大多数中转站标准)
                url = f"{custom_url}/v1/chat/completions"
                print(f"👨‍🏫 班长自动补全URL: {url}")
        else:
            base_url = url_map.get(provider_key, "")
            url = f"{base_url.rstrip('/')}/chat/completions"
            
        headers = {
            "Content-Type": "application/json", 
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" # V41: 伪装浏览器
        }
        
        default_model_map = {"Doubao": "ep-20240604052348-k8j6k", "Aliyun": "qwen-turbo", "DeepSeek": "deepseek-chat", "Ollama": "llama3", "Zhipu": "glm-4", "OpenAI": "gpt-3.5-turbo"}
        model = default_model_map.get(provider_key, model_input) if "default" in model_input.lower() else model_input

        return url, headers, model, provider_key

    def _is_english(self, s):
        if not isinstance(s, str) or not s: return False
        if re.search(r'[\u4e00-\u9fff]', s): return False
        if re.search(r'[a-zA-Z]', s): return True
        return False

    def _scan_for_untranslated(self, json_data):
        missing = {}
        count = 0
        for node_key, node_info in json_data.items():
            if not isinstance(node_info, dict): continue
            node_missing = {}
            if "title" in node_info and self._is_english(str(node_info["title"])):
                node_missing["title"] = node_info["title"]
            for section in ["inputs", "widgets", "outputs"]:
                if section in node_info and isinstance(node_info[section], dict):
                    section_missing = {}
                    for k, v in node_info[section].items():
                        val_str = str(v)
                        if (k == val_str and len(val_str) > 1) or self._is_english(val_str):
                            section_missing[k] = v
                    if section_missing:
                        node_missing[section] = section_missing
            if node_missing:
                missing[node_key] = node_missing
                count += 1
        return missing, count

    def _smart_translate_routine(self, data, url, headers, model, system_prompt, local_config=None, batch_size=5, desc="处理"):
        BATCH_SIZE = batch_size
        keys = list(data.keys())
        merged_result = {}
        total_batches = (len(keys) + BATCH_SIZE - 1) // BATCH_SIZE
        # 如果总量少，一次处理
        if len(keys) <= 5: BATCH_SIZE = len(keys)

        for i in range(0, len(keys), BATCH_SIZE):
            if INTERRUPT_EVENT.is_set():
                print("👨‍🏫 班长: 接到中断指令，停止翻译任务！")
                break
                
            batch_keys = keys[i : i + BATCH_SIZE]
            current_batch_num = (i // BATCH_SIZE) + 1
            print(f"   ...{desc}第 {current_batch_num}/{total_batches} 批 ({len(batch_keys)} 个节点)...")
            
            batch_data = {k: data[k] for k in batch_keys}
            batch_json_str = json.dumps(batch_data, ensure_ascii=False)
            
            user_msg = f"请翻译以下JSON数据:\n{batch_json_str}"
            
            if local_config:
                 # 本地模式强制低温度、长token以保证翻译质量
                 _, res_text = self._run_local_inference(
                     local_config, system_prompt, user_msg, 
                     images=[], video_frames=None, fps=0, 
                     max_tokens=4096, temperature=0.1, max_side=0
                 )
                 
                 if res_text:
                     translated_batch = self._extract_json_from_text(res_text)
                     if translated_batch:
                        clean_batch = self._nuclear_sanitize(translated_batch)
                        merged_result.update(clean_batch)
                     else:
                        print(f"   ⚠️ 第 {current_batch_num} 批本地解析JSON失败。")
                        merged_result.update(batch_data)
                 else:
                     print(f"   ⚠️ 第 {current_batch_num} 批本地推理返回空。")
                     merged_result.update(batch_data)
                     
            else:
                # API 模式
                messages = []
                if system_prompt.strip(): messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": user_msg}) 
                
                payload = {"model": model, "messages": messages, "temperature": 0.1}
                
                try:
                    response_data = self._call_api(url, headers, payload)
                    if 'choices' in response_data:
                        res_text = response_data['choices'][0]['message']['content']
                        translated_batch = self._extract_json_from_text(res_text)
                        if translated_batch:
                            clean_batch = self._nuclear_sanitize(translated_batch)
                            merged_result.update(clean_batch)
                        else: 
                            print(f"   ⚠️ 第 {current_batch_num} 批解析JSON失败，保留原文。")
                            merged_result.update(batch_data)
                    else: 
                        print(f"   ⚠️ 第 {current_batch_num} 批无有效返回。")
                        merged_result.update(batch_data)
                except Exception as e:
                    print(f"   ❌ {desc}第 {current_batch_num} 批网络/API错误，保留原文。错误: {e}")
                    merged_result.update(batch_data)
                    time.sleep(1) 
                
        return merged_result

    # --- 本地推理逻辑 ---
    def _run_local_inference(self, config, system_prompt, user_prompt, images, video_frames, fps, max_tokens, temperature, max_side):
        thread_exception = None
        generated_text_container = [""]

        if not TRANSFORMERS_AVAILABLE: return "❌ 错误: 未安装 transformers 库，无法使用本地模型。", ""
        
        model_name = config["model_name"]
        quantization = config["quantization"]
        keep_loaded = config["keep_loaded"]
        
        # 1. 显存侦探 - 加载前
        print(f"📊 [显存侦探] 加载前显存: {get_vram_info()}")
        
        # V34: 清除中断信号，开始新任务
        INTERRUPT_EVENT.clear()
        
        try:
            # 2. BnB 深度诊断
            bnb_available = False
            try:
                import bitsandbytes
                bnb_available = True
                # print(f"✅ 检测到 bitsandbytes 库: {bitsandbytes.__file__}") # 减少刷屏
            except ImportError:
                print("❌ 严重警告: 未检测到 bitsandbytes 库，4-bit 量化将失效！")
            
            # V27: 强制禁用 Flash Attention 2
            # print("👨‍🏫 班长: 强制使用 sdpa 注意力机制 (Win环境稳定性优化)")

            model_path = self.downloader.ensure_model_available(model_name)
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            cache_key = f"{model_name}_{quantization}"
            
            global MODEL_CACHE, PROCESSOR_CACHE, TOKENIZER_CACHE
            if cache_key not in MODEL_CACHE:
                print(f"👨‍🏫 班长: 正在加载本地模型 {model_name}...")
                print(f"👨‍🏫 班长 Debug: 用户选择量化模式: '{quantization}' (BnB可用: {bnb_available})")
                
                # 默认参数 (V27: 强制使用 sdpa)
                load_kwargs = {
                    "device_map": "auto",
                    "trust_remote_code": True,
                    "attn_implementation": "sdpa" 
                }
                
                q_str = str(quantization)
                quant_config = None
                
                # 构建量化配置
                if bnb_available:
                    if q_str == Quantization.Q4_BIT.value:
                        print("👨‍🏫 班长: 正在构建 4-bit 量化配置 (NF4 + Double Quant)...")
                        quant_config = BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_compute_dtype=torch.float16,
                            bnb_4bit_quant_type="nf4",
                            bnb_4bit_use_double_quant=True
                        )
                    elif q_str == Quantization.Q8_BIT.value:
                        print("👨‍🏫 班长: 正在构建 8-bit 量化配置...")
                        quant_config = BitsAndBytesConfig(load_in_8bit=True)
                
                if quant_config:
                    load_kwargs["quantization_config"] = quant_config
                else:
                    print("👨‍🏫 班长: 未启用量化 (使用 FP16 精度加载)...")
                    load_kwargs["torch_dtype"] = torch.float16

                # V23: 尝试加载配置
                try:
                    loaded_config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)
                except:
                    loaded_config = None

                model = AutoModelForImageTextToText.from_pretrained(
                    model_path, 
                    **load_kwargs
                ).eval()
                
                # 3. 显存侦探 - 加载后
                print(f"📊 [显存侦探] 模型加载后显存: {get_vram_info()}")
                
                # V23: 健壮性加载 Processor
                try:
                    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
                except Exception:
                    if loaded_config:
                        print("👨‍🏫 班长: Processor 加载失败，尝试使用 Config 兜底...")
                        processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True, config=loaded_config)
                    else:
                        raise

                # V23: 显式加载 Tokenizer
                try:
                    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
                except Exception:
                    if loaded_config:
                        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True, config=loaded_config)
                    else:
                        tokenizer = None 
                
                MODEL_CACHE[cache_key] = model
                PROCESSOR_CACHE[cache_key] = processor
                TOKENIZER_CACHE[cache_key] = tokenizer
            else:
                print(f"👨‍🏫 班长：复用已加载的本地模型缓存 (模式: {quantization})")
            
            model = MODEL_CACHE[cache_key]
            processor = PROCESSOR_CACHE[cache_key]
            tokenizer = TOKENIZER_CACHE.get(cache_key)

            messages = []
            if system_prompt: messages.append({"role": "system", "content": [{"type": "text", "text": system_prompt}]})
            
            user_content = []
            for img in images:
                if img is not None:
                    pil_img = self.image_processor.to_pil(img, max_side)
                    user_content.append({"type": "image", "image": pil_img})
            
            if video_frames is not None:
                vid_pil_list = [self.image_processor.to_pil(f, max_side) for f in video_frames]
                if len(vid_pil_list) == 1: vid_pil_list.append(vid_pil_list[0])
                user_content.append({"type": "video", "video": vid_pil_list})

            user_content.append({"type": "text", "text": user_prompt})
            messages.append({"role": "user", "content": user_content})

            text_prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            
            image_inputs = [c['image'] for c in user_content if c['type'] == 'image']
            video_inputs = [c['video'] for c in user_content if c['type'] == 'video']
            
            inputs = processor(text=[text_prompt], images=image_inputs if image_inputs else None, videos=video_inputs if video_inputs else None, return_tensors="pt", padding=True)
            inputs = inputs.to(model.device)

            stop_tokens = [tokenizer.eos_token_id] if tokenizer else []
            if tokenizer and hasattr(tokenizer, 'eot_id'): stop_tokens.append(tokenizer.eot_id)

            streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

            gen_kwargs = {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "do_sample": True if temperature > 0 else False,
                "eos_token_id": stop_tokens if stop_tokens else None,
                "streamer": streamer
            }
            if tokenizer and tokenizer.pad_token_id is not None: gen_kwargs["pad_token_id"] = tokenizer.pad_token_id

            gc.collect()
            torch.cuda.empty_cache()
            
            print("👨‍🏫 班长: 开始生成文本 (流式多线程)...")
            
            def thread_target():
                nonlocal thread_exception
                try:
                    model.generate(**dict(inputs, **gen_kwargs))
                except Exception as e:
                    thread_exception = e
                    if hasattr(streamer, 'end'): streamer.end()

            thread = threading.Thread(target=thread_target)
            thread.start()
            
            print("📝 生成内容: ", end="", flush=True)
            buffer = ""
            try:
                for new_text in streamer:
                    if INTERRUPT_EVENT.is_set():
                        print("\n⛔ 任务被用户中断！")
                        break
                    if thread_exception: raise thread_exception
                    buffer += new_text
                    if len(buffer) > 30 or "\n" in buffer:
                        sys.stdout.write(buffer)
                        sys.stdout.flush()
                        generated_text_container[0] += buffer
                        buffer = ""
                if buffer:
                    sys.stdout.write(buffer)
                    sys.stdout.flush()
                    generated_text_container[0] += buffer
            except Exception as e:
                err_str = str(e)
                if "OutOfMemoryError" in err_str: return (f"❌ 显存溢出 (OOM)！请减小 '媒体限制(边长)' 参数。\n当前设置: {max_side}\n错误详情: {e}", "")
                else: return (f"❌ 生成出错: {e}", "")

            print("\n👨‍🏫 班长: 生成结束。")

            if not keep_loaded:
                del MODEL_CACHE[cache_key]
                del PROCESSOR_CACHE[cache_key]
                if cache_key in TOKENIZER_CACHE: del TOKENIZER_CACHE[cache_key]
                torch.cuda.empty_cache()
                print("👨‍🏫 班长：已释放本地模型显存。")

            return (f"✅ 本地运行成功！\n模型：{model_name}\nToken：{max_tokens}\nTemp：{temperature}", generated_text_container[0])

        except Exception as e:
            return (f"❌ 本地推理失败: {e}", "")

    # --- API 调用逻辑 ---
    def _call_api(self, url, headers, payload, timeout=120):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
                response_text = response.read().decode('utf-8')
                if not response_text: raise Exception("API 返回了空内容。")
                try: return json.loads(response_text)
                except json.JSONDecodeError:
                    print(f"❌ API 原始响应: {response_text[:500]}")
                    raise Exception(f"API 响应非 JSON 格式: {response_text[:100]}...")
        except urllib.error.HTTPError as e:
            try: error_body = e.read().decode('utf-8')
            except: error_body = "[无法读取响应体]"
            print(f"❌ API HTTP错误: {e.code} - {error_body}")
            raise Exception(f"HTTP {e.code}: {error_body}")
        except Exception as e:
            print(f"❌ API 连接错误: {e}")
            raise e

    def _extract_json_from_text(self, text):
        clean_text = text.replace("```json", "").replace("```", "").strip()
        try: return json.loads(clean_text)
        except: pass
        try: return ast.literal_eval(text)
        except: return None

    def _flatten_to_string(self, val):
        if isinstance(val, str): return val
        if isinstance(val, (int, float, bool)): return str(val)
        if val is None: return ""
        if isinstance(val, dict):
            for v in val.values(): return self._flatten_to_string(v)
            return ""
        if isinstance(val, list): return self._flatten_to_string(val[0])
        return str(val)

    def _nuclear_sanitize(self, data):
        if not isinstance(data, dict): return {}
        clean_data = {}
        for node_key, node_info in data.items():
            if not isinstance(node_info, dict): continue
            clean_node = {}
            raw_title = node_info.get("title", node_key)
            clean_node["title"] = str(raw_title) if raw_title is not None else ""
            for section in ["inputs", "widgets", "outputs"]:
                if section in node_info and isinstance(node_info[section], dict):
                    clean_section = {}
                    for k, v in node_info[section].items():
                        clean_section[k] = str(v) if v is not None else ""
                    clean_node[section] = clean_section
            clean_data[node_key] = clean_node
        return clean_data
        
    def _scan_for_untranslated(self, json_data):
        missing = {}
        count = 0
        for node_key, node_info in json_data.items():
            if not isinstance(node_info, dict): continue
            node_missing = {}
            if "title" in node_info and self._is_english(str(node_info["title"])):
                node_missing["title"] = node_info["title"]
            for section in ["inputs", "widgets", "outputs"]:
                if section in node_info and isinstance(node_info[section], dict):
                    section_missing = {}
                    for k, v in node_info[section].items():
                        val_str = str(v)
                        # 如果 key 等于 value (且非短值)，或者 value 纯英文，则视为漏翻
                        if (k == val_str and len(val_str) > 1) or self._is_english(val_str):
                            section_missing[k] = v
                    if section_missing:
                        node_missing[section] = section_missing
            if node_missing:
                missing[node_key] = node_missing
                count += 1
        return missing, count

    def generate_content(self, **kwargs):
        INTERRUPT_EVENT.clear()
        local_config = kwargs.get("🔧 本地Qwen配置")
        preset_name = kwargs.get("🎨 提示词预设", "无 (使用自定义)")
        system_prompt = kwargs.get("🧠 系统指令 (指令)", "").strip()
        user_prompt = kwargs.get("🗣️ 用户提示 (正文)", "").strip()
        json_path = kwargs.get("📂 JSON路径", "")
        batch_size = kwargs.get("🔢 批处理大小", 10)

        # 智能预设填充
        if not system_prompt and not user_prompt:
            if preset_name in self.SYSTEM_PROMPTS:
                print(f"👨‍🏫 班长: 检测到空白输入，自动激活预设【{preset_name}】")
                system_prompt = self.SYSTEM_PROMPTS[preset_name]
                user_prompt = "请描述这张图片。"
            elif not system_prompt:
                system_prompt = "你是一个专业、友好的AI助手。"

        # V36: 汉化任务优先调度
        is_json_task = json_path and os.path.exists(json_path)
        is_translation_task = is_json_task and (preset_name == "汉化节点 - 指令" or not user_prompt.strip() or user_prompt == "请描述这张图片。")

        if is_translation_task:
            if preset_name == "汉化节点 - 指令" and not system_prompt:
                 system_prompt = self.SYSTEM_PROMPTS["汉化节点 - 指令"]
            
            # V38: 修正 provider_key 获取
            provider_full = kwargs.get("🌐 API服务商", "Doubao")
            provider_key = provider_full.split(" ")[0]
            
            mode_str = "本地显卡 (Qwen3-VL)" if local_config else f"API ({provider_key})"
            print(f"👨‍🏫 班长AI：启动智能翻译 (V38)，模式：{mode_str}，批大小：{batch_size}")
            
            try:
                with open(json_path, 'r', encoding='utf-8') as f: full_data = json.load(f)
                
                # API 配置准备
                url, headers, model, _ = self._get_api_config(kwargs)
                
                # 执行翻译
                final_result = self._smart_translate_routine(
                    full_data, url, headers, model, system_prompt, 
                    local_config=local_config, batch_size=batch_size, desc="初译"
                )
                
                # 保存
                final_result = self._nuclear_sanitize(final_result)
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(final_result, f, indent=4, ensure_ascii=False)
                    
                return (f"✅ 翻译完成！\n💾 文件已保存：{json_path}\n📊 处理条目数：{len(final_result)}", "内容已保存。")
                
            except Exception as e: return (f"❌ 翻译流程异常: {e}", "")

        # 常规对话/生图任务
        if local_config:
            max_tokens = kwargs.get("🔢 最大token数", 2048)
            temperature = kwargs.get("🌡️ 采样温度", 0.7)
            fps = kwargs.get("🎬 视频帧率", 16)
            max_side = kwargs.get("📉 媒体限制(边长)", 512)
            images = [kwargs.get(f"🖼️ 图像{i}") for i in range(1, 4)]
            video_frames = kwargs.get("🎥 视频", None)
            
            if is_json_task:
                 with open(json_path, 'r', encoding='utf-8') as f: user_prompt += f"\n\nJSON Data:\n{f.read()}"
            
            return self._run_local_inference(local_config, system_prompt, user_prompt, images, video_frames, fps, max_tokens, temperature, max_side)
        else:
            return self._v9_api_logic(**kwargs)
            
    def _v9_api_logic(self, **kwargs):
        # 简化版 API 逻辑调用，实际包含完整 urllib 请求
        # V38: 修复 provider_key 获取
        provider_full = kwargs.get("🌐 API服务商", "Doubao (豆包/火山)")
        provider_key = provider_full.split(" ")[0]
        
        api_key = kwargs.get("🔑 API_KEY", "").strip()
        url, headers, model, _ = self._get_api_config(kwargs)
        system_prompt = kwargs.get("🧠 系统指令 (指令)", "")
        user_prompt = kwargs.get("🗣️ 用户提示 (正文)", "")
        
        messages = [{"role": "user", "content": user_prompt}]
        if system_prompt: messages.insert(0, {"role": "system", "content": system_prompt})
        
        # 处理图片输入 (API 模式)
        content_parts = [{"type": "text", "text": user_prompt}]
        has_img = False
        for i in range(1, 4):
            img_input = kwargs.get(f"🖼️ 图像{i}")
            if img_input is not None:
                has_img = True
                try:
                    # ComfyUI Tensor [B, H, W, C] -> PIL -> Base64
                    # 简化处理：取 batch 中第一张图
                    img_tensor = img_input[0] 
                    i_np = 255. * img_tensor.cpu().numpy()
                    img = Image.fromarray(np.clip(i_np, 0, 255).astype(np.uint8))
                    buffered = io.BytesIO()
                    img.save(buffered, format="JPEG")
                    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    content_parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})
                except Exception as e:
                    print(f"图片处理错误: {e}")
        
        if has_img: messages[-1]["content"] = content_parts
        
        payload = {"model": model, "messages": messages, "temperature": 0.7}
        try:
            # V38: 使用增强后的 _call_api
            res = self._call_api(url, headers, payload, 180)
            
            # 兼容不同 API 的返回格式
            if 'choices' in res:
                return ("✅ API 响应成功", res['choices'][0]['message']['content'])
            else:
                return (f"❌ API 返回格式未知: {res}", "")
                
        except Exception as e: return (f"❌ API 错误: {e}", "")

    @classmethod
    def process_cancel(cls):
        print("👨‍🏫 班长: 收到前端 Cancel 信号！")
        INTERRUPT_EVENT.set()

# ================= 注册映射 =================
NODE_CLASS_MAPPINGS = {
    "BanzhangNodeTranslator": BanzhangNodeTranslator,
    "BanzhangAnyOutputNode": BanzhangAnyOutputNode,
    "BanzhangAITranslator": BanzhangAITranslator,
    "Qwen3VL_ModelConfig": Qwen3VL_ModelConfig
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BanzhangNodeTranslator": "🔍 抓取神器 V11 (究极稳定版)",
    "BanzhangAnyOutputNode": "🧩 万能空节点",
    "BanzhangAITranslator": "🤖 AI 全能生成 V38 (API调试增强版)",
    "Qwen3VL_ModelConfig": "🍭 Qwen3VL 模型配置"
}