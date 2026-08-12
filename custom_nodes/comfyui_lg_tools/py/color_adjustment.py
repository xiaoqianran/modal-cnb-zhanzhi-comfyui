from .md import *
node_data = {}
class ColorAdjustment:
    """颜色调整节点"""
    
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
            event = Event()
            node_data[node_id] = {
                "event": event,
                "result": None,
                "shape": image.shape
            }
            
            preview_image = (torch.clamp(image.clone(), 0, 1) * 255).cpu().numpy().astype(np.uint8)[0]
            pil_image = Image.fromarray(preview_image)
            buffer = io.BytesIO()
            pil_image.save(buffer, format="PNG")
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            try:
                PromptServer.instance.send_sync("color_adjustment_update", {
                    "node_id": node_id,
                    "image_data": f"data:image/png;base64,{base64_image}"
                })
                
                if not event.wait(timeout=5):
                    if node_id in node_data:
                        del node_data[node_id]
                    return (image,)

                result_image = node_data[node_id]["result"]
                del node_data[node_id]
                return (result_image if result_image is not None else image,)
                
            except Exception as e:
                if node_id in node_data:
                    del node_data[node_id]
                return (image,)
            
        except Exception as e:
            if node_id in node_data:
                del node_data[node_id]
            return (image,)

@PromptServer.instance.routes.post("/color_adjustment/apply")
async def apply_color_adjustment(request):
    try:
        data = await request.json()
        node_id = data.get("node_id")
        adjusted_data = data.get("adjusted_data")
        
        if node_id not in node_data:
            return web.json_response({"success": False, "error": "节点数据不存在"})
        
        try:
            node_info = node_data[node_id]
            
            if isinstance(adjusted_data, list):
                batch, height, width, channels = node_info["shape"]
                
                if len(adjusted_data) >= height * width * 4:
                    rgba_array = np.array(adjusted_data, dtype=np.uint8).reshape(height, width, 4)
                    rgb_array = rgba_array[:, :, :3]
                    tensor_image = torch.from_numpy(rgb_array / 255.0).float().reshape(batch, height, width, channels)
                    node_info["result"] = tensor_image
            
            node_info["event"].set()
            return web.json_response({"success": True})
            
        except Exception as e:
            if node_id in node_data and "event" in node_data[node_id]:
                node_data[node_id]["event"].set()
            return web.json_response({"success": False, "error": str(e)})

    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

NODE_CLASS_MAPPINGS = {
    "ColorAdjustment": ColorAdjustment,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ColorAdjustment": "颜色调整",
}
