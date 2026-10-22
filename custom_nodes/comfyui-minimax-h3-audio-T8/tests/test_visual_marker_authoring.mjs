import assert from "node:assert/strict";
import test from "node:test";
import {createHash,webcrypto} from "node:crypto";
import {addMarker,connectedFields,portableSHA256,readDraft,rgbSHA,setDraft} from "../web/visual_marker_editor.mjs";
import {DraftHistory,boxHandles,gestureMoved,hitMarker,renderMarkedRGBA,transformBox,validBox} from "../web/visual_marker_authoring.mjs";
import {directSource,imageSource} from "../web/visual_marker_source.mjs";

const spec=()=>({markers:[{marker_id:"A",kind:"actor",role_id:"A",description:"person",color:"cyan",xyxy:[.1,.1,.4,.9]},
    {marker_id:"T",kind:"target",description:"floor",color:"yellow",xyxy:[.7,.7,.9,.9]}],
    relations:[{actor_marker_id:"A",target_marker_id:"T",action:"walk"}]});
const node=()=>({widgets:[{name:"markers_json",value:"old"},{name:"mode",value:"render_rectangles"},
    {name:"expected_source_sha256",value:"b".repeat(64)},{name:"line_width",value:3}],inputs:[]});

for(const field of ["markers_json","mode","expected_source_sha256"])for(const link of [0,99])
    test(`externally driven ${field}/${link} refuses atomically without severing wires`,()=>{
        const n=node();n.inputs=[{name:field,link}];const before=structuredClone(n);
        assert.throws(()=>setDraft(n,spec(),"a".repeat(64),"provided_marked"),/外部连线/);
        assert.deepEqual(n,before);assert(connectedFields(n).includes(field));
    });
