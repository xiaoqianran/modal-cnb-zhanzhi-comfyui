import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";


app.registerExtension({
    name: "ColorAdjustment.Preview",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "ColorAdjustment") {

            // 扩展节点的构造函数
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated?.apply(this, arguments);
                
                // 设置组件起始位置，确保在端口下方
                this.widgets_start_y = 30; // 调整这个值以适应端口高度
                
                this.setupWebSocket();
                
                const sliderConfig = {
                    min: 0, 
                    max: 2, 
                    step: 0.01,
                    drag_start: () => this.isAdjusting = true,
                    drag_end: () => {
                        this.isAdjusting = false;
                        this.updatePreview(false);
                    }
                };

                const createSlider = (name) => {
                    this.addWidget("slider", name, 1.0, (value) => {
                        this[name] = value;
                        this.updatePreview(true);
                    }, sliderConfig);
                };

                ["brightness", "contrast", "saturation"].forEach(createSlider);
                
                return result;
            };

            // 添加WebSocket设置方法
            nodeType.prototype.setupWebSocket = function() {
                console.log(`[ColorAdjustment] 节点 ${this.id} 设置WebSocket监听`);
                api.addEventListener("color_adjustment_update", async (event) => {
                    const data = event.detail;
                    
                    if (data && data.node_id && data.node_id === this.id.toString()) {
                        console.log(`[ColorAdjustment] 节点 ${this.id} 接收到更新数据`);
                        if (data.image_data) {
                            // 处理base64图像数据
                            console.log("[ColorAdjustment] 接收到base64数据:", {
                                nodeId: this.id,
                                dataLength: data.image_data.length,
                                dataPreview: data.image_data.substring(0, 50) + "...", // 只显示前50个字符
                                isBase64: data.image_data.startsWith("data:image"),
                                timestamp: new Date().toISOString()
                            });
                            
                            this.loadImageFromBase64(data.image_data);
                        } else {
                            console.warn("[ColorAdjustment] 接收到空的图像数据");
                        }
                    }
                });
            };

            // 添加从base64加载图像的方法
            nodeType.prototype.loadImageFromBase64 = function(base64Data) {
                console.log(`[ColorAdjustment] 节点 ${this.id} 开始加载base64图像数据`);
                // 创建一个新的图像对象
                const img = new Image();
                
                // 当图像加载完成时
                img.onload = () => {
                    console.log(`[ColorAdjustment] 节点 ${this.id} 图像加载完成: ${img.width}x${img.height}`);
                    // 创建一个临时画布来获取像素数据
                    const tempCanvas = document.createElement('canvas');
                    tempCanvas.width = img.width;
                    tempCanvas.height = img.height;
                    const tempCtx = tempCanvas.getContext('2d');
                    
                    // 在临时画布上绘制图像
                    tempCtx.drawImage(img, 0, 0);
                    
                    // 获取像素数据
                    const imageData = tempCtx.getImageData(0, 0, img.width, img.height);
                    
                    // 创建二维数组存储像素数据
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
                    
                    // 存储像素数据并更新预览
                    this.originalImageData = pixelArray;
                    this.updatePreview();
                };
                
                // 设置图像源
                img.src = base64Data;
            };

            // 添加节点时的处理
            const onAdded = nodeType.prototype.onAdded;
            nodeType.prototype.onAdded = function() {
                const result = onAdded?.apply(this, arguments);
                
                if (!this.previewElement && this.id !== undefined && this.id !== -1) {
                    // 创建预览容器
                    const previewContainer = document.createElement("div");
                    previewContainer.style.position = "relative";
                    previewContainer.style.width = "100%";
                    previewContainer.style.height = "100%";
                    previewContainer.style.backgroundColor = "#333";
                    previewContainer.style.borderRadius = "8px";
                    previewContainer.style.overflow = "hidden";
                    
                    // 创建预览画布
                    const canvas = document.createElement("canvas");
                    canvas.style.width = "100%";
                    canvas.style.height = "100%";
                    canvas.style.objectFit = "contain";
                    
                    previewContainer.appendChild(canvas);
                    this.canvas = canvas;
                    this.previewElement = previewContainer;
                    
                    // 添加DOM部件
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

            // 更新预览方法
            nodeType.prototype.updatePreview = function(onlyPreview = false) {
                if (!this.originalImageData || !this.canvas) {
                    return;
                }
                
                requestAnimationFrame(() => {
                    const ctx = this.canvas.getContext("2d");
                    const width = this.originalImageData[0].length;
                    const height = this.originalImageData.length;
                    
                    if (!onlyPreview && !this.isAdjusting) {
                        console.log(`[ColorAdjustment] 节点 ${this.id} 更新预览并准备发送数据 (${width}x${height})`);
                    } else {
                        console.log(`[ColorAdjustment] 节点 ${this.id} 仅更新预览 (${width}x${height})`);
                    }
                    
                    // 创建ImageData
                    const imgData = new ImageData(width, height);
                    
                    // 填充原始数据
                    for (let y = 0; y < height; y++) {
                        for (let x = 0; x < width; x++) {
                            const idx = (y * width + x) * 4;
                            imgData.data[idx] = this.originalImageData[y][x][0];     // R
                            imgData.data[idx + 1] = this.originalImageData[y][x][1]; // G
                            imgData.data[idx + 2] = this.originalImageData[y][x][2]; // B
                            imgData.data[idx + 3] = 255;                             // A
                        }
                    }
                    
                    // 应用颜色调整
                    const adjustedData = this.adjustColors(imgData);
                    
                    // 调整画布大小并显示
                    this.canvas.width = width;
                    this.canvas.height = height;
                    ctx.putImageData(adjustedData, 0, 0);
                    
                    // 只在拖动结束时发送数据
                    if (!onlyPreview && !this.isAdjusting) {
                        this.lastAdjustedData = adjustedData;
                        this.sendAdjustedData(adjustedData);
                    }
                });
            };

            // 优化颜色调整方法，提高性能
            nodeType.prototype.adjustColors = function(imageData) {
                const brightness = this.brightness || 1.0;
                const contrast = this.contrast || 1.0;
                const saturation = this.saturation || 1.0;
                
                const result = new Uint8ClampedArray(imageData.data);
                const len = result.length;
                
                // 使用查找表优化常用计算
                const contrastFactor = contrast;
                const contrastOffset = 128 * (1 - contrast);
                
                for (let i = 0; i < len; i += 4) {
                    // 优化亮度和对比度调整
                    let r = Math.min(255, result[i] * brightness);
                    let g = Math.min(255, result[i + 1] * brightness);
                    let b = Math.min(255, result[i + 2] * brightness);
                    
                    r = r * contrastFactor + contrastOffset;
                    g = g * contrastFactor + contrastOffset;
                    b = b * contrastFactor + contrastOffset;
                    
                    // 优化饱和度调整 - 使用更准确的亮度权重
                    if (saturation !== 1.0) {
                        const avg = r * 0.299 + g * 0.587 + b * 0.114;
                        r = avg + (r - avg) * saturation;
                        g = avg + (g - avg) * saturation;
                        b = avg + (b - avg) * saturation;
                    }
                    
                    // 确保值在正确范围内
                    result[i] = Math.min(255, Math.max(0, r));
                    result[i + 1] = Math.min(255, Math.max(0, g));
                    result[i + 2] = Math.min(255, Math.max(0, b));
                }
                
                return new ImageData(result, imageData.width, imageData.height);
            };

            // 添加发送调整后数据的方法，优化为异步
            nodeType.prototype.sendAdjustedData = async function(adjustedData) {
                try {
                    const endpoint = '/color_adjustment/apply';
                    const nodeId = String(this.id);
                    
                    api.fetchApi(endpoint, {
                        method: 'POST',
                        body: JSON.stringify({
                            node_id: nodeId,
                            adjusted_data: Array.from(adjustedData.data),
                            width: adjustedData.width,
                            height: adjustedData.height
                        })
                    }).then(response => {
                        if (!response.ok) {
                            throw new Error(`服务器返回错误: ${response.status}`);
                        }
                        return response.json();
                    }).catch(error => {
                        console.error('数据发送失败:', error);
                    });
                } catch (error) {
                    console.error('发送数据时出错:', error);
                }
            };

            // 节点移除时的处理
            const onRemoved = nodeType.prototype.onRemoved;
            nodeType.prototype.onRemoved = function() {
                const result = onRemoved?.apply(this, arguments);
                
                if (this && this.canvas) {
                    const ctx = this.canvas.getContext("2d");
                    if (ctx) {
                        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
                    }
                    this.canvas = null;
                }
                if (this) {
                    this.previewElement = null;
                }
                
                return result;
            };
        }
    }
}); 


