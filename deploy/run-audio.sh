#!/usr/bin/env bash
set -euo pipefail
cd /home/clusteradmin/Desktop/Agent多模态服务
mode="${1:?whisper or omni}"
case "$mode" in
  whisper) model='/whisper/snapshots/41f01f3fe87f28c78e2fbf8b568835947dd65ed9'; port=18011 ;;
  omni) model='/omni'; port=18012; test -f /data/models/huggingface/Qwen2.5-Omni-7B/.verified.json ;;
  *) exit 2 ;;
esac
image="$(cat .private/runtime-image-id)"
docker image inspect "$image" >/dev/null
docker run --name "agent-mm-$mode" --gpus all --network host --ipc private --shm-size 2g \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=512m --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$PWD/services,dst=/work/services,readonly" \
  --mount type=bind,src=/home/clusteradmin/.cache/huggingface/hub/models--openai--whisper-large-v3-turbo,dst=/whisper,readonly \
  --mount type=bind,src=/data/models/huggingface/Qwen2.5-Omni-7B,dst=/omni,readonly \
  --env "AUDIO_MODEL=$mode" --env "AUDIO_MODEL_PATH=$model" --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
  --env HF_HOME=/tmp/huggingface --env TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor --env TRITON_CACHE_DIR=/tmp/triton --env NUMBA_CACHE_DIR=/tmp/numba --env OMP_NUM_THREADS=4 --workdir /work --entrypoint python \
  "$image" -m uvicorn services.audio_backend:app --host 127.0.0.1 --port "$port" --workers 1 --limit-concurrency 4 --backlog 8 --no-access-log
