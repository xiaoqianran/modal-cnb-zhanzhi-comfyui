import { app } from "../../scripts/app.js";

// 基础虚拟节点类
class BaseVirtualNode extends LGraphNode {
    constructor(title = "BaseVirtualNode") {
        super(title);
        this.comfyClass = "BaseVirtualNode";
        this.isVirtualNode = true;
        this.properties = this.properties || {};
        this.widgets = this.widgets || [];
    }

    static setUp() {
        if (!this.type) {
            throw new Error(`Missing type for BaseVirtualNode: ${this.title}`);
        }
        LiteGraph.registerNodeType(this.type, this);
        if (this._category) {
            this.category = this._category;
        }
    }
}

// LG节点类
export class lg_note extends BaseVirtualNode {
    constructor(title = lg_note.title) {
        super(title);
        this.comfyClass = "LG_Note";
        this.resizable = true; // 启用可调整大小

        // 默认属性
        this.properties["fontSize"] = 12;
        this.properties["fontFamily"] = "Arial";
        this.properties["fontColor"] = "#ffffff";
        this.properties["textAlign"] = "center";
        this.properties["backgroundColor"] = "transparent";
        this.properties["padding"] = 0;
        this.properties["borderRadius"] = 0;
        this.properties["autoScale"] = true; // 是否启用自动缩放
        this.properties["baseFontSize"] = 36; // 基础字体大小，用于缩放计算

        // 初始大小
        this.size = [160, 40];
        this.baseSize = [160, 40]; // 基础大小，用于缩放计算

        this.color = "#fff0";
        this.bgcolor = "#fff0";
    }

    // 计算缩放后的字体大小
    calculateScaledFontSize() {
        if (!this.properties["autoScale"]) {
            return this.properties["fontSize"];
        }

        // 计算缩放比例（基于宽度和高度的平均值）
        const widthScale = this.size[0] / this.baseSize[0];
        const heightScale = this.size[1] / this.baseSize[1];
        const scale = (widthScale + heightScale) / 2;

        // 计算缩放后的字体大小，不限制最大最小值
        const scaledFontSize = this.properties["baseFontSize"] * scale;

        // 确保字体大小至少为1像素，避免无效值
        return Math.max(1, scaledFontSize);
    }

    draw(ctx) {
        this.flags = this.flags || {};
        this.flags.allow_interaction = !this.flags.pinned;

        ctx.save();
        this.color = "#fff0";
        this.bgcolor = "#fff0";

        const fontColor = this.properties["fontColor"] || "#ffffff";
        const backgroundColor = this.properties["backgroundColor"] || "";

        // 使用缩放后的字体大小
        const currentFontSize = this.calculateScaledFontSize();
        this.properties["fontSize"] = currentFontSize; // 更新当前字体大小属性

        ctx.font = `${Math.max(currentFontSize || 0, 1)}px ${this.properties["fontFamily"] ?? "Arial"}`;

        const padding = Number(this.properties["padding"]) ?? 0;
        const lines = this.title.replace(/\n*$/, "").split("\n");

        // 如果不是自动缩放模式，则根据文本内容调整节点大小
        if (!this.properties["autoScale"]) {
            const maxWidth = Math.max(...lines.map((s) => ctx.measureText(s).width));
            this.size[0] = maxWidth + padding * 2;
            this.size[1] = currentFontSize * lines.length + padding * 2;
        }

        // 绘制背景
        if (backgroundColor) {
            ctx.beginPath();
            const borderRadius = Number(this.properties["borderRadius"]) || 0;
            ctx.roundRect(0, 0, this.size[0], this.size[1], [borderRadius]);
            ctx.fillStyle = backgroundColor;
            ctx.fill();
        }

        // 设置文本对齐
        ctx.textAlign = "left";
        let textX = padding;
        if (this.properties["textAlign"] === "center") {
            ctx.textAlign = "center";
            textX = this.size[0] / 2;
        } else if (this.properties["textAlign"] === "right") {
            ctx.textAlign = "right";
            textX = this.size[0] - padding;
        }

        // 绘制文本
        ctx.textBaseline = "middle"; // 使用middle基线
        ctx.fillStyle = fontColor;

        const lineHeight = currentFontSize * 1.2; // 行高稍微大于字体大小
        const totalTextHeight = lines.length * lineHeight;

        // 计算垂直居中的起始位置
        let startY = (this.size[1] - totalTextHeight) / 2 + lineHeight / 2;

        for (let i = 0; i < lines.length; i++) {
            const currentY = startY + i * lineHeight;
            ctx.fillText(lines[i] || " ", textX, currentY);
        }

        ctx.restore();
    }

