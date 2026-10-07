'use strict';
const crypto = require('node:crypto');
const path = require('node:path');
const {workspaceRoot, safeFile} = require('./overview');
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function sidebarHtml(data, error, cspNonce, assets = {}) {
  const files = data?.files || [];
  const known = data?.has_observations && data.totals.line_count > 0;
  const missing = files.filter(f => !f.current_uncertain).reduce((n,f) => n + f.unknown_lines, 0);
  const recording = data?.health.sessions.some(s => s.connection_state === 'connected' && s.status === 'recording');
  const paused = data?.health.sessions.some(s => s.connection_state === 'connected' && s.status === 'paused');
  const changesKnown = files.some(f => Number.isFinite(f.changed_unseen_lines));
  const changed = files.reduce((n,f) => n + (f.changed_unseen_lines || 0), 0);
  const pct = known ? new Intl.NumberFormat('en-US',{maximumFractionDigits:1}).format(missing ? Math.max(0.1,100 * missing / data.totals.line_count) : 0) + '%' : '—';
  const gaps = files.filter(f => f.current_uncertain || f.unknown_lines > 0);
  const fonts = [['mono','IBM Plex Mono'],['body','EB Garamond'],['display','Cormorant Garamond']].filter(([id])=>assets[id]).map(([id,name])=>`@font-face{font-family:'${name}';src:url('${assets[id]}') format('woff2');font-weight:400;font-display:swap}`).join('');
  const ratio = f => Math.max(0,Math.min(1,f.reported_lines / (f.line_count || 1)));
  const fill = f => f.current_uncertain || !data?.has_observations ? 'var(--unknown)' : ratio(f) === 1 ? 'var(--blue)' : `color-mix(in srgb,var(--red) ${100*(1-ratio(f))}%,var(--yellow))`;
  const meterFill = data ? fill({reported_lines:data.totals.reported_lines,line_count:data.totals.line_count}) : 'var(--unknown)';
  const fills = files.map((f,i)=>`.coverage-${i}{--fill:${fill(f)}}`).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; font-src ${assets.cspSource || "'none'"}; style-src 'nonce-${cspNonce}'; script-src 'nonce-${cspNonce}'; base-uri 'none'"><meta name="viewport" content="width=device-width, initial-scale=1"><style nonce="${cspNonce}">
  ${fonts}
  :root{--ground:#000000;--panel:#0F1215;--inset:#0A0C0E;--control:#1C2127;--border:#242A31;--text:#EFE9E1;--dim:#959DA6;--label:#8A929B;--accent:#F5A93C;--sun:#FF8A2B;--corona:#FFD27A;--red:#EF5350;--yellow:#F4D35E;--blue:#72ACE0;--unknown:#626975;--ink:#111317;--mono:'IBM Plex Mono',var(--vscode-editor-font-family,monospace);--body:'EB Garamond',serif;--display:'Cormorant Garamond',serif;color-scheme:dark}
  *{box-sizing:border-box}body{margin:0;padding:16px;color:var(--text);background:var(--ground);font:16px/1.5 var(--body)}h1,h2,p{margin:0}.brand{display:flex;align-items:center;gap:8px;font:24px var(--display)}.sun{width:17px;height:17px;border-radius:50%;border:3px solid var(--accent);box-shadow:0 0 8px color-mix(in srgb,var(--sun) 35%,transparent)}.status{margin-left:auto;font:11px var(--mono);color:var(--dim)}.eyebrow{display:block;font:11px var(--mono);text-transform:uppercase;letter-spacing:.07em;color:var(--label);margin-bottom:8px}.hero{margin:24px 0 16px}.hero h1{font:48px/1.15 var(--mono);letter-spacing:-.04em}.hero p{font:12px/1.8 var(--mono);color:var(--dim);margin-top:10px}.meter{--fill:${meterFill};height:5px;display:flex;background:var(--border);margin-top:14px}.meter progress{margin:0;height:5px;flex:1}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:16px;background:var(--panel);border:1px solid var(--border)}.metrics strong{display:block;font:22px var(--mono);margin-bottom:6px}small{font:11px/1.5 var(--mono);color:var(--dim)}button{min-height:44px;cursor:pointer;color:var(--text);background:var(--control);border:1px solid var(--border);border-radius:3px;padding:8px 10px;font:12px var(--mono)}button:hover{border-color:var(--label)}button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}button:disabled{cursor:default;opacity:.65}.primary{border-color:var(--accent)}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.controls .dashboard{flex:1}h2{font:22px var(--display);margin:22px 0 10px}.coverage-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.tile{min-height:58px;background-color:var(--fill);color:var(--ink);border:none;padding:8px;text-align:left;border-radius:2px}.tile.unknown{color:var(--text)}.tile span{display:block;font-size:11px;overflow-wrap:anywhere}.tile small{color:inherit;font-size:10px}.untested{background-image:repeating-linear-gradient(45deg,transparent,transparent 4px,color-mix(in srgb,var(--ink) 8%,transparent) 4px,color-mix(in srgb,var(--ink) 8%,transparent) 5px)}.file{display:block;text-align:left;width:100%;background:transparent;padding:12px 0;border:none;border-bottom:1px solid var(--border);border-radius:0}.file-head{display:flex;justify-content:space-between;gap:8px;align-items:baseline}.path{font:12px var(--mono);overflow-wrap:anywhere}.file-head small{white-space:nowrap}progress{appearance:none;display:block;width:100%;height:4px;margin-top:8px;border:none;background:var(--border)}progress::-webkit-progress-bar{background:var(--border)}progress::-webkit-progress-value{background:var(--fill,var(--blue))}.legend{margin-top:8px;font:10px var(--mono);color:var(--dim)}.quiet{color:var(--dim);font-size:14px}.error{padding:10px;background:var(--panel);border-left:2px solid var(--accent);margin-top:12px}.footer{margin-top:20px;padding-top:12px;border-top:1px solid var(--border);font:11px var(--mono);color:var(--dim)}${fills}
  </style></head><body><div class="brand"><span class="sun" aria-hidden="true"></span>blindspot<span class="status">${error ? 'Unavailable' : recording ? 'Recording' : paused ? 'Paused' : 'Not recording'}</span></div>${error ? `<p class="error">${escape(error)}</p>` : ''}
  <section class="hero"><span class="eyebrow">Not seen</span><h1>${pct}</h1><p>${known ? `${missing} of ${data.totals.line_count} lines not seen<br>${data.totals.reported_lines} lines seen` : 'Start recording to see coverage.'}</p>${known ? `<div class="meter"><progress max="${data.totals.line_count}" value="${data.totals.reported_lines}" aria-label="Lines seen across the project"></progress></div>` : ''}</section>
  ${data ? `<div class="metrics"><div><strong>${files.length}</strong><small>Files tracked</small></div><div title="Compared with earlier viewed versions where available"><strong>${changesKnown ? changed : '—'}</strong><small>Changed lines unseen</small></div></div>` : ''}
  <div class="controls">${recording ? '<button data-action="pause">Pause</button>' : paused ? '<button data-action="resume">Resume</button>' : '<button class="primary" data-action="start">Start recording</button>'}${recording || paused ? '<button data-action="stop">Stop</button>' : ''}<button data-action="refresh">Refresh</button></div>
  <div class="controls"><button class="dashboard primary" data-action="dashboard">Open full dashboard →</button></div>
  ${files.length ? `<h2>Coverage at a glance</h2><div class="coverage-grid">${files.slice(0,12).map((f,i)=>`<button class="tile coverage-${i} ${f.current_uncertain ? 'unknown' : ''} ${!f.review?.tested ? 'untested' : ''}" data-path="${escape(f.path)}" ${f.current_uncertain ? 'disabled' : ''} title="${escape(f.path)} · ${f.reported_lines} of ${f.line_count} lines seen"><span>${escape(f.path.split('/').at(-1))}</span><small>${f.current_uncertain || !data.has_observations ? 'Unknown' : `${Math.floor(ratio(f)*1000)/10}% seen`}</small></button>`).join('')}</div><p class="legend">Red → yellow: partly seen · Blue: fully seen<br>Hatched: never tested</p>` : ''}
  ${gaps.length ? '<h2>Files with gaps</h2>' : ''}
  ${gaps.slice(0,8).map(f => `<button class="file coverage-${files.indexOf(f)}" data-path="${escape(f.path)}" ${f.current_uncertain ? 'disabled' : ''}><span class="file-head"><span class="path">${escape(f.path)}</span><small>${f.current_uncertain ? 'Unknown' : `${f.unknown_lines} unseen`}</small></span>${!f.current_uncertain ? `<progress max="100" value="${100*ratio(f)}" aria-label="Lines seen"></progress>` : ''}</button>`).join('')}
  ${data && !gaps.length ? '<p class="quiet">No visibility gaps recorded.</p>' : ''}<footer class="footer">Local only · Updated every 10 seconds</footer>
  <script nonce="${cspNonce}">const vscode=acquireVsCodeApi();document.addEventListener('click',event=>{const button=event.target.closest('button');if(button&&!button.disabled)vscode.postMessage(button.dataset.path?{type:'file',path:button.dataset.path}:{type:'action',action:button.dataset.action});});</script></body></html>`;
}
function createSidebar(api, context, getConnection) {
  return {resolveWebviewView(view) {
    const assets = {};
    if (view.webview.asWebviewUri) {
      const folder = path.join(context.extensionPath, 'media/fonts');
      view.webview.options = {enableScripts:true, localResourceRoots:[api.Uri.file(folder)]};
      assets.cspSource = view.webview.cspSource;
      for (const [id, family] of [['mono','ibm-plex-mono'],['body','eb-garamond'],['display','cormorant-garamond']]) assets[id] = view.webview.asWebviewUri(api.Uri.file(path.join(folder,family+'.woff2'))).toString();
    } else view.webview.options = {enableScripts:true};
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
        if(!disposed)view.webview.html=sidebarHtml(data,null,crypto.randomBytes(16).toString('hex'),assets);
      } catch(error) { data=null; root=null; if(!disposed)view.webview.html=sidebarHtml(null,error.message,crypto.randomBytes(16).toString('hex'),assets); }
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
    view.webview.html=sidebarHtml(null,null,crypto.randomBytes(16).toString('hex'),assets);
    const timer=setInterval(refresh,10000);
    const visibility=view.onDidChangeVisibility(refresh);
    view.onDidDispose(()=>{disposed=true;clearInterval(timer);messages.dispose();visibility.dispose();});
    context.subscriptions.push({dispose(){disposed=true;clearInterval(timer);messages.dispose();visibility.dispose();}});
    void refresh();
  }};
}
module.exports={createSidebar,sidebarHtml};
