"""Run ComfyUI with the validated GB10 image codec path.

This NGC runtime's cuDNN Conv3D path corrupts Qwen VAE reconstruction;
GPU cuDNN-disabled and CPU reference MAE agree (~1 versus ~122 before).
The transformer still uses CUDA/PyTorch SDPA. See VAE regression evidence.
"""
import runpy
import sys
import torch

torch.backends.cudnn.enabled=False
sys.path.insert(0,'/opt/ComfyUI')
runpy.run_path('/opt/ComfyUI/main.py',run_name='__main__')
