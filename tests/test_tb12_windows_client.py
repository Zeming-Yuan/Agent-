from client.windows.configure import make_config


def test_tb12_windows_unicode_paths_are_separate_argv():
    root = r"C:\Users\Tester\图片 工具"
    config = r"C:\Users\Tester\个人 配置.json"

    plugin = make_config(root, config)["config"]

    assert plugin["command"] == root + r"\.venv\Scripts\python.exe"
    assert plugin["args"] == [root + r"\spark_image_tools.py", "--config", config]
    assert plugin["transport"] == "stdio"
    assert plugin["cwd"] == root
