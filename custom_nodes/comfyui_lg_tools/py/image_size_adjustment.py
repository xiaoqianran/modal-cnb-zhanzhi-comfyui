from .md import *
size_data = {}
class ImageSizeAdjustment:
    """图像预览和拉伸调整节点"""
    
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
    FUNCTION = "adjust"
    CATEGORY = "🎈LAOGOU/Image"
    OUTPUT_NODE = True

    def adjust(self, image, unique_id):
        try:
            node_id = unique_id
            
            # 确保清理可能存在的旧数据
            if node_id in size_data:
                del size_data[node_id]
            
            event = Event()
            size_data[node_id] = {
                "event": event,
                "result": None
            }
            
            # 发送预览图像
            preview_image = (torch.clamp(image.clone(), 0, 1) * 255).cpu().numpy().astype(np.uint8)[0]
            pil_image = Image.fromarray(preview_image)
            buffer = io.BytesIO()
            pil_image.save(buffer, format="PNG")
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            try:
                PromptServer.instance.send_sync("image_preview_update", {
                    "node_id": node_id,
                    "image_data": f"data:image/png;base64,{base64_image}"
                })
                
                # 等待前端调整完成
                if not event.wait(timeout=15):
                    if node_id in size_data:
                        del size_data[node_id]
                    return (image,)

                result_image = size_data[node_id]["result"]
                del size_data[node_id]
                return (result_image if result_image is not None else image,)
                
            except Exception as e:
                if node_id in size_data:
                    del size_data[node_id]
                return (image,)
            
        except Exception as e:
            if node_id in size_data:
                del size_data[node_id]
            return (image,)

@PromptServer.instance.routes.post("/image_preview/apply")
async def apply_image_preview(request):
    try:
        # 检查内容类型
        content_type = request.headers.get('Content-Type', '')
        print(f"[ImagePreview] 请求内容类型: {content_type}")
        
        if 'multipart/form-data' in content_type:
            # 处理multipart/form-data请求
            reader = await request.multipart()
            
            # 读取表单字段
            node_id = None
            new_width = None
            new_height = None
            image_data = None
            
            # 逐个处理表单字段
            while True:
                part = await reader.next()
                if part is None:
                    break
                    
                if part.name == 'node_id':
                    node_id = await part.text()
                elif part.name == 'width':
                    new_width = int(await part.text())
                elif part.name == 'height':
                    new_height = int(await part.text())
                elif part.name == 'image_data':
                    # 读取二进制图像数据
                    image_data = await part.read(decode=False)
        else:
            # 处理JSON请求
            data = await request.json()
            node_id = data.get("node_id")
            new_width = data.get("width")
            new_height = data.get("height")
            image_data = None
            
            # 检查是否有base64编码的图像数据
            adjusted_data_base64 = data.get("adjusted_data_base64")
            if adjusted_data_base64:
                if adjusted_data_base64.startswith('data:image'):
                    base64_data = adjusted_data_base64.split(',')[1]
                else:
                    base64_data = adjusted_data_base64
                image_data = base64.b64decode(base64_data)
        
        print(f"[ImagePreview] 接收到数据 - 节点ID: {node_id}")
        print(f"[ImagePreview] 接收到的尺寸: {new_width}x{new_height}")
        
        if node_id not in size_data:
            return web.json_response({"success": False, "error": "节点数据不存在"})
        
        try:
            node_info = size_data[node_id]
            
            if image_data:
                try:
                    # 从二进制数据创建PIL图像
                    buffer = io.BytesIO(image_data)
                    pil_image = Image.open(buffer)
                    
                    # 转换为RGB模式（如果是RGBA）
                    if pil_image.mode == 'RGBA':
                        pil_image = pil_image.convert('RGB')
                    
                    # 转换为numpy数组
                    np_image = np.array(pil_image)
                    
                    # 转换为PyTorch张量 - 使用正确的维度顺序 [B, H, W, C]
                    tensor_image = torch.from_numpy(np_image / 255.0).float().unsqueeze(0)
                    print(f"[ImagePreview] 从二进制数据创建的张量形状: {tensor_image.shape}")
                    node_info["result"] = tensor_image
                except Exception as e:
                    print(f"[ImagePreview] 处理图像数据时出错: {str(e)}")
                    traceback.print_exc()
            
            # 在成功处理后添加标记
            node_info["processed"] = True
            node_info["event"].set()
            return web.json_response({"success": True})
            
        except Exception as e:
            print(f"[ImagePreview] 处理数据时出错: {str(e)}")
            traceback.print_exc()
            if node_id in size_data and "event" in size_data[node_id]:
                size_data[node_id]["event"].set()
            return web.json_response({"success": False, "error": str(e)})

    except Exception as e:
        print(f"[ImagePreview] 请求处理出错: {str(e)}")
        traceback.print_exc()
        return web.json_response({"success": False, "error": str(e)})
    
NODE_CLASS_MAPPINGS = {
    "ImageSizeAdjustment": ImageSizeAdjustment,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageSizeAdjustment": "图像尺寸调整",
}