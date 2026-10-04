'use strict';
let report,receiverAvailable=false,selection=null,inspectGeneration=0;
const $=id=>document.getElementById(id);
const bridge=typeof acquireVsCodeApi==='function'?acquireVsCodeApi():null;
const pending=new Map();let requestId=0;
if(bridge)window.addEventListener('message',event=>{
  const item=pending.get(event.data?.id);if(!item)return;
  pending.delete(event.data.id);clearTimeout(item.timer);
  event.data.error?item.reject(new Error(event.data.error)):item.resolve(event.data.body);
});
function message(body) {
  return new Promise((resolve,reject)=>{
    const id=String(++requestId),timer=setTimeout(()=>{pending.delete(id);reject(new Error('Overview request timed out'));},15000);
    pending.set(id,{resolve,reject,timer});bridge.postMessage({...body,id});
  });
}
function node(tag,text,className){const n=document.createElement(tag);n.textContent=text;if(className)n.className=className;return n;}
async function api(route) {
  if(bridge)return message({type:'request',route});
  let r=await fetch(route,{signal:AbortSignal.timeout(12000)});
  if(r.status===401||r.status===403){await fetch('/',{signal:AbortSignal.timeout(3000)});r=await fetch(route,{signal:AbortSignal.timeout(12000)});}
  const body=await r.json();if(!r.ok)throw new Error(body.error||`Receiver returned ${r.status}.`);return body;
}
function render() {
  $('workspace').textContent=report.workspace;$('stats').replaceChildren();
  const t=report.totals;
  for(const [label,value] of [['Eligible current files',t.eligible_files],['Lines meeting dwell filter',t.dwell_lines],['Briefly displayed lines',t.brief_lines],['Lines with no matching evidence',t.unknown_lines],['Uncertain files (excluded)',t.uncertain_files]]){
    const card=node('div','','stat');card.append(node('strong',String(value)),node('span',label));$('stats').append(card);
  }
  const h=report.health,active=h.sessions.filter(s=>s.connection_state==='connected'),interrupted=h.sessions.filter(s=>['stale','interrupted'].includes(s.connection_state));
  if(receiverAvailable)$('status').textContent=`Receiver connected. ${active.length?`Extension connected: ${active.map(s=>s.status).join(', ')}.`:'No live extension heartbeat.'} ${interrupted.length?`${interrupted.length} interrupted or stale session(s).`:''}`;
  $('health').textContent=`SQLite: ${h.storage.events} records · ${h.ingestion_metrics.transactions||0} transactions this receiver run · Last tab context ${report.tab_context_fresh?'live':'historical or unavailable'}.`;
  $('diagnostics').textContent=JSON.stringify(h.latest_connection_diagnostics||[],null,2);
  $('gaps').replaceChildren(...h.recording_gaps.map(g=>node('div',`${g.recovered_at} · ${g.reason} · ${g.unacknowledged_events} event(s) lacked acknowledgement. Receiver detail: ${JSON.stringify(g.receiver_diagnostics||{})}. Gap duration is uncertain.`,'event')));
  if(!$('gaps').children.length)$('gaps').append(node('p','No recovery gap records yet. Earlier history remains unknown.'));
  const filter=$('filter').value.toLowerCase();$('files').replaceChildren();
  for(const file of report.files.filter(f=>f.path.toLowerCase().includes(filter))){
    const b=node('button',file.path,'file');
    b.append(node('small',file.current_uncertain?'Current buffer uncertain; resume recording':`${file.dwell_lines}/${file.line_count} lines meet filter · ${file.brief_lines} brief · ${file.unknown_lines} unknown · ${file.origin}`));
    b.append(node('small',`${file.review_reason}${file.open_tab?' · tab last observed open':''} · ${file.interaction_events} historical interaction events`));
    b.onclick=()=>inspect(file);$('files').append(b);
  }
  if(!$('files').children.length)$('files').append(node('p','No matching eligible files.'));
  const selected=$('kind').value,kinds=[...new Set(report.timeline.map(e=>e.kind))].sort();
  $('kind').replaceChildren(new Option('All events',''),...kinds.map(k=>new Option(k,k)));$('kind').value=selected;
  $('events').replaceChildren();
  for(const e of report.timeline.filter(e=>(!selected||e.kind===selected)&&JSON.stringify(e).toLowerCase().includes(filter)).slice(-200).reverse()){
    const row=node('div','','event');row.append(node('code',`${e.kind} #${e.sequence} · ${e.observed_at}`),node('div',JSON.stringify(e.payload)));$('events').append(row);
  }
  $('scope').textContent=report.scope+' Dwell: '+report.dwell_aggregation+'. '+report.inventory_diagnostics.join(' ');
  $('limits').replaceChildren(...report.limits.map(l=>node('li',l)));
  if(selection){const current=report.files.find(f=>f.path===selection.path);if(!current||current.current_uncertain||current.content_hash!==selection.content_hash){++inspectGeneration;selection=null;$('source').replaceChildren();$('ranges').textContent='Source changed or became uncertain; choose the file again.';}}
}
function contains(ranges,line){return ranges.some(([a,b])=>a<=line&&line<=b);}
async function inspect(file) {
  const generation=++inspectGeneration;selection=file;
  $('source-title').textContent=file.path;$('source').replaceChildren();
  if(file.current_uncertain){$('ranges').textContent='Current document state uncertain; resume recording and refresh.';return;}
  try {
    const source=await api(`/api/current-source?path=${encodeURIComponent(file.path)}&hash=${file.content_hash}`);
    if(generation!==inspectGeneration)return;
    $('ranges').textContent=`${source.origin} · ${file.content_hash.slice(0,12)} · Green: meets dwell filter; amber: brief; plain: unknown.${file.mapped_source_hashes.length?` ${file.mapped_source_hashes.length} earlier version(s) contribute verified unchanged blocks.`:' Exact-version evidence only.'}${bridge?' Double-click a line to open it in VS Code.':''}`;
    $('source').replaceChildren(...source.text.split('\n').map((text,i)=>{
      const line=i+1,n=node('span',`${String(line).padStart(4)}  ${text}`,`line${contains(file.dwell_ranges,line)?' displayed':contains(file.brief_ranges,line)?' brief':''}`);
      if(bridge)n.ondblclick=()=>message({type:'open-source',path:file.path,line}).catch(error=>{$('status').textContent=error.message;});return n;
    }));
  }catch(error){if(generation===inspectGeneration)$('ranges').textContent=error.message;}
}
let refreshing=false;
async function refresh() {
  if(refreshing)return false;refreshing=true;
  try {
    report=await api('/api/overview?dwell_ms='+($('dwell').value||1000));
    receiverAvailable=report.receiver?.status!=='storage_failed';render();
    if(selection&&receiverAvailable){const file=report.files.find(f=>f.path===selection.path);if(file)await inspect(file);}
    if(!receiverAvailable)throw new Error('Storage failed; resolve the error and restart the receiver.');
    $('status').className='';$('download').disabled=false;return true;
  }catch(error){receiverAvailable=false;$('status').textContent=`Receiver unavailable: ${error.message} Displayed data is stale; reconnection will be retried.`;$('status').className='error';$('download').disabled=true;return false;}
  finally{refreshing=false;}
}
$('refresh').onclick=refresh;$('filter').oninput=()=>report&&render();$('kind').onchange=()=>report&&render();
$('dwell').onchange=async()=>{const path=selection?.path;if(await refresh()&&path){const file=report.files.find(f=>f.path===path);if(file)await inspect(file);}};
$('download').onclick=async()=>{
  try {
    if(bridge){$('status').textContent='Use the localhost view to download the full report, or blindspot observer report for an offline export.';return;}
    const full=await api('/api/report');
    if(full.receiver?.status==='storage_failed')throw new Error('Storage failed; restart the receiver');
    const url=URL.createObjectURL(new Blob([JSON.stringify(full,null,2)],{type:'application/json'}));
    const a=node('a','');a.href=url;a.download='blindspot-observer-report.json';a.click();URL.revokeObjectURL(url);
  }catch(error){$('status').textContent=error.message;}
};
refresh();setInterval(()=>{if(typeof document.hidden==='undefined'||!document.hidden)void refresh();},5000);
