'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

test('inspector repairs a rotated cookie and preserves stale status through filtering',async()=>{
  const element=()=>({children:[],value:'',textContent:'',append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;}});
  const elements=new Map(),calls=[];
  const report={workspace:'test',totals:{},files:[],timeline:[],scope:'test',inventory_diagnostics:[],health:{sessions:[],storage:{events:0},ingestion_metrics:{},recording_gaps:[],latest_connection_diagnostics:[]},limits:[],receiver:{status:'available'}};
  let fail=false,reauthenticate=true;
  const context=vm.createContext({
    document:{getElementById:id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);},createElement:element},
    Option:function(text,value){this.text=text;this.value=value;},AbortSignal,Blob,URL,
    setInterval(){},fetch:async route=>{
      calls.push(route);
      if(fail)throw new Error('offline');
      if(route==='/'){reauthenticate=false;return {ok:true};}
      if(reauthenticate)return {ok:false,status:401};
      return {ok:true,json:async()=>report};
    }
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../../blindspot/observer/web/app.js'),'utf8'),context);
  // Allow the initial asynchronous refresh (including pairing) to complete.
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(calls,['/api/overview?dwell_ms=1000','/','/api/overview?dwell_ms=1000']);
  assert.equal(elements.get('download').disabled,false);
  fail=true;assert.equal(await vm.runInContext('refresh()',context),false);
  assert.equal(elements.get('download').disabled,true);
  const stale=elements.get('status').textContent;
  elements.get('filter').oninput();assert.equal(elements.get('status').textContent,stale);
  assert.match(stale,/stale/);
  fail=false;reauthenticate=true;assert.equal(await vm.runInContext('refresh()',context),true);
  assert.equal(elements.get('download').disabled,false);assert.match(elements.get('status').textContent,/Receiver connected/);
  report.receiver.status='storage_failed';assert.equal(await vm.runInContext('refresh()',context),false);
  assert.equal(elements.get('download').disabled,true);assert.match(elements.get('status').textContent,/Storage failed/);
});

test('source is rendered as text and a changed current hash invalidates an open inspection',async()=>{
  const element=()=>({children:[],value:'',textContent:'',append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;}});
  const elements=new Map();
  const file={path:'a.py',content_hash:'old-hash',origin:'disk',current_uncertain:false,line_count:1,dwell_lines:1,brief_lines:0,unknown_lines:0,dwell_ranges:[[1,1]],brief_ranges:[],mapped_source_hashes:[],interaction_events:0,review_reason:'reported'};
  const report={workspace:'local',totals:{},files:[file],timeline:[],scope:'test',inventory_diagnostics:[],health:{sessions:[],storage:{events:1},ingestion_metrics:{},recording_gaps:[],latest_connection_diagnostics:[]},limits:[],receiver:{status:'available'}};
  const context=vm.createContext({document:{getElementById:id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);},createElement:element},Option:function(){},AbortSignal,Blob,URL,setInterval(){},fetch:async route=>({ok:true,json:async()=>route.startsWith('/api/current-source')?{text:'<script>attack()</script>',origin:'disk'}:report})});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../../blindspot/observer/web/app.js'),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  await elements.get('files').children[0].onclick();
  assert.match(elements.get('source').children[0].textContent,/<script>attack/);
  assert.equal(elements.get('source').children[0].innerHTML,undefined);
  report.files=[{...file,content_hash:'new-hash'}];
  await vm.runInContext('refresh()',context);
  assert.equal(elements.get('source').children.length,0);
  assert.match(elements.get('ranges').textContent,/changed/);
});
