import os
import io
import base64
import string
import traceback
from typing import List, Tuple

import numpy as np
import torch
from PIL import Image

# 可选：批量模式支持 XLSX 需要 pandas 和 openpyxl
try:
    import pandas as pd
    HAS_PANDAS = True
except Exception:
    HAS_PANDAS = False

try:
    from openai import OpenAI
except Exception as e:
    OpenAI = None  # 延迟报错，在调用时提示安装依赖


def _pil_to_base64_data_url(img: Image.Image, format: str = "jpeg") -> str:
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format=format)
    img_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/{format};base64,{img_str}"


def _decode_image_from_openrouter_response(completion) -> Tuple[List[Image.Image], str]:
    """
    解析 OpenRouter chat.completions 响应中的 base64 图片，返回 PIL 列表或错误信息。
    """
    try:
        response_dict = completion.model_dump()
        images_list = response_dict.get("choices", [{}])[0].get("message", {}).get("images")
        if images_list and isinstance(images_list, list) and len(images_list) > 0:
            out_pils = []
            for image_info in images_list:
                base64_url = image_info.get("image_url", {}).get("url")
                if not base64_url:
                    continue
                # 支持 data URL 或纯 base64
                if "base64," in base64_url:
                    base64_data = base64_url.split("base64,")[1]
                else:
                    base64_data = base64_url
                img_bytes = base64.b64decode(base64_data)
                pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                out_pils.append(pil)
            if out_pils:
                return out_pils, ""
        # 未取到图片，回显原始 JSON
        return [], f"模型回复中未直接包含图片数据。\n\n--- 完整的API回复 ---\n{completion.model_dump_json(indent=2)}"
    except Exception as e:
        try:
            raw = completion.model_dump_json(indent=2)
        except Exception:
            raw = "<failed to dump json>"
        return [], f"解析API响应时出错: {e}\n\n--- 完整的API回复 ---\n{raw}"


def _tensor_to_pils(image) -> List[Image.Image]:
    """
    将 ComfyUI 的 IMAGE(tensor[B,H,W,3], 浮点0-1) 转成 PIL 列表
    """
    if isinstance(image, dict) and "images" in image:
        image = image["images"]
    if not isinstance(image, torch.Tensor):
        raise TypeError("IMAGE 输入应为 torch.Tensor 或包含 'images' 键的 dict")
    if image.ndim == 3:
        image = image.unsqueeze(0)
    imgs = []
    arr = (image.clamp(0, 1).cpu().numpy() * 255.0).astype(np.uint8)  # [B,H,W,3]
    for i in range(arr.shape[0]):
        pil = Image.fromarray(arr[i], mode="RGB")
        imgs.append(pil)
    return imgs


def _pils_to_tensor(pils: List[Image.Image]) -> torch.Tensor:
    """
    将 PIL 列表转回 ComfyUI 的 IMAGE tensor[B,H,W,3], float32 0-1
    """
    if not pils:
        # 返回一个空的占位张量，避免下游崩溃（B=0）
        return torch.zeros((0, 64, 64, 3), dtype=torch.float32)
    np_imgs = []
    for pil in pils:
        if pil.mode != "RGB":
            pil = pil.convert("RGB")
        arr = np.array(pil, dtype=np.uint8)  # [H,W,3]
        np_imgs.append(arr)
    batch = np.stack(np_imgs, axis=0).astype(np.float32) / 255.0  # [B,H,W,3]
    return torch.from_numpy(batch)


