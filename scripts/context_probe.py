"""Count tokens using the actual server template, then verify a long HTTPS request."""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import time
import httpx
p=argparse.ArgumentParser();p.add_argument('--target',type=int,required=True);p.add_argument('--label',required=True);args=p.parse_args()
base=Path(__file__).resolve().parents[1]
internal=httpx.Client(base_url='http://127.0.0.1:18010',trust_env=False,timeout=600,
    headers={'Authorization':'Bearer '+(base/'.private/main-api.key').read_text().strip()})
public=httpx.Client(base_url='https://192.168.10.77:18443',trust_env=False,timeout=600,
    verify=ssl.create_default_context(cafile=str(base/'certificates/agent-root-ca.crt')),
    headers={'Authorization':'Bearer '+(base/'.private/agent-api.key').read_text().strip()})
unit='这是本地长上下文功能验证材料。记录编号一致，数据仅用于测试，不包含业务机密。\n'

def message(n):return [{'role':'user','content':unit*n+'\n请只回答LONG_CONTEXT_OK。'}]

def count(n):
    r=internal.post('/tokenize',json={'model':'spark-main','messages':message(n),'add_generation_prompt':True});r.raise_for_status();return r.json()['count']
lo,hi=0,max(3000,args.target//16+100)
while lo+1<hi:
    mid=(lo+hi)//2
    if count(mid)<=args.target:lo=mid
    else:hi=mid
messages=message(lo);prompt_tokens=count(lo)
t=time.monotonic()
r=public.post('/v1/chat/completions',json={'model':'spark-main','messages':messages,'max_tokens':64,'temperature':0});r.raise_for_status();body=r.json()
result={'label':args.label,'prompt_tokens_from_server_tokenizer':prompt_tokens,'requested_max_output_tokens':64,
        'elapsed_seconds':round(time.monotonic()-t,3),'usage':body.get('usage'),'response':body['choices'][0]['message']['content'],
        'prompt_sha256':hashlib.sha256(messages[0]['content'].encode()).hexdigest()}
assert body['usage']['prompt_tokens']>=args.target-100
assert 'LONG_CONTEXT_OK' in (result['response'] or '')
(base/'evidence'/f'context-{args.label}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
