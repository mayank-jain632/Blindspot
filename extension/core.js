'use strict';
const {createHash, randomUUID} = require('node:crypto');
const {version} = require('./package.json');
const MAX_TEXT = 256 * 1024;
const hash = text => createHash('sha256').update(text, 'utf8').digest('hex');

class Collector {
  constructor(workspace, emit, now, wall = () => new Date().toISOString()) {
    this.workspace = workspace; this.sink = emit; this.now = now; this.wall = wall;
    this.session = randomUUID(); this.sequence = 0; this.mode = 'recording';
    this.views = new Map(); this.pending = new Map(); this.since = now(); this.versions = new Set(); this.current = new Map();
    this.excluded=false;
    // Retain only one validated source string, rather than rehashing it on scroll.
    this.lastSnapshot = null;
    this.event('session_start', {mode:'visible-editors-reported-ranges', collector_version:version, interval_ms:1000, heartbeat_interval_ms:2000});
  }
  event(kind, payload, clock = this.now()) {
    this.emitPending();
    this.emit(kind,payload,clock);
  }
  emit(kind,payload,clock) {
    this.sink({schema_version:1, session_id:this.session, sequence:this.sequence++, workspace:this.workspace,
      observed_at:this.wall(), monotonic_ms:clock, kind, payload});
  }
  emitPending() {
    const frames=[...this.pending.values()].sort((a,b)=>a.end_ms-b.end_ms);
    this.pending.clear();
    for(const payload of frames)this.emit('visibility',payload,payload.end_ms);
  }
  snapshot(path, text, origin='document', dirty=false, documentVersion=null, clock=this.now()) {
    if(this.mode !== 'recording') return null;
    let content_hash;
    if(this.lastSnapshot?.path===path && this.lastSnapshot.text===text) {
      content_hash=this.lastSnapshot.content_hash;
    } else {
      if(Buffer.byteLength(text,'utf8')>MAX_TEXT || text.includes('\0')) {
        this.event('diagnostic',{reason:'unsupported_snapshot',path},clock); return null;
      }
      content_hash=hash(text);
      this.lastSnapshot={path,text,content_hash};
    }
    const key = `${path}\0${content_hash}`;
    const changed = this.current.get(path) !== content_hash;
    // Record a change back to a known version as well as first-seen versions.
    if(!this.versions.has(key) || changed) {
      this.event('snapshot',{path,text,content_hash,line_count:text.split('\n').length,origin,dirty,document_version:documentVersion},clock);
      this.versions.add(key); this.current.set(path,content_hash);
    }
    return content_hash;
  }
  flush(clock=this.now()) {
    if(this.mode !== 'recording') return;
    const duration = clock-this.since;
    if(duration>2500) this.event('diagnostic',{reason:'sampling_gap',duration_ms:duration},clock);
    else if(duration>0&&!this.excluded) {
      const frames=[...this.views.values()].map(view=>({...view,start_ms:this.since,end_ms:clock,duration_ms:duration,focused:true,focus_scope:'window',editor_focus:'unverified'}));
      const canMerge=frames.length===this.pending.size&&frames.every(payload=>{
        const pending=this.pending.get(payload.pane_id);
        return pending&&pending.end_ms===payload.start_ms&&pending.path===payload.path&&pending.content_hash===payload.content_hash&&pending.active===payload.active&&JSON.stringify(pending.ranges)===JSON.stringify(payload.ranges)&&pending.duration_ms+duration<=2500;
      });
      if(!canMerge)this.emitPending();
      for(const payload of frames) {
        const pending=this.pending.get(payload.pane_id);
        if(canMerge){pending.end_ms=clock;pending.duration_ms+=duration;}
        else this.pending.set(payload.pane_id,payload);
      }
    }
    this.since = clock;
  }
  setView(input, clock=this.now()) {
    this.setViews(input?[{...input,paneId:input.paneId||'legacy-active',active:input.active??true,exposure:input.exposure||'active-fallback'}]:[],clock);
  }
  setViews(inputs,clock=this.now()) {
    this.flush(clock);this.views.clear();
    if(this.mode!=='recording'||this.excluded){this.emitPending();return;}
    for(const input of inputs.slice(0,16)) {
      if(!input?.focused||!input.ranges.length)continue;
      const content_hash=this.snapshot(input.path,input.text,'document',input.dirty,input.documentVersion,clock);
      if(content_hash)this.views.set(input.paneId,{path:input.path,content_hash,ranges:input.ranges.map(r=>r.slice()),pane_id:input.paneId,active:input.active,exposure:input.exposure,view_kind:'visible-editor-reported-ranges'});
    }
    if(!this.views.size)this.emitPending();
  }
  setExcluded(excluded) {
    const clock=this.now();this.flush(clock);this.views.clear();this.excluded=excluded;
    this.event('visibility_policy',{excluded},clock);
  }
  tick() { this.flush(); this.emitPending(); }
  pause() { if(this.mode !== 'recording') return; const clock=this.now(); this.flush(clock); this.views.clear(); this.mode='paused'; this.event('state',{status:'paused'},clock); }
  resume() { if(this.mode !== 'paused') return; this.mode='recording'; this.since=this.now(); this.event('state',{status:'recording'},this.since); }
  stop() { if(this.mode==='ended') return; const clock=this.now(); this.flush(clock); this.views.clear(); this.lastSnapshot=null; this.mode='ended'; this.event('session_end',{},clock); }
  interaction(payload) { if(this.mode==='recording') this.event('interaction',{...payload,content_hash:this.current.get(payload.path)||null}); }
  marker(label) { if(this.mode!=='ended') this.event('marker',{label:label.slice(0,200)}); }
}
module.exports = {Collector,hash,MAX_TEXT};
