#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/spark_image_tools.py" ]]; then
  # Private bundles place the bridge and requirements beside this installer.
  ROOT_DIR="$SCRIPT_DIR"
else
  # The source checkout keeps platform assets under client/mac/.
  ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
ACTION="install"
CONFIG_FILE=""
API_KEY_FILE=""

usage() {
  cat >&2 <<'EOF'
Usage: install-mac.command [--action install|update|uninstall]
       [--install-dir ABSOLUTE_DIR] --config-file ABSOLUTE_JSON
       --api-key-file ABSOLUTE_KEY
EOF
}

while (($#)); do
  case "$1" in
    --action)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      ACTION="$2"
      shift 2
      ;;
    --install-dir)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      mkdir -p "$2"
      ROOT_DIR="$(cd "$2" && pwd)"
      shift 2
      ;;
    --config-file)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      CONFIG_FILE="$2"
      shift 2
      ;;
    --api-key-file)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      API_KEY_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage >&1
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

case "$ACTION" in
  install|update|uninstall) ;;
  *) echo "Unknown action: $ACTION" >&2; exit 2 ;;
esac

if [[ "$ACTION" == "uninstall" ]]; then
  rm -rf "$ROOT_DIR/.venv"
  rm -f "$ROOT_DIR/deepseek-harness-plugin.json"
  # requests.sqlite3, personal config, Key and ~/Pictures output images are never removed.
  echo "已卸载 Mac 图片客户端运行环境；个人配置、Key、请求日志和图片已保留。"
  exit 0
fi

[[ -n "$CONFIG_FILE" && -f "$CONFIG_FILE" ]] || {
  echo "需要存在的 --config-file 个人 JSON 配置。" >&2
  exit 2
}
[[ -n "$API_KEY_FILE" && -f "$API_KEY_FILE" ]] || {
  echo "需要存在的 --api-key-file 个人 Key 文件。" >&2
  exit 2
}

python_bin=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,11))'; then
    python_bin="$(command -v "$candidate")"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  echo '需要 Python 3.11 或更新版本。' >&2
  exit 1
fi

require_config_paths() {
  "$python_bin" - "$CONFIG_FILE" "$API_KEY_FILE" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

path = Path(sys.argv[1]).expanduser().resolve()
provided_key = Path(sys.argv[2]).expanduser().resolve()
data = json.loads(path.read_text(encoding="utf-8"))
url = urlsplit(data.get("base_url", ""))
if url.scheme != "https" or not url.hostname or url.path.rstrip("/") != "/v1":
    raise SystemExit("base_url must be an HTTPS /v1 URL")
for key in ("api_key_file", "ca_file"):
    value = data.get(key)
    if not value:
        raise SystemExit(f"config missing {key}")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = path.parent / candidate
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise SystemExit(f"config {key} does not exist: {candidate}")
    if key == "api_key_file" and candidate != provided_key:
        raise SystemExit("--api-key-file must match config api_key_file")
PY
}

require_config_paths

backup_existing_config() {
  [[ "$ACTION" == "update" && -f "$CONFIG_FILE" ]] || return 0
  local stamp backup
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup="${CONFIG_FILE}.bak.${stamp}"
  cp -p -- "$CONFIG_FILE" "$backup"
  chmod 600 -- "$backup"
}

stage_bridge() {
  local bridge="$ROOT_DIR/spark_image_tools.py"
  [[ -f "$bridge" ]] && return 0
  [[ -f "$ROOT_DIR/client/spark_image_tools.py" ]] || {
    echo "缺少公共 spark_image_tools.py，不能安装。" >&2
    exit 2
  }
  cat > "$bridge" <<'PY'
from client.spark_image_tools import main

if __name__ == "__main__":
    main()
PY
  chmod 600 -- "$bridge"
}

backup_existing_config
stage_bridge

requirements="$ROOT_DIR/requirements.txt"
[[ -f "$requirements" ]] || requirements="$ROOT_DIR/client/image-tools-requirements.txt"
[[ -f "$requirements" ]] || { echo "缺少图片客户端依赖清单。" >&2; exit 2; }

umask 077
"$python_bin" -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/python" -m pip install -r "$requirements"
chmod 600 -- "$CONFIG_FILE" "$API_KEY_FILE"

"$ROOT_DIR/.venv/bin/python" - "$ROOT_DIR" "$CONFIG_FILE" "$ROOT_DIR/deepseek-harness-plugin.json" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
config = Path(sys.argv[2]).resolve()
output = Path(sys.argv[3])
payload = [{
    "id": "mcp-spark-images",
    "name": "@deepseek-ai/dsh-mcp-client",
    "config": {
        "serverName": "spark_images",
        "transport": "stdio",
        "command": str(root / ".venv" / "bin" / "python"),
        "args": [str(root / "spark_image_tools.py"), "--config", str(config)],
        "cwd": str(root),
        "toolCallTimeoutMs": 60000,
        "failOnStartupError": False,
    },
}]
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
output.chmod(0o600)
PY

echo "Mac 图片客户端 $ACTION 完成：$ROOT_DIR"
echo "请把 deepseek-harness-plugin.json 导入实际 Harness；Python bridge 与 Harness 网络进程分别配置 CA。"
