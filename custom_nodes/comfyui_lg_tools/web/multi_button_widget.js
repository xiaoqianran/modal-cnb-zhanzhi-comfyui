
// 通用多按钮组件定义
const MultiButtonWidget = (app, inputName, options, buttons) => {
    const widget = {
        name: inputName,
        type: "multi_button",
        y: 0,
        value: null,
        options: options || {},
        clicked_button: null,
        click_time: 0
    };

    // 使用 ComfyUI 原生样式常量
    const margin = 15;
    const button_height = LiteGraph.NODE_WIDGET_HEIGHT || 20;
    const label_width = options.labelWidth !== undefined ? options.labelWidth : 80;
    const button_spacing = options.buttonSpacing || 4;
    const button_count = buttons.length;
    
    // 原生 ComfyUI 按钮颜色
    const BUTTON_BGCOLOR = "#222";
    const BUTTON_OUTLINE_COLOR = "#666";
    const BUTTON_TEXT_COLOR = "#DDD";
    const BUTTON_CLICKED_COLOR = "#AAA";

    widget.draw = function(ctx, node, width, Y, height) {
        if (app.canvas.ds.scale < 0.50) return;
        
        ctx.save();
        ctx.lineWidth = 1;
        
        // 绘制标签（仅当有标签时）
        if (label_width > 0 && inputName) {
            ctx.fillStyle = LiteGraph.WIDGET_SECONDARY_TEXT_COLOR;
            ctx.textAlign = "left";
            ctx.fillText(inputName, margin, Y + height * 0.7);
        }

        // 计算按钮区域
        const label_space = label_width > 0 ? label_width : 0;
        const left_margin = label_width > 0 ? margin : 10; // 没有标签时使用小边距避免超出节点
        const right_margin = label_width > 0 ? margin : 10; // 右边也保持小边距
        const available_width = width - label_space - left_margin - right_margin;
        const total_spacing = button_spacing * (button_count - 1);
        const button_width = (available_width - total_spacing) / button_count;
        const start_x = label_space + left_margin;
        
        // 检查点击高亮是否需要清除
        const now = Date.now();
        if (widget.click_time && now - widget.click_time > 150) {
            widget.clicked_button = null;
            widget.click_time = 0;
        }
        
        // 循环绘制所有按钮
        for (let i = 0; i < button_count; i++) {
            const button = buttons[i];
            const button_x = start_x + i * (button_width + button_spacing);
            
            // 确定按钮颜色（点击高亮或默认）
            const is_clicked = (widget.clicked_button === i);
            const button_color = is_clicked ? BUTTON_CLICKED_COLOR : 
                                (button.color || BUTTON_BGCOLOR);
            
            // 绘制按钮背景
            ctx.fillStyle = button_color;
            ctx.fillRect(button_x, Y, button_width, button_height);
            
            // 绘制按钮边框
            ctx.strokeStyle = BUTTON_OUTLINE_COLOR;
            ctx.strokeRect(button_x, Y, button_width, button_height);
            
            // 绘制按钮文字
            ctx.fillStyle = BUTTON_TEXT_COLOR;
            ctx.textAlign = "center";
            ctx.fillText(button.text, button_x + button_width / 2, Y + button_height * 0.7);
        }
        
        ctx.restore();
    };

    widget.onPointerDown = function(pointer, node) {
        const e = pointer.eDown;
        const label_space = label_width > 0 ? label_width : 0;
        const left_margin = label_width > 0 ? margin : 10;
        const right_margin = label_width > 0 ? margin : 10;
        const x = e.canvasX - node.pos[0] - label_space - left_margin;
        const available_width = node.size[0] - label_space - left_margin - right_margin;
        const total_spacing = button_spacing * (button_count - 1);
        const button_width = (available_width - total_spacing) / button_count;
        
        pointer.onClick = () => {
            // 计算点击了哪个按钮
            for (let i = 0; i < button_count; i++) {
                const button_start = i * (button_width + button_spacing);
                const button_end = button_start + button_width;
                
                if (x >= button_start && x <= button_end) {
                    // 点击了第 i 个按钮
                    widget.clicked_button = i;
                    widget.click_time = Date.now();
                    
                    // 执行回调函数
                    if (buttons[i] && buttons[i].callback) {
                        buttons[i].callback();
                    }
                    
                    // 触发重绘以显示点击效果
                    app.graph.setDirtyCanvas(true);
                    break;
                }
            }
        };
    };

    widget.computeSize = function() {
        return [0, button_height];
    };

    widget.serializeValue = async () => {
        return null;
    };

    return widget;
};

// 导出组件
export { MultiButtonWidget };
