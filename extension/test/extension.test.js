'use strict';
// API wiring check with a fake VS Code host. Actual editor behavior is a manual gate.
const test=require('node:test');
const assert=require('node:assert/strict');
const Module=require('node:module');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {execFileSync}=require('node:child_process');

function deferred() {
  let resolve,reject;
  const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
  return {promise,resolve,reject};
}
async function until(predicate) {
  const deadline=Date.now()+2000;
  while(!predicate()) {
    if(Date.now()>deadline) throw new Error('Timed out waiting for lifecycle transition');
    await new Promise(resolve=>setTimeout(resolve,5));
  }
}
async function withHost(run) {
  const temporary=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-extension-'));
  const base=await fs.realpath(temporary),root=path.join(base,'workspace');
  await fs.mkdir(root);
  const file=path.join(root,'a.py'),connectionFile=path.join(base,'connection.json');
  await fs.writeFile(file,'one\ntwo\nthree');
  execFileSync('git',['init',root],{stdio:'ignore'});
  await fs.writeFile(connectionFile,JSON.stringify({endpoint:'http://127.0.0.1:7777',token:'test-token-'.repeat(4)}));
  const host={root,connectionFile,receiverId:'test-receiver',commands:new Map(),listeners:new Map(),events:[],errors:[],messages:[],disposed:[],logs:[],information:null,request:null};
  const subscription=name=>callback=>{
    host.listeners.set(name,callback);
    return {dispose:()=>{host.disposed.push(name);if(host.listeners.get(name)===callback)host.listeners.delete(name);}};
  };
  const uri={scheme:'file',fsPath:file};let text='one\ntwo\nthree';
  host.document={uri,isDirty:false,version:1,lineCount:3,getText:()=>text};
  const editor={document:host.document,visibleRanges:[{start:{line:0,character:0},end:{line:2,character:0}}]};
  host.edit=value=>{text=value;host.document.version++;host.document.isDirty=true;host.listeners.get('document')?.({document:host.document,contentChanges:[{text:value}]});};
  host.status={show(){},dispose(){}};
  const api={
    StatusBarAlignment:{Left:1},TextEditorSelectionChangeKind:{Keyboard:1,Mouse:2},RelativePattern:class{},
    commands:{registerCommand:(name,fn)=>{host.commands.set(name,fn);return {dispose(){}};}},
    env:{remoteName:undefined,openExternal:async()=>true},Uri:{parse:value=>value},
    workspace:{isTrusted:true,workspaceFolders:[{uri:{scheme:'file',fsPath:root}}],getConfiguration:()=>({get:()=>connectionFile}),
      createFileSystemWatcher:()=>({dispose:()=>host.disposed.push('watcher'),onDidCreate:subscription('create'),onDidChange:subscription('disk'),onDidDelete:subscription('delete')}),onDidChangeTextDocument:subscription('document')},
    window:{activeTextEditor:editor,state:{focused:true},createStatusBarItem:()=>host.status,createOutputChannel:()=>({appendLine:line=>host.logs.push(line),dispose(){}}),
      showInformationMessage:async(...args)=>{host.messages.push(args[0]);return host.information?host.information(...args):args.at(-1);},showErrorMessage:async message=>host.errors.push(message),
      onDidChangeActiveTextEditor:subscription('active'),onDidChangeTextEditorVisibleRanges:subscription('range'),onDidChangeWindowState:subscription('focus'),onDidChangeTextEditorSelection:subscription('selection')}
  };
  host.api=api;
  const originalLoad=Module._load,originalFetch=global.fetch,originalConnection=process.env.BLINDSPOT_CONNECTION_FILE;
  delete process.env.BLINDSPOT_CONNECTION_FILE;
  Module._load=function(name,...args){return name==='vscode'?api:originalLoad.call(this,name,...args);};
  global.fetch=async(url,options)=>{
    const data=options.body?JSON.parse(options.body):null;
    const events=data?.events||[];
    host.events.push(...events);
    if(host.request) {
      for(const event of events.length?events:[null]) {const response=await host.request(url,options,event);if(response)return response;}
    }
    return {ok:true,json:async()=>url.endsWith('/api/health')?{workspace:root,receiver_id:host.receiverId,capabilities:{batch_events:true,heartbeat:true,pane_events:true}}:
      {accepted:true,receiver_id:host.receiverId,received:events.length,appended:events.length,duplicates:0}};
  };
  const context={subscriptions:[]};let extension;
  try {
    delete require.cache[require.resolve('../extension')];extension=require('../extension').activate(context);
    host.command=name=>host.commands.get('blindspot.'+name)();
    await run(host);
  } finally {
    await extension?.stop();for(const item of context.subscriptions)item.dispose();
    Module._load=originalLoad;global.fetch=originalFetch;
    if(originalConnection===undefined)delete process.env.BLINDSPOT_CONNECTION_FILE;else process.env.BLINDSPOT_CONNECTION_FILE=originalConnection;
    await fs.rm(temporary,{recursive:true});
  }
}

