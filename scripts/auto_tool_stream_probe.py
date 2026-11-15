from pathlib import Path
import json,ssl,time
import httpx
from openai import OpenAI
base=Path('/work')
client=OpenAI(base_url='https://192.168.10.77:18443/v1',api_key=(base/'.private/agent-api.key').read_text().strip(),
 http_client=httpx.Client(verify=ssl.create_default_context(cafile=str(base/'certificates/agent-root-ca.crt')),trust_env=False,timeout=180),max_retries=0)
tool={'type':'function','function':{'name':'lookup_stock','description':'查询商品当前库存，不能根据常识猜测库存。','parameters':{'type':'object','properties':{'sku':{'type':'string'}},'required':['sku']}}}
messages=[{'role':'user','content':'请使用库存查询工具查询 SKU ABC-123 的实时库存，不要猜测。'}]
calls={};content='';started=time.monotonic()
for chunk in client.chat.completions.create(model='spark-main',messages=messages,tools=[tool],tool_choice='auto',parallel_tool_calls=False,max_tokens=256,temperature=0,stream=True):
 if not chunk.choices:continue
 delta=chunk.choices[0].delta
 content+=delta.content or ''
 for item in delta.tool_calls or []:
  current=calls.setdefault(item.index,{'id':'','type':'function','function':{'name':'','arguments':''}})
  current['id']+=item.id or ''
  if item.function:
   current['function']['name']+=item.function.name or ''
   current['function']['arguments']+=item.function.arguments or ''
assert len(calls)==1,(content,calls)
call=calls[0];assert call['id'] and call['function']['name']=='lookup_stock'
assert json.loads(call['function']['arguments'])=={'sku':'ABC-123'}
messages.append({'role':'assistant','content':content or None,'tool_calls':[call]})
messages.append({'role':'tool','tool_call_id':call['id'],'content':'{"sku":"ABC-123","available":17}'})
answer=client.chat.completions.create(model='spark-main',messages=messages,tools=[tool],max_tokens=256,temperature=0)
text=answer.choices[0].message.content
assert '17' in (text or '')
result={'streamed_tool_calls':list(calls.values()),'answer':text,'elapsed_seconds':round(time.monotonic()-started,3),'fixture':'Test-only inventory result17; no external business action executed'}
(base/'evidence/tool-auto-stream-roundtrip.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
