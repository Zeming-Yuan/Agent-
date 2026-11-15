#!/usr/bin/env bash
set -euo pipefail
cd /home/clusteradmin/Desktop/Agent多模态服务
for ((i=0;i<120;i++)); do
 if python3 scripts/status.py | python3 -c 'import json,sys;raise SystemExit(json.load(sys.stdin).get("health_http")!=200)'; then
  exec "$@"
 fi
 sleep 5
done
echo 'Backend readiness timeout' >&2
exit 1
