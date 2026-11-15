"""Pinned resumable ranged downloads, prioritizing the fast generation bundle."""
import concurrent.futures, hashlib, json, shutil, time, urllib.request
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
E=BASE/'evidence/image-deploy-20261114'
root=Path('/data/models/agent-mm-z-image-turbo'); chunk=32*1024*1024
hf=json.loads((E/'model-manifest.json').read_text());ms={x['Path']:x for x in json.loads((E/'modelscope-manifest.json').read_text())}
manifest=[{'repo':'Comfy-Org/z_image_turbo','hf_repo':hf['repo'],'hf_revision':hf['revision'],'path':x['rfilename'],'sha256':x['lfs']['sha256'],'size':x['size'],'revision':ms[x['rfilename']]['Revision']} for x in hf['files']]
manifest+=json.loads((E/'editor-model-manifest.json').read_text())
def locations(item):
 p=root/Path(item['path']).relative_to('split_files');return p,root/'.downloadparts'/p.name
for item in manifest:
 p,parts=locations(item);p.parent.mkdir(parents=True,exist_ok=True);parts.mkdir(parents=True,exist_ok=True)
 partial=p.with_suffix('.partial')
 if not p.exists() and partial.exists():
  with partial.open('rb') as source:
   for start in range(0,partial.stat().st_size-chunk+1,chunk):
    target=parts/str(start)
    if target.exists():source.seek(chunk,1);continue
    with target.open('wb') as out:shutil.copyfileobj(io:=__import__('io').BytesIO(source.read(chunk)),out)

def fetch(item,start):
 p,parts=locations(item);end=min(item['size'],start+chunk)-1;target=parts/str(start)
 if target.exists() and target.stat().st_size==end-start+1:return
 url=f"https://modelscope.cn/models/{item['repo']}/resolve/{item['revision']}/{item['path']}?part={start}"
 for attempt in range(8):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'}),timeout=90) as response:
    if response.status!=206 or response.headers.get('Content-Range')!=f"bytes {start}-{end}/{item['size']}":raise RuntimeError('Invalid range response')
    with target.with_suffix('.partial').open('wb') as out:shutil.copyfileobj(response,out,1024*1024)
   if target.with_suffix('.partial').stat().st_size!=end-start+1:raise RuntimeError('Incomplete range')
   target.with_suffix('.partial').rename(target);return
  except Exception:
   if attempt==7:raise
   time.sleep(min(10,attempt+1))
verified=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
 batches=[]
 for item in manifest:
  p,parts=locations(item)
  futures=[] if p.exists() else [pool.submit(fetch,item,start) for start in range(0,item['size'],chunk)]
  batches.append((item,futures))
 for number,(item,futures) in enumerate(batches):
  p,parts=locations(item)
  for i,future in enumerate(futures,1):
   future.result()
   if i%32==0:print('RANGES',p.name,i,'/',len(futures),flush=True)
  if not p.exists():
   with p.with_suffix('.assembled').open('wb') as out:
    for start in range(0,item['size'],chunk):
     with (parts/str(start)).open('rb') as source:shutil.copyfileobj(source,out,8*1024*1024)
   p.with_suffix('.assembled').rename(p)
  with p.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
  if digest!=item['sha256'] or p.stat().st_size!=item['size']:raise RuntimeError('Integrity mismatch: '+p.name)
  verified.append({**item,'local':str(p)})
  print('VERIFIED',p.name,digest,flush=True)
  if number==2:
   (E/'models-verified.json').write_text(json.dumps(verified,indent=2));(root/'.verified.json').write_text(json.dumps(verified,indent=2))
(E/'editor-models-verified.json').write_text(json.dumps(verified[3:],indent=2));(root/'.editor-verified.json').write_text(json.dumps(verified[3:],indent=2))
