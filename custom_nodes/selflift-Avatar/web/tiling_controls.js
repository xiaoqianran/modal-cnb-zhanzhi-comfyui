import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const CONTROL_NAMES = new Set([
    "highres_tiling", "highres_tiling_mode", "tiling_mode", "tiling_tiles", "tiling_axis",
    "highres_token_chunk", "highres_weight_cache_gb",
]);
const SPATIAL_CONTROLS = new Set(["tiling_mode", "tiling_tiles", "tiling_axis"]);
const GLOBAL_CONTROLS = new Set(["highres_token_chunk", "highres_weight_cache_gb"]);
const MODE_LABELS = {
    spatial: "Spatial tiling (legacy)",
    global_stream: "Global stream (recommended)",
    global: "Global (compatible)",
    global_ram: "Global RAM (legacy)",
};
const originalVisibility = new WeakMap();

function read(node, name, fallback) {
    return node.widgets?.find((w) => w.name === name)?.value ?? fallback;
}

function memoryEnabled(node) {
    return Boolean(read(node, "highres_tiling", false));
}

function memoryMode(node) {
    return read(node, "highres_tiling_mode", "spatial");
}

function choices(node) {
    if (!memoryEnabled(node)) return "设置 / Settings: OFF（高分辨率省显存关闭）";
    const m = memoryMode(node);
    if (m === "spatial") {
        const mode = read(node, "tiling_mode", "auto");
        return `设置 / Settings: spatial | ${mode} | axis=${read(node, "tiling_axis", "auto")} | tiles=${mode === "manual" ? read(node, "tiling_tiles", 2) : "auto (1–8)"}`;
    }
    const cacheValue = read(node, "highres_weight_cache_gb", 4);
    const cacheText = typeof cacheValue === "number" ? cacheValue.toFixed(1) : cacheValue;
    const cache = m === "global_stream" ? ` | cache=${cacheText} GiB` : "";
    return `设置 / Settings: ${m} | token_chunk=${read(node, "highres_token_chunk", 4096)}${cache}`;
}

function actualCount(node) {
    if (!memoryEnabled(node)) return "实际分块数量 / Actual tiles: 关闭，不分块 / OFF";
    const plan = node.selfliftTilingPlan;
    if (plan?.kind === "global") {
        return `全局上下文 / Global context: ${plan.mode ?? memoryMode(node)}（无空间块 / no spatial tiles）`;
    }
    const count = plan?.tiles;
    if (!Number.isInteger(count) || count < 1) return "实际分块数量 / Actual tiles: 待估算 / pending (高清准备阶段确定)";
    return `实际分块数量 / Actual tiles: ${count} 块${count === 1 ? "（整图，不拆分 / no split）" : ""}`;
}

function setHidden(widget, hidden) {
    if (!originalVisibility.has(widget)) {
        originalVisibility.set(widget, { type: widget.type, computeSize: widget.computeSize });
    }
    const original = originalVisibility.get(widget);
    if ("hidden" in widget) widget.hidden = hidden;
    else {
        widget.type = hidden ? "selflift-hidden" : original.type;
        widget.computeSize = hidden ? () => [0, -4] : original.computeSize;
    }
}

function refreshVisibility(node) {
    const on = memoryEnabled(node);
    const m = memoryMode(node);
    for (const widget of node.widgets || []) {
        if (!CONTROL_NAMES.has(widget.name) || widget.name === "highres_tiling") continue;
        // Converted widget inputs are owned by ComfyUI; do not alter their visibility.
        if (String(widget.type).startsWith("converted-widget")) continue;
        const linked = node.inputs?.some((slot) => slot.widget?.name === widget.name && slot.link != null);
        if (linked) {
            setHidden(widget, false);
            continue;
        }
        let hidden = false;
        if (!on) hidden = true;
        else if (m === "spatial") hidden = GLOBAL_CONTROLS.has(widget.name);
        else {
            hidden = SPATIAL_CONTROLS.has(widget.name)
                || (widget.name === "highres_weight_cache_gb" && m !== "global_stream");
        }
        setHidden(widget, hidden);
    }
    node.setDirtyCanvas?.(true, true);
}

function display(node, text, plan) {
    const box = node.selfliftTilingPanel;
    if (!box) return;
    if (text !== undefined) {
        node.selfliftTilingLast = String(text);
        // Explicit null resets a previous run; undefined supports older cached UI text.
        node.selfliftTilingPlan = plan ?? null;
        if (plan === undefined) {
            const match = String(text).match(/Effective \/ 实际:\s*(\d+)/);
            if (match) node.selfliftTilingPlan = { tiles: Number(match[1]) };
        }
    }
    refreshVisibility(node);
    box.value = actualCount(node) + "\n" + choices(node) + "\n" + (node.selfliftTilingLast || "未运行 / Not run. Actual plan appears at high-resolution preparation.\nSpatial controls apply only to the spatial mode; token chunk/cache apply only to global modes.");
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "selflift-Avatar.TilingPlan",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SelfLiftAvatarH3Sampler") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            const box = document.createElement("textarea");
            box.readOnly = true;
            box.setAttribute("aria-label", "selflift-Avatar high-resolution memory plan / 高分辨率省显存方案");
            box.style.cssText = "width:100%;height:100%;box-sizing:border-box;resize:none;overflow:auto;font:12px/1.45 monospace;color:var(--input-text,#ddd);background:var(--comfy-input-bg,#222);border:1px solid var(--border-color,#555);padding:6px;";
            this.selfliftTilingPanel = box;
            this.addDOMWidget("selflift_tiling_plan", "selflift-tiling-status", box, { serialize: false });
            for (const widget of this.widgets || []) {
                if (widget.name === "highres_tiling_mode" && widget.options) {
                    widget.options.getOptionLabel = (value) => MODE_LABELS[value] ?? value;
                }
                if (!CONTROL_NAMES.has(widget.name)) continue;
                const callback = widget.callback;
                const node = this;
                widget.callback = function () {
                    const value = callback?.apply(this, arguments);
                    display(node, "设置已修改 / Settings changed. Run again to compute a new plan.");
                    return value;
                };
            }
            this.size[0] = Math.max(this.size[0], 370);
            this.size[1] = Math.max(this.size[1], this.computeSize()[1] + 170);
            display(this);
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = configured?.apply(this, arguments);
            display(this);
            return result;
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const result = executed?.apply(this, arguments);
            if (message?.selflift_tiling) display(this, message.selflift_tiling.join("\n"), message.selflift_tiling_plan?.[0]);
            return result;
        };
    },
    setup() {
        api.addEventListener("selflift-avatar-tiling", (event) => {
            const id = String(event.detail?.node_id ?? "");
            // Root-graph events use ordinary IDs. Subgraph UI still receives onExecuted.
            const node = app.graph?.getNodeById(id) ?? (/^\d+$/.test(id) ? app.graph?.getNodeById(Number(id)) : null);
            if (node?.selfliftTilingPanel) display(node, event.detail.text, event.detail.plan);
        });
    },
});
