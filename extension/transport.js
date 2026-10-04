'use strict';
const fs=require('node:fs/promises');
const {performance}=require('node:perf_hooks');
const BATCH_DELAY_MS=200,MAX_BATCH_EVENTS=64,MAX_BATCH_BYTES=2*1024*1024;
const MAX_QUEUE_EVENTS=512,MAX_QUEUE_BYTES=8*1024*1024;
class ReceiverError extends Error {
  constructor(message,code='connection_lost',recoverable=true,retryable=true) {
    super(message);this.code=code;this.recoverable=recoverable;this.retryable=retryable;
  }
}
async function readConnection(filename) {
  if(!filename)throw new ReceiverError('Set blindspot.connectionFile to the receiver connection.json, or launch with the supplied F5 configuration.','invalid_configuration',false,false);
  const value=JSON.parse(await fs.readFile(filename,'utf8')),endpoint=new URL(value.endpoint);
  if(endpoint.protocol!=='http:'||endpoint.hostname!=='127.0.0.1'||endpoint.username||endpoint.password||endpoint.pathname!=='/'||endpoint.search||endpoint.hash||typeof value.token!=='string'||value.token.length<20)
    throw new ReceiverError('Connection must be an authenticated 127.0.0.1 HTTP receiver.','invalid_configuration',false,false);
  return {endpoint:endpoint.origin,token:value.token};
}
class Transport {
  constructor(connection,onFailure,request=fetch,options={}) {
    this.connection=connection;this.onFailure=onFailure;this.request=request;
    this.onStatus=options.onStatus||(()=>{});this.delay=options.batchDelayMs??BATCH_DELAY_MS;
    this.receiverId=options.receiverId;this.queue=[];this.queueBytes=0;this.running=false;
    this.failed=false;this.waiters=[];this.timer=null;this.lastAcknowledgedAt=null;
    this.unacknowledgedEvents=0;this.metrics={batch_requests:0,retries:0,acknowledged_events:0};
    this.recent=[];this.lastAck=null;this.lastHeartbeatAt=null;
  }
  diagnostics() {return {queue_events:this.queue.length,queue_bytes:this.queueBytes,unacknowledged_events:this.unacknowledgedEvents,last_ack:this.lastAck,last_heartbeat_at:this.lastHeartbeatAt,metrics:{...this.metrics},recent_requests:this.recent.slice(-20)};}
  trace(route,start,status,code=null) {
    this.recent.push({at:new Date().toISOString(),route,status,code,duration_ms:performance.now()-start});
    if(this.recent.length>20)this.recent.shift();
  }
  async send(route,body) {
    const start=performance.now();
    const headers={Authorization:'Bearer '+this.connection.token};
    if(this.receiverId)headers['X-Blindspot-Receiver']=this.receiverId;
    if(body!==undefined)headers['Content-Type']='application/json';
    let response,data;
    try {
      response=await this.request(this.connection.endpoint+route,{
        method:body===undefined?'GET':'POST',headers,body,signal:AbortSignal.timeout(2000)
      });
      data=await response.json();
    } catch(error) {
      this.trace(route,start,null,'connection_lost');
      throw new ReceiverError('Receiver request failed: '+error.message,'connection_lost');
    }
    this.trace(route,start,response.status||200,data?.code||null);
    if(!data||typeof data!=='object')throw new ReceiverError('Invalid receiver response.','invalid_receipt');
    if(!response.ok) {
      const fatal=response.status===400||data.code==='storage_failure'||response.status===413;
      const error=new ReceiverError(data.error||'Receiver returned '+response.status,data.code||'receiver_rejected',!fatal,!fatal&&response.status>=500);
      const details=data.diagnostics||{};
      error.diagnostics=Object.fromEntries(['reason','contact_age_ms','last_contact_at','stale_after_ms'].filter(key=>['string','number'].includes(typeof details[key])).map(key=>[key,details[key]]));
      throw error;
    }
    if(this.receiverId&&data.receiver_id!==this.receiverId)
      throw new ReceiverError('Receiver restarted; a new session is required.','receiver_changed',true,false);
    return data;
  }
  async health() {
    const data=await this.send('/api/health');
    if(typeof data.receiver_id!=='string'||!data.capabilities?.batch_events||!data.capabilities?.heartbeat)
      throw new ReceiverError('Receiver needs updating. Restart the Python receiver to enable batching and heartbeats.','unsupported_receiver',false,false);
    this.receiverId=data.receiver_id;return data;
  }
  enqueue(event) {
    if(this.failed)return;
    const encoded=JSON.stringify(event),bytes=Buffer.byteLength(encoded,'utf8');
    if(bytes>MAX_BATCH_BYTES-64) {
      this.fail(new ReceiverError('Event exceeds the batch byte limit.','event_too_large',false,false),1);return;
    }
    if(this.queue.length>=MAX_QUEUE_EVENTS||this.queueBytes+bytes>MAX_QUEUE_BYTES) {
      this.fail(new ReceiverError('Receiver queue full; recording suspended to bound buffering.','queue_overflow'),1);return;
    }
    this.queue.push({event,encoded,bytes});this.queueBytes+=bytes;
    if(['session_start','session_end','state','recording_gap'].includes(event.kind)||this.queue.length>=MAX_BATCH_EVENTS)void this.flush();
    else if(!this.running&&!this.timer)this.timer=setTimeout(()=>{this.timer=null;void this.pump();},this.delay);
  }
  fail(error,extra=0) {
    if(this.failed)return;
    this.failed=true;this.unacknowledgedEvents=this.queue.length+extra;
    this.queue=[];this.queueBytes=0;clearTimeout(this.timer);this.timer=null;
    this.onStatus('disconnected');this.onFailure(error);this.finish();
  }
  finish() {
    if(this.failed||!this.running&&!this.queue.length)
      for(const resolve of this.waiters.splice(0))resolve(!this.failed);
  }
  async flush() {
    clearTimeout(this.timer);this.timer=null;await this.pump();
  }
  async pump() {
    if(this.running||this.failed)return;
    this.running=true;
    try {
      while(this.queue.length&&!this.failed) {
        const batch=[];let bytes=32;
        for(const item of this.queue) {
          if(batch.length===MAX_BATCH_EVENTS||bytes+item.bytes+1>MAX_BATCH_BYTES)break;
          batch.push(item);bytes+=item.bytes+1;
        }
        const body='{"schema_version":1,"events":['+batch.map(item=>item.encoded).join(',')+']}';
        let error;
        for(let attempt=0;attempt<2;attempt++) {
          try {
            this.metrics.batch_requests++;
            const data=await this.send('/api/events/batch',body);
            if(data.accepted!==true||data.received!==batch.length||data.appended+data.duplicates!==batch.length)
              throw new ReceiverError('Invalid batch acknowledgement.','invalid_receipt',true,true);
            error=null;break;
          } catch(caught) {
            error=caught;
            if(attempt===0&&caught.retryable!==false) {this.metrics.retries++;this.onStatus('retrying');}
            else break;
          }
        }
        if(this.failed)break;
        if(error) {this.fail(error);break;}
        this.lastAcknowledgedAt=batch.at(-1).event.observed_at;
        this.lastAck={session_id:batch.at(-1).event.session_id,sequence:batch.at(-1).event.sequence,observed_at:this.lastAcknowledgedAt};
        this.metrics.acknowledged_events+=batch.length;
        this.queue.splice(0,batch.length);this.queueBytes-=batch.reduce((sum,item)=>sum+item.bytes,0);
        this.onStatus('connected');
      }
    } finally {this.running=false;this.finish();}
  }
  async heartbeat(sessionId,workspace) {
    if(this.failed)return;
    try {
      const data=await this.send('/api/heartbeat',JSON.stringify({schema_version:1,session_id:sessionId,workspace}));
      if(data.accepted!==true)throw new ReceiverError('Invalid heartbeat acknowledgement.');
      this.lastHeartbeatAt=new Date().toISOString();
      if(!this.failed)this.onStatus('connected');
    } catch(error) {this.fail(error);}
  }
  async drain() {
    if(this.failed)return false;
    void this.flush();
    if(!this.running&&!this.queue.length)return true;
    return new Promise(resolve=>this.waiters.push(resolve));
  }
}
module.exports={Transport,ReceiverError,readConnection,BATCH_DELAY_MS,MAX_BATCH_EVENTS,MAX_QUEUE_EVENTS,MAX_BATCH_BYTES};
