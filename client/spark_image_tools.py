"""Mac/Linux stdio MCP bridge for the private Spark image service."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import ssl
import uuid
from pathlib import Path
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent
if __package__:
    from .request_journal import RequestJournal
else:
    from request_journal import RequestJournal


class ImageBridge:
    def __init__(self,base_url,token,ca_path,output_dir,*,journal_path=None,transport=None):
        if not base_url.startswith('https://') or not base_url.rstrip('/').endswith('/v1'):
            raise ValueError('Use the HTTPS service URL ending in /v1')
        self.output_dir=Path(output_dir).expanduser()
        self.service=str(httpx.URL(base_url.rstrip('/')))
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
        if foreground_path:options['foreground_file_id']=await self.upload(foreground_path)
        payload={'kind':'image_generate','options':options}
        journal=await self.journal()
        request_id=request_id if request_id is not None else str(uuid.uuid4())
        fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        journal.prepare(request_id,fingerprint,payload)
        result=(await self.request('POST','tasks',json=payload,headers={'Idempotency-Key':request_id})).json()
        journal.accepted(request_id,result['id'])
        return {**result,'request_id':request_id}

    async def edit(self,prompt,image_paths,size,quality,seed):
        if not 1<=len(image_paths)<=3:raise ValueError('Use 1 to 3 local image paths')
        ids=[await self.upload(path) for path in image_paths]
        return (await self.request('POST','tasks',json={'kind':'image_edit','options':{
            'prompt':prompt,'image_ids':ids,'size':size,'quality':quality,'seed':seed}})).json()

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
                if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data)>32*1024*1024:raise RuntimeError('Invalid image response')
                self.output_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
                target=self.output_dir/(fid+'.png')
                target.write_bytes(data);target.chmod(0o600)
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
    server=FastMCP('Spark image tools',instructions='本地生图和图片编辑。先 generate_image/edit_image 获取任务ID，再 get_image_task 等待并展示返回的图片；不要重复提交。首次加载或切换可能需要数分钟，queued/running不是失败，不要因80秒或几轮查询而自动取消；用户要求取消时再调用取消工具。真实商品精确外观优先使用透明PNG前景合成。生成和编辑结果均需检查商标、乱码文字、商品结构与材质；缺陷需修正后再交付。')

    @server.tool()
    async def generate_image(prompt:str,size:str='1024x1024',seed:int=0,title:str='',foreground_path:str='',request_id:str|None=None)->dict:
        """生成配图/电商背景，返回任务ID。foreground_path 可指定透明商品PNG的本地绝对路径，原图合成保留外观；title 为准确排版的标题。请在提示词描述主体、构图、材质、光线和留白。"""
        return await bridge.generate(prompt,size,seed,title,foreground_path,request_id=request_id)

    @server.tool()
    async def edit_image(prompt:str,image_paths:list[str],size:str='1024x1024',quality:str='fast',seed:int=0)->dict:
        """上传1至3张本地图片并编辑，返回任务ID。用于换背景、修改颜色/材质、按指令编辑及多图融合。prompt 明确需要修改和保留的内容；默认fast=4步加速，standard=20步原版，high=40步原版较慢。"""
        return await bridge.edit(prompt,image_paths,size,quality,seed)

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
    bridge=ImageBridge(config['base_url'],token,relative('ca_file'),Path(config.get('output_dir','~/Pictures/Spark Agent')).expanduser())
    build_server(bridge).run(transport='stdio')

if __name__=='__main__':main()
