#!/usr/bin/env bash
set -euo pipefail
cd /home/clusteradmin/Desktop/Agent多模态服务
image="$(cat .private/runtime-image-id)"
mkdir -p .private/runtime
docker run --name agent-mm-gateway-runtime --network host --read-only --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges --memory 2g --pids-limit 128 \
  --mount "type=bind,src=$PWD/services,dst=/work/services,readonly" \
  --mount "type=bind,src=$PWD/.private/runtime,dst=/work/.private/runtime" \
  --mount "type=bind,src=$PWD/.private/agent-api.key,dst=/work/.private/agent-api.key,readonly" \
  --mount "type=bind,src=$PWD/.private/main-api.key,dst=/work/.private/main-api.key,readonly" \
  --mount type=bind,src=/usr/share/fonts/opentype/noto,dst=/usr/share/fonts/opentype/noto,readonly \
  --env AUDIO_ENABLED=0 --env IMAGES_ENABLED=1 \
  --env MAIN_TOKEN_FILE=/work/.private/main-api.key --env MAIN_CONTEXT_TOKENS=200000 --env OMP_NUM_THREADS=2 \
  --workdir /work --entrypoint python "$image" -m uvicorn services.gateway:application --factory \
  --host 127.0.0.1 --port 18008 --workers 1 --limit-concurrency 16 --no-access-log
