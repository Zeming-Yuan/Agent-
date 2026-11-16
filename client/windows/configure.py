"""Build the Windows DeepSeek Harness stdio plugin configuration."""

import argparse
import json
from pathlib import PureWindowsPath


def make_config(install_dir: str, config_file: str) -> dict:
    """Return a plugin fragment whose executable and arguments stay separate.

    Windows paths are parsed independently of the host operating system so the
    generated JSON can be prepared and reviewed on another platform.
    """
    root = PureWindowsPath(install_dir)
    config = PureWindowsPath(config_file)
    if not root.is_absolute() or not config.is_absolute():
        raise ValueError("absolute Windows paths required")
    return {
        "id": "mcp-spark-images",
        "name": "@deepseek-ai/dsh-mcp-client",
        "config": {
            "serverName": "spark_images",
            "transport": "stdio",
            "command": str(root / ".venv" / "Scripts" / "python.exe"),
            "args": [str(root / "spark_image_tools.py"), "--config", str(config)],
            "cwd": str(root),
            "toolCallTimeoutMs": 60000,
            "failOnStartupError": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--config-file", required=True)
    args = parser.parse_args()
    print(json.dumps([make_config(args.install_dir, args.config_file)], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
