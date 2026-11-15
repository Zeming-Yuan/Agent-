"""Optional BF16 four-step editor adapter, pinned and hash verified."""
import hashlib,json,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];E=BASE/'evidence/image-deploy-20261114';m=json.loads((E/'lightning-manifest.json').read_text())
root=Path('/data/models/agent-mm-z-image-turbo');p=root/'loras'/m['path'];p.parent.mkdir(exist_ok=True)
if not p.exists():
 partial=p.with_suffix('.partial');url=f"https://modelscope.cn/models/{m['repo']}/resolve/{m['revision']}/{m['path']}"
 subprocess.run(['curl','--http1.1','--fail','--location','--retry','8','--retry-all-errors','--connect-timeout','30','--max-time','900','--continue-at','-','--output',str(partial),url],check=True)
 partial.rename(p)
with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
assert digest==m['sha256'] and p.stat().st_size==m['size']
(E/'lightning-verified.json').write_text(json.dumps({**m,'local':str(p)},indent=2));print('VERIFIED',p.name,digest)