    onDblClick(event, pos, canvas) {
        LGraphCanvas.active_canvas.showShowNodePanel(this);
    }

    onShowCustomPanelInfo(panel) {
        // 移除不需要的属性面板项
        panel.querySelector('div.property[data-property="Mode"]')?.remove();
        panel.querySelector('div.property[data-property="Color"]')?.remove();
        panel.querySelector('div.property[data-property="baseFontSize"]')?.remove(); // 隐藏baseFontSize属性

        // 为所有属性添加实时回调
        setTimeout(() => {
            this.convertTitleToTextarea(panel);
            this.addRealTimeCallbacks(panel);
            this.createColorPickerRow(panel);
            this.moveSliderPropertiesToEnd(panel);
            this.convertToSlider(panel, "fontSize", 1, 500, 1);
            this.convertToSlider(panel, "padding", 0, 50, 1);
            this.convertToSlider(panel, "borderRadius", 0, 50, 1);
        }, 10);
    }

    // 将 Title 转换为多行文本框
    convertTitleToTextarea(panel) {
        const titleElement = panel.querySelector('div.property[data-property="Title"]');
        if (!titleElement) return;

        const valueElement = titleElement.querySelector('.property_value');
        if (!valueElement) return;

        // 移除原有的contenteditable属性
        valueElement.removeAttribute('contenteditable');

        // 创建多行文本框
        const textarea = document.createElement('textarea');
        textarea.value = this.title || '';
        textarea.style.cssText = `
            width: 100%;
            min-height: 60px;
            max-height: 150px;
            background: rgba(255,255,255,0.1);
            border: 1px solid #555;
            border-radius: 4px;
            padding: 8px;
            color: #fff;
            font-size: 13px;
            font-family: inherit;
            resize: vertical;
            outline: none;
            box-sizing: border-box;
        `;

        // 实时更新事件
        textarea.addEventListener('input', (e) => {
            this.title = e.target.value;
            this.setDirtyCanvas(true, true);
        });

        // 回车键不关闭面板，允许多行输入
        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                // 允许回车换行，不阻止默认行为
                e.stopPropagation(); // 阻止事件冒泡，防止关闭面板
            }
        });

        // 失去焦点时确保更新
        textarea.addEventListener('blur', (e) => {
            this.title = e.target.value;
            this.setDirtyCanvas(true, true);
        });

        // 替换原有的值显示元素
        valueElement.style.display = 'none';
        titleElement.appendChild(textarea);

        // 调整标题元素的布局
        titleElement.style.cssText = `
            display: block;
            margin: 8px 0;
            padding: 8px 0;
        `;

        // 调整标签样式
        const nameElement = titleElement.querySelector('.property_name');
        if (nameElement) {
            nameElement.style.cssText = `
                display: block;
                margin-bottom: 6px;
                font-weight: bold;
                color: #ccc;
            `;
        }
    }

    // 为所有属性添加实时回调
    addRealTimeCallbacks(panel) {
        // 为文本输入框添加实时回调
        const textProperties = ["fontFamily"];
        textProperties.forEach(propName => {
            const element = panel.querySelector(`div.property[data-property="${propName}"] .property_value`);
            if (element) {
                element.addEventListener('input', () => {
                    this.properties[propName] = element.textContent;
                    this.setDirtyCanvas(true, true);
                });
                element.addEventListener('blur', () => {
                    this.properties[propName] = element.textContent;
                    this.setDirtyCanvas(true, true);
                });
            }
        });

        // 为下拉选择框添加实时回调
        const comboProperties = ["textAlign"];
        comboProperties.forEach(propName => {
            const element = panel.querySelector(`div.property[data-property="${propName}"] .property_value`);
            if (element) {
                // 下拉选择的回调已经在原有代码中处理
            }
        });

        // 为布尔值属性添加实时回调
        const booleanProperties = ["autoScale"];
        booleanProperties.forEach(propName => {
            const element = panel.querySelector(`div.property[data-property="${propName}"]`);
            if (element) {
                // 布尔值的点击事件已经在原有代码中处理，但我们确保它有实时更新
                element.addEventListener('click', () => {
                    // 延迟一点确保值已经更新
                    setTimeout(() => {
                        this.setDirtyCanvas(true, true);
                        // 当 autoScale 状态改变时，更新 fontSize 滑条显示
                        this.updateFontSizeSlider(panel);
                    }, 10);
                });
            }
        });
    }

    // 更新 fontSize 滑条显示
    updateFontSizeSlider(panel) {
        const fontSizeSlider = panel.querySelector('div.property[data-property="fontSize"] input[type="range"]');
        const fontSizeValue = panel.querySelector('div.property[data-property="fontSize"] .property_value');

        if (fontSizeSlider && fontSizeValue) {
            let displayValue;
            if (this.properties["autoScale"]) {
                // auto 模式下显示 baseFontSize
                displayValue = this.properties["baseFontSize"];
            } else {
                // 非 auto 模式下显示实际 fontSize
                displayValue = this.properties["fontSize"];
            }

            fontSizeSlider.value = displayValue.toString();
            fontSizeValue.textContent = displayValue.toString();
        }
    }

    // 创建颜色选择器行
    createColorPickerRow(panel) {
        // 找到颜色相关的属性元素
        const fontColorElement = panel.querySelector('div.property[data-property="fontColor"]');
        const backgroundColorElement = panel.querySelector('div.property[data-property="backgroundColor"]');

        if (!fontColorElement || !backgroundColorElement) return;

        // 创建颜色选择器容器
        const colorRow = document.createElement('div');
        colorRow.style.cssText = `
            display: flex;
            gap: 10px;
            margin: 10px 0;
            padding: 8px;
            background: rgba(255,255,255,0.05);
            border-radius: 6px;
        `;

        // 创建字体颜色选择器
        const fontColorPicker = this.createColorPicker("Font Color", this.properties.fontColor, (color) => {
            this.properties.fontColor = color;
            this.setDirtyCanvas(true, true);
        });

        // 创建背景颜色选择器
        const backgroundColorPicker = this.createColorPicker("Background", this.properties.backgroundColor, (color) => {
            this.properties.backgroundColor = color;
            this.setDirtyCanvas(true, true);
        });

        colorRow.appendChild(fontColorPicker);
        colorRow.appendChild(backgroundColorPicker);

        // 移除原有的颜色属性元素
        fontColorElement.remove();
        backgroundColorElement.remove();

        // 在合适的位置插入颜色选择器行
        const titleElement = panel.querySelector('div.property[data-property="Title"]');
        if (titleElement && titleElement.nextSibling) {
            panel.content.insertBefore(colorRow, titleElement.nextSibling);
        } else {
            panel.content.appendChild(colorRow);
        }
    }

    // 创建颜色选择器
    createColorPicker(label, currentColor, callback) {
        const container = document.createElement('div');
        container.style.cssText = `
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
        `;

        // 标签
        const labelElement = document.createElement('span');
        labelElement.textContent = label;
        labelElement.style.cssText = `
            font-size: 12px;
            color: #ccc;
            font-weight: bold;
        `;

        // 颜色选择器容器
        const pickerContainer = document.createElement('div');
        pickerContainer.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
            width: 100%;
        `;

        // 处理初始颜色值
        const initialColor = currentColor || '#ffffff';
        const isHexColor = /^#[0-9A-Fa-f]{6}$/i.test(initialColor);

        // 颜色输入框
        const colorInput = document.createElement('input');
        colorInput.type = 'color';
        // 只有十六进制颜色才设置到颜色选择器
        colorInput.value = isHexColor ? initialColor : '#ffffff';
        colorInput.style.cssText = `
            width: 40px;
            height: 30px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            background: none;
            padding: 0;
        `;

        // 颜色值显示
        const colorValue = document.createElement('input');
        colorValue.type = 'text';
        colorValue.value = initialColor;
        colorValue.style.cssText = `
            flex: 1;
            background: rgba(255,255,255,0.1);
            border: 1px solid #555;
            border-radius: 4px;
            padding: 4px 8px;
            color: #fff;
            font-size: 11px;
            font-family: monospace;
        `;

        // 添加占位符提示
        colorValue.placeholder = 'e.g. #ff0000, red, transparent';

        // 颜色选择器事件
        colorInput.addEventListener('input', (e) => {
            const color = e.target.value;
            colorValue.value = color;
            callback(color);
        });

        // 文本输入事件 - 支持实时验证
        colorValue.addEventListener('input', (e) => {
            const formattedColor = formatColor(e.target.value);
            if (isValidColor(formattedColor)) {
                // 如果是十六进制颜色，同步到颜色选择器
                if (/^#[0-9A-Fa-f]{6}$/i.test(formattedColor)) {
                    colorInput.value = formattedColor;
                }
                callback(formattedColor);
            }
        });

        // 颜色格式化函数 - 简化版本
        const formatColor = (input) => {
            let color = input.trim();

            // 如果没有 # 且是6位十六进制，自动添加 #
            if (!color.startsWith('#') && /^[0-9A-Fa-f]{6}$/i.test(color)) {
                color = '#' + color;
            }

            return color;
        };

        // 颜色验证函数 - 使用浏览器原生验证
        const isValidColor = (color) => {
            // 空值不是有效颜色
            if (!color || color.trim() === '') return false;

            // 创建一个临时元素来测试颜色是否有效
            const tempElement = document.createElement('div');
            const originalColor = tempElement.style.color;

            try {
                tempElement.style.color = color;
                // 如果浏览器接受这个颜色值，style.color 会被设置且不等于原始值
                const isValid = tempElement.style.color !== originalColor || tempElement.style.color !== '';
                console.log(`Color validation: "${color}" -> ${isValid}`); // 调试信息
                return isValid;
            } catch (e) {
                console.log(`Color validation error: "${color}" -> false`); // 调试信息
                return false;
            }
        };

        // 回车键事件
        colorValue.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const formattedColor = formatColor(e.target.value);
                if (isValidColor(formattedColor)) {
                    colorValue.value = formattedColor;
                    // 如果是十六进制颜色，同步到颜色选择器
                    if (/^#[0-9A-Fa-f]{6}$/i.test(formattedColor)) {
                        colorInput.value = formattedColor;
                    }
                    callback(formattedColor);
                    e.target.blur(); // 失去焦点
                } else {
                    // 如果格式不正确，恢复到之前的值
                    colorValue.value = colorInput.value;
                }
            }
        });

        colorValue.addEventListener('blur', (e) => {
            const formattedColor = formatColor(e.target.value);
            if (isValidColor(formattedColor)) {
                // 失去焦点时如果格式正确，应用颜色
                colorValue.value = formattedColor;
                // 如果是十六进制颜色，同步到颜色选择器
                if (/^#[0-9A-Fa-f]{6}$/i.test(formattedColor)) {
                    colorInput.value = formattedColor;
                }
                callback(formattedColor);
            } else {
                // 如果格式不正确，恢复到之前的值
                colorValue.value = colorInput.value;
            }
        });

        pickerContainer.appendChild(colorInput);
        pickerContainer.appendChild(colorValue);
        container.appendChild(labelElement);
        container.appendChild(pickerContainer);

        return container;
    }

    // 将滑条属性移动到最后
    moveSliderPropertiesToEnd(panel) {
        const sliderProperties = ["fontSize", "padding", "borderRadius"];
        const content = panel.content;

        sliderProperties.forEach(propName => {
            const element = panel.querySelector(`div.property[data-property="${propName}"]`);
            if (element) {
                content.appendChild(element);
            }
        });
    }

    // 将数字输入框转换为滑条样式
    convertToSlider(panel, propertyName, min, max, step) {
        const propertyElement = panel.querySelector(`div.property[data-property="${propertyName}"]`);
        if (!propertyElement) return;

        const valueElement = propertyElement.querySelector('.property_value');
        if (!valueElement) return;

        // 移除原有的contenteditable属性
        valueElement.removeAttribute('contenteditable');

        // 重新设置属性元素的布局
        propertyElement.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 0;
            margin: 4px 0;
        `;

        // 创建滑条容器
        const sliderContainer = document.createElement('div');
        sliderContainer.style.cssText = `
            display: flex;
            align-items: center;
            flex: 1;
            margin-left: 10px;
            gap: 10px;
        `;

        // 创建滑条输入
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = min.toString();
        slider.max = max.toString();
        slider.step = step.toString();

        // 特殊处理 fontSize：在 auto 模式下使用 baseFontSize
        let initialValue;
        if (propertyName === 'fontSize' && this.properties["autoScale"]) {
            initialValue = this.properties["baseFontSize"];
        } else {
            initialValue = this.properties[propertyName];
        }
        slider.value = initialValue.toString();

        // 设置滑条样式 - 更显眼的设计
        slider.style.cssText = `
            flex: 1;
            height: 6px;
            background: linear-gradient(to right, #555, #777);
            outline: none;
            border-radius: 3px;
            appearance: none;
            -webkit-appearance: none;
            cursor: pointer;
        `;

        // 添加更显眼的滑条样式
        if (!document.getElementById('slider-styles')) {
            const style = document.createElement('style');
            style.id = 'slider-styles';
            style.textContent = `
                input[type="range"]::-webkit-slider-thumb {
                    appearance: none;
                    -webkit-appearance: none;
                    height: 20px;
                    width: 20px;
                    border-radius: 50%;
                    background: linear-gradient(45deg, #4CAF50, #45a049);
                    cursor: pointer;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                    border: 2px solid #fff;
                }
                input[type="range"]::-webkit-slider-thumb:hover {
                    background: linear-gradient(45deg, #5CBF60, #55b059);
                    transform: scale(1.1);
                }
                input[type="range"]::-moz-range-thumb {
                    height: 20px;
                    width: 20px;
                    border-radius: 50%;
                    background: linear-gradient(45deg, #4CAF50, #45a049);
                    cursor: pointer;
                    border: 2px solid #fff;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                }
                input[type="range"]::-moz-range-track {
                    background: linear-gradient(to right, #555, #777);
                    height: 6px;
                    border-radius: 3px;
                }
            `;
            document.head.appendChild(style);
        }

        // 修改数值显示样式 - 简洁的数字显示
        valueElement.style.cssText = `
            min-width: 35px;
            text-align: center;
            color: #fff;
            font-size: 12px;
            font-weight: bold;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            padding: 2px 6px;
        `;

        // 设置初始显示值
        valueElement.textContent = initialValue.toString();

        // 滑条事件处理 - 实时更新
        slider.addEventListener('input', (e) => {
            const newValue = parseFloat(e.target.value);

            // 特殊处理 fontSize：在 auto 模式下调整 baseFontSize
            if (propertyName === 'fontSize' && this.properties["autoScale"]) {
                this.properties["baseFontSize"] = newValue;
                // 显示的值仍然是 baseFontSize
                valueElement.textContent = newValue.toString();
            } else {
                this.properties[propertyName] = newValue;
                valueElement.textContent = newValue.toString();
            }

            // 立即更新节点显示
            this.setDirtyCanvas(true, true);
        });

        // 滑条拖拽结束事件
        slider.addEventListener('change', (e) => {
            const newValue = parseFloat(e.target.value);

            // 特殊处理 fontSize：在 auto 模式下调整 baseFontSize
            if (propertyName === 'fontSize' && this.properties["autoScale"]) {
                this.properties["baseFontSize"] = newValue;
                valueElement.textContent = newValue.toString();
            } else {
                this.properties[propertyName] = newValue;
                valueElement.textContent = newValue.toString();
            }

            this.setDirtyCanvas(true, true);
        });

        // 清空原有内容并重新组织布局
        const nameElement = propertyElement.querySelector('.property_name');
        propertyElement.innerHTML = '';

        // 重新添加元素：名称在左边，滑条和数值在右边
        propertyElement.appendChild(nameElement);
        sliderContainer.appendChild(slider);
        sliderContainer.appendChild(valueElement);
        propertyElement.appendChild(sliderContainer);
    }


    // 处理节点大小改变
    onResize(size) {
        if (this.properties["autoScale"]) {
            // 当节点大小改变时，重新计算字体大小
            this.setDirtyCanvas(true, true);
        }
    }

}

