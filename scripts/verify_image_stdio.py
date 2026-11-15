"""Exercise the packaged MCP server over real stdio; optional live image task."""
import asyncio,base64,json,sys,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

BASE=Path(__file__).resolve().parents[1]
async def main():
 params=StdioServerParameters(command=sys.executable,args=[str(BASE/'.private/mac-image-tools/spark_image_tools.py'),'--config',str(BASE/'.private/mac-image-tools/spark-image.json')])
 result={}
 async with stdio_client(params) as (read,write):
  async with ClientSession(read,write) as session:
   init=await session.initialize(); result['protocol']=init.protocolVersion
   listed=await session.list_tools();result['tools']=[x.name for x in listed.tools]
   if '--generate' in sys.argv:
    started=time.monotonic();r=await session.call_tool('generate_image',{'prompt':'商业摄影，透明玻璃花瓶插着一枝白色郁金香，暖白色石台，柔和窗边侧光，简洁背景，真实玻璃折射，高级日常配图，无文字无水印','seed':417})
    if r.isError: raise RuntimeError(str(r.content))
    state=json.loads(next(x.text for x in r.content if x.type=='text'));tid=state['id']
    while True:
     r=await session.call_tool('get_image_task',{'task_id':tid,'wait_seconds':20})
     if r.isError:raise RuntimeError(str(r.content))
     images=[x for x in r.content if x.type=='image']
     if images:
      sample=BASE/'evidence/image-deploy-20261114/samples/mcp-live.png';sample.write_bytes(base64.b64decode(images[0].data))
      result.update(path=str(sample),image_received=True,image_base64_bytes=len(images[0].data),seconds=round(time.monotonic()-started,2),task_id=tid)
      break
 result['status']='passed'
 (BASE/'evidence/image-deploy-20261114/mcp-stdio-live.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
asyncio.run(main())