class OpenRouterImageGenerator:
    """
    使用 OpenRouter Chat Completions，通过单条 prompt 或 CSV/Excel 批量，根据输入参考图生成新图。
    - 单图：提供 prompt
    - 批量：提供 file_path（含 'prompt' 列）
    输出：
      IMAGE: 生成的图像（单张或批量拼成 batch）
      STRING: 状态/日志
    """

    CATEGORY = "OpenRouter"
    FUNCTION = "generate"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "status")
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {"multiline": False, "default": ""}),
                "image": ("IMAGE",),
            },
            "optional": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "file_path": ("STRING", {"multiline": False, "default": ""}),
                "site_url": ("STRING", {"multiline": False, "default": ""}),
                "site_name": ("STRING", {"multiline": False, "default": ""}),
                "model": ("STRING", {"multiline": False, "default": "google/gemini-2.5-flash-image-preview:free"}),
            },
        }

    def _call_openrouter(
        self,
        api_key: str,
        pil_ref: Image.Image,
        prompt_text: str,
        site_url: str,
        site_name: str,
        model: str,
    ) -> Tuple[List[Image.Image], str]:
        if OpenAI is None:
            return [], "未安装 openai 库，请先安装：pip install openai"
        if not api_key:
            return [], "错误：请输入 OpenRouter API Key。"

        try:
            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
            headers = {}
            if site_url:
                headers["HTTP-Referer"] = site_url
            if site_name:
                headers["X-Title"] = site_name

            data_url = _pil_to_base64_data_url(pil_ref, format="jpeg")
            full_prompt = f"请严格根据这张图片，并结合以下提示词，生成一张新的图片。不要描述图片。提示词：'{prompt_text}'"

            completion = client.chat.completions.create(
                extra_headers=headers,
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": full_prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
            pils, err = _decode_image_from_openrouter_response(completion)
            if err:
                return [], err
            if not pils:
                return [], "未从模型收到图片数据。"
            return pils, ""
        except Exception as e:
            return [], f"生成图片时出错: {traceback.format_exc()}"

    def generate(
        self,
        api_key: str,
        image,
        prompt: str = "",
        file_path: str = "",
        site_url: str = "",
        site_name: str = "",
        model: str = "google/gemini-2.5-flash-image-preview:free",
    ):
        # 将输入 IMAGE 拿第一张作为参考图
        try:
            pils_in = _tensor_to_pils(image)
            if not pils_in:
                return image, "错误：请输入参考图像。"
            ref_pil = pils_in[0]
        except Exception as e:
            return image, f"输入图像解析失败：{e}"

        # 判定模式
        if not prompt and not file_path:
            return image, "错误：请输入提示词或提供 CSV/Excel 文件路径。"

        all_out_pils: List[Image.Image] = []
        status_msgs: List[str] = []

        # 单条 prompt
        if prompt:
            out_pils, err = self._call_openrouter(api_key, ref_pil, prompt, site_url, site_name, model)
            if err:
                return image, err
            all_out_pils.extend(out_pils)
            status_msgs.append(f"已生成 {len(out_pils)} 张图片。")

        # 批量文件
        elif file_path:
            clean_path = "".join(filter(lambda x: x in string.printable, file_path)).strip()
            if (clean_path.startswith('"') and clean_path.endswith('"')) or (clean_path.startswith("'") and clean_path.endswith("'")):
                clean_path = clean_path[1:-1]
            if not os.path.exists(clean_path):
                return image, f"错误：文件路径不存在: {clean_path}"

            if not HAS_PANDAS:
                return image, "错误：批量模式需要 pandas，请先安装：pip install pandas openpyxl"

            try:
                if clean_path.lower().endswith(".csv"):
                    df = pd.read_csv(clean_path)
                else:
                    df = pd.read_excel(clean_path, sheet_name="Sheet1")
            except Exception as e:
                return image, f"读取文件失败：{e}"

            if "prompt" not in df.columns:
                return image, "错误：文件中未找到 'prompt' 列。"

            for idx, row in df.iterrows():
                csv_prompt = row.get("prompt")
                if not isinstance(csv_prompt, str) or not csv_prompt.strip():
                    status_msgs.append(f"第 {idx + 1} 行跳过：空提示词")
                    continue
                out_pils, err = self._call_openrouter(api_key, ref_pil, csv_prompt, site_url, site_name, model)
                if err:
                    status_msgs.append(f"图片 {idx + 1} 生成失败：{err}")
                else:
                    all_out_pils.extend(out_pils)
                    status_msgs.append(f"图片 {idx + 1} 生成成功（{len(out_pils)} 张）。")

            if not all_out_pils:
                return image, "未从文件中生成任何图片。\n" + "\n".join(status_msgs)

        out_tensor = _pils_to_tensor(all_out_pils)
        status = "\n".join(status_msgs) if status_msgs else "完成"
        return (out_tensor, status)


# 注册到 ComfyUI
NODE_CLASS_MAPPINGS = {
    "OpenRouterImageGenerator": OpenRouterImageGenerator,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenRouterImageGenerator": "OpenRouter Image Generator",
}