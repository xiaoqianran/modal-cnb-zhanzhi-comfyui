// Pure authoring helpers. No graph execution, network, cache or identity inference.
export const COLORS = {red:"#ff3030", blue:"#3070ff", yellow:"#ffdf00", cyan:"#00dfff",
    green:"#20df50", magenta:"#ef30ef", orange:"#ff9000", white:"#ffffff", black:"#000000"};

const ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$/;
export function readDraft(text) {
    const value=JSON.parse(text);
    if (!value || !Array.isArray(value.markers) || !Array.isArray(value.relations))
        throw Error("JSON需要markers和relations数组。");
    if (value.markers.some(m=>!m || typeof m!=="object" || Array.isArray(m) ||
        typeof m.marker_id!=="string" || !["actor","target"].includes(m.kind) ||
        ["color","description","role_id"].some(k=>m[k]!==undefined&&typeof m[k]!=="string")) ||
        value.relations.some(r=>!r || typeof r!=="object" || Array.isArray(r)))
        throw Error("每个标记须有ID和actor／target类型；关系须为对象。可撤销或修复JSON。");
    return value;
}

function availableLabel(used, prefix="") {
    for (let index=0;;index++) {
        let rest=index+1, label="";
        while (rest) {rest--; label=String.fromCharCode(65+rest%26)+label; rest=Math.floor(rest/26);}
        if (!used.has(prefix+label)) return label;
    }
}

// Drafts may temporarily lack geometry/relations. Only Apply requires a complete
// executable spec. Helpers never invent an action or mutate the caller's draft.
export function addMarker(value, kind) {
    if (!["actor","target"].includes(kind)) throw Error("请选择人物框或目标框。");
    const next=structuredClone(value), prefix=kind+"_";
    const label=availableLabel(new Set(next.markers.map(m=>m.marker_id)),prefix);
    const used=new Set(next.markers.map(m=>(COLORS[m.color?.toLowerCase()]??m.color)?.toLowerCase()));
    const palette=kind==="actor"?["cyan","magenta","blue","green","orange","yellow","red","white"]
        :["yellow","orange","green","magenta","blue","cyan","red","white"];
    const color=palette.find(name=>!used.has(COLORS[name]))??palette[next.markers.length%palette.length];
    const marker={marker_id:prefix+label,kind,color,description:""};
    if (kind==="actor") marker.role_id=availableLabel(new Set(next.markers.filter(m=>m.kind==="actor").map(m=>m.role_id)));
    next.markers.push(marker);
    return {value:next,id:marker.marker_id};
}

