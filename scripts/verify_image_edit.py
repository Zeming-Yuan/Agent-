"""Real reference editing, SDK-style multipart, composition and cancellation checks."""
import asyncio,io,json,ssl,time
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
BASE=Path(__file__).resolve().parents[1];E=BASE/'evidence/image-deploy-20261114'

def mem():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024

async def main():
 if not Path('/data/models/agent-mm-z-image-turbo/.editor-verified.json').exists():raise SystemExit('Editor weights are not verified')
 ctx=ssl.create_default_context(cafile=str(BASE/'certificates/agent-root-ca.crt'));minimum=mem();running=True;out={}
 async def monitor():
  nonlocal minimum
  while running:minimum=min(minimum,mem());await asyncio.sleep(.2)
 async with httpx.AsyncClient(base_url='https://192.168.10.77:18443',verify=ctx,headers={'Authorization':'Bearer '+(BASE/'.private/agent-api.key').read_text().strip()},timeout=600,trust_env=False) as c:
  watch=asyncio.create_task(monitor())
  async def upload(path):
   with path.open('rb') as f:r=await c.post('/v1/files',files={'file':(path.name,f,'image/png')})
   r.raise_for_status();return r.json()['id']
  async def wait(tid,name):
   while True:
    r=await c.get('/v1/tasks/'+tid);r.raise_for_status();state=r.json()
    if state['status'] in ('completed','failed','cancelled'):break
    await asyncio.sleep(.5)
   if state['status']!='completed':raise RuntimeError(str(state))
   r=await c.get('/v1/files/'+state['result']['file_id']+'/content');r.raise_for_status();target=E/'samples'/name;target.write_bytes(r.content)
   return {'task_id':tid,'result':state['result'],'path':str(target)}
  try:
   source=E/'samples/00.png';fid=await upload(source)
   started=time.monotonic();r=await c.post('/v1/tasks',json={'kind':'image_edit','options':{'prompt':'将保温杯的白色杯身和杯盖改为深海蓝色，保持杯子的形状、按钮、视角、背景、石台和光线不变。真实产品摄影。','image_ids':[fid],'quality':'fast','seed':417}})
   r.raise_for_status();out['single_edit']=await wait(r.json()['id'],'edit-blue-cup.png');out['single_edit']['seconds']=round(time.monotonic()-started,3)
   (E/'edit-verification-progress.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('SINGLE_EDIT',out['single_edit']['seconds'],flush=True)
   first=Path(out['single_edit']['path']);second=E/'samples/03.png';started=time.monotonic()
   with first.open('rb') as a,second.open('rb') as b:
    r=await c.post('/v1/images/edits',data={'model':'spark-image-edit','prompt':'将图1的蓝色保温杯放在图2中央的白色展示台上，保留图1保温杯的颜色、按钮和外形，使用图2的浅灰摄影棚背景及柔和阴影。真实电商产品摄影。','quality':'fast','seed':'418'},files=[('image[]',('cup.png',a,'image/png')),('image[]',('background.png',b,'image/png'))])
   r.raise_for_status();data=r.json();import base64
   target=E/'samples/edit-multi-reference.png';target.write_bytes(base64.b64decode(data['data'][0]['b64_json']))
   out['sdk_multi_edit']={'task_id':data['task_id'],'path':str(target),'seconds':round(time.monotonic()-started,3),'status':r.status_code}
   (E/'edit-verification-progress.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('MULTI_EDIT',out['sdk_multi_edit']['seconds'],flush=True)
   # A transparent synthetic product fixture makes exact foreground preservation testable.
   foreground=Image.new('RGBA',(180,300),(0,0,0,0));draw=ImageDraw.Draw(foreground);draw.rounded_rectangle((10,5,170,295),radius=16,fill=(180,30,40,255));draw.rectangle((30,100,150,170),fill=(255,255,255,255))
   path=E/'samples/product-transparent-fixture.png';foreground.save(path);product=await upload(path)
   started=time.monotonic();r=await c.post('/v1/tasks',json={'kind':'image_generate','options':{'prompt':'极简电商背景，米色摄影棚和白色台面，柔和侧光，中央留白，无商品无文字','foreground_file_id':product,'title':'品质生活','seed':419}});r.raise_for_status()
   out['composition']=await wait(r.json()['id'],'product-composition.png');out['composition']['seconds']=round(time.monotonic()-started,3)
   im=Image.open(out['composition']['path']);assert im.getpixel((512,800))==(180,30,40)
   # Cancel during live image inference, then verify a new job still completes.
   r=await c.post('/v1/tasks',json={'kind':'image_generate','options':{'prompt':'一片自然森林，清晨阳光，真实摄影','seed':420}});r.raise_for_status();tid=r.json()['id']
   for _ in range(100):
    state=(await c.get('/v1/tasks/'+tid)).json()
    if state['status']=='running':break
    await asyncio.sleep(.1)
   await asyncio.sleep(1);cancelled=await c.post('/v1/tasks/'+tid+'/cancel');cancelled.raise_for_status();assert cancelled.json()['status']=='cancelled'
   r=await c.post('/v1/tasks',json={'kind':'image_generate','options':{'prompt':'一枝白色郁金香，浅米色简洁背景，真实摄影','seed':421}});r.raise_for_status();out['after_cancel']=await wait(r.json()['id'],'after-cancel.png');out['cancelled_task_id']=tid
   state=(await c.get('/v1/tasks/'+tid)).json();assert state['status']=='cancelled'
   out['health']=(await c.get('/health')).json();assert out['health']['status']=='ready'
  finally:
   running=False;await watch
 out['min_available_gib']=round(minimum/1024**3,3);out['status']='passed'
 (E/'edit-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
asyncio.run(main())
