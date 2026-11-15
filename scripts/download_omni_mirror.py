"""Download official Qwen mirror, requiring exact pinned Hugging Face hashes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import requests
from huggingface_hub import snapshot_download
BASE=Path(__file__).resolve().parents[1]
ROOT=Path('/data/models/huggingface/Qwen2.5-Omni-7B')
HF=json.loads((BASE/'evidence/omni-official-weights-manifest.json').read_text())
MS={f['Path']:f for f in json.loads((BASE/'evidence/omni-modelscope-filelist.json').read_text())['Data']['Files']}

def download(entry):
    name=entry['name'];target=ROOT/name;part=ROOT/(name+'.mirror-part')
    meta=MS[name]
    assert meta['Sha256']==entry['sha256'] and meta['Size']==entry['size']
    if target.exists():
        with target.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()==entry['sha256']:
                return
        raise RuntimeError('Existing target checksum mismatch: '+name)
    url=f"https://modelscope.cn/models/Qwen/Qwen2.5-Omni-7B/resolve/{meta['Revision']}/{name}"
    for attempt in range(5):
        start=part.stat().st_size if part.exists() else 0
        try:
            with requests.get(url,headers={'Range':f'bytes={start}-'} if start else {},stream=True,timeout=(15,60)) as r:
                r.raise_for_status()
                if start and (r.status_code!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {start}-')):
                    raise RuntimeError('Mirror did not honor resume')
                with part.open('ab' if start else 'wb') as out:
                    for chunk in r.iter_content(8*1024*1024):
                        out.write(chunk)
            if part.stat().st_size!=entry['size']:
                raise RuntimeError('Incomplete mirror transfer')
            break
        except (requests.RequestException,RuntimeError) as exc:
            print(name,'attempt',attempt+1,type(exc).__name__,flush=True)
            if attempt==4:raise
            time.sleep(3)
    with part.open('rb') as f:
        digest=hashlib.file_digest(f,'sha256').hexdigest()
    if digest!=entry['sha256']:
        raise RuntimeError('Mirror SHA256 mismatch: '+name)
    part.replace(target)
    print('Verified',name,flush=True)

print('Official mirror hashes match pinned HF revision:',HF['revision'],flush=True)
with ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(download,HF['files']))
# Fetch tokenizer/processor/config from the pinned authoritative repository.
snapshot_download('Qwen/Qwen2.5-Omni-7B',revision=HF['revision'],local_dir=ROOT,
    allow_patterns=['*.json','*.jinja','*.tiktoken','*.txt','*.model','*.pt'],max_workers=4)
aux=MS['spk_dict.pt']
with (ROOT/'spk_dict.pt').open('rb') as handle:
    assert hashlib.file_digest(handle,'sha256').hexdigest()==aux['Sha256']
(ROOT/'.verified.json').write_text(json.dumps({'repo':'Qwen/Qwen2.5-Omni-7B','revision':HF['revision'],'weights':HF['files'],'source':'Official Qwen ModelScope mirror; all weights match HF SHA256'},indent=2))
print('CHECKPOINT VERIFIED',flush=True)
