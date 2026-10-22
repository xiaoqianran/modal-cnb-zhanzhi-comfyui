import { COLORS } from "./visual_marker_editor.mjs";

// Draft history deliberately includes invalid JSON so Undo can recover an edit.
// No graph, model, large bitmap or source identity is stored in this history.
const key=s=>JSON.stringify(s);
export class DraftHistory {
    constructor(state) {this.states=[structuredClone(state)];this.index=0;this.baseline=key(state);}
    get current() {return structuredClone(this.states[this.index]);}
    get canUndo() {return this.index>0;}
    get canRedo() {return this.index<this.states.length-1;}
    commit(state) {
        if (key(state)===key(this.current)) return false;
        this.states.splice(this.index+1);this.states.push(structuredClone(state));this.index++;return true;
    }
    undo() {if(this.canUndo)this.index--;return this.current;}
    redo() {if(this.canRedo)this.index++;return this.current;}
    accept(state) {this.baseline=key(state);}
    dirty(state) {return key(state)!==this.baseline;}
}

export const validBox=p=>Array.isArray(p)&&p.length===4&&p.every(Number.isFinite)&&
    0<=p[0]&&p[0]<p[2]&&p[2]<=1&&0<=p[1]&&p[1]<p[3]&&p[3]<=1;
const clamp=n=>Math.max(0,Math.min(1,n));
export function boxHandles(p) {
    const [l,t,r,b]=p,x=(l+r)/2,y=(t+b)/2;
    return {nw:[l,t],n:[x,t],ne:[r,t],e:[r,y],se:[r,b],s:[x,b],sw:[l,b],w:[l,y]};
}
export function hitMarker(markers,point,selectedID,slop) {
    const selected=markers.find(m=>m.marker_id===selectedID);
    if (validBox(selected?.xyxy)) {
        for (const [handle,p] of Object.entries(boxHandles(selected.xyxy)))
            if(Math.abs(point[0]-p[0])<=slop[0]&&Math.abs(point[1]-p[1])<=slop[1])
                return {id:selectedID,handle};
        const [l,t,r,b]=selected.xyxy;
        if(point[0]>=l&&point[0]<=r){if(Math.abs(point[1]-t)<=slop[1])return {id:selectedID,handle:"n"};
            if(Math.abs(point[1]-b)<=slop[1])return {id:selectedID,handle:"s"};}
        if(point[1]>=t&&point[1]<=b){if(Math.abs(point[0]-l)<=slop[0])return {id:selectedID,handle:"w"};
            if(Math.abs(point[0]-r)<=slop[0])return {id:selectedID,handle:"e"};}
    }
    const inside=m=>validBox(m.xyxy)&&point[0]>=m.xyxy[0]&&point[0]<=m.xyxy[2]&&
        point[1]>=m.xyxy[1]&&point[1]<=m.xyxy[3];
    // Topmost box wins; selecting via the list exposes an obscured box's handles.
    const found=[...markers].reverse().find(inside);
    return found?{id:found.marker_id,handle:"move"}:null;
}
export function transformBox(box,handle,start,end) {
    const p=[...box],dx=end[0]-start[0],dy=end[1]-start[1];
    if(handle==="move") {
        const x=Math.max(-p[0],Math.min(1-p[2],dx)),y=Math.max(-p[1],Math.min(1-p[3],dy));
        return [p[0]+x,p[1]+y,p[2]+x,p[3]+y];
    }
    if(!/^(n|s|e|w|nw|ne|sw|se)$/.test(handle))throw Error("未知缩放手柄。");
    if(handle.includes("w"))p[0]=clamp(p[0]+dx);
    if(handle.includes("e"))p[2]=clamp(p[2]+dx);
    if(handle.includes("n"))p[1]=clamp(p[1]+dy);
    if(handle.includes("s"))p[3]=clamp(p[3]+dy);
    return [Math.min(p[0],p[2]),Math.min(p[1],p[3]),Math.max(p[0],p[2]),Math.max(p[1],p[3])];
}
export function gestureMoved(start,end,threshold=4) {
    return Math.hypot(end[0]-start[0],end[1]-start[1])>=threshold;
}

// Pixel-equivalent to Prepare's rectangle bands, BEFORE downstream resizing.
// Editor-only ID text, arrows, handles and translucent fills never go here.
export function renderMarkedRGBA(source,spec,mode,lineWidth) {
    const {width,height}=source, data=new Uint8ClampedArray(source.data);
    // IMAGE is RGB, not composited RGBA. Display the RGB values we hash/use.
    for(let i=3;i<data.length;i+=4)data[i]=255;
    if(mode==="provided_marked")return {width,height,data};
    if(mode!=="render_rectangles")throw Error("未知准备模式。");
    if(!Number.isInteger(lineWidth)||lineWidth<1)throw Error("实际输入预览需要节点的有效line_width值。");
    for(const marker of spec.markers) {
        if(!validBox(marker.xyxy))throw Error(`${marker.marker_id} 尚无有效矩形，不能预览实际输入。`);
        const hex=COLORS[marker.color?.toLowerCase()]??marker.color;
        if(!/^#[0-9a-f]{6}$/i.test(hex??""))throw Error(`${marker.marker_id} 颜色无效。`);
        const rgb=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
        const p=marker.xyxy,[l,t,r,b]=[Math.floor(p[0]*width),Math.floor(p[1]*height),
            Math.min(width,Math.ceil(p[2]*width)),Math.min(height,Math.ceil(p[3]*height))];
        const stroke=Math.min(lineWidth,r-l,b-t);
        const band=(x0,y0,x1,y1)=>{for(let y=y0;y<y1;y++)for(let x=x0;x<x1;x++){
            const i=(y*width+x)*4;data[i]=rgb[0];data[i+1]=rgb[1];data[i+2]=rgb[2];}};
        band(l,t,r,Math.min(t+stroke,b));band(l,Math.max(b-stroke,t),r,b);
        band(l,t,Math.min(l+stroke,r),b);band(Math.max(r-stroke,l),t,r,b);
    }
    return {width,height,data};
}