// 节点类型配置
lg_note.type = "LG_Note";
lg_note.title = "🎈LG_Note";
lg_note.title_mode = LiteGraph.NO_TITLE;
lg_note.collapsable = false;
lg_note._category = "🎈LAOGOU/Utils";

// 属性定义
lg_note["@fontSize"] = { type: "number" };
lg_note["@baseFontSize"] = { type: "number" }; // 基础字体大小，用于序列化
lg_note["@fontFamily"] = { type: "string" };
lg_note["@fontColor"] = { type: "string" };
lg_note["@textAlign"] = { type: "combo", values: ["left", "center", "right"] };
lg_note["@backgroundColor"] = { type: "string" };
lg_note["@padding"] = { type: "number" };
lg_note["@borderRadius"] = { type: "number" };
lg_note["@autoScale"] = { type: "boolean" };

// 全局状态管理
const labelNodeState = {
    processingMouseDown: false,
    lastAdjustedMouseEvent: null
};

// 重写绘制节点方法
const oldDrawNode = LGraphCanvas.prototype.drawNode;
LGraphCanvas.prototype.drawNode = function (node, ctx) {
    if (node.constructor === lg_note) {
        node.bgcolor = "transparent";
        node.color = "transparent";
        const v = oldDrawNode.apply(this, arguments);
        node.draw(ctx);
        return v;
    }
    const v = oldDrawNode.apply(this, arguments);
    return v;
};

