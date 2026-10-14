'use strict';
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const {createReadStream,createWriteStream}=require('node:fs');
const {createGunzip}=require('node:zlib');
const {pipeline}=require('node:stream/promises');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const exec=promisify(execFile);

async function bundledPython(directory,storage) {
  const metadata=JSON.parse(await fs.readFile(path.join(directory,'manifest.json'),'utf8'));
  const target=process.platform+'-'+process.arch;
  if(metadata.target!==target)throw new Error(`This Blindspot package is for ${metadata.target}. Install the ${target} package from Marketplace.`);
  const archive=path.join(directory,'python.tar.gz');
  const digest=crypto.createHash('sha256').update(await fs.readFile(archive)).digest('hex');
  if(digest!==metadata.sha256)throw new Error('Bundled runtime verification failed. Reinstall Blindspot.');
  const parent=path.join(storage,'runtimes');
  const destination=path.join(parent,metadata.sha256);
  const executable=path.join(destination,'python/bin/python3');
  try {await fs.access(executable,fs.constants.X_OK);return executable;} catch {}
  await fs.mkdir(parent,{recursive:true,mode:0o700});
  const temporary=await fs.mkdtemp(path.join(parent,'extract-'));
  try {
    // The archive is bundled and checksum-pinned; no runtime download is performed.
    const tar=path.join(temporary,'runtime.tar');
    await pipeline(createReadStream(archive),createGunzip(),createWriteStream(tar,{mode:0o600}));
    await exec('/usr/bin/tar',['-xf',tar,'-C',temporary],{timeout:60000});
    await fs.unlink(tar);
    await fs.access(path.join(temporary,'python/bin/python3'),fs.constants.X_OK);
    try {await fs.rename(temporary,destination);}
    catch(error) {if(!['EEXIST','ENOTEMPTY'].includes(error.code))throw error;}
  } finally {await fs.rm(temporary,{recursive:true,force:true});}
  await fs.access(executable,fs.constants.X_OK);
  return executable;
}
module.exports={bundledPython};
