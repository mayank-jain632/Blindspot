'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const root=process.env.BLINDSPOT_TEST_EXTENSION||path.resolve(__dirname,'..');
const {bundledPython}=require(path.join(root,'runtime'));

test('runtime refuses a wrong-platform package and corrupted archive before extraction',async()=>{
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'blindspot-runtime-check-'));
  try {
    const metadata=path.join(directory,'manifest.json');
    await fs.writeFile(metadata,JSON.stringify({target:'unsupported-target',sha256:'0'.repeat(64)}));
    await assert.rejects(bundledPython(directory,directory),/Install the/);
    await fs.writeFile(metadata,JSON.stringify({target:process.platform+'-'+process.arch,sha256:'0'.repeat(64)}));
    await fs.writeFile(path.join(directory,'python.tar.gz'),'corrupted');
    await assert.rejects(bundledPython(directory,directory),/verification failed/);
    await assert.rejects(fs.access(path.join(directory,'runtimes')));
  } finally {await fs.rm(directory,{recursive:true,force:true});}
});
