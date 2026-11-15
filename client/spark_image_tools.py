"""Mac/Linux stdio MCP bridge for the private Spark image service."""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import re
import ssl
import tempfile
import uuid
import warnings
from pathlib import Path
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent
from PIL import Image
if __package__:
    from .request_journal import RequestJournal
else:
    from request_journal import RequestJournal


def save_png_atomically(target, data):
    if len(data)>32*1024*1024:raise ValueError('Invalid image response size')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format!='PNG' or min(image.size)<=0:raise ValueError('Invalid PNG')
                image.verify()
            with Image.open(io.BytesIO(data)) as image:image.load()
    except (OSError,SyntaxError,ValueError,Image.DecompressionBombWarning,Image.DecompressionBombError) as exc:
        raise ValueError('Invalid PNG') from exc
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(prefix='.image-',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(name,target)
    finally:
        Path(name).unlink(missing_ok=True)


class ImageBridge:
    def __init__(self,base_url,token,ca_path,output_dir,*,journal_path=None,transport=None):
        url=httpx.URL(base_url.rstrip('/'))
        if url.scheme!='https' or not url.host or url.path!='/v1' or url.userinfo or url.query or url.fragment:
            raise ValueError('Use the HTTPS service URL ending in /v1')
        self.output_dir=Path(output_dir).expanduser()
        self.service=str(url)
        self.journal_path=Path(journal_path).expanduser() if journal_path is not None else Path.home()/'.local/state/spark-image-tools/requests.sqlite3'
        self.client=httpx.AsyncClient(base_url=base_url.rstrip('/')+'/',headers={'Authorization':'Bearer '+token},
            verify=ssl.create_default_context(cafile=str(ca_path)),timeout=30,trust_env=False,transport=transport)

    async def close(self):await self.client.aclose()

    async def request(self,method,path,**kwargs):
        response=await self.client.request(method,path,**kwargs)
        if not response.is_success:
            # Only status and response body; never request headers or key.
            raise RuntimeError(f'Spark HTTP {response.status_code}: {response.text[:1000]}')
        return response

    async def upload(self,path):
        source=Path(path).expanduser().resolve()
        if not source.is_file() or source.stat().st_size>12*1024*1024:raise ValueError('Upload an image file up to 12MiB')
        with source.open('rb') as file:
            response=await self.request('POST','files',files={'file':(source.name,file)})
        return response.json()['id']

    async def journal(self):
        identity=(await self.request('GET','me')).json()
        owner=identity.get('owner')
        if not isinstance(owner,str) or not owner:raise RuntimeError('Invalid service identity')
        return RequestJournal(self.journal_path,self.service,owner)

    async def generate(self,prompt,size,seed,title,foreground_path,*,request_id=None):
        options={'prompt':prompt,'size':size,'seed':seed,'title':title}
        return await self.submit('image_generate',options,[foreground_path] if foreground_path else [],request_id)

    async def submit(self,kind,options,paths,request_id):
        journal=await self.journal()
        request_id=request_id if request_id is not None else str(uuid.uuid4())
        materials=[]
        for path in paths:
            source=Path(path).expanduser()
            with source.open('rb') as file:data=file.read(12*1024*1024+1)
            if len(data)>12*1024*1024:raise ValueError('Upload an image file up to 12MiB')
            materials.append((source.name,data))
        identity={'kind':kind,'options':options}
        if materials:identity['materials']=[hashlib.sha256(data).hexdigest() for _,data in materials]
        fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        payload={'kind':kind,'options':options,'materials':[{'sha256':digest,'file_id':None} for digest in identity.get('materials',[])]}
        record=journal.prepare(request_id,fingerprint,payload)
        ids=[]
        for index,(name,data) in enumerate(materials):
            fid=record['payload']['materials'][index]['file_id']
            if fid:
                response=await self.client.get('files/'+fid+'/content')
                if response.status_code==404:fid=None
                elif not response.is_success:raise RuntimeError(f'Spark HTTP {response.status_code}')
            if not fid:
                fid=(await self.request('POST','files',files={'file':(name,data)})).json()['id']
                journal.remember_upload(request_id,index,fid)
            ids.append(fid)
        submitted=dict(options)
        if kind=='image_edit':submitted['image_ids']=ids
        elif ids:submitted['foreground_file_id']=ids[0]
        result=(await self.request('POST','tasks',json={'kind':kind,'options':submitted},headers={'Idempotency-Key':request_id})).json()
        journal.accepted(request_id,result['id'])
        return {**result,'request_id':request_id}

    async def edit(self,prompt,image_paths,size,quality,seed,*,request_id=None):
        if not 1<=len(image_paths)<=3:raise ValueError('Use 1 to 3 local image paths')
        return await self.submit('image_edit',{'prompt':prompt,'size':size,'quality':quality,'seed':seed},image_paths,request_id)

    async def list_tasks(self,status=None,after=None,limit=20):
        journal=await self.journal()
        params={'limit':limit}
        if status is not None:params['status']=status
        if after is not None:params['after']=after
        listing=(await self.request('GET','tasks',params=params)).json()
        return {**listing,'requests':journal.pending()}

    async def task(self,task_id,wait_seconds):
        if not re.fullmatch(r'task-[a-f0-9]{32}',task_id):raise ValueError('Invalid task ID')
        if type(wait_seconds) is not int or not 0<=wait_seconds<=20:raise ValueError('wait_seconds must be 0..20')
        deadline=asyncio.get_running_loop().time()+wait_seconds
        while True:
            state=(await self.request('GET','tasks/'+task_id)).json()
            if state['status']=='completed':
                fid=state['result']['file_id']
                if not re.fullmatch(r'file-[a-f0-9]{32}',fid):raise RuntimeError('Invalid result file ID')
                response=await self.request('GET','files/'+fid+'/content')
                data=response.content
                target=self.output_dir/(fid+'.png')
                save_png_atomically(target,data)
                return [TextContent(type='text',text=json.dumps({'task_id':task_id,'status':'completed','saved_path':str(target),'model':state['result'].get('model')},ensure_ascii=False)),
                        ImageContent(type='image',mimeType='image/png',data=base64.b64encode(data).decode())]
            if state['status'] in ('failed','cancelled'):
                raise RuntimeError('Image task '+state['status']+': '+str(state.get('error') or ''))
            if asyncio.get_running_loop().time()>=deadline:return [TextContent(type='text',text=json.dumps(state,ensure_ascii=False))]
            await asyncio.sleep(1)

    async def cancel(self,task_id):
        if not re.fullmatch(r'task-[a-f0-9]{32}',task_id):raise ValueError('Invalid task ID')
        return (await self.request('POST','tasks/'+task_id+'/cancel')).json()


def build_server(bridge):
    server=FastMCP('Spark image tools',instructions='本地生图和图片编辑。先 generate_image/edit_image 获取任务ID，再 get_image_task 等待并展示返回的图片。提交响应丢失或重启时先 list_image_tasks 找回原request_id/任务ID，同一意图重试传原request_id；明确新创作使用新request_id。下载或保存失败只重试 get_image_task。首次加载或切换可能需要数分钟，queued/running不是失败，不要因80秒或几轮查询而自动取消；用户要求取消时再调用取消工具。真实商品精确外观优先使用透明PNG前景合成。生成和编辑结果均需检查商标、乱码文字、商品结构与材质；缺陷需修正后再交付。')

    @server.tool()
    async def generate_image(prompt:str,size:str='1024x1024',seed:int=0,title:str='',foreground_path:str='',request_id:str|None=None)->dict:
        """生成配图/电商背景。恢复同一创作传原request_id，新创作省略此值。foreground_path 为透明商品PNG路径，title 为准确排版标题。"""
        return await bridge.generate(prompt,size,seed,title,foreground_path,request_id=request_id)

    @server.tool()
    async def edit_image(prompt:str,image_paths:list[str],size:str='1024x1024',quality:str='fast',seed:int=0,request_id:str|None=None)->dict:
        """编辑1至3张本地图片。恢复同一创作传原request_id，新创作省略。fast=4步，standard=20步，high=40步。"""
        return await bridge.edit(prompt,image_paths,size,quality,seed,request_id=request_id)

    @server.tool()
    async def list_image_tasks(status:str|None=None,after:str|None=None,limit:int=20)->dict:
        """找回本人任务（状态筛选及分页）和本地request_id映射。日志丢失仍能列出服务端任务；用get_image_task续取，只在用户明确要求时取消。"""
        return await bridge.list_tasks(status,after,limit)

    @server.tool(structured_output=False)
    async def get_image_task(task_id:str,wait_seconds:int=20)->list[TextContent|ImageContent]:
        """查询生图/编辑进度，最多等20秒；完成时返回可展示的图片及本地保存路径。queued/running 时继续调用本工具，不要重新提交。"""
        return await bridge.task(task_id,wait_seconds)

    @server.tool()
    async def cancel_image_task(task_id:str)->dict:
        """取消排队或运行中的生图/编辑任务。"""
        return await bridge.cancel(task_id)
    return server


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    config_path=Path(args.config).expanduser().resolve();config=json.loads(config_path.read_text())
    def relative(name):
        p=Path(config[name]).expanduser();return p if p.is_absolute() else config_path.parent/p
    token=relative('api_key_file').read_text().strip()
    output=relative('output_dir') if 'output_dir' in config else Path('~/Pictures/Spark Agent').expanduser()
    journal=relative('journal_path') if 'journal_path' in config else config_path.parent/'requests.sqlite3'
    bridge=ImageBridge(config['base_url'],token,relative('ca_file'),output,journal_path=journal)
    build_server(bridge).run(transport='stdio')

if __name__=='__main__':main()
