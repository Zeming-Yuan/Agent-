import sys
sys.path.insert(0,'/opt/ComfyUI')
import json,time,gc
from pathlib import Path
import numpy as np
from PIL import Image
import torch
from comfy.cli_args import args
args.use_pytorch_cross_attention=True
args.disable_dynamic_vram=True
import comfy.sd,comfy.utils
p=Path('/work/evidence/image-deploy-20261114');source=np.asarray(Image.open(p/'samples/00.png').convert('RGB').resize((512,512)),dtype=np.float32)/255
pixels=torch.from_numpy(source.copy()).unsqueeze(0)
results=[]
for device,dtype,cudnn in [('cuda',torch.bfloat16,False)]:
 torch.backends.cudnn.enabled=cudnn
 started=time.monotonic()
 state=comfy.utils.load_torch_file('/models/vae/qwen_image_vae.safetensors',safe_load=True)
 vae=comfy.sd.VAE(sd=state,device=torch.device(device),dtype=dtype)
 with torch.inference_mode():
  latent=vae.encode(pixels);decoded=vae.decode(latent).cpu().float().numpy().reshape(-1,source.shape[0],source.shape[1],3)[0]
 mae=float(np.abs(source-decoded).mean()*255)
 Image.fromarray(np.clip(decoded*255,0,255).astype(np.uint8)).save(p/('samples/vae-probe-'+device+'-cudnn-'+str(cudnn)+'.png'))
 results.append({'device':device,'cudnn':cudnn,'dtype':str(dtype),'mae':mae,'seconds':time.monotonic()-started,'latent_shape':list(latent.shape)})
 print(results[-1],flush=True)
 del vae,state,latent,decoded;gc.collect();torch.cuda.empty_cache()
(p/'vae-bf16-safe-probe.json').write_text(json.dumps(results,indent=2))
