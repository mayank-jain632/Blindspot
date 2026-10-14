'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const http=require('node:http');
const {execFileSync}=require('node:child_process');
const extensionRoot=process.env.BLINDSPOT_TEST_EXTENSION||path.resolve(__dirname,'..');
const {ReceiverManager}=require(path.join(extensionRoot,'receiver'));
test('managed receiver works without system Python, serves dashboard, and shuts down only its owned process',{timeout:90000},async()=>{
  const base=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-managed-'));
  const workspace=await fs.realpath(base);
  execFileSync('git',['init',workspace],{stdio:'ignore'});
  await fs.writeFile(path.join(workspace,'example.py'),'value = 1\n');
  const directory=path.join(extensionRoot,'receiver');
  const state=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-managed-state-'));
  const originalPath=process.env.PATH,originalHome=process.env.PYTHONHOME,originalPythonPath=process.env.PYTHONPATH;
  const git=execFileSync('/usr/bin/which',['git'],{encoding:'utf8'}).trim();
  const bin=path.join(state,'bin');await fs.mkdir(bin);await fs.symlink(git,path.join(bin,'git'));
  process.env.PATH=bin;process.env.PYTHONHOME='/nonexistent-python-home';process.env.PYTHONPATH='/nonexistent-python-path';
  const manager=new ReceiverManager(directory,state),reuse=new ReceiverManager(directory,state);
  try {
    const [first,second]=await Promise.all([manager.ensure(workspace),manager.ensure(workspace)]);
    assert.deepEqual(first,second);
    assert.ok(manager.child);
    assert.match(manager.child.spawnfile,/runtimes/);
    const response=await fetch(first.endpoint+'/api/health',{headers:{Authorization:'Bearer '+first.token}});
    assert.equal((await response.json()).workspace,workspace);
    const page=await fetch(first.endpoint+'/');
    assert.equal(page.status,200);
    const html=await page.text();
    const asset=html.match(/src="(\/assets\/[^\"]+\.js)"/);
    assert.ok(asset,'built dashboard JavaScript is linked');
    assert.equal((await fetch(first.endpoint+asset[1])).status,200);
    const dashboard=await (await fetch(first.endpoint+'/api/dashboard')).json();
    assert.equal(dashboard.files[0].path,'example.py');
    const rejected=await new Promise((resolve,reject)=>{
      http.get(first.endpoint+'/',{headers:{Host:'attacker.example'}},response=>{response.resume();resolve(response.statusCode);}).on('error',reject);
    });
    assert.equal(rejected,403);
    const origin=await fetch(first.endpoint+'/api/dashboard/review/start',{method:'POST',headers:{Origin:'https://attacker.example','Content-Type':'application/json'},body:'{}'});
    assert.equal(origin.status,403);
    assert.deepEqual(await reuse.ensure(workspace),first);
    assert.equal(reuse.child,null);
    await reuse.dispose();
    assert.equal(manager.child.exitCode,null);
    const child=manager.child;
    await manager.dispose();
    assert.ok(child.exitCode!==null||child.signalCode!==null);
    await assert.rejects(manager.ensure(workspace),/shutting down/);
  } finally {
    await manager.dispose();await reuse.dispose();
    if(originalPath===undefined)delete process.env.PATH;else process.env.PATH=originalPath;
    if(originalHome===undefined)delete process.env.PYTHONHOME;else process.env.PYTHONHOME=originalHome;
    if(originalPythonPath===undefined)delete process.env.PYTHONPATH;else process.env.PYTHONPATH=originalPythonPath;
    await fs.rm(base,{recursive:true,force:true});await fs.rm(state,{recursive:true,force:true});
  }
});
