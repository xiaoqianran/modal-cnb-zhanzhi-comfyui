const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const NODE_CLASS = "SFH3MultimodalDirector";
const STYLE_ID = "sf-h3-director-style";

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name);
}

function widgetValue(node, name, fallback) {
  const widget = getWidget(node, name);
  return widget?.value ?? fallback;
}

function hideWidget(widget) {
  if (!widget) return;
  widget.computeSize = () => [0, -4];
  widget.hidden = true;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, Number(value) || 0));
}

function gridDimensions(node) {
  const match = String(widgetValue(node, "grid_layout", "3x2 六宫格")).match(/(\d+)\s*x\s*(\d+)/i);
  return match ? [Number(match[1]), Number(match[2])] : [3, 2];
}

// --- 接口溯源：读取连接到 storyboard_images / storyboard_text 的上游节点 ---
function getGraphLink(linkId) {
  if (linkId == null) return null;
  const links = app.graph?.links;
  if (!links) return null;
  if (links[linkId]) return links[linkId];
  if (Array.isArray(links)) return links.find((link) => link?.id === linkId || link?.[0] === linkId) || null;
  return null;
}

function getOriginNode(node, inputName) {
  const input = node.inputs?.find((item) => item.name === inputName);
  const link = getGraphLink(input?.link);
  if (!link) return null;
  const originId = link.origin_id ?? link.originId ?? link[1];
  return app.graph?.getNodeById?.(originId) || null;
}

function normalizeImageWidgetValue(value) {
  if (!value) return { filename: "", subfolder: "", type: "input" };
  if (typeof value === "object") {
    return {
      filename: value.filename || value.name || value.image || value.path || "",
      subfolder: value.subfolder || "",
      type: value.type || "input",
    };
  }
  return { filename: String(value), subfolder: "", type: "input" };
}

function loadImageNodeUrl(node) {
  const widget = getWidget(node, "image") || getWidget(node, "图像");
  const info = normalizeImageWidgetValue(widget?.value);
  if (!info.filename) return "";
  const parts = String(info.filename).split(/[\\/]/);
  const base = parts.pop();
  const subfolder = info.subfolder || parts.join("/");
  const rawType = String(info.type || widgetValue(node, "type", "input") || "input").toLowerCase();
  const viewType = ["input", "output", "temp"].includes(rawType) ? rawType : "input";
  return api.apiURL(`/view?filename=${encodeURIComponent(base)}&type=${encodeURIComponent(viewType)}&subfolder=${encodeURIComponent(subfolder)}`);
}

// --- SF 分镜文本识别（与后端 _recognize_storyboard 同规则）---
// 方位词 -> grid_index（按布局，行优先：从左到右、从上到下），与宫格切图顺序严格对应
const H3_GRID_POSITION_MAPS = {
  "2,2": { "左上": 0, "上左": 0, "右上": 1, "上右": 1, "左下": 2, "下左": 2, "右下": 3, "下右": 3 },
  "3,2": {
    "左上": 0, "上左": 0, "中上": 1, "上中": 1, "右上": 2, "上右": 2,
    "左下": 3, "下左": 3, "中下": 4, "下中": 4, "右下": 5, "下右": 5,
  },
  "3,3": {
    "左上": 0, "上左": 0, "中上": 1, "上中": 1, "右上": 2, "上右": 2,
    "左中": 3, "中左": 3, "中中": 4, "中心": 4, "正中": 4, "中间": 4, "中央": 4, "居中": 4,
    "右中": 5, "中右": 5, "左下": 6, "下左": 6, "中下": 7, "下中": 7, "右下": 8, "下右": 8,
  },
};
const H3_POSITION_WORDS = (() => {
  const s = new Set();
  for (const k in H3_GRID_POSITION_MAPS) for (const w in H3_GRID_POSITION_MAPS[k]) s.add(w);
  return Array.from(s).sort((a, b) => b.length - a.length);
})();

function h3PositionToIndex(word, cols, rows) {
  if (!word) return null;
  const mp = H3_GRID_POSITION_MAPS[`${cols},${rows}`] || H3_GRID_POSITION_MAPS["2,2"];
  const idx = mp[word];
  return idx == null || idx < 0 || idx >= cols * rows ? null : idx;
}

function h3StripGlobalLabel(text) {
  return String(text || "")
    .replace(/^\s*(?:正面词|正面|全局提示词|全局词|全局|总提示词|总词|总览词|概述|总览|视频提示词|视频词)\s*[:：]\s*/, "")
    .trim();
}

function h3ParseSegmentBody(body, cols, rows) {
  const b = body || "";
  let position = null;
  for (const word of H3_POSITION_WORDS) {
    if (b.indexOf(word) !== -1) {
      const idx = h3PositionToIndex(word, cols, rows);
      if (idx != null) { position = idx; break; }
    }
  }
  let durationSeconds = null;
  // 不能用 \b：JS 的 \b 是 ASCII-only，中文"秒"不算单词字符；用否定前瞻
  const dm = b.match(/(\d+(?:\.\d+)?)\s*(?:秒钟|秒|s)(?![0-9a-zA-Z])/i);
  if (dm) durationSeconds = parseFloat(dm[1]);
  let prompt = b;
  for (const word of H3_POSITION_WORDS) prompt = prompt.split(word).join("");
  prompt = prompt.replace(/\d+(?:\.\d+)?\s*(?:秒钟|秒|s)(?![0-9a-zA-Z])/gi, "");
  prompt = prompt.replace(/[，,。、；;：:\s]+/g, "，");
  prompt = prompt.replace(/^，+|，+$/g, "");
  prompt = prompt.replace(/\s+/g, " ").trim();
  return { prompt, position, durationSeconds };
}

function h3RecognizeStoryboard(text, cols, rows) {
  const clean = String(text || "").trim().replace(/^```(?:json)?\s*|\s*```$/gi, "");
  if (!clean) return { globalPrompt: "", cells: [], durations: [], recognized: false };
  const anchorRe = /第\s*([0-9]+|[一二三四五六七八九十]+)\s*个?\s*(?:镜头|镜|画面|分镜|shot)/gi;
  const anchors = [...clean.matchAll(anchorRe)];
  if (!anchors.length) return { globalPrompt: "", cells: [], durations: [], recognized: false };
  const globalPrompt = h3StripGlobalLabel(clean.slice(0, anchors[0].index));
  const count = cols * rows;
  const placed = {};
  const queue = [];
  for (let i = 0; i < anchors.length; i++) {
    const start = anchors[i].index + anchors[i][0].length;
    const end = i + 1 < anchors.length ? anchors[i + 1].index : clean.length;
    const seg = h3ParseSegmentBody(clean.slice(start, end), cols, rows);
    if (seg.position != null && placed[seg.position] === undefined) placed[seg.position] = seg;
    else queue.push(seg);
  }
  const cells = new Array(count).fill("");
  const durations = new Array(count).fill(null);
  for (let idx = 0; idx < count; idx++) {
    if (placed[idx]) { cells[idx] = placed[idx].prompt; durations[idx] = placed[idx].durationSeconds; }
  }
  let qi = 0;
  for (let idx = 0; idx < count; idx++) {
    if (!cells[idx] && qi < queue.length) { cells[idx] = queue[qi].prompt; durations[idx] = queue[qi].durationSeconds; qi += 1; }
  }
  return { globalPrompt, cells, durations, recognized: true };
}

