
from .md import *
crop_node_data = {}
class ImageCropper:
    """图像裁剪专用节点"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("裁剪图像",)
    FUNCTION = "crop"
    CATEGORY = "🎈LAOGOU/Image"

    def crop(self, image, unique_id):
        try:
            node_id = unique_id
            event = Event()
            
            # 初始化节点数据
            crop_node_data[node_id] = {
                "event": event,
                "result": None,
                "processing_complete": False
            }
            
            # 发送预览图像
            preview_image = (torch.clamp(image.clone(), 0, 1) * 255).cpu().numpy().astype(np.uint8)[0]
            pil_image = Image.fromarray(preview_image)
            buffer = io.BytesIO()
            pil_image.save(buffer, format="PNG")
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            try:
                PromptServer.instance.send_sync("image_cropper_update", {
                    "node_id": node_id,
                    "image_data": f"data:image/png;base64,{base64_image}"
                })
                
                # 等待前端裁剪完成
                if not event.wait(timeout=30):
                    print(f"[ImageCropper] 等待超时: 节点ID {node_id}")
                    if node_id in crop_node_data:
                        del crop_node_data[node_id]
                    return (image,)

                # 获取结果
                result_image = None
                
                if node_id in crop_node_data:
                    result_image = crop_node_data[node_id]["result"]
                    del crop_node_data[node_id]
                
                return (result_image if result_image is not None else image,)
                
            except Exception as e:
                print(f"[ImageCropper] 处理过程中出错: {str(e)}")
                traceback.print_exc()
                if node_id in crop_node_data:
                    del crop_node_data[node_id]
                return (image,)
            
        except Exception as e:
            print(f"[ImageCropper] 节点执行出错: {str(e)}")
            traceback.print_exc()
            return (image,)

@PromptServer.instance.routes.post("/image_cropper/apply")
async def apply_image_cropper(request):
    try:
        # 检查内容类型
        content_type = request.headers.get('Content-Type', '')
        print(f"[ImageCropper] 请求内容类型: {content_type}")
        
        node_id = None
        crop_width = None
        crop_height = None
        image_data = None
        
        if 'multipart/form-data' in content_type:
            # 处理multipart/form-data请求
            reader = await request.multipart()
            
            # 读取表单字段
            while True:
                part = await reader.next()
                if part is None:
                    break
                
                if part.name == 'node_id':
                    node_id = await part.text()
                elif part.name == 'width':
                    crop_width = int(await part.text())
                elif part.name == 'height':
                    crop_height = int(await part.text())
                elif part.name == 'image_data':
                    image_data = await part.read(decode=False)
        else:
            # 处理JSON请求
            data = await request.json()
            node_id = data.get("node_id")
            crop_width = data.get("width")
            crop_height = data.get("height")
            
            cropped_data_base64 = data.get("cropped_data_base64")
            if cropped_data_base64:
                if cropped_data_base64.startswith('data:image'):
                    base64_data = cropped_data_base64.split(',')[1]
                else:
                    base64_data = cropped_data_base64
                image_data = base64.b64decode(base64_data)
        
        if node_id not in crop_node_data:
            crop_node_data[node_id] = {
                "event": Event(),
                "result": None,
                "processing_complete": False
            }
        
        try:
            node_info = crop_node_data[node_id]
            
            if image_data:
                try:
                    buffer = io.BytesIO(image_data)
                    pil_image = Image.open(buffer)
                    
                    if pil_image.mode == 'RGBA':
                        pil_image = pil_image.convert('RGB')
                    
                    np_image = np.array(pil_image)
                    
                    if len(np_image.shape) == 3 and np_image.shape[2] == 3:
                        tensor_image = torch.from_numpy(np_image / 255.0).float().unsqueeze(0)
                        node_info["result"] = tensor_image
                        node_info["event"].set()
                    else:
                        print(f"[ImageCropper] 警告: 图像数组形状不符合预期: {np_image.shape}")
                except Exception as e:
                    print(f"[ImageCropper] 处理图像数据时出错: {str(e)}")
                    traceback.print_exc()
                    node_info["event"].set()
            
            return web.json_response({"success": True})
            
        except Exception as e:
            print(f"[ImageCropper] 处理数据时出错: {str(e)}")
            traceback.print_exc()
            if node_id in crop_node_data and "event" in crop_node_data[node_id]:
                crop_node_data[node_id]["event"].set()
            return web.json_response({"success": False, "error": str(e)})

    except Exception as e:
        print(f"[ImageCropper] 请求处理出错: {str(e)}")
        traceback.print_exc()
        return web.json_response({"success": False, "error": str(e)})

@PromptServer.instance.routes.post("/image_cropper/cancel") 
async def cancel_crop(request):
    try:
        data = await request.json()
        node_id = data.get("node_id")
        
        if node_id in crop_node_data:
            # 设置事件，让节点继续执行
            crop_node_data[node_id]["event"].set()
            print(f"[ImageCropper] 取消裁剪操作: 节点ID {node_id}")
            return web.json_response({"success": True})
        
        return web.json_response({"success": False, "error": "节点未找到"})
        
    except Exception as e:
        print(f"[ImageCropper] 取消请求处理出错: {str(e)}")
        traceback.print_exc()
        return web.json_response({"success": False, "error": str(e)})

NODE_CLASS_MAPPINGS = {
    "ImageCropper": ImageCropper,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageCropper": "图像裁剪",
}
