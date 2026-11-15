import hashlib
import json
from pathlib import Path
root=Path('/data/models/huggingface/Qwen3.6-35B-A3B-NVFP4')
weights=[]
for file in sorted(root.glob('model-*-of-*.safetensors')):
    metadata=(root/'.cache/huggingface/download'/(file.name+'.metadata')).read_text().splitlines()
    with file.open('rb') as f:
        sha=hashlib.file_digest(f,'sha256').hexdigest()
    if sha!=metadata[1]:
        raise RuntimeError('Cached model checksum mismatch: '+file.name)
    weights.append({'file':file.name,'sha256':sha,'bytes':file.stat().st_size,'revision':metadata[0]})
index=json.loads((root/'model.safetensors.index.json').read_text())
if set(index['weight_map'].values())!={w['file'] for w in weights}:
    raise RuntimeError('Missing shards')
output=Path('/home/spark01/agent-multimodal-service/evidence/main-weights-verified.json')
output.write_text(json.dumps({'weights':weights,'verified_against':'existing Hugging Face download metadata'},indent=2))
print('Verified',len(weights),'main-model shards')
