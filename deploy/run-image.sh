#!/usr/bin/env bash
set -euo pipefail
cd /home/clusteradmin/Desktop/Agent多模态服务
image="$(cat .private/image-runtime/image-id)"
mkdir -p .private/runtime/comfy/{input,output,temp,user}
chmod 700 .private/runtime/comfy
# Files are admitted only after download SHA256 verification has completed.
test -f /data/models/agent-mm-z-image-turbo/.verified.json
observation_args=()
if [[ -n "${IMAGE_TELEMETRY_DIR:-}" ]]; then
  mkdir -p "$IMAGE_TELEMETRY_DIR"
  chmod 700 "$IMAGE_TELEMETRY_DIR"
  observation_args+=(--mount "type=bind,src=$IMAGE_TELEMETRY_DIR,dst=/observations")
  observation_args+=(--mount "type=bind,src=/etc/machine-id,dst=/host-machine-id,readonly")
  observation_args+=(--mount "type=bind,src=$PWD/deploy/comfy_lifecycle_probe.py,dst=/opt/comfy_lifecycle_probe.py,readonly")
  observation_args+=(--mount "type=bind,src=$PWD/services,dst=/opt/agent-mm/services,readonly")
  observation_args+=(--env "IMAGE_RUNTIME_ID=$image")
  observation_args+=(--env IMAGE_TELEMETRY_DIR=/observations --env IMAGE_HOST_ID_FILE=/host-machine-id)
fi
docker run "${observation_args[@]}" --name agent-mm-image --gpus all --network host --ipc private --shm-size 2g \
  --user "$(id -u):$(id -g)" --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g \
  --cap-drop ALL --security-opt no-new-privileges --memory 75g --memory-swap 75g --pids-limit 256 \
  --mount type=bind,src=/data/models/agent-mm-z-image-turbo,dst=/opt/ComfyUI/models,readonly \
  --mount "type=bind,src=$PWD/.private/runtime/comfy,dst=/runtime" \
  --mount "type=bind,src=$PWD/deploy/start-comfy.py,dst=/opt/start-comfy.py,readonly" \
  --entrypoint python \
  --env HOME=/runtime/user --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
  --env HF_HOME=/runtime/user/huggingface --env TORCHINDUCTOR_CACHE_DIR=/runtime/temp/torchinductor \
  --env TRITON_CACHE_DIR=/runtime/temp/triton --env OMP_NUM_THREADS=4 \
  "$image" /opt/start-comfy.py --listen 127.0.0.1 --port 18013 --disable-auto-launch --disable-api-nodes \
  --disable-all-custom-nodes --disable-metadata --disable-dynamic-vram --cache-ram 20 \
  --use-pytorch-cross-attention --bf16-text-enc --reserve-vram 20 --preview-method none --max-upload-size 12 \
  --input-directory /runtime/input --output-directory /runtime/output --temp-directory /runtime/temp \
  --user-directory /runtime/user --database-url sqlite:////runtime/user/comfyui.db
