'use strict';
const vscode=require('vscode');
const fs=require('node:fs/promises');
const path=require('node:path');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const {performance}=require('node:perf_hooks');
const {Collector,MAX_TEXT}=require('./core');
const {Transport,ReceiverError,readConnection}=require('./transport');
const {visibleInputs,openTabs}=require('./surfaces');
const exec=promisify(execFile);
const SOURCE=/\.(py|js|jsx|ts|tsx|mjs|cjs|java|c|h|cpp|hpp|cc|cs|go|rs|rb|php|swift|kt|kts|scala|sh|bash|zsh|sql|html|css|scss|svelte|vue|json|toml|ya?ml|md)$/i;
const EXCLUDED=/(^|\/)(\.git|\.claude|\.blindspot|\.venv|venv|node_modules|vendor|dist|build|__pycache__)(\/|$)|(^|\/)\.env($|\.)|(^|\/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)|\.min\.(js|css)$/;
function eligible(name) { return !EXCLUDED.test(name) && (SOURCE.test(name) || /(^|\/)(Dockerfile|Makefile)$/.test(name)); }
let shutdown=async()=>{};

function activate(context) {
  // One object owns every asynchronous operation for a recording attempt.
  // Stop detaches it immediately; stale continuations cannot mutate its successor.
  let current=null;
  let visibilityExcluded=false;
  const diagnosticHistory=[];
  const consentedWorkspaces=new Set();
  const status=vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left,10);
  status.command='blindspot.controls';
  status.tooltip='Opt-in local collector pilot';
  status.show();
  context.subscriptions.push(status);
  const output=vscode.window.createOutputChannel('Blindspot Observer');
  context.subscriptions.push(output);
  const live=run=>current===run&&!run.stopped;
  const recording=run=>live(run)&&run.collector?.mode==='recording';
  function update() {
    const label=!current?'off':current.phase==='reconnecting'?'reconnecting · '+current.desiredMode:current.collector?(current.connectionState||'connecting')+' · '+current.collector.mode:'starting';
    status.text='$(eye) Blindspot: '+label+(current&&visibilityExcluded?' · visibility excluded':'');
    status.tooltip=current?'Workspace: '+(current.root||'selecting')+'\nConnection: '+(current.connectionState||current.phase)+'\nStop cancels recording and reconnection.':'Opt-in local collector pilot';
  }
  update();

  function detach(run) {
    if(current===run)current=null;
    run.stopped=true;
    clearTimeout(run.retryTimer);
    for(const resource of run.resources.splice(0)) {
      try { resource.dispose(); }
      catch(error) { output.appendLine('Listener cleanup: '+error.message); }
    }
    update();
  }
  function newRun(root=null,desiredMode='recording',gap=null) {
    return {stopped:false,root,expectedRoot:root,desiredMode,gap,phase:'starting',connectionState:'connecting',allowed:new Set(),resources:[],collector:null,transport:null,documentMeta:new Map(),lastContext:null,resuming:false,retryDelay:2000,retryTimer:null,retryBusy:false,lastLoopLagMs:0};
  }
  function fail(run,error,transport=run.transport) {
    output.appendLine((live(run)?'Recording gap: ':'Previous recording upload: ')+error.message);
    if(!live(run)||transport!==run.transport)return;
    const previous=run.collector;
    if(previous&&error.recoverable!==false) {
      const gap={previous_session_id:previous.session,reason:error.code||'connection_lost',last_acknowledged_at:transport.lastAcknowledgedAt,
        detected_at:new Date().toISOString(),unacknowledged_events:transport.unacknowledgedEvents,duration_uncertain:true,
        receiver_diagnostics:error.diagnostics||{},client_diagnostics:transport.diagnostics(),loop_lag_ms:run.lastLoopLagMs};
      diagnosticHistory.push(gap);if(diagnosticHistory.length>20)diagnosticHistory.shift();
      const recovery=newRun(run.root,run.desiredMode,gap);
      detach(run);previous.stop();
      recovery.phase='reconnecting';recovery.connectionState='disconnected';current=recovery;update();
      scheduleRecovery(recovery);return;
    }
    detach(run);
    void vscode.window.showErrorMessage('Blindspot stopped recording: '+error.message+'. Check the receiver, then Start Recording for a new session.');
  }
  async function config() {
    return readConnection(process.env.BLINDSPOT_CONNECTION_FILE||vscode.workspace.getConfiguration('blindspot').get('connectionFile'));
  }
  function scheduleRecovery(run) {
    if(!live(run))return;
    clearTimeout(run.retryTimer);
    run.retryTimer=setTimeout(()=>void recover(run),run.retryDelay);
    run.retryDelay=Math.min(run.retryDelay*2,8000);
  }
  async function recover(run) {
    if(!live(run)||run.retryBusy)return;
    clearTimeout(run.retryTimer);run.retryBusy=true;
    try {
      const connection=await config();
      if(!live(run))return;
      const probe=new Transport(connection,()=>{}),health=await probe.health();
      if(!live(run))return;
      if(health.workspace!==run.root)throw new ReceiverError('Receiver workspace changed; automatic recovery stopped.','workspace_changed',false,false);
      const next=newRun(run.root,run.desiredMode,{...run.gap,recovered_at:new Date().toISOString()});
      detach(run);current=next;update();await connect(next,{connection,health});
    } catch(error) {
      if(!live(run))return;
      if(error.recoverable===false||error instanceof SyntaxError||error instanceof TypeError)fail(run,error);
      else {output.appendLine('Reconnect pending: '+error.message);scheduleRecovery(run);}
    } finally {run.retryBusy=false;}
  }
  async function inventory(run) {
    const {stdout}=await exec('git',['-C',run.root,'ls-files','-z','--cached','--others','--exclude-standard'],{
      encoding:'utf8',maxBuffer:2*1024*1024,env:{...process.env,GIT_OPTIONAL_LOCKS:'0'}
    });
    if(!live(run))return [];
    const names=[...new Set(stdout.split('\0').filter(n=>n&&eligible(n)))];
    const regular=await Promise.all(names.slice(0,500).map(async name=>{
      const full=path.join(run.root,name);
      try {
        const stat=await fs.lstat(full);
        return stat.isFile()&&!stat.isSymbolicLink()&&stat.size<=MAX_TEXT&&await fs.realpath(full)===full?name:null;
      } catch { return null; }
    }));
    if(!live(run))return [];
    run.allowed=new Set(regular.filter(Boolean));
    if(recording(run))run.collector.event('diagnostic',{
      reason:'inventory_scope',eligible:names.length,captured_limit:500,
      excluded_policy:'source extensions; no generated/vendor/locks/env/symlink/binary; max256KiB/file',truncated:names.length>500
    });
    return [...run.allowed];
  }
  function relative(run,uri) {
    if(!run.root||uri.scheme!=='file')return null;
    const name=path.relative(run.root,uri.fsPath).split(path.sep).join('/');
    return name&&!name.startsWith('../')&&!path.isAbsolute(name)&&run.allowed.has(name)?name:null;
  }
  async function disk(run,name) {
    try {
      const full=path.join(run.root,name),stat=await fs.lstat(full);
      if(!stat.isFile()||stat.isSymbolicLink()||stat.size>MAX_TEXT||await fs.realpath(full)!==full)return;
      const bytes=await fs.readFile(full),text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);
      if(recording(run))run.collector.snapshot(name,text,'disk');
    } catch(error) {
      if(live(run)&&error.code!=='ENOENT')output.appendLine('Skipped '+name+': '+error.message);
    }
  }
  function view(run,clock=performance.now()) {
    if(!live(run)||!run.collector)return;
    if(!recording(run)||!vscode.window.state.focused||visibilityExcluded){run.collector.setViews([],clock);return;}
    const inputs=visibleInputs(vscode,uri=>relative(run,uri));
    run.collector.setViews(inputs,clock);
    for(const input of inputs)documentState(run,input.path,input.dirty,input.documentVersion,clock,true,run.collector.views.get(input.paneId)?.content_hash||null);
  }
  function documentState(run,name,dirty,version,clock=performance.now(),isOpen=true,capturedHash=undefined) {
    const content_hash=capturedHash===undefined?run.collector.current.get(name):capturedHash;
    const state={path:name,is_open:isOpen,dirty:!!dirty,document_version:version??null,supported:!isOpen||!!content_hash,content_hash:isOpen?(content_hash||null):null};
    const encoded=JSON.stringify(state);
    if(run.documentMeta.get(name)!==encoded){run.collector.event('document_state',state,clock);run.documentMeta.set(name,encoded);}
  }
  function contextState(run) {
    if(!recording(run))return;
    const context={open_tabs:openTabs(vscode,uri=>relative(run,uri)),visible_panes:(vscode.window.visibleTextEditors||[]).length,visibility_excluded:visibilityExcluded};
    const encoded=JSON.stringify(context);
    if(encoded!==run.lastContext){run.collector.event('workspace_context',context);run.lastContext=encoded;}
  }
  async function baseline(run) {
    for(const name of run.allowed) {
      if(!recording(run))return;
      await disk(run,name);
      if(run.transport.queueBytes>2*1024*1024||run.transport.queue.length>=32)await run.transport.drain();
    }
    if(!recording(run))return;
    const documents=vscode.workspace.textDocuments;
    if(documents) {
      const names=new Set();
      for(const doc of documents) {
        const name=relative(run,doc.uri);if(!name)continue;names.add(name);
        const captured=run.collector.snapshot(name,doc.getText(),'document',doc.isDirty,doc.version);
        documentState(run,name,doc.isDirty,doc.version,performance.now(),true,captured);
        if(run.transport.queueBytes>2*1024*1024)await run.transport.drain();
        if(!recording(run))return;
      }
      for(const name of run.documentMeta.keys())if(!names.has(name))documentState(run,name,false,null,performance.now(),false);
    }
    contextState(run);
  }
  function watch(run) {
    const watcher=vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(run.root,'**/*'));
    async function changed(kind,uri) {
      if(!recording(run))return;
      try {
        await inventory(run);
        if(!recording(run))return;
        const name=path.relative(run.root,uri.fsPath).split(path.sep).join('/');
        if(!eligible(name)||name.startsWith('../'))return;
        run.collector.event('file_event',{path:name,operation:kind,cause:'unattributed-filesystem-event'});
        if(kind!=='delete'&&run.allowed.has(name))await disk(run,name);
        view(run);
      } catch(error) { fail(run,error); }
    }
    function windowState() {
      const clock=performance.now();
      view(run,clock);
      if(recording(run))run.collector.event('window_state',{
        focused:vscode.window.state.focused,focus_scope:'window',editor_focus:'unverified'
      },clock);
    }
    run.windowState=windowState;
    run.resources.push(
      watcher,
      watcher.onDidCreate(uri=>void changed('create',uri)),
      watcher.onDidChange(uri=>void changed('change',uri)),
      watcher.onDidDelete(uri=>void changed('delete',uri)),
      vscode.window.onDidChangeActiveTextEditor(()=>{view(run);contextState(run);}),
      vscode.window.onDidChangeTextEditorVisibleRanges(e=>{if((vscode.window.visibleTextEditors||[vscode.window.activeTextEditor]).includes(e.textEditor))view(run);}),
      vscode.window.onDidChangeWindowState(windowState),
      vscode.workspace.onDidChangeTextDocument(e=>{
        if(!recording(run)||!e.contentChanges.length)return;
        const name=relative(run,e.document.uri);
        if(!name)return;
        if((vscode.window.visibleTextEditors||[vscode.window.activeTextEditor]).some(editor=>editor?.document===e.document))view(run);
        else {const captured=run.collector.snapshot(name,e.document.getText(),'document',e.document.isDirty,e.document.version);documentState(run,name,e.document.isDirty,e.document.version,performance.now(),true,captured);}
        run.collector.interaction({path:name,kind:'document_change',cause:'unattributed',change_count:e.contentChanges.length});
      }),
      vscode.window.onDidChangeTextEditorSelection(e=>{
        if(!recording(run))return;
        const name=relative(run,e.textEditor.document.uri);
        if(name)run.collector.interaction({
          path:name,kind:'selection',
          cause:e.kind===vscode.TextEditorSelectionChangeKind.Keyboard?'keyboard-event':e.kind===vscode.TextEditorSelectionChangeKind.Mouse?'mouse-event':'command-or-unknown'
        });
      })
    );
    if(vscode.window.onDidChangeVisibleTextEditors)run.resources.push(vscode.window.onDidChangeVisibleTextEditors(()=>{view(run);contextState(run);}));
    for(const event of ['onDidChangeTabs','onDidChangeTabGroups'])if(vscode.window.tabGroups?.[event])run.resources.push(vscode.window.tabGroups[event](()=>{view(run);contextState(run);}));
    if(vscode.workspace.onDidCloseTextDocument)run.resources.push(vscode.workspace.onDidCloseTextDocument(doc=>{if(recording(run)){const name=relative(run,doc.uri);if(name)documentState(run,name,false,doc.version,performance.now(),false);}}));
    if(vscode.workspace.onDidOpenTextDocument)run.resources.push(vscode.workspace.onDidOpenTextDocument(doc=>{if(recording(run)){const name=relative(run,doc.uri);if(name){const captured=run.collector.snapshot(name,doc.getText(),'document',doc.isDirty,doc.version);documentState(run,name,doc.isDirty,doc.version,performance.now(),true,captured);}}}));
    if(vscode.workspace.onDidSaveTextDocument)run.resources.push(vscode.workspace.onDidSaveTextDocument(doc=>{if(recording(run)){const name=relative(run,doc.uri);if(name){const captured=run.collector.snapshot(name,doc.getText(),'document',doc.isDirty,doc.version);documentState(run,name,doc.isDirty,doc.version,performance.now(),true,captured);}}}));
  }
  async function start() {
    if(current) {
      void vscode.window.showInformationMessage(current.phase==='reconnecting'?'Blindspot is reconnecting. Stop Recording cancels retries.':current.collector?'Blindspot is already '+current.collector.mode+'. Stop Recording to start a new session.':'Blindspot is starting. Finish the opt-in prompt or Stop Recording to cancel.');
      return;
    }
    const run=newRun();current=run;update();await connect(run);
  }
  async function connect(run,preflight=null) {
    try {
      if(!vscode.workspace.isTrusted||vscode.env.remoteName)throw new Error('This pilot requires a trusted local workspace.');
      const folders=(vscode.workspace.workspaceFolders||[]).filter(f=>f.uri.scheme==='file');
      if(folders.length!==1)throw new Error('Open one local Git workspace in the Development Host.');
      run.root=await fs.realpath(folders[0].uri.fsPath);
      if(!live(run))return;
      if(run.expectedRoot&&run.root!==run.expectedRoot)throw new ReceiverError('VS Code workspace changed; recording stopped.','workspace_changed',false,false);
      const connection=preflight?.connection||await config();
      if(!live(run))return;
      const transport=new Transport(connection,error=>fail(run,error,transport),fetch,{
        receiverId:preflight?.health.receiver_id,
        onStatus:state=>{if(live(run)&&run.transport===transport){run.connectionState=state;update();}}
      });
      run.transport=transport;
      const health=preflight?.health||await transport.health();
      if(!live(run))return;
      if(health.workspace!==run.root)throw new ReceiverError('Receiver is scoped to '+health.workspace+'; open that exact workspace.','workspace_changed',false,false);
      if(!health.capabilities?.pane_events)throw new ReceiverError('Restart the Python receiver to enable SQLite and multi-pane recording.','unsupported_receiver',false,false);
      await inventory(run);
      if(!live(run))return;
      if(!consentedWorkspaces.has(run.root)) {
        const consent=await vscode.window.showInformationMessage(
          'Record eligible source snapshots and reported editor ranges in a focused VS Code window locally? Keyboard focus, reading, and authorship are unverified. Source stays in the receiver state directory.',
          {modal:true},'Start local recording'
        );
        if(!live(run))return;
        if(consent!=='Start local recording') { detach(run);return; }
        consentedWorkspaces.add(run.root);
      }
      run.collector=new Collector(run.root,event=>transport.enqueue(event),()=>performance.now());
      if(run.gap)run.collector.event('recording_gap',run.gap);
      if(run.desiredMode==='paused')run.collector.pause();
      if(visibilityExcluded)run.collector.setExcluded(true);
      update();
      await transport.drain();
      if(!live(run))return;
      // Watch before baseline reads. Each callback remains bound to this run.
      watch(run);
      await baseline(run);
      if(!live(run))return;
      run.windowState();
      const timer=setInterval(()=>{if(recording(run))run.collector.tick();},1000);
      let heartbeatBusy=false;
      let expectedHeartbeat=performance.now()+2000,diagnosticTicks=0;
      const heartbeat=setInterval(async()=>{
        if(!live(run)||heartbeatBusy)return;
        run.lastLoopLagMs=Math.max(0,performance.now()-expectedHeartbeat);expectedHeartbeat=performance.now()+2000;
        if(++diagnosticTicks%8===0)run.collector.event('diagnostic',{reason:'connection_health',loop_lag_ms:run.lastLoopLagMs,...transport.diagnostics()});
        heartbeatBusy=true;
        try {await transport.heartbeat(run.collector.session,run.root);}
        finally {heartbeatBusy=false;}
      },2000);
      run.resources.push({dispose:()=>clearInterval(timer)},{dispose:()=>clearInterval(heartbeat)});
      output.appendLine('Recording '+run.root+'; session '+run.collector.session+'.');
    } catch(error) {
      if(live(run))fail(run,error);
    }
  }
  async function stop() {
    const run=current;
    if(!run)return;
    // Includes pending health/config/consent. No await may keep startup reserved.
    detach(run);
    run.collector?.stop();
    output.appendLine(run.collector?'Stopped session '+run.collector.session+'.':'Cancelled pending recording start/reconnection.');
    await run.transport?.drain();
  }
  async function resume() {
    const run=current;
    if(!run) {
      void vscode.window.showInformationMessage('Blindspot is stopped. Use Start Recording for a new session.');
      return;
    }
    run.desiredMode='recording';
    if(run.phase==='reconnecting'){update();return;}
    if(run.collector?.mode!=='paused'||run.resuming)return;
    run.resuming=true;
    try {
      await inventory(run);
      if(!live(run))return;
      run.collector.resume();update();
      await baseline(run);
      if(live(run))run.windowState();
    } catch(error) { fail(run,error); }
    finally { run.resuming=false; }
  }
  const commands={
    start,stop,resume,
    pause:()=>{if(current)current.desiredMode='paused';current?.collector?.pause();update();},
    reconnect:async()=>{if(current?.phase==='reconnecting')await recover(current);},
    visibility:()=>{visibilityExcluded=!visibilityExcluded;current?.collector?.setExcluded(visibilityExcluded);if(current){view(current);contextState(current);}update();},
    diagnostics:()=>{output.appendLine(JSON.stringify({state:status.text,loop_lag_ms:current?.lastLoopLagMs||0,transport:current?.transport?.diagnostics()||null,recent_gaps:diagnosticHistory},null,2));output.show?.();},
    overview:async()=>{
      try {
        const connection=await config();
        const {openOverview}=require('./overview');
        await openOverview(vscode,connection,context,config);
      } catch(error) {void vscode.window.showErrorMessage('Blindspot overview: '+error.message);}
    },
    open:async()=>{
      try { const connection=await config();await vscode.env.openExternal(vscode.Uri.parse(connection.endpoint)); }
      catch(error) { void vscode.window.showErrorMessage(error.message); }
    },
    marker:async()=>{
      const run=current;
      if(!run?.collector)return;
      const label=await vscode.window.showInputBox({prompt:'Short pilot case label (metadata only)',placeHolder:'case-01 baseline'});
      if(label&&live(run))run.collector.marker(label);
    },
    controls:async()=>{
      const choices=current?(current.phase==='reconnecting'?['Reconnect Now',current.desiredMode==='paused'?'Resume':'Pause','Stop','Open Local Inspector']:current.collector?[current.collector.mode==='paused'?'Resume':'Pause','Stop','Open Local Inspector','Add Pilot Marker']:['Stop','Open Local Inspector']):['Start','Open Local Inspector'];
      choices.push('Show Codebase Overview','Show Recording Diagnostics','Toggle Visibility Exclusion');
      const selected=await vscode.window.showQuickPick(choices,{title:'Blindspot recording controls'});
      const mapping={'Start':'start','Pause':'pause','Resume':'resume','Stop':'stop','Reconnect Now':'reconnect','Open Local Inspector':'open','Add Pilot Marker':'marker','Show Codebase Overview':'overview','Show Recording Diagnostics':'diagnostics','Toggle Visibility Exclusion':'visibility'};
      if(selected)await commands[mapping[selected]]();
    }
  };
  for(const [name,handler] of Object.entries(commands))context.subscriptions.push(vscode.commands.registerCommand('blindspot.'+name,handler));
  context.subscriptions.push({dispose:()=>{void stop();}});
  if(vscode.window.registerWebviewViewProvider)context.subscriptions.push(vscode.window.registerWebviewViewProvider('blindspot.dashboard',require('./sidebar').createSidebar(vscode,context,config)));
  shutdown=stop;
  return {stop};
}
async function deactivate() { await shutdown(); }
module.exports={activate,deactivate,eligible};
