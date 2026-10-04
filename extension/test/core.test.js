'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {Collector,hash}=require('../core');
function fixture() {
  let clock=0; const events=[];
  const core=new Collector('/pilot',e=>events.push(e),()=>clock);
  const view=(text='a\nb\nc')=>core.setView({path:'a.py',text,focused:true,dirty:false,documentVersion:1,ranges:[[1,2]]});
  return {core,events,view,time:n=>clock=n};
}
test('focus loss, pause and resume cannot accrue background display',()=>{
  const f=fixture();f.view();f.time(1000);f.core.tick();f.time(1200);f.core.setView(null);
  f.time(2000);f.core.tick();f.time(2500);f.view();f.time(3000);f.core.pause();
  f.time(8000);f.core.tick();f.core.resume();f.view();f.time(8500);f.core.stop();
  const intervals=f.events.filter(e=>e.kind==='visibility');
  assert.deepEqual(intervals.map(e=>e.payload.duration_ms),[1000,200,500,500]);
  assert.equal(intervals.reduce((sum,e)=>sum+e.payload.duration_ms,0),2200);
  assert.deepEqual(f.events.filter(e=>e.kind==='state').map(e=>e.payload.status),['paused','recording']);
});
test('scroll and edits flush the old exact version before reporting the new view',()=>{
  const f=fixture();f.view();f.time(400);f.core.setView({path:'a.py',text:'a\nb\nc',focused:true,ranges:[[3,3]]});
  f.time(600);f.view('changed\nb\nc');f.time(1000);f.core.tick();
  const intervals=f.events.filter(e=>e.kind==='visibility');
  assert.deepEqual(intervals.map(e=>[e.payload.content_hash,e.payload.ranges,e.payload.duration_ms]),[[hash('a\nb\nc'),[[1,2]],400],[hash('a\nb\nc'),[[3,3]],200],[hash('changed\nb\nc'),[[1,2]],400]]);
});
test('event loop/sleep delay is a gap, not dwell time',()=>{
  const f=fixture();f.view();f.time(10000);f.core.tick();
  assert.equal(f.events.filter(e=>e.kind==='visibility').length,0);
  assert.equal(f.events.at(-1).payload.reason,'sampling_gap');
  f.time(11000);f.core.tick();assert.equal(f.events.at(-1).payload.duration_ms,1000);
});
test('paused snapshots and interactions are suppressed; reverting records old version again',()=>{
  const f=fixture();f.view();f.time(500);f.view('changed\nb\nc');f.time(1000);f.view();
  assert.equal(f.events.filter(e=>e.kind==='snapshot').length,3);
  f.core.pause();const before=f.events.length;f.core.snapshot('b.py','secret');f.core.interaction({kind:'selection'});
  assert.equal(f.events.length,before);f.core.marker('paused test');assert.equal(f.events.at(-1).kind,'marker');
});
test('oversized or binary content cannot create a display observation',()=>{
  const f=fixture();f.view('x'.repeat(256*1024+1));f.time(1000);f.core.tick();
  f.view('a\0b');f.time(2000);f.core.tick();assert.equal(f.events.filter(e=>e.kind==='visibility').length,0);
});
test('identical adjacent ranges coalesce; a version or metadata boundary stays separate',()=>{
  const f=fixture();f.view();
  for(let n=1;n<=100;n++){f.time(n);f.view();}
  f.time(101);f.core.tick();
  assert.equal(f.events.filter(e=>e.kind==='visibility').length,1);
  assert.equal(f.events.at(-1).payload.duration_ms,101);
  f.time(150);f.core.marker('boundary');f.time(200);f.view('changed\nb\nc');f.time(250);f.core.tick();
  const frames=f.events.filter(e=>e.kind==='visibility');
  assert.equal(frames.at(-1).payload.content_hash,hash('changed\nb\nc'));
  assert.equal(frames.reduce((sum,e)=>sum+e.payload.duration_ms,0),250);
  assert.ok(f.events.every((e,i)=>!i||e.monotonic_ms>=f.events[i-1].monotonic_ms));
});

test('cached source still binds exact contents on edit, revert, path change and disk/document overlap',()=>{
  const f=fixture();f.view();f.time(100);f.view();
  // Deliberately keep documentVersion=1: contents alone decide whether to reuse.
  f.time(200);f.view('changed\nb\nc');
  f.time(300);f.core.snapshot('a.py','disk\nb\nc','disk');f.view('changed\nb\nc');
  f.time(400);f.view();
  f.time(500);f.core.setView({path:'other.py',text:'a\nb\nc',focused:true,ranges:[[1,2]]});
  f.time(600);f.core.stop();
  assert.deepEqual(f.events.filter(e=>e.kind==='snapshot').map(e=>[e.payload.path,e.payload.content_hash]),[
    ['a.py',hash('a\nb\nc')],['a.py',hash('changed\nb\nc')],['a.py',hash('disk\nb\nc')],
    ['a.py',hash('changed\nb\nc')],['a.py',hash('a\nb\nc')],['other.py',hash('a\nb\nc')]
  ]);
  const frames=f.events.filter(e=>e.kind==='visibility');
  assert.equal(frames.reduce((sum,e)=>sum+e.payload.duration_ms,0),600);
  assert.deepEqual(frames.map(e=>e.payload.content_hash),[hash('a\nb\nc'),hash('changed\nb\nc'),hash('changed\nb\nc'),hash('a\nb\nc'),hash('a\nb\nc')]);
  assert.equal(f.core.lastSnapshot,null,'Stop releases the cached source');
});

test('passive panes retain separate frames and closing one ends only its interval',()=>{
  const f=fixture();
  const pane=(name,id,active)=>({path:name,text:'a\nb\nc',focused:true,ranges:[[1,2]],paneId:id,active,exposure:'reported-visible'});
  const left=pane('a.py','left',true),right=pane('b.py','right',false);
  f.core.setViews([left,right]);f.time(500);f.core.setViews([left]);f.time(1000);f.core.tick();f.core.stop();
  const frames=f.events.filter(e=>e.kind==='visibility');
  assert.equal(frames.filter(e=>e.payload.path==='a.py').reduce((s,e)=>s+e.payload.duration_ms,0),1000);
  assert.equal(frames.filter(e=>e.payload.path==='b.py').reduce((s,e)=>s+e.payload.duration_ms,0),500);
  assert.equal(frames.find(e=>e.payload.path==='b.py').payload.active,false);
  assert.ok(f.events.every((e,i)=>!i||e.monotonic_ms>=f.events[i-1].monotonic_ms));
});
test('visibility exclusion suspends pane evidence while keeping interactions separate',()=>{
  const f=fixture();f.view();f.time(500);f.core.setExcluded(true);
  f.core.interaction({path:'a.py',kind:'selection',cause:'unknown'});
  f.time(1500);f.view();f.core.tick();f.core.setExcluded(false);f.view();f.time(2000);f.core.stop();
  const frames=f.events.filter(e=>e.kind==='visibility');
  assert.equal(frames.reduce((s,e)=>s+e.payload.duration_ms,0),1000);
  assert.equal(f.events.filter(e=>e.kind==='interaction').length,1);
  assert.deepEqual(f.events.filter(e=>e.kind==='visibility_policy').map(e=>e.payload.excluded),[true,false]);
});
