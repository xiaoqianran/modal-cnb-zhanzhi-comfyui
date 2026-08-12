import { app } from "../../scripts/app.js";
import { TerminalManager } from "./Util.js";

const terminal = new TerminalManager("/lg/pip_manager", "LG_PipManager");

app.registerExtension({
    name: "LG.PipManager",
    
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "LG_PipManager") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = async function () {
                const me = onNodeCreated?.apply(this);
                terminal.setupNode(this);
                return me;
            };
            
            const onDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function (ctx, graphcanvas) {
                return terminal.updateNode(this, onDrawForeground, ctx, graphcanvas);
            };
        }
    },
}); 