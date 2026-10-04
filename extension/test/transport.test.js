'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {Transport,readConnection,MAX_BATCH_EVENTS,MAX_BATCH_BYTES,MAX_QUEUE_EVENTS}=require('../transport');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const connection={endpoint:'http://127.0.0.1:7777',token:'x'.repeat(32)};
test('network retry preserves the exact envelope and queue order',async()=>{
  const bodies=[];let calls=0;const failures=[];
  const transport=new Transport(connection,e=>failures.push(e),async(url,options)=>{bodies.push(options.body);if(calls++===0)throw new Error('ack lost');const count=JSON.parse(options.body).events.length;return {ok:true,json:async()=>({accepted:true,received:count,appended:count,duplicates:0})};});
  transport.enqueue({sequence:0});transport.enqueue({sequence:1});await transport.drain();
  assert.equal(bodies.length,2);assert.equal(bodies[0],bodies[1]);assert.deepEqual(JSON.parse(bodies[0]).events,[{sequence:0},{sequence:1}]);assert.equal(failures.length,0);
});
test('receiver rejection stops the bounded queue and reports failure once',async()=>{
  const failures=[];
  const transport=new Transport(connection,e=>failures.push(e),async()=>({ok:false,status:400,json:async()=>({error:'wrong workspace'})}));
  transport.enqueue({sequence:0});transport.enqueue({sequence:1});await transport.drain();transport.enqueue({sequence:2});
  assert.equal(failures.length,1);assert.equal(transport.failed,true);assert.equal(transport.queue.length,0);
});
test('burst batching reduces requests with exact event order and bounds',async()=>{
  const packets=[],events=Array.from({length:200},(_,sequence)=>({sequence,kind:'visibility'}));
  const transport=new Transport(connection,error=>{throw error;},async(url,options)=>{
    assert.ok(Buffer.byteLength(options.body)<=MAX_BATCH_BYTES);const packet=JSON.parse(options.body).events;
    assert.ok(packet.length<=MAX_BATCH_EVENTS);packets.push(packet);
    return {ok:true,json:async()=>({accepted:true,received:packet.length,appended:packet.length,duplicates:0})};
  });
  events.forEach(e=>transport.enqueue(e));await transport.drain();
  assert.deepEqual(packets.flat(),events);assert.equal(packets.length,4);
});
test('receiver epoch change and missing acknowledgement fail without dropping uncertainty',async()=>{
  const failures=[];
  const transport=new Transport(connection,e=>failures.push(e),async()=>({ok:true,json:async()=>({accepted:true,received:1,appended:1,duplicates:0,receiver_id:'new'})}),{receiverId:'old'});
  transport.enqueue({sequence:0});await transport.drain();
  assert.equal(failures[0].code,'receiver_changed');assert.equal(transport.unacknowledgedEvents,1);assert.equal(transport.lastAcknowledgedAt,null);
});
test('a slow receiver hits the bounded queue and a late acknowledgement cannot revive it',async()=>{
  let complete;const failures=[],states=[];
  const pending=new Promise(resolve=>{complete=resolve;});
  const transport=new Transport(connection,e=>failures.push(e),()=>pending,{onStatus:state=>states.push(state)});
  transport.enqueue({sequence:0,kind:'session_start'});
  for(let sequence=1;sequence<=MAX_QUEUE_EVENTS;sequence++)transport.enqueue({sequence});
  assert.equal(failures.length,1);assert.equal(failures[0].code,'queue_overflow');
  assert.equal(transport.unacknowledgedEvents,MAX_QUEUE_EVENTS+1);
  assert.equal(transport.queue.length,0);assert.equal(await transport.drain(),false);
  complete({ok:true,json:async()=>({accepted:true,received:1,appended:1,duplicates:0})});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(transport.failed,true);assert.deepEqual(states,['disconnected']);
});
test('large Unicode snapshots split at the byte bound without losing events',async()=>{
  const packets=[],events=Array.from({length:10},(_,sequence)=>({sequence,kind:'snapshot',text:'λ'.repeat(128*1024)}));
  const transport=new Transport(connection,error=>{throw error;},async(url,options)=>{
    assert.ok(Buffer.byteLength(options.body)<=MAX_BATCH_BYTES);
    const packet=JSON.parse(options.body).events;packets.push(packet);
    return {ok:true,json:async()=>({accepted:true,received:packet.length,appended:packet.length,duplicates:0})};
  });
  events.forEach(e=>transport.enqueue(e));await transport.drain();
  assert.equal(packets.length,2);assert.deepEqual(packets.flat(),events);
});
test('connection rejects remote endpoints and credentials in URL',async()=>{
  const temp=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-connection-'));const file=path.join(temp,'connection.json');
  try {for(const endpoint of ['https://example.com','http://127.0.0.1@example.com:7777','http://127.0.0.1:7777/private']) {
    await fs.writeFile(file,JSON.stringify({...connection,endpoint}));await assert.rejects(readConnection(file));
  } await fs.writeFile(file,JSON.stringify(connection));assert.deepEqual(await readConnection(file),connection);
  } finally {await fs.rm(temp,{recursive:true});}
});

test('diagnostics bound request history and omit credentials, request bodies and source',async()=>{
  const t=new Transport({endpoint:'http://127.0.0.1:7777',token:'private-token'},()=>{},async()=>({ok:true,status:200,json:async()=>({accepted:true})}));
  for(let n=0;n<25;n++)await t.send('/api/heartbeat','private-source');
  const diagnostics=t.diagnostics(),encoded=JSON.stringify(diagnostics);
  assert.equal(diagnostics.recent_requests.length,20);
  assert.ok(diagnostics.recent_requests.every(r=>r.duration_ms>=0));
  assert.ok(!encoded.includes('private-token')&&!encoded.includes('private-source'));
});
test('session expiry retains only whitelisted receiver contact diagnostics',async()=>{
  const t=new Transport({endpoint:'http://127.0.0.1:7777',token:'token'},()=>{},async()=>({ok:false,status:409,json:async()=>({code:'session_unavailable',error:'expired',diagnostics:{reason:'heartbeat_expired',contact_age_ms:8000,stale_after_ms:7000,text:'secret',token:'secret'}})}));
  await assert.rejects(t.send('/api/heartbeat'),error=>{
    assert.deepEqual(error.diagnostics,{reason:'heartbeat_expired',contact_age_ms:8000,stale_after_ms:7000});return true;
  });
});
