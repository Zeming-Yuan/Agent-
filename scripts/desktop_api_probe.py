"""Run in the pinned runtime image (OpenAI SDK included), mounting source/CA/key."""
import json
import ssl
import time
from pathlib import Path
import httpx
from openai import OpenAI

BASE=Path('/work')
ctx=ssl.create_default_context(cafile=str(BASE/'certificates/agent-root-ca.crt'))
client=OpenAI(base_url='https://192.168.10.77:18443/v1',api_key=(BASE/'.private/agent-api.key').read_text().strip(),
              http_client=httpx.Client(verify=ctx,trust_env=False,timeout=180),max_retries=0)
results={}
results['models']=[m.id for m in client.models.list().data]
t=time.monotonic()
answer=client.chat.completions.create(model='spark-main',messages=[{'role':'user','content':'请只回答：局域网模型接入成功'}],temperature=0,max_tokens=64)
results['chat']={'elapsed_seconds':round(time.monotonic()-t,3),'text':answer.choices[0].message.content,'usage':answer.usage.model_dump()}
chunks=[];first=None;t=time.monotonic()
for chunk in client.chat.completions.create(model='spark-main',messages=[{'role':'user','content':'请用一句话说明什么是 HTTPS。'}],temperature=0,max_tokens=100,stream=True):
    content=chunk.choices[0].delta.content if chunk.choices else None
    if content:
        if first is None:first=time.monotonic()-t
        chunks.append(content)
results['stream']={'first_content_seconds':round(first,3) if first else None,'text':''.join(chunks)}
tool={'type':'function','function':{'name':'lookup_stock','description':'查询本地仓库库存','parameters':{'type':'object','properties':{'sku':{'type':'string'}},'required':['sku']}}}
messages=[{'role':'user','content':'请查一下SKU ABC-123的库存。'}]
reply=client.chat.completions.create(model='spark-main',messages=messages,tools=[tool],tool_choice={'type':'function','function':{'name':'lookup_stock'}},temperature=0,max_tokens=256)
message=reply.choices[0].message
assert message.tool_calls and message.tool_calls[0].function.name=='lookup_stock'
call=message.tool_calls[0];arguments=json.loads(call.function.arguments)
assert arguments['sku']=='ABC-123'
messages.append(message.model_dump(exclude_none=True))
messages.append({'role':'tool','tool_call_id':call.id,'content':'{"sku":"ABC-123","available":17}'})
final=client.chat.completions.create(model='spark-main',messages=messages,tools=[tool],temperature=0,max_tokens=256)
results['tool_roundtrip']={'tool_id':call.id,'arguments':arguments,'answer':final.choices[0].message.content,'fixture':'本地固定测试库存17；未连接真实库存系统'}
assert '17' in (final.choices[0].message.content or '')
(BASE/'evidence/openai-sdk-acceptance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps(results,ensure_ascii=False,indent=2))
