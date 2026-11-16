"""Build the macOS DeepSeek Harness stdio plugin configuration."""

import argparse
import json
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


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


def validate_client_config(config_path: str | Path, api_key_file: str | Path) -> dict:
    """Validate the private endpoint and files used by the macOS bridge."""
    path = Path(config_path).expanduser().resolve()
    provided_key = Path(api_key_file).expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    url = urlsplit(data.get("base_url", ""))
    if (
        url.scheme != "https"
        or not url.hostname
        or url.path.rstrip("/") != "/v1"
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("base_url must be HTTPS /v1 without credentials, query, or fragment")
    for name in ("api_key_file", "ca_file"):
        value = data.get(name)
        if not value:
            raise ValueError(f"config missing {name}")
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = path.parent / candidate
        candidate = candidate.resolve()
        if not candidate.is_file():
            raise ValueError(f"config {name} does not exist: {candidate}")
        if name == "api_key_file" and candidate != provided_key:
            raise ValueError("--api-key-file must match config api_key_file")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir")
    parser.add_argument("--config-file")
    parser.add_argument("--validate-config")
    parser.add_argument("--api-key-file")
    args = parser.parse_args()
    if args.validate_config:
        if not args.api_key_file:
            parser.error("--api-key-file is required with --validate-config")
        validate_client_config(args.validate_config, args.api_key_file)
        return
    if not args.install_dir or not args.config_file:
        parser.error("--install-dir and --config-file are required")
    print(json.dumps([make_config(args.install_dir, args.config_file)], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
