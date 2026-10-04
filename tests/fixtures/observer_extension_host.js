'use strict';
// Mock VS Code surfaces; real extension, Git reads, transport, and Python receiver.
const fs=require('node:fs');
const Module=require('node:module');
const path=require('node:path');
const assert=require('node:assert/strict');
const config=JSON.parse(fs.readFileSync(0,'utf8'));
process.env.BLINDSPOT_CONNECTION_FILE=config.connection_file;
const commands=new Map(),listeners=new Map(),errors=[],status={show(){},dispose(){}};
const subscribe=name=>callback=>{
  listeners.set(name,callback);
  return {dispose(){if(listeners.get(name)===callback)listeners.delete(name);}};
};
let text=fs.readFileSync(path.join(config.workspace,'a.py'),'utf8');
const document={uri:{scheme:'file',fsPath:path.join(config.workspace,'a.py')},isDirty:false,version:1,lineCount:3,getText:()=>text};
const editor={document,viewColumn:1,visibleRanges:[{start:{line:0,character:0},end:{line:2,character:1}}]};
class TabInputText{constructor(uri){this.uri=uri;}}
const editors=[editor];
if(fs.existsSync(path.join(config.workspace,'b.py'))){
  const source=fs.readFileSync(path.join(config.workspace,'b.py'),'utf8');
  editors.push({viewColumn:2,document:{uri:{scheme:'file',fsPath:path.join(config.workspace,'b.py')},isDirty:false,version:1,lineCount:source.split('\n').length,getText:()=>source},visibleRanges:editor.visibleRanges});
}
const api={TabInputText,
  StatusBarAlignment:{Left:1},TextEditorSelectionChangeKind:{Keyboard:1,Mouse:2},RelativePattern:class{},
  commands:{registerCommand:(name,handler)=>{commands.set(name,handler);return {dispose(){}};}},
  env:{remoteName:undefined,openExternal:async()=>true},Uri:{parse:value=>value},
  workspace:{isTrusted:true,textDocuments:editors.map(e=>e.document),workspaceFolders:[{uri:{scheme:'file',fsPath:config.workspace}}],
    createFileSystemWatcher:()=>({dispose(){},onDidCreate:subscribe('create'),onDidChange:subscribe('disk'),onDidDelete:subscribe('delete')}),
    onDidChangeTextDocument:subscribe('document')},
  window:{activeTextEditor:editor,visibleTextEditors:editors,tabGroups:{all:editors.map(e=>{const tab={input:new TabInputText(e.document.uri)};return {viewColumn:e.viewColumn,activeTab:tab,tabs:[tab]};})},state:{focused:true},createStatusBarItem:()=>status,createOutputChannel:()=>({appendLine(){},dispose(){}}),
    showInformationMessage:async(...args)=>args.at(-1),showErrorMessage:async message=>errors.push(message),
    onDidChangeActiveTextEditor:subscribe('active'),onDidChangeTextEditorVisibleRanges:subscribe('range'),onDidChangeWindowState:subscribe('focus'),onDidChangeTextEditorSelection:subscribe('selection')}
};
const originalLoad=Module._load;
Module._load=function(name,...args){return name==='vscode'?api:originalLoad.call(this,name,...args);};
const context={subscriptions:[]};
const extension=require('../../extension/extension').activate(context);
const command=name=>commands.get('blindspot.'+name)();
async function until(predicate,timeout=15000) {
  const deadline=Date.now()+timeout;
  while(!predicate()) {
    if(Date.now()>deadline)throw new Error('Timed out: '+status.text);
    await new Promise(resolve=>setTimeout(resolve,20));
  }
}
(async()=>{
  try {
    if(config.mode==='recovery') {
      await command('start');await command('pause');
      await until(()=>status.text.includes('connected')&&status.text.endsWith('paused'));
      process.stdout.write(JSON.stringify({stage:'ready'})+'\n');
      await until(()=>status.text.includes('reconnecting'));
      process.stdout.write(JSON.stringify({stage:'disconnected'})+'\n');
      // The parent leaves the server unavailable through the first automatic probe.
      await until(()=>status.text.includes('connected')&&status.text.endsWith('paused'));
      const connection=JSON.parse(fs.readFileSync(config.connection_file,'utf8'));
      const getReport=async()=>{
        const response=await fetch(connection.endpoint+'/api/report',{headers:{Authorization:'Bearer '+connection.token}});
        assert.equal(response.ok,true);return response.json();
      };
      const recovered=await getReport();
      assert.equal(recovered.sessions.length,2);assert.equal(recovered.recording_gaps.length,1);
      assert.equal(recovered.sessions[0].connection_state,'interrupted');
      assert.equal(recovered.sessions[1].status,'paused');
      const id=recovered.sessions[1].session_id;
      assert.equal(recovered.events.filter(e=>e.session_id===id&&['snapshot','interaction','visibility'].includes(e.kind)).length,0);
      await command('resume');await new Promise(resolve=>setTimeout(resolve,30));await command('stop');
      assert.deepEqual(errors,[]);
      const report=await getReport();
      assert.ok(report.events.some(e=>e.session_id===id&&e.kind==='visibility'));
      assert.equal(report.sessions[1].status,'ended');
      process.stdout.write(JSON.stringify({stage:'done',sessions:2,gaps:1})+'\n');return;
    }
    for(let i=0;i<3;i++) {
      await command('start');assert.match(status.text,/recording$/);
      await new Promise(resolve=>setTimeout(resolve,20));
      text='session-'+i+'\ntwo\nthree';document.version++;document.isDirty=true;
      listeners.get('document')({document,contentChanges:[{text}]});
      await command('pause');assert.match(status.text,/paused$/);
      await command('resume');assert.match(status.text,/recording$/);
      await command('stop');assert.match(status.text,/off$/);
    }
    assert.deepEqual(errors,[]);
    const response=await fetch(config.endpoint+'/api/report',{headers:{Authorization:'Bearer '+config.token}});
    assert.equal(response.ok,true);
    const report=await response.json();
    assert.equal(report.sessions.length,3);assert.equal(report.event_counts.session_end,3);
    assert.ok(report.sessions.every(session=>session.status==='ended'));
    process.stdout.write(JSON.stringify({sessions:3,events:report.events.length}));
  } finally {
    await extension.stop();for(const item of context.subscriptions)item.dispose();Module._load=originalLoad;
  }
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
