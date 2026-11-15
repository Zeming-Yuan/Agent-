"""Eight-hour server-only mixed smoke test. Does not claim business/accuracy acceptance."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
import ssl
import subprocess
import time
import httpx

BASE=Path(__file__).resolve().parents[1]
ctx=ssl.create_default_context(cafile=str(BASE/'certificates/agent-root-ca.crt'))
client=httpx.Client(base_url='https://192.168.10.77:18443',verify=ctx,trust_env=False,timeout=180,
                    headers={'Authorization':'Bearer '+(BASE/'.private/agent-api.key').read_text().strip()})
RUN=BASE/'evidence/soak-server-8h';RUN.mkdir(exist_ok=True)
started=time.monotonic();deadline=started+8*3600
count=0;failures=0

def memory():
    local=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))/1024**2
    r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','spark01',"awk '/MemAvailable/ {print $2}' /proc/meminfo"],text=True,capture_output=True,timeout=10)
    return {'spark02_available_gib':round(local,2),'spark01_available_gib':round(int(r.stdout.strip())/1024**2,2) if r.returncode==0 else None}


def text():
    t=time.monotonic()
    r=client.post('/v1/chat/completions',json={'model':'spark-main','messages':[{'role':'user','content':'请用两句话说明：本地模型服务如何配合 Agent 工具使用？'}],'max_tokens':128,'temperature':0})
    r.raise_for_status();data=r.json()
    assert data['choices'][0]['message'].get('content')
    return {'elapsed_seconds':round(time.monotonic()-t,3),'usage':data.get('usage')}


def audio():
    with (BASE/'.private/samples/chinese-asr.wav').open('rb') as f:
        r=client.post('/v1/audio/transcriptions',files={'file':('sample.wav',f)},data={'model':'whisper-large-v3-turbo','language':'zh','response_format':'verbose_json'})
    r.raise_for_status();return r.json()


def media(index):
    kind='video' if index%2 else 'pdf'
    source=BASE/('.private/samples/blue-video.mp4' if kind=='video' else '.private/samples/invoice.pdf')
    with source.open('rb') as f:r=client.post('/v1/files',files={'file':(source.name,f)})
    r.raise_for_status();fid=r.json()['id']
    task=client.post('/v1/tasks',json={'kind':kind,'file_id':fid},headers={'Idempotency-Key':f'server-soak-{int(started)}-{index}'})
    task.raise_for_status();tid=task.json()['id']
    limit=time.monotonic()+180
    while time.monotonic()<limit:
        r=client.get('/v1/tasks/'+tid);r.raise_for_status();body=r.json()
        if body['status'] in ('failed','cancelled'):raise RuntimeError('Background task '+body['status'])
        if body['status']=='completed':
            if kind=='pdf':
                assert '128.50' in body['result']['pages'][0]['text']
            else:
                assert body['result']['frames'][0]['description'] and body['result']['transcript']
            client.delete('/v1/files/'+fid).raise_for_status()
            return {'task_id':tid,'status':body['status'],'kind':kind}
        time.sleep(.5)
    raise TimeoutError('Background media task timeout')

with (RUN/'events.jsonl').open('a',buffering=1) as log:
    while time.monotonic()<deadline:
        count+=1;stamp=datetime.now(timezone.utc).isoformat()
        entry={'at':stamp,'iteration':count,'memory':memory()}
        try:
            healthy=client.get('/health');healthy.raise_for_status();entry['health']=healthy.json()
            if any(v is None or v<20 for v in entry['memory'].values()):
                raise RuntimeError('Available memory below required 20GiB reserve')
            with ThreadPoolExecutor(max_workers=3) as pool:
                a=pool.submit(text);b=pool.submit(audio);c=pool.submit(media,count)
                entry['text']=a.result();entry['audio']=b.result();entry['media']=c.result()
            if count%10==0:
                # Exercise resident Omni under the same bounded background queue.
                with (BASE/'.private/samples/tone.wav').open('rb') as f:r=client.post('/v1/files',files={'file':('tone.wav',f)})
                r.raise_for_status();fid=r.json()['id']
                t=client.post('/v1/tasks',json={'kind':'audio_understand','file_id':fid});t.raise_for_status();tid=t.json()['id']
                limit=time.monotonic()+180
                while time.monotonic()<limit:
                    state=client.get('/v1/tasks/'+tid).json()
                    if state['status']=='completed':
                        client.delete('/v1/files/'+fid);entry['omni']={'task_id':tid,'status':'completed'};break
                    if state['status'] in ('failed','cancelled'):raise RuntimeError('Omni task failed')
                    time.sleep(1)
                else:raise TimeoutError('Omni task timeout')
            entry['status']='passed'
        except Exception as exc:
            failures+=1;entry['status']='failed';entry['error_type']=type(exc).__name__
        log.write(json.dumps(entry,ensure_ascii=False)+'\n')
        summary={'scope':'server-only synthetic mixed smoke; not desktop business/accuracy acceptance',
                 'elapsed_seconds':round(time.monotonic()-started,1),'iterations':count,'failures':failures,
                 'status':'running','last_event':stamp}
        (RUN/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
        if entry['status']=='failed' and (any(v is None or v<20 for v in entry['memory'].values()) or failures>=3):
            summary['status']='stopped_on_failure';break
        time.sleep(min(60,max(0,deadline-time.monotonic())))
    else:summary['status']='completed' if failures==0 else 'completed_with_failures'
summary['elapsed_seconds']=round(time.monotonic()-started,1)
(RUN/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False),flush=True)