test('extension requires Start, records document changes, obeys focus/pause, and tears down listeners',()=>withHost(async h=>{
  assert.equal(h.events.length,0,'Activation must not start recording');
  await h.command('start');assert.equal(h.events[0].kind,'session_start');
  h.edit('changed\ntwo\nthree');h.api.window.state.focused=false;h.listeners.get('focus')();
  await h.command('pause');const count=h.events.length;h.edit('paused\ntwo\nthree');assert.equal(h.events.length,count);
  await h.command('resume');await h.command('stop');
  assert.equal(h.events.at(-1).kind,'session_end');
  assert.ok(h.events.some(e=>e.kind==='snapshot'&&e.payload.dirty));
  assert.ok(h.events.some(e=>e.kind==='interaction'&&e.payload.cause==='unattributed'));
  assert.ok(h.disposed.includes('focus')&&h.disposed.includes('watcher'));assert.deepEqual(h.errors,[]);
  const focusIndex=h.events.findIndex(e=>e.kind==='window_state'&&e.payload.focused===false);
  assert.equal(h.events[focusIndex-1].kind,'visibility');
  assert.equal(h.events[focusIndex-1].monotonic_ms,h.events[focusIndex].monotonic_ms);
}));

test('repeated Stop/Start creates fresh sessions and reuses this workspace consent',()=>withHost(async h=>{
  for(let i=0;i<3;i++) {await h.command('start');h.edit('session-'+i+'\ntwo\nthree');await h.command('stop');assert.match(h.status.text,/off$/);}
  const starts=h.events.filter(e=>e.kind==='session_start');
  assert.equal(starts.length,3);assert.equal(new Set(starts.map(e=>e.session_id)).size,3);
  assert.equal(h.events.filter(e=>e.kind==='session_end').length,3);
  assert.equal(h.messages.filter(m=>m.startsWith('Record eligible')).length,1);
  for(const start of starts) {
    const events=h.events.filter(e=>e.session_id===start.session_id);
    assert.deepEqual(events.map(e=>e.sequence),events.map((_,i)=>i));
    assert.equal(events.at(-1).kind,'session_end');
  }
  assert.deepEqual(h.errors,[]);
}));

test('Stop cancels a pending consent and a late answer cannot resurrect or block it',()=>withHost(async h=>{
  const consent=deferred();let asked=false;
  h.information=message=>{if(message.startsWith('Record eligible')){asked=true;return consent.promise;}};
  const first=h.command('start');
  try {
    await until(()=>asked);await h.command('start');
    assert.ok(h.messages.some(message=>message.includes('starting')));
    await h.command('stop');assert.match(h.status.text,/off$/);
    h.information=null;await h.command('start');
    assert.equal(h.events.filter(e=>e.kind==='session_start').length,1);
    consent.resolve('Start local recording');await first;
    assert.equal(h.events.filter(e=>e.kind==='session_start').length,1);
    assert.match(h.status.text,/recording$/);await h.command('stop');
  } finally {consent.resolve(undefined);await first;}
}));

