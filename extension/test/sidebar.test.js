'use strict';
const test=require('node:test'), assert=require('node:assert/strict');
const {sidebarHtml,createSidebar}=require('../sidebar');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
test('sidebar escapes source paths, has a restrictive CSP, and does not display unsupported counts',()=>{
  const html=sidebarHtml({has_observations:true,totals:{line_count:10},health:{sessions:[]},files:[{path:'<img src=x onerror=evil()>',current_uncertain:false,unknown_lines:5,reported_lines:5,line_count:10,flagged:true}]},null,'nonce');
  assert.ok(html.includes('50%')); assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes('<img')); assert.ok(html.includes("default-src 'none'"));
  assert.ok(html.includes('Coverage at a glance'));
  assert.ok(html.includes('color-mix'));
  assert.ok(!html.includes('style="')); assert.ok(html.includes('progress'));
});
test('paused sidebar offers resume and excludes zero-gap files from its gap list',()=>{
  const html=sidebarHtml({has_observations:true,totals:{line_count:10,reported_lines:10},health:{sessions:[{connection_state:'connected',status:'paused'}]},files:[{path:'seen.py',current_uncertain:false,unknown_lines:0,reported_lines:10,line_count:10,flagged:true,review:{tested:true}}]},null,'nonce');
  assert.ok(html.includes('data-action="resume"'));assert.ok(!html.includes('data-action="pause"'));
  assert.ok(!html.includes('<h2>Files with gaps</h2>'));assert.ok(html.includes('No visibility gaps recorded.'));
});
test('sidebar validates workspace, keeps credentials out of HTML and restricts commands',async()=>{
  const temp=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-sidebar-')), original=global.fetch;
  let listener, disposed;const called=[], subscriptions=[];
  try {
    const root=await fs.realpath(temp);
    const api={workspace:{isTrusted:true,workspaceFolders:[{uri:{scheme:'file',fsPath:root}}]},env:{},commands:{executeCommand:async c=>called.push(c)},window:{showErrorMessage:()=>{}}};
    const view={visible:true,webview:{onDidReceiveMessage:fn=>{listener=fn;return {dispose(){}};}},onDidChangeVisibility:()=>({dispose(){}}),onDidDispose:fn=>{disposed=fn;}};
    global.fetch=async url=>({ok:true,json:async()=>url.endsWith('/api/health')?{workspace:root}:{workspace:root,has_observations:false,totals:{line_count:0},health:{sessions:[]},files:[]}});
    createSidebar(api,{subscriptions},async()=>({endpoint:'http://127.0.0.1:7777',token:'PRIVATE_TOKEN'})).resolveWebviewView(view);
    await new Promise(resolve=>setTimeout(resolve,30));
    assert.ok(!view.webview.html.includes('PRIVATE_TOKEN'));
    await listener({type:'action',action:'arbitrary.command'}); assert.deepEqual(called,[]);
    await listener({type:'action',action:'dashboard'});assert.deepEqual(called,['blindspot.open']);
    disposed();
  } finally {for(const s of subscriptions)s.dispose();global.fetch=original;await fs.rm(temp,{recursive:true});}
});
