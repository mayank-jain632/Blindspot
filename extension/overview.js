'use strict';
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
let existing;

async function workspaceRoot(api) {
  const folders=api.workspace.workspaceFolders||[];
  if(!api.workspace.isTrusted||api.env.remoteName||folders.length!==1||folders[0].uri.scheme!=='file')throw new Error('Open one trusted local workspace.');
  return fs.realpath(folders[0].uri.fsPath);
}
async function safeFile(root,name) {
  if(typeof name!=='string'||!name||path.isAbsolute(name)||name.split('/').includes('..'))throw new Error('Invalid source path');
  const full=path.resolve(root,name);
  if(!full.startsWith(root+path.sep)||await fs.realpath(full)!==full||(await fs.lstat(full)).isSymbolicLink())throw new Error('Source is outside the local workspace');
  return full;
}
async function openOverview(api,connection,context,reconfigure=async()=>connection) {
  const root=await workspaceRoot(api);
  async function request(route) {
    if(await workspaceRoot(api)!==root)throw new Error('Workspace changed; reopen the overview');
    const config=await reconfigure();
    const headers={Authorization:'Bearer '+config.token};
    const health=await fetch(config.endpoint+'/api/health',{headers,signal:AbortSignal.timeout(3000)});
    const status=await health.json();
    if(!health.ok||status.workspace!==root||!status.capabilities?.overview)throw new Error('Restart the receiver for this workspace with SQLite storage');
    const parsed=new URL(route,'http://bridge.invalid');
    if(parsed.origin!=='http://bridge.invalid'||!['/api/overview','/api/current-source','/api/report'].includes(parsed.pathname))throw new Error('Unsupported overview request');
    const response=await fetch(config.endpoint+parsed.pathname+parsed.search,{headers,signal:AbortSignal.timeout(10000)});
    const body=await response.json();
    if(!response.ok)throw new Error(body.error||'Receiver returned '+response.status);
    return body;
  }
  // Pair and validate before creating a panel. Credentials never enter its DOM.
  await request('/api/overview');
  if(existing){existing.reveal();return;}
  const assets=path.join(context.extensionPath,'media/overview');
  const panel=api.window.createWebviewPanel('blindspot.overview','Blindspot Overview',api.ViewColumn.Beside,{enableScripts:true,localResourceRoots:[api.Uri.file(assets)]});
  existing=panel;
  const nonce=crypto.randomBytes(16).toString('hex');
  const html=await fs.readFile(path.join(assets,'index.html'),'utf8');
  const asset=name=>panel.webview.asWebviewUri(api.Uri.file(path.join(assets,name))).toString();
  panel.webview.html=html.replace('<meta charset="utf-8">',`<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${panel.webview.cspSource}; script-src 'nonce-${nonce}'; base-uri 'none'">`).replace('href="/style.css"',`href="${asset('style.css')}"`).replace('<script src="/app.js">',`<script nonce="${nonce}" src="${asset('app.js')}">`);
  const subscription=panel.webview.onDidReceiveMessage(async message=>{
    if(!message||typeof message.id!=='string'||message.id.length>100)return;
    try {
      if(message.type==='request') {
        if(typeof message.route!=='string'||message.route.length>2000)throw new Error('Invalid route');
        const body=await request(message.route);
        await panel.webview.postMessage({id:message.id,body});
      } else if(message.type==='open-source') {
        const overview=await request('/api/overview');
        const file=overview.files.find(f=>f.path===message.path&&!f.current_uncertain);
        if(!file||!Number.isInteger(message.line)||message.line<1||message.line>file.line_count)throw new Error('Refresh and choose a current eligible source line');
        const full=await safeFile(root,file.path);
        const document=await api.workspace.openTextDocument(api.Uri.file(full));
        const editor=await api.window.showTextDocument(document,api.ViewColumn.One);
        const range=new api.Range(message.line-1,0,message.line-1,0);
        editor.selection=new api.Selection(range.start,range.end);editor.revealRange(range);
        await panel.webview.postMessage({id:message.id,body:{opened:true}});
      }
    } catch(error){await panel.webview.postMessage({id:message.id,error:error.message});}
  });
  panel.onDidDispose(()=>{if(existing===panel)existing=null;subscription.dispose();});
  context.subscriptions.push(panel,subscription);
}
module.exports={openOverview,safeFile,workspaceRoot};
