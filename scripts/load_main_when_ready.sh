#!/usr/bin/env bash
set -euo pipefail
cd /home/clusteradmin/Desktop/Agent多模态服务
while [ ! -f evidence/main-image-verified.json ]; do
    if ! systemctl --user is-active --quiet agent-mm-fetch-main-image; then
        echo 'Image acquisition stopped before verification' >&2
        exit 1
    fi
    sleep 5
done
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes spark01 docker load < .private/image-cache/main-arm64.docker.tar
ssh -o BatchMode=yes spark01 'docker image inspect sha256:991978a4dce45d28da78551777d949da90dbff03228c2f0fc98a8affe19ab4ca --format "{{.Id}} {{.Architecture}}"'
