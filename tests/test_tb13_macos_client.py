import json
import subprocess
import sys
from client.mac.configure import make_config, validate_client_config
from pathlib import Path

import pytest


def test_tb13_macos_unicode_paths_are_separate_argv():
    root = "/Users/tester/Applications/图片 工具"
    config = "/Users/tester/个人 配置.json"

    plugin = make_config(root, config)["config"]

    assert plugin["command"] == root + "/.venv/bin/python"
    assert plugin["args"] == [root + "/spark_image_tools.py", "--config", config]
    assert plugin["cwd"] == root


@pytest.mark.parametrize(
    ("root", "config"),
    [
        ("/Users/a/图片 工具", "/Users/a/个人.json"),
        ("/Applications/Spark Tools", "/Users/a/config.json"),
    ],
)
def test_tb13_config_roundtrip_does_not_embed_credentials(root, config):
    payload = json.loads(json.dumps([make_config(root, config)], ensure_ascii=False))[0]
    encoded = json.dumps(payload, ensure_ascii=False)
    assert payload["config"]["args"][-1] == config
    assert "api_key" not in encoded
    assert "Authorization" not in encoded


@pytest.mark.parametrize(
    ("root", "config"), [("relative", "/a.json"), ("/tools", "relative.json")]
)
def test_tb13_relative_paths_rejected(root, config):
    with pytest.raises(ValueError, match="absolute macOS paths"):
        make_config(root, config)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user:pass@example.test/v1",
        "https://example.test/v1?token=leak",
        "https://example.test/v1#fragment",
    ],
)
def test_tb13_personal_config_rejects_url_credentials_query_and_fragment(tmp_path, base_url):
    key = tmp_path / "key"
    ca = tmp_path / "ca.crt"
    key.write_text("personal-key")
    ca.write_text("fixture-ca")
    config = tmp_path / "personal.json"
    config.write_text(
        json.dumps(
            {
                "base_url": base_url,
                "api_key_file": str(key),
                "ca_file": str(ca),
            }
        )
    )

    with pytest.raises(ValueError, match="credentials, query, or fragment"):
        validate_client_config(config, key)


def test_tb13_configure_cli_emits_json_array_for_harness():
    script = Path(__file__).resolve().parents[1] / "client/mac/configure.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--install-dir",
            "/Users/tester/Spark Image Tools",
            "--config-file",
            "/Users/tester/个人.json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list) and len(payload) == 1
    assert payload[0]["config"]["cwd"] == "/Users/tester/Spark Image Tools"


def test_tb13_install_script_preserves_private_state_and_uses_explicit_inputs():
    script = (Path(__file__).resolve().parents[1] / "client/mac/install-mac.command").read_text()
    assert "set -euo pipefail" in script
    assert "--config-file" in script
    assert "--api-key-file" in script
    assert "源码 checkout 安装必须显式提供 --install-dir" in script
    assert "Backup-ExistingConfig" not in script
    assert "backup_existing_config" in script
    assert "stage_bridge" in script
    assert "client/image-tools-requirements.txt" in script
    assert "requests.sqlite3" in script
    assert "Pictures" in script
    assert "api_key spark-image.json" not in script
    assert '"$CONFIGURER"' in script
    assert "deepseek-harness-plugin.json" in script


def test_tb13_install_script_is_valid_shell_and_readme_explains_two_ca_processes():
    install = Path(__file__).resolve().parents[1] / "client/mac/install-mac.command"
    result = subprocess.run(["bash", "-n", str(install)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    readme = (Path(__file__).resolve().parents[1] / "client/mac/README.md").read_text()
    assert "保留配置、Key、请求日志和图片" in readme
    assert "NODE_EXTRA_CA_CERTS" in readme
    assert "个人 Key" in readme
    assert "保存失败" in readme


def test_tb13_source_checkout_rejects_repo_install_dir():
    install = Path(__file__).resolve().parents[1] / "client/mac/install-mac.command"
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "bash",
            str(install),
            "--action",
            "install",
            "--install-dir",
            str(repo),
            "--config-file",
            "/tmp/missing-personal.json",
            "--api-key-file",
            "/tmp/missing-key",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "源码 checkout" in result.stderr
