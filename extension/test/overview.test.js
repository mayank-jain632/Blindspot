'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {safeFile,workspaceRoot,openOverview}=require('../overview');
test('overview navigation rejects traversal and symlink escape, accepts a local source',async()=>{
  const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-overview-'));
  try{
    const root=await fs.realpath(tmp);await fs.writeFile(path.join(root,'a.py'),'source');
    await fs.symlink(path.join(root,'a.py'),path.join(root,'link.py'));
    assert.equal(await safeFile(root,'a.py'),path.join(root,'a.py'));
    await assert.rejects(safeFile(root,'../a.py'));
    await assert.rejects(safeFile(root,'link.py'));
    await assert.rejects(workspaceRoot({workspace:{isTrusted:false},env:{}}));
  }finally{await fs.rm(tmp,{recursive:true});}
});
test('webview uses shared assets, keeps token out of HTML, and restricts the request bridge',async()=>{
  const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-panel-'));const original=global.fetch;
  try{
    const root=await fs.realpath(tmp),messages=[];let listener,dispose;
    const panel={webview:{cspSource:'vscode-resource:',asWebviewUri:uri=>({toString:()=>uri.fsPath}),postMessage:async m=>messages.push(m),onDidReceiveMessage:fn=>{listener=fn;return {dispose(){}};}},onDidDispose:fn=>{dispose=fn;},dispose(){dispose?.();}};
    const api={workspace:{isTrusted:true,workspaceFolders:[{uri:{scheme:'file',fsPath:root}}]},env:{},ViewColumn:{Beside:2},Uri:{file:fsPath=>({fsPath})},window:{createWebviewPanel:()=>panel}};
    global.fetch=async url=>({ok:true,json:async()=>url.endsWith('/api/health')?{workspace:root,capabilities:{overview:true}}:{files:[]}});
    const context={extensionPath:path.resolve(__dirname,'..'),subscriptions:[]};
    await openOverview(api,{endpoint:'http://127.0.0.1:7777',token:'never-put-me-in-html'},context);
    assert.ok(panel.webview.html.includes('Content-Security-Policy'));
    assert.ok(!panel.webview.html.includes('never-put-me-in-html'));
    await listener({id:'1',type:'request',route:'http://remote.example/api/report'});
    assert.match(messages.at(-1).error,/Unsupported/);
    await listener({id:'2',type:'open-source',path:'../secret',line:1});
    assert.match(messages.at(-1).error,/eligible/);panel.dispose();
  }finally{global.fetch=original;await fs.rm(tmp,{recursive:true});}
});
