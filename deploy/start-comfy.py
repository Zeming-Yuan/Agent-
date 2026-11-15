"""Run ComfyUI with the validated GB10 image codec path.

This NGC runtime's cuDNN Conv3D path corrupts Qwen VAE reconstruction;
GPU cuDNN-disabled and CPU reference MAE agree (~1 versus ~122 before).
The transformer still uses CUDA/PyTorch SDPA. See VAE regression evidence.
"""
import os
from pathlib import Path
import runpy
import sys
import torch

torch.backends.cudnn.enabled=False
sys.path.insert(0,'/opt/ComfyUI')
restore_observer = None
if os.getenv('IMAGE_TELEMETRY_DIR'):
    sys.path.insert(0, '/opt/agent-mm')
    from comfy_lifecycle_probe import install_on_worker_start, runtime_identity
    from services.image_telemetry import host_identity, write_private_jsonl
    runtime_hash, descriptor = runtime_identity(Path('/opt/ComfyUI'),
        image_id=os.getenv('IMAGE_RUNTIME_ID'), argv=sys.argv[1:])
    host_id = host_identity()
    if host_id is None: raise RuntimeError('Host identity unavailable for observation')
    write_private_jsonl(os.environ['IMAGE_TELEMETRY_DIR'], 'environment.jsonl',
        {'host_id': host_id, 'runtime_hash': runtime_hash, 'descriptor': descriptor})
    restore_observer = install_on_worker_start(os.environ['IMAGE_TELEMETRY_DIR'],
        host_id=host_id, runtime_hash=runtime_hash)
try:
    runpy.run_path('/opt/ComfyUI/main.py',run_name='__main__')
finally:
    if restore_observer is not None: restore_observer()

