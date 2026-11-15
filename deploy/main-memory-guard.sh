#!/usr/bin/env bash
set -euo pipefail
while true; do
  if systemctl --user is-active --quiet agent-mm-main; then
    available_kib="$(awk '/MemAvailable/ {print $2}' /proc/meminfo)"
    if (( available_kib < 20971520 )); then
      echo "MEMORY_RESERVE_STOP MemAvailable=${available_kib}KiB; stopping this project's main model"
      systemctl --user stop agent-mm-main
    fi
  fi
  sleep 2
done