test('an old stop upload failure cannot stop a newer recording',()=>withHost(async h=>{
  await h.command('start');const firstId=h.events[0].session_id;
  const reply=deferred();let ending=false;
  h.request=async(url,options,event)=>{
    if(event?.session_id===firstId&&event.kind==='session_end') {ending=true;return reply.promise;}
  };
  const stopping=h.command('stop');
  try {
    await until(()=>ending);await h.command('start');assert.match(h.status.text,/recording$/);
    reply.resolve({ok:false,status:400,json:async()=>({error:'old upload failed'})});await stopping;
    assert.match(h.status.text,/recording$/);
    const secondId=h.events.find(e=>e.kind==='session_start'&&e.session_id!==firstId).session_id;
    h.edit('new session still works\ntwo\nthree');await h.command('stop');
    assert.ok(h.events.some(e=>e.session_id===secondId&&e.kind==='interaction'));
    assert.equal(h.events.at(-1).session_id,secondId);assert.equal(h.events.at(-1).kind,'session_end');
  } finally {reply.resolve({ok:false,status:400,json:async()=>({error:'old upload failed'})});await stopping;}
}));

test('recovery refreshes connection credentials, keeps pause, and records a fresh-session gap',()=>withHost(async h=>{
  await h.command('start');const old=h.events[0].session_id;
  h.request=async(url)=>url.endsWith('/api/events/batch')?{ok:false,status:409,json:async()=>({code:'session_unavailable',error:'expired'})}:undefined;
  await h.command('pause');await until(()=>h.status.text.includes('reconnecting'));
  const count=h.events.length;h.edit('offline resulting source\ntwo\nthree');assert.equal(h.events.length,count);
  h.receiverId='new-receiver';
  await fs.writeFile(h.connectionFile,JSON.stringify({endpoint:'http://127.0.0.1:7777',token:'rotated-token-'.repeat(4)}));
  h.request=async(url,options)=>{assert.equal(options.headers.Authorization,'Bearer '+'rotated-token-'.repeat(4));};
  await h.command('reconnect');assert.match(h.status.text,/connected · paused$/);
  const fresh=h.events.filter(e=>e.kind==='session_start').at(-1).session_id;
  assert.notEqual(fresh,old);
  const newEvents=h.events.filter(e=>e.session_id===fresh);
  assert.deepEqual(newEvents.map(e=>e.kind),['session_start','recording_gap','state']);
  assert.equal(newEvents[1].payload.previous_session_id,old);assert.equal(newEvents[1].payload.duration_uncertain,true);
  assert.ok(newEvents[1].payload.unacknowledged_events>0);
  assert.equal(h.messages.filter(m=>m.startsWith('Record eligible')).length,1);
  await h.command('resume');await h.command('stop');
  assert.ok(h.events.some(e=>e.session_id===fresh&&e.kind==='snapshot'&&e.payload.text.startsWith('offline resulting')));
  assert.deepEqual(h.errors,[]);
}));

test('Stop cancels connection retries including an in-flight recovery probe',()=>withHost(async h=>{
  await h.command('start');
  h.request=async(url)=>url.endsWith('/api/events/batch')?{ok:false,status:409,json:async()=>({code:'receiver_changed'})}:undefined;
  await h.command('pause');await until(()=>h.status.text.includes('reconnecting'));
  const probe=deferred();let probing=false;
  h.request=async(url)=>{if(url.endsWith('/api/health')){probing=true;return probe.promise;}};
  const recovery=h.command('reconnect');
  try {
    await until(()=>probing);await h.command('stop');assert.match(h.status.text,/off$/);
    probe.resolve({ok:true,json:async()=>({workspace:h.root,receiver_id:'new',capabilities:{batch_events:true,heartbeat:true,pane_events:true}})});
    await recovery;await h.command('reconnect');
    assert.equal(h.events.filter(e=>e.kind==='session_start').length,1);
    assert.match(h.status.text,/off$/);
  } finally {probe.resolve({ok:false,status:503,json:async()=>({error:'offline'})});await recovery;}
}));