// djb2 哈希：用于检测接口分镜文本是否变化（只在变化时才重排，保留手动编辑）
function h3TextSig(text) {
  let h = 5381;
  const s = String(text || "");
  for (let i = 0; i < s.length; i++) h = ((h * 33) + s.charCodeAt(i)) >>> 0;
  return h.toString(16);
}

function makeId(prefix = "ref") {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function mediaUrl(relativeName) {
  if (!relativeName) return "";
  const parts = String(relativeName).replace(/\\/g, "/").split("/");
  const filename = parts.pop();
  return api.apiURL(
    `/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(parts.join("/"))}&type=input`
  );
}

function previewUrl(info) {
  if (!info) return "";
  const filename = info.filename || info.name || "";
  if (!filename) return "";
  return api.apiURL(
    `/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(info.subfolder || "")}&type=${encodeURIComponent(info.type || "temp")}`
  );
}

function injectStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .sf-h3-director { color: #e8e8e8; background: #151515; border: 1px solid #3a3a3a; font: 13px/1.45 system-ui, sans-serif; overflow: hidden; }
    .sf-h3-director * { box-sizing: border-box; }
    .sf-h3-head { display:flex; align-items:center; gap:8px; padding:9px 10px; background:#202020; border-bottom:1px solid #3a3a3a; }
    .sf-h3-title { font-weight:700; color:#fff; margin-right:auto; }
    .sf-h3-summary { color:#a9d5b8; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:62%; }
    .sf-h3-mode-switch { display:grid; grid-template-columns:1fr 1fr; gap:4px; padding:8px 10px; background:#191919; border-bottom:1px solid #333; }
    .sf-h3-mode-btn { border:1px solid #4a4a4a; background:#252525; color:#bbb; min-height:34px; border-radius:4px; cursor:pointer; font-weight:600; }
    .sf-h3-mode-btn:hover { background:#303030; color:#eee; }
    .sf-h3-mode-btn.active { background:#315f43; border-color:#70a982; color:#fff; }
    .sf-h3-toolbar { display:flex; flex-wrap:wrap; gap:6px; padding:8px 10px; border-bottom:1px solid #333; }
    .sf-h3-btn { border:1px solid #505050; background:#292929; color:#eee; min-height:30px; padding:4px 9px; border-radius:4px; cursor:pointer; }
    .sf-h3-btn:hover { background:#353535; border-color:#6a6a6a; }
    .sf-h3-btn.danger { color:#ffb7b7; }
    .sf-h3-section { padding:9px 10px; border-bottom:1px solid #303030; }
    .sf-h3-label { display:block; color:#c9c9c9; font-size:12px; margin-bottom:5px; }
    .sf-h3-textarea, .sf-h3-input { width:100%; border:1px solid #444; border-radius:4px; background:#111; color:#eee; padding:7px 8px; outline:none; }
    .sf-h3-textarea:focus, .sf-h3-input:focus { border-color:#6a9f7b; }
    .sf-h3-global { min-height:66px; resize:vertical; }
    .sf-h3-director.reference-layout .sf-h3-global { min-height:220px; }
    .sf-h3-ruler { display:flex; justify-content:space-between; color:#888; font-size:11px; padding:0 2px 4px; }
    .sf-h3-track { position:relative; height:132px; background:#0b0b0b; border:1px solid #3d3d3d; overflow:hidden; }
    .sf-h3-track::before { content:""; position:absolute; inset:0; background:repeating-linear-gradient(90deg, transparent 0, transparent calc(10% - 1px), #242424 10%); pointer-events:none; }
    .sf-h3-track.reference-mode { display:flex; gap:8px; align-items:stretch; height:142px; padding:8px; overflow-x:auto; }
    .sf-h3-track.reference-mode::before { display:none; }
    .sf-h3-card { position:absolute; top:8px; height:112px; min-width:58px; border:1px solid #555; background:#202020; overflow:hidden; cursor:pointer; border-radius:4px; }
    .sf-h3-track.reference-mode .sf-h3-card { position:relative; inset:auto; flex:0 0 150px; width:150px; height:124px; }
    .sf-h3-card.selected { border:2px solid #77b58a; box-shadow:0 0 0 1px #101010; }
    .sf-h3-card img, .sf-h3-card video { width:100%; height:72px; display:block; object-fit:cover; background:#090909; }
    .sf-h3-grid-thumb { width:100%; height:72px; background-repeat:no-repeat; background-color:#090909; }
    .sf-h3-grid-thumb-wrap { width:100%; height:72px; display:flex; align-items:center; justify-content:center; background:#090909; overflow:hidden; }
    .sf-h3-placeholder { height:72px; display:flex; align-items:center; justify-content:center; color:#bbb; background:#1a2520; font-size:12px; }
    .sf-h3-card-meta { padding:4px 6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:#ddd; font-size:11px; }
    .sf-h3-audio-row { display:flex; gap:6px; min-height:42px; padding-top:7px; overflow-x:auto; }
    .sf-h3-audio-chip { flex:0 0 auto; max-width:210px; border:1px solid #5a5363; background:#27212d; color:#ddd; padding:7px 9px; border-radius:4px; cursor:pointer; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .sf-h3-audio-chip.selected { border-color:#b28ac7; }
    .sf-h3-editor { display:grid; grid-template-columns:120px 120px 1fr; gap:8px; align-items:end; }
    .sf-h3-editor .wide { grid-column:1 / -1; }
    .sf-h3-editor textarea { min-height:58px; resize:vertical; }
    .sf-h3-empty { color:#888; padding:14px 4px; text-align:center; }
    .sf-h3-check { display:flex; align-items:center; gap:7px; min-height:32px; color:#ddd; }
    .sf-h3-output { max-height:86px; overflow:auto; white-space:pre-wrap; color:#bfc8bf; background:#101210; border:1px solid #333; padding:7px 8px; border-radius:4px; }
  `;
  document.head.appendChild(style);
}

function emptyState() {
  return {
    version: 1,
    updatedAt: 0,
    globalPrompt: "",
    allReferencePrompt: "",
    gridImage: null,
    items: [],
    selectedId: null,
    _textSig: "",
  };
}

function normalizeState(value) {
  try {
    const parsed = typeof value === "string" ? JSON.parse(value || "{}") : value;
    if (!parsed || typeof parsed !== "object") return emptyState();
    return {
      version: 1,
      updatedAt: Number.isFinite(Number(parsed.updatedAt)) ? Number(parsed.updatedAt) : 0,
      globalPrompt: String(parsed.globalPrompt || ""),
      allReferencePrompt: String(parsed.allReferencePrompt || ""),
      gridImage: parsed.gridImage && typeof parsed.gridImage === "object" ? parsed.gridImage : null,
      items: Array.isArray(parsed.items) ? parsed.items.filter(Boolean) : [],
      selectedId: parsed.selectedId || null,
      _textSig: String(parsed._textSig || ""),
    };
  } catch (_) {
    return emptyState();
  }
}

function hasStateContent(state) {
  return !!(
    state.globalPrompt ||
    state.allReferencePrompt ||
    state.gridImage ||
    state.items.length ||
    state.selectedId
  );
}

function workflowSessionKey(node) {
  const activeTab = document.querySelector('button[data-pc-name="pctogglebutton"][aria-pressed="true"]');
  const workflowId = String(activeTab?.textContent || "workflow")
    .replace(/[•×]/g, "")
    .trim();
  const position = Array.isArray(node.pos) ? node.pos.map((value) => Math.round(Number(value) || 0)).join(",") : "0,0";
  const nodeId = Number(node.id) >= 0 ? node.id : `${node.type || NODE_CLASS}@${position}`;
  return `sf_h3_director:${workflowId}:${nodeId}`;
}

function readSessionState(storageKey) {
  try {
    return window.sessionStorage?.getItem(storageKey) || "";
  } catch (_) {
    return "";
  }
}

function loadPersistedState(node, dataWidget, serializedWidget = null, storageKey = "") {
  const candidates = [
    normalizeState(node.properties?.csH3Timeline),
    normalizeState(dataWidget?.value),
    normalizeState(serializedWidget?.value),
    normalizeState(readSessionState(storageKey)),
  ];
  const newest = Math.max(...candidates.map((state) => state.updatedAt));
  const current = candidates.filter((state) => state.updatedAt === newest);
  return current.find(hasStateContent) || current[0] || emptyState();
}

class H3DirectorUI {
  constructor(node, root) {
    this.node = node;
    this.root = root;
    this.dataWidget = getWidget(node, "timeline_data");
    this.promptWidget = getWidget(node, "global_prompt");
    this.serializedWidget = getWidget(node, "sf_h3_director_ui");
    this.storageKey = workflowSessionKey(node);
    const modeWidget = getWidget(node, "mode");
    if (modeWidget && !["宫格模式", "全能参考"].includes(modeWidget.value)) modeWidget.value = "宫格模式";
    this.state = loadPersistedState(node, this.dataWidget, this.serializedWidget, this.storageKey);
    if (!this.state.globalPrompt && this.promptWidget?.value) this.state.globalPrompt = String(this.promptWidget.value);
    if (!this.state.allReferencePrompt && this.mode === "全能参考") {
      this.state.allReferencePrompt = this.state.globalPrompt;
    }
    this.compiledPrompt = "运行后将在这里显示最终编译提示词。";
    this.summary = "等待添加参考素材";
    this.storyboardPreviews = [];
    this.gridSocketUrl = "";
    this.gridImageDims = null;
    this.build();
    this.hookWidgets();
    this.syncFromSockets();
    this.render();
  }

  get totalSeconds() {
    return clamp(widgetValue(this.node, "duration_seconds", 5), 4, 15);
  }

  get selected() {
    return this.activeItems.find((item) => item.id === this.state.selectedId) || null;
  }

  get mode() {
    const value = widgetValue(this.node, "mode", "宫格模式");
    return value === "全能参考" ? "全能参考" : "宫格模式";
  }

  get activeItems() {
    const gridMode = this.mode === "宫格模式";
    return this.state.items.filter((item) => (item.source === "storyboard") === gridMode);
  }

  build() {
    this.root.className = "sf-h3-director";
    this.root.innerHTML = "";

    const head = document.createElement("div");
    head.className = "sf-h3-head";
    this.titleEl = document.createElement("span");
    this.titleEl.className = "sf-h3-title";
    this.summaryEl = document.createElement("span");
    this.summaryEl.className = "sf-h3-summary";
    head.append(this.titleEl, this.summaryEl);
    this.root.appendChild(head);

    const modeSwitch = document.createElement("div");
    modeSwitch.className = "sf-h3-mode-switch";
    this.modeButtons = new Map();
    for (const mode of ["宫格模式", "全能参考"]) {
      const button = document.createElement("button");
      button.className = "sf-h3-mode-btn";
      button.textContent = mode;
      button.title = mode === "宫格模式"
        ? "拆分四宫格、六宫格或九宫格，并按分镜文字生成时间线"
        : "使用普通图片、视频与音频作为 H3 多模态参考";
      button.addEventListener("click", () => this.setMode(mode));
      this.modeButtons.set(mode, button);
      modeSwitch.appendChild(button);
    }
    this.root.appendChild(modeSwitch);

    const toolbar = document.createElement("div");
    toolbar.className = "sf-h3-toolbar";
    this.referenceControls = [
      this.addToolbarButton(toolbar, "＋ 图片", "添加一张或多张参考图片", "image"),
      this.addToolbarButton(toolbar, "＋ 视频", "添加最多三段参考视频", "video"),
      this.addToolbarButton(toolbar, "＋ 音频", "添加参考声音或音色", "audio"),
    ];
    this.gridControls = [
      this.addGridUploadButton(toolbar),
      this.addActionButton(toolbar, "生成宫格槽位", "根据宫格格式建立4、6或9个分镜", () => this.createStoryboardSlots()),
      this.addActionButton(toolbar, "同步接口分镜", "读取接口连接的宫格图像与分镜文本：按方位落格提示词、按X秒分配时长", () => this.syncFromSockets(true)),
    ];
    this.autoArrangeButton = this.addActionButton(toolbar, "自动排列", "将画面素材平均排列到总时长", () => this.autoArrange());
    this.addActionButton(toolbar, "删除", "删除当前选中的参考素材", () => this.removeSelected(), "danger");
    this.root.appendChild(toolbar);

    this.globalSection = document.createElement("div");
    this.globalSection.className = "sf-h3-section";
    this.globalLabel = document.createElement("label");
    this.globalLabel.className = "sf-h3-label";
    this.globalInput = document.createElement("textarea");
    this.globalInput.className = "sf-h3-textarea sf-h3-global";
    this.globalInput.placeholder = "整体风格、人物一致性、画面质感、声音氛围和必须遵守的要求……";
    this.globalInput.addEventListener("input", () => {
      this.persistPromptInput();
      this.save();
    });
    this.globalInput.addEventListener("blur", () => {
      this.save();
      clearTimeout(this.workflowCaptureTimer);
      this.notifyWorkflowChanged();
    });
    this.globalSection.append(this.globalLabel, this.globalInput);
    this.root.appendChild(this.globalSection);

    this.timelineSection = document.createElement("div");
    this.timelineSection.className = "sf-h3-section";
    this.ruler = document.createElement("div");
    this.ruler.className = "sf-h3-ruler";
    this.track = document.createElement("div");
    this.track.className = "sf-h3-track";
    this.audioRow = document.createElement("div");
    this.audioRow.className = "sf-h3-audio-row";
    this.timelineSection.append(this.ruler, this.track, this.audioRow);
    this.root.appendChild(this.timelineSection);

    this.editorSection = document.createElement("div");
    this.editorSection.className = "sf-h3-section";
    this.root.appendChild(this.editorSection);

    this.outputSection = document.createElement("div");
    this.outputSection.className = "sf-h3-section";
    const outputLabel = document.createElement("span");
    outputLabel.className = "sf-h3-label";
    outputLabel.textContent = "H3最终提示词预览";
    this.outputEl = document.createElement("div");
    this.outputEl.className = "sf-h3-output";
    this.outputSection.append(outputLabel, this.outputEl);
    this.root.appendChild(this.outputSection);
  }

  addToolbarButton(parent, text, title, kind) {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.hidden = true;
    input.accept = kind === "image" ? "image/*" : kind === "video" ? "video/*" : "audio/*";
    input.addEventListener("change", async () => {
      const files = Array.from(input.files || []);
      input.value = "";
      await this.upload(files, kind);
    });
    const button = document.createElement("button");
    button.className = "sf-h3-btn";
    button.textContent = text;
    button.title = title;
    button.addEventListener("click", () => input.click());
    parent.append(button, input);
    return button;
  }

  addActionButton(parent, text, title, action, extraClass = "") {
    const button = document.createElement("button");
    button.className = `sf-h3-btn ${extraClass}`.trim();
    button.textContent = text;
    button.title = title;
    button.addEventListener("click", action);
    parent.appendChild(button);
    return button;
  }

  addGridUploadButton(parent) {
    const input = document.createElement("input");
    input.type = "file";
    input.hidden = true;
    input.accept = "image/*";
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      input.value = "";
      if (file) await this.importGridImage(file);
    });
    const button = document.createElement("button");
    button.className = "sf-h3-btn";
    button.textContent = "导入宫格图";
    button.title = "直接导入四宫格、六宫格或九宫格图片并立即预览";
    button.addEventListener("click", () => input.click());
    parent.append(button, input);
    return button;
  }

  async importGridImage(file) {
    this.summary = `正在导入宫格图：${file.name}`;
    this.renderSummary();
    const form = new FormData();
    form.append("file", file, file.name);
    try {
      const response = await api.fetchApi("/sf_h3_director/upload", { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok || result.error) throw new Error(result.error || `上传失败：${response.status}`);
      if (result.kind !== "image") throw new Error("宫格模式只能导入图片文件。");
      this.state.gridImage = {
        file: result.name,
        name: result.original_name || file.name,
        width: result.width || 0,
        height: result.height || 0,
      };
      this.storyboardPreviews = [];
      this.createStoryboardSlots(false);
      this.summary = "等待添加参考素材";
      this.save();
      this.render();
    } catch (error) {
      this.summary = `导入失败：${String(error?.message || error)}`;
      this.renderSummary();
    }
  }

  setMode(mode) {
    const nextMode = mode === "全能参考" ? "全能参考" : "宫格模式";
    this.persistPromptInput(this.mode);
    const widget = getWidget(this.node, "mode");
    if (widget) widget.value = nextMode;
    this.syncPromptEditor(true);
    if (nextMode === "宫格模式" && !this.state.items.some((item) => item.source === "storyboard")) {
      this.createStoryboardSlots(false);
    }
    if (nextMode === "宫格模式") this.syncFromSockets();
    if (!this.selected) this.state.selectedId = this.activeItems[0]?.id || null;
    this.save();
    this.render();
  }

  persistPromptInput(mode = this.mode) {
    if (!this.globalInput) return;
    if (mode === "全能参考") {
      this.state.allReferencePrompt = this.globalInput.value;
    } else {
      this.state.globalPrompt = this.globalInput.value;
      if (this.promptWidget) this.promptWidget.value = this.globalInput.value;
    }
  }

  syncPromptEditor(force = false) {
    if (!this.globalInput || (!force && document.activeElement === this.globalInput)) return;
    if (this.mode === "全能参考") {
      this.globalLabel.textContent = "全能参考提示词";
      this.globalInput.placeholder = "点击下方素材插入 @图片1、@视频1、@音频1，再描述主体、动作、运镜、台词和声音……";
      this.globalInput.value = this.state.allReferencePrompt || "";
    } else {
      this.globalLabel.textContent = "全局创作要求";
      this.globalInput.placeholder = "整体风格、人物一致性、画面质感、声音氛围和必须遵守的要求……";
      this.globalInput.value = this.state.globalPrompt || "";
    }
  }

  referenceToken(item, items = this.activeItems) {
    const labels = { image: "图片", video: "视频", audio: "音频" };
    const sameKind = items.filter((candidate) => candidate.kind === item.kind);
    const index = sameKind.findIndex((candidate) => candidate.id === item.id);
    return index >= 0 && labels[item.kind] ? `@${labels[item.kind]}${index + 1}` : "";
  }

  insertReferenceToken(item) {
    const token = this.referenceToken(item);
    if (!token || this.mode !== "全能参考") return;
    const input = this.globalInput;
    const start = Number.isFinite(input.selectionStart) ? input.selectionStart : input.value.length;
    const end = Number.isFinite(input.selectionEnd) ? input.selectionEnd : start;
    const before = input.value.slice(0, start);
    const after = input.value.slice(end);
    const leftSpace = before && !/\s$/.test(before) ? " " : "";
    const rightSpace = after && !/^\s/.test(after) ? " " : "";
    const inserted = `${leftSpace}${token}${rightSpace}`;
    input.value = before + inserted + after;
    const cursor = before.length + inserted.length;
    input.focus();
    input.setSelectionRange(cursor, cursor);
    this.state.allReferencePrompt = input.value;
    this.state.selectedId = item.id;
    this.save();
    this.renderTrack();
  }

  updateModeUI() {
    for (const [mode, button] of this.modeButtons || []) {
      button.classList.toggle("active", mode === this.mode);
    }
    for (const button of this.referenceControls || []) button.hidden = this.mode !== "全能参考";
    for (const button of this.gridControls || []) button.hidden = this.mode !== "宫格模式";
    this.autoArrangeButton.hidden = this.mode !== "宫格模式";
    this.titleEl.textContent = this.mode === "宫格模式" ? "宫格分镜时间线" : "全能参考素材画布";
    const referenceMode = this.mode === "全能参考";
    this.root.classList.toggle("reference-layout", referenceMode);
    if (referenceMode) {
      this.root.insertBefore(this.globalSection, this.editorSection);
    } else {
      this.root.insertBefore(this.globalSection, this.timelineSection);
    }
    this.ruler.style.display = referenceMode ? "none" : "flex";
    this.editorSection.style.display = referenceMode ? "none" : "block";
    this.outputSection.style.display = referenceMode ? "none" : "block";
    this.track.classList.toggle("reference-mode", this.mode === "全能参考");
    this.syncPromptEditor();
  }

  hookWidgets() {
    for (const name of ["duration_seconds", "mode", "grid_layout"]) {
      const widget = getWidget(this.node, name);
      if (!widget || widget._csH3Hooked) continue;
      const original = widget.callback;
      widget.callback = (...args) => {
        const result = original?.apply(widget, args);
        if (name === "duration_seconds") {
          // 有接口分镜文本时按文本时长占比重新缩放；否则均分
          if (this.mode === "宫格模式" && this.getSocketStoryboardText()) this.syncFromSockets(true);
          else this.autoArrange(false);
        }
        if (name === "grid_layout") {
          // 布局变化：按新布局重建槽位（保留各格提示词），并重新应用接口文本识别
          this.createStoryboardSlots(false);
          this.syncFromSockets();
        }
        if (name === "mode" && !this.selected) this.state.selectedId = this.activeItems[0]?.id || null;
        this.render();
        return result;
      };
      widget._csH3Hooked = true;
    }
  }

  async upload(files, requestedKind) {
    if (!files.length || this.mode !== "全能参考") return;
    this.summary = `正在上传 ${files.length} 个素材……`;
    this.renderSummary();
    for (const file of files) {
      const form = new FormData();
      form.append("file", file, file.name);
      try {
        const response = await api.fetchApi("/sf_h3_director/upload", { method: "POST", body: form });
        const result = await response.json();
        if (!response.ok || result.error) throw new Error(result.error || `上传失败：${response.status}`);
        const kind = result.kind || requestedKind;
        const visualItems = this.state.items.filter((item) => item.kind === "image" || item.kind === "video");
        const lastEnd = visualItems.reduce((end, item) => Math.max(end, Number(item.start || 0) + Number(item.duration || 0)), 0);
        const item = {
          id: makeId(kind),
          kind,
          file: result.name,
          name: result.original_name || file.name,
          width: result.width || 0,
          height: result.height || 0,
          mediaDuration: result.duration || 0,
          hasAudio: !!result.has_audio,
          includeAudio: kind === "video" && !!result.has_audio,
          start: kind === "audio" ? 0 : Math.min(lastEnd, Math.max(0, this.totalSeconds - 0.5)),
          duration: kind === "audio" ? this.totalSeconds : Math.min(2.5, this.totalSeconds),
          prompt: "",
          sound: "",
        };
        this.state.items.push(item);
        this.state.selectedId = item.id;
      } catch (error) {
        this.summary = String(error?.message || error);
        this.renderSummary();
      }
    }
    const visualCount = this.state.items.filter((item) => item.kind !== "audio").length;
    if (visualCount > 0) this.autoArrange(false);
    this.save();
    this.render();
  }

  getSocketGridUrl() {
    const origin = getOriginNode(this.node, "storyboard_images");
    if (!origin) return "";
    const nodeType = origin.type || origin.comfyClass || "";
    if (nodeType === "LoadImage" || nodeType === "LoadImageMask" || getWidget(origin, "image") || getWidget(origin, "图像")) {
      const url = loadImageNodeUrl(origin);
      if (url) return url;
    }
    return origin.imgs?.[0]?.src || origin.image?.src || "";
  }

  getSocketStoryboardText() {
    const origin = getOriginNode(this.node, "storyboard_text");
    if (!origin?.widgets?.length) return "";
    for (const widget of origin.widgets) {
      if (typeof widget.value === "string" && widget.value.trim()) return widget.value;
    }
    return "";
  }

  // 探测接口宫格图的真实宽高，用于时间线缩略图等比显示（黑边填充，不拉伸）
  probeGridDims(url) {
    if (!url) return;
    const img = new Image();
    img.onload = () => {
      this.gridImageDims = { w: img.naturalWidth || 0, h: img.naturalHeight || 0 };
      this.render();
    };
    img.onerror = () => { };
    img.src = url;
  }

  // 从接口连接的宫格图像 + 分镜文本自动分镜：图片落格预览、提示词按方位落格、X秒按比例分时长。
  // 文本签名（含布局）未变化时不重排，保留用户在时间线上的手动编辑。
  syncFromSockets(force = false) {
    if (this.mode !== "宫格模式") return false;
    let changed = false;
    const gridUrl = this.getSocketGridUrl();
    if (gridUrl) {
      if (this.gridSocketUrl !== gridUrl) {
        this.gridSocketUrl = gridUrl;
        this.probeGridDims(gridUrl);
        changed = true;
      }
      if (!this.state.items.some((item) => item.source === "storyboard")) {
        this.createStoryboardSlots(false);
        changed = true;
      }
    }
    const text = this.getSocketStoryboardText();
    const [cols, rows] = gridDimensions(this.node);
    const sig = text ? `${h3TextSig(text)}@${cols}x${rows}` : "";
    if (text && (force || sig !== this.state._textSig)) {
      const recognized = h3RecognizeStoryboard(text, cols, rows);
      if (recognized.recognized) {
        if (!this.state.items.some((item) => item.source === "storyboard")) this.createStoryboardSlots(false);
        const count = cols * rows;
        const slots = this.state.items.filter((item) => item.source === "storyboard");
        const slotOf = (index) => slots.find((it) => Number(it.gridIndex) === index);
        for (let index = 0; index < count; index += 1) {
          const item = slotOf(index);
          if (item && recognized.cells[index]) item.prompt = recognized.cells[index];
        }
        // 时长：文本识别到 X秒 → 按占比缩放到总时长（与后端 _compile_prompt 同规则）；
        // 未识别时长 → 保持槽位现有起止（尊重手动调整/均分）。
        if (recognized.durations.some(Boolean)) {
          const weights = [];
          for (let i = 0; i < count; i += 1) weights.push(recognized.durations[i] || 0);
          const known = weights.filter((w) => w > 0);
          const avg = known.length ? known.reduce((a, b) => a + b, 0) / known.length : 1;
          const filled = weights.map((w) => (w > 0 ? w : avg));
          const totalW = filled.reduce((a, b) => a + b, 0) || 1;
          let cursor = 0;
          for (let index = 0; index < count; index += 1) {
            const item = slotOf(index);
            if (!item) continue;
            const dur = Math.max(0.1, filled[index] * (this.totalSeconds / totalW));
            item.start = cursor;
            item.duration = index === count - 1 ? Math.max(0.1, this.totalSeconds - cursor) : dur;
            cursor += dur;
          }
        }
        // 全局：仅在未填写全局创作要求时回填
        if (recognized.globalPrompt && !this.state.globalPrompt) {
          this.state.globalPrompt = recognized.globalPrompt;
          if (this.promptWidget) this.promptWidget.value = recognized.globalPrompt;
          if (this.globalInput) this.globalInput.value = recognized.globalPrompt;
        }
        this.state._textSig = sig;
        changed = true;
        this.summary = `已从接口同步 ${recognized.cells.filter(Boolean).length} 个分镜（方位落格/时长分配）`;
      }
    }
    if (changed) {
      this.save();
      this.render();
    }
    return changed;
  }

  createStoryboardSlots(shouldRender = true) {
    const [cols, rows] = gridDimensions(this.node);
    const count = cols * rows;
    const previous = new Map(
      this.state.items
        .filter((item) => item.source === "storyboard")
        .map((item) => [Number(item.gridIndex), item])
    );
    this.state.items = this.state.items.filter((item) => item.source !== "storyboard");
    const duration = this.totalSeconds / count;
    for (let index = 0; index < count; index += 1) {
      const old = previous.get(index) || {};
      this.state.items.push({
        id: `storyboard_${index}`,
        source: "storyboard",
        gridIndex: index,
        kind: "image",
        name: old.name || `宫格分镜 ${index + 1}`,
        start: index * duration,
        duration,
        prompt: old.prompt || "",
        sound: old.sound || "",
      });
    }
    this.state.selectedId = "storyboard_0";
    this.save();
    if (shouldRender) this.render();
  }

  autoArrange(shouldRender = true) {
    const visuals = this.activeItems.filter((item) => item.kind === "image" || item.kind === "video");
    if (!visuals.length) return;
    const duration = this.totalSeconds / visuals.length;
    visuals.forEach((item, index) => {
      item.start = index * duration;
      item.duration = index === visuals.length - 1 ? this.totalSeconds - item.start : duration;
    });
    this.activeItems.filter((item) => item.kind === "audio").forEach((item) => {
      item.start = 0;
      item.duration = this.totalSeconds;
    });
    this.save();
    if (shouldRender) this.render();
  }

  removeSelected() {
    if (!this.state.selectedId) return;
    const previousItems = this.activeItems.slice();
    this.state.items = this.state.items.filter((item) => item.id !== this.state.selectedId);
    if (this.mode === "全能参考") this.renumberReferencePrompt(previousItems);
    this.state.selectedId = this.activeItems[0]?.id || null;
    this.save();
    this.render();
  }

  renumberReferencePrompt(previousItems) {
    let prompt = this.state.allReferencePrompt || "";
    const placeholders = new Map();
    for (const item of previousItems) {
      const oldToken = this.referenceToken(item, previousItems);
      if (!oldToken) continue;
      const placeholder = `__SF_H3_REF_${String(item.id).replace(/[^A-Za-z0-9_]/g, "_")}__`;
      prompt = prompt.split(oldToken).join(placeholder);
      placeholders.set(item.id, placeholder);
    }
    for (const item of previousItems) {
      const placeholder = placeholders.get(item.id);
      if (!placeholder) continue;
      const nextToken = this.state.items.some((candidate) => candidate.id === item.id)
        ? this.referenceToken(item)
        : "";
      prompt = prompt.split(placeholder).join(nextToken);
    }
    this.state.allReferencePrompt = prompt.replace(/[ \t]{2,}/g, " ").trim();
    if (this.globalInput) this.globalInput.value = this.state.allReferencePrompt;
  }

  notifyWorkflowChanged() {
    const graph = this.node.graph || app.graph;
    this.node.setDirtyCanvas?.(true, false);
    graph?.change?.();
    graph?.onNodeChanged?.(this.node);
    graph?.onStateChanged?.();

    clearTimeout(this.workflowCaptureTimer);
    this.workflowCaptureTimer = setTimeout(() => {
      try {
        const canvasEl = app.canvasEl || app.canvas?.canvas;
        canvasEl?.dispatchEvent(new PointerEvent("pointerup", {
          bubbles: true,
          cancelable: true,
        }));
        app.canvas?.checkState?.();
        app.canvas?.captureCanvasState?.();
      } catch (_) {
        // Older ComfyUI builds persist through the graph change callbacks above.
      }
    }, 100);
  }

  save(updateTimestamp = true) {
    this.storageKey = workflowSessionKey(this.node);
    this.persistPromptInput();
    if (updateTimestamp) this.state.updatedAt = Date.now();
    const serialized = JSON.stringify(this.state);
    for (const [widget, value] of [
      [this.dataWidget, serialized],
      [this.promptWidget, this.state.globalPrompt],
    ]) {
      if (!widget || widget.value === value) continue;
      const previous = widget.value;
      widget.value = value;
      this.node.onWidgetChanged?.(widget.name, value, previous, widget);
      try {
        widget.callback?.call(widget, value);
      } catch (_) { }
    }
    this.node.properties = this.node.properties || {};
    this.node.properties.csH3Timeline = serialized;
    this.node.properties.timeline_data = serialized;
    this.node.properties.global_prompt = this.state.globalPrompt;
    if (updateTimestamp) {
      try {
        window.sessionStorage?.setItem(this.storageKey, serialized);
      } catch (_) { }
    }
    if (updateTimestamp) this.notifyWorkflowChanged();
  }

  restore() {
    this.storageKey = workflowSessionKey(this.node);
    this.state = loadPersistedState(this.node, this.dataWidget, this.serializedWidget, this.storageKey);
    if (!this.state.allReferencePrompt && this.mode === "全能参考") {
      this.state.allReferencePrompt = this.state.globalPrompt || String(this.promptWidget?.value || "");
    }
    if (!this.selected) this.state.selectedId = this.activeItems[0]?.id || null;
    this.syncPromptEditor(true);
    this.syncFromSockets();
    this.render();
  }

  renderSummary() {
    const images = this.activeItems.filter((item) => item.kind === "image").length;
    const videos = this.activeItems.filter((item) => item.kind === "video").length;
    const audios = this.activeItems.filter((item) => item.kind === "audio").length;
    this.summaryEl.textContent = this.summary.startsWith("正在") || this.summary.includes("失败")
      ? this.summary
      : this.mode === "宫格模式"
        ? `宫格模式｜${this.state.gridImage?.name || "外部宫格接口"}｜${images}分镜｜${this.totalSeconds.toFixed(1)}秒`
        : `全能参考｜${images}图 ${videos}视频 ${audios}音频｜${this.totalSeconds.toFixed(1)}秒`;
  }

  render() {
    this.updateModeUI();
    this.renderSummary();
    this.renderRuler();
    this.renderTrack();
    this.renderEditor();
    this.outputEl.textContent = this.compiledPrompt;
  }

  renderRuler() {
    this.ruler.innerHTML = "";
    for (let index = 0; index <= 5; index += 1) {
      const span = document.createElement("span");
      span.textContent = `${(this.totalSeconds * index / 5).toFixed(1)}秒`;
      this.ruler.appendChild(span);
    }
  }

  renderTrack() {
    this.track.innerHTML = "";
    const referenceMode = this.mode === "全能参考";
    const visuals = this.activeItems.filter((item) => item.kind === "image" || item.kind === "video");
    if (!visuals.length) {
      const empty = document.createElement("div");
      empty.className = "sf-h3-empty";
      empty.textContent = this.mode === "宫格模式" ? "连接宫格图像并生成宫格槽位" : "添加图片或视频参考";
      this.track.appendChild(empty);
    }
    for (const item of visuals) {
      const card = document.createElement("div");
      card.className = `sf-h3-card ${item.id === this.state.selectedId ? "selected" : ""}`;
      if (!referenceMode) {
        card.style.left = `${clamp(item.start, 0, this.totalSeconds) / this.totalSeconds * 100}%`;
        card.style.width = `${Math.max(5, clamp(item.duration, 0.1, this.totalSeconds) / this.totalSeconds * 100)}%`;
      }
      const token = referenceMode ? this.referenceToken(item) : "";
      card.title = referenceMode
        ? `点击插入 ${token}\n${item.name || "参考素材"}`
        : `${item.name || "参考素材"}\n${Number(item.start || 0).toFixed(2)}秒 - ${(Number(item.start || 0) + Number(item.duration || 0)).toFixed(2)}秒`;
      const storyboardPreview = item.source === "storyboard" ? this.storyboardPreviews[item.gridIndex] : null;
      const importedGrid = item.source === "storyboard" ? this.state.gridImage : null;
      const socketGridUrl = item.source === "storyboard" && !importedGrid?.file ? this.gridSocketUrl : "";
      if (storyboardPreview) {
        const media = document.createElement("img");
        media.src = previewUrl(storyboardPreview);
        card.appendChild(media);
      } else if (importedGrid?.file || socketGridUrl) {
        const gridUrl = importedGrid?.file ? mediaUrl(importedGrid.file) : socketGridUrl;
        const [cols, rows] = gridDimensions(this.node);
        const col = Number(item.gridIndex || 0) % cols;
        const row = Math.floor(Number(item.gridIndex || 0) / cols);
        const bgSize = `${cols * 100}% ${rows * 100}%`;
        const bgPos = `${cols > 1 ? col * 100 / (cols - 1) : 0}% ${rows > 1 ? row * 100 / (rows - 1) : 0}%`;
        // 已知宫格图真实尺寸时，单格按原始比例显示（黑边填充，不拉伸）；
        // 尺寸未知时退回铺满（与原版一致）。
        const dims = importedGrid?.file
          ? { w: Number(importedGrid.width) || 0, h: Number(importedGrid.height) || 0 }
          : (this.gridImageDims || { w: 0, h: 0 });
        const cellAspect = dims.w > 0 && dims.h > 0 ? (dims.w / cols) / (dims.h / rows) : 0;
        const thumb = document.createElement("div");
        thumb.className = "sf-h3-grid-thumb";
        thumb.style.backgroundImage = `url("${gridUrl}")`;
        thumb.style.backgroundSize = bgSize;
        thumb.style.backgroundPosition = bgPos;
        if (cellAspect > 0) {
          const wrap = document.createElement("div");
          wrap.className = "sf-h3-grid-thumb-wrap";
          thumb.style.width = `${Math.round(72 * cellAspect)}px`;
          thumb.style.maxWidth = "100%";
          wrap.appendChild(thumb);
          card.appendChild(wrap);
        } else {
          card.appendChild(thumb);
        }
      } else if (item.file) {
        const media = document.createElement(item.kind === "video" ? "video" : "img");
        media.src = mediaUrl(item.file);
        if (item.kind === "video") {
          media.muted = true;
          media.preload = "metadata";
        }
        card.appendChild(media);
      } else {
        const placeholder = document.createElement("div");
        placeholder.className = "sf-h3-placeholder";
        placeholder.textContent = item.name || "宫格分镜";
        card.appendChild(placeholder);
      }
      const meta = document.createElement("div");
      meta.className = "sf-h3-card-meta";
      meta.textContent = referenceMode
        ? `${token}｜${item.name || "未命名"}`
        : `${item.kind === "video" ? "视频" : "图片"}｜${item.name || "未命名"}`;
      card.appendChild(meta);
      card.addEventListener("click", () => {
        if (referenceMode) {
          this.insertReferenceToken(item);
          return;
        }
        this.state.selectedId = item.id;
        this.save();
        this.render();
      });
      this.track.appendChild(card);
    }

    this.audioRow.innerHTML = "";
    const audios = this.activeItems.filter((item) => item.kind === "audio");
    for (const item of audios) {
      const chip = document.createElement("button");
      chip.className = `sf-h3-audio-chip ${item.id === this.state.selectedId ? "selected" : ""}`;
      const token = referenceMode ? this.referenceToken(item) : "";
      chip.textContent = referenceMode ? `${token}｜${item.name || "参考音频"}` : `声音｜${item.name || "参考音频"}`;
      chip.title = referenceMode ? `点击插入 ${token}` : "选择这段参考音频";
      chip.addEventListener("click", () => {
        if (referenceMode) {
          this.insertReferenceToken(item);
          return;
        }
        this.state.selectedId = item.id;
        this.save();
        this.render();
      });
      this.audioRow.appendChild(chip);
    }
  }

  renderEditor() {
    this.editorSection.innerHTML = "";
    if (this.mode === "全能参考") return;
    const item = this.selected;
    if (!item) {
      const empty = document.createElement("div");
      empty.className = "sf-h3-empty";
      empty.textContent = "选择一个分镜或参考声音后，可以在这里编辑。";
      this.editorSection.appendChild(empty);
      return;
    }

    const editor = document.createElement("div");
    editor.className = "sf-h3-editor";
    const start = this.numberField("开始时间（秒）", item.start || 0, 0, this.totalSeconds, 0.05, (value) => {
      item.start = clamp(value, 0, this.totalSeconds);
      this.save();
      this.renderTrack();
    });
    const duration = this.numberField("持续时间（秒）", item.duration || 1, 0.1, this.totalSeconds, 0.05, (value) => {
      item.duration = clamp(value, 0.1, this.totalSeconds);
      this.save();
      this.renderTrack();
    });
    const name = this.textField("素材名称", item.name || "", (value) => {
      item.name = value;
      this.save();
      this.renderTrack();
    });
    editor.append(start, duration, name);

    const prompt = this.textAreaField(
      item.kind === "audio" ? "声音参考要求" : "画面、动作、镜头与台词",
      item.prompt || "",
      item.kind === "audio" ? "说明要参考的音色、说话方式、音乐节奏或环境氛围……" : "描述这一段发生的动作、情绪、运镜和人物台词……",
      (value) => { item.prompt = value; this.save(); }
    );
    prompt.classList.add("wide");
    editor.appendChild(prompt);

    if (item.kind !== "audio") {
      const sound = this.textAreaField("声音与台词补充", item.sound || "", "环境声、对白声线、音乐变化……", (value) => {
        item.sound = value;
        this.save();
      });
      sound.classList.add("wide");
      editor.appendChild(sound);
    }

    if (item.kind === "video" && item.hasAudio) {
      const wrap = document.createElement("label");
      wrap.className = "sf-h3-check wide";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = item.includeAudio !== false;
      checkbox.addEventListener("change", () => { item.includeAudio = checkbox.checked; this.save(); });
      wrap.append(checkbox, document.createTextNode("同时参考这段视频的原始声音"));
      editor.appendChild(wrap);
    }
    this.editorSection.appendChild(editor);
  }

  numberField(labelText, value, min, max, step, onChange) {
    const wrap = document.createElement("label");
    const label = document.createElement("span");
    label.className = "sf-h3-label";
    label.textContent = labelText;
    const input = document.createElement("input");
    input.className = "sf-h3-input";
    input.type = "number";
    input.min = min;
    input.max = max;
    input.step = step;
    input.value = Number(value).toFixed(2);
    input.addEventListener("change", () => onChange(input.value));
    wrap.append(label, input);
    return wrap;
  }

  textField(labelText, value, onInput) {
    const wrap = document.createElement("label");
    const label = document.createElement("span");
    label.className = "sf-h3-label";
    label.textContent = labelText;
    const input = document.createElement("input");
    input.className = "sf-h3-input";
    input.value = value;
    input.addEventListener("input", () => onInput(input.value));
    wrap.append(label, input);
    return wrap;
  }

  textAreaField(labelText, value, placeholder, onInput) {
    const wrap = document.createElement("label");
    const label = document.createElement("span");
    label.className = "sf-h3-label";
    label.textContent = labelText;
    const input = document.createElement("textarea");
    input.className = "sf-h3-textarea";
    input.value = value;
    input.placeholder = placeholder;
    input.addEventListener("input", () => onInput(input.value));
    wrap.append(label, input);
    return wrap;
  }

  onExecuted(message) {
    const prompt = message?.compiled_prompt?.[0] ?? message?.compiled_prompt;
    const summary = message?.summary?.[0] ?? message?.summary;
    const previews = message?.storyboard_previews;
    if (prompt) this.compiledPrompt = String(prompt);
    if (summary) this.summary = String(summary);
    if (Array.isArray(previews)) {
      this.storyboardPreviews = Array.isArray(previews[0]) ? previews[0] : previews;
    }
    this.render();
  }
}

app.registerExtension({
  name: "SF.H3.MultimodalDirector",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_CLASS) return;

    const originalCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = originalCreated?.apply(this, arguments);
      injectStyles();
      this.title = "SF-H3 多模态参考导演台";
      hideWidget(getWidget(this, "mode"));
      hideWidget(getWidget(this, "timeline_data"));
      hideWidget(getWidget(this, "global_prompt"));

      const root = document.createElement("div");
      const domWidget = this.addDOMWidget("sf_h3_director_ui", "sf_h3_director_ui", root, {
        hideOnZoom: false,
        getMinHeight: () => 690,
        getValue: () => "",
        setValue: () => { },
      });
      domWidget.computeSize = (width) => [width, 690];
      this._csH3Director = new H3DirectorUI(this, root);
      const width = Math.max(this.size?.[0] || 0, 920);
      const height = Math.max(this.size?.[1] || 0, 930);
      this.setSize([width, height]);
      return result;
    };

    const originalConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      const result = originalConfigure?.apply(this, arguments);
      setTimeout(() => this._csH3Director?.restore(), 0);
      return result;
    };

    const originalSerialize = nodeType.prototype.onSerialize;
    nodeType.prototype.onSerialize = function (info) {
      this._csH3Director?.save(false);
      const result = originalSerialize?.apply(this, arguments);
      if (info && typeof info === "object") {
        for (const widget of this.widgets || []) {
          if (widget.name && widget.value !== undefined && widget.name !== "sf_h3_director_ui") {
            this.properties[widget.name] = widget.value;
          }
        }
        info.properties = { ...(this.properties || {}) };
        if (Array.isArray(info.widgets_values)) {
          for (const name of ["timeline_data", "global_prompt"]) {
            const widget = getWidget(this, name);
            const index = this.widgets?.indexOf(widget) ?? -1;
            if (index >= 0 && index < info.widgets_values.length) {
              info.widgets_values[index] = widget.value;
            }
          }
        }
      }
      return result;
    };

    const originalExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      const result = originalExecuted?.apply(this, arguments);
      this._csH3Director?.onExecuted(message);
      return result;
    };

    const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function () {
      const result = originalConnectionsChange?.apply(this, arguments);
      // 宫格图像/分镜文本接口连线变化时，自动同步分镜槽位与提示词
      setTimeout(() => this._csH3Director?.syncFromSockets(), 0);
      return result;
    };
  },
});
