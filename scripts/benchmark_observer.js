'use strict';
// Synthetic collector load; real transport and receiver. No VS Code host.
const fs=require('node:fs');
const assert=require('node:assert/strict');
const {performance,monitorEventLoopDelay}=require('node:perf_hooks');
const {Collector}=require('../extension/core');
const {Transport}=require('../extension/transport');
const config=JSON.parse(fs.readFileSync(0,'utf8'));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const summary=values=>{
  const sorted=values.slice().sort((a,b)=>a-b);
  const at=q=>sorted[Math.min(sorted.length-1,Math.floor(sorted.length*q))]||0;
  return {count:values.length,p50_ms:at(.5),p95_ms:at(.95),p99_ms:at(.99),max_ms:at(1)};
};
function microbenchmark(bytes,paused=false) {
  const text=('source_line\n'.repeat(Math.ceil(bytes/12))).slice(0,bytes);
  let clock=0,events=0;
  const collector=new Collector(config.workspace,()=>events++,()=>clock);
  const input={path:'micro.py',text,focused:true,ranges:[[1,20]]};
  collector.setView(input);if(paused)collector.pause();
  // Warm the code path before measuring, then observe repeated range callbacks.
  for(let i=0;i<100;i++){clock++;collector.setView(input);}
  const samples=[],cpu=process.cpuUsage(),start=performance.now();
  for(let i=0;i<3000;i++) {
    clock++;const before=performance.now();collector.setView(input);samples.push(performance.now()-before);
    if(i%100===99)collector.tick();
  }
  const elapsed=performance.now()-start,usage=process.cpuUsage(cpu);
  collector.stop();
  return {source_bytes:Buffer.byteLength(text),text_input:'same source string on each callback',paused,callbacks:3000,wall_ms:elapsed,cpu_ms:(usage.user+usage.system)/1000,callback:summary(samples),emitted_events:events};
}
async function main() {
  const micro=[microbenchmark(8192),microbenchmark(256*1024),microbenchmark(256*1024,true)];
  const timings=[],bodyBytes=[],callbacks=[];
  let peakRss=process.memoryUsage().rss,peakQueue=0,generated=0,snapshots=0,displayMs=0,failure;
  const transport=new Transport(config,error=>{failure=error;},async(url,options)=>{
    const start=performance.now();const response=await fetch(url,options);
    // Include receipt-body read time in request latency.
    const data=await response.json();
    if(url.endsWith('/api/events/batch')) {timings.push(performance.now()-start);bodyBytes.push(Buffer.byteLength(options.body));}
    return {ok:response.ok,status:response.status,json:async()=>data};
  });
  await transport.health();
  const collector=new Collector(config.workspace,event=>{
    generated++;if(event.kind==='snapshot')snapshots++;
    if(event.kind==='visibility')displayMs+=event.payload.duration_ms;
    transport.enqueue(event);peakQueue=Math.max(peakQueue,transport.queue.length);
  },()=>performance.now());
  const cpu=process.cpuUsage(),start=performance.now();
  const delay=monitorEventLoopDelay({resolution:10});delay.enable();
  await transport.drain();
  const source='baseline source\n'.repeat(512); // 8 KiB per eligible source.
  for(let i=0;i<500;i++) {
    collector.snapshot('source-'+i+'.py',source,'disk');
    if(i%64===63)assert.equal(await transport.drain(),true);
  }
  assert.equal(await transport.drain(),true);
  const baselineMs=performance.now()-start;
  let heartbeatBusy=false;
  const heartbeat=setInterval(async()=>{
    if(heartbeatBusy)return;heartbeatBusy=true;
    try {await transport.heartbeat(collector.session,config.workspace);}
    finally {heartbeatBusy=false;}
  },2000);
  try {
    for(let i=0;i<600;i++) {
      if(i===200)collector.setView(null);
      if(i===400)collector.pause();
      if(i===450)collector.resume();
      const before=performance.now();
      if(i<200||i>=250)collector.setView({path:'source-0.py',text:source+'version '+Math.floor(i/10),focused:true,ranges:i%2?[[1,20]]:[[21,40]]});
      if(i%100===99)collector.tick();
      callbacks.push(performance.now()-before);
      peakRss=Math.max(peakRss,process.memoryUsage().rss);
      assert.equal(transport.failed,false,failure?.message);
      await sleep(10);
    }
    collector.stop();assert.equal(await transport.drain(),true,failure?.message);
  } finally {clearInterval(heartbeat);delay.disable();}
  const usage=process.cpuUsage(cpu);
  process.stdout.write(JSON.stringify({microbenchmarks:micro,load:{
    source_files:500,baseline_ms:baselineMs,source_bytes_each:Buffer.byteLength(source),callbacks:600,
    requested_callback_spacing_ms:10,wall_ms:performance.now()-start,cpu_ms:(usage.user+usage.system)/1000,
    callback:summary(callbacks),batch_request:summary(timings),batch_requests:timings.length,
    max_batch_bytes:Math.max(...bodyBytes),peak_queued_events:peakQueue,peak_rss_bytes:peakRss,
    event_loop_delay_p95_ms:delay.percentile(95)/1e6,event_loop_delay_max_ms:delay.max/1e6,
    transport_metrics:transport.metrics,generated_events:generated,generated_snapshots:snapshots,generated_display_ms:displayMs
  }}));
}
main().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