// 重写鼠标事件处理
const oldGetNodeOnPos = LGraph.prototype.getNodeOnPos;
LGraph.prototype.getNodeOnPos = function (x, y, nodes_list, margin) {
    if (nodes_list &&
        labelNodeState.processingMouseDown &&
        labelNodeState.lastAdjustedMouseEvent?.type.includes("down") &&
        labelNodeState.lastAdjustedMouseEvent?.which === 1) {
        let isDoubleClick = LiteGraph.getTime() - LGraphCanvas.active_canvas.last_mouseclick < 300;
        if (!isDoubleClick) {
            nodes_list = [...nodes_list].filter((n) => !(n instanceof lg_note) || !n.flags?.pinned);
        }
    }
    return oldGetNodeOnPos.apply(this, [x, y, nodes_list, margin]);
};

// 鼠标事件监听
const processMouseDown = LGraphCanvas.prototype.processMouseDown;
LGraphCanvas.prototype.processMouseDown = function (e) {
    labelNodeState.processingMouseDown = true;
    const returnVal = processMouseDown.apply(this, [...arguments]);
    labelNodeState.processingMouseDown = false;
    return returnVal;
};

const adjustMouseEvent = LGraphCanvas.prototype.adjustMouseEvent;
LGraphCanvas.prototype.adjustMouseEvent = function (e) {
    adjustMouseEvent.apply(this, [...arguments]);
    labelNodeState.lastAdjustedMouseEvent = e;
};

// 注册扩展
app.registerExtension({
    name: "LG_Note",
    registerCustomNodes() {
        lg_note.setUp();
    },
});
