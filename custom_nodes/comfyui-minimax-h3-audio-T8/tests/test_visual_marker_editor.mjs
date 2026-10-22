import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { addMarker, editMarker, normalizedBox, readDraft, removeMarker, rgbSHA, setDraft,
    sourcePoint, validateSpec } from "../web/visual_marker_editor.mjs";

const spec = () => ({markers:[
    {marker_id:"A",kind:"actor",role_id:"A",color:"cyan",description:"person",xyxy:[.1,.1,.4,.9]},
    {marker_id:"T",kind:"target",color:"cyan",description:"floor",xyxy:[.7,.6,.9,.9]}],
    relations:[{actor_marker_id:"A",target_marker_id:"T",action:"walk once"}]});

test("reverse drag uses actual source dimensions and bounded nonzero box",()=>{
    assert.deepEqual(normalizedBox([80,45],[20,10],100,50),[.2,.2,.8,.9]);
    assert.deepEqual(normalizedBox([-10,-10],[120,80],100,50),[0,0,1,1]);
    assert.throws(()=>normalizedBox([10,10],[10,20],100,50));
    assert.throws(()=>normalizedBox([NaN,10],[20,20],100,50));
    assert.throws(()=>normalizedBox([10],[20,20],100,50));
});
test("same color/shared target legal and handdrawing coordinates optional",()=>{
    const value=spec(); value.markers.push({...value.markers[0],marker_id:"B",role_id:"B"});
    value.relations.push({...value.relations[0],actor_marker_id:"B"});
    assert.equal(validateSpec(value),value);
    for (const marker of value.markers) delete marker.xyxy;
    assert.equal(validateSpec(value,"provided_marked"),value);
    assert.throws(()=>validateSpec(value));
    const malformed=spec(); malformed.markers[0].marker_id=1;
    assert.throws(()=>validateSpec(malformed));
});
test("only real serialized widgets changed, no queue or mode mutation",()=>{
    let dirties=0;
    const node={widgets:[{name:"mode",value:"render_rectangles"},{name:"markers_json",value:"old"},
        {name:"expected_source_sha256",value:""}],setDirtyCanvas:()=>{dirties++;},
        queuePrompt:()=>{throw Error("must not queue");}};
    const sha="a".repeat(64);
    const result=setDraft(node,spec(),sha);
    assert.deepEqual(JSON.parse(result),spec()); assert.equal(node.widgets[2].value,sha);
    assert.equal(node.widgets[0].value,"render_rectangles"); assert.equal(dirties,1);
    const reopened=JSON.parse(JSON.stringify(node.widgets));
    assert.equal(reopened[1].value,result); assert.equal(reopened[2].value,sha);
    assert.throws(()=>setDraft(node,spec(),"bad"));
});
test("browser preview SHA matches actual float32 RGB tensor byte order",async()=>{
    const pixels={width:2,height:1,data:new Uint8ClampedArray([0,223,255,255,63,128,192,255])};
    const rgb=new Float32Array([0,223/255,1,63/255,128/255,192/255]);
    const expected=createHash("sha256").update(new Uint8Array(rgb.buffer)).digest("hex");
    assert.equal(await rgbSHA(pixels),expected);
});

test("new actor/target IDs and actor roles are collision-free without inventing actions",()=>{
    const before=spec(), frozen=structuredClone(before);
    before.markers[0].marker_id="actor_A"; before.markers[1].marker_id="target_A";
    before.markers.push({...before.markers[0],marker_id:"actor_B",role_id:"B"});
    const actor=addMarker(before,"actor");
    assert.equal(actor.id,"actor_C"); assert.equal(actor.value.markers.at(-1).role_id,"C");
    assert.equal(actor.value.markers.at(-1).description,"");
    assert.equal(actor.value.markers.at(-1).xyxy,undefined);
    assert.deepEqual(actor.value.relations,before.relations);
    const target=addMarker(actor.value,"target");
    assert.equal(target.id,"target_B"); assert.equal(target.value.markers.at(-1).role_id,undefined);
    assert.equal(before.markers.length,3); assert.equal(frozen.markers.length,2);
    assert.throws(()=>addMarker(before,"unknown"));
});
test("ID edit updates every relation, preserves geometry and supports shared targets",()=>{
    const before=spec(); before.relations.push({...before.relations[0],action:"stop"});
    const fields={...before.markers[1],marker_id:"floor_2",color:"#ab12ff",description:"new floor"};
    const next=editMarker(before,"T",fields);
    assert(next.relations.every(r=>r.target_marker_id==="floor_2"));
    assert.deepEqual(next.markers[1].xyxy,before.markers[1].xyxy);
    assert.equal(before.markers[1].marker_id,"T"); assert.equal(before.relations[0].target_marker_id,"T");
    assert.throws(()=>editMarker(before,"T",{...fields,marker_id:"A"}),/已存在/);
    assert.throws(()=>editMarker(before,"T",{...fields,marker_id:"bad id"}));
    assert.throws(()=>editMarker(before,"A",{...before.markers[0],role_id:""}));
    assert.throws(()=>editMarker(before,"T",{...fields,color:"invalid"}));
    assert.equal(validateSpec(next),next);
});
test("deleting a draft marker removes only its dependent relations",()=>{
    const before=spec(); before.markers.push({...before.markers[0],marker_id:"B",role_id:"B"});
    before.relations.push({...before.relations[0],actor_marker_id:"B"});
    const next=removeMarker(before,"A");
    assert.deepEqual(next.markers.map(m=>m.marker_id),["T","B"]);
    assert.equal(next.relations.length,1); assert.equal(next.relations[0].actor_marker_id,"B");
    assert.equal(before.markers.length,3); assert.equal(before.relations.length,2);
    assert.equal(validateSpec(next),next);
    assert.throws(()=>readDraft('{"markers":null}'));
});
test("object-fit letterboxing is excluded from pointer geometry on wide and tall previews",()=>{
    const rect={left:10,top:20,width:400,height:300};
    assert.deepEqual(sourcePoint(10,70,rect,800,400),{point:[0,0],inside:true});
    assert.deepEqual(sourcePoint(410,270,rect,800,400),{point:[800,400],inside:true});
    assert.equal(sourcePoint(200,30,rect,800,400).inside,false);
    assert.deepEqual(sourcePoint(135,20,rect,400,800),{point:[0,0],inside:true});
    assert.equal(sourcePoint(20,100,rect,400,800).inside,false);
    assert.throws(()=>sourcePoint(0,0,{left:0,top:0,width:0,height:0},400,800));
    assert.throws(()=>sourcePoint(0,0,rect,0,800));
});
