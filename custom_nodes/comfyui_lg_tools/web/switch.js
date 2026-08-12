import { app } from "../../../scripts/app.js";

class BaseNode extends LGraphNode {
    static defaultComfyClass = "BaseNode"; 
     constructor(title, comfyClass) {
        super(title);
        this.isVirtualNode = false;
        this.configuring = false;
        this.__constructed__ = false;
        this.widgets = this.widgets || [];
        this.properties = this.properties || {};

        this.comfyClass = comfyClass || this.constructor.comfyClass || BaseNode.defaultComfyClass;
         setTimeout(() => {
            this.checkAndRunOnConstructed();
        });
    }

    checkAndRunOnConstructed() {
        if (!this.__constructed__) {
            this.onConstructed();
        }
        return this.__constructed__;
    }

    onConstructed() {
        if (this.__constructed__) return false;
        this.type = this.type ?? undefined;
        this.__constructed__ = true;
        return this.__constructed__;
    }

    configure(info) {
        this.configuring = true;
        super.configure(info);
        for (const w of this.widgets || []) {
            w.last_y = w.last_y || 0;
        }
        this.configuring = false;
    }
    static setUp() {
        if (!this.type) {
            throw new Error(`Missing type for ${this.name}: ${this.title}`);
        }
        LiteGraph.registerNodeType(this.type, this);
        if (this._category) {
            this.category = this._category;
        }
    }
}

const MODE_BYPASS = 4;
const MODE_MUTE = 2;
const MODE_ALWAYS = 0;

app.registerExtension({
    name: "Switcher.Mode",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "MuterSwitcher") {
            const INPUTS = ["ON_TRUE", "on_true", "ON_FALSE", "on_false"];
            
            // 定义节点的默认属性
            nodeType.default_properties = {
                ON_TRUE_Mode: "mute",
                on_true_Mode: "mute",
                ON_FALSE_Mode: "mute",
                on_false_Mode: "mute"
            };

            // 定义属性的类型和选项
            if (!nodeType["@ON_TRUE_Mode"]) {
                nodeType["@ON_TRUE_Mode"] = { type: "combo", values: ["mute", "bypass"] };
                nodeType["@on_true_Mode"] = { type: "combo", values: ["mute", "bypass"] };
                nodeType["@ON_FALSE_Mode"] = { type: "combo", values: ["mute", "bypass"] };
                nodeType["@on_false_Mode"] = { type: "combo", values: ["mute", "bypass"] };
            }

            // 添加模式选择属性
            nodeType.prototype.getExtraMenuOptions = function(_, options) {
                // 添加菜单选项
                INPUTS.forEach((input, index) => {
                    const submenu = {
                        content: `${input}_Mode`,
                        submenu: {
                            options: [
                                {
                                    content: "Mute",
                                    callback: () => {
                                        this.properties[`${input}_Mode`] = "mute";
                                        this.setDirtyCanvas(true);
                                    }
                                },
                                {
                                    content: "Bypass",
                                    callback: () => {
                                        this.properties[`${input}_Mode`] = "bypass";
                                        this.setDirtyCanvas(true);
                                    }
                                }
                            ]
                        }
                    };
                    options.push(submenu);
                });
            };

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated?.apply(this, arguments);

                // 初始化属性
                this.properties = this.properties || {};
                INPUTS.forEach(input => {
                    this.properties[`${input}_Mode`] = this.properties[`${input}_Mode`] || "mute";
                });

                const booleanWidget = this.widgets?.find(w => w.name === "boolean");
                if (booleanWidget) {
                    const originalCallback = booleanWidget.callback;
                    booleanWidget.callback = (value) => {
                        // 获取所有连接的节点
                        const nodes = INPUTS.map((_, i) => this.getConnectedNode(i));

                        // 设置各个节点的模式
                        nodes.forEach((node, index) => {
                            if (node) {
                                const isTrue = index < 2;
                                const mode = this.properties[`${INPUTS[index]}_Mode`];
                                if (isTrue) {
                                    node.mode = value ? MODE_ALWAYS : (mode === "mute" ? MODE_MUTE : MODE_BYPASS);
                                } else {
                                    node.mode = value ? (mode === "mute" ? MODE_MUTE : MODE_BYPASS) : MODE_ALWAYS;
                                }
                                node.setDirtyCanvas(true, true);
                            }
                        });

                        originalCallback?.(value);
                    };
                }
                
                return result;
            };

            nodeType.prototype.getConnectedNode = function(slot) {
                if (this.inputs && this.inputs[slot] && this.inputs[slot].link) {
                    const link = app.graph.links[this.inputs[slot].link];
                    if (link) {
                        return app.graph.getNodeById(link.origin_id);
                    }
                }
                return null;
            };
        }
    }
});


