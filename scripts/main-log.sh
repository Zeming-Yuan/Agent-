#!/usr/bin/env bash
set -euo pipefail
# vLLM must never cause credentials to appear in this chat's diagnostic output.
ssh -o BatchMode=yes spark01 'journalctl --user -u agent-mm-main -n 80 --no-pager | python3 -c '\''from pathlib import Path; import sys; key=Path("/home/spark01/agent-multimodal-service/.private/main-api.key").read_text().strip(); print(sys.stdin.read().replace(key,"[REDACTED]"))'\'''
