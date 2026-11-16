"""Build the macOS DeepSeek Harness stdio plugin configuration."""

import argparse
import json
from pathlib import PurePosixPath


def make_config(install_dir: str, config_file: str) -> dict:
    """Return a plugin fragment with paths kept in separate argv fields."""
    root = PurePosixPath(install_dir)
    config = PurePosixPath(config_file)
    if not root.is_absolute() or not config.is_absolute():
        raise ValueError("absolute macOS paths required")
    return {
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
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--config-file", required=True)
    args = parser.parse_args()
    print(json.dumps([make_config(args.install_dir, args.config_file)], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