app.registerExtension({
    name: "GroupSwitcher",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "GroupSwitcher") {
            const GROUPS = ["GROUP_A", "GROUP_B"];
            
            // 定义节点的默认属性
            nodeType.default_properties = {
                GROUP_A_Mode: "mute",
                GROUP_B_Mode: "mute",
                groupA: "",
                groupB: ""
            };

            // 定义属性的类型和选项
            if (!nodeType["@GROUP_A_Mode"]) {
                GROUPS.forEach(group => {
                    nodeType[`@${group}_Mode`] = { 
                        type: "combo", 
                        values: ["mute", "bypass"] 
                    };
                });
            }
            function recomputeInsideNodesForGroup(group) {
                const nodes = group.graph._nodes;
                group._nodes.length = 0;
                
                // 获取所有节点的边界
                const nodeBoundings = {};
                for (const node of app.graph._nodes) {
                    nodeBoundings[node.id] = node.getBounding();
                }

                // 计算组内节点
                for (const node of nodes) {
                    const node_bounding = nodeBoundings[node.id];
                    if (!node_bounding || !LiteGraph.overlapBounding(group._bounding, node_bounding)) {
                        continue;
                    }
                    group._nodes.push(node);
                }
            }

            // 获取所有组并更新组内节点
            function getGroups() {
                const groups = [...app.graph._groups];
                for (const group of groups) {
                    recomputeInsideNodesForGroup(group);
                }
                return groups;
            }
            // 获取所有组名称
            function getGroupNames() {
                return getGroups().map(g => g.title).sort();
            }

            // 添加模式选择属性
            nodeType.prototype.getExtraMenuOptions = function(_, options) {
                GROUPS.forEach(group => {
                    const submenu = {
                        content: `${group}_Mode`,
                        submenu: {
                            options: [
                                {
                                    content: "Mute",
                                    callback: () => {
                                        this.properties[`${group}_Mode`] = "mute";
                                        this.setDirtyCanvas(true);
                                    }
                                },
                                {
                                    content: "Bypass",
                                    callback: () => {
                                        this.properties[`${group}_Mode`] = "bypass";
                                        this.setDirtyCanvas(true);
                                    }
                                }
                            ]
                        }
                    };
                    options.push(submenu);
                });
            };

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated?.apply(this, arguments);

                // 初始化属性
                this.properties = this.properties || {};
                GROUPS.forEach(group => {
                    this.properties[`${group}_Mode`] = this.properties[`${group}_Mode`] || "mute";
                });

                // 添加组选择下拉框
                const widgetA = this.addWidget("combo", "Group A", this.properties.groupA || "", (v) => {
                    this.properties.groupA = v;
                }, { values: getGroupNames() });

                const widgetB = this.addWidget("combo", "Group B", this.properties.groupB || "", (v) => {
                    this.properties.groupB = v;
                }, { values: getGroupNames() });

                // 获取 boolean widget 并添加回调
                const booleanWidget = this.widgets?.find(w => w.name === "boolean");
                if (booleanWidget) {
                    const originalCallback = booleanWidget.callback;
                    booleanWidget.callback = (value) => {
                        this.switchGroups(value);
                        originalCallback?.(value);
                    };
                }

                this.updateGroupList = () => {
                    const groups = getGroupNames();
                    if (widgetA && widgetB) {
                        widgetA.options.values = groups;
                        widgetB.options.values = groups;
                        this.setDirtyCanvas(true, false);
                    }
                };

                // 监听画布变化
                const self = this;
                app.canvas.onDrawBackground = (() => {
                    const original = app.canvas.onDrawBackground;
                    return function() {
                        self.updateGroupList();
                        return original?.apply(this, arguments);
                    };
                })();
                
                return result;
            };
            nodeType.prototype.computeSize = function() {
                const widgetHeight = 24;
                const padding = 4;
                const width = 180;
                const height = (this.widgets?.length || 0) * widgetHeight + padding * 2;
                return [width, height];
            };
            // 修改组切换功能，使用新的组节点计算逻辑
            nodeType.prototype.switchGroups = function(value) {
                const groups = getGroups();
                const groupA = groups.find(g => g.title === this.properties.groupA);
                const groupB = groups.find(g => g.title === this.properties.groupB);

                if (groupA) {
                    const modeA = this.properties.GROUP_A_Mode;
                    groupA._nodes.forEach(node => {
                        node.mode = value ? MODE_ALWAYS : (modeA === "mute" ? MODE_MUTE : MODE_BYPASS);
                        node.setDirtyCanvas(true, true);
                    });
                }

                if (groupB) {
                    const modeB = this.properties.GROUP_B_Mode;
                    groupB._nodes.forEach(node => {
                        node.mode = !value ? MODE_ALWAYS : (modeB === "mute" ? MODE_MUTE : MODE_BYPASS);
                        node.setDirtyCanvas(true, true);
                    });
                }

                app.graph.setDirtyCanvas(true, false);
            };
        }
    }
});


class GroupDetectorNode extends BaseNode {
    static type = "🎈GroupDetector";
    static title = "🎈Group Detector";
    static category = "🎈LAOGOU/Switch";
    static _category = "🎈LAOGOU/Switch";
    static comfyClass = "🎈GroupDetector";

