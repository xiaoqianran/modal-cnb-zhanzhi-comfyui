import { COLORS, addMarker, connectedFields, editMarker, normalizedBox, readDraft, removeMarker,
    rgbSHA, setDraft, sourcePoint, validateSpec } from "./visual_marker_editor.mjs";
import { DraftHistory, boxHandles, gestureMoved, hitMarker, renderMarkedRGBA, transformBox,
    validBox } from "./visual_marker_authoring.mjs";

const widget=(node,name)=>node.widgets?.find(w=>w.name===name);
function el(tag,text,parent) {
    const value=document.createElement(tag);if(text!=null)value.textContent=text;parent?.appendChild(value);return value;
}
function button(label,parent,click) {
    const value=el("button",label,parent);value.type="button";value.onclick=click;return value;
}
function select(label,parent,options) {
    const wrap=el("label",label,parent), value=el("select",null,wrap);value.setAttribute("aria-label",label);
    for(const [id,name] of options) {const option=el("option",name,value);option.value=id;}return value;
}
const pretty=value=>JSON.stringify(value,null,2);
const MODES=[["render_rectangles","自动绘框：把矩形画入模型输入图"],["provided_marked","已有标记图：仅声明，不重画原图"]];

// Shared production DOM view; resolvers only read existing source links.
// Nothing in this editor can queue a prompt, replace a wire or save a workflow.
export function openMarkerEditorView(node,{upstreamSource=()=>null,locateSource=()=>"请检查来源节点。"}={}) {
    if(node._t8MarkerFocus)return node._t8MarkerFocus();
    const dialog=el("dialog",null,document.body);dialog.className="t8-marker-editor";
    dialog.setAttribute("aria-label","H3 视觉标记框选编辑器");
    el("style",`
      .t8-marker-editor {position:fixed;inset:0;margin:auto;box-sizing:border-box;width:min(96vw,1380px);height:94dvh;
        max-height:94dvh;overflow:hidden;background:#17212d;color:#eef3ff;padding:16px;border:1px solid #607185;
        border-radius:12px;font:14px/1.5 sans-serif}
      .t8-marker-editor[open] {display:flex;flex-direction:column;gap:9px}
      .t8-marker-editor::backdrop,.t8-marker-discard::backdrop {background:#0009}
      .t8-marker-editor h3,.t8-marker-editor h4,.t8-marker-editor p {margin:0}
      .t8-marker-editor button,.t8-marker-editor input,.t8-marker-editor select,.t8-marker-editor textarea {
        box-sizing:border-box;font:inherit;color:inherit;background:#253344;border:1px solid #607185;border-radius:5px;padding:6px}
      .t8-marker-editor button {cursor:pointer}.t8-marker-editor button:disabled {opacity:.45;cursor:default}
      .t8-marker-editor button[aria-pressed=true] {border-color:#f4ce91;background:#49402f}
      .t8-marker-editor header,.t8-marker-editor footer,.t8-marker-tools {display:flex;align-items:center;gap:7px;flex-wrap:wrap;flex-shrink:0}
      .t8-marker-editor header {justify-content:space-between}.t8-marker-editor .t8-marker-status {color:#ffd590;overflow-wrap:anywhere}
      .t8-marker-editor .t8-marker-ownership:empty {display:none}.t8-marker-editor .t8-marker-ownership {padding:7px;background:#493726;border-radius:5px}
      .t8-marker-editor .t8-marker-layout {display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:16px;flex:1;min-height:0}
      .t8-marker-editor .t8-marker-preview {display:flex;flex-direction:column;min-height:0;min-width:0;gap:8px}
      .t8-marker-editor .t8-marker-inspector {min-height:0;overflow:auto;overscroll-behavior:contain;padding-right:6px}
      .t8-marker-editor .t8-marker-inspector label {display:block;margin:7px 0}
      .t8-marker-editor label>input,.t8-marker-editor label>textarea,.t8-marker-editor .t8-marker-inspector label>select {display:block;width:100%;margin-top:3px}
      .t8-marker-editor canvas {display:block;flex:1;min-height:0;width:100%;object-fit:contain;touch-action:none;background:#0a111a;outline:1px solid #607185}
      .t8-marker-editor .t8-marker-relation {border:1px solid #435265;border-radius:6px;padding:8px;margin:8px 0}
      .t8-marker-editor .t8-marker-relation.active {border-color:#f4ce91}
      .t8-marker-editor .t8-marker-pair {display:flex;gap:5px;align-items:center}.t8-marker-editor .t8-marker-pair select {min-width:0;flex:1}
      .t8-marker-editor .t8-marker-geometry {display:block;color:#b6d9ff;flex-shrink:0}
      .t8-marker-editor details {margin:9px 0}.t8-marker-editor summary {cursor:pointer}
      .t8-marker-editor .t8-marker-primary {background:#e5c391;color:#17191c;font-weight:600}
      .t8-marker-editor .t8-marker-json {width:100%;min-height:180px;font:12px/1.4 monospace}
      .t8-marker-editor [hidden] {display:none!important}
      .t8-marker-discard {position:fixed;inset:0;margin:auto;max-width:min(90vw,440px);background:#17212d;color:#eef3ff;border:1px solid #607185;border-radius:10px;padding:20px}
      @media(max-width:760px) {.t8-marker-editor .t8-marker-layout {grid-template-columns:minmax(0,1fr) 230px;gap:10px}.t8-marker-editor {font-size:12px;padding:10px}}
      @media(max-width:500px) {.t8-marker-editor .t8-marker-layout {grid-template-columns:1fr;overflow:auto}.t8-marker-editor .t8-marker-preview {min-height:260px}.t8-marker-editor .t8-marker-inspector {overflow:visible}}
    `,dialog);
    const header=el("header",null,dialog);el("h3","视觉标记 · 人物 → 目标",header);
    button("关闭",header,()=>requestClose());
    const owner=el("div",null,dialog);owner.className="t8-marker-ownership";
    const controls=el("div",null,dialog);controls.className="t8-marker-tools";
    const mode=select("输入图模式",controls,MODES);
    const view=select("预览",controls,[["edit","编辑叠层"],["actual","实际输入图（Prepare输出）"]]);
    const load=button("读取上游底图",controls,()=>{
        const url=upstreamSource();if(url)void loadImage(url);
        else say("未找到本图直接／Reroute连接的LoadImage，或文件名由外部驱动。请选择与实际IMAGE相同的RGB底图；不会改接线。");
    });
    const file=el("input",null,controls);file.type="file";file.accept="image/png,image/jpeg,image/webp";
    file.setAttribute("aria-label","选择同一张RGB底图");
    const status=el("p","先读取底图；点框选择、拖内部移动、拖边角缩放。新框需填写描述和动作。",dialog);
    status.className="t8-marker-status";status.setAttribute("role","status");
    const layout=el("div",null,dialog);layout.className="t8-marker-layout";
    const preview=el("section",null,layout);preview.className="t8-marker-preview";
    const tools=el("div",null,preview);tools.className="t8-marker-tools";
    const selectTool=button("选择／移动",tools,()=>guard(()=>{flush();tool="select";relationActor=null;draw();}));
    button("＋ 人物框",tools,()=>createMarker("actor"));button("＋ 目标框",tools,()=>createMarker("target"));
    const redraw=button("重画当前框",tools,()=>guard(()=>{flush();tool="draw";draw();say("在底图拖出新范围，松开后替换当前框；Esc取消。");}));
    const relationTool=button("点选建关系",tools,()=>guard(()=>{flush();tool="relation";relationActor=null;
        say("依次点人物框、目标框建立关系；也可在右侧直接添加，再填写动作。编辑关系不会自动编造动作。");draw();}));
    const undo=button("撤销",tools,()=>travel(false)),redo=button("重做",tools,()=>travel(true));
    const canvas=el("canvas",null,preview);canvas.width=640;canvas.height=360;
    canvas.tabIndex=0;
    canvas.setAttribute("aria-label","视觉标记画布：点选、移动与边角缩放");
    const geometry=el("output","尚无底图。框是视觉参考，不是生成视频的硬坐标。",preview);geometry.className="t8-marker-geometry";
    const hint=el("small","编辑叠层的ID、控制点和关系线不进入模型输入图。",preview);
    const inspector=el("section",null,layout);inspector.className="t8-marker-inspector";
    const choice=select("当前标记",inspector,[]);
    const descriptionLabel=el("label","名称／描述",inspector),description=el("input",null,descriptionLabel);
    description.setAttribute("aria-label","名称／描述");description.placeholder="例如：红衣女子／门前地面";
    const colorLabel=el("label","颜色（名称或 #RRGGBB）",inspector),color=el("input",null,colorLabel);
    color.setAttribute("aria-label","颜色");
    const technical=el("details",null,inspector);el("summary","高级：标记ID与角色ID",technical);
    const idLabel=el("label","标记 ID",technical),id=el("input",null,idLabel);id.setAttribute("aria-label","标记 ID");
    const roleLabel=el("label","人物角色 ID",technical),role=el("input",null,roleLabel);role.setAttribute("aria-label","人物角色 ID");
    const remove=button("删除当前框及关联关系",inspector,()=>guard(()=>{flush();cancelDrag();write(removeMarker(spec(),selectedID));}));
    el("h4","人物 → 目标 · 动作",inspector);
    button("＋ 添加关系",inspector,()=>guard(()=>{flush();addRelation();}));
    const relations=el("div",null,inspector);
    const advanced=el("details",null,inspector);el("summary","高级：JSON草稿／复制",advanced);
    const text=el("textarea",null,advanced);text.className="t8-marker-json";text.setAttribute("aria-label","标记JSON草稿");
    button("复制JSON草稿",advanced,async()=>{
        try {await navigator.clipboard.writeText(text.value);say("JSON草稿已复制，尚未应用或保存。");}
        catch {advanced.open=true;text.focus();text.select();say("请按Ctrl／Cmd+C复制已选中的JSON草稿。");}
    });
    const footer=el("footer",null,dialog);
    const finish=button("应用并完成",footer,()=>apply(true));finish.className="t8-marker-primary";
    const applyMore=button("应用，继续编辑",footer,()=>apply(false));
    el("small","仅写入本节点；不运行、不自动保存工作流。",footer);
    const validity=el("small",null,footer);validity.className="t8-marker-status";

    let disposed=false,loading=false,imageEpoch=0,ownedURL=null,raw=null,sourceSHA="",drag=null;
    let selectedID="",tool="select",activeRelation=-1,relationActor=null,fieldError="",confirm=null;
    let appliedSHA=widget(node,"expected_source_sha256")?.value??"";
    let previewBaselineSHA=appliedSHA;
    mode.value=widget(node,"mode")?.value??"render_rectangles";
    const initial=widget(node,"markers_json")?.value??'{"markers":[],"relations":[]}';
    try {text.value=pretty(readDraft(initial));}catch {text.value=initial;}
    const state=()=>({text:text.value,mode:mode.value});
    const history=new DraftHistory(state());
    const ctx=canvas.getContext("2d");
    const spec=()=>readDraft(text.value);
    function say(message) {status.textContent=message;}
    function guard(fn) {try{return fn();}catch(error){say(error.message);updateButtons();return undefined;}}
    function flush() {
        if(fieldError)throw Error(fieldError);
        history.commit(state());updateButtons();
    }
    function write(value,chosen=selectedID) {
        text.value=pretty(value);fieldError="";history.commit(state());refresh(chosen);draw();
    }
    function ownership() {
        const driven=connectedFields(node),required=driven.filter(n=>n!=="line_width");
        owner.replaceChildren();
        if(driven.length) {
            el("span",`外部连线驱动：${driven.join("、")}。当前显示为本地草稿，不代表来源的运行时值；不会断线或假写隐藏控件。 `,owner);
            for(const name of driven)button(`查看 ${name} 来源`,owner,()=>say(locateSource(name)));
            if(required.length)el("small","可编辑／复制草稿；请到来源节点修改，或手动转换回控件后重开。",owner);
        }
        mode.disabled=driven.includes("mode");
        view.options[1].disabled=driven.some(n=>["markers_json","mode","line_width"].includes(n));
        return required;
    }
    function updateButtons() {
        let valid=true;try{validateSpec(spec(),mode.value);validity.textContent="";}
        catch(error){valid=false;validity.textContent=`待补全：${error.message}`;}
        const blocked=ownership().length>0;
        finish.disabled=applyMore.disabled=loading||!raw||!valid||!!fieldError||blocked;
        undo.disabled=!history.canUndo&&state().text===history.current.text;redo.disabled=!history.canRedo;
        const editing=view.value==="edit";
        selectTool.disabled=relationTool.disabled=!editing;redraw.disabled=!editing||!selectedID;
        selectTool.setAttribute("aria-pressed",String(tool==="select"));
        redraw.setAttribute("aria-pressed",String(tool==="draw"));
        relationTool.setAttribute("aria-pressed",String(tool==="relation"));
    }
    function refresh(chosen=selectedID) {
        const value=spec();fieldError="";
        selectedID=value.markers.some(m=>m.marker_id===chosen)?chosen:(value.markers[0]?.marker_id??"");
        choice.replaceChildren();
        for(const m of value.markers){const option=el("option",`${m.description||m.marker_id} · ${m.kind==="actor"?"人物":"目标"}`,choice);option.value=m.marker_id;}
        choice.value=selectedID;
        const m=value.markers.find(m=>m.marker_id===selectedID);
        description.value=m?.description??"";color.value=m?.color??"";id.value=m?.marker_id??"";role.value=m?.role_id??"";
        roleLabel.hidden=m?.kind!=="actor";
        for(const input of [description,color,id,role])input.disabled=!m;
        remove.disabled=!m;
        renderRelations(value);updateButtons();
    }
    function detailsInput() {
        try {
            const next=editMarker(spec(),selectedID,{marker_id:id.value,role_id:role.value,color:color.value,description:description.value});
            const oldID=selectedID;selectedID=id.value.trim();text.value=pretty(next);fieldError="";
            // Keep focused inputs alive while reflecting renames in selectors.
            for(const option of choice.options){if(option.value===oldID)option.value=selectedID;
                const m=next.markers.find(m=>m.marker_id===option.value);if(m)option.textContent=`${m.description||m.marker_id} · ${m.kind==="actor"?"人物":"目标"}`;}
            choice.value=selectedID;
            for(const [index,row]of [...relations.children].entries())for(const [side,dropdown]of [...row.querySelectorAll("select")].entries()){
                const key=side===0?"actor_marker_id":"target_marker_id";
                for(const option of dropdown.options){if(option.value===oldID)option.value=selectedID;
                    const m=next.markers.find(m=>m.marker_id===option.value);if(m)option.textContent=m.description||m.marker_id;}
                dropdown.value=next.relations[index][key]??"";
            }
            draw();
        }catch(error){fieldError=error.message;say(error.message);updateButtons();}
    }
    for(const input of [description,color,id,role]) {
        input.oninput=detailsInput;input.onblur=()=>guard(()=>{flush();});
        input.onkeydown=event=>{if(event.key==="Enter"){event.preventDefault();guard(()=>{flush();refresh();draw();});}};
    }
    function renderRelations(value) {
        relations.replaceChildren();
        value.relations.forEach((relation,index)=>{
            const row=el("div",null,relations);row.className="t8-marker-relation"+(index===activeRelation?" active":"");
            button(`定位关系 ${index+1}`,row,()=>{guard(()=>{flush();activeRelation=index;selectedID=spec().relations[index].actor_marker_id;refresh();draw();});});
            const pair=el("div",null,row);pair.className="t8-marker-pair";
            for(const [key,kind] of [["actor_marker_id","actor"],["target_marker_id","target"]]) {
                const dropdown=el("select",null,pair);dropdown.setAttribute("aria-label",`关系${index+1}${kind==="actor"?"人物":"目标"}`);
                for(const m of value.markers.filter(m=>m.kind===kind)){const option=el("option",m.description||m.marker_id,dropdown);option.value=m.marker_id;}
                if(![...dropdown.options].some(o=>o.value===relation[key])){const missing=el("option",`未找到：${relation[key]??"未选择"}`,dropdown);missing.value=relation[key]??"";}
                dropdown.value=relation[key]??"";
                dropdown.onchange=()=>guard(()=>{flush();const next=spec();next.relations[index][key]=dropdown.value;activeRelation=index;write(next);});
                if(kind==="actor")el("span","→",pair);
            }
            const label=el("label","动作",row),action=el("input",null,label);action.value=relation.action??"";
            action.setAttribute("aria-label",`关系${index+1}动作`);action.placeholder="填写动作，不自动编造";
            action.onfocus=()=>{activeRelation=index;for(const [i,r]of [...relations.children].entries())r.classList.toggle("active",i===index);draw();};
            action.oninput=()=>guard(()=>{const next=spec();next.relations[index].action=action.value;text.value=pretty(next);draw();});
            action.onblur=()=>guard(()=>{flush();});
            button(`删除关系 ${index+1}`,row,()=>guard(()=>{flush();const next=spec();next.relations.splice(index,1);activeRelation=-1;write(next);}));
        });
    }
    function addRelation(actorID,targetID) {
        const next=spec(),chosen=next.markers.find(m=>m.marker_id===selectedID);
        const actor=actorID??(chosen?.kind==="actor"?selectedID:next.markers.find(m=>m.kind==="actor")?.marker_id);
        const target=targetID??(chosen?.kind==="target"?selectedID:next.markers.find(m=>m.kind==="target")?.marker_id);
        if(!actor||!target)throw Error("请先添加人物框和目标框，再建立关系。");
        next.relations.push({actor_marker_id:actor,target_marker_id:target,action:""});
        activeRelation=next.relations.length-1;tool="select";relationActor=null;write(next);
        const row=relations.lastElementChild;row?.scrollIntoView({block:"nearest"});row?.querySelector("input")?.focus();
        say("已添加关系；请填写动作。框、描述和所有关系完整后才能应用。");
    }
    function createMarker(kind) {guard(()=>{
        flush();cancelDrag();const next=addMarker(spec(),kind);view.value="edit";tool="draw";activeRelation=-1;
        write(next.value,next.id);say(`已新增 ${next.id}（建议不同颜色，同色也允许）。请拖框，再填写名称／描述和对应动作。`);
    });}
    function travel(forward) {
        if(drag)cancelDrag();
        history.commit(state());const next=forward?history.redo():history.undo();text.value=next.text;mode.value=next.mode;fieldError="";
        guard(()=>refresh());draw();say(forward?"已重做草稿；节点未更改。":"已撤销草稿；节点未更改。图像选择不在草稿撤销中。");
    }
    function scale() {const r=canvas.getBoundingClientRect();return 1/Math.min(r.width/canvas.width,r.height/canvas.height);}
    function draw() {
        if(disposed)return;ctx.clearRect(0,0,canvas.width,canvas.height);if(raw)ctx.putImageData(raw,0,0);
        updateButtons();
        hint.textContent=mode.value==="provided_marked"?"已有标记图：下方矩形只声明含义，移动／改色不会重画原图。请显式选择自动绘框才会画入输入图。"
            :"自动绘框：实际输入只有按源像素线宽画出的矩形，不含ID、控制点或关系线；框不是生成画面的硬坐标。";
        try {
            const value=spec();
            if(view.value==="actual") {
                if(view.options[1].disabled)throw Error("输入字段由外部连线驱动，无法确定实际图；请查看来源节点或切回编辑叠层。");
                if(raw){const out=renderMarkedRGBA(raw,value,mode.value,Number(widget(node,"line_width")?.value??3));ctx.putImageData(new ImageData(out.data,out.width,out.height),0,0);}
                geometry.textContent="Prepare输出预览 · 无编辑叠层 · 尚未经过下游条件缩放；运行时仍校验RGB绑定。";return;
            }
            const valueScale=scale(),rel=value.relations[activeRelation];
            if(rel){const a=value.markers.find(m=>m.marker_id===rel.actor_marker_id),b=value.markers.find(m=>m.marker_id===rel.target_marker_id);
                if(validBox(a?.xyxy)&&validBox(b?.xyxy)){ctx.save();ctx.strokeStyle="#f4ce91";ctx.lineWidth=2*valueScale;ctx.setLineDash([6*valueScale,4*valueScale]);ctx.beginPath();
                    ctx.moveTo((a.xyxy[0]+a.xyxy[2])/2*canvas.width,(a.xyxy[1]+a.xyxy[3])/2*canvas.height);
                    ctx.lineTo((b.xyxy[0]+b.xyxy[2])/2*canvas.width,(b.xyxy[1]+b.xyxy[3])/2*canvas.height);ctx.stroke();ctx.restore();}}
            for(const m of value.markers){const p=drag?.id===m.marker_id&&drag.live?drag.live:m.xyxy;if(validBox(p))paint(m,p,valueScale,!!drag&&drag.id===m.marker_id,rel);}
            const liveBox=drag?.live??drag?.box;
            const dimensions=validBox(liveBox)?` · ${Math.round((liveBox[2]-liveBox[0])*canvas.width)} × ${Math.round((liveBox[3]-liveBox[1])*canvas.height)} px`:"";
            geometry.textContent=drag?`正在${drag.handle==="move"?"移动":drag.handle==="draw"?"框选":"缩放"} ${drag.id}${dimensions} · 松开确认，Esc取消`
                :raw?`${canvas.width} × ${canvas.height} · ${selectedID||"未选择"} · ${tool==="draw"?"拖动重画当前框":tool==="relation"?relationActor?"再点目标框":"先点人物框":"点选／拖动内部移动／拖边角缩放"}`:"尚无底图。先读取上游或选择与实际输入相同的RGB图。";
        }catch(error){geometry.textContent=error.message;}
    }
    function paint(marker,p,s,live,rel) {
        const [l,t,r,b]=p.map((n,i)=>n*(i%2?canvas.height:canvas.width));
        const focused=marker.marker_id===selectedID||[rel?.actor_marker_id,rel?.target_marker_id,relationActor].includes(marker.marker_id);
        ctx.save();ctx.strokeStyle=COLORS[marker.color?.toLowerCase()]??(/^#[0-9a-f]{6}$/i.test(marker.color??"")?marker.color:"#ffffff");ctx.fillStyle=ctx.strokeStyle;
        ctx.lineWidth=(focused?3:2)*s;if(live){ctx.setLineDash([7*s,4*s]);ctx.globalAlpha=.14;ctx.fillRect(l,t,r-l,b-t);ctx.globalAlpha=1;}
        ctx.strokeRect(l,t,r-l,b-t);ctx.font=`${13*s}px sans-serif`;ctx.fillText(marker.marker_id,l+4*s,t+17*s);
        if(marker.marker_id===selectedID&&tool==="select"&&!drag){ctx.setLineDash([]);for(const [x,y]of Object.values(boxHandles(p)))ctx.fillRect(x*canvas.width-4*s,y*canvas.height-4*s,8*s,8*s);}
        ctx.restore();
    }
    const at=event=>sourcePoint(event.clientX,event.clientY,canvas.getBoundingClientRect(),canvas.width,canvas.height);
    const unit=point=>[point[0]/canvas.width,point[1]/canvas.height];
    function cancelDrag() {if(!drag)return;const pid=drag.pointerId;drag=null;if(canvas.hasPointerCapture?.(pid))canvas.releasePointerCapture(pid);draw();}
    canvas.onpointerdown=event=>{
        if(!raw||loading||view.value!=="edit"||event.button!==0||drag)return;
        guard(()=>{
            const start=at(event);if(!start.inside)return;flush();canvas.focus({preventScroll:true});const value=spec(),p=unit(start.point),s=scale();
            const hit=hitMarker(value.markers,p,selectedID,[7*s/canvas.width,7*s/canvas.height]);
            if(tool==="relation") {
                const m=value.markers.find(m=>m.marker_id===hit?.id);if(!m){say("请点已有框；也可以在右侧下拉框选择关系对象。");return;}
                if(!relationActor){if(m.kind!=="actor"){say("请先点人物框，再点目标框。");return;}relationActor=m.marker_id;selectedID=m.marker_id;refresh();draw();say("已选人物，再点目标框。");}
                else if(m.kind==="target")addRelation(relationActor,m.marker_id);else{relationActor=m.marker_id;draw();}return;
            }
            if(tool!=="draw"&&!hit){say("这里没有框。新增框请点“＋人物框／＋目标框”；不会覆盖当前范围。");return;}
            const marker=value.markers.find(m=>m.marker_id===(tool==="draw"?selectedID:hit.id));if(!marker)return;
            selectedID=marker.marker_id;refresh();event.preventDefault();
            drag={id:selectedID,handle:tool==="draw"?"draw":hit.handle,box:marker.xyxy,start:start.point,
                client:[event.clientX,event.clientY],end:start.point,live:null,pointerId:event.pointerId};
            canvas.setPointerCapture(event.pointerId);draw();
        });
    };
    function dragBox(current,end) {return current.handle==="draw"?normalizedBox(current.start,end,canvas.width,canvas.height)
        :transformBox(current.box,current.handle,unit(current.start),unit(end));}
    canvas.onpointermove=event=>{
        if(!drag){if(raw&&view.value==="edit"){const p=at(event),s=scale();const hit=p.inside?guard(()=>hitMarker(spec().markers,unit(p.point),selectedID,[7*s/canvas.width,7*s/canvas.height])):null;
            canvas.style.cursor=tool==="select"?(hit?.handle==="move"?"move":hit?`${hit.handle}-resize`:"default"):"crosshair";}return;}
        if(event.pointerId!==drag.pointerId)return;event.preventDefault();drag.end=at(event).point;
        if(gestureMoved(drag.client,[event.clientX,event.clientY]))try{drag.live=dragBox(drag,drag.end);}catch{drag.live=null;}
        else drag.live=null;
        draw();
    };
    canvas.onpointerup=event=>{
        if(!drag||event.pointerId!==drag.pointerId)return;const current=drag;
        guard(()=>{if(gestureMoved(current.client,[event.clientX,event.clientY])){
            const box=dragBox(current,at(event).point);if(!validBox(box))throw Error("矩形不能为零面积，请继续调整。");
            const next=spec(),marker=next.markers.find(m=>m.marker_id===current.id);if(!marker)throw Error("当前框已不存在。");
            marker.xyxy=box;cancelDrag();tool="select";write(next,current.id);say("范围已写入草稿；应用后才更新节点。");
        }else cancelDrag();});cancelDrag();
    };
    canvas.onpointercancel=canvas.onlostpointercapture=event=>{if(drag?.pointerId===event.pointerId)cancelDrag();};
    choice.onchange=()=>{const next=choice.value;guard(()=>{flush();cancelDrag();refresh(next);draw();});choice.value=selectedID;};
    mode.onchange=()=>guard(()=>{cancelDrag();history.commit(state());draw();say("输入图模式仅修改了草稿，点击应用后写入节点。");});
    view.onchange=()=>{cancelDrag();draw();};
    // JSON itself retains focus. Refresh other controls while typing, not during
    // blur, which could remove a relation button before its first click lands.
    text.oninput=()=>{cancelDrag();fieldError="";guard(()=>refresh());draw();};
    text.onblur=()=>guard(()=>{flush();});
    dialog.addEventListener("keydown",event=>{
        if(event.key==="Escape"&&drag){event.preventDefault();event.stopPropagation();cancelDrag();return;}
        if(event.key==="Escape"&&tool!=="select"&&!confirm){event.preventDefault();tool="select";relationActor=null;draw();return;}
        if((event.ctrlKey||event.metaKey)&&!event.altKey&&!["INPUT","TEXTAREA","SELECT"].includes(event.target.tagName)&&!event.target.isContentEditable){
            if(event.key.toLowerCase()==="z"||event.key.toLowerCase()==="y"){event.preventDefault();travel(event.key.toLowerCase()==="y"||event.shiftKey);}}
    });
    async function loadImage(url) {
        const epoch=++imageEpoch;loading=true;cancelDrag();updateButtons();load.disabled=true;
        say("正在读取RGB底图并计算SHA绑定；不改接线。局域网HTTP也保留完整绑定。");
        try {
            const next=new Image();next.src=url;await next.decode();if(disposed||epoch!==imageEpoch)return;
            if(next.naturalWidth*next.naturalHeight>4*1024**2)throw Error("底图超过4MP准备预算，请显式缩图后使用。");
            const offscreen=document.createElement("canvas");offscreen.width=next.naturalWidth;offscreen.height=next.naturalHeight;
            const context=offscreen.getContext("2d",{willReadFrequently:true});context.drawImage(next,0,0);
            const pixels=context.getImageData(0,0,offscreen.width,offscreen.height);
            // Backend IMAGE has no alpha: preview its actual RGB, not transparent
            // compositing against the editor background. RGB hash stays exact.
            for(let i=3;i<pixels.data.length;i+=4)pixels.data[i]=255;
            const sha=await rgbSHA(pixels);
            if(disposed||epoch!==imageEpoch)return;
            raw=pixels;sourceSHA=sha;if(!previewBaselineSHA)previewBaselineSHA=sha;canvas.width=raw.width;canvas.height=raw.height;draw();
            say(`底图 ${raw.width}×${raw.height} · RGB ${sha.slice(0,16)}。运行时仍核对实际输入；EXIF／ICC／透明度或中间处理导致不同，请选择实际RGB结果，不要清除绑定。`);
        }catch(error){if(!disposed&&epoch===imageEpoch)say(`读取失败：${error.message}${raw?"；保留上一张有效底图。":""}`);}
        finally{if(!disposed&&epoch===imageEpoch){loading=false;load.disabled=false;updateButtons();}}
    }
    file.onchange=()=>{const selected=file.files?.[0];if(!selected)return;if(ownedURL)URL.revokeObjectURL(ownedURL);
        ownedURL=URL.createObjectURL(selected);void loadImage(ownedURL);};
    function apply(close) {guard(()=>{
        if(loading||!raw)throw Error("请先完成底图读取与RGB绑定。");flush();validateSpec(spec(),mode.value);
        setDraft(node,spec(),sourceSHA,mode.value===widget(node,"mode")?.value?undefined:mode.value);
        appliedSHA=sourceSHA;previewBaselineSHA=appliedSHA;history.accept(state());if(close)cleanup();else say("已应用到节点，仍未运行或自动保存。关闭不会撤回已应用内容。");
    });}
    function requestClose() {
        if(confirm)return;cancelDrag();
        const dirty=history.dirty(state())||!!fieldError||!!(previewBaselineSHA&&sourceSHA&&sourceSHA!==previewBaselineSHA);
        if(!dirty){cleanup();return;}
        confirm=el("dialog",null,dialog);confirm.className="t8-marker-discard";confirm.setAttribute("aria-label","未应用草稿");
        el("h3","有尚未应用的草稿",confirm);el("p","关闭会放弃这次未应用的更改；已经应用到节点的内容不会撤回。",confirm);
        const stay=button("继续编辑",confirm,()=>{confirm.remove();confirm=null;});
        button("放弃草稿并关闭",confirm,()=>cleanup());
        confirm.addEventListener("cancel",event=>{event.preventDefault();confirm.remove();confirm=null;});confirm.showModal();stay.focus();
    }
    function cleanup() {
        disposed=true;imageEpoch++;cancelDrag();if(ownedURL)URL.revokeObjectURL(ownedURL);confirm?.remove();dialog.remove();
        if(node._t8MarkerClose===cleanup){delete node._t8MarkerClose;delete node._t8MarkerFocus;}
    }
    node._t8MarkerClose=cleanup;node._t8MarkerFocus=()=>{dialog.focus();return dialog;};
    dialog.addEventListener("cancel",event=>{event.preventDefault();requestClose();});
    guard(()=>refresh());dialog.showModal();draw();
    return dialog;
}
