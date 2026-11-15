#!/usr/bin/env bash
set -euo pipefail
cd /home/clusteradmin/Desktop/Agent多模态服务
for ((i=0;i<120;i++)); do
  if python3 scripts/status.py | python3 -c 'import json,sys;raise SystemExit(json.load(sys.stdin).get("health_http")!=200)'; then
    exec docker run --rm --network host --user "$(id -u):$(id -g)" \
      --mount "type=bind,src=$PWD,dst=/work" --workdir /work --entrypoint python \
      "$(cat .private/runtime-image-id)" scripts/desktop_api_probe.py
  fi
  sleep 5
done
echo 'Backends not ready within ten minutes' >&2
exit 1
