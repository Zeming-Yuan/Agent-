import json
import subprocess
import sys
from pathlib import Path

import pytest

from client.windows.configure import make_config


def test_tb12_windows_unicode_paths_are_separate_argv():
    root = r"C:\Users\Tester\图片 工具"
    config = r"C:\Users\Tester\个人 配置.json"

    plugin = make_config(root, config)["config"]

    assert plugin["command"] == root + r"\.venv\Scripts\python.exe"
    assert plugin["args"] == [root + r"\spark_image_tools.py", "--config", config]
    assert plugin["transport"] == "stdio"
    assert plugin["cwd"] == root


@pytest.mark.parametrize(
    "root,config",
    [
        (r"C:\A B\图片", r"C:\A B\个人.json"),
        (r"D:\工具", r"D:\配置.json"),
    ],
)
def test_tb12_config_roundtrip_does_not_embed_credentials(root, config):
    plugin = make_config(root, config)
    decoded = json.loads(json.dumps([plugin], ensure_ascii=False))[0]

    assert decoded["config"]["args"][-1] == config
    assert "api_key" not in json.dumps(plugin)
    assert "Authorization" not in json.dumps(plugin)


@pytest.mark.parametrize(
    "root,config",
    [("relative", r"C:\a.json"), (r"C:\tools", "a.json")],
)
def test_tb12_relative_install_paths_rejected(root, config):
    with pytest.raises(ValueError, match="absolute Windows paths"):
        make_config(root, config)


def test_tb12_configure_cli_emits_json_array_for_harness(tmp_path):
    script = Path(__file__).resolve().parents[1] / "client/windows/configure.py"
    root = r"C:\Users\Tester\Spark Image Tools"
    config = r"C:\Users\Tester\Spark Image Tools\private.json"

    result = subprocess.run(
        [sys.executable, str(script), "--install-dir", root, "--config-file", config],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list) and len(payload) == 1
    assert payload[0]["config"]["cwd"] == root


def test_tb12_install_script_has_private_update_and_preserving_uninstall_contract():
    script = (
        Path(__file__).resolve().parents[1] / "client/windows/install-windows.ps1"
    ).read_text()

    assert "$ErrorActionPreference = \"Stop\"" in script
    assert "Backup-ExistingConfig" in script
    assert "WindowsIdentity]::GetCurrent().User" in script
    assert "SetAccessRuleProtection($true, $false)" in script
    assert "Stage-Bridge" in script
    assert "client\\image-tools-requirements.txt" in script
    assert "ConfigFile is required" in script
    assert "ApiKeyFile is required" in script
    assert "Remove-Item -LiteralPath $venv" in script
    assert "Set-ExecutionPolicy" not in script
    readme = (Path(__file__).resolve().parents[1] / "client/windows/README.md").read_text()
    assert "保留配置、Key、日志和已保存图片" in readme
    assert "NODE_EXTRA_CA_CERTS" in readme
    assert "Out-File -Encoding UTF8" in readme
    assert "utf8NoBOM" not in readme


def test_tb12_private_bundle_has_clean_root_entrypoint_and_manifest(tmp_path):
    from scripts.build_image_client_bundle import build_bundle

    personal = tmp_path / "personal"
    personal.mkdir()
    (personal / "key").write_text("test-personal-credential")
    ca = Path(__file__).resolve().parents[1] / "certificates/agent-root-ca.crt"
    (personal / "ca.crt").write_bytes(ca.read_bytes())
    config = personal / "config.json"
    config.write_text(
        json.dumps(
            {
                "base_url": "https://spark.invalid/v1",
                "api_key_file": "key",
                "ca_file": "ca.crt",
            }
        )
    )
    target = tmp_path / "bundle.zip"
    build_bundle(config, {}, target)

    import zipfile

    with zipfile.ZipFile(target) as archive:
        archive.extractall(tmp_path / "unpacked")
    root = tmp_path / "unpacked" / "SparkImageTools"
    assert (root / "spark_image_tools.py").is_file()
    assert (root / "requirements.txt").is_file()
