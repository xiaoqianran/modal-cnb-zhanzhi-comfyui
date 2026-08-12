from PIL import Image
import torch
import numpy as np
from .inspyrenet import Remover
from tqdm import tqdm


def tensor2pil(image):
    return Image.fromarray(np.clip(255. * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))

# Convert PIL to Tensor
def pil2tensor(image):
    return torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0)
class InspyrenetRembgLoader:
    def __init__(self):
        self.model = None
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "mode": (["base", "fast"],),
                "torchscript_jit": (["default", "on"],),
            },
        }

    RETURN_TYPES = ("INSPYRENET_MODEL",)
    FUNCTION = "load_model"
    CATEGORY = "image"

    def load_model(self, mode, torchscript_jit):
        jit = torchscript_jit == "on"
        self.model = Remover(mode=mode, jit=jit)
        return (self.model,)

class InspyrenetRembgProcess:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("INSPYRENET_MODEL",),
                "image": ("IMAGE",),
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "background_color": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "process_image"
    CATEGORY = "image"

    def process_image(self, model, image, threshold, background_color):
        img_list = []
        mask_list = []  # 新增mask列表
        for img in tqdm(image, "Inspyrenet Rembg"):
            mid = model.process(tensor2pil(img), type='rgba', threshold=threshold)
            
            # 保存mask（在处理背景之前）
            rgba_tensor = pil2tensor(mid)
            mask_list.append(rgba_tensor[:, :, :, 3])  # 保存alpha通道作为mask
            
            if background_color.strip():
                try:
                    rgba_img = mid
                    background = Image.new('RGBA', rgba_img.size, background_color)
                    mid = Image.alpha_composite(background, rgba_img)
                    # 转换为RGB模式，移除alpha通道
                    mid = mid.convert('RGB')
                except ValueError:
                    print(f"无效的颜色值: {background_color}，使用透明背景")
            
            out = pil2tensor(mid)
            img_list.append(out)
            
        img_stack = torch.cat(img_list, dim=0)
        mask_stack = torch.cat(mask_list, dim=0)  # 合并所有mask
        
        # 如果有背景色，返回RGB图像和mask
        if background_color.strip():
            return (img_stack[:, :, :, :3], mask_stack)
        # 如果没有背景色，保持原来的RGBA格式
        else:
            return (img_stack, mask_stack)

NODE_CLASS_MAPPINGS = {
    "InspyrenetRembgLoader": InspyrenetRembgLoader,
    "InspyrenetRembgProcess": InspyrenetRembgProcess
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "InspyrenetRembgLoader": "InSPyReNet Loader",
    "InspyrenetRembgProcess": "InSPyReNet Rembg"
} 