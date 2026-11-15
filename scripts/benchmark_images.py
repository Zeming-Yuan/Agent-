"""Authenticated end-to-end image smoke samples with memory/latency evidence."""
import asyncio,json,statistics,time
from pathlib import Path
import httpx
import ssl

BASE=Path(__file__).resolve().parents[1];E=BASE/'evidence/image-deploy-20261114';(E/'samples').mkdir(exist_ok=True)
PROMPTS=[
'商业产品摄影，一只哑光白色保温杯放在米色石台上，暖白色简洁背景，柔和侧光，真实细腻材质，电商主图，无文字无水印',
'电商护肤品场景，一只透明磨砂玻璃面霜罐，白色盖子，清晨窗光，浅米色亚麻与浅色大理石，画面整洁，高端商业摄影，无文字',
'日常公众号配图，阳光下的木质书桌，一本打开的书、一杯咖啡和绿植，温暖自然光，真实摄影，右上留白，无文字',
'极简电商场景背景，浅灰色摄影棚，中央白色圆柱展示台，柔和自然阴影，干净构图，没有商品、人物或文字',
'商业美食摄影，一碗热气腾腾的牛肉面，青菜与细葱花，暖色餐桌，自然窗边光，食材真实，细节清楚，无文字',
'日常商务文章配图，现代简洁办公室，木质桌面和笔记本电脑，窗外城市，午后自然光，干净克制，无人物无文字',
'蓝色运动鞋电商产品摄影，纯白背景，一双鞋的三分之四角度，清晰鞋带、网布和橡胶鞋底，柔和接触阴影，无文字无水印',
'日常旅行配图，江南小镇雨后石板路，白墙黛瓦，薄雾与柔和晨光，真实摄影，自然色彩，无文字无水印',
'自然风电商背景，浅米色沙地和远处柔和的绿植虚化，前景中央留出展示商品的位置，清晨侧光，无商品无文字',
'简洁写实的家庭厨房场景，白色台面、浅木色橱柜，窗边明亮自然光，中央台面留白，用于小家电电商背景，无文字',
'玻璃香水瓶商业摄影，透明方瓶和黑色瓶盖，深灰石板与柔和轮廓光，真实折射、精致材质，无品牌无文字',
'极简中文主题配图，浅蓝色背景，白色展示台，一束自然窗光，留出上方标题空间，无文字无水印',
'日常科技文章配图，简洁现代数据中心机房，整齐服务器机柜，白色与蓝灰色灯光，真实摄影，清晰自然，无文字',
'电商食品摄影，一盘新鲜草莓，浅色陶瓷盘、木质桌面和柔和窗光，真实果实纹理，自然红色，无文字',
'商业摄影，一只精致白色陶瓷花瓶和单枝白色郁金香，米色背景，柔和阴影，居家装饰产品配图，无文字',
'简洁夏季活动背景，淡黄色背景，少量柠檬切片和绿色叶片放在画面边缘，中央留白，清新明亮，无文字',
'电商包袋摄影，一只无品牌棕色皮质手提包，浅米色摄影棚背景，三分之四角度，真实皮革纹理和清晰缝线，无文字',
'柔和自然光下的现代客厅，米色沙发、浅木色茶几、绿色植物，简洁生活方式商业摄影，无人物无文字',
'电商耳机产品摄影，一副黑色头戴耳机，浅灰背景，侧面三分之四角度，材质真实、细节清楚，柔和阴影，无文字',
'蓝白色简洁商务背景，磨砂玻璃与白色几何台面，清晨自然光，右侧留白，用于文章配图，无文字无水印']

def mem():
 return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
async def main():
 key=(BASE/'.private/agent-api.key').read_text().strip();ctx=ssl.create_default_context(cafile=str(BASE/'certificates/agent-root-ca.crt'))
 results=[];minimum=mem();running=True
 async def monitor():
  nonlocal minimum
  while running:minimum=min(minimum,mem());await asyncio.sleep(.2)
 async with httpx.AsyncClient(base_url='https://192.168.10.77:18443',verify=ctx,headers={'Authorization':'Bearer '+key},timeout=60,trust_env=False) as client:
  watch=asyncio.create_task(monitor())
  try:
   for i,prompt in enumerate(PROMPTS):
    started=time.monotonic()
    r=await client.post('/v1/tasks',json={'kind':'image_generate','options':{'prompt':prompt,'seed':417+i,'title':'品质生活' if i==11 else ''}},headers={'Idempotency-Key':'image-bench-final-20261114-'+str(i)})
    r.raise_for_status();tid=r.json()['id']
    while True:
     state=(await client.get('/v1/tasks/'+tid)).json()
     if state['status'] in ('completed','failed','cancelled'):break
     await asyncio.sleep(.5)
    item={'index':i,'task_id':tid,'status':state['status'],'seconds':round(time.monotonic()-started,3),'prompt':prompt}
    if state['status']=='completed':
     fid=state['result']['file_id'];image=await client.get('/v1/files/'+fid+'/content');image.raise_for_status()
     target=E/'samples'/f'{i:02d}.png';target.write_bytes(image.content);item.update(file_id=fid,path=str(target))
    else:item['error']=state.get('error')
    results.append(item);(E/'benchmark-generation-progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(i,state['status'],item['seconds'],flush=True)
  finally:
   running=False;await watch
 values=sorted(x['seconds'] for x in results if x['status']=='completed')
 summary={'samples':results,'success':len(values),'total':len(results),'min_available_gib':round(minimum/1024**3,3),'p50_seconds':statistics.median(values) if values else None,'p95_seconds':values[max(0,__import__('math').ceil(.95*len(values))-1)] if values else None,'note':'Server-side synthetic image examples; not Mac UI or business quality acceptance. First sample includes cold loading.'}
 (E/'benchmark-generation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='samples'},ensure_ascii=False))
asyncio.run(main())
