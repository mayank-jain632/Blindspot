'use strict';
const crypto = require('node:crypto');
const {workspaceRoot, safeFile} = require('./overview');
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function sidebarHtml(data, error, cspNonce) {
  const files = data?.files || [];
  const known = data?.has_observations && data.totals.line_count > 0;
  const missing = files.filter(f => !f.current_uncertain).reduce((n,f) => n + f.unknown_lines, 0);
  const recording = data?.health.sessions.some(s => s.connection_state === 'connected' && s.status === 'recording');
  const changesKnown = files.some(f => Number.isFinite(f.changed_unseen_lines));
  const changed = files.reduce((n,f) => n + (f.changed_unseen_lines || 0), 0);
  const pct = known ? (100 * missing / data.totals.line_count).toFixed(1) + '%' : '—';
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${cspNonce}'; script-src 'nonce-${cspNonce}'; base-uri 'none'"><meta name="viewport" content="width=device-width, initial-scale=1"><style nonce="${cspNonce}">
  body{padding:12px;font:var(--vscode-font-size) var(--vscode-font-family);color:var(--vscode-foreground);background:var(--vscode-sideBar-background)}h1{font-size:36px;margin:10px 0;font-family:var(--vscode-editor-font-family)}h2{font-size:13px;margin:24px 0 10px}p{line-height:1.6;color:var(--vscode-descriptionForeground)}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px 0;border-block:1px solid var(--vscode-panel-border)}.metrics strong{display:block;font:20px var(--vscode-editor-font-family)}button{min-height:36px;cursor:pointer;color:var(--vscode-button-foreground);background:var(--vscode-button-background);border:0;padding:8px 10px}.controls{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0}.file{display:block;text-align:left;width:100%;background:transparent;color:var(--vscode-foreground);padding:10px 0;border-bottom:1px solid var(--vscode-panel-border)}.file span{display:flex;justify-content:space-between;gap:8px}.path{overflow-wrap:anywhere}progress{display:block;width:100%;height:4px;margin-top:8px;accent-color:var(--vscode-charts-orange)}small{color:var(--vscode-descriptionForeground)}.error{color:var(--vscode-errorForeground)}
  </style></head><body><small>${recording ? 'Recording' : 'Not recording'}</small>${error ? `<p class="error">${escape(error)}</p>` : ''}
  <h1>${pct}</h1><p>${known ? `${missing} of ${data.totals.line_count} lines not seen` : 'Start recording to see coverage.'}</p>
  ${data ? `<div class="metrics"><div><strong>${files.length}</strong><small>Files tracked</small></div><div><strong>${changesKnown ? changed : '—'}</strong><small>Changed lines unseen</small></div></div>` : ''}
  <div class="controls"><button data-action="start">Start</button><button data-action="pause">Pause</button><button data-action="resume">Resume</button><button data-action="stop">Stop</button></div>
  <div class="controls"><button data-action="refresh">Refresh</button><button data-action="dashboard">Full dashboard</button></div>
  ${files.some(f => f.flagged) ? '<h2>Files with gaps</h2><small>Select a file to open it in the editor.</small>' : ''}
  ${files.filter(f => f.flagged).slice(0,8).map(f => `<button class="file" data-path="${escape(f.path)}"><span><span class="path">${escape(f.path)}</span><small>${f.current_uncertain ? 'Unknown' : `${f.unknown_lines} unseen`}</small></span>${!f.current_uncertain ? `<progress max="100" value="${Math.max(0, Math.min(100, 100 * f.reported_lines / (f.line_count || 1)))}" aria-label="Lines seen"></progress>` : ''}</button>`).join('')}
  ${data && !files.some(f => f.flagged) ? '<p>No files currently flagged.</p>' : ''}
  <script nonce="${cspNonce}">const vscode=acquireVsCodeApi();document.addEventListener('click',event=>{const button=event.target.closest('button');if(button)vscode.postMessage(button.dataset.path?{type:'file',path:button.dataset.path}:{type:'action',action:button.dataset.action});});</script></body></html>`;
}
function createSidebar(api, context, getConnection) {
  return {resolveWebviewView(view) {
    view.webview.options = {enableScripts:true};
    let disposed=false, busy=false, data=null, root=null;
    async function refresh() {
      if (disposed || busy || !view.visible) return;
      busy=true;
      try {
        const workspace=await workspaceRoot(api), config=await getConnection();
        const headers={Authorization:'Bearer '+config.token};
        const health=await fetch(config.endpoint+'/api/health',{headers,signal:AbortSignal.timeout(3000)});
        const status=await health.json();
        if(!health.ok || status.workspace!==workspace)throw new Error('Start the receiver for this workspace.');
        const response=await fetch(config.endpoint+'/api/dashboard',{headers,signal:AbortSignal.timeout(10000)});
        const result=await response.json();
        if(!response.ok || result.workspace!==workspace || await workspaceRoot(api)!==workspace)throw new Error('Reconnect the receiver for this workspace.');
        data=result; root=workspace;
        if(!disposed)view.webview.html=sidebarHtml(data,null,crypto.randomBytes(16).toString('hex'));
      } catch(error) { data=null; root=null; if(!disposed)view.webview.html=sidebarHtml(null,error.message,crypto.randomBytes(16).toString('hex')); }
      finally { busy=false; }
    }
    const messages=view.webview.onDidReceiveMessage(async message=>{
      try {
        if(message?.type==='action') {
          if(message.action==='refresh')return refresh();
          if(message.action==='dashboard')return api.commands.executeCommand('blindspot.open');
          if(['start','pause','resume','stop'].includes(message.action)) {await api.commands.executeCommand('blindspot.'+message.action);await refresh();}
        } else if(message?.type==='file') {
          if(!data || await workspaceRoot(api)!==root || !data.files.some(f=>f.path===message.path&&!f.current_uncertain))throw new Error('Refresh and choose a current file.');
          const full=await safeFile(root,message.path);
          await api.window.showTextDocument(await api.workspace.openTextDocument(api.Uri.file(full)));
        }
      } catch(error) { api.window.showErrorMessage('Blindspot: '+error.message); }
    });
    view.webview.html=sidebarHtml(null,null,crypto.randomBytes(16).toString('hex'));
    const timer=setInterval(refresh,10000);
    const visibility=view.onDidChangeVisibility(refresh);
    view.onDidDispose(()=>{disposed=true;clearInterval(timer);messages.dispose();visibility.dispose();});
    context.subscriptions.push({dispose(){disposed=true;clearInterval(timer);messages.dispose();visibility.dispose();}});
    void refresh();
  }};
}
module.exports={createSidebar,sidebarHtml};
