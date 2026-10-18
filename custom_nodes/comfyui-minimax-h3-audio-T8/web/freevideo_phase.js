import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const PHASES = {
    preparation: "准备输入／卸载已指定的 CLIP", startup: "启动自有 worker",
    source_preflight: "核验固定源码和输入", imports_conditioning: "载入运行时／准备条件",
    tables_policy_lora: "核时间表／精度策略／LoRA", engine_load: "加载模型（未完成采样步不算 NFE）",
    sampling: "执行采样（第一步可能包含编译）", latent_validation_transport: "检查／传输原生潜空间",
    release: "释放 worker 权重", receipt_integrity: "写回执／核完整性",
    complete: "worker 已收尾，仍等待父进程核验", legacy_receipt: "读取已有完成 Stage，未新增采样",
    phase_unavailable: "阶段记录不可用，原生 NFE 进度继续有效",
};
let panel, text, shownPrompt, dismissedPrompt, installed = false;
function ensurePanel() {
    if (panel) return;
    panel = document.createElement("aside");
    panel.setAttribute("aria-label", "FreeVideo 实时阶段（只读）");
    panel.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:1000;max-width:440px;padding:12px 16px;border:1px solid #61788c;border-radius:10px;background:#142333;color:#e7f2ff;font:14px/1.6 system-ui;box-shadow:0 4px 20px #0008";
    const close = document.createElement("button");
    close.textContent = "关闭阶段提示";
    close.style.cssText = "float:right;margin-left:12px;font:inherit";
    close.onclick = () => { dismissedPrompt = shownPrompt; panel.hidden = true; };
    text = document.createElement("div");
    text.style.whiteSpace = "pre-wrap";
    text.setAttribute("role", "status");
    panel.append(close, text);
    document.body.append(panel);
}
function install() {
        if (installed) return;
        installed = true;
        api.addEventListener("t8.h11.freevideo_phase", event => {
            const d = event.detail;
            if (!d || d.schema !== "t8.h11.freevideo-live-phase.v1" || !Object.hasOwn(PHASES, d.phase)
                || !Number.isInteger(d.completed_NFE) || !Number.isInteger(d.total_NFE)
                || d.completed_NFE < 0 || d.completed_NFE > d.total_NFE || d.total_NFE > 2048
                || !Number.isFinite(d.observed_host_seconds) || d.observed_host_seconds < 0
                || d.phase_is_NFE !== false || d.automatic_restart !== false
                || typeof d.node_id !== "string" || d.node_id.length > 128
                || typeof d.prompt_id !== "string" || d.prompt_id.length > 128) return;
            if (d.prompt_id === dismissedPrompt) return;
            ensurePanel();
            shownPrompt = d.prompt_id;
            text.textContent = `FreeVideo · 节点 ${d.node_id}\n${PHASES[d.phase]}\n实际完成 NFE：${d.completed_NFE}/${d.total_NFE}\n${d.phase === "legacy_receipt" ? "旧 Stage 的实际回执，不是本次耗时" : `本次观察已过 ${d.observed_host_seconds.toFixed(1)} 秒（host wall）`}\n阶段不是采样百分比；不推算 ETA、不自动重启。`;
            panel.hidden = false;
        });
        api.addEventListener("execution_start", () => { dismissedPrompt = undefined; if (panel) panel.hidden = true; });
        api.addEventListener("execution_error", () => {
            if (panel && !panel.hidden) text.textContent += "\n执行报错，以原始错误为准；这不是成功回执。";
        });
        api.addEventListener("execution_interrupted", () => {
            if (panel && !panel.hidden) text.textContent += "\n已中断；不会自动重启或重复排队。";
        });
}
// Register transport on module load as well as the extension lifecycle. A
// newly discovered extension must not miss a very short metadata-only event
// while the current frontend is still finishing its setup hooks.
install();
app.registerExtension({ name: "minimax-h3-audio-t8.freevideo-phase", setup: install });
