import os

import numpy as np
import torch
import folder_paths
from PIL import Image, ImageOps


class SFLoadImageFromPath:
    """读取任意绝对路径（或 ComfyUI input 目录下的相对路径）的图片。

    用途：万象等第三方软件在链接工作流时，会把图片路径填成它自己的临时目录
    绝对路径（如 C:\\Users\\Public\\WXApp_...\\x.png），原生 LoadImage 无法识别。
    这个节点可直接填绝对路径加载，输出 IMAGE / MASK，与原生 LoadImage 兼容，
    方便在 ComfyUI 里本地测试，或替换工作流里的 LoadImage 节点。

    注意：本节点面向「图片」加载（与报错场景一致）。如需多帧/视频帧，请继续用
    原生 LoadImage / 官方视频节点。
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_path": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "图片绝对路径，或 ComfyUI input 目录下的相对路径。支持万象等软件传来的外部绝对路径。",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("IMAGE", "MASK")
    FUNCTION = "load_image"
    CATEGORY = "SF-WhatDreamsCost"

    def load_image(self, image_path):
        raw = (image_path or "").strip()
        if not raw:
            raise ValueError("image_path 不能为空")

        # 绝对路径直接用；相对路径拼 ComfyUI input 目录
        if os.path.isabs(raw):
            full = raw
        else:
            full = os.path.join(folder_paths.get_input_directory(), raw)

        if not os.path.isfile(full):
            raise FileNotFoundError("找不到图片文件: {}".format(full))

        img = Image.open(full)
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")

        image_np = np.array(img).astype(np.float32) / 255.0
        image_tensor = torch.from_numpy(image_np)[None,]

        # 与原生 LoadImage 保持一致：无 alpha 通道时输出 64x64 全 0 掩码
        if "A" in img.getbands():
            mask = np.array(img.getchannel("A")).astype(np.float32) / 255.0
            mask = 1.0 - torch.from_numpy(mask)
        else:
            mask = torch.zeros((64, 64), dtype=torch.float32)

        return (image_tensor, mask)
