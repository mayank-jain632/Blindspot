'use strict';
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawn,execFile}=require('node:child_process');
const {promisify}=require('node:util');
const {readConnection,discoverConnection,Transport}=require('./transport');
const exec=promisify(execFile);

class ReceiverManager {
  constructor(directory,stateRoot,log=()=>{}) {
    this.directory=directory;this.stateRoot=stateRoot;this.log=log;
    this.pending=null;this.child=null;this.closed=false;
  }
  async ensure(workspace) {
    if(this.closed)throw new Error('Blindspot is shutting down.');
    try {return await discoverConnection(workspace);}
    catch(error) {if(error.code!=='no_receiver')throw error;}
    if(!this.pending)this.pending=this.launch(workspace).finally(()=>{this.pending=null;});
    return this.pending;
  }
  async launch(workspace) {
    if(process.platform==='win32')throw new Error('Blindspot currently supports macOS and Linux.');
    try {await fs.access(path.join(this.directory,'blindspot','__main__.py'));}
    catch {throw new Error('Bundled receiver is missing. Reinstall the packaged Blindspot extension, or connect to a manually started receiver.');}
    const env={...process.env,PYTHONPATH:this.directory,PYTHONNOUSERSITE:'1'};
    let python;
    for(const candidate of ['python3.11','python3.12','python3.13','python3','/opt/homebrew/bin/python3.11','/opt/homebrew/bin/python3.12','/opt/homebrew/bin/python3.13']) {
      try {
        await exec(candidate,['-s','-P','-c','import sys,sqlite3,fcntl,xml.parsers.expat; assert sys.version_info >= (3,11); import blindspot'],{env,cwd:this.directory,timeout:5000});
        python=candidate;break;
      } catch {}
    }
    if(!python)throw new Error('Blindspot needs a working Python 3.11+ installation. Install Python, then try Start recording again.');
    if(this.closed)throw new Error('Blindspot is shutting down.');
    const state=path.join(this.stateRoot,crypto.createHash('sha256').update(workspace).digest('hex'));
    await fs.mkdir(state,{recursive:true,mode:0o700});
    if(this.closed)throw new Error('Blindspot is shutting down.');
    let failure=null,ended=false,details='';
    const child=spawn(python,['-s','-P','-m','blindspot','observer','serve','--workspace',workspace,'--state-dir',state,'--port','0'],{env,cwd:this.directory,stdio:['ignore','pipe','pipe']});
    this.child=child;
    child.on('error',error=>{failure=error;});
    child.on('exit',()=>{ended=true;if(this.child===child)this.child=null;});
    child.stdout.on('data',data=>this.log(data.toString()));
    child.stderr.on('data',data=>{details=(details+data.toString()).slice(-2000);this.log(data.toString());});
    const deadline=Date.now()+15000;
    while(Date.now()<deadline&&!this.closed&&!ended&&!failure) {
      try {
        const connection=await readConnection(path.join(state,'connection.json'));
        const health=await new Transport(connection,()=>{}).health();
        if(health.workspace===workspace)return connection;
      } catch {}
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    if(!ended)child.kill('SIGINT');
    throw new Error('Could not start the Blindspot receiver. '+(failure?.message||details.trim()||'Startup timed out.'));
  }
  async dispose() {
    this.closed=true;
    const child=this.child;
    if(!child)return;
    await new Promise(resolve=>{
      const timer=setTimeout(()=>{child.kill('SIGKILL');resolve();},3000);
      child.once('exit',()=>{clearTimeout(timer);resolve();});
      child.kill('SIGINT');
    });
  }
}
module.exports={ReceiverManager};
