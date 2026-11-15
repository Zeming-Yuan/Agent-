"""Check the unaccelerated editor after the image-codec fix."""
import json,ssl,time
from pathlib import Path
import httpx
b=Path(__file__).resolve().parents[1];e=b/'evidence/image-deploy-20261114'
with httpx.Client(base_url='https://192.168.10.77:18443',verify=ssl.create_default_context(cafile=str(b/'certificates/agent-root-ca.crt')),headers={'Authorization':'Bearer '+(b/'.private/agent-api.key').read_text().strip()},timeout=60,trust_env=False) as c:
 with (e/'samples/00.png').open('rb') as f:r=c.post('/v1/files',files={'file':('source.png',f,'image/png')})
 r.raise_for_status();fid=r.json()['id'];started=time.monotonic()
 r=c.post('/v1/tasks',json={'kind':'image_edit','options':{'prompt':'将保温杯的白色杯身和杯盖改为深海蓝色，保留外形、按钮、背景和石台，真实产品摄影。','image_ids':[fid],'quality':'standard','seed':417}})
 r.raise_for_status();tid=r.json()['id'];minimum=2**63
 while True:
  minimum=min(minimum,int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024)
  state=c.get('/v1/tasks/'+tid).json()
  if state['status'] in ('completed','failed','cancelled'):break
  time.sleep(.5)
 out={'task_id':tid,'status':state['status'],'seconds':round(time.monotonic()-started,3),'min_available_gib':round(minimum/1024**3,3)}
 if state['status']=='completed':
  r=c.get('/v1/files/'+state['result']['file_id']+'/content');r.raise_for_status();p=e/'samples/edit-standard-blue-cup.png';p.write_bytes(r.content);out['path']=str(p)
 else:out['error']=state.get('error')
 (e/'standard-edit-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
 if state['status']!='completed':raise SystemExit(1)
