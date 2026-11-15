#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
python_bin=''
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,11))'; then
    python_bin="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$python_bin" ]; then
  echo '需要 Python 3.11 或更新版本。请让本地 Agent 安装 Python 后重新运行本脚本。'
  exit 1
fi
"$python_bin" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod 600 api_key spark-image.json
.venv/bin/python - <<'PY'
import json
from pathlib import Path
root=Path.cwd()
# JSON strings are YAML-compatible quoted scalars, including spaces in Mac paths.
text="""- id: mcp-spark-images
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: spark_images
    transport: stdio
    command: %s
    args: [%s, '--config', %s]
    cwd: %s
    toolCallTimeoutMs: 60000
    failOnStartupError: false
""" % tuple(json.dumps(str(x),ensure_ascii=False) for x in [root/'.venv/bin/python',root/'spark_image_tools.py',root/'spark-image.json',root])
(root/'deepseek-harness-plugin.yaml').write_text(text)
print('安装完成。把 deepseek-harness-plugin.yaml 中的插件加入实际 Harness 配置。')
print('聊天继续使用 spark-main，并声明 text/image 输入能力；生图通过 MCP 工具调用。')
PY