    constructor(title = GroupDetectorNode.title) {
        super(title, GroupDetectorNode.comfyClass);
        
        this.isVirtualNode = true;
        this.size = [50, 26];
        this.shape = LiteGraph.ROUND_SHAPE;
        
        this.addOutput("output", "*");
        this.mode = MODE_ALWAYS;
        this._lastMode = this.mode; // 记录上一次的状态

        // 监听画布变化，只在状态改变时同步
        const self = this;
        app.canvas.onDrawBackground = (() => {
            const original = app.canvas.onDrawBackground;
            return function() {
                // 只在状态发生变化时同步
                if (self.mode !== self._lastMode) {
                    const group = self.getCurrentGroup();
                    if (group) {
                        group._nodes.forEach(n => {
                            if (n !== self) {
                                n.mode = self.mode;
                                n.setDirtyCanvas(true, true);
                            }
                        });
                    }
                    self._lastMode = self.mode;
                }
                return original?.apply(this, arguments);
            };
        })();

        this.onConstructed();
    }

    // 重写 onModeChanged 方法来响应状态变化
    onModeChanged(mode) {
        super.onModeChanged?.(mode);
        const group = this.getCurrentGroup();
        if (group) {
            group._nodes.forEach(n => {
                if (n !== this) {
                    n.mode = mode;
                    n.setDirtyCanvas(true, true);
                }
            });
        }
        this._lastMode = mode;
    }

    getCurrentGroup() {
        const groups = [...app.graph._groups];
        for (const group of groups) {
            const nodes = group.graph._nodes;
            group._nodes.length = 0;
            for (const n of nodes) {
                if (LiteGraph.overlapBounding(group._bounding, n.getBounding())) {
                    group._nodes.push(n);
                }
            }
            if (group._nodes.includes(this)) {
                return group;
            }
        }
        return null;
    }
}

app.registerExtension({
    name: "GroupDetector",
    registerCustomNodes() {
        GroupDetectorNode.setUp();
    }
});



class StateTransferNode extends BaseNode {
    static type = "🎈StateTransfer";
    static title = "🎈State Transfer";
    static category = "🎈LAOGOU/Switch";
    static _category = "🎈LAOGOU/Switch";
    static comfyClass = "🎈StateTransfer";

    constructor(title = StateTransferNode.title) {
        super(title, StateTransferNode.comfyClass);
        
        this.isVirtualNode = true;
        this.size = [100, 26];
        this.shape = LiteGraph.ROUND_SHAPE;
        
        // 添加初始输入和输出
        this.addInput("input_1", "*");
        this.addOutput("output", "*");
        
        // 默认状态为开启
        this.mode = MODE_ALWAYS;

        // 监听画布变化，同步状态
        const self = this;
        app.canvas.onDrawBackground = (() => {
            const original = app.canvas.onDrawBackground;
            return function() {
                self.updateConnectedNodesState();
                return original?.apply(this, arguments);
            };
        })();

        this.onConstructed();
    }

    // 更新连接节点的状态
    updateConnectedNodesState() {
        this.inputs.forEach(input => {
            if (input.link) {
                const link = app.graph.links[input.link];
                if (link) {
                    const sourceNode = app.graph.getNodeById(link.origin_id);
                    if (sourceNode) {
                        // 直接设置节点的 mode 属性
                        sourceNode.mode = this.mode;
                        sourceNode.setDirtyCanvas(true, true);
                    }
                }
            }
        });
    }

    // 处理连接变化
    onConnectionsChange(type, index, connected, link_info) {
        if (!link_info || type !== LiteGraph.INPUT) return;

        const stackTrace = new Error().stack;

        // 处理断开连接
        if (!connected) {
            if (!stackTrace.includes('LGraphNode.prototype.connect') && 
                !stackTrace.includes('LGraphNode.connect') && 
                !stackTrace.includes('loadGraphData')) {
                this.removeInput(index);
            }
        }

        // 重新编号输入端口
        let inputIndex = 1;
        this.inputs.forEach(input => {
            const newName = `input_${inputIndex}`;
            if (input.name !== newName) {
                input.name = newName;
            }
            inputIndex++;
        });

        // 如果最后一个端口被连接，添加新端口
        const lastInput = this.inputs[this.inputs.length - 1];
        if (lastInput?.link != null) {
            this.addInput(`input_${inputIndex}`, "*");
        }

        this.setDirtyCanvas(true, true);
    }

    // 添加初始化方法
    onNodeCreated() {
        const result = super.onNodeCreated?.apply(this, arguments);
        
        // 确保至少有一个输入端口
        if (!this.inputs.find(input => input.name === "input_1")) {
            this.addInput("input_1", "*");
        }
        
        return result;
    }
}

app.registerExtension({
    name: "StateTransfer",
    registerCustomNodes() {
        StateTransferNode.setUp();
    }
});