test("explicit mode choice only, with externally driven line width still editable",()=>{
    const n=node();n.inputs=[{name:"line_width",link:0}];setDraft(n,spec(),"a".repeat(64));
    assert.equal(n.widgets[1].value,"render_rectangles");setDraft(n,spec(),"a".repeat(64),"provided_marked");
    assert.equal(n.widgets[1].value,"provided_marked");const before=structuredClone(n);
    assert.throws(()=>setDraft(n,spec(),"a".repeat(64),"invalid"));assert.deepEqual(n,before);
});
test("re-check changed ownership at apply time",()=>{
    const n=node();assert.equal(connectedFields(n).length,0);n.inputs.push({name:"mode",link:42});
    assert.throws(()=>setDraft(n,spec(),"a".repeat(64)),/外部/);assert.equal(n.widgets[0].value,"old");
});
test("converted inputs without hidden widgets still report external ownership",()=>{
    const n={widgets:[],inputs:[{name:"mode",link:0}]};
    assert.throws(()=>setDraft(n,spec(),"a".repeat(64)),/外部连线/);assert.deepEqual(n.widgets,[]);
});
for(const length of [0,3,55,56,63,64,65,1000,524355])test(`portable SHA-256 matches native at length ${length}`,async()=>{
    const data=Uint8Array.from({length},(_,i)=>(i*113+19)%256);
    assert.equal(Buffer.from(await portableSHA256(data)).toString("hex"),createHash("sha256").update(data).digest("hex"));
});
test("LAN HTTP without WebCrypto preserves the identical float32 RGB binding",async()=>{
    const descriptor=Object.getOwnPropertyDescriptor(globalThis,"crypto"),pixels={width:2,height:1,data:new Uint8ClampedArray([3,9,128,255,23,11,255,255])};
    try{
        Object.defineProperty(globalThis,"crypto",{configurable:true,value:webcrypto});const expected=await rgbSHA(pixels);
        Object.defineProperty(globalThis,"crypto",{configurable:true,value:undefined});assert.equal(await rgbSHA(pixels),expected);
    }finally{if(descriptor)Object.defineProperty(globalThis,"crypto",descriptor);else delete globalThis.crypto;}
});
test("suggested colors are distinct but same-color inputs remain legal",()=>{
    const next=addMarker(spec(),"actor");assert.notEqual(next.value.markers.at(-1).color,"cyan");
    assert.notEqual(next.value.markers.at(-1).color,"yellow");
});
test("malformed nested JSON objects produce recoverable errors rather than TypeErrors",()=>{
    for(const value of [{markers:[null],relations:[]},{markers:[{kind:"bad",marker_id:"x"}],relations:[]},
        {markers:[],relations:[null]}])assert.throws(()=>readDraft(JSON.stringify(value)),/标记/);
    assert.deepEqual(readDraft('{"markers":[],"relations":[]}'),{markers:[],relations:[]});
});
test("history groups whole drafts including compound deletion, mode and malformed JSON",()=>{
    const first={text:JSON.stringify(spec()),mode:"render_rectangles"},history=new DraftHistory(first);
    assert(!history.commit(first));const edited={text:"invalid {",mode:"provided_marked"};history.commit(edited);
    assert(history.dirty(edited));assert.deepEqual(history.undo(),first);assert.deepEqual(history.redo(),edited);
    history.accept(edited);assert(!history.dirty(edited));history.undo();history.commit({...first,text:"new"});
    assert(!history.canRedo);assert.equal(history.current.text,"new");
});
test("history snapshots cannot be mutated by the caller",()=>{
    const h=new DraftHistory({nested:{v:1}});const read=h.current;read.nested.v=2;assert.equal(h.current.nested.v,1);
});
test("hit testing has eight handles, selected-handle priority, topmost interior and empty space",()=>{
    const markers=spec().markers;assert.equal(Object.keys(boxHandles(markers[0].xyxy)).length,8);
    assert.deepEqual(hitMarker(markers,[.1,.1],"A",[.01,.01]),{id:"A",handle:"nw"});
    assert.deepEqual(hitMarker(markers,[.16,.1],"A",[.01,.01]),{id:"A",handle:"n"});
    assert.deepEqual(hitMarker(markers,[.1,.3],"A",[.01,.01]),{id:"A",handle:"w"});
    assert.deepEqual(hitMarker(markers,[.2,.3],"T",[.01,.01]),{id:"A",handle:"move"});
    markers.push({...markers[0],marker_id:"B"});assert.equal(hitMarker(markers,[.2,.3],"T",[.01,.01]).id,"B");
    assert.equal(hitMarker(markers,[.6,.1],"T",[.01,.01]),null);
});
test("movement clamps to edges without changing size or mutating original geometry",()=>{
    const p=[.1,.1,.4,.9],next=transformBox(p,"move",[.2,.2],[5,-9]);
    assert.deepEqual(p,[.1,.1,.4,.9]);assert.deepEqual(next,[.7,0,1,.8]);
});
test("resize supports corners, edges and reverse dragging; zero area remains invalid",()=>{
    assert.deepEqual(transformBox([.1,.2,.4,.8],"nw",[.1,.2],[.6,.9]),[.4,.8,.6,.8999999999999999]);
    assert.deepEqual(transformBox([.1,.2,.4,.8],"e",[.4,.5],[.6,.5]),[.1,.2,.6,.8]);
    assert(!validBox(transformBox([.1,.2,.4,.8],"w",[.1,.5],[.4,.5])));
    assert(!gestureMoved([0,0],[2,2]));assert(gestureMoved([0,0],[4,0]));
});
test("provided-marked preview is unchanged source with no handles or ID text",()=>{
    const source={width:20,height:10,data:Uint8ClampedArray.from({length:800},(_,i)=>i%256)};
    for(let i=3;i<source.data.length;i+=4)source.data[i]=255;
    const copy=renderMarkedRGBA(source,spec(),"provided_marked",0);
    assert.deepEqual(copy.data,source.data);assert.notEqual(copy.data,source.data);
});
test("RGB input preview is opaque even when the browser decoder supplied alpha",()=>{
    const source={width:1,height:1,data:new Uint8ClampedArray([1,2,3,0])};
    assert.deepEqual([...renderMarkedRGBA(source,spec(),"provided_marked",0).data],[1,2,3,255]);
    assert.deepEqual([...source.data],[1,2,3,0]);
});
test("actual rendered preview uses source-pixel bands and leaves the source untouched",()=>{
    const source={width:100,height:100,data:new Uint8ClampedArray(40000).fill(128)},value=spec();
    value.markers[0].color="#12abef";const out=renderMarkedRGBA(source,value,"render_rectangles",3);
    const pixel=(x,y)=>[...out.data.slice((y*100+x)*4,(y*100+x)*4+3)];
    assert.deepEqual(pixel(10,10),[18,171,239]);assert.deepEqual(pixel(13,13),[128,128,128]);
    assert.deepEqual(pixel(39,40),[18,171,239]);assert.deepEqual(pixel(40,40),[128,128,128]);
    assert(source.data.every(n=>n===128));delete value.markers[0].xyxy;
    assert.throws(()=>renderMarkedRGBA(source,value,"render_rectangles",3),/有效矩形/);
});
test("preview rejects unknown colors and widths rather than inventing runtime output",()=>{
    const source={width:10,height:10,data:new Uint8ClampedArray(400)},value=spec();value.markers[0].color="bogus";
    assert.throws(()=>renderMarkedRGBA(source,value,"render_rectangles",1),/颜色/);
    for(const width of [0,NaN,1.5])assert.throws(()=>renderMarkedRGBA(source,spec(),"render_rectangles",width));
});
function graph(map=false){const nodes=new Map();return {nodes,links:map?new Map():{},getNodeById:id=>nodes.get(id)};}
function connect(g,consumer,name,origin,link=0){consumer.graph=g;origin.graph=g;g.nodes.set(origin.id,origin);
    consumer.inputs??=[];consumer.inputs.push({name,link});const edge={origin_id:origin.id,origin_slot:0};
    if(g.links instanceof Map)g.links.set(link,edge);else g.links[link]=edge;}
const load=()=>({id:7,type:"LoadImage",widgets:[{name:"image",value:"sub\\file.png [input]"}]});
for(const map of [false,true])test(`source resolves own child graph with colliding global IDs (${map?"Map":"object"})`,()=>{
    const child=graph(map),root=graph(),n={};connect(child,n,"image",load());root.nodes.set(7,{id:7,type:"NotTheSource"});
    assert.deepEqual(imageSource(n,root),{filename:"file.png",subfolder:"sub",type:"input"});assert.equal(directSource(n,"image",root).graph,child);
});
test("safe Reroute chain resolves, arbitrary transforms/external filename/cycles do not",()=>{
    const g=graph(),n={},r={id:8,type:"Reroute"};connect(g,n,"image",r);connect(g,r,"",load(),1);
    assert.equal(imageSource(n).filename,"file.png");r.type="ResizeImage";assert.equal(imageSource(n),null);r.type="Reroute";
    g.nodes.get(7).inputs=[{name:"image",link:2}];assert.equal(imageSource(n),null);
    g.links[1]={origin_id:8};assert.equal(imageSource(n),null);
});
test("LoadImage preserves official input/output/temp annotations and filename spaces",()=>{
    const g=graph(),n={},origin=load();connect(g,n,"image",origin);
    for(const type of ["input","output","temp"]){origin.widgets[0].value=`sub/ photo .png [${type}]`;
        assert.deepEqual(imageSource(n),{filename:" photo .png",subfolder:"sub",type});}
});
