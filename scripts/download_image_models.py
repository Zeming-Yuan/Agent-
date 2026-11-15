"""Fetch the pinned Comfy-Org Z-Image-Turbo bundle and verify every SHA-256."""
import concurrent.futures
import hashlib
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
manifest = json.loads((BASE/'evidence/image-deploy-20261114/model-manifest.json').read_text())
mirror = {x['Path']:x for x in json.loads((BASE/'evidence/image-deploy-20261114/modelscope-manifest.json').read_text())}
root = Path('/data/models/agent-mm-z-image-turbo')

def fetch(item):
    target = root / Path(item['rfilename']).relative_to('split_files')
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix('.partial')
    if not target.exists():
        revision = mirror[item['rfilename']]['Revision']
        url = f"https://modelscope.cn/models/Comfy-Org/z_image_turbo/resolve/{revision}/{item['rfilename']}"
        subprocess.run(['curl','--fail','--location','--retry','8','--retry-delay','3',
                        '--connect-timeout','30','--max-time','3600','--continue-at','-',
                        '--output',str(partial),url],check=True)
        partial.rename(target)
    digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    if target.stat().st_size != item['size'] or digest != item['lfs']['sha256']:
        raise RuntimeError(f'Integrity mismatch: {target.name}')
    print(f'VERIFIED {target.name} {target.stat().st_size} {digest}', flush=True)
    return {'path':str(target),'bytes':target.stat().st_size,'sha256':digest}

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results=list(pool.map(fetch,manifest['files']))
out={**manifest,'verified':results}
(root/'.verified.json').write_text(json.dumps(out,indent=2))
(BASE/'evidence/image-deploy-20261114/models-verified.json').write_text(json.dumps(out,indent=2))