test('automatic recovery refuses a receiver for another workspace',()=>withHost(async h=>{
  await h.command('start');
  h.request=async(url)=>url.endsWith('/api/events/batch')?{ok:false,status:409,json:async()=>({code:'receiver_changed'})}:undefined;
  await h.command('pause');await until(()=>h.status.text.includes('reconnecting'));
  h.request=async(url)=>url.endsWith('/api/health')?{ok:true,json:async()=>({workspace:h.root+'-other',receiver_id:'new',capabilities:{batch_events:true,heartbeat:true,pane_events:true}})}:undefined;
  await h.command('reconnect');assert.match(h.status.text,/off$/);
  assert.equal(h.events.filter(e=>e.kind==='session_start').length,1);
  assert.ok(h.errors.some(e=>e.includes('workspace changed')));
}));

test('a failed active recording automatically resumes collection in a fresh session',()=>withHost(async h=>{
  await h.command('start');const old=h.events[0].session_id;
  h.request=async(url)=>url.endsWith('/api/events/batch')?{ok:false,status:409,json:async()=>({code:'receiver_changed'})}:undefined;
  h.edit('before disconnect\ntwo\nthree');await until(()=>h.status.text.includes('reconnecting'));
  assert.match(h.status.text,/reconnecting · recording$/);
  h.edit('after disconnect\ntwo\nthree');h.receiverId='new';h.request=null;
  await h.command('reconnect');assert.match(h.status.text,/connected · recording$/);
  await h.command('stop');
  const fresh=h.events.filter(e=>e.kind==='session_start').at(-1).session_id;
  assert.notEqual(fresh,old);
  assert.ok(h.events.some(e=>e.session_id===fresh&&e.kind==='recording_gap'));
  assert.ok(h.events.some(e=>e.session_id===fresh&&e.kind==='snapshot'&&e.payload.text.startsWith('after disconnect')));
  assert.ok(h.events.some(e=>e.session_id===fresh&&e.kind==='visibility'));
  assert.deepEqual(h.errors,[]);
}));

test('range and focus callbacks while paused do not read document contents',()=>withHost(async h=>{
  await h.command('start');await h.command('pause');
  const read=h.document.getText;
  h.document.getText=()=>{throw new Error('Paused callback read source');};
  try {
    const editor=h.api.window.activeTextEditor;
    h.listeners.get('range')({textEditor:editor});h.listeners.get('active')();h.listeners.get('focus')();
    assert.match(h.status.text,/paused$/);
  } finally {h.document.getText=read;}
  h.edit('changed while paused\ntwo\nthree');await h.command('resume');await h.command('stop');
  assert.ok(h.events.some(e=>e.kind==='snapshot'&&e.payload.text.startsWith('changed while paused')));
  assert.deepEqual(h.errors,[]);
}));

test('connection picker validates configuration before saving and never starts recording',()=>withHost(async h=>{
  const updates=[];
  h.api.window.showOpenDialog=async()=>[{fsPath:h.connectionFile}];
  h.api.workspace.getConfiguration=()=>({get:()=>h.connectionFile,update:async(...args)=>updates.push(args)});
  await h.command('connect');
  assert.deepEqual(updates,[['connectionFile',h.connectionFile,true]]);
  assert.equal(h.events.length,0);
  await fs.writeFile(h.connectionFile,JSON.stringify({endpoint:'http://remote.example',token:'x'.repeat(40)}));
  await h.command('connect');
  assert.equal(updates.length,1);
  assert.match(h.errors.at(-1),/127.0.0.1/);
}));
