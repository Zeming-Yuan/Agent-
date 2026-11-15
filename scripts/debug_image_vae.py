"""Isolate Qwen VAE reconstruction from denoising on the private backend."""
import httpx,time,uuid,json,io
from pathlib import Path
from PIL import Image
import numpy as np
b=Path(__file__).resolve().parents[1];e=b/'evidence/image-deploy-20261114'
with httpx.Client(base_url='http://127.0.0.1:18013',timeout=60,trust_env=False) as c:
 for _ in range(100):
  q=c.get('/queue').json()
  if not q['queue_running'] and not q['queue_pending']:break
  time.sleep(.2)
 with (e/'samples/00.png').open('rb') as f:r=c.post('/upload/image',files={'image':('debug_ref.png',f,'image/png')},data={'overwrite':'true'})
 r.raise_for_status();name=r.json()['name']
 graph={'1':{'class_type':'LoadImage','inputs':{'image':name}},'2':{'class_type':'VAELoader','inputs':{'vae_name':'qwen_image_vae.safetensors'}},'3':{'class_type':'VAEEncode','inputs':{'pixels':['1',0],'vae':['2',0]}},'4':{'class_type':'VAEDecode','inputs':{'samples':['3',0],'vae':['2',0]}},'5':{'class_type':'SaveImage','inputs':{'images':['4',0],'filename_prefix':'agent-mm/task-debug-vae'}}}
 r=c.post('/prompt',json={'prompt':graph,'prompt_id':str(uuid.uuid4())});r.raise_for_status();pid=r.json()['prompt_id']
 for _ in range(300):
  h=c.get('/history/'+pid).json().get(pid)
  if h:break
  time.sleep(.2)
 print(h['status']);out=h['outputs']['5']['images'][0]
 r=c.get('/view',params=out);r.raise_for_status();target=e/'samples/debug-vae-roundtrip.png';target.write_bytes(r.content)
 a=np.asarray(Image.open(e/'samples/00.png').convert('RGB'),dtype=np.float32);d=np.asarray(Image.open(target).convert('RGB'),dtype=np.float32)
 result={'mae':float(np.mean(np.abs(a-d))),'status':h['status'],'path':str(target)}
 (e/'vae-roundtrip.json').write_text(json.dumps(result,indent=2));print('MAE',result['mae'])
 c.post('/history',json={'delete':[pid]})
 assert result['mae']<15,'Qwen VAE reconstruction is corrupted'
