"""Pinned official checkpoint acquisition; local files are verified before ready marker."""
import hashlib
import json
import os
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download

REPO = 'Qwen/Qwen2.5-Omni-7B'
REV = 'ae9e1690543ffd5c0221dc27f79834d0294cba00'
ROOT = Path('/data/models/huggingface/Qwen2.5-Omni-7B')
print('Downloading', REPO, REV, 'HTTP transfer; Xet disabled', flush=True)
snapshot_download(repo_id=REPO, revision=REV, local_dir=ROOT,
                  allow_patterns=['*.json', '*.safetensors', '*.jinja', '*.tiktoken', '*.txt', '*.model'], max_workers=2)
manifest = []
for entry in HfApi().model_info(REPO, revision=REV, files_metadata=True).siblings:
    if not entry.rfilename.endswith('.safetensors'):
        continue
    path = ROOT / entry.rfilename
    digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
    expected = entry.lfs.sha256
    if digest != expected:
        raise RuntimeError(f'Checksum mismatch: {entry.rfilename}; remove only this file before retrying')
    manifest.append({'file': entry.rfilename, 'bytes': path.stat().st_size, 'sha256': digest})
    print('Verified', entry.rfilename, flush=True)
(ROOT / '.verified.json').write_text(json.dumps({'repo': REPO, 'revision': REV, 'weights': manifest}, indent=2))
print('CHECKPOINT VERIFIED', flush=True)
