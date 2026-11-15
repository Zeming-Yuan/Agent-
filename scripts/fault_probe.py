from pathlib import Path
import json,time,ssl
import httpx
base=Path(__file__).resolve().parents[1]
ctx=ssl.create_default_context(cafile=str(base/'certificates/agent-root-ca.crt'))
client=httpx.Client(base_url='https://192.168.10.77:18443',verify=ctx,trust_env=False,timeout=120,
 headers={'Authorization':'Bearer '+(base/'.private/agent-api.key').read_text().strip()})
result={}
result['unauthenticated']=httpx.get('https://192.168.10.77:18443/v1/models',verify=ctx,trust_env=False).status_code
result['wrong_key']=client.get('/v1/models',headers={'Authorization':'Bearer wrong'}).status_code
try:
 httpx.get('https://192.168.10.77:18443/v1/models',verify=True,trust_env=False)
 result['untrusted_ca_rejected']=False
except httpx.ConnectError:
 result['untrusted_ca_rejected']=True
result['internal_main_unauthenticated']=httpx.get('http://127.0.0.1:18010/v1/models',trust_env=False).status_code
raw=b'{"model":"spark-main","messages":[{"role":"user","content":"hi"}],"temperature":NaN}'
result['invalid_number']=[client.post('/v1/chat/completions',content=raw,headers={'Content-Type':'application/json'}).status_code for _ in range(2)]
for _ in range(2):
 with client.stream('POST','/v1/chat/completions',json={'model':'spark-main','messages':[{'role':'user','content':'请详细介绍局域网中的多模态模型服务。'}],'max_tokens':256}) as response:
  response.raise_for_status()
  next(response.iter_lines())
 time.sleep(.2)
result['stream_disconnects_exercised']=2
fid=json.loads((base/'.private/acceptance-video-task.json').read_text())['file_id']
r=client.post('/v1/tasks',json={'kind':'video','file_id':fid});r.raise_for_status();tid=r.json()['id']
for _ in range(200):
 state=client.get('/v1/tasks/'+tid).json()
 if state['status']=='running':break
 time.sleep(.05)
assert state['status']=='running'
result['cancel_running_task']=client.post('/v1/tasks/'+tid+'/cancel').json()['status']
time.sleep(.3)
result['cancel_persisted']=client.get('/v1/tasks/'+tid).json()['status']
r=client.post('/v1/chat/completions',json={'model':'spark-main','messages':[{'role':'user','content':'请只回答：恢复正常'}],'max_tokens':32,'temperature':0});r.raise_for_status()
result['subsequent_chat']={'status':r.status_code,'text':r.json()['choices'][0]['message']['content']}
assert result['unauthenticated']==401 and result['wrong_key']==401 and result['untrusted_ca_rejected']
assert result['internal_main_unauthenticated']==401 and result['invalid_number']==[422,422]
assert result['cancel_persisted']=='cancelled'
(base/'evidence/fault-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
