#!/usr/bin/env bash
set -euo pipefail
cd /home/spark01/agent-multimodal-service
image='sha256:991978a4dce45d28da78551777d949da90dbff03228c2f0fc98a8affe19ab4ca'
# Preflight proves that the image is already present. No implicit unpinned pull.
docker image inspect "$image" >/dev/null
mkdir -p .private/cache-main
umask 077
python3 - <<'PY'
from pathlib import Path
key=Path('.private/main-api.key').read_text().strip()
Path('.private/main.env').write_text('VLLM_API_KEY='+key+'\nHF_HUB_OFFLINE=1\nTRANSFORMERS_OFFLINE=1\n')
PY
docker run --name agent-mm-main --gpus all --network host --ipc private --shm-size 4g \
  --env-file .private/main.env --mount "type=bind,src=$PWD/.private/cache-main,dst=/root/.cache" --mount type=bind,src=/data/models/huggingface/Qwen3.6-35B-A3B-NVFP4,dst=/model,readonly \
  "$image" /model --host 127.0.0.1 --port 18010 --served-model-name spark-main \
  --max-model-len "${MAIN_CONTEXT:-200000}" --gpu-memory-utilization 0.45 --kv-cache-memory-bytes "${MAIN_KV_CACHE_BYTES:-6442450944}" --max-num-seqs 2 \
  --max-num-batched-tokens 4096 --kv-cache-dtype fp8 --attention-backend flashinfer --moe-backend marlin \
  --load-format safetensors --enable-chunked-prefill --enable-prefix-caching --enforce-eager \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 \
  --limit-mm-per-prompt '{"image":4,"video":0}' --mm-processor-kwargs '{"max_pixels":1048576}' \
  --default-chat-template-kwargs '{"enable_thinking":false}'
