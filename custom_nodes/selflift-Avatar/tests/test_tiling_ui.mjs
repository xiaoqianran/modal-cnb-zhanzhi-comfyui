// No npm dependencies. Exercise extension callbacks with a minimal ComfyUI/DOM stub.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
let extension;
const events = new Map();
let node;
globalThis.testApp = {registerExtension: (e) => {extension=e;},graph:{getNodeById:(id)=>String(id)==='78'?node:null}};
globalThis.testApi = {addEventListener:(name,fn)=>events.set(name,fn)};
globalThis.document = {createElement:()=>({style:{},setAttribute(){},value:'',readOnly:false})};
const source = (await fs.readFile(new URL('../web/tiling_controls.js',import.meta.url),'utf8'))
  .replace('import { app } from "../../scripts/app.js";', 'const app=globalThis.testApp;')
  .replace('import { api } from "../../scripts/api.js";', 'const api=globalThis.testApi;');
await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
class Node {
    constructor(){this.size=[300,300];this.widgets=[
        {name:'highres_tiling',value:true}, {name:'tiling_mode',value:'auto'},
        {name:'tiling_tiles',value:2}, {name:'tiling_axis',value:'auto'}];}
    addDOMWidget(name,type,el,options){this.widgets.push({name,type,options});return this.widgets.at(-1);}
    computeSize(){return [300,300];}
    setDirtyCanvas(){}
}
await extension.beforeRegisterNodeDef(Node,{name:'SelfLiftAvatarH3Sampler'});
extension.setup();node=new Node();node.onNodeCreated();
assert.equal(node.selfliftTilingPanel.readOnly,true);
assert.equal(node.widgets.at(-1).options.serialize,false);
assert.match(node.selfliftTilingPanel.value,/Not run/);
node.widgets[1].value='manual';node.widgets[1].callback();
assert.match(node.selfliftTilingPanel.value,/manual/);
assert.match(node.selfliftTilingPanel.value,/Settings changed/);
events.get('selflift-avatar-tiling')({detail:{node_id:'78',text:'RUNNING | axis=W | Effective: 4'}});
assert.match(node.selfliftTilingPanel.value,/RUNNING.*Effective: 4/);
node.onExecuted({selflift_tiling:['DONE | Effective: 4']});
assert.match(node.selfliftTilingPanel.value,/DONE/);
node.widgets[3].value='height';node.widgets[3].callback();
assert.match(node.selfliftTilingPanel.value,/axis=height/);
assert.doesNotMatch(node.selfliftTilingPanel.value,/DONE/);
node.onConfigure();
assert.match(node.selfliftTilingPanel.value,/Settings changed/);
events.get('selflift-avatar-tiling')({detail:{node_id:'79',text:'WRONG NODE'}});
assert.doesNotMatch(node.selfliftTilingPanel.value,/WRONG NODE/);
events.get('selflift-avatar-tiling')({detail:{node_id:'78',text:'FAILED'}});
assert.match(node.selfliftTilingPanel.value,/FAILED/);
console.log('Frontend callback checks passed: read-only/nonserialized panel, controls, live event, completion, stale reset, configure, node routing, failure.');

// Automatic planning must show the real count above the configuration summary.
node.widgets[1].value='auto';node.widgets[1].callback();
assert.match(node.selfliftTilingPanel.value.split('\n')[0], /pending/);
events.get('selflift-avatar-tiling')({detail:{node_id:'78',text:'RUNNING',plan:{tiles:3,mode:'auto',axis:4}}});
assert.match(node.selfliftTilingPanel.value.split('\n')[0], /Actual tiles: 3/);
assert.equal(node.widgets[1].value,'auto');
assert.equal(node.widgets[2].value,2); // Never overwrite the manual dropdown.
node.onExecuted({selflift_tiling:['DONE'],selflift_tiling_plan:[{tiles:3,mode:'auto',axis:4}]});
assert.match(node.selfliftTilingPanel.value.split('\n')[0], /Actual tiles: 3/);
events.get('selflift-avatar-tiling')({detail:{node_id:'78',text:'Preparing',plan:null}});
assert.match(node.selfliftTilingPanel.value.split('\n')[0], /pending/);
// Accommodate graphs keyed by numeric IDs.
globalThis.testApp.graph.getNodeById=(id)=>id===78?node:null;
events.get('selflift-avatar-tiling')({detail:{node_id:'78',text:'RUNNING',plan:{tiles:1}}});
assert.match(node.selfliftTilingPanel.value.split('\n')[0], /Actual tiles: 1.*no split/);
node.onExecuted({selflift_tiling:['DONE\nRequested / 请求: auto | Effective / 实际: 4']});
assert.match(node.selfliftTilingPanel.value.split('\n')[0], /Actual tiles: 4/);
node.widgets[3].callback();
assert.match(node.selfliftTilingPanel.value.split('\n')[0], /pending/);
node.widgets[0].value=false;node.widgets[0].callback();
assert.match(node.selfliftTilingPanel.value.split('\n')[0], /OFF/);
console.log('Automatic actual-count tests passed (live, complete, reset, cached text, numeric node ID, single tile).');
