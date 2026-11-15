import asyncio
import base64
import io
import json
from pathlib import Path
import httpx
from PIL import Image


def test_bridge_returns_real_mcp_image_content_and_saved_file(tmp_path):
    from client.spark_image_tools import ImageBridge, build_server
    b=io.BytesIO();Image.new('RGB',(8,8),'green').save(b,format='PNG')
    tid='task-'+'1'*32;fid='file-'+'2'*32
    seen=[]
    def backend(req):
        seen.append(req)
        assert req.headers['authorization']=='Bearer test-secret-token'
        if req.url.path=='/v1/me':return httpx.Response(200,json={'owner':'A'})
        if req.url.path=='/v1/tasks' and req.method=='POST':return httpx.Response(202,json={'id':tid,'status':'queued'})
        if req.url.path=='/v1/tasks/'+tid:return httpx.Response(200,json={'id':tid,'status':'completed','result':{'file_id':fid,'model':'spark-image'}})
        if req.url.path=='/v1/files/'+fid+'/content':return httpx.Response(200,content=b.getvalue())
        return httpx.Response(404)
    async def check():
        bridge=ImageBridge('https://192.168.10.77:18443/v1','test-secret-token',Path('certificates/agent-root-ca.crt'),tmp_path,journal_path=tmp_path/'requests.sqlite3',transport=httpx.MockTransport(backend))
        server=build_server(bridge)
        listed=await server.list_tools()
        assert {t.name for t in listed}=={'generate_image','edit_image','get_image_task','cancel_image_task','list_image_tasks'}
        result=await server.call_tool('generate_image',{'prompt':'生成电商场景'})
        assert not getattr(result,'isError',False)
        result=await server.call_tool('get_image_task',{'task_id':tid,'wait_seconds':0})
        content=result[0] if isinstance(result,tuple) else result
        image=next(x for x in content if x.type=='image')
        assert image.mimeType=='image/png' and base64.b64decode(image.data)==b.getvalue()
        assert (tmp_path/(fid+'.png')).read_bytes()==b.getvalue()
        await bridge.close()
    asyncio.run(check())
