'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {execFileSync}=require('node:child_process');
const {ReceiverManager}=require('../receiver');
let available=false;
try {execFileSync('python3.11',['-c','import sqlite3,fcntl,xml.parsers.expat'],{stdio:'ignore'});available=true;} catch {}
test('managed receiver starts once, serves bundled dashboard, is reusable and shuts down only its owned process',{skip:!available,timeout:30000},async()=>{
  const base=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-managed-'));
  const workspace=await fs.realpath(base);
  execFileSync('git',['init',workspace],{stdio:'ignore'});
  await fs.writeFile(path.join(workspace,'example.py'),'value = 1\n');
  // Release builds bundle this directory; source checkout is used by development tests.
  const directory=process.env.BLINDSPOT_TEST_EXTENSION ? path.join(process.env.BLINDSPOT_TEST_EXTENSION,'receiver') : path.resolve(__dirname,'../../');
  const state=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-managed-state-'));
  const manager=new ReceiverManager(directory,state),reuse=new ReceiverManager(directory,state);
  try {
    const [first,second]=await Promise.all([manager.ensure(workspace),manager.ensure(workspace)]);
    assert.deepEqual(first,second);
    assert.ok(manager.child);
    const response=await fetch(first.endpoint+'/api/health',{headers:{Authorization:'Bearer '+first.token}});
    assert.equal((await response.json()).workspace,workspace);
    const page=await fetch(first.endpoint+'/');
    assert.equal(page.status,200);
    const html=await page.text();
    const asset=html.match(/src="(\/assets\/[^\"]+\.js)"/);
    assert.ok(asset,'built dashboard JavaScript is linked');
    assert.equal((await fetch(first.endpoint+asset[1])).status,200);
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
    await fs.rm(base,{recursive:true,force:true});await fs.rm(state,{recursive:true,force:true});
  }
});