export function editMarker(value, currentID, fields) {
    const next=structuredClone(value), marker=next.markers.find(m=>m.marker_id===currentID);
    if (!marker) throw Error("当前标记已不存在，请重新选择。");
    const newID=fields.marker_id?.trim();
    if (!ID.test(newID??"")) throw Error("ID须为1–48位英文字母、数字、下划线或短横线，首位为字母或数字。");
    if (next.markers.some(m=>m!==marker && m.marker_id===newID)) throw Error("标记ID已存在，请使用不同ID。");
    if (marker.kind==="actor" && !ID.test(fields.role_id?.trim()??"")) throw Error("人物角色ID格式有误。");
    const color=fields.color?.trim();
    if (typeof color!=="string" || !/^#[0-9a-f]{6}$/i.test(COLORS[color.toLowerCase()]??color))
        throw Error("颜色使用cyan、yellow等名称或#RRGGBB。");
    Object.assign(marker,{marker_id:newID,color,description:fields.description??""});
    if (marker.kind==="actor") marker.role_id=fields.role_id.trim();
    for (const relation of next.relations) {
        if (relation.actor_marker_id===currentID) relation.actor_marker_id=newID;
        if (relation.target_marker_id===currentID) relation.target_marker_id=newID;
    }
    return next;
}

export function removeMarker(value, id) {
    const next=structuredClone(value);
    next.markers=next.markers.filter(m=>m.marker_id!==id);
    next.relations=next.relations.filter(r=>r.actor_marker_id!==id && r.target_marker_id!==id);
    return next;
}

// Canvas object-fit:contain may letterbox inside a CSS-constrained rectangle.
// Pointer coordinates must follow the displayed image, not those empty margins.
export function sourcePoint(clientX, clientY, rect, width, height) {
    const scale=Math.min(rect.width/width,rect.height/height);
    if (!(scale>0) || width<=0 || height<=0 || ![clientX,clientY,width,height].every(Number.isFinite)) throw Error("预览尺寸无效。");
    const x=(clientX-rect.left-(rect.width-width*scale)/2)/scale;
    const y=(clientY-rect.top-(rect.height-height*scale)/2)/scale;
    return {point:[x,y],inside:x>=0 && y>=0 && x<=width && y<=height};
}

export function validateSpec(value, mode="render_rectangles") {
    if (!value || typeof value !== "object" || Array.isArray(value) ||
        Object.keys(value).sort().join(",") !== "markers,relations" ||
        !Array.isArray(value.markers) || value.markers.length<2 || value.markers.length>64 ||
        !Array.isArray(value.relations) || value.relations.length<1 || value.relations.length>128)
        throw Error("需要2–64个明确标记及1–128条人物→目标关系。");
    if (!["render_rectangles","provided_marked"].includes(mode)) throw Error("未知准备模式。");
    const ids=new Map(), id=/^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$/;
    const bounded=s=>typeof s==="string" && s.trim() && new TextEncoder().encode(s).length<=4096;
    for (const m of value.markers) {
        if (!m || typeof m!=="object" || typeof m.marker_id!=="string" || !id.test(m.marker_id) || ids.has(m.marker_id) ||
            !["actor","target"].includes(m.kind) || !bounded(m.description) ||
            Object.keys(m).some(k=>!["marker_id","kind","color","description","role_id","xyxy"].includes(k)) ||
            (m.kind==="actor" && (typeof m.role_id!=="string" || !id.test(m.role_id))) ||
            (m.kind==="target" && Object.hasOwn(m,"role_id"))) throw Error("标记ID／角色／描述有误。");
        if (typeof m.color!=="string" || m.color.length>32) throw Error("颜色必须为名称或#RRGGBB字符串。");
        const rgb=COLORS[m.color.toLowerCase()] ?? m.color.toLowerCase();
        if (!/^#[0-9a-f]{6}$/.test(rgb)) throw Error("颜色使用名称或#RRGGBB。");
        if (m.xyxy!=null) {
            const p=m.xyxy;
            if (!Array.isArray(p) || p.length!==4 || p.some(n=>typeof n!=="number" || !Number.isFinite(n)) ||
                !(0<=p[0] && p[0]<p[2] && p[2]<=1 && 0<=p[1] && p[1]<p[3] && p[3]<=1))
                throw Error("矩形需要有限、非零且0–1范围的xyxy。");
        } else if (mode==="render_rectangles") throw Error("自动画框必须有坐标，手绘模式可无坐标。");
        ids.set(m.marker_id,m);
    }
    const used=new Set();
    for (const r of value.relations) {
        if (!r || typeof r!=="object" || Object.keys(r).sort().join(",")!=="action,actor_marker_id,target_marker_id" ||
            ids.get(r.actor_marker_id)?.kind!=="actor" || ids.get(r.target_marker_id)?.kind!=="target" || !bounded(r.action))
            throw Error("关系必须明确指向人物框和目标框，并写动作。");
        used.add(r.actor_marker_id); used.add(r.target_marker_id);
    }
    if (used.size!==ids.size) throw Error("每个框都要有对应关系；同色和共享目标允许。");
    if (new TextEncoder().encode(JSON.stringify(value)).length>65536) throw Error("标记JSON超过64KiB。");
    return value;
}

export function normalizedBox(start, end, width, height) {
    if (!Array.isArray(start) || !Array.isArray(end) || start.length!==2 || end.length!==2) throw Error("拖动需要源平面上的两个点。");
    if (![...start,...end,width,height].every(Number.isFinite) || width<=0 || height<=0) throw Error("源尺寸／拖动坐标无效。");
    const clamp=n=>Math.min(1,Math.max(0,n));
    const p=[clamp(Math.min(start[0],end[0])/width),clamp(Math.min(start[1],end[1])/height),
        clamp(Math.max(start[0],end[0])/width),clamp(Math.max(start[1],end[1])/height)];
    if (p[0]>=p[2] || p[1]>=p[3]) throw Error("不能画零面积框。");
    return p;
}

export function setDraft(node, value, sourceSHA="", selectedMode) {
    const get=name=>node.widgets?.find(w=>w.name===name);
    const target=get("markers_json"), mode=get("mode"), binding=get("expected_source_sha256");
    const driven=connectedFields(node,["markers_json","mode","expected_source_sha256"]);
    if (driven.length) throw Error(`由外部连线驱动：${driven.join("、")}。编辑器不会断线或覆盖来源；请编辑来源节点，或手动转换回控件后重开。`);
    if (!target || !mode || !binding) throw Error("找不到实际工作流字段。");
    validateSpec(value,selectedMode??mode.value);
    if (typeof sourceSHA!=="string" || (sourceSHA && !/^[0-9a-f]{64}$/.test(sourceSHA))) throw Error("预览源SHA无效。");
    // Actual serialized widgets, not an unsaved hidden editor plan.
    target.value=JSON.stringify(value);
    binding.value=sourceSHA;
    if (selectedMode!==undefined) mode.value=selectedMode;
    node.setDirtyCanvas?.(true,true);
    return target.value;
}

export function connectedFields(node,names=["markers_json","mode","expected_source_sha256","line_width"]) {
    return names.filter(name=>node.inputs?.some(pin=>pin.name===name && pin.link!=null));
}

export async function rgbSHA(imageData) {
    const rgb=new Float32Array(imageData.width*imageData.height*3);
    for (let i=0,j=0;i<imageData.data.length;i+=4) {
        rgb[j++]=imageData.data[i]/255; rgb[j++]=imageData.data[i+1]/255; rgb[j++]=imageData.data[i+2]/255;
    }
    const bytes=globalThis.crypto?.subtle
        ? new Uint8Array(await globalThis.crypto.subtle.digest("SHA-256",rgb))
        : await portableSHA256(new Uint8Array(rgb.buffer));
    return [...bytes].map(b=>b.toString(16).padStart(2,"0")).join("");
}

// Same SHA-256 on LAN HTTP where WebCrypto is unavailable. This fallback never
// drops the source binding. Small chunks yield to the UI; no worker/CSP changes.
export async function portableSHA256(bytes) {
    const k=new Uint32Array([0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]);
    const h=new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);
    const w=new Uint32Array(64), total=Math.ceil((bytes.length+9)/64)*64;
    const high=Math.floor(bytes.length/0x20000000), low=(bytes.length*8)>>>0;
    const rotate=(x,n)=>(x>>>n)|(x<<(32-n));
    const byte=i=>i<bytes.length?bytes[i]:i===bytes.length?128:i>=total-4?(low>>>((total-1-i)*8))&255
        :i>=total-8?(high>>>((total-5-i)*8))&255:0;
    for (let offset=0;offset<total;offset+=64) {
        for (let i=0;i<16;i++) {const j=offset+i*4; w[i]=(byte(j)<<24)|(byte(j+1)<<16)|(byte(j+2)<<8)|byte(j+3);}
        for (let i=16;i<64;i++) {const x=w[i-15],y=w[i-2];
            w[i]=(w[i-16]+(rotate(x,7)^rotate(x,18)^(x>>>3))+w[i-7]+(rotate(y,17)^rotate(y,19)^(y>>>10)))>>>0;}
        let [a,b,c,d,e,f,g,z]=h;
        for (let i=0;i<64;i++) {const t1=(z+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^(~e&g))+k[i]+w[i])>>>0;
            const t2=((rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&b)^(a&c)^(b&c)))>>>0;
            z=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;}
        for (const [i,v] of [a,b,c,d,e,f,g,z].entries()) h[i]=(h[i]+v)>>>0;
        if (offset && offset%(512*1024)===0) await new Promise(resolve=>setTimeout(resolve,0));
    }
    const out=new Uint8Array(32), view=new DataView(out.buffer);
    for (let i=0;i<8;i++) view.setUint32(i*4,h[i]);
    return out;
}
