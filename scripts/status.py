"""Print only operational state; never print private tokens or keys."""
import json
from pathlib import Path
import ssl
import subprocess
import urllib.request
import urllib.error
BASE=Path(__file__).resolve().parents[1]
status={}
for name in ('gateway','https','tunnel','whisper','omni','image','image-memory-guard'):
    p=subprocess.run(['systemctl','--user','is-active','agent-mm-'+name],capture_output=True,text=True)
    status[name]=p.stdout.strip()
status['image_verified']=Path('/data/models/agent-mm-z-image-turbo/.verified.json').exists()
status['image_edit_verified']=Path('/data/models/agent-mm-z-image-turbo/.editor-verified.json').exists()
status['omni_verified']=Path('/data/models/huggingface/Qwen2.5-Omni-7B/.verified.json').exists()
status['main_archive_verified']=(BASE/'evidence/main-image-verified.json').exists()
try:
    ctx=ssl.create_default_context(cafile=str(BASE/'certificates/agent-root-ca.crt'))
    token=(BASE/'.private/agent-api.key').read_text().strip()
    req=urllib.request.Request('https://192.168.10.77:18443/health',headers={'Authorization':'Bearer '+token})
    try:
        r=urllib.request.urlopen(req,context=ctx,timeout=15)
    except urllib.error.HTTPError as e:
        r=e
    status['health_http']=r.status
    status['health']=json.load(r)
except Exception as exc:
    status['health_error']=type(exc).__name__
print(json.dumps(status,ensure_ascii=False,indent=2))
