import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "ImagePreview.Adjustment",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "ImageSizeAdjustment") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated?.apply(this, arguments);
                this.widgets_start_y = 30;
                this.setupWebSocket();
                
                // 创建偏移量控制器
                const createOffsetWidget = (name, defaultValue = 0) => {
                    const widget = ComfyWidgets.INT(this, name, ["INT", { 
                        default: defaultValue, 
                        min: -9999, 
                        max: 9999, 
                        step: 8
                    }]);
                    
                    // 设置值变化回调
                    widget.widget.callback = (value) => {
                        // 将值调整为8的倍数
                        value = Math.floor(value / 8) * 8;
                        
                        if (this.originalImageData) {
                            const size = name === "x_offset" 
                                ? this.originalImageData[0]?.length 
                                : this.originalImageData.length;
                            
                            if (value < 0 && Math.abs(value) > size) {
                                value = -size;
                                this.widgets.find(w => w.name === name).value = value;
                            }
                        }
                        this[name] = value;
                        this.updatePreview(true);
                    };
                    
                    // 设置拖动事件
                    widget.widget.onDragStart = function() {
                        this.node.isAdjusting = true;
                    };
                    
                    widget.widget.onDragEnd = function() {
                        this.node.isAdjusting = false;
                        this.node.updatePreview(false);
                    };
                    
                    return widget;
                };
                
                // 创建 x 和 y 偏移控制器
                createOffsetWidget("x_offset");
                createOffsetWidget("y_offset");
                
                return result;
            };

            // 添加WebSocket设置方法
            nodeType.prototype.setupWebSocket = function() {
                api.addEventListener("image_preview_update", async (event) => {
                    const data = event.detail;
                    if (data && data.node_id === this.id.toString()) {
                        console.log(`[ImagePreview] 节点 ${this.id} 接收到更新数据`);
                        if (data.image_data) {
                            this.loadImageFromBase64(data.image_data);
                        }
                    }
                });
            };

            // 更新预览方法
            nodeType.prototype.updatePreview = function(onlyPreview = false) {
                if (!this.originalImageData || !this.canvas) {
                    return;
                }
                
                if (this.updateTimeout) {
                    clearTimeout(this.updateTimeout);
                }
                
                this.updateTimeout = setTimeout(() => {
                    const ctx = this.canvas.getContext("2d");
                    const originalWidth = this.originalImageData[0].length;
                    const originalHeight = this.originalImageData.length;
                    
                    let x_offset = this.x_offset || 0;
                    let y_offset = this.y_offset || 0;
                    
                    // 计算新的宽度和高度
                    const newWidth = Math.max(1, originalWidth + x_offset);
                    const newHeight = Math.max(1, originalHeight + y_offset);
                    
                    // 同步设置画布和容器的尺寸
                    this.canvas.width = newWidth;
                    this.canvas.height = newHeight;
                    
                    ctx.clearRect(0, 0, newWidth, newHeight);
                    
                    if (!this.tempCanvas) {
                        this.tempCanvas = document.createElement('canvas');
                    }
                    
                    if (!this.originalImageRendered) {
                        this.tempCanvas.width = originalWidth;
                        this.tempCanvas.height = originalHeight;
                        const tempCtx = this.tempCanvas.getContext('2d');
                        
                        const imgData = new ImageData(originalWidth, originalHeight);
                        for (let y = 0; y < originalHeight; y++) {
                            for (let x = 0; x < originalWidth; x++) {
                                const dstIdx = (y * originalWidth + x) * 4;
                                const srcPixel = this.originalImageData[y][x];
                                imgData.data[dstIdx] = srcPixel[0];     // R
                                imgData.data[dstIdx + 1] = srcPixel[1]; // G
                                imgData.data[dstIdx + 2] = srcPixel[2]; // B
                                imgData.data[dstIdx + 3] = 255;         // A
                            }
                        }
                        tempCtx.putImageData(imgData, 0, 0);
                        this.originalImageRendered = true;
                    }
                    
                    ctx.drawImage(
                        this.tempCanvas,
                        0, 0,
                        originalWidth, originalHeight,
                        0, 0,
                        newWidth, newHeight
                    );
                    
                    if (!onlyPreview && !this.isAdjusting) {
                        const adjustedData = ctx.getImageData(0, 0, newWidth, newHeight);
                        this.sendAdjustedData(adjustedData);
                    }
                }, this.isAdjusting ? 50 : 0);
            };

            // 发送调整后的数据
            nodeType.prototype.sendAdjustedData = async function(adjustedData) {
                try {
                    const endpoint = '/image_preview/apply';
                    const nodeId = String(this.id);
                    
                    console.log(`[ImagePreview] 发送调整后的数据 - 尺寸: ${adjustedData.width}x${adjustedData.height}`);
                    
                    const canvas = document.createElement('canvas');
                    canvas.width = adjustedData.width;
                    canvas.height = adjustedData.height;
                    const ctx = canvas.getContext('2d');
                    ctx.putImageData(adjustedData, 0, 0);
                    
                    const blob = await new Promise(resolve => {
                        canvas.toBlob(resolve, 'image/jpeg', 0.9);
                    });
                    
                    const formData = new FormData();
                    formData.append('node_id', nodeId);
                    formData.append('width', adjustedData.width);
                    formData.append('height', adjustedData.height);
                    formData.append('image_data', blob, 'adjusted_image.jpg');
                    
                    api.fetchApi(endpoint, {
                        method: 'POST',
                        body: formData
                    });
                } catch (error) {
                    console.error('发送数据时出错:', error);
                }
            };

            // 添加从base64加载图像的方法
            nodeType.prototype.loadImageFromBase64 = function(base64Data) {
                const img = new Image();
                
                img.onload = () => {
                    this.originalImageRendered = false;
                    
                    const tempCanvas = document.createElement('canvas');
                    tempCanvas.width = img.width;
                    tempCanvas.height = img.height;
                    const tempCtx = tempCanvas.getContext('2d');
                    
                    tempCtx.drawImage(img, 0, 0);
                    const imageData = tempCtx.getImageData(0, 0, img.width, img.height);
                    
                    const pixelArray = [];
                    for (let y = 0; y < img.height; y++) {
                        const row = [];
                        for (let x = 0; x < img.width; x++) {
                            const idx = (y * img.width + x) * 4;
                            row.push([
                                imageData.data[idx],     // R
                                imageData.data[idx + 1], // G
                                imageData.data[idx + 2]  // B
                            ]);
                        }
                        pixelArray.push(row);
                    }
                    
                    this.originalImageData = pixelArray;
                    this.updatePreview();
                };
                
                img.src = base64Data;
            };

            // 添加节点时的处理
            const onAdded = nodeType.prototype.onAdded;
            nodeType.prototype.onAdded = function() {
                const result = onAdded?.apply(this, arguments);
                
                if (!this.previewElement && this.id !== undefined && this.id !== -1) {
                    const previewContainer = document.createElement("div");
                    previewContainer.style.position = "relative";
                    previewContainer.style.width = "100%";
                    previewContainer.style.height = "100%";
                    previewContainer.style.backgroundColor = "#333";
                    previewContainer.style.borderRadius = "8px";
                    previewContainer.style.overflow = "hidden";
                    
                    const canvas = document.createElement("canvas");
                    canvas.style.width = "100%";
                    canvas.style.height = "100%";
                    canvas.style.objectFit = "contain";
                    
                    previewContainer.appendChild(canvas);
                    
                    this.canvas = canvas;
                    this.previewElement = previewContainer;
                    
                    this.widgets ||= [];
                    this.widgets_up = true;
                    
                    requestAnimationFrame(() => {
                        if (this.widgets) {
                            this.previewWidget = this.addDOMWidget("preview", "preview", previewContainer);
                            this.setDirtyCanvas(true, true);
                        }
                    });
                }
                
                return result;
            };
        }
    }
}); 