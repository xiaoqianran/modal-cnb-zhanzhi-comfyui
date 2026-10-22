import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openMarkerEditorView } from "./visual_marker_editor_view.mjs";
import { directSource, imageSource } from "./visual_marker_source.mjs";

const ID="MiniMaxH3VisualMarkerPrepareEXPT8";
function upstreamSource(node) {
    const source=imageSource(node,app.graph);
    return source?api.apiURL("/view?"+new URLSearchParams(source)):null;
}

export function openMarkerEditor(node) {
    return openMarkerEditorView(node,{upstreamSource:()=>upstreamSource(node),
        locateSource:name=>{
            const source=directSource(node,name,app.graph);
            return source?`${name} 来源：${source.node.title??source.node.type}（#${source.node.id}）。请在该来源节点编辑，编辑器不会断线。`
                :`${name} 当前未找到外部来源，请检查连线。`;
        }});
}

app.registerExtension({
    name:"T8.VisualMarker.Editor",
    async beforeRegisterNodeDef(nodeType,nodeData) {
        if (nodeData.name!==ID) return;
        const created=nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated=function(...args) {
            const result=created?.apply(this,args);
            this.addWidget("button","框选编辑（不运行）",null,()=>openMarkerEditor(this),{serialize:false});
            return result;
        };
        const removed=nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved=function(...args) {this._t8MarkerClose?.(); return removed?.apply(this,args);};
    },
});
