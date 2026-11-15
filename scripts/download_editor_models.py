"""Resumable ranged download; every model is checked against pinned HF SHA-256."""
import concurrent.futures, hashlib, json, shutil, time, urllib.request
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
manifest=json.loads((BASE/'evidence/image-deploy-20261114/editor-model-manifest.json').read_text())
root=Path('/data/models/agent-mm-z-image-turbo')
chunk=32*1024*1024
jobs=[]
for item in manifest:
 p=root/Path(item['path']).relative_to('split_files'); p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists(): continue
 parts=root/'.downloadparts'/p.name; parts.mkdir(parents=True,exist_ok=True)
 for start in range(0,item['size'],chunk): jobs.append((item,start,min(item['size'],start+chunk)-1,parts))
def fetch(job):
 item,start,end,parts=job; target=parts/str(start)
 if target.exists() and target.stat().st_size==end-start+1: return
 url=f"https://modelscope.cn/models/{item['repo']}/resolve/{item['revision']}/{item['path']}?part={start}"
 for attempt in range(8):
  try:
   request=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'})
   with urllib.request.urlopen(request,timeout=90) as response:
    if response.status!=206 or response.headers.get('Content-Range')!=f"bytes {start}-{end}/{item['size']}": raise RuntimeError('Invalid range response')
    with target.with_suffix('.partial').open('wb') as out: shutil.copyfileobj(response,out,1024*1024)
   if target.with_suffix('.partial').stat().st_size!=end-start+1: raise RuntimeError('Incomplete range')
   target.with_suffix('.partial').rename(target)
   return
  except Exception:
   if attempt==7: raise
   time.sleep(min(10,attempt+1))
with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
 for i,_ in enumerate(pool.map(fetch,jobs),1):
  if i%16==0: print('RANGES',i,'/',len(jobs),flush=True)
results=[]
for item in manifest:
 p=root/Path(item['path']).relative_to('split_files')
 if not p.exists():
  parts=root/'.downloadparts'/p.name
  with p.with_suffix('.assembled').open('wb') as out:
   for start in range(0,item['size'],chunk):
    with (parts/str(start)).open('rb') as source: shutil.copyfileobj(source,out,8*1024*1024)
  p.with_suffix('.assembled').rename(p)
 with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
 if digest!=item['sha256'] or p.stat().st_size!=item['size']: raise RuntimeError('Integrity mismatch: '+p.name)
 print('VERIFIED',p.name,digest,flush=True)
 results.append({**item,'local':str(p)})
(BASE/'evidence/image-deploy-20261114/editor-models-verified.json').write_text(json.dumps(results,indent=2))
(root/'.editor-verified.json').write_text(json.dumps(results,indent=2))
