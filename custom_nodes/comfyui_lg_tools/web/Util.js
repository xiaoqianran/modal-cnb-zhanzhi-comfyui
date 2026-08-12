import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

export class Util {

    // Server
    static AddMessageListener(messagePath, handlerFunc) {
        api.addEventListener(messagePath, handlerFunc);
    }

    // Widget
    static SetTextAreaContent(widget, text) {
        widget.element.textContent = text
    }

    static SetTextAreaScrollPos(widget, pos01) {
        widget.element.scroll(0, widget.element.scrollHeight * pos01)
    }

    static AddReadOnlyTextArea(node, name, text, placeholder = "") {
        const inputEl = document.createElement("textarea");
        inputEl.className = "comfy-multiline-input";
        inputEl.placeholder = placeholder
        inputEl.spellcheck = false
        inputEl.readOnly = true
        inputEl.textContent = text
        return node.addDOMWidget(name, "", inputEl, {
            serialize: false,
        });
    }

    static AddButtonWidget(node, label, callback, value = null) {
        return node.addWidget("button", label, value, callback);
    }

}

// 通用终端管理器
export class TerminalManager {
    constructor(messagePath, nodeType) {
        this.messagePath = messagePath;
        this.nodeType = nodeType;
        this.textVersion = 0;
        this.lines = new Array();
        
        // 监听消息
        Util.AddMessageListener(messagePath, (event) => {
            this.textVersion++;
            if (event.detail.clear) {
                this.lines.length = 0;
            }
            let totalText = String(event.detail.text || "");
            this.lines.push(...(totalText.split("\n")));
            if (this.lines.length > 1024) {
                this.lines = this.lines.slice(-1024);
            }
            // 刷新所有相关节点
            for (let i = 0; i < app.graph._nodes.length; i++) {
                var node = app.graph._nodes[i];
                if (node.type == nodeType && node.setDirtyCanvas) {
                    node.setDirtyCanvas(true);
                }
            }
        });
    }
    
    // 清空终端
    clearTerminal() {
        this.lines.length = 0;
        this.textVersion++;
    }
    
    // 获取终端内容
    getContent() {
        return this.lines.join("\n");
    }
    
    // 创建节点时的设置
    async setupNode(node) {
        var textArea = Util.AddReadOnlyTextArea(node, "terminal", "");
        setTimeout(() => {
            if (textArea.element) {
                textArea.element.style.backgroundColor = "#000000ff";
                textArea.element.style.color = "#ffffffff";
                textArea.element.style.fontFamily = "monospace";
            }
        }, 0);

        // 动态导入避免重复声明问题
        try {
            const { MultiButtonWidget } = await import("./multi_button_widget.js");
            const { queueSelectedOutputNodes } = await import("./queue_shortcut.js");

            // 添加多按钮组件：清理日志 + 执行
            const buttons = [
                {
                    text: "清理日志",
                    callback: () => {
                        this.clearTerminal();
                    }
                },
                {
                    text: "执行",
                    callback: () => {
                        queueSelectedOutputNodes();
                    }
                }
            ];

            const multiButtonWidget = MultiButtonWidget(app, "", {
                labelWidth: 0,
                buttonSpacing: 4
            }, buttons);

            node.addCustomWidget(multiButtonWidget);
        } catch (error) {
            console.error("Failed to load button components:", error);
            // 如果动态导入失败，回退到原来的单按钮
            let clearBtn = Util.AddButtonWidget(node, "清空日志", () => {
                this.clearTerminal();
            });
            clearBtn.width = 128;
        }

        node.terminalVersion = -1;
        return node;
    }

    
    // 绘制时的更新
    updateNode(node, onDrawForeground, ctx, graphcanvas) {
        if (node.terminalVersion != this.textVersion) {
            node.terminalVersion = this.textVersion;
            for (var i = 0; i < node.widgets.length; i++) {
                var wid = node.widgets[i];
                if (wid.name == "terminal") {
                    Util.SetTextAreaContent(wid, this.getContent());
                    Util.SetTextAreaScrollPos(wid, 1.0);
                    break;
                }
            }
        }
        return onDrawForeground?.apply(node, [ctx, graphcanvas]);
    }
} 