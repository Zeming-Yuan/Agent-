"""Fetch digest-verified Docker archive without modifying either Docker daemon proxy."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import tarfile
import threading
import time
import requests

BASE=Path(__file__).resolve().parents[1]
CACHE=BASE/'.private/image-cache'
CACHE.mkdir(parents=True,exist_ok=True)
DIGEST='2a7cde230b59f3ce6cab33dd245ba6bee41aa87b38c9fe84f966ff24016813ce'
HOST='https://docker.m.daocloud.io'
REPO='vllm/vllm-openai'
s=requests.Session();s.trust_env=False
token=s.get('https://m.daocloud.io/auth/token',params={'service':'docker.m.daocloud.io','scope':f'repository:{REPO}:pull'},timeout=20).json()['token']
HEADERS={'Authorization':'Bearer '+token}
r=s.get(f'{HOST}/v2/{REPO}/manifests/sha256:{DIGEST}',headers={**HEADERS,'Accept':'application/vnd.docker.distribution.manifest.v2+json'},timeout=20)
r.raise_for_status()
assert hashlib.sha256(r.content).hexdigest()==DIGEST
manifest=r.json()
config=s.get(f"{HOST}/v2/{REPO}/blobs/{manifest['config']['digest']}",headers=HEADERS,timeout=30)
config.raise_for_status()
assert 'sha256:'+hashlib.sha256(config.content).hexdigest()==manifest['config']['digest']
assert json.loads(config.content)['architecture']=='arm64'
config_path=CACHE/(manifest['config']['digest'].split(':')[1]+'.json')
config_path.write_bytes(config.content)


def fetch(layer):
    digest=layer['digest'].split(':')[1];size=layer['size'];path=CACHE/(digest+'.tar');part=CACHE/(digest+'.part')
    journal=CACHE/(digest+'.chunks.json')
    if path.exists():
        with path.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()==digest:
                return path
        raise RuntimeError('Previously completed blob checksum mismatch')
    chunk_size=32*1024*1024
    count=(size+chunk_size-1)//chunk_size
    done=set(json.loads(journal.read_text())) if journal.exists() else set()
    fd=os.open(part,os.O_RDWR|os.O_CREAT,0o600)
    os.ftruncate(fd,size)
    lock=threading.Lock()
    def chunk(i):
        if i in done:return
        start=i*chunk_size;end=min(size,start+chunk_size)-1
        for attempt in range(5):
            try:
                session=requests.Session();session.trust_env=False
                with session.get(f"{HOST}/v2/{REPO}/blobs/{layer['digest']}",headers={**HEADERS,'Range':f'bytes={start}-{end}'},stream=True,timeout=(15,60)) as response:
                    response.raise_for_status()
                    if response.status_code!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):
                        raise RuntimeError('Registry does not support correct byte ranges')
                    offset=start
                    for data in response.iter_content(1024*1024):
                        if offset+len(data)>end+1:raise RuntimeError('Too much blob data')
                        os.pwrite(fd,data,offset);offset+=len(data)
                    if offset!=end+1:raise RuntimeError('Incomplete range')
                with lock:
                    done.add(i)
                    temp=journal.with_suffix('.tmp')
                    temp.write_text(json.dumps(sorted(done)));temp.replace(journal)
                    if len(done)%16==0 or len(done)==count:
                        print(digest[:12],f'{len(done)}/{count} chunks',flush=True)
                return
            except (requests.RequestException,RuntimeError) as exc:
                if attempt==4:raise
                time.sleep(2)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(chunk,range(count)))
        os.fsync(fd)
    finally:
        os.close(fd)
    with part.open('rb') as f:
        actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=digest:
        journal.unlink(missing_ok=True)
        raise RuntimeError('Blob SHA256 mismatch; rerun to re-fetch ranges')
    part.replace(path)
    print('VERIFIED',digest,flush=True)
    return path

layers=[]
for layer in manifest['layers']:
    layers.append(fetch(layer))
archive=CACHE/'main-arm64.docker.tar'
with tarfile.open(archive,'w') as tar:
    tar.add(config_path,arcname=config_path.name)
    for layer in layers:
        tar.add(layer,arcname=layer.name)
    docker_manifest=CACHE/'manifest.json'
    docker_manifest.write_text(json.dumps([{'Config':config_path.name,'RepoTags':['agent-mm-main:v0.28.0-arm64'],'Layers':[p.name for p in layers]}]))
    tar.add(docker_manifest,arcname='manifest.json')
(BASE/'evidence/main-image-verified.json').write_text(json.dumps({'manifest_sha256':DIGEST,'image_id':manifest['config']['digest'],'architecture':'arm64','source':'DaoCloud cache; every blob validated against pinned official manifest','archive':str(archive)},indent=2))
print('ARCHIVE READY',archive,flush=True)
